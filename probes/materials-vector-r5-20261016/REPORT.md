---
title: "Materials Vector Quality R5 — REPORT (LG-037 second real audio + frozen cross-modal gate)"
doc_type: report
category: probe
status: "complete — 2nd real audio candidate added and reachable; FROZEN HARD GATE NOT MET (Q_IMG_ZH missed top-5); LG-037 stays in-progress"
updated: "2026-10-16"
---

# REPORT — materials-vector-r5-20261016

## 0. One-line result

Through the **actual current product** vector path (`VectorSearchService` +
`OpenAICompatEmbeddingBackend` + `embeddinggemma-2-Q8_0`), a **frozen** corpus (2 real images + **2
real audio** + 6 real Chinese text sources incl. 1 textual positive) and **frozen** relevance labels
produced:

- **text→audio Recall@5 = 1.0** — both real audio candidates reachable: `Q_AUD_LANG` (中文) **rank 1**,
  `Q_AUD_EARTH` (地球/Earth) **rank 1**. **The R4 gap of "only 1 real audio candidate" is
  closed with a 2nd real human recording.**
- **text→image**: `Q_IMG_EN` **rank 1**, but `Q_IMG_ZH` **NOT in top-5** (`relevant_rank = null`).
- **Chinese textual positive** `Q_TXT_ZH` **rank 1** (full-scope text retrieval works).
- vector **MRR = 0.8**, top-1 = 0.8; lexical baseline MRR = 0.2 (only the text query).
- **FROZEN HARD GATE (PLAN §3) NOT MET:** `image_reachable = false` because not both images were in
  top-5. ⇒ **No quality-pass claim.** LG-037 **stays `in-progress`**; LG-040 not passed; LG-041 locked.

## 1. Authority & scope compliance

