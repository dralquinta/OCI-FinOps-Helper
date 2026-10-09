import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from src.utils.datasets import DiskDatasetStore
from src.utils.finops_collector import OCIFinOpsCollector


class StreamingFinOpsTests(unittest.TestCase):
    def test_report_writes_inventory_without_allocating_a_second_json_string(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = OCIFinOpsCollector('tenancy', 'region', directory)
            results = {'inventory': {'instances': [{'id': 'instance'}]}, 'candidates': [],
                       'coverage': [], 'regions': ['region'], 'compartments': ['tenancy'],
                       'discovery_complete': True, 'scope': 'read-only'}
            original = json.dumps
            def bounded_dump(value, *args, **kwargs):
                self.assertIsNot(value, results, 'whole inventory JSON string duplicates the dataset')
                return original(value, *args, **kwargs)
            with patch('src.utils.finops_collector.json.dumps', side_effect=bounded_dump):
                collector._save(results)
            self.assertEqual(json.loads((Path(directory) / 'finops_collection.json').read_text()), results)

    def test_cost_lookup_uses_disk_without_materializing_billing_rows(self):
        with DiskDatasetStore() as store:
            store.add_page('COST', 0, 0, [
                {'resourceId': 'instance', 'currency': 'USD', 'computedAmount': 12.345},
                {'resourceId': 'instance', 'region': 'region', 'currency': 'USD', 'computedAmount': 2.0}])
            costs = OCIFinOpsCollector._costs(store.dataset('COST'))
            self.assertEqual(costs.get(('instance', None)), {'USD': 12.345})
            self.assertEqual(costs.get(('instance', 'region')), {'USD': 2.0})
            self.assertEqual(costs.get(('absent', None), {}), {})
