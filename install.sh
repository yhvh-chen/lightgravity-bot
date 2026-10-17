#!/usr/bin/env bash
# LightGravity Bot local installer (LG-092).
#
# Installs the application runtime into a stable local directory, creates an
# isolated Python environment from the locked dependencies, and writes a
# launcher whose data/workspace/secret locations live outside the application
# directory.  It never starts the service, never enables LAN access, and never
# prints or stores a credential value.
#
# Typical use from a source checkout or an extracted prebuilt archive:
#   bash install.sh
#
# See docs/install.md for requirements, options and the next steps.

set -Eeuo pipefail

SCRIPT_NAME="install.sh"
SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: bash install.sh [options]

Install LightGravity Bot locally. The installer does not start the service.

Options:
  --install-dir DIR      application/runtime directory
                         (default: ~/.local/opt/lightgravity-bot)
  --data-dir DIR         runtime data root, outside the application directory
                         (default: ~/.local/share/lightgravity-bot)
  --workspace-root DIR   authorized task workspace root
                         (default: <data-dir>/workspaces)
  --secret-store DIR     credential store, outside data/workspace/application
                         (default: ~/.config/lightgravity-bot/secrets)
  --host HOST            default bind host (default: 127.0.0.1)
  --port PORT            default bind port (default: 8000)
  --team                 explicitly enable team mode in the launcher config
  --no-team              keep team mode disabled (default)
  -h, --help             show this help

The default configuration file is:
  ${XDG_CONFIG_HOME:-$HOME/.config}/lightgravity-bot/install.conf

Re-running the installer updates the application but preserves existing data,
workspaces, secrets, accounts and settings.

Requirements:
  - Linux with bash
  - uv >= 0.12 on PATH
  - For a source checkout without a prebuilt frontend: Node.js 22 and npm 10
  - Network access for uv to download CPython 3.12 and locked Python packages

This is not an offline installer. A prebuilt release archive already contains
the built frontend, so its target machine does not need Node.js or npm.
EOF
}

# ---------------------------------------------------------------------------
# Configuration helpers (read a simple KEY=value file without shell eval).
# ---------------------------------------------------------------------------
if [[ -z "${HOME:-}" ]]; then
    die "HOME is not set; cannot choose default local directories"
fi

CONFIG_FILE="${LIGHTGRAVITY_INSTALL_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/lightgravity-bot/install.conf}"
CONFIG_FILE="$(realpath -m -- "$CONFIG_FILE")"

config_value() {
    local wanted="$1" line key value
    [[ -f "$CONFIG_FILE" ]] || return 1
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        if [[ "$key" == "$wanted" ]]; then
            printf '%s' "$value"
            return 0
        fi
    done <"$CONFIG_FILE"
    return 1
}

config_or() {
    local value
    if value="$(config_value "$1")"; then
        printf '%s' "$value"
    else
        printf '%s' "$2"
    fi
}

DEFAULT_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DEFAULT_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$(config_or INSTALL_DIR "$HOME/.local/opt/lightgravity-bot")"
DATA_DIR="$(config_or DATA_DIR "$DEFAULT_DATA_HOME/lightgravity-bot")"
WORKSPACE_ROOT="$(config_or WORKSPACE_ROOT "$DATA_DIR/workspaces")"
SECRET_STORE="$(config_or SECRET_STORE "$DEFAULT_CONFIG_HOME/lightgravity-bot/secrets")"
HOST="$(config_or HOST "127.0.0.1")"
PORT="$(config_or PORT "8000")"
TEAM_MODE="$(config_or TEAM_MODE "0")"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --install-dir)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --data-dir)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            DATA_DIR="$2"
            shift 2
            ;;
        --workspace-root)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            WORKSPACE_ROOT="$2"
            shift 2
            ;;
        --secret-store)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            SECRET_STORE="$2"
            shift 2
            ;;
        --host)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            HOST="$2"
            shift 2
            ;;
        --port)
            [[ $# -ge 2 ]] || die "$1 requires a value"
            PORT="$2"
            shift 2
            ;;
        --team)
            TEAM_MODE=1
            shift
            ;;
        --no-team)
            TEAM_MODE=0
            shift
            ;;
        --)
            shift
            [[ $# -eq 0 ]] || die "unexpected positional arguments: $*"
            ;;
        -*)
            die "unknown option: $1 (use --help)"
            ;;
        *)
            die "unexpected positional argument: $1 (use --help)"
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Validation (before any target directory is changed).
# ---------------------------------------------------------------------------
validate_value() {
    local label="$1" value="$2"
    [[ -n "$value" ]] || die "$label must not be empty"
    [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] \
        || die "$label must not contain a newline"
    [[ "$value" != *$'\t'* ]] || die "$label must not contain a tab"
}

