#!/usr/bin/env python3
"""LG-032 MODE-ISOLATION serial SDK fake A-after-B proof (0 real provider).

Runs the REAL product path (``run_attempt`` with a loopback scripted fake upstream
-- real SDK, real GraphDispatcher, real Coordinator worker loop, real verify) over
ONE shared ``settings.data_dir`` in the historically-polluting order:

    arm B (enables pool)  ->  arm A (must be deterministic, pool off)

and proves the fix by:

* asserting the A attempt's *actual assembled* mode is off (via the fixed
  harness ``_assert_active_mode`` which would STOP on any pollution);
* recording the product's real selector/dispatcher state and session refs for
  both attempts (the first cohort's ``s2_pipeline__A`` had 6 refs = B-like; a
  correct A has the deterministic 3-node path);
* sharing the ONE phase ledger across both serial attempts (before/after counts).

No real credential is used (dummy), the upstream is loopback-only, and nothing is
deleted/overwritten.  This is a FAKE proof, not a formal real-provider cohort.
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

import fake_upstream as F  # noqa: E402
import run_attempt as R  # noqa: E402


def _run_one(sample: str, arm: str, shared_root: Path) -> tuple[int, dict, dict]:
    """One real fake-upstream attempt sharing ``shared_root`` as data_dir."""

    os.environ["LG032_MODE_SHARED_DRY_ROOT"] = str(shared_root)
    os.environ["DEEPSEEK_API_KEY"] = "dummy-offline-credential"
    upstream = F.FakeUpstream(sample=sample, arm=arm)
    try:
        # The connections are shared on the one settings.data_dir, so a later
        # serial attempt must repoint them at THIS invocation's fake port through
        # the product's controlled connection service (the frozen _seed_resources
        # only creates them once).  Legitimate product configuration, not a bypass.
        _repoint_connections(shared_root, upstream.base_url)
        rc = R.run_attempt(sample, arm, dry_run=True,
                           fake_upstream=upstream.base_url,
                           dry_label=f"mode-serial-{sample}-{arm}")
        out = shared_root / "offline_dry_run_output" / f"{sample}__{arm}" / "result.json"
        result = json.loads(out.read_text()) if out.exists() else {}
        records = list(upstream.records)
    finally:
        upstream.close()
    return rc, result, {"records": records}


def _repoint_connections(shared_root: Path, base_url: str) -> None:
    """Repoint the shared worker/reviewer connections at the current fake URL."""

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore, EntityNotFound

    store = FileStore(shared_root, shared_root / "workspaces")
    conns = ConnectionService(store, secret_store=FileSecretStore(shared_root / "secrets"))
    for cid in ("lg032-worker", "lg032-reviewer"):
        try:
            entity = store.read("connection", cid)
        except EntityNotFound:
            continue
        conns.update_connection(
            cid, expected_revision=entity.revision, actor="lg032-mode-isolation",
            base_url=base_url,
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="s2_pipeline")
    ap.add_argument("--label", default="sdk-serial")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shared_root = MC.SERIAL_ROOT.parent / f"{MC.SERIAL_ROOT.name}-sdk-{stamp}"
    shared_root.mkdir(parents=True, exist_ok=True)

    # Historical polluting order: B first (enables pool), then A.
    rc_b, res_b, cap_b = _run_one(args.sample, "B", shared_root)
    rc_a, res_a, cap_a = _run_one(args.sample, "A", shared_root)

    mode_b = res_b.get("mode_snapshot_after_bootstrap", {})
    mode_a = res_a.get("mode_snapshot_after_bootstrap", {})

    def phases(cap: dict) -> list[str]:
        return sorted({r["phase"] for r in cap["records"]})

    summary = {
        "utc": stamp,
        "sample": args.sample,
        "order": ["B", "A"],
        "shared_data_dir": str(shared_root),
        "B": {
            "rc": rc_b, "ok": res_b.get("ok"),
            "mode": mode_b,
            "session_refs": len(res_b.get("session_refs") or []),
            "phases": phases(cap_b),
        },
        "A_after_B": {
            "rc": rc_a, "ok": res_a.get("ok"),
            "mode": mode_a,
            "session_refs": len(res_a.get("session_refs") or []),
            "phases": phases(cap_a),
        },
        "real_provider_generation": 0,
    }
    a_pool_off = mode_a.get("dispatcher_autonomous_pool") is False
    a_congruent = bool(mode_a.get("congruent"))
    a_no_selection = "selection" not in phases(cap_a)
    summary["verdict"] = "PASS" if (a_pool_off and a_congruent and a_no_selection) else "FAIL"
    summary["checks"] = {
        "A_after_B_pool_off": a_pool_off,
        "A_after_B_congruent": a_congruent,
        "A_after_B_no_pool_selection_phase": a_no_selection,
    }

    dest = MC.EVIDENCE_DIR / f"sdk-serial-mode-{stamp}.json"
    dest.write_text(json.dumps({"summary": summary, "B_result": res_b,
                                "A_result": res_a, "B_capture": cap_b,
                                "A_capture": cap_a}, indent=2, sort_keys=True,
                               default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(f"WROTE {dest}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
