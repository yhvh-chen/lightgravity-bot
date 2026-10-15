---
title: "Materials Vector Quality R4 — REPORT (LG-037 real cross-modal text→image / text→audio)"
doc_type: report
category: probe
status: "complete — real cross-modal evidence obtained via product path; partial (1 of 2 real audio candidates); LG-037 stays in-progress"
updated: "2026-10-16"
---

# REPORT — materials-vector-quality-r4-20261016

## 0. One-line result

Through the **actual current product** vector embedder/index/service (`VectorSearchService` +
`OpenAICompatEmbeddingBackend` + `embeddinggemma-2-Q8_0`), a **frozen** 10-source corpus (2 real
images + 1 real audio + 7 real text distractors) and **frozen** text→media relevance labels
produced:
**text→image Recall@5 = 1.0** (Q_IMG_ZH at rank 5, Q_IMG_EN at rank 1) and
**text→audio Recall@5 = 1.0** (Q_AUD_ZH at rank 1); vector **MRR = 0.7333**, top-1 = 0.6667.
Negative-control queries returned **5 ranked false hits each** (no threshold/abstention — reported,
not treated as ACL failure). Lexical baseline returned **0** media hits (media has no transcript —
**not** quality evidence). **Only 1 of 2 required real audio candidates exists in the project**; the
second is named as missing rather than fabricated. **LG-037 stays `in-progress`; LG-040 not passed;
LG-041 stays locked.**

## 1. Authority & scope compliance

