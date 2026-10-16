"""Contract constants, enums, error mapping and envelope tests (LG-002)."""

from __future__ import annotations

from lightgravity.contracts import (
    API_PREFIX,
    CONTRACT_VERSION,
    ERROR_HTTP_STATUS,
    ERROR_RETRYABLE,
    SCHEMA_NAMESPACE,
    AppError,
    ErrorCode,
    HealthResponse,
    RunState,
    TaskPhase,
    TaskStatus,
    error_envelope,
)


def test_frozen_constants() -> None:
    # docs/08 §13: 1.9.0 (serial integration additive: reversible ``archived``
    # source flag + ``archive``/``unarchive`` actions and the mounted optional
    # vector endpoints) -> 1.10.0 (LG-022 R2 targeted refix additive: stop gate
    # confirms real session/reviewer resource stops; generation diagnostics gain
    # a ``persistent``/``corrupt`` durability flag) -> 1.11.0 (LG-031 runtime
    # integration additive: the four decentralized endpoints' request-body
    # ``owner`` relaxed from required to optional/compat-only + additive internal
    # ``ExecutionGrant.lease_owner``) -> 1.12.0 (LG-043 selected-material
    # implementation: additive optional message ``selected_sources`` +
    # reply/Run data ``resolved_source_bindings``/``context_truncated``/
    # ``provided_context_note``) -> 1.13.0 (LG-050 shared team mode
    # implementation: additive team-mode switch, ``/auth/me|login|logout``,
    # server-written message ``author`` and the ``forbidden`` error code) ->
    # 1.14.0 (LG-054 private Personal conversation implementation: additive
    # ``/conversations/personal/messages`` GET/POST with server-derived owner,
    # the ``personal_chat`` health capability and chat-only private routing).
    # Additive MINOR only.
    assert CONTRACT_VERSION == "1.14.0"
    assert SCHEMA_NAMESPACE == "lightgravity.bot/v1"
    assert API_PREFIX == "/api/v1"


def test_task_status_keeps_contract_spelling() -> None:
    assert TaskStatus.IN_PROGRESS.value == "in-progress"
    assert {s.value for s in TaskStatus} == {"todo", "in-progress", "done"}


def test_phase_and_run_enums_use_snake_case() -> None:
    assert TaskPhase.WAITING_DEPENDENCIES.value == "waiting_dependencies"
    assert TaskPhase.AWAITING_ACCEPTANCE.value == "awaiting_acceptance"
    assert RunState.AWAITING_ACCEPTANCE.value == "awaiting_acceptance"


def test_every_error_code_has_http_and_retry_mapping() -> None:
    codes = set(ErrorCode)
    assert set(ERROR_HTTP_STATUS) == codes
    assert set(ERROR_RETRYABLE) == codes


def test_error_envelope_default_retryability() -> None:
    retryable = error_envelope(ErrorCode.LOCK_CONFLICT, "busy")
    assert retryable.error.retryable is True
    assert retryable.error.code is ErrorCode.LOCK_CONFLICT

    final = error_envelope(ErrorCode.REVISION_CONFLICT, "stale")
    assert final.error.retryable is False


def test_app_error_maps_to_http_status_and_envelope() -> None:
    error = AppError(ErrorCode.NOT_FOUND, "missing task")
    assert error.http_status == 404
    assert error.to_envelope().error.code is ErrorCode.NOT_FOUND


def test_health_response_serializes_contract_versions() -> None:
    health = HealthResponse(
        package_version="0.1.0",
        contract_version=CONTRACT_VERSION,
        schema_version=SCHEMA_NAMESPACE,
    )
    assert health.status == "ok"
    assert health.model_dump()["schema_version"] == "lightgravity.bot/v1"
