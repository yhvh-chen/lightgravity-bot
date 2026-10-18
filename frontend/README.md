# Frontend

This directory holds the React 18 + TypeScript + Vite frontend.

## Current scope (LG-011 shell)

LG-011 (cherry-picked onto `main`) provides the left-nav shell and shared
component layer:

- `src/app/` — shell and routing: `AppShell`, `TopBar`, `NavigationRail`,
  `ShellProvider`, `uiState` (URL + `sessionStorage` prefs), `navigation`,
  `layoutMock`, `useMediaQuery`, `tokens.css`, `shell.css`.
- `src/components/` — shared components: `ContextList`, `SplitPane`
  (`PanelResizer`), `StatusBadge`/`MockBadge`, `TaskCard`, `ResourceCard`,
  `DetailHeader`, `MarkdownViewer`, `ChatComposer`, `ChatPanel`, `EmptyState`,
  `ErrorState`, `NotificationList`, `icons`.
- `src/api/` — `types` (aligned with docs/08 error envelope / health / version /
  enums), `client` (real `/api/v1` fetch with the error envelope),
  `useBackendStatus` (real `/health` probe).
- `src/views/` — `registry.tsx` view entries; `ChatView` (single Chat instance)
  plus Board/Files/Team/Resources/Settings placeholders owned by
  LG-013/014/015/026.

## Real integration status

The shell is a **layout prototype** and is **not backend-connected**:

- Only `GET /api/v1/health` and `GET /api/v1/version` exist on the backend; there
  are no Task/Run/Messages/SSE/Files/Resources/Settings endpoints yet.
- Without a running backend, Chat and status surfaces show the real
  "Backend not connected" (`network_error`) state; business views render
  placeholders/empty states marked `MockBadge` / layout mock. Nothing fakes data.
- LG-011 evidence: 19 vitest tests, 23/23 dependency-free Chrome checks
  (desktop 1440 / 1024 / 390px drawer), `tsc` / `vite build` pass; **no real
  backend integration test** was run. Results are executor-local and marked
  "pending milestone QA".

## Toolchain ownership (LG-002)

The integration executor (first LG-002) owns the shared toolchain files:
`package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`,
`index.html` and the `main.tsx` / `App.tsx` entry.

## Ownership boundary

`frontend/src/app`, `frontend/src/components`, `frontend/src/api` and
`frontend/src/views` are owned by LG-011 and the view tasks (LG-013/014/015/026),
per `docs/08-interface-contract.md` §11. Shared view files (`views/registry.tsx`,
`app/navigation.ts`, `api/`) will be extended by LG-013/014/015/026, so the
integration owner should serialize those edits. Do not copy shared contract
types: import from `backend/lightgravity/contracts` where the API shape is frozen.

Invariants carried from LG-011:

- Exactly one `ChatPanel` renders at a time (Chat main area or the right rail).
- Deep links: `?view=<chat|board|files|team|resources|settings>&task=&run=&item=`;
  shell prefs live in `sessionStorage` under `lg011.shell-prefs`.
