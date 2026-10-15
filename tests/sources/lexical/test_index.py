"""Unit tests for the rebuildable lexical cache (LG-036, docs/09 §8.1).

These are the properties the task acceptance conditions depend on at the cache
layer: exact短语/编号/日期/金额 matching, stable content hash, delete-and-rebuild
reproducibility, and honest corruption reporting.
"""

from __future__ import annotations

import sqlite3
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
    index = LexicalIndex(tmp_path)
    index.upsert(_doc())
    # Corrupt the underlying file.
    index.db_path.write_bytes(b"not a sqlite database")
    assert index.readable() is False
    with pytest.raises(IndexCorruptError):
        index.search('"ht"')


def test_search_expression_cannot_inject_fts_operators(tmp_path: Path) -> None:
    from lightgravity.sources.lexical.query import parse_query

    index = LexicalIndex(tmp_path)
    index.upsert(_doc())
    # A malicious query is tokenized, so 'OR'/'NEAR'/'*' never reach FTS as syntax.
    parsed = parse_query('") OR (1=1')
    assert "OR" not in parsed.match_expr.replace('"', "")
    assert index.search(parsed.match_expr) == []
