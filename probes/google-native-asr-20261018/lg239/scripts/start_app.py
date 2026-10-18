#!/usr/bin/env python3
"""LG-239 isolated Team-mode app startup with a transparent Google audit wrapper.

This script is QA scaffolding only.  It does not touch product sources.

The wrapper forwards every call to the real product default HTTPS transport,
returns the response unchanged, and records only non-secret transport metadata
(host/path/status/request byte count/module flags/RSS).  It never records the
request body, audio base64, headers or API key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

AUDITED_MODULES = (
    "torch",
    "numpy",
    "transformers",
    "lightgravity.asr.runtime",
    "lightgravity.asr.reader_model",
    "eg2_reader",
)


def _rss_kib() -> int | None:
    try:
        fields = Path("/proc/self/statm").read_text("ascii").split()
        return int(fields[1]) * os.sysconf("SC_PAGE_SIZE") // 1024
    except (OSError, ValueError, IndexError):
        return None


def _module_flags() -> dict[str, bool]:
    return {name: name in sys.modules for name in AUDITED_MODULES}


def _audit(path: Path, record: dict) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (payload + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def install_audit(module, audit_path: Path) -> None:
    original = module.HttpConnectionTransport
    attempts = {"count": 0}

    class AuditedHttpConnectionTransport:
        def post(self, *, url, headers, body, timeout):
            from urllib.parse import urlparse

            attempts["count"] += 1
            attempt = attempts["count"]
            parsed = urlparse(url)
            started = time.monotonic()
            rss_before = _rss_kib()
            status = None
            response_bytes = None
            error_class = None
            try:
                status, payload = original().post(
                    url=url, headers=headers, body=body, timeout=timeout
                )
                response_bytes = len(payload)
                return status, payload
            except BaseException as exc:  # recorded, then re-raised unchanged
                error_class = type(exc).__name__
                raise
            finally:
                _audit(
                    audit_path,
                    {
                        "kind": "google_transport_call",
                        "attempt": attempt,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "endpoint_host": (parsed.hostname or "").lower(),
                        "endpoint_path": parsed.path,
                        "status": status,
                        "request_bytes": len(body),
                        "response_bytes": response_bytes,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "header_names": sorted(str(name).lower() for name in headers),
                        "key_header_present": any(
                            str(name).lower() == "x-goog-api-key" for name in headers
                        ),
                        "error_class": error_class,
                        "rss_kib_before": rss_before,
                        "rss_kib_after": _rss_kib(),
                        "modules": _module_flags(),
                    },
                )

    module.HttpConnectionTransport = AuditedHttpConnectionTransport
    _audit(
        audit_path,
        {
            "kind": "audit_installed",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "modules": _module_flags(),
            "rss_kib": _rss_kib(),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--secret-store", required=True)
    parser.add_argument("--frontend-dist", required=True)
    parser.add_argument("--audit-jsonl", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18239)
    parser.add_argument("--token", default="lg239-local-runtime-token-not-a-provider-key")
    args = parser.parse_args()

    # Prove the product subprocess was not handed a provider credential.
    forbidden = sorted(
        name
        for name in os.environ
        if any(
            marker in name.upper()
            for marker in (
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
                "LG_GOOGLE_ASR_API_KEY",
                "GOOGLE_API_KEY",
                "GEMINI_API_KEY",
                "LIGHTGRAVITY_OCR_TOKEN",
            )
        )
    )
    if forbidden:
        print(
            "REFUSING TO START: provider credential env present: " + ",".join(forbidden),
            file=sys.stderr,
            flush=True,
        )
        return 3

    import lightgravity.asr.google_native as google_native
    from lightgravity.api.bootstrap import StartupOptions, build_runtime
    from lightgravity.config import Settings
    from lightgravity.runtime.token import RuntimeToken

    audit_path = Path(args.audit_jsonl)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if audit_path.exists():
        raise SystemExit(f"refusing to overwrite existing audit log: {audit_path}")
    install_audit(google_native, audit_path)

    settings = Settings(
        data_dir=Path(args.data_dir),
        workspace_root=Path(args.data_dir) / "workspaces",
        secret_store=Path(args.secret_store),
        host=args.host,
        port=args.port,
        team_mode=True,
        team_accounts=Path(args.data_dir) / "team" / "accounts.json",
    )
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken(args.token, "lg239-fixture"),
            frontend_dist=Path(args.frontend_dist),
            serve_frontend=True,
            wire_real_executor=False,
            seed_default_admin=True,
            tester=False,
            log=lambda message: print(f"[startup] {message}", flush=True),
        )
    )
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": f"http://{args.host}:{args.port}",
                "data_dir": args.data_dir,
                "secret_store": args.secret_store,
                "frontend_dist": args.frontend_dist,
                "frontend_served": state.frontend_served,
                "executor_wired": state.executor_wired,
                "team_mode": settings.team_mode,
                "modules_at_start": _module_flags(),
                "rss_kib_at_start": _rss_kib(),
                "audit_log": args.audit_jsonl,
            },
            indent=2,
        ),
        flush=True,
    )

    import uvicorn

    uvicorn.run(state.app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
