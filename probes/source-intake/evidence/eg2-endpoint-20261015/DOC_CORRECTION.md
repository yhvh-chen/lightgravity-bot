# DOC_CORRECTION — corrections to REPORT.md and PROGRESS.md

- Scope: documentation/evidence corrections for the bounded probe of `http://192.168.8.12:11434`.
- Author: pi technical-test executor (continuation context).
- Date (UTC): 2026-10-15.
- Writable dir: `/tmp/lightgravity-eg2-endpoint-20261015/` only. No product/remote config change.
- These corrections **retract** one inference in the original report and tighten three wording issues.
  The original artifacts (`REPORT.md`, `PROGRESS.md`, `results_*.json`, `mm_raw/`, samples) were kept;
  only the affected paragraphs were edited, and this file records what changed and why.

---

## C1. RETRACTION — "271 M ⇒ EmbeddingGemma-300M relabelled / probably not a new model"

**Original text (REPORT.md §0, naming caveat):**

> ... its alias list contains `embeddinggemma-300m` and its text encoder has `n_params = 271002648`
> (~271 M). This is consistent with the **EmbeddingGemma 300 M family**, relabelled "embeddinggemma-2".
> Service metadata alone does **not** prove a genuinely new "EmbeddingGemma2" architecture. ...
> PM should treat the "new model" claim as **unconfirmed**.

**Why this inference is withdrawn:**

- Per the official model card supplied by PM —
  *EmbeddingGemma 2*, `https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2` —
  the released model is **270 M text backbone + 170 M vision + 300 M audio**. The text backbone
  alone is ≈271 M parameters.
- llama.cpp/GGUF deployments routinely **split the text model and the multimodal projector** into
  separate files. This deployment loads `--mmproj /models/mmproj-embeddinggemma-2-Q8_0.gguf`
  **separately** from the text GGUF. The service-reported `n_params = 271002648` is therefore
  **most plausibly the text-backbone parameter count only**, not the full multimodal model.
- Consequently `271 M` is **consistent with** EmbeddingGemma 2's text backbone; it is **not**
  evidence of an old EmbeddingGemma-300M relabel, and the `embeddinggemma-300m` alias is not a
  counter-proof of a new architecture.

**Corrected statement:**

> The model ID is `embeddinggemma-2-Q8_0`; one alias is `embeddinggemma-300m` and the service reports
> `n_params = 271002648`, with a separate `mmproj` file loaded. This is consistent with the official
> EmbeddingGemma 2 specification (≈271 M text backbone + separate 170 M vision / 300 M audio
> components). **Checkpoint identity remains `unknown`** because no GGUF metadata dump,
> checksum, or provenance/hash check was performed in this probe. There is **no counter-evidence**
> against the "EmbeddingGemma 2" identity, and no basis to call it a relabelled older model.

The official model card is cited here as a **PM-provided specification**; this continuation did
**not** fetch it (no new network request).

---

## C2. `/api/show` was never requested

**Original text (REPORT.md §1):** a table row `GET /api/show (implied) | 404`.

**Correction:** `/api/show` is Ollama-only and was **not actually requested**. It must not be
reported as a requested-and-404 probe. What is real: `GET /api/version` and `GET /api/tags` both
returned 404 with the llama.cpp error envelope, so **no Ollama API/registry is present**. The
`/api/show` route was merely *inferred absent* from that and was removed as a probe request.

**Corrected wording:** "Ollama API absent (`/api/version`, `/api/tags` → 404). `/api/show` is
Ollama-specific and was **not requested** in this probe; its absence is inferred from the missing
Ollama API, not measured."

---

## C3. ASR wording — one model on one route, not a general disproof

**Original text (REPORT.md §4 headline row and conclusion):**

> Transcription / ASR | **not_supported with installed models** | route exists, but no audio-capable
> generation model; embedding model returns "does not support logits computation"

**Correction:** the only established fact is that the **embedding model `embeddinggemma-2-Q8_0`**
fails on that transcription route with `"the current context does not support logits computation"`.
This probe did **not** test any other model's transcription ability and found **no evidence of a
reader/ASR wiring** on the server. It must not be read as a comprehensive falsification of all
models or of the server's transcription capability.

