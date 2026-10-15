#!/usr/bin/env python3
"""Materials Quality R3 — POST #1: OCR of real Z2 PDF page 2.

Uses the UNMODIFIED product `PdfiumRasterizer` + `OpenAICompatOcrBackend`.
Exactly ONE inference POST. No truth in the prompt. Timeout 120s, retry 0.

Writes only under probes/materials-quality-20261016-r3/evidence/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(ROOT, "evidence")
PRIV = os.path.join(ROOT, "private")

sys.path.insert(0, os.path.join(ROOT, "backend"))

from lightgravity.sources.ocr.adapter import OcrRequest, OpenAICompatOcrBackend  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402

BASE_URL = "http://192.168.8.12:11434"
MODEL = "qwen3.8-27b"
PDF = os.path.join(PRIV, "LG035-ZH-Z2.pdf")


def main() -> int:
    with open(PDF, "rb") as fh:
        pdf_bytes = fh.read()
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    if pdf_sha != "da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a":
        print("PDF sha mismatch:", pdf_sha)
        return 2

    raster = PdfiumRasterizer()
    pages = raster.render(pdf_bytes, scale=2.0, max_pages=2)  # page 1 + page 2 only
    page2 = [p for p in pages if p.page == 2][0]
    png = page2.png
    png_sha = hashlib.sha256(png).hexdigest()
    print(f"raster page2 bytes={len(png)} grid={page2.width}x{page2.height} sha256={png_sha}")

    backend = OpenAICompatOcrBackend(
        base_url=BASE_URL,
        model=MODEL,
        default_timeout_seconds=120.0,
        cold_timeout_seconds=120.0,
        max_tokens=2000,
    )
    req = OcrRequest(data=png, media_type="image/png", page=2, max_tokens=2000, cold=True)
    started = time.time()
    try:
        result = backend.transcribe(req)
    except Exception as exc:  # noqa: BLE001 - record honestly
        elapsed = time.time() - started
        out = {
            "post": 1,
            "kind": "ocr_z2_page2",
            "endpoint": backend.endpoint,
            "model": MODEL,
            "page": 2,
            "input_sha256": png_sha,
            "input_bytes": len(png),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "latency_seconds": round(elapsed, 3),
            "outcome": "unknown" if "timeout" in type(exc).__name__.lower() else "failed",
        }
        with open(os.path.join(EVID, "ocr_post1.json"), "w") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print("OCR FAILED:", json.dumps(out, ensure_ascii=False))
        return 1

    elapsed = time.time() - started
    out = {
        "post": 1,
        "kind": "ocr_z2_page2",
        "endpoint": backend.endpoint,
        "model": result.model,
        "page": result.page,
        "input_sha256": result.input_sha256,
        "input_bytes": result.input_bytes,
        "latency_seconds": round(result.latency_seconds, 3),
        "finish_reason": result.finish_reason,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "text": result.text,
    }
    with open(os.path.join(EVID, "ocr_post1.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("OCR OK latency=%.2fs finish=%s prompt=%s completion=%s" % (
        out["latency_seconds"], out["finish_reason"], out["prompt_tokens"], out["completion_tokens"]))
    print("---- text ----")
    print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
