#!/usr/bin/env python3
"""LG-023 cohort-3 formal attempt driver (frozen protocol; one attempt per call).

Derived from the cohort-2 driver but **fixes the audited harness defect D1**: the
whole phase shares ONE real ``settings.data_dir`` (``cohort3_config.PHASE_DATA_DIR``)
for every serial attempt and every runtime start.  Because the product
``build_runtime`` calls ``configure_generation_ledger(settings.data_dir)``
unconditionally, a single phase data_dir makes the mature product ledger
naturally continue the same physical JSONL -- no per-attempt ``data_dir`` swap,
no post-build counter re-pin, no second env pin, and **no product source change**.

Hard properties (see ``cohort3_config.py`` for the frozen numbers):

* Runs the **real product assembly** via ``build_runtime`` (real executor, real
  Coordinator/GraphDispatcher, real ``VerificationService``, real
  ``StoreResourceStopper`` whose ``session_confirmer`` is the adapter's
  ``confirm_stopped``, real independent ``ModelReviewer``).  The Task is created
  over real HTTP; no hand-edited control state, no prefilled ``cleanup=done``,
  no deleted refs, no fabricated ``confirmed``.
* The only experimental manipulation is the **frozen, program-validated plan**
  (arm A = 1 write node, arm B = 2 dependent write nodes); validated by the
  product ``PlanValidator``.  It only varies write-node count.
* Measurement: ONE persistent phase ledger (limit 48) shared by worker +
  reviewer + any retry; a per-attempt secondary cap of 12 enforced **before a
  request is forwarded** on the *global* counter.  The guard returns ``bool``.
* Persistence: FileStore SoT, ledger and attempt output live in the shared phase
  root; per-attempt isolation uses ``attempts/<id>/{workspaces,secrets}`` and a
  distinct ``workspace_ref`` -- never swapping ``data_dir`` and never deleting a
  previous Task/Run.
* Attempt output is an immutable ``runs/<attempt-id>/`` created once; a one-time
  guard refuses a second formal run of the same attempt-id.
* **Pre-first-request ledger assertion (G5)**: the runtime diagnosis ledger
  path / persistent flag / real counter object / physical JSONL are all checked
  against the frozen path *before* the Task is created.

Usage::

    DEEPSEEK_API_KEY=... .venv/bin/python \\
        probes/lg023/cohort3/harness/run_attempt.py --sample s1_independent --arm A
"""

from __future__ import annotations

import argparse
import asyncio
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

import cohort3_config as C  # noqa: E402

