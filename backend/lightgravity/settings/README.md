# Settings backend (LG-025 / LG-104 / LG-109 / LG-111)

Store-authoritative model settings: provider Connections, `SETTINGS.md`
defaults, controlled credentials and layered saved/draft connection tests.
LG-104/LG-109 add optional non-secret provider fields, separate capability
facts and the transient `POST /settings/connections/test-draft` endpoint.
LG-111 adds the read-only persisted `last_test` summary and the protected
`DELETE /settings/connections/{id}` endpoint frozen in docs/08 §18.4.
See [docs/07](../../../docs/07-settings-and-models.md),
[docs/08 §4.3/§6.5/§8.1](../../../docs/08-interface-contract.md).

This package does **not** own `lightgravity.api`; it ships a router *factory*
for LG-012 to mount.

## Layout

| File | Purpose |
|---|---|
| `models.py` | Private value types (`Connection`, `GlobalSettings`, `CredentialStatus`, `PinnedConnection`, `ConnectionTestResult`). Not added to frozen `contracts`. |
| `repository.py` | `ConnectionRepository`: reads/writes `resources/connections/<id>.md` and `settings/SETTINGS.md` through the LG-004 `Store`; validates the registered provider/auth matrix. |
| `secret_store.py` | `FileSecretStore` (owner-only `0700/0600`, atomic, versioned) and `SecretStoreCredentialResolver` (store → environment), implementing the LG-006 `CredentialResolver`. |
| `service.py` | `ConnectionService`: defaults legality, reference blocking, cross-file compensation, credential lifecycle, revision pinning. |
| `testing.py` | `ConnectionTester` + `ConnectionTestLog`: layered saved tests and transient draft tests. OpenAI-compatible uses the LG-006 proxy; Gemini/Vertex use the installed SDK's real config with one minimal request; LiteRT is static-only. |
| `router.py` | `build_settings_router(service, *, tester=None)`: the settings HTTP routes, including the protected draft-test and connection-delete envelopes. |

## Guarantees

- **Single authority**: Connections and `settings/SETTINGS.md` are the same
  facts the adapter compiler reads; no second provider/model DB.
- **No secret leakage**: values only exist in `Secret` (redacted `repr`), are
  stored `0600` in `LIGHTGRAVITY_SECRET_STORE` (gitignored, outside the source
  tree in production), and never appear in Connection/SETTINGS Markdown,
  responses, diagnostics, evidence or logs. Environment credentials are
  read-only and reported by source.
- **Optimistic concurrency**: writes carry `expected_revision`; a stale write
  raises the frozen `revision_conflict` (409). Test requests can also pin the
  revision they were made against.
- **No dangling defaults**: a default must resolve to an existing, enabled,
  **executable** connection. Only the existing DeepSeek host on the
  `openai-compat` path is executable/default-eligible; an arbitrary custom host
  (even with the same backend enum) is configurable/testable but not executable.
  Disabling a default connection requires clearing the default in the same call
  (`clear_defaults=true`); the settings write is rolled back if the later
  connection write fails.
- **Reference blocking**: a credential still referenced by a connection cannot
  be deleted (`reference_invalid`). A Connection still referenced by a default
  role or an Agent cannot be deleted; the server check and unlink share the
  store's entity lock, and no other reference is rewritten.
- **Safe list summary**: `ConnectionView.last_test` is a read-only projection of
  the latest saved-test diagnostic (`test_id`/`overall`/`finished_at`/revision/
  credential version). It is never a second Connection state and never contains
  a draft result, layer details, request body or secret.
- **Pinning**: `pin_connection` / `resolve_default` return a `PinnedConnection`
  (revision + content hash + credential version). Later default/connection edits
  do not mutate it; `pinned_is_current` detects drift so active members are not
  hot-swapped.
- **Honest layers**: `config_parse`, `credential` and the real `runtime_network`
  result are separate from the SDK `capability` *declaration*
  (`adapter_capabilities`); `tool_probe` / `structured_output` stay separate and
  are reported `skipped` (not fabricated). A result is `stale` once its
  connection revision or credential version changes. Draft results carry
  `draft=true`, nullable saved identity, and are never persisted.
- **Separate facts**: `configurable` (may save), `testable` (may run test
  layers), `executable` (may run Tasks/be a default) and `vendor_verified`
  (real vendor evidence) are never inferred from one another.

## First-version limits

- Gemini API, Vertex Express, Vertex Project + ADC and LiteRT are saveable and
  testable, but only `openai-compat` (DeepSeek) is executable/default-eligible.
  `model` defaults to `deepseek-v4-flash`, `base_url` to
  `https://api.deepseek.com/v1` for the executable path.
- LiteRT is static-only: package presence, an allowed model path under the
  configured workspace root and SDK config construction. It never installs,
  downloads, loads or infers a model.
- Vertex ADC is environment-owned. Static tests never run gcloud or request
  metadata; an explicit network test only proceeds when a local ADC credential
  file is detected (or a test injects the prerequisite).
- A draft test may reuse an existing secret only with the saved id + current
  revision + unchanged backend/auth/credential-recipient endpoint. Changing that
  identity requires a fresh write-only key; the old secret is never sent to the
  new target. Draft tests never write a Connection, secret, default, diagnostic,
  Task/Run or SDK config.
- The store is local and permission-protected; it is **not** encrypted at rest.
- `tool_probe` / `structured_output` are not executed in LG-025; they require an
  isolated SDK session with its own temp workspace and budget.
- `DELETE /settings/connections/{id}` requires `{expected_revision}` and
  returns `{deleted:true,id}`. Missing rows are 404 and stale revisions are 409.
  It deliberately does not delete the secret-store value (it may be shared) and
  does not modify defaults, Agent references or other entities.

## Integration work for other tasks

Recorded here instead of editing shared/frozen files (docs/08 §11):

- **LG-012 (API)**: mount `build_settings_router(service, tester=tester)` under
  `/api/v1`; build `ConnectionService(store, secret_store=FileSecretStore(
  Settings.from_env().secret_store))`; add an exception handler for
  `AppError` (already present in `api.app`). The additive `PATCH /settings`
  route sets the coordinator/worker defaults; the frozen table lists
  `GET /settings`, so confirm the endpoint list with LG-012. LG-012/LG-020 must
  also enforce the local access token (`X-LG-Token`) on all credential routes;
  LG-025 already rejects non-loopback browser origins and sends
  `Cache-Control: no-store`.
- **LG-007 / executor wiring**: pass `service.credential_resolver` as the
  `AntigravityExecutor(..., credential_resolver=...)` resolver so the executor
  and the settings store share one credential reference without copying secrets.
- **LG-026 (frontend)**: consume the router's public views; never cache secrets
  in local/session storage; treat `credential.configured`/`source` only. Use
  `expected_revision`/`ETag` for edits and show old test results as stale.
- **contracts**: LG-109 owns the `1.17.0` additive MINOR constant. The private
  types in `models.py` remain the implementation value types; root PM owns the
  normative Markdown registration.
