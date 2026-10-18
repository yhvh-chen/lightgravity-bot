"""LG-013 direct-answer dialogue tests (no network, no real model call).

These assert the *contract* of the tool-less direct-answer handler: when no
connection/credential resolves it reports unavailable instead of inventing an
answer, and the synchronous adapter the coordinator uses returns that honest
message.  They never call the network and never require a credential value.
"""

from __future__ import annotations

from types import SimpleNamespace

from lightgravity.coordinator.classification import MessageIntent, classify_message
from lightgravity.coordinator.dialogue import (
    DialogueSupport,
    ModelDialogue,
    make_sync_responder,
    resolve_dialogue_support,
    unavailable_reply,
)


def _pin(**overrides: object) -> SimpleNamespace:
    values = {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "credential_ref": "deepseek-api-key",
        "backend": "openai-compat",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_resolve_support_requires_all_fields() -> None:
    assert resolve_dialogue_support(None) is None
    assert resolve_dialogue_support(_pin()) is not None
    # A missing model/credential means the connection cannot answer; do not run
    # a half-configured call.
    assert resolve_dialogue_support(_pin(model="")) is None
    assert resolve_dialogue_support(_pin(credential_ref="")) is None
    assert resolve_dialogue_support(_pin(base_url="")) is None


def test_unavailable_when_credential_missing() -> None:
    support = DialogueSupport(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-api-key",
    )
    dialogue = ModelDialogue(support, lambda _ref: None)
    assert dialogue.available() is False


def test_sync_responder_reports_unavailable_not_fabricated() -> None:
    support = DialogueSupport(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-api-key",
    )
    dialogue = ModelDialogue(support, lambda _ref: None)
    responder = make_sync_responder(dialogue)

    classification = classify_message("你能做什么？")
    reply = responder("你能做什么？", classification)

    assert reply == unavailable_reply(MessageIntent.ANSWER.value)
    assert "unavailable" in reply.lower()


def test_bounded_read_unavailable_message_mentions_no_write_grant() -> None:
    classification = classify_message("read the file")
    assert classification.intent == MessageIntent.BOUNDED_READ
    reply = unavailable_reply(classification.intent.value)
    assert "Read-only" in reply


def test_resolver_exception_is_treated_as_unavailable() -> None:
    support = DialogueSupport(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-api-key",
    )

    def boom(_ref: str) -> object:
        raise RuntimeError("secret store unavailable")

    dialogue = ModelDialogue(support, boom)
    assert dialogue.available() is False
