"""Google-native ASR backend boundary tests (docs/08 §23).

The HTTP transport is a labelled fake.  The two response fixtures are the
**recorded LG-235 real Google responses** (H1/H2) copied verbatim; using them
here exercises parser boundaries only and is not claimed as a new end-to-end
call.  No test in this module reads a real Google credential or touches the
network.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from lightgravity.asr import build_english_asr_service
from lightgravity.asr.config import GoogleAsrConfig, parse_any_block, parse_google_block
from lightgravity.asr.google_native import GoogleTransportError
from lightgravity.contracts import AppError, ErrorCode
from lightgravity.settings import FileSecretStore
from lightgravity.store.errors import RevisionConflict

from asr_helpers import make_repository, wav_bytes

FIXTURES = Path(__file__).with_name("fixtures")
H1_TEXT = (
    "On April 9th 2027 the North Harbor market opens at 6:45 and the ferry to "
    "Cedar Island carries 38 passengers."
)
H2_TEXT = (
    "thought\nDr. Lina Ortiz will visit the Eastside clinic on November 12th to "
    "review 29 patient files and collect 17 samples before noon."
)
GOOGLE_PAYLOAD = {
    "enabled": True,
    "provider": "google-native",
    "runtime": "google-native",
    "credential_ref": "google-asr-api",
    "credential_value": "test-google-key-not-real",
}


def _recorded(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeTransport:
    """Fake HTTP transport that records the real request shape."""

    def __init__(
        self,
        *,
        status: int = 200,
        payload: bytes = b"{}",
        block: threading.Event | None = None,
        release: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.payload = payload
        self.block = block
        self.release = release
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.started = threading.Event()

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append(
            {"url": url, "headers": dict(headers), "body": body, "timeout": timeout}
        )
        self.started.set()
        if self.block is not None:
            assert self.block.wait(5)
        if self.release is not None:
            assert self.release.wait(5)
        if self.error is not None:
            raise self.error
        return self.status, self.payload


def _service(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    env: dict[str, str] | None = None,
    **overrides: Any,
) -> tuple[Any, FileSecretStore]:
    secrets = FileSecretStore(tmp_path / "secrets")
    service = build_english_asr_service(
        make_repository(tmp_path),
        env=env,
        secret_store=secrets,
        google_transport=transport,
    )
    payload = {**GOOGLE_PAYLOAD, **overrides}
    service.update(0, payload, actor="test")
    return service, secrets


def _short_timeout(service: Any, seconds: float) -> None:
    original = service._snapshot

    def snapshot() -> Any:
        snap = original()
        if isinstance(snap.config, GoogleAsrConfig):
            return dataclasses.replace(
                snap, config=dataclasses.replace(snap.config, timeout_seconds=seconds)
            )
        return snap

    service._snapshot = snapshot


def test_legacy_default_view_keeps_old_shape_and_adds_provider_fields(tmp_path: Path) -> None:
    service = build_english_asr_service(make_repository(tmp_path))
    view = service.view()
    assert view["provider"] == "eg2-reader"
    assert view["model"] is None
    assert view["base_url"] is None
    assert view["credential_configured"] is False
    assert view["models"]["encoder"]["id"].startswith("google/embeddinggemma-2")
    assert "max_request_bytes" not in view["limits"]


def test_google_save_is_write_only_no_network_and_own_revision(tmp_path: Path) -> None:
    transport = FakeTransport(payload=_recorded("lg235_h1_response.json"))
    service, secrets = _service(tmp_path, transport)
    view = service.view()
    assert view["revision"] == 0
    assert view["provider"] == "google-native"
    assert view["runtime"] == "google-native"
    assert view["model"] == "gemini-3.8-flash"
    assert view["base_url"] == "https://generativelanguage.googleapis.com/v1beta"
    assert view["configured"] is True
    assert view["available"] is True
    assert view["credential_configured"] is True
    assert view["limits"] == {
        "max_audio_seconds": None,
        "max_audio_bytes": 10_000_000,
        "max_request_bytes": 20_000_000,
        "timeout_seconds": 180,
        "max_concurrency": 1,
    }
    assert view["models"] == {}
    serialized = json.dumps(view)
    assert "test-google-key-not-real" not in serialized
    assert "credential_ref" not in serialized
    assert "credential_value" not in serialized
    assert "model_dir" not in serialized
    assert "reader_dir" not in serialized
    assert transport.calls == []  # saving is local validation only

    secret_path = secrets.directory / "google-asr-api.secret"
    assert secret_path.is_file()
    assert (secret_path.stat().st_mode & 0o777) == 0o600
    assert secrets.get("google-asr-api") is not None
    assert secrets.get("google-asr-api").reveal() == "test-google-key-not-real"  # type: ignore[union-attr]
    settings_text = (tmp_path / "data" / "settings" / "ENGLISH_ASR.md").read_text("utf-8")
    assert "test-google-key-not-real" not in settings_text
    assert 'provider: google-native' in settings_text

    # Omitted provider keeps the Google provider on a disable/update.
    updated = service.update(0, {"enabled": False}, actor="test")
    assert updated["revision"] == 1
    assert updated["english_asr"]["provider"] == "google-native"
    assert updated["english_asr"]["reason"] == "disabled"


def test_google_never_uses_environment_credential(tmp_path: Path) -> None:
    transport = FakeTransport()
    secrets = FileSecretStore(tmp_path / "secrets")
    service = build_english_asr_service(
        make_repository(tmp_path),
        env={"LG_GOOGLE_ASR_API_KEY": "env-key-must-not-be-used"},
        secret_store=secrets,
        google_transport=transport,
    )
    service.update(
        0,
        {"enabled": False, "provider": "google-native", "credential_ref": "google-asr-api"},
        actor="test",
    )
    view = service.view()
    assert view["configured"] is False
    assert view["credential_configured"] is False
    with pytest.raises(AppError) as raised:
        service.update(0, {"enabled": True}, actor="test")
    assert raised.value.code is ErrorCode.VALIDATION_FAILED
    assert "credential_missing" in json.dumps(raised.value.details)


def test_credential_missing_and_deleted_secret_are_honest(tmp_path: Path) -> None:
    transport = FakeTransport()
    service, secrets = _service(tmp_path, transport)
    secrets.delete("google-asr-api")
    view = service.view()
    assert view["enabled"] is True
    assert view["configured"] is False
    assert view["available"] is False
    assert view["reason"] == "credential_missing"
    assert view["credential_configured"] is False


def test_revision_conflict_does_not_silently_overwrite_secret(tmp_path: Path) -> None:
    transport = FakeTransport()
    service, secrets = _service(tmp_path, transport)
    with pytest.raises(RevisionConflict) as raised:
        service.update(
            99,
            {
                "enabled": True,
                "credential_value": "replacement-key",
            },
            actor="test",
        )
    assert "replacement-key" not in str(raised.value)
    assert secrets.get("google-asr-api").reveal() == "test-google-key-not-real"  # type: ignore[union-attr]
    assert service.view()["revision"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": True, "credential_value": None},
        {"enabled": True, "credential_value": ""},
        {"enabled": True, "credential_ref": None},
        {"enabled": True, "credential_ref": ""},
    ],
)
def test_explicit_empty_credential_is_rejected(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    service, _secrets = _service(tmp_path, FakeTransport())
    with pytest.raises(AppError) as raised:
        service.update(0, payload, actor="test")
    assert raised.value.code is ErrorCode.VALIDATION_FAILED
    assert service.view()["revision"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"model_dir": "/tmp/model"},
        {"reader_dir": "/tmp/reader"},
        {"device": "cpu"},
        {"threads": 4},
        {"max_audio_seconds": 30},
        {"model": "bad model/id"},
        {"base_url": "http://generativelanguage.googleapis.com/v1beta"},
        {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
        {"base_url": "https://example.com/v1beta"},
        {"timeout_seconds": 601},
        {"max_audio_bytes": 14_000_001},
    ],
)
def test_google_rejects_legacy_or_out_of_contract_fields(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    service, _secrets = _service(tmp_path, FakeTransport())
    with pytest.raises(AppError) as raised:
        service.update(0, {"enabled": True, **payload}, actor="test")
    assert raised.value.code is ErrorCode.VALIDATION_FAILED
    assert service.view()["revision"] == 0


def test_google_parser_accepts_null_max_audio_seconds_and_trailing_slash() -> None:
    parsed, invalid = parse_google_block(
        {
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/",
            "max_audio_seconds": None,
        }
    )
    assert invalid is None
    assert parsed is not None
    assert parsed.base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert parsed.model == "gemini-3.8-flash"
    assert parse_any_block({"enabled": False})[0].runtime == "inprocess"  # type: ignore[union-attr]


def test_h1_recorded_response_request_shape_and_provenance(tmp_path: Path) -> None:
    transport = FakeTransport(payload=_recorded("lg235_h1_response.json"))
    service, _secrets = _service(tmp_path, transport)
    audio = wav_bytes()
    outcome = service.transcribe(audio, filename="clip.wav")
    assert outcome.status == "ready"
    assert outcome.text == H1_TEXT
    assert outcome.stop_confirmed is True
    machine = outcome.machine or {}
    assert machine["engine"] == "google-native"
    assert machine["provider"] == "google"
    assert machine["model"] == "gemini-3.8-flash"
    assert machine["runtime"] == "google-native"
    assert machine["endpoint_host"] == "generativelanguage.googleapis.com"
    assert machine["endpoint_path"] == "/v1beta/interactions"
    assert machine["prompt_version"] == "google-native-transcribe-v1"
    assert machine["model_version"] == "google-native:gemini-3.8-flash"
    assert machine["content_variant"] == "machine"
    assert machine["mime_type"] == "audio/wav"
    assert machine["audio_bytes"] == len(audio)
    assert machine["audio_sha256"] == hashlib.sha256(audio).hexdigest()
    assert machine["usage"]["total_tokens"] == 320
    assert machine["usage"]["total_thought_tokens"] == 0
    assert "encoder" not in machine and "reader" not in machine
    assert machine["request_bytes"] > len(audio)

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert call["headers"]["x-goog-api-key"] == "test-google-key-not-real"
    assert call["headers"]["Content-Type"] == "application/json"
    assert "test-google-key-not-real" not in call["url"]
    assert "test-google-key-not-real" not in call["body"].decode("utf-8")
    request = json.loads(call["body"])
    assert request["model"] == "gemini-3.8-flash"
    assert request["input"][0] == {
        "type": "text",
        "text": (
            "Transcribe the speech in this audio verbatim. Return only the plain "
            "transcription text, with no commentary, labels, or formatting."
        ),
    }
    assert request["input"][1]["type"] == "audio"
    assert request["input"][1]["mime_type"] == "audio/wav"
    assert base64.b64decode(request["input"][1]["data"]) == audio
    assert machine["request_bytes"] == len(call["body"])


def test_h2_ignores_thought_step_but_preserves_literal_model_output(tmp_path: Path) -> None:
    transport = FakeTransport(payload=_recorded("lg235_h2_response.json"))
    service, _secrets = _service(tmp_path, transport)
    outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    assert outcome.status == "ready"
    assert outcome.text == H2_TEXT
    assert outcome.text.startswith("thought\n")
    assert "signature" not in outcome.text
    assert (outcome.machine or {})["usage"]["total_thought_tokens"] == 87


@pytest.mark.parametrize(
    ("status", "expected_status", "reason"),
    [
        (401, "unavailable", "asr_auth_failed"),
        (403, "unavailable", "asr_auth_failed"),
        (404, "failed", "asr_model_unavailable"),
        (429, "failed", "asr_rate_limited"),
        (400, "failed", "asr_invalid_request"),
        (413, "failed", "asr_invalid_request"),
        (422, "failed", "asr_invalid_request"),
        (500, "failed", "asr_provider_unavailable"),
        (503, "failed", "asr_provider_unavailable"),
    ],
)
def test_http_status_error_mapping(
    tmp_path: Path, status: int, expected_status: str, reason: str
) -> None:
    transport = FakeTransport(status=status, payload=b"{}")
    service, _secrets = _service(tmp_path, transport)
    outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    assert outcome.status == expected_status
    assert outcome.reason == reason
    assert outcome.stop_confirmed is True
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"not json", "asr_response_invalid"),
        (json.dumps({"status": "failed", "steps": []}).encode(), "asr_response_invalid"),
        (json.dumps({"status": "refused", "steps": []}).encode(), "asr_refused"),
        (json.dumps({"status": "completed"}).encode(), "asr_response_invalid"),
        (
            json.dumps({"status": "completed", "steps": []}).encode(),
            "asr_empty_response",
        ),
        (
            json.dumps(
                {
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": "   "}],
                        }
                    ],
                }
            ).encode(),
            "asr_empty_response",
        ),
    ],
)
def test_completed_but_unusable_response_classes(
    tmp_path: Path, body: bytes, reason: str
) -> None:
    service, _secrets = _service(tmp_path, FakeTransport(payload=body))
    outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    assert outcome.status == "failed"
    assert outcome.reason == reason
    assert outcome.stop_confirmed is True


def test_connection_failure_before_dispatch_is_confirmed(tmp_path: Path) -> None:
    transport = FakeTransport(error=GoogleTransportError("dns failed", sent=False))
    service, _secrets = _service(tmp_path, transport)
    outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    assert outcome.status == "failed"
    assert outcome.reason == "asr_provider_unavailable"
    assert outcome.stop_confirmed is True


def test_unknown_mime_and_raw_size_fail_before_dispatch(tmp_path: Path) -> None:
    transport = FakeTransport(payload=_recorded("lg235_h1_response.json"))
    service, _secrets = _service(tmp_path, transport, max_audio_bytes=10)
    unknown = service.transcribe(b"plain text", filename="note.bin")
    assert unknown.status == "failed"
    assert unknown.reason == "asr_invalid_request"
    assert transport.calls == []

    too_big = service.transcribe(wav_bytes(1.0), filename="clip.wav")
    assert too_big.status == "failed"
    assert too_big.reason == "audio_too_long"
    assert transport.calls == []


def test_serialized_request_limit_blocks_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lightgravity.asr.service.GOOGLE_MAX_REQUEST_BYTES", 1_000_000)
    transport = FakeTransport(payload=_recorded("lg235_h1_response.json"))
    service, _secrets = _service(tmp_path, transport)
    # Valid WAV magic + enough bytes that base64 expansion exceeds the limit.
    audio = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 800_000
    outcome = service.transcribe(audio, filename="clip.wav")
    assert outcome.status == "failed"
    assert outcome.reason == "asr_invalid_request"
    assert transport.calls == []


def test_cancel_before_dispatch_sends_nothing(tmp_path: Path) -> None:
    transport = FakeTransport(payload=_recorded("lg235_h1_response.json"))
    service, _secrets = _service(tmp_path, transport)
    outcome = service.transcribe(
        wav_bytes(), filename="clip.wav", cancel_check=lambda: True
    )
    assert outcome.status == "unavailable"
    assert outcome.reason == "cancelled"
    assert outcome.stop_confirmed is True
    assert transport.calls == []


def test_post_dispatch_cancel_is_unconfirmed_and_discards_late_text(tmp_path: Path) -> None:
    release = threading.Event()
    transport = FakeTransport(
        payload=_recorded("lg235_h1_response.json"), release=release
    )
    service, _secrets = _service(tmp_path, transport)
    cancelled = threading.Event()
    result: dict[str, Any] = {}

    def run() -> None:
        result["outcome"] = service.transcribe(
            wav_bytes(),
            filename="clip.wav",
            cancel_check=lambda: cancelled.is_set(),
        )

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert transport.started.wait(5)
        cancelled.set()
        thread.join(5)
        assert not thread.is_alive()
        outcome = result["outcome"]
        assert outcome.status == "extracting"
        assert outcome.reason == "asr_stop_unconfirmed"
        assert outcome.stop_confirmed is False
        assert outcome.text is None
    finally:
        release.set()
    # Let the late fake response return and release the local concurrency slot.
    deadline = time.monotonic() + 2
    while service._google_lock.locked() and time.monotonic() < deadline:
        time.sleep(0.01)


def test_post_dispatch_timeout_is_unconfirmed(tmp_path: Path) -> None:
    release = threading.Event()
    transport = FakeTransport(
        payload=_recorded("lg235_h1_response.json"), release=release
    )
    service, _secrets = _service(tmp_path, transport)
    _short_timeout(service, 0.05)
    try:
        outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    finally:
        release.set()
    assert outcome.status == "extracting"
    assert outcome.reason == "asr_stop_unconfirmed"
    assert outcome.stop_confirmed is False
    assert outcome.text is None


def test_google_mode_does_not_import_torch_numpy_or_reader(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[2] / "backend"
    code = f"""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, {str(backend)!r})
