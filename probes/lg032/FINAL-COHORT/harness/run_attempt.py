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

    FAIRNESS-CORRECTION (LG-032): the plan is **identical for arm A and arm B**.
    Both arms declare the same three nodes -- ``alpha`` (writes file1),
    ``beta`` (writes file2), and a read-only ``verify`` that depends on both.

    The **only** experimental variable is therefore whether the product uses
    the deterministic program scheduler (arm A) or the candidate-pool
    autonomous collaboration path (arm B).  The former old design (A=1 merged
    write node, B=2 write nodes) confounded two variables (write-node count AND
    the collaboration mechanism) and is rejected by the PM.

    Emitted plans are validated by the product ``PlanValidator`` exactly like
    the product's own rule plan; this is not a control-state edit.
    """

    def __init__(self, arm: str, sample: str) -> None:
        self.name = f"lg032-fair-frozen-{arm}"
        self._arm = arm
        self._sample = sample

    async def plan(self, context: Any) -> Any:
        from lightgravity.coordinator.planner import PlanProposal, RawSubtask

        spec = SAMPLE_SPEC[self._sample]
        acceptance = tuple(context.acceptance_criteria) or tuple(spec["acceptance"])
        # Identical 3-node plan for BOTH arms (FAIRNESS-CORRECTION §1).
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
            source="lg032-fair-frozen-plan",
            notes=(
                "LG-032 FAIRNESS-CORRECTION: identical 3-node plan for both arms; "
                f"only the collaboration switch differs (arm {self._arm})",
            ),
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


def _seed_repo(sample: str) -> Path:
    """The persistent, read-only seed git repo for ``sample`` (FAIRNESS-CORRECTION §3).

    The seed is created **once** and then persisted; its single initial commit is
    the *same actual commit SHA* for every arm of every attempt.  This fixes the
    LG-023 A5 defect where each arm ran its own ``git init`` + commit, producing
    byte-identical trees but **different commit objects** (commit timestamps).

    The seed lives beside the fixture in the repo (tracked, frozen content) and
    is never written by a worker: attempt workspaces are cloned *from* it and the
    per-node worktrees are isolated copies, so the seed object store is immutable
    after first creation.
    """

    return C.FIXTURES_DIR / sample / "seed.git"


def _ensure_seed(sample: str, initial: Path) -> str:
    """Create the per-sample seed repo once; return its frozen commit SHA.

    Deterministic commit identity: fixed author/committer name/email and fixed
    commit timestamp are used so the *first* generation is reproducible and its
    SHA is stable.  Once the seed exists it is never re-created; a worker reset
    would be detected because derived repositories pin this exact SHA.
    """

    seed = _seed_repo(sample)
    if seed.exists():
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=seed,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return head
    seed.mkdir(parents=True)
    # Fixed identity + fixed timestamp => a stable, reproducible seed commit SHA.
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "lg032",
        "GIT_AUTHOR_EMAIL": "lg032@local",
        "GIT_COMMITTER_NAME": "lg032",
        "GIT_COMMITTER_EMAIL": "lg032@local",
        "GIT_AUTHOR_DATE": "2026-10-16T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-10-16T00:00:00+00:00",
    }
    shutil.copytree(initial, seed, dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=seed, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True, env=env)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture initial"],
        cwd=seed, check=True, env=env,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=seed, capture_output=True, text=True, check=True,
    ).stdout.strip()
    # A provenance record pins the seed identity for the fairness hash / audit.
    (seed.parent / "seed.sha256").write_text(head + "\n", encoding="utf-8")
    return head


def _init_repo(root: Path, initial: Path, *, sample: str) -> str:
    """Materialise the candidate workspace by CLONING the frozen seed repo.

    The workspace is a real git repository (so the product's per-write-node
    isolation applies and ``alpha``/``beta`` each get distinct worktrees).  Its
    start identity is the **same actual commit SHA** as the per-sample seed, so
    arm A and arm B start from one identical git commit object -- not merely an
    identical tree.

    Preservation: ``root`` must be a caller-owned, uniquely-named path under
    this run's own attempt root.  Refuse to touch anything else so a history /
    formal path can never be clobbered.  The read-only seed is never modified.
    """

    if root.exists() and "workspaces" not in root.parts:
        raise SystemExit(
            f"_init_repo refusing to remove non-attempt path {root} "
            "(preservation: only this run's own candidate-ws may be reused)"
        )
    seed = _seed_repo(sample)
    seed_head = _ensure_seed(sample, initial)
    if root.exists():
        shutil.rmtree(root)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "lg032",
        "GIT_AUTHOR_EMAIL": "lg032@local",
        "GIT_COMMITTER_NAME": "lg032",
        "GIT_COMMITTER_EMAIL": "lg032@local",
    }
    # Clone the seed so the derived repo shares the exact seed commit object; a
    # failed clone falls back to an explicit (SHA-checked) copy so a runner
    # without a local git transport still gets the SAME commit.
    proc = subprocess.run(
        ["git", "clone", "-q", "--no-checkout", str(seed), str(root)],
        capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        shutil.copytree(seed, root)
        subprocess.run(["git", "config", "--unset", "remote.origin.url"], cwd=root, check=False, env=env)
    subprocess.run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", seed_head],
                   cwd=root, check=True, env=env)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if head != seed_head:
        raise SystemExit(
            f"derived workspace HEAD {head} != frozen seed {seed_head} "
            "(FAIRNESS-CORRECTION: A/B must share one actual commit SHA)"
        )
    return head


def _materialize_candidate(initial_dir: Path, patch_paths: list[Path], dest: Path) -> bool:
    """Apply the run's own candidate diffs onto a fresh copy of the fixture.

    The product's real candidate for a multi-node (pool) run is the set of
    **per-node** ``evidence:<run>/<subtask>-lg006-diff.patch`` artifacts the
    dispatcher imported into the Task/Run evidence root.  The single legacy
    ``artifacts/<run>/lg006-diff.patch`` path collides across pool nodes (every
    node writes the same run-scoped name), so it is NOT the full candidate and
    must never be the only input.  ``dest`` is a brand-new unique path (never
    deleted/overwritten).
    """

    if dest.exists():
        raise SystemExit(f"refusing to reuse candidate dir {dest}")
    shutil.copytree(initial_dir, dest)
    if not patch_paths:
        return False
    for patch_path in patch_paths:
        if not patch_path.exists():
            return False
        proc = subprocess.run(
            ["git", "apply", "--unsafe-paths", "-p1", str(patch_path)],
            cwd=dest,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False
    return True


def _candidate_diff_paths(state: Any, task_id: str, run_id: str) -> list[Path]:
    """The product's real per-node candidate diffs for ``run_id``.

    Uses the product's own candidate snapshot (``load_candidate``) plus its
    canonical evidence resolver, so the machine truth runs against the exact
    artifacts the product recorded -- never an unmerged shared stub and never a
    raw executor path.  Returns them in node-ref order (deterministic); an empty
    list means the product recorded no diff evidence.
    """

    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import resolve_candidate_evidence

    store = state.store
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    diffs: list[Path] = []
    for ref in candidate.artifact_refs:
        path = resolved.get(ref)
        if path is None:
            continue
        if path.name.lower().endswith(("-lg006-diff.patch", "lg006-diff.patch")):
            diffs.append(path)
    return diffs


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

    # MODE-ISOLATION (LG-032 repair): EVERY attempt EXPLICITLY writes its own
    # mode through the product's controlled settings service BEFORE the runtime
    # is built -- arm B enables the frozen candidate-pool switch, arm A writes an
    # explicit ``False``.  The former harness only enabled B and left A at the
    # persisted value, so on the ONE shared ``settings.data_dir`` the earlier arm
    # B's ``True`` leaked into a later arm A (serial mode pollution).  Writing
    # both polarities removes the cross-attempt inheritance.  This is the
    # product's own supported settings write (``ConnectionService.update_settings``),
    # not a control-state edit, not a ``monkeypatch``, and not a fabricated Run.
    mode_snapshot_before = _set_mode(settings, arm)

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

    # MODE-ISOLATION: after the REAL bootstrap (real ``build_runtime`` wired the
    # real dispatcher from the persisted settings entity), assert the *actual*
    # active mode + the three persisted settings switches match the arm's frozen
    # expectation.  This is a read of the assembled product objects, NOT a string
    # ``os.environ`` check, and it refuses (STOP the attempt) on any mismatch --
    # so a later arm A can never silently inherit an earlier arm B's pool mode.
    mode_snapshot_after = _assert_active_mode(settings, dispatcher, arm)
    mode_snapshot_after["mode_snapshot_before"] = mode_snapshot_before

    # The real CoordinatorWorkerLoop is started by the product app's own
    # FastAPI ``lifespan`` when uvicorn boots below -- exactly the production
    # path.  Calling ``coordinator.start()`` here would run outside an event
    # loop; the product starts it inside the loop, so we do not duplicate it.

    initial_dir = C.FIXTURES_DIR / sample / "initial"
    candidate_ws = workspace_root / "candidate-ws"
    initial_head = _init_repo(candidate_ws, initial_dir, sample=sample)
    seed_head = _ensure_seed(sample, initial_dir)

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
        "seed_head": seed_head,
        "phase_data_dir": str(data_dir),
        "frozen_ledger_history": str(data_dir / "generation" / "generation.jsonl"),
        "total_limit": C.TOTAL_GENERATION_LIMIT,
        "attempt_limit": C.ATTEMPT_GENERATION_LIMIT,
        "caller": "agent:pi-lg032-final-cohort",
        "mode_snapshot_after_bootstrap": mode_snapshot_after,
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

        # Authorise the product's OWN registered machine checks on the Task
        # (docs/08 §6.1 additive ``checks`` field).  Without this the product's
        # ``verify_and_prepare`` runs ZERO checks and would treat "no checks" as
        # a pass -- FAIRNESS-CORRECTION §5 forbids treating empty Task checks as
        # a machine pass.  This is a legitimate Task configuration write through
        # the product's controlled StateWriter (not a phase/acceptance edit).
        checks_authorized = _authorize_task_checks(state, task_id)
        step("task_checks_authorized", bool(checks_authorized), checks=checks_authorized)

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
        # product-recorded per-node diffs onto a fresh copy of the frozen
        # fixture.  A multi-node (pool) run has one per-node evidence diff;
        # the colliding legacy run-level path is not sufficient on its own.
        candidate_dir = workspace_root / "candidate-eval"
        diffs = _candidate_diff_paths(state, task_id, run_id or "")
        applied = _materialize_candidate(initial_dir, diffs, candidate_dir)
        results["candidate_diffs"] = [str(p) for p in diffs]
        results["candidate_diff_count"] = len(diffs)
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
        # Accept is only attempted once the product's own truths pass (machine
        # gate + independent reviewer + real stop/teardown + real session refs).
        # If a truth failed, the run is honestly recorded as not delivered and no
        # accept is attempted (never fabricate a bound acceptance).
        review_passed = str(review.get("validated_outcome", review.get("outcome", ""))) == "passed"
        truths_ok = bool(
            results["machine_pass"]
            and review_passed
            and len(session_refs) >= 1
            and isinstance(reviewer_cleanup, dict)
            and reviewer_cleanup.get("confirmed") is True
        )
        results["truths_before_accept"] = truths_ok

        req_rev = detail.get("requirements_revision")
        accept_body = {
            "action": "accept",
            "request_id": f"lg032-{attempt_id}-accept",
            "target_run_id": run_id,
            "expected_requirements_revision": req_rev,
        }
        accepted = False
        if truths_ok:
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

            # Idempotency: replaying the SAME request_id must not create a second
            # decision nor change the bound candidate.
            icode, ires = _http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                                headers={"X-LG-Token": "lg032-token"})
            results["accept_idempotent_response"] = ires
            iacc = ires.get("acceptance") or {}
            idempotent = (
                icode == 200 and ires.get("state") == "confirmed"
                and ires.get("candidate_ref") == run_id
                and iacc.get("decision_ref") == acc.get("decision_ref")
            )
            step("accept_same_request_idempotent", idempotent, code=icode,
                 state=ires.get("state"), decision_ref=iacc.get("decision_ref"))

            # Wrong target: a different (non-active) run must be refused and must
            # not alter the confirmed acceptance.
            wrong_body = dict(accept_body, target_run_id="run_0000000000000000000000000")
            wcode, wres = _http("POST", f"{base}/tasks/{task_id}/actions", body=wrong_body,
                                headers={"X-LG-Token": "lg032-token"})
            results["accept_wrong_target_response"] = {"code": wcode, "body": wres}
            step("accept_wrong_target_rejected", wcode >= 400, code=wcode, body=wres)
        else:
            step("accept_confirmed_bound", False, skipped="preconditions_unmet",
                 machine_pass=results["machine_pass"], review_passed=review_passed)

        gen_final = gen()
        results["generation_final"] = gen_final
        results["attempt_generation_requests"] = guard.used

        results["sample_delivered"] = bool(
            results["machine_pass"] and accepted and review_passed
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
        # MODE-ISOLATION: leave the shared phase settings entity in the product
        # DEFAULT state (off) at the end of every attempt, so no later attempt's
        # bootstrap can ever observe a stale enabled switch.  Uses the product's
        # own controlled settings write; the product source default (off) is
        # never changed.  Recorded either way (restore failure is reported, not
        # hidden, but never turns a real attempt failure into a fake success).
        results["mode_restore"] = _safe_restore_mode(settings)
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


def _settings_switches(settings: Any) -> dict[str, Any]:
    """Read the three persisted settings switches from the shared settings entity.

    Reads the product ``settings/settings`` entity directly from the one phase
    ``settings.data_dir`` -- the exact persisted values ``build_runtime`` reads
    through ``ClaimPolicyReader``.  Values only; never mutates.
    """

    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    entity = store.read("settings", "settings").entity
    return {
        "decentralized_claim_enabled": bool(entity.get("decentralized_claim_enabled", False)),
        "collab_requests_enabled": bool(entity.get("collab_requests_enabled", False)),
        "claim_lease_seconds": entity.get("claim_lease_seconds"),
        "default_worker_connection_ref": entity.get("default_worker_connection_ref"),
    }


def _set_mode(settings: Any, arm: str) -> dict[str, Any]:
    """Explicitly write the arm's mode to the shared settings entity (BEFORE build).

    MODE-ISOLATION: arm B enables the decentralized candidate-pool switch; arm A
    writes an explicit ``False`` ("default off").  Both polarities are written so
    the persisted value can never be inherited from a previous serial attempt on
    the same ``settings.data_dir``.  Uses the product's controlled settings write
    (``ConnectionService.update_settings``) -- a legitimate product configuration
    input, not a control-state edit and not a ``monkeypatch``.

    Returns the settings-switch snapshot observed *before* the write for audit.
    """

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    before = _settings_switches(settings)
    try:
        current = store.read("settings", "settings").revision
    except Exception:  # noqa: BLE001
        current = None
    conns.update_settings(
        expected_revision=current,
        actor="lg032-mode-isolation",
        default_worker_connection_ref="lg032-worker",
        decentralized_claim_enabled=(arm == "B"),
    )
    after = _settings_switches(settings)
    return {"arm": arm, "before": before, "after": after}


def _assert_active_mode(settings: Any, dispatcher: Any, arm: str) -> dict[str, Any]:
    """Assert the REAL assembled dispatcher mode + persisted switches match the arm.

    MODE-ISOLATION: called after ``build_runtime`` (the product wired the real
    ``GraphDispatcher`` from the settings entity).  Checks the *actual* object
    state the program will use to dispatch -- ``_autonomous_claim``,
    ``_autonomous_pool`` and ``_decentralized_enabled()`` -- plus the three
    persisted switches.  This is not a string ``os.environ`` assertion, and it
    fails closed (raises -> attempt STOP) so a later arm A can never inherit an
    earlier arm B's pool mode.

    Returns the recorded snapshot for evidence.
    """

    want = arm == "B"
    switches = _settings_switches(settings)
    active_claim = bool(getattr(dispatcher, "_autonomous_claim", False))
    active_pool = bool(getattr(dispatcher, "_autonomous_pool", False))
    decentralized_fn = getattr(dispatcher, "_decentralized_enabled", None)
    active_decentralized = bool(decentralized_fn()) if callable(decentralized_fn) else None
    snapshot = {
        "arm": arm,
        "expected_enabled": want,
        "settings_switches": switches,
        "dispatcher_autonomous_claim": active_claim,
        "dispatcher_autonomous_pool": active_pool,
        "dispatcher_decentralized_enabled": active_decentralized,
    }
    problems = []
    if switches["decentralized_claim_enabled"] is not want:
        problems.append(
            "persisted decentralized_claim_enabled="
            f"{switches['decentralized_claim_enabled']} != expected {want}"
        )
    if active_claim is not want:
        problems.append(f"dispatcher._autonomous_claim={active_claim} != expected {want}")
    if active_pool is not want:
        problems.append(f"dispatcher._autonomous_pool={active_pool} != expected {want}")
    if active_decentralized is not want:
        problems.append(
            f"dispatcher._decentralized_enabled()={active_decentralized} != expected {want}"
        )
    snapshot["congruent"] = not problems
    snapshot["problems"] = problems
    if problems:
        raise SystemExit(
            "MODE-ISOLATION violation (arm " + arm + "); refusing to run a polluted attempt: "
            + "; ".join(problems)
        )
    print(f"[MODE] arm={arm} active mode congruant with frozen expectation: {snapshot}",
          flush=True)
    return snapshot


def _safe_restore_mode(settings: Any) -> dict[str, Any]:
    """Restore the shared phase settings candidate switch to the product default (off).

    MODE-ISOLATION: after every attempt (success or failure) the shared phase
    settings entity is returned to ``decentralized_claim_enabled=False`` so a
    subsequent serial attempt always starts from the product default and must
    explicitly re-enable its own mode.  Never touches the product source default.
    """

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    before = _settings_switches(settings)
    try:
        current = store.read("settings", "settings").revision
    except Exception:  # noqa: BLE001
        current = None
    conns.update_settings(
        expected_revision=current,
        actor="lg032-mode-isolation",
        decentralized_claim_enabled=False,
    )
    after = _settings_switches(settings)
    return {"before": before, "after": after, "restored_off": after["decentralized_claim_enabled"] is False}


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


#: The product's OWN registered machine check the Task authorises (docs/08
#: §6.1 ``checks``).  ``evidence-present`` is the minimum the FAIRNESS-CORRECTION
#: requires: it makes the product actually run a real registered check (failing
#: when no artifact/diff evidence is recorded) instead of vacuously treating an
#: empty Task-checks list as a pass.  ``artifacts-in-workspace`` (stricter
#: workspace/evidence path resolution) is deliberately NOT forced here: it is not
#: required for the graph evidence-present gate and could over-constrain a graph
#: harness whose refs are already namespace-classified; it stays a follow-up.
FROZEN_TASK_CHECKS = ("evidence-present",)


def _authorize_task_checks(state: Any, task_id: str) -> tuple[str, ...]:
    """Authorise the frozen product machine checks on the Task entity.

    Uses the product's controlled ``StateWriter.write_task`` (the same unified
    write interface every control change uses); it only sets the purely additive
    ``checks`` authorization field, never a phase/acceptance/cleanup value.  The
    verified report therefore carries real ``check_records`` instead of an empty
    "no checks" set -- an empty Task-checks list must never masquerade as a
    machine pass (FAIRNESS-CORRECTION §5).
    """

    from lightgravity.coordinator.state import StateWriter

    store = state.store
    writer = StateWriter(store, actor="lg032")
    writer.write_task(task_id, {"checks": list(FROZEN_TASK_CHECKS)})
    return FROZEN_TASK_CHECKS


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
