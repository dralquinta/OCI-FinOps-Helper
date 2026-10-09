"""SQLite-backed OCI pages and bounded, cardinality-preserving COST exports."""

import json
import math
from pathlib import Path
import sqlite3
import tempfile
import threading
import time

import pandas as pd


_USAGE_FIELDS = ('platform', 'region', 'skuPartNumber', 'shape', 'resourceName')


def _key(value):
    if value is None or value == '':
        return None
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class _JSONStream:
    """Decode object members one at a time from a bounded text buffer."""

    def __init__(self, stream):
        self.stream = stream
        self.buffer, self.position, self.eof = '', 0, False
        self.decoder = json.JSONDecoder()

    def _fill(self):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        chunk = self.stream.read(65536)
        self.buffer += chunk
        self.eof = not chunk

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position] in ' \t\n\r':
                self.position += 1
            if self.position < len(self.buffer) or self.eof:
                return self.buffer[self.position:self.position + 1]
            self._fill()

    def take(self, expected):
        if self.peek() != expected:
            raise ValueError('Invalid metadata cache JSON')
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                if end == len(self.buffer) and not self.eof:
                    self._fill()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof or len(self.buffer) - self.position >= 1048576:
                    raise ValueError('Invalid or oversized metadata cache entry')
                self._fill()

    def members(self):
        self.take('{')
        if self.peek() == '}':
            self.take('}')
            return
        while True:
            key = self.value()
            if not isinstance(key, str):
                raise ValueError('Metadata cache keys must be strings')
            self.take(':')
            yield key
            if self.peek() == ',':
                self.take(',')
            else:
                self.take('}')
                return

    def finish(self):
        if self.peek():
            raise ValueError('Trailing metadata cache content')


