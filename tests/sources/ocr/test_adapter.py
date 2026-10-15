"""LG-035 adapter/rasteriser tests: real HTTP protocol shape, no external service.

These spin up a **local** ``http.server`` and point the real
:class:`OpenAICompatOcrBackend` at it, so the adapter's actual request encoding,
timeout handling and response parsing are exercised without contacting the
authorized LAN candidate.  They also cover the stdlib PDF rasteriser and the
env-config factory's honest "unavailable" default.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from lightgravity.sources.ocr import (
    ENV_OCR_SCALE,
    MAX_OCR_SCALE,
    OpenAICompatOcrBackend,
    OcrRequest,
    OcrScaleInvalid,
    OcrServiceError,
    OcrTimeout,
    PdfiumRasterizer,
    UnavailableOcrBackend,
    backend_from_env,
    is_pdf_bytes,
    parse_scale_env,
)


class _Recorder(BaseHTTPRequestHandler):
    mode = "ok"
    last: dict[str, Any] = {}

    def log_message(self, *_: object) -> None:  # silence test output
        return

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).last = {"path": self.path, "body": body, "auth": self.headers.get("Authorization")}
        if self.mode == "error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "backend blew up"}).encode())
            return
        if self.mode == "slow":
            import time

            time.sleep(1.5)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "choices": [
                        {"message": {"role": "assistant", "content": "TRANSCRIBED"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                }
            ).encode()
        )


@pytest.fixture
def server() -> Any:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}", _Recorder
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_adapter_sends_typed_image_content_and_parses_result(server) -> None:
    base_url, recorder = server
    recorder.mode = "ok"
    backend = OpenAICompatOcrBackend(base_url=base_url, model="m1", bearer_token="secret")
    result = backend.transcribe(OcrRequest(data=b"PNGDATA", media_type="image/png", page=3))
    assert result.text == "TRANSCRIBED"
    assert result.page == 3
    assert result.prompt_tokens == 7 and result.completion_tokens == 3
    assert recorder.last["path"].endswith("/v1/chat/completions")
    body = recorder.last["body"]
    assert body["model"] == "m1" and body["temperature"] == 0 and body["stream"] is False
    parts = body["messages"][0]["content"]
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert recorder.last["auth"] == "Bearer secret"
    # The tool must not put any ground truth in the prompt.
    assert "OCR" in parts[0]["text"]


def test_adapter_reports_backend_error_without_fake_text(server) -> None:
    base_url, recorder = server
    recorder.mode = "error"
    backend = OpenAICompatOcrBackend(base_url=base_url, model="m1")
    with pytest.raises(OcrServiceError) as excinfo:
        backend.transcribe(OcrRequest(data=b"x", media_type="image/png"))
    assert excinfo.value.details["status"] == 500
    assert "backend blew up" in excinfo.value.details["message"]


def test_adapter_timeout_is_unknown_not_replayed(server) -> None:
    base_url, recorder = server
    recorder.mode = "slow"
    backend = OpenAICompatOcrBackend(base_url=base_url, model="m1", default_timeout_seconds=0.2)
    with pytest.raises(OcrTimeout) as excinfo:
        backend.transcribe(OcrRequest(data=b"x", media_type="image/png", page=1))
    assert excinfo.value.details["outcome"] == "unknown"


def test_env_factory_is_unavailable_without_configuration() -> None:
    backend = backend_from_env(env={})
    assert isinstance(backend, UnavailableOcrBackend)
    configured = backend_from_env(
        env={
            "LIGHTGRAVITY_OCR_BASE_URL": "http://example.invalid:9",
            "LIGHTGRAVITY_OCR_MODEL": "some-model",
        }
    )
    assert isinstance(configured, OpenAICompatOcrBackend)
    assert configured.model_id == "some-model"


def test_scale_env_default_unchanged_and_valid_parsed() -> None:
    # Absent or empty keeps the default render scale behaviour unchanged.
    assert parse_scale_env({}, default=2.0) == 2.0
    assert parse_scale_env({ENV_OCR_SCALE: ""}, default=2.0) == 2.0
    assert parse_scale_env({ENV_OCR_SCALE: "  "}, default=2.0) == 2.0
    # A finite positive value at or below the documented safe max is accepted.
    assert parse_scale_env({ENV_OCR_SCALE: "4.0"}, default=2.0) == 4.0
    assert parse_scale_env({ENV_OCR_SCALE: "3"}, default=2.0) == 3.0
    assert parse_scale_env({ENV_OCR_SCALE: str(MAX_OCR_SCALE)}, default=2.0) == MAX_OCR_SCALE


@pytest.mark.parametrize(
    ("raw", "reason_part"),
    [
        ("nan", "finite"),
        ("inf", "finite"),
        ("-inf", "finite"),
        ("0", "positive"),
        ("-1", "positive"),
        ("4.1", "maximum"),
        ("abc", "number"),
        ("1e400", "finite"),
    ],
)
def test_scale_env_invalid_is_rejected_not_clamped(raw: str, reason_part: str) -> None:
    # An invalid security/quality value must never silently become a pass.
    with pytest.raises(OcrScaleInvalid) as excinfo:
        parse_scale_env({ENV_OCR_SCALE: raw}, default=2.0)
    details = excinfo.value.details
    assert details["env"] == ENV_OCR_SCALE
    assert details["value"] == raw
    assert reason_part in details["reason"]
    assert details["safe_max"] == MAX_OCR_SCALE


def test_pdf_magic_and_rasteriser_multipage() -> None:
    import io

    import pypdfium2 as pdfium

    assert is_pdf_bytes(b"%PDF-1.7\n") is True
    assert is_pdf_bytes(b"\x89PNG") is False

    document = pdfium.PdfDocument.new()
    for _ in range(3):
        page = document.new_page(120, 80)
        page.close()
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    data = buffer.getvalue()

    raster = PdfiumRasterizer()
    assert raster.page_count(data) == 3
    pages = raster.render(data, scale=1.5, max_pages=2)
    assert [p.page for p in pages] == [1, 2]
    # Each rendered page is a valid PNG produced without Pillow.
    assert pages[0].png.startswith(b"\x89PNG\r\n\x1a\n")
