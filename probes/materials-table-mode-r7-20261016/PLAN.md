# LG-035 R7 — Table-aware OCR mode (OPTIONAL, default OFF) — FROZEN PLAN

* Owner package: `probes/materials-table-mode-r7-20261016/**` (only writer of this path).
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-table-mode-r7-20261016`
* Branch: `fix/materials-table-mode-r7-20261016`
* Base HEAD: `fix/materials-layout-r7-20261016` @ `8182d36` (explicit candidate dependency —
  **NOT** current `main@2d76c83`; root integrates `8182` first).
* Date (UTC): 2026-10-16. **This file is committed BEFORE any model POST.**

> Nothing here relaxes an existing threshold. Nothing here relabels R3/R4/R5/R6/R7.
> The fixture truth is the **original human-authored PDF text layer** (NOT OCR, NOT model output).

## 0. Problem statement (from prior evidence)

* R7 cohort `97c4f8f` (real grid T1): the default OCR prompt emits a **flat one-token-per-line
  list** (`structure=FAIL`, `machine_rows=0`, cell CER 1.0). The image genuinely contains a
  grid but the default prompt linearises it.
* R5 (`1a4759c`) showed a **global new prompt regresses ordinary prose** (Z2 worse; Z1 CER
  0.10582 vs 0.0423) — a global prompt swap is **rejected** and must not be repeated.
* R7 layout candidate `8182d36` proves a pure-pixel, scale-invariant, model-free table/layout
  signal exists (Z2 topology stable 1x/2x/4x; PNG decoder bounded).

## 1. What this package builds (minimal, bounded)

An **OPTIONAL table-aware OCR mode**, default **OFF**, wired through the *normal*
`SourceService → ProcessingEngine → OcrBackend` request path (not a standalone prompt harness):

1. **Program-side table classifier** (pure function of pixels + geometry; no GT / name / hash /
   known answers): given the rendered page PNG, decide *confidently* whether the page is an
   actual table using **bounded, stable column geometry + full-width horizontal rules**.
2. **Conditional prompt selection**: only when the page is confidently a table, request an
   **explicit grid** (Markdown pipe table) with generic structural instructions; **ordinary
   pages keep the exact original default prompt** (so R5 regression is not repeated).
3. **Explicit structured machine output**: the model must emit an explicit grid; no flat list.
4. **Provenance**: layout decision + prompt hash + input hash recorded in the per-page evidence.

### 1.1 Classifier signal (must be real, not decorative)

A real grid (T1, 3×8) measured: one region, 3 columns, gutters `(349,705)`/`(1296,1394)`,
4 full-width horizontal rules. Ordinary prose (MIX p1 NIST) measured: **ragged** region columns
(gutter positions differ per region) and *no* single region whose columns are stable across its
own lines. The classifier therefore requires **all** of:

* a single region whose `column_count >= 2`, **and**
* the same column gutters hold for (almost) every text line in that region (per-line column
  consistency — the discriminator that ordinary prose fails), **and**
* at least **two** horizontal rules spanning the content width (booktabs-style ruling), **and**
* column widths above the layout floor (already enforced by `layout.py`).

This uses only the layout geometry (pixels + normalised gutters). It never reads fixture
hashes/names/GT/known SI answers.

### 1.2 Honest GAP admission (decided at freeze time)

If a **reliable** table classifier cannot be built from these bounded signals, the package
**stops with an explicit gap** rather than shipping an unbounded heuristic. The classifier is
"reliable" only if it (a) fires on the real T1 crop and (b) does NOT fire on ordinary controls
(Z1 printed page, MIX p1 born-digital prose, MIX p2 real scan). This is verified offline before
any POST; the result is recorded truthfully either way.

## 2. Predeclared 2-call OCR plan (exact inputs / hashes / render / config)

### Call 1 — `LG035-R7-T1` real published grid TABLE (table mode must fire)

| Field | Value |
|---|---|
| sample | `LG035-R7-T1` (NIST SP 811 p.16, Table 1. SI base units) |
| input | fixture `honest_table_grid_scale4.png` |
| input sha256 | `39138a971d605f65d10b5df3a13e35c7cec5d3710bc38d55e6eb656fc1219652` |
| input bytes | 33716 (≤ 2 MiB) |
| render | table region PDF pts `(90.0,517.0,524.6,627.5)`, scale **4.0** |
| source page | NIST SP 811 (2008), PDF page 16 (0-based 15) |
| source sha256 | `788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f` |
| media_type | image/png, page=None (single image) |
| expectation | classifier fires → **table prompt** → explicit grid; scored vs frozen 24-cell truth |

### Call 2 — `LG035-ZH-Z1` ordinary Chinese printed page (table mode must NOT fire)

| Field | Value |
|---|---|
| sample | LG035-ZH-Z1 (老解老 p.10, public-domain scan + human Wikisource truth) |
| input | original JPEG `lg035_truth_zh_laojielao_p10.jpg` |
| input sha256 | `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f` |
| input bytes | 333996 (≤ 2 MiB) |
| source | Wikimedia Commons `File:10-13老解老.pdf` p.10 (License=Public domain) |
| human truth | `truth/LG035-ZH-Z1.p10.txt` (sha256 `9043c2b7…`) |
| media_type | image/jpeg, page=None (single image) |
| expectation | classifier does **NOT** fire → **original default prompt**; actual request hash proves unchanged; scored Z1 page CER ≤ 0.15 |

Total planned input bytes = 33716 + 333996 = **367712 B ≤ 4 MiB** (each ≤ 2 MiB).

## 3. Endpoint / config (actual, unchanged from authorized candidate)

* Endpoint `http://192.168.8.12:11434`, model `qwen3.8-27b` (existing authorized endpoint only).
* concurrency 1 · retries **0** · per-call total **120 s** / connect **5 s** · max output **4096**.
* Optional ≤ 1 health GET (8 s). Persistent reservation written BEFORE each forward; every raw
  (redacted) response/error persisted BEFORE scoring.
