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

## Honest limits

* `stat_revision` on download is a size-mtime token, **not** a crypto hash.
* The `formal/FORMAL.md` endpoint seeds from the current machine derivative
  only when one exists; with no configured backend it honestly 404s.
* `delete` removes the whole source directory after explicit confirmation;
  `revoke` only marks `archived` and keeps the original.
* Unknown token/price cost: the router reports no price → **unknown**.
* Only PDF + PNG/JPEG/WebP/GIF/BMP are handled; TIFF is out of scope.