**Corrected wording:** "当前该 embedding 模型 `embeddinggemma-2-Q8_0` 在该转写路由上不提供开箱转写；
未验证其它模型，无 reader 接线证据。Embedding 向量不是转写。"

---

## C4. Scope / HTTP accounting — target service vs external doc reads

**Original text:** §0 said "Target: strictly `http://192.168.8.12:11434`. No other ports/hosts
scanned." and §5 listed 4 external documentation reads from `raw.githubusercontent.com`, which read
as a contradiction.

**Correction / clarified scope:** the **target service probe** touched only
`http://192.168.8.12:11434`; no other ports or LAN hosts were scanned. Separately, **4 read-only
fetches of official llama.cpp documentation/source** from `raw.githubusercontent.com` were made to
confirm the deployed schema; those are **external reference reads, not target-service probes**, and
are listed on their own line. No other external requests were made.

**HTTP counts re-verified from the saved logs (`results_text.json`, `results_mm.json`, and this
round's `evidence_followup/results_followup.json`):**

| item | count |
|---|---|
| Original target HTTP calls | 21 |
| Original `/v1/embeddings` POSTs (1 text batch + 7 multimodal) | 8 |
| **This round**: additional `/v1/embeddings` POSTs (2) | 2 |
| **New cumulative target HTTP calls** | **23** |
| Cumulative embedding POSTs (8 + 2) | 10 (cap ≤ 10) |
| External read-only doc fetches (separate from target count) | 4 |

---

## C5. PROGRESS.md placeholder time

**Original line:** `- 2026-10-15T10:54:2xZ  Pending: GET /api/version, GET /api/tags.`

**Correction:** the `2x` in `10:54:2xZ` was an initial **placeholder**, not a recorded timestamp.
**Corrected wording:** `- 初始待执行项（未记录精确时刻）Pending: GET /api/version, GET /api/tags.`
No exact start/end time is invented for items that were not recorded. The `2xZ` literal was a
planning placeholder only.

---

## C6. Media interpretation strengthened by a content-contrast follow-up

**Original limitation:** the first media probes only compared "same text + media" against "text
only". That cannot strictly separate *real media content* changing the embedding from merely a
*media placeholder/token* being appended.

**Follow-up (executed, ≤ 2 new inference POSTs, no generation/ASR):** two **second** synthetic
samples with the **same geometry/format and the same text/field order**, but **different content**,
were sent to the same endpoint/model/schema (`evidence_followup/`):

- PNG: same 64×64, horizontal yellow/magenta/cyan bands + black block (original: vertical
  red/green/blue bands + white block).
- WAV: same 16 kHz / 2.0 s / mono / 16-bit length (64 044 B), **880 Hz** instead of 440 Hz.

| comparison (new vs saved original) | cos | max abs delta | dim | finite | L2 norm | HTTP elapsed |
|---|---|---|---|---|---|---|
| second image vector vs original image vector | **0.888551** | 0.08408853 | 768 | true | 1.0 | 0.099 s |
| second audio vector vs original audio vector | **0.978952** | 0.03421662 | 768 | true | 1.0 | 0.027 s |

Both new vectors are finite, 768-dim, L2 = 1.0, HTTP 200. The deltas are far above floating-point
rounding, so **different valid media content influences the embedding vector** — the original
media-vs-text difference is not only a placeholder/token effect. This remains a **pure input
consumption** result: it is **not** image recognition, **not** audio semantic quality, and **not**
ASR, and it makes **no retrieval-accuracy claim**.

---

## Corrections applied to files

| File | Change |
|---|---|
| `REPORT.md` | §0 naming caveat replaced; §0 scope clarified; §1 `/api/show` row removed/inferred; §3 follow-up added; §4 ASR reworded; §5 counts → 23 target / 10 embedding, docs listed separately; §6/§7/§8 identity & evidence updated |
| `PROGRESS.md` | placeholder `10:54:2xZ` line corrected; addendum recording this follow-up |
| `DOC_CORRECTION.md` | this file (new) |
| `evidence_followup/` | new second-media evidence (script, samples, raw vectors, results) |
