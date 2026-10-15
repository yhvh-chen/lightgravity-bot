"""LG-038 end-to-end: Chat intake → receipt → Files same source → search → open.

Closes the real HTTP loop the task requires, on the **real default app**
(``create_app``) with a real ``FileStore`` and the already-mounted sources and
search routers:

* Chat upload (``POST /sources``) lands the original first and creates **no**
  delivery Task/Run/team;
* the per-file receipt (``GET .../receipt``) and the Files list
  (``GET /sources``) read the **same** source state;
* a pasted link is recorded ``link_only`` (``fetched=false``) and is never
  indexed as text;
* the lexical query returns the source with its version + content hash;
* opening the source with its version (``GET .../content``) returns the body,
  and a stale/revoked source is refused.

No model/external service is called (scripted machine derivative mirrors a
successful extraction); ASR/vector/OCR services are not required.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from lightgravity.contracts import API_PREFIX

_HT = "http://testserver" + API_PREFIX


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _seed_machine(app: Any, source_id: str, text: str) -> None:
    """Write a trusted machine derivative (what a successful extraction yields)."""

    from lightgravity.sources.content import ContentStore, MachineDraft, PageText

    store = app.state.source_service.store
    record = store.read_source(source_id)
    content = ContentStore(source_root=store.source_dir(source_id))
    content.write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename="doc.txt",
            model="scripted",
            pages=[
                PageText(page=1, text=text, input_sha256="0" * 64, model="scripted")
            ],
            extractor="scripted",
            status="succeeded",
        )
    )


async def _task_count(api: httpx.AsyncClient) -> int:
    return len((await api.get(f"{_HT}/tasks")).json()["items"])


async def test_chat_upload_to_files_search_open_loop(api: httpx.AsyncClient, app: Any) -> None:
    before_tasks = await _task_count(api)

    # --- Chat upload: the original is stored first, no delivery Task/Run.
    upload = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": "req-lg038-upload",
            "filename": "contract.txt",
            "content_base64": _b64("合同编号 LG038-001 金额 9,999.00".encode()),
            "origin": {"kind": "upload", "fetched": False},
        },
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    source_id = body["source"]["source_id"]
    assert body["created"] is True
    # No delivery Task/Run/team is created by intake.
    assert await _task_count(api) == before_tasks

    # --- Receipt: the per-file state the Chat shows.
    receipt = await api.get(f"{_HT}/sources/{source_id}/receipt")
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["source_id"] == source_id
    assert receipt.json()["status"] == "received"

    # --- Files reads the same source state (one list endpoint).
    listing = await api.get(f"{_HT}/sources", params={"limit": 50})
    assert listing.status_code == 200, listing.text
    listed = {item["source_id"]: item for item in listing.json()["items"]}
    assert source_id in listed
    assert listed[source_id]["status"] == "received"
    assert listed[source_id]["revision"] == body["source"]["revision"]

    # --- A scripted successful extraction makes the body searchable.
    _seed_machine(app, source_id, "合同编号 LG038-001 金额 9,999.00")
    lexical = app.state.source_service.lexical
    assert lexical is not None
    lexical.index_source(source_id)

    # --- Lexical query returns the source with version + content hash.
    found = await api.get(
        f"{_HT}/search", params={"q": '"LG038-001"', "include_global": "true"}
    )
    assert found.status_code == 200, found.text
    hits = found.json()["hits"]
    assert [h["source_id"] for h in hits] == [source_id]
    hit = hits[0]
    assert hit["verified"] is True
    assert hit["source_version"] >= 1
    assert hit["content_hash"]

    # --- Open with version: read the body back from the same source.
    opened = await api.get(f"{_HT}/sources/{source_id}/content", params={"kind": "auto"})
    assert opened.status_code == 200, opened.text
    assert "LG038-001" in opened.json()["content"]

    # --- Download the original with a stat revision (not a crypto hash).
    download = await api.get(f"{_HT}/sources/{source_id}/download", params={"kind": "original"})
    assert download.status_code == 200, download.text
    assert download.headers.get("x-lg-stat-revision")
    assert download.headers.get("x-lg-kind") == "original"


async def test_link_is_link_only_and_never_indexed(api: httpx.AsyncClient) -> None:
    link = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": "req-lg038-link",
            "filename": "example.com",
            "content_base64": "",
            "media_type": "text/uri-list",
            "title": "https://example.com/report",
            "origin": {
                "kind": "link",
                "external_ref": "https://example.com/report",
                "fetched": False,
            },
        },
    )
    assert link.status_code == 201, link.text
    source = link.json()["source"]
    source_id = source["source_id"]
    assert source["origin"]["kind"] == "link"
    assert source["origin"]["fetched"] is False

    # No fetched text ⇒ not indexed; a query cannot return it as a body.
    result = await api.get(
        f"{_HT}/search", params={"q": '"https://example.com/report"', "include_global": "true"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["hits"] == []

    # And there is no trusted content to open.
    content = await api.get(f"{_HT}/sources/{source_id}/content")
    assert content.status_code == 404


async def test_revoked_source_hit_is_refused_and_original_preserved(
    api: httpx.AsyncClient, app: Any
) -> None:
    received = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": "req-lg038-revoke",
            "filename": "note.txt",
            "content_base64": _b64("编号 REVOKE-9".encode()),
        },
    )
    assert received.status_code == 201, received.text
    source_id = received.json()["source"]["source_id"]
    _seed_machine(app, source_id, "编号 REVOKE-9")
    lexical = app.state.source_service.lexical
    assert lexical is not None
    lexical.index_source(source_id)
    assert (
        await api.get(f"{_HT}/search", params={"q": '"REVOKE-9"', "include_global": "true"})
    ).json()["hits"]

    revoke = await api.post(f"{_HT}/sources/{source_id}/actions", json={"action": "revoke"})
    assert revoke.status_code == 200, revoke.text

    # Old hit is refused (not a dangling result), and the original is preserved.
    after = await api.get(
        f"{_HT}/search", params={"q": '"REVOKE-9"', "include_global": "true"}
    )
    assert after.json()["hits"] == []
    preserved = await api.get(
        f"{_HT}/sources/{source_id}/download", params={"kind": "original"}
    )
    assert preserved.status_code == 200, preserved.text


async def test_partial_or_failed_extraction_never_becomes_text(
    api: httpx.AsyncClient, app: Any
) -> None:
    """A failed extraction must not fabricate a searchable body."""

    received = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": "req-lg038-fail",
            "filename": "scan.png",
            "content_base64": _b64(b"\x89PNG fake"),
            "media_type": "image/png",
        },
    )
    assert received.status_code == 201, received.text
    source_id = received.json()["source"]["source_id"]

    # Mark a *failed* machine derivative directly (mirrors an OCR failure).
    from lightgravity.sources.content import ContentStore, MachineDraft

    store = app.state.source_service.store
    record = store.read_source(source_id)
    content = ContentStore(source_root=store.source_dir(source_id))
    content.write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename="scan.png",
            model="scripted",
            pages=[],
            extractor="scripted",
            status="failed",
        )
    )

    lexical = app.state.source_service.lexical
    assert lexical is not None
    doc, reason = lexical.document_for(store.read_source(source_id))
    assert doc is None, "a failed extraction must not yield an indexed document"

    # The original is still preserved for retry/download (File SoT).
    preserved = await api.get(
        f"{_HT}/sources/{source_id}/download", params={"kind": "original"}
    )
    assert preserved.status_code == 200, preserved.text
