"""Redact absolute workspace paths from the PROOF2-CLOSE evidence for commit.

Strips the machine-specific worktree prefix (and any home path) so the committed
evidence has stable, environment-independent content.  No secret/model text is
present in the close evidence (it contains only product service returns, hashes
and state transitions).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def redact(obj, prefix: str, repl: str):
    if isinstance(obj, dict):
        return {k: redact(v, prefix, repl) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, prefix, repl) for v in obj]
    if isinstance(obj, str):
        if prefix and prefix in obj:
            return obj.replace(prefix, repl)
        return obj
    return obj


def main() -> int:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    prefix = str(Path(sys.argv[3]).resolve())
    data = json.loads(src.read_text())
    redacted = redact(data, prefix, "<WORKTREE>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
