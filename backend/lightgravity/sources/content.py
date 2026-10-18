"""Content version layering: machine derivative vs. human formal version.

Implements the docs/08 §6.6 / docs/09 §5 rule that the **machine extraction**
and the **human edited formal content** are separate artifacts:

* ``derivative/machine.v<source_version>.md`` — machine text produced by an
  extractor for one source version.  Re-running extraction writes a new
  derivative; it never touches the formal version.
* ``formal/FORMAL.md`` — the authoritative human-edited content.  It is only
  ever created/updated through an explicit formal edit, and ``reprocess`` does
  **not** overwrite it (docs/08 §6.6 “重处理不覆盖人工正式版本”).

Every machine block carries a locator back to the concrete input:

* ``page``       — 1-based page number for PDF pages (``None`` for a single image)
* ``original``   — ``original/<name>`` relative to the source root
* ``input_sha256`` — SHA-256 of the exact image bytes OCR saw

so a found passage can be traced to a page and the original file.  The
frontmatter mirrors the frozen ``derivatives``/``formal`` fields so the source
record stays the single source of truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.atomic import append_jsonl, atomic_write_text, load_jsonl, recover_jsonl
from lightgravity.store.locking import LockManager

#: Derivative kinds recorded in ``source.derivatives[].kind``.
DERIVATIVE_MACHINE = "machine_markdown"
DERIVATIVE_PAGES = "page_map"
DERIVATIVE_EVIDENCE = "ocr_evidence"

#: Filename of the human formal version inside ``formal/``.
FORMAL_FILENAME = "FORMAL.md"


@dataclass(frozen=True, slots=True)
class PageText:
    """One page's machine transcription and its provenance."""

    page: int | None
    text: str
    input_sha256: str
    model: str
    status: str = "succeeded"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "text": self.text,
            "input_sha256": self.input_sha256,
            "model": self.model,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PageText":
        data = value if isinstance(value, dict) else {}
        page = data.get("page")
        return cls(
            page=page if isinstance(page, int) and not isinstance(page, bool) else None,
            text=str(data.get("text", "")),
            input_sha256=str(data.get("input_sha256", "")),
            model=str(data.get("model", "")),
            status=str(data.get("status", "succeeded")),
            error=data.get("error") if isinstance(data.get("error"), str) else None,
        )


@dataclass(frozen=True, slots=True)
class MachineDraft:
    """Result of an extraction run for one source version."""

    source_version: int
    filename: str
    model: str
    pages: list[PageText]
    extractor: str
    status: str  # succeeded | partial | failed
    fail_reason: str | None = None
    total_pages: int | None = None
    cancelled: bool = False

    @property
    def succeeded_pages(self) -> list[PageText]:
        return [p for p in self.pages if p.status == "succeeded"]

    @property
    def failed_pages(self) -> list[PageText]:
        return [p for p in self.pages if p.status != "succeeded"]


