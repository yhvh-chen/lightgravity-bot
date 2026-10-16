#!/usr/bin/env python3
"""F-INTAKE-FIX-R1 round-1 probe: real product source path, zero external calls.

Reproduces, at the SourceService/API assembly level (no server, no network, no
model), exactly what QA observed through HTTP:

  upload text/plain -> status 'received', derivatives [] -> content 404
  selection_layer -> None -> reference_invalid 'does not resolve'

and shows the OCR-only processing path refuses text/plain as unsupported.
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from lightgravity.contracts import AppError  # noqa: E402
from lightgravity.sources import SourceStore, build_source_service  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402


def main() -> None:
    d = Path(tempfile.mkdtemp(prefix="fintake-r1-"))
    store = SourceStore(d)
    task_store = FileStore(d, d / "ws")
    svc = build_source_service(
        data_dir=d,
        task_store=task_store,
        resolve_path=lambda rel, write: (d / rel),
    )
    body = b"ORION-71 test body\n"
    res = svc.receive_inline(
        request_id="r1",
        filename="alpha-brief.txt",
        content_base64=base64.b64encode(body).decode("ascii"),
        media_type="text/plain",
        title="alpha",
        title_origin="user",
    )
    sid = res.source.source_id
    rec = store.read_source(sid)
    print("status:", rec.status, "| derivatives:", rec.entity.get("derivatives"))
    print("content_digest:", rec.content_digest)

    try:
        view = svc.content_view(sid, kind="auto")
        print("content_view:", view)
    except AppError as exc:
        print("content_view ERROR:", exc.code.value, "|", exc.message)

    print("selection_layer:", svc.selection_layer(sid))

    out = svc.process_source(sid, force=True)
    print("process_source:", out)

    try:
        print("content_view after process:", svc.content_view(sid, kind="auto"))
    except AppError as exc:
        print("content_view after process ERROR:", exc.code.value, "|", exc.message)


if __name__ == "__main__":
    main()
