# LG-106 Provider UI → backend interface

Status: frontend candidate only. Backend implementation not started by this worktree.
Base: `85d009d` (main). Branch: `feat/provider-ui-20261017`.
Owner boundary: `frontend/src/api/settings.ts`, `frontend/src/views/settings/**`,
related frontend tests. No backend/source-contract/root-doc/main/runtime changes.

This document is the binding request from the LG-106 UI candidate to the backend
owner (LG-104 WP1/WP2/WP3). It does **not** change the contract version and does
not declare any new provider verified, executable, or model-tested.

## 1. Provider presets (UI-only mapping, no new provider database)

The dropdown is a preset over the existing Connection entity. It maps to the
existing `backend` field plus the optional LG-104 non-secret fields. Presets are
not persisted as a second provider list.

| UI label | `backend` | `auth_mode` | Required primary input | Default model | Default base URL | Default-eligible now |
|---|---|---|---|---|---|---|
| Gemini API | `gemini` | `api_key` | API key | `gemini-3.8-flash` | — | no |
| Vertex AI — Express (API key) | `vertex` | `api_key` | API key | `gemini-3.8-flash` | — | no |
| Vertex AI — Project + ADC | `vertex` | `adc` | Project ID + Location | `gemini-3.8-flash` | — | no |
| DeepSeek (OpenAI-compatible) | `openai-compat` | `proxy_api_key` | API key | `deepseek-v4-flash` | `https://api.deepseek.com/v1` | yes (existing path) |
| LiteRT (local model) | `litert` | `none` | Model file path + CPU/GPU/NPU (default GPU) | none (the file is the model) | — | no |
| Custom OpenAI-compatible (legacy) | `openai-compat` | `proxy_api_key` | existing key/endpoint | existing model | existing base URL | only if backend declares `executable` |
| Existing connection (unrecognized provider) | unchanged | unchanged | unchanged | unchanged | unchanged | only if backend declares `executable` |

DeepSeek is deliberately labelled “OpenAI-compatible”, not SDK-native. The SDK
class is `LocalOpenAIAgentConfig`; the product loopback proxy injects the key at
run time.

SDK mapping (from LG-105 audit, installed `google-antigravity==0.1.22`):

* Gemini API / Vertex Express / Vertex ADC → `LocalAgentConfig`
  (`api_key`, or `vertex=True` with `project`/`location` and ADC);
* DeepSeek / custom OpenAI-compatible → `LocalOpenAIAgentConfig`;
* LiteRT → `LiteRTAgentConfig` (`model_path`, `backend`).

## 2. Exact optional wire fields

### Response: `ConnectionView`

Existing fields stay unchanged. Additive and optional:

```ts
interface ConnectionView {
  // ...existing id/title/enabled/revision/content_hash/backend/model/
  // base_url/credential_ref/credential/references...
  auth_mode?: 'api_key' | 'adc' | 'proxy_api_key' | 'none' | null
  project?: string | null
  location?: string | null
  model_path?: string | null
  litert_backend?: 'CPU' | 'GPU' | 'NPU' | null
  capabilities?: {
    configurable?: boolean | null
    testable?: boolean | null
    executable?: boolean | null
    vendor_verified?: boolean | null
  } | null
}
```

`null`/absent on an old connection means “not stored / not declared”. The UI
infers the preset from the fields that already exist and never rewrites the
record on load.

### Create: `POST /api/v1/settings/connections`

Existing request fields remain. Additive optional fields:

```json
{
  "auth_mode": "api_key | adc | proxy_api_key | none",
  "project": "string | null",
  "location": "string | null",
  "model_path": "string | null",
  "litert_backend": "CPU | GPU | NPU | null"
}
```

Omitted means “not provided”; `null` means “explicitly empty”. The UI currently
sends `auth_mode` plus all provider fields for Gemini, Vertex Express, Vertex ADC
and LiteRT. For DeepSeek it omits all optional provider fields, preserving the
legacy proxy default. `credential_value` remains write-only.
`credential_ref` is generated as `<connection-id>-key` for new API-key presets and
is hidden under Advanced.

### Update: `PATCH /api/v1/settings/connections/{id}`

Existing request fields remain. Additive optional fields:

```json
{
  "backend": "string",
  "auth_mode": "api_key | adc | proxy_api_key | none",
  "project": "string | null",
  "location": "string | null",
  "model_path": "string | null",
  "litert_backend": "CPU | GPU | NPU | null"
}
```

* `backend` is needed so an existing connection can switch preset without
  creating a new record. The current backend cannot change `backend`; the
  backend owner must add it and validate the complete post-update state.
