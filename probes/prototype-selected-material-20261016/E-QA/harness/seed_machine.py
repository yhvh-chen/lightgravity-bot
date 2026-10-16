#!/usr/bin/env python3
"""LG-047 E-QA — materialize a *trusted machine body* for an ingested source.

Why this exists
---------------
The LG-047 brief explicitly expects QA to capture a "formal or **trusted machine
body**" for the selected material.  On this candidate, a plain-`.txt` upload
ends at intake stage ``received`` and no extraction runs (``processing.py``
only handles PDF/image OCR and reports "unsupported media type for OCR").  The
human ``POST /sources/{id}/formal`` path additionally refuses with
``not_found`` ("no machine derivative exists to seed the formal version"), so a
plain-text source can have **no** readable body through the product API at all.

To exercise the real selected-material pipeline (the actual prototype under
test) without spending LAN OCR calls, QA materializes the trusted machine
derivative using the **product's own** ``ContentStore.write_machine`` — the very
writer the OCR extraction path uses.  This is fixture setup, clearly labelled;
it is NOT a claim that the product's plain-text intake produces a body.  That
gap is reported as a finding (see REPORT.md D1/D2).

Usage:
    python seed_machine.py --data-dir <dir> --source-id <id> --text-file <path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from lightgravity.sources.content import ContentStore, MachineDraft, PageText  # noqa: E402
from lightgravity.sources.store import SourceStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--extractor", default="qa-machine-fixture")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    store = SourceStore(data_dir)
    record = store.read_source(args.source_id)
    text = Path(args.text_file).read_text("utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    content = ContentStore(source_root=store.source_dir(args.source_id))
    draft = MachineDraft(
        source_version=record.source_version,
        filename=Path(args.text_file).name,
        model="qa-fixture",
        pages=[PageText(page=1, text=text, input_sha256=sha, model="qa-fixture")],
        extractor=args.extractor,
        status="succeeded",
    )
    written = content.write_machine(draft)
    print(json.dumps({
        "source_id": args.source_id,
        "source_version": record.source_version,
        "markdown_path": written.get("markdown_path"),
        "markdown_sha256": written.get("markdown_sha256"),
        "body_sha256": sha,
        "chars": len(text),
    }, indent=2))


if __name__ == "__main__":
    main()
