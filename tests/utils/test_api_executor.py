import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.utils.api_executor import OCIAPIExecutor


class UsagePaginationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.executor = OCIAPIExecutor('tenancy', 'home', self.directory.name)

    def run_query(self, responses):
        with patch('src.utils.api_executor.ProgressSpinner'), patch(
            'src.utils.api_executor.subprocess.run', side_effect=responses
        ) as runner, contextlib.redirect_stdout(io.StringIO()):
            result = self.executor.make_api_call('COST', ['resourceId'], 'cost', '2026-09-01', '2026-10-01')
        return result, runner.call_args_list

    @staticmethod
    def response(items, headers=None):
        return subprocess.CompletedProcess([], 0, json.dumps({'data': {'items': items}, 'headers': headers or {}}), '')

    def test_collects_every_page_with_encoded_token_and_same_body(self):
        result, calls = self.run_query([
            self.response([{'resourceId': 'a'}], {'OPC-NEXT-PAGE': 'next+/='}),
            self.response([{'resourceId': 'b'}])
        ])
        self.assertEqual(['a', 'b'], [row['resourceId'] for row in result['items']])
        command = calls[1].args[0]
        self.assertEqual(['next+/='], parse_qs(urlparse(command[command.index('--target-uri') + 1]).query)['page'])
        self.assertEqual(calls[0].args[0][calls[0].args[0].index('--request-body') + 1], command[command.index('--request-body') + 1])
        self.assertFalse(list(Path(self.directory.name).glob('request_*.json')))

    def test_failed_second_page_does_not_return_partial_costs(self):
        result, _ = self.run_query([self.response([{'resourceId': 'a'}], {'opc-next-page': 'next'}), subprocess.CompletedProcess([], 1, '', 'denied')])
        self.assertIsNone(result)

    def test_repeated_page_token_fails_instead_of_looping(self):
        response = self.response([], {'opc-next-page': 'same'})
        result, calls = self.run_query([response, response])
        self.assertIsNone(result)
        self.assertEqual(2, len(calls))

    def test_timeout_cleans_request_file(self):
        result, _ = self.run_query([subprocess.TimeoutExpired('oci', 300)])
        self.assertIsNone(result)
        self.assertFalse(list(Path(self.directory.name).glob('request_*.json')))
