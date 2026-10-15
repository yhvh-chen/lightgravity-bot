# PROGRESS — media → text → Markdown → rebuildable index (isolated prototype)

- Task: small closed-loop probe: Chinese image OCR + scanned-PDF OCR, short audio transcription,
  Markdown/frontmatter source records, minimal rebuildable lexical index with search.
- Scope: isolated prototype only. NOT product implementation, NOT installing features.
- Writable dir: `/tmp/lightgravity-media-text-index-20261015/` only (owner `yhvh:yhvh`).
- Target service: only `http://192.168.8.12:11434` (llama.cpp router `b11641-843e7dcc1`).
- Constraints honored: no pull/new weights, no service config/default change, no explicit unload of
  other models, no restart, no product dir / worktree / PROJECT / backlog write, no `.env` read,
  no credentials printed, no new dependency install, no remote script, no other agents.
- Budget: target generation/OCR/ASR/embedding inference POSTs <= 10 (failures count);
  total target HTTP <= 24; connect <= 5 s; normal read <= 45 s; pre-existing large-model first
  load/generation hard cap <= 180 s (at most 1 timeout, then stop that model);
  total real probe <= 12 min (code/report excluded).
- Samples: synthetic / non-private only. Prior probe evidence is read-only reference:
  `/tmp/lightgravity-eg2-endpoint-20261015/{REPORT.md,DOC_CORRECTION.md}`.

## Truthfulness rules for this log

- Only record facts after the action actually ran; no pre-checked items; no invented timestamps.
- Failed/unverified steps are recorded as such, not hidden.

## Log (UTC)

- 2026-10-15T11:04:12Z  Created writable dir `/tmp/lightgravity-media-text-index-20261015`.
- 2026-10-15T11:04Z       Read mandatory context: `agent.md`, prior `REPORT.md` + `DOC_CORRECTION.md` + `PROGRESS.md`.
- 2026-10-15T11:04Z       Env scan: `/usr/bin/python3` 3.14.4 has Pillow 12.1.1 / numpy 2.3.5 / pyyaml 6.0.3; CJK fonts present (Noto Sans CJK SC); ffmpeg + poppler-utils present.
- 2026-10-15T11:04Z       TTS scan: no espeak/espeak-ng/piper binary, BUT `libespeak-ng.so.1` + `espeak-ng-data` (incl. `cmn_dict`, `lang/sit/cmn`) present → ctypes test synthesized 9.02 s Mandarin WAV (22050 Hz mono) offline, no download. Synthetic (formant) voice, not human.
- 2026-10-15T11:05:08Z  Fixtures generated (`make_fixtures.py`, synthetic/non-private):
  - `fixtures/screenshot.png` sha256 74025921f66ef88a… (Chinese clean render)
  - `fixtures/scanned.pdf` sha256 bd2045bdd892d436… — raster image only; `pdftotext` output = 1 byte (form feed) ⇒ **NO text layer** (true scanned-type PDF)
  - `fixtures/scanned_page-1.png` sha256 04c3c4aa7019c6b9… (PDF page rendered via `pdftoppm -r 150`; this is the OCR input)
  - `fixtures/audio.wav` sha256 580761a61c33ffa6… — Mandarin, 22050 Hz mono, **11.875 s**, synthesized by espeak-ng `cmn` (not human)
  - frozen ground truth: `ground_truth/{doc_image,doc_pdf,audio}.txt`; manifest `fixtures_manifest.json`.
- 2026-10-15T11:05Z       Fixture legibility visually verified (both images render correct Chinese; PDF page legible).

## Budget counters (live)

- Target HTTP total: see `budget_counters.json` / `http_log.jsonl` (authoritative).
- Inference POST cap ≤10: OCR used 2 so far.

## Results (UTC)

- 2026-10-15T11:05:35Z  Discovery: 2 target HTTP (GET `/v1/models`, GET `/props`), 0 inference. Live model
  list unchanged from prior probe: `bge-reranker-v2-m3-Q8_0`(text), `embeddinggemma-2-Q8_0`(text/image/audio/video),
  `gemma4-mtp`(text/image, unloaded), `qwen3.8-27b`(text/image, unloaded). Router `models_autoload=true`,
  `max_instances=2`.
