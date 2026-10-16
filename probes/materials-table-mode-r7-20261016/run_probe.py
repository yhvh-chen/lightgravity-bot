#!/usr/bin/env python3
"""LG-035 R7 table-mode LIVE 2-call probe — NORMAL product pipeline.

Drives the **actual** product path for both calls:

    SourceService.receive_from_path / IntakeService.receive
      -> ProcessingEngine.process (real per-page loop, file SoT, evidence)
        -> OcrBackend.transcribe (real OpenAI-compatible HTTP)

The optional table mode is ON for both calls (passed through
``ProcessingConfig(table_mode=True)``), so the classifier decides per page:
CALL1 (real grid) must select the explicit-grid prompt; CALL2 (ordinary Z1)
must keep the unchanged default prompt.  A thin recording wrapper captures the
*actual* request (prompt/max_tokens/input hash) without altering it.

Serial, retry 0, 120 s/call.  A persistent reservation is written BEFORE each
forward and the raw (redacted) response BEFORE scoring.  A timeout stops the
remaining call (NOTEXECUTED) and is never replayed.  Ground truth is NEVER placed
in a prompt.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.sources.content import ContentStore  # noqa: E402
from lightgravity.sources.intake import IntakeService, ReceiveRequest  # noqa: E402
from lightgravity.sources.ocr import (  # noqa: E402
    OCR_PROMPT,
    OcrRequest,
    OpenAICompatOcrBackend,
)
from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine  # noqa: E402
from lightgravity.sources.store import SourceStore  # noqa: E402

BASE_URL = "http://192.168.8.12:11434"
MODEL = "qwen3.8-27b"
TOTAL_TIMEOUT = 120.0
MAX_OUTPUT = 4096
DATA_ROOT = HERE / "private" / "data"
EVID = HERE / "evidence"
RAW = EVID / "raw"
LEDGER = EVID / "live_ledger.jsonl"

FIX = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016"
    "/probes/materials-fixtures-r7-20261016"
)
Z1 = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-retry-20261016-r2"
    "/probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg"
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ledger_add(entry: dict) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def redact(raw: str) -> str:
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        return raw[:4000]
    return json.dumps(obj, ensure_ascii=False)[:20000]


def health() -> dict:
    t0 = time.time()
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=8) as resp:  # noqa: S310
            body = resp.read(500).decode("utf-8", "replace")
        return {"ok": True, "status": resp.status, "latency": round(time.time() - t0, 3), "body": body[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:200], "latency": round(time.time() - t0, 3)}


class RecordingBackend:
    """Delegate to the real HTTP backend and record the exact request sent."""

    def __init__(self, inner: OpenAICompatOcrBackend) -> None:
        self._inner = inner
        self.requests: list[dict] = []

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def transcribe(self, request: OcrRequest):  # noqa: ANN201
        self.requests.append(
            {
                "input_sha256": sha(request.data),
                "input_bytes": len(request.data),
                "media_type": request.media_type,
                "page": request.page,
                "max_tokens": request.max_tokens,
                "prompt_override": request.prompt,
                "prompt_sha256": sha((request.prompt or OCR_PROMPT).encode("utf-8")),
                "default_prompt_sha256": sha(OCR_PROMPT.encode("utf-8")),
            }
        )
        return self._inner.transcribe(request)


def build_case(call: int):
    if call == 1:
        data = (FIX / "fixtures/honest_table_grid_scale4.png").read_bytes()
        return {
            "call": 1, "sample": "LG035-R7-T1", "filename": "honest_table_grid_scale4.png",
            "data": data, "media_type": "image/png",
            "origin": "NIST SP 811 p.16 Table 1 grid crop pts(90,517,524.6,627.5) scale4; "
                      "sourcePDF sha256 788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f",
        }
    data = Z1.read_bytes()
    return {
        "call": 2, "sample": "LG035-ZH-Z1", "filename": "lg035_truth_zh_laojielao_p10.jpg",
        "data": data, "media_type": "image/jpeg",
        "origin": "Wikimedia Commons File:10-13老解老.pdf p.10 (Public domain); "
                  "human truth truth/LG035-ZH-Z1.p10.txt sha256 9043c2b7…",
    }


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    store = SourceStore(DATA_ROOT)
    intake = IntakeService(store)
    results = []

    hc = health()
    ledger_add({"kind": "health", **hc})
    (EVID / "health.json").write_text(json.dumps(hc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("health:", json.dumps(hc, ensure_ascii=False)[:160])

    stopped = False
    for call in (1, 2):
        case = build_case(call)
        if stopped:
            ledger_add({"kind": "not_executed", "call": call, "sample": case["sample"]})
            results.append({"call": call, "sample": case["sample"], "status": "NOTEXECUTED"})
            continue

        data = case["data"]
        in_sha = sha(data)
        ledger_add({
            "kind": "reservation", "call": call, "sample": case["sample"],
            "endpoint": f"{BASE_URL}/v1/chat/completions", "model": MODEL,
            "input_sha256": in_sha, "input_bytes": len(data), "media_type": case["media_type"],
            "pipeline": "SourceService/IntakeService -> ProcessingEngine.process -> OcrBackend.transcribe",
            "table_mode": True, "max_tokens": MAX_OUTPUT, "timeout_seconds": TOTAL_TIMEOUT,
        })

        result = intake.receive(ReceiveRequest(
            request_id=f"req-table-mode-{call}", filename=case["filename"], data=data,
            media_type=case["media_type"],
        ))
        source_id = result.source.source_id

        inner = OpenAICompatOcrBackend(
            base_url=BASE_URL, model=MODEL,
            default_timeout_seconds=TOTAL_TIMEOUT, cold_timeout_seconds=TOTAL_TIMEOUT,
            max_tokens=MAX_OUTPUT,
        )
        recording = RecordingBackend(inner)
        engine = ProcessingEngine(
            store, backend=recording, intake=intake,
            config=ProcessingConfig(table_mode=True, max_tokens_per_page=MAX_OUTPUT),
        )
        rec = {"call": call, "sample": case["sample"], "origin": case["origin"],
               "input_sha256": in_sha, "input_bytes": len(data), "media_type": case["media_type"],
               "source_id": source_id, "endpoint": inner.endpoint, "model": MODEL,
               "pipeline": "ProcessingEngine.process"}
        t0 = time.time()
        try:
            outcome = engine.process(source_id)
            rec.update({"status": "ok", "processing_status": outcome.status,
                        "latency_seconds": round(time.time() - t0, 3),
                        "succeeded_pages": outcome.succeeded_pages, "total_pages": outcome.total_pages})
            rec["requests"] = recording.requests
            # Persist the machine derivative BEFORE scoring.
            content = ContentStore(source_root=store.source_dir(source_id))
            text = content.read_machine_markdown(1) or ""
            text_path = RAW / f"call{call}_{case['sample']}_machine.md"
            text_path.write_text(text, encoding="utf-8")
            try:
                rec["machine_path"] = str(text_path.relative_to(HERE))
            except ValueError:
                rec["machine_path"] = str(text_path)
            rec["machine_sha256"] = sha(text.encode("utf-8"))
            ev = content.read_evidence()
            rec["evidence"] = ev
            raw_path = RAW / f"call{call}_{case['sample']}_evidence.json"
            raw_path.write_text(json.dumps({"requests": recording.requests, "evidence": ev,
                                            "processing_status": outcome.status}, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            try:
                rec["raw_path"] = str(raw_path.relative_to(HERE))
            except ValueError:
                rec["raw_path"] = str(raw_path)
        except Exception as exc:  # noqa: BLE001 - honest capture, no replay
            rec.update({"status": "error", "error_type": type(exc).__name__, "error": str(exc),
                        "latency_seconds": round(time.time() - t0, 3),
                        "outcome": "unknown" if "timeout" in type(exc).__name__.lower() else "failed"})
            if "timeout" in type(exc).__name__.lower():
                stopped = True
        ledger_add({"kind": "result", "call": call, **rec})
        print("call", call, rec.get("status"), rec.get("processing_status"), rec.get("latency_seconds"))
        results.append(rec)

    (EVID / "call_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    executed = sum(1 for r in results if r.get("status") == "ok")
    print(f"executed={executed}/2 stopped={stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
