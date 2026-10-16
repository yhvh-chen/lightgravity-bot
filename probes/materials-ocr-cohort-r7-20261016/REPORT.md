# LG-035 R7 — real table + mixed-page OCR cohort REPORT

* Package: `probes/materials-ocr-cohort-r7-20261016/**` (only writer).
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-cohort-r7-20261016`
* Branch: `test/materials-ocr-cohort-r7-20261016`, base clean `main@2d76c83`.
* Fixture source (read-only): `materials-fixtures-r7-20261016` @ `f21d6e3` (clean, exited).
* Date (UTC): 2026-10-16. **PLAN frozen in commit `1c1b356` BEFORE any POST.**

## 1. Headline

| Sample | Metric | Value | Threshold | Gate |
|---|---|---|---|---|
| `LG035-R7-T1` real grid table | rows incl. header == 8 | machine **0** (no grid) | exact | **FAIL** |
| | cols == 3 | machine **0** | exact | **FAIL** |
| | table cell CER | **1.0** | ≤ 0.25 | **FAIL** |
| | symbol tokens byte-exact (NFKC) | **not scored** (no cells) | all | **FAIL** |
| `LG035-R7-MIX` p1 born-digital | page CER | **0.0295** | ≤ 0.15 | **PASS** |
| `LG035-R7-MIX` p2 real scan | page CER | **0.0000** | ≤ 0.15 | **PASS** |

**Overall: table hardgate FAIL; mixed-page gates PASS.** LG-035 stays **in-progress**;
LG-040/041 **not** unlocked. No self-marked done.

## 2. Cohort (exact inputs / hashes / render)

| Call | Sample | Input sha256 | bytes | render |
|---|---|---|---|---|
| 1 | `LG035-R7-T1` | `39138a97…` (fixture `honest_table_grid_scale4.png`) | 33716 | table pts `(90,517,524.6,627.5)` scale 4.0 |
| 2 | `LG035-R7-MIX` p1 | render `265f187a…` (== NIST p16 scale 2) | 239092 | actual `PdfiumRasterizer`, scale 2.0 |
| 3 | `LG035-R7-MIX` p2 | render `1aebdc63…` (== `clear_real.pdf` p1 scale 2) | 34554 | actual `PdfiumRasterizer`, scale 2.0 |

Total input 307362 B ≤ 6 MiB. Source pdf `788dd8f0…`; mixed pdf `0f728601…`; truth `02a4ada1…`;
gold `76ef157b…`. All confirmed by `preflight.py` (`evidence/offline_preflight.json`, ALL_OK).

## 3. Endpoint / config (actual)

* Endpoint `http://192.168.8.12:11434`, model `qwen3.8-27b`.
* Backend: main **actual** `OpenAICompatOcrBackend` (default prompt, sha recorded; R5 candidate NOT used).
* Health GET: 1/1, 200, 5 ms.
* 3/3 POST ok, `finish_reason=stop`; tokens 878/158, 2022/621, 276/113.
* Latency 86.05 s / 38.37 s / 7.15 s; retries 0; concurrency 1.
* Reservation written before each forward; raw (redacted) response persisted before scoring
  (`evidence/live_ledger.jsonl` order: health, reservation1, raw1, reservation2, raw2, reservation3, raw3).

## 4. Table result — honest FAIL, no GT fill

Machine output for `LG035-R7-T1` is a **flat one-token-per-line list**:

```
SI base unit / Base quantity / Name / Symbol / length / meter / m / mass / kilogram / kg / ...
```

It contains the correct tokens but emits **no explicit grid** (no Markdown pipe table, no
≥2-space aligned column boundaries). Per the preregistered parser rule, the parser records
`parse_method = "none"`, `machine_rows = 0`, `machine_cols = 0`, `structure = FAIL`, and scores
cell CER **1.0** against the frozen 24-cell truth. **Truth was NOT used to reconstruct the grid
and machine cells were NOT populated from truth** — that is exactly the forbidden shortcut.

* `evidence/raw/call1_LG035-R7-T1_pNone_text.txt` — machine text.
* `evidence/raw/call1_LG035-R7-T1_pNone.json` — redacted raw response.
* Whole-table CER (context only, not the gate): 1.0.

This mirrors R3/R4/R5/R6: the endpoint's default prompt linearises the table. R6 DECISION already
showed Z2 had no 15×3 grid geometry; here we have a **real** grid in the input image but the model
still does not emit grid structure. **R3/R4/R5 historical FAIL remain FAIL.**

### Erratum (recorded, not a truth correction)

* No fixture PLAN/GT byte was changed after seeing output.
* The table result is a genuine FAIL, not "not applicable". No threshold was relaxed.

## 5. Mixed-page results

* **p1 born-digital**: page CER **0.0295** ≤ 0.15 **PASS** (truth = NIST SP 811 p16 native text
  layer; normalised len 1898 vs 1898).
* **p2 real scan**: page CER **0.0000** ≤ 0.15 **PASS** (truth = `phototest.gold.txt`; len 225 vs 225).

`evidence/raw/call2_…_text.txt`, `call3_…_text.txt`, plus `evidence/scores.json`.

## 6. Provenance / separation

* Every call records original file sha256, render sha256, page, endpoint, model, prompt sha256,
  raw path, usage, latency, finish_reason.
* Machine vs formal separation unchanged from the LG-035 baseline (referenced, not re-proven here).

## 7. Honest scope (path strength)

* API path: **actual** `OpenAICompatOcrBackend.transcribe()` + **actual** `PdfiumRasterizer.render()`
  were executed for all 3 calls.
* This is an **adapter-level harness**, **NOT full-product end-to-end**: `ProcessingEngine.process()`
  (source SoT write, `derivative/machine.vN.md`, intake job stage, per-page partial/failure receipt)
  was **not** exercised here. The per-page bounded loop / retry-0 / no-replay rules were honoured
  by the harness but the full engine path is **unverified in this run**.
* Product processor partial/failure rules: **baseline, named LG-040** if unverified.

## 8. Counters / budget

| counter | used / cap |
|---|---|
| OCR POST | **3 / 3** |
| health GET | **1 / 1** |
| retries | **0** |
| audio / embedding / ASR / worker | **0 / 0 / 0 / 0** |
| per-call timeout | 120 s (connect folded into the adapter's single urllib timeout; adapter has no separate connect knob — recorded honestly) |
| max output | 4096 |
| input per call / total | 33716/239092/34554 B / 307362 B ≤ 6 MiB |
| input ≤ 2 MiB each | yes |

pi/DeepSeek cost: **unknown, not zero**. LAN cost: unknown.

## 9. LG-035 acceptance coverage (original classes, honest)

| Original class | Before | This run |
|---|---|---|
| real clear page | PASS baseline CER 0.0000 | referenced, not re-proven |
| low-quality page | recorded only | **still gap** |
| multipage | PASS baseline | referenced |
| Chinese printed page | PASS Z1 CER 0.0423 | referenced |
| **table** | **UNMET** | **FAIL (structure=FAIL, cell CER 1.0)** |
| **mixed born-digital + scan (one file)** | **UNMET** | **PASS p1 0.0295, p2 0.0000** |

R3/R4/R5 historical FAIL remain FAIL. Z2 FAIL unaffected.

## 10. Boundaries

* No product / docs / backlog / frontend / PROJECT.md change; only this probe package.
* No push / deploy / publish / reset / clean. No nested agents. No secret output.
* Fixture plan/GT bytes unchanged. No default prompt change.
* No self-marked done; LG-035 stays `in-progress`.