* Omitted field = preserve; `null` = clear. The UI always sends provider fields
  when the target preset or the existing record uses them. It omits them for an
  untouched old `openai-compat` record, so that path remains compatible with the
  current strict request model.
* `credential_action: "keep"` plus no `credential_value` must keep the existing
  secret. Switching provider must not delete it.
* `credential_action: "remove"` (or the existing DELETE credential route) remains
  the **only** explicit secret removal path.

### Compatibility note

The current backend request models use `extra="forbid"`. Until WP1 adds these
fields, new Gemini/Vertex/LiteRT saves will receive a real 422 and the UI will
show that error. This is intentional: the candidate does not fake success or
silently strip the provider configuration. Untouched DeepSeek saves avoid the
new fields so the existing path is not broken.

## 3. Capability semantics (never one boolean)

Capabilities are separate facts and are never inferred from one another:

* `configurable` — backend accepts and saves the provider configuration;
* `testable` — Test Connection can run its real layers;
* `executable` — product executor may use it, and it may be a Saved default;
* `vendor_verified` — evidence of a real vendor call exists.

Backend-declared values override the frontend preset fallback. The UI fallback
only preserves the already-existing DeepSeek execution path; it does not mark
Gemini/Vertex/LiteRT executable or vendor-verified. Passing tests or saving never
sets `vendor_verified`.

UI behavior driven by these flags:

* Defaults selector lists only `enabled && capabilities.executable === true`.
* `capabilities.testable === false` disables Test with an honest reason.
  `null`/absent leaves the existing Save→Test path available for backend binding.
* “vendor verification recorded” is shown only when `vendor_verified === true`.
  Absence is shown as “not declared”, never as a pass.

Backend requirements:

* return `capabilities` on list/detail (and ideally on create/update responses);
* keep the saved-default restriction executable-only;
* do not treat SDK support as executable or vendor verification;
* after native execution is approved, flip `executable`/`vendor_verified` only
  with its own evidence and budget/stop-gate work.

## 4. Credential rules

* API key input is write-only; empty means keep the current secret.
* No key is requested for Vertex ADC or LiteRT; their real prerequisites are
  shown instead (ADC on the host; `litert-lm` package/model file/CPU-GPU-NPU).
* Changing provider does not delete a stored secret. The old
  `credential_ref` is preserved; secret removal is an explicit Advanced action.
* If the new auth mode is `adc`/`none`, the backend must either accept and
  preserve an existing inert `credential_ref` without using it, or explicitly
  define a safe preservation rule. It must never silently delete the secret.
* Existing `openai-compat` connections, custom endpoints, models, refs and
  defaults load unchanged. A custom endpoint that is not
  `https://api.deepseek.com/v1` maps to the legacy/custom preset rather than
  being relabelled DeepSeek.

## 5. Save → Test contract

* New connections: Test is disabled until saved.
* Existing connections: any dirty field (including a newly typed secret)
  disables Test until Save; Test only targets the persisted revision.
* No request runs on load, provider selection, connection selection, default
  change or save.
* Test sends `expected_revision` and currently `allow_network: true` from the
  explicit click. The existing request field is retained; its policy is pending
  the user’s answer about a manual-test network budget.
* Test results stay bound to connection revision + credential version. The UI
  shows a stale marker when either changes.
* Raw layers/diagnostics are collapsed under Details; overall/model/host/finish
  time stay visible. Saving is never presented as passing.

Pending policy binding (do not decide in backend integration without the user):

1. **Native Task execution/defaults**: if approved, backend declares
   `executable` and implements executor/accounting/stop behavior. The UI needs no
   new control; it will automatically allow defaults for executable connections.
2. **Manual Test network budget**: if explicit tests may consume one call outside
   the current cap-0 policy, the existing explicit click already sends
   `allow_network: true`; backend must reserve honestly and report blocks. If not,
   backend should return static/blocked layers or declare `testable` accordingly.
   A later tiny binding change may add a dedicated
   `manual_test_network` capability if the policy needs to distinguish it from
   general provider testability.

## 6. Preserved product behavior

* Settings → Models & Providers remains the only Connection management entry.
* LG-103 stable `settings:connection:<id>` target, unknown-target miss, no
  silent alternate selection, and cross-connection late-response guard remain.
* Team member gate remains: a member never mounts Models/Connections, receives
  no configuration fetch and sees the administrator-managed notice + My Account.
* Connection list, default role choices (in collapsed Advanced/Defaults),
  Accounts and My Account remain.
* No global navigation/route API change, no new connection wizard, no wide
  platform layout.
