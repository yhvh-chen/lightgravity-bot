#!/usr/bin/env python3
"""Start the isolated LG-112 QA app (real product code) on loopback.

Usage:
  PYTHONPATH=backend python qa/fixture_app.py --port 8891 --upstream-port 8892 \
      --data-dir /tmp/lg112-data --log-dir /tmp/lg112-logs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qa_common import build_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    runtime = build_runtime(
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        upstream_port=args.upstream_port,
    )

    import uvicorn

    uvicorn.run(
        runtime.app,
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
