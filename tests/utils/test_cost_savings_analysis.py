import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from src.utils.cost_savings_analysis import analyze, export_reports, load_evidence


class CostSavingsAnalysisTests(unittest.TestCase):
    def costs(self):
        return {'call1': {'items': [
            {'resourceId': 'volume-1', 'computedAmount': 100, 'currency': 'USD', 'service': 'Storage', 'region': 'r1', 'compartmentPath': '/team', 'timeUsageStarted': '2026-01-01'},
            {'resourceId': 'volume-1', 'computedAmount': -10, 'currency': 'USD', 'service': 'Storage', 'region': 'r1'},
            {'resourceId': 'volume-1', 'computedAmount': 25, 'currency': 'EUR', 'service': 'Storage', 'region': 'r1'},
            {'resourceId': 'unknown', 'computedAmount': 0},
        ]}}

    def finops(self):
        return {'discovery_complete': False, 'coverage': [{'operation': 'attachments', 'status': 'failed'}],
                'candidates': [{'resource_id': 'volume-1', 'resource_type': 'volume', 'region': 'r1',
                                'display_name': 'backup disk', 'compartment_id': 'team-id',
                                'reason': 'unattached_volume_review', 'cost_status': 'known'}]}

    def advisor(self):
        action = {'id': 'a1', 'resource-id': 'volume-1', 'resource-type': 'Volume', 'action': 'DELETE',
                  'status': 'PENDING', 'estimated-cost-saving': 20, 'recommendation-id': 'rec1'}
        return {'items': [{'id': 'rec1', 'estimated-cost-saving': 100}],
                'resource_actions': [action, dict(action)], 'coverage': {'resource_actions': {'status': 'complete'}}}

    def test_raw_currency_totals_refunds_and_optional_evidence(self):
        report = analyze(self.costs())
        self.assertEqual(report['totals'], {'USD': 90.0, 'EUR': 25.0, 'Unknown': 0.0})
        self.assertTrue(any('FinOps' in warning for warning in report['warnings']))
        self.assertEqual(analyze({'call1': {'items': []}})['totals'], {})
        with self.assertRaisesRegex(ValueError, 'computedAmount'):
            analyze({'call1': {'items': [{'computedAmount': 'bad'}]}})
        with self.assertRaisesRegex(ValueError, 'call1'):
            analyze({})

    def test_resource_details_execution_and_overlapping_savings(self):
        report = analyze(self.costs(), self.finops(), self.advisor())
        actions = report['actions']
        self.assertEqual(len(actions), 3)  # FinOps review, unique resource action, nonadditive summary.
        candidate = next(action for action in actions if action['source'] == 'FinOps')
        self.assertEqual(candidate['resource_id'], 'volume-1')
        self.assertEqual(candidate['resource_name'], 'backup disk')
        self.assertEqual(candidate['compartment_id'], 'team-id')
        self.assertEqual(candidate['observed_costs'], {'USD': 90.0, 'EUR': 25.0})
        for key in ('what', 'how', 'where', 'prerequisites', 'risk', 'rollback', 'verification', 'command'):
            self.assertTrue(candidate[key], key)
        self.assertIn('oci bv volume delete', candidate['command'])
        self.assertIn('--region', candidate['command'])
        self.assertTrue(any('failed' in warning for warning in report['warnings']))
        self.assertEqual(report['advisor_estimates_usd'], 20)
        self.assertIsNone(candidate['estimated_monthly_savings_usd'])
        self.assertIn('overlap', next(a for a in actions if a['source'] == 'Advisor')['savings_note'])

    def test_all_candidate_types_and_unknown_advisor_action(self):
        finops = {'candidates': [dict(resource_id=kind, resource_type=kind, region='r1', reason='review')
                                 for kind in ('instance', 'volume', 'boot_volume')]}
        advisor = {'resource_actions': [{'id': 'a2', 'resource-id': 'db1', 'action': 'UNKNOWN'}]}
        report = analyze(self.costs(), finops, advisor)
        self.assertEqual(len(report['actions']), 4)
        for action in report['actions']:
            self.assertTrue(action['prerequisites'])
            self.assertTrue(action['verification'])
        self.assertIn('unknown', report['actions'][-1]['how'].lower())

    def test_distinct_overlapping_actions_and_ambiguous_region(self):
        raw = {'call1': {'items': [
            {'resourceId': 'shared', 'region': 'r1', 'currency': 'USD', 'computedAmount': 10},
            {'resourceId': 'shared', 'region': 'r2', 'currency': 'USD', 'computedAmount': 20}]}}
        advisor = {'resource_actions': [
            {'id': 'a1', 'resource-id': 'shared', 'action': 'resize', 'recommendation-id': 'rec1', 'estimated-cost-saving': 15, 'status': 'PENDING'},
            {'id': 'a2', 'resource-id': 'shared', 'action': 'delete', 'recommendation-id': 'rec2', 'estimated-cost-saving': 25, 'status': 'PENDING'}]}
        report = analyze(raw, None, advisor)
        self.assertEqual(len(report['actions']), 2)
        self.assertEqual(report['advisor_estimates_usd'], 25)
        for action in report['actions']:
            self.assertEqual(action['region'], 'Unknown')
            self.assertEqual(action['observed_costs'], {})
            self.assertIn('missing', action['evidence_gaps'])

    def test_measurement_period_and_invalid_timestamp(self):
        raw = self.costs()
        raw['call1']['items'][0]['timeUsageEnded'] = '2026-02-01T00:00:00Z'
        self.assertEqual(analyze(raw)['measurement_period']['start'], '2026-01-01T00:00:00+00:00')
        raw['call1']['items'][0]['timeUsageStarted'] = 'invalid'
        with self.assertRaisesRegex(ValueError, 'timeUsageStarted'):
            analyze(raw)

    def test_all_spend_drivers_and_summary_only_advisor_preserved(self):
        summary = {'id': 'rec-only', 'name': 'Rightsize compute', 'category-id': 'cost',
                   'resource-counts': [{'status': 'PENDING', 'count': 7}], 'estimated-cost-saving': 70}
        report = analyze(self.costs(), None, {'items': [summary]})
        self.assertTrue(any(row['resource_id'] == 'volume-1' and row['currency'] == 'USD' and row['observed_cost'] == 90 for row in report['resources']))
        self.assertTrue(any(row['compartment_path'] == '/team' for row in report['compartments']))
        self.assertTrue(any(row['resource_id'] == 'unknown' for row in report['resources']))
        action = report['actions'][0]
        self.assertEqual(action['recommendation_id'], 'rec-only')
        self.assertEqual(action['affected_resource_counts'], summary['resource-counts'])
        self.assertIn('summary-only', action['savings_note'])
        self.assertEqual(report['advisor_estimates_usd'], 0)
        with tempfile.TemporaryDirectory() as folder:
            exported = export_reports(report, folder)['markdown'].read_text()
            self.assertIn('Spend by resource', exported)
            self.assertIn('Spend by compartment', exported)
            self.assertIn('rec-only', exported)

    def test_notebook_has_correct_collection_template(self):
        notebook = Path(__file__).resolve().parents[2] / 'jupe-note/cost_savings_analysis.ipynb'
        content = notebook.read_text()
        self.assertIn('--growth-collection', content)
        self.assertNotIn('--finops-collection', content)
        self.assertIn('tar -xzf', content)

    def test_executive_exports_and_loading_raw_not_merged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'out.json').write_text(json.dumps(self.costs()))
            (root / 'output_merged.csv').write_text('computedAmount\n999999\n')
            evidence = load_evidence(root)
            report = analyze(*evidence)
            paths = export_reports(report, root / 'reports')
            self.assertEqual(set(paths), {'markdown', 'html', 'csv', 'resources_csv', 'compartments_csv', 'runbook_html'})
            md = paths['markdown'].read_text()
            self.assertIn('Executive', md)
            self.assertIn('USD', md)
            self.assertIn('EUR', md)
            self.assertIn('Approval', md)
            self.assertNotIn('999999', md)
            self.assertIn('resource_id', paths['csv'].read_text())

    def test_print_friendly_executive_report_and_complete_appendices(self):
        raw = {'call1': {'items': [{'resourceId': f'resource-{i}', 'compartmentPath': f'/team-{i}',
                                  'computedAmount': i, 'currency': 'USD', 'service': 'Compute'} for i in range(15)]}}
        report = analyze(raw)
        with tempfile.TemporaryDirectory() as folder:
            paths = export_reports(report, folder)
            markup = paths['html'].read_text()
            self.assertIn('<table>', markup)
            self.assertIn('@media print', markup)
            self.assertNotIn('<pre>', markup)
            self.assertIn('Prepared at', markup)
            self.assertIn('cost_savings_resources.csv', markup)
            self.assertNotIn('<td>resource-0</td>', markup)
            self.assertIn('<td>resource-14</td>', markup)
            self.assertIn('cost_savings_compartments.csv', paths['markdown'].read_text())
            import csv
            with paths['resources_csv'].open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 15)
            with paths['compartments_csv'].open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 15)

    def test_action_csv_has_blank_owner_outcome_and_verified_savings_tracker(self):
        import csv
        report = analyze(self.costs(), self.finops(), self.advisor())
        with tempfile.TemporaryDirectory() as folder:
            path = export_reports(report, folder)['csv']
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                for column in ('owner', 'approval_date', 'execution_date', 'baseline_period',
                               'comparison_period', 'verified_savings', 'verified_currency',
                               'verification_evidence', 'outcome_notes'):
                    self.assertIn(column, row)
                    self.assertEqual(row[column], '')

    def test_oci_structured_action_and_null_metadata_export_as_inert_detail(self):
        provider_action = {'type': 'DELETE', 'description': 'Delete <script>inert</script>',
                           'url': 'https://cloud.oracle.com/storage/volume/detail?resourceId=synthetic'}
        evidence = {'resource_actions': [{'id': 'shape-action', 'action': provider_action,
                                          'resource-id': 'volume-1', 'resource-type': 'block-volume',
                                          'status': 'PENDING', 'metadata': None,
                                          'extended-metadata': {'sample': 'detail'},
                                          'estimated-cost-saving': 12}],
                    'items': [{'id': 'shape-summary', 'description': 'Summary explanation',
                               'extended-metadata': {'threshold': 10}}]}
        report = analyze(self.costs(), None, evidence)
        with tempfile.TemporaryDirectory() as folder:
            paths = export_reports(report, folder)
            markup = paths['runbook_html'].read_text()
            self.assertIn('&lt;script&gt;inert&lt;/script&gt;', markup)
            self.assertNotIn('<script>', markup)
            self.assertIn('Summary explanation', markup)
        resource_action = next(action for action in report['actions'] if action['source'] == 'Advisor')
        self.assertEqual(resource_action['action'], 'DELETE')
        self.assertEqual(resource_action['provider_action'], provider_action)
        self.assertEqual(resource_action['provider_extended_metadata'], {'sample': 'detail'})

    def test_extended_metadata_region_and_ineligible_estimate(self):
        raw = {'call1': {'items': [{'resourceId': 'volume-1', 'currency': 'EUR', 'computedAmount': 23}]}}
        advisor = {'resource_actions': [
            {'id': 'obsolete', 'resource-id': 'volume-1', 'status': 'PENDING', 'estimated-cost-saving': 30,
             'extended-metadata': {'region': 'r3', 'noLongerRecommend': True}},
            {'id': 'error', 'resource-id': 'volume-2', 'status': 'PENDING', 'estimated-cost-saving': 50,
             'extended-metadata': {'region': 'r4', 'estimatedSavingCalculationError': 'Missing price'}}]}
        report = analyze(raw, None, advisor)
        action = next(action for action in report['actions'] if action['action_id'] == 'obsolete')
        self.assertEqual(action['region'], 'r3')
        self.assertEqual(action['observed_costs'], {'EUR': 23})
        self.assertEqual(action['status'], 'NO_LONGER_RECOMMENDED')
        self.assertEqual(report['advisor_estimates_usd'], 0)
        self.assertTrue(any('Missing price' in warning for warning in report['warnings']))

    def test_provider_string_boolean_flags_keep_valid_estimates(self):
        actions = []
        for identifier, error, obsolete in [('valid-string', 'false', 'false'), ('valid-bool', False, False),
                                             ('error-string', 'true', 'false'), ('obsolete-string', 'false', 'true'),
                                             ('error-message', 'Missing price', False)]:
            actions.append({'id': identifier, 'resource-id': identifier, 'status': 'PENDING',
                            'estimated-cost-saving': 10, 'extended-metadata': {
                                'region': 'r1', 'estimatedSavingCalculationError': error, 'noLongerRecommend': obsolete}})
        report = analyze({'call1': {'items': []}}, None, {'resource_actions': actions})
        self.assertEqual(report['advisor_estimates_usd'], 20)
        by_id = {action['action_id']: action for action in report['actions']}
        self.assertEqual(by_id['valid-string']['status'], 'PENDING')
        self.assertEqual(by_id['obsolete-string']['status'], 'NO_LONGER_RECOMMENDED')
        self.assertEqual(by_id['error-string']['status'], 'ESTIMATE_ERROR')
        self.assertEqual(sum('calculation error' in warning for warning in report['warnings']), 2)

    def test_large_backlog_has_compact_executive_and_complete_runbook(self):
        actions = [{'id': f'action-{i:03}', 'resource-id': f'volume-{i:03}', 'status': 'PENDING',
                    'estimated-cost-saving': i + 1, 'metadata': {'detail': 'x' * 1000}}
                   for i in range(100)]
        report = analyze({'call1': {'items': []}}, None, {'resource_actions': actions})
        with tempfile.TemporaryDirectory() as folder:
            paths = export_reports(report, folder)
            executive = paths['html'].read_text()
            self.assertLess(len(executive), 40000)
            self.assertNotIn('volume-000', executive)
            self.assertIn('volume-099', executive)
            self.assertIn('cost_savings_runbook.html', executive)
            for action in actions:
                self.assertIn(action['resource-id'], paths['runbook_html'].read_text())
            self.assertIn('x' * 1000, paths['runbook_html'].read_text())

    def test_notebook_executes_from_root_and_notebook_directory(self):
        notebook = Path(__file__).resolve().parents[2] / 'jupe-note/cost_savings_analysis.ipynb'
        document = json.loads(notebook.read_text())
        import os
        previous = Path.cwd()
        try:
            for cwd, empty in ((notebook.parent.parent, False), (notebook.parent, False), (notebook.parent, True)):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    (root / 'out.json').write_text(json.dumps({'call1': {'items': []}} if empty else self.costs()))
                    if not empty:
                        (root / 'finops_collection.json').write_text(json.dumps(self.finops()))
                        (root / 'recommendations.json').write_text(json.dumps(self.advisor()))
                    os.chdir(cwd)
                    namespace = {'EVIDENCE_DIR': root, 'REPORT_DIR': root / 'reports',
                                 'ACTION_RESOURCE_ID': 'volume-1' if cwd == notebook.parent.parent else None}
                    captured = io.StringIO()
                    with contextlib.redirect_stdout(captured):
                        for cell in document['cells']:
                            if cell['cell_type'] == 'code':
                                exec(compile(''.join(cell['source']), str(notebook), 'exec'), namespace)
                    self.assertTrue((root / 'reports/cost_savings_executive.md').exists())
                    if namespace['ACTION_RESOURCE_ID']:
                        self.assertIn('provider_evidence:', captured.getvalue())
        finally:
            os.chdir(previous)
