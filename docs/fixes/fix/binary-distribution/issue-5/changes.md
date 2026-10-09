# Issue 5 changes

## Root Cause Analysis
Source-only distribution required Python environment bootstrap and an externally installed OCI CLI; collection lacked an output archive contract. Existing tests covered source collectors rather than frozen process dispatch or delivery artifacts. Suite assets can accumulate notebook execution results or literal example OCI identifiers (present in README); sanitization is a preventative guardrail, not an observed defect in the current notebooks. Strengthened executable smoke also revealed OCI CLI service modules are dynamically loaded from a separate top-level package and use a frozen directory layout incompatible with PyInstaller.

## How It Was Fixed
A standalone entrypoint invokes the existing collector inside a temporary working directory, preserves its exit status, and creates a tar.gz of regular collection output files only on successful completion. Frozen OCI subprocess calls invoke the embedded OCI CLI through the same executable; source CLI calls remain unchanged. OCI dynamic service modules are bundled explicitly and their loader is directed to the PyInstaller unpack directory, with OCI argument context preserved. Root build.sh creates the PyInstaller binary with pinned builder/runtime dependencies and an allowlist of sanitized suite assets plus dependency license notices. Suite extraction rejects symlink destinations and existing files. A stable known-file metadata cache is seeded into isolated outputs and updated atomically only after successful collection/archive creation; failures preserve prior cache, and symlink paths are rejected. This preserves compatibility with the independent issue-8 metadata cache implementation.

## Summary
Added a native standalone Linux binary build and offline executable smoke verification. Runtime tar.gz archives contain safe relative output paths and a success manifest. Build output remains the executable at dist/oci-finops-helper; the build does not package the binary into a tar.gz. Source notebook files are unchanged. Extracted suite now includes allowlisted production src/**/*.py verbatim, preserving imports for notebook helpers introduced by future merged PRs.

## Validation
- Initial failing distribution tests: missing src.distribution module observed.
- Asset tests: missing preparation module observed before implementation.
- Extraction regression: symlink ancestor escape reproduced before hardening.
- Targeted: python3 -m unittest tests.test_distribution -v — 16 tests passed.
- Full regression: python3 -m unittest discover -s tests -v — 48 tests passed.
- Direct source compatibility: python3 src/collector.py --help passed.
- Actual asset preparation: all existing notebooks have empty outputs, null execution counts and no literal OCIDs; dependency license notices generated.
- Actual build: bash build.sh — exit 0, standalone Linux x86_64 executable created at dist/oci-finops-helper.
- Source-asset incremental rebuild: refreshed assets, PyInstaller --noconfirm without --clean — exit 0.
- Actual binary smoke: scripts/smoke_binary.py — passed with Python/OCI absent from PATH; embedded service help, emitted tar.gz/manifest/cache inspection, invalid arguments, local missing-config OCI child failure, no cache/archive overwrite on failure, and suite extraction including verbatim production source all passed. No cloud calls performed.

## Limits
Native binaries depend on the build platform system C library. OCI configuration/authentication is provided at runtime. Collection failure removes temporary partial outputs and emits no success archive. Nonfatal source collector warnings preserve existing source semantics. All-skipped offline smoke archives contain the manifest plus any seeded metadata cache. Notebook execution requires separately installed notebook dependencies.
