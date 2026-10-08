# Resource-level FinOps collection changes

## Root Cause Analysis
Issue #6 needs evidence for reducing consumption costs. The helper previously collected billed usage and high-level Advisor recommendations without the resource inventory and attachment relationships needed to review unused resources. Monitoring used a home-region raw request without compartment scope, incompatible minute intervals for long windows, and only 100 returned streams. Growth-only mode skipped its collection because growth ran inside the successful cost/usage merge. Usage retrieval ignored pagination, and Advisor totals could relabel USD estimates as an unconverted requested currency. No automated regression suite existed to guard these behaviors.

## How It Was Fixed
Reuse the existing OCI CLI authentication, compartment patterns and growth execution callback. The new FinOps utility collects region/compartment discovery, Search inventory, compute/block/boot configuration and attachments, and retains raw evidence with structured coverage. Search explicitly traverses CLI next-page tokens; partial pages remain visible as incomplete. Malformed identities fail safely. Orphan reviews require complete attachment evidence across compartments/availability domains. Stopped compute remains a review candidate with shape-dependent billing, not guaranteed savings.

Monitoring discovers available names across service namespaces, scopes every query to region/compartment, uses hourly intervals/resolution with bounded windows, and preserves all returned streams and definitions. Missing metrics remain unknown. Usage raw requests retain POST bodies through encoded next-page traversal and reject incomplete costs. Candidate costs use original billing items and actual currencies rather than multiplied merged rows; complete original cost data is retained.

Advisor outputs preserve recommendation summaries and add raw resource actions, metadata and failure coverage. Savings estimates remain USD in both files and console; readonly IAM guidance uses optimizer-api-family. Growth runs independently of billing/merge success, including growth-only. Requested billing/growth exceptions no longer result in a false success return. Both package imports and direct script execution work.

## Summary
- Regional raw inventory, authoritative attachment evidence and conservative review candidates.
- Complete scoped Monitoring evidence and explicitly unknown/missing coverage.
- Resource-level Advisor actions and truthful currencies.
- Paginated costs, original cost retention and independent growth-only collection.
- Read-only JSON/CSV/text outputs, official API references, updated help and 32 mocked regression tests.
- No cloud changes, deployment, merge or live tenancy execution.

## Validation
- Targeted suites exercised Red before implementation and Green after fixes; see tdd.md for chronological evidence.
- `python3 -m unittest discover -s tests -v`: 32 tests passed, exit 0 after final corrections.
- Direct and package CLI help: passed.
- `bash -n collector.sh`: passed.
- `git diff --check`: passed.
- Independent verifier audited Search pagination, attachment completeness, cost/currency association, Monitoring and integration.

Coverage remains bounded by subscribed regions, IAM-visible resources, indexed Search types, service availability and Monitoring retention/agent configuration. Collection failures are evidence gaps, not proof of inactivity. Observed costs and Advisor estimates are not guaranteed realized savings. No pre-existing suite existed; this task establishes the regression baseline.
