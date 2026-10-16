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


# ---------------------------------------------------------------------------
# LG-047 R2: English word/command matching (classifier false-positive fix)
# ---------------------------------------------------------------------------

_ORION_GOAL = (
    "Create a Markdown file orion-summary.md using only the selected brief. "
    "Include project name, programme owner, primary launch date, total approved "
    "budget, project ID, and change ticket. Return the file as the deliverable."
)


def test_observed_delivery_goal_with_approved_budget_is_delivery() -> None:
    """Substring 'approve' inside 'approved' must not turn delivery into control."""

    result = classify_message(_ORION_GOAL)
    assert result.intent == MessageIntent.DELIVERY
    assert result.next_action == "create_task"
    assert result.matched == ("create",)


def test_approved_budget_question_is_not_decision() -> None:
    result = classify_message("Who approved the budget?")
    assert result.intent == MessageIntent.ANSWER
    assert result.next_action == "direct"


def test_derived_control_nouns_are_not_control() -> None:
    """approval / acceptance / cancellation are derived nouns, not commands."""

    assert classify_message("Create acceptance.md").intent == MessageIntent.DELIVERY
    assert classify_message("Create approved-budget.md").intent == MessageIntent.DELIVERY
    assert classify_message("What is the approval status?").intent == MessageIntent.STATUS_QUERY
    result = classify_message("Create a doc explaining the cancellation policy")
    assert result.intent == MessageIntent.DELIVERY


def test_explicit_control_imperatives_still_valid() -> None:
    assert classify_message("Please approve the current candidate.").intent == MessageIntent.DECISION
    assert classify_message("Please accept the current candidate").intent == MessageIntent.DECISION
    assert classify_message("reject the current candidate").intent == MessageIntent.DECISION
    assert classify_message("cancel the running task").intent == MessageIntent.CONTROL
    assert classify_message("pause the running task").intent == MessageIntent.CONTROL


def test_quoted_or_filename_control_word_is_not_executed() -> None:
    """A delivery imperative mentioning a control word must stay delivery."""

    assert classify_message("Create a file accept.md listing the results").intent == MessageIntent.DELIVERY
    quoted = classify_message('Create a file with the text "approve" inside')
    assert quoted.intent == MessageIntent.DELIVERY


def test_question_mentioning_delivery_verb_is_not_authorized_write() -> None:
    result = classify_message("How do I create file?")
    assert result.intent == MessageIntent.ANSWER
    assert result.next_action == "direct"
    assert not result.creates_work


def test_chinese_commands_and_readonly_routing_unchanged() -> None:
    assert classify_message("取消那个修改任务").intent == MessageIntent.CONTROL
    assert classify_message("读这个文件并解释一下").intent == MessageIntent.BOUNDED_READ
    assert classify_message("现在进度如何？").intent == MessageIntent.STATUS_QUERY
    assert classify_message("修改示例页面并验证登录功能").intent == MessageIntent.DELIVERY
