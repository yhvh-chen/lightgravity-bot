---
title: "Materials Retry R2 — REPORT (Stage A + 2 POST smoke)"
doc_type: report
category: probe
status: "complete — reachable; OCR smoke PASS; embedding smoke PASS; ASR untouched (LG-041 locked)"
updated: "2026-10-16"
---

# REPORT — materials-retry-20261016-r2

## 0. One-line result

Authorized target `http://192.168.8.12:11434` is **reachable now** (Stage A: 3/3 GET HTTP 200; a
llama.cpp **router**, not Ollama). On the frozen budget (2/2 POST) a **real OCR smoke PASSED**
(real Chinese page Z1 vs human level-3 truth, **CER 0.0423 ≤ 0.15**) and a **real text embedding
smoke PASSED** (768-dim, finite, nonzero, L2=1.0). ASR remains **0 POST** and LG-041 stays locked.
Task statuses unchanged; GET reachability / smoke never implies LG-035/037/040 done.

## 1. Authority & scope compliance

- User issued **one new bounded retest**; this is **not** an auto-replay of any prior write request.
- Owner = this single pi executor. No nested agents. No push / deploy / publish. No provider switch.
- Prior **ARP failure was NOT** treated as proof the host is powered off; a fresh direct probe was run.
- Writes confined to `probes/materials-retry-20261016-r2/**`. Worktree `materials-retry-20261016-r2`,
  branch `test/materials-retry-20261016-r2`, based on actual `main` @ `db01cd6` (clean). Old
  `materials-restored` worktree / private / ledger **not reused or overwritten**.

## 2. Stage A — bounded GETs (cap 3/3, reached exactly)

| # | URL | HTTP | time_total | num_connects | retries | UTC |
|---|---|---|---|---|---|---|
| 1 | `/health` | **200** | 0.001931 s | 1 | 0 | 2026-10-15T22:16:48Z |
| 2 | `/v1/models` | **200** | 0.002872 s | 1 | 0 | 2026-10-15T22:16:48Z |
| 3 | `/props` | **200** | 0.002032 s | 1 | 0 | 2026-10-15T22:16:52Z |

- Transport: `connect-timeout 3` / `max-time 8` / `retry 0` / `--noproxy 192.168.8.12`. `/api/ollama` never called.
- `/health` body `{"status":"ok"}` (sha256 `a29ee2b1…`); `/v1/models` 3909 B (sha256 `39edaab5…`);
  `/props` 239 B (sha256 `8fcdb570…`). Raw bodies in `private/` (dir 700, files 600); no credentials present.
- No failure ⇒ **no TCP probe needed** (TCP count 0/1); no `ip route get`/`ip neigh` invoked.
- **errno 113 was NOT** re-asserted: the previous "no route to host" is a past fact, and reachability now
  contradicts using it to declare host-down.

### `/props` (verbatim, non-sensitive)

`build_info=b11641-843e7dcc1`, `role=router`, `max_instances=2`, `models_autoload=true`,
`model_alias=llama-server`, `model_path=none`, `cors_proxy_enabled=false`. → **llama.cpp router.**

## 3. Declared capabilities & active model IDs (from `/v1/models`)

| model id | aliases | input modalities | output | role |
|---|---|---|---|---|
| `embeddinggemma-2-Q8_0` | embeddinggemma-2, embeddinggemma-300M-Q8_0, embeddinggemma-300m, embeddinggemma2 | **text, image, audio** | text | embedding (mean pooling, `--embeddings`, `--mmproj`, ctx 262144) |
| `gemma4-mtp` | — | text, image | text | vision chat |
| `qwen3.8-27b` | — | text, image | text | vision chat |
| `bge-reranker-v2-m3-Q8_0` | bge-reranker-v2-m3 | text | text | reranker (rank pooling) |

All listed `status.value="unloaded"` (router autoloads on first request).
**Active IDs used this package:** OCR = `qwen3.8-27b`; embedding = `embeddinggemma-2-Q8_0`.

**ASR/audio:** only the *embedding* model declares audio; per the prior source-intake probe that
embedding model does not compute logits, and `/v1/audio/transcriptions`→501, chat `input_audio`→500.
⇒ ASR is a **declared-but-unusable** gap; **0 POST** here. LG-041 remains locked.

