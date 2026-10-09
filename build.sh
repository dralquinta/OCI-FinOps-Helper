#!/usr/bin/env bash
# Native build: output is the executable itself, never a collection archive.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
BUILD_ENV="${FINOPS_BUILD_ENV:-$ROOT/.build-venv}"
python3 -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install -r requirements-build.txt
"$BUILD_ENV/bin/python" scripts/prepare_assets.py build/suite
"$BUILD_ENV/bin/python" -m PyInstaller --noconfirm --clean packaging/collector.spec
"$BUILD_ENV/bin/python" scripts/smoke_binary.py dist/oci-finops-helper
