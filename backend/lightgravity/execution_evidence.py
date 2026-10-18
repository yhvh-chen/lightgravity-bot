"""Truthful per-Run execution evidence for Board/history readers (LG-243).

The Board must show which worker and reviewer connections actually took part in a
Run, plus the independent review verdict/findings and the exact candidate they
were bound to.  Current Settings defaults are *not* evidence: a later default or
title edit must never rewrite what an old Run used.

This module is the single allowlist boundary:

* writers build snapshots here (``worker_connection_snapshot``,
  ``reviewer_connection_snapshot``, ``review_snapshot``);
* readers re-sanitize whatever persisted JSON they find before returning it, so
  an unknown/legacy extra key can never leak through an API projection.

Only non-secret, display-safe metadata is kept: connection id, display name,
provider/backend, model, a capture timestamp and an honest status/reason.  Raw
``connection_pin`` fields (``credential_ref``, ``credential_version``,
``base_url``, ``config_hash``) are deliberately excluded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

#: Version of the additive ``Run.execution_evidence`` schema.
EXECUTION_EVIDENCE_SCHEMA = "lightgravity.execution-evidence/v1"

STATUS_RECORDED = "recorded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNKNOWN = "unknown"
_CONNECTION_STATUSES = frozenset({STATUS_RECORDED, STATUS_UNAVAILABLE, STATUS_UNKNOWN})

SOURCE_RUN_DEFAULT_PIN = "run_default_pin"
SOURCE_RUN_CONNECTION_PIN = "run_connection_pin"
SOURCE_RESOLVED_REVIEWER = "resolved_reviewer_support"
SOURCE_MISSING = "missing"

STAGE_PLANNED = "planned"
STAGE_REVIEW = "review_execution"
STAGE_UNKNOWN = "unknown"

KIND_FROZEN_WORKER = "frozen_run_connection"
KIND_REVIEWER_SUPPORT = "resolved_reviewer_support"
KIND_MISSING = "missing"

_ROLE_WORKER = "worker"
_ROLE_REVIEWER = "reviewer"

#: Finding fields that are safe to show (already program-validated evidence refs).
_FINDING_FIELDS = (
    "finding_id",
    "severity",
    "summary",
    "evidence_ref",
    "rework_target",
    "candidate_ref",
    "detail",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _timestamp(value: Any) -> str | None:
    return _text(value) or _now_iso()


def _status(value: Any, default: str = STATUS_UNKNOWN) -> str:
    return value if isinstance(value, str) and value in _CONNECTION_STATUSES else default


def connection_snapshot(
    *,
    role: str,
    connection_id: Any = None,
    name: Any = None,
    provider: Any = None,
    model: Any = None,
    status: str = STATUS_RECORDED,
    source: str = SOURCE_MISSING,
    stage: str = STAGE_UNKNOWN,
    evidence_kind: str = KIND_MISSING,
    reason: Any = None,
    captured_at: Any = None,
) -> dict[str, Any]:
    """Build one strict-allowlist connection snapshot.

    ``stage``/``evidence_kind`` keep the truth explicit: the worker entry is a
    planned/frozen connection, while the reviewer entry describes the actual
    review configuration.  Neither status implies a successful model call.
    """

    return {
        "role": role,
        "connection_id": _text(connection_id),
        "name": _text(name),
        "provider": _text(provider),
        "model": _text(model),
        "status": _status(status),
        "source": source if isinstance(source, str) and source else SOURCE_MISSING,
        "stage": stage if isinstance(stage, str) and stage else STAGE_UNKNOWN,
        "evidence_kind": (
            evidence_kind if isinstance(evidence_kind, str) and evidence_kind else KIND_MISSING
        ),
        "captured_at": (
            _text(captured_at) if status == STATUS_UNKNOWN else _timestamp(captured_at)
        ),
        "reason": _text(reason),
    }


def unknown_connection_snapshot(
    role: str,
    *,
    reason: str = "execution history is not recorded",
    source: str = SOURCE_MISSING,
    stage: str = STAGE_UNKNOWN,
    evidence_kind: str = KIND_MISSING,
) -> dict[str, Any]:
    return connection_snapshot(
        role=role,
        status=STATUS_UNKNOWN,
        source=source,
        stage=stage,
        evidence_kind=evidence_kind,
        reason=reason,
        captured_at=None,
    )


def worker_connection_snapshot(
    pin: Any,
    *,
    name: str | None = None,
    captured_at: Any = None,
    source: str = SOURCE_RUN_DEFAULT_PIN,
) -> dict[str, Any]:
    """Snapshot the worker connection resolved and frozen for this Run.

    A missing pin is honest ``unknown`` (an explicit agent connection may still
    have run); it never falls back to the current default.
    """

    if pin is None:
        return unknown_connection_snapshot(
            _ROLE_WORKER,
            reason="no worker default connection was pinned for this run",
            stage=STAGE_PLANNED,
        )
    try:
        connection_id = getattr(pin, "connection_id", None)
        provider = getattr(pin, "backend", None)
        model = getattr(pin, "model", None)
    except Exception:  # noqa: BLE001 - a bad pin is an unknown fact, not a crash
        connection_id = provider = model = None
    if not _text(connection_id):
        return unknown_connection_snapshot(
            _ROLE_WORKER,
            reason="worker connection pin has no connection id",
            stage=STAGE_PLANNED,
        )
    return connection_snapshot(
        role=_ROLE_WORKER,
        connection_id=connection_id,
        name=name,
        provider=provider,
        model=model,
        status=STATUS_RECORDED,
        source=source,
        stage=STAGE_PLANNED,
        evidence_kind=KIND_FROZEN_WORKER,
        captured_at=captured_at,
    )


def reviewer_connection_snapshot(
    support: Any,
    *,
    name: str | None = None,
    status: str = STATUS_RECORDED,
    reason: str | None = None,
    captured_at: Any = None,
    source: str = SOURCE_RESOLVED_REVIEWER,
) -> dict[str, Any]:
    """Snapshot the *resolved* reviewer support that actually ran (or failed)."""

    if support is None:
        return connection_snapshot(
            role=_ROLE_REVIEWER,
            status=STATUS_UNAVAILABLE if status == STATUS_UNAVAILABLE else STATUS_UNKNOWN,
            source=source,
            stage=STAGE_REVIEW,
            evidence_kind=KIND_MISSING,
            reason=reason or "no reviewer connection was resolved",
            captured_at=None,
        )
    try:
        connection_id = getattr(support, "connection_id", None)
        provider = getattr(support, "backend", None)
        model = getattr(support, "model", None)
        support_name = name if name is not None else getattr(support, "name", None)
        support_role = getattr(support, "role", None) or _ROLE_REVIEWER
    except Exception:  # noqa: BLE001
        connection_id = provider = model = support_name = None
        support_role = _ROLE_REVIEWER
    if not _text(connection_id):
        # A runtime-only legacy support had no connection id; never invent one.
        return connection_snapshot(
            role=support_role if isinstance(support_role, str) else _ROLE_REVIEWER,
            name=support_name,
            provider=provider,
            model=model,
            status=STATUS_UNKNOWN,
            source=source,
            stage=STAGE_REVIEW,
            evidence_kind=KIND_REVIEWER_SUPPORT,
            reason=reason or "resolved reviewer support did not expose a connection id",
            captured_at=captured_at,
        )
    return connection_snapshot(
        role=support_role if isinstance(support_role, str) else _ROLE_REVIEWER,
        connection_id=connection_id,
        name=support_name,
        provider=provider,
        model=model,
        status=status,
        source=source,
        stage=STAGE_REVIEW,
        evidence_kind=KIND_REVIEWER_SUPPORT,
        reason=reason,
        captured_at=captured_at,
    )


def _findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        finding = {field: _text(item.get(field)) for field in _FINDING_FIELDS}
        out.append(finding)
    return out


def _binding(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "run_id": _text(value.get("run_id")),
        "candidate_ref": _text(value.get("candidate_ref")),
        "requirements_revision": _int_or_none(value.get("requirements_revision")),
        "plan_hash": _text(value.get("plan_hash")),
    }


#: Known non-secret usage counter keys; vendor-specific ``*_tokens`` counters are
#: also accepted.  Anything else is not part of the execution allowlist.
_USAGE_KEYS = frozenset(
    {
        "unknown",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "candidates_tokens",
        "cached_tokens",
        "reasoning_tokens",
    }
)


def _usage(value: Any) -> dict[str, Any]:
    """Keep only primitive usage counters; unknown is preserved, never zeroed."""

    if not isinstance(value, dict):
        return {"unknown": ["usage"]}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if key not in _USAGE_KEYS and not key.endswith("_tokens"):
            continue
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, (int, float, str)):
            out[key] = item
        elif isinstance(item, list) and all(isinstance(x, str) for x in item):
            out[key] = list(item)
    return out or {"unknown": ["usage"]}


def review_snapshot(report: Any, candidate: Any, *, reviewed_at: Any = None) -> dict[str, Any]:
    """Build the persisted verdict/findings/binding snapshot for one review."""

    findings = [_safe_finding(f.to_dict()) for f in getattr(report, "findings", ()) or ()]
    unsubstantiated = [
        str(item) for item in (getattr(report, "unsubstantiated", ()) or ()) if str(item)
    ]
    return {
        "outcome": str(getattr(report, "outcome", "") or ""),
        "reviewer_kind": _text(getattr(report, "reviewer_kind", None)),
        "candidate_ref": _text(getattr(report, "candidate_ref", None)),
        "candidate_binding": {
            "run_id": _text(getattr(candidate, "run_id", None)),
            "candidate_ref": _text(getattr(candidate, "candidate_ref", None)),
            "requirements_revision": _int_or_none(
                getattr(candidate, "requirements_revision", None)
            ),
            "plan_hash": _text(getattr(candidate, "plan_hash", None)),
        },
        "findings": findings,
        "unsubstantiated": unsubstantiated,
        "model_calls": _int_or_none(getattr(report, "model_calls", None)) or 0,
        "usage": _usage(getattr(report, "usage", None)),
        "reviewed_at": _timestamp(reviewed_at),
        "reason": _text(getattr(report, "reason", None)) or "",
    }


def _safe_finding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {field: None for field in _FINDING_FIELDS}
    return {field: _text(value.get(field)) for field in _FINDING_FIELDS}


def _sanitize_connection(value: Any, role: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "role": _text(value.get("role")) or role,
        "connection_id": _text(value.get("connection_id")),
        "name": _text(value.get("name")),
        "provider": _text(value.get("provider")),
        "model": _text(value.get("model")),
        "status": _status(value.get("status")),
        "source": _text(value.get("source")) or SOURCE_MISSING,
        "stage": _text(value.get("stage")) or STAGE_UNKNOWN,
        "evidence_kind": _text(value.get("evidence_kind")) or KIND_MISSING,
        "captured_at": _text(value.get("captured_at")),
        "reason": _text(value.get("reason")),
    }


def _sanitize_review(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "outcome": _text(value.get("outcome")) or "",
        "reviewer_kind": _text(value.get("reviewer_kind")),
        "candidate_ref": _text(value.get("candidate_ref")),
        "candidate_binding": _binding(value.get("candidate_binding")),
        "findings": _findings(value.get("findings")),
        "unsubstantiated": [
            str(item) for item in value.get("unsubstantiated", []) if isinstance(item, str)
        ]
        if isinstance(value.get("unsubstantiated"), list)
        else [],
        "model_calls": _int_or_none(value.get("model_calls")) or 0,
        "usage": _usage(value.get("usage")),
        "reviewed_at": _text(value.get("reviewed_at")),
        "reason": _text(value.get("reason")) or "",
    }


def merge_execution_evidence(
    existing: Any,
    *,
    worker: Any = None,
    reviewer: Any = None,
    review: Any = None,
) -> dict[str, Any]:
    """Merge new facts into an existing evidence map without dropping history."""

    base = existing if isinstance(existing, dict) else {}
    evidence: dict[str, Any] = {"schema": EXECUTION_EVIDENCE_SCHEMA}
    if worker is not None:
        evidence["worker"] = worker
    elif isinstance(base.get("worker"), dict):
        evidence["worker"] = base["worker"]
    if reviewer is not None:
        evidence["reviewer"] = reviewer
    elif isinstance(base.get("reviewer"), dict):
        evidence["reviewer"] = base["reviewer"]
    if review is not None:
        evidence["review"] = review
    elif isinstance(base.get("review"), dict):
        evidence["review"] = base["review"]
    return evidence


def _worker_from_run(run: dict[str, Any]) -> dict[str, Any]:
    evidence = run.get("execution_evidence")
    stored = _sanitize_connection(
        evidence.get("worker") if isinstance(evidence, dict) else None, _ROLE_WORKER
    )
    if stored is not None:
        return stored
    # Legacy fallback: the frozen Run pin is real historical fact.  It is
    # re-projected through the allowlist; no current Settings default is read.
    pin = run.get("connection_pin")
    if isinstance(pin, dict) and _text(pin.get("connection_id")):
        return connection_snapshot(
            role=_ROLE_WORKER,
            connection_id=pin.get("connection_id"),
            name=None,
            provider=pin.get("backend"),
            model=pin.get("model"),
            status=STATUS_RECORDED,
            source=SOURCE_RUN_CONNECTION_PIN,
            stage=STAGE_PLANNED,
            evidence_kind=KIND_FROZEN_WORKER,
            captured_at=None,
        )
    return unknown_connection_snapshot(
        _ROLE_WORKER,
        reason="run has no worker connection history",
        stage=STAGE_PLANNED,
    )


def build_execution_view(task_id: str, run: Any = None) -> dict[str, Any]:
    """Project one Run's evidence for authorized Task readers.

    The projection is rebuilt from an allowlist; unknown legacy keys in the
    persisted map are never returned.  Nothing is inferred from current defaults.
    """

    if not isinstance(run, dict):
        return {
            "task_id": task_id,
            "schema": EXECUTION_EVIDENCE_SCHEMA,
            "run": None,
            "worker": unknown_connection_snapshot(
                _ROLE_WORKER, reason="task has no recorded run", stage=STAGE_PLANNED
            ),
            "reviewer": unknown_connection_snapshot(
                _ROLE_REVIEWER, reason="task has no recorded review history"
            ),
            "review": None,
            "connections_distinct": None,
            "missing": ["run", "worker_history", "reviewer_history", "review"],
        }

    evidence = run.get("execution_evidence")
    evidence_map = evidence if isinstance(evidence, dict) else {}
    worker = _worker_from_run(run)
    reviewer = _sanitize_connection(evidence_map.get("reviewer"), _ROLE_REVIEWER)
    if reviewer is None:
        reviewer = unknown_connection_snapshot(
            _ROLE_REVIEWER, reason="no reviewer execution history recorded for this run"
        )
    review = _sanitize_review(evidence_map.get("review"))

    missing: list[str] = []
    if worker.get("status") == STATUS_UNKNOWN:
        missing.append("worker_history")
    if reviewer.get("status") == STATUS_UNKNOWN:
        missing.append("reviewer_history")
    if review is None:
        missing.append("review")

    worker_id = worker.get("connection_id")
    reviewer_id = reviewer.get("connection_id")
    connections_distinct = (
        worker_id != reviewer_id if isinstance(worker_id, str) and isinstance(reviewer_id, str)
        else None
    )

    binding = review.get("candidate_binding") if isinstance(review, dict) else None
    requirements_revision = _int_or_none((binding or {}).get("requirements_revision"))
    plan_hash = _text((binding or {}).get("plan_hash")) or _text(run.get("plan_hash"))
    run_view = {
        "id": _text(run.get("id")) or _text(run.get("entity_id")),
        "state": _text(run.get("state")),
        "candidate_ref": _text(run.get("id")) or _text(run.get("entity_id")),
        "requirements_revision": requirements_revision,
        "plan_hash": plan_hash,
    }
    return {
        "task_id": task_id,
        "schema": EXECUTION_EVIDENCE_SCHEMA,
        "run": run_view,
        "worker": worker,
        "reviewer": reviewer,
        "review": review,
        "connections_distinct": connections_distinct,
        "missing": missing,
    }


__all__ = [
    "EXECUTION_EVIDENCE_SCHEMA",
    "KIND_FROZEN_WORKER",
    "KIND_MISSING",
    "KIND_REVIEWER_SUPPORT",
    "STAGE_PLANNED",
    "STAGE_REVIEW",
    "STATUS_RECORDED",
    "STATUS_UNAVAILABLE",
    "STATUS_UNKNOWN",
    "build_execution_view",
    "connection_snapshot",
    "merge_execution_evidence",
    "review_snapshot",
    "reviewer_connection_snapshot",
    "unknown_connection_snapshot",
    "worker_connection_snapshot",
]
