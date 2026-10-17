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

    CJK keywords have no word delimiters; action occurrences are checked against
    command syntax separately.  ASCII keywords are
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


# Action verbs must address task execution or a delivery candidate.  Describing
# a game's stop/restart behaviour or naming acceptance criteria is not consent
# to change the coordinator's state.  Keep action priority, but inspect each
# occurrence instead of promoting every substring to a command.
_CLAUSE_BOUNDARY = re.compile(r"[，,。.!！?？;；\n]|\b(?:and|but|then)\b|并且|然后|但是|但|并")
_COMMAND_PREFIX = re.compile(
    r"(?:@bot\s*)?(?:(?:请|麻烦|立即|立刻|现在|帮我)\s*|"
    r"(?:please|now)\b\s*)*$"
)
# A delivery imperative may locate its work before naming the action. Keep
# these modifiers structural and bounded: arbitrary prose (including a status
# query or a negation) is not a command prefix.
_DELIVERY_SCOPE_PREFIX = re.compile(
    r"(?:在(?:(?:本次|当前|这个|该|已获准|获准|已授权|授权|指定|允许|批准|的|本|任务|项目|共享|团队)\s*)*"
    r"(?:工作区|工作目录|仓库|目录|范围)(?:内|中)?\s*|"
    r"(?:in|within)\s+(?:(?:the|this|current|authorized|approved|designated|task|project|shared|team)\s+)*"
    r"(?:workspace|working\s+directory|repository|directory|scope)\s*)$"
)
_ACTION_TARGET = re.compile(
    r"(?:(?:这个|那个|当前|本次|该|此|正在运行的|运行中的|修改|修复|开发|交付)\s*)*"
    r"(?:任务|执行|运行|候选|产物|结果|它|task_|run_)|"
    r"(?:(?:the|this|that|current|running|active|delivery)\s+)*"
    r"(?:task|run|candidate|delivery|execution|work|it)\b"
)


def _is_command(text: str, start: int, end: int) -> bool:
    """Recognize a bare action or an imperative aimed at a task/candidate."""

    boundaries = list(_CLAUSE_BOUNDARY.finditer(text, 0, start))
    clause_start = boundaries[-1].end() if boundaries else 0
    prefix = text[clause_start:start].strip()
    if _COMMAND_PREFIX.fullmatch(prefix) is None:
        return False
    # A comma-separated negative list keeps its negation: "do not cancel,
    # pause, approve ...". An explicit new imperative starts a new request.
    sentence_prefix = re.split(r"[。.!！?？;；\n]", text[:start])[-1]
    if not prefix and re.search(r"\b(?:do not|don't|never)\b[^;]*$", sentence_prefix):
        return False
    suffix = _CLAUSE_BOUNDARY.split(text[end:], maxsplit=1)[0].strip()
    return not suffix or _ACTION_TARGET.match(suffix) is not None


def _hit(text: str, keywords: tuple[str, ...], *, actions: bool = False) -> tuple[str, ...]:
    hits: list[str] = []
    quoted = _quoted_spans(text) if actions else ()
    for keyword in keywords:
        matcher = _matcher(keyword) or re.compile(re.escape(keyword))
        for match in matcher.finditer(text):
            start, end = match.span()
            if actions and (
                _inside(quoted, start)
                or _is_filename_token(text, end)
                or not _is_command(text, start, end)
            ):
                continue
            hits.append(keyword)
            break
    return tuple(hits)


# Explicit actions precede content classification. Status words also occur in
# deliverable descriptions, so they must not mask an explicit delivery request.
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

# Explicit refusal to create a new Task is routing intent, not a delivery
# request. Keep this vocabulary bounded to Task creation; it is not a general
# negation parser ("do not deploy" must not suppress an authorized file goal).
_NO_NEW_TASK = re.compile(
    r"(?:不要|别|无需|不用|不必)\s*(?:创建|新建)\s*(?:新的?|一个)?\s*(?:任务|task\b)|"
    r"\b(?:do\s+not|don't|never)\s+(?:create|open|start)\s+"
    r"(?:(?:a|any)\s+)?(?:new\s+)?task\b"
)


def _without_no_task_requests(text: str) -> tuple[str, bool]:
    """Mask only unquoted no-new-Task phrases, preserving all other evidence."""

    quoted = _quoted_spans(text)
    spans = [match.span() for match in _NO_NEW_TASK.finditer(text)
             if not _inside(quoted, match.start())]
    masked = text
    # Once refusal is explicit, quoted examples cannot supply a conflicting
    # delivery goal either. Preserve the original text for all other routes.
    for start, end in sorted(spans + (list(quoted) if spans else []), reverse=True):
        masked = masked[:start] + " " * (end - start) + masked[end:]
    return masked, bool(spans)


def _starts_delivery_request(text: str) -> bool:
    """Recognize an initial delivery imperative, not a mentioned/negated verb.

    Reuse command prefixes and keyword boundaries, allowing a bounded work
    scope modifier before the verb. A status query mentioning "do not create"
    must remain a query. Questions and bounded reads are checked separately
    before deferring status routing.
    """

    for keyword in _DELIVERY:
        matcher = _matcher(keyword) or re.compile(re.escape(keyword))
        for match in matcher.finditer(text):
            prefix = text[:match.start()].strip()
            scope = _DELIVERY_SCOPE_PREFIX.search(prefix)
            if scope:
                prefix = prefix[:scope.start()].strip()
            if _COMMAND_PREFIX.fullmatch(prefix):
                return True
    return False


def classify_message(content: str) -> Classification:
    """Classify one message with the deterministic v1 rules."""

    text = (content or "").strip().lower()
    if not text:
        return Classification(intent=MessageIntent.UNKNOWN, next_action="clarify", note="empty message")

    delivery_text, no_new_task = _without_no_task_requests(text)
    delivery_request = (
        _starts_delivery_request(delivery_text)
        and not _hit(text, _BOUNDED_READ)
        and not _hit(text, _QUESTION)
    )
    for intent, keywords in (
        (MessageIntent.CONTROL, _CONTROL),
        (MessageIntent.DECISION, _DECISION),
        (MessageIntent.STATUS_QUERY, _STATUS),
        (MessageIntent.RETRY, _RETRY),
    ):
        if intent == MessageIntent.STATUS_QUERY and delivery_request:
            continue
        matched = _hit(
            text,
            keywords,
            actions=intent in {MessageIntent.CONTROL, MessageIntent.DECISION, MessageIntent.RETRY},
        )
        if matched:
            return Classification(
                intent=intent,
                next_action=NEXT_ACTIONS[intent],
                matched=matched,
                requires_target=intent in {MessageIntent.CONTROL, MessageIntent.DECISION},
            )

    conflicting_delivery = no_new_task and _hit(delivery_text, _DELIVERY) and (
        any(_starts_delivery_request(clause.strip()) and not _hit(clause, _QUESTION)
            for clause in _CLAUSE_BOUNDARY.split(delivery_text))
        or not (_hit(text, _QUESTION) or _hit(text, _BOUNDED_READ))
    )
    if no_new_task and conflicting_delivery:
        # A conflicting write goal cannot bypass the Task/Run record through
        # a direct answer or bounded read. Existing control/query routes above
        # still operate on their existing targets.
        return Classification(
            intent=MessageIntent.UNKNOWN,
            next_action="clarify",
            note="delivery goal conflicts with explicit no-new-Task request",
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

    matched = _hit(delivery_text, _DELIVERY)
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