* audio 0 / embedding 0 / ASR 0 / worker 0. No provider switch, no login/signup/paid.
* Other endpoint/OCR-cohort owners **exited** (verified; wrappers not killed).
* Model truth is **never** placed in a prompt; prompts carry only generic structure instructions.

## 4. Scoring (frozen protocol, reused unchanged)

* `normalise(s) = "".join(ch for ch in NFKC(s) if not ch.isspace())`.
* **T1 table hardgate (UNCHANGED)**: machine rows incl. header **== 8**; machine columns **== 3**;
  table **cell CER ≤ 0.25**; symbol tokens `m,kg,s,A,K,mol,cd` each **byte-exact** in its cell.
  Parser accepts only an explicit emitted grid (Markdown pipe table or ≥2-space aligned columns);
  **never** reconstruct a grid from GT, **never** fill a machine cell from truth.
* **Z1 page gate (UNCHANGED)**: page CER **≤ 0.15**.
* R7 cohort flatlist FAIL (`97c4f8f`) is **historical and unchanged**; this run is a new,
  separately-scored candidate. Whether the new table prompt passes is **unknown** — reported honestly.
* Do **not** redefine a gate after seeing a result.

## 5. Necessary checks (bounded, predeclared)

1. optional feature default OFF;
2. env validity (invalid mode value → explicit error, never silent);
3. true candidate gating: table fires on T1, ordinary does not (offline, before POST);
4. pipeline wire: actual `ProcessingEngine.process()` request carries the table prompt + records
   layout/provenance in evidence for CALL1; and the **default prompt** for CALL2 (hash equality);
5. unsafe input bounds (over-size/decompression-bomb PNG refused; no raw untrusted PNG exposure
   without input/decompression bounds);
6. old layout cross-scale checks still pass (20 `test_layout.py` tests unaffected).
   Run affected `tests/sources/ocr` + `tests/sources` (processing/service) + `mypy` only.

## 6. Scope / non-goals

* Files owned: `backend/lightgravity/sources/ocr/{adapter.py,layout.py,__init__.py}`,
  `backend/lightgravity/sources/{processing.py,service.py}`,
  `tests/sources/ocr/**` (focused), `docs/08`/`docs/09` (narrow additive notes),
  `probes/materials-table-mode-r7-20261016/**`.
* No vector/frontend/coordinator/settings/store/backlog/root-PM-docs changes.
* No generic platform, no new dependencies, no new provider/model install.
* Contract: no public API change if an internal option suffices. If a protocol/schema change is
  unavoidable, classify against `docs/08` change control **before** implementation (prefer internal).
* Default `scale=2.0` and ordinary-page behaviour unchanged.
* No auto-retry; a timeout stops remaining calls and reports the rest **NOTEXECUTED**.
* No self-marked done; all real acceptance stays LG-040.

## 7. Failure handling (preregistered)

* Timeout → stop network; remaining calls NOTEXECUTED; no replay.
* Service error → counted; continue remaining calls unless a timeout stopped the run.
* Parse/score failure → FAIL/unverified recorded, never relaxed.
* If the classifier is not reliable (§1.2) → stop with an explicit gap, no unbounded design.

## 8. Budget (declared before running)

| Item | Bound |
|---|---|
| OCR POST incl. failures | **2** exact |
| retries | 0 |
| concurrency | 1 |
| health GET | ≤ 1 (8 s) |
| audio / embedding / ASR / worker | 0 / 0 / 0 / 0 |
| per-call timeout (connect/total) | 5 s / 120 s |
| max output tokens | 4096 |
| per-input / total input | ≤ 2 MiB / ≤ 4 MiB |
| pi wall / rounds / non-cache / retry | 720 s / 100 / 160000 / 0 |

pi/DeepSeek cost: **unknown, not zero**. LAN cost: unknown.
