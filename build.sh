#!/usr/bin/env bash
# Build the installable zip. Works as a Blender 4.2+ extension and as a legacy
# add-on on 3.6-4.1, because the folder carries both bl_info and a manifest.
set -euo pipefail

VERSION=$(grep -m1 '^version = ' retopo_kit/blender_manifest.toml | cut -d'"' -f2)
OUT="dist/retopo_kit-${VERSION}.zip"

rm -rf dist && mkdir -p dist
find retopo_kit -name '__pycache__' -type d -exec rm -rf {} +
zip -r "$OUT" retopo_kit -x '*.DS_Store' >/dev/null

echo "Built $OUT"
