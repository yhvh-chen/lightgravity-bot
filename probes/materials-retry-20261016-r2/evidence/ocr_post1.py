"""LG-035 / materials-retry-r2 OCR smoke — POST #1.

Uses the PRODUCT OpenAICompatOcrBackend unchanged (no patch). Bounded:
concurrency 1, retries 0, one request, cold bound fixed at 120 s.
No ground truth is placed in the prompt.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from lightgravity.sources.ocr.adapter import (  # noqa: E402
    OpenAICompatOcrBackend,
    OcrRequest,
    OcrServiceError,
    OcrTimeout,
)

HERE = Path(__file__).resolve().parent
IMG = HERE.parents[1] / "lg035" / "TRUTH-PREP" / "samples" / "private" / "lg035_truth_zh_laojielao_p10.jpg"
BASE = "http://192.168.8.12:11434"
MODEL = "qwen3.8-27b"

data = IMG.read_bytes()
sha = hashlib.sha256(data).hexdigest()
print(f"fixture: {IMG} bytes={len(data)} sha256={sha}")
assert sha == "5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f", "fixture sha mismatch"

backend = OpenAICompatOcrBackend(
    base_url=BASE,
    model=MODEL,
    default_timeout_seconds=90.0,
    cold_timeout_seconds=120.0,  # frozen cold bound for this package
    max_tokens=2048,
)
req = OcrRequest(data=data, media_type="image/jpeg", page=10, max_tokens=2048, cold=True)
t0 = time.monotonic()
try:
    res = backend.transcribe(req)
except (OcrTimeout, OcrServiceError) as exc:
    print(json.dumps({"post": 1, "outcome": "error", "type": type(exc).__name__,
                      "detail": str(exc), "elapsed_s": time.monotonic() - t0}, ensure_ascii=False))
    sys.exit(2)

out = {
    "post": 1,
    "endpoint": backend.endpoint,
    "model": res.model,
    "page": res.page,
    "input_sha256": res.input_sha256,
    "input_bytes": res.input_bytes,
    "latency_seconds": round(res.latency_seconds, 3),
    "finish_reason": res.finish_reason,
    "prompt_tokens": res.prompt_tokens,
    "completion_tokens": res.completion_tokens,
    "text": res.text,
}
(HERE / "ocr_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in out.items() if k != "text"}, ensure_ascii=False))
print("--- extracted text ---")
print(res.text)
