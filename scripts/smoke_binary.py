"""Offline validation of an actual binary with Python/OCI absent from PATH."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import selectors
import signal
import time


def offline_commands():
    """Load every collector service without configuration or network access."""
    commands = [('iam', 'region', 'list'), ('compute', 'instance', 'get'),
                ('bv', 'volume', 'list'), ('usage-api', 'usage-summary', 'request-summarized-usages'),
                ('optimizer', 'resource-action-summary', 'list'),
                ('search', 'resource', 'structured-search'),
                ('monitoring', 'metric-data', 'summarize-metrics-data'),
                ('audit', 'event', 'list'), ('events', 'rule', 'list')]
    return [['--help'], ['--internal-oci', '--version']] + [
        ['--internal-oci', *command, '--help'] for command in commands]


def smoke_worker(binary, environment, directory):
    requests = [['iam', 'region', 'list', '--help'],
                ['compute', 'instance', 'get', '--help'],
                ['iam', 'region', 'list', '--help'],
                ['iam', 'region', 'list']]
    result = subprocess.run([str(binary), '--internal-oci-worker'],
                            input=''.join(json.dumps({'arguments': arguments}) + '\n' for arguments in requests),
                            env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr + result.stdout)
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == len(requests), 'Persistent CLI must return each response'
    assert all(row['returncode'] == 0 and row['stdout'] for row in responses[:3]), 'Persistent CLI command failed'
    assert responses[0]['stdout'] == responses[2]['stdout'], 'Repeated service help must remain unchanged'
    failure = responses[3]
    assert isinstance(failure['returncode'], int) and failure['returncode'] != 0, \
        'Local worker authentication failure must have a numeric exit status'
    assert any(marker in failure['stderr'] for marker in ('Abort:', 'Aborted!', 'Could not find config file')), \
        'Worker authentication failure must preserve stderr diagnostics'


def smoke_empty_inventory(binary, environment, directory):
    """Exercise frozen OCI rendering through signed requests to localhost only."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = directory / 'synthetic-api-key.pem'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.TraditionalOpenSSL,
                         serialization.NoEncryption()))
    key_path.chmod(0o600)
    config = directory / 'synthetic-config'
    config.write_text('[DEFAULT]\nuser=ocid1.user.oc1..synthetic\n'
                      'tenancy=ocid1.tenancy.oc1..synthetic\n'
                      'fingerprint=' + ':'.join(['00'] * 16) + '\n'
                      'region=us-ashburn-1\nkey_file=' + str(key_path) + '\n')
    config.chmod(0o600)
    requests = []
    class InventoryHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path.startswith('/20160918/volumes?'), self.path
            requests.append(self.path)
            rows = [] if len(requests) != 2 else [{'id': 'ocid1.volume.oc1..synthetic',
                                                   'displayName': 'synthetic-volume'}]
            body = json.dumps(rows).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('opc-request-id', 'synthetic-request')
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *arguments):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), InventoryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        arguments = ['bv', 'volume', 'list', '--compartment-id', 'ocid1.compartment.oc1..synthetic',
                     '--endpoint', endpoint, '--all', '--output', 'json']
        isolated = dict(environment, OCI_CLI_CONFIG_FILE=str(config), NO_PROXY='127.0.0.1',
                        no_proxy='127.0.0.1')
        result = subprocess.run([str(binary), '--internal-oci-worker'],
                                input=''.join(json.dumps({'arguments': arguments}) + '\n' for _ in range(3)),
                                env=isolated, cwd=directory, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(responses) == 3 and len(requests) == 3, 'Each command must reach local fixture'
        assert all(response['returncode'] == 0 for response in responses), responses
        for response in (responses[0], responses[2]):
            text = response['stdout'].strip()
            assert not text or json.loads(text)['data'] == [], 'Empty inventory must stay empty'
        assert json.loads(responses[1]['stdout'])['data'][0]['id'] == 'ocid1.volume.oc1..synthetic'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def check_missing_config(result):
    assert result.returncode != 0, 'Missing OCI configuration must fail locally'
    diagnostic = result.stdout + result.stderr
    assert not any(marker in diagnostic for marker in ('ImportError', 'ModuleNotFoundError')), \
        'Embedded OCI dependencies must load successfully'
    assert any(marker in diagnostic for marker in ('Abort:', 'Aborted!', 'Could not find config file')), \
        'Embedded OCI must reach local missing-config diagnostics, rather than fail to import'
    assert 'Collection failed; no success archive created.' in diagnostic, \
        'Local authentication failure must propagate to collection status'


def smoke_feedback(binary, environment, directory):
    """Observe flushed output through a pipe before the controlled run finishes."""
    arguments = ['--tenancy-ocid', 'example-tenancy', '--home-region', 'us-ashburn-1',
                 '--from', '2026-01-01', '--to', '2026-01-02', '--no-growth-collection',
                 '--skip-usage', '--skip-enrichment', '--skip-recommendations',
                 '--cache-dir', str(Path(directory) / 'feedback-cache')]
    process = subprocess.Popen([str(binary), *arguments], env=environment, cwd=directory,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline, output = time.monotonic() + 120, b''
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b'[status] Preparing collection' not in output:
                remaining = deadline - time.monotonic()
                assert remaining > 0, 'No flushed startup feedback before deadline'
                if not selector.select(remaining):
                    raise AssertionError('No flushed startup feedback before deadline')
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    raise AssertionError('Collection exited without flushed startup feedback')
                output = (output + chunk)[-8192:]
        assert process.poll() is None, 'Feedback appeared only after collection completed'
        process.communicate(timeout=120)
        assert process.returncode != 0, 'Missing-config feedback probe must fail locally'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        process.stdout.close()


def smoke(binary):
    binary = Path(binary).resolve()
    with tempfile.TemporaryDirectory(prefix='finops-binary-smoke-') as directory:
        directory = Path(directory)
        empty_path = directory / 'empty-path'
        empty_path.mkdir()
        environment = {key: value for key, value in os.environ.items() if not key.startswith('OCI_')}
        environment.update({'PATH': str(empty_path), 'HOME': str(directory), 'OCI_CLI_AUTH': 'api_key', 'OCI_CLI_CONFIG_FILE': str(directory / 'missing-config')})
        smoke_feedback(binary, environment, directory)
        print('PASS: startup feedback is flushed while collection is still running', flush=True)
        for arguments in offline_commands():
            result = subprocess.run([str(binary), *arguments], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError(result.stderr + result.stdout)
            if arguments == ['--help']:
                for option in ('--tenancy-ocid', '--home-region', '--from', '--to', '--no-growth-collection'):
                    assert option in result.stdout, 'Binary help must expose ' + option
            print('PASS: ' + ' '.join(arguments), flush=True)
        smoke_worker(binary, environment, directory)
        print('PASS: persistent embedded CLI repeats services without import/registration loss', flush=True)
        smoke_empty_inventory(binary, environment, directory)
        print('PASS: frozen OCI worker renders empty/nonempty/empty inventory from localhost fixture', flush=True)
        cache = directory / 'cache'
        cache.mkdir()
        cache_payload = '{"version": 1, "entries": {}}'
        (cache / 'instance_metadata_cache.json').write_text(cache_payload)
        result = subprocess.run([str(binary), '--tenancy-ocid', 'example-tenancy', '--home-region', 'us-ashburn-1', '--from', '2026-01-01', '--to', '2026-02-01', '--no-growth-collection', '--skip-cost', '--skip-usage', '--skip-enrichment', '--skip-recommendations', '--cache-dir', str(cache)], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr + result.stdout)
        archives = list(directory.glob('*.tar.gz'))
        assert len(archives) == 1, 'Binary must emit exactly one collection archive'
        with tarfile.open(archives[0]) as archive:
            members = archive.getmembers()
            assert all(member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts for member in members)
            manifest = json.load(archive.extractfile('output/collection-manifest.json'))
            assert manifest['status'] == 'success'
            assert archive.extractfile('output/instance_metadata_cache.json').read().decode() == cache_payload
        assert (cache / 'instance_metadata_cache.json').read_text() == cache_payload
        print('PASS: runtime archive and persistent cache seed inspected', flush=True)
        failure = subprocess.run([str(binary), 'invalid-arguments'], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
        assert failure.returncode != 0, 'Invalid collection must fail'
        assert len(list(directory.glob('*.tar.gz'))) == 1, 'Failed collection must not emit an archive'
        # Exercise frozen parent -> OCI child dispatch with guaranteed local auth failure.
        missing_config = subprocess.run([str(binary), 'example-tenancy', 'us-ashburn-1', '2026-01-01', '2026-02-01', '--only-recommendations', '--cache-dir', str(cache)], env=environment, cwd=directory, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        check_missing_config(missing_config)
        assert len(list(directory.glob('*.tar.gz'))) == 1, 'Failed OCI child must not emit an archive'
        assert (cache / 'instance_metadata_cache.json').read_text() == cache_payload
        print('PASS: frozen OCI child reached local config error without archive/cache overwrite', flush=True)
        extraction = directory / 'suite'
        result = subprocess.run([str(binary), '--extract-suite', str(extraction)], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr + result.stdout)
        assert (extraction / 'LICENSE').is_file()
        assert (extraction / 'src/collector.py').is_file()
        assert (extraction / 'src/distribution.py').is_file()
        assert (extraction / 'src/utils/recommendations.py').is_file()
        assert {'growth_trends_analysis.ipynb', 'finops_analysis.ipynb', 'exadata_analysis.ipynb'} <= {path.name for path in (extraction / 'jupe-note').glob('*.ipynb')}
        print('PASS: standalone help, embedded OCI CLI, collection tar.gz inspection, failure status and suite extraction; PATH has no Python/OCI.')


if __name__ == '__main__':
    smoke(sys.argv[1])
