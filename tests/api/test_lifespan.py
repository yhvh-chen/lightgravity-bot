"""App factory wiring: lifespan lifecycle and the dispatcher/executor seams."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings

from api_helpers import FakeExecutor


async def test_lifespan_starts_and_stops_coordinator(settings: Settings) -> None:
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    coordinator = app.state.coordinator
    assert getattr(coordinator, "_loop_task", None) is None
    async with app.router.lifespan_context(app):
        assert getattr(coordinator, "_loop_task", None) is not None
        # The API Store is the broadcasting proxy over the same authority.
        assert app.state.context.store is app.state.store
    assert getattr(coordinator, "_loop_task", None) is None


async def test_executor_injection_seam(settings: Settings) -> None:
    executor = FakeExecutor()
    app = create_app(
        settings,
        executor=executor,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    assert app.state.context.real_executor is True
    assert app.state.coordinator.dispatcher.executor is executor
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get("/api/v1/health")
    assert health.json()["capabilities"]["sdk_adapter"] is True


async def test_fresh_start_creates_workspace_root_but_not_missing_children(settings: Settings) -> None:
    app = create_app(settings)
    assert not settings.workspace_root.exists()
    async with app.router.lifespan_context(app):
        assert settings.workspace_root.is_dir()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            root = await client.get("/api/v1/files")
            assert root.status_code == 200
            assert root.json()["items"] == []
            assert root.json()["path"] == "."
            child = await client.get("/api/v1/files", params={"path": "missing-child"})
            assert child.status_code == 404
            assert child.json()["error"]["code"] == "not_found"
            assert not (settings.workspace_root / "missing-child").exists()


async def test_startup_preserves_existing_workspace_contents(settings: Settings) -> None:
    settings.workspace_root.mkdir(parents=True)
    existing = settings.workspace_root / "existing.txt"
    existing.write_text("preserve this")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert existing.read_text() == "preserve this"


async def test_workspace_file_collision_fails_before_coordinator_starts(settings: Settings) -> None:
    settings.workspace_root.parent.mkdir(parents=True)
    settings.workspace_root.write_text("configured root is a file")
    app = create_app(settings)
    with pytest.raises(FileExistsError):
        async with app.router.lifespan_context(app):
            pytest.fail("startup must not succeed with a file as its workspace")
    assert settings.workspace_root.read_text() == "configured root is a file"
    assert getattr(app.state.coordinator, "_loop_task", None) is None


async def test_workspace_permission_failure_is_not_hidden(settings: Settings, monkeypatch) -> None:
    app = create_app(settings)
    mkdir = Path.mkdir

    def deny_workspace(path: Path, *args, **kwargs):
        if path == settings.workspace_root:
            raise PermissionError("workspace creation denied")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_workspace)
    with pytest.raises(PermissionError, match="workspace creation denied"):
        async with app.router.lifespan_context(app):
            pytest.fail("startup must not hide workspace permission failure")
    assert not settings.workspace_root.exists()
    assert getattr(app.state.coordinator, "_loop_task", None) is None
