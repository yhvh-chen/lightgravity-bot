#!/usr/bin/env python3
"""LG-032 FINAL-COHORT formal attempt driver (frozen protocol; one attempt per call).

This is the SAME code path used by the offline hard gate, the dry-run and the
formal attempt -- only the upstream (local fake vs real DeepSeek) and the base
directory differ (dry uses a sibling ``-dry`` root so a fake-upstream run can
never consume the formal phase ledger's reservations).

Hard properties:

* Runs the **real product assembly** via ``build_runtime`` (real executor, real
  ``GraphDispatcher``, real ``Coordinator`` worker loop, real
  ``VerificationService`` + ``StoreResourceStopper`` whose ``session_confirmer``
  is the adapter's ``confirm_stopped``, real independent ``ModelReviewer``).
  The Task is created over real HTTP; pending review is drained by the real
  ``Coordinator`` loop.  No hand-edited control state, no prefilled
  ``cleanup=done``, no deleted refs, no fabricated ``confirmed``.
* The only experimental manipulation is the **frozen, program-validated plan**
  (arm A = 1 merged write node + verify; arm B = 2 independent write nodes +
  verify) plus, for arm B only, enabling the frozen product candidate-pool
  switch so a real worker autonomously claims one of the legal ready candidates.
* Measurement: ONE persistent phase ledger (limit 192) shared by every stage,
  plus a per-attempt secondary cap of 48 enforced **before a request is
  forwarded** on the *global* counter.
* Persistence: FileStore SoT, ledger and attempt output live in the shared phase
  root; per-attempt isolation uses ``attempts/<id>/{workspaces,secrets}`` and a
  distinct ``workspace_ref`` -- never swapping ``data_dir``.
* Attempt output is an immutable ``runs/<attempt-id>/`` created once; a one-time
  guard refuses a second formal run of the same attempt-id.
* **Pre-first-request ledger assertion (G5)**: the runtime diagnosis ledger path
  / persistent flag / real counter object / physical JSONL are all checked
  against the frozen path *before* the Task is created.

Usage::

    DEEPSEEK_API_KEY=... .venv/bin/python \
        probes/lg032/FINAL-COHORT/harness/run_attempt.py --sample s1_units --arm A
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import final_cohort_config as C  # noqa: E402

# Pin the ONE phase ledger/limit BEFORE any runtime/proxy is built, so worker,
# selector, verifier and reviewer share the same persistent hard cap.
os.environ.update(C.phase_env())

# The product resolves a plan's capabilities through a *role catalog*.  The
# default catalog maps every capability to every enabled agent in sorted order
# (preferring non-default), which would bind BOTH the write node and the
# read-only verify node to the same sorted-first agent.  The frozen protocol
# requires the write node to use the write-capable worker agent and the verify
# node the read-only verifier agent, so declare that catalog explicitly -- a
# supported product configuration input (`LIGHTGRAVITY_ROLE_CATALOG`), NOT a
# control-state edit or a bypass.
os.environ["LIGHTGRAVITY_ROLE_CATALOG"] = json.dumps(
    {
        "implementation": ["lg032-worker"],
        "verification": ["lg032-verifier"],
    }
)


def _assert_frozen_identity() -> None:
    import importlib.metadata as md

    installed = md.version("google-antigravity")
    if installed != C.SDK_VERSION:
        raise SystemExit(f"frozen protocol violated: SDK {installed} != {C.SDK_VERSION}")
    from lightgravity.contracts import CONTRACT_VERSION

    if CONTRACT_VERSION != C.CONTRACT_VERSION:
        raise SystemExit(
            f"frozen protocol violated: contract {CONTRACT_VERSION} != {C.CONTRACT_VERSION}"
        )


# --------------------------------------------------------------- frozen plans
#: Per-sample objective text, acceptance criteria source and the arm-B split.
SAMPLE_SPEC: dict[str, dict[str, Any]] = {
    "s1_units": {
        "title": "LG-032 final-cohort s1 units",
        "objective": (
            "Complete BOTH stub files so the acceptance criteria hold. "
            "src/labels.py must define slugify(title) -> str: lowercase, replace any run of "
            "non-[a-z0-9] characters with a single '-', then strip leading/trailing '-'. "
            "src/numeric.py must define clamp(value, lo, hi) (return lo if value<lo, hi if "
            "value>hi, else value) and in_range(value, lo, hi) -> bool (True iff lo<=v<=hi). "
            "Both files already exist as NotImplementedError stubs: OVERWRITE them. "
            "Do NOT call view_file. Write each file with ONE create_file call and stop."
        ),
        "acceptance": (
            "slugify lowercases, collapses runs of non-alphanumerics to '-', trims '-'",
            "clamp clamps to [lo, hi]; in_range returns True iff lo <= v <= hi",
        ),
        "objective_a": (
            "Part A: overwrite src/labels.py (already an existing stub) so it defines "
            "slugify(title) -> str: lowercase; replace any run of non-[a-z0-9] characters with "
            "a single '-'; strip leading/trailing '-'. Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop."
        ),
        "objective_b": (
            "Part B: overwrite src/numeric.py (already an existing stub) so it defines "
            "clamp(value, lo, hi) (return lo if value<lo, hi if value>hi, else value) and "
            "in_range(value, lo, hi) -> bool (True iff lo<=v<=hi). Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop. "
            "This is independent of part A's file."
        ),
        "files": ("src/labels.py", "src/numeric.py"),
    },
    "s2_pipeline": {
        "title": "LG-032 final-cohort s2 pipeline",
        "objective": (
            "Complete BOTH stub files so the acceptance criteria hold. "
            "src/shapes.py must define area(shape) and perimeter(shape) for shapes that are dicts "
            "with kind in {rect, circle}: rect uses width,height; circle uses radius and math.pi; "
            "an unknown kind raises ValueError. src/report.py must define describe(shape) returning "
            "f\"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}\" and it "
            "must import area, perimeter from .shapes. Both files already exist as stubs: "
            "OVERWRITE them. Do NOT call view_file. Write each file with ONE create_file call and stop."
        ),
        "acceptance": (
            "area/perimeter support rect{width,height} and circle{radius}, unknown kind raises ValueError",
            "describe(shape) == '<kind>: area=%.2f perimeter=%.2f' and uses shapes",
        ),
        "objective_a": (
            "Part A: overwrite src/shapes.py (already an existing stub) so it defines area(shape) "
            "and perimeter(shape) for dict shapes with kind in {rect, circle}: rect uses width,height; "
            "circle uses radius and math.pi; unknown kind raises ValueError. Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop."
        ),
        "objective_b": (
            "Part B (depends on part A's src/shapes.py): overwrite src/report.py (already an "
            "existing stub) so it imports area, perimeter from .shapes and defines "
            "describe(shape) returning f\"{shape['kind']}: area={area(shape):.2f} "
            "perimeter={perimeter(shape):.2f}\". Do NOT call view_file. Write it with ONE "
            "create_file call (or edit_file) and stop."
        ),
        "files": ("src/shapes.py", "src/report.py"),
    },
}

#: Frozen worker prompt template (identical for both arms and both samples).
WORKER_PROMPT_BODY = (
    "You are one implementation worker. You work ONLY in your own workspace. The program "
    "fixes your identity and gives you exactly one assigned node objective. The target files "
    "ALREADY EXIST as failing stubs; OVERWRITE their contents with a correct implementation "
    "matching the acceptance criteria. Use as few turns as possible: call create_file (or "
    "edit_file) ONCE per target file named in your objective to write the full correct "
    "implementation, then stop. Do NOT call view_file. Do not explore. Never write outside "
    "your workspace.\n"
)

#: Frozen verify-node prompt template (read-only, second Member).
VERIFY_PROMPT_BODY = (
    "You are the independent verification member. You have READ-ONLY tools. Read the upstream "
    "artifacts named in your objective and report their exact contents. Do not write anything "
    "and do not modify any file.\n"
)


class _FrozenPlanner:
    """Deterministic program-side plan frozen *before* the attempt.

    Emitted plans are validated by the product ``PlanValidator`` exactly like the
    product's own rule plan.  This is the experimental mechanism that sets the
    number of write nodes (arm A = 1 merged write node, arm B = 2 independent
    write nodes); it is not a control-state edit.
    """

    def __init__(self, arm: str, sample: str) -> None:
        self.name = f"lg032-final-frozen-{arm}"
        self._arm = arm
        self._sample = sample

    async def plan(self, context: Any) -> Any:
        from lightgravity.coordinator.planner import PlanProposal, RawSubtask

        spec = SAMPLE_SPEC[self._sample]
        acceptance = tuple(context.acceptance_criteria) or tuple(spec["acceptance"])
        if self._arm == "A":
            subtasks = (
                RawSubtask(
                    key="deliver",
                    objective=context.objective,
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
                RawSubtask(
                    key="verify",
                    objective=(
                        "Read the delivered artifacts and report their exact contents: "
                        + ", ".join(spec["files"])
                        + ". Read-only: do not write."
                    ),
                    capability="verification",
                    acceptance=acceptance,
                    depends_on=("deliver",),
                    write=False,
                ),
            )
        else:
            subtasks = (
                RawSubtask(
                    key="alpha",
                    objective=spec["objective_a"],
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
                RawSubtask(
                    key="beta",
                    objective=spec["objective_b"],
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
                RawSubtask(
                    key="verify",
                    objective=(
                        "Read the two upstream artifacts and report their exact contents and "
                        "upstream hashes: "
                        + ", ".join(spec["files"])
                        + ". Read-only: do not write."
                    ),
                    capability="verification",
                    acceptance=acceptance,
                    depends_on=("alpha", "beta"),
                    write=False,
                ),
            )
        return PlanProposal(
            subtasks=subtasks,
            source=f"lg032-final-frozen-{self._arm}",
            notes=(f"LG-032 FINAL-COHORT frozen plan for arm {self._arm}",),
        )


# ------------------------------------------------------------------- helpers
class _AttemptGuard:
    """Per-attempt cap enforced on the *global* counter before forwarding.

    ``GenerationCounter.reserve()`` returns ``bool`` (the defunct 023 guard
    checked ``.granted`` on a ``bool`` and silently never counted).
    """

    def __init__(self, counter: Any, limit: int) -> None:
        self._counter = counter
        self._limit = limit
        self._used = 0
        self._orig = counter.reserve

    def install(self) -> None:
        guard = self

        def guarded() -> bool:
            if guard._used >= guard._limit:
                return False
            granted = guard._orig()
            if granted:
                guard._used += 1
            return granted

        self._counter.reserve = guarded  # type: ignore[method-assign]

    @property
    def used(self) -> int:
        return self._used


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method: str, url: str, *, body: Any = None, headers: dict[str, str] | None = None,
          timeout: float = C.HTTP_TIMEOUT_SECONDS) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"_raw": raw}
        return exc.code, parsed


def _wait_for(predicate: Any, timeout: float, interval: float = 0.4) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _init_repo(root: Path, initial: Path) -> str:
    """Freeze the candidate workspace from the fixture ``initial/`` tree.

    The workspace is a real git repository so the product's per-write-node
    isolation applies (arm B two nodes get distinct worktrees).  The frozen
    start identity is the initial commit hash.

    Preservation: ``root`` must be a caller-owned, uniquely-named path under
    this run's own attempt root.  Refuse to touch anything else so a history /
    formal path can never be clobbered.
    """

    if root.exists() and "workspaces" not in root.parts:
        raise SystemExit(
            f"_init_repo refusing to remove non-attempt path {root} "
            "(preservation: only this run's own candidate-ws may be reused)"
        )
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(initial, root)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "lg032",
        "GIT_AUTHOR_EMAIL": "lg032@local",
        "GIT_COMMITTER_NAME": "lg032",
        "GIT_COMMITTER_EMAIL": "lg032@local",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture initial"],
                   cwd=root, check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()
    return head


def _materialize_candidate(initial_dir: Path, patch_path: Path, dest: Path) -> bool:
    """Apply the run's own candidate diff onto a fresh copy of the fixture.

    The product's real candidate is the isolated per-node worktree diff it
    records as ``lg006-diff.patch``; the machine truth must run against that
    candidate, not the untouched start workspace.  ``dest`` is a brand-new
    unique path (never deleted/overwritten).
    """

    if dest.exists():
        raise SystemExit(f"refusing to reuse candidate dir {dest}")
    shutil.copytree(initial_dir, dest)
    if not patch_path.exists():
        return False
    proc = subprocess.run(
        ["git", "apply", "--unsafe-paths", "-p1", str(patch_path)],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _machine_gate(workspace: Path, acceptance_script: Path) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    proc = subprocess.run(
        [sys.executable, str(acceptance_script), "--workspace", str(workspace)],
        capture_output=True, text=True, timeout=C.HTTP_TIMEOUT_SECONDS, env=env,
    )
    lines = proc.stdout.strip().splitlines()
    try:
        report = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        report = {"raw": proc.stdout, "stderr": proc.stderr}
    report["exit_code"] = proc.returncode
    return report


def _data_dir_for(dry_run: bool, dry_label: str = "dry") -> Path:
    """The phase ``settings.data_dir``.

    Formal runs use the ONE fixed persistent phase root.  A dry (fake-upstream)
    run uses a **brand-new unique** root each invocation so no earlier attempt
    output is ever overwritten or deleted; the legacy fixed ``-dry`` path is
    preserved as history and is never written to again.
    """

    if dry_run:
        return C.new_dry_root(dry_label)
    return C.PHASE_DATA_DIR


# --------------------------------------------------------------- main attempt
def run_attempt(sample: str, arm: str, *, dry_run: bool = False,
                fake_upstream: str | None = None, dry_label: str = "dry") -> int:
    if (sample, arm) not in C.ATTEMPTS:
        raise SystemExit(f"unknown attempt {sample}__{arm}")
    _assert_frozen_identity()

    data_dir = _data_dir_for(dry_run, dry_label)
    attempt_id = f"{sample}__{arm}"
    if dry_run:
        # Unique, freshly-created output dir -- never rmtree, never reuse.
        out_dir = data_dir / "offline_dry_run_output" / attempt_id
        if out_dir.exists():
            raise SystemExit(
                f"refusing to reuse existing dry output {out_dir} "
                "(preservation: every dry run gets a unique root)"
            )
        out_dir.mkdir(parents=True)
    else:
        out_dir = C.RUNS_DIR / attempt_id
        if out_dir.exists():
            raise SystemExit(
                f"refusing to overwrite existing attempt output {out_dir} "
                "(attempt outputs are immutable; use a fresh cohort/phase)"
            )
        out_dir.mkdir(parents=True)
        (out_dir / ".formal_attempt_started").write_text(str(time.time()), encoding="utf-8")

    credential = os.environ.get("DEEPSEEK_API_KEY")
    if not credential:
        (out_dir / "result.json").write_text(
            json.dumps({"status": "skipped", "reason": "no DEEPSEEK_API_KEY in env"}, indent=2),
            encoding="utf-8",
        )
        return 1

    started = time.monotonic()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(C.TOTAL_GENERATION_LIMIT)

    run_root = data_dir / "attempts" / attempt_id
    workspace_root = run_root / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    secret_store_root = run_root / "secrets"
    secret_store_root.mkdir(parents=True, exist_ok=True)

    from lightgravity.config import Settings
    from lightgravity.runtime.token import RuntimeToken
    from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime

    settings = Settings(
        data_dir=data_dir,                   # <-- shared phase root (fix D1)
        workspace_root=workspace_root,       # <-- per-attempt isolation
        secret_store=secret_store_root,      # <-- per-attempt isolation
        host="127.0.0.1",
        port=0,
    )
    settings.ensure_data_dir()

    base_url = fake_upstream or C.BASE_URL
    _seed_resources(settings, credential, base_url=base_url)

    # arm B (and only arm B) enables the frozen candidate-pool switch BEFORE the
    # runtime is built, so the product dispatcher wires autonomous_pool.  arm A
    # keeps the deterministic single-node path (autonomous claim off).
    if arm == "B":
        _enable_decentralized_pool(settings)

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("lg032-token", "generated"),
            serve_frontend=False,
            max_proxy_calls=C.ATTEMPT_GENERATION_LIMIT,
            model_calls_cap=C.ATTEMPT_GENERATION_LIMIT,
        )
    )

    import lightgravity.adapter.proxy as proxy_mod

    counter = proxy_mod.global_generation_counter()
    guard = _AttemptGuard(counter, C.ATTEMPT_GENERATION_LIMIT)
    guard.install()
    proxy_mod._GLOBAL_GENERATION_COUNTER = counter  # type: ignore[attr-defined]

    if dry_run:
        _enable_loopback_for_dry_run(state)

    # Narrow diagnostic hook (opt-in via env; harness-only observer, no product
    # edit).  Records every executor request/exception to LG032_DIAG_OUT.
    if os.environ.get("LG032_DIAG_EXECUTOR"):
        import diag_wrap  # noqa: PLC0415

        if state.executor is not None:
            diag_wrap.install(state.executor)

    coordinator = state.app.state.coordinator
    dispatcher = coordinator.dispatcher
    if dispatcher is None or not hasattr(dispatcher, "_program_planner"):
        raise SystemExit("real GraphDispatcher was not assembled; refusing to fake the run")
    dispatcher._program_planner = _FrozenPlanner(arm, sample)  # type: ignore[attr-defined]
    if arm == "B":
        if not getattr(dispatcher, "_autonomous_pool", False):
            raise SystemExit(
                "arm B requires the product candidate-pool path; refusing to fake the run"
            )

    # The real CoordinatorWorkerLoop is started by the product app's own
    # FastAPI ``lifespan`` when uvicorn boots below -- exactly the production
    # path.  Calling ``coordinator.start()`` here would run outside an event
    # loop; the product starts it inside the loop, so we do not duplicate it.

    initial_dir = C.FIXTURES_DIR / sample / "initial"
    candidate_ws = workspace_root / "candidate-ws"
    initial_head = _init_repo(candidate_ws, initial_dir)

    import uvicorn

    port = _free_port()
    config = uvicorn.Config(state.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}/api/v1"
    results: dict[str, Any] = {
        "attempt_id": attempt_id,
        "sample": sample,
        "arm": arm,
        "initial_head": initial_head,
        "phase_data_dir": str(data_dir),
        "frozen_ledger_history": str(data_dir / "generation" / "generation.jsonl"),
        "total_limit": C.TOTAL_GENERATION_LIMIT,
        "attempt_limit": C.ATTEMPT_GENERATION_LIMIT,
        "caller": "agent:pi-lg032-final-cohort",
        "steps": [],
    }

    def gen() -> dict[str, Any]:
        try:
            return _http("GET", f"{base}/diagnostics/generation")[1].get("generation", {})
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}

    def step(name: str, ok: bool, **detail: Any) -> None:
        results["steps"].append({"name": name, "ok": bool(ok), **detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)

    def _ledger_identity() -> dict[str, Any]:
        frozen_history = data_dir / "generation" / "generation.jsonl"
        ident: dict[str, Any] = {
            "frozen_history_path": str(frozen_history),
            "frozen_phase_data_dir": str(data_dir),
        }
        ledger = getattr(counter, "_ledger", None) or getattr(counter, "ledger", None)
        ident["counter_is_global"] = counter is proxy_mod.global_generation_counter()
        if ledger is not None:
            hist = getattr(ledger, "_history", None)
            ident["counter_ledger_history"] = str(hist) if hist is not None else None
            ident["counter_ledger_matches_frozen"] = (
                hist is not None and Path(hist).resolve() == frozen_history.resolve()
            )
        else:
            ident["counter_ledger_history"] = None
            ident["counter_ledger_matches_frozen"] = False
        ident["physical_history_exists_at_freeze"] = frozen_history.exists()
        return ident

    final_phase = ""
    try:
        if not _wait_for(lambda: getattr(server, "started", False), 20):
            step("server_started", False)
            raise RuntimeError("server did not start")
        step("health_ok", _http("GET", f"{base}/health")[0] == 200)
        report = state.execution_report()
        step("execution_ready", report["execution_ready"] is True, reasons=report["reasons"])
        step("reviewer_wired_model", report.get("reviewer", {}).get("reviewer") == "model",
             reviewer=report.get("reviewer"))

        # ---------------------------------------------------------- G5 freeze
        ident = _ledger_identity()
        results["ledger_identity_at_freeze"] = ident
        gen0 = gen()
        step("ledger_persistent_single_path",
             gen0.get("persistent") is True and gen0.get("limit") == C.TOTAL_GENERATION_LIMIT,
             generation=gen0)
        step("counter_ledger_matches_frozen_path",
             bool(ident.get("counter_ledger_matches_frozen")) and bool(ident.get("counter_is_global")),
             identity=ident)

        spec = SAMPLE_SPEC[sample]
        body = {
            "request_id": f"lg032-{attempt_id}-task",
            "title": spec["title"],
            "objective": spec["objective"],
            "acceptance_criteria": list(spec["acceptance"]),
            "workspace_ref": "candidate-ws",
        }
        code, task = _http("POST", f"{base}/tasks", body=body)
        task_id = task.get("task_id")
        step("task_created", code == 200 and bool(task_id), code=code, task_id=task_id)

        terminal = {"awaiting_acceptance", "waiting_user", "failed", "completed",
                    "recovery_required", "cancelled"}
        phases_seen: set[str] = set()

        def poll() -> str:
            deadline = time.time() + 420
            last = ""
            while time.time() < deadline:
                d = _http("GET", f"{base}/tasks/{task_id}")[1]
                last = d.get("phase", "")
                phases_seen.add(last)
                if last in terminal:
                    return last
                time.sleep(0.5)
            return last

        final_phase = poll()
        results["phases_seen"] = sorted(phases_seen)
        step("run_reached_awaiting_acceptance", final_phase == "awaiting_acceptance",
             phase=final_phase, phases_seen=sorted(phases_seen))

        detail = _http("GET", f"{base}/tasks/{task_id}")[1]
        run = detail.get("run") or {}
        run_id = run.get("id")
        results["task_after_run"] = detail
        results["task_id"] = task_id
        results["run_id"] = run_id

        # Machine truth runs against the run's REAL candidate: apply the
        # product-recorded diff onto a fresh copy of the frozen fixture.
        patch = data_dir / "artifacts" / (run_id or "") / "lg006-diff.patch"
        candidate_dir = workspace_root / "candidate-eval"
        applied = _materialize_candidate(initial_dir, patch, candidate_dir)
        results["candidate_patch"] = str(patch)
        results["candidate_patch_applied"] = applied
        machine = _machine_gate(candidate_dir, C.FIXTURES_DIR / sample / "acceptance.py")
        results["machine_gate"] = machine
        results["machine_pass"] = (
            machine.get("passed") == machine.get("total") and machine.get("total", 0) > 0
        )
        step("machine_gate_pass", results["machine_pass"], machine=machine)

        review = _review_from_store(state, task_id)
        results["review"] = review

        session_refs = run.get("session_refs") or []
        cleanup = run.get("cleanup") or {}
        reviewer_cleanup = run.get("reviewer_cleanup")
        results["session_refs"] = session_refs
        results["cleanup"] = cleanup
        results["reviewer_cleanup"] = reviewer_cleanup
        step("real_session_refs_recorded", len(session_refs) >= 1, session_refs=session_refs)
        step("reviewer_real_teardown_recorded",
             isinstance(reviewer_cleanup, dict) and reviewer_cleanup.get("confirmed") is True,
             reviewer_cleanup=reviewer_cleanup)

        # ---- bind accept through the real acceptance service
        req_rev = detail.get("requirements_revision")
        accept_body = {
            "action": "accept",
            "request_id": f"lg032-{attempt_id}-accept",
            "target_run_id": run_id,
            "expected_requirements_revision": req_rev,
        }
        acode, ares = _http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                            headers={"X-LG-Token": "lg032-token"})
        results["accept_response"] = ares
        acc = ares.get("acceptance") or {}
        accepted = (
            acode == 200 and ares.get("state") == "confirmed"
            and acc.get("status") == "accepted" and ares.get("candidate_ref") == run_id
        )
        step("accept_confirmed_bound", accepted, code=acode, state=ares.get("state"),
             acceptance=acc, candidate_ref=ares.get("candidate_ref"))

        gen_final = gen()
        results["generation_final"] = gen_final
        results["attempt_generation_requests"] = guard.used

        results["sample_delivered"] = bool(
            results["machine_pass"] and accepted
            and str(review.get("validated_outcome", review.get("outcome", ""))) == "passed"
        )
        results["first_round_machine_pass"] = results["machine_pass"]
    except Exception as exc:  # noqa: BLE001 - record the real failure, never fake success
        results["driver_error"] = f"{type(exc).__name__}: {exc}"
        step("driver_completed", False, error=results["driver_error"])
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        results["final_phase"] = final_phase
        results["elapsed_seconds"] = round(time.monotonic() - started, 2)
        results["global_ledger"] = _safe(gen)
        results["ok"] = all(s["ok"] for s in results["steps"])
        (out_dir / "result.json").write_text(
            json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        if not dry_run:
            (C.EVIDENCE_DIR / f"{attempt_id}.json").write_text(
                json.dumps(results, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
        print(f"WROTE {out_dir / 'result.json'}", flush=True)
    return 0 if results.get("ok") else 1


def _safe(fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _review_from_store(state: Any, task_id: str) -> dict[str, Any]:
    """Read the real review outcome the coordinator recorded (no extra calls)."""

    store = state.store
    out: dict[str, Any] = {"source": "recorded_events"}
    try:
        events = store.read_events(task_id) if hasattr(store, "read_events") else []
    except Exception as exc:  # noqa: BLE001
        return {"source": "recorded_events", "error": f"{type(exc).__name__}: {exc}"}
    review_events = []
    for e in events:
        rec = getattr(e, "event", None)
        if not isinstance(rec, dict):
            continue
        payload = rec.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("mode") == "review":
            review_events.append({"type": rec.get("type"), "payload": payload})
    out["events"] = review_events[-5:]
    if review_events:
        last = review_events[-1]["payload"]
        for key in ("outcome", "validated_outcome", "reason", "findings", "unsubstantiated",
                    "code", "reviewer"):
            if key in last:
                out[key] = last[key]
    out["outcome"] = out.get("outcome", "unknown")
    out["validated_outcome"] = out.get("validated_outcome", out["outcome"])
    return out


def _enable_decentralized_pool(settings: Any) -> None:
    """Write the frozen product switch for arm B (candidate-pool autonomous claim).

    The decentralized switch lives on the product ``settings`` entity
    (``decentralized_claim_enabled``); the product ``build_runtime`` reads it
    through ``ClaimPolicyReader`` and wires ``autonomous_claim`` +
    ``autonomous_pool``.  Uses the product's own controlled settings write; the
    value is part of the frozen protocol, not a control-state edit.
    """

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    try:
        current = store.read("settings", "settings").revision
    except Exception:  # noqa: BLE001
        current = None
    conns.update_settings(
        expected_revision=current,
        actor="lg032",
        default_worker_connection_ref="lg032-worker",
        decentralized_claim_enabled=True,
    )


def _seed_resources(settings: Any, credential: str, *, base_url: str = C.BASE_URL) -> None:
    """Seed the frozen worker + verifier agents, connections, tools and credential."""

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore, EntityNotFound

    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))

    def ensure_connection(cid: str) -> None:
        try:
            store.read("connection", cid)
            return
        except EntityNotFound:
            pass
        conns.create_connection(
            connection_id=cid, backend="openai-compat", model=C.MODEL,
            base_url=base_url, credential_ref=C.CREDENTIAL_REF, title=cid,
            actor="lg032", request_id=f"lg032-conn-{cid}",
        )

    ensure_connection("lg032-worker")
    ensure_connection("lg032-reviewer")

    secret_store = FileSecretStore(settings.secret_store)
    if secret_store.get(C.CREDENTIAL_REF) is None:
        secret_store.put(C.CREDENTIAL_REF, credential)

    expected_rev = None
    try:
        expected_rev = store.read("settings", "settings").revision
    except EntityNotFound:
        expected_rev = None
    conns.update_settings(
        expected_revision=expected_rev,
        actor="lg032",
        default_coordinator_connection_ref="lg032-worker",
        default_worker_connection_ref="lg032-worker",
        default_reviewer_connection_ref="lg032-reviewer",
    )

    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        try:
            store.read(kind, entity_id)
            return
        except EntityNotFound:
            pass
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="lg032",
                     request_id=f"lg032-{kind}-{entity_id}", body=body)

    for tool_id in ("view-file", "create-file", "edit-file"):
        create("tool", tool_id, {"implementation": tool_id})
    create("skill", "implementation", {"description": "Implementation"}, "# Impl\n")
    create("skill", "verification", {"description": "Verification"}, "# Verify\n")
    create(
        "agent",
        "lg032-worker",
        {
            "connection_ref": "lg032-worker",
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": ["implementation"]},
            "tool_refs": ["view-file", "create-file", "edit-file"],
            "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": [],
        },
        body=WORKER_PROMPT_BODY,
    )
    create(
        "agent",
        "lg032-verifier",
        {
            "connection_ref": "lg032-worker",
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": ["verification"]},
            # read-only tool set: no write tool
            "tool_refs": ["view-file"],
            "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": [],
        },
        body=VERIFY_PROMPT_BODY,
    )


def _enable_loopback_for_dry_run(state: Any) -> None:
    """Offline-only: let the real executor/reviewer/dialogue proxies reach a
    local fake upstream.

    The product already exposes this as a real, supported constructor flag
    (``LocalAuthProxy(allow_loopback_upstream=...)``); it is *not* a bypass of
    the loopback guard.  Worker proxies are built by the executor from
    ``executor._allow_loopback_upstream``; the reviewer (``verify.review``) and
    dialogue build their own ``LocalAuthProxy`` directly, so we wrap the class
    ``__init__`` (preserving class identity and all attributes) to default the
    flag to ``True`` for *offline fake upstream only*.  No real credential is
    used; the fake host is loopback.
    """

    executor = state.executor
    if executor is not None:
        executor._allow_loopback_upstream = True  # type: ignore[attr-defined]
    # LG-032 workspace-boundary: the selection scratch is now rooted inside the
    # executor's authorized root by the product fix (WorktreeManager
    # selection_scratch_root), so no harness-side root widening is needed or
    # allowed.  The former LG032_WIDEN_EXEC_ROOT debug escape hatch (which
    # rewrote executor._workspace_root to the data root / sibling worktrees) is
    # REMOVED from the formal path; its snapshot is retained in git history.
    # Refuse loudly if the variable is set so a widened root can never mask the
    # real boundary in a formal or dry run.
    if os.environ.get("LG032_WIDEN_EXEC_ROOT"):
        raise SystemExit(
            "LG032_WIDEN_EXEC_ROOT is a removed debug aid and must not be set "
            "(the selection scratch is inside the authorized root via the "
            "product fix); refusing to widen the executor root"
        )
    import lightgravity.adapter.proxy as proxy_mod

    cls = proxy_mod.LocalAuthProxy
    if getattr(cls, "_lg032_loopback_patched", False):
        return
    orig_init = cls.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("allow_loopback_upstream", True)
        orig_init(self, *args, **kwargs)

    cls.__init__ = patched_init  # type: ignore[method-assign]
    cls._lg032_loopback_patched = True  # type: ignore[attr-defined]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(SAMPLE_SPEC))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fake-upstream", default=None)
    ap.add_argument("--dry-label", default="dry",
                    help="suffix label for a unique dry root (preservation)")
    args = ap.parse_args()
    return run_attempt(args.sample, args.arm, dry_run=args.dry_run,
                       fake_upstream=args.fake_upstream, dry_label=args.dry_label)


if __name__ == "__main__":
    raise SystemExit(main())
