---
title: "LG-040 BROWSER R1 — recovery STATUS"
doc_type: status
category: qa
updated: "2026-10-16"
---

# LG-040 BROWSER R1 — STATUS

| Field | Value |
|---|---|
| HEAD | `edaad8e2b06c45423f2b5062f0780d62c00ada97` |
| Branch | `qa/lg040-browser-r1-20261016` |
| Product subtree | unchanged vs `2f277fa` (`backend frontend tests` diff empty; working tree clean) |
| Closure mode | non-replay recovery/finalization, **0 new LAN / GET / POST / inference**, no live rerun |
| Overall verdict | **INCOMPLETE** (2 UI cases UNVERIFIED; not a whole-version PASS) |
| Report | `probes/lg040/BROWSER-R1-20261016/REPORT.md` |

## Coverage

- Driver cases executed & persisted: **31** (28 pass / 3 fail) in `evidence/live/`.
- Required screenshot cases: **6** all PASS (`evidence/live/01..05*.png`, preserved).
- UNVERIFIED: `search returns a real source hit with v+hash`;
  `search rebuild_if_missing returns hit with hash back-check` — both searched the
  literal term `Invoice`, absent from both OCR'd docs (test-design artifact, not a
  verified product bug).

## OCR (real, live)

- POST cap **2**, **used 2** (ledger `post_used=2`, both HTTP 200) → **remaining 0**,
  reserved 0, unknown 0; cap **NON-RENEWED** this closure (spent 0).
- Input1 `clear_real.pdf`: `prompt_kind=default`, 276/114 tok, 7.197 s, **succeeded**.
- Input2 `honest_table_grid_scale4.png`: `prompt_kind=table`, 954/1833 tok, 98.817 s, **succeeded**.
- Env wiring confirmed correct live (default vs table prompt hashes match frozen truth).
- Dry-mode "failed/unavailable" is an intended harness condition, **not** a product OCR defect.

## Frontend provenance

- **Real built frontend, same-origin HTTP** (`frontend/dist` real Vite bundle served
  by real `create_app`); not `file://`, no interception/generated images.

## Processes / ports

- No leftover proxy/app/browser for this package; only the current closure wrapper
  is running. **Nothing stopped**; no port released (none was held).
- `8123` and the in-flight QUALITY run (18140/18141) untouched.

## Counts

- New product calls this closure: **0**. Prior live product OCR POSTs: **2 (actual, ledger)**.
- PI model tokens: **not printed**; PI cost **unknown (not 0)**.

## Exact next step

After QUALITY finishes (no concurrent LAN): root-coordinated final candidate retest
with a **corrected search term** and **single end-of-run state capture**; obtain an
explicit budget decision before any further live OCR POST.
