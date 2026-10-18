"""Bounded local audio decoding for the English ASR runtime.

The model path expects 16 kHz mono float32.  WAV is decoded with the Python
standard library (no external process); other containers use the already-present
local ``ffmpeg`` binary when available.  No network, no download, no service.

Failure is explicit: unsupported/corrupt input raises :class:`AudioDecodeError`
and the caller records ``audio_decode_failed`` without fabricating text.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .pins import SAMPLE_RATE


class AudioDecodeError(Exception):
    """Audio could not be decoded into finite mono samples."""


class AudioTooLong(Exception):
    """Decoded duration exceeds the configured limit."""


def _pcm_to_float(raw: bytes, width: int) -> np.ndarray:
    if width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (data - 128.0) / 128.0
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        return data / 32768.0
    if width == 3:
        usable = len(raw) - (len(raw) % 3)
        triplets = np.frombuffer(raw[:usable], dtype=np.uint8).reshape(-1, 3)
        values = (
            triplets[:, 0].astype(np.int32)
            | (triplets[:, 1].astype(np.int32) << 8)
            | (triplets[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values | ~0xFFFFFF, values)
        return values.astype(np.float32) / 8388608.0
    if width == 4:
        # wave accepts integer PCM (including PCM WAVE_FORMAT_EXTENSIBLE),
        # not IEEE-float WAV. Valid PCM32 bits may look like finite floats;
        # their magnitude cannot identify the container's sample encoding.
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32)
        return data / 2147483648.0
    raise AudioDecodeError(f"unsupported WAV sample width {width} bytes")


def _decode_wav(data: bytes) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(data)
        handle.flush()
        try:
            with wave.open(handle.name, "rb") as wav:
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except (wave.Error, EOFError) as exc:
            raise AudioDecodeError("invalid WAV container") from exc
    samples = _pcm_to_float(frames, width)
    if channels > 1:
        usable = (samples.size // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        samples = _resample_linear(samples, rate, SAMPLE_RATE)
    return samples


def _resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate <= 0:
        raise AudioDecodeError("invalid WAV sample rate")
    if samples.size == 0:
        return samples
    duration = samples.size / float(source_rate)
    target_count = max(1, int(round(duration * target_rate)))
    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.linspace(0.0, samples.size - 1, target_count, dtype=np.float64)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)


def _decode_with_ffmpeg(data: bytes, filename: str, timeout_seconds: float) -> np.ndarray:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise AudioDecodeError("ffmpeg is not available for this audio container")
    suffix = Path(filename).suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="lg-asr-") as directory:
        source = Path(directory) / f"input{suffix}"
        source.write_bytes(data)
        try:
            completed = subprocess.run(
                [
                    binary,
                    "-v",
                    "error",
                    "-nostdin",
                    "-i",
                    str(source),
                    "-ac",
                    "1",
                    "-ar",
                    str(SAMPLE_RATE),
                    "-f",
                    "f32le",
                    "-",
                ],
                capture_output=True,
                check=False,
                timeout=max(1.0, timeout_seconds),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AudioDecodeError("audio decoder did not complete") from exc
    if completed.returncode != 0 or not completed.stdout:
        raise AudioDecodeError("audio decoder rejected the input")
    return np.frombuffer(completed.stdout, dtype="<f4").astype(np.float32)


def decode_audio(
    data: bytes,
    *,
    filename: str = "audio",
    max_seconds: int,
    timeout_seconds: float = 60.0,
) -> np.ndarray:
    """Decode bytes to finite float32 mono 16 kHz samples, enforcing duration."""

    if not data:
        raise AudioDecodeError("empty audio input")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        samples = _decode_wav(data)
    else:
        samples = _decode_with_ffmpeg(data, filename, timeout_seconds)
    if samples.size == 0:
        raise AudioDecodeError("decoded zero samples")
    if not np.all(np.isfinite(samples)):
        raise AudioDecodeError("decoded audio contains non-finite samples")
    duration = samples.size / float(SAMPLE_RATE)
    if duration > max_seconds + 1e-6:
        raise AudioTooLong(f"audio duration {duration:.3f}s exceeds {max_seconds}s")
    return np.ascontiguousarray(samples, dtype=np.float32)


__all__ = [
    "AudioDecodeError",
    "AudioTooLong",
    "decode_audio",
]
