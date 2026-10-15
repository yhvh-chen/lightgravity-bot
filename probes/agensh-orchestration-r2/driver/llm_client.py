#!/usr/bin/env python3
"""Bounded OpenAI-compatible (DeepSeek) streaming chat client (round 2).

Changes vs round 1:
- explicit ``thinking.type=disabled`` (requested; if the service rejects it the
  driver records the raw error and stops, it does not silently change params);
- captures ``finish_reason``, the response ``model`` echo and any
  ``reasoning_content`` so truncation / reasoning leakage are auditable;
- never stores or logs the Authorization header or the API key.

Standard library only. See ../PROTOCOL.md.
"""
from __future__ import annotations

import http.client
import json
import math
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_HOST = "api.deepseek.com"
DEFAULT_PATH = "/v1/chat/completions"


@dataclass
class ModelResult:
    ok: bool
    content: str = ""
    usage: dict[str, Any] | None = None
    http_status: int | None = None
    error: str | None = None
    infra_failure: bool = False
    fatal: bool = False
    elapsed: float = 0.0
    raw_request: dict[str, Any] = field(default_factory=dict)
    raw_response_text: str = ""
    estimated_tokens: int = 0
    usage_unknown: bool = False
    first_event_seconds: float | None = None
    finish_reason: str | None = None
    response_model: str | None = None
    reasoning_content: str = ""
    reasoning_tokens: int = 0


def estimate_tokens(*texts: str) -> int:
    """Conservative fallback when usage is missing."""
    total_chars = sum(len(t or "") for t in texts)
    return int(math.ceil(total_chars / 4)) if total_chars else 0


def chat_completion(
    api_key: str,
    messages: list[dict[str, str]],
    *,
    model: str,
    host: str = DEFAULT_HOST,
    port: int | None = None,
    path: str = DEFAULT_PATH,
    scheme: str = "https",
    max_tokens: int = 8192,
    temperature: float = 0.0,
    first_event_timeout: float = 30.0,
    total_timeout: float = 90.0,
    json_mode: bool = False,
    thinking_disabled: bool = True,
) -> ModelResult:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    # Round 2 explicitly requests reasoning mode off. If the endpoint rejects
    # this, the error is surfaced verbatim.
    if thinking_disabled:
        payload["thinking"] = {"type": "disabled"}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    prompt_text = "\n".join(m.get("content", "") for m in messages)
    start = time.monotonic()
    deadline = start + total_timeout
    conn: http.client.HTTPSConnection | None = None
    try:
        ctx = ssl.create_default_context()
        if scheme == "http":
            conn = http.client.HTTPConnection(host, port or 80, timeout=first_event_timeout)
        else:
            conn = http.client.HTTPSConnection(host, port or 443, timeout=first_event_timeout, context=ctx)
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                # Injected per request; never stored or logged.
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = conn.getresponse()
        status = resp.status
        if status != 200:
            err_text = _safe_read(resp).decode("utf-8", "replace")[:2000]
            # 4xx = request/config rejection (fatal, no retry); 5xx/429 = infra.
            fatal = 400 <= status < 500 and status != 429
            return ModelResult(
                ok=False,
                http_status=status,
                error=f"HTTP {status}: {err_text}",
                infra_failure=not fatal,
                fatal=fatal,
                elapsed=time.monotonic() - start,
                raw_request=payload,
                raw_response_text=err_text,
                estimated_tokens=estimate_tokens(prompt_text),
                usage_unknown=True,
            )

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: dict[str, Any] | None = None
        finish_reason: str | None = None
        response_model: str | None = None
        got_done = False
        first_event: float | None = None
        sock = getattr(conn, "sock", None)
        while True:
            now = time.monotonic()
            if first_event is None and now - start > first_event_timeout:
                return ModelResult(
                    ok=False, content="".join(content_parts), http_status=status,
                    error=f"no SSE data event within {first_event_timeout:.0f}s (keep-alive only?)",
                    infra_failure=True, elapsed=time.monotonic() - start, raw_request=payload,
                    estimated_tokens=estimate_tokens(prompt_text, "".join(content_parts)),
                    usage_unknown=True, first_event_seconds=first_event)
            if now > deadline:
                return ModelResult(
                    ok=False, content="".join(content_parts), http_status=status,
                    error=f"overall timeout after {time.monotonic() - start:.1f}s",
                    infra_failure=True, elapsed=time.monotonic() - start, raw_request=payload,
                    estimated_tokens=estimate_tokens(prompt_text, "".join(content_parts)),
                    usage_unknown=True, first_event_seconds=first_event)
            if sock is not None:
                remaining = deadline - now
                if first_event is None:
                    sock.settimeout(max(0.5, min(first_event_timeout, remaining)))
                else:
                    sock.settimeout(max(0.5, remaining))
            try:
                raw = resp.readline()
            except (TimeoutError, socket.timeout):
                note = ("no SSE data event within %.0fs (keep-alive only?)" % first_event_timeout
                        if first_event is None else "stream stalled before completion")
                return ModelResult(
                    ok=False, content="".join(content_parts), http_status=status, error=note,
                    infra_failure=True, elapsed=time.monotonic() - start, raw_request=payload,
                    estimated_tokens=estimate_tokens(prompt_text, "".join(content_parts)),
                    usage_unknown=True, first_event_seconds=first_event)
            except (http.client.HTTPException, OSError) as exc:
                return ModelResult(
                    ok=False, content="".join(content_parts), http_status=status,
                    error=f"read error: {type(exc).__name__}: {exc}", infra_failure=True,
                    elapsed=time.monotonic() - start, raw_request=payload,
                    estimated_tokens=estimate_tokens(prompt_text, "".join(content_parts)),
                    usage_unknown=True, first_event_seconds=first_event)
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                got_done = True
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if first_event is None:
                first_event = time.monotonic() - start
            if isinstance(obj.get("model"), str):
                response_model = obj["model"]
            if isinstance(obj.get("usage"), dict):
                usage = obj["usage"]
            for choice in obj.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                rpiece = delta.get("reasoning_content")
                if rpiece:
                    reasoning_parts.append(rpiece)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        usage_known = usage is not None
        reasoning_tokens = 0
        if usage_known:
            details = usage.get("completion_tokens_details") or {}
            try:
                reasoning_tokens = int(details.get("reasoning_tokens") or 0)
            except (TypeError, ValueError):
                reasoning_tokens = 0
        return ModelResult(
            ok=got_done, content=content, usage=usage, http_status=status,
            error=None if got_done else "stream ended without [DONE]",
            infra_failure=not got_done, elapsed=time.monotonic() - start,
            raw_request=payload, raw_response_text=content,
            estimated_tokens=estimate_tokens(prompt_text, content) if not usage_known else int(
                usage.get("total_tokens") or 0),
            usage_unknown=not usage_known, first_event_seconds=first_event,
            finish_reason=finish_reason, response_model=response_model,
            reasoning_content=reasoning, reasoning_tokens=reasoning_tokens,
        )
    except (http.client.HTTPException, OSError, ssl.SSLError) as exc:
        return ModelResult(
            ok=False, http_status=None,
            error=f"connection error: {type(exc).__name__}: {exc}", infra_failure=True,
            elapsed=time.monotonic() - start, raw_request=payload,
            estimated_tokens=estimate_tokens(prompt_text), usage_unknown=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _safe_read(resp: http.client.HTTPResponse) -> bytes:
    try:
        return resp.read()
    except Exception:  # noqa: BLE001
        return b""
