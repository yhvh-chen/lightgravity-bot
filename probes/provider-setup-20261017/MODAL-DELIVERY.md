# LG-110 connection list + New/Edit modal delivery

Status: **frontend candidate only, not merged, not deployed**. The Save-before-Test
contract in the reusable LG-106 candidate is **superseded** by the frozen
[MODAL-CONTRACT](MODAL-CONTRACT.md): Test now targets the unsaved draft through
`POST /api/v1/settings/connections/test-draft`, while Save remains a separate
create/update operation.

- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-modal-20261017`
- Branch: `feat/provider-modal-20261017`
- Base: `2637dd2` (includes LG-106 only, no LG-108/LG-109 commits)
- Code/test commit: `b2caea9` (`feat(ui): add connection list modal with draft testing`)
- Owner boundary: `frontend/**` and related frontend tests, this delivery note,
  `MODAL-INTERFACE-NOTES.md`, and `modal-logs/`. No backend, root PM docs, task
  docs, main, live service or deployment changes.

## Delivered UX

- Settings → Models & Providers now lands on a saved Connection list showing
  Name, Provider, Model, backend-persisted test status (or an honest
  “Not tested”), and per-row Edit/Delete. There is no always-open long editor.
- “New connection” and row Edit open one compact accessible modal
  (desktop width `540px`, within the required 480–560px; `≤640px` viewport uses
  a near/full-screen sheet, including 390px).
- Fields: Provider, Name, required API key/ADC/LiteRT fields, Base URL for
  OpenAI-compatible endpoints, Model (hidden for LiteRT where the model file is
  the model). Internal Connection ID and credential-reference details are
  auto-managed in collapsed Advanced; there is no debug header or stale LG-020
  warning.
- Provider presets retain the fixed SDK 0.1.22 paths: Gemini API, Vertex Express,
  Vertex Project+ADC, DeepSeek (OpenAI-compatible), genuinely selectable
  **Custom OpenAI-compatible**, and LiteRT local. Existing custom records are
  inferred and preserved without migration.
- Custom OpenAI-compatible shows Base URL as a primary required field and states
  that this build only permits the existing DeepSeek upstream for live
  testing/execution. Saving is not presented as compatibility or verification.
- Footer layout is left `Test connection`, right `Cancel` / `Save`.
- Dirty close (Cancel, X, Escape or backdrop) opens an in-modal confirmation bar;
  “Keep editing” retains the draft, “Discard and close” clears the typed secret
  and closes. No external nested confirmation modal is used.
- The dialog traps Tab, marks the background `inert`/hidden, handles Escape, and
  returns focus to the opening control (or the saved row after Save).
- Test failure stays inline and preserves the draft/key. Save remains available
  after a failed test. Field/key edits mark an older result stale.
- Draft results show a `draft · not saved` badge and are never promoted into the
  list's persisted status. Saving never changes a test into a pass.
- Row deletion requires inline confirmation. Known default/agent references are
  blocked before a request; a server rejection is shown in place and the row is
  kept. No silent dangling-reference removal is performed.
- Unknown deeplink targets show a miss and select nothing; a valid deeplink opens
  exactly one Edit modal and closing it does not reopen in a loop. Member gate,
  Accounts/My Account, and Task/Run routing semantics are unchanged.

## Frontend interface used

### Draft test (`POST /settings/connections/test-draft`)

The client sends the frozen 1.17 envelope:

```json
{
  "connection": {
    "backend": "openai-compat|gemini|vertex|litert",
    "model": "…|null",
    "base_url": "…|null",
    "auth_mode": "api_key|adc|proxy_api_key|none",
    "project": "…|null",
    "location": "…|null",
    "model_path": "…|null",
    "litert_backend": "CPU|GPU|NPU|null"
  },
  "credential_value": "only when the user typed a new/replacement key",
  "existing_connection_id": "edit only",
  "expected_revision": 0,
  "allow_network": true
}
```

- New drafts omit `existing_connection_id` and send `expected_revision: 0`.
- Edit drafts send the saved id and current revision; an empty key field sends no
  secret value at all. The backend may resolve the saved credential only after
  validating the same backend/auth/endpoint identity.
- No request is sent on mount, selection, provider change or Save. Only the
  explicit Test click sends one request.
- A returned Draft TestResult is bound to the modal's draft version. A field/key
  edit marks it stale; a result arriving after the draft changed or the modal
  closed is discarded. A draft result is never written into list state.

### Save

- Create uses the existing `POST /settings/connections`; update uses the existing
  `PATCH /settings/connections/{id}` with `expected_revision`.
- Optional provider fields (`auth_mode`, `project`, `location`, `model_path`,
  `litert_backend`, and `backend` on update when changed) are sent for the SDK
  presets. Untouched old OpenAI-compatible records omit the optional fields, so
  their legacy content is preserved.
- Save never auto-tests. On success the modal closes, the list refreshes from the
  backend, and focus moves to the saved row.
- If provider/auth/endpoint identity changes, an old credential is never kept for
  reuse: a new API key is required for key-based providers; otherwise the old
  credential reference is cleared on Save. The typed key is cleared on success,
  close/discard and provider switch and is never written to storage, URLs or logs.
- Explicit “Remove saved credential…” remains an Advanced two-step action,
  separate from Save.

## Files changed

| File | Change |
|---|---|
| `frontend/src/api/settings.ts` | draft-test/delete API calls, draft result types, optional persisted `last_test` summary |
| `frontend/src/views/settings/SettingsView.tsx` | list landing, row actions/delete confirmation, modal lifecycle/focus/target guards, separate Default models |
| `frontend/src/views/settings/ConnectionEditor.tsx` | accessible 540px modal, provider draft form, Test-draft/Save separation, credential-identity and stale/race guards |
| `frontend/src/views/settings/ConnectionTestPanel.tsx` | draft result labelling/stale handling; Test button moved to modal footer |
| `frontend/src/views/settings/backends.ts` | selectable Custom OpenAI-compatible preset; no false executable claim for arbitrary hosts |
| `frontend/src/views/settings/settings.css` | list/modal/confirmation/responsive styles using existing tokens |
| `frontend/tests/settings.test.tsx` | updated list/defaults/save/conflict/credential/legacy-custom coverage |
| `frontend/tests/provider-setup.test.tsx` | modal lifecycle, accessibility, draft Test→Save, stale/late async, custom endpoint, presets, deletion, member/deeplink coverage |

No new UI dependency or library was installed. The existing locked
`frontend/node_modules` was used through a temporary symlink and removed before
commit. `frontend/dist` was not committed.

## Tests and logs

Run from `frontend/`:

| Command | Result | Log |
|---|---|---|
| `npx tsc --noEmit` | exit 0 | `modal-logs/typecheck.txt` |
| `npx vitest run tests/settings.test.tsx tests/provider-setup.test.tsx` | 28 passed | `modal-logs/provider-modal-tests.txt` |
| `npm run build` (`tsc --noEmit && vite build`) | exit 0 | `modal-logs/build.txt` |
| `npx vitest run` (full frontend suite) | 237 passed, 23 files | `modal-logs/frontend-tests-full.txt` |

The full-suite log retains pre-existing React `act(...)` warnings from board
tests; they are unrelated to this change and were not modified. These are unit
tests against injected fake APIs, not real-backend or browser evidence.

## Limits / not done

- No backend implementation, contract-version edit, LG-109 integration, or
  LG-108 fix consumption in this worktree.
- No real backend/test-draft run, no browser/Playwright QA, no real SDK/vendor
  request, and no real credential use. Product model calls made by this work:
  **0**; cost unknown.
- Two backend response/interface gaps are reported in
  [MODAL-INTERFACE-NOTES.md](MODAL-INTERFACE-NOTES.md): the persisted list test
  summary field and the connection-delete route are not frozen in the current
  contract text.
- The list can truthfully show only what the backend returns. Without the noted
  persisted-test summary it displays “Not tested”; it never treats a draft result
  or a successful Save as verified.
- No main merge, deployment, service restart, frontend dist replacement, remote
  push, or task status update. Browser QA and independent LG-112 acceptance
  remain pending.