# Pin the ONE phase ledger/limit BEFORE any runtime/proxy is built, so worker and
# reviewer share the same persistent hard cap.  This is consistent with (not a
# replacement for) the product's own ``configure_generation_ledger(data_dir)``.
os.environ.update(C.phase_env())


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
SAMPLE_SPEC: dict[str, dict[str, Any]] = {
    "s1_independent": {
        "title": "LG-023 cohort3 s1 independent",
        "objective": (
            "Complete BOTH stub files so the acceptance criteria hold. "
            "src/slugs.py must define slugify(title: str) -> str: lowercase, replace any run of "
            "non-[a-z0-9] characters with a single '-', then strip leading/trailing '-'. "
            "src/ranges.py must define clamp(value, lo, hi) (return lo if value<lo, hi if value>hi, "
            "else value) and in_range(value, lo, hi) -> bool (True iff lo<=value<=hi). "
            "Both files already exist as NotImplementedError stubs: OVERWRITE them. "
            "Do NOT call view_file. Write each file with ONE create_file call and stop."
        ),
        "acceptance": (
            "slugify lowercases, collapses runs of non-alphanumerics to '-', trims '-'",
            "clamp clamps to [lo, hi]; in_range returns True iff lo <= v <= hi",
        ),
        "objective_a": (
            "Part A: overwrite src/slugs.py (already an existing stub) so it defines "
            "slugify(title: str) -> str: lowercase; replace any run of non-[a-z0-9] characters "
            "with a single '-'; strip leading/trailing '-'. Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop."
        ),
        "objective_b": (
            "Part B: overwrite src/ranges.py (already an existing stub) so it defines "
            "clamp(value, lo, hi) (return lo if value<lo, hi if value>hi, else value) and "
            "in_range(value, lo, hi) -> bool (True iff lo<=value<=hi). Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop. "
            "This is independent of part A's file."
        ),
    },
    "s2_interface": {
        "title": "LG-023 cohort3 s2 interface",
        "objective": (
            "Complete BOTH stub files so the acceptance criteria hold. "
            "src/geometry.py must define area(shape) and perimeter(shape) for shapes that are dicts "
            "with kind in {rect, circle}: rect uses width,height; circle uses radius and math.pi; "
            "an unknown kind raises ValueError. src/report.py must define describe(shape) returning "
            "f\"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}\" and it "
            "must import area, perimeter from .geometry. Both files already exist as stubs: "
            "OVERWRITE them. Do NOT call view_file. Write each file with ONE create_file call and stop."
        ),
        "acceptance": (
            "area/perimeter support rect{width,height} and circle{radius}, unknown kind raises ValueError",
            "describe(shape) == '<kind>: area=%.2f perimeter=%.2f' and uses geometry",
        ),
        "objective_a": (
            "Part A: overwrite src/geometry.py (already an existing stub) so it defines area(shape) "
            "and perimeter(shape) for dict shapes with kind in {rect, circle}: rect uses width,height; "
            "circle uses radius and math.pi; unknown kind raises ValueError. Do NOT call view_file. "
            "Write it with ONE create_file call (or edit_file) and stop."
        ),
        "objective_b": (
            "Part B (depends on part A's src/geometry.py): overwrite src/report.py (already an "
            "existing stub) so it imports area, perimeter from .geometry and defines "
            "describe(shape) returning f\"{shape['kind']}: area={area(shape):.2f} "
            "perimeter={perimeter(shape):.2f}\". Do NOT call view_file. Write it with ONE "
            "create_file call (or edit_file) and stop."
        ),
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


class _FrozenPlanner:
    """Deterministic program-side plan frozen *before* the attempt.

    Emitted plans are validated by the product ``PlanValidator`` exactly like the
    product's own rule plan.  This is the experimental mechanism that sets the
    number of write nodes (arm A = 1, arm B = 2 dependent nodes); it is not a
    control-state edit and not an autonomous-planning capability comparison.
    """

    def __init__(self, arm: str, sample: str) -> None:
        self.name = f"cohort3-frozen-{arm}"
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
            )
        else:
            subtasks = (
                RawSubtask(
                    key="part_a",
                    objective=spec["objective_a"],
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
                RawSubtask(
                    key="part_b",
                    objective=spec["objective_b"],
                    capability="implementation",
                    acceptance=acceptance,
                    depends_on=("part_a",),
                    write=True,
                ),
            )
        return PlanProposal(
            subtasks=subtasks,
            source=f"cohort3-frozen-{self._arm}",
            notes=(f"LG-023 cohort3 frozen plan for arm {self._arm}",),
        )


# ------------------------------------------------------------------- helpers
class _AttemptGuard:
    """Per-attempt cap (12) enforced on the *global* counter before forwarding.

    ``GenerationCounter.reserve()`` returns ``bool``; the old harness checked
    ``.granted`` on a ``bool`` and silently never counted (audited defect D2).
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


def _init_git_repo(root: Path, initial: Path) -> str:
    """Freeze the shared candidate workspace from the fixture ``initial/`` tree.

    The workspace is deliberately a **plain directory**, not a git repo: the
    product's per-write-node git isolation only applies when the base workspace
    is an isolatable git repository, so both arms here fall back to the
    documented conservative single-writer serialization and the workers write
    into the same candidate workspace.  This keeps the only independent variable
    the number of program-planned write nodes (A=1, B=2), exactly like the
    already-passing ``qa/lg022-stream`` workspace (a plain ``ws1`` dir) and the
    one real S1/A delivery the method audit found valid.  The frozen start
    identity is the byte-level ``initial_tree_hash`` recorded with the attempt.
    """

    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(initial, root, dirs_exist_ok=True)
    return _tree_hash(initial)


def _tree_hash(root: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


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


# --------------------------------------------------------------- main attempt
def _data_dir_for(dry_run: bool) -> Path:
    """The phase ``settings.data_dir``.

    Formal attempts and the dry-run use the **same code path**; only the base
    dir differs (the dry-run uses a sibling ``-dry`` root so a fake-upstream run
    can never consume the formal phase ledger's reservations).  Both are single
    phase roots shared by every serial attempt in that mode.
    """

    if dry_run:
        return C.PHASE_DATA_DIR.parent / "lg023-cohort3-data-dry"
    return C.PHASE_DATA_DIR


def run_attempt(sample: str, arm: str, *, dry_run: bool = False,
                fake_upstream: str | None = None) -> int:
    if (sample, arm) not in C.ATTEMPTS:
        raise SystemExit(f"unknown attempt {sample}__{arm}")
    _assert_frozen_identity()

    data_dir = _data_dir_for(dry_run)
    attempt_id = f"{sample}__{arm}"
    if dry_run:
        # Offline wiring check: NEVER touches a formal runs/ output and never
        # contacts DeepSeek (uses a local fake upstream).  It still uses the SAME
        # code path and the SAME single phase data_dir (dry does not skip
        # bootstrap); only the base dir is the controlled dry sibling.
        out_dir = data_dir / "offline_dry_run_output" / attempt_id
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
    else:
        out_dir = C.RUNS_DIR / attempt_id
        if out_dir.exists():
            raise SystemExit(
                f"refusing to overwrite existing attempt output {out_dir} "
                "(attempt outputs are immutable; use a fresh cohort/phase)"
            )
        out_dir.mkdir(parents=True)
        guard_file = out_dir / ".formal_attempt_started"
        guard_file.write_text(str(time.time()), encoding="utf-8")

    credential = os.environ.get("DEEPSEEK_API_KEY")
    if not credential:
        (out_dir / "result.json").write_text(
            json.dumps({"status": "skipped", "reason": "no DEEPSEEK_API_KEY in env"}, indent=2),
            encoding="utf-8",
        )
        return 1

    started = time.monotonic()
    # ---- ONE shared phase data root for the WHOLE phase (fix D1).  This is
    # passed verbatim as Settings.data_dir so the product ledger rooted at
    # data_dir/generation is the single phase ledger.  The env override must
    # match it so a first proxy build before build_runtime resolves the same
    # root.
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(C.PHASE_GENERATION_LIMIT)

    # ---- per-attempt isolation lives OUTSIDE data_dir (workspaces/secrets) so
    # the ledger is never per-attempt and previous Task/Run state is not deleted.
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

    # ---- seed the frozen worker agent + connection, then build the real app
    base_url = fake_upstream or C.BASE_URL
    _seed_resources(settings, credential, base_url=base_url)

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("cohort3-token", "generated"),
            serve_frontend=False,
            max_proxy_calls=C.ATTEMPT_GENERATION_LIMIT,
            model_calls_cap=C.ATTEMPT_GENERATION_LIMIT,
        )
    )

    # ---- install the per-attempt guard on the ONE global counter.  No counter
    # re-pin to a different root: the product already configured the persistent
    # ledger at the shared settings.data_dir above.
    import lightgravity.adapter.proxy as proxy_mod

    counter = proxy_mod.global_generation_counter()
    guard = _AttemptGuard(counter, C.ATTEMPT_GENERATION_LIMIT)
    guard.install()
    proxy_mod._GLOBAL_GENERATION_COUNTER = counter  # type: ignore[attr-defined]

    if dry_run:
        _enable_loopback_for_dry_run(state)

    # ---- inject the frozen program plan (program-validated) into the real graph
    coordinator = state.app.state.coordinator
    dispatcher = coordinator.dispatcher
    if dispatcher is None or not hasattr(dispatcher, "_program_planner"):
        raise SystemExit("real GraphDispatcher was not assembled; refusing to fake the run")
    dispatcher._program_planner = _FrozenPlanner(arm, sample)  # type: ignore[attr-defined]
    # Workspace isolation OFF for BOTH arms, identically: the product's per-node
    # git worktrees are not auto-integrated back into the candidate workspace, so
    # enabling them would make the machine gate read the untouched base tree and
    # break the experiment for both arms.  Disabling it keeps the only
    # independent variable the number of program-planned write nodes; both arms
    # use the documented conservative single-writer serialization on the same
    # shared candidate workspace (as the passing qa/lg022-stream chain does).
    dispatcher._workspaces = None  # type: ignore[attr-defined]

    # ---- candidate workspace: fixture initial tree (plain dir, per attempt)
    initial_dir = C.FIXTURES_DIR / sample / "initial"
    candidate_ws = workspace_root / "candidate-ws"
    initial_tree_hash = _init_git_repo(candidate_ws, initial_dir)
    initial_head = initial_tree_hash  # frozen content identity (plain workspace)

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
        "phase_limit": C.PHASE_GENERATION_LIMIT,
        "attempt_limit": C.ATTEMPT_GENERATION_LIMIT,
        "worker_model_calls": C.WORKER_MODEL_CALLS,
        "worker_tool_calls": C.WORKER_TOOL_CALLS,
        "output_token_cap": C.OUTPUT_TOKEN_CAP,
        "http_timeout": C.HTTP_TIMEOUT_SECONDS,
        "retries": C.SDK_RETRIES,
        "workspace_root": str(workspace_root),
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
        """Freeze the runtime-counter / physical-ledger identity (G5)."""

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
        # Assert the runtime diagnosis ledger path / persistent flag / real
        # counter object / physical JSONL against the frozen path BEFORE the
        # first formal request (first POST /tasks).
        ident = _ledger_identity()
        results["ledger_identity_at_freeze"] = ident
        gen0 = gen()
        step("ledger_persistent_single_path",
             gen0.get("persistent") is True and gen0.get("limit") == C.PHASE_GENERATION_LIMIT,
             generation=gen0)
        # The frozen contract exposes count/limit/remaining/corrupt/persistent
        # but no path, so the path identity is asserted on the real counter
        # object's attached ledger (the actual fact source) plus the physical
        # JSONL location -- stronger than a reported string.
        diag_path = gen0.get("path") or gen0.get("ledger_path") or gen0.get("history")
        results["diagnostic_ledger_path"] = diag_path
        step("counter_ledger_matches_frozen_path",
             bool(ident.get("counter_ledger_matches_frozen")) and bool(ident.get("counter_is_global")),
             identity=ident)
        if diag_path is not None:
            step("diagnostic_path_matches_frozen",
                 str(Path(str(diag_path)).resolve()) == str((data_dir / "generation" / "generation.jsonl").resolve())
                 or str(data_dir.resolve()) in str(Path(str(diag_path)).resolve()),
                 diagnostic_ledger_path=diag_path, frozen=str(data_dir / "generation" / "generation.jsonl"))
        else:
            results["steps"].append({
                "name": "diagnostic_path_matches_frozen", "ok": True,
                "note": "contract exposes no path; asserted on real counter ledger object + physical JSONL",
                "frozen": str(data_dir / "generation" / "generation.jsonl"),
            })

        spec = SAMPLE_SPEC[sample]
        body = {
            "request_id": f"cohort3-{attempt_id}-task",
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

        machine = _machine_gate(candidate_ws, C.FIXTURES_DIR / sample / "acceptance.py")
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
            "request_id": f"cohort3-{attempt_id}-accept",
            "target_run_id": run_id,
            "expected_requirements_revision": req_rev,
        }
        acode, ares = _http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                            headers={"X-LG-Token": "cohort3-token"})
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

        diff_bytes = subprocess.run(
            ["git", "-C", str(candidate_ws), "diff", "--no-index", "--",
             str(initial_dir), str(candidate_ws)],
            capture_output=True,
        ).stdout
        diff = diff_bytes.decode("utf-8", errors="replace")
        (out_dir / "candidate.diff").write_text(diff, encoding="utf-8")
        (out_dir / "git.txt").write_text(
            f"initial_head={initial_head}\nrun_id={run_id}\n", encoding="utf-8"
        )

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
        results["global_ledger"] = _safe(lambda: gen())
        results["ok"] = all(s["ok"] for s in results["steps"])
        (out_dir / "result.json").write_text(
            json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        # Only a FORMAL attempt writes the immutable evidence copy in the cohort
        # evidence dir; a dry-run never pollutes the formal evidence directory.
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


def _seed_resources(settings: Any, credential: str, *, base_url: str = C.BASE_URL) -> None:
    """Seed the frozen worker agent, connection, tools, skills and credential."""

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
            actor="cohort3", request_id=f"cohort3-conn-{cid}",
        )

    ensure_connection("cohort3-worker")
    ensure_connection("cohort3-reviewer")

    # Store the credential value via the controlled secret store (never logged).
    secret_store = FileSecretStore(settings.secret_store)
    if secret_store.get(C.CREDENTIAL_REF) is None:
        secret_store.put(C.CREDENTIAL_REF, credential)

    # Seed ordering: connections -> settings.  When a later serial attempt
    # shares the same phase data_dir, settings already exist, so pass the
    # current revision (the product requires it for updates).  This makes the
    # seed idempotent across attempts without swapping data_dir.
    expected_rev = None
    try:
        expected_rev = store.read("settings", "settings").revision
    except EntityNotFound:
        expected_rev = None
    conns.update_settings(
        expected_revision=expected_rev,
        actor="cohort3",
        default_coordinator_connection_ref="cohort3-worker",
        default_worker_connection_ref="cohort3-worker",
        default_reviewer_connection_ref="cohort3-reviewer",
    )

    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        try:
            store.read(kind, entity_id)
            return
        except EntityNotFound:
            pass
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="cohort3",
                     request_id=f"cohort3-{kind}-{entity_id}", body=body)

    for tool_id in ("view-file", "create-file", "edit-file"):
        create("tool", tool_id, {"implementation": tool_id})
    create("skill", "implementation", {"description": "Implementation"}, "# Impl\n")
    create(
        "agent",
        "cohort3-worker",
        {
            "connection_ref": "cohort3-worker",
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": ["implementation"]},
            "tool_refs": ["view-file", "create-file", "edit-file"],
            "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": [],
        },
        body=WORKER_PROMPT_BODY,
    )


def _enable_loopback_for_dry_run(state: Any) -> None:
    """Offline-only: let the real executor/reviewer reach a local fake upstream."""

    executor = state.executor
    if executor is not None:
        executor._allow_loopback_upstream = True  # type: ignore[attr-defined]
    # ``run_review_turn`` imports LocalAuthProxy from the proxy module at call
    # time, so patch that class there (loopback allowed only for the dry-run).
    import lightgravity.adapter.proxy as proxy_mod

    orig = proxy_mod.LocalAuthProxy

    def patched(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        kwargs["allow_loopback_upstream"] = True
        return orig(*args, **kwargs)

    proxy_mod.LocalAuthProxy = patched  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(SAMPLE_SPEC))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fake-upstream", default=None)
    args = ap.parse_args()
    return run_attempt(args.sample, args.arm, dry_run=args.dry_run,
                       fake_upstream=args.fake_upstream)


if __name__ == "__main__":
    raise SystemExit(main())
