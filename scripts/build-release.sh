#!/usr/bin/env bash
# Build a local LightGravity Bot prebuilt release archive (LG-092).
#
# The archive contains the runtime source, locked Python dependency metadata,
# the frontend built from this commit, the installer, installation docs and
# third-party notices. It does not contain Node/npm, node_modules, .venv,
# runtime data, probes/QA evidence, Git metadata, environment files or secrets.
#
# Target installation of the archive only needs bash and uv (plus network access
# for uv's managed Python/dependency downloads); Node.js and npm are not used.
#
# Usage:
#   bash scripts/build-release.sh [OUTPUT_DIR]
#
# The default output directory is <repo>/dist/release. The build never mutates
# the checked-out worktree's frontend/dist or node_modules.

set -Eeuo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUTDIR="${1:-$REPO_ROOT/dist/release}"

if [[ $# -gt 1 ]]; then
    printf 'usage: %s [OUTPUT_DIR]\n' "$0" >&2
    exit 2
fi

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

for command in git node npm uv tar sha256sum; do
    command -v "$command" >/dev/null 2>&1 || die "$command is required to build the release archive"
done

[[ -f "$REPO_ROOT/pyproject.toml" && -f "$REPO_ROOT/uv.lock" ]] \
    || die "run this command from the LightGravity Bot repository"
[[ -f "$REPO_ROOT/install.sh" ]] || die "install.sh is missing from the repository root"
[[ -f "$REPO_ROOT/docs/install.md" ]] || die "docs/install.md is missing"
[[ -f "$REPO_ROOT/THIRD-PARTY-NOTICES.md" ]] || die "THIRD-PARTY-NOTICES.md is missing"

NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
NPM_MAJOR="$(npm --version | cut -d. -f1)"
[[ "$NODE_MAJOR" == "22" ]] || die "Node.js 22 is required; found $(node --version)"
[[ "$NPM_MAJOR" == "10" ]] || die "npm 10 is required; found $(npm --version)"

# Allowlist of distribution files. Developer evidence, reports, tests and PM
# documents are intentionally not included.
DIST_PATHS=(
    install.sh
    backend/lightgravity
    pyproject.toml
    uv.lock
    .python-version
    .env.example
    Makefile
    docs/install.md
    THIRD-PARTY-NOTICES.md
    frontend/src
    frontend/index.html
    frontend/tsconfig.json
    frontend/vite.config.ts
    frontend/package.json
    frontend/package-lock.json
)

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- "${DIST_PATHS[@]}")" ]]; then
    printf 'error: distribution files have uncommitted changes; commit them before packing\n' >&2
    git -C "$REPO_ROOT" status --short -- "${DIST_PATHS[@]}" >&2
    exit 3
fi

COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
TREE="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')"
SHORT="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="lightgravity-bot-${SHORT}-${STAMP}"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/lightgravity-release.XXXXXX")"
cleanup() { rm -rf -- "$TMP"; }
trap cleanup EXIT
STAGE="$TMP/$NAME"
mkdir -p "$STAGE"

info "Packing committed source files from $COMMIT"
git -C "$REPO_ROOT" archive --format=tar HEAD -- "${DIST_PATHS[@]}" | tar -C "$STAGE" -xf -

# pyproject.toml references README.md (required by hatchling). The root README
# is PM-owned and may be newer than this candidate, so ship a distribution
# quickstart generated from the installation guide instead of a stale copy.
cp -- "$STAGE/docs/install.md" "$STAGE/README.md"

info "Building the frontend from the packed source"
(
    cd "$STAGE/frontend"
    npm ci --no-audit --no-fund
    npm run build
)
[[ -f "$STAGE/frontend/dist/index.html" ]] || die "frontend build did not produce dist/index.html"

info "Collecting licenses for the production frontend packages bundled in dist"
mkdir -p "$STAGE/licenses/frontend"
npm ls --prefix "$STAGE/frontend" --omit=dev --all --parseable --silent >"$TMP/prod-deps.txt" || true
FRONTEND_ROOT="$STAGE/frontend"
while IFS= read -r package_dir; do
    [[ -n "$package_dir" ]] || continue
    [[ "$package_dir" == "$FRONTEND_ROOT" ]] && continue
    relative="${package_dir#"$FRONTEND_ROOT/node_modules/"}"
    [[ "$relative" != "$package_dir" ]] || continue
    destination="$STAGE/licenses/frontend/$relative"
    while IFS= read -r -d '' license_file; do
        mkdir -p "$destination"
        cp -- "$license_file" "$destination/"
    done < <(find "$package_dir" -maxdepth 1 -type f \
        \( -iname 'LICENSE*' -o -iname 'NOTICE*' -o -iname 'COPYING*' \) -print0)
