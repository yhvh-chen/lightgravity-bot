# Install LightGravity Bot locally

This guide covers the LG-092 local installation path. It installs a stable
runtime and launcher, keeps user data outside the application directory, and
does not start the service. The regular `start`, `status`, and `stop` commands
described below are the existing LightGravity lifecycle commands.

## Requirements

- Linux with `bash`
- `uv` 0.12 or newer on `PATH`
- Network access for `uv` to download a managed CPython 3.12 runtime if needed
  and the Python packages fixed by `uv.lock`
- For a source checkout without a built `frontend/dist`: Node.js 22 LTS and
  npm 10. A prebuilt release archive does not need Node.js or npm.

`uv` may show that it is downloading CPython and Python packages. This is not an
offline installer: only the frontend is prebuilt in the release archive, and the
Python runtime/dependencies are still obtained by `uv`.

If `uv` is missing, install it with your operating-system package manager or
follow <https://docs.astral.sh/uv/getting-started/installation/>. The LightGravity
installer does not download or execute a third-party installer script.

## Install from a prebuilt release archive

```bash
tar -xzf lightgravity-bot-<commit>-<timestamp>.tar.gz
cd lightgravity-bot-<commit>-<timestamp>
bash install.sh
```

The archive already contains the built frontend. Node.js and npm are not used.

## Install from a source checkout

```bash
bash install.sh
```

If `frontend/dist/index.html` is absent, the installer builds the frontend in a
temporary staging directory with Node.js 22 / npm 10. It does not modify the
checkout's `frontend/dist` or `node_modules`.

## Default locations

| Purpose | Default |
|---|---|
| Application/runtime | `~/.local/opt/lightgravity-bot` |
| Data root | `~/.local/share/lightgravity-bot` |
| Task workspaces | `<data-root>/workspaces` |
| Secret store | `~/.config/lightgravity-bot/secrets` |
| Launcher configuration | `~/.config/lightgravity-bot/install.conf` |
| Stable launcher | `<application>/bin/lightgravity` |

`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `HOME`, or explicit options can change these
locations. The configuration file contains paths and flags only; it never
contains credential values.

## Options

```text
bash install.sh \
  --install-dir DIR \
  --data-dir DIR \
  --workspace-root DIR \
  --secret-store DIR \
  --host 127.0.0.1 \
  --port 8000
```

Use `--team` to enable team mode explicitly in the launcher configuration, or
`--no-team` to keep it off. Team mode is off by default (the existing
single-user default). Running the installer with `--host` other than loopback is
an explicit network-facing choice; the installer still does not start the
service or open access itself.

The installer refuses unsafe targets such as `/`, `$HOME`, a non-LightGravity
directory, a symlink target, or data/secrets inside the application directory.
It also refuses to replace an application while the recorded service PID is
still running.

## Start, status, and stop

The installer prints the exact launcher path for the selected application
directory. For the defaults:

```bash
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" status
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" stop
```

Add `--daemon` to `start` for a background process whose log is written under
`<data-root>/logs`. The launcher works from any current directory and quotes
paths containing spaces. It reads the external configuration file on each run,
and accepts the normal `lightgravity` flags after the command.

The default service URL is <http://127.0.0.1:8000/>. To opt into team mode later,
start explicitly with:

```bash
LIGHTGRAVITY_TEAM_MODE=1 "$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

An empty team account store is initialized once with `admin` / `admin123`.
Change that password immediately after signing in. Existing accounts and
passwords are preserved on restart and reinstall.

## Configure a model

1. Open **Settings → Models & Providers / Connections**.
2. Create a connection, save the credential through the protected form, and test
   it. The installer never asks for or prints a credential value.
3. Set the coordinator, default worker, and independent reviewer connections.
   Delivery acceptance requires an available reviewer.
4. Configure the model path before starting real task execution.

The existing validated generation path uses DeepSeek through the Antigravity
SDK's OpenAI-compatible loopback proxy. No model call is made by the installer.

## Reinstall and preservation

Re-running `install.sh` updates the application files and Python environment.
The data root, workspaces, secret store, accounts, and settings live outside the
application directory and are not replaced. The installer also leaves existing
data and secret directories in place if they already exist.

If the recorded service is running, stop it first:

```bash
"<application>/bin/lightgravity" stop
```

## Build a prebuilt release archive

Maintainers can produce a local archive without modifying the checkout:

```bash
bash scripts/build-release.sh [OUTPUT_DIR]
```

This requires Git, Node.js 22, npm 10, and uv. The default output is
`dist/release`. The archive includes the committed runtime source,
`pyproject.toml` + `uv.lock`, the frontend built from the same commit, this
guide, the installer, `THIRD-PARTY-NOTICES.md`, and production frontend license
files. It excludes `node_modules`, `.venv`, tests, probes/QA evidence, runtime
data, secrets, and build caches. Each archive is accompanied by a per-file
manifest and a tarball SHA-256.

## Troubleshooting

- **`uv` is missing** — install uv 0.12+ using the official instructions and
  re-run the installer.
- **Source install says Node.js/npm is missing** — use a prebuilt release archive,
  or install Node.js 22 LTS and npm 10.
- **The target directory is refused** — choose an empty/new application path,
  or let the installer update a directory that contains its
  `.lightgravity-install` marker.
- **Port already in use** — pass another `--port` or edit the configuration
  file, then start again.

## Contents and licenses

The application archive does not include third-party Python package bodies;
they are rebuilt by `uv` from the locked metadata. Bundled frontend production
license files are included under `licenses/frontend/`. See
`THIRD-PARTY-NOTICES.md` for dependency provenance and the project's current
license status.
