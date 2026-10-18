"""Read-only Team conversation history projection (LG-205).

The existing message readers expose one conversation at a time.  Building the
Chat history list from the browser would therefore need one request per Task,
which does not scale and makes recency easy to fake from Task metadata.  This
module adds one narrow, read-only projection over the same persisted message
logs the existing readers use:

* the shared global conversation (``conversations/<global>/messages.jsonl``);
* every real Task conversation (``tasks/<task_id>/conversation.jsonl``).

Only the **last persisted message timestamp/seq** is projected.  It is never
inferred from ``TASK.md`` or a directory mtime, and a Task without any valid
persisted message is omitted.  Message bodies, authors and private Personal
conversations are deliberately not returned.

Authorization is unchanged: ``create_app`` mounts this router under the same
global access dependency as every other business route (team session required
in team mode; legacy local policy in single-user mode).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from .context import ApiContext, get_context
from .conversations import GLOBAL_CONVERSATION_ID

#: Bound the response and the number of conversation files read per request.
_MAX_HISTORY_ITEMS = 1000


def _last_persisted_message(path: Path) -> tuple[bool, str | None, int | None]:
    """Return ``(has_message, at, seq)`` for the last valid JSONL record.

    Reads backwards in bounded chunks so a large conversation does not need to
    be parsed in full.  A trailing partial line (from an interrupted append) is
    skipped exactly like ``load_jsonl`` does, without writing to the file.
    """

    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            buffer = b""
            while position > 0:
                size = min(8192, position)
                position -= size
                handle.seek(position)
                buffer = handle.read(size) + buffer
                lines = buffer.split(b"\n")
                if position > 0:
                    # The first line may start in the middle of a record.
                    buffer = lines[0]
                    candidates = lines[1:]
                else:
                    buffer = b""
                    candidates = lines
                for raw in reversed(candidates):
                    if not raw.strip():
                        continue
                    try:
                        record = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    at = record.get("at")
                    seq = record.get("seq")
                    return (
                        True,
                        at if isinstance(at, str) and at else None,
                        seq if isinstance(seq, int) and not isinstance(seq, bool) else None,
                    )
    except OSError:
        return False, None, None
    return False, None, None


def _sort_at(value: str | None) -> datetime | None:
    """Parse a persisted ISO timestamp for ordering; never invent one."""

    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _item(
    *,
    kind: str,
    task_ref: str | None,
    title: str,
    message: tuple[bool, str | None, int | None],
) -> dict[str, Any]:
    _has_message, at, seq = message
    return {
        "kind": kind,
        "task_ref": task_ref,
        "title": title,
        "last_message_at": at,
        "last_message_seq": seq,
    }


def build_history_router() -> APIRouter:
    """Build the additive, read-only conversation history projection."""

    router = APIRouter(tags=["conversations"])

    @router.get("/conversations/history")
    def read_history(
        ctx: Annotated[ApiContext, Depends(get_context)],
        limit: Annotated[int, Query(ge=1, le=_MAX_HISTORY_ITEMS)] = _MAX_HISTORY_ITEMS,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        data_dir = ctx.data_dir

        global_path = (
            data_dir
            / "conversations"
            / GLOBAL_CONVERSATION_ID
            / "messages.jsonl"
        )
        global_message = _last_persisted_message(global_path)
        # General is always available even when its conversation is empty.
        items.append(
            _item(
                kind="general",
                task_ref=None,
                title="General",
                message=global_message,
            )
        )

        for summary in ctx.store.list_tasks():
            path = data_dir / "tasks" / summary.id / "conversation.jsonl"
            message = _last_persisted_message(path)
            if not message[0]:
                continue
            items.append(
                _item(
                    kind="task",
                    task_ref=summary.id,
                    title=summary.title,
                    message=message,
                )
            )

        # Newest actual last message first.  General wins a tie so the
        # no-message entry stays deterministic at the end of the list.
        items.sort(
            key=lambda item: (
                _sort_at(item["last_message_at"]) is not None,
                _sort_at(item["last_message_at"]) or datetime.min.replace(tzinfo=timezone.utc),
                item["kind"] == "general",
                item["task_ref"] or "",
            ),
            reverse=True,
        )
        return {"items": items[:limit]}

    return router


__all__ = ["build_history_router"]
