"""LG-162: English ASR through the *actual* assembled application.

These tests deliberately do not mount any ASR router or source service by hand.
``create_app`` is the resident product factory; the optional ASR service is
injected into the same ``ConnectionService`` that supplies GET /settings,
health and the deferred intake worker.  Routine checks use a labelled fake
runtime and tiny fake pinned files, so no real model is downloaded, loaded or
called.  No TTS is involved.

Covered seams (docs/08 §21):
* default-off, admin-configurable settings view independent of processing;
* protected settings write classification;
* router/health/source-worker wiring through the real factory;
* own revision/content hash and first-create ``expected_revision: 0``;
* omitted ``threads`` is retained on a pathless enable/disable;
* successful transcript provenance remains readable after the capability is
  disabled, without another model call.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import threading
import time
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import (
    LocalAccessPolicy,
    is_admin_only_request,
    is_sensitive_request,
)
from lightgravity.api.app import create_app
from lightgravity.asr import build_english_asr_service, pins
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX, CONTRACT_VERSION
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore

ASR_SETTINGS = f"{API_PREFIX}/settings/english_asr"
TRANSCRIPT = "the small green truck stopped beside the bridge"


class FakeRuntime:
    """Labelled local fixture runtime; never a product model call."""

    def __init__(self, *, text: str = TRANSCRIPT) -> None:
        self.text = text
        self.calls: list[bytes] = []

    def transcribe(
        self,
        data: bytes,
        *,
        filename: str = "audio",
        cancel_check: Any = None,
    ) -> Any:
        self.calls.append(data)
        if cancel_check is not None and cancel_check():
            raise RuntimeError("cancelled fixture")

        class Value:
            text = self.text
            latency_seconds = 0.001
            audio_seconds = 0.2

        return Value()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _fake_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Create tiny files and pin *their* hashes for this test only."""

    encoder = tmp_path / "models" / "encoder"
    reader = tmp_path / "models" / "reader"
    for pin, directory in ((pins.ENCODER_PIN, encoder), (pins.READER_PIN, reader)):
        for name in list(pin.files):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"lg162 fixture {pin.role} {name}\n".encode("utf-8"))
            monkeypatch.setitem(
                pin.files, name, hashlib.sha256(path.read_bytes()).hexdigest()
            )
    return encoder, reader


def _assembled(
    settings: Settings,
    *,
    runtime: FakeRuntime | None = None,
    allow_sensitive: bool = True,
) -> tuple[FastAPI, Any, FakeRuntime]:
    runtime = runtime or FakeRuntime()
    # Connections are built before the factory, exactly like bootstrap: the
    # router, settings view, health and source provider then resolve one service
    # instance instead of lazily building a second one during assembly.
    store = FileStore(settings.data_dir, settings.workspace_root)
    connections = ConnectionService(
        store, secret_store=FileSecretStore(settings.secret_store)
    )
    service = build_english_asr_service(
        connections.repository,
        runtime_factory=lambda config: runtime,
    )
    connections.configure_english_asr(service)
    app = create_app(
        settings,
        store=store,
        connection_service=connections,
        access_policy=LocalAccessPolicy(
            allow_sensitive_without_token=allow_sensitive
        ),
    )
    # This is the one instance the real source provider, settings view, health
    # capability and settings PUT route all resolve.
    assert app.state.connection_service.english_asr is service
    return app, service, runtime


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
    client: httpx.AsyncClient, job_id: str, *, timeout: float = 10.0
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


