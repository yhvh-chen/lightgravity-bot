# LG-236 Delivery — Google native ASR backend

Status: **backend provider/runtime implemented on an isolated local branch; ready for LG-238 serial assembly**. No UI, app/bootstrap/health/constants, docs-version, deploy, push, release or production-service change. Old Reader quality history remains FAILED and unchanged.

## 1. Exact source revision

- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-backend-20261018`
- Branch: `dev/google-native-asr-backend-20261018`
- Commit: `26a87adf950adab1aa146e3b36c710df3bceb202`
- Tree: `271502bfa004544d230379155ed3a81f8bfede6c`
- Parent: `39ab93963006a796222cfa358b0b12604a6c0494`
- Worktree status after commit: clean.
- No root source/index/PM-dirty/production service/account/data edit; no deploy/push/release.
- No SDK, model weight, torch, numpy or transformers installation. `uv run python` check: `torch False`, `numpy False`, `transformers False`.

## 2. Files delivered (owned scope)

| file | change |
|---|---|
| `backend/lightgravity/asr/google_native.py` | **new**: native interactions body, MIME sniffing, standard-library HTTPS transport, completed `model_output` text extraction, usage/latency, error classes |
| `backend/lightgravity/asr/config.py` | additive Google block/config parser, provider dispatch, base URL/model/credential-ref validation; legacy `parse_block` untouched |
| `backend/lightgravity/asr/service.py` | Google settings view/PUT, `FileSecretStore` write-only secret handling + conflict compensation, attemptable availability, native transcription, post-dispatch stop semantics, Google machine provenance |
| `backend/lightgravity/asr/router.py` | additive provider/Google write fields; provider-specific bounds remain enforced in the service |
| `backend/lightgravity/asr/__init__.py` | additive `secret_store` / `google_transport` builder arguments |
| `backend/lightgravity/settings/service.py` | lazy ASR service now receives the existing controlled `FileSecretStore` |
| `tests/asr/fixtures/lg235_h1_response.json` | recorded LG-235 H1 response fixture (verbatim, non-secret) |
| `tests/asr/fixtures/lg235_h2_response.json` | recorded LG-235 H2 response fixture (verbatim, non-secret) |
| `tests/asr/test_google_native.py` | parser/provider/settings/secret/error/preflight/stop/import boundary tests |
| `tests/asr/test_google_source_pipeline.py` | actual intake worker → Google transcript → receipt/index/formal/idempotency boundary test |

Not modified: `api/app.py`, `api/bootstrap.py`, `api/health.py`, `contracts/constants.py`, docs/README/PROJECT, frontend, `provider_contract.py` semantics.

## 3. Implemented contract facts

- Legacy blocks without `provider` still parse as `eg2-reader` + `inprocess`; legacy path/thread/30-second behavior and parser are unchanged.
- Google blocks use `provider="google-native"`, `runtime="google-native"`; legacy model/device/thread fields and numeric `max_audio_seconds` are rejected. `max_audio_seconds: null` is accepted.
- Google defaults/limits: model `gemini-3.8-flash`; base `https://generativelanguage.googleapis.com/v1beta`; endpoint `/v1beta/interactions`; raw audio default `10,000,000` / max `14,000,000`; timeout `180` (`30..600`); read-only request limit `20,000,000`; local concurrency `1`.
- Google credentials are write-only via the existing `FileSecretStore`; omitted ref/value retain the stored secret; explicit `null`/empty is `422`; revision conflict rolls the secret write back and never silently replaces it. The product never reads `LG_GOOGLE_ASR_API_KEY` or another environment key for Google.
- `GET /settings.english_asr` returns provider/model/base_url/credential_configured/Google limits but no secret, credential ref, path, request body or audio.
- Saving performs local validation only: no network, no key verification, no inference, no automatic reprocessing. `available=true` means attemptable, not verified.
- Request: one inline `POST`, `x-goog-api-key` header only, fixed `google-native-transcribe-v1` prompt, base64 audio, explicit supported MIME. No Files API, SDK, fallback, model roulette or automatic retry.
- Response: only completed `steps[type="model_output"].content[type="text"].text`; thought steps/signatures ignored. Literal model text is preserved (the recorded H2 `thought` prefix is kept and disclosed as model output).
- Errors map to `asr_auth_failed` (401/403), `asr_rate_limited` (429), `asr_model_unavailable` (404), `asr_provider_unavailable` (5xx/connect), `asr_invalid_request` (400/413/422/local MIME/body), `asr_refused`, `asr_empty_response`, `asr_response_invalid`; post-dispatch timeout/cancel/connection loss is `asr_stop_unconfirmed` with `stop_confirmed=false` and no late body write.
- Machine provenance contains Google engine/provider/model/endpoint/prompt version/model version, audio SHA/MIME/bytes, request bytes, latency and non-secret usage. No fake encoder/reader/timestamp/language detection.
- The existing source worker writes the machine transcript to the canonical machine body, receipt and index; human formal content is not overwritten; disable/reload keeps history; duplicate upload does not make a second ASR call.
- No new lifetime call cap. `max_asr_calls=1` per job remains the existing one-attempt intake boundary.

