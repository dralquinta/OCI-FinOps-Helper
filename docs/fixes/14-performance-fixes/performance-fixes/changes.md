# Issue 14 changes

## Root Cause Analysis
The original issue branch predates executable delivery and recent collection corrections. Current develop still requires positional arguments, opts into growth collection, launches up to 30 heavyweight metadata CLI processes, repeats Monitoring discovery per namespace, and writes monetary CSV fields without consistent two-decimal formatting. Tests cover earlier collection fixes but not this CLI/export/resource envelope.

## How It Was Fixed
Pending implementation after tracking PR publication. The approved plan preserves existing executable delivery and raw source precision while bounding collection work.

## Summary
Scope: named CLI options, growth default and opt-out, resource-conscious collection, explicit monetary export formatting, executable and read-only OCI validation.

## Validation
Pending. Targeted tests, full regression, binary smoke and authorized read-only OCI validation are required; no validation pass is claimed yet.
