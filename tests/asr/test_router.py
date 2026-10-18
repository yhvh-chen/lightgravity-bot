"""HTTP round-trip for the protected English ASR settings seam."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.asr import build_english_asr_router, build_english_asr_service
from lightgravity.contracts import API_PREFIX, AppError

from asr_helpers import FakeRuntime, make_repository


def _app(tmp_path: Path) -> tuple[FastAPI, Any]:
    service = build_english_asr_service(
        make_repository(tmp_path), runtime_factory=lambda config: FakeRuntime()
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
    return app, service


async def test_put_first_create_returns_own_revision_and_no_store(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    app, service = _app(tmp_path)
    encoder, reader = fake_models
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/v1/settings/english_asr",
            json={
                "expected_revision": 0,
                "enabled": True,
                "runtime": "inprocess",
                "model_dir": str(encoder),
                "reader_dir": str(reader),
                "device": "cpu",
                "threads": 4,
                "timeout_seconds": 180,
                "max_audio_seconds": 30,
                "max_audio_bytes": 10_000_000,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 0
    assert body["english_asr"]["revision"] == 0
    assert body["english_asr"]["available"] is True
    assert "model_dir" not in body["english_asr"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["etag"] == '"0"'
    assert service.view()["available"] is True


async def test_put_invalid_path_is_422_and_not_persisted(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    app, service = _app(tmp_path)
    _encoder, reader = fake_models
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/v1/settings/english_asr",
            json={
                "expected_revision": 0,
                "enabled": True,
                "model_dir": str(tmp_path / "nope"),
                "reader_dir": str(reader),
            },
        )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    assert service.view()["revision"] == 0
    assert service.view()["configured"] is False


async def test_put_stale_revision_is_409(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    app, service = _app(tmp_path)
    encoder, reader = fake_models
    service.update(
        0,
        {"enabled": True, "model_dir": str(encoder), "reader_dir": str(reader)},
        actor="test",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/v1/settings/english_asr",
            json={"expected_revision": 9, "enabled": False},
        )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "revision_conflict"
