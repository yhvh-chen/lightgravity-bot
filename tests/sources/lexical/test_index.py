"""Unit tests for the rebuildable lexical cache (LG-036, docs/09 §8.1).

These are the properties the task acceptance conditions depend on at the cache
layer: exact短语/编号/日期/金额 matching, stable content hash, delete-and-rebuild
reproducibility, and honest corruption reporting.
"""

from __future__ import annotations

import sqlite3
import gc
from pathlib import Path

import pytest

from lightgravity.sources.lexical.index import (
    IndexCorruptError,
    IndexedDocument,
    LexicalIndex,
    tokenize,
)


def _doc(source_id: str = "source_1", text: str | None = None, **kwargs) -> IndexedDocument:
    return IndexedDocument(
        source_id=source_id,
        source_version=kwargs.pop("source_version", 1),
        content_hash=kwargs.pop("content_hash", "a" * 64),
        basis=kwargs.pop("basis", "formal"),
        title=kwargs.pop("title", "合同 发票"),
        text=text
        if text is not None
        else "这是合同编号 HT-2024-001，金额 1,234.56 元，日期 2026-10-16。",
        **kwargs,
    )


def test_tokenize_roundtrips_through_fts5() -> None:
    """The tokens we store must survive FTS5 ``unicode61`` unchanged.

    We index a pre-tokenized, space-joined copy of the text; FTS5 re-tokenizes
    it with ``unicode61``.  The invariant that makes phrase/exact matching work
    is that FTS5's resulting terms equal our tokens exactly, so a query built
    from ``tokenize`` matches what was indexed.  (``unicode61`` groups CJK text
    into whole runs, so we split CJK ourselves **before** indexing.)
    """

    sample = "合同 HT-2024-001 金额 1,234.56 元 2026-10-16 a_b"
    expected = sorted(tokenize(sample))
    stored = " ".join(tokenize(sample))
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61')")
        conn.execute("CREATE VIRTUAL TABLE v USING fts5vocab(t, 'row')")
        conn.execute("INSERT INTO t(x) VALUES (?)", (stored,))
        terms = sorted(row[0] for row in conn.execute("SELECT term FROM v"))
    assert expected == terms


@pytest.mark.parametrize(
    "query",
    [
        '"合同编号"',  # exact CJK phrase
        '"HT-2024-001"',  # identifier
        '"2026-10-16"',  # date
        '"1,234.56"',  # amount
        '"合同编号 HT-2024-001"',  # cross-script phrase
    ],
)
def test_exact_queries_hit(tmp_path: Path, query: str) -> None:
    from lightgravity.sources.lexical.query import parse_query

    index = LexicalIndex(tmp_path)
    index.upsert(_doc())
    index.upsert(_doc("source_2", text="无关内容 999", basis="machine"))
    parsed = parse_query(query)
    hits = [row["source_id"] for row in index.search(parsed.match_expr)]
    assert hits == ["source_1"], query


def test_negative_control_returns_no_hit(tmp_path: Path) -> None:
    from lightgravity.sources.lexical.query import parse_query

    index = LexicalIndex(tmp_path)
    index.upsert(_doc())
    parsed = parse_query("完全不存在的词组")
    assert index.search(parsed.match_expr) == []


def test_lexical_hash_stable_across_rebuild(tmp_path: Path) -> None:
    index = LexicalIndex(tmp_path)
    first = index.upsert(_doc())
    entry = index.entry("source_1")
    assert entry is not None and entry["lexical_hash"] == first

    # Delete and rebuild from the same document -> identical hash.
    index.delete()
    assert not index.exists()
    second = index.upsert(_doc())
    assert second == first


def test_replace_all_rebuilds_and_reports(tmp_path: Path) -> None:
    index = LexicalIndex(tmp_path)
    index.upsert(_doc("stale_source"))
    report = index.replace_all([_doc("source_1"), _doc("source_2", text="其它 内容")])
    assert report.documents == 2
    assert index.entry("stale_source") is None
    assert index.entry("source_1") is not None


def test_corrupt_cache_is_reported_not_silently_empty(tmp_path: Path) -> None:
    # Prevent incidental collection before corruption, then force collection at
    # the exact old failure window. A leaked WAL connection used to restore the
    # overwritten database at this point instead of reporting corruption.
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        index = LexicalIndex(tmp_path)
        index.upsert(_doc())
        index.db_path.write_bytes(b"not a sqlite database")
        assert index.readable() is False
        gc.collect()
        assert index.db_path.read_bytes() == b"not a sqlite database"
        with pytest.raises(IndexCorruptError):
            index.search('"ht"')
    finally:
        if was_enabled:
            gc.enable()


def test_connections_close_after_transactions_and_roll_back_on_error(tmp_path: Path) -> None:
    index = LexicalIndex(tmp_path)
    with index._connect() as connection:
        connection.execute("CREATE TABLE lifecycle (value TEXT)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="abort transaction"):
        with index._connect() as failed_connection:
            failed_connection.execute("INSERT INTO lifecycle VALUES ('discard')")
            raise RuntimeError("abort transaction")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed_connection.execute("SELECT 1")
    with index._connect() as connection:
        assert connection.execute("SELECT count(*) FROM lifecycle").fetchone() == (0,)


def test_search_expression_cannot_inject_fts_operators(tmp_path: Path) -> None:
    from lightgravity.sources.lexical.query import parse_query

    index = LexicalIndex(tmp_path)
    index.upsert(_doc())
    # A malicious query is tokenized, so 'OR'/'NEAR'/'*' never reach FTS as syntax.
    parsed = parse_query('") OR (1=1')
    assert "OR" not in parsed.match_expr.replace('"', "")
    assert index.search(parsed.match_expr) == []


def test_first_connection_setup_is_serialized_across_cache_instances(tmp_path, monkeypatch) -> None:
    """A paused SQLite opener must not race a second WAL initializer."""
    import threading

    first = LexicalIndex(tmp_path / "cache")
    second = LexicalIndex(tmp_path / "cache")
    original_connect = sqlite3.connect
    first_opening = threading.Event()
    second_attempting = threading.Event()
    second_opening = threading.Event()
    release_first = threading.Event()
    counts_lock = threading.Lock()
    calls = 0
    errors: list[BaseException] = []

    def controlled_connect(*args, **kwargs):
        nonlocal calls
        with counts_lock:
            calls += 1
            position = calls
        if position == 1:
            first_opening.set()
            assert release_first.wait(5), "test did not release first SQLite opener"
        else:
            second_opening.set()
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", controlled_connect)
    second_connect = second._connect

    def mark_second_attempt():
        second_attempting.set()
        return second_connect()

    monkeypatch.setattr(second, "_connect", mark_second_attempt)

    def write(index, source_id):
        try:
            index.upsert(_doc(source_id))
        except BaseException as exc:
            errors.append(exc)

    writer1 = threading.Thread(target=write, args=(first, "first"))
    writer2 = threading.Thread(target=write, args=(second, "second"))
    writer1.start()
    try:
        assert first_opening.wait(5)
        writer2.start()
        assert second_attempting.wait(5)
        # Give the second attempted connection a chance to contend. The first
        # remains paused, so overlapping SQLite setup is deterministic if allowed.
        assert not second_opening.wait(0.2), "SQLite WAL setup overlapped"
    finally:
        release_first.set()
        writer1.join(5)
        if writer2.ident is not None:
            writer2.join(5)
    assert not writer1.is_alive() and not writer2.is_alive()
    assert not errors
    assert first.readable()
    assert {entry["source_id"] for entry in first.all_entries()} == {"first", "second"}
