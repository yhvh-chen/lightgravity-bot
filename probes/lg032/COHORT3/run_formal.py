#!/usr/bin/env python3
"""LG-032 COHORT3 formal attempt runner (minimal directory-assembly repair).

Background (why a NEW entry file exists)
----------------------------------------
COHORT2's formal entry (``probes/lg032/COHORT2-QA/run_formal.py``) redirected
``C.EVIDENCE_DIR`` to a *fresh, independent* output root but *neither the entry
nor the frozen driver ever created that directory*.  On the first real attempt
this deterministically raised::

    FileNotFoundError: ...
      '/home/yhvh/.../lg032-cohort2-formal/evidence/s1_units__A.json'
      at run_attempt.py:888  (C.EVIDENCE_DIR / f"{attempt_id}.json").write_text(...)

The old layout never exposed this because ``EVIDENCE_DIR`` used to be a
*pre-existing committed repo directory* (``COHORT/evidence``).  The independent
formal root made the latent defect fatal (recorded as the COHORT2 STOP).

This COHORT3 entry is the *minimal assembly repair* requested by the PM:

* it installs the ALREADY-AUDITED mode-fixed overlay
  (``probes/lg032/MODE-ISOLATION/mode_config.py`` -> ``install()``) FIRST;
* it reuses the byte-identical, already-QA'd frozen driver
  ``run_attempt.run_attempt(..., dry_run=False)`` -- **no** driver / budget /
  model / tool / stop / state / mode logic is copied or altered;
* it adds ONE new, controlled step: :func:`prepare_output_roots` pre-creates the
  independent cohort3 output roots ``<root>/runs`` and ``<root>/evidence``
  (mode ``700``) so the driver's evidence write has an existing parent.  The
  SAME function is invoked by ``--prepare-only`` and by a real attempt, so the
  preflight exercises the exact code path the formal run uses.

Controlled paths (frozen, fixed by the PM for COHORT3)
------------------------------------------------------
* phase data root      : ``/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data``
* formal output root   : ``/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal``
* formal RUNS_DIR      : ``<output root>/runs``
* formal EVIDENCE_DIR  : ``<output root>/evidence``

The phase data root is deliberately **not** created by ``--prepare-only`` (the
driver creates it on a real attempt); only the two output dirs are assembled.

Modes
-----
Read-only identity (creates NOTHING)::

    .venv/bin/python probes/lg032/COHORT3/run_formal.py --freeze-identity

Controlled directory preflight (creates ONLY the two output dirs, no runtime /
Task / proxy / SDK / generation; records the side effect in a fresh NONCE
scratch)::

    .venv/bin/python probes/lg032/COHORT3/run_formal.py --prepare-only

Formal attempt (PM-authorised only; one attempt id runs once)::

    DEEPSEEK_API_KEY=... .venv/bin/python \
        probes/lg032/COHORT3/run_formal.py --sample s1_units --arm A

Old COHORT1 (87 mode-invalid) and COHORT2 (19 real reservations, entry
assembly STOP) raw data / runs / ledgers / reports / worktrees are NEVER
deleted, modified or "repaired": the 106-protocol-failure cost stays a separate
line.  Nothing here appends to, zeroes, or rewrites an old attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
import time
from pathlib import Path

# ------------------------------------------------------------- frozen identity
#: This fix worktree (frozen actual root owner).  Driver bytes are read from the
#: local FINAL-COHORT harness (byte-identical to the cohort2-qa harness).
WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry")
#: The single controlled parent for the independent output root (never widened).
WORKTREES_DIR = WORKTREE.parent
COHORT = WORKTREE / "probes" / "lg032" / "FINAL-COHORT"
HARNESS_DIR = COHORT / "harness"
MODE_DIR = WORKTREE / "probes" / "lg032" / "MODE-ISOLATION"
ENTRY = Path(__file__).resolve()

#: The ONE actual persistent formal phase data root for COHORT3 (frozen).
FORMAL_PHASE_DATA_DIR = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data"
)

#: Independent COHORT3-formal OUTPUT roots (new, unique; NEVER cohort2-formal /
#: METHOD-FINAL / FINAL-COHORT / cohort-ready).  They live OUTSIDE the repo so
#: no old package's immutable attempt output can ever be overwritten or scanned.
FORMAL_OUTPUT_DIR = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal"
)
FORMAL_RUNS_DIR = FORMAL_OUTPUT_DIR / "runs"
FORMAL_EVIDENCE_DIR = FORMAL_OUTPUT_DIR / "evidence"

#: The four frozen attempt ids (immutable; existence of any is a hard refusal).
ATTEMPT_IDS = (
    "s1_units__A",
    "s1_units__B",
    "s2_pipeline__A",
    "s2_pipeline__B",
)

#: The controlled directory permissions (never world/group writable).
DIR_MODE = 0o700

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

#: Overlay sha256 (frozen; read-only, byte-identical to cohort2's audited file).
FROZEN_OVERLAY_SHA256 = (
    "df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ path guard
def _assert_controlled(path: Path, *, role: str, parent: Path) -> None:
    """Refuse any path that is not exactly the frozen, controlled COHORT3 path.

    Guards against: unknown paths, symlinked output roots (which could escape the
    controlled root), and paths whose *expected* parent is not a real, non-symlink
    directory.  ``parent`` is the single sanctioned parent for ``path`` (e.g. the
    worktrees dir for the output root, the output root for ``runs``/``evidence``);
    this never widens the root and never follows a symlink to create a target.
    """

    # Exact-match the controlled set.  ``resolve(strict=False)`` catches a
    # symlinked path or parent (e.g. ``.../lg032-cohort3-formal`` being a link).
    if path.parent != parent:
        raise SystemExit(
            f"refusing {role}: {path} is not under the controlled parent {parent}"
        )
    resolved = path.resolve(strict=False)
    if resolved != path:
        raise SystemExit(
            f"refusing {role}: path {path} resolves to {resolved}; "
            "controlled COHORT3 paths must not traverse a symlink"
        )
    if not parent.is_dir():
        raise SystemExit(
            f"refusing {role}: parent {parent} is not an existing directory"
        )
    if parent.is_symlink():
        raise SystemExit(
            f"refusing {role}: parent {parent} is a symlink (outside controlled root)"
        )


def _assert_no_attempt_artifacts(current_attempt_id: str | None = None) -> None:
    """Refuse a prepare / attempt if the *current* attempt id already exists.

    Scope is deliberately limited to the ONE attempt being prepared: a cohort is
    a *sequential* chain (``s1_units__A`` -> ``s1_units__B`` -> ...), so earlier
    attempts in the SAME controlled root must be left intact and must NOT block
    the next one.  Pass ``current_attempt_id=None`` (e.g. ``--prepare-only``) to
    check nothing -- this only *creates / re-checks* the two root dirs and never
    touches any historical attempt file.

    For the current id, any pre-existing attempt dir / ``result.json`` /
    evidence file is a hard refusal, so a prepare can never cover (mask) the
    attempt's own output.
    """

    if current_attempt_id is None:
        return
    if current_attempt_id not in ATTEMPT_IDS:
        raise SystemExit(
            f"refusing to prepare: unknown attempt id {current_attempt_id!r} "
            f"(expected one of {list(ATTEMPT_IDS)})"
        )

    attempt_dir = FORMAL_RUNS_DIR / current_attempt_id
    if attempt_dir.exists():
        raise SystemExit(
            f"refusing to prepare: attempt dir already exists "
            f"{attempt_dir} (attempt outputs are immutable)"
        )
    result_json = attempt_dir / "result.json"
    if result_json.exists():
        raise SystemExit(
            f"refusing to prepare: attempt result already exists {result_json}"
        )
    evidence_json = FORMAL_EVIDENCE_DIR / f"{current_attempt_id}.json"
    if evidence_json.exists():
        raise SystemExit(
            f"refusing to prepare: attempt evidence already exists {evidence_json}"
        )


def prepare_output_roots(current_attempt_id: str | None = None) -> dict[str, object]:
    """Controlled minimal assembly: pre-create the two COHORT3 output dirs.

    This is the ONE new step this repair package adds.  It is deliberately tiny
    and defensive:

    * creates ``FORMAL_RUNS_DIR`` and ``FORMAL_EVIDENCE_DIR`` with mode ``700``,
      ``parents=True`` (so the ``lg032-cohort3-formal`` root is assembled), and
      ``exist_ok=True`` (idempotent re-check is allowed) -- **but never touches
      any existing attempt dir / result / evidence file**;
    * refuses unknown/symlinked/outside paths (see :func:`_assert_controlled`);
    * refuses to proceed only if the **current** attempt id's dir / result /
      evidence already exists (see :func:`_assert_no_attempt_artifacts`);
      earlier attempts in the same sequential chain are preserved untouched and
      do not block the next attempt.  ``--prepare-only`` passes ``None`` and so
      refuses nothing, keeping the preflight idempotent and history-free.
    * does NOT create the phase data root, does NOT build a runtime, Task,
      proxy or SDK, and sends NO generation.

    The SAME function is called by ``--prepare-only`` and by a real formal
    attempt, so the preflight exercises the exact formal code path.

    Returns a JSON-serialisable record of the controlled side effect.
    """

    assert FORMAL_OUTPUT_DIR == FORMAL_RUNS_DIR.parent == FORMAL_EVIDENCE_DIR.parent

    # Output root is created under the controlled worktrees dir; runs/evidence
    # are created under the (then-existing) output root.  Guard the output root
    # BEFORE creating it, then create it, then guard its two children.
    _assert_controlled(FORMAL_OUTPUT_DIR, role="output root", parent=WORKTREES_DIR)
    _assert_no_attempt_artifacts(current_attempt_id)

    created: list[str] = []
    # Assemble the output root first (never symlink-following); ``exist_ok=True``
    # makes a re-check idempotent but the guards above + _assert_no_attempt_artifacts
    # refuse to mask any attempt.
    if not FORMAL_OUTPUT_DIR.exists():
        FORMAL_OUTPUT_DIR.mkdir(parents=True, mode=DIR_MODE, exist_ok=True)
        created.append(str(FORMAL_OUTPUT_DIR))

    _assert_controlled(FORMAL_RUNS_DIR, role="runs dir", parent=FORMAL_OUTPUT_DIR)
    _assert_controlled(FORMAL_EVIDENCE_DIR, role="evidence dir", parent=FORMAL_OUTPUT_DIR)

    for path in (FORMAL_RUNS_DIR, FORMAL_EVIDENCE_DIR):
        if not path.exists():
            path.mkdir(mode=DIR_MODE, exist_ok=True)
            created.append(str(path))
        # Re-assert mode without altering content; never recurse into files.
        try:
            os.chmod(path, DIR_MODE)
        except OSError:
            pass

    # Post-conditions: dirs exist, are real dirs (not symlinks), are empty of
    # our frozen attempt ids, and carry the controlled mode.
    for path in (FORMAL_OUTPUT_DIR, FORMAL_RUNS_DIR, FORMAL_EVIDENCE_DIR):
        if not path.is_dir() or path.is_symlink():
            raise SystemExit(f"prepare post-check failed: {path} is not a real dir")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != DIR_MODE:
            raise SystemExit(
                f"prepare post-check failed: {path} mode {oct(mode)} != {oct(DIR_MODE)}"
            )
    _assert_no_attempt_artifacts(current_attempt_id)

    return {
        "status": "prepared",
        "output_root": str(FORMAL_OUTPUT_DIR),
        "runs_dir": str(FORMAL_RUNS_DIR),
        "runs_dir_exists": FORMAL_RUNS_DIR.is_dir(),
        "evidence_dir": str(FORMAL_EVIDENCE_DIR),
        "evidence_dir_exists": FORMAL_EVIDENCE_DIR.is_dir(),
        "dir_mode": oct(DIR_MODE),
        "created_now": created,
        "phase_data_dir": str(FORMAL_PHASE_DATA_DIR),
        "phase_data_dir_exists": FORMAL_PHASE_DATA_DIR.exists(),
        "current_attempt_id": current_attempt_id,
        "current_attempt_absent": True,
    }


def _load_overlay_config() -> "object":
    """Load the audited cohort overlay and install it (path constants only).

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

    Deliberately BEFORE any runtime / proxy / Task / model call / `output-root`
    creation.  Never prints credential / env / secret values; in particular it
    does NOT call :func:`prepare_output_roots`.
    """

    assert C.PHASE_DATA_DIR == FORMAL_PHASE_DATA_DIR, (
        f"overlay root {C.PHASE_DATA_DIR} != frozen {FORMAL_PHASE_DATA_DIR}"
    )
    assert C.RUNS_DIR == FORMAL_RUNS_DIR
    assert C.EVIDENCE_DIR == FORMAL_EVIDENCE_DIR

    import run_attempt as R  # noqa: PLC0415

    print("== LG-032 COHORT3 formal entry — freeze identity (read-only) ==")
    print(f"entry            : {ENTRY}")
    print(f"entry_sha256     : {_sha256(ENTRY)}")
    print(f"overlay          : {MODE_DIR / 'mode_config.py'}")
    ov = _sha256(MODE_DIR / "mode_config.py")
    print(f"overlay_sha256   : {ov} [{'OK' if ov == FROZEN_OVERLAY_SHA256 else 'MISMATCH'}]")
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
    print(f"runsDir_exists   : {FORMAL_RUNS_DIR.exists()}")
    print(f"evidenceDir_exists: {FORMAL_EVIDENCE_DIR.exists()}")
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


def _prepare_only() -> int:
    """``--prepare-only``: call the SAME prepare function, record the side effect.

    This runs the exact :func:`prepare_output_roots` the formal path uses, then
    persists a *synthetic* preparation record to a **fresh NONCE scratch dir**
    (never into the formal attempt id paths, never into the phase root).  The
    record is explicitly marked ``not_formal`` / ``not_product_result`` -- no
    fake attempt result is ever written.
    """

    t0 = time.time()
    # --prepare-only creates / re-checks the two root dirs only: it passes
    # current_attempt_id=None so it is idempotent and never inspects, refuses or
    # touches any historical attempt file in either root.
    record = prepare_output_roots(current_attempt_id=None)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    nonce = secrets.token_hex(6)
    scratch = Path(
        f"/home/yhvh/code/lightgravity-bot-worktrees/"
        f"lg032-cohort3-prepare-scratch-{stamp}-{nonce}"
    )
    scratch.mkdir(parents=True, mode=DIR_MODE, exist_ok=False)

    payload = {
        "marker": "not_formal / not_product_result — synthetic directory-preparation record",
        "kind": "cohort3-prepare-only",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - t0, 3),
        "identity": {
            "worktree": str(WORKTREE),
            "entry": str(ENTRY),
            "entry_sha256": _sha256(ENTRY),
            "overlay_sha256": _sha256(MODE_DIR / "mode_config.py"),
        },
        "prepare": record,
        "real_generation": 0,
    }
    out = scratch / "prepare-record.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("== LG-032 COHORT3 --prepare-only (controlled directory assembly) ==")
    print(f"output_root      : {record['output_root']}")
    print(f"runs_dir         : {record['runs_dir']} (exists={record['runs_dir_exists']})")
    print(f"evidence_dir     : {record['evidence_dir']} (exists={record['evidence_dir_exists']})")
    print(f"dir_mode         : {record['dir_mode']}")
    print(f"created_now      : {record['created_now']}")
    print(f"phase_data_root  : {record['phase_data_dir']} (exists={record['phase_data_dir_exists']})")
    print(f"current_attempt_id : {record['current_attempt_id']}")
    print(f"current_attempt_absent: {record['current_attempt_absent']}")
    print("runtime/task/sdk : NOT built (no proxy, no generation, no phase root)")
    print(f"prepare_record   : {out} (synthetic; not formal)")
    print("== end --prepare-only ==")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LG-032 COHORT3 formal entry (mode-fixed overlay + frozen driver, "
                    "with controlled output-root assembly)"
    )
    ap.add_argument("--sample", choices=["s1_units", "s2_pipeline"])
    ap.add_argument("--arm", choices=["A", "B"])
    ap.add_argument(
        "--freeze-identity",
        action="store_true",
        help="read-only: print non-sensitive frozen config identity and exit "
             "(creates no root/runtime/Task/model call)",
    )
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="controlled: pre-create the two COHORT3 output dirs via the SAME "
             "prepare function a real attempt uses; no runtime/Task/SDK/generation",
    )
    args = ap.parse_args()

    C = _load_overlay_config()

    if args.freeze_identity:
        return _print_identity(C)

    if args.prepare_only:
        return _prepare_only()

    if not args.sample or not args.arm:
        ap.error("--sample and --arm are required for a formal attempt")

    # Controlled minimal assembly: the SAME function as --prepare-only, so the
    # driver's evidence write always has an existing parent directory.  The
    # current attempt id is assembled from the CLI choices (which match the
    # frozen ATTEMPT_IDS) so the guard refuses only THIS attempt's own output and
    # leaves earlier attempts in the sequential chain untouched.
    current_attempt_id = f"{args.sample}__{args.arm}"
    prepare_output_roots(current_attempt_id=current_attempt_id)

    sys.path.insert(0, str(HARNESS_DIR))
    import run_attempt as R  # noqa: PLC0415

    # Same audited driver function; real provider; one attempt id, once.
    return R.run_attempt(args.sample, args.arm, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
