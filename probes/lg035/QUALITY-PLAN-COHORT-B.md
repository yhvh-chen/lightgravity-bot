# LG-035 QUALITY PLAN — COHORT B (append-only; frozen before any new inference)

Status: **frozen before any new inference POST**. This file is **additive** to
`QUALITY-PLAN.md` (cohort A). It does **not** change cohort A's samples,
thresholds, scores or the original pass/fail record. Cohort A stays exactly as
recorded; this cohort exists only to close the three quality-gate gaps that
cohort A left **BLOCKED**:

1. a real **Chinese** page with **human** ground truth,
2. a page with a **table** structure,
3. a **mixed born-digital text + scan** input in one file.

Cohort A's original thresholds are **not modified**. No cohort A score is
reused, re-scored or reinterpreted here. This cohort is only meaningful if it is
run with the **product** OCR adapter (`OpenAICompatOcrBackend`) from the product
Python 3.12 env against the same authorized candidate.

## 0. Hard prerequisites (must hold before any POST)

* The authorized candidate endpoint `http://192.168.8.12:11434` must be
  reachable. Verified state at cohort-B freeze time: **UNREACHABLE**
  (`connect: No route to host`, ICMP 100% loss — see `reports/cohort_b/`).
  While this holds, **no new OCR POST is performed at all** and this cohort
  makes **zero** quality claims. The blocker is recorded as an external,
  environment-level cause, not a sample cause.
* Every sample must be **publicly licensed** for product-fixture reuse and
  must ship **human** ground truth (not machine output). Provenance, licence
  and SHA-256 must be recorded before use.

## 1. Budget for cohort B (declared before running)

| Item | Bound |
|---|---|
| read-only `health`/`props`/`models` | ≤ 2 requests (within the shared ≤4 read budget) |
| **new** inference POST, incl. failures | ≤ 5 |
| **LG-035 cumulative** inference POST, incl. failures/retries/prior packages | ≤ 10 (cohort A already used **4**) |
| automatic retries | 0 |
| concurrency | 1 |
| per-page output | ≤ 2000 tokens |
| timeout (non-cold) | 90 s |
| timeout (first cold load) | ≤ 180 s |
| additional network download | ≤ 20 MiB total, ≤ 10 MiB per file, HTTP timeout 30 s |
| product real worker calls | 0 |

### 1.1 True inference-POST accounting (from raw logs, not reports)

* `probes/lg035/reports/http_log.jsonl` → **4** `POST /v1/chat/completions`
  (cohort A; 0 failures). This is the LG-035-origin count.
* The prior **LG-034** source-intake evidence
  (`probes/source-intake/evidence/.../http_log.jsonl`) contains 2 OCR
  `chat/completions` + 2 audio attempts + 1 embeddings = 5 inference POSTs, but
  those belong to **LG-034's** budget/evidence, not LG-035's task record.
* **LG-035 cumulative = 4 / 10** → at most **6** remain. Cohort B caps itself at
  **5** to leave margin. If the endpoint stays unreachable, **0** are used.

A timeout is an unknown outcome and is **never** replayed; a failed attempt is
counted.

## 2. Pre-registered cohort-B criteria (do not relax to pass)

Same metric definition as cohort A: CER on NFKC-normalised, whitespace-stripped
text, `edit_distance / len(gold_norm)`, `accuracy = 1 - CER`.

| Sample class | Threshold (pre-registered) | Notes |
|---|---|---|
| real Chinese page, human truth | **CER ≤ 0.15** | dense CJK form/print page |
| Chinese table page | **CER ≤ 0.25** on cell text | table metric is separate, see §3 |
| mixed born-digital text + real scan (one PDF) | text-layer page CER ≤ 0.15; scan page within its class | derived fixture must be labelled as derived |
| low-quality Chinese page | recorded, not scored | honest failure allowed |

**Anti-fabrication rules (unchanged from cohort A):**

* Ground truth is **human** only. **Never** use this run's OCR output as truth.
  The earlier synthetic 2-image CER 0 evidence is **explicitly not reused**.
* A failed page must never contribute body text and must never be
  `searchable=true`.