@dataclass(frozen=True, slots=True)
class ContentStore:
    """File operations for machine derivatives and the formal version."""

    source_root: Path
    #: Lock directory; defaults under the source parent so nothing lands in the
    #: process working directory.
    locks: LockManager | None = None

    def _lock_manager(self) -> LockManager:
        if self.locks is not None:
            return self.locks
        return LockManager(self.source_root.parent / "locks", default_timeout=10.0)

    # ------------------------------------------------------------------ paths
    def derivative_dir(self) -> Path:
        return self.source_root / "derivative"

    def formal_dir(self) -> Path:
        return self.source_root / "formal"

    def machine_markdown_path(self, source_version: int) -> Path:
        return self.derivative_dir() / f"machine.v{source_version}.md"

    def pages_path(self, source_version: int) -> Path:
        return self.derivative_dir() / f"machine.v{source_version}.pages.json"

    def evidence_path(self) -> Path:
        return self.derivative_dir() / "ocr_evidence.jsonl"

    def formal_path(self) -> Path:
        return self.formal_dir() / FORMAL_FILENAME

    # -------------------------------------------------------- machine writing
    def write_machine(self, draft: MachineDraft) -> dict[str, Any]:
        """Write the machine derivative for one source version (atomic)."""

        markdown = render_machine_markdown(draft)
        pages_doc = {
            "schema": "lightgravity.bot/v1",
            "kind": "source_derivative",
            "derivative": DERIVATIVE_PAGES,
            "source_version": draft.source_version,
            "filename": draft.filename,
            "model": draft.model,
            "extractor": draft.extractor,
            "status": draft.status,
            "total_pages": draft.total_pages,
            "pages": [p.to_dict() for p in draft.pages],
        }
        with self._lock_manager().acquire(f"derivative:{self.source_root.name}"):
            self.derivative_dir().mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.machine_markdown_path(draft.source_version), markdown)
            atomic_write_text(
                self.pages_path(draft.source_version),
                json.dumps(pages_doc, ensure_ascii=False, indent=2),
            )
        return {
            "markdown_path": f"derivative/{self.machine_markdown_path(draft.source_version).name}",
            "pages_path": f"derivative/{self.pages_path(draft.source_version).name}",
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "status": draft.status,
        }

    def write_transcript(
        self,
        source_version: int,
        text: str,
        *,
        filename: str,
        input_sha256: str,
        model: str,
        extractor: str = "eg2-reader-v2",
    ) -> dict[str, Any]:
        """Write the ASR machine transcript as the existing machine body.

        Unlike OCR Markdown, the content endpoint for an audio transcript returns
        exactly the machine English text (no synthetic page wrapper).  Provenance
        lives in the source ``derivatives`` entry and the receipt.  The companion
        pages document keeps the same status shape old receipt inference reads.
        """

        pages_doc = {
            "schema": "lightgravity.bot/v1",
            "kind": "source_derivative",
            "derivative": DERIVATIVE_PAGES,
            "source_version": source_version,
            "filename": filename,
            "model": model,
            "extractor": extractor,
            "status": "succeeded",
            "total_pages": 1,
            "pages": [
                PageText(
                    page=1,
                    text=text,
                    input_sha256=input_sha256,
                    model=model,
                    status="succeeded",
                ).to_dict()
            ],
        }
        with self._lock_manager().acquire(f"derivative:{self.source_root.name}"):
            self.derivative_dir().mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.machine_markdown_path(source_version), text)
            atomic_write_text(
                self.pages_path(source_version),
                json.dumps(pages_doc, ensure_ascii=False, indent=2),
            )
        return {
            "markdown_path": f"derivative/{self.machine_markdown_path(source_version).name}",
            "pages_path": f"derivative/{self.pages_path(source_version).name}",
            "markdown_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "status": "succeeded",
        }

    def append_evidence(self, record: dict[str, Any]) -> None:
        """Append one redacted OCR request/response record (never a secret)."""

        path = self.evidence_path()
        with self._lock_manager().acquire(f"evidence:{self.source_root.name}"):
            self.derivative_dir().mkdir(parents=True, exist_ok=True)
            recover_jsonl(path)
            append_jsonl(path, record)

    def read_evidence(self) -> list[dict[str, Any]]:
        records, _ = load_jsonl(self.evidence_path())
        return records

    def read_pages(self, source_version: int) -> dict[str, Any] | None:
        path = self.pages_path(source_version)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def read_machine_markdown(self, source_version: int) -> str | None:
        path = self.machine_markdown_path(source_version)
        if not path.is_file():
            return None
        try:
            return path.read_text("utf-8")
        except OSError:
            return None

    # ---------------------------------------------------------- formal version
    def has_formal(self) -> bool:
        return self.formal_path().is_file()

    def read_formal(self) -> str | None:
        path = self.formal_path()
        if not path.is_file():
            return None
        try:
            return path.read_text("utf-8")
        except OSError:
            return None

    def initialize_formal_from_machine(self, source_version: int, *, edited_by: str) -> bool:
        """Seed the formal version once from a machine draft.

        This is the *only* place the formal file is created from machine text,
        and it happens on an explicit human edit request.  It refuses to
        overwrite an existing formal version — that is what makes reprocessing
        non-destructive (docs/08 §6.6).
        """

        if self.has_formal():
            return False
        markdown = self.read_machine_markdown(source_version)
        if markdown is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "no machine derivative exists to seed the formal version",
                details={"source_version": source_version},
            )
        header = (
            "<!-- formal version: human-edited. Reprocessing never overwrites this file. -->\n"
            f"<!-- seeded_from_machine: machine.v{source_version}.md -->\n"
            f"<!-- edited_by: {edited_by} -->\n\n"
        )
        with self._lock_manager().acquire(f"formal:{self.source_root.name}"):
            if self.has_formal():
                return False
            self.formal_dir().mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.formal_path(), header + markdown)
        return True

    def write_formal(self, content: str, *, edited_by: str, expected_revision: int | None) -> int:
        """Write the human formal version and return its new revision.

        The revision is tracked outside the file body (the source frontmatter
        owns ``formal.revision``); this method only writes bytes atomically.
        """

        with self._lock_manager().acquire(f"formal:{self.source_root.name}"):
            current = 0 if expected_revision is None else expected_revision
            header = (
                "<!-- formal version: human-edited. Reprocessing never overwrites this file. -->\n"
                f"<!-- edited_by: {edited_by} -->\n\n"
            )
            self.formal_dir().mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.formal_path(), header + content)
        return current + 1

    def formal_relative_path(self) -> str:
        return f"formal/{FORMAL_FILENAME}"


