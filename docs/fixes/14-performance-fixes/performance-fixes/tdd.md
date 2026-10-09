# TDD log

## Baseline
The issue branch originally had no regression suite or standalone binary. The approved fast-forward to develop retains prior fixes and tests. No behavior implementation has begun.

## Planned Red
- CLI named options and growth default/opt-out.
- Bounded metadata work and Monitoring discovery; daily Audit windows and capped retained samples.
- Monetary export precision with raw data and quantities preserved.

## Baseline validation
`python3 -m unittest discover -s tests -v`: 76 tests passed in 0.272 seconds before implementation.

## CLI Red -> Green
Auditor wrote tests before collector edits. `python3 -m unittest tests.test_cli tests.test_distribution.DistributionTests.test_named_collection_arguments_create_archive_with_default_growth -v`: 8 tests, 9 failing assertions including subtests. Named invocation exited 2, growth default was false, and invalid/conflicting inputs were accepted. Two added exact `--from`/`--to` and help regressions failed before their implementation.

Minimal fix: named arguments with date aliases, exclusive legacy/named input, date/calendar/window validation, exclusive modes, growth default and explicit opt-out. `python3 -m unittest tests.test_cli tests.test_distribution -v`: 26 passed independently.

## Currency and collector resource limit Red -> Green
`python3 -m unittest tests.utils.test_currency -v`: 3 tests failed. CSV emitted `12.345` instead of `12.35`, `2` instead of `2.00`, and metadata construction requested 30 workers instead of at most four. Raw JSON/quantity preservation is asserted in the same tests.

Minimal fix: export copies format only monetary fields with Decimal half-up rounding; original dataframe and JSON are unchanged. Missing billing currency is labeled Unknown rather than converted or relabeled USD. Default metadata worker count becomes four.

`python3 -m unittest tests.test_cli tests.test_distribution.DistributionTests.test_named_collection_arguments_create_archive_with_default_growth tests.utils.test_currency -v`: 13 passed in 0.050 seconds.

## Performance Red -> Green
`python3 -m unittest tests.utils.test_executor tests.utils.test_growth_collector -v`: 13 tests, 6 failures and 1 error. Defaults were 10/20/30 workers; submitted metadata work exceeded the pool; Audit commands omitted daily windows/coverage; Monitoring made 16 discovery requests instead of two in the fixture.

Minimal fix: conservative four-worker defaults, bounded pending metadata futures, one Monitoring discovery per region/compartment, supported namespace filtering and bounded parallel scopes, daily exclusive Audit windows and at most 1000 retained samples with complete counts and explicit failures.

`python3 -m unittest tests.utils.test_executor tests.utils.test_growth_collector tests.utils.test_api_executor -v`: 18 passed in 0.041 seconds. Existing two-worker Usage API concurrency/pagination remains unchanged.

## Audit pagination refinement Red -> Green
Two added tests failed before replacing whole-day `--all` output: expected 1,400 total events but got 700, and repeated-page handling made one request instead of two. Audit now requests server-sized pages with `--page`, detects repeated tokens, counts all retrieved events, and retains partial counts with failed coverage if a later page fails. No unsupported `--limit` option is used. Daily windows are a performance choice; the installed SDK confirms exclusive end times and whole-minute timestamps.

`python3 -m unittest tests.utils.test_executor tests.utils.test_growth_collector tests.utils.test_api_executor -v`: 20 passed after pagination refinement.

## Presentation Red -> Green
Three focused tests reproduced raw resource-action savings `1.235`, numeric nested FinOps CSV cost `1.235`, and raw report estimates/HTML values. The FinOps fixture initially used the wrong schema; it was corrected to an items dictionary and cost list, then rerun against restored original export code to observe the meaningful failing assertion before the fix.

Minimal fix: Decimal monetary display helper applied to resource-action savings, nested FinOps candidate CSV costs, savings review Markdown/HTML/runbook and action/resource/compartment CSV exports. Export copies preserve original report and raw JSON values.

`python3 -m unittest tests.utils.test_recommendations tests.utils.test_finops_collector tests.utils.test_cost_savings_analysis -v`: 36 passed.

## Shell help Red -> Green
`python3 -m unittest tests.test_wrapper -v`: one test failed because `--help` returned 1 before exposing named options. Help now forwards to the source parser before authentication or environment setup. Same command: one passed.

## Regional inventory Red -> Green
Read-only discovery revealed the approved tenancy has 31 subscribed regions and 2,186 active child compartments. Serial regional inventory remained a throughput bottleneck.

