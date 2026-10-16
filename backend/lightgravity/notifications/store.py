"""Durable notification read-state store (LG-019; docs/04 §8).

Projection identifies notifications; this store remembers which ones the user
has read.  Read state is independent of Task status (docs/04 §8: the record only
maintains read/delivered, it does not copy Task state) and survives a browser
refresh or a process restart.

Each notification is one Markdown file ``<data>/notifications/<id>.md`` with
frontmatter ``kind: notification``.  There is intentionally no write path from
the projection: ``mark_read`` is the only mutation and it is idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ..store.atomic import atomic_write_text
from ..store.clock import to_iso, utcnow
from ..store.frontmatter import parse_document, plain, render_document


class NotificationStateStore:
    """Per-notification read flags keyed by the projection's stable id."""

    def __init__(self, data_dir: Path | str) -> None:
        self._root = Path(data_dir) / "notifications"

    @property
    def root(self) -> Path:
        return self._root

    def path(self, notification_id: str) -> Path:
        return self._root / f"{notification_id}.md"

    def read_state(self, notification_id: str) -> dict[str, Any]:
        path = self.path(notification_id)
        if not path.is_file():
            return {}
        try:
            raw, _ = parse_document(path.read_text("utf-8"), source=str(path))
        except Exception:  # noqa: BLE001 - a corrupt record is treated as unread
            return {}
        return plain(raw) if isinstance(raw, dict) else {}

    def is_read(self, notification_id: str) -> bool:
        return bool(self.read_state(notification_id).get("read"))

    def mark_read(self, notification_id: str, *, at: str | None = None) -> dict[str, Any]:
        """Persist ``read: true``; idempotent for the same id."""

        self._root.mkdir(parents=True, exist_ok=True)
        path = self.path(notification_id)
        state = self.read_state(notification_id)
        if not state.get("read"):
            record = {
                "schema": "lightgravity.bot/v1",
                "kind": "notification",
                "id": notification_id,
                "read": True,
                "read_at": at or to_iso(utcnow()),
            }
            body = json.dumps(
                {"notification_id": notification_id, "read": True}, ensure_ascii=False
            )
            atomic_write_text(path, render_document(record, body))  # type: ignore[arg-type]
            state = self.read_state(notification_id)
        return state

    def read_map(self, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        return {nid: self.read_state(nid) for nid in ids}


__all__ = ["NotificationStateStore"]
