# LG-050 backend report

- Worktree: `/tmp/lg-team-backend-20261016`
- Branch: `feat/team-backend-20261016`
- Commit: `1df73109d2392e949d87367d9550553a06bcdb1c`
  (`feat(lg050): additive team mode — accounts/session auth, role policy, @bot gating`)
- Base: `main` `d873a36`
- Interface: `/tmp/lg-team-interface-20261016.md`
- Deviations/registrations: `/tmp/lg-team-backend-contract-notes.md`

## What was delivered

Additive team mode behind `LIGHTGRAVITY_TEAM_MODE` (default **off**). In
single-user mode no behaviour changes and no accounts file is read/created.

- **Accounts fact source** (`backend/lightgravity/team/accounts.py`): one JSON
  document, atomic same-dir replace + `fsync`, forced `0600`, process lock,
  PBKDF2-HMAC-SHA256 (200000 iters, per-account salt); unknown `algo` refused;
  unknown fields preserved; no cleartext/hash ever logged or printed.
- **Sessions** (`team/sessions.py`, `team/service.py`): in-memory
  `session_id -> {username, role, expires_at}`, TTL expiry, immediate revoke,
  login throttling.
- **Auth endpoints** (`api/auth.py`): `GET /auth/me` (always registered; team or
  single), `POST /auth/login` (team only, `Set-Cookie` HttpOnly/SameSite=Lax/
  optional Secure), `POST /auth/logout` (401 anonymous, 204 idempotent). Origin
  guard and 429 `budget_exhausted` throttling after 5 failures/60 s.
- **Role policy** (`team/policy.py`): only the server-resolved session cookie is
  identity. Anonymous -> 401 on all business/SSE; member -> business read/write
  allowed, `/settings*` + resource mutations 403 `forbidden`; admin -> all.
  `X-LG-Token` never grants or elevates a team role.
- **Global messages** (`coordinator/service.py`, `api/conversations.py`):
  server-injected `author`; ordinary messages persisted only with
  `kind="recorded"`, `reply=null`, zero classifier/responder/model calls and no
  Task; `@bot` (configurable, whitespace/punctuation boundary) strips the prefix
  and follows the existing `classify_message` + `_route_global` route; Task
  messages are never gated. Per-conversation bot-turn lock + idempotency make
  concurrent duplicate retries run once. Assistant replies carry the bot author.
- **Task resource-proposal bypass closed**: proposal messages require an
  admin `authorize(..., admin=True)` gate and the coordinator refuses a
  non-admin author as defense in depth.
- **SSE**: anonymous rejected before the stream starts; an established stream
  re-checks the session every 2 s and closes on logout/expiry.
- **CLI** (`cli.py`): `lightgravity user add --username --role` (password via
  `getpass`, never argv) and `user list` (username/role/created_at only).
- **Contracts** (`backend/contracts/**`): additive `ErrorCode.FORBIDDEN` (403)
  and `Author` DTO. Contract version left at 1.12.0 (docs out of scope); see
  notes.
- **Files protection**: team-mode Files refuses any path inside `<data>/team/`.

## Verification (real results)

Run from the worktree with the shared venv
`/home/yhvh/code/lightgravity-bot/.venv` and `PYTHONPATH=backend` (the shared venv
was used read-only, not modified):

- `python -m mypy` -> **Success: no issues found in 145 source files**.
- `python -m pytest -q` (full suite) -> **978 passed, 5 skipped, 1 warning in
  ~156 s**. The 5 skips are the pre-existing environment-gated tests.
- `python -m pytest tests/team -q` -> **44 passed**.

### CLI / real-process startup smoke (dedicated port 8792 + temp data root)

`lightgravity user add --role admin`, `user list`: account created, file mode
`-rw-------` (`0600`), no password/hash printed. Started
`lightgravity start --host 127.0.0.1 --port 8792 --no-frontend` with team mode
env, then:

| Request | Result |
|---|---|
| `GET /api/v1/health` | 200 ok |
| `GET /api/v1/auth/me` (anon) | 200 `{"mode":"team","authenticated":false,...}` |
| `GET /api/v1/team/available` (anon) | 401 |
| `GET /api/v1/team/available` + `X-LG-Token: anything` | 401 |
| `POST /auth/login` wrong password | 401 |
| `POST /auth/login` admin | 200 `{"username":"admin","role":"admin"}` |
| `GET /settings` admin | 200 |
| `POST /auth/login` member | 200 `{"username":"bob","role":"member"}` |
| `GET /settings` member | 403 `forbidden` |
| `GET /team/available` member | 200 |
| `POST /global/messages` member plain | 200 `kind="recorded"`, `reply=null` |
| `GET /events/stream` anon | 401 |
| `POST /auth/logout` | 204 |
| `GET /settings` admin after logout | 401 |

The process was stopped via `lightgravity stop` (SIGTERM, confirmed), the port
released and the temp dirs removed.

## Constraints respected

- Never read `.env`/real secrets; no real product model call was made.
- The pre-existing resident uvicorn on `127.0.0.1:8123` (pid 3320750) was not
  touched or reused; smoke used dedicated ports/data roots.
- Shared venv used read-only; no modification.
- Did not modify `frontend/`, `docs/`, `README.md`, `PROJECT.md`, `backlog/`,
  `PROGRESS.md`, or the main workspace dirty/untracked files.
- No secrets/account data committed (accounts live under the gitignored
  `bot-data` in normal runs; tests use `tmp_path`).

## Limitations / out of scope

- Sessions are process-memory only; a restart invalidates every session (the
  interface explicitly accepts this) and the frontend must log in again.
- Login throttling is in-memory per process; a multi-process deployment would
  need a shared store. This is a documented additive behaviour choice.
- Contract version/docs and the frontend auth gate/polling are owned by other
  workstreams; frontend integration is expected to consume `/auth/me`, cookies
  and the additive `author` field.
- This is single-executor work; independent version QA has not run. Status is
  "implementation complete, pending version QA".
