#!/usr/bin/env python3
"""LG-032 COHORT2-QA serial fake chain: s1A -> s1B -> s2A -> s2B (0 real provider).

Independent serial-method QA of the mode-isolation fix.  Runs the *unmodified*
formal driver (``run_attempt.py``) over ONE shared ``settings.data_dir`` in the
EXACT formal order, so a later arm A genuinely has the opportunity to inherit an
earlier arm B's ``decentralized_claim_enabled=True`` -- the defect that invalidated
the first formal cohort.

Each of the four attempts:
  * uses a fresh loopback ``FakeUpstream`` (arm/sample-scripted; dummy credential);
  * runs the REAL product path (real ``build_runtime``, real ``GraphDispatcher``,
    real ``CoordinatorWorkerLoop`` via uvicorn lifespan, real verify/reviewer);
  * writes into the ONE shared QA phase root (same physical ledger JSONL);
  * the fixed harness ``_set_mode`` writes the arm polarity before build, and the
    ``_assert_active_mode`` (which fires before any uvicorn/SDK forward) must agree.

This probe NEVER touches the formal cohort2 root, METHOD-FINAL, or cohort-ready.

Preservation: unique persistent output; nothing deleted/overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA_DIR = HERE
sys.path.insert(0, str(QA_DIR / "overlay"))

import qa_mode_config as QMC  # noqa: E402

C = QMC.install()
sys.path.insert(0, str(QMC.HARNESS_DIR))

import fake_upstream as F  # noqa: E402
import run_attempt as R  # noqa: E402

ATTEMPT_ORDER = [("s1_units", "A"), ("s1_units", "B"),
                 ("s2_pipeline", "A"), ("s2_pipeline", "B")]


def _repoint_connections(shared_root: Path, base_url: str) -> None:
    """Repoint the two shared connections at THIS attempt's fake port.

    The connections live on the ONE shared settings.data_dir, so once created they
    must be re-pointed at the current fake upstream through the product's own
    controlled connection service (legitimate product configuration, not a bypass).
    Reads the *same* real config object the driver uses.
    """

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
            cid, expected_revision=entity.revision, actor="lg032-cohort2-qa",
            base_url=base_url,
        )


def _phase_names(records: list[dict]) -> list[str]:
    return sorted({r.get("phase") for r in records})


def run_chain(shared_root: Path) -> dict:
    os.environ["LG032_QA_SHARED_DRY_ROOT"] = str(shared_root)
    os.environ["DEEPSEEK_API_KEY"] = "dummy-offline-credential"
    shared_root.mkdir(parents=True, exist_ok=True)

    steps = []
    for sample, arm in ATTEMPT_ORDER:
        attempt_id = f"{sample}__{arm}"
        ledger_before = _ledger_count(shared_root)
        upstream = F.FakeUpstream(sample=sample, arm=arm)
        entry: dict = {"attempt_id": attempt_id, "sample": sample, "arm": arm,
                       "ledger_count_before": ledger_before,
                       "fake_base_url": upstream.base_url}
        try:
            _repoint_connections(shared_root, upstream.base_url)
            try:
                rc = R.run_attempt(sample, arm, dry_run=True,
                                   fake_upstream=upstream.base_url,
                                   dry_label=f"qa-cohort2-{sample}-{arm}")
                entry["rc"] = rc
                entry["driver_error"] = None
            except BaseException as exc:  # noqa: BLE001
                entry["rc"] = None
                entry["driver_error"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()
            out = shared_root / "offline_dry_run_output" / attempt_id / "result.json"
            result = json.loads(out.read_text()) if out.exists() else {}
            entry["result_path"] = str(out)
            entry["ok"] = result.get("ok")
            entry["final_phase"] = result.get("final_phase")
            entry["steps"] = result.get("steps", [])
            entry["steps_pass"] = sum(1 for s in result.get("steps", []) if s.get("ok"))
            entry["steps_total"] = len(result.get("steps", []))
            entry["mode_snapshot_after_bootstrap"] = result.get("mode_snapshot_after_bootstrap")
            entry["mode_restore"] = result.get("mode_restore")
            entry["session_refs"] = result.get("session_refs") or []
            entry["session_ref_count"] = len(result.get("session_refs") or [])
            entry["reviewer_cleanup"] = result.get("reviewer_cleanup")
            entry["machine_pass"] = result.get("machine_pass")
            entry["machine_gate"] = result.get("machine_gate")
            entry["truths_before_accept"] = result.get("truths_before_accept")
            entry["accept_response"] = result.get("accept_response")
            entry["accept_idempotent_response"] = result.get("accept_idempotent_response")
            entry["accept_wrong_target_response"] = result.get("accept_wrong_target_response")
            entry["seed_head"] = result.get("seed_head")
            entry["frozen_ledger_history"] = result.get("frozen_ledger_history")
            entry["phases"] = _phase_names(list(upstream.records))
            entry["fake_phase_records"] = len(list(upstream.records))
            entry["selection_present"] = "selection" in entry["phases"]
        finally:
            upstream.close()
        entry["ledger_count_after"] = _ledger_count(shared_root)
        steps.append(entry)

    return {"attempt_order": [f"{s}__{a}" for s, a in ATTEMPT_ORDER], "steps": steps}


def _ledger_count(shared_root: Path) -> dict:
    hist = shared_root / "generation" / "generation.jsonl"
    count = shared_root / "generation" / "generation.count.json"
    out: dict = {"history": str(hist), "history_exists": hist.exists()}
    if hist.exists():
        out["history_lines"] = sum(1 for _ in hist.open("rb"))
    if count.exists():
        try:
            out["count_json"] = json.loads(count.read_text())
        except Exception as exc:  # noqa: BLE001
            out["count_json_error"] = str(exc)
    return out


def _evaluate(chain: dict) -> dict:
    checks: dict = {}
    s1a, s1b, s2a, s2b = chain["steps"]
    # mode congruence per attempt (set by the fixed harness assertion)
    for e in chain["steps"]:
        snap = e.get("mode_snapshot_after_bootstrap") or {}
        want = e["arm"] == "B"
        checks[f"{e['attempt_id']}_mode_congruent"] = bool(snap.get("congruent"))
        checks[f"{e['attempt_id']}_dispatcher_pool_is_{want}"] = (
            snap.get("dispatcher_autonomous_pool") is want
        )
        checks[f"{e['attempt_id']}_ok"] = e.get("ok") is True
        checks[f"{e['attempt_id']}_all_steps_pass"] = (
            e.get("steps_total", 0) > 0 and e.get("steps_pass") == e.get("steps_total")
        )
        checks[f"{e['attempt_id']}_restored_off"] = bool(
            (e.get("mode_restore") or {}).get("restored_off")
        )
        checks[f"{e['attempt_id']}_reviewer_teardown_confirmed"] = bool(
            (e.get("reviewer_cleanup") or {}).get("confirmed")
        )
    # B has 6 refs + selection; A-after-B has 3 refs and NO selection
    checks["s1B_6_refs"] = s1b["session_ref_count"] == 6
    checks["s1B_selection"] = s1b["selection_present"] is True
    checks["s1A_3_refs"] = s1a["session_ref_count"] == 3
    checks["s2A_after_B_3_refs"] = s2a["session_ref_count"] == 3
    checks["s2A_after_B_no_selection"] = s2a["selection_present"] is False
    checks["s2B_6_refs"] = s2b["session_ref_count"] == 6
    # ledger strictly increasing, one physical JSONL
    counts = [e.get("ledger_count_after", {}).get("count_json", {}).get("count")
              for e in chain["steps"]]
    checks["ledger_strictly_increasing"] = all(
        isinstance(c, int) and c > 0 for c in counts
    ) and all(b > a for a, b in zip(counts, counts[1:]))
    checks["one_physical_ledger"] = len(
        {e.get("ledger_count_after", {}).get("history") for e in chain["steps"]}
    ) == 1
    checks["no_driver_error"] = all(e.get("driver_error") is None for e in chain["steps"])
    checks["verdict"] = "PASS" if all(v is True for k, v in checks.items()) else "FAIL"
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="qa-serial")
    args = ap.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Brand-new unique QA phase root; NEVER the formal cohort2 root.
    shared_root = QMC.QA_SERIAL_PHASE_ROOT.parent / f"{QMC.QA_SERIAL_PHASE_ROOT.name}-{stamp}"
    chain = run_chain(shared_root)
    checks = _evaluate(chain)
    summary = {
        "utc": stamp,
        "label": args.label,
        "shared_phase_root": str(shared_root),
        "formal_phase_root_reserved": str(QMC.FORMAL_PHASE_DATA_DIR),
        "formal_phase_root_created": QMC.FORMAL_PHASE_DATA_DIR.exists(),
        "real_provider_generation": 0,
        "checks": checks,
        "verdict": checks["verdict"],
    }
    QMC.QA_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QMC.QA_EVIDENCE_DIR / f"serial-chain-{stamp}.json"
    dest.write_text(json.dumps({"summary": summary, "chain": chain}, indent=2,
                               sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    print(json.dumps(summary, indent=2, default=str))
    print(f"WROTE {dest}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
