"""LG-017 R1: bootstrap assembles the independent reviewer honestly.

No network/model: the reviewer connection is configured but the *real SDK turn*
is not invoked here (the gated real-model probe covers that).  These tests
assert the assembly decision:

* no reviewer default -> the runtime reports ``unavailable`` and the
  coordinator's honest default reviewer blocks acceptance (no fake pass);
* a reviewer default set to a resolvable connection -> a real ``ModelReviewer``
  is assembled on a role/connection *separate* from the worker.
"""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.minimal import AgentInit, ConnectionInit, initialize_minimal
from lightgravity.runtime.token import RuntimeToken
from lightgravity.verify.review import ModelReviewer, UnavailableReviewer


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _seed(tmp_path: Path, settings: Settings, *, reviewer: bool) -> None:
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    service = ConnectionService(
        store, secret_store=FileSecretStore(settings.secret_store)
    )
    report = initialize_minimal(
        store,
        service,
        connection=ConnectionInit(
            id="lg-primary",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref="lg-worker-key",
        ),
        agent=AgentInit(id="developer", connection_ref="lg-primary"),
        set_worker_default=True,
    )
    assert "connection:lg-primary" in report.created
    if reviewer:
        service.create_connection(
            "lg-reviewer",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref="lg-reviewer-key",
            actor="test",
            request_id="req-reviewer",
        )
        service.update_settings(
            expected_revision=service.get_settings()["revision"],
            actor="test",
            default_reviewer_connection_ref="lg-reviewer",
        )


def _build(tmp_path: Path, settings: Settings) -> RuntimeState:
    return build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )


def test_no_reviewer_is_reported_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed(tmp_path, settings, reviewer=False)
    state = _build(tmp_path, settings)
    report = state.execution_report()
    assert report["reviewer"]["reviewer"] == "unavailable"
    # The coordinator's honest default reviewer is UnavailableReviewer, never a
    # program-only check masquerading as an independent review.
    orchestrator = state.app.state.coordinator._resolved_rework()
    assert isinstance(orchestrator._reviewer, UnavailableReviewer)


def test_configured_reviewer_assembles_model_reviewer(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed(tmp_path, settings, reviewer=True)
    state = _build(tmp_path, settings)
    report = state.execution_report()
    assert report["reviewer"]["reviewer"] == "model"
    orchestrator = state.app.state.coordinator._resolved_rework()
    assert isinstance(orchestrator._reviewer, ModelReviewer)
    # Reviewer runs on its own connection/credential role, separate from worker.
    assert orchestrator._reviewer.support.credential_ref == "lg-reviewer-key"


def test_reviewer_credential_independence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed(tmp_path, settings, reviewer=True)
    state = _build(tmp_path, settings)
    orchestrator = state.app.state.coordinator._resolved_rework()
    reviewer = orchestrator._reviewer
    assert isinstance(reviewer, ModelReviewer)
    # No real credential value was stored, so a real turn reports unavailable;
    # the assembly is still real (ModelReviewer wired), not a fake pass.
    assert reviewer.available() is False
    assert reviewer.model_calls == 0
