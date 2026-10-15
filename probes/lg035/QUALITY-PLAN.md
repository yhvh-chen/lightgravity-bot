# LG-035 QUALITY PLAN (pre-registered before any inference call)

Status: **frozen before the first inference POST**. Thresholds and samples were
fixed in this file before the real OCR probe ran; they were **not** adjusted
afterwards. Where a required sample class could not be obtained under the
license/budget/time constraints, the class is marked **BLOCKED** and no metric
is claimed for it.

## 1. Authorization and endpoint (candidate)

* Endpoint under test: `http://192.168.8.12:11434` — authorized read-only
  candidate, recorded **only as a test target**. It is **not** a product default
  and is not hard-coded anywhere in the product code; the product reads
  `LIGHTGRAVITY_OCR_BASE_URL` / `LIGHTGRAVITY_OCR_MODEL`.
* Server identity (live `/props`, 200): `role=router`, `build_info=b11641-843e7dcc1`,
  `models_autoload=true`. This is a **llama.cpp `llama-server` router, not Ollama**
  (`/api/version`, `/api/tags` are 404 on this server, per the LG-034-era
  source-intake evidence).
* Live `/v1/models` (200): `bge-reranker-v2-m3-Q8_0`, `embeddinggemma-2-Q8_0`,
  `gemma4-mtp`, `qwen3.8-27b`.
* OCR model under test: `qwen3.8-27b` (the model that the source-intake probe
  actually served Chinese OCR with). **Embedding models are not OCR** and are
  not used for transcription; a working `/v1/embeddings` route is never counted
  as OCR capability (docs/08 §6.6, docs/09 §7).
* Protocol: OpenAI-compatible `POST /v1/chat/completions`, typed content with an
  `image_url` data URL. `temperature=0`, `stream=false`,
  `max_tokens<=2000` per page.

## 2. Budget (declared before running)

| Item | Bound | Notes |
|---|---|---|
| read-only `health`/`props`/`models` | ≤ 4 requests | no inference |
| inference POST (`chat/completions`) | ≤ 10 total, incl. failures | **zero automatic retry**, concurrency 1 |
| per-page output | ≤ 2000 tokens | prompt forbids completion |
| total output | ≤ 16000 tokens | |
| first cold-load timeout | 180 s | router may load the model |
| other request timeout | ≤ 90 s | |
| network downloads (samples) | ≤ 25 MiB total, ≤ 12 MiB/file | |
| product real worker calls | 0 | OCR is an intake job, not a delivery Run |
| wall clock | ~20 min | |

A timeout is an **unknown outcome** and is never automatically replayed.

## 3. Sample set, provenance and license

All fixtures are **real scans** from the `tesseract-ocr/test` repository,
licensed **Apache-2.0** (verified via the GitHub license API; the repo ships an
Apache-2.0 `LICENSE`). They are public, non-private, and each human-verified
gold text is the repository's own `.txt`/`.gold.txt`. Total downloaded: ≈1.7 MiB (single largest file 1.61 MiB, since removed as
unused) — inside the 25 MiB/12 MiB bounds.  Only the fixtures actually used by
the probe are kept (≈400 KiB total).

| File | Role | sha256 (fixture) |
|---|---|---|
| `phototest.tif` | real clear printed page | `d2241a1eb6d6cd2eb6544b8e228c2862c852b7467d16ed636caa32179b780692` |
| `phototest.gold.txt` | human gold text for the above | `76ef157baeb6ab275b7d90f310477a8060d5822aea2b2e05d480f459b016a6ed` |
| `8071_093.3B.tif` | real second page (different typography) | `d4f01cba19c99f8894d94a6d43eb8ed8013f8cf17fc08af9346bb9fb3697d452` |
| `8071_093.3B.txt` | human gold text for the above | `29f290e47012a809f5139c796493b3c693e44e009dd8fb3dafe15420e8b4c7d5` |
| `phototestrot.tif` | low-quality/rotated page (degraded) | `b725a8aebbaab4b82a82b13619ecad4ddfc4a0b3b69dcdd93ce579d6e9f9d8e1` |
| `phototest-rotated-L.png` | rotated PNG (degraded) | `f9c80afb481abc07fdc6ff013df3048ef31141e7b1b90ec90ccbee8c3eddbea7` |

Multi-page sample: a **real-content multi-page PDF** is assembled locally from
`phototest.tif` (page 1) + `8071_093.3B.tif` (page 2) using the product PDF
rasteriser; the page-level ground truth is the concatenation of the two human
gold files. This is real scanned content, not a synthetic image.

## 4. Pre-registered quality criteria

* **CER** (character error rate) on NFKC-normalised, whitespace-stripped text:
  `edit_distance / len(gold)`.
* **Character accuracy** = `1 - CER`.
* Thresholds:
  * real clear printed page (phototest): **CER ≤ 0.05**.
  * real second page (8071): **CER ≤ 0.15** (older print, dense prose).
  * multi-page PDF: each page within its single-page threshold.
  * low-quality / rotated page: **recorded, not scored as a pass** — OCR is
    allowed to fail here; a failure must appear as an honest failed page, not
    fabricated text.
* **Page back-reference**: every machine page block must carry `page=<n>` and
  an `input_sha256` matching the SHA-256 of the exact rendered/loaded image
  bytes the model saw.
* **Field/traceability**: any value present in gold (number-like tokens) that
  the model returns must be byte-exact after NFKC (no silent normalisation of
  digits/IDs).
* **"Failed is not body"**: a failed page must never contribute text to the
  machine Markdown body and must never be reported `searchable=true`.

## 5. Required sample classes and honesty about BLOCKED classes

| Class | Required by acceptance | This run |
|---|---|---|
| real clear page | yes | ✅ covered (phototest) |
| low-quality page | yes | ✅ covered (rotated tif/png), **not scored** |
| multi-page | yes | ✅ covered (2-page real PDF) |
| mixed text/scanned | yes | ✅ partially: the assembled PDF has a rasterised scan page; a born-digital text layer mixed in one file was **not** available under license here → **BLOCKED**, recorded, not claimed |
| table | yes | ❌ **BLOCKED**: no license-clear Chinese/table page with human truth was obtainable in the time/budget; **no table metric is claimed** |
| **real Chinese page with human truth** | yes (Chinese product) | ❌ **BLOCKED** — see §7 |

Blocked classes are recorded as **quality-gate blockers**; the task stays
`in-progress`. No synthetic image is used to pretend these classes passed.

## 6. Machine output vs. human formal version

Pre-registered check (independent of OCR quality):

* `derivative/machine.v<source_version>.md` is the machine copy.
* `formal/FORMAL.md` is the human copy, in a **separate directory**.
* Running `reprocess` after a formal edit **must not** change `formal/FORMAL.md`;
  the machine derivative is overwritten/versioned only.

## 7. Known limitations carried into the result

* The OCR candidate is a LAN test service; reachability is **not** quality.
* No Chinese real-sample human truth was available in budget → **Chinese OCR
  quality is unverified** (the earlier synthetic 2-image CER 0 evidence is
  explicitly **not** reused as product acceptance).
* `tif` inputs are rendered to PNG locally; if the model cannot decode a page,
  it is a failed page, not fake text.
* Unknown token cost: the router does not report price → cost is **unknown**.
