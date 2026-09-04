#!/usr/bin/env bash
# Release TKSfw: bump VERSION, run tests, rebuild plugins/tksfw + dist/, commit and tag.
#   ./tools/release.sh 0.2.0
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
NEW="${1:-}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$ ]] || { echo "usage: $0 <semver>"; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "working tree not clean"; exit 1; }
grep -q "^## \[$NEW\]" CHANGELOG.md || { echo "CHANGELOG.md has no '## [$NEW]' section"; exit 1; }
echo "$NEW" > VERSION
python3 tools/build_plugin.py            # regenerate plugins/tksfw + dist/ with the new version
python3 tests/run_tests.py               # includes build_plugin.py --check
git add VERSION CHANGELOG.md plugins/
git commit -m "release: v$NEW"
git tag -a "v$NEW" -m "TKSfw v$NEW"
echo "tagged v$NEW — artifacts in dist/ (git-ignored):"; ls -1 dist/
