---
title: "LG-040 QUALITY-R1-20261016 METHOD-AUDIT — STATUS"
doc_type: report
category: probe
status: "complete — independent classification of existing frozen bytes; 0 model calls"
updated: "2026-10-16"
---

# STATUS — METHOD-AUDIT (LG-040 QUALITY-R1-20261016)

- **Owner**: independent pi method auditor; Root PM only. Same named LG-040 milestone.
- **Worktree / base**: `qa/lg040-quality-r1-20261016` @ `cc09a98`; product == `2f277fa` (byte-identical).
- **Write scope**: only `probes/lg040/QUALITY-R1-20261016/METHOD-AUDIT/**` (new). Originals untouched
  and hash-verified unchanged (see `AUDIT.md` §0).
- **Activity**: offline re-scoring only. No network/POST/model/new-experiment/product writes.
- **Quota**: OCR 2/2, embedding 17/18 (**1 spare UNSPENT**), inference 19/≤20, retries 0.

## Classifications

| Finding | Classification |
|---|---|
| OCR page-1 "CER 2.79" | **BENCHMARK_DEFECT** — full-page output compared to a 600-char mid-page subset reference; corrected full-page CER **0.0026** (ed 6). Frozen FAIL kept historical as INVALID_REFERENCE. |
| TIFF HTTP 500 vs PNG success | **KNOWN_LIMIT** — unsupported format failed honestly (no false success); PNG image vector works. |
| G2 image top-1 FAIL / PNG rank 2 | **KNOWN_LIMIT** — rank-1 D2 is the same-content text twin of D3 (relevant duplicate), margin 0.0448; G2 stays FAIL as experiment result. |
| G2 "image top-1" as hard gate | **UNVERIFIED** — declared QA-owner metric, not a docs/08–09 or user/PM release-hard condition. |

## Deliverables

- `METHOD-AUDIT/AUDIT.md`
- `METHOD-AUDIT/recompute.py`, `METHOD-AUDIT/recompute_output.json`
- `METHOD-AUDIT/STATUS.md` (this file)
