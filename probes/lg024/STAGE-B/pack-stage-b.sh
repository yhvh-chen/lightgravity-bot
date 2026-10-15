#!/usr/bin/env bash
# LG-024 Stage B: local L0 source packer (private local review; NOT a release).
#
# Produces a portable L0 source archive from an explicit whitelist at a pinned
# commit, overlays the portable README / NOTICE and an optional prebuilt frontend
# dist, writes a per-file MANIFEST.sha256, and never mutates the worktree,
# never runs git clean/reset, never pushes/uploads/deploys, and never includes
# secrets, runtime data, SDK session DBs, raw logs, dependency bodies or
# developer-machine absolute paths.
#
# Usage:
#   bash probes/lg024/STAGE-B/pack-stage-b.sh <outdir> [ref]
#     <outdir>  destination directory (created if missing)
#     [ref]     git ref providing the product tree (default: e0a8cec)
#
# Exit codes: 0 ok; 2 usage; 3 dirty product tree refused; 4 empty archive.
set -euo pipefail

OUTDIR="${1:-}"
REF="${2:-e0a8cec}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [[ -z "$OUTDIR" ]]; then
  echo "usage: $0 <outdir> [ref]" >&2
  exit 2
fi

# Refuse if the product tree has uncommitted changes.
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

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/lg024-stageb.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
DEST="$STAGE/$NAME"
mkdir -p "$DEST"

# --- L0 whitelist: runtime source + user docs + lockfiles.  No dev/PM evidence,
#     no dependency bodies, no dist in this list (dist is overlaid below). -----
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
  design.md
  AGENTS.md
  docs/01-design.md
  docs/02-task-and-sdk-resources.md
  docs/03-sdk-capability-audit.md
  docs/04-bot-behavior.md
  docs/05-navigation-and-team.md
  docs/06-roadmap.md
  docs/07-settings-and-models.md
  docs/09-source-intake-and-retrieval.md
  docs/contracts/LG-028-preparation.md
)

git archive "$COMMIT" -- "${PATHS[@]}" | tar -x -C "$DEST"

# --- Overlay portable README / NOTICE (authored in Stage B). -------------------
cp "$HERE/PORTABLE-README.md" "$DEST/README.md"
cp "$HERE/NOTICE.md" "$DEST/NOTICE.md"

# --- Optional prebuilt frontend dist (built from the same source tree). --------
# Only include if present and committed-source-consistent; the build is done by
# the caller (npm ci --offline && npm run build) against this same commit.
DIST_SRC="$REPO_ROOT/frontend/dist"
DIST_NOTE="not-included"
if [[ -d "$DIST_SRC" ]]; then
  mkdir -p "$DEST/frontend/dist"
  cp -a "$DIST_SRC/." "$DEST/frontend/dist/"
  DIST_NOTE="included (prebuilt static assets)"
fi

# --- Anchors header for human review. -----------------------------------------
{
  echo "# LG-024 L0 source package (private local review; NOT a release)"
  echo "source_commit: $COMMIT"
  echo "source_tree:   $TREE"
  echo "packed_at:     $STAMP"
  echo "packer:        probes/lg024/STAGE-B/pack-stage-b.sh"
  echo "manifest:      MANIFEST.sha256 (per-file sha256, sorted)"
  echo "readme:        README.md (portable first-version guide, from PORTABLE-README.md)"
  echo "notice:        NOTICE.md (third-party licenses and source versions)"
  echo "frontend_dist: $DIST_NOTE"
  echo "license:       project has NO LICENSE/NOTICE; public license undecided; not granted"
  echo "excludes:      PROGRESS.md agent.md BACKLOG.md backlog/ PROJECT.md docs/08 docs/contracts/LG-033-preparation.md"
  echo "excludes:      .env/credentials/secrets/bot-data/**/*.db/**/*.log/probes/qa/.venv/node_modules/.git"
} > "$DEST/PACK-ANCHORS.txt"

# --- Per-file sha256 manifest (sorted, deterministic). ------------------------
( cd "$DEST" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$DEST/MANIFEST.sha256"

mkdir -p "$OUTDIR"
TARBALL="$OUTDIR/$NAME.tar.gz"
tar -czf "$TARBALL" -C "$STAGE" "$NAME"

cp "$DEST/MANIFEST.sha256" "$OUTDIR/$NAME.MANIFEST.sha256"
cp "$DEST/PACK-ANCHORS.txt" "$OUTDIR/$NAME.PACK-ANCHORS.txt"

if [[ ! -s "$TARBALL" ]]; then
  echo "error: empty archive" >&2
  exit 4
fi

echo "packed:   $TARBALL"
echo "manifest: $OUTDIR/$NAME.MANIFEST.sha256"
echo "anchors:  $OUTDIR/$NAME.PACK-ANCHORS.txt"
echo "files:    $(wc -l < "$DEST/MANIFEST.sha256")"
echo "sha256(tarball): $(sha256sum "$TARBALL" | awk '{print $1}')"
