# LG-050 Frontend Execution Report

- **Task**: LG-050 frontend (team chat + simple auth), scope `frontend/**` only.
- **Worktree / branch**: `/tmp/lg-team-frontend-20261016` @ `feat/team-frontend-20261016`
- **Commit**: `26dc6f4a8c46e8b1e181d95acc774b9f5e06a06a`
  `feat(lg050): team login gate, server author, global polling`
- **Base**: `main` HEAD `d873a36`
- **Environment**: node v22.23.2, npm 10.9.8. Tests/build ran against the
  existing main-worktree `frontend/node_modules` (temporarily symlinked; the
  symlink was removed before commit). `package.json` / `package-lock.json`
  were not modified; no install/upgrade was performed.

## What was delivered (all additive, single-user default unchanged)

| Area | Change |
|---|---|
| Auth API | New `src/api/teamAuth.ts`: `GET /auth/me`, `POST /auth/login`, `POST /auth/logout`. |
| Cookie transport | `credentials: 'include'` added to `apiRequest` and the two direct `fetch` calls (`files/download`, `sources/download`). SSE stays same-origin. |
| Auth state | New `AuthProvider` / `useAuth`. Probes `/auth/me`; team-anonymous ⇒ login gate, team-authenticated ⇒ workspace + identity/sign-out, `single`/404/network ⇒ existing single-user workspace. Clears the in-memory runtime token in team mode so `X-LG-Token` cannot act as a team identity. |
| Login gate | New `src/views/auth/LoginView.tsx` + `auth.css` (English UI, uses shared tokens, password cleared on failure, never persisted). |
| Identity / logout | `TopBar` shows server username + role and a `Sign out` button (team mode only). |
| Admin entry | `NavigationRail` disables the Settings entry for team `member` (`title="Administrator only"`); backend still enforces 403. |
| Author | `ChatMessage.author` added and normalized from nested/flat wire shapes. Team mode renders the real author and **Unknown** for authorless history; single mode keeps "You". |
| `recorded` | `ChatBody` treats `kind === "recorded"` as a shared team message (`Shared with the team.`), no bot reply, nothing fabricated. Client never sends `author` in the body. |
| Polling | `useChat` polls the **global** conversation every 3s in team mode: incremental `after` cursor, `message_id` dedupe, paused while `document.hidden`, and `401` ⇒ `requireLogin()` (back to the gate). Task-scoped conversations and single mode never poll. |
| Draft/scroll | Polling only appends; the draft is untouched. The view auto-scrolls only when already near the bottom, otherwise a `New messages ↓` entry appears. Scope switches reset the badge. |
| `@bot` | Frontend never injects `@bot`; team composer hint states plain messages are shared and `@bot` asks the assistant. |

## Verification (real commands, real results)

All commands from `/tmp/lg-team-frontend-20261016/frontend`:

1. **Typecheck** — `npm run typecheck` (`tsc --noEmit`): **PASS**.
2. **Vitest full suite** — `npx vitest run`: **16 files / 128 tests passed**,
   including the new `tests/team-auth.test.tsx` (7) and
   `tests/chat-author.test.tsx` (8); the 113 pre-existing tests still pass.
3. **Production build** — `npm run build` (`tsc --noEmit && vite build`):
   **PASS**, 107 modules transformed, `dist/` bundle emitted.

New coverage: login gate + successful login, bad-credential rejection,
single-mode pass-through, `/auth/me` 404 fallback, identity/sign-out,
admin-vs-member Settings entry, `401` re-login, `author` normalization and
Unknown history, `recorded` handling with no client `author`, incremental
polling + dedupe, hidden-page pause/resume, poll `401`, task-scope no-poll,
and no-poll single mode.

No `.env` was read, no real model was called, no request touched `:8123`, and
no `bot-data` directory was used.

## Limitations / deviations

- **Backend contract notes absent**: `/tmp/lg-team-backend-contract-notes.md`
  did not exist at implementation time, and the backend worktree
  `feat/team-backend-20261016` had no LG-050 commits yet. This frontend was
  implemented strictly against `/tmp/lg-team-interface-20261016.md`; there was
  no live team-mode backend to integrate with, so auth/polling tests use
  stubbed `fetch` only.
- **No live end-to-end browser run**: without a team-mode backend to point at,
  the login → workspace → cross-window polling path was not exercised against
  a real server. Visibility-pause and scroll behavior are covered by hook/unit
  tests, not a browser.
- **Optimistic probe**: during the initial `/auth/me` probe the shell renders
  the single-user workspace (this keeps the pre-existing synchronous shell
  tests and default behavior intact). For a real team-anonymous session the
  gate replaces it as soon as the probe resolves; child views may briefly issue
  unauthenticated requests in that window.
- **Session lifetime**: the cookie maps to server process memory per the
  interface, so a backend restart invalidates it; the frontend then returns to
  the login gate on the next `401` (as specified, not faked as persistent).
- **Assistant author label**: in team mode an assistant message with a server
  author renders that username (the contract uses `bot`), falling back to
  `Bot` only when the server omits it.
- No browser E2E screenshots were produced; visual checks are token-based and
  unit-level only.
