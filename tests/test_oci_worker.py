"""Persistent OCI protocol, bounded concurrency and lifecycle regressions."""

import concurrent.futures
import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from src.oci_worker import OCIWorker, OCIWorkerPool, serve


FAKE_WORKER = '''
import json, os, sys, time
count = 0
for line in sys.stdin:
    request = json.loads(line)
    count += 1
    arguments = request['arguments']
    if arguments[0] == 'sleep':
        time.sleep(float(arguments[1]))
    result = {'returncode': 7 if arguments[0] == 'fail' else 0,
              'stdout': json.dumps({'pid': os.getpid(), 'count': count}) + '\\n',
              'stderr': 'diagnostic\\n'}
    if arguments[0] == 'large':
        result['stdout'] = 'x' * 1000000 + '\\r\\n'
    print(json.dumps(result), flush=True)
'''


class OCIWorkerTests(unittest.TestCase):
    def worker(self):
        return OCIWorker(command=[sys.executable, '-u', '-c', FAKE_WORKER])

    def test_protocol_captures_output_and_reuses_invoker(self):
        requests = io.StringIO(json.dumps({'arguments': ['--version']}) + '\n' +
                               json.dumps({'arguments': ['iam', '--help']}) + '\n')
        responses = io.StringIO()
        arguments_seen = []
        def invoke(arguments):
            arguments_seen.append(arguments)
            print('output\nwith newline')
            print('warning', file=sys.stderr)
            self.assertEqual('', sys.stdin.read())
            return 3
        serve(requests, responses, invoke)
        results = [json.loads(line) for line in responses.getvalue().splitlines()]
        self.assertEqual([['--version'], ['iam', '--help']], arguments_seen)
        self.assertEqual(2, len(results))
        self.assertEqual({'returncode': 3, 'stdout': 'output\nwith newline\n',
                          'stderr': 'warning\n'}, results[0])

    def test_system_exit_message_becomes_stderr_and_numeric_failure(self):
        responses = io.StringIO()
        serve(io.StringIO(json.dumps({'arguments': ['iam']}) + '\n'),
              responses, lambda arguments: 'Abort: ')
        result = json.loads(responses.getvalue())
        self.assertEqual(1, result['returncode'])
        self.assertEqual('Abort: \n', result['stderr'])

    def test_completed_process_and_bytes_semantics_reuse_process(self):
        with OCIWorkerPool(max_workers=1, worker_factory=self.worker) as pool:
            first = pool.run(['oci', '--version'], capture_output=True, text=True, timeout=2)
            second = pool.run(['oci', '--version'], capture_output=True, timeout=2)
            self.assertIsInstance(first, subprocess.CompletedProcess)
            self.assertEqual(['oci', '--version'], first.args)
            self.assertEqual(0, first.returncode)
            self.assertEqual('diagnostic\n', first.stderr)
            self.assertIsInstance(second.stdout, bytes)
            first_data, second_data = json.loads(first.stdout), json.loads(second.stdout)
            self.assertEqual(first_data['pid'], second_data['pid'])
            self.assertEqual(2, second_data['count'])
            process = pool.workers[0].process
        self.assertIsNotNone(process.poll())

    def test_timeout_kills_worker_and_next_command_starts_new_process(self):
        with OCIWorkerPool(max_workers=1, worker_factory=self.worker) as pool:
            initial = pool.run(['oci', '--version'], capture_output=True, text=True, timeout=2)
            process = pool.workers[0].process
            with self.assertRaises(subprocess.TimeoutExpired):
                pool.run(['oci', 'sleep', '2'], capture_output=True, text=True, timeout=0.05)
            self.assertIsNotNone(process.poll())
            replacement = pool.run(['oci', '--version'], capture_output=True, text=True, timeout=2)
            self.assertNotEqual(json.loads(initial.stdout)['pid'], json.loads(replacement.stdout)['pid'])
            self.assertEqual(1, json.loads(replacement.stdout)['count'])

    def test_failed_command_not_retried_and_check_preserves_output(self):
        with OCIWorkerPool(max_workers=1, worker_factory=self.worker) as pool:
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                pool.run(['oci', 'fail'], capture_output=True, text=True, check=True, timeout=2)
            self.assertEqual(7, failure.exception.returncode)
            self.assertEqual(1, json.loads(failure.exception.stdout)['count'])
            self.assertEqual('diagnostic\n', failure.exception.stderr)
            following = pool.run(['oci', '--version'], capture_output=True, text=True, timeout=2)
            self.assertEqual(2, json.loads(following.stdout)['count'])

    def test_parallel_requests_use_at_most_four_persistent_processes(self):
        with OCIWorkerPool(max_workers=4, worker_factory=self.worker) as pool:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _: pool.run(
                    ['oci', 'sleep', '0.05'], capture_output=True, text=True, timeout=2), range(16)))
            self.assertEqual(4, len({json.loads(result.stdout)['pid'] for result in results}))
            self.assertEqual(16, len(results))
            self.assertTrue(all(result.returncode == 0 for result in results))
            processes = [worker.process for worker in pool.workers]
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_keyboard_interrupt_closes_workers(self):
        pool = OCIWorkerPool(max_workers=1, worker_factory=self.worker)
        with self.assertRaises(KeyboardInterrupt):
            with pool:
                pool.run(['oci', '--version'], capture_output=True, text=True, timeout=2)
                process = pool.workers[0].process
                raise KeyboardInterrupt()
        self.assertIsNotNone(process.poll())

    def test_large_output_drains_pipe_and_text_normalizes_newlines(self):
        with OCIWorkerPool(max_workers=1, worker_factory=self.worker) as pool:
            result = pool.run(['oci', 'large'], capture_output=True, text=True, timeout=2)
            self.assertEqual('x' * 1000000 + '\n', result.stdout)

    def test_source_worker_command_uses_absolute_module_path(self):
        worker = OCIWorker()
        with patch.object(sys, 'frozen', False, create=True), \
                patch('src.oci_worker.subprocess.Popen') as popen:
            worker._start()
        self.assertEqual([sys.executable, '-u'], popen.call_args.args[0][:2])
        self.assertTrue(popen.call_args.args[0][2].endswith('/src/oci_worker.py'))
        self.assertTrue(popen.call_args.args[0][2].startswith('/'))

    def test_frozen_worker_reuses_executable(self):
        worker = OCIWorker()
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', '/binary/helper'), \
                patch('src.oci_worker.subprocess.Popen') as popen:
            worker._start()
        self.assertEqual(['/binary/helper', '--internal-oci-worker'], popen.call_args.args[0])


