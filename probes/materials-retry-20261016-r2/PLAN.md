---
title: "Materials Retry R2 — POST PLAN (frozen before any POST)"
doc_type: report
category: probe
status: "frozen — written before the first inference POST"
updated: "2026-10-16"
---

# POST PLAN — materials-retry-20261016-r2

This plan is **frozen before** the first POST. No result may change it.

## Discovered service facts (from Stage A GETs, all HTTP 200)

- Endpoint `http://192.168.8.12:11434` — llma.cpp **router**, `build_info=b11641-843e7dcc1`,
  `role=router`, `max_instances=2`, `models_autoload=true`. **Not Ollama** (`/api/ollama` never touched).
- `/v1/models` input modalities (verbatim, scrubbed):
  - `embeddinggemma-2-Q8_0` (aliases `embeddinggemma-2`,`embeddinggemma-300M-Q8_0`,`embeddinggemma-300m`,`embeddinggemma2`):
    `input_modalities=["text","image","audio"]`, `output_modalities=["text"]`, mean pooling, `--embeddings`, `--mmproj` present,
    `context_length=262144`. **This is the embedding / multimodal model.**
  - `gemma4-mtp`: `input_modalities=["text","image"]` (vision chat).
  - `qwen3.8-27b`: `input_modalities=["text","image"]` (vision chat).
  - `bge-reranker-v2-m3-Q8_0`: `input_modalities=["text"]` (reranker only).
- All models listed `status.value="unloaded"` (router autoload on first request; prior probe measured 162 s cold load).

## Capability determination (honest, from metadata only)

| Capability | Backend | Declared by metadata? | Decision this package |
|---|---|---|---|
| Chat/vision OCR | `OpenAICompatOcrBackend` → `/v1/chat/completions` | **Yes** — `qwen3.8-27b` declares `image`; prior source-intake probe verified this exact schema & model (CER 0.0 synthetic) | **1 POST allowed** with Z1 |
| Embedding (text) | `OpenAICompatEmbeddingBackend` → `/v1/embeddings` | **Yes** — `embeddinggemma-2-Q8_0` `--embeddings`, prior probe verified `/v1/embeddings` 768-dim L2=1.0 | **1 POST allowed** |
| ASR / audio | — | **No** — prior probe: `/v1/audio/transcriptions`→501, chat `input_audio`→500; only audio-declaring model is the *embedding* model which does not compute logits | **0 POST** (LG-041 stays locked) |

**Active model IDs used:** OCR = `qwen3.8-27b`; embedding = `embeddinggemma-2-Q8_0`.
The product adapters take model/base_url from env; **no product code is modified**. The adapters do **not**
send `chat_template_kwargs`; the prior probe sent `enable_thinking=false` but the product adapter is used
as-is (bounded `max_tokens`, `temperature=0`, `stream=false`) — this deviation is recorded, not patched.

## Budget & transport

- **POST hard cap: 2 total** (OCR ≤1 + embedding ≤1). ASR 0. Counts start at 0/2.
- `HTTP inference timeout = 90 s` (cold start allowed a single 120 s only if fixed here): OCR uses
  `cold=True` → cold bound fixed at **120 s** (single request; docs default is 180 but this package freezes 120).
- concurrency 1, retries 0, input ≤ 2 MiB, output ≤ 2048 tokens. No auto-retry on failure.
- No DeepSeek product worker, no real Task/Run writes, no external third-party upload.

## OCR smoke (POST #1)

- Fixture: `probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg`
  sha256 `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f` (333,996 B), media `image/jpeg`.
  Real Chinese printed book page (老解老 p10); human ProofreadPage **level 3** truth in
  `probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z1.p10.txt`.
- Path: product `OpenAICompatOcrBackend.transcribe`, `/v1/chat/completions`, model `qwen3.8-27b`, image URL data part.
- Expected output: the page's visible Chinese text as a machine transcription; never truth-in-prompt.
- **Fixed truth / threshold (pre-registered, from SCORING-PROTOCOL §1–§2)**: page CER ≤ **0.15** after
  NFKC + whitespace-strip, Levenshtein over code points. Threshold not relaxed after seeing results.
- Table gate (Z2) is **not** asserted this package (no Z2 POST).

## Embedding smoke (POST #2)

- Real Chinese text input (single batch; one input string). No vector dimension guessed; read actual dim/model.
- Path: product `OpenAICompatEmbeddingBackend.embed`, `/v1/embeddings`, model `embeddinggemma-2-Q8_0`.
- Record: finite / nonzero / actual dimension / model ID / input sha256. **Vector ≠ quality**; real
  Recall@k deferred to a later frozen set (LG-040).
- If the model rejects plain text embeddings (it is a multimodal model), record the error honestly;
  no protocol guess beyond the already-verified `/v1/embeddings` `input` shape.

## Counters at PLAN freeze

- GET used: 3/3 (cap reached) · POST used: 0/2 · TCP probe used: 0/1 · retries: 0
