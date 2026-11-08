#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
#
# Install the exact wheel in a directory into a clean environment and run it end
# to end. CI and the release workflow both run this on the files they publish.
#
# Usage: scripts/smoke_test.sh <dist-directory>

set -euo pipefail

dist="${1:?dist directory required}"
shopt -s nullglob
wheels=("$dist"/*.whl)
[[ ${#wheels[@]} -eq 1 ]] || { echo "expected exactly one wheel in $dist" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

uv venv --quiet "$work/venv"
uv pip install --quiet --python "$work/venv" --no-deps "${wheels[0]}"
if [[ -x "$work/venv/bin/pakad" ]]; then pakad="$work/venv/bin/pakad"; else pakad="$work/venv/Scripts/pakad"; fi

"$pakad" --version
"$pakad" schema > "$work/schema.json"
"$pakad" schema manifest > "$work/manifest-schema.json"
"$pakad" example "$work/demo" > /dev/null
status=0
"$pakad" reconcile -p "$work/demo/profile.toml" -e "$work/demo/expected.csv" \
  -c "$work/demo/collected.csv" -o "$work/demo/report" --as-of 2026-11-07T12:00:00Z \
  > /dev/null || status=$?
[[ "$status" -eq 1 ]] || { echo "expected exit code 1 (findings), got $status" >&2; exit 1; }
for name in pakad-report.html pakad-report.json pakad-findings.csv pakad-report.md pakad-manifest.json; do
  [[ -s "$work/demo/report/$name" ]] || { echo "missing $name" >&2; exit 1; }
done
echo "smoke test passed: ${wheels[0]}"