- Single pi executor (no nested agents). Root PM only.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-quality-r4-20261016`,
  branch `test/materials-vector-quality-r4-20261016`, base **`main @ 71a2041`** (verified clean).
- Write owner exact: `probes/materials-vector-quality-r4-20261016/**`. **No product / docs /
  backlog / contract edits** (`git diff HEAD -- backend/ frontend/ tests/ contracts/ docs/ backlog/`
  empty). No reset / clean / push / deploy / publish.
- Prior worktrees, dirty state and raw evidence preserved.
- **Network gate respected:** prior OCR owner wrapper `materials-ocr-r4-repair-20261016.txt`
  (`python3 .../lightgravity-pi-bounded.py ...`, PID 2727394) was observed **still running** at
  start; all Phase-A offline work (PLAN + labels + commit `ff6615e`) was completed first. The
  wrapper **exited** before the network phase, so no shared-endpoint overlap occurred. It was not
  killed.
- **FREEZE BEFORE POST:** `PLAN.md` + `corpus.json` (labels) committed as `ff6615e` **before any
  POST**. Hashes: `PLAN.md` `2e3b635d…`, `corpus.json` `846e61b1…`.

## 2. Frozen method (through the product, not a bypass)

- Product `VectorSearchService.index_source` embeds each source: **trusted formal text as a text
  vector**, and any source whose `original.media_type` is `image/*` or `audio/*` is embedded **as
  media** (`EmbedInput.image` / `.audio` → `image_url` / `input_audio` data URLs) — never fabricated
  into text.
- Product `VectorSearchService.search()` embeds **only a text query** (`EmbedInput.text_input`).
  There is **no image→image or audio→audio query API**. This package therefore measures
  **text query → media vector** ranking over the product's single ranked list — a genuine
  cross-modal comparison, and the strongest one the current product path supports.
- Reused **real product** `SourceStore`, `ContentStore`, `LexicalSearchService` (baseline). No mock,
  no bypass. Same product environment as prior evidence.

## 3. Corpus, provenance, licence, hashes (frozen before POST)

| id | media | file (in-repo / preserved worktree) | licence | semantically trustworthy truth |
|---|---|---|---|---|
| M_IMG_ZH | image/jpeg | Z1 page-10 JPG `lg035-truth-prep .../lg035_truth_zh_laojielao_p10.jpg` sha256 `5c73b9d0…` (333,996 B) | Public domain (Commons PD scan render) + CC BY-SA 4.0 (Wikisource human transcription) | real printed content = human proofread transcription: 老解老 (Laozi commentary), 老子學說 |
| M_IMG_EN | image/png | `probes/lg035/fixtures/phototest-rotated-L.png` sha256 `f9c80afb…` (6,793 B) | Apache-2.0 (`tesseract-ocr/test`) | real gold text of the page: "12 point text to test the ocr code … quick brown dog jumped over the lazy fox" |
| M_AUD_ZH | audio | `probes/lg039/evidence/real_voice_chinese_language-1.ogg` sha256 `1a8df6fb…` (1,509,884 B) | CC BY-SA 3.0 (`File:Chinese language-1.ogg`, real human) | real human speech reading the English-Wikipedia "Chinese language" opening; **topic-level** truth = Chinese language / 中文 (NO verbatim transcript) |
| D1–D7 | text | real Chinese human-transcribed fragments (from frozen R3 corpus) | CC BY-SA 4.0 + PD scan | **distractors only**, not the truth for any media query |

- **No downloads, no synthesized media, no image editing.** The audio's only transform is a
  **lossless container/PCM conversion** described in §4; the original ogg hash is the provenance
  anchor.
- Frozen queries/labels (`corpus.json`):

| query | text | label |
|---|---|---|
| Q_IMG_ZH | 老子 道德經 註解 學說 | `["M_IMG_ZH"]` |
| Q_IMG_EN | quick brown dog jumped over the lazy fox | `["M_IMG_EN"]` |
| Q_AUD_ZH | Chinese language 中文 spoken language | `["M_AUD_ZH"]` |
| Q_NEG_ZH | 量子色動力學 膠子 強相互作用 | `[]` |
| Q_NEG_EN | 2024 annual financial statement net profit | `[]` |

`labels_authorship = executor-authored` (NOT independent/human review) — declared.

## 4. Real execution + raw results

- `GET /health` → **HTTP 200**, `{"status":"ok"}`, 0.0015 s (raw `http/health.raw.json`
  sha256 `a29ee2b1…`, 0600). **GET 1/2.** `/v1/models` NOT re-fetched (metadata reused from prior
  evidence; endpoint llama.cpp router `b11641-843e7dcc1`).
- **POST used exactly 16/16** (7 corpus text + 2 image + 1 audio-raw + 1 audio-PCM + 5 queries),
  serial, **retries 0**, per-call timeout 90 s.

### Vector ranking (real, product path)

| query | type | vector top-5 (title order) | relevant rank |
|---|---|---|---|
| Q_IMG_ZH | positive text→image | D1, D2, D3, D5, **M_IMG_ZH** | **5** |
| Q_IMG_EN | positive text→image | **M_IMG_EN**, D2, D6, D7, D1 | **1** |
| Q_AUD_ZH | positive text→audio | **M_AUD_ZH**, D4, D2, D5, D7 | **1** |

All 10 indexed vectors: **768-dim, finite, L2 = 1.0, nonzero**, model `embeddinggemma-2-Q8_0`.
Media vectors carry `kind=image`/`audio` with `fragment_hash` = the exact input bytes hash
(image → original file sha256; audio → PCM wav sha256 `0cf59176…`). See
`evidence/vector_cache_summary.json`.

### Metrics

| metric | vector | lexical baseline |
|---|---|---|
| Recall@1 | **0.6667** | 0.0 |
| Recall@3 | **0.6667** | 0.0 |
| Recall@5 | **1.0** | 0.0 |
| MRR | **0.7333** | 0.0 |
| top-1 accuracy | **0.6667** | 0.0 |
| negative-control false hits (Q_NEG_ZH / Q_NEG_EN) | **5 / 5** | 0 / 0 |

- The lexical baseline returns **0** media hits because neither image nor audio has a text
  transcript in this corpus. That is **expected** and is explicitly **NOT** evidence that vectors
  are globally superior; it only shows the lexical path cannot reach transcriptless media.
- Negative controls: the vector path has **no score threshold and no abstention** (docs/08 froze no
  threshold field). Both negative queries returned a full ranked list of 5 unrelated docs
  (Q_NEG_ZH: D2,D6,D5,D1,D4; Q_NEG_EN: D2,D1,D5,D3,D6). This is **reported as the expected
  top-k-NN false-hit behaviour**, consistent with the R3 independent audit — **not an
  ACL/contract failure**.
- Claim scope: **3 positive cross-modal queries over a small corpus — indicative only.** No default
  threshold is proposed, tuned, or validated; the R3 7-doc text queries were **not** reused to
  calibrate anything.

## 5. Audio handling (format, no synthesis/ASR)

- Raw **Ogg/Vorbis** input was attempted first: product `index_source` raised
  `capability_unavailable` (`EmbeddingServiceError` surfaced through the product's `AppError`
  boundary). **Honest limitation:** the product's `AppError` boundary did not surface the exact
  upstream HTTP status/message, and the harness did not capture it; this exact message is
  **not available** in this run. This is consistent with prior evidence (`probes/lg039` §2,
  `probes/source-intake/eg2-endpoint`) that the endpoint expects PCM WAV for `input_audio`. **No
  retry was made beyond the single planned attempt** (budget honoured).
- The permitted **lossless PCM conversion** (`ffmpeg -ac 1 -ar 16000 -t 30 -c:a pcm_s16le`, **no
  synthesis, no transcription**) then succeeded: **audio vector 768-dim finite**, input = first
  **30.0 s**, sha256 `0cf59176…`. Original ogg is 143.58 s (CC BY-SA 3.0 real human).
- **Audio embedding ≠ ASR.** No transcript was produced or used; LG-041 remains locked.

## 6. Counters (final, exact)

| counter | used / cap |
|---|---|
| GET | **1 / 2** |
| inference POST total | **16 / 16** (7 text + 2 image + 1 audio-raw-fail + 1 audio-pcm + 5 queries) |
| retries | **0** |
| concurrency | 1 (serial) |
| ASR / OCR POST | **0 / 0** |
| media uploaded | 2,810,751 B ≈ **2.68 MiB / 10 MiB** |
| real audio input | **30.0 s / ≤30 s** |
| product worker calls / new services / model installs | 0 / 0 / 0 |

Cost/tokens: **unknown** (endpoint exposes no price); not counted as zero.

## 7. Honest gaps (not passed / not claimed)

1. **Only 1 real audio candidate** exists in the project (`real_voice_chinese_language-1.ogg`).
   The **exact missing sample** for a second meaningful real audio candidate with trustworthy
   semantic truth is: *a second real human-audio recording with a license-clear, known spoken topic
   (ideally Chinese). None is present in-repo; the only other audio is the synthetic espeak-ng
   `audio.wav`, which is forbidden as quality evidence.* → **no fabricated second audio label.**
2. Real image candidates exist (M_IMG_ZH, M_IMG_EN used); a 3rd (raw TIFF `phototest.tif`) was not
   used to avoid TIFF-format-uncertainty / budget.
3. **No relevance threshold / score-margin behaviour** validated; negatives leak as expected.
4. **No second embedding model switch** (no second authorized model; providers not switched).
5. Corpus/query sample is small (indicative only); **LG-040 is not claimed passed** (QA only at the
   integrated named milestone).
6. The product has **no media→media query API**; text-query→media-vector is the strongest
   cross-modal comparison currently available and is what was measured.

## 8. If media quality "failed": next concrete action

Cross-modal retrieval is **partially positive** (both image and audio candidates are reachable by
text queries). The one weak point is **rank** for Q_IMG_ZH (rank 5). Concrete next action (NOT done
here, needs separate authorization): add a second real Chinese image and a second real Chinese
audio candidate to widen the cross-modal corpus, and (separately) evaluate score-margin behaviour;
do **not** tune a default threshold on these frozen queries.

## 9. Immutability / preservation

- `git status` in this worktree shows only `probes/materials-vector-quality-r4-20261016/**`.
- `git diff <base> -- backend/ frontend/ tests/ contracts/ docs/ backlog/` **empty**; task files
  unchanged; contract `1.11.0` / SDK `0.1.22` unchanged.
- Failed attempt (raw ogg) retained; negative false hits retained; no threshold lowered.

## 10. Evidence index

- `STATUS.md`, `PLAN.md` (frozen pre-inference, commit `ff6615e`), this `REPORT.md`, `corpus.json`
- `http/health.raw.json` (0600, sha256 `a29ee2b1…`)
- `evidence/crossmodal_harness.py`, `evidence/crossmodal_results.json` (sha256 `94219685…`)
- `evidence/vector_cache_summary.json` (sha256 `5cac7051…`)
- `private/` (mode 700): vector-data cache, PCM wav, original media copies
- Budget: GET 1/2, POST 16/16, retries 0. LG-037 `in-progress`; LG-040 not passed; LG-041 locked.
