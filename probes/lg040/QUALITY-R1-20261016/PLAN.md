---
title: "LG-040 QUALITY-R1-20261016 — independent English-primary quality/cost/data-provenance plan (FROZEN before any POST)"
doc_type: plan
category: qa
status: "frozen — corpus/labels/metrics/gates/counts/input-hashes fixed in this separate commit BEFORE any model POST"
updated: "2026-10-16"
---

# QUALITY QA — LG-040 R1-20261016 (independent, fresh)

## 0. Authority & scope

- Owner: **fresh independent pi QUALITY QA** (`qa/lg040-quality-r1-20261016`), no implementer context.
  **Root PM only** at the process level; this owner performs the QA slice itself.
- Write scope: **only** `probes/lg040/QUALITY-R1-20261016/**`. No product/tests/PM-docs/backlog edits,
  no nested agents, no push/deploy/publish/reset/clean.
- Base: worktree HEAD `dd4ca81`, branch `qa/lg040-quality-r1-20261016`; product tree MUST equal
  `2f277fa` (`backend/`, `frontend/`, `tests/` byte-identical). Verified clean before prep.
- Endpoint: **only** `http://192.168.8.12:11434`; models **only** `qwen3.8-27b` (OCR) and
  `embeddinggemma-2-Q8_0` (embedding). No substitute provider/endpoint/model; no ASR; no worker;
  no DeepSeek product generation; no model install; **no real second live model**.
- Serialization: **no LAN inference or health/models GET until the BROWSER wrapper
  `lg040-browser-r1-20261016.txt` has exited** (exact basename). Offline prep done before that.

## 1. Truth provenance (human-authored, BEFORE any call)

All truth comes from human-authored originals that pre-exist this run; **no model output is truth**.

| Doc | Kind | Original source (human-authored) | In-repo path | sha256 |
|---|---|---|---|---|
| D1 | English text | NIST SP 811 §4.1 "SI base units" prose + Table 1 text, native PDF text layer, US-gov public domain | `corpus/d1_si_units.txt` | `fa74a73e43a5bb631954b4d9a0998c84e757e8dcb7fece0754bd691409b2d7ec` |
| D2 | English text | tesseract-ocr/test `phototest.gold.txt` human gold, Apache-2.0 | `corpus/d2_phototest_gold.txt` | `76ef157baeb6ab275b7d90f310477a8060d5822aea2b2e05d480f459b016a6ed` |
| D3 | English image | tesseract-ocr/test `phototest.tif` real photo-test image, Apache-2.0 | `probes/lg035/fixtures/phototest.tif` | `d2241a1eb6d6cd2eb6544b8e228c2862c852b7467d16ed636caa32179b780692` |
| D4 | real-human audio | Wikimedia Commons `File:Chinese language-1.ogg`, **CC BY-SA 3.0**, real human voice reading the English-Wikipedia "Chinese language" article opening; **language is mixed Chinese/English per source description — NOT assumed English** | `probes/lg039/evidence/real_voice_chinese_language-1.ogg` (sha256 `1a8df6fbd1cff0ce6c192932cb6d1d5a8e20e551ba915896685544abb0528e9f`), first ≤10 s sent | `1eede9d1b03022f5c01332a65148a076dc61c32eb5dc0a4cc82d8b5995e6cad0` for the ≤10 s PCM copy (`corpus/d4_audio_10s.wav`, mono 16 kHz, exactly 10.000 s, derived offline) |

D1/D2 are **human-authored text**; the product embeds them as **trusted text** (formal version set
by the normal `POST /sources/{id}/formal` path, never OCR). D3/D4 originals are embedded **as media**
(image/audio vectors); the vector is never relabelled as OCR/ASR text.

## 2. Frozen corpus (minimal balanced: 2 EN text + 1 EN image + 1 real-human audio)

Four sources only, all global-scope, all indexed by the **actual product vector service**.

## 3. Frozen query labels (English positive per type + unrelated negative)

| Q | Query string | Positive doc | Type |
|---|---|---|---|
| Q1 | `SI base unit for electric current` | D1 | text |
| Q2 | `quick brown dog jumped over the lazy fox` | D2 | text |
| Q3 | `scanned page of twelve point text with the quick brown fox sentence` | D3 | image |
| Q4 | `spoken recording of the Wikipedia article about the Chinese language` | D4 | audio (**INDICATIVE ONLY**, see §7) |
| QN | `renormalization of lattice quantum chromodynamics gauge fields` | none (negative) | negative |