def render_machine_markdown(draft: MachineDraft) -> str:
    """Render the machine derivative as traceable Markdown.

    The frontmatter is *data*, not executable semantics (docs/08 §6.6): it
    records extractor provenance, and every page block carries its locator.
    Failed pages are recorded as failures and never presented as body text
    (docs/09 §6).
    """

    lines: list[str] = []
    lines.append("---")
    lines.append("schema: lightgravity.bot/v1")
    lines.append("kind: source_derivative")
    lines.append(f"record_type: {_record_type_for(draft.extractor)}")
    lines.append(f"source_version: {draft.source_version}")
    lines.append(f"extractor: {draft.extractor}")
    lines.append(f"extractor_model: {draft.model}")
    lines.append(f"extraction_status: {draft.status}")
    lines.append(f"source_file: {_yaml_escape(draft.filename)}")
    if draft.total_pages is not None:
        lines.append(f"total_pages: {draft.total_pages}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {_heading_for(draft.extractor)} — {draft.filename}")
    lines.append("")
    lines.append(
        "> Machine transcription. Authoritative human edits live in `formal/FORMAL.md`; "
        "reprocessing replaces this file only."
    )
    lines.append("")
    for page in draft.pages:
        locator = page.page if page.page is not None else 1
        if page.status == "succeeded":
            lines.append(f"## Page {locator}")
            lines.append("")
            lines.append(f"<!-- original: {draft.filename} page={locator} "f"input_sha256={page.input_sha256} -->")
            lines.append("")
            lines.append(page.text.rstrip("\n"))
            lines.append("")
        else:
            # Honest failure: no fabricated body, just a bounded failure note.
            lines.append(f"## Page {locator} — failed")
            lines.append("")
            lines.append(f"<!-- original: {draft.filename} page={locator} status=failed -->")
            lines.append("")
            lines.append(f"Page {locator} was not transcribed: {page.error or 'unknown error'}.")
            lines.append("")
    if draft.status == "failed" and not draft.pages:
        lines.append("No text could be extracted for this source.")
        lines.append("")
    return "\n".join(lines)


def _record_type_for(extractor: str) -> str:
    """Honest derivative ``record_type`` label for the extractor provenance.

    Native UTF-8 text is not OCR; labelling it as such would be a false
    provenance claim.  All other extractors keep the frozen ``machine_ocr``
    label used by the OCR/raster path.
    """

    if extractor == "native-utf8-text":
        return "machine_native_text"
    if extractor == "eg2-reader-v2":
        return "machine_transcript"
    return "machine_ocr"


def _heading_for(extractor: str) -> str:
    """Honest human-readable heading matching the extractor provenance."""

    if extractor == "native-utf8-text":
        return "Machine native text"
    if extractor == "eg2-reader-v2":
        return "Machine transcript"
    return "Machine OCR"


def _yaml_escape(value: str) -> str:
    if re.search(r"[:#\[\]{}&*!|>'\"%@`]", value) or value != value.strip():
        return json.dumps(value, ensure_ascii=False)
    return value


__all__ = [
    "DERIVATIVE_EVIDENCE",
    "DERIVATIVE_MACHINE",
    "DERIVATIVE_PAGES",
    "FORMAL_FILENAME",
    "ContentStore",
    "MachineDraft",
    "PageText",
    "render_machine_markdown",
]
