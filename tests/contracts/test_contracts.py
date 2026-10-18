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
    # the ``personal_chat`` health capability and chat-only private routing) ->
    # 1.15.0 (LG-062 account management: additive team-only ``/accounts*`` and
    # ``/account/password`` endpoints, additive account ``enabled``/``revision``/
    # ``session_version`` fields, session invalidation, last-active-admin guard
    # and the ``accounts`` health capability) -> 1.16.0 (LG-066 global/Team
    # Task-ID status query: additive ``query``/``clarify`` response kinds and a
    # read-only ``data`` snapshot on the existing global-messages endpoint;
    # explicit legal Task ID only, no guess, no Task/Run/worker/model side
    # effect) -> 1.17.0 (LG-104/LG-109 provider modal backend: additive
    # Connection auth/provider fields, capability facts, draft test endpoint,
    # additive TestResult draft/nullable identity, saved last_test summary and
    # the revision/reference-gated DELETE endpoint; no native task execution)
    # -> 1.18.0 (LG-122 additive MINOR implemented in the isolated complete
    # candidate: read-only Team groups projection, Personal private attachments
    # with bounded model context, independent Embedding settings, goal-fit team
    # provenance and bounded multi-Task capacity/waiting reasons) -> 1.19.0
    # (LG-144 integrated LG-139 material intake v2 candidate: deferred worker,
    # receipt v2 branches, message source_refs, automatic configured media
    # embedding and protected full rebuild) -> 1.20.0 (LG-162 isolated assembly
    # of optional default-off shared-English-audio EG2 Reader transcription:
    # protected english_asr settings view/PUT, processing-availability health
    # capability, additive source/receipt/content provenance and bounded intake
    # branch; raw LG-159 quality gate remains FAIL) -> 1.21.0 (LG-206 integrated
    # Tasks-workspace candidate: read-only Team conversation history projection
    # and additive SourceView context availability fields; independent LG-207 QA
    # still pending) -> 1.22.0 (LG-238 serial assembly of the LG-236 Google
    # native backend + LG-237 provider-aware UI: additive google-native provider
    # discriminator, protected english_asr settings view/PUT with a write-only
    # managed credential, native inline-audio REST transcription without
    # torch/numpy/Reader/SDK, and additive machine provenance; legacy 1.20
    # blocks keep their behavior, the old Reader quality gate stays FAILED and
    # independent LG-239 version/browser QA is still pending) -> 1.23.0 (LG-251
    # local demo-recording integration candidate: read-only canonical TASK.md
    # definition, default-delivery machine-check policy/binding/acceptance facts,
    # allowlisted Run execution evidence + task-scoped history endpoint,
    # text-layer-first PDF extraction and Team Task configured-mention routing +
    # health.team_bot_mention; isolated local candidate, not deployed, LG-252
    # independent browser/recording QA pending) -> 1.24.0 (follow-up batch
    # serial integration: LG-210 hash-only durable team sessions, LG-217 honest
    # unavailable assistant replies without false provided-context, and LG-256
    # authoritative explicit receipt branches; no new endpoint/field/enum) ->
    # 1.25.0 (material follow-up integration: LG-222 type-routed reprocess with
    # additive source.reprocess/formal.origin/preserved_existing_body, audio as
    # one bounded deferred ASR job, 503/409 pre-write guards, preserved
    # body/index on failure; LG-223 first human formal body; no new endpoint,
    # request field, error code or enum) -> 1.26.0 (final native-defect
    # integration: LG-265 optional runtime_applied/runtime_message on settings
    # saves with immediate coordinator/reviewer default wiring, LG-263 legal
    # waiting_user -> recovery_required parking plus recovery_transition_failed
    # diagnostics and stricter stop confirmation, LG-264 frontend Recruited
    # details, LG-267 structured-extraction body usability that keeps failed
    # artifacts previewable but not selectable; no new endpoint/error code/entity
    # enum value).
    assert CONTRACT_VERSION == "1.26.0"
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
