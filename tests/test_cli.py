"""CLI behavior without OCI authentication or network calls."""

import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from src.collector import main


class CollectorCLITests(unittest.TestCase):
    positional = ['ocid1.tenancy.oc1..test', 'us-ashburn-1', '2026-01-01', '2026-02-01']
    named = ['--tenancy-ocid', positional[0], '--home-region', positional[1],
             '--from-date', positional[2], '--to-date', positional[3]]

    def invoke(self, arguments):
        with patch.object(sys, 'argv', ['collector', *arguments]), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()), \
                patch('src.collector.OCICostCollector') as collector, \
                patch('src.collector.OCIRecommendationsFetcher') as recommendations:
            collector.return_value.collect.return_value = True
            recommendations.return_value.fetch_and_save.return_value = 'report'
            with self.assertRaises(SystemExit) as exit_status:
                main()
            return exit_status.exception.code, collector, recommendations

    def test_named_arguments_match_positional_arguments(self):
        positional_status, positional_collector, _ = self.invoke(self.positional)
        named_status, named_collector, _ = self.invoke(self.named)
        self.assertEqual(0, positional_status)
        self.assertEqual(0, named_status)
        self.assertEqual(positional_collector.call_args, named_collector.call_args)
        self.assertTrue(named_collector.call_args.kwargs['streaming'])
        self.assertEqual(positional_collector.return_value.collect.call_args,
                         named_collector.return_value.collect.call_args)

    def test_growth_enabled_by_default(self):
        status, collector, _ = self.invoke(self.positional)
        self.assertEqual(0, status)
        self.assertTrue(collector.return_value.collect.call_args.kwargs['growth_collection'])

    def test_issue_date_flag_names(self):
        arguments = [name.replace('--from-date', '--from').replace('--to-date', '--to')
                     for name in self.named]
        status, collector, _ = self.invoke(arguments)
        self.assertEqual(0, status)
        self.assertEqual('2026-01-01', collector.call_args.kwargs['from_date'])
        self.assertEqual('2026-02-01', collector.call_args.kwargs['to_date'])

    def test_help_documents_named_arguments_and_growth_opt_out(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['collector', '--help']), \
                contextlib.redirect_stdout(output), \
                patch('src.collector.OCICostCollector') as collector:
            with self.assertRaises(SystemExit) as status:
                main()
        self.assertEqual(0, status.exception.code)
        for option in ['--tenancy-ocid', '--home-region', '--from', '--to',
                       '--no-growth-collection']:
            self.assertIn(option, output.getvalue())
        collector.assert_not_called()

    def test_growth_opt_out(self):
        status, collector, _ = self.invoke([*self.positional, '--no-growth-collection'])
        self.assertEqual(0, status)
        self.assertFalse(collector.return_value.collect.call_args.kwargs['growth_collection'])

    def test_explicit_growth_flag_remains_supported(self):
        status, collector, _ = self.invoke([*self.positional, '--growth-collection'])
        self.assertEqual(0, status)
        self.assertTrue(collector.return_value.collect.call_args.kwargs['growth_collection'])

    def test_only_growth_skips_other_stages(self):
        status, collector, recommendations = self.invoke([*self.positional, '--only-growth'])
        self.assertEqual(0, status)
        flags = collector.return_value.collect.call_args.kwargs
        self.assertTrue(flags['growth_collection'])
        for stage in ['skip_cost', 'skip_usage', 'skip_enrichment', 'skip_recommendations']:
            self.assertTrue(flags[stage])
        recommendations.assert_not_called()

    def test_only_recommendations_remains_fast(self):
        status, collector, recommendations = self.invoke([*self.positional, '--only-recommendations'])
        self.assertEqual(0, status)
        collector.return_value.collect.assert_not_called()
        recommendations.return_value.fetch_and_save.assert_called_once_with()

    def test_invalid_arguments_fail_before_collection(self):
        cases = [
            self.named[:-2],
            [*self.positional, '--home-region', 'eu-frankfurt-1'],
            [*self.positional, '--growth-collection', '--no-growth-collection'],
            [*self.positional, '--only-growth', '--only-recommendations'],
            [*self.positional, '--only-growth', '--no-growth-collection'],
            [*self.positional[:2], '2026-02-30', self.positional[3]],
            [*self.positional[:2], '2026-2-01', self.positional[3]],
            [*self.positional[:2], '2026-03-01', self.positional[3]],
            [*self.positional[:2], self.positional[3], self.positional[3]],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                status, collector, recommendations = self.invoke(arguments)
                self.assertEqual(2, status)
                collector.assert_not_called()
                recommendations.assert_not_called()
