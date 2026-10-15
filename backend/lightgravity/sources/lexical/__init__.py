"""Rebuildable lexical index + source-of-truth re-verification (LG-036).

This package implements the LG-036 half of the LG-033 source-intake contract
(docs/08 §4.3 ``GET /search``, §5.1 ``source.indexed``/``source.invalidated``,
§6.6 ``index.lexical``/``lexical_hash``): a stdlib-sqlite **FTS5** cache built
from the file source of truth, with authorized-candidate → 回源核对 semantics.

Boundaries kept deliberately:

* Files (``SOURCE.md`` + original bytes + formal/machine content) remain the
  only source of truth; the SQLite file is a派生 cache with no独有的 permission
  or control state and can be deleted and rebuilt to the same hashes.
* No separate database service is started — ``sqlite3`` is the standard library
  and the cache is a local file (docs/09 §7).
* Only trusted bodies are indexed (human formal version preferred, trusted OCR
  machine derivative next).  A source with no trusted body is honestly
  ``not_indexed``; no synthetic/English sample is ever presented as Chinese OCR
  or image-retrieval quality.
"""

from .index import (
    CACHE_SCHEMA_VERSION,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    IndexBuildReport,
    IndexCorruptError,
    IndexedDocument,
    LexicalIndex,
    tokenize,
)
from .query import (
    ParsedQuery,
    ScopeFilter,
    SearchOutcome,
    VerifiedHit,
    authorize_and_verify,
    build_snippet,
    parse_query,
)
from .service import LexicalSearchService, SearchRequest, lexical_hash_for

__all__ = [
    "CACHE_SCHEMA_VERSION",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "IndexBuildReport",
    "IndexCorruptError",
    "IndexedDocument",
    "LexicalIndex",
    "LexicalSearchService",
    "ParsedQuery",
    "ScopeFilter",
    "SearchOutcome",
    "SearchRequest",
    "VerifiedHit",
    "authorize_and_verify",
    "build_snippet",
    "lexical_hash_for",
    "parse_query",
    "tokenize",
]
