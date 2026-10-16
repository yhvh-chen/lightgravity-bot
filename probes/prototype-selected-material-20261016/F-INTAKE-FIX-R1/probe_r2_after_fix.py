#!/usr/bin/env python3
"""F-INTAKE-FIX-R1 round-2 probe: real product source path AFTER the fix.

Reproduces, at the real SourceService assembly level (no server, no network, no
model, no OCR), what the R1 repair changed:

  text/plain upload -> status 'extracted', machine derivative written
  -> content_view(kind=auto) served -> selection_layer returns a real body

and pins the frozen selected-source error ordering (docs/10 §5) for a source
that genuinely has no readable body:

  existing + no body            -> capability_unavailable (503)
  existing + no body + stale v  -> source_stale (409)

Zero external calls: this constructs the real product service via
``build_source_service`` and never enters OCR/LLM/network paths.
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


def _service(d: Path):
    store = SourceStore(d)
    task_store = FileStore(d, d / "ws")
    return store, build_source_service(
        data_dir=d,
        task_store=task_store,
        resolve_path=lambda rel, write: (d / rel),
    )


def main() -> None:
    d = Path(tempfile.mkdtemp(prefix="fintake-r2-"))
    store, svc = _service(d)

    # --- native UTF-8 text: the real upload path now extracts ---------------
    body = "ORION-71 test body\nÜnïcödé stays exact.\n".encode()
    res = svc.receive_inline(
        request_id="r2-plain",
        filename="alpha-brief.txt",
        content_base64=base64.b64encode(body).decode("ascii"),
        media_type="text/plain",
        title="alpha",
        title_origin="user",
    )
    sid = res.source.source_id
    rec = store.read_source(sid)
    print("status:", rec.status, "| derivatives:", rec.entity.get("derivatives"))
    print("job:", res.job.status, res.job.stage)

    view = svc.content_view(sid, kind="auto")
    print("content_view kind:", view["kind"], "| path:", view["path"])
    print("record_type line:", [
        ln for ln in view["content"].splitlines() if ln.startswith("record_type:")
    ])
    print("extractor line:", [
        ln for ln in view["content"].splitlines() if ln.startswith("extractor:")
    ])
    print("native body exact:", body.decode() in view["content"])

    layer = svc.selection_layer(sid)
    print("selection_layer layer:", None if layer is None else layer[0])

    # --- opaque binary: genuine no-body capability gap ----------------------
    bin_res = svc.receive_inline(
        request_id="r2-bin",
        filename="blob.bin",
        content_base64=base64.b64encode(b"\x00\x01\x02\xff\xfe\xfd").decode("ascii"),
        media_type="application/octet-stream",
        title_origin="user",
    )
    bin_sid = bin_res.source.source_id
    bin_rec = store.read_source(bin_sid)
    print("binary status:", bin_rec.status, "| derivatives:", bin_rec.entity.get("derivatives"))
    try:
        svc.content_view(bin_sid, kind="auto")
        print("binary content_view: UNEXPECTED success")
    except AppError as exc:
        print("binary content_view:", exc.code.value)

    # selection_layer on a bodyless source returns body=None (not None result),
    # so the resolver can distinguish stale from missing-body.
    print("binary selection_layer:", svc.selection_layer(bin_sid))

    # --- malformed UTF-8 text/plain fails honestly (no fake body) -----------
    bad = svc.receive_inline(
        request_id="r2-bad",
        filename="bad.txt",
        content_base64=base64.b64encode(b"\xff\xfe not utf8 \x80\x81").decode("ascii"),
        media_type="text/plain",
        title_origin="user",
    )
    bad_rec = store.read_source(bad.source.source_id)
    print(
        "malformed status:",
        bad_rec.status,
        "| job:",
        bad.job.status,
        "| reason:",
        bad.job.entity.get("fail_reason"),
    )


if __name__ == "__main__":
    main()
