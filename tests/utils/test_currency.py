import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from src.collector import OCICostCollector


class MonetaryExportTests(unittest.TestCase):
    def test_cost_csv_formats_money_only_and_preserves_raw_precision(self):
        row = {'resourceId': 'volume', 'timeUsageStarted': '2025-09-01',
               'computedAmount': 12.345, 'attributedCost': 0.005,
               'computedQuantity': 1.23456789, 'currency': 'USD'}
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'us-ashburn-1', '2025-09-01', '2025-09-18', directory)
            with patch('src.collector.ProgressSpinner'), contextlib.redirect_stdout(io.StringIO()):
                frame = collector.merge_and_enrich({'items': [row]}, {'items': []}, skip_enrichment=True)
            self.assertEqual(12.345, frame.computedAmount.iloc[0])
            self.assertEqual(0.005, frame.attributedCost.iloc[0])
            self.assertEqual(row, json.loads((Path(directory) / 'out.json').read_text())['call1']['items'][0])
            for name in ('output.csv', 'output_merged.csv'):
                with (Path(directory) / name).open() as stream:
                    exported = next(csv.DictReader(stream))
                self.assertEqual('12.35', exported['computedAmount'])
                self.assertEqual('0.01', exported['attributedCost'])
                self.assertEqual('1.23456789', exported['computedQuantity'])
                self.assertEqual('USD', exported['currency'])

    def test_export_missing_values_source_currency_and_fixed_decimals(self):
        rows = [{'resourceId': 'a', 'computedAmount': '2', 'currency': 'EUR'},
                {'resourceId': 'b', 'computedAmount': None, 'currency': 'USD'},
                {'resourceId': 'c', 'computedAmount': -1.005, 'currency': None}]
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'home', '2025-09-01', '2025-09-18', directory)
            with patch('src.collector.ProgressSpinner'), contextlib.redirect_stdout(io.StringIO()):
                collector.merge_and_enrich({'items': rows}, {'items': []}, skip_enrichment=True)
            with (Path(directory) / 'output.csv').open() as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(['2.00', '', '-1.01'], [item['computedAmount'] for item in exported])
            self.assertEqual(['EUR', 'USD', 'Unknown'], [item['currency'] for item in exported])

    def test_default_metadata_subprocess_fanout_is_conservative(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = OCICostCollector('synthetic', 'home', '2025-09-01', '2025-09-18', directory)
            with patch('src.collector.OCIMetadataFetcher') as fetcher, contextlib.redirect_stdout(io.StringIO()):
                fetcher.return_value.fetch_metadata.return_value = ({}, 0, 1)
                collector.fetch_instance_metadata(['ocid1.instance.oc1.test.synthetic'])
            self.assertLessEqual(fetcher.call_args.kwargs['max_workers'], 4)
