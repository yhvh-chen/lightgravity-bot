# LG-106 provider UI delivery

Status: **independent frontend candidate, not merged, not runtime-deployed**.
Branch `feat/provider-ui-20261017` in isolated worktree
`/home/yhvh/code/lightgravity-bot-worktrees/provider-ui-20261017`, based on main
`85d009d`.

Candidate code/test commit: `9c40e78` (`feat(ui): simplify provider setup with
SDK presets`). This delivery document is committed separately.

## What was delivered

A minimal, bindable Provider form in Settings → Models & Providers:

* provider dropdown with the five SDK 0.1.22 presets (Gemini API, Vertex Express,
  Vertex Project+ADC, DeepSeek OpenAI-compatible, LiteRT local model);
* auth fields that match each real provider path: API key only where the SDK uses
  one; Project/Location + ADC for Vertex Standard; model file path + CPU/GPU/NPU
  for LiteRT;
* SDK defaults (`gemini-3.8-flash`; DeepSeek `deepseek-v4-flash` +
  `https://api.deepseek.com/v1`);
* Save + Test as the primary actions; Test disabled until saved and disabled for
  unsaved/dirty edits; no automatic test on load/select/save;
* collapsed Advanced containing auto-generated ID, optional title, enabled,
  backend/auth enum, credential reference, endpoint override, references,
  explicit credential removal and collapsed raw test layers;
* legacy/custom OpenAI-compatible records remain discoverable and preserved;
  empty key keeps the stored secret and provider switching never deletes it;
* stale LG-020 warning and debug header (`task`/`source GET`) removed from the
  primary UI; real errors remain visible;
* capability metadata (`configurable`, `testable`, `executable`,
  `vendor_verified`) kept separate and backend-overridable; no new provider is
  marked executable or vendor-verified;
* default role selectors moved into a minimal collapsed Advanced/Defaults area;
* LG-103 routing/missing-target/late-response guards and the member no-config
  fetch gate preserved.

## Files owned/changed

| File | Change |
|---|---|
| `frontend/src/api/settings.ts` | optional provider fields + capability types, SDK model constant |
| `frontend/src/views/settings/backends.ts` | provider presets, legacy inference, capability merge/default eligibility |
| `frontend/src/views/settings/ConnectionEditor.tsx` | primary provider form + Advanced, Save/Test/dirty/secret rules |
| `frontend/src/views/settings/ConnectionTestPanel.tsx` | explicit-test wording, collapsed raw layers |
| `frontend/src/views/settings/SettingsView.tsx` | remove stale warning/debug header, provider list badges, collapsed Defaults |
| `frontend/src/views/settings/DefaultsEditor.tsx` | executable-capability default filter |
| `frontend/src/views/settings/settings.css` | disclosure/Advanced styles |
| `frontend/tests/settings.test.tsx` | updated existing Settings coverage for the simplified flow |
| `frontend/tests/provider-setup.test.tsx` | new provider matrix, secret, dirty Test, capability, member and late-ID tests |

No backend, contract, root project/task doc, main, index, live service or
`frontend/dist` change was made from this worktree. No new dependency was
installed; tests/build reused the existing locked `frontend/node_modules` through a
temporary symlink that was removed before commit.

## Tests and logs

Run from `frontend/`:

| Command | Result | Log |
|---|---|---|
| `npx tsc --noEmit` | exit 0, no output | `probes/provider-setup-20261017/logs/typecheck.txt` |
| `npx vitest run tests/settings.test.tsx tests/settings-auth.test.ts tests/provider-setup.test.tsx` | 35 passed | `.../logs/provider-settings-tests.txt` |
| `npx vitest run` (full frontend suite) | 240 passed, 23 files | `.../logs/frontend-tests.txt` |
| `npm run build` (`tsc --noEmit && vite build`) | exit 0 | `.../logs/build.txt` |

The full-suite log includes pre-existing React `act(...)` warnings from board
tests; they are not caused by this change and were not modified. No browser/E2E
campaign was run because the backend contract is still pending. No mock or unit
test result is presented as SDK/vendor verification.

Test coverage highlights:

* every provider preset maps to the expected backend/auth/model/default fields;
* required Vertex ADC / LiteRT inputs fail honestly without an API call;
* empty API key sends `credential_action: keep` with no value and no removal;
* provider switch keeps the old credential reference and never deletes it;
* Test requires a saved, non-dirty revision and sends only on explicit click;
* backend-declared `testable: false` disables Test honestly;
* existing custom OpenAI-compatible endpoint remains a legacy preset with no
  migration/optional-field injection;
* member role does not fetch Models/Connections;
* unknown target and late cross-ID save do not select/overwrite another record.

## Interface for backend integration

See [UI-INTERFACE.md](UI-INTERFACE.md) for the exact optional payload/response
fields, preset mapping, capability requirements, Save→Test semantics and the two
pending policy bindings. Summary of backend asks:

1. Accept/echo optional `auth_mode`, `project`, `location`, `model_path`,
   `litert_backend` on create/update; `null` clears, omitted preserves.
2. Allow `backend` change on update (with atomic validation of the combined
   state) so changing provider preset does not require a new record.
3. Return backend-declared `capabilities`; defaults remain executable-only.
4. Preserve existing secrets/refs on provider switch; explicit removal only.
5. Keep old `openai-compat` files and defaults working unchanged.
6. Implement real test layers per provider; the UI never asks for a test on load,
   selection or save.

## Limits / not done

* No backend implementation, source-contract change or contract-version bump.
* No real Gemini/Vertex/LiteRT/DeepSeek request, no real key read/output, no model
  or vendor verification; product model calls made by this work was **0** and
  cost is unknown.
* The current backend uses `extra="forbid"`, so new provider saves will return a
  real 422 until the backend owner lands the additive fields. Untouched DeepSeek
  saves omit the new fields and remain compatible.
* Native Task execution/default selection and manual Test network budget are
  **not decided here**. The candidate is capability-driven; a small binding
  change may be needed during integration (documented in UI-INTERFACE §5).
* No main merge, runtime service update/restart, frontend dist replacement,
  commit to another owner’s files, or browser QA.
* Pending independent QA and backend integration; this candidate is not a
  version acceptance.
