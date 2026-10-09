# Issue 5: Standalone collection binary

Approved request: fix #5 independently from #8 and #9, coordinated by tracking issue #10. Base: develop. Branch: fix/binary-distribution. Tracking PR: https://github.com/dralquinta/OCI-FinOps-Helper/pull/11.

## Acceptance criteria
- Root `build.sh` builds a standalone Linux x86_64 `dist/oci-finops-helper` embedding Python, collector, OCI CLI, notebooks, documentation and license.
- Running the binary performs collection in an isolated output directory and emits a tar.gz archive containing collection outputs with safe relative paths.
- Collection failures propagate as nonzero exit codes and cannot be represented as successful archives.
- Binary smoke validation runs with neither Python nor OCI CLI on PATH and inspects a tar.gz produced by an offline/no-op collection.
- No customer files, credentials or generated output are embedded or committed.
- Preserve only the known metadata cache across isolated runs, with atomic successful updates, no overwrite on failure and symlink rejection; issue-8 validates cache scope/TTL.

## Plan
1. Write failing distribution tests for CLI dispatch, frozen OCI command routing, isolated collection outputs, success archives and failures.
2. Add a binary entrypoint and frozen-aware OCI launch helper; integrate launch seams into existing collector utilities without changing source CLI behavior.
3. Package OCI CLI, runtime libraries and explicitly allowed suite assets using PyInstaller; provide root build.sh and native Linux build workflow.
4. Verify safe archive members, status propagation, suite asset extraction and source runtime compatibility.
5. Run targeted and full unittest suites, build the actual binary, and run an offline smoke test with restricted PATH.
6. Update TDD records, commit scoped changes, push and mark the issue PR ready only after validation.

## Agent roster and file ownership
- issue5 agent: implementation, tests and issue-5 TDD documentation in this isolated worktree.
- root coordinator: independent verification/TDD auditor, tracking PR gate, integration review.
- Concurrent issue8 and issue9 owners operate in separate worktrees; shared source filenames are isolated by branch.

Owned files: src/distribution.py; src/binary_entrypoint.py; src/utils/api_executor.py; src/utils/executor.py; src/utils/recommendations.py; src/utils/growth_collector.py; src/utils/finops_collector.py; packaging/collector.spec; requirements-build.txt; build.sh; scripts/smoke_binary.py; scripts/prepare_assets.py; .github/workflows/build-binary.yml; docs/binary-distribution.md; .gitignore; tests/test_distribution.py; docs/fixes/fix/binary-distribution/issue-5/{plan,tdd,changes}.md.

## Validation
- python3 -m unittest tests.test_distribution -v
- python3 -m unittest discover -s tests -v
- bash build.sh
- python3 scripts/smoke_binary.py dist/oci-finops-helper

## Constraints
Tokensave is unavailable in the tool surface; targeted source reads are used. No implementation edits until remote tracking draft PR exists. No SDD requested. First Red step is the targeted distribution test suite; expected missing-module failures initially, followed by behavior-specific tests.
