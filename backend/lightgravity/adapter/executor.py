"""Real Antigravity executor + product loopback auth proxy wiring (LG-006).

This is the formal product executor, not a probe.  It:

* compiles the LG-005 permission-bounded plan and refuses to run a plan whose
  ``executable`` flag is false (config built != authenticated);
* resolves the ``credential_ref`` in memory (env / controlled store);
* starts a :class:`~lightgravity.adapter.proxy.LocalAuthProxy` on a loopback
  ephemeral port and points the SDK's ``LocalOpenAIAgentConfig.base_url`` at it
  (the SDK config has no ``api_key`` field, so injection is explicit);
* runs the SDK session, normalizes SDK chunks into adapter events and calls the
  coordinator's ``emit`` sink;
* returns a structured :class:`ExecutorResult` with artifacts, diff, checks,
  session, usage and an honest stop classification;
* confirms proxy/agent stop and never reports a cancellation it did not verify.

It never writes control state (TASK.md/RUN.md/member files); those stay with the
coordinator/``Store``.  MCP, Triggers, ``search_web`` and SDK-internal
delegation stay off because the compiled plan marks them unavailable.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from lightgravity.contracts import AppError
from lightgravity.store import Store, StoreError

from .capabilities import AdapterCapabilities, SDK_PINNED_VERSION, adapter_capabilities
from .compiler import CompileConstraints, CompiledAgentConfig, ResourceCompiler
from .credentials import CredentialResolver, EnvCredentialResolver, Secret
from .errors import AdapterConfigInvalid, CapabilityUnavailable
from .execution import (
    CancelResult,
    CheckRecord,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    FailureInfo,
    SessionRef,
    Usage,
)
from .proxy import LocalAuthProxy, upstream_chat_completions
from .redaction import mask_values, redact
from .sdk_config import build_sdk_config

#: Stop reasons that mean the run stopped because of a limit, not completion.
_BUDGET_MARKERS = (
    "MAX_MODEL_CALLS",
    "MAX_TOOL_CALLS",
    "MAX_INPUT_TOKENS",
    "MAX_OUTPUT_TOKENS",
    "MAX_TOTAL_TOKENS",
    "QUOTA_EXHAUSTED",
)

_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".venv",
    }
)
_MAX_SNAPSHOT_FILE_BYTES = 1_000_000
_MAX_SNAPSHOT_TEXT_BYTES = 256_000
_MAX_DIFF_BYTES = 400_000


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _is_within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def snapshot_tree(root: Path) -> dict[str, str | None]:
    """Snapshot changed-file detection: text content, or ``None`` if binary/large."""

    snapshot: dict[str, str | None] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in relative.parts):
            continue
        try:
            size = path.stat().st_size
            if size > _MAX_SNAPSHOT_FILE_BYTES:
                snapshot[str(relative)] = None
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:1024]:
            snapshot[str(relative)] = None
            continue
        if size > _MAX_SNAPSHOT_TEXT_BYTES:
            snapshot[str(relative)] = None
            continue
        snapshot[str(relative)] = data.decode("utf-8", "replace")
    return snapshot


def diff_snapshots(
    before: dict[str, str | None], after: dict[str, str | None]
) -> tuple[str, list[str], list[str]]:
    """Return ``(unified_diff, produced, removed)`` for two snapshots."""

    changed = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    produced = [path for path in changed if path in after]
    removed = [path for path in changed if path not in after]
    pieces: list[str] = []
    for path in changed:
        old = before.get(path)
        new = after.get(path)
        if path in before and old is None:
            pieces.append(f"Binary or large file changed: {path}\n")
            continue
        if path in after and new is None:
            pieces.append(f"Binary or large file added: {path}\n")
            continue
        old_lines = (old or "").splitlines(keepends=True)
        new_lines = (new or "").splitlines(keepends=True)
        pieces.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    text = "".join(pieces)
    if len(text) > _MAX_DIFF_BYTES:
        text = text[:_MAX_DIFF_BYTES] + "\n[diff truncated]\n"
    return text, produced, removed


def classify_outcome(
    *,
    stop_reason: str | None,
    tool_errors: int,
    has_output: bool,
    stream_error: BaseException | None,
    cancel_requested: bool,
    cancel_confirmed: bool,
    timed_out: bool,
) -> tuple[str, FailureInfo | None]:
    """Map raw turn facts to the frozen outcome classification."""

    if timed_out:
        detail = "cancel confirmed" if cancel_confirmed else "cancel NOT confirmed"
        return "timeout", FailureInfo("timeout", f"execution exceeded its time limit ({detail})")
    if cancel_requested:
        if cancel_confirmed:
            return "cancelled", FailureInfo("cancelled", "turn cancelled and stop confirmed")
        return "blocked", FailureInfo(
            "cancellation_unconfirmed",
            "cancel was requested but the conversation did not confirm stopping",
        )
    if stream_error is not None:
        return "failed", FailureInfo(
            "execution_error", f"{type(stream_error).__name__}: {stream_error}"
        )
    if stop_reason and any(marker in stop_reason for marker in _BUDGET_MARKERS):
        return "budget_exhausted", FailureInfo("budget_exhausted", stop_reason)
    if tool_errors and not has_output:
        return "failed", FailureInfo(
            "tool_failed", f"{tool_errors} tool call(s) failed and no output was produced"
        )
    return "succeeded", None


def _executable_failure_code(reasons: tuple[str, ...]) -> str:
    runtime_reasons = {"backend_unverified", "credential_unresolved"}
    if any(reason in runtime_reasons for reason in reasons):
        return "capability_unavailable"
    return "config_invalid"


def _structured_usage(metadata: Any) -> Usage:
    if metadata is None:
        return Usage(unknown=("prompt_tokens", "candidates_tokens", "total_tokens"))

    def counter(name: str) -> int | None:
        value = getattr(metadata, name, None)
        return value if isinstance(value, int) else None

    prompt = counter("prompt_token_count")
    candidates = counter("candidates_token_count")
    total = counter("total_token_count")
    thoughts = counter("thoughts_token_count")
    cached = counter("cached_content_token_count")
    unknown = tuple(
        label
        for label, value in (
            ("prompt_tokens", prompt),
            ("candidates_tokens", candidates),
            ("total_tokens", total),
        )
        if value is None
    )
    return Usage(
        prompt_tokens=prompt,
        candidates_tokens=candidates,
        total_tokens=total,
        thought_tokens=thoughts,
        cached_tokens=cached,
        unknown=unknown,
    )


@runtime_checkable
class ArtifactSink(Protocol):
    """Persist an adapter artifact and return a stable reference."""

    def write(self, name: str, content: str) -> str: ...


class DirectoryArtifactSink:
    """Write artifacts under a directory, rejecting path escape."""

    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir).resolve()

    @property
    def base_dir(self) -> Path:
        return self._base

    def write(self, name: str, content: str) -> str:
        target = (self._base / name).resolve()
        if not _is_within(target, self._base):
            raise AdapterConfigInvalid(f"artifact name {name!r} escapes the artifact root")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target.as_posix()


@dataclass
class _ExecutionHandle:
    execution: ExecutionRef
    request: ExecuteRequest
    cancel_timeout: float
    task: "asyncio.Task[Any] | None" = None
    agent: Any | None = None
    conversation: Any | None = None
    response: Any | None = None
    session_ref: SessionRef | None = None
    proxy: LocalAuthProxy | None = None
    cancel_requested: bool = False
    cancel_confirmed: bool = False
    cancel_resolved: asyncio.Event = field(default_factory=asyncio.Event)
    timed_out: bool = False
    stream_error: BaseException | None = None
    proxy_stop_confirmed: bool | None = None
    model_calls_counted: bool = False
    closed: bool = False

    def is_idle(self) -> bool:
        conversation = self.conversation
        if conversation is None:
            return True
        try:
            return bool(conversation.is_idle)
        except Exception:  # noqa: BLE001 - idle probe must never raise
            return False

    async def wait_stopped(self) -> bool:
        deadline = time.monotonic() + self.cancel_timeout
        while time.monotonic() < deadline:
            if self.is_idle():
                return True
            await asyncio.sleep(0.05)
        return self.is_idle()

    async def request_cancel(self) -> CancelResult:
        self.cancel_requested = True
        try:
            return await self._request_cancel_inner()
        finally:
            self.cancel_resolved.set()

    async def _request_cancel_inner(self) -> CancelResult:
        response = self.response
        if response is None:
            return CancelResult(
                confirmed=False, state="requested", reason="no active turn to cancel"
            )
        try:
            await response.cancel()
        except Exception as exc:  # noqa: BLE001 - report failure, do not fake stop
            return CancelResult(
                confirmed=False,
                state="unconfirmed",
                reason=f"cancel call failed: {type(exc).__name__}",
            )
        confirmed = await self.wait_stopped()
        self.cancel_confirmed = confirmed
        if confirmed:
            return CancelResult(
                confirmed=True, state="cancelled", reason="conversation idle after cancel"
            )
        return CancelResult(
            confirmed=False,
            state="unconfirmed",
            reason="conversation did not become idle within the cancel timeout",
        )

    async def ensure_closed(self) -> bool:
        if self.closed:
            return True
        self.closed = True
        agent = self.agent
        if agent is None:
            return True
        try:
            await agent.__aexit__(None, None, None)
            return True
        except Exception:  # noqa: BLE001 - close is best-effort but reported
            return False


class AntigravityExecutor:
    """docs/08 §8 executor for the first-version OpenAI-compatible backend."""

    name = "antigravity"
    version = SDK_PINNED_VERSION

    def __init__(
        self,
        store: Store,
        compiler: ResourceCompiler | None = None,
        *,
        credential_resolver: CredentialResolver | None = None,
        artifacts: ArtifactSink | None = None,
        workspace_root: Path | str | None = None,
        max_proxy_calls: int = 8,
        model_calls_cap: int | None = None,
        cancel_timeout: float = 15.0,
        upstream_timeout: float = 120.0,
        allow_loopback_upstream: bool = False,
        proxy_factory: Callable[[Secret, str, int], LocalAuthProxy] | None = None,
    ) -> None:
        self._store = store
        self._compiler = compiler or ResourceCompiler(store)
        self._resolver = credential_resolver or EnvCredentialResolver()
        self._artifacts = artifacts
        root = workspace_root if workspace_root is not None else getattr(store, "workspace_root", None)
        self._workspace_root = Path(root).resolve() if root is not None else None
        self._max_proxy_calls = max_proxy_calls
        self._model_calls_cap = model_calls_cap
        self._model_calls_made = 0
        self._cancel_timeout = cancel_timeout
        self._upstream_timeout = upstream_timeout
        self._allow_loopback_upstream = allow_loopback_upstream
        self._proxy_factory = proxy_factory
        self._active: dict[str, _ExecutionHandle] = {}
        self._sessions: dict[str, _ExecutionHandle] = {}
        self._secret_values: list[str] = []

    # ---------------------------------------------------------- capabilities
    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    @property
    def model_calls_made(self) -> int:
        return self._model_calls_made

    def _make_proxy(self, credential: Secret, upstream: str, max_calls: int) -> LocalAuthProxy:
        if self._proxy_factory is not None:
            return self._proxy_factory(credential, upstream, max_calls)
        return LocalAuthProxy(
            credential=credential,
            upstream_url=upstream,
            max_calls=max_calls,
            timeout=self._upstream_timeout,
            allow_loopback_upstream=self._allow_loopback_upstream,
        )

    # ------------------------------------------------------------- execution
    async def execute(
        self,
        request: ExecuteRequest,
        emit: Callable[[dict[str, Any]], Any],
    ) -> ExecutorResult:
        execution = ExecutionRef(
            execution_id=f"exec_{uuid.uuid4().hex}",
            task_id=request.task_id,
            run_id=request.run_id,
            subtask_id=request.subtask_id,
        )
        handle = _ExecutionHandle(
            execution=execution, request=request, cancel_timeout=self._cancel_timeout
        )
        handle.task = asyncio.current_task()
        self._active[execution.execution_id] = handle
        try:
            return await self._execute(handle, emit)
        finally:
            await handle.ensure_closed()
            self._stop_proxy(handle)
            self._active.pop(execution.execution_id, None)
            if handle.session_ref is not None:
                self._sessions.pop(handle.session_ref.session_id, None)

    def _stop_proxy(self, handle: _ExecutionHandle) -> bool:
        proxy = handle.proxy
        if proxy is None:
            return True
        confirmed = proxy.stop()
        handle.proxy_stop_confirmed = confirmed
        if not handle.model_calls_counted:
            handle.model_calls_counted = True
            self._model_calls_made += proxy.call_count
        return confirmed

    async def _execute(
        self, handle: _ExecutionHandle, emit: Callable[[dict[str, Any]], Any]
    ) -> ExecutorResult:
        request = handle.request
        await self._emit(
            emit,
            {
                "type": "adapter.execution_started",
                "execution": handle.execution.to_dict(),
                "objective": request.objective,
            },
        )
        try:
            compiled = self._compile(request)
        except (AppError, StoreError) as exc:
            code = exc.code.value if isinstance(exc, AppError) else "config_invalid"
            return await self._blocked(handle, emit, code=code, message=str(exc))

        if not compiled.executable:
            return await self._blocked(
                handle,
                emit,
                code=_executable_failure_code(compiled.executable_reasons),
                message="compiled plan is not executable: "
                + ", ".join(compiled.executable_reasons),
            )

        connection = compiled.connection
        assert connection is not None  # executable implies a connection
        if connection.sdk_config_kind != "openai" or connection.backend != "openai-compat":
            # Never silently fall back to an unverified backend.
            return await self._blocked(
                handle,
                emit,
                code="capability_unavailable",
                message=(
                    "first-version executor only runs the verified openai-compat "
                    f"backend, not {connection.backend!r}"
                ),
            )
        if not connection.model:
            return await self._blocked(
                handle,
                emit,
                code="config_invalid",
                message="connection has no model; refusing to guess a model id",
            )
        if not connection.base_url:
            return await self._blocked(
                handle,
                emit,
                code="config_invalid",
                message="openai-compat connection requires base_url",
            )

        credential = self._resolver.resolve(connection.credential_ref or "")
        if credential is None:
            return await self._blocked(
                handle,
                emit,
                code="capability_unavailable",
                message=(
                    f"credential_ref {connection.credential_ref!r} could not be "
                    "resolved from the environment or a controlled store"
                ),
            )
        self._secret_values.append(credential.reveal())

        try:
            workspace = self._resolve_workspace(request.workspace_path)
        except AdapterConfigInvalid as exc:
            return await self._blocked(handle, emit, code=exc.code.value, message=str(exc))

        remaining = (
            None if self._model_calls_cap is None else self._model_calls_cap - self._model_calls_made
        )
        if remaining is not None and remaining <= 0:
            return await self._blocked(
                handle,
                emit,
                code="budget_exhausted",
                message="adapter real-model call cap reached",
            )
        max_calls = self._max_proxy_calls if remaining is None else min(self._max_proxy_calls, remaining)

        upstream = upstream_chat_completions(connection.base_url)
        proxy = self._make_proxy(credential, upstream, max_calls)
        try:
            proxy.start()
        except CapabilityUnavailable as exc:
            return await self._blocked(handle, emit, code="capability_unavailable", message=str(exc))
        handle.proxy = proxy

        try:
            sdk_result = build_sdk_config(
                compiled,
                workspaces=[str(workspace)],
                base_url=proxy.base_url,
                save_dir=request.save_dir,
                response_schema=request.response_schema,
            )
        except CapabilityUnavailable as exc:
            return await self._blocked(handle, emit, code="capability_unavailable", message=str(exc))

        model_sent = _model_name(sdk_result.config)
        before = snapshot_tree(workspace)
        tool_errors: list[str] = []

        await self._emit(
            emit,
            {
                "type": "adapter.session_requested",
                "backend": connection.backend,
                "model": model_sent,
                "upstream_host": urlparse(upstream).hostname,
                "connection_ref": connection.ref,
                "proxy_base_url": proxy.base_url,
                "workspace": str(workspace),
            },
        )

        try:
            from google.antigravity import Agent
        except Exception as exc:  # noqa: BLE001 - SDK missing is a capability gap
            return await self._blocked(
                handle, emit, code="capability_unavailable", message=f"SDK unavailable: {exc}"
            )

        agent = Agent(sdk_result.config)
        handle.agent = agent
        try:
            await agent.__aenter__()
        except Exception as exc:  # noqa: BLE001 - report, do not fake readiness
            return await self._failed(
                handle,
                emit,
                code="session_start_failed",
                message=f"{type(exc).__name__}: {exc}",
                model=model_sent,
            )

        handle.conversation = agent.conversation
        conversation_id = _safe_str(lambda: agent.conversation_id)
        session_state = "resumed" if request.conversation_id else "created"
        handle.session_ref = SessionRef(
            session_id=f"sess_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            state=session_state,
            save_dir=request.save_dir,
        )
        self._sessions[handle.session_ref.session_id] = handle
        sandbox = _safe_attr(agent, "sandbox_status")
        sandbox_available = bool(getattr(sandbox, "available", False))
        await self._emit(
            emit,
            {
                "type": "adapter.session_started",
                "session": handle.session_ref.to_dict(),
                "sandbox": {
                    "available": sandbox_available,
                    "reason": getattr(sandbox, "unavailable_reason", None),
                },
            },
        )

        prompt = self._build_prompt(request, compiled)
        chunks: list[Any] = []
        try:
            await self._run_turn(handle, emit, credential, prompt, chunks, tool_errors)
        except Exception as exc:  # noqa: BLE001 - convert to a classified failure
            handle.stream_error = exc

        stop_reason: str | None = None
        response_obj = handle.response
        if response_obj is not None:
            stop_reason = _safe_str(lambda: str(response_obj.stop_reason))
        if handle.cancel_requested:
            # The cancel caller may still be confirming the stop; wait for its
            # verdict so the result reflects the same confirmation.
            try:
                await asyncio.wait_for(
                    handle.cancel_resolved.wait(), timeout=self._cancel_timeout + 1.0
                )
            except asyncio.TimeoutError:
                pass
        final_conversation_id = _safe_str(lambda: agent.conversation_id)
        if handle.session_ref is not None and (
            final_conversation_id
            and final_conversation_id != handle.session_ref.conversation_id
        ):
            handle.session_ref = SessionRef(
                session_id=handle.session_ref.session_id,
                conversation_id=final_conversation_id,
                state=handle.session_ref.state,
                save_dir=handle.session_ref.save_dir,
            )
        usage = _structured_usage(getattr(handle.response, "usage_metadata", None))
        structured: Any = None
        if not handle.cancel_requested and not handle.timed_out:
            structured = await self._structured_output(handle)

        await handle.ensure_closed()
        after = snapshot_tree(workspace)
        diff_text, produced, removed = diff_snapshots(before, after)
        diff_ref: str | None = None
        if diff_text and self._artifacts is not None:
            diff_ref = self._artifacts.write(f"{request.run_id}/lg006-diff.patch", diff_text)

        proxy_confirmed = self._stop_proxy(handle)

        has_output = bool(_collected_text(chunks)) or structured is not None
        state, failure = classify_outcome(
            stop_reason=stop_reason,
            tool_errors=len(tool_errors),
            has_output=has_output,
            stream_error=handle.stream_error,
            cancel_requested=handle.cancel_requested,
            cancel_confirmed=handle.cancel_confirmed,
            timed_out=handle.timed_out,
        )
        stop_confirmed: bool | None
        if handle.cancel_requested:
            stop_confirmed = handle.cancel_confirmed
        elif handle.timed_out:
            stop_confirmed = handle.cancel_confirmed
        else:
            stop_confirmed = None

        records = self._check_records(
            sandbox_available=sandbox_available,
            sandbox_reason=getattr(sandbox, "unavailable_reason", None),
            model_sent=model_sent,
            proxy_confirmed=proxy_confirmed,
            tool_errors=tool_errors,
            tool_calls=chunks,
            diff_text=diff_text,
            structured=structured,
        )
        summary = self._summarize(state, chunks, structured, failure)
        result = ExecutorResult(
            state=state,
            summary=summary,
            artifact_refs=tuple(produced),
            diff_ref=diff_ref,
            check_records=tuple(records),
            session_ref=handle.session_ref,
            failure=failure,
            usage=usage,
            stop_reason=stop_reason,
            stop_confirmed=stop_confirmed,
            execution_ref=handle.execution,
            model=model_sent,
            upstream_model=proxy.upstream_model,
            diff=diff_text or None,
        )
        await self._emit(
            emit,
            {
                "type": "adapter.execution_finished",
                "execution": handle.execution.to_dict(),
                "result": result.to_dict(),
                "removed": removed,
                "upstream_calls": proxy.call_records(),
            },
        )
        return result

    # --------------------------------------------------------------- helpers
    def _compile(self, request: ExecuteRequest) -> CompiledAgentConfig:
        if not request.agent_ref:
            raise AdapterConfigInvalid(
                "ExecuteRequest.agent_ref is required to compile the LG-005 plan"
            )
        budget = dict(request.budget or {})
        constraints = CompileConstraints(
            allowed_tools=(
                frozenset(request.allowed_tools) if request.allowed_tools is not None else None
            ),
            max_model_calls=_int_or_none(budget.get("max_model_calls")),
            max_tool_calls=_int_or_none(budget.get("max_tool_calls")),
            max_total_tokens=_int_or_none(budget.get("max_total_tokens")),
            timeout_seconds=request.timeout_seconds,
            workspace_path=request.workspace_path,
            conversation_id=request.conversation_id,
        )
        compiled = self._compiler.compile_agent(request.agent_ref, constraints=constraints)
        connection = compiled.connection
        if connection is not None and request.connection_ref and request.connection_ref != connection.ref:
            raise AdapterConfigInvalid(
                f"request connection_ref {request.connection_ref!r} does not match the "
                f"compiled connection {connection.ref!r}"
            )
        if request.skill_refs:
            allowed = set(compiled.skills.refs)
            missing = [ref for ref in request.skill_refs if ref not in allowed]
            if missing:
                raise AdapterConfigInvalid(
                    f"request skill_refs {missing!r} are not present in the compiled plan"
                )
        return compiled

    def _resolve_workspace(self, workspace_path: str) -> Path:
        if not isinstance(workspace_path, str) or not workspace_path.strip():
            raise AdapterConfigInvalid("ExecuteRequest.workspace_path is required")
        resolved = Path(workspace_path).resolve()
        root = self._workspace_root
        if root is not None and not _is_within(resolved, root):
            raise AdapterConfigInvalid(
                f"workspace {str(resolved)!r} escapes the authorized root {str(root)!r}"
            )
        if not resolved.is_dir():
            raise AdapterConfigInvalid(f"workspace {str(resolved)!r} is not an existing directory")
        return resolved

    def _build_prompt(self, request: ExecuteRequest, compiled: CompiledAgentConfig) -> str:
        parts: list[str] = []
        if request.objective.strip():
            parts.append(request.objective.strip())
        if request.instructions.strip() and request.instructions.strip() != request.objective.strip():
            parts.append(request.instructions.strip())
        if request.acceptance_criteria:
            parts.append(
                "Acceptance criteria:\n"
                + "\n".join(f"- {item}" for item in request.acceptance_criteria)
            )
        if request.upstream_artifact_refs:
            parts.append(
                "Upstream artifacts:\n"
                + "\n".join(f"- {item}" for item in request.upstream_artifact_refs)
            )
        if not parts:
            parts.append("Proceed with the assigned subtask.")
        del compiled  # instructions already travel as system_instructions
        return "\n\n".join(parts)

    async def _run_turn(
        self,
        handle: _ExecutionHandle,
        emit: Callable[[dict[str, Any]], Any],
        credential: Secret,
        prompt: str,
        chunks: list[Any],
        tool_errors: list[str],
    ) -> None:
        agent = handle.agent
        assert agent is not None
        response = await agent.chat(prompt)
        handle.response = response
        drain = asyncio.create_task(self._drain(response, handle, emit, credential, chunks, tool_errors))
        timeout = handle.request.timeout_seconds
        if not timeout:
            await drain
            return
        timer = asyncio.create_task(asyncio.sleep(float(timeout)))
        done, _ = await asyncio.wait({drain, timer}, return_when=asyncio.FIRST_COMPLETED)
        if timer in done and drain not in done:
            handle.timed_out = True
            await handle.request_cancel()
            try:
                await asyncio.wait_for(drain, timeout=max(self._cancel_timeout, 1.0))
            except Exception:  # noqa: BLE001 - timeout path is best-effort
                drain.cancel()
        else:
            timer.cancel()
        if drain.done() and not drain.cancelled():
            error = drain.exception()
            if error is not None:
                raise error

    async def _drain(
        self,
        response: Any,
        handle: _ExecutionHandle,
        emit: Callable[[dict[str, Any]], Any],
        credential: Secret,
        chunks: list[Any],
        tool_errors: list[str],
    ) -> None:
        from google.antigravity import types

        try:
            async for chunk in response.chunks:
                chunks.append(chunk)
                if isinstance(chunk, types.ToolResult):
                    if chunk.error or chunk.exception:
                        tool_errors.append(str(chunk.name))
                await self._emit_chunk(emit, chunk)
        except types.AntigravityCancelledError:
            if not handle.cancel_requested:
                handle.stream_error = RuntimeError("stream cancelled without a request")
            return
        except Exception as exc:  # noqa: BLE001 - record and classify, do not crash
            handle.stream_error = exc
            await self._emit(
                emit,
                {"type": "adapter.error", "error": type(exc).__name__, "message": str(exc)[:500]},
            )

    async def _structured_output(self, handle: _ExecutionHandle) -> Any:
        response = handle.response
        if response is None:
            return None
        try:
            return await response.structured_output()
        except Exception:  # noqa: BLE001 - structured output is optional
            return None

    def _check_records(
        self,
        *,
        sandbox_available: bool,
        sandbox_reason: str | None,
        model_sent: str | None,
        proxy_confirmed: bool,
        tool_errors: list[str],
        tool_calls: list[Any],
        diff_text: str,
        structured: Any,
    ) -> list[CheckRecord]:
        records: list[CheckRecord] = [
            CheckRecord(
                name="sandbox",
                status="passed" if sandbox_available else "unknown",
                detail=str(sandbox_reason or ""),
            ),
            CheckRecord(
                name="auth_proxy_stopped",
                status="passed" if proxy_confirmed else "failed",
                detail="loopback proxy socket closed" if proxy_confirmed else "proxy stop unconfirmed",
            ),
            CheckRecord(
                name="model_identity",
                status="passed" if model_sent else "failed",
                detail=model_sent or "no model id configured",
            ),
            CheckRecord(
                name="diff",
                status="passed" if diff_text else "unknown",
                detail=f"{len(diff_text)} chars",
            ),
        ]
        for name in tool_errors:
            records.append(CheckRecord(name=f"tool:{name}", status="failed", detail="tool error"))
        if structured is not None:
            records.append(
                CheckRecord(
                    name="structured_output",
                    status="passed",
                    detail=repr(structured)[:500],
                )
            )
        return records

    def _summarize(
        self,
        state: str,
        chunks: list[Any],
        structured: Any,
        failure: FailureInfo | None,
    ) -> str:
        if failure is not None and state != "succeeded":
            return f"{state}: {failure.message}"
        text = _collected_text(chunks).strip()
        if structured is not None:
            return f"{state}: {structured!r}"[:1000]
        return f"{state}: {text[:1000]}" if text else state

    # ------------------------------------------------------------------ emit
    async def _emit(self, emit: Callable[[dict[str, Any]], Any], event: dict[str, Any]) -> None:
        payload = mask_values(event, self._secret_values)
        payload.setdefault("at", _now())
        result = emit(payload)
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            await result

    async def _emit_chunk(self, emit: Callable[[dict[str, Any]], Any], chunk: Any) -> None:
        from google.antigravity import types

        if isinstance(chunk, types.Text):
            event: dict[str, Any] = {"type": "adapter.text", "text": chunk.text[:4000]}
        elif isinstance(chunk, types.Thought):
            event = {"type": "adapter.thought", "text": chunk.text[:4000]}
        elif isinstance(chunk, types.ToolCall):
            event = {
                "type": "adapter.tool_call",
                "name": str(chunk.name),
                "args": redact(_bounded(chunk.args)),
            }
        elif isinstance(chunk, types.ToolResult):
            event = {
                "type": "adapter.tool_result",
                "name": str(chunk.name),
                "status": "error" if (chunk.error or chunk.exception) else "ok",
                "error": (chunk.error or "")[:500],
            }
        else:
            event = {"type": "adapter.chunk"}
        await self._emit(emit, event)

    # ------------------------------------------------------------- cancel/close
    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        handle = self._active.get(execution_ref.execution_id)
        if handle is None:
            return CancelResult(
                confirmed=False,
                state="not_found",
                reason=f"no active execution {execution_ref.execution_id!r}",
            )
        return await handle.request_cancel()

    async def close(self, session_ref: SessionRef) -> None:
        handle = self._sessions.get(session_ref.session_id)
        if handle is None:
            return
        await handle.ensure_closed()
        self._stop_proxy(handle)

    # ------------------------------------------------------------ blocked/failed
    async def _blocked(
        self,
        handle: _ExecutionHandle,
        emit: Callable[[dict[str, Any]], Any],
        *,
        code: str,
        message: str,
    ) -> ExecutorResult:
        failure = FailureInfo(code, message)
        result = ExecutorResult(
            state="blocked",
            summary=f"blocked: {message}",
            failure=failure,
            execution_ref=handle.execution,
            check_records=(CheckRecord(name="readiness", status="failed", detail=message),),
        )
        await self._emit(
            emit,
            {
                "type": "adapter.execution_blocked",
                "execution": handle.execution.to_dict(),
                "failure": failure.to_dict(),
            },
        )
        return result

    async def _failed(
        self,
        handle: _ExecutionHandle,
        emit: Callable[[dict[str, Any]], Any],
        *,
        code: str,
        message: str,
        model: str | None,
    ) -> ExecutorResult:
        await handle.ensure_closed()
        self._stop_proxy(handle)
        failure = FailureInfo(code, message)
        result = ExecutorResult(
            state="failed",
            summary=f"failed: {message}",
            failure=failure,
            session_ref=handle.session_ref,
            execution_ref=handle.execution,
            model=model,
            stop_confirmed=True,
            check_records=(CheckRecord(name="session_start", status="failed", detail=message),),
        )
        await self._emit(
            emit,
            {
                "type": "adapter.execution_finished",
                "execution": handle.execution.to_dict(),
                "result": result.to_dict(),
            },
        )
        return result


def _model_name(config: Any) -> str | None:
    model = getattr(config, "model", None)
    if model is None:
        return None
    value = getattr(model, "name", None) or getattr(model, "model", None) or model
    return value if isinstance(value, str) else str(value)


def _safe_str(getter: Callable[[], Any]) -> str | None:
    try:
        value = getter()
    except Exception:  # noqa: BLE001 - best-effort introspection
        return None
    return None if value is None else str(value)


def _safe_attr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name, None)
    except Exception:  # noqa: BLE001
        return None


def _bounded(value: Any, *, depth: int = 3) -> Any:
    if depth <= 0:
        return "<truncated>"
    if isinstance(value, dict):
        return {str(key): _bounded(item, depth=depth - 1) for key, item in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_bounded(item, depth=depth - 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value[:2000]
    return value


def _collected_text(chunks: list[Any]) -> str:
    from google.antigravity import types

    return "".join(chunk.text for chunk in chunks if isinstance(chunk, types.Text))


__all__ = [
    "AntigravityExecutor",
    "ArtifactSink",
    "DirectoryArtifactSink",
    "snapshot_tree",
    "diff_snapshots",
    "classify_outcome",
]
