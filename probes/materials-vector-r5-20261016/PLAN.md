---
title: "Materials Vector Quality R5 — FROZEN PLAN (pre-registered before any inference POST)"
doc_type: report
category: probe
status: "frozen — written before the first POST; no result may change it"
updated: "2026-10-16"
---

# FROZEN PLAN — materials-vector-r5-20261016

**This plan and the relevance labels in `corpus.json` are frozen BEFORE any POST.**
No result may change a threshold, a corpus item, a query, its labels, or the call count.
Failed attempts and false hits are kept and reported.

## 0. Purpose (scope honesty)

Close the **honest remaining LG-037 cross-modal gap**: the R4 run had only **1 real human audio**
candidate. This run adds a **second real human-audio candidate with trustworthy, non-model topic
truth** (a Wikimedia Commons pronunciation recording of 地球 / *Earth*), then re-runs a **frozen**
cross-modal retrieval measurement through the **actual current product** vector path.

**Out of scope / not claimed:** ASR (audio embedding ≠ ASR; LG-041 stays locked), OCR quality
(LG-035 separate), global model superiority, LG-040 gate pass, product threshold tuning, default
threshold calibration, any second live embedding model (no second authorized model exists).

## 1. Method (what is actually testable through the product)

Same real product path as R4 (no bypass, no mock):
1. `VectorSearchService.index_source()` embeds trusted formal text as a **text** vector, and any
   source whose `original.media_type` starts with `image/` or `audio/` is embedded **as media**
   (`EmbedInput.image` / `.audio` → `image_url` / `input_audio` data URLs) — never fabricated into
   text.
2. `VectorSearchService.search()` embeds **only a text query** (`EmbedInput.text_input`). The
   product has **no image→image or audio→audio query API**; text-query → media-vector ranking over
   the product's single ranked list is the strongest cross-modal comparison the current product
   supports.
3. Real `SourceStore`, `ContentStore`, `LexicalSearchService` (baseline) reused. Authorized
   candidates are re-verified via `authorize_and_verify` + 回源核对; **no score threshold, no
   abstention** (docs/08 froze no threshold field).

### Media handling constraints
- Media bytes are sent **as media** — never OCR'd/ASR'd to text first, never relabeled.
- **No image editing, no synthesized media.** 2 images + 1 audio are pre-existing licensed
  fixtures; 1 audio newly acquired from Commons (real human pronunciation, no TTS).
- Audio: endpoint expectation established in R4 = PCM WAV for `input_audio`. The only permitted
  transform is `ffmpeg -ac 1 -ar 16000 -t <clip> -c:a pcm_s16le`: **resampling + time-clipping,
  NOT lossless** (recorded honestly). The ORIGINAL ogg SHA-256 (and Commons SHA1) is the provenance
  anchor. No synthesis, no transcription.

## 2. Corpus + label manifest (`corpus.json`, frozen here)

| id | kind | file | license / provenance | trustworthy semantic truth (basis) |
|---|---|---|---|---|
| M_IMG_ZH | image/jpeg | Z1 page-10 JPG (preserved `lg035-truth-prep` worktree) | PD book scan + CC BY-SA 4.0 Wikisource human transcription | printed content = human proofread transcription: 老解老 / 老子學說 |
| M_IMG_EN | image/png | `probes/lg035/fixtures/phototest-rotated-L.png` | Apache-2.0 (`tesseract-ocr/test`) | human gold text: "… the quick brown dog jumped over the lazy fox" |
| M_AUD_ZH | audio/ogg→PCM | `probes/lg039/evidence/real_voice_chinese_language-1.ogg` | CC BY-SA 3.0 (Commons `File:Chinese language-1.ogg`, real human) | topic = **Chinese language / 中文** (no verbatim transcript) |
| M_AUD_DIQIU | audio/ogg→PCM | `private/Zh-地球.ogg` (Commons `File:Zh-地球.ogg`) | **CC BY-SA 4.0** (Commons, author CanonNi, own work 2024-10-07) | the file's OWN description page declares `{{pronunciation|地球|lang=zh|translation=Earth}}` ⇒ topic = **Earth / 地球** (real human; no TTS) |
| D1–D3, D5–D6 | text | real Chinese transcribed fragments (frozen R3/R4) | CC BY-SA 4.0 + PD scan | **distractors only** |
| T_NORTHWIND | text | real Chinese dialect fragment (same provenance) | CC BY-SA 4.0 + PD scan | **Chinese textual positive target** for Q_TXT_ZH |

