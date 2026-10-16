#!/usr/bin/env python3
"""LG-050 independent QA — real HTTP authentication / team-chat matrix.

Runs the *candidate* application (this QA worktree) with a real uvicorn server
on a temporary loopback port and a throwaway data root.  It uses two independent
cookie jars for two accounts and exercises the acceptance matrix over the wire.

Deliberately NOT used here:
* no real model / SDK / executor (a counting stub proves zero model-side calls);
* no .env, no real secrets, no existing ``bot-data``, no resident ``8123``;
* no FastAPI TestClient — plain ``http.client``/``urllib`` against the socket.

Passwords below are throwaway QA fixtures generated in the temp data root, not
real credentials.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.team import TeamAccounts  # noqa: E402

QA_PASSWORD = "qa-throwaway-pass-123!"  # QA fixture only
ADMIN = ("alice", "admin")
MEMBER = ("bob", "member")
EVIL_ORIGIN = "http://evil.example"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body
        try:
            self.json = json.loads(body.decode("utf-8")) if body else None
        except ValueError:
            self.json = None

    def __repr__(self) -> str:  # pragma: no cover - diagnostic
        return f"<Response {self.status} {self.body[:160]!r}>"


class Client:
    """Minimal HTTP client with its own cookie jar (one per independent account)."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.cookies: dict[str, str] = {}

    def _connect(self) -> http.client.HTTPConnection:
        parsed = urllib.parse.urlparse(self.base)
        return http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=15)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        read: bool = True,
    ) -> Response:
        conn = self._connect()
        hdrs = dict(headers or {})
        if self.cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            for name, value in resp.getheaders():
                if name.lower() == "set-cookie":
                    cookie = value.split(";", 1)[0]
                    if "=" in cookie:
                        key, val = cookie.split("=", 1)
                        if val:
                            self.cookies[key.strip()] = val
                        else:
                            self.cookies.pop(key.strip(), None)
            body = resp.read() if read else b""
            return Response(resp.status, dict(resp.getheaders()), body)
        finally:
            conn.close()

    def get(self, path: str, **kw) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> Response:
        return self.request("POST", path, **kw)


def make_server(*, team_mode: bool, workspace_root: Path | None, counters: dict, data_dir: Path, secret: Path, ttl: int = 3600):
    settings = Settings(
        data_dir=data_dir,
        workspace_root=workspace_root if workspace_root is not None else data_dir / "workspaces",
        secret_store=secret,
        team_mode=team_mode,
        team_session_ttl_seconds=ttl,
    )
    app = create_app(settings)
    # QA-only instrumentation: wrap the app's *own* coordinator (built on the
    # broadcasting store, so SSE/live events stay real) with counting stubs.
    # These counters prove whether the classifier/responder ran; there is still
    # no executor or model behind them.
    coordinator = app.state.coordinator
    real_classifier = coordinator._classifier  # noqa: SLF001

    def counting_classifier(content):
        counters["classifier"] += 1
        return real_classifier(content)

    def counting_responder(prompt, classification):
        counters["responder"] += 1
        return "QA-STUB-REPLY"

    coordinator._classifier = counting_classifier  # noqa: SLF001
    coordinator._responder = counting_responder  # noqa: SLF001
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("server did not start")
    return server, f"http://127.0.0.1:{port}", settings, app


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps({"checks": self.checks, "failed": len(self.failed)}, indent=2))


def sse_reader(base: str, cookies: dict[str, str], stop: threading.Event, out: dict) -> None:
    """Read an SSE stream until it closes (or ``stop``), recording timing."""

    parsed = urllib.parse.urlparse(base)
    try:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=30)
        conn.request(
            "GET",
            "/api/v1/events/stream",
            headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())},
        )
        resp = conn.getresponse()
        out["status"] = resp.status
        out["opened_at"] = time.time()
        out["events"] = 0
        if resp.status != 200:
            out["closed_at"] = time.time()
            conn.close()
            return
        for raw in resp:
            if stop.is_set():
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                out["events"] += 1
        out["closed_at"] = time.time()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        out.setdefault("closed_at", time.time())


