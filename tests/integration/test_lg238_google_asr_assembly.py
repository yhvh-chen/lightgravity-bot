"""LG-238: Google-native ASR through the *actual* assembled application.

These tests mount nothing by hand: ``create_app`` is the resident product
factory, and the optional ASR service is the one instance resolved by
``ConnectionService`` for GET /settings, the protected PUT, /health and the
deferred intake worker.  The only fake is the HTTP transport, which replays the
recorded LG-235 H1 response; no product Google call, SDK, torch/numpy/Reader,
model container, Files API or environment product key is involved.

Covered seams (docs/08 §23, contract 1.22.0):
* the lazy service built by the real bootstrap path receives the controlled
  ``FileSecretStore`` (a Google credential can be saved and then read back as
  ``credential_configured``);
* the 1.22 GET view/PUT field shape, default model/base URL, read-only limits
  and absence of secrets/local paths;
* ``/health.contract_version == 1.23.0`` and attemptable ``english_asr``
  capability without torch/numpy installed;
* an upload through the real deferred intake worker producing a Google
  ``machine`` transcript/receipt/index entry with the frozen provenance;
* a saved Google configuration does not break legacy blocks (missing
  ``provider`` still resolves to ``eg2-reader``).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.asr import build_english_asr_service
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX, CONTRACT_VERSION
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore

ASR_SETTINGS = f"{API_PREFIX}/settings/english_asr"
FIXTURE = Path(__file__).parents[1] / "asr" / "fixtures" / "lg235_h1_response.json"
H1_TEXT = (
    "On April 9th 2027 the North Harbor market opens at 6:45 and the ferry to "
    "Cedar Island carries 38 passengers."
)
GOOGLE_KEY = "integration-google-key-not-real"


class RecordedTransport:
    """Replays the recorded LG-235 H1 response; never a product call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes, float]] = []
        self.payload = FIXTURE.read_bytes()

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append((url, headers, body, timeout))
        return 200, self.payload


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _connections(settings: Settings) -> ConnectionService:
    store = FileStore(settings.data_dir, settings.workspace_root)
    return ConnectionService(
        store, secret_store=FileSecretStore(settings.secret_store)
    )


def _app(
    settings: Settings,
    connections: ConnectionService,
    *,
    allow_sensitive: bool = True,
) -> FastAPI:
    return create_app(
        settings,
        store=connections.repository.store,
        connection_service=connections,
        access_policy=LocalAccessPolicy(
            allow_sensitive_without_token=allow_sensitive
        ),
    )


