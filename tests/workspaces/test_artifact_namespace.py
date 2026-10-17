"""Current-Run evidence from real isolated worktrees, with local fake execution."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import httpx
import pytest

from lightgravity.adapter import ExecuteRequest, ExecutorResult
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.coordinator import GraphDispatcher, PlanProposal, RawSubtask, RoleCatalog
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
from lightgravity.evidence import EvidenceRefError, parse_evidence_ref, resolve_evidence_ref
from lightgravity.store import FileStore
from lightgravity.verify.candidate import load_candidate
from lightgravity.verify.checks import CheckContext, default_check_registry, run_checks
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager
from gitfixtures import GitRepo
from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup


class DeliveryPlan:
    name = "test-file-contract"

    async def plan(self, context):
        return PlanProposal(subtasks=(
            RawSubtask(key="deliver", objective="Reuse index.html and design.md", capability="implementation",
                       acceptance=("index.html and design.md match the request",), write=True),
            RawSubtask(key="verify", objective="Check the delivered evidence", capability="verification",
                       acceptance=("files verified",), depends_on=("deliver",), write=False),
        ), source="test")


async def run_case(task_repo: GitRepo, tmp_path: Path, *, malicious: str = ""):
    task_repo.write("index.html", "<html>retained game</html>")
    task_repo.write("design.md", "retained design")
    task_repo.commit_all("retained inputs")
    store = FileStore(tmp_path / "data", task_repo.path.parent)
    build_environment(store)
    task_id, run_id, controller, context = make_dispatch_setup(store)

    def execute(request: ExecuteRequest) -> ExecutorResult:
        workspace = Path(request.workspace_path)
        if request.objective.startswith("Reuse"):
            # Mutating the stale Task base must not alter this isolated candidate.
            task_repo.write("index.html", "STALE BASE MUST NOT BE PUBLISHED")
            (workspace / "new-note.md").write_text("exact new verification bytes")
            if malicious:
                if malicious == "symlink":
                    (workspace / "leak.md").symlink_to(tmp_path / "outside.md")
                    (tmp_path / "outside.md").write_text("outside")
                    refs = ("leak.md",)
                else:
                    refs = (malicious,)
            else:
                refs = ("new-note.md",)
            return ExecutorResult(state="succeeded", summary="delivery", artifact_refs=refs)
        # Verifier reads the bounded copies of canonical evidence, never base.
        assert workspace != task_repo.path
        assert "digest-verified" in request.instructions
        files = {p.name: p.read_text() for p in workspace.iterdir()}
        assert next(v for k, v in files.items() if k.endswith("-index.html")) == "<html>retained game</html>"
        assert next(v for k, v in files.items() if k.endswith("-new-note.md")) == "exact new verification bytes"
        return ExecutorResult(state="succeeded", summary="verified")

    executor = FakeGraphExecutor(execute)
    dispatcher = GraphDispatcher(
        store, executor, planner=DeliveryPlan(),
        catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
        workspaces=GraphWorkspaceProvider(WorktreeManager(task_repo.path.parent)),
    )
    context = replace(context, planning_request=PlanningRequest(
        trigger=PlanningTrigger.USER_REQUEST, reason="test", requested_by="test", max_calls=1,
    ))
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    return store, task_id, run_id, executor, outcome


async def test_new_isolated_file_and_unchanged_inputs_are_bound_and_downloadable(task_repo, tmp_path):
    store, task_id, run_id, executor, outcome = await run_case(task_repo, tmp_path)
    assert outcome.state == "succeeded"
    assert len(executor.requests) == 2
    assert not (task_repo.path / "new-note.md").exists()
    candidate = load_candidate(store, task_id)
    assert len(candidate.artifact_refs) == 3
    assert all(ref.startswith(f"evidence:{run_id}/") for ref in candidate.artifact_refs)
    checks = run_checks(default_check_registry(), ("evidence-present", "artifacts-in-workspace"),
                        CheckContext(task_id, run_id, candidate, store, candidate.workspace_path))
    assert checks.satisfied
    index_ref = next(ref for ref in candidate.artifact_refs if "-index.html@" in ref)
    parsed = parse_evidence_ref(index_ref)
    assert parsed.digest == hashlib.sha256(b"<html>retained game</html>").hexdigest()
    for wrong_task, wrong_run in [("task_other", run_id), (task_id, "run_other")]:
        with pytest.raises(EvidenceRefError):
            resolve_evidence_ref(index_ref, data_dir=store.data_dir, task_id=wrong_task, run_id=wrong_run)

    app = create_app(Settings(data_dir=store.data_dir, workspace_root=task_repo.path.parent,
                              secret_store=tmp_path / "secrets"), store=store,
                     access_policy=LocalAccessPolicy(token="test-token"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as api:
        listing = (await api.get(f"/api/v1/tasks/{task_id}/artifacts")).json()
        assert any(e["evidence_ref"] == index_ref for e in listing["evidence"])
        download = await api.get(f"/api/v1/tasks/{task_id}/artifacts/download", params={"evidence_ref": index_ref})
        assert download.status_code == 200
        assert download.content == b"<html>retained game</html>"
        bad_ref = index_ref[:-1] + ("0" if index_ref[-1] != "0" else "1")
        assert (await api.get(f"/api/v1/tasks/{task_id}/artifacts/download",
                              params={"evidence_ref": bad_ref})).status_code == 404
    source = resolve_evidence_ref(index_ref, data_dir=store.data_dir, task_id=task_id, run_id=run_id)
    source.write_text("tampered")
    with pytest.raises(EvidenceRefError, match="digest mismatch"):
        resolve_evidence_ref(index_ref, data_dir=store.data_dir, task_id=task_id, run_id=run_id)


@pytest.mark.parametrize("malicious", ["../escape.md", "symlink", "evidence:run_other/foreign.md@sha256:" + "0" * 64])
async def test_outputs_cannot_escape_or_adopt_another_run(task_repo, tmp_path, malicious):
    store, task_id, run_id, executor, outcome = await run_case(task_repo, tmp_path, malicious=malicious)
    assert outcome.state == "failed"
    assert len(executor.requests) == 1
    assert "file evidence could not be imported" in outcome.failure_message
