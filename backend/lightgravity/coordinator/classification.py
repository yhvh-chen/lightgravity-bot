"""Deterministic first-version message classification (LG-007, docs/04 §2).

Every incoming message is classified before anything is written.  The rule set
is intentionally small and deterministic so routing is reproducible and does
**not** depend on a model call.  LG-010 may inject a richer classifier later,
but the coordinator never lets a classifier grant permissions or start work by
itself.

Key safety rule (docs/04 §3): the direct-answer and bounded read-only paths
never create a Task/Run and never receive write-capable tools.  The bounded
read ceiling below is an explicit allow-list subset of the SDK's built-in
read-only tools; anything not listed is denied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

#: The maximum tools a bounded read-only request may ever receive.  The
#: coordinator intersects this with the agent's ``tool_refs``; it never unions
#: in write/command/search tools to satisfy an under-specified request.
READ_ONLY_TOOL_CEILING: tuple[str, ...] = (
    "view_file",
    "list_directory",
    "search_directory",
    "find_file",
    "read_url_content",
)


class MessageIntent(StrEnum):
    """First-version routing intents (docs/04 §2 table)."""

    ANSWER = "answer"
    BOUNDED_READ = "bounded_read"
    DELIVERY = "delivery"
    FOLLOWUP = "followup"
    RETRY = "retry"
    STATUS_QUERY = "status_query"
    CONTROL = "control"
    DECISION = "decision"
    UNKNOWN = "unknown"


#: What the coordinator should do with a classified message.
#: ``direct``/``bounded_read``/``query`` never create a Run.
NEXT_ACTIONS: dict[MessageIntent, str] = {
    MessageIntent.ANSWER: "direct",
    MessageIntent.BOUNDED_READ: "bounded_read",
    MessageIntent.DELIVERY: "create_task",
    MessageIntent.FOLLOWUP: "append",
    MessageIntent.RETRY: "retry",
    MessageIntent.STATUS_QUERY: "query",
    MessageIntent.CONTROL: "control",
    MessageIntent.DECISION: "decision",
    MessageIntent.UNKNOWN: "clarify",
}


@dataclass(frozen=True, slots=True)
class Classification:
    """Result of classifying one message."""

    intent: MessageIntent
    next_action: str
    matched: tuple[str, ...] = ()
    bounded_tools: tuple[str, ...] = ()
    requires_target: bool = False
    note: str = ""

    @property
    def creates_work(self) -> bool:
        """Whether this message may create a Task/Run."""

        return self.next_action in {"create_task", "retry"}

    @property
    def is_direct(self) -> bool:
        """Whether this message is answered without any execution slot."""

        return self.next_action in {"direct", "bounded_read"}


#: Quote pairs whose contents are treated as quoted content, not commands.
_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (("\"", "\""), ("'", "'"), ("`", "`"), ("\u201c", "\u201d"))


def _ascii_matcher(keyword: str) -> re.Pattern[str] | None:
    """Whole-word regex for an ASCII keyword, or ``None`` for CJK keywords.

    CJK keywords have no word delimiters, so they keep the original substring
    semantics (existing Chinese commands must not regress).  ASCII keywords are
    matched on word boundaries so derived forms such as ``approved``,
    ``approval``, ``acceptance`` or ``cancellation`` no longer match the control
    stems ``approve``/``accept``/``cancel``.
    """

    if not keyword.isascii():
        return None
    pattern = re.escape(keyword)
    if keyword[:1].isalnum() or keyword[:1] == "_":
        pattern = r"(?<!\w)" + pattern
    if keyword[-1:].isalnum() or keyword[-1:] == "_":
        pattern = pattern + r"(?!\w)"
    return re.compile(pattern)


_MATCHER_CACHE: dict[str, re.Pattern[str] | None] = {}


def _matcher(keyword: str) -> re.Pattern[str] | None:
    if keyword not in _MATCHER_CACHE:
        _MATCHER_CACHE[keyword] = _ascii_matcher(keyword)
    return _MATCHER_CACHE[keyword]


def _quoted_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Character spans that sit inside a matched quoted segment."""

    spans: list[tuple[int, int]] = []
    for open_quote, close_quote in _QUOTE_PAIRS:
        start = 0
        while True:
            begin = text.find(open_quote, start)
            if begin == -1:
                break
            end = text.find(close_quote, begin + 1)
            if end == -1:
                break
            spans.append((begin, end + 1))
            start = end + 1
    return tuple(spans)


def _inside(spans: tuple[tuple[int, int], ...], pos: int) -> bool:
    return any(begin <= pos < end for begin, end in spans)


def _is_filename_token(text: str, end: int) -> bool:
    """Whether a keyword is immediately followed by a file extension."""

    return bool(re.match(r"\.[a-z0-9]{1,6}(?!\w)", text[end:]))


