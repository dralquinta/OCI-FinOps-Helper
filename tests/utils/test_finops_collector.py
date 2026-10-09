import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.utils.finops_collector import OCIFinOpsCollector


class FinOpsCollectorTests(unittest.TestCase):
    def test_candidate_csv_formats_costs_without_rounding_raw_evidence(self):
        costs = {'items': [
            {'resourceId': 'orphan', 'region': 'r1', 'currency': 'USD',
             'computedAmount': 1.235}]}
        result = self.collect(costs)
        candidate = next(item for item in result['candidates']
                         if item['resource_id'] == 'orphan' and item['region'] == 'r1')
        self.assertEqual([{'currency': 'USD', 'computed_amount': 1.235}], candidate['costs'])
        folder = Path(self.directory.name)
        with (folder / 'finops_candidates.csv').open() as stream:
            exported = next(row for row in csv.DictReader(stream)
                            if row['resource_id'] == 'orphan' and row['region'] == 'r1')
        self.assertEqual([{'currency': 'USD', 'computed_amount': '1.24'}], json.loads(exported['costs']))
        raw = json.loads((folder / 'finops_collection.json').read_text())
        self.assertEqual(result, raw)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.commands = []
        self.fail_attachments = False
        self.fail_compartments = False

    def execute(self, command, description):
        self.commands.append(command)
        operation = tuple(command[1:4])
        compartment = command[command.index('--compartment-id') + 1] if '--compartment-id' in command else None
        if operation == ('iam', 'region-subscription', 'list'):
            return [{'region-name': 'r1'}, {'region-name': 'r2'}]
        if operation == ('iam', 'compartment', 'list'):
            return None if self.fail_compartments else [{'id': 'child', 'lifecycle-state': 'ACTIVE'}]
        if operation == ('iam', 'availability-domain', 'list'):
            return [{'name': 'AD-1'}]
        if operation == ('search', 'resource', 'structured-search'):
            return {'items': [{'identifier': 'other', 'resource-type': 'Bucket'}]}
        if operation == ('compute', 'instance', 'list'):
            return [{'id': 'stopped', 'lifecycle-state': 'STOPPED', 'shape': 'VM.Standard.E4.Flex'}] if compartment == 'root' else []
        if operation == ('bv', 'volume', 'list'):
            return [{'id': 'attached', 'lifecycle-state': 'AVAILABLE'}, {'id': 'orphan', 'lifecycle-state': 'AVAILABLE'}] if compartment == 'root' else []
        if operation == ('compute', 'volume-attachment', 'list'):
            if self.fail_attachments and compartment == 'child':
                return None
            return [{'id': 'a', 'volume-id': 'attached', 'lifecycle-state': 'ATTACHING'}] if compartment == 'child' else []
        if operation == ('bv', 'boot-volume', 'list'):
            return [{'id': 'boot', 'lifecycle-state': 'AVAILABLE'}] if compartment == 'root' else []
        if operation == ('compute', 'boot-volume-attachment', 'list'):
            return []
        raise AssertionError(command)

    def collect(self, costs=None):
        return OCIFinOpsCollector('root', 'r1', self.directory.name, self.execute).collect_all('2026-01-01', '2026-02-01', costs)

    def test_regional_inventory_cross_compartment_attachments_and_outputs(self):
        result = self.collect()
        self.assertEqual(result['regions'], ['r1', 'r2'])
        candidates = result['candidates']
        self.assertEqual({item['resource_id'] for item in candidates}, {'orphan', 'boot', 'stopped'})
        self.assertEqual(len(candidates), 6)
        self.assertTrue(all(item['cost_status'] == 'unknown' for item in candidates))
        self.assertTrue(any(item['status'] == 'empty' for item in result['coverage']))
        self.assertTrue(any(item['status'] == 'success' for item in result['coverage']))
        for command in self.commands:
            self.assertIn('--region', command)
            if command[1:4] == ['search', 'resource', 'structured-search']:
                self.assertNotIn('--all', command)
            else:
                self.assertIn('--all', command)
            self.assertNotIn('delete', command)
            self.assertNotIn('stop', command)
        folder = Path(self.directory.name)
        self.assertEqual(json.loads((folder / 'finops_collection.json').read_text())['candidates'], candidates)
        with (folder / 'finops_candidates.csv').open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 6)
        self.assertTrue((folder / 'finops_summary.txt').exists())

    def test_failed_attachment_read_prevents_block_orphan_classification(self):
        self.fail_attachments = True
        result = self.collect()
        self.assertNotIn('orphan', {item['resource_id'] for item in result['candidates']})
        self.assertTrue(any(item['status'] == 'failed' for item in result['coverage']))

    def test_failed_compartment_discovery_prevents_orphan_classification(self):
        self.fail_compartments = True
        result = self.collect()
        self.assertEqual({item['resource_id'] for item in result['candidates']}, {'stopped'})

    def test_costs_preserve_currency_zero_and_resource_region(self):
        costs = {'items': [
            {'resourceId': 'orphan', 'region': 'r1', 'currency': 'USD', 'computedAmount': 3},
            {'resource-id': 'orphan', 'region': 'r1', 'currency': 'USD', 'computed-amount': 2},
            {'resource-id': 'orphan', 'region': 'r1', 'currency': 'EUR', 'computed-amount': 1},
            {'resource-id': 'boot', 'region': 'r1', 'currency': 'USD', 'computed-amount': 0},
        ]}
        result = self.collect(costs)
        self.assertEqual(result['cost_data'], costs)
        candidates = {(item['resource_id'], item['region']): item for item in result['candidates']}
        self.assertEqual(candidates['orphan', 'r1']['costs'], [{'currency': 'EUR', 'computed_amount': 1.0}, {'currency': 'USD', 'computed_amount': 5.0}])
        self.assertEqual(candidates['boot', 'r1']['cost_status'], 'known')
        self.assertEqual(candidates['boot', 'r1']['costs'][0]['computed_amount'], 0)
        self.assertEqual(candidates['orphan', 'r2']['cost_status'], 'unknown')

    def test_region_discovery_failure_preserves_fallback_coverage(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['iam', 'region-subscription', 'list']:
                return None
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertEqual(result['regions'], ['r1'])
        self.assertEqual({item['resource_id'] for item in result['candidates']}, {'stopped'})

    def test_failed_boot_attachment_read_prevents_boot_orphans_only(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['compute', 'boot-volume-attachment', 'list']:
                return None
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertEqual({item['resource_id'] for item in result['candidates']}, {'orphan', 'stopped'})

    def test_unknown_attachment_state_blocks_orphan_when_resource_is_referenced(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['compute', 'volume-attachment', 'list']:
                return [{'id': 'attachment', 'volume-id': 'orphan', 'lifecycle-state': 'UNKNOWN'}]
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertNotIn('orphan', {item['resource_id'] for item in result['candidates']})

    def test_malformed_attachment_evidence_prevents_orphan_inference(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['compute', 'volume-attachment', 'list']:
                return [{'id': 'attachment', 'lifecycle-state': 'ATTACHED'}]
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertNotIn('orphan', {item['resource_id'] for item in result['candidates']})

    def test_search_paginated_envelopes_preserve_all_records(self):
        execute = self.execute
        pages = []
        def callback(command, description):
            if command[1:4] == ['search', 'resource', 'structured-search']:
                self.assertNotIn('--all', command)
                page = command[command.index('--page') + 1] if '--page' in command else None
                pages.append(page)
                return {'data': {'items': [{'identifier': 'first' if page is None else 'second'}]},
                        'opc-next-page': 'next' if page is None else None}
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertEqual(pages, [None, 'next', None, 'next'])
        self.assertEqual(len(result['inventory']['resources']), 4)

    def test_failed_search_later_page_preserves_evidence_and_marks_failed(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['search', 'resource', 'structured-search']:
                if '--page' in command:
                    return None
                return {'data': {'items': [{'identifier': 'first'}]}, 'opc-next-page': 'next'}
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertEqual(len(result['inventory']['resources']), 2)
        coverage = [item for item in result['coverage'] if item['operation'] == 'search resource structured-search']
        self.assertTrue(all(item['status'] == 'failed' for item in coverage))

    def test_malformed_attachment_reference_is_failed_coverage_not_crash(self):
        execute = self.execute
        def callback(command, description):
            if command[1:4] == ['compute', 'volume-attachment', 'list']:
                return [{'id': 'attachment', 'volume-id': ['orphan'], 'lifecycle-state': 'ATTACHED'}]
            return execute(command, description)
        result = OCIFinOpsCollector('root', 'r1', self.directory.name, callback).collect_all()
        self.assertNotIn('orphan', {item['resource_id'] for item in result['candidates']})
        self.assertTrue(any(item['status'] == 'failed' for item in result['coverage']))


if __name__ == '__main__':
    unittest.main()


class RegionalInventoryPerformanceTests(unittest.TestCase):
    def test_region_inventory_overlaps_with_four_worker_bound_and_ordered_merge(self):
        import threading
        import time
        import tempfile
        from src.utils.finops_collector import OCIFinOpsCollector
        barrier = threading.Barrier(4)
        lock = threading.Lock()
        active = 0
        peak = 0
        regions = ['region-' + str(i) for i in range(8)]
        def execute(command, description):
            nonlocal active, peak
            if 'region-subscription' in command:
                return [{'region-name': region, 'status': 'READY'} for region in reversed(regions)]
            if 'compartment' in command:
                return []
            if 'structured-search' in command:
                with lock:
                    active += 1
                    peak = max(peak, active)
                try:
                    barrier.wait(timeout=2)
                    time.sleep(0.01)
                    region = command[command.index('--region')+1]
                    return {'data': {'items': [{'identifier': 'resource-' + region}]}}
                finally:
                    with lock:
                        active -= 1
            if 'availability-domain' in command:
                return [{'name': 'ad'}]
            if command[1:4] == ['bv', 'volume', 'list']:
                region = command[command.index('--region')+1]
                return [{'id': 'volume-' + region, 'lifecycle-state': 'AVAILABLE'}]
            return []
        with tempfile.TemporaryDirectory() as directory:
            result = OCIFinOpsCollector('tenancy', 'home', directory, execute).collect_all()
        self.assertEqual(4, peak)
        self.assertTrue(result['discovery_complete'])
        self.assertEqual(regions, result['regions'])
        self.assertEqual(regions, [row['region'] for row in result['inventory']['resources']])
        self.assertEqual(regions, [row['region'] for row in result['candidates']])
        self.assertEqual(58, len(result['coverage']))
        self.assertFalse(any(row['status'] == 'failed' for row in result['coverage']))
