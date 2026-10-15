"""Optional multimodal vector index over the file source of truth (LG-037).

This package implements the LG-033/docs-08 §6.6 optional-vector rules as a
**rebuildable派生 cache**:

* Files (``SOURCE.md`` + original bytes + formal/machine content) remain the only
  source of truth.  The vector cache stores **no独有的 permission/attribution/
  control state** and can be deleted and rebuilt from files.
* Vectors are an **optional派生**: OCR/ASR and the lexical index never depend on
  them, and when the embedding backend is unavailable the lexical path and
  original viewing keep working.
* **Media stays media**: image/audio originals are embedded directly as media
  parts, never fabricated into text.  ASR/OCR are separate paths (LG-035/LG-039).
* Every cached vector records the **model id / dimension / fragment hash / cache
  version**; a **model switch rebuilds** the cache instead of mixing
  incompatible vectors.
* Authorization and scope come only from ``SOURCE.md``; every hit is re-verified
 回源 before it is returned.

``embedding ≠ OCR/ASR``: a vector is never a transcription or a
recognition-quality claim.  No image/PDF retrieval-quality claim is made here;
LG-035's OCR quality gate remains blocked.
"""

from .embedder import (
    EmbedInput,
    EmbedResult,
    EmbeddingBackend,
    EmbeddingServiceError,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    OpenAICompatEmbeddingBackend,
    UnavailableEmbeddingBackend,
    backend_from_env,
    cosine_similarity,
)
from .index import (
    VECTOR_CACHE_VERSION,
    VECTOR_KINDS,
    VectorBuildReport,
    VectorCacheCorruptError,
    VectorEntry,
    VectorIndex,
    VectorModelMismatchError,
    fragment_hash,
)
from .service import VectorSearchRequest, VectorSearchService, build_vector_service

__all__ = [
    "EmbedInput",
    "EmbedResult",
    "EmbeddingBackend",
    "EmbeddingServiceError",
    "EmbeddingTimeout",
    "EmbeddingUnavailable",
    "OpenAICompatEmbeddingBackend",
    "UnavailableEmbeddingBackend",
    "VECTOR_CACHE_VERSION",
    "VECTOR_KINDS",
    "VectorBuildReport",
    "VectorCacheCorruptError",
    "VectorEntry",
    "VectorIndex",
    "VectorModelMismatchError",
    "VectorSearchRequest",
    "VectorSearchService",
    "backend_from_env",
    "build_vector_service",
    "cosine_similarity",
    "fragment_hash",
]
