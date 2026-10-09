"""Run from repository root: python3 docs/fixes/fix/collection-performance/issue-8/benchmark.py."""
import contextlib
import io
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path.cwd()))
from src.collector import OCICostCollector


def main():
    instance = 'ocid1.instance.oc1.synthetic.example'
    costs = [{'resourceId': instance, 'timeUsageStarted': str(i % 161000), 'computedAmount': 1.0}
             for i in range(322000)]
    usage = [{'resourceId': instance, 'timeUsageStarted': str(i % 161000), 'platform': 'Linux',
              'skuPartNumber': str(i % 2)} for i in range(324000)]
    started = time.perf_counter()
    legacy = pd.DataFrame(costs).merge(pd.DataFrame(usage), on=['resourceId', 'timeUsageStarted'], how='left')
    legacy_seconds = time.perf_counter() - started
    legacy_rows = len(legacy)
    del legacy
    metadata = {instance: {'shape': 'shape', 'resourceName': 'name'}}
    with tempfile.TemporaryDirectory() as directory, patch('src.collector.ProgressSpinner'), contextlib.redirect_stdout(io.StringIO()):
        collector = OCICostCollector('synthetic-tenancy', 'synthetic-region', 'start', 'end', directory)
        with patch.object(collector, 'fetch_instance_metadata', return_value=metadata):
            started = time.perf_counter()
            frame = collector.merge_and_enrich({'items': costs}, {'items': usage})
            merge_seconds = time.perf_counter() - started
        with patch('src.collector.OCIMetadataFetcher') as fetcher:
            fetcher.return_value.fetch_metadata.return_value = (metadata, 1, 0)
            collector.fetch_instance_metadata([instance])
            collector.fetch_instance_metadata([instance])
            assert fetcher.return_value.fetch_metadata.call_count == 1
    assert len(frame) == 322000 and frame.computedAmount.sum() == 322000
    baseline = frame[['resourceId']].copy()
    def enrich_row(row):
        entry = metadata.get(row['resourceId'], {})
        row['shape'] = entry.get('shape', '')
        row['resourceName'] = entry.get('resourceName', '')
        return row
    started = time.perf_counter()
    old = baseline.apply(enrich_row, axis=1)
    row_apply_seconds = time.perf_counter() - started
    started = time.perf_counter()
    new = baseline.copy()
    for column in ('shape', 'resourceName'):
        new[column] = new.resourceId.map({iid: entry[column] for iid, entry in metadata.items()})
    vector_seconds = time.perf_counter() - started
    pd.testing.assert_frame_equal(old, new)
    print(json.dumps({'cost_rows': len(costs), 'usage_rows': len(usage), 'legacy_rows': legacy_rows,
                      'corrected_rows': len(frame), 'corrected_amount': frame.computedAmount.sum(),
                      'legacy_merge_seconds': round(legacy_seconds, 3),
                      'corrected_merge_including_json_csv_seconds': round(merge_seconds, 3),
                      'legacy_row_apply_seconds': round(row_apply_seconds, 3),
                      'vector_fill_seconds': round(vector_seconds, 3),
                      'warm_cache_fetch_calls': 0,
                      'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, indent=2))


if __name__ == '__main__':
    main()
