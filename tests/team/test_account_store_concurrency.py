"""Independent-instance/process writes share one authoritative transaction lock."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from lightgravity.team.accounts import TeamAccounts, TeamAccountsLastAdminError


@pytest.mark.parametrize("operation", ["add", "disable", "seed"])
def test_paused_writer_cannot_overwrite_another_instance(tmp_path: Path, operation: str) -> None:
    path = tmp_path / "team" / "accounts.json"
    if operation != "seed":
        initial = TeamAccounts(path)
        initial.add("admin", "fixture-password", "admin")
        initial.add("alice", "fixture-password")
    entered = threading.Event()
    release = threading.Event()
    second_finished = threading.Event()

    class PausedAccounts(TeamAccounts):
        def _write(self, data):
            entered.set()
            assert release.wait(5), "writer was not released"
            super()._write(data)

    first = PausedAccounts(path)
    second = TeamAccounts(path)

    def first_change():
        if operation == "add":
            return first.add("carol", "fixture-password")
        if operation == "disable":
            return first.set_enabled("alice", False)
        return first.ensure_default_admin(username="seed_a", password="fixture-password")

    def second_change():
        try:
            if operation == "add":
                return second.set_enabled("alice", False)
            if operation == "disable":
                return second.add("carol", "fixture-password")
            return second.ensure_default_admin(username="seed_b", password="fixture-password")
        finally:
            second_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future1 = pool.submit(first_change)
        try:
            assert entered.wait(5)
            future2 = pool.submit(second_change)
            # Old code lets the second operation finish against the same old
            # snapshot. With the fix it waits until the first writer commits.
            second_finished.wait(0.5)
        finally:
            release.set()
        result1 = future1.result(timeout=5)
        result2 = future2.result(timeout=5)
    if operation == "seed":
        assert sorted([result1, result2]) == [False, True]
        assert len(second.list_accounts()) == 1
    else:
        assert second.get("carol") is not None
        assert second.get("alice").enabled is False


_WORKER = r'''
import json, pathlib, sys, time
import lightgravity.api.app
from lightgravity.team.accounts import TeamAccounts, TeamAccountsLastAdminError
path, mode, username, ready, gate = sys.argv[1:]
store = TeamAccounts(path)
pathlib.Path(ready).touch()
end = time.monotonic() + 10
while not pathlib.Path(gate).exists():
    if time.monotonic() > end: raise RuntimeError("start gate timeout")
    time.sleep(.005)
try:
    if mode == "toggle":
        count = 60
        for n in range(count): store.set_enabled(username, n % 2 == 1)
        result = {"accepted": count}
    elif mode == "seed":
        result = {"seeded": store.ensure_default_admin(username=username, password="fixture-password")}
    elif mode == "disable":
        store.set_enabled(username, False)
        result = {"changed": True}
    elif mode == "demote":
        store.set_role(username, "member")
        result = {"changed": True}
    else: raise ValueError(mode)
except TeamAccountsLastAdminError:
    result = {"changed": False}
print(json.dumps(result))
'''


def _processes(tmp_path: Path, path: Path, operations: list[tuple[str, str]]) -> list[dict]:
    backend = Path(__file__).resolve().parents[2] / "backend"
    # Explicit small allowlist: no inherited model/provider/token credentials.
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(backend)}
    gate = tmp_path / "start"
    children = []
    try:
        for i, (mode, name) in enumerate(operations):
            ready = tmp_path / f"ready-{i}"
            child = subprocess.Popen([sys.executable, "-c", _WORKER, str(path), mode, name, str(ready), str(gate)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children.append((child, ready))
        end = time.monotonic() + 10
        while not all(ready.exists() for _, ready in children):
            assert time.monotonic() < end, "child import/start timed out"
            assert all(child.poll() is None for child, _ in children)
            time.sleep(.01)
        gate.touch()
        result = []
        for child, _ in children:
            stdout, stderr = child.communicate(timeout=20)
            assert child.returncode == 0, stderr
            result.append(json.loads(stdout))
        return result
    finally:
        for child, _ in children:
            if child.poll() is None:
                child.kill()
                child.wait()


def test_real_processes_preserve_every_accepted_revision(tmp_path: Path) -> None:
    path = tmp_path / "team" / "accounts.json"
    store = TeamAccounts(path)
    for name in ("alice", "bob"):
        store.add(name, "fixture-password")
    results = _processes(tmp_path, path, [("toggle", "alice"), ("toggle", "bob")])
    for name, result in zip(("alice", "bob"), results):
        account = store.get(name)
        assert account.revision == account.session_version == result["accepted"] == 60
        assert account.enabled is True


@pytest.mark.parametrize("second_action", ["disable", "demote"])
def test_real_processes_cannot_remove_last_active_admin(tmp_path: Path, second_action: str) -> None:
    path = tmp_path / "team" / "accounts.json"
    store = TeamAccounts(path)
    store.add("admin_a", "fixture-password", "admin")
    store.add("admin_b", "fixture-password", "admin")
    results = _processes(tmp_path, path, [("disable", "admin_a"), (second_action, "admin_b")])
    assert sorted(result["changed"] for result in results) == [False, True]
    assert len([a for a in store.list_accounts() if a.enabled and a.role == "admin"]) == 1


def test_real_processes_seed_one_admin_only(tmp_path: Path) -> None:
    path = tmp_path / "team" / "accounts.json"
    results = _processes(tmp_path, path, [("seed", "seed_a"), ("seed", "seed_b")])
    assert sorted(result["seeded"] for result in results) == [False, True]
    assert len(TeamAccounts(path).list_accounts()) == 1


def test_write_and_guard_exceptions_release_the_store_lock(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "team" / "accounts.json"
    first = TeamAccounts(path)
    second = TeamAccounts(path)
    first.add("admin", "fixture-password", "admin")
    with pytest.raises(TeamAccountsLastAdminError):
        first.set_enabled("admin", False)
    second.add("alice", "fixture-password")
    with monkeypatch.context() as patch:
        def fail_write(_data):
            raise OSError("fixture disk failure")
        patch.setattr(first, "_write", fail_write)
        with pytest.raises(OSError, match="fixture disk failure"):
            first.set_enabled("alice", False)
    assert second.set_enabled("alice", False).revision == 1
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_aliases_share_stable_lock_and_preserve_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "team" / "accounts.json"
    first = TeamAccounts(path)
    first.add("admin", "fixture-password", "admin")
    document = json.loads(path.read_text())
    document["custom_top"] = {"retained": True}
    document["accounts"]["admin"]["custom_account"] = "retained"
    path.write_text(json.dumps(document))
    alias = tmp_path / "team-alias"
    alias.symlink_to(path.parent, target_is_directory=True)
    second = TeamAccounts(alias / "accounts.json")
    lock_path = path.parent / "accounts.json.lock"
    lock_inode = lock_path.stat().st_ino
    second.add("alice", "fixture-password")
    first.set_password("admin", "new-fixture-password")
    assert second.get("alice") is not None
    assert second.authenticate("admin", "new-fixture-password") is not None
    updated = json.loads(path.read_text())
    assert updated["custom_top"] == {"retained": True}
    assert updated["accounts"]["admin"]["custom_account"] == "retained"
    assert lock_path.stat().st_ino == lock_inode
    assert lock_path.stat().st_mode & 0o777 == 0o600
