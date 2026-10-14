# Settings backend (LG-025)

Store-authoritative model settings: first-version DeepSeek connection,
`SETTINGS.md` defaults, controlled credentials and layered connection tests.
See [docs/07](../../../docs/07-settings-and-models.md),
[docs/08 §4.3/§6.5/§8.1](../../../docs/08-interface-contract.md).

This package does **not** own `lightgravity.api`; it ships a router *factory*
for LG-012 to mount.

## Layout

| File | Purpose |
|---|---|
| `models.py` | Private value types (`Connection`, `GlobalSettings`, `CredentialStatus`, `PinnedConnection`, `ConnectionTestResult`). Not added to frozen `contracts`. |
| `repository.py` | `ConnectionRepository`: reads/writes `resources/connections/<id>.md` and `settings/SETTINGS.md` through the LG-004 `Store`; validates first-version backend rules. |
| `secret_store.py` | `FileSecretStore` (owner-only `0700/0600`, atomic, versioned) and `SecretStoreCredentialResolver` (store → environment), implementing the LG-006 `CredentialResolver`. |
| `service.py` | `ConnectionService`: defaults legality, reference blocking, cross-file compensation, credential lifecycle, revision pinning. |
| `testing.py` | `ConnectionTester` + `ConnectionTestLog`: layered tests reusing the LG-006 `LocalAuthProxy`; results bound to connection revision + credential version. |
| `router.py` | `build_settings_router(service, *, tester=None)`: the settings HTTP routes. |

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
  verified (`openai-compat`) connection. Disabling a default connection requires
  clearing the default in the same call (`clear_defaults=true`); the settings
  write is rolled back if the later connection write fails.
- **Reference blocking**: a credential still referenced by a connection cannot
  be deleted (`reference_invalid`).
- **Pinning**: `pin_connection` / `resolve_default` return a `PinnedConnection`
  (revision + content hash + credential version). Later default/connection edits
  do not mutate it; `pinned_is_current` detects drift so active members are not
  hot-swapped.
- **Honest layers**: `config_parse`, `credential` and the real `runtime_network`
  result are separate from the SDK `capability` *declaration*
  (`adapter_capabilities`); `tool_probe` / `structured_output` stay separate and
  are reported `skipped` (not fabricated). A result is `stale` once its
  connection revision or credential version changes.

## First-version limits

- Only `openai-compat` (DeepSeek) may be saved as an executable connection;
  `gemini`/`vertex` are rejected as unverified. `model` defaults to
  `deepseek-v4-flash`, `base_url` to `https://api.deepseek.com/v1`.
- The store is local and permission-protected; it is **not** encrypted at rest.
- `tool_probe` / `structured_output` are not executed in LG-025; they require an
  isolated SDK session with its own temp workspace and budget.
- Connection deletion is out of scope: the frozen v1 API has no delete-connection
  endpoint and the `Store` protocol has no delete, so LG-025 supports disable +
  credential removal instead.

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
- **contracts**: no new DTOs were added; the private types in `models.py` are the
  candidate wire shapes for a later additive contract change if LG-012/LG-026
  want them frozen.
