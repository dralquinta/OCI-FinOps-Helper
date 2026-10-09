#!/usr/bin/env python3
"""Synthetic real-export benchmark; no OCI credentials or network calls.

Run: python3 docs/fixes/14-performance-fixes/performance-fixes/memory_benchmark.py
Each size runs in a fresh process so peak RSS measurements are independent.
COST rows have two matching USAGE SKU rows and 150-byte metadata. Only API
page delivery is replaced; disk persistence, merge, raw export and CSV export
run through the production collector. No full input or output array is retained.
"""
import argparse
import contextlib
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from src.collector import OCICostCollector
from src.utils.datasets import DiskDatasetStore
from tests.test_streaming_collection import page_api


def count_token(path, token):
    token = token.encode()
    count, carry = 0, b''
    with path.open('rb') as handle:
        while True:
            block = handle.read(65536)
            if not block:
                return count + carry.count(token)
            data = carry + block
            boundary = len(data) - len(token) + 1
            if boundary <= 0:
                carry = data
                continue
            # Count only matches starting before the final overlap.
            cursor = 0
            while True:
                found = data.find(token, cursor)
                if found < 0 or found >= boundary:
                    break
                count += 1
                cursor = found + len(token)
            carry = data[boundary:]


def run_child(count):
    start = time.monotonic()
    scratch_bytes = []
    original_close = DiskDatasetStore.close
    def measured_close(store):
        if store.path.parent.exists():
            scratch_bytes.append(sum(path.stat().st_size for path in store.path.parent.iterdir()
                                     if path.is_file()))
        original_close(store)
    with tempfile.TemporaryDirectory() as directory:
        collector = OCICostCollector('synthetic-tenancy', 'synthetic-region',
                                     '2026-09-01', '2026-09-02', directory, streaming=True)
        # Send progress output to disk as well; retaining a StringIO here would
        # conceal an unbounded console logging regression in the benchmark.
        with tempfile.TemporaryFile(mode='w+') as log, \
             patch('src.utils.api_executor.OCIAPIExecutor.collect_to_store', new=page_api(count)), \
             patch.object(DiskDatasetStore, 'close', new=measured_close), \
             contextlib.redirect_stdout(log):
            success = collector.collect(skip_enrichment=True, skip_recommendations=True,
                                        growth_collection=False)
        if not success:
            log.seek(0)
            raise AssertionError(log.read()[-4000:])
        observed, amount, quantity = 0, Decimal('0'), Decimal('0')
        with (Path(directory) / 'output_merged.csv').open() as handle:
            for row in csv.DictReader(handle):
                observed += 1
                amount += Decimal(row['computedAmount'])
                quantity += Decimal(row['computedQuantity'])
                assert row['skuPartNumber'] == '', 'ambiguous usage SKU attached'
                assert row['platform'] == ('existing' if observed == 1 else 'Linux')
                assert row['computedAmount'] == '12.35'
                assert row['computedQuantity'] == '1.234567'
        assert observed == count, (observed, count)
        assert amount == count * Decimal('12.35')
        assert quantity == count * Decimal('1.234567')
        raw = Path(directory) / 'out.json'
        assert count_token(raw, 'resourceId') == count * 3
        assert count_token(raw, '12.345') == count
        assert count_token(raw, '1.234567') == count
        report_bytes = sum(path.stat().st_size for path in Path(directory).glob('*.csv'))
        return {'cost_rows': count, 'usage_rows': count * 2, 'export_rows': observed,
                'csv_amount_total': float(amount), 'quantity_total': float(quantity),
                'raw_precision_preserved': True, 'report_bytes': report_bytes,
                'raw_json_bytes': raw.stat().st_size,
                'scratch_database_bytes': max(scratch_bytes, default=0),
                'peak_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
                'elapsed_seconds': round(time.monotonic() - start, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--rows', type=int, default=100000)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_child(args.rows)))
        return
    results = []
    for count in (100000, 1000000):
        result = subprocess.run([sys.executable, __file__, '--child', '--rows', str(count)],
                                check=True, capture_output=True, text=True)
        report = json.loads(result.stdout)
        results.append(report)
        print(json.dumps(report), flush=True)
    assert results[1]['peak_rss_mib'] < 256, results
    assert results[1]['peak_rss_mib'] - results[0]['peak_rss_mib'] < 64, results
    print(json.dumps({'memory_budget_mib': 256, 'max_rss_growth_mib': 64, 'passed': True}))


if __name__ == '__main__':
    main()
