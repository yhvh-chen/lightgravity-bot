"""Message classification and read-only permission ceiling (LG-007)."""

from __future__ import annotations

from lightgravity.coordinator import READ_ONLY_TOOL_CEILING, MessageIntent, classify_message


def test_plain_question_is_direct_answer() -> None:
    result = classify_message("你能做什么？")
    assert result.intent == MessageIntent.ANSWER
    assert result.next_action == "direct"
    assert not result.creates_work


def test_delivery_request_creates_task() -> None:
    result = classify_message("修改示例页面并验证登录功能")
    assert result.intent == MessageIntent.DELIVERY
    assert result.next_action == "create_task"
    assert result.creates_work


def test_control_beats_delivery_keywords() -> None:
    result = classify_message("取消那个修改任务")
    assert result.intent == MessageIntent.CONTROL
    assert result.next_action == "control"


def test_status_query() -> None:
    result = classify_message("现在进度如何？")
    assert result.intent == MessageIntent.STATUS_QUERY
    assert result.next_action == "query"


def test_bounded_read_only_ceiling() -> None:
    result = classify_message("读这个文件并解释一下")
    assert result.intent == MessageIntent.BOUNDED_READ
    assert result.next_action == "bounded_read"
    assert result.is_direct
    assert result.bounded_tools
    assert set(result.bounded_tools) <= set(READ_ONLY_TOOL_CEILING)
    # Explicitly no write/command/search permission expansion.
    assert "create_file" not in result.bounded_tools
    assert "edit_file" not in result.bounded_tools
    assert "run_command" not in result.bounded_tools
    assert "search_web" not in result.bounded_tools


def test_empty_message_is_clarify() -> None:
    result = classify_message("   ")
    assert result.intent == MessageIntent.UNKNOWN
    assert result.next_action == "clarify"
