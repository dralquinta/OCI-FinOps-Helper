# Issue 8: Collection performance

Tracking coordinator: #10. Branch: `fix/collection-performance`. Base: `develop`.
Tracking PR: pending remote draft creation.

## Approved scope and rationale

Overlap independent COST/USAGE queries with at most two workers, preserve complete pagination and independent failure outcomes, prevent USAGE matches from multiplying COST rows or monetary totals, vectorize metadata enrichment, and reuse fresh successful metadata across runs. Cache entries expire after 24 hours; failures are retried. Conflicting USAGE metadata is left blank rather than assigned arbitrarily. Existing COST values are preserved.

## Plan

1. Add failing concurrency, cost-preservation, enrichment, skip-stage, and cache tests before changing source.
2. Run independent query requests concurrently with bounded workers and input-order results.
3. Collapse USAGE metadata by resource/day to unambiguous values and join many-to-one; retain COST row counts and totals.
4. Fill missing shape/name values by vectorized mapping, honor skip-enrichment, and cache successful lookups with expiry and safe corrupt-cache fallback.
5. Deduplicate metadata IDs and isolate malformed or failed responses.
6. Run targeted and full regression suites; record a synthetic 322k/324k-row benchmark and cache warm-run behavior.

## Agent roster and file ownership

- issue8: implementation/test/docs owner and branch integration owner.
- root: independent TDD auditor and cross-review coordinator.
- Other issue agents: isolated branches; no shared worktree edits.
- issue8 owns `src/collector.py`, `src/utils/api_executor.py`, `src/utils/executor.py`, `tests/test_collector.py`, `tests/utils/test_api_executor.py`, new `tests/utils/test_executor.py`, and this documentation directory.
- Conflicts: none.

## Planned tests and validation

- `tests/test_collector.py`: COST row count/sum preservation with duplicate USAGE matches; conflicting metadata; preserving existing values; no row-wise apply; skip-enrichment; cache reuse/expiry/corruption.
- `tests/utils/test_api_executor.py`: concurrent starts using synchronization events, input-order results, independent failure outcomes, existing pagination regressions.
- `tests/utils/test_executor.py`: duplicate IDs, malformed response isolation, timeout handling.
- Targeted: `python3 -m unittest tests.test_collector tests.utils.test_api_executor tests.utils.test_executor -v`.
- Regression: `python3 -m unittest discover -s tests -v`.
- Benchmark: synthetic 322k COST/324k USAGE rows; exact COST rows and monetary sum; local elapsed time without brittle timing assertions; fresh cache requests no CLI metadata lookups.

## Acceptance criteria

Independent API work overlaps without losing pagination results. Every COST row appears once and monetary totals remain unchanged. Enrichment preserves supplied values, avoids row-wise processing, and can be skipped. Fresh successful metadata is reused; expired, missing, failed, or corrupt entries safely trigger lookups. Targeted and full suites pass; benchmark evidence is recorded.
