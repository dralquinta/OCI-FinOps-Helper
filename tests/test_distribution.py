import contextlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from src.distribution import archive_outputs, extract_suite, oci_command, run_collection, main


class DistributionTests(unittest.TestCase):
    def test_startup_feedback_is_flushed_before_blocked_cache_copy(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        entered, release, flushed = threading.Event(), threading.Event(), threading.Event()
        class Output(io.StringIO):
            def flush(self):
                if 'Preparing collection' in self.getvalue():
                    flushed.set()
                super().flush()
        output = Output()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            (root / 'cache/instance_metadata_cache.json').write_text('{"entries": {}}')
            original_copy = __import__('shutil').copyfile
            def copy(source, destination):
                entered.set()
                release.wait(timeout=2)
                return original_copy(source, destination)
            with contextlib.redirect_stdout(output), patch('src.distribution.shutil.copyfile', side_effect=copy):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    result = executor.submit(run_collection, [], root / 'archives', lambda: None,
                                             cache_dir=root / 'cache')
                    try:
                        self.assertTrue(entered.wait(timeout=1), 'Cache copy did not start')
                        self.assertTrue(flushed.is_set(), 'Startup feedback was not flushed before cache copy')
                        self.assertFalse(result.done())
                    finally:
                        release.set()
                    self.assertEqual(0, result.result(timeout=2))

    def test_archive_feedback_is_flushed_before_blocked_compression(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        from src.utils.feedback import progress_heartbeat
        entered, release, flushed = threading.Event(), threading.Event(), threading.Event()
        heartbeat = threading.Event()
        class Output(io.StringIO):
            def flush(self):
                if 'Creating collection archive' in self.getvalue():
                    flushed.set()
                if 'Creating collection archive: still working' in self.getvalue():
                    heartbeat.set()
                super().flush()
        output = Output()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def archive(source, destination):
                entered.set()
                release.wait(timeout=2)
                destination.write_bytes(b'archive')
            with contextlib.redirect_stdout(output), patch('src.distribution.archive_outputs', side_effect=archive), \
                    patch('src.utils.feedback.progress_heartbeat',
                          side_effect=lambda label: progress_heartbeat(label, interval=0.01)):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    result = executor.submit(run_collection, [], root / 'archives', lambda: None,
                                             cache_dir=root / 'cache')
                    try:
                        self.assertTrue(entered.wait(timeout=1), 'Archive compression did not start')
                        self.assertTrue(flushed.is_set(), 'Archive feedback was not flushed before compression')
                        self.assertTrue(heartbeat.wait(timeout=1), 'Blocked compression has no heartbeat')
                        self.assertFalse(result.done())
                    finally:
                        release.set()
                    self.assertEqual(0, result.result(timeout=2))

    def test_named_collection_arguments_create_archive_with_default_growth(self):
        arguments = ['--tenancy-ocid', 'ocid1.tenancy.oc1..test',
                     '--home-region', 'us-ashburn-1',
                     '--from-date', '2026-01-01', '--to-date', '2026-02-01']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def collect(**flags):
                self.assertTrue(flags['growth_collection'])
                Path('output/result.json').write_text('{"complete": true}')
                return True
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()), \
                    patch('src.collector.OCICostCollector.collect', side_effect=collect) as collection:
                status = main(['--archive-dir', str(root / 'archives'),
                               '--cache-dir', str(root / 'cache'), *arguments])
            self.assertEqual(0, status)
            collection.assert_called_once()
            archives = list((root / 'archives').glob('*.tar.gz'))
            self.assertEqual(1, len(archives))
            with tarfile.open(archives[0]) as archive:
                self.assertIn('output/result.json', archive.getnames())

    def test_source_keeps_external_oci_command(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(['oci', 'iam', 'region', 'list'], oci_command(['oci', 'iam', 'region', 'list']))

    def test_frozen_routes_oci_to_same_binary(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', '/binary/helper'):
            self.assertEqual(['/binary/helper', '--internal-oci', '--version'], oci_command(['oci', '--version']))

    def test_success_isolates_outputs_and_archives_relative_members(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            def collect():
                self.assertNotEqual(previous, Path.cwd())
                Path('output').mkdir()
                Path('output/report.json').write_text('{"items": []}')
                raise SystemExit(0)
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_collection(['tenancy', 'region', '2026-01-01', '2026-02-01'], Path(directory), collect)
            self.assertEqual(0, result)
            self.assertEqual(previous, Path.cwd())
            archives = list(Path(directory).glob('*.tar.gz'))
            self.assertEqual(1, len(archives))
            with tarfile.open(archives[0]) as archive:
                self.assertIn('output/report.json', archive.getnames())
                self.assertTrue(all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in archive.getnames()))

    def test_failed_collection_has_no_success_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            def collect():
                Path('output').mkdir()
                Path('output/partial.json').write_text('{}')
                raise SystemExit(2)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, run_collection([], Path(directory), collect))
            self.assertEqual([], list(Path(directory).glob('*.tar.gz')))

    def test_archive_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'output').mkdir()
            (root / 'secret').write_text('outside')
            (root / 'output/link').symlink_to(root / 'secret')
            with self.assertRaises(ValueError):
                archive_outputs(root / 'output', root / 'result.tar.gz')
            self.assertFalse((root / 'result.tar.gz').exists())

    def test_help_forwards_without_collecting_or_creating_archive(self):
        with patch('src.collector.main', side_effect=SystemExit(0)) as collector, patch('src.distribution.run_collection') as run:
            self.assertEqual(0, main(['--help']))
            collector.assert_called_once()
            run.assert_not_called()

    def test_internal_oci_forwards_arguments_and_status(self):
        with patch('src.distribution.invoke_oci', return_value=7) as cli:
            self.assertEqual(7, main(['--internal-oci', 'iam', 'region', 'list']))
            cli.assert_called_once_with(['iam', 'region', 'list'])


class AssetTests(unittest.TestCase):
    def test_notebook_outputs_metadata_and_customer_ids_are_removed(self):
        from scripts.prepare_assets import sanitize_notebook
        notebook = {'metadata': {'widgets': {'secret': 'value'}}, 'cells': [
            {'cell_type': 'code', 'metadata': {'private': 'data'}, 'execution_count': 3,
             'source': ['tenancy = "ocid1.tenancy.oc1..customersecret"\n'],
             'outputs': [{'text': ['customer cost data']}]}]}
        clean = sanitize_notebook(notebook)
        self.assertEqual([], clean['cells'][0]['outputs'])
        self.assertIsNone(clean['cells'][0]['execution_count'])
        self.assertEqual({}, clean['metadata'])
        self.assertNotIn('customersecret', json.dumps(clean))
        self.assertNotIn('customer cost data', json.dumps(clean))

    def test_asset_allowlist_excludes_credentials_and_runtime_outputs(self):
        from scripts.prepare_assets import asset_sources
        root = Path(__file__).resolve().parents[1]
        files = asset_sources(root)
        self.assertTrue(any(path.suffix == '.ipynb' for path in files))
        self.assertTrue(all(not {'.aws', '.oci', 'output', 'customer_files', 'fixes'} & set(path.relative_to(root).parts) for path in files))


class ExtractionSafetyTests(unittest.TestCase):
    def test_symlinked_destination_parent_cannot_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'embedded/suite/docs').mkdir(parents=True)
            (root / 'embedded/suite/docs/guide.md').write_text('guide')
            (root / 'destination').mkdir()
            (root / 'external').mkdir()
            (root / 'destination/docs').symlink_to(root / 'external', target_is_directory=True)
            with patch.object(sys, '_MEIPASS', str(root / 'embedded'), create=True):
                with self.assertRaises(ValueError):
                    extract_suite(root / 'destination')
            self.assertFalse((root / 'external/guide.md').exists())


