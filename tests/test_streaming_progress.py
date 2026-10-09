import contextlib
import io
import json
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.collector import OCICostCollector
from src.utils.api_executor import OCIAPIExecutor


class FlushedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = []
    def flush(self):
        self.flushes.append(self.getvalue())


class StreamingProgressTests(unittest.TestCase):
    def test_api_reports_and_flushes_before_request_and_after_each_saved_page(self):
        output = FlushedOutput()
        with tempfile.TemporaryDirectory() as directory:
            api = OCIAPIExecutor('ocid1.tenancy.oc1.private', 'home', directory)
            class Store:
                def add_page(self, *args, **kwargs):
                    pass
            def request(command, **kwargs):
                self.assertIn('requesting page 1', output.getvalue())
                self.assertTrue(any('requesting page 1' in text for text in output.flushes))
                return subprocess.CompletedProcess(command, 0, json.dumps({'status': '200 OK', 'data': {'items': [{}, {}]}, 'headers': {}}), '')
            with contextlib.redirect_stdout(output), patch('src.utils.api_executor.run_oci', side_effect=request):
                self.assertTrue(api.collect_to_store(Store(), 'COST', ['resourceId'], '2026-09-01', '2026-09-01', '2026-09-02'))
        self.assertIn('page 1 saved', output.getvalue())
        self.assertIn('2 records', output.getvalue())
        self.assertNotIn('ocid1.tenancy', output.getvalue())

    def test_startup_and_stages_are_visible_before_billing_and_export(self):
        output = FlushedOutput()
        def collect(api, store, kind, fields, partition, start, end):
            self.assertIn('Starting OCI FinOps collection', output.getvalue())
            self.assertIn('Billing collection', output.getvalue())
            self.assertTrue(any('Starting OCI FinOps collection' in text for text in output.flushes))
            store.add_page(kind, partition, 0, [{'resourceId': 'resource', 'timeUsageStarted': start, 'computedAmount': .12345}])
            return True
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output), patch.object(OCIAPIExecutor, 'collect_to_store', collect):
            collector = OCICostCollector('ocid1.tenancy.oc1.private', 'home', '2026-09-01', '2026-09-02', directory, streaming=True)
            self.assertTrue(collector.collect(skip_enrichment=True, skip_recommendations=True, growth_collection=False))
        text = output.getvalue()
        for marker in ('2026-09-01', '2026-09-02', 'Raw billing JSON', 'CSV export', 'Collection complete'):
            self.assertIn(marker, text)
        self.assertNotIn('ocid1.tenancy', text)
        self.assertTrue(any('Collection complete' in value for value in output.flushes))

    def test_metadata_growth_and_recommendation_status_precedes_work(self):
        output = FlushedOutput()
        instance = 'ocid1.instance.oc1.region.synthetic'
        def billing(api, store, kind, fields, partition, start, end):
            store.add_page(kind, partition, 0, [{'resourceId': instance, 'timeUsageStarted': start}])
            return True
        def assert_visible(marker):
            self.assertIn(marker, output.getvalue())
            self.assertTrue(any(marker in text for text in output.flushes))
        def metadata(ids):
            assert_visible('Metadata enrichment: requesting batch')
            return {instance: {'shape': 'shape', 'resourceName': 'name'}}, 1, 0
        def growth(**kwargs):
            assert_visible('Growth/FinOps: starting')
            return {}
        def recommendations():
            assert_visible('Recommendations: starting')
            return 'recommendations.csv'
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output), \
             patch.object(OCIAPIExecutor, 'collect_to_store', billing), \
             patch('src.collector.OCIMetadataFetcher') as fetcher, \
             patch('src.collector.OCIGrowthCollector') as growth_collector, \
             patch('src.collector.OCIRecommendationsFetcher') as advisor:
            fetcher.return_value.fetch_metadata.side_effect = metadata
            growth_collector.return_value.collect_all.side_effect = growth
            growth_collector.return_value.enrich_dataframe_with_tags.side_effect = lambda frame: frame
            advisor.return_value.fetch_and_save.side_effect = recommendations
            collector = OCICostCollector('ocid1.tenancy.oc1.private', 'home', '2026-09-01', '2026-09-02', directory, streaming=True)
            self.assertTrue(collector.collect())
        for marker in ('Metadata enrichment: complete', 'Growth/FinOps: complete', 'Recommendations: complete'):
            self.assertIn(marker, output.getvalue())
        self.assertNotIn('ocid1.', output.getvalue())

    def test_heartbeat_emits_without_waiting_for_blocking_stage_to_finish(self):
        from src.utils.feedback import progress_heartbeat
        event = threading.Event()
        with patch('src.utils.feedback.report_progress', side_effect=lambda message: event.set()) as report:
            with progress_heartbeat('Slow stage', interval=.01):
                self.assertTrue(event.wait(1))
            self.assertTrue(report.called)

    def test_progress_redacts_ocids_and_terminal_control_characters(self):
        from src.utils.feedback import report_progress
        output = FlushedOutput()
        with contextlib.redirect_stdout(output):
            report_progress('stage \x1b[31m ocid1.tenancy.oc1.private\ncontinued')
        self.assertNotIn('ocid1.', output.getvalue())
        self.assertNotIn('\x1b', output.getvalue())
        self.assertEqual(1, output.getvalue().count('\n'))
        self.assertTrue(output.flushes)
