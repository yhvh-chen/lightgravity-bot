"""Adapter capability declaration (docs/08 §8 ``AdapterCapabilities``).

Capabilities describe the *installed* SDK version and the limits observed by
the LG-003 probe.  They are deliberately conservative:

* ``compile`` only claims that static configuration compilation is implemented.
* Execution capabilities that the probe verified on a non-Gemini endpoint are
  separated from the product's unverified Gemini/Vertex path.
* MCP, Triggers, internal delegation and ``search_web`` stay ``False`` for the
  first version so the UI/reporting cannot present them as usable.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

#: Distribution name pinned by LG-005 in the root ``pyproject.toml``.
SDK_DISTRIBUTION = "google-antigravity"
#: Version verified by the LG-003 probe and locked for the first version.
SDK_PINNED_VERSION = "0.1.22"


def installed_sdk_version() -> str | None:
    """Return the installed distribution version, or ``None`` when absent."""

    try:
        return version(SDK_DISTRIBUTION)
    except PackageNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - metadata must never break compilation
        return None


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """Concrete capability snapshot for the pinned SDK version."""

    sdk_version: str
    sdk_installed: bool
    compile: bool
    cancel: bool
    resume: bool
    usage: bool
    structured_output: bool
    sandbox_reporting: bool
    skills_paths: bool
    inline_skills: bool
    subagents: bool
    mcp: bool
    triggers: bool
    search_web: bool
    probe_verified_backends: tuple[str, ...]
    unverified_backends: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sdk_version": self.sdk_version,
            "sdk_installed": self.sdk_installed,
            "compile": self.compile,
            "cancel": self.cancel,
            "resume": self.resume,
            "usage": self.usage,
            "structured_output": self.structured_output,
            "sandbox_reporting": self.sandbox_reporting,
            "skills_paths": self.skills_paths,
            "inline_skills": self.inline_skills,
            "subagents": self.subagents,
            "mcp": self.mcp,
            "triggers": self.triggers,
            "search_web": self.search_web,
            "probe_verified_backends": list(self.probe_verified_backends),
            "unverified_backends": list(self.unverified_backends),
            "notes": list(self.notes),
        }


def adapter_capabilities() -> AdapterCapabilities:
    """Return the capability snapshot for the locked SDK version."""

    installed = installed_sdk_version()
    notes = [
        "Static resource/config compilation is implemented; execution is LG-006.",
        "Gemini Developer API / Vertex remain unverified in this environment "
        "(no credential); they must not be displayed as validated.",
        "search_web is unavailable on the probe's non-Gemini endpoint; MCP, "
        "Triggers and SDK-internal delegation are off in the first version.",
        "sandbox_reporting reflects the probe's reported SandboxStatus, not an "
        "escape/isolation guarantee.",
    ]
    if installed is not None and installed != SDK_PINNED_VERSION:
        notes.append(
            f"Installed {SDK_DISTRIBUTION}=={installed} differs from the pinned "
            f"{SDK_PINNED_VERSION}; re-run the LG-003 probe before trusting it."
        )
    return AdapterCapabilities(
        sdk_version=SDK_PINNED_VERSION,
        sdk_installed=installed is not None,
        compile=True,
        cancel=True,
        resume=True,
        usage=True,
        structured_output=True,
        sandbox_reporting=True,
        skills_paths=True,
        inline_skills=True,
        subagents=False,
        mcp=False,
        triggers=False,
        search_web=False,
        probe_verified_backends=("openai_compat",),
        unverified_backends=("gemini", "vertex"),
        notes=tuple(notes),
    )


__all__ = [
    "SDK_DISTRIBUTION",
    "SDK_PINNED_VERSION",
    "AdapterCapabilities",
    "adapter_capabilities",
    "installed_sdk_version",
]
