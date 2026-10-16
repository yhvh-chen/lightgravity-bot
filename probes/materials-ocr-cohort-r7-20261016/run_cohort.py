#!/usr/bin/env python3
"""LG-035 R7 cohort — LIVE 3-call OCR driver (actual product adapter).

Exactly 3 planned POST via the main **actual** `OpenAICompatOcrBackend`. MIX pages
rendered by the **actual** `PdfiumRasterizer`. Serial, retry 0, 120 s per call.
Writes a persistent reservation BEFORE each forward and the raw (redacted) response
BEFORE scoring. A timeout stops further network (remaining = NOTEXECUTED). No replay.

Raw responses are persisted BEFORE this script scores anything.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIX = "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016/probes/materials-fixtures-r7-20261016"
EVID = os.path.join(HERE, "evidence")
RAW = os.path.join(EVID, "raw")
LEDGER = os.path.join(EVID, "live_ledger.jsonl")

BASE_URL = "http://192.168.8.12:11434"
MODEL = "qwen3.8-27b"
TOTAL_TIMEOUT = 120.0
MAX_OUTPUT = 4096

sys.path.insert(0, os.path.join(REPO, "backend"))
from lightgravity.sources.ocr.adapter import (  # noqa: E402
    OCR_PROMPT,
    OcrRequest,
    OpenAICompatOcrBackend,
)
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ledger_add(entry: dict) -> None:
    os.makedirs(EVID, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def redact(raw: str) -> str:
    """Keep the response JSON shape; drop giant base64 echoes if any."""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw[:4000]
    return json.dumps(obj, ensure_ascii=False)[:20000]


def health() -> dict:
    url = f"{BASE_URL}/health"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310 - fixed authorized host
            body = resp.read(500).decode("utf-8", "replace")
        return {"ok": True, "status": resp.status, "latency": round(time.time() - t0, 3),
                "body": body[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:200],
                "latency": round(time.time() - t0, 3)}


def build_inputs() -> list[dict]:
    t1 = open(os.path.join(FIX, "fixtures/honest_table_grid_scale4.png"), "rb").read()
    mix = open(os.path.join(FIX, "fixtures/mixed_born_digital_plus_scan.pdf"), "rb").read()
    pages = PdfiumRasterizer().render(mix, scale=2.0)
    p1 = [p for p in pages if p.page == 1][0]
    p2 = [p for p in pages if p.page == 2][0]
    return [
        {"call": 1, "sample": "LG035-R7-T1", "data": t1, "media_type": "image/png",
         "page": None, "source_sha": None,
         "origin": "fixture honest_table_grid_scale4.png (NIST SP811 p16 table crop, pts(90,517,524.6,627.5) scale4)"},
        {"call": 2, "sample": "LG035-R7-MIX", "data": p1.png, "media_type": "image/png",
         "page": 1, "source_sha": sha(mix),
         "origin": "mixed pdf page1 render scale2 (== NIST p16 scale2)"},
        {"call": 3, "sample": "LG035-R7-MIX", "data": p2.png, "media_type": "image/png",
         "page": 2, "source_sha": sha(mix),
         "origin": "mixed pdf page2 render scale2 (== clear_real.pdf p1 scale2)"},
    ]


def main() -> int:
    os.makedirs(RAW, exist_ok=True)
    inputs = build_inputs()

    hc = health()
    with open(os.path.join(EVID, "health.json"), "w", encoding="utf-8") as fh:
        json.dump(hc, fh, ensure_ascii=False, indent=2)
    print("health:", json.dumps(hc, ensure_ascii=False)[:200])
    ledger_add({"kind": "health", **hc})

    backend = OpenAICompatOcrBackend(
        base_url=BASE_URL, model=MODEL,
        default_timeout_seconds=TOTAL_TIMEOUT, cold_timeout_seconds=TOTAL_TIMEOUT,
        max_tokens=MAX_OUTPUT,
    )
    prompt_sha = sha(OCR_PROMPT.encode("utf-8"))

    results = []
    stopped = False
    for item in inputs:
        call = item["call"]
        if stopped:
            ledger_add({"kind": "not_executed", "call": call, "sample": item["sample"],
                        "reason": "prior timeout stopped network; no replay"})
            results.append({"call": call, "sample": item["sample"], "status": "NOTEXECUTED"})
            continue

        data = item["data"]
        in_sha = sha(data)
        # persistent reservation BEFORE forward
        ledger_add({"kind": "reservation", "call": call, "sample": item["sample"],
                    "endpoint": f"{BASE_URL}/v1/chat/completions", "model": MODEL,
                    "input_sha256": in_sha, "input_bytes": len(data), "page": item["page"],
                    "media_type": item["media_type"], "max_tokens": MAX_OUTPUT,
                    "timeout_seconds": TOTAL_TIMEOUT, "prompt_sha256": prompt_sha})

        req = OcrRequest(data=data, media_type=item["media_type"], page=item["page"],
                         max_tokens=MAX_OUTPUT, timeout_seconds=TOTAL_TIMEOUT, cold=True)
        t0 = time.time()
        rec = {"call": call, "sample": item["sample"], "page": item["page"],
               "origin": item["origin"], "input_sha256": in_sha, "input_bytes": len(data),
               "source_sha256": item["source_sha"], "endpoint": backend.endpoint,
               "model": MODEL, "prompt_sha256": prompt_sha}
        try:
            res = backend.transcribe(req)
            rec.update({"status": "ok", "latency_seconds": round(time.time() - t0, 3),
                        "model_returned": res.model, "prompt_tokens": res.prompt_tokens,
                        "completion_tokens": res.completion_tokens,
                        "finish_reason": res.finish_reason})
            raw_path = os.path.join(RAW, f"call{call}_{item['sample']}_p{item['page']}.json")
            with open(raw_path, "w", encoding="utf-8") as fh:
                fh.write(redact(res.raw_response))
            rec["raw_response_path"] = os.path.relpath(raw_path, HERE)
            rec["machine_text_path"] = os.path.relpath(
                os.path.join(RAW, f"call{call}_{item['sample']}_p{item['page']}_text.txt"), HERE)
            with open(os.path.join(RAW, f"call{call}_{item['sample']}_p{item['page']}_text.txt"),
                      "w", encoding="utf-8") as fh:
                fh.write(res.text)
            rec["machine_text_sha256"] = sha(res.text.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - honest capture, no replay
            rec.update({"status": "error", "error_type": type(exc).__name__,
                        "error": str(exc), "latency_seconds": round(time.time() - t0, 3),
                        "outcome": "unknown" if "timeout" in type(exc).__name__.lower() else "failed"})
            raw_path = os.path.join(RAW, f"call{call}_{item['sample']}_p{item['page']}_error.json")
            with open(raw_path, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=2)
            rec["raw_response_path"] = os.path.relpath(raw_path, HERE)
            if "timeout" in type(exc).__name__.lower():
                stopped = True
        ledger_add({"kind": "raw_response", **rec})
        print("call", call, rec.get("status"), "latency", rec.get("latency_seconds"))
        results.append(rec)

    with open(os.path.join(EVID, "call_results_prelim.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    executed = sum(1 for r in results if r.get("status") in ("ok", "error"))
    print(f"executed={executed}/3 stopped={stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