validate_value "install directory" "$INSTALL_DIR"
validate_value "data directory" "$DATA_DIR"
validate_value "workspace root" "$WORKSPACE_ROOT"
validate_value "secret store" "$SECRET_STORE"
validate_value "host" "$HOST"
validate_value "port" "$PORT"
validate_value "launcher config path" "$CONFIG_FILE"

INSTALL_DIR="$(realpath -m -- "$INSTALL_DIR")"
DATA_DIR="$(realpath -m -- "$DATA_DIR")"
WORKSPACE_ROOT="$(realpath -m -- "$WORKSPACE_ROOT")"
SECRET_STORE="$(realpath -m -- "$SECRET_STORE")"

[[ "$PORT" =~ ^[0-9]+$ ]] || die "port must be an integer, got: $PORT"
((PORT >= 1 && PORT <= 65535)) || die "port must be between 1 and 65535"
[[ "$HOST" != *[[:space:]]* && "$HOST" != */* ]] || die "host contains unsupported characters: $HOST"
[[ "$TEAM_MODE" == "0" || "$TEAM_MODE" == "1" ]] || die "TEAM_MODE in the config must be 0 or 1"

path_within() {
    local child="$1" parent="$2"
    [[ "$child" == "$parent" || "$child" == "$parent"/* ]]
}

case "$INSTALL_DIR" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/proc|/root|/sbin|/sys|/usr|/var|"$HOME")
        die "refusing unsafe install directory: $INSTALL_DIR"
        ;;
esac
if [[ -L "$INSTALL_DIR" ]]; then
    die "refusing symlink install directory: $INSTALL_DIR"
fi
if path_within "$INSTALL_DIR" "$SOURCE_DIR" || path_within "$SOURCE_DIR" "$INSTALL_DIR"; then
    die "install directory must not overlap the source tree: $INSTALL_DIR"
fi
if path_within "$DATA_DIR" "$INSTALL_DIR" || path_within "$INSTALL_DIR" "$DATA_DIR"; then
    die "data directory must be outside the application directory"
fi
if path_within "$WORKSPACE_ROOT" "$INSTALL_DIR" || path_within "$INSTALL_DIR" "$WORKSPACE_ROOT"; then
    die "workspace root must be outside the application directory"
fi
if path_within "$SECRET_STORE" "$INSTALL_DIR" || path_within "$INSTALL_DIR" "$SECRET_STORE"; then
    die "secret store must be outside the application directory"
fi
if path_within "$SECRET_STORE" "$DATA_DIR" || path_within "$DATA_DIR" "$SECRET_STORE"; then
    die "secret store and data directory must be separate"
fi
if path_within "$SECRET_STORE" "$WORKSPACE_ROOT" || path_within "$WORKSPACE_ROOT" "$SECRET_STORE"; then
    die "secret store and workspace root must be separate"
fi
if path_within "$DATA_DIR" "$SOURCE_DIR" || path_within "$SECRET_STORE" "$SOURCE_DIR" \
    || path_within "$WORKSPACE_ROOT" "$SOURCE_DIR"; then
    die "data, workspace and secret directories must be outside the source tree"
fi
if path_within "$CONFIG_FILE" "$INSTALL_DIR" || path_within "$INSTALL_DIR" "$CONFIG_FILE"; then
    die "launcher config must not overlap the application directory"
fi
if path_within "$CONFIG_FILE" "$SOURCE_DIR"; then
    die "launcher config must not be inside the source tree"
fi

[[ -f "$SOURCE_DIR/pyproject.toml" ]] || die "pyproject.toml not found; run this installer from the repository or extracted release"
[[ -f "$SOURCE_DIR/uv.lock" ]] || die "uv.lock not found; run this installer from the repository or extracted release"
[[ -d "$SOURCE_DIR/backend/lightgravity" ]] || die "backend/lightgravity not found; incomplete source/release"
[[ -f "$SOURCE_DIR/install.sh" ]] || die "install.sh not found in the source/release tree"

# ---------------------------------------------------------------------------
# Existing install/update safety and prerequisite checks.
# ---------------------------------------------------------------------------
if [[ -e "$INSTALL_DIR" && ! -d "$INSTALL_DIR" ]]; then
    die "install path exists and is not a directory: $INSTALL_DIR"
fi
if [[ -d "$INSTALL_DIR" ]] && [[ -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    [[ -f "$INSTALL_DIR/.lightgravity-install" ]] \
        || die "refusing to overwrite a non-LightGravity directory: $INSTALL_DIR"
fi

PID_RECORD="$DATA_DIR/runtime/lightgravity.json"
if [[ -f "$PID_RECORD" ]]; then
    RUNNING_PID="$(grep -o '"pid"[[:space:]]*:[[:space:]]*[0-9][0-9]*' "$PID_RECORD" \
        | head -n 1 | grep -o '[0-9][0-9]*$' || true)"
    if [[ -n "$RUNNING_PID" ]] && kill -0 "$RUNNING_PID" 2>/dev/null; then
        die "a LightGravity service appears to be running (pid $RUNNING_PID); stop it before reinstalling"
    fi
fi

command -v uv >/dev/null 2>&1 || {
    cat >&2 <<'EOF'
error: uv is required but was not found on PATH.

Install uv 0.12 or newer using your operating-system package manager, or see
the official installation guide at:
  https://docs.astral.sh/uv/getting-started/installation/

This installer deliberately does not download or execute a third-party
installer script. Re-run install.sh after uv is available on PATH.
EOF
    exit 1
}

UV_VERSION="$(uv --version 2>/dev/null | awk '{print $2}')"
if [[ "$UV_VERSION" =~ ^([0-9]+)\.([0-9]+) ]]; then
    UV_MAJOR="${BASH_REMATCH[1]}"
    UV_MINOR="${BASH_REMATCH[2]}"
    if ((UV_MAJOR == 0 && UV_MINOR < 12)); then
        die "uv >= 0.12 is required; found $UV_VERSION"
    fi
else
    warn "could not parse uv version '$UV_VERSION'; continuing"
fi

PREBUILT_FRONTEND=0
if [[ -f "$SOURCE_DIR/frontend/dist/index.html" ]]; then
    PREBUILT_FRONTEND=1
    info "Using the prebuilt frontend from $SOURCE_DIR/frontend/dist"
else
    [[ -f "$SOURCE_DIR/frontend/package.json" && -f "$SOURCE_DIR/frontend/package-lock.json" ]] \
        || die "frontend source or package lock is missing; cannot build the frontend"
    command -v node >/dev/null 2>&1 || {
        cat >&2 <<'EOF'
error: no prebuilt frontend is present and Node.js was not found on PATH.

Use a prebuilt release archive (its frontend is already built and does not need
Node.js), or install Node.js 22 LTS and npm 10 to build from source.
EOF
        exit 1
    }
    command -v npm >/dev/null 2>&1 || {
        cat >&2 <<'EOF'
error: no prebuilt frontend is present and npm was not found on PATH.

Use a prebuilt release archive, or install Node.js 22 LTS and npm 10 to build
from source.
EOF
        exit 1
    }
    NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
    NPM_MAJOR="$(npm --version | cut -d. -f1)"
    [[ "$NODE_MAJOR" == "22" ]] || die "Node.js 22 is required to build the frontend; found $(node --version)"
    [[ "$NPM_MAJOR" == "10" ]] || die "npm 10 is required to build the frontend; found $(npm --version)"
fi

if [[ "$TEAM_MODE" == "1" ]]; then
    info "Team mode is explicitly enabled in the launcher configuration."
else
    info "Team mode remains disabled (single-user default)."
fi
case "$HOST" in
    127.0.0.1|localhost|::1)
        ;;
    *)
        warn "non-loopback host '$HOST' selected. The installer does not start the service or open access; use team mode/authentication deliberately."
        ;;
esac
if [[ -d "$DATA_DIR" || -d "$SECRET_STORE" ]]; then
    info "Existing data/secrets directories will be reused and left in place."
fi

# ---------------------------------------------------------------------------
# Stage the application, build the frontend if needed, install locked Python
# dependencies, and generate the launcher. Nothing is started.
# ---------------------------------------------------------------------------
mkdir -p "$(dirname -- "$INSTALL_DIR")"
STAGE="$(mktemp -d "$(dirname -- "$INSTALL_DIR")/.lightgravity-install.XXXXXX")"
cleanup() {
    if [[ -n "${STAGE:-}" && -d "$STAGE" ]]; then
        rm -rf -- "$STAGE"
    fi
}
trap cleanup EXIT

COPY_PATHS=(
    install.sh
    README.md
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
# frontend/README.md is retained in full source checkouts but is not required for
# a release archive; the installer must work with the distribution allowlist.
if [[ -f "$SOURCE_DIR/frontend/README.md" ]]; then
    COPY_PATHS+=(frontend/README.md)
fi
if [[ -f "$SOURCE_DIR/RELEASE-INFO" ]]; then
    COPY_PATHS+=(RELEASE-INFO)
fi
if [[ -f "$SOURCE_DIR/scripts/build-release.sh" ]]; then
    COPY_PATHS+=(scripts/build-release.sh)
fi
if [[ -d "$SOURCE_DIR/frontend/dist" ]]; then
    COPY_PATHS+=(frontend/dist)
fi

info "Staging application files in $STAGE"
tar -C "$SOURCE_DIR" -cf - \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
    -- "${COPY_PATHS[@]}" | tar -C "$STAGE" -xf -

# Hatchling requires the README referenced by pyproject.toml. An extracted
# archive has its own quickstart README; a stripped source tree falls back to
# the installation guide rather than failing metadata validation.
if [[ ! -f "$STAGE/README.md" ]]; then
    cp -- "$STAGE/docs/install.md" "$STAGE/README.md"
fi

if [[ ! -f "$STAGE/frontend/dist/index.html" ]]; then
    info "Building the frontend with Node.js $(node --version) / npm $(npm --version)"
    (
        cd "$STAGE/frontend"
        npm ci --no-audit --no-fund
        npm run build
    )
fi
[[ -f "$STAGE/frontend/dist/index.html" ]] || die "frontend build did not produce frontend/dist/index.html"
rm -rf "$STAGE/frontend/node_modules" "$STAGE/frontend/.vite"
find "$STAGE/frontend" -maxdepth 1 -name '*.tsbuildinfo' -delete 2>/dev/null || true

info "uv will now obtain managed CPython 3.12 if needed and install the locked Python dependencies."
info "This installer is not offline: Python packages may be downloaded from the configured index."
(
    cd "$STAGE"
    UV_PYTHON_DOWNLOADS=automatic uv sync --frozen --no-dev --python 3.12 --no-progress
)
[[ -x "$STAGE/.venv/bin/python" ]] || die "uv sync did not create .venv/bin/python"
PYTHONPATH="$STAGE/backend" "$STAGE/.venv/bin/python" -c 'import lightgravity, fastapi, uvicorn' \
    || die "installed Python environment cannot import the runtime"

# ---------------------------------------------------------------------------
# Generate the stable launcher. It embeds no secret values; every path is read
# from the external config file (with safe install-time defaults).
# ---------------------------------------------------------------------------
LAUNCHER="$STAGE/bin/lightgravity"
mkdir -p "$STAGE/bin"

quote() { printf '%q' "$1"; }
Q_CONFIG="$(quote "$CONFIG_FILE")"
Q_DATA="$(quote "$DATA_DIR")"
Q_WORKSPACE="$(quote "$WORKSPACE_ROOT")"
Q_SECRET="$(quote "$SECRET_STORE")"
Q_HOST="$(quote "$HOST")"
Q_PORT="$(quote "$PORT")"
Q_TEAM="$(quote "$TEAM_MODE")"

cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Generated by LightGravity Bot install.sh. Safe to keep; do not put secrets here.
set -euo pipefail
APP_ROOT="\$(CDPATH= cd -- "\$(dirname -- "\${BASH_SOURCE[0]}")/.." && pwd -P)"
CONFIG_FILE=$Q_CONFIG
DEFAULT_DATA_DIR=$Q_DATA
DEFAULT_WORKSPACE_ROOT=$Q_WORKSPACE
DEFAULT_SECRET_STORE=$Q_SECRET
DEFAULT_HOST=$Q_HOST
DEFAULT_PORT=$Q_PORT
DEFAULT_TEAM_MODE=$Q_TEAM

config_value() {
    local wanted="\$1" line key value
    [[ -f "\$CONFIG_FILE" ]] || return 1
    while IFS= read -r line || [[ -n "\$line" ]]; do
        [[ -z "\$line" || "\$line" == \#* ]] && continue
        key="\${line%%=*}"
        value="\${line#*=}"
        if [[ "\$key" == "\$wanted" ]]; then
            printf '%s' "\$value"
            return 0
        fi
    done <"\$CONFIG_FILE"
    return 1
}

set_default_env() {
    local name="\$1" key="\$2" fallback="\$3" value
    case "\$name" in
        LIGHTGRAVITY_DATA_DIR) [[ -n "\${LIGHTGRAVITY_DATA_DIR+x}" ]] && return 0 ;;
        LIGHTGRAVITY_WORKSPACE_ROOT) [[ -n "\${LIGHTGRAVITY_WORKSPACE_ROOT+x}" ]] && return 0 ;;
        LIGHTGRAVITY_SECRET_STORE) [[ -n "\${LIGHTGRAVITY_SECRET_STORE+x}" ]] && return 0 ;;
        LIGHTGRAVITY_HOST) [[ -n "\${LIGHTGRAVITY_HOST+x}" ]] && return 0 ;;
        LIGHTGRAVITY_PORT) [[ -n "\${LIGHTGRAVITY_PORT+x}" ]] && return 0 ;;
        LIGHTGRAVITY_TEAM_MODE) [[ -n "\${LIGHTGRAVITY_TEAM_MODE+x}" ]] && return 0 ;;
    esac
    if value="\$(config_value "\$key")"; then
        export "\$name=\$value"
    else
        export "\$name=\$fallback"
    fi
}

set_default_env LIGHTGRAVITY_DATA_DIR DATA_DIR "\$DEFAULT_DATA_DIR"
set_default_env LIGHTGRAVITY_WORKSPACE_ROOT WORKSPACE_ROOT "\$DEFAULT_WORKSPACE_ROOT"
set_default_env LIGHTGRAVITY_SECRET_STORE SECRET_STORE "\$DEFAULT_SECRET_STORE"
set_default_env LIGHTGRAVITY_HOST HOST "\$DEFAULT_HOST"
set_default_env LIGHTGRAVITY_PORT PORT "\$DEFAULT_PORT"
set_default_env LIGHTGRAVITY_TEAM_MODE TEAM_MODE "\$DEFAULT_TEAM_MODE"
if [[ -z "\${LIGHTGRAVITY_FRONTEND_DIST+x}" ]]; then
    export LIGHTGRAVITY_FRONTEND_DIST="\$APP_ROOT/frontend/dist"
fi
export PYTHONPATH="\$APP_ROOT/backend\${PYTHONPATH:+:\$PYTHONPATH}"
exec "\$APP_ROOT/.venv/bin/python" -m lightgravity "\$@"
EOF
chmod 755 "$LAUNCHER"

if [[ "$PREBUILT_FRONTEND" == "1" ]]; then
    FRONTEND_KIND="prebuilt"
else
    FRONTEND_KIND="built from source"
fi
SOURCE_COMMIT="unknown"
if [[ -f "$SOURCE_DIR/RELEASE-INFO" ]]; then
    SOURCE_COMMIT="$(sed -n 's/^source_commit=//p' "$SOURCE_DIR/RELEASE-INFO" | head -n 1)"
fi
if [[ -z "$SOURCE_COMMIT" || "$SOURCE_COMMIT" == "unknown" ]] && command -v git >/dev/null 2>&1; then
    if git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        SOURCE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
    fi
fi
[[ -n "$SOURCE_COMMIT" ]] || SOURCE_COMMIT="unknown"

cat >"$STAGE/.lightgravity-install" <<EOF
schema=lightgravity.install/v1
installed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
installer=$SCRIPT_NAME
source_commit=$SOURCE_COMMIT
frontend=$FRONTEND_KIND
data_dir=$DATA_DIR
workspace_root=$WORKSPACE_ROOT
secret_store=$SECRET_STORE
config_file=$CONFIG_FILE
EOF
chmod 644 "$STAGE/.lightgravity-install"

# Persist only non-secret launcher settings. Write atomically.
mkdir -p "$(dirname -- "$CONFIG_FILE")"
CONFIG_TMP="$(mktemp "${CONFIG_FILE}.tmp.XXXXXX")"
cat >"$CONFIG_TMP" <<EOF
# LightGravity Bot local install configuration.
# This file contains paths and flags only. Never place credential values here.
INSTALL_DIR=$INSTALL_DIR
DATA_DIR=$DATA_DIR
WORKSPACE_ROOT=$WORKSPACE_ROOT
SECRET_STORE=$SECRET_STORE
HOST=$HOST
PORT=$PORT
TEAM_MODE=$TEAM_MODE
EOF
chmod 600 "$CONFIG_TMP"

# Create persistent directories outside the application. Existing permissions
# and contents are left untouched.
for directory in "$DATA_DIR" "$WORKSPACE_ROOT" "$SECRET_STORE"; do
    if [[ ! -d "$directory" ]]; then
        mkdir -p "$directory"
        chmod 700 "$directory"
    fi
done

# Swap the staged application into place, keeping a rollback until the move
# succeeds. The data/workspace/secret directories are never inside the swap.
BACKUP=""
if [[ -d "$INSTALL_DIR" && -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    BACKUP="${INSTALL_DIR}.previous.$$"
    mv -- "$INSTALL_DIR" "$BACKUP"
fi
if ! mv -- "$STAGE" "$INSTALL_DIR"; then
    if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
        mv -- "$BACKUP" "$INSTALL_DIR"
    fi
    die "could not move the staged application into $INSTALL_DIR"
fi
STAGE=""
if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
    rm -rf -- "$BACKUP"
fi
mv -- "$CONFIG_TMP" "$CONFIG_FILE"

cat <<EOF

LightGravity Bot installed successfully.

  application: $INSTALL_DIR
  data:        $DATA_DIR
  workspaces:  $WORKSPACE_ROOT
  secrets:     $SECRET_STORE
  config:      $CONFIG_FILE
  frontend:    $FRONTEND_KIND

The installer did not start the service and did not open network access.

Start (foreground):
  "$INSTALL_DIR/bin/lightgravity" start

Optional background start:
  "$INSTALL_DIR/bin/lightgravity" start --daemon

Check or stop:
  "$INSTALL_DIR/bin/lightgravity" status
  "$INSTALL_DIR/bin/lightgravity" stop

Open:
  http://$HOST:$PORT/

Model configuration next steps:
  1. Open Settings -> Models & Providers / Connections.
  2. Create a connection, save the credential through the protected form, and
     test it. The credential value is never printed by this installer.
  3. Set the coordinator, default worker, and independent reviewer connections.
     Delivery acceptance requires an available reviewer.
  4. Configure models before starting real task execution.

Team mode is $([[ "$TEAM_MODE" == "1" ]] && printf 'enabled by this install' || printf 'off (single-user default)').
EOF
if [[ "$TEAM_MODE" != "1" ]]; then
    cat <<EOF
To opt in later, either re-run this installer with --team, or start once with:
  LIGHTGRAVITY_TEAM_MODE=1 "$INSTALL_DIR/bin/lightgravity" start
The first empty team account store creates admin/admin123; change that password
immediately after signing in. This default applies only to the local service.
EOF
fi
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && "$HOST" != "::1" ]]; then
    cat <<EOF

Note: the configured bind host is '$HOST'. Binding a non-loopback interface is
an explicit network-facing choice; use authentication/team mode and a firewall.
The installer itself did not start or expose anything.
EOF
fi

exit 0
