#!/usr/bin/env python3
"""Generate the corrected-experiment freeze manifest (exact epoch + hashes)."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent
REPO = ROOT.parents[1]  # /tmp/lightgravity-worktrees/agensh-sdk-corrected-20261015
VENV = Path("/home/yhvh/code/lightgravity-bot/.venv/lib/python3.12/site-packages/google/antigravity")

FROZEN_AT_EPOCH = 1792048031
FROZEN_AT_UTC = "2026-10-15T07:07:11Z"
BASE_COMMIT = "9987d4f643b3ad02618d0c45fa35f8eb6ae84eef"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    lines = [
        "# agensh-sdk-corrected-20261015 FREEZE MANIFEST",
        f"frozen_at_epoch: {FROZEN_AT_EPOCH}",
        f"frozen_at_utc: {FROZEN_AT_UTC}",
        f"branch: experiment/agensh-sdk-corrected-20261015",
        f"base_commit: {BASE_COMMIT}",
        "sdk: google-antigravity==0.1.22",
        "",
        "## probe files (driver / fixtures / docs)",
    ]
    runtime_files = [
        ROOT / "driver" / name for name in (
            "hooks.py", "host.py", "relay.py", "sessiondb.py", "experiment.py",
            "sotyaml.py", "calibrate.py",
        )
    ]
    probe_files = sorted(
        p for p in (runtime_files
                    + list((ROOT / "fixtures").rglob("*"))
                    + [ROOT / "PROTOCOL.md"])
        if p.is_file() and "__pycache__" not in p.parts
    )
    for p in probe_files:
        lines.append(f"{sha256_file(p)}  {p.relative_to(ROOT).as_posix()}")
    lines += ["", "## read-only product adapter (referenced, not modified)"]
    for rel in ("backend/lightgravity/adapter/executor.py",
                "backend/lightgravity/adapter/proxy.py",
                "backend/lightgravity/adapter/sdk_config.py",
                "backend/lightgravity/adapter/compiler.py",
                "backend/lightgravity/adapter/registry.py",
                "backend/lightgravity/adapter/credentials.py"):
        p = REPO / rel
        if p.exists():
            lines.append(f"{sha256_file(p)}  {rel}")
    lines += ["", "## sdk"]
    harness = VENV / "bin" / "localharness"
    if harness.exists():
        lines.append(f"{sha256_file(harness)}  {harness}")
    lines.append("google-antigravity==0.1.22")
    out = ROOT / "evidence" / "FREEZE_MANIFEST.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
