---
title: "Materials Vector Quality R4 — FROZEN PLAN (pre-registered before any inference POST)"
doc_type: report
category: probe
status: "frozen — written before the first POST; no result may change it"
updated: "2026-10-16"
---

# FROZEN PLAN — materials-vector-quality-r4-20261016

**This plan and the relevance labels in `corpus.json` are frozen BEFORE any POST.**
No result may change a threshold, a corpus item, a query, its labels, or the call count.
Failed attempts and false hits are kept and reported.

## 0. Purpose (scope honesty)

Deliver the **remaining real cross-modal retrieval-quality evidence** for LG-037 using the
**actual current product vector embedder/index/service**. In scope: **text query → real image
vector** and **text query → real audio vector** ranking against the product's single ranked list.

**Out of scope / not claimed:** ASR (audio embedding ≠ ASR; LG-041 stays locked), OCR quality
(LG-035 separate), global model superiority, LG-040 gate pass, product threshold tuning, default
threshold calibration. The prior R3 7-doc text result is **indicative only** and is not re-scored
or re-used as a threshold.

## 1. Method (what is actually testable through the product)

The product `VectorSearchService.search()` accepts **only a text query**
(`embedder.py: EmbedInput.text_input(request.query)`); there is **no image→image or audio→audio
query API**. The product path does:
1. `index_source()` embeds each source: trusted text as a **text** vector, and a source whose
   `original.media_type` starts with `image/` or `audio/` is embedded **as media** (never
   fabricated into text) — `service.py:_vector_inputs`.
2. `search(text)` embeds the query text and returns a single ranked candidate list; candidates are
   authorized + re-verified by `authorize_and_verify` + 回源核对, with **no score threshold and no
   abstention** (docs/08 froze no threshold field).

So this package measures, **through the real product**, whether a **text query that encodes the
known semantic content of a real media file** retrieves that media candidate from the single
ranked list. This is a genuine text↔media cross-modal comparison over the product's own path.

### Media handling constraints
- Media bytes are sent **as media** (`image_url` / `input_audio` data URLs) — never OCR'd/ASR'd to
  text first, never relabeled.
- **No image editing, no synthesized media, no downloads.** Only pre-existing licensed fixtures.
- Audio: the real human-voice fixture is **Ogg/Vorbis 44.1 kHz**. Prior product/probe evidence
  (`probes/lg039` §2, `probes/source-intake/eg2-endpoint`) establishes that the endpoint expects
  PCM WAV for `input_audio`. If raw Ogg is rejected, the **only** permitted transform is a
  **lossless container/PCM conversion** (`ffmpeg -ac 1 -ar 16000`, **no synthesis, no
  transcription**) whose hash is recorded; the ORIGINAL ogg hash is the provenance anchor. If no
  conversion is needed, none is done.
- Image: prefer formats already proven acceptable (JPEG/PNG). A raw TIFF is first tried **only if
  within POST budget**; TIFF is not transcoded (no image editing).

## 2. Corpus + label manifest (`corpus.json`, frozen here)

Real media candidates (semantic truth recorded from their **own** provenance, frozen before POST):

| id | kind | file | license / provenance | trustworthy semantic truth (basis) |
|---|---|---|---|---|
| M_IMG_ZH | image/jpeg | Z1 page-10 JPG (preserved `lg035-truth-prep` worktree) | Public-domain PD book scan; Wikisource human transcription CC BY-SA 4.0 | the page's real printed content = human proofread transcription (`truth/LG035-ZH-Z1.p10.txt`): Laozi commentary 老解老, 老子學說 |
| M_IMG_EN | image/png | `probes/lg035/fixtures/phototest-rotated-L.png` | Apache-2.0 (`tesseract-ocr/test`) | the page's real printed content = human gold `phototest.gold.txt`: "12 point text to test the ocr code … the quick brown dog jumped over the lazy fox" |
| M_AUD_ZH | audio (ogg→PCM wav if required) | `probes/lg039/evidence/real_voice_chinese_language-1.ogg` | CC BY-SA 3.0; real human reading of English-Wikipedia "Chinese language" article opening | spoken topic = **Chinese language / 中文** (real human speech; NO verbatim transcript — topic-level truth only) |

