#!/usr/bin/env python3
"""LG-047 R2 — durable, independent campaign ledger + pre-forward guard.

Purpose
-------
The LG-047 **R2** budget is at most **8 real product DeepSeek requests for the
entire R2 campaign** (all attempts / worker / reviewer / retries, retry 0).
This module is the *independent second* gate in front of the real upstream.

It creates **ONE** campaign directory in an absolute, controlled location and
writes a persistent manifest once.  Rules (from the Root PM R2 replan):

* the ledger is **append-only** and is **NEVER reset** across app restarts,
  harness restarts or attempts;
* a reserve is persisted **atomically before** any upstream socket is opened;
* a missing ledger while a manifest already exists ⇒ **deny** (never treat as 0);
* a corrupt ledger ⇒ **deny** (never treat as 0);
* cap exhausted ⇒ deny; no auto-extend.

The guard is intended to be pointed at as the *real upstream* via
``LG_QA_REAL_UPSTREAM`` for a loopback HTTP guard (``http_guard.py``) AND used
directly as an in-process reservation API by the harness.  A denied request is
HTTP 429 and never connects.

Credentials are never read, logged or stored here.  Only redacted metadata
(count, kind, status, latency, bytes, model) is written.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

#: Absolute, controlled, worktree-local campaign root.  ONE campaign only.
CAMPAIGN_ROOT = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016/"
    "probes/prototype-selected-material-20261016/I-R2-QA/campaign"
)
MANIFEST = CAMPAIGN_ROOT / "manifest.json"
HISTORY = CAMPAIGN_ROOT / "history.jsonl"
COUNT_FILE = CAMPAIGN_ROOT / "count.json"

#: The R2 cap: at most 8 NEW real product requests.  Distinct from R1.
R2_CAP = 8


class LedgerCorrupt(RuntimeError):
    """The persisted ledger cannot be trusted (never reset to 0)."""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    # fsync the directory so the rename is durable across a crash.
    try:
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def init_campaign(cap: int = R2_CAP, *, campaign_id: str = "LG-047-R2") -> dict:
    """Initialise the campaign manifest exactly ONCE.

    If a manifest already exists it is returned unchanged (never re-created,
    never reset).  If history/count exist without a manifest that is an
    inconsistent state and is refused.
    """

    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    if HISTORY.exists() or COUNT_FILE.exists():
        raise LedgerCorrupt(
            "ledger files exist but manifest is missing — refuse to re-init"
        )
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "campaign_id": campaign_id,
        "cap": cap,
        "created_ts": time.time(),
        "purpose": "LG-047 R2 independent product-request budget (all attempts/worker/reviewer)",
        "notes": "One-time init. Never reset. Missing/corrupt ledger with existing manifest denies.",
    }
    _atomic_write(MANIFEST, json.dumps(manifest, indent=2) + "\n")
    return manifest


def _read_history_count() -> int:
    if not HISTORY.exists():
        return 0
    try:
        raw = HISTORY.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise LedgerCorrupt(f"history unreadable: {exc}") from exc
    count = 0
    for i, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise LedgerCorrupt(f"history line {i} invalid json") from exc
        if not isinstance(obj, dict):
            raise LedgerCorrupt(f"history line {i} not an object")
        if obj.get("kind") in ("reserve", "forwarded", "failed"):
            count += 1
    return count


def _read_snapshot() -> int | None:
    if not COUNT_FILE.exists():
        return None
    try:
        data = json.loads(COUNT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerCorrupt(f"count unreadable: {exc}") from exc
    value = data.get("count") if isinstance(data, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LedgerCorrupt("count snapshot is not a non-negative int")
    return value


def snapshot() -> dict:
    """Authoritative snapshot: max(history, snapshot); corruption = deny."""

    if not MANIFEST.exists():
        return {"count": None, "cap": None, "remaining": None, "corrupt": True,
                "reason": "no manifest — campaign not initialised"}
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"count": None, "cap": None, "remaining": None, "corrupt": True,
                "reason": f"manifest unreadable: {exc}"}
    cap = int(manifest.get("cap", R2_CAP))
    try:
        hist = _read_history_count()
        snap = _read_snapshot()
    except LedgerCorrupt as exc:
        return {"count": None, "cap": cap, "remaining": None, "corrupt": True,
                "reason": str(exc)}
    count = hist if snap is None else max(hist, snap)
    return {
        "count": count,
        "cap": cap,
        "remaining": max(0, cap - count),
        "corrupt": False,
        "history_lines": hist,
        "snapshot": snap,
    }


def reserve(kind: str = "product", note: str = "") -> tuple[bool, int, str]:
    """Reserve one product slot, persisting it BEFORE any forward.

    Returns ``(granted, count_after_or_current, reason)``.
    """

    if not MANIFEST.exists():
        return False, -1, "no manifest — refuse (campaign not initialised)"
    snap = snapshot()
    if snap["corrupt"]:
        return False, -1, f"corrupt ledger: {snap['reason']}"
    current = snap["count"]
    cap = snap["cap"]
    if current >= cap:
        return False, current, f"campaign cap {cap} reached (no auto-extend)"
    new_count = current + 1
    row = {
        "kind": "reserve",
        "count": new_count,
        "campaign": "LG-047-R2",
        "reserve_kind": kind,
        "note": note,
        "pid": os.getpid(),
        "ts": time.time(),
    }
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    _atomic_write(COUNT_FILE, json.dumps({"count": new_count}) + "\n")
    return True, new_count, "ok"


def record_outcome(count: int, *, status: int | None, model: str | None,
                   latency_s: float | None, note: str = "") -> None:
    """Append a redacted outcome row (never a secret, never a prompt body)."""

    row = {
        "kind": "outcome",
        "count": count,
        "status": status,
        "model": model,
        "latency_s": latency_s,
        "note": note,
        "ts": time.time(),
    }
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["init", "snapshot", "reserve", "selftest"])
    ap.add_argument("--cap", type=int, default=R2_CAP)
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    if args.command == "init":
        print(json.dumps(init_campaign(args.cap), indent=2))
    elif args.command == "snapshot":
        print(json.dumps(snapshot(), indent=2))
    elif args.command == "reserve":
        ok, count, reason = reserve(note=args.note)
        print(json.dumps({"granted": ok, "count": count, "reason": reason}))
    elif args.command == "selftest":
        # Offline self-test in a SEPARATE temp ledger: never touches product quota.
        import tempfile

        global CAMPAIGN_ROOT, MANIFEST, HISTORY, COUNT_FILE
        with tempfile.TemporaryDirectory(prefix="lg047-r2-guardtest-") as td:
            CAMPAIGN_ROOT = Path(td)
            MANIFEST = CAMPAIGN_ROOT / "manifest.json"
            HISTORY = CAMPAIGN_ROOT / "history.jsonl"
            COUNT_FILE = CAMPAIGN_ROOT / "count.json"
            checks = []
            checks.append(("deny_before_init", reserve()[0] is False))
            init_campaign(3)
            grants = [reserve()[0] for _ in range(4)]
            checks.append(("3_granted_then_denied", grants == [True, True, True, False]))
            checks.append(("count_is_3", snapshot()["count"] == 3))
            # corruption denial: break the count file
            COUNT_FILE.write_text("{not json", encoding="utf-8")
            checks.append(("corrupt_denies", reserve()[0] is False))
            COUNT_FILE.unlink()
            HISTORY.write_text("{bad json\n", encoding="utf-8")
            checks.append(("corrupt_history_denies", reserve()[0] is False))
            # missing ledger with manifest present denies
            COUNT_FILE.unlink(missing_ok=True)
            HISTORY.unlink()
            HISTORY.mkdir()
            checks.append(("missing_history_dir_denies", snapshot()["corrupt"] is True))
            print(json.dumps({"checks": checks,
                              "all_pass": all(c[1] for c in checks)}, indent=2))


if __name__ == "__main__":
    main()