* If no eligible sample is obtainable under licence/budget, the class stays
  **BLOCKED** and **no metric is claimed**.

## 3. Table-structure criteria (pre-registered)

For a Chinese table page, in addition to cell-text CER, the machine Markdown
must be checked against a pre-declared structure:

1. the number of machine table rows equals the human row count, and
2. the number of machine table columns equals the human column count, and
3. every human cell value's number-like/ID tokens appear **byte-exact** after
   NFKC (no silent digit/ID normalisation).

If the model emits no table structure, record `table_rows=0` and the metric as
**failed**, not "not applicable". Structure pass requires (1) AND (2) AND (3).

## 4. Input / ground-truth / key fields per class

| Class | Input | Ground truth | Key fields |
|---|---|---|---|
| Chinese real page | real scan (PNG/JPEG) or PDF page | human full-page transcript | full text CER; `input_sha256`; `page` |
| Chinese table | real scan of a table | human cell matrix + human row/col counts | cell CER; rows; cols; byte-exact tokens |
| mixed text+scan PDF | one PDF, one born-digital text-layer page + one real scanned page, both from licensed sources | human text for each page | per-page CER; explicit "derived fixture" label |

Mixed-file fixture may be **assembled** only from already-licensed real
material (a real scanned page + its real/derived text page). It must be
labelled **"mixed fixture derived from real licensed sources"** — never
presented as a native born-digital+scan PDF.

## 5. Sample coverage target for cohort B

* ≥1 real Chinese page with human truth.
* ≥1 Chinese table page (can be the same page only if it has a labelled table
  region with human cell truth).
* ≥1 mixed text+scan PDF (derived, labelled).
* ≥1 low-quality Chinese page (recorded only).

If any class cannot be sourced under licence/budget, mark it BLOCKED with the
concrete blocking reason (link, HTTP status, licence, size) — no substitute
synthetic image, no machine-output truth.

## 6. Candidate sources investigated for cohort B (facts, not assumptions)

| Candidate | Real Chinese? | Human truth? | Licence (verified) | File size | Verdict |
|---|---|---|---|---|---|
| **Microsoft XFUND** `doc-analysis/XFUND` release v1.0 | yes (real forms, ZH) | yes (human key/value labels) | **CC BY-NC-SA 4.0 (NonCommercial + ShareAlike)** per the official README §License | `zh.val.json` 1,711,142 B (annotations only); images in `zh.val.zip` **69,217,820 B** | **BLOCKED** — NonCommercial licence not usable for a product fixture, and the image archive exceeds the ≤10 MiB single-file cap |
| **SWHL/ChineseOCRBench** (HF) | images yes, but **VQA short answers** | "approved" short answers, **not full-page transcripts** | card says `apache-2.0`, but content is a re-host of ESTVQA + ReCTS whose own licence is not clearly permissive | 3,410 rows / ≈379 MB total | **NOT SUITABLE** — no full-page human truth ⇒ cannot support page CER |
| `Yuliang-Liu/MultimodalOCR` (source repo) | Chinese eval data referenced | short VQA answers | MIT for the **repo**, but bundled ESTVQA/ReCTS image licence unclear | repo 173 MB | **NOT SUITABLE** (same reason as above) |
| `tesseract-ocr/test` (already used, Apache-2.0) | no real Chinese scan+truth pair found in `testing/` | yes for English pages only | Apache-2.0 | — | no Chinese sample present |

The XFUND NonCommercial finding is the decisive licence fact: a real Chinese
form benchmark with human truth **exists**, but is **not licence-clear** for
this product's fixture, so it cannot be used even though it would otherwise fit
the sample requirement.

## 7. Outcome rule for cohort B

* Run only if §0 holds **and** at least the Chinese real page (with human truth)
  is licence-clear and within the download cap.
* If the endpoint is unreachable (§0 fails) → **no POST**, cohort B records
  `status=blocked_external`, and LG-035 stays `in-progress`.
* Only if **all** classes in §5 are covered and within thresholds → LG-035 may
  move to done-pending-LG-040. Never relax thresholds to pass.