class DiskDatasetStore:
    """Own a scratch database outside archived collection output.

    Page writes serialize on one connection. Reads use one bounded-cache
    connection per thread, while iterators fetch incrementally from indexes.
    """

    def __init__(self, directory=None):
        if directory is not None:
            Path(directory).mkdir(parents=True, exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(prefix='oci-datasets-', dir=directory)
        self.path = Path(self._temporary.name) / 'pages.sqlite3'
        self._lock = threading.RLock()
        self._local = threading.local()
        self._readers = []
        self._closed = False
        self._writer = sqlite3.connect(str(self.path), check_same_thread=False)
        self._configure(self._writer)
        self._writer.execute('PRAGMA journal_mode=WAL')
        self._writer.executescript("""
            CREATE TABLE records (
                kind TEXT, partition_name TEXT, page_seq INTEGER, row_seq INTEGER,
                resource_key TEXT, time_key TEXT, resource_id TEXT, region TEXT,
                currency TEXT, amount REAL, raw_json TEXT NOT NULL,
                PRIMARY KEY(kind, partition_name, page_seq, row_seq)
            ) WITHOUT ROWID;
            CREATE INDEX resource_costs ON records(kind, resource_id, region, currency);
            CREATE TABLE fields (kind TEXT, name TEXT, PRIMARY KEY(kind, name)) WITHOUT ROWID;
            CREATE TABLE pages (
                kind TEXT, partition_name TEXT, page_seq INTEGER, metadata TEXT,
                PRIMARY KEY(kind, partition_name, page_seq)
            ) WITHOUT ROWID;
            CREATE TABLE usage_values (
                resource_key TEXT, time_key TEXT, field TEXT, value_json TEXT,
                PRIMARY KEY(resource_key, time_key, field, value_json)
            ) WITHOUT ROWID;
            CREATE TABLE instance_metadata (
                resource_id TEXT PRIMARY KEY, metadata TEXT NOT NULL, fetched_at REAL
            ) WITHOUT ROWID;
        """)
        self._writer.commit()

    @staticmethod
    def _configure(connection):
        connection.execute('PRAGMA cache_size=-8192')
        connection.execute('PRAGMA temp_store=FILE')
        connection.execute('PRAGMA busy_timeout=30000')

    def _reader(self):
        with self._lock:
            if self._closed:
                raise RuntimeError('Dataset store is closed')
            connection = getattr(self._local, 'connection', None)
            if connection is None:
                connection = sqlite3.connect(str(self.path), check_same_thread=False)
                self._configure(connection)
                connection.execute('PRAGMA query_only=ON')
                self._local.connection = connection
                self._readers.append(connection)
            return connection

    def add_page(self, kind, partition, page_seq, rows, metadata=None):
        """Insert one caller-sized page without building a second array copy."""
        kind = kind.upper()
        metadata = {key: value for key, value in (metadata or {}).items() if key != 'items'}
        with self._lock:
            if self._closed:
                raise RuntimeError('Dataset store is closed')
            with self._writer:
                self._writer.execute('INSERT INTO pages VALUES (?, ?, ?, ?)',
                                     (kind, str(partition), page_seq, json.dumps(metadata)))
                page_fields = set()
                for offset, record in enumerate(rows):
                    if not isinstance(record, dict):
                        raise ValueError('OCI records must be objects')
                    resource = record.get('resourceId', record.get('resource-id'))
                    started = record.get('timeUsageStarted', record.get('time-usage-started'))
                    resource_key, time_key = _key(resource), _key(started)
                    region = record.get('region')
                    currency = record.get('currency')
                    raw_amount = record.get('computedAmount', record.get('computed-amount'))
                    try:
                        amount = float(raw_amount) if raw_amount is not None and not isinstance(raw_amount, bool) else None
                        if amount is not None and not math.isfinite(amount):
                            amount = None
                    except (TypeError, ValueError):
                        amount = None
                    if region is not None and not isinstance(region, str):
                        amount = None
                    self._writer.execute('INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                         (kind, str(partition), page_seq, offset, resource_key, time_key,
                                          resource if isinstance(resource, str) else None,
                                          region if isinstance(region, str) else None,
                                          currency if isinstance(currency, str) and currency else None,
                                          amount, json.dumps(record, separators=(',', ':'))))
                    page_fields.update(record)
                    if kind == 'USAGE' and resource_key is not None and time_key is not None:
                        self._writer.executemany('INSERT OR IGNORE INTO usage_values VALUES (?, ?, ?, ?)',
                            ((resource_key, time_key, field, json.dumps(record[field], sort_keys=True))
                             for field in _USAGE_FIELDS if record.get(field) is not None and record[field] != ''))
                self._writer.executemany('INSERT OR IGNORE INTO fields VALUES (?, ?)',
                                         ((kind, name) for name in sorted(page_fields)))

    def dataset(self, kind):
        return DiskDataset(self, kind.upper())

    @property
    def merged_fieldnames(self):
        cost_fields = set(self.dataset('COST').fieldnames)
        usage_fields = set(self.dataset('USAGE').fieldnames)
        return sorted(cost_fields | {'resourceId', 'timeUsageStarted'} |
                      (usage_fields & set(_USAGE_FIELDS)))

    def iter_merged_chunks(self, chunk_size=2000):
        """Fill blank COST metadata only when every nonblank USAGE value agrees."""
        if chunk_size < 1:
            raise ValueError('chunk_size must be positive')
        fields = self.merged_fieldnames
        usage_fields = set(self.dataset('USAGE').fieldnames)
        enrichment = [field for field in _USAGE_FIELDS if field in usage_fields]
        selections = ["""(SELECT CASE WHEN COUNT(DISTINCT value_json)=1 THEN MIN(value_json) END
                         FROM usage_values AS u WHERE u.resource_key=r.resource_key
                         AND u.time_key=r.time_key AND u.field=?)""" for field in enrichment]
        query = 'SELECT r.raw_json' + (',' + ','.join(selections) if selections else '') + """
            FROM records AS r WHERE r.kind='COST'
            ORDER BY r.partition_name, r.page_seq, r.row_seq"""
        cursor = self._reader().execute(query, enrichment)
        try:
            while True:
                batch = cursor.fetchmany(chunk_size)
                if not batch:
                    break
                records = []
                for result in batch:
                    record = json.loads(result[0])
                    for field, resolved in zip(enrichment, result[1:]):
                        if record.get(field) is None or record[field] == '':
                            record[field] = json.loads(resolved) if resolved is not None else None
                    records.append(record)
                yield pd.DataFrame.from_records(records, columns=fields)
        finally:
            cursor.close()

    def write_raw_json(self, path, datasets):
        """Stream original records, retaining monetary precision and API metadata."""
        with Path(path).open('w', encoding='utf-8') as output:
            output.write('{')
            for index, (name, dataset) in enumerate(datasets.items()):
                if index:
                    output.write(',')
                output.write(json.dumps(name) + ':')
                if not isinstance(dataset, DiskDataset):
                    json.dump(dataset, output)
                    continue
                output.write('{')
                metadata = dataset.metadata
                for field, value in metadata.items():
                    output.write(json.dumps(field) + ':')
                    json.dump(value, output)
                    output.write(',')
                output.write('"items":[')
                for row_index, raw in enumerate(dataset._iter_raw()):
                    if row_index:
                        output.write(',')
                    output.write(raw)
                output.write(']}')
            output.write('}')

    def add_metadata(self, mapping, fetched_at=None):
        fetched_at = time.time() if fetched_at is None else fetched_at
        with self._lock:
            if self._closed:
                raise RuntimeError('Dataset store is closed')
            with self._writer:
                self._writer.executemany('INSERT OR REPLACE INTO instance_metadata VALUES (?, ?, ?)',
                    ((resource, json.dumps(metadata), fetched_at) for resource, metadata in mapping.items()))

    def lookup_metadata(self, ids):
        # Caller IDs are a bounded export chunk. Individual indexed lookups avoid
        # SQLite's variable-count limit without expanding the full metadata map.
        connection = self._reader()
        result = {}
        for resource in ids:
            row = connection.execute('SELECT metadata FROM instance_metadata WHERE resource_id=?',
                                     (resource,)).fetchone()
            if row:
                result[resource] = json.loads(row[0])
        return result

    def missing_instance_ids(self):
        cursor = self._reader().execute("""SELECT DISTINCT r.resource_id FROM records AS r
            WHERE r.kind='COST' AND r.resource_id LIKE '%instance.oc1%'
            AND NOT EXISTS (SELECT 1 FROM instance_metadata AS m WHERE m.resource_id=r.resource_id)
            ORDER BY r.resource_id""")
        try:
            for row in cursor:
                yield row[0]
        finally:
            cursor.close()

    def iter_metadata(self):
        cursor = self._reader().execute('SELECT resource_id, metadata FROM instance_metadata ORDER BY resource_id')
        try:
            for resource, metadata in cursor:
                yield resource, json.loads(metadata)
        finally:
            cursor.close()

    def iter_metadata_entries(self):
        cursor = self._reader().execute('SELECT resource_id, metadata, fetched_at FROM instance_metadata ORDER BY resource_id')
        try:
            for resource, metadata, fetched_at in cursor:
                yield resource, json.loads(metadata), fetched_at
        finally:
            cursor.close()

    def load_metadata_cache(self, path, tenancy, region, now, ttl=86400):
        """Stage entries on disk; reuse none until syntax and scope are verified."""
        with self._lock:
            if self._closed:
                raise RuntimeError('Dataset store is closed')
            try:
                with Path(path).open(encoding='utf-8') as source, self._writer:
                    self._writer.execute('DROP TABLE IF EXISTS cache_stage')
                    self._writer.execute('CREATE TABLE cache_stage (resource_id TEXT PRIMARY KEY, metadata TEXT, fetched_at REAL) WITHOUT ROWID')
                    parser = _JSONStream(source)
                    headers = {}
                    found_entries = False
                    for field in parser.members():
                        if field == 'entries':
                            if found_entries:
                                raise ValueError('Duplicate metadata cache entries object')
                            found_entries = True
                            for resource in parser.members():
                                entry = parser.value()
                                if not isinstance(entry, dict):
                                    continue
                                fetched_at, metadata = entry.get('fetched_at'), entry.get('metadata')
                                if (isinstance(fetched_at, (int, float)) and not isinstance(fetched_at, bool)
                                        and 0 <= now - fetched_at < ttl and isinstance(metadata, dict)
                                        and all(isinstance(metadata.get(name, ''), str) for name in ('shape', 'resourceName'))):
                                    self._writer.execute('INSERT OR REPLACE INTO cache_stage VALUES (?, ?, ?)',
                                                         (resource, json.dumps(metadata), fetched_at))
                        else:
                            value = parser.value()
                            if field in ('tenancy', 'region'):
                                if field in headers:
                                    raise ValueError('Duplicate metadata cache header')
                                headers[field] = value
                    parser.finish()
                    if not found_entries or headers.get('tenancy') != tenancy or headers.get('region') != region:
                        raise ValueError('Metadata cache scope mismatch')
                    count = self._writer.execute('SELECT COUNT(*) FROM cache_stage').fetchone()[0]
                    self._writer.execute('INSERT OR IGNORE INTO instance_metadata SELECT * FROM cache_stage')
                    self._writer.execute('DROP TABLE cache_stage')
                    return count
            except (OSError, ValueError, TypeError):
                self._writer.execute('DROP TABLE IF EXISTS cache_stage')
                self._writer.commit()
                return 0

    def write_metadata_files(self, output_dir, tenancy, region, now):
        """Write legacy-compatible metadata files without materializing the cache."""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        metadata_path = output / 'instance_metadata.json'
        cache_path = output / 'instance_metadata_cache.json'
        metadata_tmp, cache_tmp = metadata_path.with_suffix('.tmp'), cache_path.with_suffix('.tmp')
        try:
            with metadata_tmp.open('w', encoding='utf-8') as target:
                target.write('{')
                cursor = self._reader().execute("""SELECT m.resource_id, m.metadata FROM instance_metadata AS m
                    WHERE EXISTS (SELECT 1 FROM records AS r WHERE r.kind='COST' AND r.resource_id=m.resource_id)
                    ORDER BY m.resource_id""")
                try:
                    for index, (resource, metadata) in enumerate(cursor):
                        if index:
                            target.write(',')
                        target.write(json.dumps(resource) + ':' + metadata)
                finally:
                    cursor.close()
                target.write('}')
            with cache_tmp.open('w', encoding='utf-8') as target:
                target.write('{"tenancy":' + json.dumps(tenancy) + ',"region":' + json.dumps(region) + ',"entries":{')
                first = True
                for resource, metadata, fetched_at in self.iter_metadata_entries():
                    if fetched_at is None or not 0 <= now - fetched_at < 86400:
                        continue
                    if not first:
                        target.write(',')
                    first = False
                    target.write(json.dumps(resource) + ':')
                    json.dump({'fetched_at': fetched_at, 'metadata': metadata}, target)
                target.write('}}')
            metadata_tmp.replace(metadata_path)
            cache_tmp.replace(cache_path)
        finally:
            metadata_tmp.unlink(missing_ok=True)
            cache_tmp.unlink(missing_ok=True)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                for connection in self._readers:
                    connection.close()
                self._writer.close()
                self._temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DiskDataset:
    """A repeatable handle, never an in-memory array of the dataset."""

    def __init__(self, store, kind):
        self.store, self.kind = store, kind

    @property
    def count(self):
        return self.store._reader().execute('SELECT COUNT(*) FROM records WHERE kind=?', (self.kind,)).fetchone()[0]

    @property
    def fieldnames(self):
        return [row[0] for row in self.store._reader().execute('SELECT name FROM fields WHERE kind=? ORDER BY name', (self.kind,))]

    @property
    def metadata(self):
        row = self.store._reader().execute('SELECT metadata FROM pages WHERE kind=? ORDER BY partition_name, page_seq LIMIT 1', (self.kind,)).fetchone()
        return json.loads(row[0]) if row else {}

    def _iter_raw(self):
        cursor = self.store._reader().execute('SELECT raw_json FROM records WHERE kind=? ORDER BY partition_name, page_seq, row_seq', (self.kind,))
        try:
            for row in cursor:
                yield row[0]
        finally:
            cursor.close()

    def iter_items(self):
        for raw in self._iter_raw():
            yield json.loads(raw)

    def compute_instance_ids(self):
        cursor = self.store._reader().execute("""SELECT DISTINCT resource_id FROM records
            WHERE kind=? AND resource_id LIKE '%instance.oc1%' ORDER BY resource_id""", (self.kind,))
        try:
            for row in cursor:
                yield row[0]
        finally:
            cursor.close()

    def lookup_costs(self, resource_id, region=None):
        # Return only this exact region bucket. FinOps separately combines its
        # (resource, None) and (resource, region) buckets, preserving legacy sums.
        return dict(self.store._reader().execute("""SELECT currency, SUM(amount) FROM records
            WHERE kind=? AND resource_id=? AND region IS ? AND currency IS NOT NULL
            AND amount IS NOT NULL GROUP BY currency""", (self.kind, resource_id, region)))
