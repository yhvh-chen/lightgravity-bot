"""LG-022 R1: process-global generation-request counter tests (no network)."""

from __future__ import annotations

import threading

from lightgravity.adapter.proxy import GenerationCounter


def test_counter_counts_and_enforces_global_limit() -> None:
    counter = GenerationCounter(limit=3)
    assert [counter.reserve() for _ in range(4)] == [True, True, True, False]
    assert counter.count == 3
    # LG-022 R2: snapshot carries an additive ``persistent`` flag; an in-memory
    # counter is honestly non-persistent.
    assert counter.snapshot() == {
        "count": 3,
        "limit": 3,
        "remaining": 0,
        "persistent": False,
    }


def test_counter_none_limit_counts_without_capping() -> None:
    counter = GenerationCounter(limit=None)
    for _ in range(10):
        assert counter.reserve() is True
    assert counter.snapshot()["remaining"] is None
    assert counter.count == 10


def test_counter_thread_safe_under_concurrency() -> None:
    counter = GenerationCounter(limit=50)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(10):
            ok = counter.reserve()
            with lock:
                granted.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(1 for value in granted if value) == 50
    assert counter.count == 50


def test_global_counter_is_shared_by_default() -> None:
    from lightgravity.adapter.proxy import global_generation_counter

    assert global_generation_counter() is global_generation_counter()
