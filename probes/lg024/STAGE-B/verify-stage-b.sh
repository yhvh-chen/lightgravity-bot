#!/usr/bin/env bash
# LG-024 Stage B: strict static verifier for the L0 source package.
#
# Fails (non-zero) if the staged directory or tarball contains any forbidden
# pattern, ANY developer-machine absolute path (/home/yhvh/), obvious secrets,
# SDK session DBs, runtime data, raw logs or dependency/build bodies.
#
# Unlike the Stage A checker there is NO warn path: the L0 package must be
# strictly free of personal absolute paths and secrets.
#
# Usage: bash probes/lg024/STAGE-B/verify-stage-b.sh <dir-or-tarball>
# Exit codes: 0 clean; 2 usage/missing; 1 forbidden content found.
set -euo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" || ! -e "$TARGET" ]]; then
  echo "usage: $0 <dir-or-tarball>" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/lg024-verifyb.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if [[ -d "$TARGET" ]]; then
  ROOT="$TARGET"
else
  tar -xzf "$TARGET" -C "$WORK"
  ROOT="$WORK"
fi

# Forbidden relative-path patterns (ERE).
PATTERNS=(
  '(^|/)\.env$'
  '(^|/)\.env\.[^/]+$'
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
  '(^|/)\.ruff_cache/'
  '\.tsbuildinfo$'
  '(^|/)probes/'
  '(^|/)qa/'
  '(^|/)\.git/'
  '(^|/)\.git$'
  '(^|/)backlog/'
  '(^|/)PROGRESS\.md$'
  '(^|/)agent\.md$'
  '(^|/)BACKLOG\.md$'
  '(^|/)PROJECT\.md$'
  '(^|/)docs/08-interface-contract\.md$'
  '(^|/)docs/contracts/LG-033-preparation\.md$'
)

mapfile -t FILES < <( cd "$ROOT" && find . -type f -printf '%p\n' | sed 's|^\./||' )

fail=0
for f in "${FILES[@]}"; do
  case "$f" in
    */.env.example|.env.example) : ;;  # sanctioned, value-free example
    *)
      for p in "${PATTERNS[@]}"; do
        if printf '%s\n' "$f" | grep -Eq "$p"; then
          echo "FORBIDDEN: $f  (matched: $p)" >&2
          fail=1
        fi
      done
      ;;
  esac

  # Absolute developer-machine path: FAIL anywhere (product code OR docs).
  case "$f" in
    *.txt|*.md|*.py|*.json|*.toml|*.ts|*.tsx|*.js|*.css|*.html|*.yaml|*.yml|*.lock|*.cfg|*.ini|*.map|*.svg|*.sh)
      if grep -qI '/home/yhvh/' "$ROOT/$f" 2>/dev/null; then
        echo "ABSPATH-FAIL: $f  (contains /home/yhvh/)" >&2
        fail=1
      fi
      ;;
  esac

  # Obvious secret-looking assignments (best-effort, avoids false positives).
  case "$f" in
    *.txt|*.md|*.py|*.json|*.toml|*.ts|*.tsx|*.js|*.yaml|*.yml|*.cfg|*.ini|*.sh)
      if grep -nE 'sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' "$ROOT/$f" >/dev/null 2>&1; then
        echo "SECRET-FAIL: $f  (looks like an embedded secret/key)" >&2
        fail=1
      fi
      ;;
  esac
done

if [[ "$fail" -ne 0 ]]; then
  echo "verify-stage-b: FAIL (forbidden content present)" >&2
  exit 1
fi

echo "verify-stage-b: OK (${#FILES[@]} files, strictly clean: no abs paths, secrets, deps, DBs, dev docs)"
