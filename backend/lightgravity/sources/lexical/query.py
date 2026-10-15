"""Query parsing, authorization filtering and回源 re-verification (LG-036).

The unified search semantics (docs/08 §6.6, docs/contracts/LG-033-preparation
§5.3) are: **authorized candidates → re-verify against the file source of truth
(existence / hash / version / permission) → real location**.  This module owns
the middle two steps:

1. :func:`parse_query` turns a user query into an FTS ``MATCH`` expression made
   only from our own tokenizer, so user text cannot inject FTS operators.  It
   supports exact phrases (``"..."``), bare numbers/identifiers, dates and
   amounts through the same tokenizer, plus explicit ``kind:`` labels.
2. :func:`authorize_and_verify` re-reads the ``SOURCE.md`` frontmatter for each
   candidate and rejects hits whose scope the caller is not authorized for, whose
   source was revoked/archived, whose source version or content hash changed
   (``source_stale``), or whose original/formal file vanished.  A cache entry is
   never returned as authority on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .index import MAX_LIMIT, SNIPPET_CHARS, tokenize

#: Query kinds reported back to the caller (informational, never authoritative).
QUERY_KINDS = ("phrase", "term", "number", "date", "amount", "identifier")

_PHRASE_RE = re.compile(r'"([^"]*)"')
_DATE_RE = re.compile(r"\b\d{4}[-/.]\d{1,2}([-/.]\d{1,2})?\b")
_AMOUNT_RE = re.compile(r"(?:[¥$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:元|美元|万元|元整))")
_IDENT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9._-]*\d[A-Za-z0-9._-]*\b|\b\d+[A-Za-z][A-Za-z0-9._-]*\b")


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """A parsed query: raw text plus the FTS expression derived from it."""

    raw: str
    match_expr: str
    phrases: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    tokens: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.match_expr.strip()


def parse_query(raw: str) -> ParsedQuery:
    """Parse a user query into a safe FTS ``MATCH`` expression.

    Exact phrases (quoted) become FTS phrase queries over adjacent tokens; all
    other runs are AND-ed so that every requested token must be present.  Because
    tokens come from :func:`tokenize`, dates/amounts/identifiers stay intact and
    CJK phrases are matchable as token sequences.
    """

    text = (raw or "").strip()
    if not text:
        return ParsedQuery(raw=raw, match_expr="")

    phrases = tuple(p.strip() for p in _PHRASE_RE.findall(text) if p.strip())
    remainder = _PHRASE_RE.sub(" ", text)

    kinds: list[str] = []
    phrase_terms: list[str] = []
    for phrase in phrases:
        toks = tokenize(phrase)
        if not toks:
            continue
        if len(toks) == 1:
            phrase_terms.append(_fts_term(toks[0]))
        else:
            # Adjacent tokens must match in order: an FTS5 phrase query.  Tokens
            # are already reduced to safe characters by ``tokenize``; quote the
            # ones that could contain FTS syntax (dots/dashes) individually.
            phrase_terms.append(_fts_phrase(toks))
        kinds.append("phrase")

    # Classify remainder spans for honest reporting (does not change matching).
    for pattern, kind in ((_DATE_RE, "date"), (_AMOUNT_RE, "amount"), (_IDENT_RE, "identifier")):
        if pattern.search(remainder):
            kinds.append(kind)

    bare_tokens = tokenize(remainder)
    all_tokens = list(bare_tokens)
    for phrase in phrases:
        all_tokens.extend(tokenize(phrase))
    term_exprs = [_fts_term(t) for t in bare_tokens]
    if any(re.fullmatch(r"\d[\d,]*", t) for t in bare_tokens):
        kinds.append("number")

    parts = list(phrase_terms) + term_exprs
    match_expr = " AND ".join(parts)
    ordered_kinds = tuple(dict.fromkeys(kinds)) or (("term",) if match_expr else ())
    return ParsedQuery(
        raw=raw,
        match_expr=match_expr,
        phrases=phrases,
        kinds=ordered_kinds,
        tokens=tuple(all_tokens),
    )


def _fts_quote(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _fts_term(token: str) -> str:
    """Quote a token as an FTS term so operators cannot be injected."""

    return _fts_quote(token)


def _fts_phrase(tokens: list[str]) -> str:
    """Build an ordered FTS5 phrase query from tokens.

    Simple word tokens stay bare (so ``unicode61`` re-tokenizes them normally);
    tokens containing FTS syntax (``.``/``-``/``/`` etc.) are quoted so they are
    matched as a single term.  The whole construct is itself wrapped in a
    phrase so order is preserved.
    """

    # ``tokenize`` only emits alphanumerics/underscore/CJK, so every token is
    # safe as a bare phrase term; order is preserved by the enclosing quotes.
    return '"' + " ".join(tokens) + '"'


@dataclass(frozen=True, slots=True)
class ScopeFilter:
    """Authorization filter derived from the *caller's* request scope.

    ``task_ref``/``project_ref``/``inbox_ref`` restrict the search to that
    scope; ``include_global`` additionally admits unscoped material.  A caller
    can never widen permission through the query — the filter only narrows.
    """

    task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None
    include_global: bool = False

    def allows(self, scope: dict[str, Any]) -> bool:
        scope_task = scope.get("task_ref")
        scope_project = scope.get("project_ref")
        scope_inbox = scope.get("inbox_ref")
        is_global = scope_task is None and scope_project is None and scope_inbox is None
        if self.task_ref is not None and scope_task == self.task_ref:
            return True
        if self.project_ref is not None and scope_project == self.project_ref:
            return True
        if self.inbox_ref is not None and scope_inbox == self.inbox_ref:
            return True
        return bool(self.include_global and is_global)


@dataclass(slots=True)
class VerifiedHit:
    """One candidate after回源 re-verification against the file SoT."""

    source_id: str
    score: float
    basis: str
    source_version: int
    content_hash: str | None
    scope: dict[str, Any]
    title: str
    locators: list[dict[str, Any]]
    snippet: str
    verified: bool = True
    stale: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "basis": self.basis,
            "scope": dict(self.scope),
            "title": self.title,
            "locators": list(self.locators),
            "snippet": self.snippet,
            "verified": self.verified,
            "stale": self.stale,
            "reason": self.reason,
        }


@dataclass(slots=True)
class SearchOutcome:
    """Result of one search after authorization + re-verification."""

    hits: list[VerifiedHit] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": [h.to_dict() for h in self.hits],
            "stale": list(self.stale),
            "skipped": list(self.skipped),
        }


def authorize_and_verify(
    candidates: Iterable[dict[str, Any]],
    *,
    scope_filter: ScopeFilter,
    read_source: Callable[[str], Any],
    verify_source: Callable[[Any], tuple[bool, str | None]],
    query_tokens: Iterable[str] = (),
) -> SearchOutcome:
    """Filter candidates by scope and re-verify each against the file SoT.

    ``read_source`` must return the current ``SourceRecord`` (raising if the
    entity no longer exists); ``verify_source`` must return ``(ok, reason)`` for
    the *current* record plus its version/hash (e.g. "revoked"/"missing
    original"/"formal missing").  Any candidate whose source cannot be read or
    re-verified is dropped — no dangling hit is ever returned.
    """

    outcome = SearchOutcome()
    tokens = [t for t in query_tokens if t]
    for candidate in candidates:
        source_id = str(candidate.get("source_id") or "")
        if not source_id:
            continue
        try:
            record = read_source(source_id)
        except Exception:
            outcome.skipped.append({"source_id": source_id, "reason": "source_missing"})
            continue

        scope = _scope_of(record)
        if not scope_filter.allows(scope):
            outcome.skipped.append({"source_id": source_id, "reason": "out_of_scope"})
            continue

        current_version = _int_of(getattr(record, "source_version", None), default=1)
        cached_version = _int_of(candidate.get("source_version"), default=-1)
        current_hash = getattr(record, "content_digest", None)

        if current_version != cached_version:
            outcome.stale.append(
                {
                    "source_id": source_id,
                    "cached_version": cached_version,
                    "current_version": current_version,
                    "reason": "source_stale",
                }
            )
            continue

        ok, reason = verify_source(record)
        if not ok:
            outcome.stale.append(
                {
                    "source_id": source_id,
                    "cached_version": cached_version,
                    "current_version": current_version,
                    "reason": reason or "source_stale",
                }
            )
            continue

        body = str(candidate.get("body") or "")
        title = str(candidate.get("title") or getattr(record, "title", "") or "")
        outcome.hits.append(
            VerifiedHit(
                source_id=source_id,
                score=0.0,
                basis=str(candidate.get("basis") or "machine"),
                source_version=current_version,
                content_hash=current_hash,
                scope=scope,
                title=title,
                locators=list(candidate.get("locators") or []),
                snippet=build_snippet(title, body, tokens),
            )
        )
    return outcome


def build_snippet(title: str, body: str, tokens: Iterable[str]) -> str:
    """Return a bounded excerpt centred on the first query token, if present."""

    text = body.strip()
    if not text:
        return ""
    lowered = text.lower()
    anchor = len(text)
    for token in tokens:
        if not token:
            continue
        position = lowered.find(token.lower())
        if position != -1:
            anchor = position
            break
    span = SNIPPET_CHARS
    start = max(anchor - span // 3, 0)
    end = min(start + span, len(text))
    excerpt = text[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return MAX_LIMIT
    return max(min(int(limit), MAX_LIMIT), 1)


def _scope_of(record: Any) -> dict[str, Any]:
    scope = getattr(record, "scope", None)
    if scope is None:
        return {"task_ref": None, "project_ref": None, "inbox_ref": None}
    if hasattr(scope, "to_dict"):
        value = scope.to_dict()
        return value if isinstance(value, dict) else {}
    return dict(scope) if isinstance(scope, dict) else {}


def _int_of(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


__all__ = [
    "QUERY_KINDS",
    "ParsedQuery",
    "ScopeFilter",
    "SearchOutcome",
    "VerifiedHit",
    "authorize_and_verify",
    "build_snippet",
    "clamp_limit",
    "parse_query",
]
