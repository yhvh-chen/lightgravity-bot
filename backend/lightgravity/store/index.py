"""Rebuildable derived index (LG-004, docs/08 §7).

The index is never a second source of truth: it is rebuilt by scanning the
authoritative Markdown files and can be discarded at any time.  Rebuild also
surfaces duplicate-id and invalid-entity diagnostics instead of hiding them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .entities import RESOURCE_DIRS
from .errors import ConfigInvalid
from .frontmatter import as_mapping, parse_document, plain
from .models import Diagnostic, TaskSummary
from .entities import validate_entity


@dataclass(frozen=True, slots=True)
class IndexEntry:
    kind: str
    entity_id: str
    data: dict[str, Any]
    revision: int
    path: str


@dataclass(frozen=True, slots=True)
class BuildResult:
    entries: dict[tuple[str, str], IndexEntry]
    diagnostics: list[Diagnostic]
    scanned: int


def _candidate_files(data_dir: Path) -> list[tuple[str, str, Path]]:
    """Yield ``(kind, expected_id, path)`` for every authoritative file."""

    found: list[tuple[str, str, Path]] = []
    tasks_dir = data_dir / "tasks"
    if tasks_dir.is_dir():
        for task_dir in sorted(tasks_dir.iterdir()):
            path = task_dir / "TASK.md"
            if task_dir.is_dir() and path.is_file():
                found.append(("task", task_dir.name, path))
    for kind, container, filename in (
        ("run", data_dir / "runs", "RUN.md"),
        ("subtask", data_dir / "subtasks", "SUBTASK.md"),
    ):
        if container.is_dir():
            for entity_dir in sorted(container.iterdir()):
                path = entity_dir / filename
                if entity_dir.is_dir() and path.is_file():
                    found.append((kind, entity_dir.name, path))
    members_dir = data_dir / "members"
    if members_dir.is_dir():
        for path in sorted(members_dir.glob("*.md")):
            found.append(("member", path.stem, path))
    resources_root = data_dir / "resources"
    for kind, dirname in RESOURCE_DIRS.items():
        kind_dir = resources_root / dirname
        if not kind_dir.is_dir():
            continue
        if kind == "skill":
            for entity_dir in sorted(kind_dir.iterdir()):
                path = entity_dir / "SKILL.md"
                if entity_dir.is_dir() and path.is_file():
                    found.append((kind, entity_dir.name, path))
        else:
            for path in sorted(kind_dir.glob("*.md")):
                found.append((kind, path.stem, path))
    settings_file = data_dir / "settings" / "SETTINGS.md"
    if settings_file.is_file():
        found.append(("settings", "settings", settings_file))
    return found


def build_index(data_dir: Path) -> BuildResult:
    entries: dict[tuple[str, str], IndexEntry] = {}
    diagnostics: list[Diagnostic] = []
    scanned = 0
    for kind, expected_id, path in _candidate_files(data_dir):
        scanned += 1
        try:
            data, _ = parse_document(path.read_text("utf-8"), source=str(path))
            parsed = plain(data)
        except ConfigInvalid as exc:
            for diag in exc.diagnostics:
                diagnostics.append(
                    Diagnostic(
                        code=str(diag.get("code", "config_invalid")),
                        message=str(diag.get("message", "invalid frontmatter")),
                        location=str(diag.get("location", str(path))),
                        detail={"path": str(path)},
                    )
                )
            continue
        static = validate_entity(kind, parsed, source=str(path))
        errors = [d for d in static if d.level == "error"]
        if errors:
            diagnostics.extend(errors)
            continue
        entity_id = str(parsed.get("id"))
        if entity_id != expected_id and path.name not in ("SETTINGS.md", "SKILL.md"):
            diagnostics.append(
                Diagnostic(
                    code="id_path_mismatch",
                    message=f"id {entity_id!r} does not match file location {expected_id!r}",
                    location=str(path),
                )
            )
        key = (kind, entity_id)
        if key in entries:
            diagnostics.append(
                Diagnostic(
                    code="duplicate_id",
                    message=f"duplicate {kind} id {entity_id!r}",
                    location=str(path),
                    detail={"first_path": entries[key].path},
                )
            )
            continue
        revision = parsed.get("revision")
        entries[key] = IndexEntry(
            kind=kind,
            entity_id=entity_id,
            data=parsed,
            revision=revision if isinstance(revision, int) and not isinstance(revision, bool) else 0,
            path=str(path),
        )
    return BuildResult(entries=entries, diagnostics=diagnostics, scanned=scanned)


def task_summary(entry: IndexEntry) -> TaskSummary:
    data = entry.data
    queue = as_mapping(data.get("queue"))
    requirements = data.get("requirements_revision")
    return TaskSummary(
        id=entry.entity_id,
        title=str(data.get("title", "")),
        status=str(data.get("status", "")),
        phase=str(data.get("phase", "")),
        revision=entry.revision,
        requirements_revision=(
            requirements
            if isinstance(requirements, int) and not isinstance(requirements, bool)
            else 0
        ),
        queue_state=str(queue.get("state", "not_queued")),
        owner=queue.get("owner") if isinstance(queue.get("owner"), str) else None,
        lease_expires_at=(
            queue.get("lease_expires_at")
            if isinstance(queue.get("lease_expires_at"), str)
            else None
        ),
        archived=bool(data.get("archived", False)),
        path=entry.path,
    )


__all__ = ["IndexEntry", "BuildResult", "build_index", "task_summary"]
