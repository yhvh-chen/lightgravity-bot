#!/usr/bin/env python3
"""LG-235 scoped Google native audio probe: one GET + one POST per H1/H2.

Credentials come only from the inherited process environment variable
``LG_GOOGLE_ASR_API_KEY`` (mapped by the runner from the root .env).  The key is
sent only in the ``x-goog-api-key`` header and is never printed, written to a
file, or put in a URL.  Request audio bytes/base64 and headers are not logged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/yhvh/code/lightgravity-bot")
OUT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "probes/english-asr-20261018/lg163/artifacts/tts"
CLIPS = [
    ("H1", AUDIO_DIR / "qa-h1-harbor.piper-ljspeech-high.16k.wav"),
    ("H2", AUDIO_DIR / "qa-h2-clinic.piper-ljspeech-high.16k.wav"),
]
HOST = "generativelanguage.googleapis.com"
MODEL = "gemini-3.8-flash"
ENDPOINT = f"https://{HOST}/v1beta/interactions"
META = f"https://{HOST}/v1beta/models/{MODEL}"
PROMPT = (
    "Transcribe the speech in this audio verbatim. Return only the plain "
    "transcription text, with no commentary, labels, or formatting."
)


def _key() -> str:
    value = os.environ.get("LG_GOOGLE_ASR_API_KEY", "")
    if not value:
        raise SystemExit("LG_GOOGLE_ASR_API_KEY is not set in the process environment")
    return value


def _redact(value: str, key: str) -> str:
    return value.replace(key, "[REDACTED]")


def _request(url: str, key: str, *, payload: dict | None = None, timeout: int = 120):
    data = None
    headers = {"x-goog-api-key": key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            return response.status, body, time.monotonic() - started, dict(response.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, body, time.monotonic() - started, dict(exc.headers)
    except Exception as exc:  # noqa: BLE001 - sanitized transport failure
        return None, str(exc).encode("utf-8"), time.monotonic() - started, {}


def _body_json(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def _response_text(parsed):
    if not isinstance(parsed, dict):
        return None
    direct = parsed.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    # Documented SDK reads interaction.output_text; REST wraps the interaction.
    interaction = parsed.get("interaction")
    if isinstance(interaction, dict):
        direct = interaction.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
    steps = parsed.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            content = step.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("output_text")
                        if isinstance(text, str) and text.strip():
                            return text
    for candidate in ("outputs", "output", "candidates"):
        value = parsed.get(candidate)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("output_text")
                    if isinstance(text, str) and text.strip():
                        return text
    return None


def _usage(parsed):
    if not isinstance(parsed, dict):
        return None
    for candidate in ("usage", "usage_metadata", "usageMetadata"):
        value = parsed.get(candidate)
        if isinstance(value, dict):
            return value
    interaction = parsed.get("interaction")
    if isinstance(interaction, dict):
        for candidate in ("usage", "usage_metadata", "usageMetadata"):
            value = interaction.get(candidate)
            if isinstance(value, dict):
                return value
    return None


def main() -> int:
    key = _key()
    report = {
        "probe": "LG-235 google native audio",
        "official_sources": [
            "https://ai.google.dev/gemini-api/docs/audio",
            "https://ai.google.dev/gemini-api/docs/generate-content/audio",
            "https://ai.google.dev/gemini-api/docs/transcribe",
        ],
        "endpoint_host": HOST,
        "endpoint_path": "/v1beta/interactions",
        "model": MODEL,
        "prompt": PROMPT,
        "requests": [],
        "stop_reason": None,
    }

    prior = None
    for prior_name in ("attempt1-harness-parse-failure.json", "probe-report.json"):
        prior_path = OUT / prior_name
        if prior_path.is_file():
            try:
                prior = json.loads(prior_path.read_text(encoding="utf-8"))
                break
            except Exception:  # noqa: BLE001 - ignored archival read
                prior = None
    if prior and isinstance(prior.get("model_metadata"), dict):
        report["model_metadata"] = prior["model_metadata"]
        report["metadata_reused_from_prior_run"] = True
    else:
        status, body, latency, _headers = _request(META, key, timeout=30)
        parsed = _body_json(body)
        meta_record = {
            "kind": "model_metadata",
            "status": status,
            "latency_seconds": round(latency, 3),
            "sanitized_body": _redact(body.decode("utf-8", "replace"), key)[:4000],
        }
        report["requests"].append(meta_record)
        if status != 200:
            report["stop_reason"] = "model_metadata_failed"
            (OUT / "probe-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"metadata_status": status, "stop_reason": report["stop_reason"]}))
            return 2
        if isinstance(parsed, dict):
            report["model_metadata"] = {
                k: parsed.get(k)
                for k in ("name", "displayName", "description", "supportedGenerationMethods", "inputTokenLimit", "outputTokenLimit", "version")
                if k in parsed
            }

    for clip, path in CLIPS:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        response_path = OUT / f"{clip.lower()}-response.json"
        prior_record = None
        if prior and isinstance(prior.get("requests"), list):
            for item in prior["requests"]:
                if isinstance(item, dict) and item.get("kind") == "transcription" and item.get("clip") == clip:
                    prior_record = item
                    break
        if response_path.is_file():
            # Resume from an already-recorded HTTP 200 response: no new inference.
            parsed_body = json.loads(response_path.read_text(encoding="utf-8"))
            text = _response_text(parsed_body)
            record = {
                "kind": "transcription",
                "clip": clip,
                "audio_path": str(path.relative_to(ROOT)),
                "audio_sha256": sha,
                "audio_bytes": len(raw),
                "mime_type": "audio/wav",
                "status": (prior_record or {}).get("status", 200),
                "latency_seconds": (prior_record or {}).get("latency_seconds"),
                "usage": _usage(parsed_body) or (prior_record or {}).get("usage"),
                "text": text,
                "reused_existing_response": response_path.name,
                "top_level_keys": sorted(parsed_body.keys()) if isinstance(parsed_body, dict) else None,
            }
        else:
            payload = {
                "model": MODEL,
                "input": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "audio",
                        "data": base64.b64encode(raw).decode("ascii"),
                        "mime_type": "audio/wav",
                    },
                ],
            }
            status, body, latency, _headers = _request(ENDPOINT, key, payload=payload, timeout=180)
            parsed_body = _body_json(body)
            text = _response_text(parsed_body)
            record = {
                "kind": "transcription",
                "clip": clip,
                "audio_path": str(path.relative_to(ROOT)),
                "audio_sha256": sha,
                "audio_bytes": len(raw),
                "mime_type": "audio/wav",
                "status": status,
                "latency_seconds": round(latency, 3),
                "usage": _usage(parsed_body),
                "text": text,
                "top_level_keys": sorted(parsed_body.keys()) if isinstance(parsed_body, dict) else None,
                "sanitized_body": None if text else _redact(body.decode("utf-8", "replace"), key)[:8000],
            }
            response_path.write_text(
                json.dumps(parsed_body, indent=2)[:200000], encoding="utf-8"
            )
        report["requests"].append(record)
        if record["status"] != 200 or not text:
            report["stop_reason"] = f"{clip}_protocol_or_status_failure"
            (OUT / "probe-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"clip": clip, "status": record["status"], "stop_reason": report["stop_reason"]}))
            return 3
        (OUT / f"{clip.lower()}-transcript.txt").write_text(text.strip() + "\n", encoding="utf-8")
        print(json.dumps({"clip": clip, "status": record["status"], "latency_seconds": record["latency_seconds"], "chars": len(text)}))

    (OUT / "probe-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
