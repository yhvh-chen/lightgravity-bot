# LG-035 R7 — REAL TABLE + MIXED-PAGE OCR COHORT PLAN (FROZEN BEFORE ANY POST)

* Owner: pi execution owner. Package: `probes/materials-ocr-cohort-r7-20261016/**` (only writer).
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-cohort-r7-20261016`
* Branch: `test/materials-ocr-cohort-r7-20261016`, base clean `main@2d76c83`.
* Fixture source (read-only): `materials-fixtures-r7-20261016` @ `f21d6e3` (clean, exited).
* Frozen at (UTC): 2026-10-16. **This file is committed BEFORE any network POST.**
* Rejected prior candidate: R5 prompt (`fix/materials-ocr-r5-20261016`) — **not reused**. The
  main actual `OpenAICompatOcrBackend` default prompt is used unchanged.

> Nothing here relaxes an existing threshold. Nothing here relabels R3/R4/R5/R6.
> The fixture package's frozen truth is the **original human-authored PDF text layer**
> (NOT OCR, NOT model output). This run does **not** modify fixture plan/GT bytes: if a
> mistake is found after seeing output, a new erratum/FAIL/unverified is recorded, never a
> silent truth correction.

## 0. Hard rules for this run

* Exactly **3 planned OCR POST** (no adaptive extras, all 3 run even if the table fails).
* No auto-replay. A timeout stops further network; the remaining calls stay **NOTEXECUTED**.
* Endpoint: `http://192.168.8.12:11434`, model `qwen3.8-27b` (authoritative existing endpoint only).
* concurrency 1 · retries 0 · per-call total 120 s / connect 5 s · max output 4096 tokens ·
  each input ≤ 2 MiB · total input ≤ 6 MiB · audio 0 / embedding 0 / ASR 0 / worker 0.
* Optional ≤ 1 health GET (8 s). Persistent reservation written BEFORE forward; every raw
  (redacted) response/error persisted BEFORE scoring.
* Sole endpoint owner: the previous wrapper (prompt basename `materials-endpoint-r7-20261016.txt`)
  has **exited** (verified: no process, no open connection, REPORT committed). Offline prep only
  while it ran; no LAN request until confirmed gone.

## 1. Predeclared 3-call cohort (exact inputs / hashes / render / config)

### Call 1 — `LG035-R7-T1` real published grid TABLE

| Field | Value |
|---|---|
| sample | `LG035-R7-T1` (NIST SP 811 p.16, Table 1. SI base units) |
| input | fixture `fixtures/honest_table_grid_scale4.png` |
| input sha256 | `39138a971d605f65d10b5df3a13e35c7cec5d3710bc38d55e6eb656fc1219652` |
| input bytes | 33716 (≤ 2 MiB) |
| render | table region PDF pts `(90.0,517.0,524.6,627.5)`, scale **4.0** |
| source page | NIST SP 811 (2008), PDF page 16 (0-based 15) |
| source sha256 | `788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f` |
| media_type | image/png, page=None (single image) |

### Call 2 — `LG035-R7-MIX` page 1 (born-digital, native text layer)

| Field | Value |
|---|---|
| input | `fixtures/mixed_born_digital_plus_scan.pdf` page 1, rendered by **actual** `PdfiumRasterizer`, scale **2.0** |
| file sha256 | `0f7286016cc22717d4dab67319180604be097374b4d07a53fe68332c9f68ada5` |
| page1 render sha256 | `265f187a8345146435282a6bf898141d748a50b086b8377d4e72fa916150f571` (239092 B) |
| equivalence | equals product re-render of NIST SP 811 p.16 @ scale 2.0 (same sha) — verified offline |
| page | 1 |

### Call 3 — `LG035-R7-MIX` page 2 (real scan, no text layer)

| Field | Value |
|---|---|
| input | `fixtures/mixed_born_digital_plus_scan.pdf` page 2, rendered by **actual** `PdfiumRasterizer`, scale **2.0** |
| file sha256 | `0f7286016cc22717d4dab67319180604be097374b4d07a53fe68332c9f68ada5` |
| page2 render sha256 | `1aebdc639db93532eeb19b4c3a0e0d67d796a621d20cbba6112d5dd975a28276` (34554 B) |
| equivalence | equals `clear_real.pdf` page 1 @ scale 2.0 (same sha) — verified offline |
| page | 2 |

Total planned input bytes = 33716 + 239092 + 34554 = **307362 B ≤ 6 MiB**.

## 2. Parser + cell-alignment (preregistered, before any call)

The machine table is parsed **only** from the model's actual emitted structure:

