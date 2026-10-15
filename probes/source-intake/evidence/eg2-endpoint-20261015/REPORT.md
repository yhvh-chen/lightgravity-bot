# REPORT — Bounded probe of `http://192.168.8.12:11434` (EmbeddingGemma2 / multimodal / transcription)

- Author: pi technical-test executor (bounded, read-only probe)
- Date (UTC): 2026-10-15, window 10:54:25Z – 10:56:56Z (~2 min 31 s total, budget ≤ 8 min)
- Writable dir: `/tmp/lightgravity-eg2-endpoint-20261015/` (owner `yhvh:yhvh`, mode 700)
- Target service: only `http://192.168.8.12:11434`; no other ports or LAN hosts scanned.
  (Separately, 4 read-only fetches of official llama.cpp docs from `raw.githubusercontent.com`
  were used as schema references — see §5; they are not target-service probes.)
- Constraints honored: no product/config change, no remote writes, no pull/download, no other proxy,
  no `.env` read, no credentials printed, stdlib-only client (`urllib`/`http.client`).

---

## 0. Headline result

The endpoint is **NOT Ollama**. It is a **llama.cpp `llama-server` (router mode)** build
`b11641-843e7dcc1` behind an OpenAI-compatible API. The Ollama API (`/api/version`,
`/api/tags`) is **absent (HTTP 404)**; `/api/show` is Ollama-specific and was **not requested**
(its absence is inferred, not measured — see `DOC_CORRECTION.md` C2).

The target model exists and is loaded: **`embeddinggemma-2-Q8_0`**
(aliases `embeddinggemma-2`, `embeddinggemma2`, `embeddinggemma-300m`, `embeddinggemma-300M-Q8_0`).

| Area | Verdict | Basis |
|---|---|---|
| Service / model discovery | **pass** | `/v1/models`, `/props`, `/health` |
| Text embedding | **pass (sanity probe only)** | 768-dim, finite, L2=1.0, sensible ranking |
| Image → embedding | **pass (transport-level consumption only)** | text+image differs from text-only control and a second valid image further changes the vector (cos 0.889); invalid image rejected 500 |
| Audio → embedding | **pass (transport-level consumption only)** | text+audio differs and a second valid tone further changes the vector (cos 0.979); invalid audio rejected 500 |
| Video → embedding | **pass (transport-level consumption only)** | text+video differs from text-only control |
| Transcription / ASR | **fails for `embeddinggemma-2-Q8_0` on this route** | route exists; that embedding model returns "does not support logits computation"; other models untested, no reader wiring evidence (see `DOC_CORRECTION.md` C3) |
| Recognition/quality of media embeddings | **unverified** | synthetic samples cannot prove semantic quality |

> **Identity note (corrected — see `DOC_CORRECTION.md` C1):** the exact ID is `embeddinggemma-2-Q8_0`,
> one alias is `embeddinggemma-300m`, and the service reports `n_params = 271002648` with a separate
> `mmproj` file loaded. This is **consistent with** the official EmbeddingGemma 2 specification
> (≈271 M text backbone + separate 170 M vision / 300 M audio components); the 271 M figure is most
> plausibly the **text backbone only**. Checkpoint identity remains **unknown** (no GGUF metadata
> dump, checksum, or provenance check was done), but there is **no counter-evidence** against the
> "EmbeddingGemma 2" identity and no basis to call it a relabelled older model. There is no
> `gemini-embedding-2` model on this host.

---

## 1. Service identification (actual evidence)

Raw non-secret metadata saved in `version.json`, `tags.json`, `v1_models.raw.json`.

| Request | Status | Notes |
|---|---|---|
| `GET /api/version` | 404 | error envelope `{"error":{"message":"File Not Found","type":"not_found_error","code":404}}` — **not** Ollama's `{"error":"..."}` |
| `GET /api/tags` | 404 | same envelope → no Ollama model registry |
| `GET /api/show` | *not requested* | Ollama-specific; **not probed**. Absence inferred from the missing Ollama API, not measured (see `DOC_CORRECTION.md` C2) |
| `GET /` | 415 | non-JSON 44 bytes |
| `GET /health` | 200 | `{"status":"ok"}` |
| `GET /v1/models` | 200 | OpenAI-compatible; `owned_by: llamacpp` |
| `GET /props` | 200 | `{"role":"router","max_instances":2,"models_autoload":true,"model_alias":"llama-server","build_info":"b11641-843e7dcc1"}` |

Installed models (`GET /v1/models`, 2026-10-15T10:54:45Z):

