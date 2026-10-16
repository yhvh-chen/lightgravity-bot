"""LG-061 requested default admin, safe reset and restart semantics.

Covers the additive first-initialisation contract:

* an empty (missing or zero-account) team store seeds requested ``admin`` with
  role ``admin`` and stores only a salted PBKDF2 hash;
* any existing store -- including one whose password was changed -- is never
  rewritten, so a restart cannot reset a password;
* single-user mode never reads or creates the team account file;
* ``TeamAccounts.set_password`` preserves roles, other accounts and unknown
  fields, and login only ever succeeds via the stored hash.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import pytest

from lightgravity.api.app import create_app
from lightgravity.api.bootstrap import StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken
from lightgravity.team import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    TeamAccounts,
    TeamAccountsError,
)
from lightgravity.team.accounts import PASSWORD_ALGO

LOGIN = "/api/v1/auth/login"


def _team_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
        team_mode=True,
    )


def _single_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def test_default_credentials_are_the_requested_values() -> None:
    assert DEFAULT_ADMIN_USERNAME == "admin"
    assert DEFAULT_ADMIN_PASSWORD == "admin123"


def test_ensure_default_admin_seeds_only_an_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "data" / "team" / "accounts.json"
    store = TeamAccounts(path)

    assert store.ensure_default_admin() is True
    # A second first-init (or a restart) is a no-op, not a password reset.
    before = path.read_text("utf-8")
    assert store.ensure_default_admin() is False
    assert path.read_text("utf-8") == before

    accounts = store.list_accounts()
    assert [account.username for account in accounts] == ["admin"]
    assert accounts[0].role == "admin"
    assert accounts[0].password["algo"] == PASSWORD_ALGO
    assert store.authenticate("admin", "admin123") is not None
    assert store.authenticate("admin", "wrong") is None

    # Stored hash only: no cleartext, mode 0600.
    text = path.read_text("utf-8")
    assert "admin123" not in text
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_ensure_default_admin_treats_zero_account_file_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "team" / "accounts.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": "lightgravity.team/v1", "accounts": {}}), "utf-8")
    store = TeamAccounts(path)
    assert store.ensure_default_admin() is True
    assert [account.username for account in store.list_accounts()] == ["admin"]


def test_ensure_default_admin_never_overwrites_a_custom_admin(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("admin", "custom-pw", "admin")
    before = path.read_text("utf-8")

    assert store.ensure_default_admin() is False
    assert path.read_text("utf-8") == before
    assert store.authenticate("admin", "custom-pw") is not None
    assert store.authenticate("admin", "admin123") is None


def test_ensure_default_admin_leaves_a_non_admin_store_alone(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("alice", "alice-pw", "member")

    assert store.ensure_default_admin() is False
    assert [account.username for account in store.list_accounts()] == ["alice"]
    assert store.authenticate("alice", "alice-pw") is not None


def test_restart_after_changed_password_does_not_reset(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("admin", "original-pw", "admin")
    store.set_password("admin", "changed-pw")

    # A restart constructs a new store and re-runs the first-init check.
    restarted = TeamAccounts(path)
    assert restarted.ensure_default_admin() is False
    assert restarted.authenticate("admin", "changed-pw") is not None
    assert restarted.authenticate("admin", "original-pw") is None
    assert restarted.authenticate("admin", "admin123") is None


def test_set_password_preserves_everything_but_the_hash(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("admin", "old-pw", "admin")
    store.add("alice", "alice-pw", "member")

    document = json.loads(path.read_text("utf-8"))
    document["future_top_level"] = {"note": "keep me"}
    document["accounts"]["admin"]["extension"] = {"x": 1}
    document["accounts"]["alice"]["extension"] = 7
    alice_hash = document["accounts"]["alice"]["password"]["hash"]
    path.write_text(json.dumps(document), "utf-8")

    updated = store.set_password("admin", "new-pw")
    assert updated.role == "admin"

    rewritten = json.loads(path.read_text("utf-8"))
    assert rewritten["future_top_level"] == {"note": "keep me"}
    assert rewritten["accounts"]["admin"]["extension"] == {"x": 1}
    assert rewritten["accounts"]["alice"]["extension"] == 7
    assert rewritten["accounts"]["admin"]["role"] == "admin"
    assert rewritten["accounts"]["alice"]["password"]["hash"] == alice_hash
    assert "new-pw" not in path.read_text("utf-8")

    assert store.authenticate("admin", "new-pw") is not None
    assert store.authenticate("admin", "old-pw") is None
    assert store.authenticate("alice", "alice-pw") is not None


def test_set_password_rejects_unknown_account(tmp_path: Path) -> None:
    store = TeamAccounts(tmp_path / "accounts.json")
    store.add("alice", "pw", "member")
    with pytest.raises(TeamAccountsError):
        store.set_password("ghost", "pw")


def test_persisted_hash_is_the_only_login_authority(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.ensure_default_admin()
    # A brand-new instance reading the same file still authenticates.
    reopened = TeamAccounts(path)
    assert reopened.authenticate("admin", "admin123") is not None
    # There is no accept-any fallback for a malformed/absent record.
    assert reopened.authenticate("ghost", "admin123") is None
    assert reopened.authenticate("admin", "") is None


@pytest.fixture
def team_settings(tmp_path: Path) -> Settings:
    return _team_settings(tmp_path)


async def test_team_app_first_init_seeds_login(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                LOGIN,
                json={
                    "username": DEFAULT_ADMIN_USERNAME,
                    "password": DEFAULT_ADMIN_PASSWORD,
                },
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"username": "admin", "role": "admin"}
            me = await client.get("/api/v1/auth/me")
            assert me.json() == {
                "mode": "team",
                "authenticated": True,
                "username": "admin",
                "role": "admin",
            }


async def test_read_only_initialisation_does_not_seed(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    app = create_app(settings, initialize_team_accounts=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                LOGIN,
                json={
                    "username": DEFAULT_ADMIN_USERNAME,
                    "password": DEFAULT_ADMIN_PASSWORD,
                },
            )
            assert response.status_code == 401
    assert not settings.team_accounts_path.exists()


def test_startup_seeding_is_gated_for_read_only_status(tmp_path: Path) -> None:
    settings = _team_settings(tmp_path)
    build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "environment"),
            serve_frontend=False,
            wire_real_executor=False,
            seed_default_admin=False,
        )
    )
    assert not settings.team_accounts_path.exists()

    build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "environment"),
            serve_frontend=False,
            wire_real_executor=False,
        )
    )
    assert settings.team_accounts_path.is_file()
    assert TeamAccounts(settings.team_accounts_path).authenticate("admin", "admin123")


async def test_single_user_mode_never_provisions_team_accounts(tmp_path: Path) -> None:
    settings = _single_settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            me = await client.get("/api/v1/auth/me")
            assert me.json()["mode"] == "single"
    assert not settings.team_accounts_path.exists()
