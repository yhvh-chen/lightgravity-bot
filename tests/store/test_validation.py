"""Static state validation and Task transition rules."""

from __future__ import annotations

import pytest

from lightgravity.store import ConfigInvalid, FileStore, IllegalTransition, new_id
from lightgravity.store.entities import validate_entity, validate_transition

from store_helpers import create_task, task_content


@pytest.mark.parametrize(
    ("status", "phase"),
    [
        ("done", "executing"),
        ("todo", "executing"),
        ("done", "failed"),
        ("todo", "planning"),
    ],
)
def test_illegal_status_phase_is_rejected(status: str, phase: str) -> None:
    content = task_content(status=status, phase=phase)
    diagnostics = validate_entity("task", content)
    assert "illegal_status_phase" in {d.code for d in diagnostics}


@pytest.mark.parametrize(
    ("status", "phase"),
    [
        ("todo", "intake"),
        ("todo", "waiting_dependencies"),
        ("in-progress", "executing"),
        ("in-progress", "awaiting_acceptance"),
        ("in-progress", "recovery_required"),
        ("done", "completed"),
    ],
)
def test_legal_status_phase_combinations(status: str, phase: str) -> None:
    content = task_content(status=status, phase=phase)
    codes = {d.code for d in validate_entity("task", content)}
    assert "illegal_status_phase" not in codes


def test_wrong_schema_and_kind_are_reported() -> None:
    content = task_content()
    content["schema"] = "other/v9"
    content["kind"] = "run"
    codes = {d.code for d in validate_entity("task", content)}
    assert {"schema_unsupported", "kind_mismatch"} <= codes


def test_invalid_resource_enabled_flag() -> None:
    content = {
        "schema": "lightgravity.bot/v1",
        "kind": "agent",
        "id": "developer",
        "revision": 1,
        "enabled": "yes",
    }
    codes = {d.code for d in validate_entity("agent", content)}
    assert "enabled_invalid" in codes


def test_transition_matrix_allows_and_blocks() -> None:
    planning = task_content(status="in-progress", phase="planning")
    recruiting = task_content(status="in-progress", phase="recruiting")
    executing = task_content(status="in-progress", phase="executing")
    assert validate_transition("task", planning, recruiting) == []
    blocked = validate_transition("task", planning, executing)
    assert [d.code for d in blocked] == ["illegal_transition"]


def test_illegal_transition_does_not_write(store: FileStore) -> None:
    task_id = create_task(store, status="in-progress", phase="planning")
    with pytest.raises(IllegalTransition):
        store.write("task", task_id, {"phase": "executing"}, expected_revision=0, actor="test")
    # File unchanged: still planning at revision 0.
    current = store.read("task", task_id)
    assert current.entity["phase"] == "planning"
    assert current.revision == 0


def test_invalid_status_write_leaves_entity_unchanged(store: FileStore) -> None:
    task_id = create_task(store)
    with pytest.raises(ConfigInvalid):
        store.write(
            "task",
            task_id,
            {"status": "done", "phase": "executing"},
            expected_revision=0,
            actor="test",
        )
    assert store.read("task", task_id).revision == 0


def test_invalid_entity_id_rejected_on_create(store: FileStore) -> None:
    with pytest.raises(ConfigInvalid) as excinfo:
        store.create("task", "../../escape", task_content(), actor="t", request_id="r")
    assert "id_invalid" in {d["code"] for d in excinfo.value.details["diagnostics"]}
    assert not new_id("task").startswith("../../")
