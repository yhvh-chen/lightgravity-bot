#!/usr/bin/env bash
# LG-024 Stage A: local DRAFT source-staging packer (NOT a release).
#
# Produces an L0 source archive from an explicit whitelist at a pinned commit,
# plus a per-file MANIFEST.sha256.  It never mutates the worktree, never runs
# git clean/reset, never pushes/uploads/deploys, and never includes secrets,
# runtime data, SDK session DBs, raw logs or dependency bodies.
#
# Usage:
#   bash probes/lg024/pack-local.sh <outdir> [ref]
#     <outdir>  destination directory (created if missing; must be empty-ish)
#     [ref]     git ref to pack (default: HEAD)
#
# Exit codes: 0 ok; 2 usage; 3 dirty product tree refused; 4 nothing packed.
set -euo pipefail

OUTDIR="${1:-}"
REF="${2:-HEAD}"
if [[ -z "$OUTDIR" ]]; then
  echo "usage: $0 <outdir> [ref]" >&2
  exit 2
fi

# Resolve repo root and verify we are inside a git worktree.
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Refuse if the *product* tree has uncommitted changes: a draft must be a clean,
# reproducible snapshot.  (probes/ drafts may be dirty while Stage A is authored.)
PRODUCT_PATHS=(backend frontend/src frontend/index.html tests pyproject.toml uv.lock)
if [[ -n "$(git status --porcelain -- "${PRODUCT_PATHS[@]}" 2>/dev/null)" ]]; then
  echo "refuse: product tree is dirty; commit before packing" >&2
  exit 3
fi

COMMIT="$(git rev-parse "$REF")"
TREE="$(git rev-parse "$REF^{tree}")"
SHORT="$(git rev-parse --short "$REF")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="lightgravity-bot-L0-${SHORT}-${STAMP}"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/lg024-stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
DEST="$STAGE/$NAME"
mkdir -p "$DEST"

# L0 whitelist: own source + engineering/docs + lockfiles.  No probes/, qa/,
# no dependency bodies, no dist.
PATHS=(
  backend/lightgravity
  frontend/src
  frontend/index.html
  frontend/tsconfig.json
  frontend/vite.config.ts
  frontend/README.md
  tests
  pyproject.toml
  uv.lock
  frontend/package.json
  frontend/package-lock.json
  Makefile
  .python-version
  .env.example
  .gitignore
  README.md
  PROJECT.md
  agent.md
  design.md
  AGENTS.md
  BACKLOG.md
  PROGRESS.md
  docs
  backlog
)

# git archive only emits tracked files under these pathspecs.
git archive "$COMMIT" -- "${PATHS[@]}" | tar -x -C "$DEST"

# Per-file sha256 manifest (sorted, deterministic).
( cd "$DEST" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$DEST/MANIFEST.sha256"

# Anchors header for human review.
{
  echo "# LG-024 L0 draft source staging (NOT a release)"
  echo "source_commit: $COMMIT"
  echo "source_tree:   $TREE"
  echo "packed_at:     $STAMP"
  echo "packer:        probes/lg024/pack-local.sh"
  echo "manifest:      MANIFEST.sha256 (per-file sha256, sorted)"
  echo "excludes:      .env/credentials/secrets/bot-data/**/*.db/**/*.log/probes/qa/.venv/node_modules/dist"
} > "$DEST/PACK-ANCHORS.txt"

mkdir -p "$OUTDIR"
TARBALL="$OUTDIR/$NAME.tar.gz"
tar -czf "$TARBALL" -C "$STAGE" "$NAME"

# Also copy the manifest + anchors next to the tarball for easy review.
cp "$DEST/MANIFEST.sha256" "$OUTDIR/$NAME.MANIFEST.sha256"
cp "$DEST/PACK-ANCHORS.txt" "$OUTDIR/$NAME.PACK-ANCHORS.txt"

if [[ ! -s "$TARBALL" ]]; then
  echo "error: empty archive" >&2
  exit 4
fi

echo "packed: $TARBALL"
echo "manifest: $OUTDIR/$NAME.MANIFEST.sha256"
echo "anchors:  $OUTDIR/$NAME.PACK-ANCHORS.txt"
echo "sha256(tarball): $(sha256sum "$TARBALL" | awk '{print $1}')"
