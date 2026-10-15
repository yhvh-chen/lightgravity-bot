"""LG-022 reverify R2 — SUPPLY-ONLY unified phase-ledger runner (NOT executed).

Why this file exists
--------------------
The R2 REPORT summed "main chain 7 + light QA 1 = 8/10", but the two original
evidence files show the two stages ran against **different** data dirs with
**different** limits:

  * main chain  : ``/tmp/lg022-r2-real/data/generation``     limit=10 count=7
  * light QA    : ``/tmp/lg022-r2-lightqa/data/generation``  limit=3  count=1

So no single persistent phase ledger ever enforced a unified hard cap.  That is
a QA **process** gap (NOT a product ledger defect — the product ledger semantics
are independently proven in ``evidence/ledger-proof.json``).

This module is a *config/coordination* helper that enforces the fix going
forward, WITHOUT re-running anything here and WITHOUT touching historical
evidence.  It is intentionally NOT invoked by this closing package (0 real
model calls in this package).

Required config for future 024/023 (and any QA harness)
-------------------------------------------------------
1. ONE data dir per run: main chain + every auxiliary probe (light Q&A, etc.)
   must receive the SAME ``data_dir`` so they share
   ``<data_dir>/generation/`` (generation.jsonl + generation.count.json).
2. ONE ``LG022_GEN_LIMIT``: the value baked into each harness default AND the
   value on the command line must be identical (e.g. 10).  Never rely on
   differing per-script defaults (10 vs 3).
3. Aux probes must RESERVE into the shared ledger (no separate data_dir / no
   separate limit), so ``count`` / ``remaining`` is monotone across stages.
4. Report the unified ledger ``count`` only — never sum counts from independent
   ledgers to fake a single hard-capped total.
5. Keep old scripts/evidence unchanged (hashes below); add corrected scripts or
   an explicit diff instead.

Frozen hashes of the ORIGINAL harness scripts (do not rewrite in place):
"""

from __future__ import annotations

import os

# Original harness SHA-256 (frozen 2026-10-16, closing supplement commit).
ORIGINAL_HARNESS_SHA256 = {
    "deterministic_probe_r2.py": "fc95283cc8b8ee91867c9fc562533f4e01fb12ba899b3df0cbc449c8553f7357",
    "ledger_proof.py": "5b7d5400eb57a8cc783e056ef1d5c0bb4abe3613c773950f7dae13ab8fb78853",
    "light_qa_probe.py": "e73e9e9df682345335cf85a4d8c22af69adabac6b3db7c38c04d77814e9f8a72",
    "real_chain_r2.py": "98da253c2e721ecc9fa0ece1b37fff0a6f5d5396b9a1e112cf0343ef2c38ce89",
    "review_cancel_sdk_proof.py": "ce4a6ba9f9c496d33a239133f124d0d53ce6383ff4a9f00385333acc51a587a7",
    "service_ledger_proof.py": "af4cbbf5bd3e1d73fe08f846f5fc8d1918ac6f29b18bf487b5d608e65b4b593a",
    "stopgate_proof.py": "7c326b68c59c2f0939b002421143a31dbac70942a6a3839fa88bc62d4dc9ae95",
}

# Single source of truth for the unified phase budget.
UNIFIED_GEN_LIMIT_ENV = "LG022_GEN_LIMIT"
UNIFIED_GEN_LIMIT_DEFAULT = 10


def unified_generation_limit() -> int:
    """Return the ONE limit that every stage must use."""
    return int(os.environ.get(UNIFIED_GEN_LIMIT_ENV, str(UNIFIED_GEN_LIMIT_DEFAULT)))


def apply_unified_env() -> int:
    """Force the process-wide product cap to the unified value.

    Call BEFORE ``build_runtime`` so worker/reviewer/light-QA all reserve into
    the same persistent ledger.  Never called by the closing package.
    """
    limit = unified_generation_limit()
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(limit)
    return limit


def validate_run_config(*, data_dirs: list[str], limits: list[int]) -> list[str]:
    """Return a list of violations for a (would-be) run configuration.

    Empty list == config is unified: exactly ONE data dir and ONE limit.
    """
    problems: list[str] = []
    uniq_dirs = sorted(set(data_dirs))
    if len(uniq_dirs) != 1:
        problems.append(
            f"stages must share ONE data_dir (got {len(uniq_dirs)}): {uniq_dirs}; "
            "separate dirs == separate ledgers == no unified hard cap"
        )
    if len(set(limits)) != 1:
        problems.append(
            f"stages must share ONE limit (got {sorted(set(limits))}); "
            "differing limits == no unified hard cap"
        )
    return problems


if __name__ == "__main__":  # pragma: no cover - documentation only
    raise SystemExit(
        "Supply-only helper: this file is NOT run by the closing package. "
        "Use it from future 024/023 runners to enforce one data_dir + one limit."
    )
