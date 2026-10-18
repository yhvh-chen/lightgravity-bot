"""LG-120 Available metadata and compiled prompt/tool-policy trace."""

from __future__ import annotations

from pathlib import Path

from lightgravity.adapter import CompileConstraints, ResourceCompiler
from lightgravity.resources import ResourceService
from lightgravity.runtime.roles import seed_role_library
from lightgravity.store import FileStore


def make_store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")


def make_connection(store: FileStore) -> None:
    store.create(
        "connection",
        "test-connection",
        {
            "title": "test connection",
            "enabled": True,
            "backend": "openai-compat",
            "model": "deepseek-v4-flash",
            "base_url": "https://example.invalid/v1",
            "credential_ref": "test-key",
        },
        actor="test",
        request_id="req-test-connection",
    )


def test_available_agents_expose_role_source_capability_and_unsupported_reason(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    seed_role_library(store)
    service = ResourceService(store, data_dir=tmp_path / "data")
    items = {item["id"]: item for item in service.available_agents()}
    role = items["marketing-content-creator"]
    assert role["role_category"] == "marketing"
    assert role["capabilities"] == ["writing"]
    assert role["recruitable"] is True
    assert role["summary"]
    assert role["agency_source"]["repository"].endswith("/agency-agents")
    assert role["agency_source"]["license"] == "MIT"
    assert role["seed"]["source_commit"] == (
        "652b2692f8d8ec2b1f1a38e559073e287dfdc469"
    )
    assert set(role["tool_refs"]) == {"view-file", "create-file", "edit-file"}

    research = items["research-synthesist"]
    assert research["recruitable"] is False
    assert research["tool_refs"] == []
    assert research["unsupported_reasons"]

    reviewer = items["engineering-code-reviewer"]
    assert reviewer["tool_refs"] == ["view-file"]
    assert reviewer["recruitable"] is True

    disabled = store.read("agent", "design-ui-designer")
    store.write(
        "agent",
        "design-ui-designer",
        {"enabled": False},
        expected_revision=disabled.revision,
        actor="user",
    )
    disabled_item = {
        item["id"]: item for item in ResourceService(store, data_dir=tmp_path / "data").available_agents()
    }["design-ui-designer"]
    assert disabled_item["enabled"] is False
    assert disabled_item["availability"]["state"] == "disabled"
    assert disabled_item["recruitable"] is False


def test_compiled_prompt_trace_keeps_imported_text_but_no_extra_permissions(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    make_connection(store)
    seed_role_library(store)
    compiler = ResourceCompiler(store)
    constraints = CompileConstraints(connection_ref_override="test-connection")

    review = compiler.compile_agent("engineering-code-reviewer", constraints=constraints)
    assert review.instructions.startswith("> **Imported role guidance (pinned upstream).**")
    assert "You are **Code Reviewer**" in review.instructions
    assert [tool.ref for tool in review.tools] == ["view-file"]
    assert review.skills.source == "inline"
    assert review.skills.refs == ()
    assert review.budget == {}

    # The upstream Pricing Analyst declares ``tools: WebFetch, WebSearch...``;
    # that string is kept as provenance data only and grants nothing.
    pricing_version = store.read("agent", "specialized-pricing-analyst")
    assert "WebFetch" in str(pricing_version.entity["upstream"].get("tools"))
    pricing = compiler.compile_agent("specialized-pricing-analyst", constraints=constraints)
    assert {tool.ref for tool in pricing.tools} == {"view-file", "create-file", "edit-file"}
    assert "WebFetch" not in {tool.ref for tool in pricing.tools}
    assert "WebSearch" not in {tool.ref for tool in pricing.tools}
    assert "Imported role guidance" in pricing.to_dict()["instructions"]
