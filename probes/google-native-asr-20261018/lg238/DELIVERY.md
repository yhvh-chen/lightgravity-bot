# LG-238 Delivery — Google native ASR serial integration (contract 1.22.0 candidate)

Status: **236 backend + 237 UI assembled and locally checked; implemented 1.22.0 candidate, pending LG-239 independent version/browser/real-Google QA.** Not deployed, not pushed, no release/Cloud resource. Public 8123/5173 remains 1.20.0. Old Reader quality gate stays **FAILED** and unchanged; no Google quality pass is claimed.

## 1. Frozen source identity

- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-integrated-20261018`
- Branch: `integration/google-native-asr-20261018`
- Base: `26a87adf950adab1aa146e3b36c710df3bceb202` (LG-236; backend tree below)
- **Frozen candidate source commit: `ecda49f692097b07d6f574652f9ed72b6387919a`**
- **Candidate tree: `d96f22b6d5acbb509cb9cbf6c232d557215af19b`**
- Parent chain: `ecda49f` → `b5b7e39` (exact cherry-pick of LG-237 `f17b0d1bb4319e07393a5a21f9a08983ba8d9ee4`) → `26a87ad` (LG-236) → `39ab939` (LG-235)
- Subtree identities at the frozen commit:
  - `backend`: `6cc2a72d74cd274b5d68a6e47ef423b7395f376b`
  - `frontend`: `2526bbf54770a5302462630bb2f7d17d6d12ddbd` — **identical to LG-237 `f17b0d1:frontend`**
  - `tests`: `e9ebfaf72946ae8af50f6f5772c401f0e3cf129a`
  - `docs`: `37fbb25eb4fe3cf53a7962a6abf510723264adae`
- Relative to LG-236, the backend subtree differs only in `backend/lightgravity/api/health.py` (provider-aware capability comment) and `backend/lightgravity/contracts/constants.py` (1.22.0 + changelog comment). No 236 provider/service/native-client semantics were changed.
- Worktree clean after the source commit. This report is a separate docs-only commit on top; the frozen candidate identity above is immutable and was captured **before** writing/committing this report.

## 2. What LG-238 changed (integration-owned files only)

| file | change |
|---|---|
| `backend/lightgravity/contracts/constants.py` | `CONTRACT_VERSION = "1.22.0"` + §23 assembly provenance comment; `SCHEMA_NAMESPACE`/`API_PREFIX` unchanged |
| `backend/lightgravity/api/health.py` | capability comment now states legacy vs Google attemptable semantics (no logic change) |
| `tests/integration/test_lg238_google_asr_assembly.py` | **new** 5-test assembled-app suite (lazy secret-store wiring, 1.22 view/PUT shape, invalid Google fields, real intake worker + fake transport, fresh-interpreter import boundary) |
| `tests/contracts/test_contracts.py` | contract assertion/comment → `1.22.0` |
| `tests/api/test_source_refs_messages.py` | stale `/health.contract_version` literal → `1.22.0` |
| `docs/08-interface-contract.md` | frontmatter/banner/checklist/changelog/§23 status/§23.12 → implemented 1.22.0 candidate pending LG-239; all §18–§22 text and old Reader FAILED preserved |
| `docs/07-settings-and-models.md` | new §8 provider-aware English ASR usage (legacy vs Google native, write-only key, limits, no fallback, deployment boundary) |
| `README.md` | 1.22 candidate banner, bounded-media limitation, docs table; deployed 1.20.0 kept distinct |
| `PROJECT.md` | one minimum 2026-10-18 decision-log entry for the 1.22 candidate (root PM still owns root PROJECT) |

Not touched: `backend/lightgravity/api/app.py`, `api/bootstrap.py` (no change needed — the protected router is already mounted and `ConnectionService.english_asr` is the single lazy service with `FileSecretStore` injected by 236), `backend/lightgravity/asr/**` semantics, 237 frontend sources, root `PROJECT.md`/docs/index, services/accounts/data, deploy/push.

Wiring facts verified:
- `api/app.py` mounts exactly one `build_english_asr_router(connections.english_asr, ...)`; `/settings`, `/health` and the intake worker resolve the same instance.
- No other bootstrap path builds `build_english_asr_service(...)`; the only direct builders are tests.
- `settings/service.py` lazy builder passes `secret_store=self._secrets`; the new integration test proves a Google key can be saved through the real API and read back as `credential_configured` with no configure step.
- Google availability is true without `torch`/`numpy`/`transformers`/Reader; fresh-interpreter subprocess asserts none of them (and `lightgravity.asr.runtime`) are imported by `create_app` + lazy Google view/capability.
- Full names/provenance/reasons align 236 ↔ 237: `provider/runtime/model/base_url/credential_configured`, limits incl. read-only `max_request_bytes`, receipt `machine.engine/provider/model/runtime/endpoint_host/endpoint_path/prompt_version/model_version/content_variant/audio_*/request_bytes/latency_ms/usage`, Google reason strings. Recorded H2 literal `thought` prefix is preserved (not post-filtered); the real `type=thought` step is ignored.

## 3. Checks actually run (real commands / exits)

Commands run from the candidate worktree unless stated. No real Google/product/ASR/TTS/embedding/OCR call was made in LG-238.

| # | command | result |
|---|---|---|
| 1 | `PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m pytest -q tests/asr tests/settings/test_connection_service.py tests/api/test_settings_integration.py tests/api/test_health.py tests/integration tests/contracts tests/api/test_source_refs_messages.py` | **123 passed**, exit 0 (243.70 s) |
| 2 | `PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m pytest -q tests/sources/test_intake_worker.py tests/sources/test_intake_jobs.py tests/sources/test_receipt_branches.py` | **35 passed**, exit 0 (18.56 s) |
| 3 | `/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-backend-20261018/.venv/bin/python -m mypy` | **Success: no issues found in 172 source files**, exit 0 |
| 4 | `cd frontend && npm run test:run -- --maxWorkers=2 --minWorkers=1` | **38 files / 353 tests passed**, exit 0 (45.93 s) |
| 5 | `cd frontend && npm run typecheck` | exit 0 |
| 6 | `cd frontend && npm run build` | exit 0; 128 modules; `dist/assets/index-DDU0pU3S.js` 453.46 kB (gzip 128.42 kB), `dist/assets/index-BMHMEIYi.css` 68.30 kB (gzip 9.71 kB) |
| 7 | `git diff --check` (before source commit) | exit 0 |
| 8 | `python -c` fresh-interpreter import check (part of test 1, subprocess) | torch/numpy/transformers/`lightgravity.asr.runtime` not imported |

Concurrency/memory configuration: frontend full suite was run **once** with Vitest `--maxWorkers=2 --minWorkers=1`; typecheck and build were run sequentially afterwards. No other memory-heavy tool ran in parallel.

**Failed attempt preserved (not rewritten as a pass):** an earlier full `mypy` using the ROOT venv (`/home/yhvh/code/lightgravity-bot/.venv/bin/python -m mypy`) timed out at 600 s while resolving heavy installed type stubs, reaching ~1.3 GB RSS and exhausting host memory/swap; PM sent SIGINT after it had already ended. That run produced **no result** and is not evidence. The successful full mypy (test 3) used the lightweight LG-236 venv on the same candidate source.

Notes on reuse: the frontend subtree is byte-identical to LG-237 (`2526bbf…`), so 237's frontend proof remains valid; it was still re-run here once as required. Backend differs from LG-236 only in the two integration-owned files above, so the 236 behavioral proof carries and the directly affected focused suites were re-run (tests 1–3).

## 4. Google body-fixture proof (no real runtime claim)

- Recorded successful LG-235 response bodies committed by 236: **2** (`tests/asr/fixtures/lg235_h1_response.json`, `lg235_h2_response.json`; verbatim, non-secret).
- The new LG-238 assembled test replays **exactly 1** fake-transport request using the H1 body through `create_app` + the real deferred intake worker: HTTP 200 → `text.status=ready` → machine transcript equals the H1 text, usage `total_tokens=320`, provenance complete, keyword index searchable, machine content readable after disable, and no second request.
- H2 thought-step ignore / literal-text retention remains covered by the 236 suite replaying the H2 fixture.
- **This is recorded-fixture/fake-transport evidence only. It does not claim that a real product Google API call was verified in LG-238.** The only real Google calls in the programme remain LG-235's one H1 + one H2 prototype; the first real UI/intake call belongs to LG-239.
- Fake credential used in tests: `integration-google-key-not-real` / `fake-google-key` / `fresh-interpreter-key`; no real key, audio base64 or request header is stored in repo/logs/report.

## 5. Exact LG-239 startup / config / API shape

Use the lightweight **LG-236 venv** (verified `torch=False`, `numpy=False`, `transformers=False`), **not** the root venv (root has Torch installed). Use an isolated data dir/secret store and a port that is not 8123/5173/18123 (example 18124). Do not modify root services.

```bash
cd /home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-integrated-20261018
LIGHTGRAVITY_RUNTIME_TOKEN=<random QA token> \
PYTHONPATH=backend \
/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-backend-20261018/.venv/bin/python -m lightgravity.cli start \
  --data-dir /tmp/lg239-data --secret-store /tmp/lg239-secrets \
  --host 127.0.0.1 --port 18124 \
  --frontend-dist frontend/dist
