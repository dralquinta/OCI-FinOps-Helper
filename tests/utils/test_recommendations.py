import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.utils.recommendations import OCIRecommendationsFetcher


class RecommendationsEvidenceTests(unittest.TestCase):
    def test_resource_action_amount_is_rounded_only_in_report(self):
        data = {'items': [], 'resource_actions': [
            {'estimated-cost-saving': 1.235}, {'estimated-cost-saving': None}]}
        report = self.fetcher.format_actionable_report(data)
        self.assertIn('Savings:         1.24 USD/month', report)
        self.assertIn('Savings:         UNKNOWN USD/month', report)
        self.assertEqual(1.235, data['resource_actions'][0]['estimated-cost-saving'])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fetcher = OCIRecommendationsFetcher('tenancy', 'home-region', self.directory.name, 'EUR')
        self.summary = {'id': 'recommendation', 'name': 'idle_volume', 'estimated-cost-saving': 42}
        self.action = {
            'id': 'action-id', 'recommendation-id': 'recommendation',
            'resource-id': 'volume-id', 'resource-type': 'block-volume',
            'action': 'Delete unattached volume', 'status': 'PENDING',
            'estimated-cost-saving': 42, 'metadata': {'attachment': 'none'},
        }
        self.addCleanup(patch.stopall)
        patch('src.utils.recommendations.ProgressSpinner').start()
        self.run = patch('src.utils.recommendations.subprocess.run').start()

    @staticmethod
    def response(data):
        return subprocess.CompletedProcess([], 0, json.dumps({'data': data}), '')

    def fetch(self):
        with redirect_stdout(io.StringIO()):
            return self.fetcher.fetch_recommendations_api()

    def test_collects_full_resource_actions_and_preserves_summary_metadata(self):
        self.run.side_effect = [self.response({'items': [self.summary], 'extra': 'preserved',
                                              'metadata': {'original': 'metadata'},
                                              'coverage': {'summary': 'complete'}}),
                                self.response({'items': [self.action]})]
        data = self.fetch()
        self.assertEqual(data['items'], [self.summary])
        self.assertEqual(data['extra'], 'preserved')
        self.assertEqual(data['resource_actions'], [self.action])
        self.assertEqual(data['coverage']['resource_actions']['status'], 'complete')
        self.assertEqual(data['metadata']['advisor_savings_currency'], 'USD')
        self.assertEqual(data['metadata']['configured_currency'], 'EUR')
        self.assertEqual(data['metadata']['original'], 'metadata')
        self.assertEqual(data['coverage']['summary'], 'complete')
        command = self.run.call_args_list[1].args[0]
        self.assertEqual(command[:4], ['oci', 'optimizer', 'resource-action-summary', 'list'])
        for flag, value in [('--compartment-id', 'tenancy'), ('--compartment-id-in-subtree', 'true'),
                            ('--include-resource-metadata', 'true'), ('--region', 'home-region')]:
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn('--all', command)

    def test_list_responses_and_empty_summary_preserve_actions(self):
        self.run.side_effect = [self.response([]), self.response([self.action])]
        data = self.fetch()
        self.assertEqual(data['items'], [])
        self.assertEqual(data['resource_actions'], [self.action])
        self.assertIn('volume-id', self.fetcher.format_actionable_report(data))

    def test_partial_action_errors_do_not_discard_summaries(self):
        failures = [subprocess.CompletedProcess([], 1, '', 'NotAuthorizedOrNotFound'),
                    subprocess.TimeoutExpired('oci', 300),
                    subprocess.CompletedProcess([], 0, 'not-json', ''),
                    self.response({'unexpected': 'shape'})]
        for failure in failures:
            with self.subTest(failure=str(failure)):
                self.run.side_effect = [self.response([self.summary]), failure]
                data = self.fetch()
                self.assertEqual(data['items'], [self.summary])
                self.assertEqual(data['resource_actions'], [])
                coverage = data['coverage']['resource_actions']
                self.assertEqual(coverage['status'], 'failed')
                self.assertTrue(coverage['error'])

    def test_report_and_saved_raw_data_preserve_usd_and_resource_evidence(self):
        data = {'items': [self.summary], 'resource_actions': [self.action]}
        report = self.fetcher.format_actionable_report(data)
        self.assertIn('42.00 USD', report)
        self.assertNotIn('42.00 EUR', report)
        for value in ['action-id', 'volume-id', 'block-volume', 'Delete unattached volume',
                      'PENDING', 'attachment', 'none']:
            self.assertIn(value, report)
        with redirect_stdout(io.StringIO()):
            saved = self.fetcher.save_recommendations(data)
        self.assertEqual(json.loads(saved['json'].read_text()), data)

    def test_empty_summary_does_not_hide_failed_action_coverage(self):
        self.run.side_effect = [self.response([]),
                                subprocess.CompletedProcess([], 1, '', 'NotAuthorizedOrNotFound')]
        report = self.fetcher.format_actionable_report(self.fetch())
        self.assertIn('failed', report)
        self.assertIn('NotAuthorizedOrNotFound', report)

    def test_authorization_guidance_uses_readonly_optimizer_policy(self):
        self.run.return_value = subprocess.CompletedProcess([], 1, '', 'NotAuthorizedOrNotFound')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertIsNone(self.fetcher.fetch_recommendations_api())
        self.assertIn('to read optimizer-api-family in tenancy', output.getvalue())
        self.assertNotIn('cloud-advisor-family', output.getvalue())
        self.assertNotIn('to manage', output.getvalue())

    def test_fetch_and_save_console_preserves_advisor_usd(self):
        self.run.side_effect = [self.response([self.summary]), self.response([self.action])]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertIsNotNone(self.fetcher.fetch_and_save())
        self.assertIn('Total Potential Savings: 42.00 USD/month', output.getvalue())
        self.assertNotIn('42.00 EUR', output.getvalue())
