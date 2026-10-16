# LG-050 backend contract notes (implementation deviations)

Base: `main` @ `d873a36`. Worktree `/tmp/lg-team-backend-20261016`,
branch `feat/team-backend-20261016`. Interface: `/tmp/lg-team-interface-20261016.md`.

The implementation follows the agreed interface. These are the necessary /
deliberate deviations and additions an integrator should register in docs/08.

## Additive contract registrations (backend/contracts)

1. `ErrorCode.FORBIDDEN = "forbidden"`, HTTP 403, `retryable=false`
   (`contracts/enums.py`, `contracts/errors.py`). Envelope matches the interface:
   `details={"required_role":"admin", "endpoint": ...}`.
2. `Author` DTO (`contracts/dto.py`): `{kind, username|null, role|null}`, exported
   from `contracts/__init__.py`. It is server-only; `GlobalMessageRequest` still
   uses `extra="forbid"`, so a client-supplied `author` is a 422
   `validation_failed` before any handler runs.

Contract version was **not** bumped (`1.12.0` unchanged) because docs/08 and the
docs owner are out of this task's write scope. Integration should record the
LG-050 additive items as a MINOR.

## Documented behaviour choices

3. **Recorded result `reply`.** Internally the coordinator returns
   `reply=""` for a recorded-only message; the API boundary
   (`api/conversations.py`) rewrites `reply` to JSON `null` for
   `kind=="recorded"` so the wire shape matches the interface exactly. No other
   result kind is rewritten.

4. **Login throttling code.** There is no dedicated frozen "too many requests"
   error code. After 5 failures per `(client-host, username)` in a rolling 60 s
   window, login returns HTTP 429 with `code="budget_exhausted"` and a
   `Retry-After` header. This is additive; success clears the counter.

5. **Logout idempotency vs anonymous 401.** `/auth/logout` is reachable without
   a session at the policy layer so the handler can distinguish the two cases:
   * no cookie -> 401 `unauthorized` (anonymous);
   * cookie present (valid, expired or already revoked) -> 204 + cookie clear
     (idempotent, covers the "重复登出" case).
   A revoked session's already-open SSE stream is torn down (see 7).

6. **Admin-only scope.** `/api/v1/settings*` is admin-only for **all** methods
   including GET (matches the docs/08 matrix table: member is denied the
   `/settings*` column). Business reads/writes (tasks, conversations, files
   incl. upload/download, sources, search, vector, resources/team reads,
   notifications, events) are allowed for members. `PATCH/PUT/DELETE
   /api/v1/resources/{kind}/{id}` is admin-only. Credentials live under
   `/settings`, so they inherit the admin gate.

7. **SSE session liveness.** The event generator re-resolves the session every
   `_SESSION_CHECK_SECONDS = 2.0` while the stream is idle; a logout/expiry
   closes an already-established stream instead of letting it outlive the
   session. Single-user mode keeps the original 15 s keep-alive only.

8. **Static frontend anonymity.** In team mode the SPA/asset paths (anything not
   under `/api/v1`) stay anonymous so the login gate can render. Team mode never
   injects the runtime token into the page; `bootstrap.build_runtime` passes an
   empty token to `mount_frontend`. The token is not an identity and can never
   elevate a member.

9. **Policy signature.** `AccessPolicy.authorize` gained an additive keyword
   `admin: bool = False`. `LocalAccessPolicy` ignores it (single-user operator is
   implicitly admin), so single-user behaviour is unchanged.
   `is_sensitive_request` was additively extended to cover resource mutations;
   the resources route already re-checked, so single-user behaviour is
   unchanged.

10. **Files protection.** In team mode `files._reject_secret` also refuses any
    path resolving inside the controlled team-state directory
    (`<data>/team/`), so `accounts.json` cannot be read through Files even if
    the workspace root is misconfigured to contain it. Default workspace root is
    `<data>/workspaces`, outside the team dir.

11. **Task `resource_proposal` indirect path.** `coordinator/api.py` now injects
    the server-resolved `author` into Task messages and requires
    `authorize(sensitive=True, admin=True)` whenever a proposal is present, so a
    member gets 403 before any write. Defense in depth: the coordinator also
    refuses a team-mode proposal whose injected `author.role != "admin"`.

12. **CLI team settings.** `cli._settings_from_args` now carries the resolved
    `team_*` Settings fields so explicit `--data-dir/--host/--port` never reset
    team mode (a real startup smoke caught the initial drop).

## Not changed

- `.env`/real products/models were never read or called; no real network model
  call was made in any check here.
- The pre-existing resident uvicorn on `127.0.0.1:8123` (pid 3320750) was not
  touched; all smoke runs used dedicated ports/data roots and were stopped.
- `frontend/`, `docs/`, `README.md`, `PROJECT.md`, `backlog/`, `PROGRESS.md`
  were not modified.
