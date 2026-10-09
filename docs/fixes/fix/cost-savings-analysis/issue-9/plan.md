# Issue 9: actionable cost savings walkthrough

Approved scope: add a new self-guided notebook without modifying the existing FinOps notebook. Tracking coordinator: https://github.com/dralquinta/OCI-FinOps-Helper/issues/10. Tracking PR: pending.

## Plan
1. Add behavioral tests for authoritative raw costs, currency separation, refunds, input validation, optional evidence, Advisor overlap, and notebook execution from both supported working directories.
2. Implement a small analysis helper reading raw COST evidence from `out.json` (`call1.items`), never treating multiplied merged CSV rows as authoritative costs.
3. Build a sequential walkthrough notebook showing spend drivers, candidate evidence and coverage, Advisor actions, configurable savings scenarios, an action backlog, and CSV exports.
4. Verify targeted tests and the full regression suite, independently review financial semantics, then update TDD documentation and the issue-specific PR.

## Files and ownership
- `src/utils/cost_savings_analysis.py`, `jupe-note/cost_savings_analysis.ipynb`, `tests/utils/test_cost_savings_analysis.py`, and this task's documentation: issue9 implementation owner.
- Independent TDD and financial-semantic audit: root coordinator; other issue owners may cross-review after completing their isolated changes.
- Integration owner: root coordinator. No concurrent edits of owned implementation files.

## Acceptance criteria
- Notebook runs sequentially using synthetic local evidence without OCI/network access, from the repository root or `jupe-note/`.
- Raw COST amounts remain authoritative; totals are separated by currency and refunds retained.
- Empty inputs and missing optional FinOps/Advisor evidence are explained; malformed required evidence produces actionable validation.
- Observed spend, hypothetical scenario savings, and Advisor USD estimates remain distinct; duplicate or overlapping Advisor evidence is never summed into invented savings.
- Inventory review candidates preserve coverage and unknown costs; stopped instances and unattached volumes require owner validation before changes.
- Notebook supplies concrete review steps and exports an actionable backlog without modifying infrastructure.

## Validation
- First Red: `python3 -m unittest tests.utils.test_cost_savings_analysis -v` should fail because the new helper module does not exist.
- Green/targeted: `python3 -m unittest tests.utils.test_cost_savings_analysis -v`.
- Full regression: `python3 -m unittest discover -s tests -v`.

Spec-driven mode disabled. Implementation remains gated on the remote tracking draft PR.
