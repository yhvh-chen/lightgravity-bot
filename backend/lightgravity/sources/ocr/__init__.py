"""Configurable OCR backends for source extraction (LG-035).

Two backends ship here:

* :class:`OpenAICompatOcrBackend` — talks to a real OpenAI-compatible
  ``/v1/chat/completions`` endpoint (the verified candidate is a
  ``llama.cpp`` ``llama-server`` router, **not** Ollama).  Base URL and model
  are configuration, never a hard-coded LAN dependency.
* :class:`UnavailableOcrBackend` — explicit, honest "no backend configured"
  stub.  It raises :class:`OcrUnavailable` instead of fabricating text, so a
  missing service keeps the original and records a clear failure.

Embedding is **not** OCR (docs/08 §6.6, docs/09 §7): the embedding endpoint is
not used here, and a working embedding route never implies OCR support.
"""

from __future__ import annotations

from .adapter import (
    ENV_OCR_SCALE,
    ENV_OCR_TABLE_MODE,
    MAX_OCR_SCALE,
    OCR_PROMPT,
    OCR_TABLE_PROMPT,
    OcrBackend,
    OcrPageResult,
    OcrRequest,
    OcrScaleInvalid,
    OcrServiceError,
    OcrTableModeInvalid,
    OcrTimeout,
    OcrUnavailable,
    OpenAICompatOcrBackend,
    UnavailableOcrBackend,
    backend_from_env,
    parse_scale_env,
    parse_table_mode_env,
)
from .pdf import (
    PdfRenderError,
    PdfRasterizer,
    PdfiumRasterizer,
    is_pdf_bytes,
)
from .text import (
    MIN_TEXT_LAYER_CHARS,
    PDF_TEXT_LAYER_EXTRACTOR,
    PDF_TEXT_LAYER_MODEL,
    PdfTextLayerExtractor,
    PdfiumTextLayerExtractor,
    TextLayerPage,
    is_sparse_text_layer,
    visible_char_count,
)
from .layout import (
    DEFAULT_INK_THRESHOLD,
    MAX_PAGE_PIXELS,
    MAX_PAGE_SIDE,
    MIN_GUTTER_PX,
    ColumnRegion,
    LayoutAnalysis,
    LayoutAnalysisError,
    PageGeometry,
    RegionAnalysis,
    TableClassification,
    TextLine,
    analyse_image_bytes,
    analyse_page,
    analyse_rendered_page,
    classify_image_bytes,
    classify_table,
    decode_png_gray,
)

__all__ = [
    "OcrBackend",
    "OcrPageResult",
    "OcrRequest",
    "OcrScaleInvalid",
    "OcrServiceError",
    "OcrTableModeInvalid",
    "OcrTimeout",
    "OcrUnavailable",
    "OpenAICompatOcrBackend",
    "UnavailableOcrBackend",
    "backend_from_env",
    "ENV_OCR_SCALE",
    "ENV_OCR_TABLE_MODE",
    "MAX_OCR_SCALE",
    "OCR_PROMPT",
    "OCR_TABLE_PROMPT",
    "parse_scale_env",
    "parse_table_mode_env",
    "MIN_TEXT_LAYER_CHARS",
    "PDF_TEXT_LAYER_EXTRACTOR",
    "PDF_TEXT_LAYER_MODEL",
    "PdfTextLayerExtractor",
    "PdfiumTextLayerExtractor",
    "TextLayerPage",
    "is_sparse_text_layer",
    "visible_char_count",
    "PdfRenderError",
    "PdfRasterizer",
    "PdfiumRasterizer",
    "is_pdf_bytes",
    "DEFAULT_INK_THRESHOLD",
    "MAX_PAGE_PIXELS",
    "MAX_PAGE_SIDE",
    "MIN_GUTTER_PX",
    "ColumnRegion",
    "LayoutAnalysis",
    "LayoutAnalysisError",
    "PageGeometry",
    "RegionAnalysis",
    "TableClassification",
    "TextLine",
    "analyse_image_bytes",
    "analyse_page",
    "analyse_rendered_page",
    "classify_image_bytes",
    "classify_table",
    "decode_png_gray",
]
