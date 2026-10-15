# LG-035 STATUS — image/PDF OCR to traceable Markdown

* Branch: `dev/lg035` (persistent worktree). Base before work: `61fad69`.
* Task file: `backlog/tasks/LG-035.md`.
* Status: **in-progress** (not done). Product quality gate is **partially
  blocked** — see below. Independent QA belongs to LG-040.
* Product real worker calls: **0**. OCR is an intake job, not a delivery Run.
* Pushed/deployed/released: **no**.

## What was delivered

| Area | File(s) |
|---|---|
| OCR backend (real HTTP, configurable) | `backend/lightgravity/sources/ocr/adapter.py` |
| PDF rasteriser (pypdfium2, lazy, stdlib PNG) | `backend/lightgravity/sources/ocr/pdf.py` |
| Machine-vs-formal content versions | `backend/lightgravity/sources/content.py` |
| Processing orchestration (partial/cancel/timeout) | `backend/lightgravity/sources/processing.py` |
| Service + wiring | `backend/lightgravity/sources/service.py` |
| API: content/download/actions/formal | `backend/lightgravity/api/sources.py` |
| Tests | `tests/sources/ocr/**` (17 tests) |
| Quality pre-registration + evidence | `probes/lg035/QUALITY-PLAN.md`, `probes/lg035/reports/**` |
| Dependency | `pypdfium2>=5,<6` in `pyproject.toml` + `uv.lock` |

## Local checks actually run (real output)

* `uv run mypy` → **Success: no issues found in 122 source files**.
* `uv run pytest tests/sources/ocr -q` → **17 passed**.
* `uv run pytest tests/sources tests/api tests/contracts -q` → **108 passed**.
* `uv run pytest -q` (full) → **585 passed, 4 skipped**.
* Real OCR over HTTP against the authorized candidate: **4 inference POSTs**
  (within the ≤10 budget), **0 automatic retries**, concurrency 1.

## Real OCR quality (product code, product Python 3.12 env)

Pre-registered thresholds in `QUALITY-PLAN.md`; **not changed after the run**.

| Sample | Class | CER | Threshold | Result |
|---|---|---|---|---|
| `phototest` real scan → PDF → render → OCR | real clear page | **0.0000** | ≤0.05 | ✅ pass |
| 2-page real PDF page 1 | multi-page | **0.0000** | ≤0.05 | ✅ pass |
| 2-page real PDF page 2 (dense prose) | multi-page | **0.0763** | ≤0.15 | ✅ pass |
| rotated real page | low quality | — | not scored | recorded (not a pass claim) |

Samples: real scans from `tesseract-ocr/test` (**Apache-2.0**, verified via
GitHub license API). Fixture sha256 and gold sha256 are in
`probes/lg035/reports/quality_summary.json`; redacted raw responses in
`probes/lg035/reports/raw_responses/`; request log in
`probes/lg035/reports/http_log.jsonl`.

## Quality-gate blockers (why not done)

* **Real Chinese page with human ground truth: BLOCKED.** No license-clear
  Chinese scan + human truth was obtainable inside the download/time budget
  (Wikimedia blocked, Archive.org restricted, HuggingFace 401). Chinese OCR
  quality is therefore **unverified**; the earlier synthetic 2-image CER 0
  evidence is explicitly **not** reused as product acceptance.
* **Table sample: BLOCKED** — no license-clear table page with human truth.
* **Mixed born-digital text + scan in one file: BLOCKED** under license.
* Embedding is not OCR; vector service availability was not used to claim OCR.

## Cohort B (2026-10-16) — public-sample + quality completion attempt

Additive follow-up; **cohort A scores/thresholds are unchanged**. Pre-registered
in [`QUALITY-PLAN-COHORT-B.md`](QUALITY-PLAN-COHORT-B.md) before any inference.

* **Decisive blocker: the authorized endpoint is unreachable.**
  `http://192.168.8.12:11434` → `connect failed: No route to host` (curl HTTP
  000; ICMP 100% loss), verified 2×. So **0** new OCR POSTs were made and **no**
  quality metric is claimed for cohort B. Evidence:
  [`reports/cohort_b/endpoint_reachability.txt`](reports/cohort_b/endpoint_reachability.txt).
* **Inference-POST accounting (from raw logs, not reports):** cohort A log has
  **4** `POST /v1/chat/completions` → **LG-035 cumulative 4 / 10** (≤6 remain,
  cohort B declares ≤5). Cohort B used **0**.
* **Licence findings (verified, links in report):**
  [`reports/cohort_b/source_provenance_checks.md`](reports/cohort_b/source_provenance_checks.md)
  * Microsoft **XFUND** is a real Chinese form benchmark **with human truth**,
    but its official README licenses it **CC BY-NC-SA 4.0 (NonCommercial)** and
    its image archive `zh.val.zip` is **69,217,820 B** (>10 MiB cap) → not
    licence-clear for a product fixture.
  * **SWHL/ChineseOCRBench** (HF, card `apache-2.0`) is **short-answer VQA
    only** (no full-page human transcript) → cannot support page CER; upstream
    ESTVQA/ReCTS image licence unclear.
  * `tesseract-ocr/test` (Apache-2.0) has **no real Chinese scan + truth pair**.
* **Download budget spent on samples: 0 bytes** (nothing eligible).
* **No product code changed** in this package; no new fixture beyond the
  cohort-B evidence/report files. Status stays **in-progress**.

## Honest limits

* `stat_revision` on download is a size-mtime token, **not** a crypto hash.
* The `formal/FORMAL.md` endpoint seeds from the current machine derivative
  only when one exists; with no configured backend it honestly 404s.
* `delete` removes the whole source directory after explicit confirmation;
  `revoke` only marks `archived` and keeps the original.
* Unknown token/price cost: the router reports no price → **unknown**.
* Only PDF + PNG/JPEG/WebP/GIF/BMP are handled; TIFF is out of scope.