def _wav_bytes(seconds: float = 0.2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x00\x00" * int(16_000 * seconds))
    return buffer.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _wait_for_job(
    client: httpx.AsyncClient, job_id: str, *, timeout: float = 15.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(f"{API_PREFIX}/intake/jobs/{job_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] not in ("queued", "running"):
            return body
        await asyncio.sleep(0.02)
    raise AssertionError("intake job did not reach a terminal state")


async def test_assembled_lazy_service_uses_controlled_secret_store_and_122_views(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    connections = _connections(settings)
    # No configure_english_asr(): this is exactly the resident lazy path.
    app = _app(settings, connections)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get(f"{API_PREFIX}/health")
            assert health.status_code == 200, health.text
            assert health.json()["contract_version"] == "1.23.0"
            assert CONTRACT_VERSION == "1.23.0"
            # Default off, but the admin configuration view stays available.
            default_view = (await client.get(f"{API_PREFIX}/settings")).json()[
                "english_asr"
            ]
            assert default_view["provider"] == "eg2-reader"
            assert default_view["runtime"] == "inprocess"
            assert "max_request_bytes" not in default_view["limits"]

            saved = await client.put(
                ASR_SETTINGS,
                json={
                    "expected_revision": 0,
                    "enabled": True,
                    "provider": "google-native",
                    "credential_value": GOOGLE_KEY,
                },
            )
            assert saved.status_code == 200, saved.text
            body = saved.json()
            view = body["english_asr"]
            # The lazy ConnectionService-built service received the controlled
            # FileSecretStore: omitting credential_ref above uses its default
            # ref and the secret is resolvable on the next read.
            assert view["provider"] == "google-native"
            assert view["runtime"] == "google-native"
            assert view["enabled"] is True
            assert view["configured"] is True
            assert view["available"] is True
            assert view["reason"] is None
            assert view["credential_configured"] is True
            assert view["model"] == "gemini-3.8-flash"
            assert (
                view["base_url"]
                == "https://generativelanguage.googleapis.com/v1beta"
            )
            assert view["language"] == "en"
            assert view["timestamps_supported"] is False
            assert view["limits"] == {
                "max_audio_seconds": None,
                "max_audio_bytes": 10_000_000,
                "max_request_bytes": 20_000_000,
                "timeout_seconds": 180,
                "max_concurrency": 1,
            }
            # Never echo a secret/ref/path/body.
            serialized = json.dumps(body)
            assert GOOGLE_KEY not in serialized
            for forbidden in (
                "credential_ref",
                "credential_value",
                "model_dir",
                "reader_dir",
            ):
                assert forbidden not in serialized

            reloaded = (await client.get(f"{API_PREFIX}/settings")).json()[
                "english_asr"
            ]
            assert reloaded == view
            assert reloaded["revision"] == 0

            health = (await client.get(f"{API_PREFIX}/health")).json()
            assert health["contract_version"] == "1.23.0"
            assert health["capabilities"]["english_asr"] is True

            # An update without ``provider`` follows the existing Google block
            # (old-client behavior) and must not silently reinterpret it.
            disabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            disabled_view = disabled.json()["english_asr"]
            assert disabled_view["provider"] == "google-native"
            assert disabled_view["runtime"] == "google-native"
            assert disabled_view["enabled"] is False
            assert disabled_view["configured"] is True
            assert disabled_view["available"] is False
            assert disabled_view["reason"] == "disabled"
            assert disabled_view["credential_configured"] is True
            assert disabled_view["revision"] == 1


async def test_assembled_google_config_rejects_reader_fields_and_bad_host(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    connections = _connections(settings)
    app = _app(settings, connections)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            base = {
                "expected_revision": 0,
                "enabled": False,
                "provider": "google-native",
            }
            for bad in (
                {**base, "model_dir": "/tmp/model"},
                {**base, "reader_dir": "/tmp/reader"},
                {**base, "threads": 4},
                {**base, "device": "cpu"},
                {**base, "max_audio_seconds": 30},
                {
                    **base,
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                },
                {**base, "base_url": "http://generativelanguage.googleapis.com/v1beta"},
                {**base, "base_url": "https://example.com/v1beta"},
                {**base, "runtime": "inprocess"},
            ):
                rejected = await client.put(ASR_SETTINGS, json=bad)
                assert rejected.status_code == 422, (bad, rejected.text)
            # Nothing was persisted by the rejected writes.
            view = (await client.get(f"{API_PREFIX}/settings")).json()[
                "english_asr"
            ]
            assert view["provider"] == "eg2-reader"
            assert view["revision"] == 0


async def test_assembled_google_source_intake_uses_one_native_request(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    connections = _connections(settings)
    recorded = RecordedTransport()
    # Mirrors bootstrap: one service instance over this ConnectionService's
    # controlled secret store; only the transport is a labelled test fake.
    service = build_english_asr_service(
        connections.repository,
        secret_store=connections.secret_store,
        google_transport=recorded,
    )
    connections.configure_english_asr(service)
    app = _app(settings, connections)
    assert app.state.connection_service.english_asr is service

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            configured = await client.put(
                ASR_SETTINGS,
                json={
                    "expected_revision": 0,
                    "enabled": True,
                    "provider": "google-native",
                    "credential_value": GOOGLE_KEY,
                },
            )
            assert configured.status_code == 200, configured.text
            assert (
                (await client.get(f"{API_PREFIX}/health")).json()[
                    "capabilities"
                ]["english_asr"]
                is True
            )
            assert recorded.calls == []

            audio = _wav_bytes()
            created = await client.post(
                f"{API_PREFIX}/sources",
                json={
                    "request_id": "lg238-google-assembly",
                    "filename": "google-clip.wav",
                    "content_base64": _b64(audio),
                    "media_type": "audio/wav",
                    "intake_mode": "deferred",
                },
            )
            assert created.status_code == 201, created.text
            payload = created.json()
            source_id = payload["source"]["source_id"]
            assert payload["job"]["budget"]["max_asr_calls"] == 1

            job = await _wait_for_job(client, payload["job"]["job_id"])
            assert job["status"] == "succeeded", job
            assert len(recorded.calls) == 1
            url, headers, request_body, timeout = recorded.calls[0]
            assert url == "https://generativelanguage.googleapis.com/v1beta/interactions"
            assert headers["x-goog-api-key"] == GOOGLE_KEY
            request = json.loads(request_body)
            assert request["model"] == "gemini-3.8-flash"
            assert request["input"][0]["text"].startswith(
                "Transcribe the speech in this audio verbatim."
            )
            assert request["input"][1]["mime_type"] == "audio/wav"
            assert request["input"][1]["data"] == _b64(audio)
            assert GOOGLE_KEY not in request_body.decode("utf-8")
            assert timeout == 180.0

            source = (
                await client.get(f"{API_PREFIX}/sources/{source_id}")
            ).json()
            assert source["language"] == "en"
            assert source["text_status"] == "ready"
            transcript = [
                item
                for item in source["derivatives"]
                if item.get("kind") == "transcript"
            ]
            assert len(transcript) == 1
            assert (
                transcript[0]["model_version"]
                == "google-native:gemini-3.8-flash"
            )

            receipt = (
                await client.get(f"{API_PREFIX}/sources/{source_id}/receipt")
            ).json()["latest"]
            assert receipt["text"]["status"] == "ready"
            assert receipt["text"]["language"] == "en"
            assert receipt["text"]["timestamps"] is None
            machine = receipt["text"]["machine"]
            assert machine["engine"] == "google-native"
            assert machine["provider"] == "google"
            assert machine["runtime"] == "google-native"
            assert machine["model"] == "gemini-3.8-flash"
            assert machine["model_version"] == "google-native:gemini-3.8-flash"
            assert machine["endpoint_host"] == "generativelanguage.googleapis.com"
            assert machine["endpoint_path"] == "/v1beta/interactions"
            assert machine["prompt_version"] == "google-native-transcribe-v1"
            assert machine["content_variant"] == "machine"
            assert machine["mime_type"] == "audio/wav"
            assert machine["audio_bytes"] == len(audio)
            assert machine["usage"]["total_tokens"] == 320
            assert machine["latency_ms"] >= 0
            # No reader/encoder provenance may be fabricated on this path.
            assert "encoder" not in machine
            assert "reader" not in machine
            assert receipt["keyword"]["status"] == "searchable"

            content = await client.get(
                f"{API_PREFIX}/sources/{source_id}/content",
                params={"kind": "machine"},
            )
            assert content.status_code == 200, content.text
            assert content.json()["content"] == H1_TEXT

            # Disabling keeps the historical transcript readable and makes no
            # second provider request.
            disabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            assert (await client.get(f"{API_PREFIX}/health")).json()[
                "capabilities"
            ]["english_asr"] is False
            after = (
                await client.get(f"{API_PREFIX}/sources/{source_id}/receipt")
            ).json()["latest"]["text"]["machine"]
            assert after == machine
            content_after = await client.get(
                f"{API_PREFIX}/sources/{source_id}/content",
                params={"kind": "machine"},
            )
            assert content_after.json()["content"] == H1_TEXT
            assert len(recorded.calls) == 1


def test_assembled_factory_google_path_imports_no_reader_stack(tmp_path: Path) -> None:
    """Fresh interpreter: the real factory + lazy Google service import no
    torch/numpy/transformers/Reader, so Google availability does not depend on
    locally installed audio runtimes."""

    import os
    import subprocess

    backend = Path(__file__).resolve().parents[2] / "backend"
    code = f"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, {str(backend)!r})
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.asr import english_asr_capability
from lightgravity.config import Settings
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore

root = Path(tempfile.mkdtemp())
settings = Settings(
    data_dir=root / "data",
    workspace_root=root / "data" / "workspaces",
    secret_store=root / "secrets",
)
store = FileStore(settings.data_dir, settings.workspace_root)
connections = ConnectionService(
    store, secret_store=FileSecretStore(settings.secret_store)
)
app = create_app(
    settings,
    store=store,
    connection_service=connections,
    access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    enable_intake_worker=False,
)
service = connections.english_asr
assert app.state.connection_service.english_asr is service
service.update(0, {{
    "enabled": True,
    "provider": "google-native",
    "credential_value": "fresh-interpreter-key",
}}, actor="test")
view = service.view()
assert view["available"] is True, view
assert view["credential_configured"] is True
assert english_asr_capability(service)["available"] is True
for name in ("torch", "numpy", "transformers", "lightgravity.asr.runtime"):
    assert name not in sys.modules, name + " imported"
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


@pytest.mark.parametrize("unused", [None])
def test_fixture_exists(unused: None) -> None:
    # Guard against a silently moved/renamed fixture: this test file must replay
    # recorded non-secret evidence, never a synthesized "success" body.
    assert FIXTURE.exists()
    payload = json.loads(FIXTURE.read_text("utf-8"))
    assert payload["status"] == "completed"
    assert GOOGLE_KEY not in FIXTURE.read_text("utf-8")
