"""LG-022 R2: the generation-budget ledger must be restart/cross-process durable.

The R1 re-verification found ``GenerationCounter`` was in-memory only, so the
hard cap reset on every restart.  These tests pin the persistent ledger:

* a fresh ledger object (new process/instance) reads the same count;
* two independent instances over one ledger never over-spend ``limit=1``;
* corruption is never treated as ``0`` (it denies the reservation and reports);
* the snapshot exposes ``persistent``/``corrupt`` and never leaks inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

from lightgravity.adapter.generation_ledger import (
    GenerationLedgerCorrupt,
    PersistentGenerationLedger,
)
from lightgravity.adapter.proxy import GenerationCounter


def test_reserve_is_persisted_across_new_instance(tmp_path: Path) -> None:
    first = PersistentGenerationLedger(tmp_path, limit=5)
    assert first.reserve().granted is True
    assert first.reserve().granted is True
    assert first.count() == 2

    # A second instance simulates a fresh process reading the same data root.
    second = PersistentGenerationLedger(tmp_path, limit=5)
    assert second.count() == 2
    assert second.reserve().granted is True
    assert second.count() == 3


def test_two_instances_share_limit_one(tmp_path: Path) -> None:
    a = PersistentGenerationLedger(tmp_path, limit=1)
    b = PersistentGenerationLedger(tmp_path, limit=1)
    assert a.reserve().granted is True
    # The second instance must read the persisted count and refuse.
    refused = b.reserve()
    assert refused.granted is False
    assert refused.remaining == 0
    assert b.count() == 1


def test_counter_delegates_to_persistent_ledger(tmp_path: Path) -> None:
    ledger = PersistentGenerationLedger(tmp_path, limit=2)
    counter = GenerationCounter(2, ledger=ledger)
    assert counter.reserve() is True
    assert counter.reserve() is True
    assert counter.reserve() is False
    snap = counter.snapshot()
    assert snap == {
        "count": 2,
        "limit": 2,
        "remaining": 0,
        "corrupt": False,
        "persistent": True,
    }

    # A brand new counter over the same root still sees the spent budget.
    fresh = GenerationCounter(2, ledger=PersistentGenerationLedger(tmp_path, limit=2))
    assert fresh.count == 2
    assert fresh.reserve() is False


def test_corrupt_ledger_is_never_zero(tmp_path: Path) -> None:
    ledger = PersistentGenerationLedger(tmp_path, limit=10)
    ledger.reserve()
    # Corrupt the history: an unparsable line must raise, not be skipped.
    history = tmp_path / "generation" / "generation.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    import pytest

    with pytest.raises(GenerationLedgerCorrupt):
        ledger.count()

    snap = ledger.snapshot()
    assert snap["corrupt"] is True
    assert snap["count"] is None
    # A corrupt ledger denies the reservation rather than spending it as 0.
    assert ledger.reserve().granted is False
    assert ledger.reserve().corrupt is True


def test_corrupt_snapshot_refused_by_counter(tmp_path: Path) -> None:
    ledger = PersistentGenerationLedger(tmp_path, limit=2)
    ledger.reserve()
    (tmp_path / "generation" / "generation.count.json").write_text(
        json.dumps({"count": "not-an-int"}), encoding="utf-8"
    )
    counter = GenerationCounter(2, ledger=ledger)
    assert counter.reserve() is False
    assert counter.snapshot()["corrupt"] is True


def test_ledger_writes_only_counts_no_inputs(tmp_path: Path) -> None:
    ledger = PersistentGenerationLedger(tmp_path, limit=3)
    ledger.reserve()
    history = (tmp_path / "generation" / "generation.jsonl").read_text(encoding="utf-8")
    assert "prompt" not in history
    assert "Authorization" not in history
    assert "credential" not in history
    for line in history.splitlines():
        entry = json.loads(line)
        assert set(entry).issubset({"kind", "count", "reserve_id", "pid", "ts"})


def test_two_processes_share_one_ledger(tmp_path: Path) -> None:
    """A genuinely separate process reads the same persisted count (C4)."""

    import subprocess
    import sys

    program = (
        "import json,sys\n"
        "from lightgravity.adapter.generation_ledger import PersistentGenerationLedger\n"
        "led = PersistentGenerationLedger(sys.argv[1], limit=1)\n"
        "r = led.reserve()\n"
        "print(json.dumps({'granted': r.granted, 'count': r.count}))\n"
    )
    # Process 1 consumes the single slot and exits.
    first = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(first.stdout.strip()) == {"granted": True, "count": 1}
    # Process 2 (a fresh interpreter) reads the persisted count and refuses.
    second = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(second.stdout.strip()) == {"granted": False, "count": 1}
