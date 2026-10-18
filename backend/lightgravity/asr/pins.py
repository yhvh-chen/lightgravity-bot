"""Pinned English ASR artifacts for the optional in-process CPU runtime.

Only the public pair validated by LG-159 is accepted (docs/08 §21.2):

* ``google/embeddinggemma-2`` at revision ``914f7f89...`` (Apache-2.0)
* ``mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader`` v2 at revision
  ``de224fd8...`` (Apache-2.0)

The runtime never downloads, installs, trains or substitutes another model.
Every required file is checked by exact name and SHA-256 before it is loaded.
Model files are provisioned by the operator outside this repository; see
``backend/lightgravity/asr/README.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

MODEL_VERSION = "eg2-reader-v2+embeddinggemma-2@914f7f89"
ENGINE = "eg2-reader-v2"
LANGUAGE = "en"


@dataclass(frozen=True, slots=True)
class ModelPin:
    """One pinned public model/reader artifact."""

    role: str
    id: str
    revision: str
    license: str
    files: Mapping[str, str]

    def public(self) -> dict[str, str]:
        """Receipt/settings-safe provenance (never a local path)."""

        primary = next(iter(self.files.values()))
        return {
            "id": self.id,
            "revision": self.revision,
            "sha256": primary,
            "license": self.license,
        }


#: Audio encoder.  ``config.json`` and ``preprocessor_config.json`` are pinned
#: too because the feature extractor/config affect the real math.
ENCODER_PIN = ModelPin(
    role="encoder",
    id="google/embeddinggemma-2",
    revision="914f7f89142e33e77833254d9c9b90c3cef7303b",
    license="apache-2.0",
    files={
        "model.safetensors": "197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79",
        "config.json": "b8f1e9931b57fbc054acdb445c41765d55b0074c58d145fa82839941ad1b5bb3",
        "preprocessor_config.json": "ea2ae257e901064abdd98dceb19f2b0da06af600bed15e0f99f5c85c37ee9d78",
    },
)

#: Reader v2 + its word table/vocab/config.  The primary SHA exposed in public
#: provenance is ``reader.pt``; the other hashes are enforced locally.
READER_PIN = ModelPin(
    role="reader",
    id="mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader",
    revision="de224fd8fa4ed4519fdddd9aa4154432d46a1bd3",
    license="apache-2.0",
    files={
        "reader.pt": "d605f6fba8687497be6b5fd717ea6c51beaee5d5f69c30a64225da96ebe0d8c2",
        "reader_config.json": "3aede371f7fc1b69bd948a3fce6f861e44eedb237d7b6dce360063ea007a90ed",
        "word_table.npy": "b2d0b13cc70c492f1444b8a42deab437d25254eac47d752d777d27b65377faa8",
        "vocab.txt": "bb3b3c70379082333e1bbd90d07ca69fe5c0096bd1c3b2b3f83edd65f1062a68",
    },
)

PINS: tuple[ModelPin, ...] = (ENCODER_PIN, READER_PIN)

#: Exact runtime contract values (docs/08 §21.2).  They are recorded in the
#: reader config and checked again at load time.
SAMPLE_RATE = 16_000
SOFT_TOKEN_WIDTH = 512
TABLE_ROWS = 200_000
TABLE_WIDTH = 768
READER_ARCHITECTURE = "a"
READER_LAYERS = 6
READER_PARAMS = 19_573_762

#: Defaults frozen by the interface contract.
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_AUDIO_SECONDS = 30
DEFAULT_MAX_AUDIO_BYTES = 10_000_000
MAX_THREADS = 8
MIN_THREADS = 1


__all__ = [
    "MODEL_VERSION",
    "ENGINE",
    "LANGUAGE",
    "ModelPin",
    "ENCODER_PIN",
    "READER_PIN",
    "PINS",
    "SAMPLE_RATE",
    "SOFT_TOKEN_WIDTH",
    "TABLE_ROWS",
    "TABLE_WIDTH",
    "READER_ARCHITECTURE",
    "READER_LAYERS",
    "READER_PARAMS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_AUDIO_SECONDS",
    "DEFAULT_MAX_AUDIO_BYTES",
    "MIN_THREADS",
    "MAX_THREADS",
]
