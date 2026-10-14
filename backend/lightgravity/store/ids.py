"""ULID generation and entity-id validation (docs/08 §3.1-§3.2).

Runtime entities use ``<kind>_<ULID>``; resources use a stable slug.  ULIDs are
26-char Crockford Base32, time-ordered, generated without third-party deps so
the store stays dependency-minimal.
"""

from __future__ import annotations

import os
import re
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_RUNTIME_PREFIXES = ("task", "run", "subtask", "member", "conv", "msg", "evt", "notif", "req")

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_RUNTIME_ID_RE = re.compile(
    r"^(?:" + "|".join(_RUNTIME_PREFIXES) + r")_[0-9A-HJKMNP-TV-Z]{26}$"
)


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """Return a new 26-char Crockford Base32 ULID."""

    ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    time_chars = []
    for _ in range(10):
        time_chars.append(_CROCKFORD[ts & 0x1F])
        ts >>= 5
    time_part = "".join(reversed(time_chars))

    value = int.from_bytes(os.urandom(10), "big")
    rand_chars = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return time_part + "".join(reversed(rand_chars))


def new_id(kind: str) -> str:
    """Generate a runtime id for ``kind`` (e.g. ``task_01J...``)."""

    if kind not in _RUNTIME_PREFIXES:
        raise ValueError(f"unknown runtime kind {kind!r}")
    return f"{kind}_{new_ulid()}"


def is_runtime_id(value: object) -> bool:
    return isinstance(value, str) and bool(_RUNTIME_ID_RE.match(value))


def is_slug(value: object) -> bool:
    return isinstance(value, str) and bool(_SLUG_RE.match(value))


def id_matches_kind(kind: str, value: object) -> bool:
    """Validate an entity id against the rule for its kind (docs/08 §3)."""

    if not isinstance(value, str):
        return False
    if kind in _RUNTIME_PREFIXES:
        return value.startswith(f"{kind}_") and bool(_ULID_RE.match(value[len(kind) + 1 :]))
    if kind == "settings":
        return is_slug(value)
    return is_slug(value)


__all__ = [
    "new_ulid",
    "new_id",
    "is_runtime_id",
    "is_slug",
    "id_matches_kind",
]
