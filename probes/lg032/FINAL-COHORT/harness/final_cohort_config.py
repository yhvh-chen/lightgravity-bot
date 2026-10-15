"""LG-032 FINAL-COHORT frozen protocol configuration (PM pre-registered).

Single source of truth for the final-cohort protocol.  Every number below is
frozen **before the first real DeepSeek request** and must not change afterwards.
Free of product imports so any harness / prover / report reader can use it
without starting a runtime.

Pre-registration (PM, 2026-10-16) -- see ``../PLAN.md``:

* 2 samples x 2 arms x 1 repeat = **exactly 4 attempts**, each attempt runs once
  (immutable attempt-id output dir; a second run of the same id is refused).
* Total real generation cap **192**; per attempt cap **48** (4 x 48 = 192).
  Both are enforced **before forwarding** on the ONE persistent phase ledger.
* One phase ``settings.data_dir`` shared by every serial attempt / runtime start,
  so the product ``configure_generation_ledger(settings.data_dir)`` naturally
  continues the same physical JSONL across two runtime starts.  Worker, sel
  selector, verifier and reviewer all charge the same ledger; a corrupt ledger
  fails closed and is NEVER read as 0.
* output <= 16000 tokens / HTTP timeout 120s / SDK retries 0 / concurrency 1.
* At most ONE product business rework per attempt, identical for both arms,
  charged inside the attempt cap; no new orchestration agent.
* Old 023 cohorts (45/4/16), old 022 and old LG-031 (34+24+28=86) are listed
  separately and are NOT merged into this cohort or washed to 0.
"""

from __future__ import annotations

from pathlib import Path

# ------------------------------------------------------------------ paths
#: Project-adjacent, persistent, never a TemporaryDirectory.
#: LG-032 cohort-ready: the protocol moved to its own worktree after the
#: workspace-boundary product fix was safely merged.  The previous harness
#: worktree (`lg032-final-cohort`) and its data roots are PRESERVED verbatim as
#: history and are never written to again (preservation incident rule).
WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort-ready")
COHORT = WORKTREE / "probes" / "lg032" / "FINAL-COHORT"

#: The ONE controlled persistent phase data root for the WHOLE cohort.
#: Passed verbatim as ``Settings.data_dir`` for every serial attempt / runtime
#: start, so the product ledger rooted at ``data_dir/generation`` IS the single
#: phase ledger (fixes the 023 cohort-2 D1 per-attempt-ledger defect).
#: Kept as a distinct (fresh) root for the cohort-ready phase; the formal
#: attempt ledger has never been started, so this is not a reset of any data.
PHASE_DATA_DIR = WORKTREE.parent / "lg032-cohort-ready-data"

#: Product's OWN layout under ``data_dir``.
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"
LEDGER_COUNT = LEDGER_DIR / "generation.count.json"

#: Immutable per-attempt output root (created once, never overwritten).
RUNS_DIR = COHORT / "runs"
EVIDENCE_DIR = COHORT / "evidence"
FIXTURES_DIR = COHORT / "fixtures"

# ------------------------------------------------------------- budget/limits
#: The single real-DeepSeek generation hard cap for the ENTIRE cohort.
TOTAL_GENERATION_LIMIT = 192
#: Per-attempt hard cap (2 arms x 2 samples x 1 run, 4 x 48 = 192).
ATTEMPT_GENERATION_LIMIT = 48

#: Frozen per-request / transport limits.
OUTPUT_TOKEN_CAP = 16000
HTTP_TIMEOUT_SECONDS = 120
SDK_RETRIES = 0
MAX_CONCURRENCY = 1

#: Frozen worker budget (identical for both arms).
WORKER_MODEL_CALLS = 12
WORKER_TOOL_CALLS = 32
#: Frozen reviewer budget (independent role, same ledger).
REVIEWER_MODEL_CALLS = 1
#: At most one product business rework per attempt, identical for both arms.
MAX_REWORKS_PER_ATTEMPT = 1

#: Frozen experiment shape.
SAMPLES = ("s1_units", "s2_pipeline")
ARMS = ("A", "B")
ATTEMPTS = (
    ("s1_units", "A"),
    ("s1_units", "B"),
    ("s2_pipeline", "A"),
    ("s2_pipeline", "B"),
)

