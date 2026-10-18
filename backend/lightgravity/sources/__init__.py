"""Source intake: original-receipt persistence and recoverable intake jobs.

This package implements the LG-034 half of the LG-033 source-intake contract
frozen additively in docs/08 ``1.6.0`` (§4.3 endpoints, §5.1 events, §6.6
entities).  It owns only the ``source`` / ``intake_job`` entities, the
controlled inbox and the receiving/attribution stage; extraction (LG-035) and
the rebuildable lexical index (LG-036) are separate modules that consume the
file source of truth produced here.

Boundaries kept deliberately:

* Files remain the only source of truth.  The ``source`` frontmatter +
  original bytes + ``intake_job`` frontmatter live under ``<data>/sources/``;
  JSONL history is append-only; nothing here is a second authoritative database.
* Receiving **never** creates a delivery Task/Run/Member and never writes Task
  control state (docs/08 §6.6 write-authorization boundary).
* Uploaded bodies/frontmatter are data, never instructions: unknown fields are
  preserved but never gain execution semantics, and no path escapes the
  authorized roots.
"""

from .content import ContentStore, MachineDraft, PageText
from .intake import (
    IntakeService,
    PayloadHashMismatch,
    ReceiveRequest,
    compute_content_hash,
    compute_payload_hash,
)
from .lexical import (
    IndexedDocument,
    LexicalIndex,
    LexicalSearchService,
    SearchRequest,
    parse_query,
    tokenize,
)
from .models import IntakeJobRecord, ReceiptEntry, SourceRecord
from .ocr import (
    OcrBackend,
    OcrPageResult,
    OcrRequest,
    OcrTimeout,
    OcrUnavailable,
    OpenAICompatOcrBackend,
    PdfiumRasterizer,
    UnavailableOcrBackend,
    is_pdf_bytes,
)
from .processing import ProcessingConfig, ProcessingEngine, ProcessingOutcome
from .service import SourceService, build_source_service
from .store import SourceStore
from .worker import IntakeWorker

__all__ = [
    "ContentStore",
    "IndexedDocument",
    "IntakeService",
    "IntakeJobRecord",
    "IntakeWorker",
    "LexicalIndex",
    "LexicalSearchService",
    "MachineDraft",
    "OcrBackend",
    "OcrPageResult",
    "OcrRequest",
    "OcrTimeout",
    "OcrUnavailable",
    "OpenAICompatOcrBackend",
    "PageText",
    "PayloadHashMismatch",
    "PdfiumRasterizer",
    "ProcessingConfig",
    "ProcessingEngine",
    "ProcessingOutcome",
    "ReceiptEntry",
    "ReceiveRequest",
    "SourceRecord",
    "SourceService",
    "SearchRequest",
    "SourceStore",
    "UnavailableOcrBackend",
    "build_source_service",
    "compute_content_hash",
    "compute_payload_hash",
    "is_pdf_bytes",
    "parse_query",
    "tokenize",
]