def _is_incidental_control(text: str, matcher: re.Pattern[str]) -> bool:
    """True when a control/decision keyword is only quoted content or a filename.

    A delivery imperative that merely *mentions* a control word (inside quotes
    or as a filename such as ``accept.md``) must not execute that word as a
    control command.  Only the concrete occurrence is suppressed; the keyword
    itself keeps matching elsewhere in the message.
    """

    quoted = _quoted_spans(text)
    for match in matcher.finditer(text):
        start, end = match.span()
        if _inside(quoted, start) or _is_filename_token(text, end):
            continue
        return False
    return True


def _hit(text: str, keywords: tuple[str, ...], *, suppress_incidental: bool = False) -> tuple[str, ...]:
    hits: list[str] = []
    for keyword in keywords:
        matcher = _matcher(keyword)
        if matcher is None:
            if keyword in text:
                hits.append(keyword)
        elif matcher.search(text):
            if suppress_incidental and _is_incidental_control(text, matcher):
                continue
            hits.append(keyword)
    return tuple(hits)


# Ordered rules: control/decision/status/retry precede content classification so
# that a high-impact verb is never mistaken for a delivery request.
_CONTROL = ("暂停", "取消", "停止", "中止", "pause", "cancel", "stop", "abort")
_DECISION = ("验收", "接受", "拒绝", "重开", "通过验收", "accept", "reject", "reopen", "approve")
_STATUS = (
    "进度",
    "状态",
    "队列",
    "排队",
    "成本",
    "费用",
    "用量",
    "结果如何",
    "status",
    "progress",
    "queue",
    "cost",
    "usage",
)
_RETRY = ("继续", "重试", "返修", "恢复执行", "retry", "continue", "repair", "resume")
_BOUNDED_READ = (
    "读这个文件",
    "读一下",
    "查看文件",
    "打开文件",
    "解释",
    "是什么内容",
    "read the file",
    "read this",
    "look at",
    "explain",
    "summarize the file",
    "show me the file",
)
_FOLLOWUP = ("补充", "另外", "追加", "更新需求", "补充资料", "follow up", "additionally", "update the task")
_QUESTION = ("你能做什么", "是什么", "为什么", "怎么", "如何", "吗？", "吗?", "what can you", "what is", "how ", "why ")
_DELIVERY = (
    "修改",
    "实现",
    "创建",
    "新增",
    "添加",
    "开发",
    "修复",
    "写一个",
    "写个",
    "重构",
    "部署",
    "implement",
    "modify",
    "create",
    "add ",
    "fix ",
    "build ",
    "refactor",
)


def classify_message(content: str) -> Classification:
    """Classify one message with the deterministic v1 rules."""

    text = (content or "").strip().lower()
    if not text:
        return Classification(intent=MessageIntent.UNKNOWN, next_action="clarify", note="empty message")

    for intent, keywords in (
        (MessageIntent.CONTROL, _CONTROL),
        (MessageIntent.DECISION, _DECISION),
        (MessageIntent.STATUS_QUERY, _STATUS),
        (MessageIntent.RETRY, _RETRY),
    ):
        matched = _hit(
            text,
            keywords,
            suppress_incidental=intent in {MessageIntent.CONTROL, MessageIntent.DECISION},
        )
        if matched:
            return Classification(
                intent=intent,
                next_action=NEXT_ACTIONS[intent],
                matched=matched,
                requires_target=intent in {MessageIntent.CONTROL, MessageIntent.DECISION},
            )

    matched = _hit(text, _BOUNDED_READ)
    if matched:
        return Classification(
            intent=MessageIntent.BOUNDED_READ,
            next_action="bounded_read",
            matched=matched,
            bounded_tools=READ_ONLY_TOOL_CEILING,
            note="read-only ceiling; no write/command tools",
        )

    # A question is answered directly even if it contains a delivery verb.
    if _hit(text, _QUESTION):
        return Classification(
            intent=MessageIntent.ANSWER,
            next_action="direct",
            matched=_hit(text, _QUESTION),
        )

    matched = _hit(text, _DELIVERY)
    if matched:
        return Classification(
            intent=MessageIntent.DELIVERY,
            next_action="create_task",
            matched=matched,
        )

    matched = _hit(text, _FOLLOWUP)
    if matched:
        return Classification(
            intent=MessageIntent.FOLLOWUP,
            next_action="append",
            matched=matched,
            requires_target=True,
        )

    # Unrecognized plain text is a direct answer, never an implicit delivery.
    return Classification(intent=MessageIntent.ANSWER, next_action="direct")


@dataclass(frozen=True, slots=True)
class DirectReply:
    """A reply produced without entering the delivery pipeline."""

    content: str
    intent: MessageIntent
    tool_ceiling: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "READ_ONLY_TOOL_CEILING",
    "MessageIntent",
    "NEXT_ACTIONS",
    "Classification",
    "DirectReply",
    "classify_message",
]