```

- Startup prints `url/data_dir/secret_store/workspace_root/frontend_served/executor_wired/execution`; it does not print the runtime token. The served `index.html` injects `window.__LG_RUNTIME_TOKEN__` for the browser; API harness calls need `X-LG-Token: <token>` on sensitive writes.
- **Do not** put the Google key in the process env expecting product fallback: the product never reads `LG_GOOGLE_ASR_API_KEY`. The QA harness may read that variable itself and submit it as write-only `credential_value` via the UI/PUT; never log it, and do not write it into the repo.
- Initial settings view: `GET /api/v1/settings` → `english_asr` (default `provider:"eg2-reader"`, `enabled:false`, `revision:0`).
- Enable Google (`PUT /api/v1/settings/english_asr`, admin/protected; safe Origin/Host; token for the API harness):
  ```json
  {
    "expected_revision": 0,
    "enabled": true,
    "provider": "google-native",
    "runtime": "google-native",
    "model": "gemini-3.8-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta",
    "credential_value": "<real key, write-only>",
    "timeout_seconds": 180,
    "max_audio_bytes": 10000000
  }
  ```
  Optional `credential_ref` (defaults internally); omit it and `credential_value` on later saves to retain the stored secret. Omit all reader fields; `max_audio_seconds` must be omitted or `null`.
- Expected successful response: `revision`/`content_hash` plus full `english_asr` view with `provider/runtime:"google-native"`, `configured:true`, `available:true`, `credential_configured:true`, `limits.max_audio_seconds:null`, `max_audio_bytes:10000000`, `max_request_bytes:20000000`, `timeout_seconds:180`, `max_concurrency:1`; no key/ref/path.
- Health: `GET /api/v1/health` → `contract_version:"1.22.0"`, `capabilities.english_asr:true` after enable (attemptable, **not** key/model verified).
- One real intake call through the UI (preferred) or `POST /api/v1/sources` with `media_type:"audio/wav"`, base64 content, `intake_mode:"deferred"`; poll `GET /api/v1/intake/jobs/{job_id}`; then `GET /api/v1/sources/{id}/receipt` and `.../content?kind=machine`. Expect one provider request, `text.status:"ready"`, `machine.engine:"google-native"`, `machine.provider:"google"`, `prompt_version:"google-native-transcribe-v1"`, real usage/latency, no reader/encoder/timestamps, and literal model text (known defects allowed).
- Real-call boundaries for 239: exactly one audio; report 401/403/429/model-unavailable/timeout honestly; no auto retry/provider switch, no Reader fallback, no second real call to "fix" a sample. No Cloud resources/accounts/deploy/push.

## 6. Remaining limits / open facts

- **LG-239 not run:** no real browser, permissions, narrow-screen, or real Google runtime call in LG-238. Version acceptance is pending.
- Real Google key validity/quota/error rates, long/noisy/real-human audio, dedicated `gemini-3.5-transcribe`, timestamps/diarization and production readiness remain unknown/unverified. LG-235's metadata observation (interactions absent from `supportedGenerationMethods` but HTTP 200) still stands as an observation, not a guarantee for other models.
- Known recognition defects accepted by the user (e.g. H2 `Lena`→`Lina`, literal leading `thought`, date-surface changes) are preserved and disclosed; functionality/permission/false-success gates apply, not word-perfect names.
- Old Reader quality **FAILED**, §21 limitations and historical evidence are unchanged; switching provider does not reprocess old sources.
- Secret + settings remain two files with compensation (same limits as 236); concurrent same-ref rotation inherits existing local-store limits.
- `frontend/dist` is build output (git-ignored) and was not committed; the build hashes above are the local evidence.
- `docs/15-english-asr-and-ui.md` exists only as a root-only ignored PM document, not in the source tree; LG-238 documented native Google usage in `docs/07` + README instead of wholesale-copying root PM docs, and left root docs untouched for the PM.
- The root venv mypy attempt failed (see §3); use the LG-236 venv for 239 as noted.
- No deployment/push/release; 8123 remains 1.20.0. Task status remains root PM-owned.
