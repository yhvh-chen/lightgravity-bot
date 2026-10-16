"""LG-062 account store: enable/role, revisions, last-admin lock, legacy read.

Store-level coverage for the additive fields (``enabled``, ``revision``,
``session_version``) and the last-active-administrator invariant.  Password
cleartext, salts and hashes never appear in public responses (see the API
suite in ``test_account_management_api.py``).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from lightgravity.team.accounts import (
    TeamAccounts,
    TeamAccountsConflictError,
    TeamAccountsError,
    TeamAccountsLastAdminError,
)


def _store(tmp_path: Path) -> TeamAccounts:
    return TeamAccounts(tmp_path / "team" / "accounts.json")


def test_new_account_defaults_are_enabled_revision_zero(tmp_path: Path) -> None:
    store = _store(tmp_path)
    account = store.add("alice", "pw", "member")
    assert account.enabled is True
    assert account.revision == 0
    assert account.session_version == 0
    document = json.loads(store.path.read_text("utf-8"))
    raw = document["accounts"]["alice"]
    assert raw["enabled"] is True
    assert raw["revision"] == 0
    assert raw["session_version"] == 0


def test_legacy_account_without_new_fields_loads_compatibly(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("alice", "pw", "member")
    document = json.loads(path.read_text("utf-8"))
    for key in ("enabled", "revision", "session_version"):
        document["accounts"]["alice"].pop(key, None)
    path.write_text(json.dumps(document), "utf-8")

    reopened = TeamAccounts(path)
    account = reopened.get("alice")
    assert account is not None
    assert account.enabled is True
    assert account.revision == 0
    assert account.session_version == 0
    # A legacy account can still authenticate.
    assert reopened.authenticate("alice", "pw") is not None


def test_disabled_account_cannot_authenticate_but_keeps_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add("alice", "pw", "member")
    updated = store.set_enabled("alice", False)
    assert updated.enabled is False
    assert updated.role == "member"
    assert store.authenticate("alice", "pw") is None
    # Identity/record survives; it is a disable, not a delete.
    assert store.get("alice") is not None


def test_enable_disable_bumps_revision_and_session_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.add("alice", "pw", "member")
    disabled = store.set_enabled("alice", False, expected_revision=created.revision)
    assert disabled.revision == created.revision + 1
    assert disabled.session_version == created.session_version + 1
    enabled = store.set_enabled("alice", True, expected_revision=disabled.revision)
    assert enabled.enabled is True
    assert enabled.revision == disabled.revision + 1
    # Re-enabling does not reset the auth revision, so an old cookie stays dead.
    assert enabled.session_version == disabled.session_version + 1


def test_noop_update_does_not_bump_revision(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.add("alice", "pw", "member")
    same = store.set_role("alice", "member", expected_revision=created.revision)
    assert same.revision == created.revision
    assert same.session_version == created.session_version


def test_role_change_bumps_session_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.add("alice", "pw", "member")
    promoted = store.set_role("alice", "admin", expected_revision=created.revision)
    assert promoted.role == "admin"
    assert promoted.revision == created.revision + 1
    assert promoted.session_version == created.session_version + 1


def test_password_change_bumps_session_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.add("alice", "pw", "member")
    changed = store.set_password("alice", "new-pw", expected_revision=created.revision)
    assert changed.revision == created.revision + 1
    assert changed.session_version == created.session_version + 1
    assert store.authenticate("alice", "new-pw") is not None
    assert store.authenticate("alice", "pw") is None


def test_stale_revision_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.add("alice", "pw", "member")
    store.set_role("alice", "admin", expected_revision=created.revision)
    with pytest.raises(TeamAccountsConflictError):
        store.set_role("alice", "member", expected_revision=created.revision)
    # The store is unchanged by the rejected write.
    assert store.get("alice").role == "admin"


def test_unknown_fields_survive_enable_role_password_changes(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = TeamAccounts(path)
    store.add("alice", "pw", "member")
    document = json.loads(path.read_text("utf-8"))
    document["future_top"] = {"keep": 1}
    document["accounts"]["alice"]["extension"] = {"x": 1}
    path.write_text(json.dumps(document), "utf-8")

    store.set_enabled("alice", False)
    store.set_role("alice", "admin")
    store.set_password("alice", "new-pw")
    rewritten = json.loads(path.read_text("utf-8"))
    assert rewritten["future_top"] == {"keep": 1}
    assert rewritten["accounts"]["alice"]["extension"] == {"x": 1}
    assert rewritten["accounts"]["alice"]["role"] == "admin"


def test_last_active_admin_cannot_be_disabled_or_demoted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    admin = store.add("admin", "pw", "admin")
    member = store.add("alice", "pw", "member")

    with pytest.raises(TeamAccountsLastAdminError):
        store.set_enabled("admin", False, expected_revision=admin.revision)
    with pytest.raises(TeamAccountsLastAdminError):
        store.set_role("admin", "member", expected_revision=admin.revision)
    # A disabled admin does not count, so it cannot guard the invariant alone.
    assert store.get("admin").enabled is True
    # The unrelated member is unaffected.
    assert store.get("alice").revision == member.revision


def test_last_admin_guard_allows_change_when_another_active_admin_exists(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = store.add("admin1", "pw", "admin")
    store.add("admin2", "pw", "admin")
    demoted = store.set_role("admin1", "member", expected_revision=first.revision)
    assert demoted.role == "member"
    # Now admin2 is the last active admin and is protected.
    with pytest.raises(TeamAccountsLastAdminError):
        store.set_enabled("admin2", False)
    # A disabled admin is not an active admin and does not count.
    store.set_enabled("admin1", True)
    store.set_role("admin1", "admin")
    assert len([a for a in store.list_accounts() if a.role == "admin" and a.enabled]) == 2


def test_disabled_admin_is_not_counted_as_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add("admin", "pw", "admin")
    store.add("other", "pw", "admin")
    # Disabling the second admin is allowed; disabling the first then fails.
    store.set_enabled("other", False)
    with pytest.raises(TeamAccountsLastAdminError):
        store.set_enabled("admin", False)


def test_concurrent_demotions_never_leave_zero_active_admins(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add("admin1", "pw", "admin")
    store.add("admin2", "pw", "admin")

    def disable(name: str) -> bool:
        try:
            store.set_enabled(name, False)
            return True
        except TeamAccountsLastAdminError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(disable, ["admin1", "admin2"]))
    assert sorted(results) == [False, True]
    active = [a for a in store.list_accounts() if a.role == "admin" and a.enabled]
    assert len(active) == 1


def test_concurrent_role_changes_never_leave_zero_active_admins(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add("admin1", "pw", "admin")
    store.add("admin2", "pw", "admin")

    def demote(name: str) -> bool:
        try:
            store.set_role(name, "member")
            return True
        except TeamAccountsLastAdminError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(demote, ["admin1", "admin2"]))
    assert results.count(True) == 1
    active = [a for a in store.list_accounts() if a.role == "admin" and a.enabled]
    assert len(active) == 1


def test_ensure_default_admin_sets_new_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.ensure_default_admin() is True
    account = store.get("admin")
    assert account is not None
    assert account.enabled is True
    assert account.revision == 0
    assert account.session_version == 0


def test_unknown_account_operations_raise(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TeamAccountsError):
        store.set_enabled("ghost", False)
    with pytest.raises(TeamAccountsError):
        store.set_role("ghost", "admin")
    with pytest.raises(TeamAccountsError):
        store.update_account("ghost", enabled=False)
