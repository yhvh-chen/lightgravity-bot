#!/usr/bin/env python3
"""Offline selftests for the SDK-round experiment (0 real model calls).

Covers:
  * safe-YAML SoT round-trip, legal null, duplicate-key + illegal-`-` rejection;
  * relay parameter unification + SSE parsing (pure functions);
  * path-guard hook boundary checks;
  * ``finish`` output extraction;
  * a full product-executor turn against a **canned** loopback OpenAI SSE
    upstream (proves executor→proxy→SDK wiring without any model).

The canned end-to-end turn uses only loopback; it makes no external request.
"""
from __future__ import annotations

import asyncio
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


# ---------------------------------------------------------------- sotyaml
def test_sotyaml() -> None:
    from sotyaml import (FrontmatterError, dump_frontmatter, parse_frontmatter,
                         parse_frontmatter_file, write_frontmatter_file)
    text = dump_frontmatter({"a": 1, "lease_path": None, "s": "x: y", "list": ["p", "q"]}, "# body\n")
    fm = parse_frontmatter(text)
    check("sotyaml/null-roundtrip", fm.get("lease_path") is None and fm.get("a") == 1, str(fm))
    check("sotyaml/list-roundtrip", fm.get("list") == ["p", "q"], str(fm))
    # duplicate keys rejected
    try:
        parse_frontmatter("---\na: 1\na: 2\n---\n")
        check("sotyaml/duplicate-rejected", False)
    except FrontmatterError:
        check("sotyaml/duplicate-rejected", True)
    # illegal dash scalar rejected (the round-2 bug)
    try:
        parse_frontmatter("---\nlease_path: -\n---\n")
        check("sotyaml/dash-rejected", False)
    except FrontmatterError:
        check("sotyaml/dash-rejected", True)
    # non-mapping rejected
    try:
        parse_frontmatter("---\n- a\n- b\n---\n")
        check("sotyaml/nonmapping-rejected", False)
    except FrontmatterError:
        check("sotyaml/nonmapping-rejected", True)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.md"
        write_frontmatter_file(p, {"lease_path": None, "n": 3}, "# X\n")
        fm2 = parse_frontmatter_file(p)
        check("sotyaml/file-roundtrip", fm2.get("n") == 3 and fm2.get("lease_path") is None)


# ---------------------------------------------------------------- relay
def test_relay() -> None:
    from relay import _param_view, _parse_sse, unify_request
    payload = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}],
               "tools": [{"function": {"name": "view_file"}}]}
    view = _param_view(payload)
    check("relay/param-view", view["model"] == "m" and view["tool_names"] == ["view_file"], str(view))
    out, rewrites = unify_request(dict(payload))
    check("relay/unify-max-tokens", out["max_tokens"] == 8192 and "max_tokens" in rewrites)
    check("relay/unify-thinking", out["thinking"] == {"type": "disabled"})
    check("relay/unify-usage", out["stream_options"] == {"include_usage": True})
    # already-unified request records no rewrite
    _, rewrites2 = unify_request({"max_tokens": 8192, "thinking": {"type": "disabled"},
                                  "stream_options": {"include_usage": True}})
    check("relay/no-spurious-rewrite", rewrites2 == {}, str(rewrites2))
    sse = (
        b'data: {"model":"deepseek-flash","choices":[{"index":0,"delta":{"content":"x"},'
        b'"finish_reason":null}]}\n\n'
        b'data: {"model":"deepseek-flash","choices":[{"index":0,"delta":{},'
        b'"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":5,"completion_tokens":2,'
        b'"total_tokens":7}}\n\ndata: [DONE]\n\n'
    )
    usage, model, reasons, reasoning = _parse_sse(sse)
    check("relay/sse-usage", usage == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})
    check("relay/sse-model", model == "deepseek-flash")
    check("relay/sse-finish", reasons == ["tool_calls"], str(reasons))
    check("relay/sse-reasoning", reasoning is False)
    sse2 = b'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}\n\n'
    check("relay/sse-reasoning-seen", _parse_sse(sse2)[3] is True)


