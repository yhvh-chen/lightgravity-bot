---
title: "LG-040 TRANSITION-QA-20261016 — STATUS"
doc_type: status
category: qa
status: "final"
updated: "2026-10-16"
---

# STATUS — LG-040 TRANSITION-QA

| Item | State |
|---|---|
| Candidate | `30029eb95465c32fde94dcf7ce44ae18db4a43a0` (LG-040 transition shell-CSS fix) |
| Fresh build | `tsc --noEmit` EXIT 0; `vite build` EXIT 0 (logs + exit files retained) |
| Bundle CSS sha256 | `a62d304df63662e4fae57a6d31c1ee5d65a83dd3c464c7aa36bcda4ae11769f0` (matches implementer claim) |
| Transition max overshoot | **0** on all sampled transitions/states |
| Sustained 390 starvation | **0** overflow / 1986 samples |
| Width matrix | **19/19 PASS** (390/1024/1440) |
| Bounded readiness | **ready=true at 76 ms** (bound 2000 ms, corrected predicate) |
| Old raw FAIL preserved | YES — `evidence/prior-raw-FAIL/` (`docScrollWidth 428`, unmodified) |
| 2 s bound | **Kept**; NOT relaxed to 8 s |
| CSS display:none rail | Accepted as valid (DOM unmount NOT required) |
| Deny ledger | 0 attempts (all 5 runs) |
| Own children stopped | YES (none lingering) |
| `:8123` / source data | Untouched; snapshot read-only copy unchanged |
| Product/task/upstream changes | NONE |
| Verdict | **PASS_WITH_LIMITATIONS** (0 open important defects in scope) |
| User final acceptance | PENDING |

Files of record: `REPORT.md`, `STATUS.md`, `scripts/`, `evidence/run/`,
`evidence/snapshot/`, `evidence/prior-raw-FAIL/`.
