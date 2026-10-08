import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from src.collector import OCICostCollector


class CollectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.collector = OCICostCollector('tenancy', 'home', '2026-09-01', '2026-10-01', self.directory.name)

    def test_growth_only_runs_collection_independent_of_cost_usage(self):
        with patch('src.collector.OCIGrowthCollector') as growth, patch.object(self.collector, 'make_api_call') as cost, contextlib.redirect_stdout(io.StringIO()):
            result = self.collector.collect(skip_cost=True, skip_usage=True, skip_recommendations=True, growth_collection=True)
        self.assertTrue(result)
        cost.assert_not_called()
        growth.return_value.collect_all.assert_called_once_with(from_date='2026-09-01', to_date='2026-10-01', cost_data=None)

    def test_growth_uses_raw_cost_items_instead_of_multiplied_merged_rows(self):
        raw = {'items': [{'resourceId': 'instance', 'computedAmount': 10, 'currency': 'USD'}]}
        frame = pd.DataFrame([{'resourceId': 'instance', 'computedAmount': 10}] * 3)
        with patch('src.collector.OCIGrowthCollector') as growth, patch.object(self.collector, 'make_api_call', side_effect=[raw, {'items': []}]), patch.object(self.collector, 'merge_and_enrich', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            growth.return_value.enrich_dataframe_with_tags.return_value = frame
            self.assertTrue(self.collector.collect(skip_recommendations=True, growth_collection=True))
        self.assertIs(raw, growth.return_value.collect_all.call_args.kwargs['cost_data'])
        growth.return_value.collect_all.assert_called_once()

    def test_normal_collection_does_not_add_growth_api_calls(self):
        with patch('src.collector.OCIGrowthCollector') as growth, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.collector.collect(skip_cost=True, skip_usage=True, skip_recommendations=True))
        growth.assert_not_called()

    def test_inventory_still_runs_when_requested_cost_collection_fails(self):
        with patch('src.collector.OCIGrowthCollector') as growth, patch.object(self.collector, 'make_api_call', return_value=None), contextlib.redirect_stdout(io.StringIO()):
            result = self.collector.collect(skip_usage=True, skip_recommendations=True, growth_collection=True)
        self.assertFalse(result)
        growth.return_value.collect_all.assert_called_once()

    def test_growth_failure_does_not_report_success(self):
        with patch('src.collector.OCIGrowthCollector') as growth, contextlib.redirect_stdout(io.StringIO()):
            growth.return_value.collect_all.side_effect = RuntimeError('denied')
            result = self.collector.collect(skip_cost=True, skip_usage=True, skip_recommendations=True, growth_collection=True)
        self.assertFalse(result)
