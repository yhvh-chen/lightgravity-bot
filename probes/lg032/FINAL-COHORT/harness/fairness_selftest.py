#!/usr/bin/env python3
"""LG-032 FAIRNESS-CORRECTION local self-test (no network, no provider, no fakes).

Focused invariant checks only (per the authorising PM directive):

1. **Canonical plan hash A == B**: the frozen plan emitted for arm A and arm B
   must be byte-identical after removing the *only* legitimate arm token (the
   ``source``/``notes`` arm tag), because the plan itself is shared.
2. **Only the collaboration switch differs**: the arm-dependent branch in
   ``run_attempt`` must be exactly the ``decentralized_claim_enabled`` switch.
3. **Seed commit SHA is arm-independent**: the per-sample seed repo yields one
   stable commit SHA, and a derived workspace ``HEAD`` equals that SHA -- so A/B
   share one *actual git commit object*, not merely an identical tree.

Preservation: writes only inside a caller-provided, uniquely-named temporary
root; never touches the real fixture tree or any attempt output.  Read-only w.r.t.
the product source.  Usage::

    .venv/bin/python probes/lg032/FINAL-COHORT/harness/fairness_selftest.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_attempt as R  # noqa: E402


class _Ctx:
    def __init__(self, acceptance: tuple[str, ...]) -> None:
        self.objective = ""
        self.acceptance_criteria = acceptance


def _canonical_plan(arm: str, sample: str) -> dict[str, Any]:
    """The frozen plan for ``arm`` with all arm-identifying tokens removed.

    Removes only ``source``/``notes`` (the arm tag) so a *residual* difference
    would prove the plan genuinely differs between arms.
    """

    proposal = asyncio.run(
        R._FrozenPlanner(arm, sample).plan(_Ctx(R.SAMPLE_SPEC[sample]["acceptance"]))
    )
    payload = asdict(proposal)
    payload.pop("source", None)
    payload.pop("notes", None)
    return payload


def _canonical_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def check_plan_hash_equal() -> dict[str, Any]:
    out: dict[str, Any] = {}
    ok = True
    for sample in sorted(R.SAMPLE_SPEC):
        a = _canonical_plan("A", sample)
        b = _canonical_plan("B", sample)
        ha, hb = _canonical_hash(a), _canonical_hash(b)
        equal = ha == hb
        ok = ok and equal
        out[sample] = {
            "plan_hash_A": ha,
            "plan_hash_B": hb,
            "nodes": [s["key"] for s in a["subtasks"]],
            "equal": equal,
        }
    return {"ok": ok, "samples": out}


def check_only_mode_switch_differs() -> dict[str, Any]:
    """Static proof: the ONLY arm-dependent variable is the collaboration switch.

    MODE-ISOLATION update: the fixed harness writes the switch *explicitly for
    every arm* (A -> False, B -> True) through ``_set_mode``, and re-asserts the
    real assembled dispatcher mode through ``_assert_active_mode`` after build.
    So the required static invariants are now:

    * ``_set_mode`` exists and is CALLED unconditionally before ``build_runtime``
      (not inside an ``arm == "B"`` branch);
    * ``_safe_restore_mode`` exists and is called (phase-end restore off);
    * ``_assert_active_mode`` exists and is called (post-bootstrap assertion);
    * every ``arm == "B"`` gate concerns only the collaboration switch -- none
      alters the plan, members, tools, objective, acceptance, truth or caps.

    A guard that fails loudly is *not* an experimental variable; an unconditional
    explicit switch write for BOTH arms is the fix, not a new variable.
    """

    src = (HERE / "run_attempt.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    arm_gates = [i for i, line in enumerate(lines) if 'arm == "B"' in line]
    # Each arm-dependent gate must stay inside the mode helpers, i.e. its window
    # references the collaboration switch only.
    switch_markers = ("decentralized", "_autonomous_pool", "_autonomous_claim")
    gates_ok = True
    for i in arm_gates:
        window = "\n".join(lines[i : i + 6])
        gates_ok = gates_ok and any(m in window for m in switch_markers)
    # The fix requires an UNCONDITIONAL per-attempt writer + restore + assertion.
    set_mode_present = "def _set_mode(" in src and "_set_mode(settings, arm)" in src
    restore_present = "def _safe_restore_mode(" in src and "_safe_restore_mode(settings)" in src
    assert_present = ("def _assert_active_mode(" in src
                      and "_assert_active_mode(settings, dispatcher, arm)" in src)
    # The old B-only writer must be gone (it caused the serial pollution).
    legacy_writer_removed = "_enable_decentralized_pool" not in src
    ok = (gates_ok and set_mode_present and restore_present and assert_present
          and legacy_writer_removed)
    return {
        "ok": ok,
        "arm_B_gate_count": len(arm_gates),
        "all_gates_are_switch": gates_ok,
        "set_mode_present": set_mode_present,
        "restore_present": restore_present,
        "post_bootstrap_assert_present": assert_present,
        "legacy_b_only_writer_removed": legacy_writer_removed,
    }


def check_seed_sha_arm_independent() -> dict[str, Any]:
    """Seed SHA + derived HEAD are identical, using an isolated temp fixture."""

    sample = sorted(R.SAMPLE_SPEC)[0]
    real_initial = R.C.FIXTURES_DIR / sample / "initial"
    with tempfile.TemporaryDirectory(prefix="lg032-fair-selftest-") as tmp:
        tmp_root = Path(tmp)
        # Isolated copy of the fixture initial tree (never the real fixtures dir).
        initial = tmp_root / sample / "initial"
        initial.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copytree(real_initial, initial)
        # Redirect the seed location into the temp tree for this self-test only.
        orig_seed_repo = R._seed_repo
        R._seed_repo = lambda s: tmp_root / s / "seed.git"  # type: ignore[assignment]
        try:
            seed_head_1 = R._ensure_seed(sample, initial)
            seed_head_2 = R._ensure_seed(sample, initial)
            ws_a = tmp_root / "runA" / "workspaces" / "candidate-ws"
            ws_b = tmp_root / "runB" / "workspaces" / "candidate-ws"
            head_a = R._init_repo(ws_a, initial, sample=sample)
            head_b = R._init_repo(ws_b, initial, sample=sample)
        finally:
            R._seed_repo = orig_seed_repo  # type: ignore[assignment]

        ok = seed_head_1 == seed_head_2 == head_a == head_b
        return {
            "ok": ok,
            "seed_head_first": seed_head_1,
            "seed_head_second": seed_head_2,
            "derived_head_A": head_a,
            "derived_head_B": head_b,
        }


def main() -> int:
    results = {
        "plan_hash_equal": check_plan_hash_equal(),
        "only_mode_switch_differs": check_only_mode_switch_differs(),
        "seed_sha_arm_independent": check_seed_sha_arm_independent(),
    }
    print(json.dumps(results, indent=2))
    all_ok = all(v["ok"] for v in results.values())
    print(f"\nFAIRNESS-SELFTEST {'PASS' if all_ok else 'FAIL'}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