class EmbeddedOCILoaderTests(unittest.TestCase):
    def test_frozen_service_loader_uses_unpack_directory(self):
        from types import SimpleNamespace
        from src.distribution import configure_oci_loader
        loader = SimpleNamespace(services_dir='/wrong/services', python_cli_root_dir='/wrong')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', '/binary-assets', create=True):
            configure_oci_loader(loader)
        self.assertEqual('/binary-assets/services', loader.services_dir)
        self.assertEqual('/binary-assets', loader.python_cli_root_dir)


class OCIInitializationTests(unittest.TestCase):
    def test_persistent_worker_finalizes_service_callbacks_once(self):
        from types import ModuleType, SimpleNamespace
        from unittest.mock import Mock
        from src.distribution import invoke_oci
        package = ModuleType('oci_cli')
        package.__path__ = []
        package.dynamic_loader = SimpleNamespace(load_service_from_command=Mock())
        callback = Mock()
        package.final_command_processor = SimpleNamespace(
            process=Mock(side_effect=callback), add_shortcuts=Mock(),
            SERVICE_FUNCTIONS_TO_EXECUTE=[callback])
        module = ModuleType('oci_cli.cli')
        module.cli = SimpleNamespace(main=Mock(side_effect=SystemExit(0)))
        with patch.dict(sys.modules, {'oci_cli': package, 'oci_cli.cli': module}), \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', '/binary-assets', create=True), \
                patch('src.distribution._persistent_worker', True, create=True), \
                patch('src.distribution._processed_oci_callbacks', set(), create=True):
            self.assertEqual(0, invoke_oci(['compute', '--help']))
            self.assertEqual(0, invoke_oci(['compute', '--help']))
        callback.assert_called_once_with()

    def test_service_loading_is_repeated_after_frozen_path_configuration(self):
        from types import ModuleType, SimpleNamespace
        from unittest.mock import Mock
        from src.distribution import invoke_oci
        package = ModuleType('oci_cli')
        package.__path__ = []
        loader = SimpleNamespace(services_dir='/wrong', python_cli_root_dir='/wrong', load_service_from_command=Mock())
        package.dynamic_loader = loader
        package.final_command_processor = SimpleNamespace(process=Mock())
        module = ModuleType('oci_cli.cli')
        module.cli = SimpleNamespace(main=Mock(side_effect=SystemExit(0)))
        observed = []
        loader.load_service_from_command.side_effect = lambda args: observed.append((loader.services_dir, list(args)))
        previous = sys.argv
        with patch.dict(sys.modules, {'oci_cli': package, 'oci_cli.cli': module}), patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', '/binary-assets', create=True):
            self.assertEqual(0, invoke_oci(['compute', '--help']))
        self.assertEqual([('/binary-assets/services', ['oci', 'compute', '--help'])], observed)
        self.assertIs(previous, sys.argv)
        package.final_command_processor.process.assert_called_once_with()


