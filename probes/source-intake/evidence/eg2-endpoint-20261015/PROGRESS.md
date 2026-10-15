# PROGRESS — Bounded Ollama endpoint probe

- Task: probe `http://192.168.8.12:11434` for EmbeddingGemma2 multimodal/embedding capability, transcription, file index (SoT) feasibility.
- Scope: read-only GET/POST; no model pull; no config change; no remote writes; no other proxies.
- Authorized network: only 192.168.8.12:11434. Connect <=5s, read <=30s, first-load inference <=90s, total <=8min. (Separate from target service: 4 read-only official llama.cpp doc fetches from raw.githubusercontent.com as schema reference; listed independently, not target-service probes — see DOC_CORRECTION.md C4.)

## Log (UTC)

- 2026-10-15T10:54:25Z  Session start. Read /home/yhvh/code/lightgravity-bot/agent.md.
- 2026-10-15T10:54:27Z  Created writable dir /tmp/lightgravity-eg2-endpoint-20261015 (owner yhvh:yhvh, mode 700).
- 初始待执行项（未记录精确时刻）Pending: GET /api/version, GET /api/tags. [correction: the literal `10:54:2xZ` was an initial placeholder, not a recorded timestamp — see DOC_CORRECTION.md C5]

## Findings so far (UTC)

- 2026-10-15T10:54:36Z  GET /api/version -> HTTP 404, error envelope `{"error":{"message":"File Not Found","type":"not_found_error","code":404}}` => NOT Ollama.
- 2026-10-15T10:54:37Z  GET /api/tags -> HTTP 404 same envelope. Ollama API absent.
- 2026-10-15T10:54:40Z  GET / -> HTTP 415 (44 bytes non-JSON). GET /health -> 200 {"status":"ok"}.
- 2026-10-15T10:54:41Z  GET /v1/models -> 200, OpenAI-compatible. owned_by=llamacpp => llama.cpp-based server behind a manager (NOT Ollama).
- 2026-10-15T10:54:45Z  n_models=4: `bge-reranker-v2-m3-Q8_0` (loaded), `embeddinggemma-2-Q8_0` (loaded), `gemma4-mtp` (unloaded), `qwen3.8-27b` (unloaded).
- 2026-10-15T10:54:52Z  Target model present: id `embeddinggemma-2-Q8_0`, aliases include `embeddinggemma-2`, `embeddinggemma2`, `embeddinggemma-300m`. status=loaded. Launch args include `--embeddings`, `--pooling mean`, `--mmproj /models/mmproj-embeddinggemma-2-Q8_0.gguf`. meta: n_embd=512, n_params=271002648, size=294064224, ftype=Q8_0, n_ctx_train=262144. Architecture field (manager-reported, UNVERIFIED): input_modalities=[text,image,audio,video].
- NOTE: /api/show is Ollama-only; **NOT requested/probed**. Ollama API absent; use llama.cpp-native metadata endpoints instead. (See DOC_CORRECTION.md C2.)

## Final (UTC)

- 2026-10-15T10:55:49Z  Text embedding pass: /v1/embeddings 4 inputs, dim 768, finite, L2=1.0; sensible ranking (cat pairs 0.73-0.87 > unrelated ~0.53-0.57).
- 2026-10-15T10:56:04Z  Multimodal probes (7 embedding POSTs): image cos 0.765, audio cos 0.931, video cos 0.716 vs text-only control => media consumed; invalid image/audio rejected HTTP 500. Transport-level only; quality unverified.
- 2026-10-15T10:56:13Z  /v1/audio/transcriptions route EXISTS (deployed build server.cpp registers it); JSON probe -> 400, multipart with embedding model -> 500 "does not support logits computation".
- 2026-10-15T10:56:46Z  Router metadata declares no audio-capable generation/ASR model installed (only audio-declaring model is the embedding model). This does not independently test other models or prove the server lacks transcription; no reader wiring evidence. No model pulled/loaded/deployed. (See DOC_CORRECTION.md C3.)
- 2026-10-15T10:56:56Z  Session complete. Target HTTP requests = 21 (embedding inference = 8, limit 12). Failures expected/negative only. Total ~2m31s. REPORT.md written.
- Note (corrected, see DOC_CORRECTION.md C1): exact model id embeddinggemma-2-Q8_0 aliases embeddinggemma-300m; n_params 271002648 is most plausibly the EmbeddingGemma2 *text backbone* (official spec ≈271M text + separate 170M vision / 300M audio), with mmproj loaded separately. Identity still unknown (no provenance/checksum check) but no counter-evidence; earlier "likely 300M family relabelled" inference retracted.

## Addendum (continuation, UTC)

- 2026-10-15T10:58:43Z  Follow-up media content-contrast probe: 2 additional /v1/embeddings POSTs (second 64×64 PNG with different colours, second 2.0 s / 16 kHz WAV at 880 Hz), same text and field order. New image vector cos 0.888551 vs original image; new audio cos 0.978952 vs original audio; both finite, 768-dim, L2=1.0, HTTP 200. => different valid media content influences the vector (content, not just a placeholder/token). Evidence in `evidence_followup/`. Input-consumption only; no quality/ASR/retrieval claim.
- New cumulative target HTTP = 21 + 2 = 23; cumulative embedding POSTs = 8 + 2 = 10 (cap 10). External read-only official-doc fetches = 4, listed separately from target-service counts.
- Corrections/retraction logged in `DOC_CORRECTION.md`; `REPORT.md` updated accordingly.
