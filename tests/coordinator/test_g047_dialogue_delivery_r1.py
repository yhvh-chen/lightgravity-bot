"""LG-047 QA-R1 G repair tests — dialogue persistence + default Chat delivery.

Owed by the LG-047 R1 repair for the two frozen QA findings:

1. A selected direct/bounded-read answer must be **persisted** (assistant body +
   ``Sources`` bindings) in the same conversation log its user message used, so
   reopening ``GET .../messages`` shows the answer and the original sources.  A
   retried ``message_id`` must not call the model again or append duplicates; the
   no-selection path stays legacy-compatible.
2. An ordinary Chat delivery request ("Create a Markdown file ...") must produce
   a **valid minimal single-worker program plan** with acceptance criteria and an
   authorized workspace boundary, and dispatch the selected material's exact
   original body to the worker.

Everything here is a **local unit** test: the executor is an in-process fake
(explicitly **not** real SDK/model evidence) and no network/credential is used.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecutionRef,
    ExecutorResult,
    adapter_capabilities,
)
from lightgravity.coordinator import Coordinator
from lightgravity.coordinator.classification import classify_message
from lightgravity.coordinator.graph import GraphDispatcher
from lightgravity.coordinator.recruiter import RoleCatalog
from lightgravity.sources.content import ContentStore, MachineDraft, PageText
from lightgravity.sources.service import build_source_service
from lightgravity.sources.selection import UNTRUSTED_BEGIN
from lightgravity.store import FileStore, new_id

# The exact docs/11 Flow B delivery phrasing (a concrete file deliverable).
DELIVERY_PROMPT = (
    "Create a Markdown file summary with these exact fixture facts: project code "
    "name ORION-71, programme owner Halden Reyes, primary launch date 2027-03-14, "
    "total approved budget 418,250 EUR."
)
# A delivery phrasing for the *global chat* path (docs/11 Flow B phrasing sent
# as a Task message keeps "approved", which the decision rule would capture).
CHAT_DELIVERY_PROMPT = (
    "Create a Markdown file summary with these exact fixture facts: project code "
    "name ORION-71, programme owner Halden Reyes, primary launch date 2027-03-14, "
    "total budget 418,250 EUR."
)
BRIEF_BODY = (
    "PROJECT ORION-71 — sample brief. Project code name ORION-71. "
    "Programme owner Halden Reyes. Primary launch date 2027-03-14. "
    "Total approved budget 418,250 EUR."
)

ONE_AGENT = RoleCatalog(
    {"implementation": ["developer"], "verification": ["developer"]}
)


class FakeExecutor:
    """In-process unit executor (explicitly not real SDK/model evidence)."""

    name = "fake"
    version = "0"

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(self, request: Any, emit: Any) -> ExecutorResult:
        self.requests.append(request)
        return ExecutorResult(
            state="succeeded",
            summary="fake:succeeded",
            artifact_refs=(f"artifact_{request.subtask_id}",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        return CancelResult(confirmed=True, state="cancelled")


def _service(store: FileStore) -> Any:
    return build_source_service(
        data_dir=store.data_dir,
        task_store=store,
        resolve_path=lambda relative, write: store.resolve_path(relative, write=write),
    )


def _seed_machine(service: Any, source_id: str, text: str) -> None:
    store = service.store
    record = store.read_source(source_id)
    ContentStore(source_root=store.source_dir(source_id)).write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename="brief.txt",
            model="scripted",
            pages=[PageText(page=1, text=text, input_sha256="0" * 64, model="scripted")],
            extractor="scripted",
            status="succeeded",
        )
    )


def _selected_source(service: Any, text: str, *, task_ref: str | None = None) -> str:
    result = service.receive_inline(
        request_id=new_id("req"),
        filename="brief.txt",
        content_base64=base64.b64encode(text.encode()).decode(),
        task_ref=task_ref,
    )
    _seed_machine(service, result.source.source_id, text)
    return result.source.source_id


# ------------------------------------------------------- dialogue persistence


async def test_global_selected_answer_persists_assistant_and_sources(tmp_path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "ws")
    service = _service(store)
    source_id = _selected_source(service, BRIEF_BODY)
    calls: list[str] = []

    def responder(content: str, classification: Any) -> str:
        calls.append(content)
        return "ORION-71 by Halden Reyes, launch 2027-03-14, budget 418,250 EUR."

    coordinator = Coordinator(store, source_service=service, responder=responder)
    conv = new_id("conv")
    result = await coordinator.submit_global_message(
        conv,
        {
            "message_id": "qa-g1",
            "role": "user",
            "content": "Summarize the selected brief.",
            "selected_sources": [{"source_id": source_id}],
        },
    )
    assert result.kind in {"direct", "bounded_read"}
    assert UNTRUSTED_BEGIN in calls[0]

    reopened = coordinator.read_global_messages(conv)
    assert [r["message_id"] for r in reopened] == ["qa-g1", "assistant:qa-g1"]
    assistant = reopened[-1]["message"]
    assert assistant["role"] == "assistant"
    assert assistant["content"].startswith("ORION-71")
    bindings = assistant["data"]["resolved_source_bindings"]
    assert [b["source_id"] for b in bindings] == [source_id]
    assert bindings[0]["layer"] == "machine"
    assert assistant["selected_context"]["refs"][0]["source_id"] == source_id

    # Retry of the same message_id: no second model call, no duplicate row.
    again = await coordinator.submit_global_message(
        conv,
        {
            "message_id": "qa-g1",
            "role": "user",
            "content": "Summarize the selected brief.",
            "selected_sources": [{"source_id": source_id}],
        },
    )
    assert again.to_dict() == result.to_dict()
    assert len(calls) == 1
    assert len(coordinator.read_global_messages(conv)) == 2


async def test_task_selected_answer_persists_assistant_and_sources(tmp_path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "ws")
    service = _service(store)
    task_id = coordinator_task(store)
    source_id = _selected_source(service, BRIEF_BODY, task_ref=task_id)

    coordinator = Coordinator(store, source_service=service, responder=lambda c, k: "answer")
    result = await coordinator.submit_task_message(
        task_id,
        {
            "message_id": "qa-t1",
            "role": "user",
            "content": "Summarize the selected brief.",
            "selected_sources": [{"source_id": source_id}],
        },
    )
    assert result.kind == "direct"

    reopened = coordinator.read_task_messages(task_id)
    assert [r["message_id"] for r in reopened] == ["qa-t1", "assistant:qa-t1"]
    assistant = reopened[-1]["message"]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "answer"
    assert assistant["data"]["resolved_source_bindings"][0]["source_id"] == source_id


async def test_no_source_legacy_direct_answer_has_no_binding_fields(tmp_path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "ws")
    coordinator = Coordinator(store, responder=lambda c, k: "plain")
    conv = new_id("conv")
    result = await coordinator.submit_global_message(
        conv, {"message_id": "qa-legacy", "role": "user", "content": "hello there"}
    )
    assert "resolved_source_bindings" not in result.data
    reopened = coordinator.read_global_messages(conv)
    assistant = reopened[-1]["message"]
    assert assistant["role"] == "assistant"
    # No-selection answer stays legacy-compatible: no selected-source bindings
    # or resolved snapshot are attached (only the ordinary bounded-tools list).
    data = assistant.get("data", {})
    assert "resolved_source_bindings" not in data
    assert "selected_context" not in assistant


# ------------------------------------------------- default Chat delivery plan


def _delivery_task(
    store: FileStore, dispatcher: GraphDispatcher, service: Any | None = None
) -> Coordinator:
    return Coordinator(store, dispatcher=dispatcher, source_service=service)


def test_delivery_prompt_classifies_as_task() -> None:
    # A docs/11-style delivery phrasing that also avoids the DECISION keyword
    # ("approved") so the global-chat path routes it as a delivery Task.
    assert classify_message(CHAT_DELIVERY_PROMPT).next_action == "create_task"


async def test_default_chat_delivery_validates_and_dispatches_selected_body(
    tmp_path,
) -> None:
    """End-to-end (local): global Chat file request -> valid plan -> worker
    receives the exact original selected body with a real workspace boundary."""

    from graph_helpers import build_environment

    store = FileStore(tmp_path / "data", tmp_path / "ws")
    build_environment(store)
    service = _service(store)
    source_id = _selected_source(service, BRIEF_BODY)
    executor = FakeExecutor()
    coordinator = _delivery_task(
        store, GraphDispatcher(store, executor, catalog=ONE_AGENT), service=service
    )
    conv = new_id("conv")

    created = await coordinator.submit_global_message(
        conv,
        {
            "message_id": "qa-deliver",
            "role": "user",
            "content": CHAT_DELIVERY_PROMPT,
            "selected_sources": [{"source_id": source_id}],
        },
    )
    assert created.kind == "task"
    task_id = str(created.task_id)

    task = store.read("task", task_id).entity
    # A program-derived acceptance criterion and an authorized workspace were
    # supplied because the Chat request named neither.
    assert task["acceptance_criteria"]
    assert task["workspace_ref"]
    assert store.resolve_path(task["workspace_ref"], write=True).is_dir()

    coordinator.start()
    try:
        phase = await wait_for_plan(coordinator, task_id)
    finally:
        await coordinator.stop()

    # Plan validation passed and a worker actually ran.
    assert phase not in {"failed"}
    assert executor.requests, "expected at least one dispatched ExecuteRequest"
    request = executor.requests[0]
    assert request.workspace_path and request.workspace_path != ""
    # The exact selected body (untrusted-wrapped) reaches the worker prompt.
    assert BRIEF_BODY in request.instructions
    assert UNTRUSTED_BEGIN in request.instructions
    assert request.acceptance_criteria


async def test_source_bound_trigger_unchanged_with_default_delivery(tmp_path) -> None:
    """The selected-source Run trigger binding is unchanged by the default plan.

    A delivery that carries a selected source still freezes that exact selection
    (and its message id) into the Task's queued Run trigger; a later no-selection
    delivery carries ``snapshot: None`` (legacy) and never inherits the earlier
    selection.
    """

    from graph_helpers import build_environment

    store = FileStore(tmp_path / "data", tmp_path / "ws")
    build_environment(store)
    service = _service(store)
    source_id = _selected_source(service, BRIEF_BODY)
    executor = FakeExecutor()
    coordinator = _delivery_task(
        store, GraphDispatcher(store, executor, catalog=ONE_AGENT), service=service
    )

    with_selection = await coordinator.submit_global_message(
        new_id("conv"),
        {
            "message_id": "qa-trig-sel",
            "role": "user",
            "content": CHAT_DELIVERY_PROMPT,
            "selected_sources": [{"source_id": source_id}],
        },
    )
    trigger = store.read("task", str(with_selection.task_id)).entity["selected_trigger"]
    assert trigger["message_id"] == "qa-trig-sel"
    assert trigger["snapshot"] is not None
    assert trigger["snapshot"]["refs"][0]["source_id"] == source_id

    # A second, no-selection delivery: its trigger snapshot must be None, never
    # the first task's selection (no cross-message inheritance).
    without = await coordinator.submit_global_message(
        new_id("conv"),
        {"message_id": "qa-trig-none", "role": "user", "content": CHAT_DELIVERY_PROMPT},
    )
    legacy = store.read("task", str(without.task_id)).entity["selected_trigger"]
    assert legacy["message_id"] == "qa-trig-none"
    assert legacy["snapshot"] is None


async def test_default_chat_delivery_plan_is_minimal_single_worker(tmp_path) -> None:
    """The derived default keeps the prototype's single deliver node (no verify)."""

    from graph_helpers import build_environment

    store = FileStore(tmp_path / "data", tmp_path / "ws")
    build_environment(store)
    executor = FakeExecutor()
    coordinator = _delivery_task(store, GraphDispatcher(store, executor, catalog=ONE_AGENT))
    created = await coordinator.submit_global_message(
        new_id("conv"),
        {"message_id": "qa-min", "role": "user", "content": CHAT_DELIVERY_PROMPT},
    )
    task_id = str(created.task_id)
    coordinator.start()
    try:
        await wait_for_plan(coordinator, task_id)
    finally:
        await coordinator.stop()
    assert len(executor.requests) == 1
    assert executor.requests[0].acceptance_criteria


