#!/usr/bin/env python3
"""materials-ocr-r4 — OCR POST: Z2 PDF page 2 at scale 4.0 (bounded phase).

Uses the UNMODIFIED product `PdfiumRasterizer` + `OpenAICompatOcrBackend`, and
drives the *explicit* scale through the product `ProcessingConfig`/env path so
the retest also exercises the new configuration surface. Exactly ONE inference
POST (serial, retry 0, timeout 120 s). No truth in the prompt.

Writes only under probes/materials-ocr-r4-20261016/evidence/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(ROOT, "evidence")
PRIV = os.path.join(ROOT, "private")

sys.path.insert(0, os.path.join(ROOT, "backend"))

from lightgravity.sources.ocr.adapter import OcrRequest, OpenAICompatOcrBackend  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402
from lightgravity.sources.processing import ProcessingConfig  # noqa: E402

BASE_URL = "http://192.168.8.12:11434"
MODEL = "qwen3.8-27b"
PDF = os.path.join(PRIV, "LG035-ZH-Z2.pdf")
PDF_SHA = "da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a"
SCALE = 4.0
HEALTH = os.path.join(EVID, "health.json")


def health_check() -> dict:
    url = f"{BASE_URL}/health"
    started = time.time()
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310 - fixed authorized host
            body = resp.read(2000).decode("utf-8", "replace")
        return {"ok": True, "status": resp.status, "latency": round(time.time() - started, 3),
                "body": body[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:300],
                "latency": round(time.time() - started, 3)}


def main() -> int:
    # Respect the new optional env path: if LIGHTGRAVITY_OCR_SCALE is set it must
    # be valid; here we drive the value explicitly for the retest.
    cfg = ProcessingConfig.from_env(env={"LIGHTGRAVITY_OCR_SCALE": str(SCALE)})
    assert cfg.scale == SCALE, cfg.scale

    with open(PDF, "rb") as fh:
        pdf_bytes = fh.read()
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    if pdf_sha != PDF_SHA:
        print("PDF sha mismatch:", pdf_sha)
        return 2

    hc = health_check()
    with open(HEALTH, "w") as fh:
        json.dump(hc, fh, ensure_ascii=False, indent=2)
    print("health:", json.dumps(hc, ensure_ascii=False)[:200])

    raster = PdfiumRasterizer()
    pages = raster.render(pdf_bytes, scale=cfg.scale, max_pages=2)
    page2 = [p for p in pages if p.page == 2][0]
    png = page2.png
    if len(png) > 2 * 1024 * 1024:
        print("input over 2 MiB, aborting (no POST):", len(png))
        return 3
    png_sha = hashlib.sha256(png).hexdigest()
    print(f"raster page2 scale={cfg.scale} bytes={len(png)} grid={page2.width}x{page2.height} sha256={png_sha}")

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
    except Exception as exc:  # noqa: BLE001 - record honestly, NO retry
        elapsed = time.time() - started
        out = {
            "post": 1,
            "kind": "ocr_z2_page2_scale4",
            "endpoint": backend.endpoint,
            "model": MODEL,
            "scale": cfg.scale,
            "page": 2,
            "input_sha256": png_sha,
            "input_bytes": len(png),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "latency_seconds": round(elapsed, 3),
            "outcome": "unknown" if "timeout" in type(exc).__name__.lower() else "failed",
        }
        with open(os.path.join(EVID, "ocr_post1_scale4.json"), "w") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print("OCR FAILED:", json.dumps(out, ensure_ascii=False))
        return 1

    out = {
        "post": 1,
        "kind": "ocr_z2_page2_scale4",
        "endpoint": backend.endpoint,
        "model": result.model,
        "scale": cfg.scale,
        "page": result.page,
        "input_sha256": result.input_sha256,
        "input_bytes": result.input_bytes,
        "latency_seconds": round(result.latency_seconds, 3),
        "finish_reason": result.finish_reason,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "text": result.text,
    }
    with open(os.path.join(EVID, "ocr_post1_scale4.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("OCR OK latency=%.2fs finish=%s prompt=%s completion=%s" % (
        out["latency_seconds"], out["finish_reason"], out["prompt_tokens"], out["completion_tokens"]))
    print("---- text ----")
    print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
