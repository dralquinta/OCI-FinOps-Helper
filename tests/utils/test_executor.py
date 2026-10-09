import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

from src.utils.executor import OCIMetadataFetcher


class MetadataFetcherTests(unittest.TestCase):
    def test_duplicate_instance_ids_are_fetched_once(self):
        instance = 'ocid1.instance.oc1.region.synthetic'
        response = subprocess.CompletedProcess([], 0, json.dumps({'data': {'shape': 'shape', 'display-name': 'name'}}))
        with patch('src.utils.executor.subprocess.run', return_value=response) as run, patch('src.utils.executor.ProgressTracker'), contextlib.redirect_stdout(io.StringIO()):
            metadata, successful, failed = OCIMetadataFetcher().fetch_metadata([instance, instance])
        self.assertEqual(run.call_count, 1)
        self.assertEqual((successful, failed), (1, 0))
        self.assertEqual(metadata[instance]['resourceName'], 'name')

    def test_malformed_responses_and_timeouts_are_isolated(self):
        responses = [subprocess.CompletedProcess([], 0, '{broken'),
                     subprocess.CompletedProcess([], 0, json.dumps({'data': []})),
                     subprocess.TimeoutExpired('oci', 30)]
        with patch('src.utils.executor.subprocess.run', side_effect=responses), patch('src.utils.executor.ProgressTracker'):
            result = OCIMetadataFetcher(max_workers=1).fetch_metadata(['ocid1.instance.oc1.region.' + str(i) for i in range(3)])
        self.assertEqual(result, ({}, 0, 3))


class MetadataQueueTests(unittest.TestCase):
    def test_default_workers_are_conservative(self):
        self.assertEqual(4, OCIMetadataFetcher().max_workers)

    def test_pending_futures_are_bounded_by_workers(self):
        from concurrent.futures import Future
        pending = []
        class Pool:
            def __init__(self, max_workers):
                self.workers = max_workers
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def submit(self, function, instance):
                pending.append(instance)
                if len(pending) > self.workers:
                    raise AssertionError('unbounded metadata queue')
                future = Future()
                future.set_result((instance, {'shape': 'shape'}))
                return future
        def wait_for_next(futures, **kwargs):
            first = next(iter(futures))
            pending.pop(0)
            return {first}, set(futures) - {first}
        with patch('src.utils.executor.ThreadPoolExecutor', Pool), patch('src.utils.executor.wait', side_effect=wait_for_next, create=True), patch('src.utils.executor.ProgressTracker'):
            metadata, successful, failed = OCIMetadataFetcher(max_workers=2).fetch_metadata([str(i) for i in range(10)])
        self.assertEqual((10, 0), (successful, failed))
        self.assertEqual(10, len(metadata))