| id | aliases | state | declared input modalities* |
|---|---|---|---|
| `bge-reranker-v2-m3-Q8_0` | `bge-reranker-v2-m3` | loaded | text |
| `embeddinggemma-2-Q8_0` | `embeddinggemma-2`, `embeddinggemma2`, `embeddinggemma-300m`, `embeddinggemma-300M-Q8_0` | loaded | text, image, audio, video |
| `gemma4-mtp` | — | unloaded (31 B Q4) | text, image |
| `qwen3.8-27b` | — | unloaded | text, image |

\* `architecture.input_modalities` is **router-reported metadata, not independently proven capability**.
No model was loaded/unloaded/changed by this probe.

### Target model facts (`embeddinggemma-2-Q8_0`)
- `status = loaded`; launch args include `--embeddings`, `--pooling mean`,
  `--mmproj /models/mmproj-embeddinggemma-2-Q8_0.gguf` (multimodal projector present).
- `meta`: `ftype=Q8_0`, `size=294064224`, `n_params=271002648`, `n_ctx_train=262144`,
  `context_length=262144`, `n_embd=512` (reported; see actual output dim below).
- `/api/show` equivalent: this service has no `/{model}` retrieve route (`GET /v1/models/<id>` → 404);
  the model entry from `GET /v1/models` is the authoritative metadata available (`v1_models.raw.json`).

---

## 2. Text embedding validation (sanity probe, not a quality benchmark)

Single `POST /v1/embeddings` (batch of 4 inputs), 2026-10-15T10:55:49Z.
Raw result: `results_text.json`, `text_test.out`.

- Inputs: `"A cat sits on the mat."`, `"A kitten is resting on a rug."`,
  `"量子色动力学描述胶子之间的强相互作用。"`, `"一只猫坐在垫子上。"`
- Output: `n_vectors=4`, `dim=768` each, all **finite**, **L2 norm = 1.0**;
  `usage.prompt_tokens=41`; latency 0.064 s.
- **Dim note:** the server metadata reported `n_embd=512` but actual returned vectors are **768-dim**.
  Report the measured 768, not the metadata field.

Cosine similarities (rough ordering):

| pair | cos |
|---|---|
| zh "猫坐在垫子上" vs en "A cat sits on the mat." | **0.870** |
| en near ("kitten/rug") vs en anchor ("cat/mat") | **0.781** |
| zh near vs en near | **0.726** |
| en near vs zh unrelated (QCD) | 0.527 |
| en anchor vs zh unrelated | 0.566 |
| zh unrelated vs en anchor | 0.566 |

Meaningful cat/kitten pairs score clearly above unrelated QCD pairs. This is a **liveness / ordering
probe only**, not a retrieval-quality benchmark.

---

## 3. Multimodal embedding probes (transport consumption only)

Schema source (version-matched official docs, read-only):
- `https://raw.githubusercontent.com/ggml-org/llama.cpp/b11641/tools/server/README.md`
  (saved `llamacpp_server_README_b11641.md`) — §"POST /v1/embeddings" documents a `content` array per
  input element with `text`, `image_url`, `input_audio`, `input_video` parts.
- `https://raw.githubusercontent.com/ggml-org/llama.cpp/b11641/docs/multimodal.md`
  (saved `llamacpp_multimodal_b11641.md`) — image/audio/video via `libmtmd`, experimental.
- Deployed route registration verified in source for the build:
  `https://raw.githubusercontent.com/ggml-org/llama.cpp/b11641/tools/server/server.cpp`
  (`ctx_http.post("/v1/embeddings", ...)`, `ctx_http.post("/v1/audio/transcriptions", ...)`).

Exact request shape actually used (payloads abbreviated; full request shapes in `results_mm.json`):

```json
POST /v1/embeddings
{ "model": "embeddinggemma-2-Q8_0",
  "encoding_format": "float",
  "input": [
    { "content": [
        { "type": "image_url", "image_url": { "url": "data:image/png;base64,<...>" } },
        { "type": "text", "text": "a photograph" } ] } ] }
```

Results (2026-10-15T10:56:04Z, `results_mm.json`, `mm_test.out`, vectors in `mm_raw/`):