class WorkerDispatchTests(unittest.TestCase):
    def test_nested_context_retains_workers_until_outer_collection_finishes(self):
        from src.distribution import oci_worker_pool
        with patch('src.distribution.OCIWorkerPool') as pool_class, \
                patch('src.distribution.worker_available', return_value=True):
            with oci_worker_pool() as outer:
                with oci_worker_pool() as inner:
                    self.assertIs(outer, inner)
                pool_class.return_value.close.assert_not_called()
            pool_class.return_value.close.assert_called_once()

    def test_internal_worker_dispatch_does_not_collect(self):
        from src.distribution import main
        with patch('src.oci_worker.serve', return_value=0) as worker:
            self.assertEqual(0, main(['--internal-oci-worker']))
        worker.assert_called_once_with()

    def test_collection_context_routes_oci_and_restores_normal_dispatch(self):
        from src.distribution import oci_worker_pool, run_oci
        with patch('src.distribution.OCIWorkerPool') as pool_class, \
                patch('src.distribution.worker_available', return_value=True), \
                patch('src.distribution.subprocess.run') as subprocess_run:
            pool = pool_class.return_value
            pool.run.return_value = subprocess.CompletedProcess(['oci'], 0, 'ok', '')
            with oci_worker_pool(max_workers=4):
                self.assertEqual('ok', run_oci(['oci', '--version'], capture_output=True, text=True).stdout)
            pool.run.assert_called_once()
            pool.close.assert_called_once()
            subprocess_run.assert_not_called()
            run_oci(['oci', '--version'], capture_output=True, text=True)
            subprocess_run.assert_called_once()

    def test_unavailable_sdk_and_custom_environment_preserve_subprocess_path(self):
        from src.distribution import oci_worker_pool, run_oci
        with patch('src.distribution.worker_available', return_value=False), \
                patch('src.distribution.subprocess.run') as subprocess_run:
            with oci_worker_pool():
                run_oci(['oci', '--version'], capture_output=True, text=True)
            subprocess_run.assert_called_once()
        with patch('src.distribution.worker_available', return_value=True), \
                patch('src.distribution.OCIWorkerPool') as pool_class, \
                patch('src.distribution.subprocess.run') as subprocess_run:
            with oci_worker_pool():
                run_oci(['oci', '--version'], capture_output=True, text=True, env={'CUSTOM': 'value'})
            pool_class.return_value.run.assert_not_called()
            subprocess_run.assert_called_once()
