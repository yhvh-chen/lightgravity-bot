"""LG268: explicit delivery goals outrank question words in their content."""
from __future__ import annotations

import pytest

from lightgravity.coordinator import MessageIntent, classify_message
from lightgravity.store import FileStore

from coordinator_helpers import CONV, make_coordinator, message

# Exact script §4 P1, retained here as a regression input, not production logic.
P1 = (
    '@bot Using the selected sources, write launch-brief.md: a one-page launch brief for\n'
    'the product in the brief. Include the headline and key message, a Free vs Team pricing\n'
    'table, the top customer concern from the call and how we answer it, and a short FAQ.\n'
    'Cite the source for every point.'
)


@pytest.mark.parametrize('content', [
    P1,
    P1.replace('write ', 'create ', 1),
    'Write notes.md covering how we answer it.',
    'Please draft an outline of what is missing.',
    'Produce a progress report covering why we delayed.',
    'Using the provided materials, draft a memo on how it works.',
    'From attached files, produce an FAQ about what is new.',
    'Based on the selected context, write a report about how it works.',
    'Create a file: how should it work?',
    'Implement a page showing how to use the product.',
])
def test_explicit_delivery_outranks_embedded_questions(content: str) -> None:
    result = classify_message(content)
    assert result.intent == MessageIntent.DELIVERY
    assert result.next_action == 'create_task'


@pytest.mark.parametrize('content,intent', [
    ('How do I write a report?', MessageIntent.ANSWER),
    ('What is the best way to draft a memo?', MessageIntent.ANSWER),
    ('Why produce another document?', MessageIntent.ANSWER),
    ('Can you explain how to create a page?', MessageIntent.BOUNDED_READ),
    ('Read this file and explain how it works.', MessageIntent.BOUNDED_READ),
    ('Write a memo; explain the existing implementation.', MessageIntent.BOUNDED_READ),
    ('"Write notes about how it works"', MessageIntent.ANSWER),
    ('Please write notes on how it works; do not create a task.', MessageIntent.UNKNOWN),
    ('Write a file on how it works; cancel the current task.', MessageIntent.CONTROL),
    ('Draft an outline of how it works; approve the current candidate.', MessageIntent.DECISION),
    ('Produce a report about how it works; retry the current task.', MessageIntent.RETRY),
    ('What is the progress of the draft?', MessageIntent.STATUS_QUERY),
])
def test_questions_reads_and_actions_keep_their_routes(content: str, intent: MessageIntent) -> None:
    assert classify_message(content).intent == intent


@pytest.mark.parametrize('content,kind', [
    (P1, 'task'),
    (P1.replace('write ', 'create ', 1), 'task'),
    (P1.removeprefix('@bot '), 'recorded'),
    ('@bot How do I write a launch brief?', 'direct'),
    ('@bot Read this file and explain how it works.', 'bounded_read'),
])
async def test_team_global_delivery_and_mention_boundary(
    store: FileStore, content: str, kind: str,
) -> None:
    # Local deterministic responder only: no model, SDK execution or UI claim.
    coordinator = make_coordinator(store, team_mode=True, responder=lambda *_: 'fixture')
    try:
        result = await coordinator.submit_global_message(CONV, message(content))
        assert result.kind == kind
        tasks = coordinator.list_tasks()
        assert len(tasks) == (1 if kind == 'task' else 0)
        assert (result.task_id is not None) == (kind == 'task')
        if kind == 'task':
            assert coordinator.status(result.task_id)['phase'] == 'queued'
    finally:
        await coordinator.stop()
