# LG-109 backend delivery record

Status: complete backend candidate, not merged/deployed. Branch/worktree:
`feat/provider-backend-20261017` at
`/home/yhvh/code/lightgravity-bot-worktrees/provider-backend-20261017`, based on
`main`/`85d009d`. Contract constant updated to **1.17.0**; root PM owns normative
Markdown registration.

## Commits

| Commit | Meaning |
|---|---|
| `d158c57` | Imported LG-108 minimal tester-budget fix by cherry-picking `3f8f8e6` from `fix/provider-test-budget-20261017`; no duplicate fix was made. |
| `ea09a86` | LG-109 backend implementation, tests, settings README and interface notes. |
| following `docs(probes)` commit | This delivery record plus the raw `backend-logs/` evidence. The handoff reports its exact hash. |

No root Markdown, frontend, live service, user data, real key, installed
package/service, cloud resource or remote push was touched. Product vendor model
calls made by this task: **0**. Development token/cost: **unknown**.

## Implemented backend scope

- Optional non-secret Connection fields `auth_mode`, `project`, `location`,
  `model_path`, `litert_backend`; serialization/storage/update semantics preserve
  omitted fields, allow explicit `null` clears, and preserve old unknown fields,
  body, defaults and unchanged secret refs.
- Provider/auth matrix for Gemini API, Vertex Express, Vertex Project + ADC,
  OpenAI-compatible/DeepSeek and LiteRT. Saving requires `configurable`, not
  `verified`; execution/defaults require the separate `executable` fact.
- `capabilities={configurable,testable,executable,vendor_verified}` on the
  public Connection view and resolved defaults. Only `openai-compat` is
  executable/default-eligible; Gemini/Vertex/LiteRT are `executable=false` and
  `vendor_verified=false`.
- Compiler/SDK construction: `CompiledConnection` carries provider fields;
  `build_sdk_config`/`build_connection_sdk_config` construct the installed
  `LocalAgentConfig` (Gemini key, Vertex Express key, Vertex ADC
  project/location), `LocalOpenAIAgentConfig` and `LiteRTAgentConfig` without
  executing them.
- `POST /api/v1/settings/connections/test-draft` with the frozen envelope:
  `connection`, optional write-only `credential_value`, optional
  `existing_connection_id`/`expected_revision`, `allow_network`. Returns the
  existing layered TestResult plus `draft:true`; saved identity fields are `null`
  for a new draft. Existing edit reuse requires the saved id + current revision +
  same backend/auth/credential-recipient identity; changed identity requires a
  fresh key, otherwise sanitized `422`.
- Draft path writes no Connection/secret/default/diagnostic/Task/Run/SDK config.
  Gemini/Vertex use one real-SDK minimal request (no tools/subagents/retries,
  `max_model_calls=1`) only on explicit `allow_network=true`; OpenAI-compatible
  keeps the existing loopback proxy; LiteRT is static package/file/config only.
  Every native probe reserves the persistent global generation ledger before the
  request; cap `0` and a corrupt ledger fail closed. ADC never runs gcloud or
  requests metadata during static checks.
- Saved test endpoint remains compatible, still binds revision/credential
  version and persists safe diagnostics. LG-108 per-invocation network allowance
  behavior is preserved.
- DeepSeek remains the only executable/default path and its loopback proxy host
  allowlist is unchanged; custom OpenAI-compatible hosts remain honestly limited.
  Existing `openai-compat` execution behavior is not expanded.
- LiteRT `model_path` is confined to the existing authorized workspace path
  policy at save and compile boundaries; no file content is read, installed,
  downloaded or inferred.

## Interface adjustments relayed to PM/frontend

See [BACKEND-INTERFACE-NOTES.md](BACKEND-INTERFACE-NOTES.md). Key points: draft
results use the existing nullable `connection_id` field (plus `draft:true`);
missing edit revision is `422` and stale is `409`; changed recipient requires a
fresh key; saved provider changes detach an old `credential_ref` instead of ever
reusing the old secret (the secret file remains); layer names stay the existing
six; `native_base_url` is an internal test-only loopback seam, never an HTTP
field.

## Verification evidence

Raw logs: [backend-logs](backend-logs/).

- Targeted provider/draft/regression tests: **55 passed** in 6.54s
  (`targeted-tests.txt`).
- Full backend test suite: **1195 passed, 5 skipped** in 184.85s; only the
  existing Starlette/anyio deprecation warning
  (`full-suite.txt`).
- `mypy backend/lightgravity`: **Success: no issues found in 147 source files**
  (`mypy.txt`).
- `git diff --check`: clean before commit.
- Actual installed SDK `google-antigravity==0.1.22` was run against a controlled
  loopback fake Gemini/Vertex streaming protocol for Gemini API key, Vertex
  Express key and Vertex ADC, with dummy keys only. The tests assert the real SDK
  path, one request, no keys in the result, and no saved Connection/secret. This
  distinguishes **SDK/local-protocol verification** from real-vendor
  verification (none).
- Tests cover provider matrix, old-file/default/unknown-field/body preservation,
  explicit field clearing, backend switch safety, default executable policy,
  LiteRT path restriction, draft no-write behavior, revision/credential identity
  errors, sanitized 422s, admin/member/anonymous gates, cross-origin rejection,
  cap-0/corrupt-ledger/native budget counting, repeated draft tests after LG-108,
  and saved-diagnostic compatibility.

## Limitations / not claimed

- No native Task execution, default selection, reviewer/default-capacity change
  for Gemini/Vertex/LiteRT. This package does not merely flip `verified`.
- No real Gemini/Vertex vendor call, real credential read/output or LiteRT
  package/model installation. LiteRT result is static only; no inference.
- ADC detection is a local credential-file prerequisite check, not an
  authentication proof. Explicit ADC network tests may still fail honestly.
- Frontend modal integration/browser QA belongs to LG-110/LG-112; this package
  only implements the backend/API contract.
- No merge into `main`, rebuild/deploy of live services, remote push, cloud
  resource creation or task-status change. This is a candidate pending LG-111
  integration and LG-112 QA.
