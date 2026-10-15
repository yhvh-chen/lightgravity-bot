# LG-035 TRUTH-PREP — PLAN / STATUS (independent prep worktree)

* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep`
* Branch: `prep/lg035-real-truth` (base `main@5df1956`)
* Owner scope: `probes/lg035/TRUTH-PREP/**` + LG-035 record addendum.
  **Does NOT touch** main/task docs08/source, frontend, coordinator, store, contracts,
  shared docs, `PROJECT.md`, `api/app.py`, `pyproject.toml`, `uv.lock`.
* Product real worker calls: **0**. No POST / no inference / no new model service /
  no OCR / no embedding / no ASR. No push / deploy / publish.
* LG-035 task status stays **in-progress**. This package never reports `qualitypass`
  and never unlocks LG-040/LG-041.

## Goal (bounded, single-purpose)

Independently prepare **real** Chinese evaluated truth material — real scanned /
image / table mixed pages with **human** ground truth — so that a later,
separately-authorized run can measure Chinese OCR quality **without** fabricating
samples. This is data preparation only: no model is called here.

Hard rules obeyed by this package:

* Prefer **already-existing real** Chinese scan/image/table-mixed originals with
  human ground truth + public provenance.
* If absent, pick at most **2–3 tiny samples** from **official primary sources**
  with an **explicit permissive licence** (PD / CC0 / CC-BY) that permits this
  evaluation use; strict pairing: original scan ↔ human transcription
  (e.g. public-domain scan + Wikisource human `Page:` transcript).
* **Never**: AI-generated text images, synthetic scans, embedding output as OCR
  truth, or machine output as truth.
* If scan+truth cannot be **strictly paired** or the licence is unclear →
  **exclude** and report the exact gap; do not fabricate to pad the count.
* NC is neither blanket-forbidden nor auto-allowed: pick only **explicitly
  applicable** authorisation; if only NC is found, record it as a decision point.
* Originals stay **private (0700/0600)**, never packaged for publication; the repo
  may carry only a reviewable, de-identified manifest/provenance/GT (or, if
  licence forbids, the private path hash).

## Network budget (hard, declared before first GET)

| Item | Bound |
|---|---|
| read-only GET | **≤ 12 total** |
| total downloaded bytes | **≤ 20 MiB** |
| connect timeout | 5 s |
| total request time | ≤ 15 s each |
| retries | **0** |
| provider switching / login / signup / paid / email / external write | **none** |

## Phase plan

1. **Round 1–3**: inventory already-present raw/provenance/quality-gate evidence
   (cohort A, cohort B, LG-034 source-intake) — no network.
2. **Round 4–8**: bounded read-only GETs against official primary sources to find
   a real Chinese scan ↔ human transcription pair with permissive licence.
3. **Round 9+**: write local, no-model scoring protocol (char normalisation / CER,
   table structure / field truth). **No OCR/embedding/ASR execution.**
4. Local commit at the end; report actual GETs and bytes.

## Status

**Round 1 (inventory) — done.** Findings:

| Evidence set | Real Chinese? | Human truth? | Reusable as product truth? |
|---|---|---|---|
| Cohort A (`tesseract-ocr/test`) | no (English) | yes | yes, but English only |
| LG-034 source-intake fixtures | images are **Pillow-rendered synthetic**, audio is **espeak-ng synthetic** | frozen text written by the probe author | **NO** — synthetic, explicitly not product acceptance |
| Cohort B | — | — | blocked: no permissive Chinese scan+truth |
| `probes/lg039/evidence/real_voice_chinese_language-1.ogg` | audio only | — | out of scope (ASR, not OCR) |

**Round 2 (endpoint check) — done.** `http://192.168.8.12:11434` still
unreachable: `curl` → HTTP `000`, exit 7 (`No route to host`). No inference
possible; not needed for this prep package anyway. GET budget used: **1**.

See `REPORT.md` for the live log and the final numbers.
