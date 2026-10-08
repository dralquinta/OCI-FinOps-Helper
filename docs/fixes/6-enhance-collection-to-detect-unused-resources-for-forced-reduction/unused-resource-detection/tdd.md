# TDD log

## Baseline
No pre-existing tests directory. No tests run yet.

## Red (planned)
Add mocked behavior tests before implementation; record actual failures.

## Red observed
- New FinOps suite: import failed because `src.utils.finops_collector` did not exist (agent run).
- `python3 -m unittest tests.utils.test_growth_collector tests.utils.test_api_executor tests.test_collector -v`: exit 1 before implementation. Monitoring returned no scoped queries/coverage; FinOps integration symbol absent; pagination omitted additional pages and returned partial costs; timeout left request file; growth-only did not run collection; raw cost data was not forwarded.

## Green and refactor
- Inventory suite: 8 tests passed after module implementation; independent auditor confirmed conservative cross-compartment attachment handling.
- Advisor suite: initial Red 5 tests had missing resource-action evidence, incorrect currency/IAM and partial-error coverage failures. Initial Green passed 5. Additional metadata/empty-summary tests failed, then passed; final focused suite 6 tests.
- Monitoring: 3 behavior tests passed after discovery/scoping, complete series retention and FinOps integration.
- Usage pagination: 4 behavior tests passed after page traversal, URL encoding, repeated-token guard and finally cleanup. Corrected a test-only missing Path import discovered during Green.
- Growth integration: 5 tests passed after collection moved outside merge dependency, raw costs forwarded, and requested failures reported truthfully. Package/direct imports remove full-discovery module collision.
- Search callback: dedicated envelope-retention test failed, then passed after callback retained top-level pagination metadata.
- First full regression passed 27 tests before the final Search pagination correction. This is not final certification.

## Independent audit follow-up
Search does not support --all; implement explicit CLI page traversal. Red includes pagination, malformed attachment reference and raw-cost preservation cases. Final results pending.

## Final audit corrections and Green
- Search suite expanded: Red 11 tests failed on unsupported --all, pagination record count, and malformed attachment reference. Green: all 11 collector tests pass after explicit CLI page traversal, envelope retention and defensive identifier validation. Complete raw input cost data is retained.
- Advisor console currency regression: dedicated test failed before changing console totals to USD; all 7 Advisor tests pass afterward.
- Growth summary regression: candidate/failure visibility test failed before summary section, then passed. Monitoring/growth suite now 5 tests.
- Refactor retained existing authentication/CLI modes, isolated inventory into a small utility and kept the previous recommendation items contract. No further behavioral refactoring was needed.

## Final verification
- `python3 -m unittest tests.utils.test_finops_collector -v`: 11 passed (collector owner and independent audit).
- `python3 -m unittest tests.utils.test_recommendations -v`: 7 passed (Advisor owner).
- `python3 -m unittest tests.utils.test_growth_collector -v`: 5 passed in full suite, including dedicated Red/Green for Search envelope and summary.
- `python3 -m unittest tests.utils.test_api_executor -v`: 4 passed.
- `python3 -m unittest tests.test_collector -v`: 5 passed.
- `python3 -m unittest discover -s tests -v`: exit 0, 32 tests passed. This is the final regression after all corrections.
- `python3 src/collector.py --help` and `python3 -m src.collector --help`: pass.
- `bash -n collector.sh`: pass.
- `git diff --check`: pass.
- No live OCI collection or cloud mutations performed. APIs/CLI were checked against Oracle references; production coverage remains dependent on IAM, subscriptions, agents and retention.
