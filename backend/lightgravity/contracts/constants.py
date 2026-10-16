"""Frozen contract constants (docs/08-interface-contract.md §2, §4)."""

from __future__ import annotations

SCHEMA_NAMESPACE = "lightgravity.bot/v1"
#: docs/08 §13: 1.13.0 (2026-10-16) is the additive MINOR bump for LG-050's
#: shared-team-mode implementation (interface frozen in ``1.13.0`` by the PM):
#: an explicitly-enabled team mode (default off, single-user unchanged), the
#: ``/api/v1/auth/me|login|logout`` session endpoints, the server-written
#: additive optional message ``author`` field, the ``forbidden`` (403) error
#: code, and the read-only ``GET /auth/me`` single/team discriminator.  No
#: existing endpoint, enum or migration direction changes; anonymous access to
#: business APIs is default-deny in team mode and the legacy ``X-LG-Token``
#: never contributes team identity.
#:
#: docs/08 §13: 1.12.0 (2026-10-16) is the additive MINOR bump for LG-043's
#: selected-material implementation (frozen in ``1.12.0`` reserved by LG-042):
#: the message envelope gains the additive optional ``selected_sources`` field
#: (≤3 refs ``{source_id, source_version?, content_hash?}``) and reply/Run data
#: gains the additive ``resolved_source_bindings`` / ``context_truncated`` /
#: ``provided_context_note`` fields (docs/08 §6.6.1, docs/10).  Total bounded at
#: 12000 Unicode chars with explicit truncation metadata, formal-first with a
#: machine fallback, and stale/revoked/missing/cross-Task refs are rejected
#: before any product model dispatch.  No new endpoints, error codes, enums or
#: migration directions; legacy clients that omit the field are byte-for-byte
#: unchanged.
#:
#: docs/08 §13: 1.11.0 (2026-10-16) is the conservative additive MINOR bump
#: registering the LG-031 runtime/API/SDK integration's actual public-compat
#: changes (R1 observation O3), replacing the earlier "implementation-note,
#: no version change" wording kept at 1.10.0.  Two public-compat changes:
#: (a) the request-body ``owner`` on the four decentralized endpoints
#: (``GET /runs/{run_id}/discoverable``, ``POST /runs/{run_id}/claim_requests``,
#: ``POST /subtasks/{subtask_id}/lease/renew``,
#: ``POST /subtasks/{subtask_id}/lease/release``) is relaxed from
#: required/endpoint-adopted (``1.6.0`` freeze) to optional/compat-check-only
#: and no longer carries authorization; (b) ``ExecutionGrant`` gains the
#: additive in-process non-persistent field ``lease_owner`` (program-frozen
#: lease authority, ``effective_lease_owner = lease_owner or member_ref``).
#: Both are backward-compatible: an old client may still send ``owner`` (now
#: only consistency-checked, not authorized) or omit it; no
#: endpoint/enum/error-code/entity-schema/transition changes, and the
#: unauthenticated/default-deny/no-persist boundary is unchanged.
#:
#: docs/08 §13: 1.10.0 (2026-10-16) is the LG-022 second targeted-refix additive MINOR: the
#: stop gate may confirm a Run's real session/reviewer stop from authoritative
#: adapter facts (``run.cleanup``/``run.reviewer_cleanup`` stop-confirmation)
#: instead of requiring a fabricated ``cleanup=done``, and
#: ``GET /api/v1/diagnostics/generation`` gains additive ``persistent``
#: (and, on a persistent ledger, ``corrupt``/``reason``) fields -- the global
#: generation counter is now a durable ledger under the controlled data root.
#: No new endpoints, enums, transitions or error codes; no secret is exposed.
#:
#: docs/08 §13: 1.9.0 (2026-10-16) is an additive MINOR bump from the serial
#: integration after the first-version repair: the reversible organizational
#: ``archived`` source flag + ``archive``/``unarchive`` actions (§4.3, §6.6;
#: archive keeps retrieval/opening/permissions, unlike the invalidating
#: ``revoke``) and the mounted optional vector endpoints
#: ``GET /vector/status``, ``GET /vector/search``, ``POST /vector/rebuild``
#: (§4.3, §6.6; disabled by default, env-configured, candidates re-verified).
#: 1.8.0 was the LG-022
#: first-version QA D1/D2 repair R1: the legal transitions
#: ``verifying -> recovery_required`` and ``repairing -> recovery_required``
#: (§6.1, restart during independent review parks honestly for a human) and the
#: read-only ``GET /api/v1/diagnostics/generation`` endpoint reporting the
#: process-global upstream generation-request count (counted before forwarding).
#: 1.7.0 was the LG-017 repair R1 bump: the new settings role/field
#: ``default_reviewer_connection_ref`` (§6.5), the additive Task rework-ledger
#: fields ``reviewer``/``reviewer_kind``/``model_usage`` (§6.1), additive
#: review/rework event payloads ``reviewer_kind``/``model_calls``/``usage``
#: (§5.1), and the independent-review semantics (§9: no usable reviewer =>
#: ``unavailable`` and accept is blocked; a program machine gate is not
#: independent QA).  No endpoints, error codes,
#: state/phase/acceptance enums, transitions or existing field semantics change;
#: no new provider or secret form is introduced.
#:
#: docs/08 §13: 1.6.0 (2026-10-16) is the single-owner serial freeze of two
#: NOT-YET-IMPLEMENTED lines.  LG-028 (decentralized collaboration) adds the
#: additive optional Subtask ``fence`` field plus lease/fencing/expiry semantics,
#: discovery/claim/renew/release/collab endpoints, ``subtask.lease_*`` /
#: ``collab.*`` / ``handoff.*`` events, ``stale_lease``/``claim_refused`` error
#: codes, and default-off switches ``decentralized_claim_enabled`` /
#: ``collab_requests_enabled`` / ``claim_lease_seconds``.  LG-033 (source intake
#: and retrieval) adds the ``source``/``intake_job`` entities, ``sources`` /
#: ``intake`` / ``search`` / ``inbox`` endpoints, ``source.*``/``intake.*``
#: events, and ``source_conflict``/``source_stale``/``index_unavailable`` error
#: codes.  Everything is additive and optional: existing state/phase/acceptance
#: enums, transitions, endpoints and error-code semantics are unchanged, and the
#: decentralized path defaults off.  The new endpoints/entities are frozen
#: interfaces only (NOT implemented).  Full checkpoint skip remains unimplemented.
#:
#: 1.5.0 (2026-10-15) registers LG-020's additive, non-secret
#: ``connection_pin`` field on Run and Member entities.  It records the default
#: worker connection (ref + revision + content_hash + opaque
#: ``credential_version``) resolved when a Run recruits its team, so a later
#: default/credential edit cannot silently hot-swap an active member's connection;
#: drift fails the next subtask as ``config_invalid`` and a new Run re-resolves.
#: No secret is ever stored.  Existing endpoint semantics, error codes, event
#: types, enums and state transitions are unchanged.
#:
#: 1.4.0 (2026-10-15) registers LG-015's additive
#: ``PATCH /resources/{kind}/{id}`` controlled write, the ``GET /team/available``
#: and ``GET /team/members`` read endpoints, and the additive Task-message
#: ``resource_proposal`` field that routes a bounded resource change through the
#: coordinator and ``ResourceService.update``, with the actual result/conflict
#: written back as ``resource_result.status``.  Existing endpoint semantics,
#: error codes, event types, enums and state transitions are unchanged.
#:
#: 1.3.1 (2026-10-15) marks LG-014's ``POST /files/upload``/
#: ``GET /files/download`` (registered as planned in 1.3.0) as implemented and
#: states the machine-check evidence-reference semantics: workspace-relative refs
#: resolve under the authorized workspace root, executor artifacts are
#: canonicalized as ``evidence:<run_id>/<name>@sha256:<hex>`` under the Task/Run
#: evidence root, and raw absolute paths are rejected.
#:
#: 1.3.0 registered LG-009's additive Task ``checks`` authorization and
#: ``acceptance`` candidate-binding fields (``candidate_ref``/
#: ``candidate_plan_hash``/``check_records``/``note``), the read-only
#: ``GET /tasks/{task_id}/acceptance`` endpoint, LG-025's settings detail/default
#: endpoints, and the singleton global-conversation messages endpoints.
CONTRACT_VERSION = "1.13.0"
API_PREFIX = "/api/v1"

__all__ = ["SCHEMA_NAMESPACE", "CONTRACT_VERSION", "API_PREFIX"]
