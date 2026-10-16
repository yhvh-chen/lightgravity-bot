---
title: "LG-040 FILES-NARROW-FIX-20261016 — REPORT"
doc_type: report
category: engineering
status: "final"
updated: "2026-10-16"
---

# LG-040 FILES-NARROW-FIX — REPORT

## 1. Identity

| Field | Value |
|---|---|
| Role | Frontend Files Materials CSS implementer (NOT independent QA) |
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-files-narrow-fix-20261016` |
| Branch | `fix/lg040-files-narrow-20261016` |
| Base | `75c6048` (LG-040 R1 integration candidate) |
| Owner writes | `frontend/src/views/files/files.css` + `probes/lg040/FILES-NARROW-FIX-20261016/**` only |
| Product file changed | `frontend/src/views/files/files.css` (CSS only, no TSX/logic change) |

## 2. Root cause (verified, not guessed)

The narrow-width horizontal overflow was in the **Files → Materials** surface,
inside `frontend/src/views/files/files.css`:

1. `.lg-files-materials` (the section) is a flex item inside `.lg-files`, which
   is a flex column with `overflow: hidden`. With no `min-width: 0` the section
   sized to its content's **max-content** width instead of the available width.
2. `.lg-files-materials__body` used `grid-template-columns: minmax(220px, 320px) 1fr`.
   The `1fr` track lacks `minmax(0, 1fr)`, so non-wrapping detail content
   (`white-space: nowrap` names, long source ids / content hashes) expanded the
   track instead of wrapping.
3. Grid children defaulted to `min-width: auto`, so the list/detail panels could
   not shrink below their content.
4. The lone `@media (max-width: 700px)` stack did not cover the real breakpoint:
   the app shell keeps the 56px rail + 240px context + 360px chat **inline down
   to 1023px**, so at a 1024px viewport the content area is only ~330px wide and
   the 220px list floor left the detail panel at ~0 width.

Baseline failure (`documentElement.scrollWidth > innerWidth + 2` at 390px Files
Materials) was **independently proven** in the committed BROWSER-RETEST R1
report (`59fe58e`, `probes/lg040/BROWSER-RETEST-R1-20261016/REPORT.md` §6). It
was NOT re-reproduced here; this slice fixes it and re-measures.

## 3. Fix (minimal CSS, no fake clipping)

`frontend/src/views/files/files.css`:

- `.lg-files-materials { min-width: 0; }` (stop max-content sizing).
- `.lg-files-materials__body { grid-template-columns: minmax(220px, 320px) minmax(0, 1fr); min-width: 0; }`.
- `.lg-files-materials__list-panel, .lg-files-materials__detail-panel { min-width: 0; }`.
- `.lg-files-materials__list, .lg-files-materials__facts { min-width: 0; }` and
  `.lg-files-materials__facts dd { overflow-wrap: anywhere; }` (wrap long ids/hashes).
- `.lg-files-materials__textarea { width: 100%; min-width: 0; box-sizing: border-box; }`.
- Stack breakpoint `@media (max-width: 1199px)` → single `minmax(0, 1fr)` column,
  chosen to account for the still-inline shell chrome (56 + 240 + 360) so the
  detail panel is never squeezed to 0 at 1024px.
- Outer Files grid hardening: `.lg-files__body { min-width: 0; }` and
  `.lg-files__tree-panel, .lg-files__preview { min-width: 0; }`.

**Explicitly NOT done** (forbidden fake fixes): no `overflow: hidden` on body /
panels to hide the problem, no clipping, no `position` hacks. Preview/code
blocks keep their own `overflow: auto`; the outer Files grid keeps its desktop
behaviour (`minmax(200px, 280px) minmax(0, 1fr)` unchanged; only `min-width: 0`
added).

## 4. Verification — real app + fresh frontend build + real Firefox BiDi

Harness reused **in whole** from the proven committed BROWSER-RETEST R1
orchestrator/launcher/deny-proxy (`59fe58e`), copied into this probe with only
own-probe/driver path constants changed (no `sed` of nested blocks). The
interrupted attempt's already-written minimal driver was used (not redesigned).

- Real product app launched via `launch_app.py` on a **read-only snapshot copy**
  of the real prior data (`evidence/snapshot/data`, 3 real sources).
- **Real built `frontend/dist`** served by the product itself (fresh bundle from
  this CSS change).
- Real Firefox WebDriver BiDi; actual DOM box measurement +
  `documentElement.scrollWidth` + screenshots.
- OCR/embedding targets point at a loopback **DENY** proxy. Ledger:
  `{"attempts": 0, "events": []}`. No uploads, no reprocess, no model calls.

Command actually used:

```
RUN_DIR=/tmp/lg040-files-narrow-run3-<pid> \
  .venv/bin/python probes/lg040/FILES-NARROW-FIX-20261016/scripts/orchestrate.py
```

### Result: 13/13 PASS

| Check | 390 | 1024 | 1440 |
|---|---|---|---|
| Files Materials no horizontal overflow (`scrollWidth ≤ innerWidth+2`) | PASS (390=390) | PASS (1024=1024) | PASS (1440=1440) |
| English actions visible & in-viewport | PASS | PASS | PASS |
| Detected panel widths | list=detail=310 (stacked) | list=detail=276 (stacked) | list=320 / detail=360 (2-col) |
| Long name/path no page overflow | PASS | — | — |
| Preview body keeps own scroll | PASS (`overflow: auto`) | — | — |
| Chat 390 unchanged (no overflow, search present) | PASS | — | — |
| Desktop 1440 two-panel grid preserved | — | — | PASS |

Evidence: `evidence/run/lg040-files-narrow-results.json`,
`evidence/run/dom-diagnosis.json`, screenshots `diag-files-materials-*.png`,
`verify-chat-narrow-390.png`, `verify-files-materials-desktop-1440.png`,
run logs in `evidence/run-logs/`.

## 5. Local non-browser checks

- `tsc --noEmit`: exit 0.
- `vite build`: success (fresh `dist/assets/index-DIrliPjY.css`).
- No Files component tests exist and none were added (CSS-only change; no
  mirroring tests per instruction).

## 6. Limitations / independent recheck needed

- This slice does **not** issue a whole-package LG-040 verdict and is **not**
  independent QA. The verification is the implementer's own minimal driver.
- The 1024px breakpoint decision is viewport-based and assumes the shell chrome
  widths above; if those tokens change, re-check the threshold.
- Independent QA should re-measure the 390/1024/1440 Files Materials widths on
  the committed bundle and confirm no fake clipping (no body `overflow: hidden`).

## 7. Stop state

Clean: no live writers started beyond own children (all stopped), no broad
`pkill`, the pre-existing `:8123` service untouched, deny ledger 0, snapshot/live
data untouched (read-only), no new uploads/OCR.
