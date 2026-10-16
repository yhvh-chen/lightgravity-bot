# B-FRONTEND REPORT (LG-044)

> LG-044 frontend owner. Base **21e6344** (frozen contract, docs/10). Depends on
> LG-042 only; A backend (LG-043) runs in parallel — this work binds to the
> frozen contract and is verified by **local mock component/hook tests**, never
> against a live backend. **No real E2E claim until LG-047 concentrated QA.**
> No product model/network calls were made.

## Status

**Implementation complete — PENDING LG-047 version QA.** Not a version-QA pass.

## Scope / changed files (all under `frontend/**`)

New:

- `frontend/src/views/chat/useChatSelection.ts` — Task-scoped selection state
  hook (default none, ≤3, clears on scope change, real version/hash refs).
- `frontend/src/views/chat/ChatSourcePicker.tsx` — manual picker over
  already-ingested global + current-Task materials; failed/revoked/un-ingested
  rows are not selectable; shows limit; honest error state.
- `frontend/src/views/chat/ChatSources.tsx` — reply `Sources` block from
  `resolved_source_bindings`/`context_truncated`/`provided_context_note`
  (version/hash/layer/truncation), with an in-app backlink to Files.
- `frontend/tests/lg044-selected-material.test.tsx` — 15 focused tests.

Modified:

- `frontend/src/api/chat.ts` — additive frozen TS shapes + `selected_sources`
  serialisation (omitted when empty) + response `data` normalisation (both the
  nested `{message:{...}}` envelope and legacy flat shapes; legacy rows with no
  source fields normalize to `null`).
- `frontend/src/views/chat/useChat.ts` — `send(content, attachments,
  selectedSources?)`; returns `resolvedSources` parsed from the submit `data`.
- `frontend/src/views/chat/ChatBody.tsx` — wires the picker, sends the refs,
  renders reply + persisted `Sources`, keeps the Task scope for backlinks, and
  clears transient reply Sources on Task change.
- `frontend/src/views/chat/chat.css` — additive styles reusing existing tokens
  (no new palette/components).

No backend, docs, lockfile, symlink or `dist` changes.

## Frozen interface binding

- Request (docs/10 §2): `selected_sources?: { source_id: string;
  source_version?: number; content_hash?: string }[]` on the existing message
  envelope for **both** global (`/conversations/global/messages`) and Task
  (`/tasks/{id}/messages`). Omitting the key keeps the request byte-identical
  to legacy (verified by a test asserting the key is absent when nothing is
  selected). At most 3 refs (`MAX_SELECTED_SOURCES = 3`).
- Response (docs/10 §4/§9): reads
  `data.resolved_source_bindings[]`, `data.context_truncated`,
  `data.provided_context_note`; each binding renders `source_id`,
  `source_version`, `content_hash`, `layer`, `locator`, `char_count`, and
  `truncated`/`truncation`. TS shapes copied **verbatim** from docs/10 §9
  (`SelectedSourceRef`, `ResolvedSourceBinding`, `ResolvedSourceBindingsData`).
- Labels: the block is titled **`Sources`** with a non-authoritative
  `provided context` badge and the backend's own
  "citations are NOT span-verified" note. No verified/model-used claim.

## Implementation choices (explicit, docs/10 §8)

- **Selection after send**: cleared on a **successful** send (the refs are then
  bound to that message); a **failed** send keeps the selection so an explicit
  retry reuses it. This is the docs/10 §8 "clear/pending" choice B declares.
- **Task isolation**: the selection hook clears whenever `task_ref` changes, and
  the picker never lists other Tasks' sources in a Task scope (it reads the Task
  filter plus the unscoped list and keeps only `scope.task_ref == null` global
  rows). Cross-Task refs are refused in the UI; the server validates
  independently (docs/10 §5).
- **Backlinks** are real in-app routes to Files (`selectItem: source:<id>` +
  view=files), preserving the current Task scope. No fabricated local file URLs.
- The picker treats a **revoked** source (`status: archived`, docs/08 §6.6 /
  docs/10 §5) and `failed`/not-yet-ingested sources as **not selectable** and
  labels why.

## Raw commands (real output, EXIT)

```
$ cd frontend && npx tsc --noEmit
TSC_EXIT=0

$ cd frontend && npx vitest run tests/lg044-selected-material.test.tsx
 ✓ tests/lg044-selected-material.test.tsx (15 tests) 352ms
 Test Files  1 passed (1)   Tests  15 passed (15)
VITEST_EXIT=0

$ cd frontend && npx vitest run   # full suite
 Test Files  14 passed (14)   Tests  112 passed (112)
VITEST_EXIT=0

$ cd frontend && npm run build
> tsc --noEmit && vite build
✓ 103 modules transformed.
dist/assets/index-Bzb1Pkc-.css   36.91 kB │ gzip:  5.55 kB
dist/assets/index-Cl1GOq_4.js   291.50 kB │ gzip: 85.87 kB
✓ built in 1.19s
BUILD_EXIT=0
```

Note: `frontend/node_modules` was symlinked to the main repo's installed deps
to run the checks (untracked, git-ignored; never committed). `dist/` is
git-ignored and never committed.

### Test coverage map (LG-044 acceptance)

- Task isolation / scope reset — `useChatSelection` + `ChatSourcePicker`
  cross-Task exclusion test.
- API serialization — omitted-when-empty and real version/hash (no invented
  hash) tests; both global and Task paths use the same `sendMessage`.
- 3-source limit — `atLimit` UI + hook bound.
- Errors — `capability_unavailable` list error, `source_stale` send error kept
  in place with draft preserved.
- Backlink target metadata + truncation — `ChatSources` renders real
  id/version/hash/layer and kept-vs-original counts; backlink calls `onOpen`
  with the real `source_id`.
- Legacy — `ChatSources` renders nothing when `data` is null.

## Stop state

No background processes started; no product model/network call. Only the local
mock component/hook tests, tsc and vite build ran. Nothing on port 8123.

## Limits / remaining risk (honest)

- **No real backend / browser E2E.** These are local mock tests; they do not
  prove wire compatibility with LG-043's actual implementation, nor real
  truncation/`source_stale`/`revoke` behaviour end-to-end. That is LG-047.
- **Repository persisted reply Sources**: the frontend reads the additive
  fields off the POST `data` and, defensively, off the message row if the
  backend also persists them. If A only returns them on the POST (not
  persisted), reopened history will not show Sources for old replies — this is
  a deliberate fail-open-to-legacy choice, not a fabricated claim. Confirm
  persistence shape during LG-047.
- **Global-list filtering**: in Task scope the picker reads the unfiltered
  `GET /sources` list to recover global rows; it drops non-global rows
  client-side. If A tightens `GET /sources` authorization so an unfiltered read
  is refused in a Task scope, the picker will surface an honest error and only
  the Task-filtered rows would be available — a behaviour to reconcile at
  integration.
- No CSS-mirror tests (per task); responsive shell CSS is unchanged.