done <"$TMP/prod-deps.txt"
if ! find "$STAGE/licenses/frontend" -type f -print -quit | grep -q .; then
    die "no production frontend license files were collected"
fi

# Node/npm are build tools only; never distribute dependency bodies or caches.
rm -rf "$STAGE/frontend/node_modules" "$STAGE/frontend/.vite"
find "$STAGE/frontend" -maxdepth 1 -name '*.tsbuildinfo' -delete 2>/dev/null || true
rm -rf "$STAGE/frontend/dist/.vite"

cat >"$STAGE/RELEASE-INFO" <<EOF
release_format=lightgravity.prebuilt/v1
source_commit=$COMMIT
source_tree=$TREE
built_at=$STAMP
built_with_node=$(node --version)
built_with_npm=$(npm --version)
built_with_uv=$(uv --version | awk '{print $2}')
python_requires=>=3.12,<3.13
installer=install.sh
frontend=prebuilt
note=Python dependencies are not included; uv downloads the locked packages.
note=This archive is not an offline installer.
EOF

# Static distribution checks: reject forbidden files, host absolute paths and
# obvious credential material even though the allowlist should already prevent
# them.
FORBIDDEN_PATTERNS=(
    '(^|/)\.env$'
    '(^|/)\.env\.[^/]+$'
    '(^|/)[^/]*\.(pem|key|p12|pfx)$'
    '(^|/)credentials\.json$'
    '(^|/)secrets\.json$'
    '(^|/)secrets/'
    '(^|/)bot-data/'
    '\.(db|sqlite|sqlite3|log|pyc)$'
    '(^|/)node_modules/'
    '(^|/)\.venv/'
    '(^|/)__pycache__/'
    '(^|/)\.pytest_cache/'
    '(^|/)\.mypy_cache/'
    '(^|/)\.git/'
    '(^|/)probes/'
    '(^|/)qa/'
    '(^|/)tests/'
    '(^|/)backlog/'
    '(^|/)PROGRESS\.md$'
    '(^|/)PROJECT\.md$'
    '(^|/)agent\.md$'
    '(^|/)BACKLOG\.md$'
)
while IFS= read -r relative; do
    case "$relative" in
        ./.env.example) continue ;;
    esac
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        if printf '%s\n' "$relative" | grep -Eq "$pattern"; then
            die "forbidden distribution file: $relative (matched $pattern)"
        fi
    done
done < <(cd "$STAGE" && find . -type f -printf '%p\n')

if grep -rIlF -- "$HOME/" "$STAGE" >/dev/null 2>&1; then
    grep -rIlF -- "$HOME/" "$STAGE" >&2 || true
    die "build-user home path found in release staging"
fi
if grep -rIlE -- 'sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' "$STAGE" >/dev/null 2>&1; then
    grep -rIlE -- 'sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' "$STAGE" >&2 || true
    die "possible embedded secret found in release staging"
fi

(
    cd "$STAGE"
    find . -type f -print0 | sort -z | xargs -0 sha256sum
) >"$TMP/MANIFEST.sha256"
mv "$TMP/MANIFEST.sha256" "$STAGE/MANIFEST.sha256"

mkdir -p "$OUTDIR"
TARBALL="$OUTDIR/$NAME.tar.gz"
tar -czf "$TARBALL" -C "$TMP" "$NAME"
cp "$STAGE/MANIFEST.sha256" "$OUTDIR/$NAME.MANIFEST.sha256"
(
    cd "$OUTDIR"
    sha256sum "$(basename "$TARBALL")" >"$NAME.tar.gz.sha256"
)

info "Release archive: $TARBALL"
info "Manifest:        $OUTDIR/$NAME.MANIFEST.sha256"
info "SHA256 file:     $OUTDIR/$NAME.tar.gz.sha256"
info "SHA256:          $(cut -d' ' -f1 "$OUTDIR/$NAME.tar.gz.sha256")"
info "Files:           $(wc -l <"$STAGE/MANIFEST.sha256")"
info "Source commit:   $COMMIT"
if command -v du >/dev/null 2>&1; then
    info "Size:            $(du -h "$TARBALL" | awk '{print $1}')"
fi
