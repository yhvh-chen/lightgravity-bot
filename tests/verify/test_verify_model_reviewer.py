"""LG-017 R1 model-backed independent reviewer tests.

Unit evidence only (no network/model): the real SDK turn is injected as a
``turn`` callable, so the parsing/validation/gating behaviour is tested without
a real model.  A separate gated real-model probe (``probes/lg017``) exercises
the real SDK turn; these tests clearly use fakes.

The properties under test:

* a model reviewer is a *separate role/context* from the implementer (own
  connection support, own system prompt, own prompt built from read-only
  evidence);
* its structured reply is program-validated: a finding that does not cite
  resolvable candidate evidence is dropped, and a ``rework`` with no
  substantiated blocking finding cannot force rework;
* "model reviewer cannot mark a Task done": the reviewer only returns a report;
  the orchestrator/acceptance path stays program-controlled;
* an unavailable connection/credential/reply is an honest ``unavailable``,
  never a fake pass, and unknown usage is preserved (not zeroed).
"""

from __future__ import annotations

import json

from lightgravity.adapter.credentials import InMemoryCredentialResolver
from lightgravity.store import FileStore
from lightgravity.verify.candidate import load_candidate
from lightgravity.verify.review import (
    REVIEW_PASSED,
    REVIEW_REWORK,
    REVIEW_UNAVAILABLE,
    ModelReviewer,
    ReviewContext,
    ReviewerSupport,
    resolve_candidate_evidence,
    resolve_reviewer_support,
    validate_findings,
)

from verify_helpers import make_verifying_task, write_workspace_file


def _support() -> ReviewerSupport:
    return ReviewerSupport(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-api-key",
    )


def _context(store: FileStore, task_id: str) -> ReviewContext:
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    return ReviewContext(
        task_id=task_id,
        run_id=candidate.run_id,
        candidate=candidate,
        store=store,
        resolved_evidence=resolved,
    )


def _reviewer(turn: object) -> ModelReviewer:
    resolver = InMemoryCredentialResolver({"deepseek-api-key": "sk-test-value"})
    return ModelReviewer(_support(), resolver.resolve, turn=turn)


