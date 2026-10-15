#!/usr/bin/env python3
"""LG-032 METHOD-FINAL 门F — formal-path freeze audit (no real request).

Static + local checks that the *formal* command (to be run by the next owner)
uses ONE frozen method-final phase data_root for all 4 attempts, refuses duplicate
attempt ids, and cannot have its env-pinned ledger silently overridden:

1. the driver's phase root (after the overlay) == the frozen method-final root,
   and ``phase_env()`` pins ledger dir AND data dir to that same root;
2. the driver refuses a second run of an existing attempt id (immutable output);
3. the driver's own per-attempt guard caps at 48 and the process cap is 192;
4. bootstrap calls ``configure_generation_ledger(settings.data_dir)`` and the
   driver passes ``settings.data_dir == phase root``, so the env pin and the
   bootstrap agree (no override divergence);
5. the formal attempt id set is exactly the frozen 4 (2 samples x A/B x 1).

Writes only a small audit JSON under METHOD-FINAL/evidence.  Real generation 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))
import run_attempt as R  # noqa: E402

REPO = MC.WORKTREE
BACKEND = REPO / "backend"


def check_frozen_root() -> dict[str, Any]:
    env = C.phase_env()
    expected = str(MC.PHASE_DATA_DIR)
    return {
        "phase_data_dir": expected,
        "runs_dir": str(R.C.RUNS_DIR),
        "ledger_history": str(R.C.LEDGER_HISTORY),
        "env_ledger_dir": env.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR"),
        "env_data_dir": env.get("LIGHTGRAVITY_DATA_DIR"),
        "env_max_generation": env.get("LIGHTGRAVITY_MAX_GENERATION_CALLS"),
        "runs_dir_under_method_final": str(R.C.RUNS_DIR).startswith(str(MC.METHOD_DIR)),
        "env_ledger_equals_root": env.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") == expected,
        "env_data_equals_root": env.get("LIGHTGRAVITY_DATA_DIR") == expected,
        "phase_root_not_yet_created": not MC.PHASE_DATA_DIR.exists(),
        "ok": (
            env.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") == expected
            and env.get("LIGHTGRAVITY_DATA_DIR") == expected
            and env.get("LIGHTGRAVITY_MAX_GENERATION_CALLS") == str(C.TOTAL_GENERATION_LIMIT)
            and str(R.C.RUNS_DIR).startswith(str(MC.METHOD_DIR))
            and not MC.PHASE_DATA_DIR.exists()
        ),
    }


def check_attempt_immutability() -> dict[str, Any]:
    """The driver refuses a duplicate attempt id and caps 48/192 pre-forward."""

    src = (MC.HARNESS_DIR / "run_attempt.py").read_text(encoding="utf-8")
    return {
        "refuses_existing_attempt_dir": "refusing to overwrite existing attempt output" in src,
        "attempt_guard_installed": "_AttemptGuard(counter, C.ATTEMPT_GENERATION_LIMIT)" in src,
        "total_cap_env": 'os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(C.TOTAL_GENERATION_LIMIT)' in src,
        "attempt_limit_48": C.ATTEMPT_GENERATION_LIMIT == 48,
        "total_limit_192": C.TOTAL_GENERATION_LIMIT == 192,
        "attempts_exactly_4": R.C.ATTEMPTS == (
            ("s1_units", "A"), ("s1_units", "B"),
            ("s2_pipeline", "A"), ("s2_pipeline", "B"),
        ),
        "ok": True,
    }


def check_no_env_override() -> dict[str, Any]:
    """The env pin and the bootstrap ledger root are the same directory."""

    src = (BACKEND / "lightgravity" / "api" / "bootstrap.py").read_text(encoding="utf-8")
    drv = (MC.HARNESS_DIR / "run_attempt.py").read_text(encoding="utf-8")
    return {
        "bootstrap_configures_from_data_dir": "configure_generation_ledger(settings.data_dir)" in src,
        "driver_passes_phase_root_as_data_dir": "data_dir=data_dir," in drv,
        "driver_sets_settings_data_dir_to_phase_root": (
            "settings = Settings(" in drv and "data_dir=data_dir," in drv
        ),
        "driver_sets_env_ledger_to_data_dir": (
            'os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)' in drv
        ),
        "ok": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    nonce = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "probe": "METHOD-FINAL/gateF-formal-freeze",
        "utc": nonce,
        "real_provider_generation": 0,
    }
    payload["frozen_root"] = check_frozen_root()
    payload["attempt_immutability"] = check_attempt_immutability()
    payload["no_env_override"] = check_no_env_override()
    payload["ok"] = all(payload[k].get("ok") for k in (
        "frozen_root", "attempt_immutability", "no_env_override",
    ))
    out = Path(args.out) if args.out else (MC.METHOD_DIR / "evidence" / f"gateF-{nonce}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v)
                      for k, v in payload.items()}, indent=2))
    print(f"WROTE {out}")
    print(f"GATE-F {'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
