"""The shell entrypoint exposes CLI help without OCI authentication."""
from pathlib import Path
import subprocess
import unittest


class WrapperTests(unittest.TestCase):
    def test_help_lists_named_options_without_authentication(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['bash', str(root / 'collector.sh'), '--help'],
                                cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for option in ('--tenancy-ocid', '--home-region', '--from', '--to', '--no-growth-collection'):
            self.assertIn(option, result.stdout)
        self.assertNotIn('Checking OCI Authentication', result.stdout)
