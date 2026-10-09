"""Standalone binary dispatch and safe collection archive delivery."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import uuid
import importlib.util
import threading
import shutil
try:
    from .oci_worker import OCIWorkerPool
except ImportError:  # Direct src/collector.py execution
    from oci_worker import OCIWorkerPool


_worker_pool = None
_worker_pool_users = 0
_worker_pool_lock = threading.RLock()
_persistent_worker = False
_processed_oci_callbacks = set()


def worker_available():
    return getattr(sys, 'frozen', False) or importlib.util.find_spec('oci_cli') is not None


@contextmanager
def oci_worker_pool(max_workers=4):
    """Reuse CLI interpreters only within an explicitly scoped collection."""
    global _worker_pool, _worker_pool_users
    if not worker_available():
        yield None
        return
    with _worker_pool_lock:
        if _worker_pool is None:
            _worker_pool = OCIWorkerPool(max_workers=max_workers)
        _worker_pool_users += 1
        active = _worker_pool
    try:
        yield active
    finally:
        with _worker_pool_lock:
            _worker_pool_users -= 1
            if _worker_pool_users == 0:
                _worker_pool = None
                active.close()


def oci_command(command):
    """Frozen builds invoke their embedded OCI CLI; source runs keep PATH lookup."""
    if getattr(sys, 'frozen', False) and command and command[0] == 'oci':
        return [sys.executable, '--internal-oci', *command[1:]]
    return command


def run_oci(command, **kwargs):
    supported = {'capture_output', 'text', 'timeout', 'check', 'encoding', 'errors', 'universal_newlines'}
    with _worker_pool_lock:
        pool = _worker_pool
    if pool is not None and command and command[0] == 'oci' and kwargs.get('capture_output') and not set(kwargs) - supported:
        return pool.run(command, **kwargs)
    return subprocess.run(oci_command(command), **kwargs)


def configure_oci_loader(loader):
    # OCI's frozen loader expects a cx_Freeze/MSI directory layout.
    # PyInstaller extracts service source assets into its own runtime directory.
    if getattr(sys, 'frozen', False):
        loader.python_cli_root_dir = sys._MEIPASS
        loader.services_dir = str(Path(sys._MEIPASS) / 'services')


def invoke_oci(arguments):
    original_arguments = sys.argv
    sys.argv = ['oci', *arguments]
    try:
        from oci_cli import dynamic_loader
        configure_oci_loader(dynamic_loader)
        dynamic_loader.load_service_from_command(sys.argv)
        if getattr(sys, 'frozen', False):
            from oci_cli import final_command_processor
            if _persistent_worker:
                final_command_processor.add_shortcuts()
                for callback in final_command_processor.SERVICE_FUNCTIONS_TO_EXECUTE:
                    if callback not in _processed_oci_callbacks:
                        callback()
                        _processed_oci_callbacks.add(callback)
            else:
                final_command_processor.process()
        from oci_cli.cli import cli
        try:
            cli.main(args=arguments, prog_name='oci', standalone_mode=True)
        except SystemExit as error:
            return error.code or 0
        return 0
    finally:
        sys.argv = original_arguments


def archive_outputs(output, destination):
    """Archive regular output files only, never follow links outside collection."""
    files = sorted(output.rglob('*'))
    for path in files:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Collection output contains an unsafe file: ' + str(path.name))
    temporary = destination.with_suffix(destination.suffix + '.partial')
    try:
        with tarfile.open(temporary, 'w:gz') as archive:
            for path in files:
                if path.is_file():
                    archive.add(path, arcname=str(Path('output') / path.relative_to(output)), recursive=False)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def checked_cache_file(cache_dir):
    target = cache_dir / 'instance_metadata_cache.json'
    if any(path.is_symlink() for path in [target, *target.parents]):
        raise ValueError('Metadata cache path must not contain symlinks.')
    if target.exists() and not target.is_file():
        raise ValueError('Metadata cache must be a regular file.')
    return target


def persist_cache(output, cache_dir):
    source = output / 'instance_metadata_cache.json'
    if source.is_symlink() or (source.exists() and not source.is_file()):
        raise ValueError('Collected metadata cache must be a regular file.')
    if not source.exists():
        return
    target = checked_cache_file(cache_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.cache-', delete=False) as stream:
            temporary = Path(stream.name)
            with source.open('rb') as original:
                shutil.copyfileobj(original, stream, length=1024 * 1024)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_collection(arguments, archive_dir, collector, cache_dir=None):
    # Import lazily: utils exports OCI callers that depend on this module.
    if __package__:
        from .utils.feedback import report_progress, progress_heartbeat
    else:
        from utils.feedback import report_progress, progress_heartbeat
    report_progress('[status] Preparing collection')
    archive_dir = Path(archive_dir).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir or Path.home() / '.cache' / 'oci-finops-helper').absolute()
    original_directory, original_arguments = Path.cwd(), sys.argv
    destination = None
    with tempfile.TemporaryDirectory(prefix='oci-finops-collection-') as directory:
        try:
            with progress_heartbeat('[status] Preparing collection'):
                persistent = checked_cache_file(cache_dir)
                if persistent.exists():
                    seeded_output = Path(directory) / 'output'
                    seeded_output.mkdir()
                    shutil.copyfile(persistent, seeded_output / persistent.name)
                os.chdir(directory)
                sys.argv = ['oci-finops-helper', *arguments]
            try:
                collector()
                status = 0
            except SystemExit as error:
                status = error.code or 0
            if status:
                print('Collection failed; no success archive created.', file=sys.stderr)
                return status if isinstance(status, int) else 1
            output = Path(directory) / 'output'
            output.mkdir(exist_ok=True)
            (output / 'collection-manifest.json').write_text(json.dumps({
                'status': 'success', 'created_at': datetime.now(timezone.utc).isoformat(),
                'files': sorted(str(path.relative_to(output)) for path in output.rglob('*') if path.is_file())
            }, indent=2))
            name = 'oci-finops-collection-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.tar.gz'
            destination = archive_dir / name
            report_progress('[status] Creating collection archive')
            with progress_heartbeat('[status] Creating collection archive'):
                archive_outputs(output, destination)
            report_progress('[status] Saving metadata cache')
            with progress_heartbeat('[status] Saving metadata cache'):
                persist_cache(output, cache_dir)
            report_progress('Collection archive: ' + str(destination))
            return 0
        except Exception as error:
            if destination is not None:
                destination.unlink(missing_ok=True)
            print('Collection failed; no success archive created: ' + str(error), file=sys.stderr)
            return 1
        finally:
            os.chdir(original_directory)
            sys.argv = original_arguments


def extract_suite(destination):
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'suite'
    if not assets.is_dir():
        raise ValueError('Embedded suite assets are available in the built binary.')
    destination = Path(destination).absolute()
    if any(path.is_symlink() for path in [destination, *destination.parents]):
        raise ValueError('Suite destination must not contain symlinks.')
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    for source in sorted(assets.rglob('*')):
        if source.is_file():
            target = destination / source.relative_to(assets)
            # Reject redirected directories before creating files.
            if any(path.is_symlink() for path in [target, *target.parents]):
                raise ValueError('Suite destination must not contain symlinks.')
            target.resolve().relative_to(destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(source.read_bytes())


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments[:1] == ['--internal-oci']:
        return invoke_oci(arguments[1:])
    if arguments[:1] == ['--internal-oci-worker']:
        from .oci_worker import serve
        return serve()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--archive-dir', default=str(Path.cwd()))
    parser.add_argument('--extract-suite')
    parser.add_argument('--cache-dir')
    options, collector_arguments = parser.parse_known_args(arguments)
    if options.extract_suite:
        try:
            extract_suite(options.extract_suite)
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
    from src.collector import main as collector
    if '--help' in collector_arguments or '-h' in collector_arguments:
        original_arguments = sys.argv
        try:
            sys.argv = ['oci-finops-helper', *collector_arguments]
            collector()
        except SystemExit as error:
            return error.code or 0
        finally:
            sys.argv = original_arguments
        return 0
    return run_collection(collector_arguments, options.archive_dir, collector, cache_dir=options.cache_dir)
