# Approved plan: unused resource detection

Issue: https://github.com/dralquinta/OCI-FinOps-Helper/issues/6
Branch: `6-enhance-collection-to-detect-unused-resources-for-forced-reduction`
Base: `develop`
Approval: user approved API-backed implementation plan. SDD disabled.
Tracking PR: https://github.com/dralquinta/OCI-FinOps-Helper/pull/7

## Plan and rationale
1. Collect regional Search inventory, compute, block/boot volumes and attachments across accessible active compartments, including root. Preserve raw evidence and structured coverage.
2. Repair monitoring scope and resolution; preserve complete series and distinguish missing data from zero activity.
3. Extend Cloud Advisor summaries with resource actions and metadata; preserve dollar estimates and correct IAM guidance.
4. Aggregate actual resource costs without multiplying billing rows, report review candidates and unknown evidence, and integrate existing full/growth-only modes.
5. Run mocked targeted suites and full regression; document APIs, limitations, and permissions.

No cloud mutations. Search is an indexed inventory, not proof of complete coverage. Stopped compute is a review candidate, not guaranteed savings. Orphan classification requires successful attachment coverage across compartments.

## Agent roster and ownership
- api_research: implementation owner of `src/utils/finops_collector.py`, `tests/utils/test_finops_collector.py`.
- root: integration owner of `src/collector.py`, `src/utils/growth_collector.py`, `src/utils/recommendations.py`, `src/utils/api_executor.py`; remaining tests; README and docs.
- verification_audit: independent read-only verification and TDD auditor.
No concurrent shared-file edits.

## Files
Create `src/utils/finops_collector.py`, `tests/__init__.py`, `tests/utils/__init__.py`, `tests/utils/test_finops_collector.py`, `tests/utils/test_growth_collector.py`, `tests/utils/test_recommendations.py`, `tests/utils/test_api_executor.py`, `tests/test_collector.py`, `docs/FINOPS_COLLECTION.md`, and this directory's `plan.md`, `tdd.md`, `changes.md`.
Modify the existing harnesses listed above and `README.md`.

## TDD and validation
First Red: missing FinOps collector and failing scoped monitoring/Advisor/pagination/growth-only integration tests.
Targeted: `python3 -m unittest tests.utils.test_finops_collector tests.utils.test_growth_collector tests.utils.test_recommendations tests.utils.test_api_executor tests.test_collector -v`.
Full regression: `python3 -m unittest discover -s tests -v`.
External OCI APIs are mocked. No pre-existing tests directory; new suite establishes regression coverage.

## Acceptance criteria
- Discover subscribed regions and accessible active compartments with explicit scope and pagination.
- Preserve inventory, attachment metadata, monitoring series, Advisor actions and actual resource costs.
- Failed or missing evidence is explicit and never treated as inactivity.
- Candidate reporting is read-only and avoids unsupported savings/currency claims.
- Existing modes work, including growth-only, without requiring successful cost/usage queries.
- Targeted and full regression pass with recorded Red/Green evidence.

## Tool availability
Tokensave tools unavailable; use targeted file reads and searches.

## Additional parallel slice
- advisor_enrichment owns only `src/utils/recommendations.py` and `tests/utils/test_recommendations.py`; root relinquishes these files.

## Final implementation notes
Search uses explicit CLI --page traversal because --all is unsupported. The growth CLI callback preserves Search's top-level pagination envelope. Search partial pages retain available records with failed coverage. Final collector suite covers malformed identifiers and retained raw costs.
Modified `collector.sh` help/output text as part of integration; no new flags or authentication mechanism.
Additional output validation covers growth summary candidate/failure counts.
Tracking commits: `8fe6c59`, `74b997c`.

## Review steering
Checked PR comments, inline comments and reviews during work. Only the agent-authored tracking update was present; no external steering pending.
