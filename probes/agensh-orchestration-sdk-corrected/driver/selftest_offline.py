#!/usr/bin/env python3
"""Offline selftests for the corrected SDK-round experiment (0 model calls).

Covers the corrected-version acceptance points:

  * full, lossless ``finish`` recovery from the first attempt's SDK native
    session DBs (read-only source), vs the 2000-char truncated emitted event;
  * strict ``PlanSchema`` rejection of the three old planner reports;
  * fail-closed path guard canary replay on realistic SDK event shapes
    (``AbsolutePath`` / ``TargetFile`` / unknown key), including lease writes;
  * safe-YAML round-trip, legal null, duplicate-key + illegal-``-`` rejection;
  * relay single-output-limit unification (``max_completion_tokens`` removed);
  * budget counting / conservative unknown usage / cap;
  * per-turn stop evidence (positive vs unknown -> no lease release);
  * no secret leak in serialized turn records.

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
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

FAILURES: list[str] = []

# First-attempt source (read-only) for offline replay.
FIRST_ATTEMPT = Path(
    "/tmp/lightgravity-worktrees/agensh-sdk-20261015/probes/agensh-orchestration-sdk"
)


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
    for bad, name in (("---\na: 1\na: 2\n---\n", "duplicate-rejected"),
                      ("---\nlease_path: -\n---\n", "dash-rejected"),
                      ("---\n- a\n- b\n---\n", "nonmapping-rejected")):
        try:
            parse_frontmatter(bad)
            check(f"sotyaml/{name}", False)
        except FrontmatterError:
            check(f"sotyaml/{name}", True)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.md"
        write_frontmatter_file(p, {"lease_path": None, "n": 3}, "# X\n")
        fm2 = parse_frontmatter_file(p)
        check("sotyaml/file-roundtrip", fm2.get("n") == 3 and fm2.get("lease_path") is None)


# ---------------------------------------------------------------- relay
def test_relay() -> None:
    from relay import _param_view, _parse_sse, output_limit_fields, unify_request
    payload = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}],
               "tools": [{"function": {"name": "view_file"}}],
               "max_completion_tokens": 65535}
    view = _param_view(payload)
    check("relay/param-view", view["model"] == "m" and view["tool_names"] == ["view_file"], str(view))
    check("relay/before-two-limits", set(view["output_limit_fields"]) ==
          {"max_completion_tokens"}, str(view["output_limit_fields"]))
    out, rewrites = unify_request(dict(payload))
    check("relay/unify-max-tokens", out["max_tokens"] == 8192 and "max_tokens" in rewrites)
    check("relay/alias-removed", "max_completion_tokens" not in out and
          "max_completion_tokens" in rewrites, json.dumps(rewrites))
    check("relay/single-output-limit", output_limit_fields(out) == ["max_tokens"],
          str(output_limit_fields(out)))
    check("relay/unify-thinking", out["thinking"] == {"type": "disabled"})
    check("relay/unify-usage", out["stream_options"] == {"include_usage": True})
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


# ---------------------------------------------------------------- hooks canary
def test_hooks_canary() -> None:
    from hooks import check_call, extract_paths
    root = Path(tempfile.mkdtemp()).resolve()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    lease = {(root / "src" / "a.py").resolve().as_posix()}

    def call(name, **args):
        return SimpleNamespace(name=name, args=args, canonical_path=None)

    # real SDK wire shapes
    inside = call("view_file", AbsolutePath=str(root / "src" / "a.py"))
    check("canary/inside-read", check_call(inside, allowed_root=root)[0])
    check("canary/inside-read-nonempty", extract_paths(inside) != [])
    outside = call("view_file", AbsolutePath="/etc/passwd")
    ok, reason = check_call(outside, allowed_root=root)
    check("canary/outside-read-denied", not ok and "escapes" in reason, reason)
    control = call("view_file", AbsolutePath=str(root / "reference" / "x.py"))
    ok, reason = check_call(control, allowed_root=root)
    check("canary/control-read-denied", not ok, reason)
    acceptance = call("view_file", AbsolutePath=str(root / "acceptance.py"))
    ok, reason = check_call(acceptance, allowed_root=root)
    check("canary/hidden-acceptance-read-denied", not ok, reason)
    unknown = call("view_file", SomeWeirdPath=str(root / "src" / "a.py"))
    ok, reason = check_call(unknown, allowed_root=root)
    check("canary/unknown-key-denied", not ok and "unknown_file_argument" in reason, reason)

    lease_write = call("edit_file", TargetFile=str(root / "src" / "a.py"))
    ok, reason = check_call(lease_write, allowed_root=root, write_lease_paths=lease)
    check("canary/lease-write-allowed", ok, reason)
    other_write = call("edit_file", TargetFile=str(root / "src" / "b.py"))
    ok, reason = check_call(other_write, allowed_root=root, write_lease_paths=lease)
    check("canary/nonlease-write-denied", not ok and "not the held lease" in reason, reason)
    reviewer_write = call("create_file", TargetFile=str(root / "src" / "a.py"))
    ok, reason = check_call(reviewer_write, allowed_root=root, write_lease_paths=set())
    check("canary/reviewer-write-denied", not ok and "no lease" in reason, reason)
    outside_write = call("create_file", TargetFile="/tmp/evil.py")
    ok, reason = check_call(outside_write, allowed_root=root, write_lease_paths=lease)
    check("canary/outside-write-denied", not ok and "escapes" in reason, reason)
    # finish is explicitly allowed and path-free
    ok, reason = check_call(call("finish"), allowed_root=root)
    check("canary/finish-allowed", ok, reason)
    # unknown tool fails closed
    ok, reason = check_call(call("run_command", command="rm -rf /"), allowed_root=root)
    check("canary/unknown-tool-denied", not ok, reason)

    # decorated hook denies (no SDK network)
    from hooks import make_path_guard_hook
    decisions: list[dict] = []
    hook = make_path_guard_hook(root, decisions, write_lease_paths=lease)
    result = asyncio.run(hook.run(None, outside))
    check("canary/decorated-deny", getattr(result, "allow", True) is False)
    check("canary/decision-recorded", decisions and decisions[-1]["allow"] is False)


# ---------------------------------------------------------------- plan schema
def _old_plans() -> list[dict]:
    from sessiondb import extract_best_finish_payload
    plans = []
    base = FIRST_ATTEMPT / "runs" / "formal"
    for run in sorted(base.glob("*__B__r0")):
        dbs = sorted((run / "sessions" / "planner").glob("*.db"))
        if dbs:
            p = extract_best_finish_payload(dbs[0])
            if p:
                plans.append(p)
    return plans


def test_session_db_replay() -> None:
    from sessiondb import extract_best_finish_payload
    base = FIRST_ATTEMPT / "runs" / "formal"
    expected = {"t1_independent__B__r0": 6110, "t2_interface__B__r0": 1196,
                "t3_evolving__B__r0": 7690}
    for run_id, size in expected.items():
        dbs = sorted((base / run_id / "sessions" / "planner").glob("*.db"))
        if not dbs:
            check(f"sessiondb/{run_id}", False, "source DB missing")
            continue
        payload = extract_best_finish_payload(dbs[0])
        got = len(json.dumps(payload, ensure_ascii=False, sort_keys=True)) if payload else 0
        check(f"sessiondb/{run_id}-recovered", payload is not None and got >= size - 50, str(got))


def test_plan_schema_rejects_old() -> None:
    from host import PlanSchema
    import pydantic
    plans = _old_plans()
    if not plans:
        check("plan-schema/old-plans-available", False, "no old plans")
        return
    rejected = 0
    for p in plans:
        try:
            PlanSchema.model_validate(p)
        except pydantic.ValidationError:
            rejected += 1
    check("plan-schema/rejects-all-old", rejected == len(plans), f"{rejected}/{len(plans)}")
    # a strict valid plan is accepted
    valid = {"plan": [
        {"worker": "w1", "objective": "implement slugs", "files": ["src/slugs.py"]},
        {"worker": "w2", "objective": "implement ranges", "files": ["src/ranges.py"]},
    ], "interface_notes": "keep signatures stable", "findings": ["ok"]}
    PlanSchema.model_validate(valid)
    check("plan-schema/accepts-strict", True)
    # aliases / extra keys rejected
    for alias in ({"plan": [{"assignee": "w1", "task": "x", "files": []}]},
                  {"plan": [{"worker": "w1", "objective": "x", "files": [], "extra": 1}]},
                  {"plan": [{"worker": "w3", "objective": "x", "files": []}]}):
        try:
            PlanSchema.model_validate(alias)
            check(f"plan-schema/reject-alias-{list(alias['plan'][0])[0]}", False)
        except pydantic.ValidationError:
            check(f"plan-schema/reject-alias-{list(alias['plan'][0])[0]}", True)
    # multi-file assignment rejected
    try:
        PlanSchema.model_validate({"plan": [{"worker": "w1", "objective": "x",
                                             "files": ["a.py", "b.py"]}]})
        check("plan-schema/reject-multifile", False)
    except pydantic.ValidationError:
        check("plan-schema/reject-multifile", True)


# ---------------------------------------------------------------- finish extract
def test_finish_extract() -> None:
    from host import extract_finish_from_calls, extract_finish_output, parse_finish_args
    full_obj = {"plan": [{"worker": "w1", "objective": "do", "files": ["src/a.py"]}],
                "interface_notes": "n", "findings": ["f"]}
    # hook-captured full payload
    capture = [{"name": "view_file", "args": {"AbsolutePath": "/x"}},
               {"name": "finish", "args": {"output_string": json.dumps(full_obj)}}]
    payload, err, src = extract_finish_from_calls(capture)
    check("finish/hook-full", payload == full_obj and err is None and src["name"] == "finish")
    # emitted 2000-char truncation is a different, lossy object
    large = {"plan": [{"worker": "w1", "objective": "do", "files": ["src/a.py"]}],
             "interface_notes": "n" * 3000, "findings": ["f"]}
    truncated = json.dumps(large)[:2000]
    payload2, err2 = parse_finish_args({"output_string": truncated})
    check("finish/truncated-detected", err2 == "invalid_json" and payload2 is None, str(err2))
    check("finish/no-call", extract_finish_from_calls([{"name": "view_file", "args": {}}])[1]
          == "no_finish_call")
    check("finish/legacy-helper", extract_finish_output(capture) == full_obj)


# ---------------------------------------------------------------- budget
def test_budget() -> None:
    sys.path.insert(0, str(_HERE.parent / "driver"))
    # import Budget without pulling the product adapter
    import importlib.util
    spec = importlib.util.spec_from_file_location("_exp_budget", _HERE / "experiment.py")
    # Experiment imports host (product bootstrap); that is fine offline.
    from experiment import Budget
    b = Budget(http_cap=2, token_cap=1000, wall_seconds=100)
    b.charge(http=1, usage={"total_tokens": 100}, est_tokens=50)
    check("budget/known-usage", b.tokens_used == 100 and b.tokens_unknown == 0)
    b.charge(http=1, usage=None, est_tokens=50)
    check("budget/unknown-conservative", b.tokens_unknown == 1 and b.tokens_used == 150)
    check("budget/http-cap", b.check() is not None and "HTTP cap" in b.check())
    b2 = Budget(http_cap=99, token_cap=100, wall_seconds=100)
    b2.charge(http=0, usage={"total_tokens": 100}, est_tokens=0)
    check("budget/token-cap", "token cap" in (b2.check() or ""))


# ---------------------------------------------------------------- stop gate
def _fake_result(*, auth_proxy_passed: bool, stop_confirmed=None):
    class _Usage:
        def to_dict(self):
            return {"total_tokens": 1}
    rec = SimpleNamespace(name="auth_proxy_stopped", status="passed" if auth_proxy_passed else "failed",
                          detail="x")
    return SimpleNamespace(
        state="succeeded", summary="s", stop_reason="StopReason.UNSPECIFIED",
        stop_confirmed=stop_confirmed, failure=None, usage=_Usage(), model="m",
        upstream_model="deepseek", check_records=[rec], session_ref=None,
    )


def test_stop_gate() -> None:
    from host import ObservedProxy, _turn_record

    class _Inner:
        is_running = False
        port = 12345
        upstream_model = "deepseek"

        def stop(self, *a, **k):
            return True

    def record(evidence_inner, auth_passed):
        captured = [{"name": "finish", "args": {"output_string": json.dumps({"summary": "s"})}}]
        return _turn_record(
            result=_fake_result(auth_proxy_passed=auth_passed), events=[], decisions=[],
            tool_events=[], captured_calls=captured, elapsed=0.1, model_sent="m",
            stop_events=evidence_inner, port=12345, port_open_after=False,
            harness_before=[], harness_after=[], close_sink=[{"ensure_closed_returned": True}],
            close_observed=True, save_dir=None, workspace=Path("/tmp"), write_lease=None,
        )

    pos = record([{"returned": True, "is_running_after": False}], auth_passed=True)
    check("stop/positive-confirmed", pos["stop_evidence"]["positive"] is True
          and pos["stop_evidence"]["status"] == "confirmed", json.dumps(pos["stop_evidence"]))
    unk = record([{"returned": False, "is_running_after": True}], auth_passed=False)
    check("stop/unconfirmed-unknown", unk["stop_evidence"]["positive"] is False
          and unk["stop_evidence"]["status"] == "unknown", json.dumps(unk["stop_evidence"]))
    # gate: unknown must not release lease / pass
    def gate(ev):
        return "release" if ev["status"] == "confirmed" else "hold_unknown"
    check("stop/unknown-holds-lease", gate(unk["stop_evidence"]) == "hold_unknown")


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
    from host import SdkHost
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
            check("canned/stop-evidence-present", isinstance(turn.get("stop_evidence"), dict))
            check("canned/no-secret-leak", "sk-canned-not-real" not in json.dumps(turn))
    except Exception as exc:  # noqa: BLE001
        check("canned/turn", False, f"{type(exc).__name__}: {exc}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_secret_purge() -> None:
    import os
    from host import read_and_purge_secret
    os.environ["DEEPSEEK_API_KEY"] = "sk-should-be-purged"
    os.environ["OPENAI_API_KEY"] = "sk-peer"
    val = read_and_purge_secret()
    check("secret/read-once", val == "sk-should-be-purged")
    check("secret/purged", "DEEPSEEK_API_KEY" not in os.environ
          and "OPENAI_API_KEY" not in os.environ)


def main() -> int:
    test_sotyaml()
    test_relay()
    test_hooks_canary()
    test_session_db_replay()
    test_plan_schema_rejects_old()
    test_finish_extract()
    test_budget()
    test_stop_gate()
    test_canned_turn()
    test_secret_purge()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL OFFLINE SELFTESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
