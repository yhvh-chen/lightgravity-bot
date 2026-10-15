"""PDF page rasterisation for OCR (LG-035).

Rendering a PDF page to a bitmap is the only way OCR can see a scanned page.
This module wraps **pypdfium2** (BSD-3-Clause + Apache-2.0, self-contained
wheel; no ``poppler`` system dependency, no AGPL) behind a tiny protocol so the
processing layer stays testable and the import stays lazy — a deployment that
never OCRs a PDF does not import PDFium.

The rasteriser never mutates the original file; it reads bytes and returns
fresh PNG bytes per page.  PNG encoding uses only the standard library
(``zlib`` + ``struct``), so no image library (Pillow) is required at all.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Protocol

from ...contracts import AppError, ErrorCode

#: Magic prefix shared by every PDF file.
PDF_MAGIC = b"%PDF-"
#: Default render scale: ~150 DPI from the 72-DPI PDF unit.
DEFAULT_SCALE = 2.0
#: Hard cap on pages processed by one job (bounded work, honest partial result).
DEFAULT_MAX_PAGES = 100


class PdfRenderError(AppError):
    """The PDF could not be parsed/rendered; a clear failure, not fake text."""

    def __init__(self, detail: str, *, page: int | None = None) -> None:
        super().__init__(
            ErrorCode.VALIDATION_FAILED,
            "PDF page could not be rendered",
            details={"reason": detail, "page": page},
        )


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """One rasterised page: PNG bytes plus its 1-based page number."""

    page: int
    png: bytes
    width: int
    height: int


class PdfRasterizer(Protocol):
    """Render a PDF into per-page PNG images."""

    def page_count(self, data: bytes) -> int: ...

    def render(self, data: bytes, *, scale: float = DEFAULT_SCALE, max_pages: int = DEFAULT_MAX_PAGES) -> list[RenderedPage]: ...


def is_pdf_bytes(data: bytes) -> bool:
    """Return True when ``data`` starts with the PDF magic number."""

    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    return head.startswith(PDF_MAGIC)


class PdfiumRasterizer:
    """pypdfium2-backed rasteriser (lazy import)."""

    def _open(self, data: bytes) -> object:
        if not is_pdf_bytes(data):
            raise PdfRenderError("input is not a PDF")
        try:
            import pypdfium2 as pdfium  # local import: optional until a PDF is seen
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise PdfRenderError("pypdfium2 is not installed") from exc
        try:
            return pdfium.PdfDocument(data)
        except Exception as exc:  # noqa: BLE001 - surface any parse failure honestly
            raise PdfRenderError(f"failed to open PDF: {type(exc).__name__}") from None

    def page_count(self, data: bytes) -> int:
        document = self._open(data)
        try:
            return len(document)  # type: ignore[arg-type]
        finally:
            _close(document)

    def render(
        self,
        data: bytes,
        *,
        scale: float = DEFAULT_SCALE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[RenderedPage]:
        if scale <= 0:
            raise PdfRenderError("scale must be positive")
        document = self._open(data)
        pages: list[RenderedPage] = []
        try:
            total = len(document)  # type: ignore[arg-type]
            limit = min(total, max(int(max_pages), 1))
            for index in range(limit):
                page = None
                bitmap = None
                try:
                    page = document.get_page(index)  # type: ignore[attr-defined]
                    width = int(page.get_width())
                    height = int(page.get_height())
                    bitmap = page.render(scale=scale)
                    png = _bitmap_to_png(bitmap)
                except PdfRenderError:
                    raise
                except Exception as exc:  # noqa: BLE001 - one bad page is a clear failure
                    raise PdfRenderError(
                        f"failed to render page {index + 1}: {type(exc).__name__}",
                        page=index + 1,
                    ) from None
                finally:
                    if bitmap is not None:
                        close = getattr(bitmap, "close", None)
                        if callable(close):
                            close()
                    if page is not None:
                        close = getattr(page, "close", None)
                        if callable(close):
                            close()
                pages.append(
                    RenderedPage(page=index + 1, png=png, width=width, height=height)
                )
            return pages
        finally:
            _close(document)


#: pypdfium2 bitmap format constants (pypdfium2.raw).
_FPDFBITMAP_GRAY = 1
_FPDFBITMAP_BGR = 2
_FPDFBITMAP_BGRX = 3
_FPDFBITMAP_BGRA = 4
_FPDFBITMAP_BGRA_PREMUL = 5


def _bitmap_to_png(bitmap: object) -> bytes:
    """Encode a pypdfium2 bitmap to PNG using only the standard library."""

    fmt = int(getattr(bitmap, "format"))
    width = int(getattr(bitmap, "width"))
    height = int(getattr(bitmap, "height"))
    stride = int(getattr(bitmap, "stride"))
    buffer = bytes(getattr(bitmap, "buffer"))

    if fmt == _FPDFBITMAP_GRAY:
        rows = [buffer[r * stride : r * stride + width] for r in range(height)]
        return _png_gray8(width, height, rows)

    channels = 4 if fmt in (_FPDFBITMAP_BGRA, _FPDFBITMAP_BGRA_PREMUL) else 3
    if fmt not in (_FPDFBITMAP_BGR, _FPDFBITMAP_BGRX, _FPDFBITMAP_BGRA, _FPDFBITMAP_BGRA_PREMUL):
        raise PdfRenderError(f"unsupported bitmap format {fmt}")
    rows = []
    for r in range(height):
        start = r * stride
        line = bytearray(width * 3)
        src = buffer[start : start + width * channels]
        for x in range(width):
            base = x * channels
            dst = x * 3
            line[dst] = src[base + 2]  # R <- BGR(A)
            line[dst + 1] = src[base + 1]  # G
            line[dst + 2] = src[base]  # B
        rows.append(bytes(line))
    return _png_rgb8(width, height, rows)


def _png_rgb8(width: int, height: int, rows: list[bytes]) -> bytes:
    raw = b"".join(b"\x00" + row for row in rows)
    return _png_container(width, height, bit_depth=8, color_type=2, raw=raw)


def _png_gray8(width: int, height: int, rows: list[bytes]) -> bytes:
    raw = b"".join(b"\x00" + row for row in rows)
    return _png_container(width, height, bit_depth=8, color_type=0, raw=raw)


def _png_container(width: int, height: int, *, bit_depth: int, color_type: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    idat = zlib.compress(raw, 6)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _close(document: object) -> None:
    close = getattr(document, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 - closing must not mask the real result
            pass


__all__ = [
    "DEFAULT_MAX_PAGES",
    "DEFAULT_SCALE",
    "PDF_MAGIC",
    "PdfRasterizer",
    "PdfRenderError",
    "PdfiumRasterizer",
    "RenderedPage",
    "is_pdf_bytes",
]
