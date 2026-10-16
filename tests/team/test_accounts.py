"""Accounts fact source: hashing, atomic 0600 writes, no cleartext (LG-050)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from lightgravity.team.accounts import (
    PASSWORD_ALGO,
    TeamAccounts,
    TeamAccountsError,
    hash_password,
    verify_password,
)


def test_hash_and_verify_roundtrip() -> None:
    record = hash_password("correct horse battery staple")
    assert record["algo"] == PASSWORD_ALGO
    assert record["iterations"] >= 200_000
    assert verify_password("correct horse battery staple", record) is True
    assert verify_password("wrong", record) is False
    # The cleartext never appears in the record.
    assert "correct horse" not in json.dumps(record)


def test_unknown_algo_is_refused() -> None:
    assert verify_password("x", {"algo": "md5", "salt": "a", "hash": "b"}) is False


def test_add_writes_0600_and_no_cleartext(tmp_path: Path) -> None:
    path = tmp_path / "data" / "team" / "accounts.json"
    store = TeamAccounts(path)
    store.add("alice", "s3cret-pw", "member")
    assert path.is_file()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    text = path.read_text("utf-8")
    assert "s3cret-pw" not in text
    data = json.loads(text)
    assert data["schema"] == "lightgravity.team/v1"
    assert data["accounts"]["alice"]["role"] == "member"
    assert data["accounts"]["alice"]["password"]["algo"] == PASSWORD_ALGO


def test_duplicate_and_invalid_role_rejected(tmp_path: Path) -> None:
    store = TeamAccounts(tmp_path / "accounts.json")
    store.add("alice", "pw", "member")
    with pytest.raises(TeamAccountsError):
        store.add("alice", "pw2", "member")
    with pytest.raises(TeamAccountsError):
        store.add("bob", "pw", "root")
    assert [account.username for account in store.list_accounts()] == ["alice"]


def test_authenticate_unknown_user_returns_none(tmp_path: Path) -> None:
    store = TeamAccounts(tmp_path / "accounts.json")
    store.add("alice", "pw", "admin")
    assert store.authenticate("alice", "pw") is not None
    assert store.authenticate("alice", "nope") is None
    assert store.authenticate("ghost", "pw") is None


def test_existing_file_is_replaced_atomically(tmp_path: Path) -> None:
    store = TeamAccounts(tmp_path / "accounts.json")
    store.add("alice", "pw", "member")
    store.add("bob", "pw", "admin")
    accounts = {account.username: account for account in store.list_accounts()}
    assert set(accounts) == {"alice", "bob"}
    assert accounts["bob"].role == "admin"


def test_unknown_fields_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("alice", "pw", "member")
    document = json.loads(path.read_text("utf-8"))
    document["future_top_level"] = {"note": "keep me"}
    document["accounts"]["alice"]["extension"] = 42
    path.write_text(json.dumps(document), "utf-8")
    # A new controlled write must not drop the unknown fields.
    store.add("bob", "pw", "admin")
    rewritten = json.loads(path.read_text("utf-8"))
    assert rewritten["future_top_level"] == {"note": "keep me"}
    assert rewritten["accounts"]["alice"]["extension"] == 42