| probe | HTTP | dim | elapsed | finding |
|---|---|---|---|---|
| `img_text_control` (text only) | 200 | 768 | 0.030 s | control vector |
| `image_text` (png + same text) | 200 | 768 | 0.542 s | **differs from control**, cos = **0.7654** → image consumed |
| `audio_text_control` (text only) | 200 | 768 | 0.008 s | control vector |
| `audio_text` (wav + same text) | 200 | 768 | 0.823 s | **differs from control**, cos = **0.9306** → audio consumed |
| `video_text` (mp4 + text) | 200 | 768 | 0.240 s | **differs from control**, cos = **0.7158** → video consumed |
| `invalid_image` (png data URI of non-image bytes) | **500** | — | 0.047 s | explicitly rejected: `"Failed to load image or audio file"` |
| `invalid_audio` (garbage bytes) | **500** | — | 0.047 s | explicitly rejected: `"Failed to load image or audio file"` |

**Follow-up content-contrast evidence (`evidence_followup/`, 2026-10-15T10:58:43Z):** to separate
"real media content changes the embedding" from "a media placeholder/token was merely appended",
two **second** synthetic samples with different content but the same geometry/format, text and field
order were sent (2 additional embedding POSTs; cumulative 10):

| comparison | cos vs original | max abs delta | dim | finite | norm | HTTP |
|---|---|---|---|---|---|---|
| `image2_text` (64×64 horizontal bands + black block) vs original `image_text` | **0.888551** | 0.08408853 | 768 | true | 1.0 | 0.099 s |
| `audio2_text` (880 Hz, same 16 kHz/2.0 s/16-bit length) vs original `audio_text` | **0.978952** | 0.03421662 | 768 | true | 1.0 | 0.027 s |

Both deltas are far above floating-point rounding, so **different valid media content influences the
embedding vector** (not just a placeholder/token effect). This is still **input-consumption only**:
no retrieval-accuracy, recognition-quality, or ASR claim is made.

**Interpretation discipline**
- "Differs from text-only control" proves the media bytes reach the embedding computation
  (not a silent ignore) at this build. It does **not** prove semantic recognition quality.
- The follow-up shows the *content* of the media (not only its presence) changes the vector.
- The invalid-media 500 responses show the media loader is genuinely invoked (not ignored).
- Synthetic image (64×64 colour bands) and synthetic tones (440 Hz / 880 Hz) are non-private and
  **cannot** evidence recognition quality, and the tones **cannot** evidence ASR/transcription.

---

## 4. Transcription / ASR

- The deployed build registers a real proxy route: `POST /v1/audio/transcriptions` (and
  `/audio/transcriptions`), confirmed in `server.cpp` for `b11641`.
- `POST /v1/audio/transcriptions` (JSON, base64 file) → **400** `"No input file found for transcription"`
  (multipart/form-data expected).
- `POST /v1/audio/transcriptions` (proper multipart, `model=embeddinggemma-2-Q8_0`, `sample.wav`) →
  **500** `"the current context does not support logits computation. skipping"`.
- `GET /v1/audio/transcriptions` → 404.
- Router metadata declares **no audio-capable generation/ASR model** installed (the only
  audio-declaring model is the embedding model; `gemma4-mtp` and `qwen3.8-27b` declare text+image
  only). This is metadata-based and does not independently test those other models; it is not a
  general proof that the server cannot transcribe.

**Conclusion:** 当前该 embedding 模型 `embeddinggemma-2-Q8_0` 在该转写路由上不提供开箱转写（该模型
本身报 logits 不可用）。**未验证其它模型**，也没有 reader 接线证据；本探针未证明服务器整体不具备
转写能力，只证明这一个模型在这条路由上失败。Embedding 向量**不是**转写。No reader/ASR model was
deployed, downloaded, or loaded. (Unloaded models were left untouched.)

---

## 5. HTTP accounting, timing, failures

Target-service requests (all to `192.168.8.12:11434`): original **21**, plus **2** in the follow-up
round = **23 total**.

- Discovery/read-only: 10 (`/api/version`, `/api/tags`, `/`, `/v1/models` ×2, `/health`, `/api/models`,
  `/props`, `/v1/models/<id>`, `/version`).
- Embedding inference POSTs: **8** original (1 text batch + 7 multimodal) + **2** follow-up
  (second image + second audio) = **10 cumulative** (cap ≤10).
- Transcription probes: 3 (2 error-format + 1 multipart).
- Failures observed: 404 ×6, 415 ×1, 400 ×1, 500 ×3. All were expected/negative probes; no retries,
  no unbounded loops.

Timing: every original target request returned in ≤ 0.83 s (max `audio_text` 0.823 s); the two
follow-up requests returned in 0.099 s and 0.027 s (each timeout ≤30 s). Original session
10:54:25Z–10:56:56Z = **2 m 31 s**; follow-up round ~0.15 s at 2026-10-15T10:58:43Z. No request hit
the 5 s connect / 30 s read / 90 s first-load limits (model was already loaded).

