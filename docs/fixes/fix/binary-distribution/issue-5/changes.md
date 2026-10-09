# Issue 5 changes

## Root Cause Analysis
The repository distributes source scripts and a shell wrapper that creates a Python environment and requires an external OCI CLI. No standalone binary build exists, and collection does not produce an archive for delivery. Existing tests exercise source collectors only, so distribution and archive behavior have no guardrails.

## How It Was Fixed
Pending implementation after remote draft PR gate.

## Summary
Approved standalone collector binary and runtime collection tar.gz contract recorded.

## Validation
Pending targeted tests, full regression, actual binary build and isolated-PATH archive smoke test.
