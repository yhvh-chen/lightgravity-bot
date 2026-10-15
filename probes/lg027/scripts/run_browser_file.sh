#!/usr/bin/env bash
# LG-027 real-browser rendering QA driver.
#
# This sandbox blocks Chrome's HTTP(S) navigation and in-page fetch (the request
# never reaches the server — see probes/lg027/reports/lg027-qa-report.md). It
# does allow file:// pages, so we inline the freshly built frontend/dist into a
# single HTML file and drive the *real production bundle* with the system
# Chrome over CDP.
#
# Backend-integrated Settings behaviour (CRUD -> layered test -> default -> new
# Task execution) is covered separately by lg027_settings_path.py against the
# real CLI server over real HTTP. This driver only claims rendering evidence.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="${LG027_OUT:-/tmp/lg027-browser-file}"
INLINE="${LG027_INLINE:-/tmp/lg027-inline.html}"
TASK_REF="${LG027_FIXTURE_TASK:-task_lg027_fixture}"

mkdir -p "$OUT"
cd "$REPO/frontend"

if [ ! -d dist/assets ]; then
  echo "frontend/dist missing — run: (cd frontend && npm run build)" >&2
  exit 1
fi

INLINE_OUT="$INLINE" node tests/browser/inline-build.mjs >/dev/null

LG027_FILE_URL="file://$INLINE" LG027_OUT="$OUT" LG027_FIXTURE_TASK="$TASK_REF" \
  node "$REPO/probes/lg027/scripts/lg027_browser_file.mjs"

echo "results=$OUT/lg027-browser-file-results.json"
