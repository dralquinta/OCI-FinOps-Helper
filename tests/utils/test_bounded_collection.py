"""Large collection scopes must not queue an unbounded number of results."""
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.utils.finops_collector import OCIFinOpsCollector
from src.utils.growth_collector import OCIGrowthCollector


class BoundedExecutor:
    """Executor that rejects backlog beyond its workers before consuming results."""
    def __init__(self, max_workers):
        self.limit = max_workers
        self.outstanding = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, item):
        self.outstanding += 1
        if self.outstanding > self.limit:
            raise AssertionError('collection queued more scopes than workers')
        executor = self
        class Result:
            def result(self):
                executor.outstanding -= 1
                return function(item)
        return Result()

    def map(self, function, iterable):
        # Standard Executor.map eagerly submits the entire input.
        futures = [self.submit(function, item) for item in iterable]
        return (future.result() for future in futures)


class CollectionBacklogTests(unittest.TestCase):
    def test_monitoring_audit_and_inventory_bound_pending_scopes(self):
        regions = [{'region-name': 'region-' + str(i), 'status': 'READY'} for i in range(10)]
        def execute(command, description):
            return regions if 'region-subscription' in command else []
        with tempfile.TemporaryDirectory() as directory:
            growth = OCIGrowthCollector('tenancy', 'home', directory)
            growth.compartments = ['comp-' + str(i) for i in range(10)]
            operations = [
                ('monitoring', 'src.utils.growth_collector.ThreadPoolExecutor',
                 lambda: growth.collect_performance_metrics('2026-09-01', '2026-09-02')),
                ('audit', 'src.utils.growth_collector.ThreadPoolExecutor',
                 lambda: growth.collect_audit_events('2026-09-01', '2026-09-02')),
                ('inventory', 'src.utils.finops_collector.ThreadPoolExecutor',
                 lambda: OCIFinOpsCollector('tenancy', 'home', directory, execute).collect_all()),
            ]
            with patch.object(growth, '_execute_oci_command', side_effect=execute), patch('src.utils.growth_collector.run_oci', return_value=subprocess.CompletedProcess([], 0, json.dumps({'data': []}), '')):
                for name, executor_path, collect in operations:
                    with self.subTest(collection=name), patch(executor_path, BoundedExecutor):
                        result = collect()
                        self.assertTrue(result['coverage'])
                        self.assertFalse(any(row['status'] == 'failed' for row in result['coverage']))
