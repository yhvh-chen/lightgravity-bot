#!/usr/bin/env bash
# LG-024 Stage A: static exclusion checker for a staged distribution directory
# or tarball.  Fails (non-zero) if any forbidden pattern is present.
#
# Usage:
#   bash probes/lg024/verify-dist-exclusion.sh <dir-or-tarball>
#
# Exit codes: 0 clean; 2 usage/missing; 1 forbidden content found.
#
# Semantics:
#  * forbidden PATHS (secrets, runtime data, DBs, raw logs, deps, caches) -> FAIL
#  * /home/yhvh/ inside PRODUCT CODE (backend/, frontend/src/, src/)        -> FAIL
#  * /home/yhvh/ inside docs/evidence (historical command records)          -> WARN
#    (shared docs are owned elsewhere; must not be silently rewritten here)
set -euo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" || ! -e "$TARGET" ]]; then
  echo "usage: $0 <dir-or-tarball>" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/lg024-verify.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if [[ -d "$TARGET" ]]; then
  ROOT="$TARGET"
else
  tar -xzf "$TARGET" -C "$WORK"
  ROOT="$WORK"
fi

REPORT="DIST-EXCLUSION-WARNINGS.txt"
rm -f "$ROOT/$REPORT"

# Forbidden path patterns (ERE over relative paths).
PATTERNS=(
  '(^|/)\.env$'                  # real .env only; .env.example allowed below
  '(^|/)\.env\.[^/]+$'           # .env.local etc (but not .env.example)
  '(^|/)[^/]*\.pem$'
  '(^|/)[^/]*\.key$'
  '(^|/)credentials\.json$'
  '(^|/)secrets\.json$'
  '(^|/)secrets/'
  '(^|/)bot-data/'
  '\.db$'
  '\.sqlite3?$'
  '\.log$'
  '(^|/)node_modules/'
  '(^|/)\.venv/'
  '(^|/)__pycache__/'
  '\.pyc$'
  '(^|/)\.pytest_cache/'
  '(^|/)\.mypy_cache/'
  '(^|/)frontend/dist/'
  '(^|/)raw/'
  '(^|/)probes/'
  '(^|/)qa/'
)

mapfile -t FILES < <( cd "$ROOT" && find . -type f -printf '%p\n' | sed 's|^\./||' )

fail=0
for f in "${FILES[@]}"; do
  rel="${f#"${f%%[!/]*}"}" # no-op; keep $f as-is
  # Allow the explicitly-sanctioned example file (any directory prefix).
  case "$f" in
    */.env.example|.env.example) continue ;;
  esac
  for p in "${PATTERNS[@]}"; do
    if printf '%s\n' "$f" | grep -Eq "$p"; then
      echo "FORBIDDEN: $f  (matched: $p)" >&2
      fail=1
    fi
  done
  # Absolute local paths.
  case "$f" in
    *.txt|*.md|*.py|*.json|*.toml|*.ts|*.tsx|*.yaml|*.yml|*.lock|*.cfg|*.ini)
      if grep -qI '/home/yhvh/' "$ROOT/$f" 2>/dev/null; then
        case "$f" in
          */backend/*|*/frontend/src/*|*/src/*|backend/*|frontend/src/*|src/*)
            echo "ABSPATH-FAIL: $f  (product code contains /home/yhvh/)" >&2
            fail=1
            ;;
          *)
            echo "ABSPATH-WARN: $f  (contains /home/yhvh/; evidence/doc, not a runtime dep)" | tee -a "$ROOT/$REPORT" >&2
            ;;
        esac
      fi
      ;;
  esac
done

if [[ "$fail" -ne 0 ]]; then
  echo "verify-dist-exclusion: FAIL (forbidden content present)" >&2
  exit 1
fi

echo "verify-dist-exclusion: OK (${#FILES[@]} files, no forbidden patterns)"
if [[ -s "$ROOT/$REPORT" ]]; then
  echo "warnings recorded: $ROOT/$REPORT"
fi
