"""LG-120 startup wiring: seed, catalog and Available metadata."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from lightgravity.api.bootstrap import StartupOptions, build_runtime, load_role_catalog
from lightgravity.config import Settings
from lightgravity.runtime.minimal import DEFAULT_AGENT_ID
from lightgravity.runtime.roles import EXECUTABLE_CAPABILITIES
from lightgravity.runtime.token import RuntimeToken


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def test_bootstrap_seeds_complete_library_and_reusable_catalog(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )
    assert state.role_seed["created"] == 282
    assert state.role_seed["errors"] == 0
    catalog = load_role_catalog(state.store, settings.data_dir)
    assert catalog is not None
    assert set(catalog.capabilities) == set(EXECUTABLE_CAPABILITIES)
    assert "research" not in catalog.capabilities
    # LG-126: the generic built-in worker is the fallback at the end of the
    # pool, not a blanket first choice that shadows mapped agency roles.
    assert catalog.candidate_refs("implementation")[-1] == DEFAULT_AGENT_ID
    assert catalog.ranked_candidates("implementation", "implement login")[0] == DEFAULT_AGENT_ID
    assert (
        catalog.ranked_candidates(
            "implementation",
            "制作一页活动报名静态页，含主题、时间、地点和联系入口 HTML",
        )[0]
        == "engineering-frontend-developer"
    )
    assert "engineering-frontend-developer" in catalog.candidate_refs("implementation")
    assert "marketing-content-creator" in catalog.candidate_refs("writing")
    assert "engineering-code-reviewer" in catalog.candidate_refs("review")
    assert "testing-api-tester" in catalog.candidate_refs("verification") or any(
        "tester" in ref for ref in catalog.candidate_refs("verification")
    )
    assert "research-synthesist" not in {
        ref for refs in (catalog.candidate_refs(item) for item in catalog.capabilities) for ref in refs
    }

    second = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )
    assert second.role_seed["created"] == 0
    assert second.role_seed["unchanged"] == 282


@pytest.mark.asyncio
async def test_team_available_exposes_role_metadata_and_unsupported_reason(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/team/available")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 283  # built-in worker + complete pinned library
    by_id = {item["id"]: item for item in items}
    role = by_id["engineering-frontend-developer"]
    assert role["role_category"] == "engineering"
    assert role["capabilities"] == ["implementation"]
    assert role["recruitable"] is True
    assert role["summary"].startswith("Expert frontend developer")
    assert role["agency_source"]["commit"] == (
        "652b2692f8d8ec2b1f1a38e559073e287dfdc469"
    )
    assert role["agency_source"]["license"] == "MIT"
    assert role["seed"]["version"] == 1
    research = by_id["research-synthesist"]
    assert research["capabilities"] == ["research"]
    assert research["recruitable"] is False
    assert research["unsupported_reasons"] == [
        "unsupported: research requires a web tool, which is not available in this version"
    ]
    custom = by_id[DEFAULT_AGENT_ID]
    assert custom["role_category"] == "custom"
    assert custom["capabilities"] == []
