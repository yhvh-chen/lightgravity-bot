#!/usr/bin/env python3
"""LG-032 MODE-ISOLATION serial bootstrap probe (0 real provider).

Reproduces and fixes the LG-032 first-formal-cohort serial mode pollution at the
exact vector: the shared persistent ``settings/settings`` entity under ONE
``settings.data_dir`` that every serial attempt reuses.

Method (no provider, no task, no Run; product source read-only):

* ONE shared, unique, persistent ``settings.data_dir`` (the "serialFakePhaseRoot").
* Serial bootstraps **A -> B -> A -> B** using the REAL product ``build_runtime``
  (real Settings/FileStore/ClaimPolicyReader/GraphDispatcher).  Each step:
    1. ``R._set_mode(settings, arm)`` -- the FIXED harness path that explicitly
       writes the arm's polarity through the product settings service BEFORE
       build (arm A -> False, arm B -> True).
    2. real ``build_runtime``.
    3. ``R._assert_active_mode`` -- asserts the *actual assembled* dispatcher
       mode (``_autonomous_claim``/``_autonomous_pool``/``_decentralized_enabled()``)
       AND the persisted three switches match the arm; raises on any mismatch.
    4. record the real selector/dispatcher state the product would use.
    5. ``R._safe_restore_mode`` -- leaves the shared entity at product default off.
* The SAME sequence is also run with the LEGACY enable-B-only behaviour to
  demonstrate the pollution it caused (A-after-B inherits pool=True), proving the
  probe actually exercises the defect and not a vacuous path.

Evidence is written to a unique persistent JSON; nothing is deleted/overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS_DIR = HERE.parent / "FINAL-COHORT" / "harness"
sys.path.insert(0, str(HARNESS_DIR))
sys.path.insert(0, str(HERE))

import mode_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))

import run_attempt as R  # noqa: E402


def _build_and_probe(settings, arm: str) -> dict:
    """Real build_runtime + real active-mode snapshot for ``arm``."""

    from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
    from lightgravity.runtime.token import RuntimeToken

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("lg032-mode-serial", "generated"),
            serve_frontend=False,
            max_proxy_calls=8,
            model_calls_cap=8,
        )
    )
    dispatcher = state.app.state.coordinator.dispatcher
    if dispatcher is None:
        raise SystemExit("real dispatcher not assembled")
    snapshot = R._assert_active_mode(settings, dispatcher, arm)
    snapshot["execution_ready"] = state.execution_report()["execution_ready"]
    return snapshot


def _legacy_enable_b_only(settings, arm: str) -> dict:
    """The OLD (defective) behaviour: only arm B writes the switch, A writes nothing.

    Demonstrates that on a shared settings entity a later arm A inherits the
    earlier arm B's enabled pool mode -- i.e. the probe is not vacuous.
    """

    if arm == "B":
        return R._set_mode(settings, arm)
    return {"arm": arm, "legacy": "no write (inherits persisted value)"}


def run_scenario(shared_dir: Path, *, use_fix: bool) -> dict:
    from lightgravity.config import Settings

    shared_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(shared_dir)
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(shared_dir)

    workspace_root = shared_dir / "workspaces"
    secret_store = shared_dir / "secrets"
    settings = Settings(
        data_dir=shared_dir,
        workspace_root=workspace_root,
        secret_store=secret_store,
        host="127.0.0.1",
        port=0,
    )
    settings.ensure_data_dir()
    # Seed the frozen worker/reviewer resources through the product service so
    # settings/default_worker_connection_ref exists for every bootstrap.
    R._seed_resources(settings, "dummy-serial-credential", base_url="http://127.0.0.1:9")

    steps = []
    for arm in ("A", "B", "A", "B"):
        before = R._settings_switches(settings)
        if use_fix:
            write_info = R._set_mode(settings, arm)
        else:
            write_info = _legacy_enable_b_only(settings, arm)
        after_write = R._settings_switches(settings)
        if use_fix:
            snapshot = _build_and_probe(settings, arm)
        else:
            # Legacy scenario: observe the *actual* assembled mode WITHOUT the
            # failing assertion (the whole point is to show it is wrong), and do
            # NOT restore between steps -- exactly like the first formal cohort.
            snapshot = _legacy_boot_observe(settings, arm)
            snapshot["expected_enabled"] = arm == "B"
            snapshot["congruent"] = (
                snapshot["dispatcher_autonomous_pool"] is (arm == "B")
            )
        restore = {"skipped": "legacy scenario never restored"} if not use_fix \
            else R._safe_restore_mode(settings)
        steps.append({
            "arm": arm,
            "switches_before_write": before,
            "write": write_info,
            "switches_after_write": after_write,
            "active_mode_snapshot": snapshot,
            "restore": restore,
        })
    return {"scenario": "fix" if use_fix else "legacy_enable_b_only", "steps": steps}


def _legacy_boot_observe(settings, arm: str) -> dict:
    """Build with NO per-attempt write and observe the inherited active mode."""

    from lightgravity.api.bootstrap import StartupOptions, build_runtime
    from lightgravity.runtime.token import RuntimeToken

    state = build_runtime(
        StartupOptions(settings=settings, token=RuntimeToken("x", "generated"),
                       serve_frontend=False, max_proxy_calls=8, model_calls_cap=8)
    )
    dispatcher = state.app.state.coordinator.dispatcher
    return {
        "arm": arm,
        "persisted_switches": R._settings_switches(settings),
        "dispatcher_autonomous_pool": bool(getattr(dispatcher, "_autonomous_pool", False)),
        "dispatcher_decentralized_enabled": bool(dispatcher._decentralized_enabled()),
    }


def run_legacy_pollution_demo(shared_dir: Path) -> dict:
    """Old behaviour demo: A(fresh) -> B -> A with NO per-attempt write on the 2nd A.

    The 1st A uses the product default (off); B enables; the 2nd A writes nothing
    and therefore inherits B's enabled pool -- the exact first-cohort pollution.
    """

    from lightgravity.config import Settings

    shared_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(shared_dir)
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(shared_dir)
    settings = Settings(data_dir=shared_dir, workspace_root=shared_dir / "workspaces",
                        secret_store=shared_dir / "secrets", host="127.0.0.1", port=0)
    settings.ensure_data_dir()
    R._seed_resources(settings, "dummy-serial-credential", base_url="http://127.0.0.1:9")

    observed = []
    # 1st A: product default (off), no write.
    observed.append(_legacy_boot_observe(settings, "A"))
    # B: legacy enable-only write.
    _legacy_enable_b_only(settings, "B")
    observed.append(_legacy_boot_observe(settings, "B"))
    # 2nd A: legacy NEVER writes False -> inherits B.
    observed.append(_legacy_boot_observe(settings, "A_after_B_legacy"))
    return {"scenario": "legacy_pollution_demo", "observed": observed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="serial")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = MC.EVIDENCE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Unique persistent root names; never reused, never deleted.
    fix_root = MC.SERIAL_ROOT.parent / f"{MC.SERIAL_ROOT.name}-fix-{stamp}"
    legacy_root = MC.SERIAL_ROOT.parent / f"{MC.SERIAL_ROOT.name}-legacy-{stamp}"

    fix_result = run_scenario(fix_root, use_fix=True)
    legacy_result = run_scenario(legacy_root, use_fix=False)
    legacy_demo = run_legacy_pollution_demo(
        MC.SERIAL_ROOT.parent / f"{MC.SERIAL_ROOT.name}-legacydemo-{stamp}"
    )

    def fix_ok(res: dict) -> bool:
        for step in res["steps"]:
            snap = step["active_mode_snapshot"]
            if not snap.get("congruent"):
                return False
        return True

    def legacy_shows_pollution(res: dict) -> bool:
        # Steps: A,B,A,B with NO restore. The 3rd step (A after B) must show
        # the enabled pool inherited from step 2 -- the first-cohort defect.
        third = res["steps"][2]
        return (
            third["arm"] == "A"
            and bool(third["active_mode_snapshot"].get("dispatcher_autonomous_pool"))
        )

    demo = legacy_demo["observed"]
    demo_pollution = bool(
        demo[1]["dispatcher_autonomous_pool"] is True
        and demo[2]["dispatcher_autonomous_pool"] is True
        and demo[2]["arm"] == "A_after_B_legacy"
    )

    summary = {
        "utc": stamp,
        "label": args.label,
        "shared_data_dir_strategy": "one shared settings.data_dir per scenario "
                                    "(A->B->A->B serial bootstraps), not per-nonce roots",
        "fix_scenario_congruent_all_steps": fix_ok(fix_result),
        "legacy_scenario_A_after_B_shows_pool_true": legacy_shows_pollution(legacy_result),
        "legacy_pollution_demo_reproduced": demo_pollution,
        "real_provider_generation": 0,
        "fix_root": str(fix_root),
        "legacy_root": str(legacy_root),
        "verdict": (
            "PASS" if (fix_ok(fix_result) and legacy_shows_pollution(legacy_result)
                       and demo_pollution) else "FAIL"
        ),
    }
    out = {
        "summary": summary,
        "fix_scenario": fix_result,
        "legacy_scenario_A_after_B": legacy_result,
        "legacy_pollution_demo": legacy_demo,
    }
    dest = out_dir / f"serial-mode-{stamp}.json"
    dest.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(f"WROTE {dest}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
