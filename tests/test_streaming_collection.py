"""End-to-end bounded-page collection using real disk merge and report exports."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from src.collector import OCICostCollector


def generated_rows(kind, count):
    for index in range(count):
        row = {'resourceId': f'resource-{index}', 'timeUsageStarted': '2026-09-01T00:00:00Z',
               'currency': 'USD', 'description': f'synthetic metadata {index} ' + 'x' * 150}
        if kind == 'COST':
            yield dict(row, computedAmount=12.345, computedQuantity=1.234567,
                       platform='existing' if index == 0 else '')
        else:
            for sku in ('A', 'B'):
                yield dict(row, platform='Linux', region='synthetic-region', skuPartNumber=sku)


def add_generated_pages(store, kind, partition, count, page_size=1000):
    page, sequence = [], 0
    for row in generated_rows(kind, count):
        page.append(row)
        if len(page) == page_size:
            store.add_page(kind, partition, sequence, page)
            sequence += 1
            page = []
    if page:
        store.add_page(kind, partition, sequence, page)
    return True


def page_api(count):
    def fake(executor, store, kind=None, fields=None, partition=0, start=None, end=None, **kwargs):
        kind = kind or kwargs.get('query_type')
        return add_generated_pages(store, kind, partition, count)
    return fake


class StreamingCollectionTests(unittest.TestCase):
    def test_slow_consumer_cannot_submit_entire_dataset_as_futures(self):
        from src.utils.parallel import bounded_map
        submitted = []
        def source():
            for index in range(1000000):
                submitted.append(index)
                yield index
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = bounded_map(executor, lambda value: 'x' * 1000, source(), max_pending=4)
            self.assertEqual(next(results), 'x' * 1000)
            self.assertLessEqual(len(submitted), 4)
            for _ in range(10):
                next(results)
            self.assertLessEqual(len(submitted), 14)
            results.close()

    def test_real_disk_pipeline_preserves_cardinality_precision_and_bounded_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic-tenancy', 'synthetic-region',
                                         '2026-09-01', '2026-09-02', directory, streaming=True)
            frame_class = __import__('pandas').DataFrame
            original_init = frame_class.__init__
            original_records = frame_class.from_records
            frame_sizes = []
            def bounded_frame(frame, *args, **kwargs):
                original_init(frame, *args, **kwargs)
                frame_sizes.append(len(frame))
                self.assertLessEqual(len(frame), 2000, 'whole dataset retained in a DataFrame')
            def bounded_records(*args, **kwargs):
                frame = original_records(*args, **kwargs)
                frame_sizes.append(len(frame))
                self.assertLessEqual(len(frame), 2000)
                return frame
            with patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=page_api(4501)), \
                 patch.object(frame_class, '__init__', new=bounded_frame), \
                 patch.object(frame_class, 'from_records', new=bounded_records), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(collector.collect(skip_enrichment=True, skip_recommendations=True,
                                                  growth_collection=False))
            self.assertTrue(frame_sizes, 'export should process actual bounded DataFrames')
            with (Path(directory) / 'output_merged.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4501)
            self.assertAlmostEqual(sum(float(row['computedAmount']) for row in rows), 4501 * 12.35, places=5)
            self.assertEqual(rows[0]['platform'], 'existing')
            self.assertEqual(rows[1]['platform'], 'Linux')
            self.assertTrue(all(row['skuPartNumber'] == '' for row in rows))
            self.assertEqual(rows[0]['computedQuantity'], '1.234567')
            raw = json.loads((Path(directory) / 'out.json').read_text())
            self.assertEqual(len(raw['call1']['items']), 4501)
            self.assertEqual(len(raw['call2']['items']), 9002)
            self.assertEqual(raw['call1']['items'][0]['computedAmount'], 12.345)
            self.assertEqual(raw['call1']['items'][0]['computedQuantity'], 1.234567)

    def test_partial_api_pages_are_exported_but_do_not_report_success(self):
        def partial(executor, store, kind, fields, partition, start, end):
            add_generated_pages(store, kind, partition, 17)
            return kind != 'USAGE'
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'synthetic', '2026-09-01',
                                         '2026-09-02', directory, streaming=True)
            with patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=partial), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(collector.collect(skip_enrichment=True, skip_recommendations=True,
                                                   growth_collection=False))
            raw = json.loads((Path(directory) / 'out.json').read_text())
            self.assertEqual(len(raw['call1']['items']), 17)
            self.assertEqual(len(raw['call2']['items']), 34)
            with (Path(directory) / 'output_merged.csv').open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 17)

    def test_skip_cost_collects_only_usage_and_inventory_receives_no_cost_handle(self):
        seen = []
        def usage_only(executor, store, kind, fields, partition, start, end):
            seen.append(kind)
            return add_generated_pages(store, kind, partition, 13)
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'synthetic', '2026-09-01',
                                         '2026-09-02', directory, streaming=True)
            with patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=usage_only), \
                 patch('src.collector.OCIGrowthCollector') as growth, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(collector.collect(skip_cost=True, skip_recommendations=True))
            self.assertEqual(seen, ['USAGE'])
            self.assertIsNone(growth.return_value.collect_all.call_args.kwargs['cost_data'])
            raw = json.loads((Path(directory) / 'out.json').read_text())
            self.assertIsNone(raw['call1'])
            self.assertEqual(len(raw['call2']['items']), 26)
            self.assertFalse((Path(directory) / 'output_merged.csv').exists())

    def test_compute_metadata_is_fetched_in_bounded_batches_and_cache_reused(self):
        def compute(executor, store, kind, fields, partition, start, end):
            rows = [{'resourceId': f'ocid1.instance.oc1.synthetic.{index}',
                     'timeUsageStarted': start, 'computedAmount': 1, 'currency': 'USD'}
                    for index in range(501)]
            store.add_page(kind, partition, 0, rows)
            return True
        def metadata(ids):
            self.assertLessEqual(len(ids), 200)
            return ({iid: {'shape': 'synthetic-shape', 'resourceName': iid} for iid in ids}, len(ids), 0)
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'synthetic', '2026-09-01',
                                         '2026-09-02', directory, streaming=True)
            with patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=compute), \
                 patch('src.collector.OCIMetadataFetcher') as fetcher, \
                 contextlib.redirect_stdout(io.StringIO()):
                fetcher.return_value.fetch_metadata.side_effect = metadata
                self.assertTrue(collector.collect(skip_recommendations=True, growth_collection=False))
                self.assertEqual([len(call.args[0]) for call in fetcher.return_value.fetch_metadata.call_args_list],
                                 [200, 200, 101])
                self.assertTrue(collector.collect(skip_recommendations=True, growth_collection=False))
                self.assertEqual(fetcher.return_value.fetch_metadata.call_count, 3)
            with (Path(directory) / 'output_merged.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 501)
            self.assertTrue(all(row['shape'] == 'synthetic-shape' for row in rows))

    def test_daily_parallel_partitions_export_in_chronological_order(self):
        windows = []
        def daily(executor, store, kind, fields, partition, start, end):
            windows.append((kind, start, end))
            store.add_page(kind, partition, 0, [{'resourceId': 'synthetic-resource',
                'timeUsageStarted': start, 'computedAmount': 1.01, 'currency': 'USD'}])
            return True
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'synthetic', '2026-09-01',
                                         '2026-09-13', directory, streaming=True)
            with patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=daily), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(collector.collect(skip_enrichment=True, skip_recommendations=True,
                                                  growth_collection=False))
            expected = [f'2026-09-{day:02d}' for day in range(1, 13)]
            raw = json.loads((Path(directory) / 'out.json').read_text())
            self.assertEqual([row['timeUsageStarted'] for row in raw['call1']['items']], expected)
            with (Path(directory) / 'output_merged.csv').open() as handle:
                self.assertEqual([row['timeUsageStarted'] for row in csv.DictReader(handle)], expected)
            for kind in ('COST', 'USAGE'):
                self.assertEqual(sorted((start, end) for query, start, end in windows if query == kind),
                                 [(f'2026-09-{day:02d}', f'2026-09-{day + 1:02d}') for day in range(1, 13)])