## 4. Verification (real commands, current commit)

All commands run inside the worktree:

| command | result |
|---|---|
| `uv run pytest -q tests/asr` | **80 passed, 2 skipped**, exit 0 |
| `uv run pytest -q tests/asr tests/settings/test_connection_service.py tests/api/test_settings_integration.py tests/api/test_health.py tests/integration/test_lg162_english_asr_assembly.py` | **103 passed, 2 skipped**, exit 0 |
| `uv run pytest -q tests/sources/test_intake_worker.py tests/sources/test_intake_jobs.py tests/sources/test_receipt_branches.py` | **35 passed**, exit 0 |
| `uv run mypy` | **Success: no issues found in 172 source files**, exit 0 |
| `git diff --check` | exit 0 |
| `uv run python` torch/numpy/transformers presence check | all `False`; no SDK/weight/torch install |

Focused tests cover: legacy compatibility; Google view/write-only secret; environment-key non-use; revision conflict secret preservation; invalid legacy fields; base URL/model/limits; H1 request shape/provenance; H2 thought-step ignore + literal text retention; HTTP error classes; malformed/empty/refused responses; unknown MIME/raw/request limits; pre-dispatch vs post-dispatch cancel/timeout; no torch/numpy/Reader import; actual source pipeline, formal retention, disable/reload and idempotency.

Not run in LG-236 (by scope): full backend suite, frontend tests/build, browser/Playwright, real Google call, live live-transport smoke, deployment. LG-239 owns independent real browser/provider QA.

## 5. LG-238 wiring / checks

The current app base already mounts the protected ASR router; **no new endpoint implementation is required from 238**:

- `backend/lightgravity/api/app.py` already includes `build_english_asr_router(connections.english_asr, require_admin=None, safe_origin=english_asr_safe_origin)` under `API_PREFIX`. Keep that one instance.
- `connections.english_asr` now lazily builds with `secret_store=self._secrets`; therefore GET `/settings`, PUT `/settings/english_asr`, health and source intake all resolve the same service. Do not build a second Google-only service.
- If another bootstrap path builds `build_english_asr_service(...)` directly, pass `secret_store=connections.secret_store` (or the existing `FileSecretStore`) so Google credentials resolve. Do not pass an environment key.
- `api/health.py` needs no code change: `english_asr_capability(connections.english_asr).available` is true for enabled + resolvable-secret Google without torch.
- `contracts/constants.py`: bump `CONTRACT_VERSION` to `1.22.0` only after 236+237 assembly and focused checks pass; then update `/health` contract and docs/README/PROJECT status as 238 owner. Do not change 236 semantics.
- Suggested 238 backend check:
  `uv run pytest -q tests/asr tests/settings/test_connection_service.py tests/api/test_settings_integration.py tests/api/test_health.py tests/integration/test_lg162_english_asr_assembly.py && uv run mypy`
- Add the 237 frontend type/test/build checks and LG-239 real browser/provider verification separately.

### 237/238 write-shape caution

- First Google save must explicitly send `provider: "google-native"`; `runtime` may be omitted.
- For Google saves, **omit** `model_dir`, `reader_dir`, `device`, `threads`; `max_audio_seconds` must be omitted or explicitly `null` (a number is `422`).
- Blank credential inputs should be omitted to retain the stored secret. Explicit `null`/empty is rejected; never render or return the stored ref/value.
- `expected_revision` must come from `english_asr.revision`.

## 6. Known facts / limitations / defect report

- **No newly found blocking backend defect** in this package. The default live `HttpConnectionTransport` was intentionally not exercised against Google here; tests use recorded LG-235 responses and a labelled fake transport. LG-239 must make the first real call.
- **Retained provider defect/limitation:** recorded H2 `model_output` text begins with the literal word `thought`. LG-236 preserves it as untrusted machine text (does not strip it, does not rewrite names/numbers). The real thought step is ignored. Reader/Google quality history is not re-judged.
- **Retained provider observation:** LG-235 model metadata did not list `interactions` in `supportedGenerationMethods` even though the native request returned 200. LG-236 does not assume it for other models/endpoints.
- Secret + settings are two existing files; LG-236 uses compensation (restore/delete secret on settings write failure) rather than claiming a cross-file transaction. Concurrent same-ref rotations still inherit the existing local-store compensation limits.
- Local concurrency-busy is reported as `unavailable/asr_unavailable` without dispatch/provider usage; it is not retried.
- LG-235's two sample requests are not product budget/caps; no new lifetime cap was added.
- Unknown/unverified: live key validity, quota, error rates, long/real-human audio, dedicated transcribe model, timestamps/diarization, deployment. Old Reader FAILED and §21 limitations remain.

## 7. Safety / credentials

No real Google key, request audio, headers or base64 is present in source, fixtures, logs, this report or commits. The fixture files are the recorded non-secret LG-235 response JSONs. `LG_GOOGLE_ASR_API_KEY` is not used by product code; the fake tests use only `test-google-key-not-real` / `fake-google-key`.
