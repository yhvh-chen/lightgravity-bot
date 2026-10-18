"""Native PDF text-layer extraction (LG-224).

Electronic PDFs already carry selectable text.  Rasterising them and asking an
OCR model to re-read the same glyphs is unnecessary, and it made an electronic
PDF fail outright whenever no OCR backend was configured.  This module reads
the embedded text layer with the **already installed** ``pypdfium2`` wheel
(no new dependency, no model, no network, no credentials).

The extractor is deliberately small and honest:

* it never claims OCR provenance — callers label its output with
  :data:`PDF_TEXT_LAYER_EXTRACTOR`;
* a page whose text operation fails is returned with empty text and an explicit
  ``error`` so the processing layer can fall back to OCR for that page;
* if the document itself cannot be opened the existing :class:`PdfRenderError`
  contract is kept, so callers fail clearly rather than fabricating text.

Sparse text layers are still handled by the caller (``processing``): this
module only reports the text and its visible character count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .pdf import DEFAULT_MAX_PAGES, PdfRenderError, is_pdf_bytes

#: Extractor provenance recorded for a native PDF text-layer page.
PDF_TEXT_LAYER_EXTRACTOR = "pdfium-text-layer"
#: No model is called on this path (same convention as native UTF-8 text).
PDF_TEXT_LAYER_MODEL = "none"
#: A page with fewer visible characters than this is treated as "empty or very
#: sparse" and falls back to OCR.  Pages with a real text layer never reach OCR.
MIN_TEXT_LAYER_CHARS = 16


@dataclass(frozen=True, slots=True)
class TextLayerPage:
    """One page's embedded text and (if any) extraction error."""

    page: int
    text: str
    error: str | None = None

    @property
    def visible_chars(self) -> int:
        return visible_char_count(self.text)

    def to_dict(self) -> dict[str, object]:
        return {
            "page": self.page,
            "visible_chars": self.visible_chars,
            "error": self.error,
        }


class PdfTextLayerExtractor(Protocol):
    """Read the embedded text layer of a PDF, page by page."""

    def extract(
        self, data: bytes, *, max_pages: int | None = DEFAULT_MAX_PAGES
    ) -> list[TextLayerPage]: ...


def visible_char_count(text: str) -> int:
    """Count non-whitespace characters (layout whitespace is not content)."""

    return sum(1 for char in text if not char.isspace())


def is_sparse_text_layer(text: str, *, min_chars: int = MIN_TEXT_LAYER_CHARS) -> bool:
    """Whether a page's text layer is empty/too sparse to trust as the body."""

    return visible_char_count(text) < max(int(min_chars), 1)


class PdfiumTextLayerExtractor:
    """``pypdfium2``-backed text-layer reader (lazy import, no model)."""

    def extract(
        self, data: bytes, *, max_pages: int | None = DEFAULT_MAX_PAGES
    ) -> list[TextLayerPage]:
        if not is_pdf_bytes(data):
            raise PdfRenderError("input is not a PDF")
        try:
            import pypdfium2 as pdfium  # local import: optional until a PDF is seen
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise PdfRenderError("pypdfium2 is not installed") from exc
        try:
            document = pdfium.PdfDocument(data)
        except Exception as exc:  # noqa: BLE001 - surface any parse failure honestly
            raise PdfRenderError(f"failed to open PDF: {type(exc).__name__}") from None
        try:
            total = len(document)
            limit = total if max_pages is None else min(total, max(int(max_pages), 1))
            pages: list[TextLayerPage] = []
            for index in range(limit):
                text = ""
                error: str | None = None
                page = None
                textpage = None
                try:
                    page = document.get_page(index)
                    textpage = page.get_textpage()
                    extracted = textpage.get_text_range()
                    text = extracted if isinstance(extracted, str) else ""
                except Exception as exc:  # noqa: BLE001 - one page falls back to OCR
                    error = f"text_layer_unreadable: {type(exc).__name__}"
                finally:
                    if textpage is not None:
                        close = getattr(textpage, "close", None)
                        if callable(close):
                            close()
                    if page is not None:
                        close = getattr(page, "close", None)
                        if callable(close):
                            close()
                pages.append(TextLayerPage(page=index + 1, text=text, error=error))
            return pages
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - closing must not mask the result
                    pass


__all__ = [
    "MIN_TEXT_LAYER_CHARS",
    "PDF_TEXT_LAYER_EXTRACTOR",
    "PDF_TEXT_LAYER_MODEL",
    "PdfTextLayerExtractor",
    "PdfiumTextLayerExtractor",
    "TextLayerPage",
    "is_sparse_text_layer",
    "visible_char_count",
]
