"""Offline validation of an actual binary with Python/OCI absent from PATH."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


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


def check_missing_config(result):
    assert result.returncode != 0, 'Missing OCI configuration must fail locally'
    diagnostic = result.stdout + result.stderr
    assert not any(marker in diagnostic for marker in ('ImportError', 'ModuleNotFoundError')), \
        'Embedded OCI dependencies must load successfully'
    assert any(marker in diagnostic for marker in ('Abort:', 'Aborted!', 'Could not find config file')), \
        'Embedded OCI must reach local missing-config diagnostics, rather than fail to import'
    assert 'Collection failed; no success archive created.' in diagnostic, \
        'Local authentication failure must propagate to collection status'


def smoke(binary):
    binary = Path(binary).resolve()
    with tempfile.TemporaryDirectory(prefix='finops-binary-smoke-') as directory:
        directory = Path(directory)
        empty_path = directory / 'empty-path'
        empty_path.mkdir()
        environment = {key: value for key, value in os.environ.items() if not key.startswith('OCI_')}
        environment.update({'PATH': str(empty_path), 'HOME': str(directory), 'OCI_CLI_AUTH': 'api_key', 'OCI_CLI_CONFIG_FILE': str(directory / 'missing-config')})
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
