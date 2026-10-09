# Issue 8 changes

## Root Cause Analysis

COST and USAGE requests run serially. Merging on resource/day against multiple USAGE rows multiplies COST rows and amounts. Metadata enrichment invokes a Python callback for each dataframe row. A metadata JSON file is written but never reused, so subsequent runs repeat all instance GET calls. Existing tests cover integration and pagination but do not assert merge cardinality, concurrent execution, or cache reuse.

## How It Was Fixed

Independent COST/USAGE queries now use at most two workers. USAGE metadata is collapsed per complete resource/day key, retaining only unambiguous values and enforcing a many-to-one join. Blank fields are filled without replacing existing COST data. Shape/name enrichment uses vector mapping, and skip-enrichment prevents metadata requests. Successful metadata is cached for 24 hours in `instance_metadata_cache.json`, scoped by tenancy and region; expired/corrupt entries and previous failures are retried. The existing `instance_metadata.json` output remains the plain enriched metadata artifact. Duplicate instance IDs are fetched once and malformed CLI JSON is isolated.

## Summary

Implemented bounded query concurrency, cost-preserving metadata merge, vectorized enrichment, skip-enrichment handling, and expiring positive metadata cache. Independent root review caught and drove a regression for anonymous join keys. No cloud access or customer output was required.

## Validation

Targeted/related suite passed 22 tests. Full unittest discovery passed 45 tests. Diff whitespace check passed. Root independently confirmed the focused suite. The reproducible benchmark preserved 322000 COST rows and amount 322000.0 from 324000 USAGE rows (legacy join: 648000 rows). Corrected merge including JSON/CSV writing took 5.761s. On the same 322000-row frame, legacy row enrichment took 137.419s and vector fill 0.015s; dataframe equality passed. Fresh warm cache made zero fetch calls. Peak RSS was 1630276 KiB for the full process including the legacy comparison, not isolated collector memory. Timing results are local synthetic measurements, not OCI service latency guarantees. Conflicting USAGE metadata deliberately remains blank; callers can still retrieve shape/name from instance metadata. Fresh metadata can be up to 24 hours old; deleting the cache forces refresh.