`python3 -m unittest tests.utils.test_finops_collector.RegionalInventoryPerformanceTests -v`: one failure, peak concurrent inventory 1 instead of 4 (2.004 seconds).

Minimal fix: existing regional body executes in a four-worker pool, with worker-local inventory, coverage, deduplication and candidates. Sorted aggregation preserves deterministic output and attachment/discovery safety checks.

`python3 -m unittest tests.utils.test_finops_collector -v`: 13 passed in 0.047 seconds. Eight-region fixture verifies peak concurrency four and all 58 coverage records.

## Integration and verification
Existing collection tests explicitly disable growth when isolating unrelated behavior, while default/opt-out integration coverage verifies the changed contract. Binary smoke invokes exact named arguments and disables growth only for its intentional offline no-op collection.

Full regression after CLI/monetary/Monitoring/Audit fixes: 102 passed. After regional inventory fix: `python3 -m unittest discover -s tests -v`, 103 passed in 1.101 seconds. `git diff --check` passes.

Native build environment matches all pinned build requirements (PyInstaller 6.18.0, OCI CLI 3.94.2, pandas 2.2.3). Ran asset preparation and PyInstaller directly using those installed dependencies, avoiding an unnecessary download/reinstall. Initial actual executable smoke passed eight checks with Python/OCI absent from PATH, including named invocation, cache/archive inspection, embedded CLI, authentication failure and suite extraction. Final rebuild/live verification is pending.

## Growth backlog Red -> Green
Final memory review found `Executor.map` eagerly queued every Monitoring/Audit/region scope. A slow first request could retain completed Audit samples for many later compartments even though active processes were bounded.

`python3 -m unittest tests.utils.test_bounded_collection -v`: one test with three failing subtests (Monitoring, Audit, regional inventory), each exceeding the four-worker pending-scope bound before consumption.

Minimal fix: shared bounded ordered map submits at most the pool size, consumes scopes incrementally and preserves output order. Monitoring region/compartment pairs are generated lazily. Existing real concurrency/coverage tests remain green.

`python3 -m unittest tests.utils.test_bounded_collection tests.utils.test_executor tests.utils.test_growth_collector tests.utils.test_api_executor tests.utils.test_finops_collector -v`: 34 passed in 0.097 seconds.

`python3 -m unittest discover -s tests -v`: 104 passed in 1.319 seconds. Rebuilt executable before this final growth-only queue correction passed nine smoke checks, now including Audit CLI help; extracted collector/currency/regional sources matched their then-current checkout bytes. Final queue-enabled rebuild and bounded growth triage remain pending.

Complete cost/usage live validation is running against a preserved executable snapshot whose collector, API, metadata and currency code match final source; only unused growth scheduling changes differ. Customer outputs stay in isolated temporary storage. The invocation uses the issue's authorized tenancy, `us-ashburn-1`, `[2025-09-01, 2025-09-18)` and the user-approved `--no-growth-collection` option. No `--skip-*` flags are used.

## Streaming refinement Red / Green
- Live bulk baseline: 322,139 COST / 324,499 USAGE rows, 718.56 seconds, peak process-tree RSS 4,835.04 MiB. This fails the requested slim resource envelope and is not the final validation.
- Streaming API Red: missing collect_to_store; Green: page persistence before next request, repeated token and failed page checks pass.
- Streaming integration Red: constructor rejects streaming=True. Green: disk merge and fixed CSV chunks preserve COST cardinality, raw precision and two-decimal report amounts. Verifier adjusted frame instrumentation for pandas from_records bypassing __init__.
- Disk-backed FinOps Red: missing indexed cost adapter returns no totals. Green: exact resource/region currency lookup passes without materializing billing rows.
- Cache and schema Red/Green: eight dataset tests pass including 100k rows and 100k cache entries, with bounded allocations, malformed scope handling, TTL preservation and page-level schema inserts.
- System full regression: 131 tests passed after initial streaming integration. Later refinements require final rerun.
- Synthetic 100k COST + 200k USAGE full raw/CSV export: 128.62 MiB peak RSS, 10.73 seconds; larger benchmark pending.

## Cache and ordering review corrections
- New metadata-cache reuse test failed: six lookups rather than three because freshly fetched timestamps exceeded the write-filter snapshot. Passing the same fetched_at timestamp fixes cache persistence; bounded batches are 200/200/101 and the second run makes no requests.
- Review identified decimal-string partition ordering; collector now uses ISO date partitions. Twelve-day chronological raw/CSV regression passes.
- Distribution cache-copy Red prohibited whole-file read_bytes; Green uses bounded copies while retaining atomic write and path safety checks.
- Final synthetic benchmark (strict Decimal totals): 100k COST + 200k USAGE 136.95 MiB / 10.09s; 1M COST + 2M USAGE 136.85 MiB / 102.85s. Peak <256 MiB and growth <64 MiB gates pass. One-million-row scratch is 1.85 GiB; raw JSON and both CSV files use additional disk.
- Six streaming integration tests pass after these fixes.

