# Frontend

This directory holds the React 18 + TypeScript + Vite frontend.

## LG-002 scope (current)

The integration executor (first LG-002) owns the shared toolchain files:

- `package.json`, `package-lock.json`
- `vite.config.ts`, `tsconfig.json`
- `index.html`
- minimal `src/main.tsx` + `src/App.tsx` placeholders that prove the shell
  starts, type-checks, tests and builds
- `tests/` smoke test and setup

## Ownership boundary

`frontend/src/app`, `frontend/src/components`, `frontend/src/api` and
`frontend/src/views` are owned by LG-011 and the view tasks (LG-013/014/015/026),
per `docs/08-interface-contract.md` §11. LG-011 may restructure the placeholder
entry files as needed. Do not copy shared contract types: import from
`backend/lightgravity/contracts` where the API shape is frozen.