External (documentation) reads — **not target-service probes, listed separately**: 4 small files from
`raw.githubusercontent.com/ggml-org/llama.cpp` (build tag `b11641` README, `multimodal.md`,
`server.cpp`; plus `master` README for cross-check). No remote scripts executed. The target-service
scope was only the one IP:port above.

---

## 6. Samples and limitations

- `sample.png` (153 B, 64×64 RGB bands + white block) — synthetic, no private data.
- `sample.wav` (64 044 B, 2.0 s, 16 kHz mono, 440 Hz sine) — synthetic, not speech.
- `sample.mp4` (1 911 B, 1 s) — synthesized via local `ffmpeg`.
- Follow-up samples in `evidence_followup/`: `sample2.png` (159 B, 64×64) and `sample2.wav`
  (64 044 B, 2.0 s, 16 kHz, 880 Hz) — synthetic, second content variants.
- The 768-dim vectors are derived from these synthetic inputs; saved under `mm_raw/` and
  `evidence_followup/mm_raw_followup/` as evidence.
- Limitations: (a) synthetic media cannot establish semantic embedding quality; (b) the model is an
  **embedding/feature-extraction** model, not a captioner or ASR; (c) `input_modalities` is
  router metadata; only transport-level/content-contrast consumption was independently shown; (d) the
  checkpoint identity is **unknown** (not provenance/checksum-verified), though there is no
  counter-evidence against `embeddinggemma-2` (see `DOC_CORRECTION.md` C1).

---

## 7. Evidence files (in `/tmp/lightgravity-eg2-endpoint-20261015/`)

| File | Content |
|---|---|
| `PROGRESS.md` | timestamped progress log |
| `version.json`, `tags.json` | Ollama API 404 evidence |
| `v1_models.raw.json` | full `/v1/models` response (all 4 models) |
| `models_full.txt`, `embed_model_entry.txt` | model list / target model entry |
| `results_text.json`, `text_test.out` | text embedding probe + cosine ordering |
| `results_mm.json`, `mm_test.out`, `mm_raw/*.embedding.json` | multimodal probes + raw vectors |
| `sample.png`, `sample.wav`, `sample.mp4` | original synthetic non-private samples |
| `DOC_CORRECTION.md` | corrections/retraction log (C1–C6) |
| `evidence_followup/` | second-media content-contrast evidence: `followup_media.py`, `followup.out`, `results_followup.json`, `sample2.png`, `sample2.wav`, `mm_raw_followup/*.embedding.json` |
| `asr_probe.out`, `asr_multipart_probe.out` | transcription-route probes |
| `llamacpp_server_README_b11641.md`, `llamacpp_multimodal_b11641.md`, `llamacpp_server_server_b11641.cpp`, `llamacpp_server_README_master.md` | official schema sources |
| `probe.py`, `run_tests.py`, `run_mm.py` | stdlib probe code (reproducible) |

No secrets/credentials are present in any artifact. No `.env` was read. No product repo/worktree,
`PROJECT.md`, `backlog/`, or `.env` was written.

---

## 8. Recommended next steps (NOT executed here)

1. **Confirm model identity with PM/owner (unchanged: identity `unknown`).** Per the PM-provided
   official card, EmbeddingGemma 2 is ≈271 M text + separate 170 M vision / 300 M audio, and this
   deployment loads `mmproj` separately — so `n_params=271002648` is consistent with the text
   backbone. The earlier "300 M relabel" inference is **retracted** (`DOC_CORRECTION.md` C1). A GGUF
   metadata dump/checksum would still settle provenance, but there is no reason to doubt the ID.
2. **Quality evaluation is required before claiming image/audio feature extraction.** Run a labelled
   image–text retrieval set and a real speech set against the `/v1/embeddings` content schema;
   compare against a text-only baseline and a known vision/audio encoder. Current evidence is
   transport-only.
3. **If ASR is required**, a properly licensed audio-capable ASR/omni model must be installed on the
   server by the owner (not by this probe). Then re-test `/v1/audio/transcriptions` with
   multipart/form-data and a known transcript.
4. **SoT file index feasibility:** the text embedding path is functional (768-dim, normalized) and
   `/v1/embeddings` accepts batch `input`; a file index could use text chunks today. Multimodal
   indexing should wait for (2).
5. **Do not** infer transcription or recognition quality from the 200 responses; the only established
   facts are (a) text embeddings work and (b) media bytes, and different media content, influence the
   embedding at this build (transport/content-contrast only).

Status: **真实有界探针完成；未改产品、未提交、未发布。**
