---
title: "LG-040 GATE-PREP — offline CER recompute record"
doc_type: report
category: probe
status: "complete — 1 offline stdlib run, no network"
updated: "2026-10-16"
---

# Offline CER recompute — record

## Inputs (read-only, from `materials-retry-20261016-r2` @ `b3b7b4f`)

- Human truth: `probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z1.p10.txt`
  (Wikisource ProofreadPage **level 3**; paired to PD scan `File:10-13老解老.pdf` p10).
- Machine hypothesis: `.text` field of
  `probes/materials-retry-20261016-r2/evidence/ocr_result.json`.
- Fixture image: `probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg`
  sha256 `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f`
  (re-verified by `sha256sum` in this audit; matches OCR `input_sha256` and manifest).

## Method

`SCORING-PROTOCOL.md` §1: `NFKC` normalize → strip whitespace → Levenshtein over code points →
`CER = edit_distance / max(1, len(norm_truth))`. Threshold 0.15 pre-registered **before** the r2 run.
No network, no model, pure local Python 3 stdlib.

## Result

```
truth_chars(norm) = 189
hyp_chars(norm)   = 193
edit_distance     = 8
CER               = 0.0423
threshold 0.15 -> PASS
```

Matches the committed `evidence/ocr_cer.json` (`truth_chars=189, hyp_chars=193, edit_distance=8,
cer=0.0423, verdict=PASS`) exactly.

## Interpretation

Reproduces the arithmetic and truth pairing. It does **not** convert a single-page smoke into a
quality battery; Z2 table/mixed/multi-page classes remain unrun, and real retrieval/ASR quality
remain unmeasured. No implementer evidence was modified.
