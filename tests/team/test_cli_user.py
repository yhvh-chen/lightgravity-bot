"""CLI team-account bootstrap: getpass input and read-only list (LG-050 §2)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from lightgravity.cli import main
from lightgravity import cli


def test_settings_from_args_preserves_team_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIGHTGRAVITY_TEAM_MODE", "1")
    monkeypatch.setenv("LIGHTGRAVITY_TEAM_BOT_MENTION", "!lg")
    monkeypatch.setenv("LIGHTGRAVITY_TEAM_COOKIE_SECURE", "true")
    args = cli._build_parser().parse_args(
        [
            "start",
            "--data-dir",
            str(tmp_path / "data"),
            "--no-frontend",
        ]
    )
    settings = cli._settings_from_args(args)
    assert settings.team_mode is True
    assert settings.team_bot_mention == "!lg"
    assert settings.team_cookie_secure is True


def _run_add(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, password: str, *extra: str
) -> int:
    calls: list[str] = []

    def fake_getpass(prompt: str = "") -> str:
        calls.append(prompt)
        return password

    monkeypatch.setattr("lightgravity.cli.getpass.getpass", fake_getpass)
    return main(
        [
            "user",
            "add",
            "--data-dir",
            str(tmp_path / "data"),
            "--username",
            "admin",
            "--role",
            "admin",
            *extra,
        ]
    )


def test_user_add_writes_0600_and_does_not_print_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_add(tmp_path, monkeypatch, "top-secret-pw")
    assert rc == 0
    out = capsys.readouterr().out
    assert "top-secret-pw" not in out
    assert "pbkdf2" not in out
    path = tmp_path / "data" / "team" / "accounts.json"
    assert path.is_file()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    document = json.loads(path.read_text("utf-8"))
    assert document["accounts"]["admin"]["role"] == "admin"
    assert "top-secret-pw" not in path.read_text("utf-8")


def test_user_add_password_mismatch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = iter(["one", "two"])
    monkeypatch.setattr(
        "lightgravity.cli.getpass.getpass", lambda prompt="": next(responses)
    )
    rc = main(
        [
            "user",
            "add",
            "--data-dir",
            str(tmp_path / "data"),
            "--username",
            "admin",
            "--role",
            "admin",
        ]
    )
    assert rc == 1
    assert not (tmp_path / "data" / "team" / "accounts.json").exists()


def test_user_list_prints_only_safe_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_add(tmp_path, monkeypatch, "pw") == 0
    capsys.readouterr()
    rc = main(
        ["user", "list", "--data-dir", str(tmp_path / "data")]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accounts"] == [
        {
            "username": "admin",
            "role": "admin",
            "created_at": payload["accounts"][0]["created_at"],
        }
    ]
    assert "password" not in json.dumps(payload)
    assert "hash" not in json.dumps(payload)


def test_user_add_duplicate_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_add(tmp_path, monkeypatch, "pw") == 0
    assert _run_add(tmp_path, monkeypatch, "pw") == 1
