"""Personal responder seam receives attachment context separately (LG-119 R2).

No product model call is made.  These tests exercise the real coordinator
entry point and the synchronous dialogue adapter with fakes, proving that:

* the injected responder receives the bounded, owner-checked text as a separate
  argument (never merged into the persisted user ``content``);
* the reply note explains unsupported/binary content instead of claiming it was
  read;
* a legacy 2-arg responder keeps working and gets the honest "not delivered"
  note rather than a silent drop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lightgravity.coordinator.classification import classify_message
from lightgravity.coordinator.dialogue import make_sync_responder
from lightgravity.coordinator.service import Coordinator
from lightgravity.store import FileStore, new_id


def _coordinator(
    tmp_path: Path, responder: Any
) -> tuple[Coordinator, FileStore]:
    store = FileStore(tmp_path / "data", tmp_path / "ws")
    return (
        Coordinator(
            store,
            responder=responder,
            team_mode=True,
            data_dir=tmp_path / "data",
        ),
        store,
    )


async def test_three_arg_personal_responder_receives_exact_context_separately(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, str | None]] = []

    def responder(
        content: str, _classification: Any, attachment_context: str | None = None
    ) -> str:
        seen.append((content, attachment_context))
        return "reply"

    coordinator, _store = _coordinator(tmp_path, responder)
    conversation_id = new_id("conv")
    sentinel = "EXACT-FILE-SENTINEL-KEEP-SEPARATE"
    result = await coordinator.submit_personal_message(
        conversation_id,
        {
            "message_id": "msg_seam",
            "role": "user",
            "content": "what does the file say?",
            "attachments": [
                {
                    "attachment_id": "att_01J9Z0000000000000000000AH",
                    "filename": "x.txt",
                }
            ],
            "private": True,
        },
        owner="alice",
        attachment_context=sentinel,
    )
    assert result.kind == "direct"
    assert seen == [("what does the file say?", sentinel)]
    items = coordinator.read_global_messages(conversation_id)
    user = next(item for item in items if item["message_id"] == "msg_seam")
    assert user["message"]["content"] == "what does the file say?"
    assert sentinel not in user["message"]["content"]
    assistant = next(
        item for item in items if item["message"].get("role") == "assistant"
    )
    assert assistant["message"]["data"]["attachment_context_included"] is True


async def test_unsupported_note_is_visible_and_binary_never_claimed_read(
    tmp_path: Path,
) -> None:
    seen: list[str | None] = []

    def responder(
        content: str, _classification: Any, attachment_context: str | None = None
    ) -> str:
        seen.append(attachment_context)
        return "ok"

    coordinator, _store = _coordinator(tmp_path, responder)
    note = "Not read by the model: scan.pdf (binary or non-UTF-8)."
    result = await coordinator.submit_personal_message(
        new_id("conv"),
        {"message_id": "msg_note", "role": "user", "content": "read it", "private": True},
        owner="alice",
        attachment_context="",
        attachment_note=note,
    )
    assert seen == [""]
    assert result.reply is not None
    assert result.reply.startswith(note)
    assert "ok" in result.reply


async def test_two_arg_legacy_responder_gets_honest_not_delivered_note(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def responder(content: str, _classification: Any) -> str:
        calls.append(content)
        return "legacy reply"

    coordinator, _store = _coordinator(tmp_path, responder)
    result = await coordinator.submit_personal_message(
        new_id("conv"),
        {"message_id": "msg_legacy", "role": "user", "content": "hi", "private": True},
        owner="alice",
        attachment_context="SENTINEL",
    )
    assert calls == ["hi"]
    assert result.reply is not None
    assert "could not receive the attachment text" in result.reply
    assert "SENTINEL" not in result.reply


async def test_sync_dialogue_adapter_forwards_context_to_real_dialogue_method() -> None:
    seen: list[tuple[str, str | None]] = []

    class FakeDialogue:
        timeout_seconds = 1.0

        async def answer(self, text: str, attachment_context: str | None = None) -> str:
            seen.append((text, attachment_context))
            return "dialogue answer"

    responder = make_sync_responder(FakeDialogue())  # type: ignore[arg-type]
    reply = responder(
        "question", classify_message("question"), "EXACT-FILE-SENTINEL"
    )
    assert reply == "dialogue answer"
    assert seen == [("question", "EXACT-FILE-SENTINEL")]


def test_context_is_wrapped_as_untrusted_data_in_prompt() -> None:
    from lightgravity.coordinator.dialogue import _compose_prompt

    prompt = _compose_prompt("summarize", "EXACT-FILE-SENTINEL")
    assert "EXACT-FILE-SENTINEL" in prompt
    assert "untrusted-data" in prompt
    assert "not instructions" in prompt
    # Without attachments the legacy prompt is unchanged.
    assert _compose_prompt("summarize", None) == "summarize"
