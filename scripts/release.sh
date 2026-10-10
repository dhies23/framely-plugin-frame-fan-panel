#!/usr/bin/env bash
# Build a release of the Framely plugin package.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/icon.py
npm run build
python3 scripts/pack.py
cd dist
sha256sum --check SHA256SUMS
ls -l