## Binary and report memory refinement
- Packaging Red: duplicate SDK source payload and disabled native stripping. Green: eliminate duplicate SDK source data, preserve SDK modules, auth, service loader sources and help docs; strip unneeded native debug symbols. Baseline binary 175,734,792 bytes; final size pending rebuild.
- Expanded executable smoke covers nine OCI services and repeated persistent-worker commands. Packaging/distribution tests passed before final executable validation.
- FinOps report Red: whole-inventory JSON string allocates a second representation. Green: json.dump writes directly to file; indexed COST lookups and output precision tests pass.

## Monitoring retention
Red: synthetic 20,000 datapoints retained beyond the 1,000-point cap. Green: thirteen related growth/bounded tests pass; counts remain complete and samples expose truncation. Both worker-local and global caps prevent accumulating full sample responses. Final system suite: 142 tests pass.

## Final source verification
System Python: 142 tests passed in 12.302s. Pinned build Python: 142 tests passed in 17.056s. Independent pinned rerun passed in 16.987s. Compilation and diff whitespace checks passed. These suites include named/legacy CLI streaming defaults, worker reuse/timeout/cleanup, packaging dependency preservation, bounded cache transfer, daily page failure semantics, chronological raw/CSV exports and capped Monitoring/Audit retention.

Final stripped build initially failed because its default native-binary cache was read-only. Retried with a writable temporary PyInstaller cache; no repository or runtime behavior change.

## Native strip executable regression
Final stripped build completed, but real --help failed before any API request: NumPy OpenBLAS ELF load command alignment was invalid. The first attempted live repeat exited at startup and is not a valid performance measurement. Native stripping is therefore removed; duplicate SDK-source removal remains. Rebuild and all executable smoke checks must pass before final live validation.

## Safe executable rebuild
Native libraries preserved intact. Final binary is 141,247,800 bytes (134.70 MiB), compared with 175,734,792 bytes (167.59 MiB): 19.62% smaller. Archive entries decrease from 32,880 to 15,169; duplicate SDK source entries are absent. Independent extraction checks match all six changed production source assets and the native OpenBLAS wheel bytes. Final startup --help passes; expanded smoke/live checks in progress.

Final source regression after no-strip packaging correction and writable cache wrapper: 143 tests pass in both system and pinned environments.

## Persistent-worker diagnostic correction
Expanded missing-configuration executable check exposed string-valued SystemExit serialization as a returncode. Focused Red reproduced it; Green normalizes string exits to numeric status 1 and preserves the message on stderr, matching ordinary CLI semantics. Valid-config live collection is unaffected by this error-only correction. Final delivery executable rebuild and full regression repeat follow.

## Live transient-page correction
The first safe streaming live repeat correctly returned partial status 1 with no archive: COST September 11 and USAGE September 6 returned invalid payloads, removing whole daily partitions. All present dates exactly match baseline counts, monetary totals and quantities. The run took 583.15s with 1,198.72 MiB peak process-tree RSS; this is incomplete triage evidence, not a success comparison.

Installed OCI CLI raw-request source confirms HTTP 4xx/5xx responses return CLI status zero and bypass SDK ServiceError retries. New Red tests reproduce failure on HTTP 429/503 responses. Green adds four bounded retries per page for 429/500/502/503/504, capped backoff and numeric Retry-After, without duplicate page writes. HTTP authentication failures and malformed payloads fail immediately. Diagnostics now expose only HTTP status and safe API code. Full regression and rebuilt executable/live repeat pending.

## Final retry-enabled delivery verification
System full suite: 148 tests passed in 12.546s. Pinned full suite: 148 tests passed (final log retained locally). The HTTP-status guard also rejects valid-looking item arrays on failed responses without persisting them. Two previously failed daily partitions collected successfully with exact baseline counts. Final retry-enabled binary is 141,250,704 bytes (134.71 MiB), 19.62% smaller; expanded executable smoke passed with external Python/OCI absent. Seven packaged production sources match the checkout and native library bytes remain intact. Final complete live run is in progress.

