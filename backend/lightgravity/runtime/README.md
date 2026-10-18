# Runtime Startup and Local Distribution

This package (`lightgravity.runtime`) along with `lightgravity.api.bootstrap` and `lightgravity.cli` provides local startup and distribution wiring. It does not modify the frozen `api/app.py`, `api/context.py`, or the existing implementations in `adapter/`, `coordinator/`, and `verify/`. Runtime assembly is performed exclusively through the public `create_app(...)` factory.

## CLI Entrypoints

```bash
# Single-command foreground startup (default loopback); serves frontend/dist when built
uv run lightgravity start

# Specify isolated data / workspace / secret directories
uv run lightgravity start \
  --data-dir ./bot-data --workspace-root ./bot-data/workspaces --secret-store ./secrets

# Background daemon mode (logs in <data-dir>/logs/lightgravity.log), paired with status / stop
uv run lightgravity start --daemon
uv run lightgravity status          # Process + /api/v1/health
uv run lightgravity status --deep   # Detailed execution readiness report
uv run lightgravity stop            # SIGTERM, SIGKILL fallback, cleans up pid record

# Explicit, idempotent minimal resource initialization
uv run lightgravity init --connection-id primary --credential-ref worker-key \
  --agent-id developer --set-worker-default
```

`python -m lightgravity ...` is equivalent to the installed `lightgravity` / `lg` console scripts.
`make lg-start / lg-start-daemon / lg-status / lg-stop / lg-init` are equivalent make wrappers.

## Runtime Assembly

- `lightgravity.store.FileStore`: Manages data and workspace isolation (`LIGHTGRAVITY_DATA_DIR`).
- `lightgravity.settings`: `FileSecretStore` + `ConnectionService` + `ConnectionTester` (Settings, tests, and default connections operate against a single authoritative store; secrets stay in controlled storage or environment).
- `lightgravity.adapter.AntigravityExecutor`: DeepSeek loopback authentication proxy; credential resolution handled by the settings layer `credential_resolver`. Returns `capability_unavailable` or `config_invalid` when credentials or model definitions are absent, without crashing or falsifying success.
- `lightgravity.coordinator.GraphDispatcher`: Connects planner, recruiter, and scheduler to the executor.

## Authentication Handshake and Access Boundaries

- Each service process generates a random in-memory `X-LG-Token` (or uses `LIGHTGRAVITY_RUNTIME_TOKEN` when injected).
- Static frontend assets are hosted in-process: when serving `index.html`, the token is injected into `window.__LG_RUNTIME_TOKEN__` with `Cache-Control: no-store`. It is never written to URLs, logs, `localStorage`, `IndexedDB`, or disk.
- Sensitive write endpoints (`POST/PUT/PATCH/DELETE` on `/api/v1/settings`) require a valid token (`401 unauthorized` on mismatch).
- `HostGuardMiddleware`: By default accepts only loopback, `testserver`, or hosts explicitly configured in `LIGHTGRAVITY_ALLOWED_HOSTS`.

## Readiness Semantics

`execution_report()` (`status --deep` / startup banner) reports concrete operational facts:

- `executor_wired`: Whether the adapter and `GraphDispatcher` are assembled.
- `agent_refs`: Active agent resources (role catalog source).
- `default_worker_connection_ref` and `credential_configured`: Model connection status.
- `execution_ready`: True only when all prerequisites are met; otherwise provides explicit `reasons`.

When credentials or runtimes are unconfigured, historical queries (`GET /tasks`) and Settings remain accessible while execution remains unavailable.

## Directories and Configuration

- Runtime data: `--data-dir` (default `./bot-data`, gitignored); pid stored in `<data-dir>/runtime/lightgravity.json`.
- Secrets: `--secret-store` (default `./secrets`, gitignored).
- Frontend: `--frontend-dist` (default `./frontend/dist`); `--no-frontend` runs API only.
- Example environment variables are documented in `.env.example`.

## Tests

Test suite in `tests/startup/` covers: in-memory token safety, Host/Origin guards, SPA hosting with token injection, refusal of unauthorized writes, readiness reporting, idempotent initialization, runtime default agent seeding, Settings-to-task execution paths, and child process start/status/stop roundtrips.

```bash
uv run pytest tests/startup -q
uv run pytest -q
uv run mypy
```