class PersistentCacheTests(unittest.TestCase):
    def test_persistent_cache_transfer_never_materializes_entire_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            payload = '{"entries": ' + ' ' * (1024 * 1024) + '{} }'
            (root / 'cache/instance_metadata_cache.json').write_text(payload)
            def collect():
                self.assertEqual(payload, Path('output/instance_metadata_cache.json').read_text())
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('Unbounded cache read')), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, run_collection([], root / 'archives', collect, cache_dir=root / 'cache'))
            self.assertEqual(payload, (root / 'cache/instance_metadata_cache.json').read_text())

    def test_second_invocation_is_seeded_with_successful_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def first():
                Path('output').mkdir(exist_ok=True)
                Path('output/instance_metadata_cache.json').write_text('{"cache": "first"}')
            def second():
                self.assertEqual('{"cache": "first"}', Path('output/instance_metadata_cache.json').read_text())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, run_collection([], root / 'archives', first, cache_dir=root / 'cache'))
                self.assertEqual(0, run_collection([], root / 'archives', second, cache_dir=root / 'cache'))

    def test_failed_collection_does_not_overwrite_persistent_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            (root / 'cache/instance_metadata_cache.json').write_text('original')
            def failed():
                Path('output/instance_metadata_cache.json').write_text('failed')
                raise SystemExit(1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, run_collection([], root / 'archives', failed, cache_dir=root / 'cache'))
            self.assertEqual('original', (root / 'cache/instance_metadata_cache.json').read_text())


class CacheSafetyTests(unittest.TestCase):
    def test_symlinked_persistent_cache_is_rejected_without_following(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            (root / 'external').write_text('private')
            (root / 'cache/instance_metadata_cache.json').symlink_to(root / 'external')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, run_collection([], root / 'archives', lambda: None, cache_dir=root / 'cache'))
            self.assertEqual('private', (root / 'external').read_text())
            self.assertEqual([], list((root / 'archives').glob('*.tar.gz')))


class SourceAssetTests(unittest.TestCase):
    def test_extracted_suite_contains_source_and_future_notebook_helpers_verbatim(self):
        import shutil
        import subprocess
        from scripts.prepare_assets import prepare
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'repository'
            source.mkdir()
            for name in ['README.md', 'LICENSE', 'collector.sh', 'requirements.txt']:
                shutil.copyfile(repository / name, source / name)
            shutil.copytree(repository / 'src', source / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            helper = source / 'src/utils/future_notebook_helper.py'
            helper.write_text('TYPE_PREFIX = "ocid1.instance."\n')
            (source / 'src/ignore.pyc').write_bytes(b'not source')
            (source / 'tests').mkdir()
            (source / 'tests/private_test.py').write_text('excluded')
            with patch('scripts.prepare_assets.metadata.distributions', return_value=[]):
                prepare(source, root / 'embedded/suite')
            with patch.object(sys, '_MEIPASS', str(root / 'embedded'), create=True):
                extract_suite(root / 'extracted')
            extracted = root / 'extracted'
            self.assertTrue((extracted / 'src/collector.py').is_file())
            self.assertTrue((extracted / 'src/distribution.py').is_file())
            self.assertEqual(helper.read_bytes(), (extracted / 'src/utils/future_notebook_helper.py').read_bytes())
            self.assertFalse((extracted / 'src/ignore.pyc').exists())
            self.assertFalse((extracted / 'tests').exists())
            result = subprocess.run([sys.executable, '-c', 'from src.utils.future_notebook_helper import TYPE_PREFIX; assert TYPE_PREFIX == "ocid1.instance."'], cwd=extracted, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
