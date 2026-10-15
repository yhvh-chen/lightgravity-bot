# LG-035 TRUTH-PREP — local scoring protocol (NO model execution)

This protocol is **prepared, not executed**. It defines how a **later,
separately-authorized** run would score a machine OCR output against the
human truth in `../truth/*.txt`. Running it requires no network and no model;
it is pure local string comparison. **No OCR, embedding or ASR is run here.**

## 0. Invariants

* Truth is **human** (Wikisource ProofreadPage level 3). Never replace truth
  with a model's output, and never score a machine answer the model produced
  using that same answer as truth.
* A machine page that fails must never contribute body text and must never be
  reported `searchable=true`.
* All thresholds are **pre-registered before** any OCR run; they must not be
  relaxed afterwards to pass.

## 1. Character normalisation (reused from cohort A/B, unchanged)

```
normalise(s):
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if not ch.isspace())
    return s

cer(norm_truth, norm_hyp):
    return edit_distance(norm_truth, norm_hyp) / max(1, len(norm_truth))

accuracy = 1 - cer
```

* Edit distance = Levenshtein over Unicode code points.
* Whitespace is stripped **before** CER (Chinese pages), matching cohort A/B.

## 2. Per-class thresholds (pre-registered, do not relax)

| Class | Metric | Threshold | Sample |
|---|---|---|---|
| real Chinese printed page | page CER | ≤ 0.15 | Z1 (`LG035-ZH-Z1`) |
| real Chinese table/side-by-side page | cell/segment CER ≤ 0.25 **and** structural pass (below) | Z2 (`LG035-ZH-Z2`) |
| low-quality page (optional) | recorded, never a pass claim | — | — |

## 3. Field / token truth (mechanical, byte-exact after NFKC)

For any number-like or ID-like token present in human truth, the machine output
must contain it **byte-exact after NFKC** — no silent digit/ID normalisation and
no dropped or invented values. Record each token as `{token, present: bool,
exact: bool}`.

## 4. Table structure check (Z2 class)

Against a pre-declared human structure:

1. machine table **row count** == human row count, and
2. machine table **column count** == human column count, and
3. every human cell/segment token appears byte-exact after NFKC.

Structure pass requires (1) AND (2) AND (3). If the model emits no table
structure, record `table_rows=0` and the metric as **failed**, never
"not applicable".

## 5. Page back-reference requirement

Every machine page block must carry `page=<n>` and `input_sha256` equal to the
SHA-256 of the exact image bytes the model saw. For Z1 the prepared input image
is `samples/private/lg035_truth_zh_laojielao_p10.jpg`
(`sha256=5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f`).

## 6. Machine vs. formal separation (unchanged from QUALITY-PLAN)

* `derivative/machine.v<ver>.md` = machine copy.
* `formal/FORMAL.md` = human copy, **separate directory**.
* `reprocess` after a formal edit must not change `formal/FORMAL.md`.

## 7. How a later run consumes this package

1. Fetch Z2's PDF with the command in `manifest/truth_manifest.json` and verify
   `sha1=fe5572520076aee2f3a252277e0fa648588a02bc`.
2. Confirm `192.168.8.12:11434` (or another explicitly authorized
   OpenAI-compatible OCR endpoint) is reachable — currently **unreachable**.
3. Run the **product** OCR adapter (`OpenAICompatOcrBackend`, product Python
   3.12 env) against Z1 and Z2 within the declared POST budget.
4. Score with §1–§4 against `truth/LG035-ZH-Z1.p10.txt` and
   `truth/LG035-ZH-Z2.p2.txt`.
5. Report pass/fail honestly per class; a blocked endpoint or missing sample
   stays blocked, never fabricated.

## 8. Explicit non-goals of this package

* No OCR / embedding / ASR execution.
* No quality-pass claim; LG-035 stays `in-progress`.
* No unlocking of LG-040 / LG-041.
* No synthetic image, synthetic scan, or machine-output-as-truth.
