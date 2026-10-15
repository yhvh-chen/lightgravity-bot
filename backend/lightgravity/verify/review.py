"""Independent candidate review (LG-017, docs/08 §6.1/§9).

LG-009 hands a *verified* candidate to human acceptance.  LG-017 adds the
runtime step the product actually needs: an **independent reviewer** that looks
at the *candidate version's real evidence* and produces structured findings
before the candidate is offered for acceptance.

Two hard rules from the task:

* the reviewer is a separate context/role from the implementer.  It does not run
  the executor, it receives a read-only snapshot and the program-resolved
  evidence payloads (never the worker's own summary as proof);
* a finding is only valid when it cites a **resolvable** evidence reference
  belonging to the reviewed candidate.  Findings that cite missing/foreign
  evidence are dropped and reported as ``unsubstantiated`` rather than trusted.

There are three honest reviewer outcomes:

* :data:`REVIEW_PASSED`  - the reviewer examined the candidate and found no
  blocking problem;
* :data:`REVIEW_REWORK`  - the reviewer found problems and named rework targets;
* :data:`REVIEW_UNAVAILABLE` - **no usable independent reviewer** was available.
  This is *not* a pass: the candidate cannot be accepted and no round is spent.

The default reviewer is program-driven and deterministic: it re-derives the
authorized machine checks *in the reviewer's own context* and additionally
verifies that every recorded candidate artifact ref resolves under the owning
Task/Run.  A model-backed reviewer can be injected through the
:class:`Reviewer` port without changing the orchestrator; whatever it returns is
still passed through :func:`validate_findings`, so a model can never directly
mark a Task done.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from lightgravity.evidence import (
    EvidenceRefError,
    resolve_evidence_ref,
)
from lightgravity.store import Store

from .candidate import Candidate
from .checks import (
    ABSOLUTE_REF,
    BLOCKING_STATUSES,
    EVIDENCE_REF,
    WORKSPACE_REF,
    CheckRegistry,
    authorized_checks,
    classify_artifact_ref,
    default_check_registry,
    run_checks,
)

#: Reviewer outcomes (docs/08 §6.1 phase ``verifying`` -> ``repairing``).
REVIEW_PASSED = "passed"
REVIEW_REWORK = "rework"
REVIEW_UNAVAILABLE = "unavailable"

#: Severities a finding may carry.  Only ``blocking`` prevents acceptance.
SEV_BLOCKING = "blocking"
SEV_ADVISORY = "advisory"
_SEVERITIES = frozenset({SEV_BLOCKING, SEV_ADVISORY})

#: Empty placeholder that is **never** treated as a finding.
_NO_REF = ""


@dataclass(frozen=True, slots=True)
class Finding:
    """One structured review problem with a real evidence target.

    ``evidence_ref`` must resolve inside the reviewed candidate's Task/Run
    evidence root; ``rework_target`` names what a repair Run should change.
    """

    finding_id: str
    severity: str
    summary: str
    evidence_ref: str
    rework_target: str
    candidate_ref: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "summary": self.summary,
            "evidence_ref": self.evidence_ref,
            "rework_target": self.rework_target,
            "candidate_ref": self.candidate_ref,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        return cls(
            finding_id=str(data.get("finding_id", "")),
            severity=str(data.get("severity", SEV_BLOCKING)),
            summary=str(data.get("summary", "")),
            evidence_ref=str(data.get("evidence_ref", "")),
            rework_target=str(data.get("rework_target", "")),
            candidate_ref=str(data.get("candidate_ref", "")),
            detail=str(data.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class ReviewContext:
    """The read-only material a reviewer may inspect (no executor, no control)."""

    task_id: str
    run_id: str
    candidate: Candidate
    store: Store
    #: Evidence refs the program resolved to real, owned files (ref -> path).
    resolved_evidence: dict[str, Path] = field(default_factory=dict)
    #: LG-022 R1: cooperative stop channel for a long model turn.  The
    #: coordinator's review lifecycle sets this so pause/cancel can actually
    #: stop a running reviewer instead of only tracking the worker.  ``None``
    #: in the sync fixture path.
    stop_event: Any | None = None
    #: LG-022 R2: mutable sink the reviewer fills with the **real** reviewer
    #: resource teardown fact (SDK agent closed + loopback proxy stopped).  The
    #: coordinator records it so the stop gate sees the reviewer resource really
    #: stopped, not only the worker.  Left empty when no real turn ran.
    resource_stop_report: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ReviewReport:
    """Reviewer outcome for exactly one candidate version."""

    outcome: str
    candidate_ref: str
    findings: tuple[Finding, ...] = ()
    unsubstantiated: tuple[str, ...] = ()
    reviewer: str = ""
    reason: str = ""
    #: LG-017 R1 additive: ``program`` | ``model`` | ``unavailable`` — makes it
    #: explicit whether this was a machine gate or a real independent review.
    reviewer_kind: str = ""
    #: LG-017 R1 additive: real model calls made by this review (0 for program).
    model_calls: int = 0
    #: LG-017 R1 additive: real usage counters; unknown counters are listed,
    #: never zeroed.
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def is_pass(self) -> bool:
        return self.outcome == REVIEW_PASSED

    @property
    def is_rework(self) -> bool:
        return self.outcome == REVIEW_REWORK

    @property
    def is_unavailable(self) -> bool:
        return self.outcome == REVIEW_UNAVAILABLE

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == SEV_BLOCKING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "candidate_ref": self.candidate_ref,
            "findings": [f.to_dict() for f in self.findings],
            "unsubstantiated": list(self.unsubstantiated),
            "reviewer": self.reviewer,
            "reason": self.reason,
            "reviewer_kind": self.reviewer_kind,
            "model_calls": self.model_calls,
            "usage": dict(self.usage),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewReport":
        raw = data.get("findings")
        findings = tuple(
            Finding.from_dict(item) for item in raw if isinstance(item, dict)
        ) if isinstance(raw, list) else ()
        unsub = data.get("unsubstantiated")
        usage = data.get("usage")
        model_calls = data.get("model_calls")
        return cls(
            outcome=str(data.get("outcome", REVIEW_UNAVAILABLE)),
            candidate_ref=str(data.get("candidate_ref", "")),
            findings=findings,
            unsubstantiated=tuple(str(x) for x in unsub) if isinstance(unsub, list) else (),
            reviewer=str(data.get("reviewer", "")),
            reason=str(data.get("reason", "")),
            reviewer_kind=str(data.get("reviewer_kind", "")),
            model_calls=model_calls if isinstance(model_calls, int) and not isinstance(model_calls, bool) else 0,
            usage=dict(usage) if isinstance(usage, dict) else {},
        )


@runtime_checkable
class Reviewer(Protocol):
    """Independent reviewer port.

    Implementations must be *independent of the implementer*: they only receive
    :class:`ReviewContext` and return a :class:`ReviewReport`.  They never write
    control state.  A reviewer that cannot run must return
    ``outcome=unavailable`` (never a fabricated pass).
    """

    name: str

    def review(self, context: ReviewContext) -> ReviewReport: ...


def resolve_candidate_evidence(store: Store, candidate: Candidate) -> dict[str, Path]:
    """Resolve every recorded candidate artifact ref to a real owned file.

    Only canonical ``evidence:`` refs (owned by this Task/Run) and
    workspace-relative refs (under the authorized workspace root) resolve.
    Opaque refs (executor artifact ids that are not paths) and raw absolute
    paths are left out of the map: a finding citing them is unsubstantiated, and
    they must not be mistaken for missing workspace evidence.
    """

    resolved: dict[str, Path] = {}
    data_dir = getattr(store, "data_dir", None)
    for ref in candidate.artifact_refs:
        if not isinstance(ref, str) or not ref:
            continue
        kind, payload = classify_artifact_ref(ref)
        if kind == EVIDENCE_REF and payload:
            try:
                path = resolve_evidence_ref(
                    payload,
                    data_dir=data_dir,
                    task_id=candidate.task_id,
                    run_id=candidate.run_id,
                )
            except EvidenceRefError:
                continue
            resolved[ref] = path
            continue
        if kind == WORKSPACE_REF and payload:
            workspace_file = _resolve_workspace_ref(store, candidate, payload)
            if workspace_file is not None:
                resolved[ref] = workspace_file
    return resolved


def _resolve_workspace_ref(store: Store, candidate: Candidate, payload: str) -> Path | None:
    """Resolve a workspace-relative ref under the candidate's workspace root.

    Mirrors the machine-check containment rule (docs/08 §6.2/§6.3): the ref is
    joined to the candidate's authorized ``workspace_path`` and must stay inside
    it; a ref that escapes or does not resolve to a file is absent.
    """

    base_raw = candidate.workspace_path
    if not base_raw:
        return None
    try:
        base = Path(base_raw).resolve()
        target = (base / payload).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None

def declared_path_refs(candidate: Candidate) -> tuple[str, ...]:
    """Candidate artifact refs that *claim* to be resolvable path evidence.

    Opaque executor ids are excluded: they are not missing files, they are just
    not path evidence.  An empty tuple means the candidate declares no path
    evidence at all (LG-009 runs zero evidence checks in that case).
    """

    refs: list[str] = []
    for ref in candidate.artifact_refs:
        if not isinstance(ref, str) or not ref:
            continue
        kind, payload = classify_artifact_ref(ref)
        if kind in {EVIDENCE_REF, WORKSPACE_REF, ABSOLUTE_REF} and payload:
            refs.append(ref)
    return tuple(refs)


def validate_findings(
    report: ReviewReport,
    *,
    candidate: Candidate,
    resolved_evidence: dict[str, Path],
) -> ReviewReport:
    """Drop findings that do not cite a resolvable, candidate-owned artifact.

    This is the program gate that makes the reviewer's output trustworthy: a
    model (or check) can only raise a problem against *real* evidence.  Findings
    that fail are reported under ``unsubstantiated``; a ``rework`` report whose
    every finding is dropped degrades to ``unavailable`` rather than blocking
    with no evidence.
    """

    kept: list[Finding] = []
    dropped: list[str] = []
    for finding in report.findings:
        ref = finding.evidence_ref
        if (
            not finding.summary.strip()
            or finding.severity not in _SEVERITIES
            or not ref
            or ref == _NO_REF
            or ref not in resolved_evidence
        ):
            dropped.append(finding.finding_id or finding.summary or "<unnamed>")
            continue
        # Bind the finding to the reviewed candidate, never a foreign one.
        kept.append(
            Finding(
                finding_id=finding.finding_id,
                severity=finding.severity,
                summary=finding.summary,
                evidence_ref=ref,
                rework_target=finding.rework_target,
                candidate_ref=candidate.candidate_ref,
                detail=finding.detail,
            )
        )
    outcome = report.outcome
    if outcome == REVIEW_REWORK and not any(f.severity == SEV_BLOCKING for f in kept):
        # A rework with no substantiated blocking finding cannot force rework.
        outcome = REVIEW_UNAVAILABLE
    return ReviewReport(
        outcome=outcome,
        candidate_ref=candidate.candidate_ref,
        findings=tuple(kept),
        unsubstantiated=tuple(dropped),
        reviewer=report.reviewer,
        reason=report.reason,
        # Preserve the reviewer identity/kind and real model usage through
        # validation: dropping them would let a validated model review be
        # recorded as if it were a program gate (or hide a real call).
        reviewer_kind=report.reviewer_kind,
        model_calls=report.model_calls,
        usage=dict(report.usage),
    )


class ProgramReviewer:
    """Deterministic default reviewer (no model call).

    Independent of the implementer because it only reads the candidate snapshot
    and re-runs the Task-authorized machine checks in its own context, then
    confirms every candidate artifact actually resolves.  It produces a
    ``rework`` finding against the failing evidence when checks fail, and a
    ``passed`` report only when there is at least one real resolvable artifact
    to have reviewed (a candidate with *no* evidence is ``unavailable``, never a
    silent pass).
    """

    name = "program-reviewer"
    kind = "program"

    def __init__(self, registry: CheckRegistry | None = None) -> None:
        self._registry = registry or default_check_registry()

    def review(self, context: ReviewContext) -> ReviewReport:
        candidate = context.candidate
        resolved = context.resolved_evidence

        # Declared-but-unresolvable path evidence is a real integrity problem:
        # the candidate claims artifacts it cannot produce.  Opaque executor ids
        # (not paths) are excluded.  The reviewer cannot anchor a finding to a
        # missing file, so it reports unavailable (an honest bounded failure)
        # rather than a pass or a fabricated finding.
        declared = declared_path_refs(candidate)
        if declared and not resolved:
            return ReviewReport(
                outcome=REVIEW_UNAVAILABLE,
                candidate_ref=candidate.candidate_ref,
                reviewer=self.name,
                reason=(
                    f"candidate declares {len(declared)} artifact ref(s) but none resolve; "
                    "cannot substantiate an independent review"
                ),
            )

        authorized = authorized_checks(
            context.store.read("task", candidate.task_id).entity
        )
        from .checks import CheckContext

        report = run_checks(
            self._registry,
            authorized,
            CheckContext(
                task_id=candidate.task_id,
                run_id=candidate.run_id,
                candidate=candidate,
                store=context.store,
                workspace_path=candidate.workspace_path,
            ),
        )
        failed = [r for r in report.results if r.status in BLOCKING_STATUSES]
        if failed:
            if not resolved:
                # Nothing resolvable to anchor a finding to; this is an
                # unavailable review, never a fabricated rework or a pass.
                return ReviewReport(
                    outcome=REVIEW_UNAVAILABLE,
                    candidate_ref=candidate.candidate_ref,
                    reviewer=self.name,
                    reason="blocking check(s) failed but no candidate evidence resolves",
                )
            # Cite the first resolvable artifact as the evidence anchor: the
            # finding is about the candidate as a whole, and the anchor must be
            # a real owned file for the finding to survive validation.
            anchor = next(iter(resolved))
            findings = tuple(
                Finding(
                    finding_id=f"check:{r.check_id}",
                    severity=SEV_BLOCKING,
                    summary=f"machine check {r.check_id!r} reported {r.status}",
                    evidence_ref=anchor,
                    rework_target=(
                        candidate.subtask_refs[0] if candidate.subtask_refs else "deliverable"
                    ),
                    detail=r.detail,
                )
                for r in failed
            )
            return ReviewReport(
                outcome=REVIEW_REWORK,
                candidate_ref=candidate.candidate_ref,
                findings=findings,
                reviewer=self.name,
                reason=f"{len(failed)} blocking machine check(s) failed",
            )
        return ReviewReport(
            outcome=REVIEW_PASSED,
            candidate_ref=candidate.candidate_ref,
            reviewer=self.name,
            reason=(
                "independent program review found no blocking problem "
                f"across {len(resolved)} artifact(s)"
            ),
        )


class UnavailableReviewer:
    """Explicit "no independent reviewer is wired" reviewer.

    Used as the honest default when the runtime has no reviewer configured: it
    returns ``unavailable`` so the orchestrator keeps the candidate pending for
    a human/next step instead of accepting it, and never spends a rework round.
    """

    name = "unavailable"
    kind = "unavailable"

    def review(self, context: ReviewContext) -> ReviewReport:
        return ReviewReport(
            outcome=REVIEW_UNAVAILABLE,
            candidate_ref=context.candidate.candidate_ref,
            reviewer=self.name,
            reason="no independent reviewer is configured in this runtime",
        )


#: A model-backed review is a *single* bounded, tool-less turn.
DEFAULT_REVIEW_MODEL_CALLS = 1
DEFAULT_REVIEW_TIMEOUT_SECONDS = 120.0

_REVIEW_SYSTEM_INSTRUCTIONS = (
    "You are an independent QA reviewer for a delivery candidate. You did NOT "
    "write this candidate and you cannot change it. You receive only a read-only "
    "description of the candidate: the task title/objective/acceptance criteria, "
    "the machine check results, and a bounded excerpt of each of the candidate's "
    "real, resolvable evidence files. Decide whether the candidate satisfies the "
    "acceptance criteria based on that material. You have no tools: you cannot "
    "read further, write, run commands or browse. "
    "Reply with a single JSON object and nothing else:\n"
    '{"outcome": "passed"|"rework", "reason": string, '
    '"findings": [{"finding_id": string, "severity": "blocking"|"advisory", '
    '"summary": string, "evidence_ref": string, "rework_target": string, '
    '"detail": string}]}\n'
    "Every finding MUST cite an evidence_ref copied verbatim from the provided "
    "evidence list; a finding that cites anything else is discarded and cannot "
    "block or pass the candidate. If the provided material is insufficient to "
    "substantiate a verdict, reply with outcome \"unavailable\" instead of "
    "guessing. A 'passed' verdict means you examined the provided evidence and "
    "found no blocking problem."
)


def _parse_review_json(text: str) -> dict[str, Any] | None:
    """Extract one JSON object from a model reply (tolerating code fences)."""

    if not isinstance(text, str) or not text.strip():
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    import json

    try:
        parsed = json.loads(candidate[start : end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True, slots=True)
class ReviewerSupport:
    """Resolved, non-secret configuration for a real model-backed review.

    Built from the *reviewer* default connection pin + its `credential_ref`, so
    the reviewer never shares the implementer's connection/session unless the
    operator explicitly points them at the same connection.
    """

    model: str
    base_url: str
    credential_ref: str
    backend: str = "openai-compat"

    @property
    def usable(self) -> bool:
        return bool(self.model and self.base_url and self.credential_ref)


def resolve_reviewer_support(connection_pin: Any) -> ReviewerSupport | None:
    """Build :class:`ReviewerSupport` from a pinned reviewer connection."""

    if connection_pin is None:
        return None
    try:
        model = str(getattr(connection_pin, "model", "") or "")
        base_url = str(getattr(connection_pin, "base_url", "") or "")
        credential_ref = str(getattr(connection_pin, "credential_ref", "") or "")
        backend = str(getattr(connection_pin, "backend", "") or "openai-compat")
    except Exception:  # noqa: BLE001 - never raise at startup
        return None
    support = ReviewerSupport(
        model=model, base_url=base_url, credential_ref=credential_ref, backend=backend
    )
    return support if support.usable else None


#: Cap on how much of each evidence file the reviewer may read into its
#: read-only prompt (keeps the context bounded and the model roughly honest).
EVIDENCE_EXCERPT_BYTES = 2000


def _evidence_digest(context: ReviewContext) -> str:
    """Read-only, non-secret description of the candidate + its evidence.

    Includes a bounded excerpt of each resolved evidence file so the reviewer
    can substantiate a verdict from what was actually delivered (a bare ref list
    is not enough for a content criterion).  Excerpts are truncated and never
    include credential values.
    """

    candidate = context.candidate
    task_entity: dict[str, Any] = {}
    try:
        task_entity = context.store.read("task", candidate.task_id).entity
    except Exception:  # noqa: BLE001 - a missing task just means a thinner digest
        task_entity = {}
    lines = [
        f"task_id: {candidate.task_id}",
        f"run_id: {candidate.run_id}",
        f"candidate_ref: {candidate.candidate_ref}",
    ]
    title = task_entity.get("title")
    objective = task_entity.get("objective")
    if isinstance(title, str) and title:
        lines.append(f"title: {title}")
    if isinstance(objective, str) and objective:
        lines.append(f"objective: {objective}")
    criteria = task_entity.get("acceptance_criteria")
    if isinstance(criteria, list) and criteria:
        lines.append("acceptance_criteria:")
        lines.extend(f"- {item}" for item in criteria if isinstance(item, str))
    check_records = candidate.check_records
    if check_records:
        lines.append("machine_checks:")
        for record in check_records:
            check_id = record.get("check_id") if isinstance(record, dict) else None
            status = record.get("status") if isinstance(record, dict) else None
            detail = record.get("detail") if isinstance(record, dict) else None
            lines.append(f"- {check_id}: {status} {detail or ''}".rstrip())
    lines.append(
        "evidence (only these refs may be cited; a bounded excerpt of each is "
        "shown):"
    )
    if context.resolved_evidence:
        for ref, path in context.resolved_evidence.items():
            lines.append(f"--- {ref} ---")
            excerpt = _read_excerpt(path)
            lines.append(excerpt if excerpt else "<unreadable>")
    else:
        lines.append("- <none resolved>")
    return "\n".join(lines)


def _read_excerpt(path: Path) -> str:
    """Bounded, best-effort text excerpt of one evidence file (never raises)."""

    try:
        if not path.is_file():
            return ""
        raw = path.read_bytes()[:EVIDENCE_EXCERPT_BYTES]
    except OSError:
        return ""
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - decoding is best-effort
        return ""
    if len(raw) >= EVIDENCE_EXCERPT_BYTES:
        text += "\n<truncated>"
    return text


class ModelReviewer:
    """Real, minimal, controlled SDK reviewer (LG-017 R1).

    Runs **one** tool-less turn on the *reviewer* default connection (via the
    same loopback auth proxy the executor uses) with its own system instructions
    and its own prompt built from the read-only candidate evidence digest.  It
    never runs the executor, never reuses the implementer's session/context, and
    never writes control state.

    Its structured reply is parsed and then passed through
    :func:`validate_findings`, so a model can never accept a candidate on its own
    and a finding that does not cite resolvable candidate evidence is dropped.
    If the connection/credential/SDK is unavailable, or the turn fails, it
    returns an honest ``unavailable`` (never a fabricated pass) and records the
    attempt in :attr:`last_usage`.
    """

    name = "model-reviewer"
    kind = "model"

    def __init__(
        self,
        support: ReviewerSupport,
        credential_resolver: Callable[[str], Any],
        *,
        turn: Any | None = None,
        timeout_seconds: float = DEFAULT_REVIEW_TIMEOUT_SECONDS,
        max_model_calls: int = DEFAULT_REVIEW_MODEL_CALLS,
    ) -> None:
        self._support = support
        self._resolve = credential_resolver
        #: Injected turn (tests use a fake); ``None`` uses the real SDK turn.
        self._turn = turn
        self._timeout = timeout_seconds
        self._max_calls = max_model_calls
        self.model_calls = 0
        self.last_usage: dict[str, Any] = {"unknown": ["usage"]}
        self.last_error: str | None = None

    @property
    def support(self) -> ReviewerSupport:
        return self._support

    def available(self) -> bool:
        if not self._support.usable:
            return False
        try:
            return self._resolve(self._support.credential_ref) is not None
        except Exception:  # noqa: BLE001 - resolution failure is a readiness gap
            return False

    def review(self, context: ReviewContext) -> ReviewReport:
        candidate = context.candidate
        self.last_error = None
        if not self.available():
            self.last_error = "reviewer connection/credential is not resolvable"
            self.last_usage = {"unknown": ["usage"]}
            return self._report(
                REVIEW_UNAVAILABLE, candidate.candidate_ref, reason=self.last_error
            )
        declared = declared_path_refs(candidate)
        if declared and not context.resolved_evidence:
            self.last_error = "candidate declares path evidence but none resolves"
            return self._report(
                REVIEW_UNAVAILABLE, candidate.candidate_ref, reason=self.last_error
            )
        prompt = (
            "Review the following candidate. Cite only the evidence refs listed.\n\n"
            + _evidence_digest(context)
        )
        self.model_calls += 1
        try:
            raw_text, usage = self._run_turn(
                prompt, context.stop_event, context.resource_stop_report
            )
        except Exception as exc:  # noqa: BLE001 - a failed turn is unavailable
            self.last_error = f"reviewer turn raised {type(exc).__name__}: {exc}"
            self.last_usage = {"unknown": ["usage"]}
            return self._report(
                REVIEW_UNAVAILABLE, candidate.candidate_ref, reason=self.last_error
            )
        self.last_usage = usage or {"unknown": ["usage"]}
        parsed = _parse_review_json(raw_text or "")
        if parsed is None:
            self.last_error = "reviewer reply was not a single JSON object"
            return self._report(
                REVIEW_UNAVAILABLE, candidate.candidate_ref, reason=self.last_error
            )
        outcome = str(parsed.get("outcome", "")).strip().lower()
        if outcome not in {REVIEW_PASSED, REVIEW_REWORK, REVIEW_UNAVAILABLE}:
            self.last_error = f"reviewer returned an unknown outcome {outcome!r}"
            return self._report(
                REVIEW_UNAVAILABLE, candidate.candidate_ref, reason=self.last_error
            )
        findings_raw = parsed.get("findings")
        findings: tuple[Finding, ...] = ()
        if isinstance(findings_raw, list):
            findings = tuple(
                Finding.from_dict(item)
                for item in findings_raw
                if isinstance(item, dict)
            )
        return self._report(
            outcome,
            candidate.candidate_ref,
            findings=findings,
            reason=str(parsed.get("reason", "")),
        )

    def _report(
        self,
        outcome: str,
        candidate_ref: str,
        *,
        findings: tuple[Finding, ...] = (),
        reason: str = "",
    ) -> ReviewReport:
        """Build a report stamped with the real reviewer identity + usage.

        Stamping happens here (not just in the orchestrator) so a directly
        called reviewer still reports its kind/calls/usage honestly.
        """

        return ReviewReport(
            outcome=outcome,
            candidate_ref=candidate_ref,
            findings=findings,
            reviewer=self.name,
            reason=reason,
            reviewer_kind=self.kind,
            model_calls=self.model_calls,
            usage=dict(self.last_usage),
        )

    def _run_turn(
        self,
        prompt: str,
        stop_event: Any | None = None,
        resource_stop_report: dict[str, Any] | None = None,
    ) -> tuple[str | None, dict[str, Any]]:
        if self._turn is not None:
            return self._turn(prompt)
        return run_review_turn(
            self._support,
            self._resolve,
            prompt,
            timeout_seconds=self._timeout,
            max_model_calls=self._max_calls,
            stop_event=stop_event,
            resource_stop_report=resource_stop_report,
        )


def _run_coro_sync(coro: Any) -> Any:
    """Run ``coro`` synchronously, safe inside a running event loop.

    D1 (LG-022 QA): the real coordinator calls the (synchronous) reviewer from
    inside its running asyncio loop.  ``asyncio.run`` there raises
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``,
    which made every real review ``unavailable``.  Mirror the existing
    :func:`lightgravity.coordinator.dialogue.make_sync_responder` seam: when a
    loop is already running on this thread, run the coroutine on a *private*
    loop in a worker thread instead of reusing or nesting the caller's loop.

    The synchronous entry point is kept so existing sync fixtures/probes keep
    working; the real coordinator now drives the turn off its own loop.
    """

    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running on this thread: the original behaviour is fine.
        return asyncio.run(coro)

    def runner() -> Any:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001 - loop teardown is best effort
                pass
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(runner).result()


async def _await_with_stop(chat: Any, stop_event: Any | None) -> Any:
    """Await ``chat`` but abort promptly when a cooperative stop is requested.

    The stop event is a :class:`threading.Event` polled from the async loop via
    small sleeps.  When it fires we cancel the outstanding chat and raise
    :class:`~lightgravity.verify.review_lifecycle.ReviewStopped` so the lifecycle
    reports an honest stop instead of a fabricated outcome.  ``None`` means no
    stop channel (sync fixture path): behave like a plain await.
    """

    if stop_event is None:
        return await chat
    while True:
        if stop_event.is_set():
            chat.cancel()
            try:
                await chat
            except BaseException:  # noqa: BLE001 - cancellation is the point
                pass
            from .review_lifecycle import ReviewStopped

            raise ReviewStopped("", "")
        try:
            return await asyncio.wait_for(asyncio.shield(chat), timeout=0.1)
        except asyncio.TimeoutError:
            continue


def run_review_turn(
    support: ReviewerSupport,
    credential_resolver: Callable[[str], Any],
    prompt: str,
    *,
    timeout_seconds: float = DEFAULT_REVIEW_TIMEOUT_SECONDS,
    max_model_calls: int = DEFAULT_REVIEW_MODEL_CALLS,
    stop_event: Any | None = None,
    resource_stop_report: dict[str, Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """One real, tool-less SDK turn on the reviewer connection.

    Reuses the pinned SDK (``LocalOpenAIAgentConfig`` + loopback auth proxy)
    already used by the executor/dialogue; no second SDK and no second secret
    path are introduced.  Returns ``(text, usage)``; raises only on a setup
    error so the caller can classify it as ``unavailable``.  The credential value
    is never logged or serialized.

    safe to call from inside the coordinator's running event loop (D1 fix):
    the turn runs on a private loop in a worker thread (see
    :func:`_run_coro_sync`) rather than nesting ``asyncio.run`` in the caller's
    loop.
    """

    import asyncio

    import google.antigravity as ag
    from google.antigravity import Agent
    from google.antigravity import types

    from ..adapter.proxy import LocalAuthProxy, upstream_chat_completions

    credential = credential_resolver(support.credential_ref)
    if credential is None:
        return None, {"unknown": ["usage"]}

    proxy = LocalAuthProxy(
        credential=credential,
        upstream_url=upstream_chat_completions(support.base_url),
        max_calls=max_model_calls,
    )
    agent = None
    try:
        proxy.start()
        capabilities = types.CapabilitiesConfig(enabled_tools=[], enable_subagents=False)
        config = ag.LocalOpenAIAgentConfig(
            base_url=proxy.base_url,
            model=support.model,
            system_instructions=_REVIEW_SYSTEM_INSTRUCTIONS,
            capabilities=capabilities,
            workspaces=None,
        )

        async def _turn() -> tuple[str, dict[str, Any]]:
            nonlocal agent
            agent = Agent(config)
            await agent.__aenter__()
            chat = asyncio.ensure_future(
                asyncio.wait_for(agent.chat(prompt), timeout=timeout_seconds)
            )
            response = await _await_with_stop(chat, stop_event)
            chunks = []
            async for chunk in response.chunks:
                chunks.append(chunk)
            text = "".join(
                chunk.text for chunk in chunks if isinstance(chunk, types.Text)
            ).strip()
            usage = _usage_from_response(response)
            return text, usage

        return _run_coro_sync(_turn())
    finally:
        # LG-022 R2: record the *real* reviewer resource teardown so the
        # coordinator can prove the reviewer stopped, not only the worker.  A
        # failed agent close or proxy stop is reported honestly (never assumed).
        agent_closed = True
        proxy_stopped = True
        problems: list[str] = []
        if agent is not None:
            try:
                _run_coro_sync(agent.__aexit__(None, None, None))
            except Exception as exc:  # noqa: BLE001 - teardown failure reported
                agent_closed = False
                problems.append(f"reviewer agent close failed: {type(exc).__name__}")
        try:
            proxy_stopped = bool(proxy.stop())
        except Exception as exc:  # noqa: BLE001 - stop confirmation is best effort
            proxy_stopped = False
            problems.append(f"reviewer proxy stop failed: {type(exc).__name__}")
        if resource_stop_report is not None:
            resource_stop_report.clear()
            resource_stop_report.update(
                {
                    "agent_closed": agent_closed,
                    "proxy_stopped": proxy_stopped,
                    "confirmed": agent_closed and proxy_stopped,
                    "problems": problems,
                }
            )


def _usage_from_response(response: Any) -> dict[str, Any]:
    """Extract real usage counters; unknown counters are listed, never zeroed."""

    usage_obj = getattr(response, "usage", None)
    if usage_obj is None:
        return {"unknown": ["usage"]}
    mapping = usage_obj.to_dict() if hasattr(usage_obj, "to_dict") else None
    if not isinstance(mapping, dict):
        fields = {
            key: getattr(usage_obj, key, None)
            for key in ("prompt_tokens", "candidates_tokens", "total_tokens")
        }
        mapping = {k: v for k, v in fields.items() if v is not None}
    unknown = [key for key, value in mapping.items() if value is None]
    result = {key: value for key, value in mapping.items() if value is not None}
    if unknown:
        result["unknown"] = unknown
    return result or {"unknown": ["usage"]}


__all__ = [
    "DEFAULT_REVIEW_MODEL_CALLS",
    "DEFAULT_REVIEW_TIMEOUT_SECONDS",
    "Finding",
    "ModelReviewer",
    "ProgramReviewer",
    "REVIEW_PASSED",
    "REVIEW_REWORK",
    "REVIEW_UNAVAILABLE",
    "ReviewContext",
    "ReviewReport",
    "Reviewer",
    "ReviewerSupport",
    "SEV_ADVISORY",
    "SEV_BLOCKING",
    "UnavailableReviewer",
    "declared_path_refs",
    "resolve_candidate_evidence",
    "validate_findings",
]
