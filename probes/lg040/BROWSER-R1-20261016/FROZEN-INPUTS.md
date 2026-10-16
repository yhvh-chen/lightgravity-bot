---
title: "LG-040 BROWSER R1 — FROZEN OCR INPUTS / TRUTH / PATHS / CALL COUNT"
doc_type: evidence
category: qa
updated: "2026-10-16"
---

# FROZEN before ANY LAN POST (BROWSER owner)

This file is frozen and committed **before** the first product OCR POST. It fixes
the exact two browser OCR inputs, their hashes, their truth sources, the paths
they take through the real UI, and the exact allowed call count. Nothing here is
re-tuned after a result is seen.

## Candidate under test

- Product tree = `2f277fa` (claimed-plan product subtree); verified `git diff
  2f277fa HEAD -- backend frontend tests` empty at QA start (see STATUS).
- Real app: `python -m lightgravity start --no-executor` (real `create_app`,
  real `frontend/dist`, real runtime token injected into the served HTML).

## Browser OCR POST budget (this owner)

- **Hard cap = 2 POST** to the LAN OCR endpoint total (product OCR).
- The app's **own automatic** reprocess/reprocess calls all count against this
  cap (via the loopback proxy hard cap, pre-forward reservation).
- retries = 0, concurrency = 1, OCR read timeout = 110 s, connect timeout honoured
  by the proxy (5 s), max output tokens = 4096 (env), input ≤ 2 MiB/call.
- `embedding` POST = 0 (this owner). ASR = 0. No worker/DeepSeek product gen.
- health/models GET ≤ 2 (one used to confirm the endpoint/model before POST).

## Input 1 — real English scan (PDF, product-rasterised)

| Field | Value |
|---|---|
| Path | `probes/lg035/fixtures/clear_real.pdf` |
| sha256 | `89c6b42242d0aa16efdb7ff814604c4bfc5214e0bbdd040ead67dcf453d9ec0f` |
| Media | `application/pdf` (1 page, real scan, Apache-2.0 tesseract-ocr/test) |
| Truth source | `probes/lg035/fixtures/phototest.gold.txt` (human gold, sha256 `76ef157baeb6ab275b7d90f310477a8060d5822aea2b2e05d480f459b016a6ed`) — **reference only, never placed in the prompt** |
| UI path | Chat **Upload / drop files** → Files → **Reprocess (OCR)** |
| Table-mode relevance | classifier must NOT mark this as a table → default prompt used |

## Input 2 — real NIST published table (rasterised crop, PNG)

| Field | Value |
|---|---|
| Path | `probes/materials-fixtures-r7-20261016/fixtures/honest_table_grid_scale4.png` |
| sha256 | `39138a971d605f65d10b5df3a13e35c7cec5d3710bc38d55e6eb656fc1219652` |
| Media | `image/png` (1739x442 real published table crop) |
| Truth source | `probes/materials-fixtures-r7-20261016/truth/LG035-R7-T1.table.json` (human cell truth from the PDF native text layer, sha256 `02a4ada1be2c38d356034bf79a1b856394f3cbac5a2bfd8ca0d11bc780d4f39d`) — **reference only, never placed in the prompt** |
| Provenance | NIST SP 811 (2008) Table 1, public domain (US Gov work) |
| UI path | Chat **Upload / drop files** → Files → **Reprocess (OCR)** |
| Table-mode relevance | classifier SHOULD mark this as a table → explicit table prompt (named test mode ON) |

## Prompt discipline

- Default table mode = **OFF**. Verified separately (offline import check) that
  the app default is OFF and an ordinary request keeps the **unchanged**
  `OCR_PROMPT`.
- For the named table test the browser app is launched with
  `LIGHTGRAVITY_OCR_TABLE_MODE=1`; the product still uses `OCR_PROMPT` for
  non-classified pages (Input 1) and `OCR_TABLE_PROMPT` only for the classified
  table page (Input 2). No page text / ground truth is ever placed in a prompt.

## Exact allowed call count

| # | Input | Prompt (expected) | Counts |
|---|---|---|---|
| 1 | clear_real.pdf page 1 | default `OCR_PROMPT` | 1 POST |
| 2 | honest_table_grid_scale4.png | `OCR_TABLE_PROMPT` (classified table) | 1 POST |

Total allowed product OCR POST = **2**. If any POST times out → stop remaining
POST, do **not** replay. If the UI fails before any model call, the 2 POST stay
**unexecuted** (honest), and the error path may be exercised with a controlled
unavailable backend (no fake success).
