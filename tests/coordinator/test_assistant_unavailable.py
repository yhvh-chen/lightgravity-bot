"""LG217 bounded no-responder functional checks; zero model/network calls."""
import pytest

from lightgravity.coordinator import Coordinator
from lightgravity.store import new_id
from coordinator_helpers import message, raw_task
from test_g047_dialogue_delivery_r1 import _service, _selected_source, BRIEF_BODY


@pytest.mark.parametrize("surface", ["global", "team", "task", "personal"])
@pytest.mark.parametrize("content", ["Hello", "Read this file. Do not create a task."])
async def test_no_responder_is_unavailable_without_false_sources(store, surface, content):
    sources = _service(store)
    source_id = _selected_source(sources, BRIEF_BODY)
    coordinator = Coordinator(store, source_service=sources, team_mode=surface in {"team", "personal"})
    conv = new_id("conv")
    task_id = raw_task(store) if surface == "task" else None
    payload = message(("@bot " if surface == "team" else "") + content)
    if surface != "personal":
        payload["selected_sources"] = [{"source_id": source_id}]

    async def submit():
        if surface == "personal":
            return await coordinator.submit_personal_message(conv, payload, owner="alice", attachment_context="private fixture")
        if task_id:
            return await coordinator.submit_task_message(task_id, payload)
        return await coordinator.submit_global_message(conv, payload)

    result = await submit()
    print({"surface": surface, "kind": result.kind, "data": result.data, "reply": result.reply})
    assert result.kind == "unavailable"
    assert result.data["unavailable"] is True
    assert result.data["intent"] == ("answer" if content == "Hello" else "bounded_read")
    assert "unavailable" in result.reply.lower()
    assert "Settings" in result.reply
    assert "restart" in result.reply.lower()
    assert "resolved_source_bindings" not in result.data
    assert not result.data.get("attachment_context_included")
    items = coordinator.read_task_messages(task_id) if task_id else coordinator.read_global_messages(conv)
    user = next(row["message"] for row in items if row["message"].get("role") == "user")
    assert user["content"] == payload["content"]
    if surface != "personal":
        assert user["selected_sources"] == payload["selected_sources"]
    # read_task_messages and global records use the same outer message envelope.
    assistant = [row["message"] for row in items if row["message"].get("role") == "assistant"]
    assert len(assistant) == 1
    assert "selected_context" not in assistant[0]
    assert "resolved_source_bindings" not in assistant[0].get("data", {})
    assert not assistant[0].get("data", {}).get("attachment_context_included")
    assert (await submit()).to_dict() == result.to_dict()
    reopened = coordinator.read_task_messages(task_id) if task_id else coordinator.read_global_messages(conv)
    assert len([row for row in reopened if row["message"].get("role") == "assistant"]) == 1
    assert len(coordinator.list_tasks()) == (1 if task_id else 0)
    assert not list((store.data_dir / "runs").glob("*/RUN.md"))
