"""Message classification and read-only permission ceiling (LG-007)."""

from __future__ import annotations

import pytest

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


# Delivery description with stop/restart/approval wording; generic fixture data.
_DELIVERY_DESCRIPTION = """@bot 请在本次获准的任务工作区开发一个名为 FOCUS TIMER 的网页小工具，并创建交付任务。

玩法：点击开始后倒计时，操作结果实时更新；每局 30 秒，时间到后停止计时并显示最终结果，支持重新开始，重开时结果和计时归零。

交付：design.md、单文件 index.html（CSS 和 JavaScript 全部内联，无外部资源或网络依赖）、验证结果。请先明确设计，再按设计实现并验证。

验收：有开始按钮、实时结果和剩余时间；计时能启动且操作有效；结束后不能继续计时；重新开始正常；常见桌面和手机宽度均可操作。

请按需使用当前已配置的能力，保留实际执行与验证记录。不要部署或发布，完成后等待人工验收，并返回 Task ID。
"""


def test_delivery_description_with_control_words_creates_work() -> None:
    result = classify_message(_DELIVERY_DESCRIPTION)
    assert result.intent == MessageIntent.DELIVERY
    assert result.next_action == "create_task"
    assert not result.requires_target


@pytest.mark.parametrize("content", [
    "开发小工具，时间到后停止计时，完成后等待人工验收。",
    "创建计时器。验收：有开始按钮，重开时结果归零。",
    "实现计时器，结束后不能继续计时。验收条件：重新开始正常。",
    "Create a timer; stop timing when time expires and restart the timer on replay.",
    '创建文件，内容是“取消当前任务”和“验收当前候选”。',
    "Create a timer and wait for a human to approve the current candidate.",
])
def test_delivery_action_descriptions_are_not_commands(content: str) -> None:
    assert classify_message(content).intent == MessageIntent.DELIVERY


@pytest.mark.parametrize("content, intent", [
    ("取消那个修改任务", MessageIntent.CONTROL),
    ("@bot 请暂停当前任务", MessageIntent.CONTROL),
    ("请停止正在运行的任务", MessageIntent.CONTROL),
    ("修改页面，但取消当前任务", MessageIntent.CONTROL),
    ("Create a page, but cancel the current task", MessageIntent.CONTROL),
    ("Create a page and pause the running task", MessageIntent.CONTROL),
    ("请验收当前候选", MessageIntent.DECISION),
    ("Please approve the current candidate", MessageIntent.DECISION),
    ("创建页面；请拒绝当前候选", MessageIntent.DECISION),
    ("请继续修复当前任务", MessageIntent.RETRY),
    ("retry", MessageIntent.RETRY),
    ("取消", MessageIntent.CONTROL),
    ("验收", MessageIntent.DECISION),
])
def test_real_actions_keep_priority(content: str, intent: MessageIntent) -> None:
    assert classify_message(content).intent == intent


@pytest.mark.parametrize("content", [
    "@bot 请查询共享任务 task_01ARZ3NDEKTSV4RRFFQ69G5FAV（每日计划）的当前状态：正在做什么、已经完成什么、是否有阻塞，以及已有的结果入口。只读取真实任务记录，不创建任务，不启动开发或返修。",
    "查询当前任务状态，不要取消或暂停，也不要继续开发或返修。",
    "Show current task status; do not cancel, pause, approve or repair it.",
    "验收状态如何？不要接受当前候选。",
])
def test_status_queries_with_negative_actions_create_no_work(content: str) -> None:
    result = classify_message(content)
    assert result.intent == MessageIntent.STATUS_QUERY
    assert result.next_action == "query"
    assert not result.creates_work


def test_negative_cancel_does_not_mask_positive_pause() -> None:
    result = classify_message("暂停当前任务，不要取消")
    assert result.intent == MessageIntent.CONTROL
    assert result.matched == ("暂停",)


@pytest.mark.parametrize("content", [
    "开发一个显示系统状态的小工具。",
    "实现页面，实时状态每 30 秒刷新。",
    "开发页面。验收：实时状态正确。",
    "@bot 请创建一个显示队列、进度和用量的页面。",
    "修改页面，显示成本与费用。",
    "Please create a system status page.",
    "Implement a progress indicator.",
    "Build a queue usage dashboard.",
    "Fix the cost display.",
])
def test_delivery_imperatives_with_status_words_create_work(content: str) -> None:
    result = classify_message(content)
    assert result.intent == MessageIntent.DELIVERY
    assert result.next_action == "create_task"
    assert result.creates_work


@pytest.mark.parametrize("content, intent", [
    ("查询创建任务的状态，不要创建新任务。", MessageIntent.STATUS_QUERY),
    ("Show the status of the build task; do not create a new task.", MessageIntent.STATUS_QUERY),
    ("What is the implementation progress?", MessageIntent.STATUS_QUERY),
    ("状态", MessageIntent.STATUS_QUERY),
    ("status", MessageIntent.STATUS_QUERY),
    ("如何创建状态页面？", MessageIntent.STATUS_QUERY),
    ("How do I create a status page?", MessageIntent.STATUS_QUERY),
    ("Create a status page 是什么意思？", MessageIntent.STATUS_QUERY),
    ("读这个文件，查看状态页面的实现。", MessageIntent.STATUS_QUERY),
    ("Read this file to explain the status display.", MessageIntent.STATUS_QUERY),
    ("创建一个页面，解释现有实现。", MessageIntent.BOUNDED_READ),
    ("Create a page; explain the current implementation.", MessageIntent.BOUNDED_READ),
    ("Create a file: how should it work?", MessageIntent.ANSWER),
    ("开发状态页面，但取消当前任务。", MessageIntent.CONTROL),
    ("Create a status page; please approve the current candidate.", MessageIntent.DECISION),
    ("实现状态页面；请继续修复当前任务。", MessageIntent.RETRY),
    ("Create a status page; retry the current task.", MessageIntent.RETRY),
])
def test_delivery_status_precedence_preserves_existing_boundaries(
    content: str, intent: MessageIntent,
) -> None:
    result = classify_message(content)
    assert result.intent == intent
    assert result.next_action != "create_task"
    if intent != MessageIntent.RETRY:
        assert not result.creates_work
