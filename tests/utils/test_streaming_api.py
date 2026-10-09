import json
import subprocess
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from src.utils.api_executor import OCIAPIExecutor


class PageStore:
    def __init__(self):
        self.pages = []

    def add_page(self, kind, partition, page_seq, rows, metadata=None):
        self.pages.append((kind, partition, page_seq, list(rows), metadata))


class StreamingAPITests(unittest.TestCase):
    def test_transient_http_failure_retries_same_page_without_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = OCIAPIExecutor('synthetic', 'home', directory)
            responses = [
                {'status': '429 Too Many Requests', 'data': {'code': 'TooManyRequests'},
                 'headers': {'retry-after': '2'}},
                {'data': {'items': [{'computedAmount': 1.2345}]}, 'headers': {'opc-next-page': 'next'}},
                {'status': '503 Service Unavailable', 'data': {'code': 'ServiceUnavailable'}, 'headers': {}},
                {'data': {'items': [{'computedAmount': 2.3456}]}, 'headers': {}}]
            replies = [subprocess.CompletedProcess([], 0, json.dumps(value), '') for value in responses]
            store = PageStore()
            with patch('src.utils.api_executor.run_oci', side_effect=replies) as request, \
                 patch('time.sleep') as sleep:
                self.assertTrue(executor.collect_to_store(store, 'COST', ['resourceId'],
                                '2025-09-01', '2025-09-01', '2025-09-02'))
            self.assertEqual(2, len(store.pages))
            self.assertEqual(request.call_args_list[0], request.call_args_list[1])
            self.assertEqual(request.call_args_list[2], request.call_args_list[3])
            self.assertEqual(2, sleep.call_count)

    def test_http_retry_is_bounded_and_authentication_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = OCIAPIExecutor('synthetic', 'home', directory)
            for status, code, calls in [('503 Service Unavailable', 'ServiceUnavailable', 5),
                                        ('401 Unauthorized', 'NotAuthenticated', 1)]:
                result = subprocess.CompletedProcess([], 0, json.dumps(
                    {'status': status, 'data': {'code': code}, 'headers': {}}), '')
                with self.subTest(status=status), patch('src.utils.api_executor.run_oci', return_value=result) as request, \
                     patch('time.sleep'):
                    self.assertFalse(executor.collect_to_store(PageStore(), 'COST', ['resourceId'],
                                     '2025-09-01', '2025-09-01', '2025-09-02'))
                self.assertEqual(calls, request.call_count)

    def test_error_status_never_persists_even_a_well_formed_items_array(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = OCIAPIExecutor('synthetic', 'home', directory)
            for status, calls in [('401 Unauthorized', 1), ('503 Service Unavailable', 5)]:
                result = subprocess.CompletedProcess([], 0, json.dumps(
                    {'status': status, 'data': {'items': [{'computedAmount': 9.99}]}, 'headers': {}}), '')
                store = PageStore()
                with self.subTest(status=status), patch('src.utils.api_executor.run_oci', return_value=result) as request, \
                     patch('time.sleep'):
                    self.assertFalse(executor.collect_to_store(store, 'COST', ['resourceId'],
                                     '2025-09-01', '2025-09-01', '2025-09-02'))
                self.assertEqual([], store.pages)
                self.assertEqual(calls, request.call_count)

    def test_pages_are_bounded_and_delivered_before_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PageStore()
            executor = OCIAPIExecutor('synthetic', 'home', directory)
            requests = []
            def request(command, **kwargs):
                self.assertEqual(len(requests), len(store.pages))
                uri = command[command.index('--target-uri') + 1]
                query = parse_qs(urlparse(uri).query)
                self.assertEqual(['1000'], query['limit'])
                requests.append(query)
                page = {'data': {'items': [{'computedAmount': 0.123456}], 'granularity': 'DAILY'},
                        'headers': {'opc-next-page': 'second'} if len(requests) == 1 else {}}
                return subprocess.CompletedProcess(command, 0, json.dumps(page), '')
            with patch('src.utils.api_executor.run_oci', side_effect=request):
                self.assertTrue(executor.collect_to_store(store, 'COST', ['resourceId'],
                                '2025-09-01', '2025-09-01', '2025-09-02'))
            self.assertEqual(2, len(store.pages))
            self.assertEqual(['second'], requests[1]['page'])
            self.assertEqual(0.123456, store.pages[0][3][0]['computedAmount'])

    def test_repeated_page_and_failed_page_do_not_report_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = OCIAPIExecutor('synthetic', 'home', directory)
            repeated = subprocess.CompletedProcess([], 0, json.dumps({
                'data': {'items': []}, 'headers': {'opc-next-page': 'same'}}), '')
            for responses in ([repeated, repeated], [repeated, subprocess.CompletedProcess([], 1, '', 'failed')]):
                with self.subTest(failure=responses[-1].returncode), patch('src.utils.api_executor.run_oci', side_effect=responses):
                    self.assertFalse(executor.collect_to_store(PageStore(), 'COST', ['resourceId'],
                                     '2025-09-01', '2025-09-01', '2025-09-02'))
