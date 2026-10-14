"""Executor unit coverage: classification, diffing, blocked paths and cancel."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.adapter import (
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
    ExecutionRef,
    InMemoryCredentialResolver,
    ResourceCompiler,
    classify_outcome,
    diff_snapshots,
    snapshot_tree,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, make_registry


def _executor(
    store: FileStore,
    *,
    resolver: InMemoryCredentialResolver | None = None,
    artifacts: DirectoryArtifactSink | None = None,
) -> AntigravityExecutor:
    return AntigravityExecutor(
        store,
        ResourceCompiler(store, registry=make_registry()),
        credential_resolver=resolver,
        artifacts=artifacts,
    )


def test_classify_outcome_branches() -> None:
    assert classify_outcome(
        stop_reason=None,
        tool_errors=0,
        has_output=True,
        stream_error=None,
        cancel_requested=False,
        cancel_confirmed=False,
        timed_out=False,
    )[0] == "succeeded"

    budget = classify_outcome(
        stop_reason="StopReason.MAX_MODEL_CALLS_EXCEEDED",
        tool_errors=0,
        has_output=False,
        stream_error=None,
        cancel_requested=False,
        cancel_confirmed=False,
        timed_out=False,
    )
    assert budget[0] == "budget_exhausted"

    cancelled = classify_outcome(
        stop_reason=None,
        tool_errors=0,
        has_output=False,
        stream_error=None,
        cancel_requested=True,
        cancel_confirmed=True,
        timed_out=False,
    )
    assert cancelled[0] == "cancelled"

    unconfirmed = classify_outcome(
        stop_reason=None,
        tool_errors=0,
        has_output=False,
        stream_error=None,
        cancel_requested=True,
        cancel_confirmed=False,
        timed_out=False,
    )
    assert unconfirmed[0] == "blocked"
    assert unconfirmed[1] is not None and unconfirmed[1].code == "cancellation_unconfirmed"

    timed_out = classify_outcome(
        stop_reason=None,
        tool_errors=0,
        has_output=False,
        stream_error=None,
        cancel_requested=True,
        cancel_confirmed=False,
        timed_out=True,
    )
    assert timed_out[0] == "timeout"

    failed = classify_outcome(
        stop_reason=None,
        tool_errors=2,
        has_output=False,
        stream_error=None,
        cancel_requested=False,
        cancel_confirmed=False,
        timed_out=False,
    )
    assert failed[0] == "failed" and failed[1] is not None and failed[1].code == "tool_failed"


def test_snapshot_and_diff_detect_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("same", encoding="utf-8")
    (workspace / "edit.txt").write_text("before", encoding="utf-8")
    (workspace / "remove.txt").write_text("gone", encoding="utf-8")

    before = snapshot_tree(workspace)
    (workspace / "edit.txt").write_text("after", encoding="utf-8")
    (workspace / "new.txt").write_text("new content", encoding="utf-8")
    (workspace / "remove.txt").unlink()
    after = snapshot_tree(workspace)

    text, produced, removed = diff_snapshots(before, after)
    assert "new.txt" in produced
    assert "edit.txt" in produced
    assert "remove.txt" in removed
    assert "-before" in text and "+after" in text


def test_directory_artifact_sink_rejects_escape(tmp_path: Path) -> None:
    sink = DirectoryArtifactSink(tmp_path / "artifacts")
    ref = sink.write("run_1/diff.patch", "content")
    assert ref.endswith("run_1/diff.patch")
    with pytest.raises(Exception):
        sink.write("../escape.patch", "x")


async def test_execute_requires_agent_ref(store: FileStore) -> None:
    executor = _executor(store)
    result = await executor.execute(
        ExecuteRequest(task_id="task_x", run_id="run_x", subtask_id="sub_x"), lambda event: None
    )
    assert result.state == "blocked"
    assert result.failure is not None and result.failure.code == "config_invalid"


async def test_execute_blocks_unverified_backend(store: FileStore) -> None:
    build_basic_environment(store, backend="gemini", credential_ref="gemini-key")
    build_agent(store)
    executor = _executor(store, resolver=InMemoryCredentialResolver({"gemini-key": "x"}))
    result = await executor.execute(
        ExecuteRequest(
            task_id="task_x",
            run_id="run_x",
            subtask_id="sub_x",
            agent_ref="developer",
        ),
        lambda event: None,
    )
    assert result.state == "blocked"
    assert result.failure is not None
    assert result.failure.code == "capability_unavailable"
    assert result.session_ref is None  # no session was created


async def test_execute_blocks_unresolved_credential(store: FileStore) -> None:
    build_basic_environment(store, credential_ref="deepseek-api-key")
    build_agent(store)
    executor = _executor(store, resolver=InMemoryCredentialResolver({}))
    result = await executor.execute(
        ExecuteRequest(
            task_id="task_x",
            run_id="run_x",
            subtask_id="sub_x",
            agent_ref="developer",
            workspace_path=str(store.workspace_root),
        ),
        lambda event: None,
    )
    assert result.state == "blocked"
    assert result.failure is not None and result.failure.code == "capability_unavailable"


async def test_cancel_unknown_execution(store: FileStore) -> None:
    executor = _executor(store)
    result = await executor.cancel(ExecutionRef(execution_id="exec_missing"))
    assert result.confirmed is False
    assert result.state == "not_found"


def test_executor_capabilities_declare_executor_and_proxy(store: FileStore) -> None:
    caps = _executor(store).capabilities()
    assert caps.executor is True
    assert caps.local_auth_proxy is True
    assert caps.search_web is False
    assert caps.subagents is False


async def test_workspace_escape_is_rejected(store: FileStore, tmp_path: Path) -> None:
    build_basic_environment(store, credential_ref="deepseek-api-key")
    build_agent(store)
    executor = _executor(store, resolver=InMemoryCredentialResolver({"deepseek-api-key": "x"}))
    outside = tmp_path / "outside-root"
    outside.mkdir()
    result = await executor.execute(
        ExecuteRequest(
            task_id="task_x",
            run_id="run_x",
            subtask_id="sub_x",
            agent_ref="developer",
            workspace_path=str(outside),
        ),
        lambda event: None,
    )
    assert result.state == "blocked"
    assert result.failure is not None and result.failure.code == "config_invalid"