## Historical persistent-worker TDD evidence
Independent auditor recorded missing-module Red before worker implementation, followed by 31 worker/distribution tests green in system and pinned Python. Offline source stress completed 32 help requests through four persistent workers in 0.46s, about 274 MiB combined worker RSS, with all children reaped on pool close. This source-only worker envelope is separate from final frozen live process-tree measurements. Final frozen smoke additionally validates reused workers and numeric authentication-failure status.

Final retry-enabled source verification: 148 tests passed in 12.546s (system) and 17.665s (pinned build). Independent review found no blockers in pagination, retries, finite backoff, header parsing or failure handling. Final diff/security audit passed.

## Final complete live cost/usage validation
Final retry-enabled standalone executable: status 0, one archive, 393.77s, peak process-tree RSS 1,263.56 MiB, six processes. Baseline: 718.56s / 4,835.04 MiB; observed runtime reduction 45.20%, memory reduction 73.87%. Fresh cache; identical authorized tenancy, region and date interval. Raw COST 322,139 / USAGE 324,499; merged rows 322,139. Streaming archive inspection confirms raw counts, merged cardinality, per-currency monetary totals and quantity totals exactly match baseline. Metadata matches baseline (25 successful / 1,770 unavailable); no authentication, parameter, connection or partial-collection indicators were detected. These measurements include the OCI workers, unlike the synthetic collector-only benchmark.

## Final bounded default-growth triage
Final binary invoked without an explicit growth flag, while skipping already-tested billing, enrichment and Advisor. Intentional 60-second cutoff: 61.57s elapsed, 639.81 MiB peak process-tree RSS, six processes, SIGTERM status -15 and no archive as expected. No authentication/parameter/import/connection indicators appeared. Probe scratch was isolated and cleaned. This verifies the approved bounded default path, not a complete scan of 31 regions / 2,186 active child compartments.

## Completion check
- Tests preceded implementation and expected Red failures were observed.
- Green/refactor and related/full regression results are recorded chronologically.
- 148 tests pass in system and pinned build environments.
- Final standalone executable smoke, source-byte verification, synthetic memory benchmark and approved live validations pass within their stated scope.
- Documentation reflects measured limits; no customer data or machine-local paths are staged.

## Follow-up: missing on-screen feedback
Diagnosis: the foreground executable matches the committed source. Distribution forwards parent stdout; only OCI worker response payloads are captured intentionally. The streaming early return bypasses legacy startup/spinner reporting and successful page requests emit no feedback. Existing tests verified data/memory semantics and CLI help but did not require visible flushed streaming progress before blocking requests. Red/Green and executable results follow.

## Progress feedback Red / Green
Performance Red: two missing-output failures before blocking calls and two missing-helper errors. Green: five feedback tests plus streaming/collector/API regressions passed. Messages are thread-safe, flushed and identifier/control-character redacted; 30-second heartbeats use stoppable waits and fixed active-stage threads. Per-page counts use local accumulators; CSV notices are first/every ten chunks/final, with no per-row logging or per-page database counts.

Distribution Red: blocked cache and gzip operations emitted no flushed startup/stage feedback. Green: 21 distribution tests pass, including controlled slow-archive heartbeat. Wrapper feedback begins before workspace/cache operations and covers archive and cache completion. System full suite: 155 passed in 13.287s; pinned full suite: 155 passed in 17.464s. Executable pipe visibility and rebuilt artifact validation pending.

Actual old-binary Red: isolated synthetic missing-configuration probe failed the immediate flushed startup-feedback contract, without changing the user process or executable. New executable verification must pass Popen pipe first-output-before-completion and prior service/worker/archive/cache checks.

Final progress follow-up full regression: 156 tests passed in 14.199s (system) and 18.516s (pinned). The 100k COST / 200k USAGE export retained exact cardinality/precision at 132.43 MiB peak collector RSS and 12.37s; concurrent binary build means this timing is not an isolated overhead comparison. New feedback leaves page retries, billing joins, chunk sizes and worker limits unchanged.

## Progress follow-up executable Green and delivery
Rebuilt artifact: 141,257,448 bytes, with duplicate SDK source count still zero. The actual Popen pipe check observes startup feedback before process completion; all nine OCI services, worker reuse, archive/cache routing and isolated auth-failure checks pass. Collector, API, distribution, feedback helper and worker packaged source bytes match the checkout.

Installed the verified artifact as dist/oci-finops-helper-progress. The active canonical binary is byte-for-byte unchanged. PyInstaller lazily reopens its executable-embedded PYZ archive, so replacing that pathname while the user run is active would be unsafe. The running process continues with its loaded version; next invocation can use the updated filename with the same arguments.
