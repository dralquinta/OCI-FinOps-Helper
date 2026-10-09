# TDD record

## Tracking preparation
Approved scope and isolated branch documented before implementation. Red pending: add tests/test_distribution.py for standalone dispatch and runtime collection archive contract after draft PR gate is confirmed. No implementation changes or tests run yet.

## Red
Added tests/test_distribution.py before implementation. `python3 -m unittest tests.test_distribution -v` failed as expected: ModuleNotFoundError: src.distribution (1 loader error). Tests specify frozen OCI routing, output isolation, safe tar members, failure propagation, symlink rejection, help forwarding and OCI dispatch.

## Asset and extraction Red/Green
Asset tests initially failed with missing scripts module (2 errors), then passed after adding explicit allowlist and notebook sanitizer. Root review found a symlinked extraction ancestor escape: test_symlinked_destination_parent_cannot_escape failed (ValueError not raised), then rejection of destination path symlinks and resolved containment was added.

## Green
Initial distribution tests: 7 passed; asset extension: 9 passed. Full source regression before extraction hardening: 41 passed (`python3 -m unittest discover -s tests -v`). Actual build started using `bash build.sh`; pending binary smoke completion.

## Executable smoke discovered service-loader regression
First build and initial smoke passed embedded CLI version, archive creation/inspection, failure status and extraction. Strengthened second-build smoke failed on `oci compute instance get --help`: No such command compute. OCI service modules live outside oci_cli and the vendor frozen loader assumes a cx_Freeze/MSI layout. Added a failing test for frozen service directory configuration (ImportError before helper existed), then bundled the separate services package and adapted its unpack-directory loader. Third build pending. Root independent targeted audit passed the preceding 10 tests. Notebook sanitation is preventative: current source notebooks had no outputs or OCI literals, while README contains example identifiers.

## OCI initialization order Red/Green
Third actual build still failed service help despite bundling services: OCI package __init__ attempts service loading before the frozen path correction. Added test_service_loading_is_repeated_after_frozen_path_configuration; it failed with an empty observed service-loading sequence. Explicitly reload the requested service after correcting the loader directory and preserve/restore OCI argv context. Fourth build pending. The offline child-failure smoke uses API-key auth and nonexistent configuration with stdin EOF; source OCI confirmed this aborts locally without cloud access.

## Cross-PR cache compatibility Red/Green
Root cross-PR audit identified that isolated temporary outputs would discard issue-8 persistent metadata cache. New two-invocation reuse and failure-preservation tests failed before implementation with unexpected cache_dir argument. Added known-file cache seeding and atomic persistence after successful archive creation, symlink/regular-file checks, default user cache directory and optional --cache-dir. CacheSafety test initially failed with missing parameter. OCI final-command processing assertion also initially failed (not called); frozen commands are finalized after explicit service reloading. This does not borrow or merge issue-8 collector implementation.

## Fourth actual executable validation
`bash build.sh` completed with exit 0 after initialization-order repair. Actual embedded compute/optimizer/monitoring help commands passed, and frozen parent-to-OCI-child invocation reached the forced local missing-configuration abort without cloud calls or a success archive. Help, actual tar.gz inspection, failure propagation and suite extraction all passed under empty PATH. Latest source suite: 15 distribution tests and 47 full regression tests passed after cache compatibility. A final build embeds cache/final-command processing; final smoke seeds a fixture cache and inspects that file in the emitted archive and unchanged after failure.

## Final Green / Refactor / Verification
Source frozen after root audit. Refactor kept the OCI subprocess seam thin and removed an unused import; source CLI behavior and mock compatibility remain unchanged. `python3 -m unittest tests.test_distribution -v`: 15 passed. `python3 -m unittest discover -s tests -v`: 47 passed. Root independently confirmed focused tests and whitespace checks.

Final `bash build.sh` completed with exit 0, producing the standalone Linux x86_64 executable at dist/oci-finops-helper. The build script invokes `python scripts/smoke_binary.py dist/oci-finops-helper` inside its isolated build environment. Actual binary checks passed with no Python or OCI CLI on PATH: source collector help; embedded OCI version; compute, optimizer and monitoring command help; real tar.gz collection archive containing success manifest and seeded known metadata cache; invalid arguments fail without another archive; frozen parent-to-OCI-child reaches forced local missing-config abort without cloud access, archive creation or cache overwrite; sanitized notebook/docs/license extraction succeeds.

All requested validation is complete. Artifact remains ignored and is handed to root for copying into the foreground dist directory. No implementation commit or push performed by this owner; root manages final audit/commit/PR readiness.

## Final independent coordinator delivery audit

Coordinator independently passed all 15 focused distribution tests and diff whitespace check. Cross-PR audit identified and verified persistent-cache compatibility without merging branches. Reviewed archive regular-file restrictions, safe extraction, frozen loader routing and cache atomicity. Copied the final validated native binary to the requested local dist directory; SHA256 matches the tested artifact and executable permission is preserved. Generated binary and customer reports are excluded from commits.
