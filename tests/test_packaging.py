"""Packaging preserves runtime code while omitting duplicate SDK source data."""

from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import json
import subprocess
import os
import tempfile


class PackagingPolicyTests(unittest.TestCase):
    def build_spec(self):
        hooks = ModuleType('PyInstaller.utils.hooks')
        collections = {
            'oci_cli': ([('/cli/help.txt', 'oci_cli/help'), ('/cli/main.py', 'oci_cli')],
                        [], ['oci_cli.cli']),
            'oci': ([('/sdk/config.py', 'oci'), ('/sdk/signer.py', 'oci/auth'),
                     ('/sdk/cert.pem', 'oci'), ('/sdk/METADATA', 'oci.dist-info')],
                    [('/sdk/native.so', 'oci')], ['oci.config', 'oci.auth.signers']),
            'services': ([('/services/compute_cli.py', 'services/compute/src')],
                         [], ['services.compute.src.compute_cli']),
        }
        hooks.collect_all = lambda name: collections[name]
        analysis, executable = Mock(), Mock()
        root = Path(__file__).resolve().parents[1]
        with patch.dict(sys.modules, {'PyInstaller.utils.hooks': hooks}):
            runpy.run_path(str(root / 'packaging/collector.spec'), init_globals={
                'SPECPATH': str(root / 'packaging'), 'Analysis': analysis,
                'PYZ': Mock(), 'EXE': executable})
        return analysis.call_args.kwargs, executable.call_args.kwargs

    def test_sdk_source_is_not_duplicated_as_runtime_data(self):
        analysis, _ = self.build_spec()
        self.assertNotIn(('/sdk/config.py', 'oci'), analysis['datas'])
        self.assertNotIn(('/sdk/signer.py', 'oci/auth'), analysis['datas'])
        for item in [('/sdk/cert.pem', 'oci'), ('/sdk/METADATA', 'oci.dist-info'),
                     ('/cli/help.txt', 'oci_cli/help'),
                     ('/services/compute_cli.py', 'services/compute/src')]:
            self.assertIn(item, analysis['datas'])
        self.assertIn('oci.auth.signers', analysis['hiddenimports'])
        self.assertIn('services.compute.src.compute_cli', analysis['hiddenimports'])
        self.assertIn(('/sdk/native.so', 'oci'), analysis['binaries'])

    def test_native_libraries_preserve_wheel_elf_alignment(self):
        _, executable = self.build_spec()
        self.assertFalse(executable['strip'])


class SlimRuntimeSmokeTests(unittest.TestCase):
    def test_auth_failure_smoke_accepts_stage_diagnostics_and_rejects_import_failure(self):
        from scripts.smoke_binary import check_missing_config
        for diagnostic in ['API call failed: Abort:', 'COST page failed: Abort:\nPARTIAL COLLECTION']:
            check_missing_config(subprocess.CompletedProcess([], 1, diagnostic,
                                  'Collection failed; no success archive created.'))
        with self.assertRaises(AssertionError):
            check_missing_config(subprocess.CompletedProcess([], 1, '', 'ImportError: missing NumPy'))
        with self.assertRaises(AssertionError):
            check_missing_config(subprocess.CompletedProcess([], 1, 'Abort: ImportError: broken dependency',
                                  'Collection failed; no success archive created.'))

    def test_offline_smoke_covers_every_collector_service(self):
        from scripts.smoke_binary import offline_commands
        services = {arguments[1] for arguments in offline_commands()
                    if arguments[:1] == ['--internal-oci'] and len(arguments) > 2}
        self.assertEqual({'iam', 'compute', 'bv', 'usage-api', 'optimizer',
                          'search', 'monitoring', 'audit', 'events'}, services)

    def test_persistent_worker_smoke_checks_repeated_responses(self):
        from scripts.smoke_binary import smoke_worker
        responses = [{'returncode': 0, 'stdout': 'help\n', 'stderr': ''}] * 3 + [
            {'returncode': 1, 'stdout': '', 'stderr': 'Abort: \n'}]
        result = subprocess.CompletedProcess([], 0, '\n'.join(json.dumps(row) for row in responses), '')
        with patch('scripts.smoke_binary.subprocess.run', return_value=result) as run:
            smoke_worker('/binary/helper', {}, '/tmp')
        self.assertEqual(['/binary/helper', '--internal-oci-worker'], run.call_args.args[0])
        self.assertEqual(4, len(run.call_args.kwargs['input'].splitlines()))
        with patch('scripts.smoke_binary.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaises(AssertionError):
                smoke_worker('/binary/helper', {}, '/tmp')


class BuildCacheTests(unittest.TestCase):
    def test_build_cache_is_local_by_default_and_preserves_explicit_override(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            commands = directory / 'commands'
            commands.mkdir()
            (commands / 'python3').write_text('#!/bin/sh\nexit 0\n')
            (commands / 'python3').chmod(0o755)
            environment_path = directory / 'environment'
            (environment_path / 'bin').mkdir(parents=True)
            python = environment_path / 'bin/python'
            python.write_text('#!/bin/sh\nif [ "$1" = "-m" ] && [ "$2" = "PyInstaller" ]; then\n'
                              'printf "%s" "$PYINSTALLER_CONFIG_DIR" > "$TEST_BUILD_LOG"\nfi\n')
            python.chmod(0o755)
            for override in [None, str(directory / 'custom-cache')]:
                with self.subTest(override=override):
                    environment = dict(os.environ)
                    environment.pop('PYINSTALLER_CONFIG_DIR', None)
                    environment.update(PATH=str(commands) + os.pathsep + environment['PATH'],
                                       FINOPS_BUILD_ENV=str(environment_path),
                                       TEST_BUILD_LOG=str(directory / 'cache.log'))
                    if override is not None:
                        environment['PYINSTALLER_CONFIG_DIR'] = override
                    result = subprocess.run(['bash', str(root / 'build.sh')], env=environment,
                                            capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(override or str(root / 'build/pyinstaller-cache'),
                                     (directory / 'cache.log').read_text())