from lightgravity.asr import build_english_asr_service
from lightgravity.settings import FileSecretStore

class Store:
    data_dir = Path(tempfile.mkdtemp()) / "data"
class Repo:
    store = Store()
class Transport:
    def post(self, *, url, headers, body, timeout):
        return 200, json.dumps({{
            "status": "completed",
            "steps": [{{"type": "model_output", "content": [
                {{"type": "text", "text": "fresh google transcript"}}
            ]}}],
            "usage": {{"total_tokens": 1}},
        }}).encode()

service = build_english_asr_service(
    Repo(), secret_store=FileSecretStore(Path(tempfile.mkdtemp()) / "secrets"),
    google_transport=Transport(),
)
service.update(0, {{
    "enabled": True, "provider": "google-native", "runtime": "google-native",
    "credential_ref": "google-asr-api", "credential_value": "fake-key",
}}, actor="test")
outcome = service.transcribe(b"RIFF\\x00\\x00\\x00\\x00WAVE" + b"\\x00" * 64, filename="clip.wav")
assert outcome.status == "ready", outcome
assert "torch" not in sys.modules, "torch imported"
assert "numpy" not in sys.modules, "numpy imported"
assert "transformers" not in sys.modules, "transformers imported"
assert "lightgravity.asr.runtime" not in sys.modules, "Reader runtime imported"
print("clean")
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "clean" in completed.stdout