## 4. POST #1 — OCR smoke (product `OpenAICompatOcrBackend`)

- Frozen fixture: `probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg`
  sha256 `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f` (333,996 B) — matches manifest.
  Truth: `probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z1.p10.txt` (human Wikisource ProofreadPage **level 3**).
- Endpoint `/v1/chat/completions`, model `qwen3.8-27b`, `temperature=0`, `stream=false`, `max_tokens=2048`,
  cold bound 120 s, retries 0. **Product adapter unmodified**; truth never placed in the prompt.
- Result: **HTTP 200**, `finish_reason=stop`, latency **92.41 s** (cold load), prompt 1262 / completion 555 tokens.
- **Metric (frozen protocol, NFKC + whitespace-strip, Levenshtein):** truth 189 chars, hyp 193 chars,
  edit distance 8, **CER 0.0423**, threshold ≤ 0.15 ⇒ **PASS**.
- Notes recorded honestly: hypothesis has 4 extra chars and a few glyph variants (`鑽研` vs truth `鑽硏`,
  `導窽` vs `導竅`) plus an appended running title/heading `老解老自敘`. Even with these, CER is well under
  the gate. This is **one real printed page**, not a full quality battery; the Z2 table gate was **not** exercised.

## 5. POST #2 — embedding smoke (product `OpenAICompatEmbeddingBackend`)

- Input: one real Chinese text string (108 B, sha256 `220bf48f…`). Endpoint `/v1/embeddings`,
  model `embeddinggemma-2-Q8_0`, timeout 90 s, retries 0, single input.
- Result: **HTTP 200**, latency **4.873 s**, prompt 37 tokens.
  **dimension 768** (read from response, not guessed), `finite=true`, `nonzero=true`, **L2 norm = 1.0**.
  First 8 dims `[-0.032838, -0.009322, -0.025601, 0.004019, 0.019534, 0.035327, 0.003682, -0.026947]`.
- **Vector ≠ quality**: no Recall@k / relevance claim is made. Real retrieval quality on a frozen
  Chinese query set is deferred to **LG-040**.

## 6. Counters (final)

| Counter | Used / Cap |
|---|---|
| GET | **3 / 3** (reached exactly; no extra) |
| POST (inference) | **2 / 2** (OCR 1 + embedding 1; ASR 0) |
| TCP connect probe (11434) | 0 / 1 (unused — GETs succeeded) |
| retries | 0 |

## 7. Honest limits & what a next package needs

- Only **one** real printed page and **one** text embedding were tested. No Z2 table/PDF POST,
  no low-quality page, no multi-page, no mixed text/scan; the table gate is unproven.
- No recall/relevance, no negative-control retrieval, no dimension/model-switch rebuild test.
- OCR ran on `qwen3.8-27b` (vision chat), **not** the embedding model; the embedding model is a
  pure embedding/multimodal model and was **not** forced to chat/OCR/ASR (as instructed).
- **ASR still has no usable backend** ⇒ LG-041 remains locked; report `done` never equals quality pass.
- **These results do NOT mark LG-035/037/040 `done`**, do not change any task status, and do not
  modify shared contracts or product code. Full quality batteries + independent QA are the PM's call.

## 8. Next package recommendation (PM to dispatch)

1. **LG-035 OCR quality battery**: extend to Z2 table page (cell/segment CER ≤ 0.25 + structural pass),
   low-quality page, multi-page PDF, mixed born-digital+scan; freeze truth/thresholds first; ≤ a few POSTs.
2. **LG-037 retrieval quality**: frozen real-Chinese query set + relevance truth, Recall@k / ordering /
   negative controls vs lexical baseline; record model switch → index rebuild.
3. **LG-040** only after 1–2 pass and a separately authorized version QA; **LG-041** only after a real
   ASR backend exists and a human-audio quality gate passes.

## 9. Evidence index (this package)

- `STATUS.md`, `PLAN.md`, this `REPORT.md`
- `http/stageA_results.json` (GET digests), `private/*.body` (raw, 600)
- `evidence/ocr_post1.py`, `evidence/ocr_result.json`, `evidence/ocr_cer.json`
- `evidence/embedding_post2.py`, `evidence/embedding_result.json`
