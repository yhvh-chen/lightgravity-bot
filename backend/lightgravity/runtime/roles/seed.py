"""Idempotent seed of the packaged role library into the Store (LG-120).

Rules implemented here (docs/08 §19.6):

* only missing templates are created;
* an existing custom/user template is never overwritten;
* a managed template is upgraded only when its body still equals the last seed
  hash; a user-edited body is preserved and marked ``update_available``;
* ``enabled``/``disabled``, connection/skill/tool references and any unknown
  frontmatter fields are preserved;
* Member instances are never touched, so an upgrade cannot hot-swap an active
  member.

No secret value is written and no remote content is fetched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, cast

from ...store import ConfigInvalid, EntityNotFound, Store, Versioned
from .catalog import (
    AGENCY_COMMIT,
    AGENCY_LICENSE,
    CAPABILITY_TOOL_REFS,
    ROLE_LIBRARY_VERSION,
    RoleTemplate,
    iter_templates,
)

#: The bounded file tools referenced by adapted role templates.
ROLE_TOOL_REFS: tuple[str, ...] = tuple(
    dict.fromkeys(
        ref
        for capability in CAPABILITY_TOOL_REFS
        for ref in CAPABILITY_TOOL_REFS[capability]
    )
)


class _BodyStore(Protocol):
    """The concrete Store accepts Markdown prose; the frozen protocol does not."""

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned: ...

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
        body: str | None = None,
    ) -> Versioned: ...


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class RoleSeedReport:
    """What the idempotent role seed actually did (no secret/prompt echo)."""

    total_templates: int = 0
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped_custom: list[str] = field(default_factory=list)
    update_available: list[str] = field(default_factory=list)
    tools_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": "agency-agents",
            "source_commit": AGENCY_COMMIT,
            "license": AGENCY_LICENSE,
            "library_version": ROLE_LIBRARY_VERSION,
            "total_templates": self.total_templates,
            "created": list(self.created),
            "updated": list(self.updated),
            "unchanged": list(self.unchanged),
            "skipped_custom": list(self.skipped_custom),
            "update_available": list(self.update_available),
            "tools_created": list(self.tools_created),
            "errors": list(self.errors),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "library": "agency-agents",
            "source_commit": AGENCY_COMMIT,
            "total_templates": self.total_templates,
            "created": len(self.created),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "skipped_custom": len(self.skipped_custom),
            "update_available": len(self.update_available),
            "tools_created": len(self.tools_created),
            "errors": len(self.errors),
        }


def _create_content(template: RoleTemplate) -> dict[str, Any]:
    entity = dict(template.entity)
    for key in ("schema", "kind", "id", "revision"):
        entity.pop(key, None)
    return entity


def _is_managed(existing: Mapping[str, Any], template: RoleTemplate) -> bool:
    seed = existing.get("seed")
    if not isinstance(seed, Mapping):
        return False
    return seed.get("library") == "agency-agents" and seed.get("role_id") == template.id


def _desired_seed(template: RoleTemplate, *, update_available: bool = False) -> dict[str, Any]:
    return {
        "library": "agency-agents",
        "role_id": template.id,
        "version": ROLE_LIBRARY_VERSION,
        "source_commit": AGENCY_COMMIT,
        "content_hash": template.body_sha256,
        "update_available": update_available,
        "available_content_hash": template.body_sha256 if update_available else None,
    }


def _ensure_tools(
    store: Store, report: RoleSeedReport, *, actor: str, request_id: str
) -> None:
    for ref in ROLE_TOOL_REFS:
        try:
            store.read("tool", ref)
            continue
        except EntityNotFound:
            pass
        except ConfigInvalid as exc:
            report.errors.append(f"tool:{ref}: existing tool is invalid: {exc}")
            continue
        try:
            cast(_BodyStore, store).create(
                "tool",
                ref,
                {"title": ref, "enabled": True, "implementation": ref},
                actor=actor,
                request_id=f"{request_id}-tool-{ref}",
                body="",
            )
            report.tools_created.append(ref)
        except ConfigInvalid as exc:
            report.errors.append(f"tool:{ref}: {exc}")


def seed_role_library(
    store: Store,
    *,
    actor: str = "lg-runtime",
    request_id: str = "lg-seed-agency-roles",
    templates: Iterable[RoleTemplate] | None = None,
) -> RoleSeedReport:
    """Create/upgrade packaged role templates idempotently.

    ``templates`` is injectable for tests; production always reads the pinned
    package resources.  A single bad role is recorded and does not abort the
    rest of the seed or startup.
    """

    report = RoleSeedReport()
    body_store = cast(_BodyStore, store)
    _ensure_tools(store, report, actor=actor, request_id=request_id)
    for template in templates if templates is not None else iter_templates():
        report.total_templates += 1
        try:
            versioned = store.read("agent", template.id)
        except EntityNotFound:
            try:
                body_store.create(
                    "agent",
                    template.id,
                    _create_content(template),
                    actor=actor,
                    request_id=f"{request_id}-{template.id}",
                    body=template.body,
                )
                report.created.append(template.id)
            except (ConfigInvalid, ValueError) as exc:
                report.errors.append(f"agent:{template.id}: create failed: {exc}")
            continue
        except ConfigInvalid as exc:
            report.errors.append(
                f"agent:{template.id}: existing agent is invalid and was preserved: {exc}"
            )
            continue

        existing = dict(versioned.entity)
        if not _is_managed(existing, template):
            report.skipped_custom.append(template.id)
            continue

        existing_seed = dict(existing.get("seed") or {})
        existing_body_hash = _sha256_text(versioned.body)
        if existing_body_hash != str(existing_seed.get("content_hash")):
            report.update_available.append(template.id)
            if not existing_seed.get("update_available"):
                try:
                    body_store.write(
                        "agent",
                        template.id,
                        {
                            "seed": _desired_seed(template, update_available=True),
                        },
                        expected_revision=versioned.revision,
                        actor=actor,
                        body=None,
                    )
                except (ConfigInvalid, EntityNotFound) as exc:
                    report.errors.append(
                        f"agent:{template.id}: update marker failed: {exc}"
                    )
            continue

        desired_seed = _desired_seed(template)
        updates: dict[str, Any] = {
            "agency_source": dict(template.agency_source),
            "seed": desired_seed,
        }
        for key, value in (
            ("role_category", template.role_category),
            ("capabilities", list(template.capabilities)),
            ("recruitable", template.recruitable),
            ("unsupported_reasons", list(template.unsupported_reasons)),
            ("capability_notes", list(template.capability_notes)),
        ):
            if key not in existing:
                updates[key] = value

        already_current = (
            existing_body_hash == template.body_sha256
            and existing.get("agency_source") == dict(template.agency_source)
            and existing_seed.get("version") == ROLE_LIBRARY_VERSION
            and existing_seed.get("content_hash") == template.body_sha256
            and existing_seed.get("update_available") is False
            and all(key in existing for key in updates)
        )
        if already_current:
            report.unchanged.append(template.id)
            continue
        try:
            body_store.write(
                "agent",
                template.id,
                updates,
                expected_revision=versioned.revision,
                actor=actor,
                body=template.body,
            )
            report.updated.append(template.id)
        except (ConfigInvalid, EntityNotFound) as exc:
            report.errors.append(f"agent:{template.id}: update failed: {exc}")
    return report


__all__ = ["ROLE_TOOL_REFS", "RoleSeedReport", "seed_role_library"]