def test_unsafe_workspace_ref_is_rejected(tmp_path) -> None:
    """A path escape is still rejected; the program checks are not waived."""

    from lightgravity.contracts import AppError

    store = FileStore(tmp_path / "data", tmp_path / "ws")
    # The workspace boundary is enforced by the store resolver the program uses
    # for every write/dispatch: an escaping ref must never resolve.
    with pytest.raises(AppError):
        store.resolve_path("../escape", write=True)


def coordinator_task(store: FileStore) -> str:
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "T",
            "objective": "do",
            "acceptance_criteria": ["it works"],
            "status": "todo",
            "phase": "intake",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": None,
            "agent_ref": "coordinator",
            "depends_on": [],
            "active_run": None,
            "deliverable_revision": 0,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
            },
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
            "archived": False,
        },
        actor="test",
        request_id=f"req:{task_id}",
        body="# Task\n",
    )
    return task_id


def _latest_run_dir(store: FileStore, task_id: str) -> str | None:
    task = store.read("task", task_id).entity
    return task.get("active_run")


async def wait_for_plan(coordinator: Coordinator, task_id: str) -> str:
    import asyncio

    for _ in range(200):
        snapshot = coordinator.status(task_id)
        phase = snapshot["phase"]
        if phase in {"executing", "verifying", "waiting_user", "awaiting_acceptance", "failed"}:
            return str(phase)
        await asyncio.sleep(0.02)
    return str(coordinator.status(task_id)["phase"])
