"""LG-035 real OCR quality probe (product Python 3.12 env, product code).

Runs the **product** OCR adapter + PDF rasteriser against the authorized
candidate and scores the machine output against human gold text.  Budget and
criteria are pre-registered in ``QUALITY-PLAN.md`` and are not adjusted here.

Usage::

    uv run python probes/lg035/run_quality_probe.py            # full
    uv run python probes/lg035/run_quality_probe.py --dry-run   # no POST

Every HTTP request is logged to ``reports/http_log.jsonl``.  A timeout is never
retried.  The endpoint/model come from the environment
(``LIGHTGRAVITY_OCR_BASE_URL`` / ``LIGHTGRAVITY_OCR_MODEL``).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
REPORTS = HERE / "reports"

from lightgravity.sources.ocr import (  # noqa: E402 - after path setup
    OcrRequest,
    OcrServiceError,
    OcrTimeout,
    OcrUnavailable,
    OpenAICompatOcrBackend,
    PdfiumRasterizer,
)


@dataclass
class HttpLog:
    path: Path
    entries: list[dict[str, object]] = field(default_factory=list)

    def add(self, **entry: object) -> None:
        self.entries.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    return "".join(ch for ch in folded if not ch.isspace())


def _redact_raw(raw: str) -> str:
    """Keep the response shape but drop any image echo/credential-like value."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"unparseable": True, "length": len(raw)}, ensure_ascii=False)

    def scrub(value: object) -> object:
        if isinstance(value, dict):
            return {
                k: ("[redacted]" if k.lower() in {"authorization", "api_key", "token"} else scrub(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str) and value.startswith("data:image"):
            return "[image-data-redacted]"
        return value

    return json.dumps(scrub(payload), ensure_ascii=False, indent=2)


def edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def cer(gold: str, got: str) -> float:
    g = norm(gold)
    if not g:
        return 0.0 if not norm(got) else 1.0
    return edit_distance(g, norm(got)) / len(g)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=4)
    args = parser.parse_args()

    base_url = os.environ.get("LIGHTGRAVITY_OCR_BASE_URL", "")
    model = os.environ.get("LIGHTGRAVITY_OCR_MODEL", "")
    REPORTS.mkdir(parents=True, exist_ok=True)
    log = HttpLog(REPORTS / "http_log.jsonl")

    summary: dict[str, object] = {
        "probe": "lg035-ocr-quality",
        "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url_configured": bool(base_url),
        "model_configured": model or None,
        "dry_run": args.dry_run,
        "samples": [],
        "budget": {"inference_posts": 0, "max_posts": 10},
        "criteria_source": "probes/lg035/QUALITY-PLAN.md",
    }

    if args.dry_run or not base_url or not model:
        summary["note"] = (
            "dry run or backend not configured; no inference performed"
            if not args.dry_run or (not base_url or not model)
            else ""
        )
        (REPORTS / "quality_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    backend = OpenAICompatOcrBackend(base_url=base_url, model=model, max_tokens=2000)
    raster = PdfiumRasterizer()

    posts = 0

    def transcribe(data: bytes, media_type: str, page: int | None, cold: bool) -> tuple[str, dict[str, object]]:
        nonlocal posts
        if posts >= 10:
            raise RuntimeError("inference POST budget (10) exhausted; refusing to exceed")
        posts += 1
        summary["budget"]["inference_posts"] = posts  # type: ignore[index]
        started = time.monotonic()
        req = OcrRequest(data=data, media_type=media_type, page=page, max_tokens=2000, cold=cold)
        try:
            result = backend.transcribe(req)
        except (OcrTimeout, OcrUnavailable, OcrServiceError) as exc:
            log.add(
                page=page, outcome="error", error_type=type(exc).__name__,
                detail=getattr(exc, "details", {}), latency_s=round(time.monotonic() - started, 3),
            )
            raise
        latency = round(time.monotonic() - started, 3)
        raw_path = REPORTS / "raw_responses" / f"page_{page if page is not None else 'image'}_{result.input_sha256[:12]}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(_redact_raw(result.raw_response), encoding="utf-8")
        log.add(
            page=page, outcome="ok", http=200, latency_s=latency,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            input_sha256=result.input_sha256, finish_reason=result.finish_reason,
            raw_response_file=str(raw_path),
        )
        return result.text, {
            "latency_s": latency,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "input_sha256": result.input_sha256,
            "finish_reason": result.finish_reason,
            "raw_response_file": str(raw_path),
        }

    # ---- Sample 1/2: real clear page (PDF from the real scan) -------------
    gold_clear = (FIXTURES / "phototest.gold.txt").read_text("utf-8")
    clear_pdf = (FIXTURES / "clear_real.pdf").read_bytes()
    pages = raster.render(clear_pdf, scale=2.0, max_pages=args.max_pages)
    assert len(pages) == 1, "clear_real.pdf must be one page"
    try:
        text, meta = transcribe(pages[0].png, "image/png", 1, cold=True)
        c = cer(gold_clear, text)
        summary["samples"].append({  # type: ignore[union-attr]
            "id": "clear_real_page",
            "class": "real_clear_page",
            "fixture_pdf_sha256": __import__("hashlib").sha256(clear_pdf).hexdigest(),
            "gold_sha256": __import__("hashlib").sha256(gold_clear.encode()).hexdigest(),
            "gold_chars": len(norm(gold_clear)),
            "cer": c,
            "char_accuracy": 1 - c,
            "threshold_cer": 0.05,
            "pass": c <= 0.05,
            "machine_text": text,
            "meta": meta,
        })
    except (OcrTimeout, OcrUnavailable, OcrServiceError) as exc:
        summary["samples"].append({"id": "clear_real_page", "error": type(exc).__name__})  # type: ignore[union-attr]

    # ---- Sample 3: real multi-page PDF (2 pages, per-page gold) -----------
    gold_multi = [
        (FIXTURES / "phototest.gold.txt").read_text("utf-8"),
        (FIXTURES / "8071_093.3B.txt").read_text("utf-8"),
    ]
    multi_pdf = (FIXTURES / "multipage_real.pdf").read_bytes()
    mpages = raster.render(multi_pdf, scale=2.0, max_pages=args.max_pages)
    multi_record: dict[str, object] = {
        "id": "multipage_real_pdf",
        "class": "real_multipage_pdf",
        "fixture_pdf_sha256": __import__("hashlib").sha256(multi_pdf).hexdigest(),
        "pages": [],
    }
    for index, rpage in enumerate(mpages, 1):
        gold = gold_multi[index - 1]
        try:
            text, meta = transcribe(rpage.png, "image/png", index, cold=False)
            c = cer(gold, text)
            multi_record["pages"].append({  # type: ignore[union-attr]
                "page": index,
                "gold_chars": len(norm(gold)),
                "cer": c,
                "char_accuracy": 1 - c,
                "input_sha256": meta["input_sha256"],
                "page_locator_present": True,
                "machine_text": text,
                "meta": meta,
            })
        except (OcrTimeout, OcrUnavailable, OcrServiceError) as exc:
            multi_record["pages"].append({"page": index, "error": type(exc).__name__})  # type: ignore[union-attr]
    summary["samples"].append(multi_record)  # type: ignore[union-attr]

    # ---- Sample 4: degraded page (recorded, not scored) -------------------
    low_pdf = raster.render((FIXTURES / "clear_real.pdf").read_bytes(), scale=0.8, max_pages=1)
    # Rotated input: use the repository's rotated PNG directly (real fixture).
    rotated = (FIXTURES / "phototest-rotated-L.png").read_bytes()
    try:
        text, meta = transcribe(rotated, "image/png", None, cold=False)
        summary["samples"].append({  # type: ignore[union-attr]
            "id": "degraded_rotated_page",
            "class": "low_quality_page",
            "scored": False,
            "note": "recorded honestly; not a pass/fail metric",
            "machine_text": text,
            "meta": meta,
        })
    except (OcrTimeout, OcrUnavailable, OcrServiceError) as exc:
        summary["samples"].append({  # type: ignore[union-attr]
            "id": "degraded_rotated_page",
            "class": "low_quality_page",
            "scored": False,
            "error": type(exc).__name__,
            "detail": getattr(exc, "details", {}),
        })
    _ = low_pdf  # rendered as a sanity artifact only

    summary["blocked_classes"] = [
        {"class": "real_chinese_page_with_human_truth", "reason": "no license-clear Chinese page + human truth under budget/time"},
        {"class": "table", "reason": "no license-clear table page with human truth under budget/time"},
        {"class": "mixed_text_and_scan_single_file", "reason": "not obtainable under license here"},
    ]
    (REPORTS / "quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "samples"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
