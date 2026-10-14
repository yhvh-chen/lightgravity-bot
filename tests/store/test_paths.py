"""Workspace path authorization (lexical and symlink containment)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lightgravity.store import FileStore, PathOutsideWorkspace


@pytest.mark.parametrize(
    "relative",
    ["../escape", "../../etc/passwd", "/etc/passwd", "a/../../escape", "sub/../../escape"],
)
def test_escapes_are_blocked(store: FileStore, relative: str) -> None:
    with pytest.raises(PathOutsideWorkspace):
        store.resolve_path(relative, write=False)


def test_absolute_path_inside_root_is_allowed(store: FileStore, workspace_root: Path) -> None:
    resolved = store.resolve_path(str(workspace_root / "nested" / "file.txt"), write=True)
    assert resolved == (workspace_root / "nested" / "file.txt").resolve()


def test_relative_path_inside_root(store: FileStore, workspace_root: Path) -> None:
    resolved = store.resolve_path("nested/file.txt", write=True)
    assert resolved == (workspace_root / "nested" / "file.txt").resolve()


def test_symlink_escape_is_blocked(store: FileStore, workspace_root: Path) -> None:
    link = workspace_root / "link"
    os.symlink("/tmp", link)
    with pytest.raises(PathOutsideWorkspace):
        store.resolve_path("link/secret", write=False)


def test_symlink_inside_root_is_allowed(store: FileStore, workspace_root: Path) -> None:
    (workspace_root / "real").mkdir()
    os.symlink(workspace_root / "real", workspace_root / "alias")
    assert store.resolve_path("alias/f.txt", write=False) == (workspace_root / "real").resolve() / "f.txt"
