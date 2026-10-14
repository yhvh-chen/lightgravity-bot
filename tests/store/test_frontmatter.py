"""Frontmatter parsing, duplicate keys and body/unknown-field preservation."""

from __future__ import annotations

import pytest

from lightgravity.store.errors import ConfigInvalid
from lightgravity.store.frontmatter import (
    as_mapping,
    merge_maps,
    parse_document,
    render_document,
)


def test_parse_keeps_body_and_unknown_fields() -> None:
    text = (
        "---\n"
        "schema: lightgravity.bot/v1\n"
        "kind: task\n"
        "id: task_x\n"
        "custom_ext:\n"
        "  nested: 1\n"
        "---\n"
        "# Body\n\nkeep me\n"
    )
    data, body = parse_document(text)
    assert data["custom_ext"] == {"nested": 1}
    assert data["id"] == "task_x"
    assert body == "# Body\n\nkeep me\n"


def test_duplicate_yaml_key_is_rejected() -> None:
    text = "---\nid: task_a\nid: task_b\n---\n"
    with pytest.raises(ConfigInvalid) as excinfo:
        parse_document(text)
    assert [d["code"] for d in excinfo.value.diagnostics] == ["duplicate_key"]


def test_invalid_yaml_is_rejected() -> None:
    text = "---\nid: [unclosed\n---\n"
    with pytest.raises(ConfigInvalid) as excinfo:
        parse_document(text)
    assert [d["code"] for d in excinfo.value.diagnostics] == ["invalid_yaml"]


def test_missing_frontmatter_delimiters() -> None:
    with pytest.raises(ConfigInvalid) as excinfo:
        parse_document("# just markdown\n")
    assert [d["code"] for d in excinfo.value.diagnostics] == ["frontmatter_missing"]

    with pytest.raises(ConfigInvalid) as unclosed:
        parse_document("---\nid: task_a\nbody\n")
    assert [d["code"] for d in unclosed.value.diagnostics] == ["frontmatter_unclosed"]


def test_merge_preserves_unknown_and_sibling_fields() -> None:
    data, _ = parse_document(
        "---\n"
        "title: old\n"
        "unknown: keep\n"
        "queue:\n"
        "  state: not_queued\n"
        "  extension: keep\n"
        "---\n"
    )
    merge_maps(data, {"title": "new", "queue": {"state": "queued"}})
    assert data["title"] == "new"
    assert data["unknown"] == "keep"
    assert data["queue"]["state"] == "queued"
    assert data["queue"]["extension"] == "keep"


def test_render_round_trips_unknown_fields() -> None:
    data, _ = parse_document("---\ntitle: t\nunknown: 1\n---\n")
    rendered = render_document(data, "body\n")
    again, body = parse_document(rendered)
    assert again["unknown"] == 1
    assert body == "body\n"


def test_as_mapping_handles_non_mappings() -> None:
    assert as_mapping({"a": 1}) == {"a": 1}
    assert as_mapping(None) == {}
    assert as_mapping("x") == {}
