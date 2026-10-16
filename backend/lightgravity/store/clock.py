"""UTC clock helpers (LG-004, docs/08 §3.3).

Timestamps are ISO-8601 UTC with a ``Z`` suffix.  The clock is injectable so
lease-expiry and recovery tests do not need to sleep or patch global time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_iso(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def plus_seconds(moment: datetime, seconds: int) -> datetime:
    return moment + timedelta(seconds=seconds)


__all__ = ["Clock", "utcnow", "to_iso", "from_iso", "plus_seconds"]
