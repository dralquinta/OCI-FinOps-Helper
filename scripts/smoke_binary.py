"""Offline validation of an actual binary with Python/OCI absent from PATH."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def smoke(binary):
    binary = Path(binary).resolve()
    with tempfile.TemporaryDirectory(prefix='finops-binary-smoke-') as directory:
        directory = Path(directory)
        empty_path = directory / 'empty-path'
        empty_path.mkdir()
        environment = {key: value for key, value in os.environ.items() if not key.startswith('OCI_')}
        environment.update({'PATH': str(empty_path), 'HOME': str(directory), 'OCI_CLI_AUTH': 'api_key', 'OCI_CLI_CONFIG_FILE': str(directory / 'missing-config')})
        for arguments in [['--help'], ['--internal-oci', '--version'], ['--internal-oci', 'compute', 'instance', 'get', '--help'], ['--internal-oci', 'optimizer', 'resource-action-summary', 'list', '--help'], ['--internal-oci', 'monitoring', 'metric-data', 'summarize-metrics-data', '--help']]:
            result = subprocess.run([str(binary), *arguments], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError(result.stderr + result.stdout)
            print('PASS: ' + ' '.join(arguments), flush=True)
        cache = directory / 'cache'
        cache.mkdir()
        cache_payload = '{"version": 1, "entries": {}}'
        (cache / 'instance_metadata_cache.json').write_text(cache_payload)
        result = subprocess.run([str(binary), 'example-tenancy', 'us-ashburn-1', '2026-01-01', '2026-02-01', '--skip-cost', '--skip-usage', '--skip-enrichment', '--skip-recommendations', '--cache-dir', str(cache)], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
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
        assert missing_config.returncode != 0, 'Missing OCI configuration must fail locally'
        assert 'API call failed: Abort:' in missing_config.stdout, 'Embedded OCI child must reach local missing-config prompt and abort on EOF'
        assert len(list(directory.glob('*.tar.gz'))) == 1, 'Failed OCI child must not emit an archive'
        assert (cache / 'instance_metadata_cache.json').read_text() == cache_payload
        print('PASS: frozen OCI child reached local config error without archive/cache overwrite', flush=True)
        extraction = directory / 'suite'
        result = subprocess.run([str(binary), '--extract-suite', str(extraction)], env=environment, cwd=directory, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr + result.stdout)
        assert (extraction / 'LICENSE').is_file()
        assert {'growth_trends_analysis.ipynb', 'finops_analysis.ipynb', 'exadata_analysis.ipynb'} <= {path.name for path in (extraction / 'jupe-note').glob('*.ipynb')}
        print('PASS: standalone help, embedded OCI CLI, collection tar.gz inspection, failure status and suite extraction; PATH has no Python/OCI.')


if __name__ == '__main__':
    smoke(sys.argv[1])
