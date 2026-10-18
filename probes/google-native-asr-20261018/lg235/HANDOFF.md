# LG-235 HANDOFF — Google native ASR contract/prototype

Status: **ready for LG-236 (backend) + LG-237 (UI) parallel work**, then LG-238 serial integration. LG-235 did **not** implement product backend/UI, change `CONTRACT_VERSION` (stays `1.21.0`), deploy, push, or touch root services/data.

## Read first

- Contract: [`CONTRACT.md`](CONTRACT.md) and canonical [`docs/08 §23`](../../../docs/08-interface-contract.md).
- Probe evidence: [`raw/probe-summary.json`](raw/probe-summary.json), [`REPORT.md`](REPORT.md).
- Frozen shared code: `backend/lightgravity/asr/provider_contract.py`, `frontend/src/api/googleAsr.ts`.
- Existing ASR seams: `backend/lightgravity/asr/service.py`, `router.py`, `settings_store.py`, `sources/worker.py`.

## Parallel owners (do not cross)

| owner | owns | must not touch |
|---|---|---|
| **LG-236 backend** | `backend/lightgravity/asr/**` (config/service/router/settings_store + new Google native client/runtime; `provider_contract.py` additive only), `backend/lightgravity/sources/worker.py`, `backend/lightgravity/settings/service.py`, `tests/asr/**`, relevant `tests/sources/**` | `api/app.py`, `api/bootstrap.py`, `api/health.py`, `contracts/constants.py`, docs version/status, README/PROJECT, frontend |
| **LG-237 UI** | `frontend/src/**` (Settings English ASR form, `api/englishAsr.ts`, additive use of `api/googleAsr.ts`, Files/Chat receipt UI, styles, frontend tests) | backend, app/bootstrap/health/constants, docs version/README/PROJECT |
| **LG-238 integration** | `backend/lightgravity/api/app.py`, `api/bootstrap.py`, `api/health.py`, `contracts/constants.py`, `docs/08` version/status, `README.md`, `PROJECT.md`, `tests/integration/**`, e2e assembly | 236/237 internal implementation semantics |

Shared-file conflicts are resolved only by LG-238. Both 236 and 237 use separate worktrees.

## LG-236 concrete checklist

1. Extend `asr/config.py`/`settings_store.py` with `provider` (`eg2-reader` default for old blocks; `google-native` + `runtime=google-native`). Keep old fields/behavior intact.
2. `GET /settings.english_asr` additive fields: `provider`, `model`, `base_url`, `credential_configured`, Google `limits` (`max_audio_seconds:null`, `max_request_bytes:20000000`, etc.). Never return secret/ref.
3. `PUT` Google validation: model/base_url/secret write-only, host/path exact, no `model_dir`/`reader_dir`/`threads`/`device`, no numeric `max_audio_seconds`. Persist secret via existing `FileSecretStore`; no env key. Saving = no network/inference.
4. Implement native client with standard HTTP (httpx/stdlib): `POST <base>/interactions`, header `x-goog-api-key`, fixed prompt, inline base64 audio, response `steps[type=model_output].content[type=text].text`. No SDK/Files API/fallback/retry.
5. Double preflight: raw `max_audio_bytes` and serialized JSON `<= 20_000_000` (base64 expansion). Record `usage`/latency/request bytes in `AsrOutcome.machine`.
6. Error mapping per CONTRACT §7; post-dispatch timeout/cancel => `extracting` + `asr_stop_unconfirmed`, no late write. Keep `max_asr_calls=1`/job, no product total cap.
7. Preserve `build_english_asr_service` / `build_english_asr_router` / `english_asr_capability` / `transcribe(...)` seam; 238 should only wire it.
8. Add focused tests: legacy block unchanged, Google view/PUT validation, secret write-only/no env, preflight/base64 limit, response parsing/thought ignore, 401/429/5xx/timeout classes, no torch/numpy/Reader import in Google mode, no fallback.

## LG-237 concrete checklist

1. Show provider-aware Settings form from existing `GET /settings.english_asr`: legacy EG2 fields vs Google native fields. Do not probe new endpoints.
2. Google fields: model (default `gemini-3.8-flash`), base_url (default `https://generativelanguage.googleapis.com/v1beta`), write-only API key/credential ref, timeout/byte limits. Never render a stored key/ref; blank = retain.
3. Save via existing `PUT /settings/english_asr` with `english_asr.revision` as `expected_revision`. UI wording: “configured / capability not verified”; saving does not run transcription.
4. Google labels: native Google transcription, English mainline, no Reader 30-second wording, no timestamps/diarization claim. Legacy Reader quality FAILED history remains visible/honest where relevant.
5. Upload/receipt/Files/Chat: machine transcript is untrusted derived text; failures/empty/refused show real reason; no fake success/fallback. History remains readable after disable/reload.
6. Keep desktop/narrow layouts, member/admin visibility, busy/error/reload states; typecheck/build/local tests only.

## LG-238 integration checklist

1. Wire 236 service/router into `api/app.py`/`bootstrap.py`/`health.py`; do not reimplement provider logic.
2. Keep `CONTRACT_VERSION=1.21.0` until public backend runtime actually implemented and assembled; then bump to `1.22.0` and update `/health`, docs/08 status, README/PROJECT.
3. Verify Google mode works without torch/numpy/transformers/Reader/192.168.8.12; legacy EG2 config still parses unchanged.
4. Run focused backend + frontend type/build + contract tests; leave independent real-browser/version QA to LG-239.
5. Do not deploy, push, create Cloud resources or touch root PM dirty/docs/accounts.

## Frozen facts 236/237 must not silently change

- Provider values: `eg2-reader`, `google-native`; runtimes: `inprocess`, `google-native`.
- Defaults: model `gemini-3.8-flash`; base `https://generativelanguage.googleapis.com/v1beta`; endpoint `/v1beta/interactions`; request limit `20,000,000`; raw audio default `10,000,000`, max `14,000,000`; timeout default `180`, range `30..600`; concurrency `1`.
- Prompt/version: `google-native-transcribe-v1`, fixed verbatim prompt in `provider_contract.py`.
- Reasons: existing 1.20 set + `asr_auth_failed`, `asr_rate_limited`, `asr_model_unavailable`, `asr_provider_unavailable`, `asr_invalid_request`, `asr_refused`, `asr_empty_response`, `asr_response_invalid`; config reasons `credential_missing`, `model_unavailable`.
- No fallback, no model roulette, no automatic retry, no Files API, no env product credential.
- Dedicated `gemini-3.5-transcribe` is official but **not called/assumed enabled**; only explicit admin config + real success counts.

## Probe result summary

- H1: HTTP 200, 6.078 s, usable transcript; existing normalizer WER 0.04, key facts 5/6 (`April ninth` surface becomes `April 9th`).
- H2: HTTP 200, 7.221 s, raw text starts with literal `thought`; WER 0.17391, key facts 3/5 (`Lena`→`Lina`, `November twelfth`→`November 12th`). Eastside Clinic preserved.
- Old Reader labels unchanged: H1 WER 0.08/5-of-6 (Cedar Island lost), H2 0.21739/3-of-5. Google is a separate scoped prototype, not a quality pass.
- No third inference; no response/quality artifact was rewritten. See REPORT for the one-time harness parse note.

## Do not

- Do not store the real Google key in repo, docs, logs, commits, Settings root or probe files. `LG_GOOGLE_ASR_API_KEY` is probe-only.
- Do not import the frozen remote ASR candidate (`33b73b3`) or mix its 1.21-divergent docs.
- Do not edit root task statuses/PM docs, deploy/push/release, or call production accounts/services.
