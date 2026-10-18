# LG-239 QA — Google-native English ASR, candidate 1.22.0

Status: **PASS_WITH_LIMITATIONS**
Date: 2026-10-18
Independent version/browser QA on the frozen candidate; no deployment, push, release, root service change, production account change or Cloud resource was made.

## 1. Candidate and environment

| Item | Verified value |
|---|---|
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-qa-20261018` |
| Branch | `qa/google-native-asr-20261018` |
| Commit | `ecda49f692097b07d6f574652f9ed72b6387919a` |
| Tree | `d96f22b6d5acbb509cb9cbf6c232d557215af19b` |
| Contract | `1.22.0` (`/health.contract_version`) |
| Backend tree | `6cc2a72d74cd274b5d68a6e47ef423b7395f376b` |
| Frontend tree | `2526bbf54770a5302462630bb2f7d17d6d12ddbd` |
| Product source changes by QA | none (`git status --short` clean) |
| Frontend | reused LG-238 build `index-DDU0pU3S.js` + `index-BMHMEIYi.css` (sizes match LG-238) |
| App | isolated Team mode on `127.0.0.1:18239`, fresh data root, fresh secret store, no executor, no responder |
| Python | lightweight LG-236 venv (Torch/numpy/transformers absent) |
| Data | `/home/yhvh/tmp/lg239-google-data` (preserved) |
| Secrets | `/home/yhvh/tmp/lg239-google-secrets` (preserved, owner-only; real key only there) |

The product subprocess was started with all provider credentials removed. `/proc/<pid>/environ` contained no `LG_GOOGLE_ASR_API_KEY`, DeepSeek/OpenAI/Google/Gemini key or OCR token. The real key was supplied only as a write-only value to the protected settings API from a separate Python harness process before browser/network capture.

## 2. Actual Google call — exactly one

The single real call was made through the real product UI: an ordinary Team Chat message with an audio attachment, **without `@bot`**, so no chat LLM/Task run was invoked.

| Item | Value |
|---|---|
| Audio | `probes/english-asr-20261018/lg163/artifacts/tts/qa-h1-harbor.piper-ljspeech-high.16k.wav` |
| Input SHA-256 | `e186594f70db78b4cbd9bb926beb72421bd5dfe3f7d2da4f1bba0a498663c740` |
| Bytes | 333,332 |
| Source | `source_01M57APF4Q67D8XT97WE6JKRHA` |
| Job | `intake_01M57APF57HXQWCBCX4EBFCEPG` |
| Job terminal | `succeeded`, stage `done`, attempt `1`, `max_asr_calls=1`, finished `2026-10-18T11:00:13.923Z` |
| Provider route | `POST https://generativelanguage.googleapis.com/v1beta/interactions` |
| Model | `gemini-3.8-flash` |
| Prompt version | `google-native-transcribe-v1` |
| HTTP result | 200; transport latency 6,082 ms; machine latency 6,084 ms |
| Request bytes | 444,689 (inline audio + prompt + JSON overhead) |
| Usage | total 321, input 287 (text 26 + audio 261), output 34, thought 0 |
| Transcript | `On April 9th 2027 the North Harbor Market opens at 6:45, and the ferry to Cedar Island carries 38 passengers.` |
| Transcript SHA-256 | `b36b3406b77ae2198dac2f5cdd81898f065dd5cc0078688db2206c0afbe735c0` |
| Google attempts final | **1** |

The audit wrapper forwarded the real default HTTPS transport unchanged and recorded only non-secret metadata. It never recorded the key, headers' values, request body or audio base64. The app process reported `torch=false`, `numpy=false`, `transformers=false`, `lightgravity.asr.runtime=false`, `lightgravity.asr.reader_model=false` at startup and after the real call. Local process RSS moved from 65,544 KiB to 71,324 KiB across the call (local observation only; **not** a Cloud Run memory/cold-start measurement).

No second audio was submitted to shared ASR/Google and no request was replayed after the first HTTP 200.

## 3. What was checked

### 3.1 Settings, secret and revision boundary (15/15 protected API checks passed)

