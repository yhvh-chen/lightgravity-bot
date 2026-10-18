"""Optional in-process CPU runtime: EmbeddingGemma 2 audio tower + reader v2/CTC.

This module is imported **only** when the English ASR capability is enabled,
configured and its pinned files validate.  ``torch``/``transformers`` are never
imported at application import time, and the default application works without
the optional ``english-asr`` dependency group.

The real math is the LG-159 verified path:

16 kHz mono -> 128-bin log-mel (frame 320, hop 160) -> audio tower + embed_audio
(25 soft tokens/s, 512-d) -> reader v2 (6 pre-LayerNorm layers, 19,573,762
parameters) -> per-token 768-d unit vector + blank logit -> greedy CTC -> lower
case English words without punctuation/timestamps.

One model instance is lazily loaded and inference is serialized.  There is no
network access, no download/install, no warm-up and no automatic retry.
"""

from __future__ import annotations

import gc
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

from .config import (
    EnglishAsrConfig,
    HashCache,
    verify_model_dir,
)
from .pins import (
    ENCODER_PIN,
    MODEL_VERSION,
    READER_ARCHITECTURE,
    READER_LAYERS,
    READER_PARAMS,
    READER_PIN,
    SAMPLE_RATE,
    SOFT_TOKEN_WIDTH,
    TABLE_ROWS,
    TABLE_WIDTH,
)
from .reader_model import Reader, collapse

_WORD_CLEAN = re.compile(r"[^a-z0-9]+")


class RuntimeUnavailable(Exception):
    """The optional model dependencies/runtime cannot be loaded."""


class ModelIncompatible(Exception):
    """A pinned file/configuration is not the released reader contract."""


class InferenceFailed(Exception):
    """Real inference returned an unusable (empty) result."""


@dataclass(frozen=True, slots=True)
class RuntimeTranscription:
    """One real runtime result (no writes and no job control happen here)."""

    text: str
    latency_seconds: float
    audio_seconds: float
    encoder_ms: int
    reader_ms: int
    model_version: str = MODEL_VERSION


def _load_safetensors_into(module: torch.nn.Module, path: Path, prefix: str) -> int:
    """Copy one tensor at a time into an existing module (no duplicate state dict)."""

    from safetensors import safe_open

    target = module.state_dict()
    loaded = 0
    with safe_open(str(path), "pt") as handle:
        available = set(handle.keys())
        for name, destination in target.items():
            source_name = prefix + name
            if source_name not in available:
                raise ModelIncompatible(f"{source_name} missing from {path.name}")
            source = handle.get_tensor(source_name)
            if source.dtype != destination.dtype:
                source = source.to(destination.dtype)
            destination.copy_(source)
            loaded += 1
    return loaded


def _load_table_with_norms(
    path: Path, device: torch.device, *, chunk_rows: int = 8192
) -> tuple[torch.Tensor, torch.Tensor]:
    table = np.load(str(path), mmap_mode="r")
    if table.ndim != 2 or int(table.shape[0]) != TABLE_ROWS or int(table.shape[1]) != TABLE_WIDTH:
        raise ModelIncompatible(f"word table has shape {table.shape}, expected [{TABLE_ROWS}, {TABLE_WIDTH}]")
    values = torch.from_numpy(np.array(table, dtype=np.float16, copy=True))
    norms = torch.empty(int(values.shape[0]), dtype=torch.float32)
    for start in range(0, int(values.shape[0]), chunk_rows):
        block = values[start : start + chunk_rows].to(torch.float32)
        norms[start : start + int(block.shape[0])] = block.norm(dim=-1)
    if float(norms.min()) <= 0:
        raise ModelIncompatible("word table contains a zero-norm row")
    return values.to(device), norms.to(device)