async def test_actual_app_default_off_view_health_and_protected_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_models(tmp_path, monkeypatch)
    settings = _settings(tmp_path)
    app, _service, _runtime = _assembled(settings, allow_sensitive=False)

    assert is_sensitive_request(
        type("Req", (), {"method": "PUT", "url": type("U", (), {"path": ASR_SETTINGS})(), "query_params": {}})()
    )
    assert is_admin_only_request(
        type("Req", (), {"method": "PUT", "url": type("U", (), {"path": ASR_SETTINGS})(), "query_params": {}})()
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get(f"{API_PREFIX}/health")
            assert health.status_code == 200
            assert health.json()["contract_version"] == CONTRACT_VERSION
            # Processing is off by default, but the admin configuration view is
            # still present (PM clarification: capability != configurability).
            assert health.json()["capabilities"]["english_asr"] is False

            view = await client.get(f"{API_PREFIX}/settings")
            assert view.status_code == 200
            english = view.json()["english_asr"]
            assert english["enabled"] is False
            assert english["configured"] is False
            assert english["available"] is False
            assert english["reason"] == "disabled"
            assert english["revision"] == 0
            assert english["content_hash"] == ""
            assert "model_dir" not in english
            assert "reader_dir" not in english

            denied = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            # No configured local authorization mechanism => default deny for a
            # sensitive /settings write, never an open configuration endpoint.
            assert denied.status_code == 401, denied.text
            assert denied.json()["error"]["code"] == "unauthorized"


async def test_actual_app_owns_revision_and_retains_omitted_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoder, reader = _fake_models(tmp_path, monkeypatch)
    settings = _settings(tmp_path)
    app, service, runtime = _assembled(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            created = await client.put(
                ASR_SETTINGS,
                json={
                    "expected_revision": 0,
                    "enabled": True,
                    "runtime": "inprocess",
                    "model_dir": str(encoder),
                    "reader_dir": str(reader),
                    "device": "cpu",
                    "threads": 6,
                },
            )
            assert created.status_code == 200, created.text
            body = created.json()
            assert body["revision"] == body["english_asr"]["revision"] == 0
            assert body["content_hash"] == body["english_asr"]["content_hash"]
            assert body["english_asr"]["configured"] is True
            assert body["english_asr"]["available"] is True
            assert "model_dir" not in body["english_asr"]
            assert created.headers["cache-control"] == "no-store"
            assert service.snapshot().config.threads == 6
            assert runtime.calls == []

            health = await client.get(f"{API_PREFIX}/health")
            assert health.json()["capabilities"]["english_asr"] is True

            # Admin UI intentionally omits ``threads`` because GET does not
            # return it.  A pathless disable must retain the configured 6.
            disabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            snap = service.snapshot()
            assert snap.revision == 1
            assert snap.config.enabled is False
            assert snap.config.threads == 6
            assert snap.config.model_dir == str(encoder)
            assert snap.config.reader_dir == str(reader)
            assert (await client.get(f"{API_PREFIX}/health")).json()[
                "capabilities"
            ]["english_asr"] is False

            view = (await client.get(f"{API_PREFIX}/settings")).json()["english_asr"]
            assert view["revision"] == 1
            assert view["enabled"] is False
            assert view["configured"] is True
            assert view["reason"] == "disabled"
            assert "model_dir" not in view

            # A pathless re-enable keeps both the stored paths and threads.
            enabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 1, "enabled": True},
            )
            assert enabled.status_code == 200, enabled.text
            snap = service.snapshot()
            assert snap.revision == 2
            assert snap.config.enabled is True
            assert snap.config.threads == 6
            assert snap.available is True
            assert runtime.calls == []

            canonical = (
                settings.data_dir / "settings" / "ENGLISH_ASR.md"
            ).read_text("utf-8")
            assert "threads: 6" in canonical


async def test_successful_transcript_survives_disable_without_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoder, reader = _fake_models(tmp_path, monkeypatch)
    settings = _settings(tmp_path)
    app, service, runtime = _assembled(settings)

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
                    "model_dir": str(encoder),
                    "reader_dir": str(reader),
                    "threads": 2,
                },
            )
            assert configured.status_code == 200, configured.text

            created = await client.post(
                f"{API_PREFIX}/sources",
                json={
                    "request_id": "lg162-asr-history",
                    "filename": "clip.wav",
                    "content_base64": _b64(_wav_bytes()),
                    "media_type": "audio/wav",
                    "intake_mode": "deferred",
                },
            )
            assert created.status_code == 201, created.text
            payload = created.json()
            source_id = payload["source"]["source_id"]
            job_id = payload["job"]["job_id"]
            assert payload["job"]["budget"]["max_asr_calls"] == 1

            job = await _wait_for_job(client, job_id)
            assert job["status"] == "succeeded", job
            assert len(runtime.calls) == 1

            source = (await client.get(f"{API_PREFIX}/sources/{source_id}")).json()
            assert source["language"] == "en"
            assert source["text_status"] == "ready"
            transcript = [
                item
                for item in source["derivatives"]
                if item.get("kind") == "transcript"
            ]
            assert len(transcript) == 1
            assert transcript[0]["content_hash"]
            assert transcript[0]["model_version"]

            receipt = (
                await client.get(f"{API_PREFIX}/sources/{source_id}/receipt")
            ).json()
            latest = receipt["latest"]
            assert latest["text"]["status"] == "ready"
            assert latest["text"]["language"] == "en"
            assert latest["text"]["timestamps"] is None
            assert latest["text"]["machine"]["engine"] == "eg2-reader-v2"
            assert latest["text"]["machine"]["content_variant"] == "machine"

            content = await client.get(
                f"{API_PREFIX}/sources/{source_id}/content",
                params={"kind": "machine"},
            )
            assert content.status_code == 200, content.text
            assert content.json()["content"] == TRANSCRIPT
            assert content.json()["media_type"] == "text/markdown; charset=utf-8"

            download = await client.get(
                f"{API_PREFIX}/sources/{source_id}/download",
                params={"kind": "machine"},
            )
            assert download.status_code == 200
            assert download.content.decode("utf-8") == TRANSCRIPT

            hits = await client.get(
                f"{API_PREFIX}/search", params={"q": "green", "limit": 20}
            )
            assert hits.status_code == 200, hits.text
            assert any(
                hit["source_id"] == source_id for hit in hits.json()["hits"]
            )

            # Disable processing.  Stored machine content and its provenance are
            # historical facts, not a live capability; reading them must not run
            # a model or require ASR to stay enabled.
            disabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            assert (await client.get(f"{API_PREFIX}/health")).json()[
                "capabilities"
            ]["english_asr"] is False
            calls_after_success = len(runtime.calls)

            source_after = (
                await client.get(f"{API_PREFIX}/sources/{source_id}")
            ).json()
            assert source_after["language"] == "en"
            assert source_after["text_status"] == "ready"
            assert source_after["derivatives"] == source["derivatives"]
            assert (
                await client.get(f"{API_PREFIX}/sources/{source_id}/receipt")
            ).json()["latest"]["text"]["machine"] == latest["text"]["machine"]
            content_after = await client.get(
                f"{API_PREFIX}/sources/{source_id}/content",
                params={"kind": "machine"},
            )
            assert content_after.status_code == 200
            assert content_after.json()["content"] == TRANSCRIPT
            download_after = await client.get(
                f"{API_PREFIX}/sources/{source_id}/download",
                params={"kind": "machine"},
            )
            assert download_after.status_code == 200
            assert download_after.content.decode("utf-8") == TRANSCRIPT
            hits_after = await client.get(
                f"{API_PREFIX}/search", params={"q": "green", "limit": 20}
            )
            assert hits_after.status_code == 200
            assert any(
                hit["source_id"] == source_id for hit in hits_after.json()["hits"]
            )
            assert len(runtime.calls) == calls_after_success
            assert service.capability()["available"] is False


