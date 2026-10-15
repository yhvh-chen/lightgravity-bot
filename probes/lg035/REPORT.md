# LG-035 REPORT — image/PDF OCR to traceable Markdown

* Executor: `agent:pi-lg035` (persistent worktree `dev/lg035`).
* Base point before work: `61fad69` (main after batch-2 integration).
* Task: `backlog/tasks/LG-035.md`. Status: **in-progress** (see blockers).
* Date (UTC): 2026-10-15.

## 1. Outcome summary

The product now turns an image or a PDF into a **traceable machine Markdown
derivative**, with machine output and human formal content in **separate files**,
per-page back-references, honest partial-failure/cancel/timeout handling, and a
configurable OCR endpoint that is **not** hard-coded to the LAN.

Real Chinese OCR quality remains **unverified** because no license-clear Chinese
page with human ground truth was obtainable in budget; the task therefore stays
`in-progress` with an explicit quality-gate blocker rather than claiming a pass.

## 2. Real OCR quality against the authorized candidate

* Target: `http://192.168.8.12:11434`. Live `/props` (200) confirms a
  **llama.cpp `llama-server` router** (`build_info=b11641-843e7dcc1`,
  `role=router`), **not Ollama**.
* Live `/v1/models` (200): `bge-reranker-v2-m3-Q8_0`, `embeddinggemma-2-Q8_0`,
  `gemma4-mtp`, `qwen3.8-27b`. OCR model used: `qwen3.8-27b`.
* Protocol: OpenAI-compatible `POST /v1/chat/completions`, typed `image_url`
  data URL, `temperature=0`, `stream=false`, `max_tokens=2000`.

### 2.1 Scores (pre-registered thresholds in `QUALITY-PLAN.md`, unchanged)

| Sample | Class | CER | Threshold | Result |
|---|---|---|---|---|
| real clear scan → PDF → render | real clear | 0.0000 | ≤0.05 | pass |
| 2-page real PDF, page 1 | multi-page | 0.0000 | ≤0.05 | pass |
| 2-page real PDF, page 2 | multi-page | 0.0763 | ≤0.15 | pass |
| rotated real page | low quality | not scored | — | recorded |

Fixtures are **real scans** from `tesseract-ocr/test` (**Apache-2.0**),
downloaded ≈1.9 MiB total (largest 1.61 MiB).  Gold text is the repository's own
human transcription.  sha256 for every fixture and gold file is in
`reports/quality_summary.json`.  The multi-page PDF was assembled locally from
two real scan pages (`tiff2pdf` at probe time, not a product dependency).

### 2.2 Request/response evidence (redacted)

Per-page HTTP log: `reports/http_log.jsonl`.  Redacted raw responses:
`reports/raw_responses/*.json` (image data and credential-like keys removed).

Example request shape (image data elided; the real request carries a
`data:image/png;base64,...` URL — never logged):

```json
{
  "model": "qwen3.8-27b",
  "temperature": 0,
  "stream": false,
  "max_tokens": 2000,
  "messages": [{"role": "user", "content": [
    {"type": "text", "text": "You are a precise OCR engine. Transcribe only the text that is visibly present ... Return only the transcription."},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,[redacted]"}}
  ]}]
}
```

Example redacted response (`reports/raw_responses/page_1_1aebdc639db9.json`):

```json
{"choices": [{"finish_reason": "stop", "index": 0, "message": {
  "role": "assistant",
  "content": "This is a lot of 12 point text to test the\nocr code and see if it works on all types\nof file format.\n...",
  "reasoning_content": "The user wants a direct transcription of the text in the image. ..."
}}]}
```

### 2.3 Failure / statistics accounting

| Metric | Value |
|---|---|
| read-only `health`/`props`/`models` requests | 3 (≤4) |
| inference POSTs (incl. failures) | 4 (≤10) |
| failed inference requests | 0 |
| automatic retries | 0 |
| concurrency | 1 |
| prompt tokens (sum) | 2996 |
| completion tokens (sum) | 1360 (≤16000) |
| first cold-load latency | 13.35 s (<180 s) |
| slowest page | 40.71 s (<90 s) |

Every failed request is counted in the log; there were none this run.  Since a
timeout is an unknown outcome, the adapter reports `capability_unavailable`
with `outcome=unknown` and the engine records it as a failed page without a
replay — verified by `tests/sources/ocr/test_adapter.py::test_adapter_timeout_is_unknown_not_replayed`.

## 3. Dependency lock and resource budget

* Added: `pypdfium2==5.14.0` (resolved in `uv.lock`).
* License proven permissive: **BSD-3-Clause + Apache-2.0** plus permissive
  bundled dependency licenses (abseil, freetype, libjpeg-turbo, libpng, icu,
  lcms, openjpeg, agg23, …).  No GPL/AGPL.  Self-contained wheel → no `poppler`
  system dependency at product runtime.
* **No Pillow**: PNG encoding uses stdlib `zlib`/`struct`.
* Product Python env: 3.12 (`uv run`, `.python-version=3.12`).
* Unknown cost: the router exposes no price → **unknown**.

## 4. Where the guarantees live

| Guarantee | Implementation | Test |
|---|---|---|
| original persisted before extraction | `intake.receive` (LG-034) + `processing._read_original` | `test_unavailable_backend_keeps_original...` |
| machine ≠ human formal | `content.py` (separate dirs) | `test_reprocess_does_not_overwrite_formal...` |
| reprocess never overwrites formal | `edit_formal` refuses overwrite; `write_machine` only touches `derivative/` | same |
| page + original back-reference | `rendered page` → `page=<n>` + `input_sha256` | `test_machine_markdown_has_page_backref...` |
| partial failure is honest | `_finalize` → `partial`; failed page has no body | `test_partial_failure_is_honest...` |
| cancel keeps completed pages | `cancel_check` between pages | `test_cancel_after_confirmed_stop...` |
| timeout not replayed | one attempt; `outcome=unknown` | `test_timeout_is_recorded_and_never_auto_replayed` |
| authz / no path escape | reuses LG-034 `resolve_path` | LG-034 tests |
| service unavailable keeps original | `UnavailableOcrBackend` | `test_unavailable_backend_keeps_original...` |

## 5. Commands run (real output)

```
uv run mypy                      -> Success: no issues found in 122 source files
uv run pytest tests/sources/ocr  -> 17 passed
uv run pytest tests/sources tests/api tests/contracts -q -> 108 passed
uv run pytest -q                 -> 585 passed, 4 skipped
```

## 6. Unmet / remaining gates

1. **Real Chinese sample with human truth** — BLOCKED (no license-clear source
   in budget). Chinese OCR quality unverified.
2. **Table sample** — BLOCKED.
3. **Mixed born-digital text + scan** — BLOCKED under license.
4. **docs/08 §4.3 status rows** — not updated here (single docs08 owner).
5. Independent QA — LG-040.
