import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
from src.utils.growth_collector import OCIGrowthCollector


class MonitoringEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.collector = OCIGrowthCollector('tenancy', 'home', self.directory.name)
        self.collector.compartments = ['tenancy', 'child']

    def test_scopes_discovered_metrics_to_every_region_and_compartment_without_truncation(self):
        commands = []
        series = [{'name': 'CpuUtilization', 'dimensions': {'resourceId': str(i)}, 'aggregated-datapoints': [{'value': 0}]} for i in range(125)]
        def execute(command, description):
            commands.append(command)
            if 'region-subscription' in command:
                return [{'region-name': 'home', 'status': 'READY'}, {'region-name': 'other', 'status': 'READY'}]
            if 'metric' in command:
                return [{'name': 'CpuUtilization'}] if command[command.index('--namespace') + 1] == 'oci_computeagent' else []
            return series
        with patch.object(self.collector, '_execute_oci_command', side_effect=execute), contextlib.redirect_stdout(io.StringIO()):
            result = self.collector.collect_performance_metrics('2026-09-01', '2026-10-01')
        queries = [c for c in commands if 'summarize-metrics-data' in c]
        self.assertEqual(4, len(queries))
        self.assertEqual({('home', 'tenancy'), ('home', 'child'), ('other', 'tenancy'), ('other', 'child')}, {(c[c.index('--region')+1], c[c.index('--compartment-id')+1]) for c in queries})
        for command in queries:
            self.assertIn('CpuUtilization[1h].mean()', command)
            self.assertEqual('2026-10-01T00:00:00Z', command[command.index('--end-time') + 1])
        samples = result['metrics_by_namespace']['oci_computeagent']['metrics']['CpuUtilization']['samples']
        self.assertEqual(500, len(samples))
        self.assertEqual({'home', 'other'}, {s['region'] for s in samples})
        self.assertTrue(result['coverage'])

    def test_permission_failure_is_distinct_from_successful_empty_data(self):
        def execute(command, description):
            if 'region-subscription' in command:
                return [{'region-name': 'home', 'status': 'READY'}]
            return None if '--namespace' in command and command[command.index('--namespace')+1] == 'oci_computeagent' else []
        with patch.object(self.collector, '_execute_oci_command', side_effect=execute), contextlib.redirect_stdout(io.StringIO()):
            result = self.collector.collect_performance_metrics('2026-09-01', '2026-10-01')
        statuses = {row['status'] for row in result['coverage']}
        self.assertIn('failed', statuses)
        self.assertIn('empty', statuses)
        self.assertEqual({}, result['metrics_by_namespace']['oci_computeagent']['metrics'])

    def test_collect_all_integrates_finops_even_without_date_range(self):
        with patch.object(self.collector, '_get_all_compartments', return_value=['tenancy']), patch.object(self.collector, 'collect_tag_namespaces', return_value=[]), patch.object(self.collector, 'collect_tag_definitions', return_value={}), patch.object(self.collector, 'collect_tag_defaults', return_value=[]), patch.object(self.collector, 'collect_event_rules', return_value={}), patch.object(self.collector, '_save_results'), patch('src.utils.growth_collector.OCIFinOpsCollector') as finops, contextlib.redirect_stdout(io.StringIO()):
            finops.return_value.collect_all.return_value = {'candidates': []}
            result = self.collector.collect_all()
        self.assertEqual({'candidates': []}, result['finops'])
        self.assertTrue(finops.call_args.kwargs['execute_command'])

    def test_search_callback_preserves_next_page_envelope(self):
        import json
        import subprocess
        response = {'data': {'items': [{'identifier': 'resource'}]}, 'opc-next-page': 'next'}
        with patch('src.utils.growth_collector.ProgressSpinner'), patch('src.utils.growth_collector.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(response), '')):
            actual = self.collector._execute_oci_command(['oci', 'search', 'resource', 'structured-search'], 'Search')
        self.assertEqual(response, actual)

    def test_summary_exposes_finops_candidates_and_failed_coverage(self):
        from pathlib import Path
        output = Path(self.directory.name) / 'summary.txt'
        self.collector._generate_summary_report({'finops': {'regions': ['home'], 'candidates': [{'reason': 'unattached_volume'}], 'coverage': [{'status': 'failed'}]}}, output)
        summary = output.read_text()
        self.assertIn('FINOPS RESOURCE EVIDENCE', summary)
        self.assertIn('Review Candidates: 1', summary)
        self.assertIn('Failed Source Queries: 1', summary)
