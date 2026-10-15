"""LG-031 phase3 G1: the product bootstrap must wire autonomous claim.

R2's real probe bypassed the product ``GraphDispatcher`` (it hand-rolled the pool
grant/claim callback), so it never proved the *product coordinator* path can run
an autonomous claim.  Reading the code showed the default ``build_runtime`` never
passed ``autonomous_claim``/``grant_registry`` and never read the
``decentralized_claim_enabled`` switch, i.e. the switch was unreachable from the
product path.

These tests pin the additive fix: switch OFF (default) keeps the deterministic
path exactly (no autonomous tool, no grant registry); switch ON wires the
autonomous claim tool and the process-wide grant registry.  No network, no model.
"""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.bootstrap import StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.coordinator.graph import GraphDispatcher
from lightgravity.runtime.token import RuntimeToken
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _runtime(tmp_path: Path):
    return build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
            wire_real_executor=True,
        )
    )


def _coordinator(state) -> GraphDispatcher:
    # ``app.state.coordinator`` is the Coordinator service; the graph dispatcher
    # is the execution dispatcher it was built with.
    service = state.app.state.coordinator
    coordinator = service._dispatcher
    assert isinstance(coordinator, GraphDispatcher)
    return coordinator


def test_default_switch_leaves_the_deterministic_path(tmp_path: Path) -> None:
    state = _runtime(tmp_path)
    coordinator = _coordinator(state)
    # Default-closed: the product path must NOT attach the autonomous tool.
    assert coordinator._autonomous_claim is False
    assert coordinator._grant_registry is None


def test_switch_on_wires_autonomous_claim_and_registry(tmp_path: Path) -> None:
    state = _runtime(tmp_path)
    # Flip the real SETTINGS switch through the real service, then rebuild the
    # runtime from the SAME data dir (the bootstrap re-reads the switch).
    store = FileStore(state.settings.data_dir, state.settings.workspace_root)
    service = ConnectionService(store, secret_store=FileSecretStore(state.settings.secret_store))
    service.update_settings(
        expected_revision=0,
        actor="test",
        decentralized_claim_enabled=True,
        collab_requests_enabled=True,
    )
    rebuilt = build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
            wire_real_executor=True,
        )
    )
    coordinator = _coordinator(rebuilt)
    assert coordinator._autonomous_claim is True
    # The dispatcher shares the process-wide registry (the same seam the API
    # identity resolver uses), so a node grant minted during an autonomous claim
    # is resolvable by ``resolve_worker_identity``.
    from lightgravity.collaboration import default_registry

    assert coordinator._grant_registry is default_registry()
    assert coordinator._collaboration is not None
    assert coordinator._collaboration.enabled is True
