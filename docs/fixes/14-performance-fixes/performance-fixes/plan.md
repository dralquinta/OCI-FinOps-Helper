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
- root: integration owner; `src/collector.py`, currency export helper and tests, `tests/test_collector.py`, `tests/test_wrapper.py`, `collector.sh`, `README.md`, `scripts/smoke_binary.py`, tracking documentation and build/remote validation.
- performance: `src/utils/executor.py`, `src/utils/api_executor.py`, `src/utils/growth_collector.py`; `tests/utils/test_executor.py`, `tests/utils/test_api_executor.py`, `tests/utils/test_growth_collector.py`. After auditor's currency slice completed, ownership of `src/utils/finops_collector.py` and `tests/utils/test_finops_collector.py` transferred here for bounded regional inventory. Final queue review adds `src/utils/parallel.py` and `tests/utils/test_bounded_collection.py`.
- auditor: `tests/test_cli.py`, `tests/test_distribution.py`; `src/utils/recommendations.py`, `src/utils/cost_savings_analysis.py` and their tests for monetary presentation; initially FinOps monetary presentation, then explicit handoff to performance; independent final verification and TDD document audit.
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

## Integration notes
CLI regression scope includes strict date validation and mutually exclusive modes. Monetary presentation coverage also includes nested FinOps candidate cost CSVs and savings report Markdown/HTML/CSV exports. These are within the approved reports/CSV scope; raw numerical JSON remains unchanged.

Read-only discovery found 31 subscribed regions and 2,186 active child compartments. Regional inventory therefore also receives a four-worker pool with isolated evidence state and deterministic aggregation. The user approved bounded default-growth triage plus a complete cost/usage invocation with `--no-growth-collection`, rather than an exhaustive live scan across more than 67,000 region/compartment combinations. Test coverage still verifies full collection scope and accurate failure records.

## Approved large-dataset and binary refinement
User requires slim memory use and fast bounded parallel execution, and explicitly requests binary slimming in parallel. Root owns streamed collector/CSV/FinOps integration; performance owns disk datasets and streamed metadata cache; verifier owns integration tests and memory benchmark; auditor owns persistent workers and packaging slimming. Existing approvals cover this refinement.

Daily Usage API partitions persist server pages to indexed temporary SQLite. CSV exports and enrichment use at most 2,000 billing rows per chunk. Four workers and bounded queues cap active requests. Metadata cache is streamed and timestamps retain original TTL. Binary audit removes redundant bundled sources only after dependency verification.

## Final ownership and verification handoffs
Root integrates collector, API pages/retries, monetary export, FinOps indexed costs and documentation. Performance owns disk datasets/cache and Monitoring retention; large_data_verifier owns streaming integration, memory benchmark and CLI streaming assertion; auditor owns distribution/worker, packaging, build cache wrapper and executable smoke. The explicit smoke-script handoff supersedes earlier root ownership. All implementation slices are complete and independently reviewed; complete live/default-growth validation and final commit remain.

## Verification complete
148 system and pinned tests, final executable smoke, seven source-byte matches, synthetic million-row memory gates, complete live cost/usage parity and approved bounded default-growth triage passed. Independent audits found no blockers. Final live runtime 393.77s and peak RSS 1,263.56 MiB; binary 134.71 MiB. Latest ownership slices are complete. Next: scoped commit, push and mark tracking PR ready for review.

## Follow-up: visible streaming progress
User reports no on-screen feedback from the committed binary. Existing authorization and tracking PR cover this regression correction; reuse this task and branch without further planning approval. Root owns integration, docs, isolated build and safe versioned executable delivery. Performance owns collector/API feedback and new feedback helper plus progress regressions; auditor owns distribution/cache/archive feedback, independent review and executable smoke. No overlapping ownership.

1. Reproduce missing flushed startup/page/stage output and heartbeat behavior with deterministic tests.
2. Add lightweight thread-safe progress without changing requests, resource bounds, results or CLI arguments.
3. Verify full regression and actual executable feedback; build separately and install the verified binary alongside the active executable without interrupting its run; commit and update PR.

