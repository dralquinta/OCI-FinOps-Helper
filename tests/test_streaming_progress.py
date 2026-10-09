import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.collector import OCICostCollector
from src.utils.api_executor import OCIAPIExecutor


class FlushedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = []
    def flush(self):
        self.flushes.append(self.getvalue())


class StreamingProgressTests(unittest.TestCase):
    def test_api_reports_and_flushes_before_request_without_page_log_flood(self):
        output = FlushedOutput()
        with tempfile.TemporaryDirectory() as directory:
            api = OCIAPIExecutor('ocid1.tenancy.oc1.private', 'home', directory)
            class Store:
                def add_page(self, *args, **kwargs):
                    pass
            def request(command, **kwargs):
                self.assertIn('Billing COST', output.getvalue())
                self.assertTrue(any('Billing COST' in text for text in output.flushes))
                return subprocess.CompletedProcess(command, 0, json.dumps({'status': '200 OK', 'data': {'items': [{}, {}]}, 'headers': {}}), '')
            with contextlib.redirect_stdout(output), patch('src.utils.api_executor.run_oci', side_effect=request):
                self.assertTrue(api.collect_to_store(Store(), 'COST', ['resourceId'], '2026-09-01', '2026-09-01', '2026-09-02'))
        self.assertNotIn('page 1 saved', output.getvalue())
        self.assertIn('2 records', output.getvalue())
        self.assertNotIn('ocid1.tenancy', output.getvalue())

    def test_parallel_billing_pages_emit_compact_aggregate_and_exact_totals(self):
        output = FlushedOutput()
        requested = []
        lock = threading.Lock()
        def request(command, **kwargs):
            self.assertTrue(any('Billing collection' in text for text in output.flushes))
            body = json.loads(Path(
                command[command.index('--request-body') + 1][7:]).read_text())
            query = parse_qs(urlparse(command[command.index('--target-uri') + 1]).query)
            page = int(query.get('page', ['0'])[0])
            with lock:
                requested.append((body['queryType'], body['timeUsageStarted'], page))
            payload = {'status': '200 OK', 'data': {'items': [
                {'resourceId': f'synthetic-{page}-{row}',
                 'timeUsageStarted': body['timeUsageStarted'], 'computedAmount': .12345}
                for row in range(2)]},
                'headers': {'opc-next-page': str(page + 1)} if page < 29 else {}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), '')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output), \
             patch('src.utils.api_executor.run_oci', side_effect=request):
            collector = OCICostCollector('synthetic', 'home', '2026-09-01', '2026-09-03',
                                         directory, streaming=True)
            self.assertTrue(collector.collect(skip_enrichment=True, skip_recommendations=True,
                                              growth_collection=False))
        self.assertEqual(120, len(requested))
        text = output.getvalue()
        billing_lines = [line for line in text.splitlines() if line.startswith('Billing')]
        self.assertLess(len(billing_lines), 20)
        self.assertNotIn('requesting page', text)
        self.assertNotIn('page 30 saved', text)
        self.assertIn('COST 120 records', text)
        self.assertIn('USAGE 120 records', text)
        self.assertTrue(any('Billing collection complete: 4/4 windows completed; failed 0; '
                            'COST 120 records / 60 pages; USAGE 120 records / 60 pages; retries 0;'
                            in line for line in billing_lines))
        self.assertIn('Collection complete', text)

    def test_billing_retry_and_failed_window_preserve_partial_aggregate_totals(self):
        output = FlushedOutput()
        attempts = {}
        lock = threading.Lock()
        def request(command, **kwargs):
            body = json.loads(Path(command[command.index('--request-body') + 1][7:]).read_text())
            kind = body['queryType']
            query = parse_qs(urlparse(command[command.index('--target-uri') + 1]).query)
            page = int(query.get('page', ['0'])[0])
            with lock:
                attempts[kind, page] = attempts.get((kind, page), 0) + 1
                attempt = attempts[kind, page]
            if page == 1 and (kind == 'USAGE' or attempt == 1):
                status = '401 Unauthorized' if kind == 'USAGE' else '503 Service Unavailable'
                payload = {'status': status, 'data': {'code': 'SyntheticFailure'}, 'headers': {}}
            else:
                count = 2 if kind == 'COST' and page == 0 else 1
                payload = {'status': '200 OK', 'data': {'items': [
                    {'resourceId': f'synthetic-{page}-{row}',
                     'timeUsageStarted': body['timeUsageStarted'], 'computedAmount': .12345}
                    for row in range(count)]},
                    'headers': {'opc-next-page': '1'} if page == 0 else {}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), '')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output), \
             patch('src.utils.api_executor.run_oci', side_effect=request), \
             patch('src.utils.api_executor.time.sleep'):
            collector = OCICostCollector('synthetic', 'home', '2026-09-01', '2026-09-02',
                                         directory, streaming=True)
            self.assertFalse(collector.collect(skip_enrichment=True, skip_recommendations=True,
                                               growth_collection=False))
        self.assertEqual({('COST', 0): 1, ('COST', 1): 2,
                          ('USAGE', 0): 1, ('USAGE', 1): 1}, attempts)
        text = output.getvalue()
        self.assertIn('retry 1/4', text)
        self.assertIn('503', text)
        self.assertIn('401', text)
        self.assertIn('Billing collection partial: 1/2 windows completed; failed 1; '
                      'COST 3 records / 2 pages; USAGE 1 records / 1 pages; retries 1;', text)
        self.assertIn('PARTIAL COLLECTION', text)
        self.assertNotIn('Billing collection complete:', text)
        self.assertNotIn('Collection complete', text)
        self.assertTrue(any('Billing collection partial:' in value for value in output.flushes))

    def test_startup_and_stages_are_visible_before_billing_and_export(self):
        output = FlushedOutput()
        def collect(api, store, kind, fields, partition, start, end, **kwargs):
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
        def billing(api, store, kind, fields, partition, start, end, **kwargs):
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