#: Frozen SDK/model/contract identity (asserted at runtime, never switched).
SDK_VERSION = "0.1.22"
CONTRACT_VERSION = "1.11.0"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
CREDENTIAL_REF = "deepseek-api-key"

#: Product tree the cohort snapshot is pinned to.
#: Product tree the cohort-ready harness is pinned to: the workspace-boundary
#: fix (selection scratch rooted inside the executor authorized root), safely
#: merged onto the final-cohort WIP base.  Product real generation stays 0.
PRODUCT_BASE_COMMIT = "a29e94f"
PRODUCT_FIX_COMMIT = "0814b80"


def phase_env() -> dict[str, str]:
    """Environment overrides pinning every stage to the one ledger/limit.

    ``LIGHTGRAVITY_DATA_DIR`` and ``LIGHTGRAVITY_GENERATION_LEDGER_DIR`` both
    point at the one phase root, consistent with (not a replacement for) the
    product's own ``configure_generation_ledger(settings.data_dir)`` call.
    """

    return {
        "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_DATA_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(TOTAL_GENERATION_LIMIT),
    }


def attempt_root(attempt_id: str) -> Path:
    """Per-attempt isolation root (workspaces/secrets), NOT data_dir."""

    return PHASE_DATA_DIR / "attempts" / attempt_id


# ------------------------------------------------------- preservation (dry)
#: Legacy fixed dry root.  It is PRESERVED verbatim as history and is NEVER
#: written to or deleted again.  New dry runs MUST use a unique path instead
#: (see ``new_dry_root``) so no prior attempt output can ever be clobbered.
LEGACY_DRY_DATA_DIR = PHASE_DATA_DIR.parent / "lg032-final-cohort-data-dry"
#: Phase-1 harness data root (lg032-final-cohort); preserved, never written now.
LEGACY_PHASE_DATA_DIR = PHASE_DATA_DIR.parent / "lg032-final-cohort-data"


def new_dry_root(label: str = "dry") -> Path:
    """A brand-new unique dry data root (UTC timestamp + nonce).

    Preservation incident fix: the prior owner repeatedly ``rm -rf``-ed the
    single fixed dry root to reuse it, destroying each earlier attempt's
    output.  Every dry run now gets its own immutable root; the legacy fixed
    path is left untouched and nothing is ever removed.

    The FORMAL ``PHASE_DATA_DIR`` and the four frozen attempt ids are NOT
    affected by this uniqueness -- per-attempt dry UUIDs may never be used to
    bypass the single parent phase-ledger requirement for formal runs.
    """

    import datetime as _dt
    import os as _os
    import uuid as _uuid

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = (_os.environ.get("LG032_DRY_NONCE") or _uuid.uuid4().hex[:8]).strip()
    root = PHASE_DATA_DIR.parent / f"{PHASE_DATA_DIR.name}-{label}-{stamp}-{nonce}"
    if root.exists():  # never reuse / never delete; add a further nonce
        root = root.with_name(root.name + "-" + _uuid.uuid4().hex[:6])
    return root


__all__ = [
    "ARMS",
    "ATTEMPT_GENERATION_LIMIT",
    "ATTEMPTS",
    "BASE_URL",
    "COHORT",
    "CONTRACT_VERSION",
    "CREDENTIAL_REF",
    "EVIDENCE_DIR",
    "FIXTURES_DIR",
    "HTTP_TIMEOUT_SECONDS",
    "LEDGER_COUNT",
    "LEDGER_DIR",
    "LEDGER_HISTORY",
    "LEGACY_DRY_DATA_DIR",
    "LEGACY_PHASE_DATA_DIR",
    "MAX_CONCURRENCY",
    "MAX_REWORKS_PER_ATTEMPT",
    "MODEL",
    "OUTPUT_TOKEN_CAP",
    "PHASE_DATA_DIR",
    "PRODUCT_BASE_COMMIT",
    "REVIEWER_MODEL_CALLS",
    "RUNS_DIR",
    "SAMPLES",
    "SDK_RETRIES",
    "SDK_VERSION",
    "TOTAL_GENERATION_LIMIT",
    "WORKER_MODEL_CALLS",
    "WORKER_TOOL_CALLS",
    "WORKTREE",
    "attempt_root",
    "new_dry_root",
    "phase_env",
]