Source files: src/collector.py, src/utils/api_executor.py, src/utils/feedback.py, src/distribution.py. Tests: tests/test_streaming_progress.py, tests/test_distribution.py, scripts/smoke_binary.py and tests/test_packaging.py. Red step: successful streaming requests currently emit no startup/page status or flushed waiting heartbeat.

Progress follow-up verification is complete: 156 tests in both Python environments, old executable feedback Red and rebuilt executable feedback Green, full executable smoke and 100k memory/cardinality guard. Install the updated artifact as dist/oci-finops-helper-progress while preserving the active canonical executable: PyInstaller reopens its embedded PYZ archive during imports, making replacement during a run unsafe. Source build output retains the canonical name for subsequent builds. Next: commit/push and return PR to ready for review.

## Follow-up: empty regional inventory responses

User reported repeated JSON decoding errors for compute and block-volume list commands. Diagnose successful empty OCI CLI output and worker capture, then preserve empty inventories without concealing malformed or failed responses. Existing implementation and remote PR remain the tracking baseline.

Ownership: performance owns src/utils/growth_collector.py and tests/utils/test_growth_collector.py; auditor independently verifies OCI CLI and worker capture and owns tests/test_oci_worker.py if necessary; root owns integration and TDD docs. No overlapping edits. First Red: successful empty inventory list response must produce an empty list without JSON-decoding errors. Validation: targeted growth/worker/FinOps suites, full unittest regression, frozen executable smoke.

Follow-up completed: all three agents finished their assigned slices; successful empty list normalization verified by Red/Green tests, real CLI rendering, worker capture, four bounded live inventory requests, 159-test suites in both interpreters, and rebuilt executable smoke. No worker change was required. Canonical local executable updated safely after the reported process exited.

## Follow-up: compact billing progress UI

Replace billing page/request logs with a compact live terminal status and periodic plain summaries for redirected output. Show completed/total daily windows, COST/USAGE record and page totals, elapsed time, active requests, retries, and truthful failed/interrupted completion. Retain visible retry/error notices and immediate flushed startup. Use bounded counters and active-window state without retaining page history; no new runtime dependency.

Ownership: performance owns src/utils/feedback.py and tests/utils/test_billing_progress.py; auditor owns tests/test_streaming_progress.py and independent verification; root owns src/collector.py, src/utils/api_executor.py, integration and TDD docs. Existing tracking PR #15 reused. First Red: collecting many mocked pages must emit bounded aggregate output rather than one line per request/page. Validate TTY rendering, plain fallback, concurrency, failed/retry counters, full regression, and rebuilt binary smoke.

Verification roster expanded: large_data_verifier owns tests/test_streaming_collection.py and scripts/smoke_binary.py for scale and actual PTY evidence; no overlap with renderer/integration ownership. All three agent source slices are now frozen. Final rebuild and system/pinned regression are running.

Follow-up complete: source and executable verified, compact progress installed in the canonical local binary; all agent-owned slices integrated without conflicts. System/pinned suites each passed 166 tests. Actual PTY smoke verified the requested terminal UX.

## Follow-up: progress bar and terminal color

User requested a bar and color for compact billing progress. Add a width-aware ASCII bar and percentage to real terminals, cyan activity, green success, amber retries/partial outcomes and red failures. Progress measures finished windows including failed windows while success and failure totals remain explicit. Preserve plain redirected logs, TERM=dumb fallback, NO_COLOR opt-out, throttling, bounded memory, redaction and existing interfaces. No runtime dependency is added.

Ownership: performance owns src/utils/feedback.py and tests/utils/test_billing_progress.py; auditor independently verifies terminal rendering and outcome semantics; root owns integration/docs/executable build and smoke adaptations if necessary. Existing tracking PR #15 reused. First Red: real TTY output lacks colored bar/percentage. Validation: ANSI-aware terminal widths, successful/failed/interrupted and zero-window states, no-color/plain output, full unittest suites, real executable PTY smoke.

Follow-up complete: both 169-test suites and rebuilt executable smoke passed, including the genuine-PTY bar/color assertions. Verified binary installed at `dist/oci-finops-helper`; agent slices integrated without conflicts.
