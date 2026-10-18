"""LG-210 focused functional checks: durable, hash-only team sessions.

These tests use the real ``TeamAuthService``/``SessionRegistry`` and real local
files only.  No model/provider is called and no existing user store is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.team import TeamAccounts, TeamAuthService
from lightgravity.team.sessions import SessionRegistry

MEMBER_PASSWORD = "fixture-member-password"
ADMIN_PASSWORD = "fixture-admin-password"


def _team_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
        team_mode=True,
    )


def _accounts(settings: Settings) -> TeamAccounts:
    store = TeamAccounts(settings.team_accounts_path)
    store.add("root", ADMIN_PASSWORD, "admin")
    store.add("alice", MEMBER_PASSWORD, "member")
    return store


def _service(
    accounts: TeamAccounts,
    settings: Settings,
    *,
    clock=None,
) -> TeamAuthService:
    return TeamAuthService(
        accounts,
        session_ttl_seconds=60,
        session_store_path=settings.team_accounts_path.parent / "sessions.json",
        **({} if clock is None else {"clock": clock}),
    )


def _login_session(service: TeamAuthService, username: str, password: str) -> str:
    identity = service.authenticate(username, password)
    assert identity is not None
    return service.create_session(identity)


def test_login_survives_restart_and_logout_invalidates(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    accounts = _accounts(settings)
    first = _service(accounts, settings)
    session_id = _login_session(first, "alice", MEMBER_PASSWORD)

    session_path = settings.team_accounts_path.parent / "sessions.json"
    text = session_path.read_text("utf-8")
    assert session_id not in text
    assert hashlib.sha256(session_id.encode("utf-8")).hexdigest() in text
    assert stat.S_IMODE(os.stat(session_path).st_mode) == 0o600
    for path in settings.team_root.rglob("*"):
        if path.is_file():
            assert session_id not in path.read_text("utf-8", errors="ignore")

    # A new service/process construction resolves the same cookie.
    restarted = _service(TeamAccounts(settings.team_accounts_path), settings)
    assert restarted.resolve(session_id) is not None
    assert restarted.resolve(session_id).username == "alice"

    # Logout is durable: a further restart still rejects the token.
    assert restarted.revoke(session_id) is True
    after_logout = _service(TeamAccounts(settings.team_accounts_path), settings)
    assert after_logout.resolve(session_id) is None


def test_password_role_and_disabled_revoke_persisted_sessions(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    accounts = _accounts(settings)
    accounts.add("bob", MEMBER_PASSWORD, "member")
    accounts.add("carol", MEMBER_PASSWORD, "member")
    service = _service(accounts, settings)
    alice_session = _login_session(service, "alice", MEMBER_PASSWORD)
    bob_session = _login_session(service, "bob", MEMBER_PASSWORD)
    carol_session = _login_session(service, "carol", MEMBER_PASSWORD)
    assert service.resolve(alice_session) is not None
    assert service.resolve(bob_session) is not None
    assert service.resolve(carol_session) is not None

    accounts.set_password("alice", "changed-password")
    accounts.set_role("bob", "admin")
    accounts.set_enabled("carol", False)

    restarted = _service(TeamAccounts(settings.team_accounts_path), settings)
    # Account facts are still authoritative across restarts; a cached persisted
    # role/version never keeps an old session alive.
    assert restarted.resolve(alice_session) is None
    assert restarted.resolve(bob_session) is None
    assert restarted.resolve(carol_session) is None


def test_expiry_is_absolute_across_restart(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    accounts = _accounts(settings)
    now = {"value": 1000.0}
    service = _service(accounts, settings, clock=lambda: now["value"])
    session_id = _login_session(service, "alice", MEMBER_PASSWORD)
    assert service.resolve(session_id) is not None

    now["value"] += 61
    restarted = _service(
        TeamAccounts(settings.team_accounts_path),
        settings,
        clock=lambda: now["value"],
    )
    assert restarted.resolve(session_id) is None
    session_path = settings.team_accounts_path.parent / "sessions.json"
    document = json.loads(session_path.read_text("utf-8"))
    assert hashlib.sha256(session_id.encode("utf-8")).hexdigest() not in document[
        "sessions"
    ]


def test_corrupt_store_fails_closed_then_new_login_recovers(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    accounts = _accounts(settings)
    service = _service(accounts, settings)
    old_session = _login_session(service, "alice", MEMBER_PASSWORD)
    session_path = settings.team_accounts_path.parent / "sessions.json"
    session_path.write_text('{"schema": broken', "utf-8")

    restarted = _service(TeamAccounts(settings.team_accounts_path), settings)
    assert restarted.resolve(old_session) is None

    # Reauthentication is the recovery path; a fresh login starts a clean,
    # valid hash-only store and the old token still cannot resolve.
    identity = restarted.authenticate("alice", MEMBER_PASSWORD)
    assert identity is not None
    new_session = restarted.create_session(identity)
    assert new_session != old_session
    assert restarted.resolve(old_session) is None
    assert restarted.resolve(new_session) is not None
    document = json.loads(session_path.read_text("utf-8"))
    assert document["schema"] == "lightgravity.team.sessions/v1"
    assert old_session not in session_path.read_text("utf-8")


def test_symlinked_store_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside-sessions.json"
    owner = SessionRegistry(60, store_path=outside)
    session = owner.create("alice", "member")
    assert outside.read_text("utf-8")

    team_root = tmp_path / "team"
    team_root.mkdir()
    link = team_root / "sessions.json"
    link.symlink_to(outside)
    linked = SessionRegistry(60, store_path=link)
    assert linked.resolve(session.session_id) is None

    # A successful login replaces the link with a regular controlled file and
    # never writes the plaintext token through to the link target.
    before = outside.read_text("utf-8")
    replacement = linked.create("bob", "admin")
    assert outside.read_text("utf-8") == before
    assert not link.is_symlink()
    assert linked.resolve(replacement.session_id) is not None


_WORKER = r'''
import json, sys
from pathlib import Path
import lightgravity.api.app  # noqa: F401 - assemble the package before team imports
from lightgravity.team.sessions import SessionRegistry

path, mode = sys.argv[1:3]
registry = SessionRegistry(60, store_path=Path(path))
if mode == "create":
    registry.create("child", "member")
    print(json.dumps({"created": True}))
elif mode == "revoke":
    print(json.dumps({"revoked": registry.revoke(sys.stdin.readline().strip())}))
else:
    raise SystemExit("unknown mode")
'''


def _run_worker(path: Path, mode: str, token: str | None = None) -> dict:
    backend = Path(__file__).resolve().parents[2] / "backend"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(backend)}
    completed = subprocess.run(
        [sys.executable, "-c", _WORKER, str(path), mode],
        input=f"{token}\n" if token else "",
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    # Child stdout carries only metadata; the token is passed via stdin.
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_other_process_create_and_revoke_keep_store_consistent(tmp_path: Path) -> None:
    path = tmp_path / "team" / "sessions.json"
    local = SessionRegistry(60, store_path=path)
    local_session = local.create("alice", "member")
    assert _run_worker(path, "create") == {"created": True}

    document = json.loads(path.read_text("utf-8"))
    assert len(document["sessions"]) == 2
    assert local.resolve(local_session.session_id) is not None

    assert _run_worker(path, "revoke", local_session.session_id) == {"revoked": True}
    restarted = SessionRegistry(60, store_path=path)
    assert restarted.resolve(local_session.session_id) is None


async def _client_for(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_real_app_restart_keeps_cookie_and_logout_survives(
    tmp_path: Path,
) -> None:
    settings = _team_settings(tmp_path)
    _accounts(settings)

    first_app = create_app(settings)
    async with first_app.router.lifespan_context(first_app):
        async with await _client_for(first_app) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": MEMBER_PASSWORD},
            )
            assert login.status_code == 200
            cookie = client.cookies.get("lg_session")
            assert cookie

    # A fresh app object with the same data root models a service restart.
    second_app = create_app(settings)
    async with second_app.router.lifespan_context(second_app):
        async with await _client_for(second_app) as client:
            headers = {"cookie": f"lg_session={cookie}"}
            me = await client.get("/api/v1/auth/me", headers=headers)
            assert me.json() == {
                "mode": "team",
                "authenticated": True,
                "username": "alice",
                "role": "member",
            }
            assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204

    third_app = create_app(settings)
    async with third_app.router.lifespan_context(third_app):
        async with await _client_for(third_app) as client:
            me = await client.get(
                "/api/v1/auth/me", headers={"cookie": f"lg_session={cookie}"}
            )
            assert me.json()["authenticated"] is False
