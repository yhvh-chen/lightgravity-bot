"""Config resolution and startup data-dir behaviour (LG-002)."""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.app import create_app
from lightgravity.config import Settings


def test_from_env_defaults_are_relative() -> None:
    settings = Settings.from_env({})
    assert settings.data_dir == Path("bot-data")
    assert settings.workspace_root == Path("bot-data/workspaces")
    assert settings.secret_store == Path("secrets")
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_from_env_overrides(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "LIGHTGRAVITY_DATA_DIR": str(tmp_path / "d"),
            "LIGHTGRAVITY_HOST": "127.0.0.1",
            "LIGHTGRAVITY_PORT": "9001",
        }
    )
    assert settings.data_dir == tmp_path / "d"
    assert settings.workspace_root == tmp_path / "d" / "workspaces"
    assert settings.port == 9001


async def test_startup_creates_separate_data_dir(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    assert not settings.data_dir.exists()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert settings.data_dir.is_dir()