- 2026-10-15T11:08:25Z  **OCR #1** `run_ocr.py fixtures/screenshot.png doc_image qwen3.8-27b` → HTTP 200.
  This triggered router auto-load of `qwen3.8-27b` (first call 162.25 s, within 180 s cap; `finish_reason=stop`,
  usage prompt 562 / completion 65 / total 627). Extracted text **exact full match** (CER 0.0, char-acc 1.0),
  fields 编号/日期/金额 all exact. Ground truth NOT in prompt.
- 2026-10-15T11:08:49Z  **OCR #2** `run_ocr.py fixtures/scanned_page-1.png doc_pdf qwen3.8-27b` (raster PDF page,
  no text layer) → HTTP 200, 21.80 s, `finish_reason=stop`, usage 562/83/645. Extracted text **exact full match**
  (CER 0.0), fields 发票号码/开票日期/价税合计 all exact.
- Metrics: `ocr_metrics.json`; raw responses `ocr_*_raw_response.json`; extracted `ocr_*_extracted.txt`.
- **Caveat:** clean synthetic samples; this is a small-sample sanity result, NOT evidence of production OCR quality.
- Inference POSTs used: 2 of ≤10.
- 2026-10-15T11:09Z **ASR attempt** (`run_asr.py`, Mandarin 11.875 s synthetic WAV, ground truth NOT sent):
  - `POST /v1/audio/transcriptions` (multipart, model `qwen3.8-27b`) → **HTTP 501** `"The current model does not support audio input."`
  - `POST /v1/chat/completions` with `input_audio` part → **HTTP 500** `"audio input is not supported - hint: ... you may need to provide the mmproj"`
  - ⇒ **ASR = FAIL/gap**: no ASR-capable model / audio mmproj installed. `qwen3.8-27b`(tested) and `gemma4-mtp`(NOT tested) declare text+image only; only the embedding model declares audio and prior probe showed it cannot transcribe. No download/deploy attempted. Chinese transcription **not measured** (no backend). Evidence: `asr_results.json`.
- Inference POSTs used: 4 of ≤10 (2 OCR + 2 ASR).
- 2026-10-15T11:09Z  **Markdown records** built (`build_docs.py`): `docs/doc_image.md` (status success),
  `docs/doc_pdf.md` (status success), `docs/audio.md` (status **failed**, no fabricated extracted text).
  YAML frontmatter is legal (parsed back by pyyaml) and marked `record_type: probe_source_record` /
  "NOT a product schema". Extracted body = actual OCR output, never ground truth.
- 2026-10-15T11:10Z  **Lexical index** (`index_lib.py`, `run_index_tests.py`): token-union candidate +
  normalized-substring verification. Results (`index_tests.json`): cross-material `服务` → 2 docs;
  exact `LG-2026-1015-007`/`8,765.42`/`25337000000098765432` → correct single docs; negative controls
  `紫水晶矩阵`/`紫水晶项目` → 0 hits. (First token-only pass gave a false positive via shared token `项目`;
  substring verification fixed it — recorded honestly.)
- 2026-10-15T11:10Z  **Rebuildability:** deleted `index.json` (cache only) and rebuilt → postings+documents
  byte-identical, all source hashes unchanged, query results identical. `index.json` now sha256 `04a0d47c…`.
- 2026-10-15T11:10Z  **Stale-hash rejection:** sandbox copy (originals untouched), mutated copied
  `screenshot.png` → `doc-image-001` hit rejected (`stale_hash=true`), `doc-pdf-001` still accepted.
- 2026-10-15T11:10:44Z  **Embedding** (1 batched POST, `embeddinggemma-2-Q8_0`, 5 inputs, dim 768,
  finite, L2=1.0, 0.076 s): semantic query `多久之内必须给出回应` ranks doc_image 0.657 > doc_pdf 0.609;
  exact number ranks doc_pdf 0.725 > doc_image 0.678; negative 0.568/0.578 (lowest). Vectors cached
  `embeddings.npy` + `embeddings.json` (first 8 dims only in JSON).
- Final target HTTP = 7, inference POSTs = 5 (cap 10). ASR failures were expected/negative; no retries.
- Status: loop complete for image/scanned-PDF text; **audio leg is a real service gap (not hidden)**.
  REPORT.md written. Not product, not integrated, small synthetic sample.
