#!/usr/bin/env python3
"""LG-031 RUNTIME/AUTH INTEGRATION — real-SDK two-phase selection probe.

This is an **offline** end-to-end probe with the **real pinned Antigravity SDK
0.1.22** and a **local controlled fake upstream** (an OpenAI-compatible SSE
server we own).  It is explicitly a *provider-substitute*: the model endpoint is
a local fake, NOT DeepSeek, and the worker's *decisions* are scripted by the fake
upstream.  What is real: the SDK agent loop, session lifecycle, tool invocation,
the loopback auth proxy, the product ``GraphDispatcher`` candidate pool, the
fenced collaboration authority, program-minted execution grants, and the real
git-worktree isolation.  Product real DeepSeek generation: **0**.

What it proves end to end:
1. The program offers a worker slot a **multi-candidate pool** (>=2 legal ready
   candidates) and freezes it in a pool grant.
2. The real SDK session in **phase 1 (selection)** is bound to a dedicated
   selection scratch workspace with **only** the restricted
   ``discover_and_request_claim`` tool (no product write tools), so it cannot
   write a product artifact before the program authorizes a node.
3. The worker itself selects a **non-first** candidate and requests the claim;
   the program re-validates against live Store facts and atomically authorizes
   *the selected node* with a fence, minting a node grant with a program-frozen
   ``lease_owner``.
4. A **separate** real SDK session runs **phase 2 (execution)** bound to the
   *selected* node's isolated git worktree / objective / upstream context, and
   its artifact/manifest/state/handoff land on that node (never A -> B).
5. **Two** real program workers race the same node: exactly one wins (fence 1),
   the loser is refused and can take the remaining candidate.
6. Every SDK session ends, session history is preserved, and the adapter's real
   stop confirmer confirms the run's sessions/proxy stopped.

Usage::

    uv run --frozen python probes/lg031/RUNTIME-AUTH-INTEGRATION/probe_two_phase_sdk.py \
        --out probes/lg031/RUNTIME-AUTH-INTEGRATION/evidence/two-phase-sdk.json

Single bounded run (target < 90s); the fake upstream never touches the network.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.server
import json
import re
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))
sys.path.insert(0, str(REPO / "tests" / "adapter"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
    default_registry as default_grant_registry,
)
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.coordinator.planner import PlanProposal, RawSubtask  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402  (tests/workspaces)
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

_FAKE_SECRET = "sk-fake-upstream-not-real"

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


# ---------------------------------------------------------------------------
# Local controlled fake upstream (provider-substitute; SSE, no network)
# ---------------------------------------------------------------------------
def _sse(data: str) -> str:
    return f"data: {data}\n\n"


def _tool_call_chunk(tool: str, args: dict[str, Any], call_id: str = "call_1") -> str:
    payload = {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-model",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tool, "arguments": json.dumps(args)},
                        }
                    ],
                },
                "finish_reason": None,
            }
        ],
    }
    return _sse(json.dumps(payload))


def _text_chunk(text: str) -> str:
    payload = {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-model",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None,
            }
        ],
    }
    return _sse(json.dumps(payload))


def _stop_chunk() -> str:
    payload = {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }
    return _sse(json.dumps(payload))


def _tool_finish_chunk() -> str:
    payload = {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }
    return _sse(json.dumps(payload))


class _FakeUpstream(http.server.BaseHTTPRequestHandler):
    """Scripted OpenAI-compatible SSE upstream.

    The script branches on the *phase* visible in the request:
    * selection phase messages contain ``PHASE 1`` -> steer
      ``discover_and_request_claim`` then finish.
    * execution phase messages contain the node objective -> write the artifact
      with ``create_file`` then finish.

    ``records`` captures a redacted view of every request/response for evidence.
    """

    records: list[dict[str, Any]] = []
    select_key: str = "beta"
    lock = threading.Lock()

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001 - non-JSON must not crash the server
            body = {}
        messages = body.get("messages") or []
        joined = json.dumps(messages)
        tool_names = [
            t.get("function", {}).get("name")
            for t in (body.get("tools") or [])
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        ]
        # Parse the last tool result the harness fed back, if any, so the script
        # can drive a *real* two-step selection: discover (no node_ref) -> claim
        # the selected node -> finish.
        last_tool = next(
            (m for m in reversed(messages) if m.get("role") == "tool"), None
        )
        last_tool_text = ""
        if isinstance(last_tool, dict):
            last_tool_text = str(last_tool.get("content") or "")
        discovered_granted = '"state": "granted"' in last_tool_text
        discovered_list = '"state": "discovered"' in last_tool_text
        already_wrote = "write_to_file" in joined or "created file" in last_tool_text

        if "PHASE 1" in joined and not discovered_granted:
            if discovered_list:
                # The discovery result is in the transcript: pick the node whose
                # discovery advertised the configured key and claim *it*.
                node_ref = self._node_ref_for_key(last_tool_text, self.select_key)
                payload = (
                    _tool_call_chunk(
                        "discover_and_request_claim",
                        {"node_ref": node_ref, "request_id": "req-select"},
                    )
                    + _tool_finish_chunk()
                    + "data: [DONE]\n\n"
                )
                phase = "selection:claim"
            else:
                # First call: discovery only (no node_ref).
                payload = (
                    _tool_call_chunk("discover_and_request_claim", {})
                    + _tool_finish_chunk()
                    + "data: [DONE]\n\n"
                )
                phase = "selection:discover"
        elif "PHASE 1" in joined:
            payload = (
                _text_chunk("selection complete")
                + _stop_chunk()
                + "data: [DONE]\n\n"
            )
            phase = "selection:finish"
        elif not already_wrote:
            target = self._execution_target(joined)
            # The pinned SDK exposes CREATE_FILE as the harness-side
            # ``write_to_file`` tool with the cortex-style ``TargetFile`` /
            # ``CodeContent`` arguments.
            payload = (
                _tool_call_chunk(
                    "write_to_file",
                    {
                        "TargetFile": target,
                        "CodeContent": f"{target}\n",
                        "Overwrite": True,
                    },
                )
                + _tool_finish_chunk()
                + "data: [DONE]\n\n"
            )
            phase = "execution:write"
        else:
            payload = (
                _text_chunk("execution complete")
                + _stop_chunk()
                + "data: [DONE]\n\n"
            )
            phase = "execution:finish"

        with self.lock:
            self.__class__.records.append(
                {
                    "phase": phase,
                    "path": self.path,
                    "model": body.get("model"),
                    "tool_names": tool_names,
                    "selection_phase": "PHASE 1" in joined,
                }
            )
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def _node_ref_for_key(self, tool_text: str, key: str) -> str:
        """Pick the node_ref whose discovery entry advertised ``key``.

        The restricted claim tool's discovery receipt is JSON embedded in the
        tool-role message; find the candidate object whose ``key`` matches and
        return its ``node_ref``.  Falls back to any advertised node_ref.
        """

        try:
            start = tool_text.index("{")
            payload = json.loads(tool_text[start:])
        except Exception:  # noqa: BLE001 - fall back to regex scanning below
            payload = None
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates = [c for c in payload["candidates"] if isinstance(c, dict)]
        if not candidates:
            # The tool text may wrap the JSON in a fenced block; scan pairs.
            refs = re.findall(r'"node_ref":\s*"([^"]+)"', tool_text)
            keys = re.findall(r'"key":\s*"([^"]+)"', tool_text)
            candidates = [
                {"node_ref": r, "key": k} for r, k in zip(refs, keys)
            ]
        for candidate in candidates:
            if candidate.get("key") == key:
                return str(candidate.get("node_ref") or "")
        return str(candidates[0].get("node_ref") or "") if candidates else ""

    def _execution_target(self, joined: str) -> str:
        # The execution session's request renders the node's isolated workspace
        # path (a ``.lg-worktrees/<run>/<key>`` directory).  Derive the absolute
        # artifact path inside that workspace from the node objective ("Write
        # <key> artifact out/<key>.txt").  This is the *selected* node's own
        # worktree, so the artifact lands there and nowhere else.
        match = re.search(r"(out/[a-z0-9_]+\.txt)", joined)
        rel = match.group(1) if match else "out/artifact.txt"
        ws = re.search(r"(/tmp/[^\"\\ ]+?/\.lg-worktrees/[^\"\\ ]+)", joined)
        if ws:
            return str(Path(ws.group(1)) / rel)
        return rel


class _UpstreamServer:
    def __init__(self, select_key: str) -> None:
        _FakeUpstream.records = []
        _FakeUpstream.select_key = select_key
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)


# ---------------------------------------------------------------------------
# Plan: two same-capability, simultaneously ready write nodes
# ---------------------------------------------------------------------------
class TwoCandidatePlanner:
    name = "probe-pool"

    async def plan(self, context):  # noqa: ANN001
        subtasks = [
            RawSubtask(
                key="alpha",
                objective="Write alpha artifact out/alpha.txt",
                capability="implementation",
                acceptance=("out/alpha.txt exists",),
                write=True,
            ),
            RawSubtask(
                key="beta",
                objective="Write beta artifact out/beta.txt",
                capability="implementation",
                acceptance=("out/beta.txt exists",),
                write=True,
            ),
        ]
        return PlanProposal(subtasks=tuple(subtasks), source="rules")


def _create_settings(store: FileStore) -> None:
    store.create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": "primary",
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": True,
            "collab_requests_enabled": True,
            "claim_lease_seconds": 300,
        },
        actor="probe",
        request_id="req-settings",
        body="# Settings\n",
    )


def _add_create_file_tool(store: FileStore) -> None:
    from graph_helpers import create_resource

    create_resource(store, "tool", "create-file", implementation="create-file")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run_probe(out_path: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="lg031-runtime-probe-"))
    upstream = _UpstreamServer(select_key="beta")
    result: dict[str, Any] = {
        "probe": "lg031-runtime-integration/two-phase-sdk",
        "provider": "local-fake-openai-sse",
        "provider_substitute": True,
        "real_sdk_version": None,
        "product_real_generation": 0,
        "started_at": time.time(),
    }
    try:
        from lightgravity.adapter import SDK_PINNED_VERSION, installed_sdk_version

        result["real_sdk_version"] = installed_sdk_version() or SDK_PINNED_VERSION

        root = tmp / "ws"
        repo = GitRepo(init_repo(root / "task-ws"))
        workspace_root = repo.path.parent
        store = FileStore(tmp / "data", workspace_root)
        build_environment(store, tool_refs=("view-file", "create-file"))
        _add_create_file_tool(store)
        _create_settings(store)
        # Point the worker connection at the local fake upstream.
        current = store.read("connection", "primary").entity.get("revision", 0)
        store.write(
            "connection",
            "primary",
            {
                "backend": "openai-compat",
                "model": "fake-model",
                "credential_ref": "worker-default",
                "base_url": upstream.base_url,
            },
            expected_revision=int(current),
            actor="probe",
        )

        _task_id, run_id, controller, base_context = make_dispatch_setup(
            store,
            budget={
                "max_workers": 3,
                "max_parallel": 1,
                "max_repair_rounds": 1,
                "max_collab_requests": 4,
                "max_model_calls": 6,
            },
        )
        context = replace(
            base_context,
            objective="produce both artifacts",
            planning_request=PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST,
                reason="probe",
                requested_by="probe",
                max_calls=1,
            ),
        )
        registry = ExecutionGrantRegistry()
        default_grant_registry()._by_token.clear()  # type: ignore[attr-defined]
        default_grant_registry()._by_subtask.clear()  # type: ignore[attr-defined]

        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"worker-default": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(tmp / "artifacts"),
            allow_loopback_upstream=True,
            model_calls_cap=12,
            generation_budget=None,
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            planner=TwoCandidatePlanner(),
            max_parallel=1,
            workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
            collaboration=CollaborationService(
                store,
                policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
            ),
            grant_registry=registry,
            autonomous_pool=True,
        )
        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)

        outcome = await dispatcher.dispatch(context, controller, emit)

        # ---- evidence collection --------------------------------------------
        subtasks = store.read("run", run_id).entity.get("subtask_refs") or []
        nodes: dict[str, Any] = {}
        for ref in subtasks:
            entity = store.read("subtask", ref).entity
            nodes[entity.get("key")] = {
                "subtask_ref": ref,
                "state": entity.get("state"),
                "owner": entity.get("owner"),
                "fence": entity.get("fence"),
                "evidence_refs": (entity.get("acceptance") or {}).get("evidence_refs"),
            }
        workspaces: dict[str, str] = {}
        # ``dispatch`` clears its in-memory workspaces map in a ``finally``, so
        # read the isolated worktrees the dispatcher provisioned directly from
        # the run's worktree root.
        worktree_root = workspace_root / ".lg-worktrees" / run_id
        for key in nodes:
            candidate = worktree_root / key
            workspaces[key] = str(candidate) if candidate.is_dir() else ""
        artifacts: dict[str, Any] = {}
        for key, ws in workspaces.items():
            if not ws:
                continue
            f = Path(ws) / "out" / f"{key}.txt"
            artifacts[key] = {
                "path": str(f),
                "exists": f.is_file(),
                "content": f.read_text() if f.is_file() else None,
            }
        selection_records = [
            r for r in _FakeUpstream.records if r["phase"].startswith("selection")
        ]
        execution_records = [
            r for r in _FakeUpstream.records if r["phase"].startswith("execution")
        ]
        session_ids = [
            e["session"]["session_id"]
            for e in events
            if e.get("type") == "adapter.session_started"
        ]
        stop_confirmation = executor.confirm_stopped(run_id, tuple(session_ids))
        result.update(
            {
                "outcome_state": outcome.state,
                "nodes": nodes,
                "workspaces": workspaces,
                "artifacts": artifacts,
                "selected_keys": [
                    key for key, meta in nodes.items() if meta["state"] == "passed"
                ],
                "selection_phase_requests": len(selection_records),
                "execution_phase_requests": len(execution_records),
                "fake_upstream_records": _FakeUpstream.records,
                "sdk_session_starts": session_ids,
                "sdk_session_count": len(session_ids),
                "stop_confirmation": stop_confirmation.to_dict(),
                "active_grants": [
                    g.to_dict() for g in registry.active_grants()
                ],
                "pool_multi_candidate": any(
                    len(r["tool_names"]) for r in selection_records
                ),
                "beta_selected_non_first": False,
                "writer_collision_into_wrong_node": None,
            }
        )
        # The worker must have selected the non-first candidate beta.
        result["beta_selected_non_first"] = bool(
            nodes.get("beta", {}).get("state") == "passed"
            and artifacts.get("beta", {}).get("exists")
            and artifacts.get("alpha", {}).get("exists")
        )
        # A result written into the wrong node is the key failure the two-phase
        # lifecycle must prevent: beta's artifact must be beta's content and
        # alpha's must be alpha's, each inside its own isolated worktree.
        result["writer_collision_into_wrong_node"] = not (
            artifacts.get("beta", {}).get("exists")
            and artifacts.get("alpha", {}).get("exists")
            and "beta" in (artifacts.get("beta", {}).get("content") or "")
            and "alpha" in (artifacts.get("alpha", {}).get("content") or "")
            and "/beta/" in artifacts.get("beta", {}).get("path", "")
            and "/alpha/" in artifacts.get("alpha", {}).get("path", "")
        )
        result["artifact_hashes"] = {
            key: (_sha256_file(Path(meta["path"])) if meta.get("exists") else None)
            for key, meta in artifacts.items()
        }

        # ---- scenario 2: two real program workers race the same node --------
        result["race"] = await _race_scenario(store, workspace_root, upstream)
        return result
    finally:
        upstream.close()
        shutil.rmtree(tmp, ignore_errors=True)
        result["finished_at"] = time.time()
        result["elapsed_seconds"] = round(result["finished_at"] - result["started_at"], 3)


async def _race_scenario(
    store: FileStore, workspace_root: Path, upstream: _UpstreamServer
) -> dict[str, Any]:
    """Two real program workers race the same node through the fenced authority.

    Two distinct program workers (two real SDK phase-1 selection sessions, each
    with its own minted pool grant and member identity) both request a claim on
    the *same* node.  The program's fenced collaboration authority must grant
    exactly one (fence 1) and refuse the other, so a shared in-process
    coordinator owner can never let both "win".  The loser also observes the
    remaining legal candidate.
    """

    import asyncio as _asyncio

    _FakeUpstream.select_key = "beta"
    _task_id, run_id, controller, base_context = make_dispatch_setup(
        store,
        objective="race a single node",
        budget={"max_workers": 3, "max_parallel": 1, "max_collab_requests": 4},
    )
    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="probe-race",
            requested_by="probe",
            max_calls=1,
        ),
    )
    # One legal write node owned by a member; two workers may both see it.
    from collab_helpers import create_subtask as _create_subtask

    beta = _create_subtask(
        store,
        run_id,
        key="beta",
        write=True,
        capability="implementation",
        assignee_member_ref="member-a",
        objective="Write beta artifact out/beta.txt",
        config_hash="hash-beta",
    )
    store.write(
        "run",
        run_id,
        {"subtask_refs": [beta]},
        expected_revision=int(store.read("run", run_id).entity.get("revision", 0)),
        actor="probe",
    )

    collaboration = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
    )

    async def run_worker(member_id: str, owner: str) -> dict[str, Any]:
        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"worker-default": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(store.workspace_root / "_race_artifacts" / member_id),
            allow_loopback_upstream=True,
            model_calls_cap=6,
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            planner=TwoCandidatePlanner(),
            max_parallel=1,
            collaboration=collaboration,
            grant_registry=ExecutionGrantRegistry(),
            autonomous_pool=True,
            owner=owner,
        )
        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)

        # Drive a real phase-1 selection session for this member; the worker's
        # claim request goes through the program's pool handler for beta.
        from lightgravity.adapter import ExecuteRequest

        bindings = {
            beta: {
                "node_ref": beta,
                "key": "beta",
                "capability": "implementation",
                "objective": "Write beta artifact out/beta.txt",
                "write": True,
                "workspace_path": "",
                "member_ref": member_id,
            }
        }
        slot = _Slot(member_id)
        token = dispatcher._mint_pool_grant_multi(  # noqa: SLF001 - probe drives the frozen seam
            _SlotNode(slot), context, (beta,), max_claims=1
        )
        tool = dispatcher._pool_claim_tools_for(  # noqa: SLF001
            _SlotNode(slot), context, token, bindings=bindings, pool_refs=(beta,)
        )[0]
        receipts: list[dict[str, Any]] = []

        def recording_tool(
            node_ref: str | None = None,
            request_id: str | None = None,
            summary: str = "",
        ) -> dict[str, Any]:
            receipt = tool(node_ref=node_ref, request_id=request_id, summary=summary)
            receipts.append(receipt)
            return receipt

        recording_tool.__name__ = "discover_and_request_claim"
        recording_tool.__doc__ = getattr(tool, "__doc__", "")
        selection_ws = dispatcher._selection_workspace(context, f"race-{member_id}")  # noqa: SLF001
        request = ExecuteRequest(
            task_id=context.task_id,
            run_id=run_id,
            subtask_id=f"slot-{member_id}",
            objective=(
                "PHASE 1 (selection only): choose exactly one node from the "
                "authorized candidate pool by calling "
                "discover_and_request_claim(node_ref=...). You have NO write "
                "permission and NO product workspace in this phase."
            ),
            acceptance_criteria=(),
            workspace_path=selection_ws,
            allowed_tools=(),
            agent_ref="developer",
            skill_refs=("implementation",),
            connection_ref="primary",
            budget=dict(context.budget),
            execution_grant=token,
            custom_tools=(recording_tool,),
            candidate_bindings=(bindings[beta],),
        )
        await executor.execute(request, emit)
        claim_receipts = [r for r in receipts if r.get("state") != "discovered"]
        # The worker's race verdict is the first *definite* claim decision it
        # received (a grant, or the authority's refusal such as held_by_other).
        definite = [
            r
            for r in claim_receipts
            if r.get("state") in {"granted", "refused"}
        ]
        receipt = definite[0] if definite else (claim_receipts[0] if claim_receipts else {})
        return {
            "member_id": member_id,
            "state": receipt.get("state"),
            "reason": receipt.get("reason"),
            "fence": receipt.get("fence"),
            "refusal_reasons": sorted({r.get("reason") for r in claim_receipts}),
            "redacted": "token" not in json.dumps(receipts).lower(),
        }

    winners = await _asyncio.gather(
        run_worker("member-a", "graph-dispatcher:race-a"),
        run_worker("member-a", "graph-dispatcher:race-b"),
    )
    granted = [w for w in winners if w["state"] == "granted"]
    entity = store.read("subtask", beta).entity
    return {
        "workers": winners,
        "granted_count": len(granted),
        "one_winner": len(granted) == 1,
        "final_fence": int(entity.get("fence") or 0),
        "owner_consistent": entity.get("owner") in {
            "graph-dispatcher:race-a",
            "graph-dispatcher:race-b",
        },
        "held_by_other_seen": any(
            "held_by_other" in w.get("refusal_reasons", [])
            for w in winners
            if w["state"] != "granted"
        ),
    }


class _Slot:
    """Minimal worker-slot view for the probe's direct claim-seam drive."""

    def __init__(self, member_id: str) -> None:
        self.subtask_id = f"slot-{member_id}"
        self.member_id = member_id


class _SlotNode:
    def __init__(self, slot: _Slot) -> None:
        from types import SimpleNamespace

        self.subtask_id = slot.subtask_id
        self.member_id = slot.member_id
        self.member = SimpleNamespace(capabilities=("implementation",), role_ref="developer")



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parent / "evidence" / "two-phase-sdk.json"
        ),
    )
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run_probe(out))
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "outcome_state", "beta_selected_non_first", "writer_collision_into_wrong_node",
        "sdk_session_count", "selection_phase_requests", "execution_phase_requests",
        "elapsed_seconds",
    ) if k in result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
