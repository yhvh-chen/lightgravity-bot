---
title: "LG-040 FILES-NARROW-FIX-20261016 — STATUS"
doc_type: status
category: engineering
status: "final"
updated: "2026-10-16"
---

# STATUS — LG-040 FILES-NARROW-FIX

| Item | State |
|---|---|
| Product fix | **DONE** — `frontend/src/views/files/files.css` (CSS only) |
| Typecheck | PASS (`tsc --noEmit` exit 0) |
| Build | PASS (`vite build`, fresh bundle) |
| Browser verify | **PASS 13/13** (real app + fresh dist + real Firefox BiDi) |
| 390 Files Materials overflow | **FIXED** (`scrollWidth == innerWidth == 390`) |
| 1024 Files Materials | **FIXED** (stacked; detail panel full width, not 0) |
| 1440 Files Materials | **UNCHANGED** (two-panel grid, list 320 / detail 360) |
| Chat 390 | **UNCHANGED** (no overflow, search present) |
| Deny ledger | 0 attempts |
| Fake clipping (body overflow:hidden) | NOT used |
| Independent QA | NOT performed here — recheck required |
| Whole-package LG-040 verdict | NOT owned by this slice |

Root cause: missing `min-width: 0` (section + grid children), `1fr` track not
`minmax(0,1fr)`, and a 700px stack breakpoint too low for the inline shell
chrome (1023px cutoff) — see `REPORT.md`.

Files of record: `REPORT.md`, `evidence/run/`, `evidence/run-logs/`,
`scripts/` (harness copied in whole from proven BROWSER-RETEST R1).
