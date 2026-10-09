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
                return [{'name': 'CpuUtilization', 'namespace': 'oci_computeagent'}]
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
            return None if command[command.index('--compartment-id')+1] == 'tenancy' else []
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


class GrowthPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.collector = OCIGrowthCollector('tenancy', 'home', self.directory.name)
        self.collector.compartments = ['tenancy', 'child']

    def test_conservative_default_workers(self):
        self.assertEqual(4, self.collector.max_workers_tags)
        self.assertEqual(4, self.collector.max_workers_compartments)

    def test_monitoring_discovers_once_per_scope_and_overlaps_scopes(self):
        import threading
        barrier = threading.Barrier(2)
        commands = []
        def execute(command, description):
            commands.append(command)
            if 'region-subscription' in command:
                return [{'region-name': 'home', 'status': 'READY'}]
            if 'metric' in command:
                barrier.wait(timeout=2)
                return [{'name': 'CpuUtilization', 'namespace': 'oci_computeagent'},
                        {'name': 'IgnoreMe', 'namespace': 'unsupported'}]
            return [{'aggregated-datapoints': [{'value': 5}]}]
        with patch.object(self.collector, '_execute_oci_command', side_effect=execute):
            result = self.collector.collect_performance_metrics('2026-09-01', '2026-09-02')
        self.assertEqual(2, len([c for c in commands if 'metric' in c]))
        self.assertTrue(all('--namespace' not in c for c in commands if 'metric' in c))
        self.assertEqual(2, len([c for c in commands if 'summarize-metrics-data' in c]))
        self.assertEqual(2, result['metrics_by_namespace']['oci_computeagent']['metrics']['CpuUtilization']['data_points'])
        self.assertFalse(any(row['status'] == 'failed' for row in result['coverage']))

    def test_audit_daily_exclusive_windows_totals_and_sample_cap(self):
        import json
        import subprocess
        commands = []
        events = [{'data': {'eventName': 'Create', 'resourceName': 'Instance',
                           'identity': {'principalName': 'user'}}}] * 600
        def execute(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps({'data': events}), '')
        with patch('src.utils.growth_collector.run_oci', side_effect=execute), patch('src.utils.growth_collector.ProgressTracker'):
            result = self.collector.collect_audit_events('2026-09-01', '2026-09-03')
        self.assertEqual(4, len(commands))
        windows = {(c[c.index('--start-time')+1], c[c.index('--end-time')+1]) for c in commands}
        self.assertEqual({('2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z'),
                          ('2026-09-02T00:00:00Z', '2026-09-03T00:00:00Z')}, windows)
        self.assertEqual(2400, result['total_events'])
        self.assertEqual(1000, len(result['sample_events']))
        self.assertTrue(result['collection_period']['end_exclusive'])
        self.assertEqual(4, len(result['coverage']))

    def test_audit_failure_keeps_successful_evidence_and_marks_coverage(self):
        import json
        import subprocess
        def execute(command, **kwargs):
            if command[command.index('--compartment-id')+1] == 'child':
                raise subprocess.TimeoutExpired(command, 60)
            return subprocess.CompletedProcess(command, 0, json.dumps({'data': []}), '')
        with patch('src.utils.growth_collector.run_oci', side_effect=execute), patch('src.utils.growth_collector.ProgressTracker'):
            result = self.collector.collect_audit_events('2026-09-01', '2026-09-02')
        self.assertEqual({'empty', 'failed'}, {r['status'] for r in result['coverage']})

    def test_audit_pages_incrementally_and_preserves_all_totals(self):
        import json
        import subprocess
        self.collector.compartments = ['tenancy']
        event = {'data': {'eventName': 'Create'}}
        pages = [subprocess.CompletedProcess([], 0, json.dumps({'data': [event] * 700, 'opc-next-page': 'next'}), ''),
                 subprocess.CompletedProcess([], 0, json.dumps({'data': [event] * 700}), '')]
        with patch('src.utils.growth_collector.run_oci', side_effect=pages) as runner, patch('src.utils.growth_collector.ProgressTracker'):
            result = self.collector.collect_audit_events('2026-09-01', '2026-09-02')
        self.assertEqual(1400, result['total_events'])
        self.assertEqual(1000, len(result['sample_events']))
        self.assertEqual(2, runner.call_count)
        for call in runner.call_args_list:
            self.assertNotIn('--all', call.args[0])
            self.assertNotIn('--limit', call.args[0])
        second = runner.call_args_list[1].args[0]
        self.assertEqual('next', second[second.index('--page')+1])

    def test_repeated_audit_page_token_stops_with_failed_coverage(self):
        import json
        import subprocess
        self.collector.compartments = ['tenancy']
        response = subprocess.CompletedProcess([], 0, json.dumps({'data': [], 'opc-next-page': 'same'}), '')
        with patch('src.utils.growth_collector.run_oci', return_value=response) as runner, patch('src.utils.growth_collector.ProgressTracker'):
            result = self.collector.collect_audit_events('2026-09-01', '2026-09-02')
        self.assertEqual(2, runner.call_count)
        self.assertEqual('failed', result['coverage'][0]['status'])


class MonitoringRetentionTests(unittest.TestCase):
    def test_sample_retention_bounds_points_but_counts_all_streams(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            collector = OCIGrowthCollector('tenancy', 'home', directory)
            collector.compartments = ['one', 'two']
            streams = [{'name': 'CpuUtilization', 'dimensions': {'resourceId': str(index)},
                        'aggregated-datapoints': [{'value': point} for point in range(100)]}
                       for index in range(100)]
            def execute(command, description):
                if 'region-subscription' in command:
                    return [{'region-name': 'home', 'status': 'READY'}]
                if 'metric' in command:
                    return [{'namespace': 'oci_computeagent', 'name': 'CpuUtilization'}]
                return streams
            with patch.object(collector, '_execute_oci_command', side_effect=execute):
                result = collector.collect_performance_metrics('2026-09-01', '2026-09-02')
        metric = result['metrics_by_namespace']['oci_computeagent']['metrics']['CpuUtilization']
        self.assertEqual(20000, metric['data_points'])
        retained = sum(len(sample['aggregated-datapoints']) for sample in metric['samples'])
        self.assertLessEqual(retained, 1000)
        self.assertEqual(1000, metric['retained_data_points'])
        self.assertEqual(200, metric['stream_count'])
        self.assertTrue(metric['samples_truncated'])
        self.assertIn('1000', result['sampling_note'])
        self.assertFalse(any(row['status'] == 'failed' for row in result['coverage']))
