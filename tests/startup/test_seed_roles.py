"""LG-120 packaged role library: enumeration, provenance and idempotent seed."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lightgravity.runtime.roles.catalog import (
    AGENCY_COMMIT,
    AGENCY_COPYRIGHT,
    AGENCY_LICENSE,
    AGENCY_REPOSITORY,
    CAPABILITIES,
    CAPABILITY_TOOL_REFS,
    EXECUTABLE_CAPABILITIES,
    build_expected_role_capabilities,
    capability_catalog,
    iter_templates,
    load_manifest,
)
from lightgravity.runtime.roles.seed import seed_role_library
from lightgravity.store import FileStore


def make_store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")


def test_manifest_enumerates_the_complete_pinned_library() -> None:
    manifest = load_manifest()
    templates = list(iter_templates())
    assert manifest["source"] == {
        "repository": AGENCY_REPOSITORY,
        "commit": AGENCY_COMMIT,
        "license": AGENCY_LICENSE,
        "copyright": AGENCY_COPYRIGHT,
    }
    assert manifest["enumeration"]["role_file_count"] == len(templates) == 282
    assert manifest["enumeration"]["total_markdown_files"] == 329
    assert manifest["enumeration"]["excluded_count"] == 47
    assert len(templates) > 3
    ids = {template.id for template in templates}
    assert len(ids) == len(templates)
    excluded = manifest["enumeration"]["excluded"]
    assert len(excluded) == 47
    assert all(item["reason"] and item["path"] for item in excluded)
    # Excluded docs are not silently turned into role templates.
    assert not any(item["path"].removesuffix(".md").split("/")[-1] in ids for item in excluded)


def test_every_template_has_provenance_capability_and_safe_tools() -> None:
    for template in iter_templates():
        source = template.agency_source
        assert source["repository"] == AGENCY_REPOSITORY
        assert source["commit"] == AGENCY_COMMIT
        assert source["license"] == AGENCY_LICENSE
        assert source["copyright"] == AGENCY_COPYRIGHT
        assert source["path"].startswith(template.division + "/")
        assert len(source["blob_sha"]) == 40
        assert len(source["sha256"]) == 64
        assert len(template.body_sha256) == 64
        assert template.body_sha256 == hashlib.sha256(template.body.encode("utf-8")).hexdigest()
        assert template.seed["content_hash"] == template.body_sha256
        assert template.seed["source_commit"] == AGENCY_COMMIT
        assert template.seed["update_available"] is False
        assert set(template.capabilities) <= set(CAPABILITIES)
        expected = build_expected_role_capabilities(
            template.division, template.id, template.title
        )
        assert list(template.capabilities) == expected["capabilities"]
        assert list(template.tool_refs) == expected["tool_refs"]
        assert template.recruitable is expected["recruitable"]
        safe_refs = {
            ref for refs in CAPABILITY_TOOL_REFS.values() for ref in refs
        }
        assert set(template.tool_refs) <= safe_refs
        if not template.recruitable:
            assert template.unsupported_reasons
            assert "research" in template.capabilities
        # Upstream ``tools:`` frontmatter is data, not an authorization grant.
        assert "WebFetch" not in template.tool_refs
        assert "WebSearch" not in template.tool_refs


def test_capability_catalog_is_reusable_metadata_not_three_ids() -> None:
    catalog = capability_catalog()
    assert set(catalog) == set(EXECUTABLE_CAPABILITIES)
    assert "research" not in catalog
    assert len(catalog["implementation"]) > 3
    assert len(catalog["writing"]) > 3
    assert "engineering-code-reviewer" in catalog["review"]
    assert "engineering-frontend-developer" in catalog["implementation"]
    assert "research-synthesist" not in {
        role_id for refs in catalog.values() for role_id in refs
    }


def test_original_upstream_bytes_and_license_are_preserved() -> None:
    root = Path(__file__).resolve().parents[2] / "backend/lightgravity/runtime/roles/agency"
    license_text = (root / "LICENSE").read_text("utf-8")
    assert AGENCY_LICENSE == "MIT"
    assert AGENCY_COPYRIGHT in license_text
    for template in iter_templates():
        original = root / "upstream" / template.agency_source["path"]
        assert original.is_file()
        raw = original.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == template.agency_source["sha256"]
        blob = hashlib.sha1()
        blob.update(f"blob {len(raw)}\0".encode("ascii"))
        blob.update(raw)
        assert blob.hexdigest() == template.agency_source["blob_sha"]


def test_seed_creates_full_library_and_is_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = seed_role_library(store)
    assert first.total_templates == 282
    assert len(first.created) == 282
    assert first.errors == []
    assert set(first.tools_created) == {"view-file", "create-file", "edit-file"}
    agent_files = list((tmp_path / "data/resources/agents").glob("*.md"))
    assert len(agent_files) == 282
    revisions = {path.stem: store.read("agent", path.stem).revision for path in agent_files}

    second = seed_role_library(store)
    assert second.created == []
    assert second.updated == []
    assert len(second.unchanged) == 282
    assert second.errors == []
    assert {
        path.stem: store.read("agent", path.stem).revision for path in agent_files
    } == revisions


def test_seed_preserves_disabled_user_edits_and_custom_templates(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create(
        "agent",
        "engineering-frontend-developer",
        {
            "title": "My custom frontend",
            "enabled": False,
            "connection_ref": "my-connection",
            "skills": {"source": "inline", "refs": []},
            "tool_refs": [],
        },
        actor="user",
        request_id="req-custom",
        body="my custom body\n",
    )
    first = seed_role_library(store)
    assert "engineering-frontend-developer" in first.skipped_custom
    custom = store.read("agent", "engineering-frontend-developer")
    assert custom.body == "my custom body\n"
    assert custom.entity["title"] == "My custom frontend"
    assert custom.entity["enabled"] is False
    assert custom.entity["connection_ref"] == "my-connection"
    assert custom.revision == 0

    # A managed role can be disabled/edited and is preserved on the next start.
    seeded = store.read("agent", "engineering-code-reviewer")
    store.write(
        "agent",
        "engineering-code-reviewer",
        {
            "enabled": False,
            "connection_ref": "local-review",
            "capabilities": ["review"],
            "unknown_user_field": {"keep": "me"},
        },
        expected_revision=seeded.revision,
        actor="user",
        body=seeded.body,
    )
    edited = store.read("agent", "engineering-code-reviewer")
    second = seed_role_library(store)
    assert "engineering-code-reviewer" in second.unchanged
    after = store.read("agent", "engineering-code-reviewer")
    assert after.revision == edited.revision
    assert after.entity["enabled"] is False
    assert after.entity["connection_ref"] == "local-review"
    assert after.entity["unknown_user_field"] == {"keep": "me"}


def test_seed_preserves_user_body_and_marks_update_available(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    seed_role_library(store)
    seeded = store.read("agent", "engineering-frontend-developer")
    store.write(
        "agent",
        "engineering-frontend-developer",
        {"custom_note": "keep this"},
        expected_revision=seeded.revision,
        actor="user",
        body="user-edited role body\n",
    )
    edited = store.read("agent", "engineering-frontend-developer")
    report = seed_role_library(store)
    assert "engineering-frontend-developer" in report.update_available
    after = store.read("agent", "engineering-frontend-developer")
    assert after.body == "user-edited role body\n"
    assert after.entity["seed"]["update_available"] is True
    assert after.entity["seed"]["available_content_hash"] == edited.entity["seed"]["content_hash"]
    assert after.entity["custom_note"] == "keep this"
    revision = after.revision
    seed_role_library(store)
    assert store.read("agent", "engineering-frontend-developer").revision == revision


def test_seed_does_not_touch_existing_member_instances(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    member = store.create(
        "member",
        "member_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        {
            "run_ref": "run_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "role_ref": "engineering-frontend-developer",
            "state": "running",
            "template_version": "1",
            "connection_ref": None,
            "skill_refs": [],
            "assigned_subtask_refs": [],
            "config_hash": "pinned-hash",
        },
        actor="user",
        request_id="req-member",
        body="pinned member\n",
    )
    seed_role_library(store)
    after = store.read("member", member.entity_id)
    assert after.revision == member.revision
    assert after.body == "pinned member\n"
    assert after.entity["config_hash"] == "pinned-hash"