* **Accepted**: (a) GitHub Markdown pipe table (`| a | b | c |` + separator row), or
  (b) an explicit plain-text aligned table where each data line has ≥ 3 whitespace-separated
  runs separated by **≥ 2 spaces** (explicit column gutters) and row count matches.
* **Rejected → `structure=FAIL`**: unstructured prose, any output with no explicit grid.
* **NEVER**: reconstruct a missing grid from GT known tokens; **NEVER** populate a machine cell
  with truth text. GT is used only in the scoring comparator, never in parsing/assembly.
* Cell alignment: split each row at the explicit boundaries above; if the header row is present,
  it is row 0. Row/column counts must equal human counts (8 rows incl. header, 3 cols) exactly.

## 3. Scoring (frozen protocol §1 normalisation, reused unchanged)

```
normalise(s) = "".join(ch for ch in NFKC(s) if not ch.isspace())
cell_cer(truth_norm, hyp_norm) = edit_distance(truth_norm, hyp_norm) / max(1, len(truth_norm))
```

Cell CER = mean over the 24 cells (header + 7 data rows × 3 cols) after alignment; a missing/
mismatched cell contributes CER 1.0 against its truth (never silently dropped).

### Table hardgate (UNCHANGED)

| Gate | Threshold |
|---|---|
| machine rows incl. header | **== 8 exact** |
| machine columns | **== 3 exact** |
| table **cell CER** | **≤ 0.25** |
| numeric/ID/unit tokens `m,kg,s,A,K,mol,cd` | each **byte-exact after NFKC** in its symbol cell |

Page wholeCER for `LG035-R7-T1` is recorded **context only**, **NOT** part of the table gate.

### Page gates (UNCHANGED, per-page classes)

| Page | Truth | Threshold |
|---|---|---|
| MIX p1 born-digital | native text layer of NIST SP 811 p.16 | page CER **≤ 0.15** |
| MIX p2 real scan | `probes/lg035/fixtures/phototest.gold.txt` (`76ef157b…`) | page CER **≤ 0.15** |

Normalisation preserves original character normalisation (NFKC + strip whitespace). No new
markup stripping is applied unless already frozen in the fixture protocol.

## 4. Provenance (mandatory per machine block)

Each result records: original file sha256, render sha256, page, endpoint, model, prompt sha256,
raw (redacted) response path, token usage, latency, finish_reason. Machine/formal separation is
unchanged; baseline machine-vs-formal evidence is referenced (LG-035 baseline), not re-proven.

## 5. Honest scope statement (decided at freeze time)

* API path used: **actual** `OpenAICompatOcrBackend.transcribe()` for all 3 calls; MIX pages are
  rendered with the **actual** `PdfiumRasterizer`. The table image (call 1) is the frozen fixture
  PNG (already rendered by the fixture's product-shape rasteriser), not re-rendered here.
* Call-1/2/3 drive the adapter **directly** (bounded, retry-free, raw-capture harness). This is an
  **adapter-level harness**, **NOT** full-product end-to-end. Where `ProcessingEngine` applies
  (per-page bounded loop, honest partial/failure, no auto-replay) the same rules are honoured, but
  no full `ProcessingEngine.process()` file/SoT round-trip is performed here.
* Product processor partial/failure rules: **baseline, named LG-040** if unverified here.
* **No tiny independent QA** in this package.

## 6. Budget (declared before running)

| Item | Bound |
|---|---|
| OCR POST incl. failures | **3** exact |
| retries | 0 |
| concurrency | 1 |
| health GET | ≤ 1 (8 s) |
| audio / embedding / ASR / worker | 0 / 0 / 0 / 0 |
| per-call timeout (connect/total) | 5 s / 120 s |
| max output tokens | 4096 |
| per-input / total input | ≤ 2 MiB / ≤ 6 MiB |

## 7. Failure handling (preregistered)

* If a call **times out** → stop further network; remaining calls = **NOTEXECUTED**; no replay.
* If a call returns a service error → counted, continue to remaining planned calls (still 3 total
  unless a timeout stops the run).
* Any parse/score failure is recorded as FAIL/unverified, never relaxed.
* Budget stop with unknown side effects → checkpoint, no replay.

## 8. Remaining ORIGINAL LG-035 acceptance coverage (this run)

| Original class | Status before | This run |
|---|---|---|
| real clear page | PASS (baseline CER 0.0000) | referenced, not re-proven |
| low-quality page | recorded only | **still gap** |
| multipage | PASS (baseline) | referenced |
| Chinese printed page | PASS (Z1 CER 0.0423) | referenced |
| **table** | **UNMET** | **this run: T1** |
| **mixed born-digital + scan (one file)** | **UNMET** | **this run: MIX p1/p2** |

R3/R4/R5 historical FAIL remain FAIL.
