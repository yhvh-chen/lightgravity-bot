"""Read and validate the packaged agency-agents role library (LG-120).

Runtime reads only package resources; there is no network access, clone, or
upstream script execution.  The catalog exposes two things:

* the full browsable role templates (including unsupported/research-only roles);
* a small, reusable capability -> role-ref map for the scheduler (LG-121).

Capability metadata never grants a tool.  The safe tool refs below are the
existing bounded workspace file tools, chosen only from the role's declared
capability class.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any, Iterable, Mapping

from ...store.frontmatter import parse_document, plain

AGENCY_REPOSITORY = "https://github.com/msitarzewski/agency-agents"
AGENCY_COMMIT = "652b2692f8d8ec2b1f1a38e559073e287dfdc469"
AGENCY_LICENSE = "MIT"
AGENCY_COPYRIGHT = "Copyright (c) 2025 AgentLand Contributors"
ROLE_LIBRARY_VERSION = 1

#: docs/08 §19.6 controlled capability vocabulary.
CAPABILITIES: tuple[str, ...] = (
    "research",
    "design",
    "implementation",
    "verification",
    "writing",
    "review",
)

#: The only tool refs a role template may receive.  They are the existing
#: bounded workspace file tools; research receives none because no web tool is
#: available in this version.
CAPABILITY_TOOL_REFS: Mapping[str, tuple[str, ...]] = {
    "research": (),
    "design": ("view-file", "create-file", "edit-file"),
    "implementation": ("view-file", "create-file", "edit-file"),
    "verification": ("view-file",),
    "writing": ("view-file", "create-file", "edit-file"),
    "review": ("view-file",),
}

EXECUTABLE_CAPABILITIES: tuple[str, ...] = tuple(
    capability for capability in CAPABILITIES if CAPABILITY_TOOL_REFS[capability]
)

_DIVISION_DEFAULT: Mapping[str, str] = {
    "academic": "research",
    "design": "design",
    "engineering": "implementation",
    "finance": "writing",
    "game-development": "implementation",
    "gis": "implementation",
    "healthcare": "writing",
    "marketing": "writing",
    "paid-media": "writing",
    "product": "writing",
    "project-management": "writing",
    "research": "research",
    "sales": "writing",
    "security": "review",
    "spatial-computing": "implementation",
    "specialized": "writing",
    "support": "writing",
    "testing": "verification",
}

_REVIEW_RE = re.compile(r"\b(review|reviewer|audit|auditor|compliance|red[ -]?team)\b", re.I)
_VERIFY_RE = re.compile(
    r"\b(verification|verify|validator|validation|tester|testing|qa|quality[ -]?assurance)\b",
    re.I,
)
_DESIGN_RE = re.compile(
    r"\b(design|designer|ux|ui|visual|brand|creative|artist|illustrator|cartographer|cartography)\b",
    re.I,
)
_WRITE_RE = re.compile(
    r"\b(writer|writing|editor|copywriter|content|document|narrative|storyteller|"
    r"translator|localization|proposal|book)\b",
    re.I,
)
_IMPL_RE = re.compile(
    r"\b(engineer|engineering|developer|architect|scripter|programmer|coder|"
    r"builder|automator|sre|devops|implementation)\b",
    re.I,
)
_RESEARCH_RE = re.compile(
    r"\b(research|researcher|analyst|scientist|synthesist|intelligence|trend|economist)\b",
    re.I,
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_ROLE_CAPABILITIES = frozenset(CAPABILITIES)


def _order(capabilities: Iterable[str]) -> tuple[str, ...]:
    values = set(capabilities)
    return tuple(capability for capability in CAPABILITIES if capability in values)


def classify_role(division: str, slug: str, name: str) -> tuple[str, ...]:
    """Reproducible capability rule for one upstream role.

    Only the division, filename slug and upstream ``name`` are inputs.  The
    description is intentionally not used so prose wording cannot silently
    change scheduler capabilities.  Review/verification win; otherwise
    design/writing/implementation keyword classes are checked, then the
    division default.  Research is added as a limitation marker and is never
    executable without a web tool.
    """

    text = f"{slug} {name}"
    capabilities: set[str] = set()
    if _REVIEW_RE.search(text):
        capabilities.add("review")
    if _VERIFY_RE.search(text):
        capabilities.add("verification")
    if not capabilities:
        if _DESIGN_RE.search(text):
            capabilities.add("design")
        elif _WRITE_RE.search(text):
            capabilities.add("writing")
        elif _IMPL_RE.search(text):
            capabilities.add("implementation")
        else:
            capabilities.add(_DIVISION_DEFAULT.get(division, "writing"))
    if _RESEARCH_RE.search(text):
        capabilities.add("research")
    return _order(capabilities)


def _tool_refs(capabilities: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for capability in CAPABILITIES:
        if capability not in capabilities:
            continue
        for ref in CAPABILITY_TOOL_REFS[capability]:
            if ref not in ordered:
                ordered.append(ref)
    return tuple(ordered)


def _unsupported_reasons(capabilities: tuple[str, ...]) -> tuple[str, ...]:
    executable = [capability for capability in capabilities if capability in EXECUTABLE_CAPABILITIES]
    if executable:
        return ()
    if "research" in capabilities:
        return (
            "unsupported: research requires a web tool, which is not available in this version",
        )
    return ("unsupported: no scheduler capability mapping",)


def _capability_notes(capabilities: tuple[str, ...]) -> tuple[str, ...]:
    notes: list[str] = []
    if "research" in capabilities:
        notes.append(
            "research is not executable in this version (no web tool); other declared "
            "capabilities may still be recruitable"
        )
    return tuple(notes)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class RoleTemplate:
    id: str
    title: str
    description: str
    division: str
    role_category: str
    capabilities: tuple[str, ...]
    recruitable: bool
    unsupported_reasons: tuple[str, ...]
    capability_notes: tuple[str, ...]
    tool_refs: tuple[str, ...]
    agency_source: Mapping[str, Any]
    seed: Mapping[str, Any]
    body: str
    body_sha256: str
    template_sha256: str
    upstream: Mapping[str, Any]
    entity: Mapping[str, Any]

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "division": self.division,
            "role_category": self.role_category,
            "capabilities": list(self.capabilities),
            "recruitable": self.recruitable,
            "unsupported_reasons": list(self.unsupported_reasons),
            "capability_notes": list(self.capability_notes),
            "tool_refs": list(self.tool_refs),
            "agency_source": dict(self.agency_source),
            "seed": dict(self.seed),
            "body_sha256": self.body_sha256,
            "template_sha256": self.template_sha256,
            "upstream": dict(self.upstream),
        }


def _agency_root() -> resources.abc.Traversable:
    return resources.files(__package__).joinpath("agency")


def load_manifest() -> dict[str, Any]:
    raw = _agency_root().joinpath("MANIFEST.json").read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("agency role manifest is not a JSON object")
    if data.get("source", {}).get("commit") != AGENCY_COMMIT:
        raise ValueError("agency role manifest commit does not match the pinned commit")
    if data.get("source", {}).get("license") != AGENCY_LICENSE:
        raise ValueError("agency role manifest license does not match MIT")
    return data


def iter_templates() -> Iterable[RoleTemplate]:
    template_dir = _agency_root().joinpath("templates")
    paths = sorted(
        (path for path in template_dir.iterdir() if path.name.endswith(".md")),
        key=lambda path: path.name,
    )
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        frontmatter, body = parse_document(text, source=f"agency/templates/{path.name}")
        entity = plain(frontmatter)
        role_id = str(entity.get("id") or path.name[:-3])
        if not _SLUG_RE.match(role_id):
            raise ValueError(f"invalid packaged role id {role_id!r}")
        expected_id = path.name[:-3]
        if role_id != expected_id:
            raise ValueError(f"packaged role id {role_id!r} does not match {path.name!r}")
        capabilities = tuple(str(item) for item in entity.get("capabilities") or ())
        unknown = [item for item in capabilities if item not in _ROLE_CAPABILITIES]
        if unknown:
            raise ValueError(f"role {role_id!r} has unknown capabilities {unknown!r}")
        seed = entity.get("seed")
        if not isinstance(seed, Mapping):
            raise ValueError(f"role {role_id!r} has no seed metadata")
        body_sha = _sha256_bytes(body.encode("utf-8"))
        if seed.get("content_hash") != body_sha:
            raise ValueError(f"role {role_id!r} seed content hash is stale")
        agency_source = entity.get("agency_source")
        if not isinstance(agency_source, Mapping):
            raise ValueError(f"role {role_id!r} has no agency_source")
        if agency_source.get("commit") != AGENCY_COMMIT:
            raise ValueError(f"role {role_id!r} has a non-pinned source commit")
        if agency_source.get("license") != AGENCY_LICENSE:
            raise ValueError(f"role {role_id!r} has a non-MIT source license")
        upstream = entity.get("upstream")
        if not isinstance(upstream, Mapping):
            raise ValueError(f"role {role_id!r} has no upstream metadata")
        yield RoleTemplate(
            id=role_id,
            title=str(entity.get("title") or role_id),
            description=str(upstream.get("description") or ""),
            division=str(upstream.get("division") or ""),
            role_category=str(entity.get("role_category") or "agency"),
            capabilities=capabilities,
            recruitable=bool(entity.get("recruitable", False)),
            unsupported_reasons=tuple(str(item) for item in entity.get("unsupported_reasons") or ()),
            capability_notes=tuple(str(item) for item in entity.get("capability_notes") or ()),
            tool_refs=tuple(str(item) for item in entity.get("tool_refs") or ()),
            agency_source=dict(agency_source),
            seed=dict(seed),
            body=body,
            body_sha256=body_sha,
            template_sha256=_sha256_bytes(raw),
            upstream=dict(upstream),
            entity=entity,
        )


def capability_catalog(
    templates: Iterable[RoleTemplate | Mapping[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """Return the reusable scheduler catalog: capability -> recruitable role ids."""

    rows = list(iter_templates() if templates is None else templates)
    result: dict[str, list[str]] = {
        capability: [] for capability in EXECUTABLE_CAPABILITIES
    }
    for row in rows:
        if isinstance(row, RoleTemplate):
            capabilities = row.capabilities
            recruitable = row.recruitable
            role_id = row.id
        else:
            capabilities = tuple(str(item) for item in row.get("capabilities") or ())
            recruitable = bool(row.get("recruitable"))
            role_id = str(row.get("id") or "")
        if not recruitable or not role_id:
            continue
        for capability in capabilities:
            if capability in result and role_id not in result[capability]:
                result[capability].append(role_id)
    for refs in result.values():
        refs.sort()
    return result


def build_expected_role_capabilities(
    division: str, slug: str, title: str
) -> dict[str, Any]:
    """Public helper used by the reproducible manifest check/tests."""

    capabilities = classify_role(division, slug, title)
    tool_refs = _tool_refs(capabilities)
    return {
        "capabilities": list(capabilities),
        "tool_refs": list(tool_refs),
        "recruitable": bool(tool_refs) and any(
            capability in EXECUTABLE_CAPABILITIES for capability in capabilities
        ),
        "unsupported_reasons": list(_unsupported_reasons(capabilities)),
        "capability_notes": list(_capability_notes(capabilities)),
    }


__all__ = [
    "AGENCY_COMMIT",
    "AGENCY_COPYRIGHT",
    "AGENCY_LICENSE",
    "AGENCY_REPOSITORY",
    "CAPABILITIES",
    "CAPABILITY_TOOL_REFS",
    "EXECUTABLE_CAPABILITIES",
    "ROLE_LIBRARY_VERSION",
    "RoleTemplate",
    "build_expected_role_capabilities",
    "capability_catalog",
    "classify_role",
    "iter_templates",
    "load_manifest",
]
