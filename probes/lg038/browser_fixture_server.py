#!/usr/bin/env python3
"""LG-038 real-HTTP browser fixture server.

Boots the **real** ``create_app()`` (sources + search routers already mounted)
with a fixture data dir, seeds one source with a scripted machine body (no OCR /
model call) plus one link-only source, and serves the built frontend ``dist/``
at ``/`` so a real browser can exercise the same-origin Chat/Files material
surfaces.

Evidence tooling only: it does not modify product code, task state, contracts or
dependencies, and it calls no model/external service.
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.sources import build_source_service
from lightgravity.sources.content import ContentStore, MachineDraft, PageText


def _service_for(app: FastAPI):
    """Mirror ``api/sources.py::_service`` so we reuse the router's engine."""

    cached = getattr(app.state, "source_service", None)
    if cached is not None:
        return cached
    ctx = app.state.context

    def _resolve(relative: str, write: bool):
        return ctx.store.resolve_path(relative, write=write)

    service = build_source_service(
        data_dir=ctx.data_dir,
        task_store=ctx.store,
        resolve_path=_resolve,
        events=ctx.store,
    )
    app.state.source_service = service
    return service


def _seed_upload(service, *, request_id: str, filename: str, text: str) -> str:
    data = text.encode("utf-8")
    result = service.receive_inline(
        request_id=request_id,
        filename=filename,
        content_base64=base64.b64encode(data).decode("ascii"),
        media_type="text/plain",
        title=filename,
        origin_kind="upload",
        fetched=False,
    )
    source_id = result.source.source_id
    store = service.store
    record = store.read_source(source_id)
    content = ContentStore(source_root=store.source_dir(source_id))
    content.write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename=filename,
            model="scripted",
            pages=[PageText(page=1, text=text, input_sha256="0" * 64, model="scripted")],
            extractor="scripted",
            status="succeeded",
        )
    )
    if service.lexical is not None:
        service.lexical.index_source(source_id)
    return source_id


def _seed_link(service, *, request_id: str, url: str) -> str:
    result = service.receive_inline(
        request_id=request_id,
        filename="example.com",
        content_base64="",
        media_type="text/uri-list",
        title=url,
        origin_kind="link",
        external_ref=url,
        fetched=False,
    )
    return result.source.source_id


def build(data_dir: Path, dist_dir: Path) -> FastAPI:
    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir / "secrets",
    )
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )

    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="ui")
    # Seed synchronously so the fixture is ready before uvicorn serves traffic.
    service = _service_for(app)
    service.create_inbox()
    _seed_upload(
        service,
        request_id="req-fixture-doc",
        filename="invoice.txt",
        text="Invoice LG038-001 total 9,999.00 due 2026-10-16",
    )
    _seed_link(service, request_id="req-fixture-link", url="https://example.com/report")
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    app = build(Path(args.data_dir), Path(args.dist_dir))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