async def test_google_put_route_uses_existing_write_contract(tmp_path: Path) -> None:
    import httpx
    from fastapi import FastAPI

    from lightgravity.asr import build_english_asr_router
    from lightgravity.contracts import API_PREFIX

    transport = FakeTransport()
    secrets = FileSecretStore(tmp_path / "secrets")
    service = build_english_asr_service(
        make_repository(tmp_path),
        secret_store=secrets,
        google_transport=transport,
    )
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _error(request: Any, exc: AppError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope().model_dump(mode="json"),
        )

    app.include_router(
        build_english_asr_router(service, safe_origin=lambda request: None),
        prefix=API_PREFIX,
    )
    request_body = {
        "expected_revision": 0,
        "enabled": True,
        "provider": "google-native",
        "runtime": "google-native",
        "model": "gemini-3.8-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "credential_ref": "google-asr-api",
        "credential_value": "route-only-test-key",
        "timeout_seconds": 180,
        "max_audio_bytes": 10_000_000,
        "max_audio_seconds": None,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.put(
            f"{API_PREFIX}/settings/english_asr", json=request_body
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 0
    assert body["english_asr"]["provider"] == "google-native"
    assert body["english_asr"]["available"] is True
    assert body["english_asr"]["credential_configured"] is True
    assert body["english_asr"]["limits"]["max_request_bytes"] == 20_000_000
    assert "credential_ref" not in json.dumps(body)
    assert "route-only-test-key" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert transport.calls == []


def test_audio_mime_magic_distinguishes_adts_aac_from_mpeg() -> None:
    from lightgravity.asr.google_native import detect_audio_mime

    assert detect_audio_mime("clip.aac", b"\xff\xf1\x50\x80\x00") == "audio/aac"
    assert detect_audio_mime("clip.mp3", b"\xff\xfb\x90\x64\x00") == "audio/mpeg"
    assert detect_audio_mime("clip.mp3", b"ID3\x04\x00\x00") == "audio/mpeg"
    assert detect_audio_mime("clip.wav", b"RIFF\x00\x00\x00\x00WAVEfmt ") == "audio/wav"
    assert detect_audio_mime("notes.txt", b"plain text") is None
