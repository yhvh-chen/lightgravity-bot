# LG-035 R7 Layout Cross-Scale Finalization — REPORT

- **Task**: continuation/finalization of interrupted `fix/materials-layout-r7-20261016`
- **Worktree**: `/home/yhvh/code/lightgravity-bot-worktrees/materials-layout-r7-20261016`
- **Branch**: `fix/materials-layout-r7-20261016`
- **Base HEAD**: `2d76c830badbbe79dafd2f8ff7d6e8ff425a6f82`
- **Continuation note**: the first attempt wrapper exited **143** (`max_rounds_reached`, ~381s) with unknown side effects. Live-writer check before touching anything: the only process with cwd in this worktree was **this** continuation wrapper (`materials-layout-r7-close-20261016.txt`, pid 3012498); no stale writer, no `.git` lock. All pre-existing dirty work was preserved (non-replay continuation; no reset/clean).

## Status: PASS (scoped acceptance)

The existing R6 algorithm already satisfies the acceptance criteria. This
finalization added **only** the essential cross-scale / PNG-bound checks plus a
decoder allocation bound; it did **not** redesign or tune the algorithm.

## Delivered files (owned only)

| Path | git-hash-object |
|---|---|
| `backend/lightgravity/sources/ocr/layout.py` | `b11dd4be149c1c28e77d1ce66b1bcfafcccdaf7e` |
| `backend/lightgravity/sources/ocr/__init__.py` | `5bc55520244889ed42b7a9f9d7d49891a691769c` |
| `tests/sources/ocr/test_layout.py` | `6980bc92347f0b0503d76c894b8cdcc1fe5cdc8e` |
| `probes/materials-layout-r7-20261016/sweep.py` | `873eef61972515fbd521e3251082064423d58d02` |
| `probes/materials-layout-r7-20261016/scale_diagnose.py` | `bb13cf2dbde972cf39becfebfaad755257ef5fa3` |
| `probes/materials-layout-r7-20261016/evidence/scale_diagnosis.json` | `d834d90de0dfb89ac64bbe3b8058eb161ee37092` |

Changes made this continuation (minimal):
- `layout.py`: bounded PNG IDAT inflation (security), docstring notes for the
  scale-invariant topology and decoder bounds. `__all__` was already complete.
- `test_layout.py`: +4 tests (cross-scale Z2 topology, control single-column,
  2 PNG-bomb/bound tests).
- `evidence/scale_diagnosis.json`: regenerated; **byte-identical** to the
  pre-existing evidence (deterministic).

## Check commands and exits

| Command | Exit | Result |
|---|---|---|
| `PYTHONPATH=$PWD/backend .venv/bin/python -m pytest tests/sources/ocr/test_layout.py -q` | 0 | **20 passed** (16 R6 + 4 new) |
| `PYTHONPATH=$PWD/backend .venv/bin/python -m mypy backend/lightgravity/sources/ocr/layout.py backend/lightgravity/sources/ocr/__init__.py` | 0 | Success, no issues |
| `PYTHONPATH=$PWD/backend .venv/bin/python probes/materials-layout-r7-20261016/scale_diagnose.py` | 0 | wrote evidence; `diff` vs prior = identical |

No full suite was run (per instruction). OCR calls: **0**. Network calls: **0**.
The venv used is the main worktree's `.venv` read-only for deps; `PYTHONPATH`
forces this worktree's `backend/`.

## Scale topology (actual, from `evidence/scale_diagnosis.json`)

Z2 page 2 (`LG035-ZH-Z2.pdf`):

| scale | column_model | global_cols | max_region_cols | region_counts | side-by-side region |
|---|---|---|---|---|---|
| 1.0 | `multi_column_local` | 1 | 2 | [1, 2, 1, 1] | region 1, cols=2 |
| 2.0 | `multi_column_local` | 1 | 2 | [1, 2, 1, 1] | region 1, cols=2 |
| 4.0 | `multi_column_local` | 1 | 2 | [1, 2, 1, 1] | region 1, cols=2 |

Controls (`clear_real.pdf`, `multipage_real.pdf`) at 1x/2x/4x: all
`single_column`, region_counts `[1]`, `is_multicolumn=False`.

## Criteria and measured result

- **Same high-level model at 1/2/4** — PASS (all `multi_column_local`).
- **Same normalized region counts** — PASS (identical `[1, 2, 1, 1]`).
- **Actual side-by-side region detected at all scales, not collapsed** — PASS
  (region index 1 has cols=2 at 1x/2x/4x; anti-collapse assertion proven
  load-bearing: a collapse to `[1,1,1,1]` is rejected by exact count compare).
- **Real ordinary control single-column** — PASS (6/6 control renders).
- **Normalized coordinates within predeclared tolerance** — PASS against
  `CROSS_SCALE_COORD_TOLERANCE_NORM = 15.0`; measured max drift ≈ 13.0 px.
  Left edges / y bounds stable ≲1 px; the largest drift is the right edge of the
  side-by-side region's second column, caused by faint right-edge word fragments
  falling below the ink threshold at 1x. This is rasterisation jitter, not a
  topology change. The tolerance is far below the ~40+ px gutter width, so it
  cannot mask a lost gutter.
- **Deterministic output / source-page hash** — PASS. Evidence regenerated
  byte-identical; `input_sha256` is the exact page bytes (`analyse_rendered_page`
  hashes the rendered PNG).
- **Ground truth never an algorithm input** — PASS (layout.py is a pure function
  of pixels/geometry; GT not imported).
- **Default pipeline unchanged** — PASS (no changes to `adapter.py`, `pdf.py`,
  or any non-owned file; `__init__.py` only re-exports).
- **OCR quality** — NOT assessed; **no claim of quality pass**.

## Security review — PNG decoder (local bounds)

Pre-existing risk fixed this continuation:

- **Before**: `zlib.decompress(bytes(idat))` was **unbounded**; a small IDAT
  could inflate to an arbitrarily large buffer (decompression bomb).
- **After**: IHDR geometry is checked against `MAX_PAGE_SIDE` /
  `MAX_PAGE_PIXELS` before inflation, and IDAT is inflated via a capped
  `decompressobj().decompress(..., expected)` limited to exactly the declared
  row bytes; over-long streams are refused via `unconsumed_tail`. Two new tests
  cover both refusals.
- **Remaining limitation (noted, not fixed)**: IDAT payload chunks supplied by
  the caller are accumulated in memory; the bound is the caller-provided input
  size, not an independent cap. Acceptable for the product rasteriser's own PNG
  output on local files; would need a stream cap if fed untrusted remote bytes.

## Limits / caveats

- Cross-scale coordinate tolerance (15 px) is empirically motivated by 1x
  aliasing on the real Z2 fixture; it is declared, not fitted per-run, and does
  not permit collapse.
- Only the layout test module was run; broader OCR/PDF suites untouched.
- `min_gutter_px`, `MAX_PAGE_SIDE`, `MAX_PAGE_PIXELS` and the gutter/line-band
  fractions were left at their R6/R7 values.
