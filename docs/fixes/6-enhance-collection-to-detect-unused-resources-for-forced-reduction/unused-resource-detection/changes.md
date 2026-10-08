# Changes

## Root Cause Analysis
The helper collects cost/usage and recommendation summaries, but lacks resource-level inventory and attachment evidence for reduction reviews. Monitoring uses only the home region, omits compartment scope, and truncates returned series. Growth-only skips its collection stage. No regression suite existed to cover these gaps.

## How It Was Fixed
Pending implementation.

## Summary
Approved read-only collection expansion for issue #6.

## Validation
Pending targeted and full regression.
