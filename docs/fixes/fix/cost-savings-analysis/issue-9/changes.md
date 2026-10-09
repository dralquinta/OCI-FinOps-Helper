# Issue 9 changes

## Root Cause Analysis
The existing exploratory notebook lacks a self-guided, evidence-backed savings action workflow. Its resource usage and merged-cost data cannot alone prove idleness or realizable savings. Existing tests cover collectors rather than notebook financial semantics and execution.

## How It Was Fixed
Added a new self-guided notebook and offline analysis helper using original COST records, separated currencies and refunds, optional collection evidence, explicit measurement periods and unknowns. Resource backlogs contain exact available identity/location details, observed costs, Advisor estimates, review prerequisites, commands only where mapped, risk, recovery limitations and verification. Unsupported Advisor mappings use a Console runbook rather than an invented command.

Executive Markdown/HTML/CSV exports include service/currency and action/status summaries, an approval checklist, collection gaps, conservative overlapping-action screening assumptions and a full resource action appendix. Unassessed rightsizing, licensing/commitment, storage-performance, scheduling and networking opportunities list the specific additional evidence to obtain. Actual spend is never represented as guaranteed savings; cross-resource dependencies remain explicit scenario limitations.

## Summary
Implementation prepared on the isolated issue-specific branch. The existing user-modified notebook and foreground worktree remain untouched. No infrastructure actions were performed.

## Validation
- Targeted: `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: 15 passed.
- Full regression: `python3 -m unittest discover -s tests -v`: 47 passed.
- Sequential synthetic notebook execution: repository root, notebook directory, full optional evidence and empty input passed.
- TDD first observed missing-module Red, then two additional audit-driven missing-field failures before fixes.
- Independent coordinator review pending. No implementation commit or push performed yet.

Coordinator audit expanded exports and walkthrough with all resource and compartment spend drivers (including resources without candidate evidence), retained summary-only Advisor recommendations without inflating screening totals, and corrected collection/extraction templates.

Executive presentation refinement: readable print-friendly HTML tables, top 10 spend drivers per currency in the main briefing, linked full resource/compartment CSV appendices, and report preparation timestamp. Full action execution details remain in the appendix and action CSV.

Action CSV includes initially blank editable ownership, approval/execution, measurement and verified-outcome tracking fields. Notebook explains later evidence-backed outcome reporting and preserving an edited copy from export overwrites.

Real OCI Advisor compatibility: normalize dictionary-valued action types while preserving full inert provider action descriptions/URLs, summary descriptions, extended metadata and original evidence. Read region from extended metadata. Exclude no-longer-recommended and calculation-error estimates from screening totals, preserving explanatory statuses and warnings. Synthetic fixtures model actual provider shapes without customer data.

Explicit OCI boolean/string flag normalization preserves valid estimates when metadata contains `false`, excludes explicitly invalidated `true` entries, and retains genuine error descriptions.

Independent coordinator validation passed all 14 focused tests and real-input report generation. Five report artifacts were generated locally; no customer inputs/results are committed. Collection gaps remain explicit, including unavailable FinOps evidence.

Executive reports remain compact with top 20 action summaries, top spend tables and sampled coverage gaps; the linked complete execution-runbook HTML and full CSV appendices preserve every detail. Notebook resource filtering and shortlists prevent thousands of actions from overwhelming walkthrough output.
