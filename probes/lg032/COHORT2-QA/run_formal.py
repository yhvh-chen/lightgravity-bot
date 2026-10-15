#!/usr/bin/env python3
"""LG-032 COHORT2 formal attempt runner (real provider, one attempt per call).

This is the cohort2 **formal entry point** whose absence was recorded as the
single gate-4 gap in ``COHORT2-QA/REPORT-SERIAL-R1.md`` §5/§8.  It is the
cohort2 equivalent of ``METHOD-FINAL/probes/run_formal.py`` and:

* installs the ALREADY-AUDITED cohort2 overlay
  (``probes/lg032/MODE-ISOLATION/mode_config.py`` -> ``install()``) FIRST, so the
  ONE phase ``settings.data_dir`` is the frozen formal root
  ``/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`` -- **never**
  the cohort-ready / method-final root used by an old driver invocation;
* delegates to the byte-identical, audited driver function
  ``run_attempt.run_attempt`` with ``dry_run=False`` -- no logic is copied and
  the driver's mode/fairness/ledger semantics are NOT altered;
* redirects ONLY the ``runs`` / ``evidence`` output roots to a fresh, independent
  cohort2-formal location (never METHOD-FINAL / FINAL-COHORT);
* never writes the key anywhere, never switches the provider, and never creates
  the formal phase root unless a real attempt is actually started.

The frozen command is documented in ``COHORT2-FORMAL-FREEZE.md``; the secret is
read from ``DEEPSEEK_API_KEY`` in the environment and its VALUE is never printed
or recorded.

Read-only identity check (creates no root, no runtime, no Task, no model call)::

    .venv/bin/python probes/lg032/COHORT2-QA/run_formal.py --freeze-identity

Formal attempt (PM-authorised only; one attempt id runs once)::

    DEEPSEEK_API_KEY=... .venv/bin/python \
        probes/lg032/COHORT2-QA/run_formal.py --sample s1_units --arm A
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# ------------------------------------------------------------- frozen identity
#: This QA worktree (frozen actual root owner).  Driver bytes are read from the
#: local FINAL-COHORT harness (byte-identical to the fix worktree's harness).
WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa")
COHORT = WORKTREE / "probes" / "lg032" / "FINAL-COHORT"
HARNESS_DIR = COHORT / "harness"
MODE_DIR = WORKTREE / "probes" / "lg032" / "MODE-ISOLATION"
ENTRY = Path(__file__).resolve()

#: The ONE actual persistent formal phase data root (frozen, MUST equal the fix
#: owner's declared ``MODE-ISOLATION/mode_config.PHASE_DATA_DIR``).
FORMAL_PHASE_DATA_DIR = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data"
)

#: Independent cohort2-formal OUTPUT roots (new, unique; NEVER METHOD-FINAL /
#: FINAL-COHORT / cohort-ready).  These live OUTSIDE the repo so no old package's
#: immutable attempt output can ever be overwritten or scanned.
FORMAL_OUTPUT_DIR = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal"
)
FORMAL_RUNS_DIR = FORMAL_OUTPUT_DIR / "runs"
FORMAL_EVIDENCE_DIR = FORMAL_OUTPUT_DIR / "evidence"

#: Frozen declared arm polarity (the driver's own ``_set_mode`` writes exactly
#: these; this is a DECLARATION only -- ``--freeze-identity`` does not write).
MODE_POLARITY = {
    "A": "program-scheduler / autonomous_pool=off / decentralized_claim=off (explicit False)",
    "B": "candidate-pool autonomous / autonomous_pool=on / decentralized_claim=on (explicit True)",
}

FROZEN_DRIVER_SHA256 = {
    "run_attempt.py": "503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208",
    "final_cohort_config.py": "a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_overlay_config() -> "object":
    """Load the audited cohort2 overlay and install it (path constants only).

    The overlay is imported READ-ONLY from ``MODE-ISOLATION/mode_config.py`` and
    adapted ENTRY-LOCALLY to this worktree's byte-identical harness + fixtures
    (the fixtures already carry the frozen seed repos).  No driver / overlay byte
    is edited and no product policy is changed.
    """

    if str(MODE_DIR) not in sys.path:
        sys.path.insert(0, str(MODE_DIR))
    import mode_config as MC  # noqa: PLC0415

    # Entry-local path adaptation: point harness/cohort at THIS worktree.  The
    # frozen actual root is derived from WORKTREE.parent, identical either way.
    MC.WORKTREE = WORKTREE
    MC.COHORT = COHORT
    MC.HARNESS_DIR = HARNESS_DIR
    MC.MODE_DIR = MODE_DIR
    MC.RUNS_DIR = FORMAL_RUNS_DIR
    MC.EVIDENCE_DIR = FORMAL_EVIDENCE_DIR
    MC.FIXTURES_DIR = COHORT / "fixtures"
    MC.PHASE_DATA_DIR = FORMAL_PHASE_DATA_DIR
    MC.LEDGER_DIR = FORMAL_PHASE_DATA_DIR / "generation"
    MC.LEDGER_HISTORY = MC.LEDGER_DIR / "generation.jsonl"
    MC.LEDGER_COUNT = MC.LEDGER_DIR / "generation.count.json"

    C = MC.install()

    # install() re-derives RUNS_DIR/EVIDENCE_DIR from the module globals; pin the
    # independent formal output roots explicitly (entry-local only).
    C.RUNS_DIR = FORMAL_RUNS_DIR
    C.EVIDENCE_DIR = FORMAL_EVIDENCE_DIR
    C.FIXTURES_DIR = COHORT / "fixtures"
    return C


def _frozen_source_tree() -> str:
    """The frozen product tree object for ``backend/lightgravity`` (read-only)."""

    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD:backend/lightgravity"],
            cwd=str(WORKTREE), capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception as exc:  # pragma: no cover - defensive
        return f"<unavailable: {exc}>"


def _print_identity(C: "object") -> int:
    """Print the non-sensitive config identity.  Creates NOTHING.

    Deliberately BEFORE any runtime / proxy / Task / model call / formal root
    creation.  Never prints credential / env / secret values.
    """

    assert C.PHASE_DATA_DIR == FORMAL_PHASE_DATA_DIR, (
        f"overlay root {C.PHASE_DATA_DIR} != frozen {FORMAL_PHASE_DATA_DIR}"
    )
    assert C.RUNS_DIR == FORMAL_RUNS_DIR
    assert C.EVIDENCE_DIR == FORMAL_EVIDENCE_DIR

    import run_attempt as R  # noqa: PLC0415

    print("== LG-032 COHORT2 formal entry — freeze identity (read-only) ==")
    print(f"entry            : {ENTRY}")
    print(f"entry_sha256     : {_sha256(ENTRY)}")
    print(f"overlay          : {MODE_DIR / 'mode_config.py'}")
    print(f"overlay_sha256   : {_sha256(MODE_DIR / 'mode_config.py')}")
    print(f"driver           : {HARNESS_DIR / 'run_attempt.py'}")
    for name, want in FROZEN_DRIVER_SHA256.items():
        got = _sha256(HARNESS_DIR / name)
        flag = "OK" if got == want else "MISMATCH"
        print(f"driver_{name}_sha256 : {got} [{flag}]")
    print(f"harness_dir      : {HARNESS_DIR}")
    print(f"fixtures_dir     : {C.FIXTURES_DIR}")
    print(f"phaseRoot        : {C.PHASE_DATA_DIR}")
    print(f"phaseRoot_exists : {C.PHASE_DATA_DIR.exists()}")
    print(f"ledgerPath       : {C.LEDGER_HISTORY}")
    print(f"RUNS_DIR         : {C.RUNS_DIR}")
    print(f"EVIDENCE_DIR     : {C.EVIDENCE_DIR}")
    print(f"outputRoot_exists: {FORMAL_OUTPUT_DIR.exists()}")
    print(f"attempt_ids      : {[f'{s}__{a}' for s, a in C.ATTEMPTS]}")
    print(f"total_limit      : {C.TOTAL_GENERATION_LIMIT}")
    print(f"attempt_limit    : {C.ATTEMPT_GENERATION_LIMIT}")
    print(f"sdk/contract     : {C.SDK_VERSION} / {C.CONTRACT_VERSION}")
    print(f"model/base_url   : {C.MODEL} @ {C.BASE_URL} (credential_ref={C.CREDENTIAL_REF})")
    print(f"sample_spec      : {sorted(R.SAMPLE_SPEC)}")
    print(f"source_tree      : {_frozen_source_tree()}")
    print(f"product_base_commit  : {C.PRODUCT_BASE_COMMIT}")
    print(f"product_fix_commit   : {C.PRODUCT_FIX_COMMIT}")
    print("mode_polarity    :")
    for arm in ("A", "B"):
        print(f"  {arm}: {MODE_POLARITY[arm]}")
    print("secrets          : <not printed; read from env DEEPSEEK_API_KEY>")
    print("== end freeze identity ==")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LG-032 COHORT2 formal entry (loads cohort2 overlay, then the frozen driver)"
    )
    ap.add_argument("--sample", choices=["s1_units", "s2_pipeline"])
    ap.add_argument("--arm", choices=["A", "B"])
    ap.add_argument(
        "--freeze-identity",
        action="store_true",
        help="read-only: print non-sensitive frozen config identity and exit "
             "(creates no root/runtime/Task/model call)",
    )
    args = ap.parse_args()

    C = _load_overlay_config()

    if args.freeze_identity:
        return _print_identity(C)

    if not args.sample or not args.arm:
        ap.error("--sample and --arm are required for a formal attempt")

    sys.path.insert(0, str(HARNESS_DIR))
    import run_attempt as R  # noqa: PLC0415

    # Same audited driver function; real provider; one attempt id, once.
    return R.run_attempt(args.sample, args.arm, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