def main() -> int:
    report = Report()
    counters = {"classifier": 0, "responder": 0}
    root = Path(tempfile.mkdtemp(prefix="lg050-qa-"))
    data_dir = root / "data"
    # Misconfigure the workspace root to CONTAIN the team accounts dir on purpose,
    # so the Files protection (not lexical path escape) is what must stop the read.
    secret = root / "secrets"
    # Throwaway accounts.
    accounts_path = data_dir / "team" / "accounts.json"
    accounts = TeamAccounts(accounts_path)
    accounts.add(ADMIN[0], QA_PASSWORD, ADMIN[1])
    accounts.add(MEMBER[0], QA_PASSWORD, MEMBER[1])
    accounts_hash_present = "hash" in accounts_path.read_text() and "salt" in accounts_path.read_text()

    server, base, settings, app = make_server(
        team_mode=True,
        workspace_root=data_dir,
        counters=counters,
        data_dir=data_dir,
        secret=secret,
    )
    anon = Client(base)
    admin = Client(base)
    member = Client(base)

    try:
        # ---------------------------------------------------------------- login
        r = anon.get("/api/v1/auth/me")
        report.check(
            "T01a anon /auth/me reports team+unauthenticated",
            r.status == 200 and r.json.get("mode") == "team" and r.json.get("authenticated") is False,
            f"{r.status} {r.json}",
        )
        r = admin.post("/api/v1/auth/login", json_body={"username": ADMIN[0], "password": QA_PASSWORD})
        report.check("T01b admin login 200", r.status == 200 and r.json.get("role") == "admin", f"{r.status} {r.json}")
        r = member.post("/api/v1/auth/login", json_body={"username": MEMBER[0], "password": QA_PASSWORD})
        report.check("T01c member login 200", r.status == 200 and r.json.get("role") == "member", f"{r.status} {r.json}")
        r = admin.get("/api/v1/auth/me")
        report.check(
            "T01d admin /auth/me identifies alice",
            r.status == 200 and r.json == {"mode": "team", "authenticated": True, "username": "alice", "role": "admin"},
            f"{r.status} {r.json}",
        )
        # bad password
        bad = Client(base).post("/api/v1/auth/login", json_body={"username": ADMIN[0], "password": "wrong-password"})
        report.check("T01e wrong password 401", bad.status == 401, f"{bad.status} {bad.json}")

        # ------------------------------------------------- anonymous 401 sweep
        anon_paths = [
            "/api/v1/tasks",
            "/api/v1/conversations/global/messages",
            "/api/v1/files/download?path=x",
            "/api/v1/files/content?path=x",
            "/api/v1/sources",
            "/api/v1/search?q=x",
            "/api/v1/events/stream",
            "/api/v1/settings",
            "/api/v1/resources/skill/none",
        ]
        for path in anon_paths:
            r = anon.get(path)
            report.check(f"T02 anon {path} -> 401", r.status == 401, f"{r.status} {str(r.json)[:120]}")

        # ------------------------------------------ legacy X-LG-Token no bypass
        r = anon.get("/api/v1/tasks", headers={"X-LG-Token": "anything"})
        report.check("T03a anon + X-LG-Token -> 401", r.status == 401, f"{r.status}")
        r = anon.get("/api/v1/conversations/global/messages", headers={"X-LG-Token": "anything"})
        report.check("T03b anon + X-LG-Token (history) -> 401", r.status == 401, f"{r.status}")
        r = member.get("/api/v1/settings", headers={"X-LG-Token": "anything"})
        report.check("T03c member + X-LG-Token cannot reach /settings -> 403", r.status == 403, f"{r.status}")

        # ------------------------------------------------ shared group chat
        r1 = admin.post(
            "/api/v1/conversations/global/messages",
            json_body={"message_id": "qa-alice-1", "content": "hello from alice"},
        )
        report.check(
            "T04a admin ordinary message recorded, reply null, no task",
            r1.status == 200 and r1.json.get("kind") == "recorded" and r1.json.get("reply") is None and r1.json.get("data", {}).get("creates_task") is False,
            f"{r1.status} {r1.json}",
        )
        r2 = member.post(
            "/api/v1/conversations/global/messages",
            json_body={"message_id": "qa-bob-1", "content": "hi from bob"},
        )
        report.check("T04b member ordinary message recorded", r2.status == 200 and r2.json.get("kind") == "recorded", f"{r2.status}")
        hist = admin.get("/api/v1/conversations/global/messages?limit=1000")
        items = hist.json["items"] if hist.json else []
        authors = {m["message_id"]: m["message"].get("author") for m in items}
        alice_author = authors.get("qa-alice-1")
        bob_author = authors.get("qa-bob-1")
        report.check(
            "T04c shared history shows real authors",
            alice_author == {"kind": "user", "username": "alice", "role": "admin"}
            and bob_author == {"kind": "user", "username": "bob", "role": "member"},
            f"alice={alice_author} bob={bob_author}",
        )
        # Both accounts see the same history.
        member_hist = member.get("/api/v1/conversations/global/messages?limit=1000")
        report.check(
            "T04d member sees the same shared history",
            member_hist.status == 200
            and {m["message_id"] for m in member_hist.json["items"]} >= {"qa-alice-1", "qa-bob-1"},
            f"{member_hist.status}",
        )

        # ------------------------------------------------ forged author rejected
        r = member.post(
            "/api/v1/conversations/global/messages",
            json_body={"message_id": "qa-forge-1", "content": "forged", "author": {"kind": "user", "username": "alice", "role": "admin"}},
        )
        report.check("T05a global message with client author -> 422", r.status == 422, f"{r.status} {r.json}")
        hist = admin.get("/api/v1/conversations/global/messages?limit=1000")
        forged = [m for m in hist.json["items"] if m["message_id"] == "qa-forge-1"]
        report.check("T05b forged message not persisted", not forged, f"found={len(forged)}")
        # Task message path must reject a client author too.
        r = member.post(
            "/api/v1/tasks/qa-none/messages",
            json_body={"message_id": "qa-forge-task", "content": "x", "author": {"kind": "user", "username": "alice", "role": "admin"}},
        )
        report.check("T05c task message with client author -> 422", r.status == 422, f"{r.status}")

        # ------------------------------- ordinary messages: zero model-side calls
        counters["classifier"] = 0
        counters["responder"] = 0
        for i in range(3):
            member.post(
                "/api/v1/conversations/global/messages",
                json_body={"message_id": f"qa-zero-{i}", "content": f"ordinary chatter {i}"},
            )
        report.check(
            "T06 ordinary chat triggers zero classifier/responder (no model)",
            counters["classifier"] == 0 and counters["responder"] == 0,
            f"counters={counters}",
        )
        tasks = admin.get("/api/v1/tasks")
        report.check("T06b ordinary chat created no Task", tasks.status == 200 and len(tasks.json.get("items", [])) == 0, f"{tasks.status} {len(tasks.json.get('items', [])) if tasks.json else '?'}")

        # ------------------------------------------------ @bot exactly once
        counters["classifier"] = 0
        counters["responder"] = 0
        r = member.post(
            "/api/v1/conversations/global/messages",
            json_body={"message_id": "qa-bot-1", "content": "@bot hello team"},
        )
        report.check(
            "T07a @bot triggers exactly one classifier+responder",
            r.status == 200 and counters["classifier"] == 1 and counters["responder"] == 1 and (r.json or {}).get("kind") in {"direct", "bounded_read"},
            f"{r.status} counters={counters} body={str(r.json)[:120]}",
        )

        # ------------------- duplicate message_id, concurrent @bot -> one reply
        counters["classifier"] = 0
        counters["responder"] = 0
        dup_results = []

        def send_dup():
            c = Client(base)
            c.cookies = dict(member.cookies)
            dup_results.append(c.post("/api/v1/conversations/global/messages", json_body={"message_id": "qa-dup-1", "content": "@bot duplicate please"}))

        threads = [threading.Thread(target=send_dup) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        report.check(
            "T08a concurrent duplicate @bot -> exactly one responder/classifier",
            counters["responder"] == 1 and counters["classifier"] == 1,
            f"counters={counters} statuses={[x.status for x in dup_results]}",
        )
        hist = admin.get("/api/v1/conversations/global/messages?limit=1000")
        dup_rows = [m for m in hist.json["items"] if m["message_id"] == "qa-dup-1"]
        report.check("T08b duplicate message persisted once", len(dup_rows) == 1, f"rows={len(dup_rows)}")

        # ---------------------- concurrent ordinary messages: no sequence loss
        n = 24
        sent = []
        lock = threading.Lock()

        def send_ordinary(i):
            c = Client(base)
            c.cookies = dict(member.cookies)
            resp = c.post(
                "/api/v1/conversations/global/messages",
                json_body={"message_id": f"qa-conc-{i}", "content": f"concurrent {i}"},
            )
            with lock:
                sent.append((i, resp.status))

        ts = [threading.Thread(target=send_ordinary, args=(i,)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        hist = admin.get("/api/v1/conversations/global/messages?limit=1000")
        seqs = [m["seq"] for m in hist.json["items"]]
        contents = {m["message"]["content"] for m in hist.json["items"]}
        missing = [f"concurrent {i}" for i in range(n) if f"concurrent {i}" not in contents]
        report.check(
            "T09a all concurrent ordinary messages persisted",
            not missing and len(seqs) == len(set(seqs)),
            f"missing={missing[:5]} dup_seqs={len(seqs) - len(set(seqs))}",
        )
        report.check("T09b sequence numbers strictly increasing (server order)", seqs == sorted(seqs), f"n={len(seqs)}")

        # ------------------------------------------------- cursor catch-up
        first_page = admin.get("/api/v1/conversations/global/messages?limit=2")
        cursor = first_page.json["next_cursor"]
        report.check("T10a first page returns cursor", bool(cursor) and len(first_page.json["items"]) == 2, f"cursor={cursor}")
        catchup = admin.get(f"/api/v1/conversations/global/messages?after={urllib.parse.quote(cursor)}&limit=1000")
        catch_ids = {m["message_id"] for m in catchup.json["items"]}
        report.check(
            "T10b cursor returns only newer messages incl. concurrent set",
            catchup.status == 200 and "qa-conc-0" in catch_ids and all(
                m["seq"] > first_page.json["items"][1]["seq"] for m in catchup.json["items"]
            ),
            f"n={len(catch_ids)}",
        )

        # ---------------------- member cannot admin-write + no writes land
        r = member.get("/api/v1/settings")
        report.check("T11a member GET /settings -> 403", r.status == 403, f"{r.status}")
        r = member.request("PATCH", "/api/v1/settings", json_body={"actor": "bob"})
        report.check("T11b member PATCH /settings -> 403", r.status == 403, f"{r.status} {r.json}")
        r = member.request("PUT", "/api/v1/settings/credentials/qa_cred", json_body={"value": "qa-not-a-real-secret"})
        report.check("T11c member PUT credential -> 403", r.status == 403, f"{r.status} {r.json}")
        r = member.request("PATCH", "/api/v1/resources/skill/none", json_body={"description": "hacked"})
        report.check("T11d member PATCH /resources -> 403", r.status == 403, f"{r.status} {r.json}")
        # No credential file must have been written.
        cred_files = list(secret.rglob("*")) if secret.exists() else []
        report.check("T11e member credential write left no secret file", not [p for p in cred_files if p.is_file()], f"files={cred_files}")

        # ------------- Task resource_proposal indirect path (403, no write)
        ct = member.post("/api/v1/tasks", json_body={"request_id": "qa-task-req-1", "title": "QA proposal target", "objective": "test"})
        task_id = ct.json.get("task_id") if ct.json else None
        report.check("T12a member can create a task (business write allowed)", ct.status == 200 and bool(task_id), f"{ct.status} {task_id}")
        if task_id:
            r = member.post(
                f"/api/v1/tasks/{task_id}/messages",
                json_body={
                    "message_id": "qa-proposal-1",
                    "content": "please apply",
                    "resource_proposal": {"kind": "skill", "action": "create", "id": "qa-evil", "content": "x"},
                },
            )
            report.check("T12b member resource_proposal -> 403", r.status == 403, f"{r.status} {str(r.json)[:160]}")
            msgs = admin.get(f"/api/v1/tasks/{task_id}/messages?limit=1000")
            proposal_rows = [m for m in msgs.json["items"] if m["message_id"] == "qa-proposal-1"]
            report.check("T12c rejected proposal not persisted", not proposal_rows, f"rows={len(proposal_rows)}")
            res = admin.get("/api/v1/resources/skill/qa-evil")
            report.check("T12d rejected proposal created no resource", res.status == 404, f"{res.status}")

        # ---------------------------- account hash file not readable via Files
        report.check("T13a accounts file really contains a hash+salt", accounts_hash_present, f"path={accounts_path}")
        r = admin.get("/api/v1/files/content?path=" + urllib.parse.quote("team/accounts.json"))
        err = (r.json or {}).get("error", {})
        report.check(
            "T13b /files/content cannot read accounts.json",
            r.status != 200 and err.get("code") == "path_outside_workspace",
            f"{r.status} {str(r.json)[:160]}",
        )
        r = admin.get("/api/v1/files/download?path=" + urllib.parse.quote("team/accounts.json"))
        report.check("T13c /files/download cannot read accounts.json", r.status != 200, f"{r.status}")
        r = admin.get("/api/v1/files?path=" + urllib.parse.quote("team"))
        report.check("T13d /files listing does not list accounts.json", r.status != 200 or "accounts.json" not in json.dumps(r.json or {}), f"{r.status}")

        # ------------------------------------------- cross-origin write reject
        r = admin.request(
            "PUT",
            "/api/v1/settings/credentials/qa_crossorigin",
            json_body={"value": "qa-not-a-real-secret"},
            headers={"Origin": EVIL_ORIGIN},
        )
        rerr = (r.json or {}).get("error", {})
        report.check(
            "T14a cross-origin credential write rejected",
            r.status in {401, 403} and "loopback" in rerr.get("message", ""),
            f"{r.status} {str(r.json)[:160]}",
        )
        cross = Client(base)
        r = cross.post(
            "/api/v1/auth/login",
            json_body={"username": ADMIN[0], "password": QA_PASSWORD},
            headers={"Origin": EVIL_ORIGIN},
        )
        report.check("T14b cross-origin login -> 403", r.status == 403, f"{r.status} {str(r.json)[:120]}")
        # same-origin (no Origin) still works
        r = Client(base).post("/api/v1/auth/login", json_body={"username": ADMIN[0], "password": QA_PASSWORD})
        report.check("T14c loopback login still works", r.status == 200, f"{r.status}")

        # ------------------------------ logout invalidates + expired SSE stream
        r = member.post("/api/v1/auth/logout")
        report.check("T15a logout 204", r.status == 204, f"{r.status}")
        r = member.get("/api/v1/auth/me")
        report.check("T15b /auth/me after logout unauthenticated", r.status == 200 and r.json.get("authenticated") is False, f"{r.status} {r.json}")
        r = member.get("/api/v1/tasks")
        report.check("T15c old cookie after logout -> 401", r.status == 401, f"{r.status}")

        # Re-login a dedicated client for the SSE-expiry test.
        sse_client = Client(base)
        sse_client.post("/api/v1/auth/login", json_body={"username": MEMBER[0], "password": QA_PASSWORD})
        sse_out: dict = {}
        stop = threading.Event()
        reader = threading.Thread(target=sse_reader, args=(base, sse_client.cookies, stop, sse_out), daemon=True)
        reader.start()
        time.sleep(0.6)
        opened_status = sse_out.get("status")
        # Force expiry of this session in the server's registry to exercise the
        # live-session check (controller holds the real service object).
        service = app.state.context.team
        sid = next(iter(sse_client.cookies.values()))
        with service._sessions._lock:  # noqa: SLF001 - QA-only expiry control
            sess = service._sessions._sessions.get(sid)
            if sess is not None:
                service._sessions._sessions[sid] = type(sess)(
                    session_id=sess.session_id,
                    username=sess.username,
                    role=sess.role,
                    expires_at=time.time() - 1,
                )
        # keep feeding live events while the session expires
        for i in range(12):
            admin.post("/api/v1/tasks", json_body={"request_id": f"qa-ev-{i}", "title": f"ev {i}", "objective": "x"})
            time.sleep(0.2)
        reader.join(timeout=12)
        closed = sse_out.get("closed_at")
        report.check("T15d open SSE stream opened", opened_status == 200, f"status={opened_status}")
        report.check(
            "T15e open SSE stream is torn down by session expiry",
            closed is not None and reader.is_alive() is False,
            f"events={sse_out.get('events')} open={sse_out.get('opened_at')} closed={closed} err={sse_out.get('error')}",
        )
        r = sse_client.get("/api/v1/tasks")
        report.check("T15f expired cookie -> 401", r.status == 401, f"{r.status}")

    except Exception:  # noqa: BLE001
        report.check("EXCEPTION", False, traceback.format_exc())
    finally:
        server.should_exit = True
        time.sleep(0.4)
        # -------------------------------- single-user mode smoke (separate app)
        try:
            counters2 = {"classifier": 0, "responder": 0}
            sdir = root / "single"
            server2, base2, _, app2 = make_server(team_mode=False, workspace_root=None, counters=counters2, data_dir=sdir, secret=root / "secrets2")
            try:
                c = Client(base2)
                r = c.get("/api/v1/auth/me")
                report.check(
                    "T16a single mode /auth/me = single authenticated",
                    r.status == 200 and r.json.get("mode") == "single" and r.json.get("authenticated") is True,
                    f"{r.status} {r.json}",
                )
                r = c.get("/api/v1/tasks")
                report.check("T16b single mode /tasks reachable on loopback", r.status == 200, f"{r.status}")
                r = c.get("/api/v1/version")
                report.check("T16c single mode version reachable", r.status == 200 and "contract_version" in (r.json or {}), f"{r.status}")
            finally:
                server2.should_exit = True
                time.sleep(0.3)
        except Exception:  # noqa: BLE001
            report.check("EXCEPTION single", False, traceback.format_exc())

    outdir = Path(__file__).resolve().parent
    report.dump(outdir / "qa-http-results.json")
    print("\n==== SUMMARY ====")
    print(f"checks={len(report.checks)} failed={len(report.failed)}")
    for f in report.failed:
        print(f"  FAIL {f['name']} :: {f['detail']}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
