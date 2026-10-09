# Issue 8 changes

## Root Cause Analysis

COST and USAGE requests run serially. Merging on resource/day against multiple USAGE rows multiplies COST rows and amounts. Metadata enrichment invokes a Python callback for each dataframe row. A metadata JSON file is written but never reused, so subsequent runs repeat all instance GET calls. Existing tests cover integration and pagination but do not assert merge cardinality, concurrent execution, or cache reuse.

## How It Was Fixed

Pending implementation after the remote tracking draft PR exists.

## Summary

Approved bounded query concurrency, cost-preserving metadata merge, vectorized enrichment, skip-enrichment handling, and expiring positive metadata cache. Work remains in this isolated branch.

## Validation

Not run yet. Planned targeted suite, full unittest regression, and synthetic 322k/324k-row benchmark are listed in plan.md. No success claimed before those checks run.