**No post-hoc label expansion, no threshold calibration.** All queries are fixed in this commit.

## 4. Frozen metrics & gates

- Metrics: Recall@1/3/5, MRR, top-1 correct, negative false-hit count over top-5, and the **same
  corpus lexical baseline** (`GET /search`) for contrast. Cosine order **independently recomputed**
  from persisted raw vectors (not trusted from the service).
- Pre-registered gates (indicative, bounded — **not** a broad statistical claim):
  - **G1 (text)**: Q1 and Q2 vector top-1 == correct doc; Recall@1 for {Q1,Q2} == 1.0.
  - **G2 (image)**: Q3 vector top-1 == D3 (image vector). PASS/FAIL; if FAIL, report which doc won.
  - **G3 (audio)**: Q4 top-1 == D4 — **reported but INDICATIVE**, because the real audio's spoken
    language is mixed (source says so; no ASR, no transcript claim). G3 does not gate the slice.
  - **G4 (negative)**: QN returns top-5 with **no abstention** (product is expected to return
    candidates, per docs/09 §7); record false hits honestly as a **quality false-hit count, not an
    ACL bug**. Gate: none (informational).
- **Chinese R5 image rank 7 is an accepted historical limitation, not a standalone failure here.**
  Old R5 queries are **not** re-tuned.

## 5. Frozen call budget (EMBEDDING ≤ 18 POST total; OCR ≤ 2 POST)

| Step | Embedding POST | Notes |
|---|---|---|
| Build index (D1,D2,D3,D4) | 4 | one vector per source |
| Main queries Q1,Q2,Q3,Q4 | 4 | one query POST each |
| Negative QN | 1 | |
| Delete cache + rebuild (all 4) | 4 | reproduction |
| Post-rebuild reproducibility Q1′ | 1 | |
| **Total** | **14 / 18** | 4 spare reserved; no unknown replay |

- OCR POST ≤ 2 via the **actual normal product** `ProcessingEngine`/`IntakeService`:
  page-1 native NIST full page, page-2 real scan, of `mixed_born_digital_plus_scan.pdf`.
- health/models GET ≤ 2 total for this slice. All: **retries 0**, concurrency 1,
  OCR 120 s / connect 5 s, max output 4096 tokens, input ≤ 2 MiB/call; embedding 90 s / connect 5 s,
  concurrency 1; media ≤ 10 MiB; **AUDIO TOTAL ≤ 15 s** (one real-human clip ≤10 s, optional ≤2.048 s);
  at most 20 inference POST this slice.
- **Persistent reservation + hard cap BEFORE forward**; over-cap is rejected **before** HTTP;
  timeouts stop the remaining POST and are reported UNEXECUTED (no replay).
- Missing usage ⇒ **unknown, not 0**.

## 6. Cache rebuild / model-compatibility

- Actual cache delete + rebuild reproduction is inside the 14-POST quota.
- The cache/model-mixing guard is verified **mechanistically** (a real second live model is NOT
  authorized): the guard rejects a differing recorded model; reuse API-owner evidence for the
  cross-task/ACL mechanical compatibility. No fake real switch.

## 7. Honest limits (pre-declared)

- One query per type is a **bounded indicative battery**, not a benchmark; no broad English-quality
  claim. Q4 audio ranking is indicative because the real audio language is mixed and no ASR exists.
- Raw direct-media embeddings are **not** OCR/ASR text and never claimed as transcription.
- Chinese image rank-7 accepted limitation retained/disclosed.
- If the vector backend is unavailable, the lexical/original path is still usable; a controlled
  fault is a mechanical check, not a quality result.
- If the product tree changes during QA, that is a defect/stop, not silent adaptation.
- Full LG-040 acceptance unverified ⇒ slice result is **INCOMPLETE**, never a self-claimed full PASS.

## 8. Counters (this package)

- Pre-freeze: network 0 / POST 0 / model 0 / product inference 0. Cost: pi **unknown, not 0**.
