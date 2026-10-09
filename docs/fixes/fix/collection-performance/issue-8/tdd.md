# TDD record

## First Red step (planned)

Write behavior tests reproducing COST-row multiplication from repeated USAGE keys and the lack of concurrent query execution. Run the smallest targets and record actual expected failures before implementation. Add enrichment/cache correctness tests before their corresponding implementation.

Remote tracking gate completed: draft PR #12 was visible before test or implementation changes.

## Red evidence

1. `python3 -m unittest tests.test_collector.CollectionPerformanceTests tests.utils.test_executor -v`: observed four failures and four errors. Duplicate USAGE doubled two COST rows; metadata enrichment hit the deliberately forbidden DataFrame.apply; cache refetched successes; duplicate IDs fetched twice; empty USAGE raised KeyError; skip-enrichment keyword was unsupported; sequential requests broke the synchronization barrier; malformed JSON escaped the worker. The expiry test already passed by always refetching, so it was not treated as Red evidence.
2. `python3 -m unittest tests.utils.test_api_executor.ParallelUsageTests -v`: failed with BrokenBarrierError because batch queries were sequential.
3. Blank COST metadata fill regression: failed with `['', 'original']` instead of `['Linux', 'original']` before the merge-fill change.
4. Independent root audit identified incomplete resource/day keys. The new regression failed because anonymous USAGE metadata attached to unrelated COST records, before incomplete USAGE keys were excluded.

## Green and Refactor

Bounded two-worker query execution preserves input-order outcomes and existing pagination. USAGE fields collapse to one unambiguous value per resource/day; many-to-one validation protects COST cardinality. Vector mapping fills blank metadata and preserves existing fields. Expiring positive cache scopes tenancy/region, ignores malformed entries, reuses successes, and retries failures. IDs deduplicate and CLI JSON/timeout failures remain isolated. Retained collector.make_api_call and subprocess seams for existing tests and compatibility with the independently developed CLI fix.

Refactor: replaced constructed string join keys with explicit dataframe keys; excluded incomplete keys and used nullable string matching for instance detection. No speculative API changes or cloud operations.

## Verification

- Targeted/related: `python3 -m unittest tests.test_collector tests.utils.test_api_executor tests.utils.test_executor -v`: 22 tests passed.
- Full regression: `python3 -m unittest discover -s tests -v`: 45 tests passed after the final source change.
- `git diff --check`: passed.
- Synthetic benchmark: `python3 docs/fixes/fix/collection-performance/issue-8/benchmark.py`: 322000 COST / 324000 USAGE rows; legacy join produced 648000 rows; corrected output contained exactly 322000 rows and amount 322000.0. Corrected merge plus JSON/CSV writes took 5.761s. Legacy row-wise enrichment took 137.419s versus vector fill 0.015s on the same 322000-row frame, with dataframe equality asserted. Warm cache made zero fetch calls. Process peak RSS was 1630276 KiB including the intentionally expensive legacy comparison; it does not isolate corrected collector memory. Legacy join alone took 0.527s and excludes output writing, so it is not comparable to the corrected end-to-end duration.
- Root independently ran the 22 focused tests and diff check successfully. README now documents cache filename, 24-hour expiry, scoping, snapshot distinction, concurrent calls, and cost preservation.

## Independent coordinator audit

Coordinator independently reran the 22 focused collector, metadata and API tests: all passed. Diff whitespace check passed. Reviewed null-key attribution, monetary cardinality, concurrency, cache scoping/expiry and README accuracy.
