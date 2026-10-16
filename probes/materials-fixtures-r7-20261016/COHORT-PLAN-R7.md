# LG-035 R7 — COHORT PLAN (FROZEN BEFORE ANY FUTURE MODEL CALL)

* Package: `probes/materials-fixtures-r7-20261016/**`
* Base: `main@2d76c83`. Branch `test/materials-fixtures-r7-20261016`.
* This package is **OFFLINE / acquisition only**: model, OCR, embedding and ASR HTTP calls = **0**.
  No product LAN request. Actual model calls are **NOT authorized** in this package.
* Frozen at (UTC): 2026-10-16.

> This plan pre-registers the cohort, the truth/cell schema, the input hashes and the
> thresholds **before** any future OCR run. Running it later is a separate, separately
> authorized step. Nothing here relaxes an existing threshold and nothing here relabels
> any historical R3/R4/R5/R6 result.

## 1. Why this cohort exists

The R6 DECISION (`probes/materials-ocr-protocol-r6-20261016/DECISION.md`) established that:

* the predeclared Z2 `15 rows × 3 columns` shape was a **semantic dialect taxonomy**, not page
  geometry (F1–F6), so Z2's page carries **no 15×3 grid**; and
* the original task's **"real table" hard requirement is still UNMET**: it needs a page with an
  **actual grid geometry** and **human cell-level truth**.

This cohort supplies exactly one such sample, from a real published born-digital PDF, plus a
mixed born-digital + real-scan fixture. Chinese printed page coverage is **already discharged by
Z1** (page CER 0.0423 ≤ 0.15 in the R2 smoke and R3) and is not re-opened here.

## 2. Cohort A — real published grid TABLE (`LG035-R7-T1`)

| Field | Value |
|---|---|
| Sample id | `LG035-R7-T1` |
| Class | real published grid table (born-digital native page) |
| Source | NIST SP 811 (2008), *Guide for the Use of the International System of Units (SI)* |
| Issuer | National Institute of Standards and Technology (US federal) |
| URL | `https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf` |
| License | US Government work → **public domain** (17 U.S.C. §105) |
| Page | PDF page **16** (1-based); 0-based index 15 |
| Table | **Table 1. SI base units** (header row + 7 data rows × 3 columns) |
| Table region (PDF pts) | `(90.0, 517.0, 524.6, 627.5)`, origin bottom-left |
| Grid evidence | 3 full-width horizontal rules + 3 consistent columns with >50 pt gutters |
| Truth origin | the PDF's **original text layer** (human-authored, **not OCR**) |
| Truth file | `truth/LG035-R7-T1.table.json` · sha256 recorded in `truth/TRUTH-MANIFEST.json` |
| Input image | `fixtures/honest_table_grid_scale4.png` (product rasteriser, scale 4.0) |

**Structure (frozen):** 3 columns `[Base quantity, Name, Symbol]`, 8 rows total
(1 header + 7 data). Cell-level truth is `truth/LG035-R7-T1.table.json`.

### Metrics and thresholds (UNCHANGED)

| Metric | Threshold | Source |
|---|---|---|
| table **cell CER** | **≤ 0.25** | frozen protocol §2 / R6 §5 |
| row count == human row count | exact | frozen protocol §4 |
| column count == human column count | exact | frozen protocol §4 |
| numeric/ID tokens byte-exact after NFKC | all present | frozen protocol §3 |

Scoring uses the frozen `SCORING-PROTOCOL.md` §1 normalisation (NFKC, whitespace stripped) and
§4 structure check, applied to the **cell matrix** rather than a linear list.

### Numeric/ID tokens (byte-exact after NFKC)

From the truth cells: `m`, `kg`, `s`, `A`, `K`, `mol`, `cd`. Each must appear byte-exact after
NFKC in the corresponding machine cell. Record `{token, present, exact}` per token.

## 3. Cohort B — mixed born-digital + real-scan PDF (`LG035-R7-MIX`)

| Field | Value |
|---|---|
| Sample id | `LG035-R7-MIX` |
| Class | mixed born-digital + real-scan, single PDF |
| File | `fixtures/mixed_born_digital_plus_scan.pdf` · sha256 in `truth/TRUTH-MANIFEST.json` |
| Page 1 | born-digital NIST SP 811 p.16 — **native text layer present** (mechanically verified) |
| Page 2 | `clear_real.pdf` page 1 — real scan (tesseract-ocr/test, Apache-2.0) — **no text layer** |
| Composition | local pypdfium2 `PdfDocument.new()` + `import_pages`; no synthetic text/scan |

**Disclosure (mandatory):** this is a **composite test fixture**, **not** an unmodified historical
document. Both constituent inputs are real and licensed.

### Metric / threshold

Mixed-page scoring uses the per-page class thresholds already frozen:
born-digital page → **page CER ≤ 0.15** (native-text page used as its own truth);
scan page → **page CER ≤ 0.15** against the human gold text
(`probes/lg035/fixtures/phototest.gold.txt`, sha256 `76ef157b…`).

## 4. Non-negotiable conditions for the future run

* Truth is human-authored native text / human gold — **never** model output.
* No synthetic image, synthetic scan, or machine-output-as-truth fills any class.
* Thresholds are frozen above; they must not be relaxed afterwards to pass.
* A machine page that fails must not contribute body text and must not be `searchable=true`.
* Every machine block carries `page=<n>` and `input_sha256` of the exact image bytes seen.

## 5. What this package does NOT do

* No OCR / embedding / ASR / model call (HTTP = 0).
* No product code, docs, frontend, backlog or PROJECT.md change.
* No quality pass, no status change (LG-035 stays `in-progress`), no LG-040/041 unlock.
* No push / deploy / publish.