def _n_frames_for(n_samples: int) -> int:
    return max(0, (n_samples - 161) // 160 + 1)


def _n_tokens_for(n_frames: int) -> int:
    return ((n_frames + 1) // 2 + 1) // 2


@torch.no_grad()
def _greedy_labels_chunked(
    h: torch.Tensor,
    blank: torch.Tensor,
    table: torch.Tensor,
    table_norms: torch.Tensor,
    scale: torch.Tensor,
    *,
    frame_chunk: int = 256,
    table_chunk: int = 8192,
) -> torch.Tensor:
    m = int(h.shape[0])
    if m == 0:
        return torch.zeros(0, dtype=torch.long, device=h.device)
    out = torch.empty(m, dtype=torch.long, device=h.device)
    rows = int(table.shape[0])
    for start in range(0, m, frame_chunk):
        block = h[start : start + frame_chunk]
        best = torch.full((int(block.shape[0]),), float("-inf"), dtype=torch.float32, device=h.device)
        best_index = torch.zeros((int(block.shape[0]),), dtype=torch.long, device=h.device)
        for offset in range(0, rows, table_chunk):
            stop = min(offset + table_chunk, rows)
            chunk = table[offset:stop].to(torch.float32) / table_norms[offset:stop, None]
            value, index = torch.mm(block, chunk.T).max(dim=1)
            take = value > best
            best = torch.where(take, value, best)
            best_index = torch.where(take, index + offset, best_index)
        blank_block = blank[start : start + int(block.shape[0])]
        out[start : start + int(block.shape[0])] = torch.where(
            blank_block > best * scale,
            torch.full_like(best_index, rows),
            best_index,
        )
    return out


class AudioEncoder:
    """Low-memory audio tower + embed_audio loader (no full/vision/text tower)."""

    def __init__(self, model_dir: Path, *, threads: int) -> None:
        try:
            from transformers import AutoModel, Gemma4AudioFeatureExtractor
            from transformers.models.embedding_gemma2.configuration_embedding_gemma2 import (
                EmbeddingGemma2Config,
            )
            from transformers.models.embedding_gemma2.modeling_embedding_gemma2 import (
                EmbeddingGemma2MultimodalEmbedder,
            )
        except Exception as exc:  # noqa: BLE001 - optional dependency boundary
            raise RuntimeUnavailable("transformers/safetensors are not available") from exc
        try:
            torch.set_num_threads(threads)
        except (RuntimeError, ValueError):
            pass
        self._device = torch.device("cpu")
        self._feature_extractor = Gemma4AudioFeatureExtractor.from_pretrained(str(model_dir))
        config = EmbeddingGemma2Config.from_pretrained(str(model_dir))
        # Build directly in float32: building bf16 and calling .float() briefly
        # holds two copies of the 305 M-parameter tower.
        self._audio_tower = AutoModel.from_config(
            config.audio_config, dtype=torch.float32
        ).to(self._device).eval()
        self._embed_audio = EmbeddingGemma2MultimodalEmbedder(
            config.audio_config, config.text_config
        ).float().to(self._device).eval()
        safetensors_path = model_dir / "model.safetensors"
        _load_safetensors_into(self._audio_tower, safetensors_path, "audio_tower.")
        _load_safetensors_into(self._embed_audio, safetensors_path, "embed_audio.")
        implementation = getattr(config.audio_config, "_attn_implementation", None)
        if implementation == "eager":
            raise ModelIncompatible(
                "audio attention resolved to eager; the pinned transformers version reads wrong positions"
            )

    @torch.no_grad()
    def features(self, wav: np.ndarray) -> tuple[np.ndarray, int]:
        out = self._feature_extractor(
            [np.asarray(wav, dtype=np.float32)],
            return_tensors="np",
            max_length=None,
            truncation=False,
        )
        features = out["input_features"][0].astype(np.float32)
        mask = out["input_features_mask"][0].astype(bool)
        frames = _n_frames_for(int(wav.size))
        if int(mask.sum()) != frames or not bool(mask[:frames].all()):
            raise ModelIncompatible(
                f"feature extractor mask {int(mask.sum())} != {frames} leading frames"
            )
        if np.any(features[frames:]):
            raise ModelIncompatible("feature extractor padding rows are not zero")
        return features[:frames], frames

    @torch.no_grad()
    def soft_tokens(self, wav: np.ndarray) -> tuple[np.ndarray, int]:
        features, frames = self.features(wav)
        x = torch.from_numpy(features[None].astype(np.float32)).to(self._device)
        mask = torch.ones(x.shape[:2], dtype=torch.bool, device=self._device)
        out = self._audio_tower(x, mask, return_dict=True)
        pooled = self._embed_audio(inputs_embeds=out.last_hidden_state)
        soft = pooled[0][out.attention_mask[0]].float().cpu().numpy()
        expected = _n_tokens_for(frames)
        if int(soft.shape[0]) != expected:
            raise ModelIncompatible(
                f"{int(soft.shape[0])} soft tokens != {expected} for {frames} frames"
            )
        if int(soft.shape[1]) != SOFT_TOKEN_WIDTH:
            raise ModelIncompatible(
                f"soft token width {int(soft.shape[1])} != {SOFT_TOKEN_WIDTH}"
            )
        return soft, frames


class ReaderDecoder:
    """Pinned reader v2 + float16 word table with bounded float32 read-out."""

    def __init__(self, reader_dir: Path, *, threads: int) -> None:
        try:
            torch.set_num_threads(threads)
        except (RuntimeError, ValueError):
            pass
        self._device = torch.device("cpu")
        config_path = reader_dir / "reader_config.json"
        try:
            config = json.loads(config_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelIncompatible("reader_config.json is unreadable") from exc
        architecture = config.get("architecture")
        vocab_name = config.get("vocab")
        table_config = config.get("table")
        if not isinstance(architecture, dict) or not isinstance(vocab_name, str):
            raise ModelIncompatible("reader config is missing architecture/vocab")
        if architecture.get("name") != READER_ARCHITECTURE:
            raise ModelIncompatible("reader architecture is not the pinned architecture 'a'")
        if int(architecture.get("layers", 0)) != READER_LAYERS:
            raise ModelIncompatible("reader layer count is not the pinned value")
        if int(config.get("n_vocab", 0)) != TABLE_ROWS:
            raise ModelIncompatible("reader vocabulary size is not the pinned value")
        if not isinstance(table_config, dict) or table_config.get("file") != "word_table.npy":
            raise ModelIncompatible("reader word table configuration is not the pinned value")
        try:
            vocab = [
                line.rstrip("\n")
                for line in (reader_dir / vocab_name).read_text("utf-8").splitlines()
                if line.strip()
            ]
        except OSError as exc:
            raise ModelIncompatible("reader vocab is unreadable") from exc
        if len(vocab) != TABLE_ROWS:
            raise ModelIncompatible("reader vocab size is not the pinned value")
        try:
            state = torch.load(
                str(reader_dir / "reader.pt"), map_location="cpu", weights_only=True
            )
        except Exception as exc:  # noqa: BLE001 - torch.load failure is an honest model error
            raise ModelIncompatible("reader.pt could not be loaded with weights_only=True") from exc
        model = Reader(READER_ARCHITECTURE, len(vocab), layers=READER_LAYERS)
        try:
            model.load_state_dict(state)
        except RuntimeError as exc:
            raise ModelIncompatible("reader state dict does not match the pinned architecture") from exc
        self._model = model.to(self._device).eval()
        parameters = sum(parameter.numel() for parameter in self._model.parameters())
        if parameters != READER_PARAMS:
            raise ModelIncompatible(
                f"reader parameter count {parameters} != pinned {READER_PARAMS}"
            )
        configured_scale = float(config.get("scale", 0.0))
        if abs(float(self._model.scale.detach()) - configured_scale) > 1e-4:
            raise ModelIncompatible("reader scale does not match reader_config.json")
        self._vocab = vocab
        self._table, self._norms = _load_table_with_norms(
            reader_dir / table_config["file"], self._device
        )
        if int(self._table.shape[0]) != TABLE_ROWS:
            raise ModelIncompatible("word table rows do not match the pinned vocabulary")

    @torch.no_grad()
    def decode(self, soft: np.ndarray) -> tuple[str, int]:
        x = torch.from_numpy(soft.astype(np.float32))[None].to(self._device)
        lengths = torch.tensor([x.shape[1]], dtype=torch.long)
        h, blank = self._model(x, lengths)
        valid = torch.arange(x.shape[1], device=self._device)[None, :] < lengths[:, None]
        labels = _greedy_labels_chunked(
            h[valid],
            blank[valid],
            self._table,
            self._norms,
            self._model.scale,
        )
        words = collapse(labels.cpu().numpy().tolist(), len(self._vocab))
        text = " ".join(self._vocab[index] for index in words)
        return text, int(soft.shape[0])


class Eg2ReaderRuntime:
    """Lazy, single-instance CPU runtime over the exact pinned model pair."""

    def __init__(
        self,
        config: EnglishAsrConfig,
        *,
        hash_cache: HashCache | None = None,
        filename: str = "audio",
    ) -> None:
        if config.model_dir is None or config.reader_dir is None:
            raise RuntimeUnavailable("both model_dir and reader_dir are required")
        self._config = config
        self._hash_cache = hash_cache or HashCache()
        self._encoder: AudioEncoder | None = None
        self._reader: ReaderDecoder | None = None
        self._lock = threading.Lock()
        self._filename = filename
        self._encoder_dir: Path | None = None
        self._reader_dir: Path | None = None

    @property
    def loaded(self) -> bool:
        return self._encoder is not None and self._reader is not None

    def close(self) -> None:
        """Drop loaded weights so a changed config cannot keep two towers resident."""

        self._encoder = None
        self._reader = None
        gc.collect()

    def _ensure_loaded(self) -> None:
        if self._encoder is not None and self._reader is not None:
            return
        assert self._config.model_dir is not None
        assert self._config.reader_dir is not None
        try:
            encoder_dir = verify_model_dir(
                self._config.model_dir, ENCODER_PIN, cache=self._hash_cache
            )
            reader_dir = verify_model_dir(
                self._config.reader_dir, READER_PIN, cache=self._hash_cache
            )
        except Exception as exc:  # noqa: BLE001 - surfaced honestly by the service
            raise ModelIncompatible("pinned model files failed validation") from exc
        if self._encoder is None:
            try:
                self._encoder = AudioEncoder(encoder_dir, threads=self._config.threads)
            except (RuntimeUnavailable, ModelIncompatible):
                raise
            except MemoryError:
                raise
            except Exception as exc:  # noqa: BLE001 - optional runtime failure
                raise RuntimeUnavailable(f"audio encoder could not be loaded: {type(exc).__name__}") from exc
            self._encoder_dir = encoder_dir
        if self._reader is None:
            try:
                self._reader = ReaderDecoder(reader_dir, threads=self._config.threads)
            except (ModelIncompatible,):
                raise
            except MemoryError:
                raise
            except Exception as exc:  # noqa: BLE001 - optional runtime failure
                raise RuntimeUnavailable(f"reader could not be loaded: {type(exc).__name__}") from exc
            self._reader_dir = reader_dir

    def transcribe(
        self,
        data: bytes,
        *,
        filename: str = "audio",
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeTranscription:
        """Decode one bounded audio input, then run the real model path.

        Duration/size limits are checked before any model load.  A cancellation
        only returns after the current real call has actually stopped; the
        service decides whether the stop was confirmed.
        """

        from .audio import decode_audio

        started = time.monotonic()
        audio = decode_audio(
            data,
            filename=filename,
            max_seconds=self._config.max_audio_seconds,
            timeout_seconds=min(float(self._config.timeout_seconds), 60.0),
        )
        if cancel_check is not None and cancel_check():
            raise RuntimeUnavailable("cancelled before model start")
        if not self._lock.acquire(blocking=False):
            raise RuntimeUnavailable("English ASR runtime is already processing another audio source")
        try:
            self._ensure_loaded()
            if cancel_check is not None and cancel_check():
                raise RuntimeUnavailable("cancelled before inference")
            assert self._encoder is not None
            assert self._reader is not None
            encode_started = time.monotonic()
            soft, _frames = self._encoder.soft_tokens(audio)
            encoder_ms = int((time.monotonic() - encode_started) * 1000)
            if cancel_check is not None and cancel_check():
                raise RuntimeUnavailable("cancelled after encoding")
            reader_started = time.monotonic()
            raw_text, _tokens = self._reader.decode(soft)
            reader_ms = int((time.monotonic() - reader_started) * 1000)
            text = _WORD_CLEAN.sub(" ", raw_text.lower())
            text = " ".join(text.split())
            if not text:
                raise InferenceFailed("reader returned an empty transcript")
            return RuntimeTranscription(
                text=text,
                latency_seconds=time.monotonic() - started,
                audio_seconds=float(audio.size) / float(SAMPLE_RATE),
                encoder_ms=encoder_ms,
                reader_ms=reader_ms,
            )
        finally:
            self._lock.release()


def decode_input(
    data: bytes,
    *,
    filename: str,
    max_seconds: int,
    timeout_seconds: float,
) -> np.ndarray:
    """Public seam used by the service; imported lazily to keep torch optional."""

    from .audio import decode_audio

    return decode_audio(
        data,
        filename=filename,
        max_seconds=max_seconds,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "RuntimeUnavailable",
    "ModelIncompatible",
    "InferenceFailed",
    "RuntimeTranscription",
    "Eg2ReaderRuntime",
    "decode_input",
]