Acquisition honesty: the second audio was obtained with the **official Commons API** (metadata:
license/author/page/hash) plus **ONE** direct upload GET; download SHA1 verified against the API's
declared SHA1. Metadata raw response retained in `http/commons_zh_diqiu_metadata.raw.json`.

### Frozen queries and EXACT relevance labels

| q | query text (exact) | type | relevant (exact) |
|---|---|---|---|
| Q_IMG_ZH | 老子 道德經 註解 學說 | positive cross-modal image | `["M_IMG_ZH"]` |
| Q_IMG_EN | quick brown dog jumped over the lazy fox | positive cross-modal image | `["M_IMG_EN"]` |
| Q_AUD_LANG | Chinese language 中文 spoken language | positive cross-modal audio | `["M_AUD_ZH"]` |
| Q_AUD_EARTH | 地球 Earth 發音 spoken word | positive cross-modal audio | `["M_AUD_DIQIU"]` |
| Q_TXT_ZH | 北風 跟 太陽 爭論 誰的本事大 | positive Chinese text | `["T_NORTHWIND"]` |
| Q_NEG_ZH | 量子色動力學 膠子 強相互作用 | negative control | `[]` |
| Q_NEG_EN | 2024 annual financial statement net profit | negative control | `[]` |

- Labels are **executor-authored**, derived from each source file's own recorded truth/description,
  **NOT from model output** — declared. R4's queries are **not** reused for calibration.

## 3. Metrics & gates (frozen)

- `recall@k(positive) = |relevant ∩ topk| / |relevant|`; report k = 1, 3, 5.
- `MRR` and `top1_accuracy` over positive queries (cross-modal + textual).
- Negative controls: report the **full ranked** returned candidate list as raw false hits
  (id, kind, rank, score); **no zero-hit gate**.
- Lexical baseline: the real product `LexicalSearchService` over the **same** corpus, same queries,
  same k — reported side by side. Transcriptless media has no lexical body; its lexical absence is
  **NOT** quality evidence for vectors, and no global superiority is inferred.
- **Indicative-only**: 4 cross-modal positive + 1 textual positive over a small corpus. No default
  threshold proposed or validated.
- **HARD GATE (declared, from LG-037 acceptance):** both real audio candidates must be **reachable**
  (Recall@5 = 1.0 for the two audio queries) AND both real image candidates reachable
  (Recall@5 = 1.0 for the two image queries) AND the Chinese textual positive reachable. Any hard
  gate unmet ⇒ reported as **FAIL**; no quality-pass claim.

## 4. Transport & budget (hard)

| Item | Bound |
|---|---|
| `/health` GET | ≤ 2 (connect 5 s / total 10 s); `/v1/models` metadata reused, no re-fetch |
| inference POST total | **≤ 18** planned cap; planned = 6 text + 2 image + 2 audio + 7 queries = **17**, 1 spare reserved for at most one raw-audio format attempt |
| concurrency | 1 (strictly serial) |
| retries | **0** — timeout/interruption ⇒ record unknown, no replay |
| per inference POST timeout | 90 s |
| media per POST | ≤ 10 MiB total; audio input ≤ 30 s |
| ASR POST / OCR POST | 0 / 0 |
| other providers / models / installs / services / worker calls | none |
| public acquisition (separate) | metadata GET ≤ 10 total; download ≤ 1 file ≤ 5 MiB; no remote execution |

POST reservation ledger persisted **before** each forwarded POST; raw redacted HTTP/response scores
captured as available.

## 5. Failure semantics

- Endpoint unreachable / `health` non-200 ⇒ record exact HTTP + error, **pause**, do not substitute
  another service/model.
- **Network gate:** do NOT send inference/health/models **while** the prior OCR owner wrapper whose
  argv contains basename `materials-ocr-r5-20261016.txt` is alive (exclude my own wrapper). Offline
  + public provenance GETs allowed meanwhile. Do not kill the other owner.
- A media POST that fails (format/timeout) is recorded as a **failure with its raw response**,
  counted against POST budget; no silent retry. If an audio cannot be made acceptable **without
  synthesis**, report the exact missing sample rather than fabricate a label.
- Any negative false hit is reported, never hidden.

## 6. Counters to record

GET used, POST used (by kind), retries, concurrency, media MiB, audio seconds, dim/model/finite per
vector, fragment SHA-256 per input, raw response hashes. Cost/tokens = record actual; **unknown is
not zero**.
