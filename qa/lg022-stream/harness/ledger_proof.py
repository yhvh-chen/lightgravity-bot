"""LG-022 stream-stop QA — offline persistent generation-ledger hard gate.

Independent proof (0 model calls) that the *persistent* generation ledger is the
single path/limit for the whole phase and behaves correctly:

  L1  a single controlled ledger at the frozen path persists across a fresh
      ``PersistentGenerationLedger`` instance (simulating a service restart):
      reserve -> new instance -> count does NOT reset to 0;
  L2  a fresh *process* (separate interpreter) reading the SAME path sees the
      cumulative count (true cross-process/cross-restart, not just in-instance);
  L3  the hard cap is enforced on the frozen limit and ``remaining`` decreases;
  L4  a corrupted history is fail-closed: ``reserve`` refuses with
      ``corrupt=True`` and the diagnostics snapshot reports ``corrupt`` -- never
      silently reset to 0 (uses a throwaway copy, never the frozen ledger);
  L5  the same (path, limit) is handed to every stage via ``phase_env()`` and
      the product resolves the ledger to exactly that path
      (``ledger_root_from_env`` under the phase env).

Writes only under the frozen phase data dir (L1/L2/L3) and a scratch copy for
the corruption case; never touches the product tree.

Run: .venv/bin/python qa/lg022-stream/harness/ledger_proof.py <evidence.json>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "backend"))

import unified_phase_ledger_config as cfg  # noqa: E402

from lightgravity.adapter.generation_ledger import (  # noqa: E402
    GenerationLedgerCorrupt,
    PersistentGenerationLedger,
)

# A dedicated, *reset-able* sub-ledger for this proof so the phase's real ledger
# (used by the main chain) stays pristine.  It lives under the same frozen root,
# proving the same persistence semantics at the controlled dataRoot.
PROOF_DIR = cfg.PHASE_DATA_DIR / "ledger-proof"


def _fresh_ledger(limit: int = cfg.PHASE_GENERATION_LIMIT) -> PersistentGenerationLedger:
    return PersistentGenerationLedger(PROOF_DIR, limit=limit)


def _reset_proof_dir() -> None:
    if PROOF_DIR.exists():
        shutil.rmtree(PROOF_DIR)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)


_CROSS_PROCESS = r"""
import json, sys
sys.path.insert(0, {backend!r})
from pathlib import Path
from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
led = PersistentGenerationLedger(Path({root!r}), limit={limit})
res = led.reserve()
print(json.dumps({{"count": led.count(), "granted": res.granted,
                   "count_after": res.count, "remaining": res.remaining}}))
"""


def main() -> int:
    out_path = Path(sys.argv[1])
    out: dict = {
        "phase_data_dir": str(cfg.PHASE_DATA_DIR),
        "phase_limit": cfg.PHASE_GENERATION_LIMIT,
        "proof_dir": str(PROOF_DIR),
        "env": cfg.phase_env(),
        "checks": {},
    }
    checks = out["checks"]
    try:
        _reset_proof_dir()

        # L1: in-instance + fresh-instance persistence (restart simulation).
        led = _fresh_ledger()
        r1 = led.reserve()
        r2 = led.reserve()
        count_after_two = led.count()
        led_restart = _fresh_ledger()  # simulates a new service process
        count_restart = led_restart.count()
        checks["L1_single_ledger_persists_across_instance"] = {
            "pass": (
                r1.granted and r2.granted and count_after_two == 2
                and count_restart == 2
            ),
            "count_after_two_reserves": count_after_two,
            "count_after_fresh_instance": count_restart,
            "reserves": [r1.count, r2.count],
        }

        # L2: genuine separate process reads the SAME path.
        proc = subprocess.run(
            [sys.executable, "-c", _CROSS_PROCESS.format(
                backend=str(REPO / "backend"), root=str(PROOF_DIR),
                limit=cfg.PHASE_GENERATION_LIMIT)],
            capture_output=True, text=True, timeout=60, cwd=str(REPO),
        )
        cross = json.loads(proc.stdout) if proc.returncode == 0 else {}
        checks["L2_cross_process_sees_cumulative"] = {
            "pass": (
                proc.returncode == 0 and cross.get("granted") is True
                and cross.get("count_after") == 3 and cross.get("count") == 3
            ),
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr_tail": proc.stderr.strip()[-400:],
        }

        # L3: hard cap enforced at the frozen limit (use a small dedicated cap so
        # the test is bounded and independent of how many reserves L1/L2 made).
        cap_dir = cfg.PHASE_DATA_DIR / "ledger-proof-cap"
        if cap_dir.exists():
            shutil.rmtree(cap_dir)
        cap = PersistentGenerationLedger(cap_dir, limit=2)
        grants = [cap.reserve().granted for _ in range(3)]
        last = cap.reserve()
        checks["L3_hard_cap_enforced"] = {
            "pass": grants == [True, True, False] and last.granted is False
            and last.remaining == 0 and cap.count() == 2,
            "grants": grants,
            "count": cap.count(),
            "refused_remaining": last.remaining,
            "refused_reason": last.reason,
        }

        # L4: corruption is fail-closed and reported, never reset to 0.
        corrupt_dir = cfg.PHASE_DATA_DIR / "ledger-proof-corrupt"
        if corrupt_dir.exists():
            shutil.rmtree(corrupt_dir)
        (corrupt_dir / "generation").mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "generation" / "generation.jsonl").write_text(
            "{not valid json}\n", encoding="utf-8"
        )
        bad = PersistentGenerationLedger(corrupt_dir, limit=cfg.PHASE_GENERATION_LIMIT)
        refused = bad.reserve()
        snap = bad.snapshot()
        raised = False
        try:
            bad.count()
        except GenerationLedgerCorrupt:
            raised = True
        checks["L4_corruption_fail_closed"] = {
            "pass": (
                refused.granted is False and refused.corrupt is True
                and snap.get("corrupt") is True and snap.get("count") is None
                and raised
            ),
            "refused_granted": refused.granted,
            "refused_corrupt": refused.corrupt,
            "snapshot_corrupt": snap.get("corrupt"),
            "snapshot_count_is_none": snap.get("count") is None,
            "count_raised": raised,
            "reason": refused.reason,
        }

        # L5: the product resolves the ledger to exactly the frozen path under
        # the phase env (so every stage is wired to the same ledger).
        os.environ.update(cfg.phase_env())
        from lightgravity.adapter.generation_ledger import ledger_root_from_env
        resolved = ledger_root_from_env()
        checks["L5_env_wires_single_path"] = {
            "pass": resolved == cfg.PHASE_DATA_DIR,
            "resolved": str(resolved) if resolved else None,
            "expected": str(cfg.PHASE_DATA_DIR),
            "limit_env": os.environ.get("LIGHTGRAVITY_MAX_GENERATION_CALLS"),
        }
    finally:
        out["ok"] = all(c.get("pass") is True for c in checks.values())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