async def test_inflight_snapshot_is_immutable_and_next_job_uses_new_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoder, reader = _fake_models(tmp_path, monkeypatch)
    settings = _settings(tmp_path)

    class BlockingRuntime(FakeRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        def transcribe(
            self,
            data: bytes,
            *,
            filename: str = "audio",
            cancel_check: Any = None,
        ) -> Any:
            self.calls.append(data)
            self.started.set()
            assert self.release.wait(5), "fixture runtime was not released"
            if cancel_check is not None and cancel_check():
                raise RuntimeError("cancelled fixture")

            class Value:
                text = TRANSCRIPT
                latency_seconds = 0.001
                audio_seconds = 0.2

            return Value()

    runtime = BlockingRuntime()
    app, service, _ = _assembled(settings, runtime=runtime)

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
                    "model_dir": str(encoder),
                    "reader_dir": str(reader),
                    "threads": 5,
                },
            )
            assert configured.status_code == 200, configured.text

            first = await client.post(
                f"{API_PREFIX}/sources",
                json={
                    "request_id": "lg162-inflight-first",
                    "filename": "inflight.wav",
                    "content_base64": _b64(_wav_bytes()),
                    "media_type": "audio/wav",
                    "intake_mode": "deferred",
                },
            )
            assert first.status_code == 201, first.text
            first_payload = first.json()
            assert first_payload["job"]["budget"]["max_asr_calls"] == 1

            deadline = time.monotonic() + 5
            while not runtime.started.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert runtime.started.is_set()

            # A saved change applies to the next operation, but the in-flight
            # call keeps its immutable snapshot and still records the old
            # provenance after it returns.
            disabled = await client.put(
                ASR_SETTINGS,
                json={"expected_revision": 0, "enabled": False},
            )
            assert disabled.status_code == 200, disabled.text
            assert service.snapshot().config.enabled is False
            assert service.snapshot().config.threads == 5
            assert service.snapshot().config.model_dir == str(encoder)
            assert (await client.get(f"{API_PREFIX}/health")).json()[
                "capabilities"
            ]["english_asr"] is False

            runtime.release.set()
            first_job = await _wait_for_job(client, first_payload["job"]["job_id"])
            assert first_job["status"] == "succeeded", first_job
            first_receipt = (
                await client.get(
                    f"{API_PREFIX}/sources/{first_payload['source']['source_id']}/receipt"
                )
            ).json()["latest"]
            assert first_receipt["text"]["status"] == "ready"
            assert first_receipt["text"]["machine"]["model_version"]
            assert len(runtime.calls) == 1

            # No GET primer was needed: the next job is created with the saved
            # disabled configuration and therefore never calls the model.
            second = await client.post(
                f"{API_PREFIX}/sources",
                json={
                    "request_id": "lg162-inflight-second",
                    "filename": "after-disable.wav",
                    "content_base64": _b64(_wav_bytes(0.3)),
                    "media_type": "audio/wav",
                    "intake_mode": "deferred",
                },
            )
            assert second.status_code == 201, second.text
            second_payload = second.json()
            assert second_payload["job"]["budget"]["max_asr_calls"] == 0
            await _wait_for_job(client, second_payload["job"]["job_id"])
            second_receipt = (
                await client.get(
                    f"{API_PREFIX}/sources/{second_payload['source']['source_id']}/receipt"
                )
            ).json()["latest"]
            assert second_receipt["text"]["status"] == "unavailable"
            assert second_receipt["text"]["reason"] == "asr_disabled"
            assert len(runtime.calls) == 1
