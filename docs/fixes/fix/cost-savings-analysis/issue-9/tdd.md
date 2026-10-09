# TDD record: issue 9

## Red: missing implementation
Added `tests/utils/test_cost_savings_analysis.py` before implementation. Ran `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: failed with `ModuleNotFoundError: No module named 'src.utils.cost_savings_analysis'`. Five planned behavior tests covered raw authoritative costs/currencies, resource execution detail/duplicate Advisor evidence, all candidate types, executive exports, and notebook launch locations.

## Green
Remote draft PR #13 opened before implementation. Added the offline analysis helper and new notebook; all five tests passed. No cloud commands run. User steering incorporated full resource-action execution detail and executive Markdown/HTML/CSV exports.

## Red: independent audit follow-up
Added two tests for distinct Advisor actions overlapping on the same resource, ambiguous cross-region billing attribution, explicit evidence gaps, measurement period, and invalid ISO timestamps. Ran the two focused tests: both errored as expected with missing `evidence_gaps` and `measurement_period` keys.

## Green: audit follow-up
Added explicit evidence-gap/measurement-period fields, ISO timestamp validation and retained conservative per-resource maximum estimates. Two distinct overlapping actions estimate 25 rather than 40 USD/month; ambiguous-region actions retain unknown observed costs. All seven targeted tests passed.

## Refactor and regression
Consolidated execution details in one helper; no provider text executed. Notebook cells have deterministic IDs and no saved customer outputs. Extended sequential execution verification to include full synthetic FinOps/Advisor evidence from both repository root and notebook directory plus empty cost evidence. Captured notebook stdout in tests to keep regression output concise.

- `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: 7 tests passed.
- `python3 -m unittest discover -s tests -v`: 39 tests passed after final notebook/test updates.
- Notebook sequential execution is part of the targeted test: both working directories and empty inputs passed.

Independent root audit pending; no implementation commit/push yet.

## Red/Green: coordinator audit of completeness
Added tests for complete resource/compartment spend summaries, summary-only Advisor backlog and the real collector command. First run failed with missing `resources` and missing `--growth-collection` (notebook used a nonexistent flag). Added full spend tables (including unknown identities/refunds), preserved Advisor summaries as nonadditive reviews, added exact recommendation metadata/counts and expanded Console location detail. Corrected collection instructions to four positional parameters plus `--growth-collection`, default recommendations and binary archive extraction. Updated the existing backlog-count assertion because summaries are now intentionally retained.

Final validation after these changes:
- `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: 9 passed.
- `python3 -m unittest discover -s tests -v`: 41 passed.
- Synthetic notebook sequential runs with full evidence and empty inputs remain passing.

## Red/Green: executive readability and complete linked appendices
Added `test_print_friendly_executive_report_and_complete_appendices` first. Focused run failed because the HTML output lacked `<table>` (it wrapped Markdown in `<pre>`). Implemented styled, print-friendly HTML tables for baseline, measurement period, top drivers, action/status counts and full action appendix. Executive main sections show top 10 drivers per currency; resource/compartment CSV appendices preserve all rows and are linked from Markdown/HTML. Added UTC report preparation timestamp. Tests verify complete 15-row CSV exports while low-ranked rows are absent from the executive table.

Final targeted command: `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: 10 passed.
Final full regression: `python3 -m unittest discover -s tests -v`: 42 passed.
Sequential notebook execution remains passing after report refinements. Coordinator independently accepted financial logic before this reporting refinement; final reporting review pending.

## Red/Green: editable post-change outcome tracker
Added `test_action_csv_has_blank_owner_outcome_and_verified_savings_tracker` before implementation. Focused run failed because the action CSV lacked `owner`. Added initially blank owner, approval/execution date, baseline/comparison period, verified savings/currency/evidence and outcome-notes columns. Notebook explains editing a separate tracker copy, preserving evidence, and keeping verified results distinct from estimates. No calculations of realized savings or cloud changes are performed.

Final targeted: 11 passed. Final full regression: 43 passed. Commands: `python3 -m unittest tests.utils.test_cost_savings_analysis -v` and `python3 -m unittest discover -s tests -v`.

## Red/Green: real OCI Advisor action shape
Coordinator real-evidence validation found dictionary-valued resource action objects. Added a synthetic provider-shaped fixture (no customer data) with `action` containing type/description/url, null metadata, extended metadata and summary description. First focused test reproduced `TypeError: unhashable type: 'dict'` when exporting action counts. Normalized the action label from its scalar type while preserving all original provider fields as inert evidence in the appendix and CSV. Provider URLs/descriptions are escaped text, never executed.

Added another synthetic test for extended-metadata region and invalidated estimates. First run failed because region remained Unknown. Region now uses provider extended metadata before cost inference. `noLongerRecommend` and estimate-calculation errors explicitly change review status and exclude estimates from the screening aggregate; errors remain visible warnings.

Final targeted: `python3 -m unittest tests.utils.test_cost_savings_analysis -v`: 13 passed.
Final full regression: `python3 -m unittest discover -s tests -v`: 45 passed.
Coordinator real-input rerun pending.

## Red/Green: OCI string boolean metadata
Coordinator real-input validation identified string `false`/`true` flags in estimatedSavingCalculationError and noLongerRecommend. Added a synthetic boolean/string/error-message matrix test. First run incorrectly retained only 10 rather than 20 USD/month eligible estimates. Added explicit known-token boolean normalization; string false no longer produces errors, string true invalidation is honored, and real nonboolean error descriptions remain flagged. Original provider evidence remains untouched.

Final targeted: 14 passed. Final full regression: 46 passed. Both standard validation commands ran successfully. Coordinator real-report rerun pending.

## Final independent coordinator verification

Coordinator independently ran all 14 focused tests and diff whitespace check: passed. Local supplied evidence successfully produced all five report files covering 3,410 deduplicated review entries and 18,055 resource-spend rows; 1,657 pending resource entries retain nonzero eligible estimates. The earlier structured-action export failure and string-boolean exclusion bug were reproduced and corrected with synthetic regression fixtures. Customer evidence and generated reports remain untracked. No OCI calls or infrastructure changes occurred.
