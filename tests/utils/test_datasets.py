import json
from pathlib import Path
import tempfile
import threading
import tracemalloc
import unittest

from src.utils.datasets import DiskDatasetStore


class DiskDatasetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DiskDatasetStore(self.directory.name)
        self.addCleanup(self.store.close)

    def test_merge_preserves_cost_rows_ambiguous_keys_and_schema_union(self):
        costs = [
            {'resourceId': 'a', 'timeUsageStarted': 'day', 'computedAmount': 1.123456789012345, 'region': 'cost'},
            {'resourceId': 'a', 'timeUsageStarted': 'day', 'computedAmount': 2, 'shape': ''},
            {'resourceId': None, 'timeUsageStarted': 'day', 'computedAmount': 3},
            {'resourceId': 'a', 'timeUsageStarted': None, 'computedAmount': 4},
        ]
        usage = [
            {'resourceId': 'a', 'timeUsageStarted': 'day', 'region': 'usage', 'shape': 'one', 'resourceName': 'same'},
            {'resourceId': 'a', 'timeUsageStarted': 'day', 'region': 'usage', 'shape': 'two', 'resourceName': 'same'},
            {'resourceId': None, 'timeUsageStarted': 'day', 'resourceName': 'null-must-not-join'},
        ]
        self.store.add_page('COST', 'b', 0, costs[2:], {'currency': 'USD'})
        self.store.add_page('COST', 'a', 0, costs[:2], {'currency': 'USD'})
        self.store.add_page('COST', 'b', 1, [{'computedAmount': 0, 'extra': 'schema-drift'}])
        self.store.add_page('USAGE', 'a', 0, usage)
        chunks = list(self.store.iter_merged_chunks(2))
        self.assertEqual([2, 2, 1], [len(frame) for frame in chunks])
        rows = [row for frame in chunks for row in frame.to_dict('records')]
        self.assertEqual(5, len(rows))
        self.assertEqual('cost', rows[0]['region'])
        self.assertEqual('usage', rows[1]['region'])
        self.assertEqual('same', rows[0]['resourceName'])
        self.assertTrue(__import__('pandas').isna(rows[1]['shape']))
        self.assertTrue(__import__('pandas').isna(rows[2]['resourceName']))
        self.assertIn('extra', self.store.merged_fieldnames)
        self.assertTrue(all(list(frame.columns) == list(self.store.merged_fieldnames) for frame in chunks))
        dataset = self.store.dataset('COST')
        self.assertEqual(5, dataset.count)
        self.assertEqual(list(dataset.iter_items()), list(dataset.iter_items()))
        self.assertEqual(costs[0], next(dataset.iter_items()))

    def test_raw_json_precise_metadata_threaded_pages_and_cleanup(self):
        amount = 1.123456789012345
        def add(partition):
            self.store.add_page('COST', partition, 0, [{'computedAmount': amount, 'currency': 'USD'}], {'foo': partition})
        threads = [threading.Thread(target=add, args=(part,)) for part in ('z', 'a')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        path = Path(self.directory.name) / 'raw.json'
        self.store.write_raw_json(path, {'call1': self.store.dataset('COST'), 'call2': None})
        actual = json.loads(path.read_text())
        self.assertEqual(amount, actual['call1']['items'][0]['computedAmount'])
        self.assertEqual('a', actual['call1']['foo'])
        self.assertIsNone(actual['call2'])
        database_path = self.store.path
        self.assertTrue(database_path.exists())
        self.store.close()
        self.assertFalse(database_path.exists())

    def test_indexed_cost_lookup_and_disk_metadata(self):
        instance = 'ocid1.instance.oc1.region.test'
        self.store.add_page('COST', 'a', 0, [
            {'resourceId': instance, 'region': 'one', 'currency': 'USD', 'computedAmount': 1.5},
            {'resourceId': instance, 'region': None, 'currency': 'USD', 'computedAmount': 0.25},
            {'resourceId': instance, 'region': 'two', 'currency': 'EUR', 'computedAmount': 9},
            {'resourceId': instance, 'region': 123, 'currency': 'USD', 'computedAmount': 99},
        ])
        dataset = self.store.dataset('COST')
        self.assertEqual([instance], list(dataset.compute_instance_ids()))
        self.assertEqual({'USD': 1.5}, dataset.lookup_costs(instance, 'one'))
        self.assertEqual({'USD': .25}, dataset.lookup_costs(instance, None))
        self.assertEqual([instance], list(self.store.missing_instance_ids()))
        self.store.add_metadata({instance: {'shape': 'shape', 'resourceName': 'name'}})
        self.assertEqual([], list(self.store.missing_instance_ids()))
        self.assertEqual({instance: {'shape': 'shape', 'resourceName': 'name'}}, self.store.lookup_metadata([instance, 'unknown']))
        self.assertEqual([(instance, {'shape': 'shape', 'resourceName': 'name'})], list(self.store.iter_metadata()))

    def test_one_hundred_thousand_rows_use_bounded_merge_chunks(self):
        tracemalloc.start()
        try:
            for page in range(100):
                rows = [{'resourceId': 'resource-' + str(page * 1000 + index), 'timeUsageStarted': 'day',
                         'computedAmount': 0.123456789, 'currency': 'USD'} for index in range(1000)]
                self.store.add_page('COST', 'a', page, rows)
            self.store.add_page('USAGE', 'a', 0, [{'resourceId': 'resource-' + str(index), 'timeUsageStarted': 'day', 'shape': 'shape'} for index in range(100)])
            count = 0
            for frame in self.store.iter_merged_chunks(2000):
                self.assertLessEqual(len(frame), 2000)
                count += len(frame)
            self.assertEqual(100000, count)
            self.assertEqual(100000, self.store.dataset('COST').count)
            self.assertLess(tracemalloc.get_traced_memory()[1], 32 * 1024 * 1024)
        finally:
            tracemalloc.stop()


class MetadataCacheStreamingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DiskDatasetStore(self.directory.name)
        self.addCleanup(self.store.close)

    def cache(self, text):
        path = Path(self.directory.name) / 'cache.json'
        path.write_text(text)
        return path

    def test_page_schema_updates_scale_with_fields_not_record_count(self):
        statements = []
        self.store._writer.set_trace_callback(statements.append)
        self.store.add_page('COST', 'a', 0, [{'a': index, 'b': index} for index in range(100)])
        updates = [statement for statement in statements if 'INSERT OR IGNORE INTO fields' in statement]
        self.assertLessEqual(len(updates), 2)

    def test_unordered_cache_ttl_validation_and_original_timestamps(self):
        entries = {
            'hit': {'fetched_at': 950, 'metadata': {'shape': 'shape', 'resourceName': 'name'}},
            'old': {'fetched_at': 1000-86400, 'metadata': {'shape': 'old'}},
            'future': {'fetched_at': 1001, 'metadata': {'shape': 'future'}},
            'invalid': {'fetched_at': 950, 'metadata': {'shape': None}},
        }
        path = self.cache(json.dumps({'entries': entries, 'region': 'home', 'tenancy': 'tenancy'}))
        self.assertEqual(1, self.store.load_metadata_cache(path, 'tenancy', 'home', 1000))
        self.store.add_metadata({'fetched': {'shape': 'new'}}, fetched_at=1000)
        self.store.write_metadata_files(self.directory.name, 'tenancy', 'home', 1100)
        saved = json.loads((Path(self.directory.name) / 'instance_metadata_cache.json').read_text())
        self.assertEqual(950, saved['entries']['hit']['fetched_at'])
        self.assertEqual(1000, saved['entries']['fetched']['fetched_at'])
        self.assertEqual({'hit', 'fetched'}, set(saved['entries']))
        self.assertEqual({'hit': {'shape': 'shape', 'resourceName': 'name'}}, self.store.lookup_metadata(['hit', 'old', 'future', 'invalid']))

    def test_malformed_or_wrong_scope_discards_staged_entries(self):
        entry = {'hit': {'fetched_at': 950, 'metadata': {'shape': 'shape'}}}
        examples = [json.dumps({'entries': entry, 'region': 'home', 'tenancy': 'wrong'}),
                    json.dumps({'entries': entry, 'region': 'home', 'tenancy': 'tenancy'})[:-1],
                    json.dumps({'entries': entry, 'region': 'home', 'tenancy': 'tenancy'}) + ' trailing',
                    '{"tenancy":"tenancy","region":"home","entries":[]}',
                    '{"entries": {"hit":']
        for text in examples:
            with self.subTest(cache=text):
                self.assertEqual(0, self.store.load_metadata_cache(self.cache(text), 'tenancy', 'home', 1000))
                self.assertEqual({}, self.store.lookup_metadata(['hit']))

    def test_hundred_thousand_cache_entries_stream_with_bounded_allocation(self):
        path = Path(self.directory.name) / 'cache.json'
        with path.open('w') as output:
            output.write('{"entries":{')
            for index in range(100000):
                if index:
                    output.write(',')
                output.write(json.dumps('id-' + str(index)) + ':' + json.dumps({'fetched_at': 900, 'metadata': {'shape': 'shape', 'resourceName': 'name'}}))
            output.write('},"region":"home","tenancy":"tenancy"}')
        tracemalloc.start()
        try:
            self.assertEqual(100000, self.store.load_metadata_cache(path, 'tenancy', 'home', 1000))
            self.store.write_metadata_files(self.directory.name, 'tenancy', 'home', 1100)
            self.assertLess(tracemalloc.get_traced_memory()[1], 32 * 1024 * 1024)
        finally:
            tracemalloc.stop()
        self.assertEqual({'id-99999': {'shape': 'shape', 'resourceName': 'name'}}, self.store.lookup_metadata(['id-99999']))
