#!/usr/bin/env python3
"""LG-003 probe: record exact SDK / runtime / platform versions and credentials present.

Never prints credential values -- only whether a variable is present.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import os
import platform
import sys


def main() -> int:
    import google.antigravity as ag

    pkg = md.distribution("google-antigravity")
    binary = None
    for f in pkg.files or []:
        if str(f).replace("\\", "/").endswith("google/antigravity/bin/localharness"):
            binary = f.locate()
            break
    binary_info = None
    if binary is not None and os.path.exists(binary):
        digest = hashlib.sha256()
        with open(binary, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        binary_info = {
            "path": str(binary),
            "size_bytes": os.path.getsize(binary),
            "sha256": digest.hexdigest(),
        }
    dep_names = [
        "google-antigravity", "google-genai", "pydantic", "mcp", "uvicorn",
        "websockets", "protobuf", "absl-py",
    ]
    info = {
        "sdk": {
            "distribution": "google-antigravity",
            "version": md.version("google-antigravity"),
            "module_file": ag.__file__,
        },
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dependencies": {n: md.version(n) for n in dep_names},
        "localharness": binary_info,
        "credentials_present": {
            name: bool(os.environ.get(name))
            for name in (
                "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            )
        },
    }
    print(json.dumps(info, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
