---
title: "materials-ocr-r4 — STATUS"
doc_type: status
category: probe
updated: "2026-10-16"
---

# STATUS — materials-ocr-r4-20261016

- Branch `fix/materials-ocr-r4-20261016`, base `main @ db01cd6`.
- PLAN frozen in a separate commit (`311c2d4`) **before** any POST.
- Product repair committed (`8337e04`); scoring/raster committed (`e9fd5e5`);
  report + evidence final.
- Counters: GET 1/1, POST 1/2 (planned 1 spent), retries 0, ASR 0, embedding 0.
- Mechanism repair **PASS**; Z2 table quality **FAIL** (whole 0.2508; fair
  token-weighted segment 0.2689; structure unverified/fail).
- No task status / main / R3 / audit changes.
