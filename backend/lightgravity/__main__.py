"""``python -m lightgravity`` -> ``lightgravity`` CLI (LG-020)."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
