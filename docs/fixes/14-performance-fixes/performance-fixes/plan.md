# Issue 14: performance fixes

Issue: https://github.com/dralquinta/OCI-FinOps-Helper/issues/14
Branch: `14-performance-fixes`; base: `develop`; tracking PR: https://github.com/dralquinta/OCI-FinOps-Helper/pull/15 (draft).
Mode: new task; spec-driven disabled. Scope and plan approved by the user.

## Approved plan
1. Fast-forward the existing issue branch to current develop to retain the standalone binary and previous regression fixes.
2. Publish these tracking documents and open a draft PR before implementation.
3. Write failing CLI and binary dispatch tests, then add named tenancy/region/date options with positional compatibility, default growth collection and an explicit opt-out. Preserve recommendations-only behavior and reject invalid/conflicting arguments before collection.
4. Write performance regressions, then reduce excessive OCI subprocess concurrency, bound pending work, and remove redundant Monitoring discovery. Preserve failures and collection coverage. Split Audit requests into supported daily windows and bound retained samples.
5. Write export regressions, then render monetary CSV fields with two decimals and explicit source currency, preserving quantities and raw JSON precision. Existing USD Advisor report semantics remain intact; no currency conversion is implied.
6. Run targeted and related tests, full regression, actual binary smoke checks and read-only OCI triage using the issue's authorized parameters. Commit, push and mark the PR ready after validation.

## Agent roster and file ownership
- root: integration owner; `src/collector.py`, currency export helper and tests, `collector.sh`, `README.md`, `scripts/smoke_binary.py`, tracking documentation and build/remote validation.
- performance: `src/utils/executor.py`, `src/utils/api_executor.py`, `src/utils/growth_collector.py`; `tests/utils/test_executor.py`, `tests/utils/test_api_executor.py`, `tests/utils/test_growth_collector.py`.
- auditor: `tests/test_cli.py`, `tests/test_distribution.py`; independent final verification and TDD document audit.
- Conflicts: none. Only the assigned owner edits a file until explicit handoff.

## Planned files
Owned files above, plus test package markers if needed. No SDD files, customer output, credentials, compiled binaries or unrelated notebook changes will be committed.

## Acceptance criteria
- Named `--tenancy-ocid`, `--home-region`, `--from`, `--to` work in source and executable; positional invocation still works.
- Growth runs by default; `--no-growth-collection` disables it; recommendations-only remains independent.
- Default subprocess fan-out and outstanding work are bounded; redundant discovery is removed; Audit windows and failure coverage remain truthful.
- Monetary CSV values use two decimals and source currency; raw JSON and nonmonetary measurements keep their precision.
- Full regression and executable checks pass; real OCI validation is recorded truthfully, including access or historical-data limitations.

## Validation commands
- `python3 -m unittest tests.test_cli tests.test_distribution tests.test_collector -v`
- `python3 -m unittest tests.utils.test_executor tests.utils.test_api_executor tests.utils.test_growth_collector tests.utils.test_currency -v`
- `python3 -m unittest discover -s tests -v`
- `bash build.sh` and `python3 scripts/smoke_binary.py dist/oci-finops-helper`
- Read-only executable collection with issue parameters, isolated output/cache and runtime measurements. Customer identifiers and data remain outside tracked artifacts.

## Tooling
Tokensave MCP and harness file-read tools are unavailable in this session; targeted shell reads are the fallback. Available collaboration tools satisfy the skill's two-agent requirement. All shell commands use RTK.

## First Red step
Observe named-argument/default-growth failures in `tests/test_cli.py` and worker/discovery/export regressions before each corresponding behavior change.
