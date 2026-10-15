"""Persistent global generation-budget ledger (LG-022 R2).

LG-022 R1 added :class:`~lightgravity.adapter.proxy.GenerationCounter`, a
process-global hard cap on upstream chat-completion requests.  The R1
independent re-verification found it was **in-memory only**: a fresh process
started from ``count=0``, so the cap reset on every service restart
(``counting-proof.json`` C4 ``persisted_across_restart=false``).

This module is the minimal durable bookkeeping the meter needs:

* a **file source of truth** under the controlled data root: an append-only
  JSONL history plus a small atomic counter file that is *rebuildable* from the
  history (never a second authoritative JSON/DB);
* a **reserve-before-forward** operation that locks and atomically persists the
  incremented count *before* the request is forwarded, so two processes / two
  sessions / a reviewer and a worker all contend on the same fact;
* **corruption is never treated as zero**: an unreadable/corrupt ledger refuses
  the reservation (the caller reports a bounded failure) instead of silently
  resetting the budget.

The ledger stores **only counters and minimal metadata** (a monotonic sequence,
timestamp and an opaque reserve id).  Inputs, prompts, headers, credentials and
grants are never written.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightgravity.store.locking import LockConflict, LockManager

#: Reserved-but-unconfirmed vs confirmed-forward labels (never claimed as
#: remote exactly-once).
RESERVE_UNCONFIRMED = "reserved"
FORWARD_CONFIRMED = "forwarded"

_LEDGER_SUBDIR = ("generation",)
_HISTORY_NAME = "generation.jsonl"
_COUNT_NAME = "generation.count.json"
_LOCK_KEY = "generation-budget"


class GenerationLedgerCorrupt(RuntimeError):
    """Raised when the persisted ledger cannot be trusted (never reset to 0)."""


@dataclass(frozen=True, slots=True)
class LedgerReservation:
    """One atomic reservation; ``reserve_id`` is opaque and non-secret."""

    granted: bool
    count: int
    limit: int | None
    remaining: int | None
    reserve_id: str | None
    corrupt: bool = False
    reason: str = ""


class PersistentGenerationLedger:
    """Cross-process, restart-persistent generation budget.

    The JSONL append is the history of record; the counter file is an atomic
    snapshot that is always reconciled against the history on read, so a torn
    write or stale snapshot cannot under-count.  A corrupt history is a hard
    error, never ``0``.
    """

    def __init__(self, root: Path | str, *, limit: int | None = None) -> None:
        base = Path(root).joinpath(*_LEDGER_SUBDIR)
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._history = base / _HISTORY_NAME
        self._count_file = base / _COUNT_NAME
        self._lock = LockManager(base, default_timeout=10.0)
        self._limit = limit
        self._thread_lock = threading.Lock()
        self._seq = 0

    # ------------------------------------------------------------------ read
    @property
    def limit(self) -> int | None:
        return self._limit

    def _read_history_count(self) -> int:
        """Count confirmed/reserved entries in the JSONL history.

        A missing history is an empty (valid) ledger; an unparsable line is
        corruption and raises rather than being skipped.
        """

        if not self._history.exists():
            return 0
        count = 0
        try:
            raw = self._history.read_text(encoding="utf-8")
        except OSError as exc:
            raise GenerationLedgerCorrupt(f"history unreadable: {exc}") from exc
        for line_no, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError as exc:
                raise GenerationLedgerCorrupt(
                    f"history line {line_no} is not valid JSON"
                ) from exc
            if not isinstance(entry, dict):
                raise GenerationLedgerCorrupt(f"history line {line_no} is not an object")
            if entry.get("kind") in {RESERVE_UNCONFIRMED, FORWARD_CONFIRMED}:
                count += 1
        return count

    def _read_snapshot_count(self) -> int | None:
        if not self._count_file.exists():
            return None
        try:
            data = json.loads(self._count_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GenerationLedgerCorrupt(f"count snapshot unreadable: {exc}") from exc
        value = data.get("count") if isinstance(data, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise GenerationLedgerCorrupt("count snapshot is not a non-negative int")
        return value

    def count(self) -> int:
        """The authoritative count: max(history, snapshot), corruption = error."""

        history = self._read_history_count()
        snapshot = self._read_snapshot_count()
        if snapshot is None:
            return history
        return max(history, snapshot)

    def snapshot(self) -> dict[str, Any]:
        try:
            current = self.count()
        except GenerationLedgerCorrupt as exc:
            return {
                "count": None,
                "limit": self._limit,
                "remaining": None,
                "corrupt": True,
                "reason": str(exc),
            }
        return {
            "count": current,
            "limit": self._limit,
            "remaining": (
                None if self._limit is None else max(0, self._limit - current)
            ),
            "corrupt": False,
        }

    # ----------------------------------------------------------- reserve
    def reserve(self) -> LedgerReservation:
        """Atomically reserve one slot and persist it *before* forwarding."""

        with self._thread_lock:
            try:
                with self._lock.acquire(_LOCK_KEY):
                    current = self.count()
                    if self._limit is not None and current >= self._limit:
                        return LedgerReservation(
                            granted=False,
                            count=current,
                            limit=self._limit,
                            remaining=0,
                            reserve_id=None,
                            reason="limit reached",
                        )
                    self._seq += 1
                    reserve_id = f"{os.getpid()}-{int(time.time() * 1000)}-{self._seq}"
                    new_count = current + 1
                    self._append_history(
                        {
                            "kind": RESERVE_UNCONFIRMED,
                            "count": new_count,
                            "reserve_id": reserve_id,
                            "pid": os.getpid(),
                            "ts": time.time(),
                        }
                    )
                    self._write_snapshot(new_count)
                    return LedgerReservation(
                        granted=True,
                        count=new_count,
                        limit=self._limit,
                        remaining=(
                            None
                            if self._limit is None
                            else max(0, self._limit - new_count)
                        ),
                        reserve_id=reserve_id,
                    )
            except LockConflict as exc:
                # Could not obtain the cross-process lock: refuse rather than
                # risk an unsafe double-spend.
                return LedgerReservation(
                    granted=False,
                    count=-1,
                    limit=self._limit,
                    remaining=None,
                    reserve_id=None,
                    reason=f"ledger lock unavailable: {exc}",
                )
            except GenerationLedgerCorrupt as exc:
                return LedgerReservation(
                    granted=False,
                    count=-1,
                    limit=self._limit,
                    remaining=None,
                    reserve_id=None,
                    corrupt=True,
                    reason=str(exc),
                )

    def confirm(self, reserve_id: str) -> None:
        """Record a confirmed forward (reservation -> forwarded).  Best effort."""

        with self._thread_lock:
            try:
                with self._lock.acquire(_LOCK_KEY):
                    self._append_history(
                        {
                            "kind": FORWARD_CONFIRMED,
                            "reserve_id": reserve_id,
                            "pid": os.getpid(),
                            "ts": time.time(),
                        }
                    )
            except (LockConflict, GenerationLedgerCorrupt, OSError):
                # A failed confirmation never rewinds the reservation; the
                # reserved entry already counted the request.
                return

    # ------------------------------------------------------------- internals
    def _append_history(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n"
        with self._history.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _write_snapshot(self, count: int) -> None:
        payload = json.dumps({"count": count}, separators=(",", ":"))
        tmp = self._count_file.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self._count_file)


def ledger_root_from_env() -> Path | None:
    """Resolve the controlled data root for the persistent ledger.

    Order: an explicit ``LIGHTGRAVITY_GENERATION_LEDGER_DIR`` (tests/ops), then
    the product data root ``LIGHTGRAVITY_DATA_DIR``.  Missing means "no
    persistence" (the in-memory counter remains), never a silent reset.
    """

    explicit = os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR")
    if explicit and explicit.strip():
        return Path(explicit)
    data_dir = os.environ.get("LIGHTGRAVITY_DATA_DIR")
    if data_dir and data_dir.strip():
        return Path(data_dir)
    return None


__all__ = [
    "FORWARD_CONFIRMED",
    "GenerationLedgerCorrupt",
    "LedgerReservation",
    "PersistentGenerationLedger",
    "RESERVE_UNCONFIRMED",
    "ledger_root_from_env",
]