- Initial settings view was legacy `eg2-reader`; `GET /settings` is admin-only in Team mode (ordinary member got **403**).
- Invalid Google model id, non-native base URL and legacy `max_audio_seconds=30` each returned **422** with no fake-key echo and no persistence.
- A valid Google save with a **fake** key returned 200 and made **zero** Google calls (save only validates/persists).
- `GET /settings` returned no key, no `credential_ref`/`credential_value`, no `model_dir`/`reader_dir`, no request body.
- Omitting `credential_value` retained the stored secret; explicit empty is rejected (offline/contract test).
- A stale `expected_revision` write with a fake credential returned **409**, did not echo it and did not overwrite the stored secret.
- The real key was restored via an out-of-trace protected Python API call; the view stayed write-only.
- `/health` reported contract `1.22.0` and `capabilities.english_asr=true` only after enable.
- In the real UI, saving a fake key cleared the password field and stated that saving does not transcribe or verify; the fake key never appeared in the browser document. The real key was restored out-of-trace before upload.
- A subsequent UI blank-secret save retained `credential_configured=true`; the later real transcription proves the retained key was still usable.

### 3.2 Admin Google config at 1440 / 1024 / 390

At all three widths the admin Settings dialog:

- showed provider **Google native**, model `gemini-3.8-flash`, native base URL, `API key configured`, `enabled`, `configured`, `available`, and “not verified” wording;
- contained **no** `Model assets directory`, `Reader assets directory`, `Maximum audio seconds (1–30)` or pinned Reader model fields;
- showed the key field as blank and `type=password`;
- had no horizontal overflow at the page or modal level.

Screenshots: `screenshots/admin-google-config-1440.png`, `-1024.png`, `-390.png`, `admin-google-config-fake-key-saved-1440.png`.

### 3.3 Team upload, receipt, persistence and history

- Before the upload there were **zero** Tasks and **zero** shared sources; the upload created a deferred intake job but no delivery Task/Run.
- `TEXT` reached `ready` in English; `KEYWORD` was `searchable`; `SEMANTIC` was honestly `disabled` with `vector_backend_unavailable` (no embedding/OCR provider configured).
- Receipt branch showed `machine Google transcript · Google native · google-native · gemini-3.8-flash · word timestamps not available`; `timestamps` was `null`; no fake encoder/Reader fields.
- Machine content was nonempty, selectable text in the Tasks material detail.
- The actual persisted original matched the input SHA-256 and 333,332-byte size; its reported path was source-root-relative.
- Keyword search for `Cedar Island` found the source and `Open in Tasks` returned to the same material.
- The human formal version was initially absent; writing it succeeded and left the machine body byte-identical. This preserves the machine/formal separation.
- After disabling Google ASR, the view was honest (`enabled=false`, `configured=true`, `available=false`, `reason=disabled`) and the historical machine transcript remained readable after a real page reload. No fake success was shown and no second Google call occurred.

Screenshots: `member-h1-receipt-1440.png`, `member-h1-detail-1440.png`, `member-keyword-search-1440.png`, `member-history-1024.png`, `member-history-390.png`, `member-history-after-disable-1440.png`.

### 3.4 Privacy and permissions

- **Personal private audio:** attaching/sending the same H1 audio in Personal added no shared source, produced no Google attempt and no shared transcript/index claim.
- **Cross-Task backend negative:** a source scoped to Task A was not returned by Task B's source list; a Task B message carrying that Task A `source_ref` was rejected with **422** (`reference_invalid` / outside scope).
- **Ordinary member:** `GET /api/v1/settings` returned 403; the member had no admin Google config read path.

### 3.5 Browser network and vendor boundary

Across the pre-upload/upload phase and the continuation phase (275 sanitized browser requests total):

- cross-origin requests: **0**;
- direct browser requests to `generativelanguage.googleapis.com`: **0**;
- responses carrying Google vendor headers (`x-goog-*`): **0**;
- all product traffic stayed on `127.0.0.1:18239`; Google authentication happened only server-side.

Raw sanitized network metadata is in `traces/browser-network-sanitized.json` and `traces/browser-network-continuation-sanitized.json`; no bodies/audio/key are stored.

### 3.6 Error/timeout/cancel/missing-config boundaries (offline, labelled)

To avoid invalid Google calls and extra quota, live 401/403/429/empty/malformed/timeout/cancel/stop-unconfirmed cases were **not** sent to Google. The frozen candidate was checked with:

```text
PYTHONPATH=backend <LG-236 venv>/python -m pytest -q \
  tests/asr/test_google_provider_contract.py tests/asr/test_google_native.py \
  tests/asr/test_google_source_pipeline.py tests/asr/test_stop_truth.py
# 60 passed in 2.67s
```