Text distractors (real Chinese, from the frozen R3 `corpus.json`, license-clear): D1–D7, used as
**distractors only** so the media candidates must compete in the same ranked list. They are NOT
the truth for any media query.

### Frozen queries and EXACT relevance labels (positive = must retrieve the media candidate)

| q | query text (exact) | type | relevant (exact) |
|---|---|---|---|
| Q_IMG_ZH | 老子 道德經 註解 學說 | positive cross-modal | `["M_IMG_ZH"]` |
| Q_IMG_EN | quick brown dog jumped over the lazy fox | positive cross-modal | `["M_IMG_EN"]` |
| Q_AUD_ZH | Chinese language 中文 spoken language | positive cross-modal | `["M_AUD_ZH"]` |
| Q_NEG_ZH | 量子色動力學 膠子 強相互作用 | negative control | `[]` (report all ranked false hits) |
| Q_NEG_EN | 2024 annual financial statement net profit | negative control | `[]` (report all ranked false hits) |

- Labels are **executor-authored** (NOT independent/human review) — declared. They are derived
  from each media file's own recorded truth, not from the model output.
- Negative queries: product has no abstention; the returned top-k are **reported as false hits**.
  This is expected top-k NN behaviour, **not** an ACL/contract failure (per R3 audit).

## 3. Metrics & gates (frozen)

- `recall@k(positive) = |relevant ∩ topk| / |relevant|`; report k = 1, 3, 5.
- `MRR` and `top1_accuracy` over positive cross-modal queries.
- Negative controls: report the **full ranked** returned candidate list as raw false hits
  (id, kind, rank, score); no zero-hit gate.
- Lexical baseline: the real product `LexicalSearchService` over the **same** corpus, same queries,
  same k — reported side by side. A media source with no transcript has no lexical body; its lexical
  absence is **not** treated as quality evidence for vectors, and no global superiority is inferred.
- **Indicative-only** claim: 3 positive cross-modal queries over a small corpus. No default
  threshold is proposed or validated.

## 4. Transport & budget (hard)

| Item | Bound |
|---|---|
| `/health` GET | ≤ 1 (connect 3 s / total 8 s); reuse prior `/v1/models` metadata, no re-fetch |
| inference POST total | **≤ 16** (corpus text 7 + image 2 + audio 1 + queries 5 = 15 planned; 1 spare) |
| concurrency | 1 (strictly serial) |
| retries | **0** — timeout/interruption ⇒ record unknown, no replay |
| per inference POST timeout | 90 s |
| media per POST | ≤ 10 MiB total; audio input ≤ 30 s |
| ASR POST / OCR POST | 0 / 0 |
| other providers / models / installs / services / worker calls / autoupload | none |

## 5. Failure semantics

- Endpoint unreachable / `health` non-200 ⇒ record exact HTTP + error, **pause**, do not substitute
  another service/model. If the OCR wrapper PID is still alive when ready, **pause network** until it
  exits (bounded by wall budget); if it never exits in budget, deliver partial offline evidence and
  name the exact missing run.
- A media POST that fails (format/timeout) is recorded as a **failure with its raw response**, counted
  against POST budget; no silent retry. If the audio cannot be made acceptable **without synthesis**,
  report the exact missing sample rather than fabricate a label.
- Any negative false hit is reported, never hidden.

## 6. Counters to record

GET used, POST used (by kind), retries, concurrency, media MiB, audio seconds, dim/model/finite per
vector, fragment sha256 per input, raw response hashes. Cost/tokens = record actual; **unknown is
not zero**.
