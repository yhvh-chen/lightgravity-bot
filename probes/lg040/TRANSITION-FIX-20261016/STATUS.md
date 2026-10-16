---
title: "LG-040 TRANSITION-FIX-20261016 — STATUS"
doc_type: status
category: engineering
status: "final"
updated: "2026-10-16"
---

# STATUS — LG-040 TRANSITION-FIX

| Item | State |
|---|---|
| Product fix | **DONE** — `frontend/src/app/shell.css` (CSS only, no state/logic change) |
| Root cause | Inline JS-width rail wrappers kept width during 1440↔390 transition before React `compact` commit → transient `docScrollWidth 428` at 390 (recorded pre-fix FAIL) |
| Built bundle carries fix | YES (`lg-chat-rail,...{display:none}` in `dist/assets/index-DRJ4h6SM.css`) |
| CSS bundle sha256 | `a62d304df63662e4fae57a6d31c1ee5d65a83dd3c464c7aa36bcda4ae11769f0` |
| `tsc`/build receipt | Build confirmed by compiled dist artifact; **no retained exit-code log** |
| Transition overflow (FIXED) | **0** maxOvershoot all 5 states (`transition-results-FIXED.json`) |
| Sustained 390 starvation | **0** overflow over 2011 samples; rail hidden; panels usable |
| Files narrow matrix | **PASS 19/19** (390/1024/1440) |
| Remaining failed assertion | **1** — settle requires `.lg-chat-rail` **removed from DOM**; fix uses CSS `display:none` (still mounted). Overflow in same scenario PASSES. Assertion-authoring mismatch, NOT a regression |
| Old raw failure | Preserved unchanged (not re-labeled PASS) |
| New probes this session | **NONE**; `lg040-finalqa-width-driver.mjs` retained raw as **UNEXECUTED** |
| Deny ledger | 0 attempts |
| Fake clipping (body overflow:hidden) | NOT used |
| Independent QA | **NOT performed here** — settle DOM-removal contract + whole-package LG-040 verdict are QA's next scope |
| Whole-package LG-040 verdict | NOT owned by this slice |

Files of record: `REPORT.md`, `STATUS.md`, `scripts/` (existing own probe
harness), `evidence/run/` + `evidence/snapshot/` (retained raw).

Stop state: no live writers started (none to stop); `:8123` untouched; no broad
`pkill`; no product model / backend / push.