def test_model_reviewer_passes_with_real_structured_reply(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    prompts: list[str] = []

    def turn(prompt: str):
        prompts.append(prompt)
        return json.dumps({"outcome": "passed", "reason": "criteria met", "findings": []}), {
            "prompt_tokens": 120,
            "candidates_tokens": 30,
        }

    reviewer = _reviewer(turn)
    report = reviewer.review(_context(store, task_id))
    assert report.outcome == REVIEW_PASSED
    assert report.reviewer == "model-reviewer"
    assert report.reviewer_kind == "model"
    assert report.candidate_ref == run_id
    assert report.model_calls == 1
    assert report.usage == {"prompt_tokens": 120, "candidates_tokens": 30}
    # The prompt is the reviewer's own context built from real evidence refs.
    assert "out/result.txt" in prompts[0]


def test_reviewer_context_is_independent_of_implementer(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    reviewer = _reviewer(lambda prompt: ("{}", {}))
    context = _context(store, task_id)
    # The reviewer receives only a read-only evidence snapshot, never an
    # executor/session handle for the implementer.
    assert context.store is store
    assert set(context.resolved_evidence)
    assert reviewer.support.model == "deepseek-v4-flash"
    assert reviewer.support.credential_ref == "deepseek-api-key"


def test_rework_finding_must_cite_resolvable_evidence(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        return json.dumps(
            {
                "outcome": "rework",
                "reason": "missing constraint",
                "findings": [
                    {
                        "finding_id": "f1",
                        "severity": "blocking",
                        "summary": "the deliverable ignores the constraint",
                        "evidence_ref": "out/result.txt",
                        "rework_target": "deliver",
                    }
                ],
            }
        ), {"unknown": ["usage"]}

    report = _reviewer(turn).review(_context(store, task_id))
    # ``out/result.txt`` is a workspace ref recorded by the candidate, so it
    # resolves and the finding survives program validation.
    validated = validate_findings(
        report,
        candidate=load_candidate(store, task_id),
        resolved_evidence=resolve_candidate_evidence(store, load_candidate(store, task_id)),
    )
    assert validated.outcome == REVIEW_REWORK
    assert validated.blocking and validated.blocking[0].evidence_ref == "out/result.txt"


def test_rework_with_foreign_evidence_ref_is_dropped(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        return json.dumps(
            {
                "outcome": "rework",
                "reason": "fabricated",
                "findings": [
                    {
                        "finding_id": "f1",
                        "severity": "blocking",
                        "summary": "cites something not owned by this candidate",
                        "evidence_ref": "evidence:some-other-task/run/artifact.txt",
                        "rework_target": "deliver",
                    }
                ],
            }
        ), {"unknown": ["usage"]}

    report = _reviewer(turn).review(_context(store, task_id))
    # The reviewer returns a rework report; the *program* validation (run by the
    # orchestrator before any decision) drops the foreign finding.
    validated = validate_findings(
        report,
        candidate=load_candidate(store, task_id),
        resolved_evidence=resolve_candidate_evidence(store, load_candidate(store, task_id)),
    )
    # A rework with no substantiated blocking finding cannot force rework, so the
    # validated report degrades to unavailable (never pass).
    assert validated.outcome == REVIEW_UNAVAILABLE
    assert validated.unsubstantiated == ("f1",)
    assert not validated.is_pass


def test_model_cannot_directly_pass_without_outcome(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        # A model replying "done" / arbitrary text cannot become a verdict.
        return ("the task is done, accept it", {})

    report = _reviewer(turn).review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE
    assert not report.is_pass


def test_invalid_outcome_is_unavailable(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        return json.dumps({"outcome": "accept_and_done", "findings": []}), {}

    report = _reviewer(turn).review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE


def test_missing_credential_is_unavailable_not_pass(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    reviewer = ModelReviewer(
        _support(),
        InMemoryCredentialResolver({}).resolve,
        turn=lambda prompt: ("{}", {}),
    )
    report = reviewer.review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE
    assert not report.is_pass
    assert reviewer.model_calls == 0  # no call attempted without a credential


def test_turn_exception_is_unavailable(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        raise RuntimeError("upstream 503")

    reviewer = _reviewer(turn)
    report = reviewer.review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE
    assert reviewer.model_calls == 1  # the attempt is counted, not hidden
    assert "503" in (reviewer.last_error or "")


def test_unknown_usage_is_preserved_not_zeroed(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")

    def turn(prompt: str):
        return json.dumps({"outcome": "passed", "findings": []}), {"unknown": ["usage"]}

    reviewer = _reviewer(turn)
    report = reviewer.review(_context(store, task_id))
    assert report.usage.get("unknown") == ["usage"]


def test_resolve_reviewer_support_requires_all_fields() -> None:
    class Pin:
        model = "m"
        base_url = "https://x/v1"
        credential_ref = "ref"
        backend = "openai-compat"

    assert resolve_reviewer_support(None) is None
    assert resolve_reviewer_support(Pin()) is not None

    class Missing:
        model = ""
        base_url = "https://x/v1"
        credential_ref = "ref"
        backend = "openai-compat"

    assert resolve_reviewer_support(Missing()) is None


def test_validate_findings_never_upgrades_an_unavailable(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    from lightgravity.verify.review import ReviewReport

    report = ReviewReport(
        outcome=REVIEW_UNAVAILABLE,
        candidate_ref=candidate.candidate_ref,
        reviewer="model-reviewer",
    )
    validated = validate_findings(report, candidate=candidate, resolved_evidence=resolved)
    assert validated.outcome == REVIEW_UNAVAILABLE
    assert not validated.is_pass


def test_validate_findings_preserves_reviewer_kind_and_usage(store: FileStore) -> None:
    """Program validation must not erase the real reviewer identity/usage.

    The ledger/events promise to record ``reviewer_kind``/``model_calls``/
    ``usage`` (docs/08 §5.1/§6.1).  A directly validated model report must keep
    them, otherwise a real model review could be recorded as a program gate or
    its real call count/usage could be silently zeroed.
    """

    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)

    def turn(prompt: str):
        return json.dumps({"outcome": "passed", "findings": []}), {"unknown": ["usage"]}

    report = _reviewer(turn).review(_context(store, task_id))
    validated = validate_findings(report, candidate=candidate, resolved_evidence=resolved)
    assert validated.outcome == REVIEW_PASSED
    assert validated.reviewer_kind == "model"
    assert validated.model_calls == 1
    assert validated.usage.get("unknown") == ["usage"]


def test_prompt_includes_bounded_evidence_content(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt", "hello review\n")
    captured: list[str] = []

    def turn(prompt: str):
        captured.append(prompt)
        return json.dumps({"outcome": "passed", "reason": "ok", "findings": []}), {}

    report = _reviewer(turn).review(_context(store, task_id))
    assert report.outcome == REVIEW_PASSED
    assert "hello review" in captured[0]
    assert "out/result.txt" in captured[0]