These cover missing/unreadable credential, environment credential never used, H1/H2 response parsing, thought-step ignore with literal text retained, 401/429/model/5xx/invalid-request mapping, empty/malformed/non-completed response failure, pre-dispatch cancel, post-dispatch timeout/cancel `asr_stop_unconfirmed` with late text discarded, and request-size/MIME preflight. They are **offline unit boundaries**, not live provider evidence.

## 4. Harness corrections — preserved, no product failure

No product source was changed. All failed harness attempts are preserved under `runs/`; the first real Google call was never repeated.

| Run | Outcome | Correction |
|---|---|---|
| `run1-preupload-harness-assertion` | admin dialog assertion expected input values in `innerText` | assert model/Base URL input values directly |
| `run2-real-google-success-then-job-poll-harness-bug` | **one real Google 200 already made**; harness demanded terminal job status while still `indexing` | continue from the same source/job; no resubmission |
| `run3-resume-receipt-shape-harness-bug` | receipt v2 is `items[]`, not top-level `text` | select latest item with `text.machine` |
| `run4-resume-chat-receipt-assertion-harness-bug` | Chat receipt shows provenance + backlink, not transcript body | assert truthful receipt/backlink; transcript checked in Tasks |
| `run5-resume-disabled-wording-harness-bug` | UI says “no transcript is generated” not “No transcription is generated” | accept the actual honest wording |
| `run6-final-success` | final evidence snapshot | 28 continuation checks passed; final Google count 1 |

These were harness/test-expectation defects, not product defects. The candidate was not modified to make tests pass.

## 5. Verdict and limitations

**Final verdict: PASS_WITH_LIMITATIONS.**

The candidate’s scoped Google-native lifecycle works on the frozen source: protected admin configuration, write-only secret handling, one real native transcription through ordinary Team intake, truthful receipt/provenance, text persistence, keyword search, source backlink, formal/machine separation, responsive layouts at 1440/1024/390, honest disable/history behavior, Personal privacy and cross-Task scope negatives.

Not claimed / not browser-validated:

- **Recognition quality is not a PASS gate here.** This is one licensed synthetic H1 sample. Human/noisy/accented/long/multilingual audio, timestamps and diarization were not validated. H1’s `North Harbor Market` capitalization and `April 9th` surface form are accepted model output, not truth.
- **H2 was not re-run.** The recorded H2 literal leading `thought` inside final `model_output` and `Lena`→`Lina` remain known accepted model defects; the parser must not hardcode sample words. The old Reader quality **FAILED** remains unchanged.
- Live provider 401/403/429/empty/malformed/timeout/cancel classes were intentionally covered by offline fake-transport tests, not invalid real calls.
- Missing/deleted credential was not created through a destructive live API; disabled live state and offline missing-secret tests cover honest unavailable behavior.
- No Cloud Run RAM, cold-start, real quota/concurrency or production readiness measurement is claimed from local RSS/one call.
- No full Tasks/Board/Team browser matrix, new TTS/video, broad fuzzing or full historical regression suite was repeated; only core legacy Task/scope plus ASR-sensitive paths were checked.
- No deployment/push/release, no root service/data change; public 8123 remains the deployed 1.20.0 service. Production accounts were not read or changed.
- **Observation, not a blocker:** receipt v2’s legacy `formal_path` field can point at `derivative/machine.vN.md` on the text-ready row even before a human formal version exists. The tested UI does not treat it as formal presence; the formal/machine boundary was verified through `content?kind=formal/machine`.

## 6. Evidence

Primary:

- `results.json`
- `QA.md`
- `logs/google-transport-audit.jsonl` — the only real Google transport row (HTTP 200, 6,082 ms)
- `provenance/candidate-identity.txt`, `provenance/frontend-dist.txt`, `provenance/import-guard.txt`, `provenance/google-attempts-before-after.json`
- `logs/request-counts.json`
- `traces/browser-run.json` (pre-upload + upload), `traces/browser-resume.json` (final continuation)
- `traces/api-setup-and-secret-boundaries.json`
- `logs/offline-boundary-pytest.log`
- `screenshots/` (13 images)
- `runs/` (all harness attempts preserved; see each `README.txt`)

Cleanup: the QA app and browser processes were stopped after evidence capture. The isolated candidate test data and the owner-only secret store are preserved for review; no production service was stopped or changed.
