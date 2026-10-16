# LG-035 R7 — materials fixtures REPORT

* Package: `probes/materials-fixtures-r7-20261016/**` (only writer of this path).
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016`
* Branch: `test/materials-fixtures-r7-20261016`, base clean `main@2d76c83`.
* Offline/acquisition only: model / OCR / embedding / ASR HTTP = **0**; product LAN = **0**.
* Date (UTC): 2026-10-16.

## 1. Deliverables

### A. Genuine published grid TABLE (`LG035-R7-T1`)

A small, simple, real published table taken from an official **born-digital** PDF:

| | |
|---|---|
| Source | NIST SP 811 (2008), *Guide for the Use of the International System of Units (SI)* |
| Host | `nvlpubs.nist.gov` (official NIST Publications) |
| License | US Government work → **public domain** (17 U.S.C. §105) |
| sha256 | `788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f` (2,027,518 B) |
| Page / table | page 16 · **Table 1. SI base units** |
| Region (PDF pts) | `(90.0, 517.0, 524.6, 627.5)`, origin bottom-left |
| Input image | `fixtures/honest_table_grid_scale4.png` (`39138a97…`), product rasteriser scale 4.0 |
| Truth | `truth/LG035-R7-T1.table.json` (`02a4ada1…`) from the PDF **original text layer** |

**Structure (frozen, actual grid):** 3 columns × (1 header + 7 data rows).
Columns `[Base quantity, Name, Symbol]`.

**Grid geometry evidence (mechanical, from the product-rendered crop):**
* 3 full-width **horizontal rules** at pixel rows `[2,3]`, `[98,99]`, `[422,423]` (top, below header, bottom);
* 3 consistent **column gutters** — native column starts at x ≈ 95.6 / 266.6 / 438.8 pt with >50 pt gaps;
* no vertical rules (booktabs-style grid = ruling + consistent gutters, matching R6 DECISION §5 wording).

**Truth provenance:** all 24 cell strings are present **byte-exact** in the PDF's original text layer,
verified by `verify_truth.py` (raw output in `evidence/local_checks.txt`). Truth was determined
**before** any (future) model call. No model output is used as truth.

### B. Mixed born-digital + real-scan PDF fixture (`LG035-R7-MIX`)

| | |
|---|---|
| File | `fixtures/mixed_born_digital_plus_scan.pdf` (`0f728601…`), 2 pages, 103,371 B |
| Page 1 | born-digital NIST SP 811 p.16 — **native text layer present** (verified) |
| Page 2 | `clear_real.pdf` p.1 — real scan (tesseract-ocr/test, Apache-2.0) — **no text layer** |
| Composition | pypdfium2 `PdfDocument.new()` + `import_pages`; no synthetic text or scan |

**Mechanical text-layer split verified** (`verify_truth.py`): pages=2, page1 `native_text_layer_present=True`,
page2 `native_text_layer_present=False`. `pdftotext` page 1 yields the native prose; page 2 yields a bare
form-feed (`\f`) — no text. **Disclosure:** composite **TEST FIXTURE**, not an unmodified historical document.

### C. Frozen plan / schema / hashes / thresholds

* `COHORT-PLAN-R7.md` — cohort, truth/cell schema, input hashes, thresholds, frozen before any call.
* `truth/TRUTH-MANIFEST.json` — per-sample truth + input hashes, thresholds, disclosures.
* `SOURCES.md` — acquisition counter, URLs, licenses, sha256, attribution.
* `evidence/local_checks.txt` — raw local check output.

## 2. Acquisition budget (honest)

| Item | Cap | Used |
|---|---|---|
| read-only GET | ≤ 14 | **7** |
| downloads (full PDF) | ≤ 3 | **1** (NIST SP 811, 1.93 MiB) |
| per-download bytes | ≤ 10 MiB | 1.93 MiB |
| total download bytes | ≤ 15 MiB | 1.93 MiB |
| timeout / retries | 15 s / 0 | 15 s / 0 |

Full request log in `SOURCES.md`. 3 GETs were official-domain reachability probes (bodies discarded);
1 was a size-only check; 1 body download; 2 were redundant size checks. All counted.

## 3. Meaningful local checks (no full suite)

* `verify_truth.py` → **PASS**: 24/24 cell texts byte-exact in native layer; structure 3×8; mixed
  text-layer split correct.
* Grid-geometry decode: 3 horizontal rules, 0 vertical rules (consistent gutters) — real grid.
* `pdfinfo` / `pdftotext` on the mixed fixture confirm page count and text-layer split.
* Builders are deterministic and committed (`build_fixtures.py`, `verify_truth.py`).

## 4. Boundaries (explicit non-claims)

* This package makes **no** quality-pass claim and does **not** change LG-035 status
  (stays `in-progress`) or unlock LG-040/041.
* The table page is **born-digital**, disclosed as such — **not** claimed to be a historical scan.
* No Chinese table is provided; not required (Z1 already discharges the Chinese printed-page class).
* No product source / docs / frontend / backlog / PROJECT.md change; this is a test-fixture package.
* No push / deploy / publish / reset / clean. All prior worktrees/branches/raw preserved.
* pi/DeepSeek cost: **unknown, not zero**.

## 5. Ready-for-future (NOT executed here)

A future, separately authorized OCR run can score:

* `LG035-R7-T1`: product OCR of `fixtures/honest_table_grid_scale4.png` vs
  `truth/LG035-R7-T1.table.json` — **cell CER ≤ 0.25**, exact row/col counts, symbol tokens byte-exact
  after NFKC.
* `LG035-R7-MIX`: per-page page CER ≤ 0.15 (born-digital page vs its native text; scan page vs
  `phototest.gold.txt`).
