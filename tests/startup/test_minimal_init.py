"""Idempotent minimal resource init: explicit only, revision preserving (LG-020)."""

from __future__ import annotations

from pathlib import Path

from lightgravity.runtime.minimal import AgentInit, ConnectionInit, initialize_minimal
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore, new_id


def _service(tmp_path: Path) -> tuple[FileStore, ConnectionService]:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    connections = ConnectionService(
        store, secret_store=FileSecretStore(tmp_path / "secrets")
    )
    return store, connections


def _init(store: FileStore, connections: ConnectionService):
    return initialize_minimal(
        store,
        connections,
        connection=ConnectionInit(
            id="primary",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref="worker-key",
        ),
        agent=AgentInit(
            id="developer",
            connection_ref="primary",
            skill_refs=("implementation", "verification"),
            tool_refs=("view-file", "edit-file", "run-command"),
        ),
        tools=("view-file", "edit-file", "run-command"),
        skills={"implementation": "# Impl\n", "verification": "# Verify\n"},
        set_worker_default=True,
    )


def test_minimal_init_creates_explicit_resources(tmp_path: Path) -> None:
    store, connections = _service(tmp_path)
    report = _init(store, connections)
    assert "connection:primary" in report.created
    assert "agent:developer" in report.created
    assert "tool:view-file" in report.created
    assert "skill:implementation" in report.created
    assert report.defaults["default_worker_connection_ref"] == "primary"
    assert connections.get_settings()["default_worker_connection_ref"] == "primary"

    connection = store.read("connection", "primary")
    assert connection.entity["credential_ref"] == "worker-key"
    assert "worker-key" not in connection.body


def test_minimal_init_is_idempotent_and_preserves_revisions(tmp_path: Path) -> None:
    store, connections = _service(tmp_path)
    first = _init(store, connections)
    revisions = {
        "connection": store.read("connection", "primary").revision,
        "agent": store.read("agent", "developer").revision,
        "settings": connections.get_settings()["revision"],
    }
    second = _init(store, connections)
    assert second.created == []
    assert "connection:primary" in second.skipped
    assert "agent:developer" in second.skipped
    assert "settings:default_worker_connection_ref" in second.skipped
    assert second.defaults == {}
    assert store.read("connection", "primary").revision == revisions["connection"]
    assert store.read("agent", "developer").revision == revisions["agent"]
    assert connections.get_settings()["revision"] == revisions["settings"]
    assert first.created == second.skipped[: len(first.created)]


def test_minimal_init_does_not_invent_resources_without_explicit_agent(
    tmp_path: Path,
) -> None:
    store, connections = _service(tmp_path)
    report = initialize_minimal(
        store,
        connections,
        connection=ConnectionInit(
            id="primary",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref="worker-key",
        ),
    )
    assert report.created == ["connection:primary"]
    assert report.defaults == {}
    # No agent/catalog is fabricated when the operator did not ask for one.
    assert not (tmp_path / "data" / "resources" / "agents").exists()


def test_manual_resources_are_not_overwritten(tmp_path: Path) -> None:
    store, connections = _service(tmp_path)
    store.create(
        "connection",
        "primary",
        {
            "title": "mine",
            "enabled": True,
            "backend": "openai-compat",
            "model": "custom-model",
            "base_url": "https://example.test/v1",
            "credential_ref": "my-ref",
        },
        actor="user",
        request_id=new_id("req"),
    )
    original = store.read("connection", "primary")
    report = initialize_minimal(
        store,
        connections,
        connection=ConnectionInit(
            id="primary",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref="worker-key",
        ),
    )
    assert report.created == []
    assert "connection:primary" in report.skipped
    after = store.read("connection", "primary")
    assert after.revision == original.revision
    assert after.entity["model"] == "custom-model"
    assert after.entity["credential_ref"] == "my-ref"
