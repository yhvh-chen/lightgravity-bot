#!/usr/bin/env python3
"""LG-032 METHOD-FINAL 门B — real-ledger / real-injection / boundary audit.

Independent evidence (does NOT reuse the cohort-ready hard-gate result) that the
**actual product-injected** generation counter objects — the real executor's own
proxy path and the real independent reviewer's own proxy path — accumulate on
ONE persistent physical ledger, across TWO runtime startups, and that the
forward-refusal and corrupt fail-closed boundaries hold.

Design (audit directive):

* All ledgers here live in an **independent method-final scratch root** with a
  small/necessary cap; the FORMAL ``lg032-method-final-data`` phase root is
  NEVER touched by this probe, so no formal accounting is confused.
* ``build_runtime`` is the real product startup chain; the executor's own
  ``_make_proxy`` (which injects ``generation_budget=global_generation_counter()``)
  is the counted object for worker traffic.  The real reviewer path is invoked
  through ``lightgravity.verify.review.run_review_turn`` (the exact function the
  product ``ModelReviewer`` uses), whose proxy defaults to the same global
  counter.
* ``_AttemptGuard`` is the frozen driver's own per-attempt cap object, installed
  on the product global counter, proving the 48-forward boundary on the real
  counting object; the total-cap (192 / small equivalent) is proven via the
  product's own ``LIGHTGRAVITY_MAX_GENERATION_CALLS`` + proxy 429.
* Corrupt: the physical ``generation.jsonl`` is overwritten with junk; the real
  proxy must then refuse (429) and ``snapshot()`` must report ``corrupt`` and
  ``count is None`` (never 0).

Real provider generation = 0 (loopback fake upstream, dummy credential).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

# NOTE: this probe builds its OWN scratch roots; it never installs the formal
# phase root.  It only needs the frozen constants from the driver, so import the
# driver WITHOUT the method-final formal phase env (install() also updates env;
# that only sets defaults, and we override LIGHTGRAVITY_* for each scratch root).
C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))
import run_attempt as R  # noqa: E402

REPO = MC.WORKTREE
sys.path.insert(0, str(REPO / "backend"))

#: Small equivalent cap used for the boundary probes (independent scratch).
SMALL_CAP = 3


class _FakeHTTP(BaseHTTPRequestHandler):
    """Loopback SSE upstream that answers chat completions with a short text."""

    served = 0
    lock = threading.Lock()
    reply_text = "ok"
    json_reply = False

    def log_message(self, *args: Any) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        with type(self).lock:
            type(self).served += 1
        if type(self).json_reply:
            content = json.dumps({
                "outcome": "passed",
                "reason": "audit fake: no problems",
                "findings": [],
            })
        else:
            content = type(self).reply_text
        chunk = {
            "id": "chunk", "object": "chat.completion.chunk", "created": 1,
            "model": "fake-model",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
        payload = (f"data: {json.dumps(chunk)}\n\n" + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _allow_loopback_proxies() -> None:
    """Offline-only: default ``allow_loopback_upstream=True`` for the REAL
    ``LocalAuthProxy`` class, exactly as the frozen driver does for dry runs.

    The reviewer builds its own ``LocalAuthProxy`` and has no injectable flag,
    so the same supported offline wrapper is required for the reviewer proxy to
    reach the local fake upstream.  Class identity and attributes are preserved.
    """

    import lightgravity.adapter.proxy as proxy_mod

    cls = proxy_mod.LocalAuthProxy
    if getattr(cls, "_lg032_method_loopback_patched", False):
        return
    orig_init = cls.__init__

    def patched_init(self: Any, *a: Any, **kw: Any) -> None:  # noqa: ANN401
        kw.setdefault("allow_loopback_upstream", True)
        orig_init(self, *a, **kw)

    cls.__init__ = patched_init  # type: ignore[method-assign]
    cls._lg032_method_loopback_patched = True  # type: ignore[attr-defined]


def _post(proxy: Any, n: int) -> list[int]:
    codes = []
    for _ in range(n):
        req = urllib.request.Request(
            proxy.base_url + "/chat/completions",
            data=b'{"model":"x","messages":[]}',
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
                codes.append(resp.status)
        except urllib.error.HTTPError as exc:
            exc.read()
            codes.append(exc.code)
    return codes


def _fresh_root(label: str, nonce: str) -> Path:
    root = MC.BOUNDARY_DIR / f"{label}-{nonce}"
    if root.exists():
        raise SystemExit(f"refusing to reuse boundary root {root}")
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build(root: Path, upstream_url: str, *, cap: int, credential: str = "dummy-cred"):
    """Real product startup chain against ``root`` with the given total cap."""

    from lightgravity.config import Settings
    from lightgravity.runtime.token import RuntimeToken
    from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore, EntityNotFound

    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(root)
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(root)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(cap)

    secret_root = root / "secrets"
    secret_root.mkdir(parents=True, exist_ok=True)
    ws_root = root / "workspaces"
    ws_root.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=root, workspace_root=ws_root, secret_store=secret_root,
                        host="127.0.0.1", port=0)
    settings.ensure_data_dir()

    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    for cid in ("gate-worker", "gate-reviewer"):
        try:
            store.read("connection", cid)
            continue
        except EntityNotFound:
            pass
        conns.create_connection(connection_id=cid, backend="openai-compat", model="m",
                                base_url=upstream_url, credential_ref="gate-cred",
                                title=cid, actor="gate", request_id=f"gate-{cid}")
    ss = FileSecretStore(settings.secret_store)
    if ss.get("gate-cred") is None:
        ss.put("gate-cred", credential)
    rev = None
    try:
        rev = store.read("settings", "settings").revision
    except EntityNotFound:
        rev = None
    conns.update_settings(expected_revision=rev, actor="gate",
                          default_coordinator_connection_ref="gate-worker",
                          default_worker_connection_ref="gate-worker",
                          default_reviewer_connection_ref="gate-reviewer")

    state: RuntimeState = build_runtime(StartupOptions(
        settings=settings, token=RuntimeToken("gate-token", "generated"),
        serve_frontend=False, max_proxy_calls=cap, model_calls_cap=cap,
    ))
    # Offline-only: the product exposes ``allow_loopback_upstream`` as a real
    # constructor flag (not a bypass of the loopback guard).  The frozen driver
    # sets it on the real executor for offline runs; the boundary audit does the
    # same so the real executor proxy can reach the local fake upstream.
    if state.executor is not None:
        state.executor._allow_loopback_upstream = True  # type: ignore[attr-defined]
    return state, settings, store


def _counter_snapshot() -> dict[str, Any]:
    from lightgravity.adapter.proxy import global_generation_counter
    return global_generation_counter().snapshot()


def _counter_object_id() -> dict[str, Any]:
    from lightgravity.adapter.proxy import global_generation_counter
    counter = global_generation_counter()
    ledger = getattr(counter, "_ledger", None)
    hist = getattr(ledger, "_history", None) if ledger is not None else None
    return {
        "counter_is_module_global": counter is global_generation_counter(),
        "ledger_history": str(hist) if hist is not None else None,
        "persistent": ledger is not None,
    }


def part_real_injection(nonce: str, upstream_url: str) -> dict[str, Any]:
    """Real executor proxy + real reviewer path accumulate on ONE physical ledger."""

    root = _fresh_root("real", nonce)
    hist = root / "generation" / "generation.jsonl"
    out: dict[str, Any] = {"root": str(root), "physical_history": str(hist)}

    state1, settings1, _ = _build(root, upstream_url, cap=64)
    # Probe 1: the real executor's own proxy factory (product-injected budget).
    from lightgravity.adapter.credentials import Secret
    proxy1 = state1.executor._make_proxy(Secret("dummy-cred"), upstream_url, 64)
    proxy1.start()
    try:
        codes1 = _post(proxy1, 3)
        snap1 = _counter_snapshot()
        hist_lines1 = len(hist.read_text(encoding="utf-8").splitlines()) if hist.exists() else 0
    finally:
        proxy1.stop()
    out["worker_via_executor_make_proxy"] = {
        "codes": codes1, "counter_after": snap1, "physical_lines": hist_lines1,
        "counter_id": _counter_object_id(),
    }

    # Probe 2: real reviewer path (the exact function ModelReviewer uses).
    from lightgravity.verify.review import ReviewerSupport, run_review_turn
    from lightgravity.adapter.credentials import Secret
    support = ReviewerSupport(model="m", base_url=upstream_url, credential_ref="gate-cred")
    _FakeHTTP.json_reply = True
    text, usage = run_review_turn(support, lambda ref: Secret("dummy-cred"), "review this",
                                  max_model_calls=1)
    _FakeHTTP.json_reply = False
    snap2 = _counter_snapshot()
    hist_lines2 = len(hist.read_text(encoding="utf-8").splitlines()) if hist.exists() else 0
    out["reviewer_via_run_review_turn"] = {
        "reply": (text or "")[:80], "usage": usage,
        "counter_after": snap2, "physical_lines": hist_lines2,
    }

    # Restart: build a fresh runtime on the SAME root; count must be persisted.
    del state1
    state2, settings2, _ = _build(root, upstream_url, cap=64)
    snap_at_start2 = _counter_snapshot()
    proxy2 = state2.executor._make_proxy(Secret("dummy-cred"), upstream_url, 64)
    proxy2.start()
    try:
        codes2 = _post(proxy2, 2)
        snap3 = _counter_snapshot()
        hist_lines3 = len(hist.read_text(encoding="utf-8").splitlines()) if hist.exists() else 0
    finally:
        proxy2.stop()
    out["restart"] = {
        "counter_at_start2": snap_at_start2,
        "worker_codes_start2": codes2,
        "counter_after_start2": snap3,
        "physical_lines": hist_lines3,
    }

    c1 = snap1.get("count")
    c2 = snap2.get("count")
    c_start2 = snap_at_start2.get("count")
    c3 = snap3.get("count")
    reviewer_round = (text or "").strip().startswith("{") or (text or "").strip().startswith("```")
    out["checks"] = {
        "worker_3_forwarded_ok": all(x == 200 for x in codes1),
        "worker_count_incremented": isinstance(c1, int) and c1 >= 3,
        "reviewer_reply_parsed_as_json": reviewer_round,
        "reviewer_count_incremented": isinstance(c2, int) and isinstance(c1, int) and c2 == c1 + 1,
        "same_physical_ledger_all_stages": str(hist) in json.dumps(_counter_object_id()),
        "persisted_across_restart": c_start2 == c2,
        "restart_traffic_accumulates": isinstance(c3, int) and c3 == c_start2 + 2,
        "physical_jsonl_grew": hist_lines3 >= (c3 or 0),
    }
    out["ok"] = all(out["checks"].values())
    return out


def part_forward_refusal(nonce: str, upstream_url: str) -> dict[str, Any]:
    """48 per-attempt guard + total-cap refusal before forwarding (real proxy)."""

    root = _fresh_root("refusal", nonce)
    hist = root / "generation" / "generation.jsonl"
    _build(root, upstream_url, cap=C.TOTAL_GENERATION_LIMIT)

    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import global_generation_counter
    counter = global_generation_counter()

    # The frozen driver's own per-attempt guard on the real product counter.
    guard = R._AttemptGuard(counter, C.ATTEMPT_GENERATION_LIMIT)
    guard.install()

    proxy = __import__("lightgravity.adapter.proxy", fromlist=["LocalAuthProxy"]).LocalAuthProxy(
        credential=Secret("dummy-cred"), upstream_url=upstream_url + "/chat/completions",
        max_calls=10_000, allow_loopback_upstream=True, generation_budget=counter,
    )
    proxy.start()
    try:
        n = C.ATTEMPT_GENERATION_LIMIT + 2
        codes = _post(proxy, n)
        snap = counter.snapshot()
    finally:
        proxy.stop()
    used = guard.used
    physical = len(hist.read_text(encoding="utf-8").splitlines()) if hist.exists() else 0
    out = {
        "root": str(root), "limit": C.ATTEMPT_GENERATION_LIMIT, "requests": n,
        "first_429_index": codes.index(429) if 429 in codes else None,
        "guard_used": used,
        "count_after_overrun": snap.get("count"),
        "physical_lines": physical,
    }
    out["checks"] = {
        "guard_used_equals_limit": used == C.ATTEMPT_GENERATION_LIMIT,
        "over_limit_denied_429": codes[-1] == 429 and codes.count(429) == 2,
        "count_never_exceeds_limit": snap.get("count") == C.ATTEMPT_GENERATION_LIMIT,
        "no_forward_for_denied": physical <= C.ATTEMPT_GENERATION_LIMIT,
    }
    out["ok"] = all(out["checks"].values())
    return out


def part_total_cap_small_equiv(nonce: str, upstream_url: str) -> dict[str, Any]:
    """Total-cap forward-refusal, small equivalent cap on independent scratch."""

    root = _fresh_root("total", nonce)
    _build(root, upstream_url, cap=SMALL_CAP)
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import global_generation_counter, LocalAuthProxy
    counter = global_generation_counter()
    proxy = LocalAuthProxy(credential=Secret("dummy-cred"),
                           upstream_url=upstream_url + "/chat/completions",
                           max_calls=10_000, allow_loopback_upstream=True,
                           generation_budget=counter)
    proxy.start()
    try:
        codes = _post(proxy, SMALL_CAP + 2)
        snap = counter.snapshot()
    finally:
        proxy.stop()
    out = {"root": str(root), "small_cap": SMALL_CAP, "codes": codes,
           "count": snap.get("count"), "limit": snap.get("limit")}
    out["checks"] = {
        "first_over_cap_denied": codes[SMALL_CAP] == 429,
        "count_pinned_at_cap": snap.get("count") == SMALL_CAP,
    }
    out["ok"] = all(out["checks"].values())
    return out


def part_corrupt_failclosed(nonce: str, upstream_url: str) -> dict[str, Any]:
    """Corrupt physical ledger -> real proxy refuses; snapshot corrupt, count None."""

    root = _fresh_root("corrupt", nonce)
    _build(root, upstream_url, cap=C.TOTAL_GENERATION_LIMIT)
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import global_generation_counter, LocalAuthProxy
    from lightgravity.adapter.generation_ledger import (
        GenerationLedgerCorrupt, PersistentGenerationLedger,
    )

    counter = global_generation_counter()
    proxy = LocalAuthProxy(credential=Secret("dummy-cred"),
                           upstream_url=upstream_url + "/chat/completions",
                           max_calls=10_000, allow_loopback_upstream=True,
                           generation_budget=counter)
    proxy.start()
    try:
        before = _post(proxy, 1)
        # Corrupt the PHYSICAL history file of the very ledger the proxy uses.
        ledger = counter._ledger
        ledger._history.write_text("this is not json\n", encoding="utf-8")
        after = _post(proxy, 1)
        snap = counter.snapshot()
    finally:
        proxy.stop()

    # Direct ledger reserve must also fail closed.
    direct = _fresh_root("corrupt-direct", nonce)
    led = PersistentGenerationLedger(direct, limit=C.TOTAL_GENERATION_LIMIT)
    base_ok = led.reserve().granted
    led._history.write_text("{not json\n", encoding="utf-8")
    denied = False
    try:
        denied = led.reserve().granted is False
    except GenerationLedgerCorrupt:
        denied = True
    out = {
        "root": str(root),
        "codes_before_and_after": [before, after],
        "snapshot_after_corrupt": snap,
        "direct_baseline_reserved": base_ok,
        "direct_corrupt_denied": denied,
    }
    out["checks"] = {
        "pre_corrupt_forwarded_ok": before == [200],
        "post_corrupt_refused_429": after == [429],
        "snapshot_corrupt_flag": snap.get("corrupt") is True,
        "snapshot_count_is_none_not_zero": snap.get("count") is None,
        "direct_corrupt_denied": bool(base_ok and denied),
    }
    out["ok"] = all(out["checks"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    nonce = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    MC.BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    _allow_loopback_proxies()

    port = _free_port()
    upstream = ThreadingHTTPServer(("127.0.0.1", port), _FakeHTTP)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{port}/v1"

    payload: dict[str, Any] = {
        "probe": "METHOD-FINAL/gateB-ledger-boundary",
        "utc": nonce,
        "real_provider_generation": 0,
        "scratch_root": str(MC.BOUNDARY_DIR),
        "formal_root_untouched": str(MC.PHASE_DATA_DIR),
        "small_cap": SMALL_CAP,
    }
    try:
        payload["real_injection"] = part_real_injection(nonce, upstream_url)
        payload["forward_refusal_48"] = part_forward_refusal(nonce, upstream_url)
        payload["total_cap_small_equiv"] = part_total_cap_small_equiv(nonce, upstream_url)
        payload["corrupt_failclosed"] = part_corrupt_failclosed(nonce, upstream_url)
        payload["fake_upstream_served"] = _FakeHTTP.served
        payload["formal_root_exists"] = MC.PHASE_DATA_DIR.exists()
        payload["ok"] = all(payload[k]["ok"] for k in (
            "real_injection", "forward_refusal_48", "total_cap_small_equiv",
            "corrupt_failclosed",
        )) and payload["formal_root_exists"] is False
    finally:
        upstream.shutdown()

    out = Path(args.out) if args.out else (MC.METHOD_DIR / "evidence" / f"gateB-{nonce}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v)
                      for k, v in payload.items()}, indent=2))
    print(f"WROTE {out}")
    print(f"GATE-B {'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