- Single pi executor (no nested agents). Root PM only.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016`,
  branch `test/materials-vector-r5-20261016`, base **`main @ a2dc40a`** (verified clean).
- Write owner exact: `probes/materials-vector-r5-20261016/**`. **No product / docs / backlog /
  contract edits**: `git diff a2dc40a HEAD -- backend/ frontend/ src/ tests/ contracts/ docs/
  pyproject.toml uv.lock Makefile backlog/ README.md PROGRESS.md` = **empty**. Same as main for
  source. No reset / clean / push / deploy / publish.
- **Network gate respected:** prior OCR owner wrapper with argv basename
  `materials-ocr-r5-20261016.txt` (PID 2784651) was observed **alive** at start; ALL offline work
  (acquisition, PLAN, labels, harness, dry-run) was completed first. The wrapper **exited on its own**
  (≈6 min, within its own 600 s budget) before the network phase; it was **not killed**. My own
  wrapper `materials-vector-r5-20261016.txt` was excluded. No `OCR/ASR/worker/new provider/model`
  calls.
- **FREEZE BEFORE POST:** `PLAN.md` + `corpus.json` committed as **`0ca7a42`** **before any POST**.
  Hashes: `PLAN.md` `80d063da…`, `corpus.json` `9853f9ed…`.

## 2. Second real audio candidate (acquisition, exact)

- **File:** Wikimedia Commons **`File:Zh-地球.ogg`** — a **real human** pronunciation recording of the
  Chinese word **地球** (Earth).
- **Licence:** **CC BY-SA 4.0**; `{{self|cc-by-sa-4.0}}`; author **CanonNi** (own work), 2024-10-07;
  page `https://commons.wikimedia.org/wiki/File:Zh-地球.ogg`; category *Chinese pronunciation*.
- **Trustworthy topic truth** comes from the file's **OWN description page**:
  `{{pronunciation|地球|lang=zh|translation=Earth}}` ⇒ topic = **Earth / 地球** — **not** model output,
  **not** a guess.
- **Metadata** via official Commons API (license/author/size/sha1/extmetadata + page wikitext);
  raw response `http/commons_zh_diqiu_metadata.raw.json` sha256 `2ccf3bbd…`.
- **Download:** ONE direct upload GET (`.../wikipedia/commons/2/29/Zh-%E5%9C%B0%E7%90%83.ogg`,
  HTTP 200, **19,957 B ≤ 5 MiB**); download **SHA1 `a8c67e62…` verified equal** to the API-declared
  SHA1. SHA-256 `46781b4e…`. Real Vorbis, mono 48 kHz, **2.048 s ≤ 15 s**. No TTS.
- **Audio budget:** original ≤ 15 s. Second audio adds ~2.05 s, so total embedding audio ≈ 32.05 s
  (first audio 30 s + second 2.05 s) — the per-POST ≤ 30 s bound is respected per call.
- **Resampling/clipping recorded honestly (NOT lossless):** endpoint expectation (established in R4)
  is PCM WAV for `input_audio`; the transform is
  `ffmpeg -ac 1 -ar 16000 -t <clip> -c:a pcm_s16le` = **resample to 16 kHz mono + time-clip**. The
  original ogg (and its Commons SHA1) is the **provenance anchor**; the PCM WAV is what was embedded.
  Private originals preserved under `private/`.

## 3. Frozen method (through the product, not a bypass)

- Product `index_source` embeds formal text as a **text** vector; a source with `original.media_type`
  `image/*` or `audio/*` is embedded **as media** (`image_url` / `input_audio` data URLs) — never
  fabricated into text. Real `SourceStore` / `ContentStore` / `LexicalSearchService` reused. No mock,
  no bypass.
- Product `search()` embeds **only a text query**; there is **no media→media query API**. This
  package measures **text query → media vector** ranking over the product's single ranked list.
- Media handling: bytes sent as media; **no image editing**; 2 images + 1 audio reused from existing
  licensed fixtures, 1 audio newly acquired (above); **no synthesized media**.

## 4. Frozen corpus + relevance labels (pre-registered)

| id | media | file | licence | trustworthy truth |
|---|---|---|---|---|
| M_IMG_ZH | image/jpeg | Z1 page-10 JPG (`lg035-truth-prep`, sha256 `5c73b9d0…`) | PD scan + CC BY-SA 4.0 (Wikisource human transcription) | 老解老 / 老子學說 |
| M_IMG_EN | image/png | `probes/lg035/fixtures/phototest-rotated-L.png` (sha256 `f9c80afb…`) | Apache-2.0 | "quick brown dog jumped over the lazy fox" |
| M_AUD_ZH | audio/ogg→PCM | `probes/lg039/evidence/real_voice_chinese_language-1.ogg` (sha256 `1a8df6fb…`) | CC BY-SA 3.0, real human | Chinese language / 中文 (topic-level) |
| **M_AUD_DIQIU** | audio/ogg→PCM | `private/Zh-地球.ogg` (sha256 `46781b4e…`, Commons sha1 `a8c67e62…`) | **CC BY-SA 4.0**, real human | **Earth / 地球** (from file description) |
| D1–D3, D5–D6 | text | real Chinese fragments | CC BY-SA 4.0 + PD scan | **distractors only** |
| T_NORTHWIND | text | real Chinese fragment | CC BY-SA 4.0 + PD scan | Chinese **textual positive** target |

Frozen queries (exact): `Q_IMG_ZH 老子 道德經 註解 學說`→[M_IMG_ZH]; `Q_IMG_EN quick brown dog jumped
over the lazy fox`→[M_IMG_EN]; `Q_AUD_LANG Chinese language 中文 spoken language`→[M_AUD_ZH];
`Q_AUD_EARTH 地球 Earth 發音 spoken word`→[M_AUD_DIQIU]; `Q_TXT_ZH 北風 跟 太陽 爭論 誰的本事大`→
[T_NORTHWIND]; negatives `Q_NEG_ZH`/`Q_NEG_EN`→[]. Labels **executor-authored** from each source's own
recorded truth (NOT model output). **R4 queries not reused for calibration.**

## 5. Real execution + raw results

- `GET /health` → **HTTP 200**, `{"status":"ok"}`, 0.0019 s (`http/health.raw.json` sha256
  `a29ee2b1…`, 0600). **GET 1/2.** `/v1/models` NOT re-fetched (metadata reused).
- **POST used exactly 17/18** (6 text + 2 image + 2 audio-PCM + 7 queries), **serial**, **retries 0**,
  per-call timeout 90 s. Reservation ledger `evidence/post_reservations.jsonl` (17 lines) persisted
  **before** each forward.

### Vector ranking (real, product path)

| query | type | vector top-5 (title order) | relevant rank |
|---|---|---|---|
| Q_IMG_ZH | positive text→image | D1, D2, D3, D5, T_NORTHWIND | **absent (miss)** |
| Q_IMG_EN | positive text→image | **M_IMG_EN**, D6, D2, D1, T_NORTHWIND | **1** |
| Q_AUD_LANG | positive text→audio | **M_AUD_ZH**, D2, D6, D5, T_NORTHWIND | **1** |
| Q_AUD_EARTH | positive text→audio | **M_AUD_DIQIU**, D6, D5, M_AUD_ZH, D2 | **1** |
| Q_TXT_ZH | positive Chinese text | **T_NORTHWIND**, D5, M_AUD_DIQIU, D6, D2 | **1** |

All 10 indexed vectors: **768-dim, `embeddinggemma-2-Q8_0`**, media `kind=image`/`audio` with
`fragment_hash` = exact input bytes hash. See `evidence/crossmodal_results.json`.

### Metrics

| metric | vector | lexical baseline |
|---|---|---|
| Recall@1 / @3 / @5 | **0.8 / 0.8 / 0.8** | 0.2 / 0.2 / 0.2 |
| MRR | **0.8** | 0.2 |
| top-1 accuracy | **0.8** | 0.2 |
| negative-control false hits (Q_NEG_ZH / Q_NEG_EN) | **5 / 5** | 0 / 0 |

- Lexical baseline only reaches the **text** query (T_NORTHWIND); it returns **0** for every media
  query because media has no transcript. That is **expected** and is **NOT** evidence that vectors are
  globally superior.
- Negative controls: no score threshold / no abstention (docs/08 froze no threshold field); both
  negative queries returned a full ranked list of 5 unrelated docs (Q_NEG_ZH: D2,D6,D5,D1,T_NORTHWIND;
  Q_NEG_EN: D2,D5,D6,D1,M_AUD_DIQIU). **Reported as the expected top-k-NN false-hit behaviour**, not
  an ACL/contract failure (per R3 audit).
- **Claim scope: 5 positive queries (4 cross-modal + 1 textual) over a small corpus — indicative
  only.** No default threshold proposed/tuned/validated.

## 6. Frozen hard gate (declared in PLAN §3) — outcome

| gate | result |
|---|---|
| both real audio reachable (Recall@5) | **PASS** (Q_AUD_LANG rank 1, Q_AUD_EARTH rank 1) |
| both real images reachable (Recall@5) | **FAIL** (Q_IMG_ZH absent; Q_IMG_EN rank 1) |
| Chinese textual positive reachable | **PASS** (rank 1) |
| `all_hard_gates_met` | **false** |

⇒ **Honest outcome: the frozen quality gate is NOT met. No quality-pass claim.** The **second-audio
gap is closed**, but cross-modal retrieval quality on the **image** side did not meet the
pre-registered gate this run.

## 7. Cache/model provenance verification (targeted, not repeated)

- The prompt permits targeted model/cache checks **only if not already covered** by previous
  implementation evidence. Prior implementation already has focused tests for these behaviours; I
  ran the **targeted** vector suite in this branch (source identical to main) instead of a full-suite
  probe:
  `pytest tests/sources/vectors/ -q` → **38 passed, 1 skipped** (skip = live-endpoint real-quality
  probe). Covered: `test_model_switch_is_not_mixed`, `test_search_refuses_other_model`,
  `test_search_skips_dimension_mismatch`, `test_delete_and_rebuild_reproduces_entries`,
  `test_corrupt_cache_is_reported`, `test_scope_filter_never_widens`, `test_revoked_source_is_stale`,
  `test_version_change_makes_hit_stale`, `test_model_switch_rebuilds_not_mixes`,
  `test_search_model_mismatch_requires_rebuild`, `test_backend_failure_downgrades_honestly`,
  `test_cache_holds_no_permission_state`.
- **Model-switch cache invalidation is verified mechanically** (altered fingerprint / test backend
  refuses mixing + requires rebuild). This task does **NOT** demand a 2nd live model; **no 2nd live
  model was switched or pretended**.

## 8. Counters (final, exact)

| counter | used / cap |
|---|---|
| GET (health) | **1 / 2** |
| inference POST total | **17 / 18** (6 text + 2 image + 2 audio + 7 queries) |
| retries | **0** |
| concurrency | 1 (serial) |
| ASR / OCR POST | **0 / 0** |
| media uploaded | 1,366,481 B ≈ **1.30 MiB / 10 MiB** |
| audio input | 30.0 s + 2.048 s = **32.048 s total** (each POST ≤ 30 s) |
| public acquisition | metadata GET ≤ 6 total, **1 download 19,957 B ≤ 5 MiB** |
| product worker calls / new services / model installs | 0 / 0 / 0 |
| targeted vector tests | 38 passed, 1 skipped |

Cost/tokens: **unknown** (endpoint exposes no price); pi/DeepSeek execution cost separate and
**unknown, not zero**.

## 9. Honest assessment vs LG-037 original acceptance

Original LG-037 acceptance (backlog/tasks/LG-037.md) and status per this evidence:

| original acceptance item | status from R5 |
|---|---|
| verify real model + multimodal protocol at configured endpoint | supported (R4 + R5 real media POSTs; 768-dim finite) |
| record model/version/dim/fragment hash/source/cache version; model switch rebuilds, no mixing | implemented + **targeted tests pass** (incl. model-switch no-mix/rebuild) |
| fixed query set incl. real Chinese text + image + audio with relevance truth; report Recall@k + negative false-hits; lexical baseline; keep limits | **run** — 2 images + **2 audio** + real Chinese text; Recall@k/MRR/ranks/false-hits + lexical baseline reported |
| media embedded directly, not fabricated into text; ASR/OCR separate; lexical + original view usable when vectors unavailable | implemented; media embedded as media; embedding ≠ ASR/OCR; downgrade test passes |
| queries and hits re-source-verified under authorization; cache deletable/rebuildable, no sole business fact; no resident model agent | implemented; targeted ACL/rebuild/cache-no-permission tests pass |

**Remaining honest gap:** the **pre-registered hard gate** for image reachability failed on
`Q_IMG_ZH`. This is a *quality* result (the image page competes against semantically close Chinese
text distractors), **not** a mechanism/contract failure. It means LG-037's "report Recall@k and keep
limitations" is satisfied, but a **quality-pass cannot be claimed**.

## 10. Recommendation (do NOT change task status)

- **Do NOT mark LG-037 done** and **do NOT self-certify product/version QA.** The original
  implementation acceptance is largely supported, but the **quality truth is not robust** (frozen
  image gate unmet; tiny corpus). State the exact gap rather than claim pass.
- Concrete next action (NOT done here, needs separate authorization): a **larger, more balanced
  cross-modal corpus** and a **score-margin** evaluation; **do not** tune a threshold on these frozen
  queries. LG-037 remains `in-progress`; LG-040 remains `todo` pending version QA; LG-041 locked.

## 11. Evidence index / commands

- Freeze commit `0ca7a42`; harness commit `967d97b`; final evidence commit (this REPORT).
- `probes/materials-vector-r5-20261016/{STATUS.md,PLAN.md,REPORT.md,corpus.json}`
- `http/health.raw.json` (0600, sha256 `a29ee2b1…`), `http/commons_zh_diqiu_metadata.raw.json`
  (sha256 `2ccf3bbd…`)
- `evidence/crossmodal_harness.py`, `evidence/offline_dryrun.py`,
  `evidence/crossmodal_results.json` (sha256 `2695d24a…`), `evidence/post_reservations.jsonl`
  (sha256 `e3adffd3…`, 17 reservations)
- `private/` (mode 700): `Zh-地球.ogg` + PCM wav, first audio PCM wav, vector-data cache
- Exact commands: `PYTHONPATH=backend LG_R5_BASE_URL=http://192.168.8.12:11434
  LG_R5_MODEL=embeddinggemma-2-Q8_0 python probes/materials-vector-r5-20261016/evidence/crossmodal_harness.py`;
  `pytest tests/sources/vectors/ -q` → 38 passed, 1 skipped.
- Budget: GET 1/2, POST 17/18, retries 0. **LG-037 in-progress; LG-040 not passed; LG-041 locked.**
