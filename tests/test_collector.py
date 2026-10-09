import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from unittest.mock import patch
import pandas as pd
from src.collector import OCICostCollector


class CollectionPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.collector = OCICostCollector('tenancy', 'home', '2026-09-01', '2026-10-01', self.directory.name)
        self.instance = 'ocid1.instance.oc1.test.synthetic'

    def merge(self, costs, usage, **kwargs):
        with patch('src.collector.ProgressSpinner'), contextlib.redirect_stdout(io.StringIO()):
            return self.collector.merge_and_enrich({'items': costs}, {'items': usage}, **kwargs)

    def test_usage_duplicates_preserve_cost_rows_totals_and_ambiguous_fields(self):
        costs = [{'resourceId': 'volume', 'timeUsageStarted': 'day', 'computedAmount': 3},
                 {'resourceId': 'volume', 'timeUsageStarted': 'day', 'computedAmount': 5}]
        usage = [{'resourceId': 'volume', 'timeUsageStarted': 'day', 'platform': 'Linux', 'skuPartNumber': sku}
                 for sku in ['A', 'B']]
        frame = self.merge(costs, usage)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.computedAmount.sum(), 8)
        self.assertEqual(frame.platform.tolist(), ['Linux', 'Linux'])
        self.assertTrue(frame.skuPartNumber.isna().all())

    def test_vectorized_enrichment_preserves_existing_and_fills_missing_columns(self):
        costs = [{'resourceId': self.instance, 'timeUsageStarted': 'day', 'shape': 'original'},
                 {'resourceId': self.instance, 'timeUsageStarted': 'other', 'shape': ''}]
        usage = [{'resourceId': self.instance, 'timeUsageStarted': 'day'}]
        with patch.object(self.collector, 'fetch_instance_metadata', return_value={self.instance: {'shape': 'fetched', 'resourceName': 'name'}}), patch.object(pd.DataFrame, 'apply', side_effect=AssertionError('row apply forbidden')):
            frame = self.merge(costs, usage)
        self.assertEqual(frame['shape'].tolist(), ['original', 'fetched'])
        self.assertEqual(frame.resourceName.tolist(), ['name', 'name'])

    def test_skip_enrichment_makes_no_metadata_requests(self):
        row = {'resourceId': self.instance, 'timeUsageStarted': 'day'}
        with patch.object(self.collector, 'fetch_instance_metadata') as fetch:
            frame = self.merge([row], [row], skip_enrichment=True)
        fetch.assert_not_called()
        self.assertEqual(len(frame), 1)

    def test_empty_usage_keeps_costs_and_empty_costs_are_valid(self):
        row = {'resourceId': 'volume', 'timeUsageStarted': 'day', 'computedAmount': 7}
        self.assertEqual(self.merge([row], []).computedAmount.sum(), 7)
        self.assertEqual(len(self.merge([], [row])), 0)

    def test_usage_fills_blank_cost_metadata_without_overwriting_existing_values(self):
        costs = [{'resourceId': 'volume', 'timeUsageStarted': 'day', 'platform': ''},
                 {'resourceId': 'volume', 'timeUsageStarted': 'other', 'platform': 'original'}]
        usage = [{'resourceId': 'volume', 'timeUsageStarted': day, 'platform': 'Linux'} for day in ['day', 'other']]
        self.assertEqual(self.merge(costs, usage).platform.tolist(), ['Linux', 'original'])

    def test_incomplete_join_keys_do_not_attach_anonymous_usage_metadata(self):
        costs = [{'resourceId': None, 'timeUsageStarted': 'day', 'computedAmount': 4},
                 {'resourceId': 'volume', 'timeUsageStarted': None, 'computedAmount': 5}]
        usage = [dict(row, platform='arbitrary') for row in costs]
        frame = self.merge(costs, usage)
        self.assertEqual(frame.computedAmount.sum(), 9)
        self.assertTrue(frame.platform.isna().all())

    def test_cache_survives_new_collector_and_scopes_tenancy(self):
        metadata = {self.instance: {'shape': 'shape', 'resourceName': 'name'}}
        with patch('src.collector.OCIMetadataFetcher') as fetcher, contextlib.redirect_stdout(io.StringIO()):
            fetcher.return_value.fetch_metadata.return_value = (metadata, 1, 0)
            self.collector.fetch_instance_metadata([self.instance])
            same = OCICostCollector('tenancy', 'home', 'start', 'end', self.directory.name)
            self.assertEqual(same.fetch_instance_metadata([self.instance]), metadata)
            self.assertEqual(fetcher.return_value.fetch_metadata.call_count, 1)
            other = OCICostCollector('different', 'home', 'start', 'end', self.directory.name)
            other.fetch_instance_metadata([self.instance])
            self.assertEqual(fetcher.return_value.fetch_metadata.call_count, 2)

    def test_cost_and_usage_requests_overlap(self):
        barrier = threading.Barrier(2)
        def query(**kwargs):
            barrier.wait(timeout=3)
            return {'items': []}
        with patch.object(self.collector, 'make_api_call', side_effect=query), patch.object(self.collector, 'merge_and_enrich', return_value=pd.DataFrame()), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.collector.collect(skip_recommendations=True))

    def test_metadata_cache_reuses_successes_and_retries_failures(self):
        metadata = {self.instance: {'shape': 'shape', 'resourceName': 'name'}}
        with patch('src.collector.OCIMetadataFetcher') as fetcher, contextlib.redirect_stdout(io.StringIO()):
            fetcher.return_value.fetch_metadata.side_effect = [(metadata, 1, 1), ({}, 0, 1)]
            self.collector.fetch_instance_metadata([self.instance, 'failed'])
            result = self.collector.fetch_instance_metadata([self.instance, 'failed'])
        self.assertEqual(result, metadata)
        self.assertEqual(fetcher.return_value.fetch_metadata.call_args_list[1].args[0], ['failed'])

    def test_expired_or_corrupt_metadata_cache_is_refetched(self):
        path = Path(self.directory.name) / 'instance_metadata_cache.json'
        path.write_text('{broken')
        metadata = {self.instance: {'shape': 'shape', 'resourceName': 'name'}}
        with patch('src.collector.OCIMetadataFetcher') as fetcher, patch('src.collector.time.time', side_effect=[0, 90000]), contextlib.redirect_stdout(io.StringIO()):
            fetcher.return_value.fetch_metadata.return_value = (metadata, 1, 0)
            self.collector.fetch_instance_metadata([self.instance])
            self.collector.fetch_instance_metadata([self.instance])
        self.assertEqual(fetcher.return_value.fetch_metadata.call_count, 2)


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
