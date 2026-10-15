#!/usr/bin/env python3
"""materials-ocr-r5 — bounded product-path OCR POST driver.

Renders the frozen Z2 page 2 through the **real product** `PdfiumRasterizer`
(scale from `LIGHTGRAVITY_OCR_SCALE`, composed through `ProcessingConfig.from_env`)
and OCRs it through the **real product** `OpenAICompatOcrBackend` with the new
generic layout-aware instruction.

Persistence-before-POST: writes a reservation line to ``evidence/reservations.jsonl``
**before** the HTTP call, then stores the raw (redacted) result.  No retry, no
adaptive extra call; timeout is recorded as unknown and never replayed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
EVID = ROOT / "evidence"

sys.path.insert(0, str(Path(os.environ["LG_BACKEND"])))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reserve(record: dict) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    with open(EVID / "reservations.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", type=int, required=True, choices=[1, 2])
    ap.add_argument("--kind", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", default="4.0")
    ap.add_argument("--page", type=int, default=None)
    ap.add_argument("--image", default=None, help="image file (Z1 regression)")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--endpoint", default="http://192.168.8.12:11434")
    ap.add_argument("--model", default="qwen3.8-27b")
    args = ap.parse_args()

    from lightgravity.sources.ocr import (
        OCR_PROMPT,
        OpenAICompatOcrBackend,
        OcrRequest,
        OcrServiceError,
        OcrTimeout,
        PdfiumRasterizer,
    )
    from lightgravity.sources.processing import ProcessingConfig as PC

    env = {"LIGHTGRAVITY_OCR_SCALE": args.scale}
    cfg = PC.from_env(env=env)
    assert cfg.scale == float(args.scale), cfg

    if args.image:
        data = Path(args.image).read_bytes()
        media = "image/jpeg" if args.image.lower().endswith((".jpg", ".jpeg")) else "image/png"
        page = None
    else:
        pdf = (PRIVATE / "LG035-ZH-Z2.pdf").read_bytes()
        raster = PdfiumRasterizer()
        pages = raster.render(pdf, scale=cfg.scale, max_pages=2)
        chosen = [p for p in pages if p.page == args.page]
        if not chosen:
            raise SystemExit(f"page {args.page} not rendered; got {[p.page for p in pages]}")
        data = chosen[0].png
        media = "image/png"
        page = args.page

    input_sha = hashlib.sha256(data).hexdigest()
    reservation = {
        "plan": "materials-ocr-r5-20261016",
        "call": args.call,
        "kind": args.kind,
        "endpoint": args.endpoint,
        "model": args.model,
        "scale": float(args.scale) if not args.image else None,
        "page": page,
        "input_sha256": input_sha,
        "input_bytes": len(data),
        "max_tokens": args.max_tokens,
        "timeout_seconds": args.timeout,
        "temperature": 0,
        "stream": False,
        "instruction_sha256": hashlib.sha256(OCR_PROMPT.encode("utf-8")).hexdigest(),
        "instruction_name": "lg035-generic-layout-ocr-v2",
        "thresholds": {"z1_printed_page_cer": 0.15, "z2_segment_cer": 0.25},
        "reserved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    reserve(reservation)

    backend = OpenAICompatOcrBackend(
        base_url=args.endpoint,
        model=args.model,
        max_tokens=args.max_tokens,
    )
    started = time.monotonic()
    try:
        result = backend.transcribe(
            OcrRequest(data=data, media_type=media, page=page,
                       max_tokens=args.max_tokens, timeout_seconds=args.timeout, cold=True)
        )
    except OcrTimeout as exc:
        payload = {"call": args.call, "kind": args.kind, "outcome": "timeout",
                   "detail": exc.details, "input_sha256": input_sha,
                   "input_bytes": len(data), "latency_seconds": round(time.monotonic() - started, 3)}
        (EVID / args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    except OcrServiceError as exc:
        payload = {"call": args.call, "kind": args.kind, "outcome": "service_error",
                   "detail": exc.details, "input_sha256": input_sha,
                   "input_bytes": len(data), "latency_seconds": round(time.monotonic() - started, 3)}
        (EVID / args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 3

    payload = {
        "call": args.call,
        "kind": args.kind,
        "endpoint": f"{args.endpoint}/v1/chat/completions",
        "model": result.model,
        "scale": float(args.scale) if not args.image else None,
        "page": result.page,
        "input_sha256": result.input_sha256,
        "input_bytes": result.input_bytes,
        "latency_seconds": round(result.latency_seconds, 3),
        "finish_reason": result.finish_reason,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "text": result.text,
    }
    (EVID / args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in
                      ("call", "kind", "input_sha256", "input_bytes", "latency_seconds",
                       "finish_reason", "completion_tokens")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
