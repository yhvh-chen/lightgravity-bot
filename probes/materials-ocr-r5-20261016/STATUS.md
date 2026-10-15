---
title: "Materials OCR R5 — STATUS"
doc_type: status
category: probe
updated: "2026-10-16"
---

# STATUS — materials-ocr-r5-20261016

- Branch `fix/materials-ocr-r5-20261016`, base `main @ a2dc40a` (clean).
- PLAN frozen in a separate commit (`7afe8eb`) **before** any POST.
- Product change committed (`06fabd3`): generic layout-aware OCR instruction.
- Counters: GET **1/1**, POST **2/2** (both planned), retries 0, ASR 0,
  embedding 0.
- **Z1 printed page PASS** (whole-page CER 0.10582 ≤ 0.15; ordinary text
  retained). **Z2 table quality FAIL** (fair token-weighted segment CER
  0.277946 > 0.25; no Markdown table emitted ⇒ `machine_rows=0` structural
  FAIL).
- Focused tests: `tests/sources/ocr/{test_adapter,test_processing}.py` **23
  passed**; mypy 2 changed source files **Success**.
- No LG-035 status / frontmatter change; no docs/08 change; no main / R3 / R4 /
  vector changes; no push/deploy/publish.

## Rounds

- R1 (done): worktree, context read, PLAN frozen, health GET 1/1.
- R2 (done): product instruction + focused tests + docs09 note; focused tests
  and mypy pass.
- R3 (done): offline scoring method comparability check (reproduces R4 exact).
- R4 (done): exactly 2 bound POST (Z2 scale4 layout; Z1 regression).
- R5 (done): rescore + REPORT + STATUS + commit.