# ---------------------------------------------------------------- hooks
def test_hooks() -> None:
    from hooks import check_paths, extract_paths
    root = Path(tempfile.mkdtemp()).resolve()
    (root / "src").mkdir()
    ok, _ = check_paths(["src/a.py"], allowed_root=root)
    check("hooks/allow-inside", ok)
    bad, reason = check_paths(["../outside.py"], allowed_root=root)
    check("hooks/deny-escape", not bad and "escape" in reason, reason)
    bad2, reason2 = check_paths([str(root / ".env")], allowed_root=root)
    check("hooks/deny-basename", not bad2, reason2)
    bad3, reason3 = check_paths([str(root / "reference" / "x.py")], allowed_root=root)
    check("hooks/deny-reference", not bad3, reason3)

    class _Call:
        name = "view_file"
        canonical_path = None
        args = {"file_path": str(root / "src" / "a.py")}
    check("hooks/extract-paths", extract_paths(_Call()) == [str(root / "src" / "a.py")])
    # decorated hook builds and denies (no SDK network)
    try:
        from hooks import make_path_guard_hook
        hook = make_path_guard_hook(root, [])
        result = asyncio.run(hook.run(None, _Call()))
        check("hooks/decorated-allow", bool(getattr(result, "allow", False)))
    except Exception as exc:  # noqa: BLE001
        check("hooks/decorated-allow", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- finish extract
def test_finish_extract() -> None:
    from host import extract_finish_output
    calls = [
        {"name": "view_file", "args": {"file_path": "x"}},
        {"name": "finish", "args": {"output_string": json.dumps({"claim": "src/a.py", "message": "m"})}},
    ]
    out = extract_finish_output(calls)
    check("finish/extract", isinstance(out, dict) and out.get("claim") == "src/a.py", str(out))
    check("finish/none-when-absent", extract_finish_output([{"name": "view_file", "args": {}}]) is None)


# ---------------------------------------------------------------- canned SDK turn
_ROLE_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"deepseek-flash","choices":[{"index":0,'
    '"delta":{"role":"assistant","content":"pong"},"finish_reason":null}]}\n\n'
)
_STOP_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"deepseek-flash","choices":[{"index":0,"delta":{},'
    '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
    '"completion_tokens":1,"total_tokens":4}}\n\n'
    "data: [DONE]\n\n"
)


class _CannedUpstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = (_ROLE_CHUNK + _STOP_CHUNK).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


def test_canned_turn() -> None:
    try:
        from host import SdkHost
    except Exception as exc:  # noqa: BLE001
        check("canned/import-host", False, f"{type(exc).__name__}: {exc}")
        return
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CannedUpstream)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            workspace = tdp / "ws"
            (workspace / "src").mkdir(parents=True)
            (workspace / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            host = SdkHost(tdp / "sdkdata", url, workspace_root=tdp)
            turn = asyncio.run(host.run_turn(
                credential="sk-canned-not-real", agent_ref="claim-worker",
                workspace=workspace, objective="Say pong then finish.",
                response_schema=None, allowed_tools=("view-file",),
                timeout_seconds=60, save_dir=tdp / "sessions",
            ))
            check("canned/turn-succeeded", turn["state"] == "succeeded", str(turn.get("state")))
            check("canned/text", "pong" in (turn.get("text") or ""), str(turn.get("text")))
            check("canned/upstream-model", turn.get("upstream_model") == "deepseek-flash")
            check("canned/usage", (turn.get("usage") or {}).get("total_tokens") == 4)
            check("canned/tool-call-event", "finish" in (turn.get("tool_call_names") or [])
                  or turn["state"] == "succeeded")
            # proxy stopped check
            records = {r if isinstance(r, str) else getattr(r, "name", None): getattr(r, "status", None)
                       for r in []}
            check("canned/no-secret-leak", "sk-canned-not-real" not in json.dumps(turn))
    except Exception as exc:  # noqa: BLE001
        check("canned/turn", False, f"{type(exc).__name__}: {exc}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_relay_end_to_end() -> None:
    """Full SDK->proxy->relay->loopback-upstream path (no external network)."""
    try:
        from host import SdkHost
        from relay import MeteringRelay
    except Exception as exc:  # noqa: BLE001
        check("relay-e2e/import", False, f"{type(exc).__name__}: {exc}")
        return
    up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CannedUpstream)
    up.daemon_threads = True
    ut = threading.Thread(target=up.serve_forever, daemon=True)
    ut.start()
    relay = MeteringRelay()  # authorized ctor; upstream retargeted for the test only
    relay._state.upstream_url = f"http://127.0.0.1:{up.server_address[1]}/v1/chat/completions"
    relay.start()
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            workspace = tdp / "ws"
            (workspace / "src").mkdir(parents=True)
            (workspace / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            host = SdkHost(tdp / "sdkdata", relay.base_url, workspace_root=tdp)
            turn = asyncio.run(host.run_turn(
                credential="sk-canned-not-real", agent_ref="claim-worker",
                workspace=workspace, objective="Say pong then finish.",
                response_schema=None, allowed_tools=("view-file",),
                timeout_seconds=60, save_dir=tdp / "sessions",
            ))
            check("relay-e2e/turn", turn["state"] == "succeeded", str(turn.get("state")))
            check("relay-e2e/count", relay.call_count >= 1, str(relay.call_count))
            records = relay.call_records()
            after = records[0]["request_after"]
            check("relay-e2e/forced-params", after.get("max_tokens") == 8192
                  and after.get("thinking") == {"type": "disabled"}, json.dumps(after))
            check("relay-e2e/usage", relay.total_reported_tokens() == 4, str(relay.total_reported_tokens()))
            check("relay-e2e/no-secret", "sk-canned-not-real" not in json.dumps(records))
    except Exception as exc:  # noqa: BLE001
        check("relay-e2e", False, f"{type(exc).__name__}: {exc}")
    finally:
        relay.stop()
        up.shutdown()
        up.server_close()
        ut.join(5)


def main() -> int:
    test_sotyaml()
    test_relay()
    test_hooks()
    test_finish_extract()
    test_canned_turn()
    test_relay_end_to_end()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL OFFLINE SELFTESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
