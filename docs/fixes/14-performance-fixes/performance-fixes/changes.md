# Issue 14 changes

## Root Cause Analysis

The issue branch predated executable delivery and recent collection corrections. The existing CLI required positional arguments and opted into growth collection. Metadata launched up to 30 heavyweight CLI processes with eager futures; Monitoring repeated discovery for every namespace; regional inventory ran serially; Audit retained whole-range responses; monetary report formatting varied.

The first approved live cost/usage run showed that worker limits alone were insufficient: 322,139 COST and 324,499 USAGE rows took 718.56 seconds and peaked at 4,835.04 MiB process-tree RSS. Full response arrays, DataFrames, enrichment maps and JSON/cache copies amplified memory use.

Executable and live verification exposed two additional defects. Native stripping corrupted the patched NumPy OpenBLAS ELF alignment, so stripping was rejected. OCI raw-request treats HTTP errors as successful CLI executions; two failed daily responses initially removed complete partitions. The collector returned partial failure and created no archive, but needed application-level transient retries and better diagnostics.

## How It Was Fixed

- Named tenancy, region and date options coexist with positional compatibility. Input is validated before collection. Growth is enabled by default, with opt-out and independent only modes.
- The CLI persists daily, 1,000-row Usage API pages to temporary indexed SQLite. Raw JSON and CSV reports stream incrementally; joins and metadata enrichment handle at most 2,000 COST rows per chunk. Ambiguous USAGE metadata never multiplies monetary rows.
- Four reusable OCI workers and bounded queues cap active requests and prevent task backlogs. Metadata uses batches of 200 IDs; caches load, write and transfer incrementally with scope checks, original timestamps and TTL preserved.
- HTTP 429/500/502/503/504 receive four bounded retries per page, with capped backoff and numeric Retry-After. Retries preserve the page token and persist rows only after success. Authentication errors, malformed success payloads and exhausted retries fail explicitly.
- Monitoring discovers metrics once per scope and retains at most 1,000 streams and 1,000 datapoints per metric, with complete counts and explicit truncation. Audit paginates daily windows, counts all retrieved events and retains at most 1,000 sample events. Failure coverage remains visible.
- Regional inventory runs with four isolated workers. FinOps uses indexed billing lookups and streams JSON serialization. Candidate safety continues to require complete discovery and attachment evidence.
- Money is rounded half-up to two decimals only for display. Quantities and raw numeric values retain precision; billing currency is preserved, missing currency is Unknown, and Advisor estimates remain USD without conversion.
- Packaging removes duplicate SDK source payloads while retaining compiled SDK modules, OCI service loading, help, auth and intact native libraries. Build caches default to a writable project-local directory.

## Summary

The branch provides the requested CLI and report behavior, bounded billing-data memory, reusable parallel workers, truthful partial-result handling and a slimmer standalone binary. Source, large-dataset, executable and complete live cost/usage verification passed.

## Validation

- System and pinned-build full regression: 148 tests passed. Coverage includes CLI defaults, page retries, exact joins, precision, bounded metadata/cache transfer, worker timeout/replacement/cleanup, and Monitoring/Audit caps.
- Synthetic full export: 100k COST plus 200k USAGE used 136.95 MiB collector RSS in 10.09s; one million COST plus two million USAGE used 136.85 MiB in 102.85s. Exact Decimal totals, raw precision and row cardinality passed. The larger run used 1.85 GiB scratch disk, plus raw JSON and CSV artifacts. These measurements exclude OCI worker processes.
- Final binary: 141,250,704 bytes (134.71 MiB), down 19.62% from 175,734,792 bytes (167.59 MiB). Duplicate SDK sources are absent; packaged changed sources match the checkout and OpenBLAS matches the original wheel bytes. Expanded executable smoke passed with Python/OCI absent from PATH: nine service commands, persistent worker reuse and authentication status, archives, cache safety, invalid-input handling and suite extraction.
- Incomplete streaming triage: 583.15s and 1,198.72 MiB process-tree RSS, correctly returning status 1 with no archive. Every present day matched baseline counts and numeric totals; two failed partitions were isolated. Targeted retry-enabled collection recovered their exact 19,223 COST and 18,633 USAGE rows. This triage is not the final success measurement.
- Final complete retry-enabled live run: status 0, one archive, 393.77s, 1,263.56 MiB peak process-tree RSS and six processes. Compared with the 718.56s / 4,835.04 MiB baseline, runtime fell 45.20% and peak memory fell 73.87%. Raw counts (322,139 COST / 324,499 USAGE), merged cardinality, per-currency monetary totals and quantities exactly match the baseline. Metadata results also match: 25 fetched and 1,770 unavailable; unavailability reasons were not individually retained.
- Final approved bounded default-growth probe: intentionally terminated after the 60-second budget (61.57s elapsed), 639.81 MiB peak process-tree RSS, six processes, no authentication/parameter/import/connection indicators. No archive was expected from the interrupted probe; private probe scratch was cleaned. An exhaustive scan of 31 subscribed regions and 2,186 active child compartments was not requested.

Inventory and attachment safety indexes still scale with discovered resources. Growth duration scales with region/compartment scopes and service permissions; billing-memory benchmarks do not establish a tenancy-independent envelope for exhaustive growth. Scratch and artifact disk use scale with row count. See tdd.md for the chronological Red/Green record and measured limitations.

## Follow-up: streaming progress visibility
User-observed regression: collection starts silently because the streaming path bypasses legacy banners/spinners. Startup, stage, request, persisted-page counts and completion messages now flush immediately. Slow requests, processing, cache transfers and archiving emit a 30-second heartbeat. Reporting is thread-safe and redacts resource identifiers/control characters; counters remain bounded and exports report first/every ten chunks/final. The request, join, retry and worker semantics remain unchanged.

Validation: 156 tests pass in system and pinned Python, actual rebuilt executable feedback arrives before the process finishes, and all expanded executable checks pass. The 100k COST / 200k USAGE benchmark preserves cardinality and precision at 132.43 MiB collector RSS. Binary size is 141,257,448 bytes, retaining the earlier packaging reduction.

The verified update is installed alongside the current executable as dist/oci-finops-helper-progress. The canonical executable is unchanged to protect the user run: PyInstaller lazily reads its embedded archive and must not have that pathname replaced while running. Future source builds retain the canonical output name.

## Follow-up: regional inventory JSON errors

### Root Cause Analysis
OCI CLI suppresses stdout for successful list operations with no resources. The growth executor unconditionally decoded that empty string as JSON, printing a decoding failure for each empty compartment/region and classifying valid empty evidence as failed. Existing tests used JSON-encoded empty arrays and did not cover the actual CLI renderer. Worker output capture was verified independently.

### How It Was Fixed
Successful blank list responses become empty lists; return-code errors, malformed nonblank JSON, and empty non-list responses retain failure behavior.

### Summary
Empty regional inventories no longer flood the terminal with JSON parse errors.

### Validation
Red regression observed and targeted growth/FinOps suites passed (29 tests). Bounded live request independently confirmed successful empty CLI output. Full suite and rebuilt executable checks pending.

Final follow-up validation: both system and pinned Python regression suites passed all 159 tests. Growth-to-FinOps integration preserves empty evidence and attachment-failure safety. Bounded live requests for all four reported operations completed without parse errors, including empty and nonempty results. Rebuilt standalone binary passed expanded offline smoke with signed localhost empty/nonempty/empty inventory requests and existing service/worker/archive/cache checks; installed at `dist/oci-finops-helper`. No exhaustive tenancy growth scan was repeated for this follow-up.
