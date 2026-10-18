"""LG-223: a material with no machine body can get its first human formal body."""

from __future__ import annotations

import base64

import httpx

from .conftest import make_png

HT = "/api/v1"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _upload(api: httpx.AsyncClient) -> str:
    response = await api.post(
        f"{HT}/sources",
        json={
            "request_id": "req-lg223-first-formal",
            "filename": "scan.png",
            "content_base64": _b64(make_png()),
            "media_type": "image/png",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["source"]["source_id"])


async def test_first_human_formal_is_readable_searchable_and_selectable(
    api: httpx.AsyncClient,
) -> None:
    source_id = await _upload(api)
    machine = await api.get(f"{HT}/sources/{source_id}/content", params={"kind": "machine"})
    assert machine.status_code == 404

    saved = await api.post(
        f"{HT}/sources/{source_id}/formal",
        json={
            "content": "handwritten invoice total 42\n",
            "edited_by": "user",
            "expected_revision": 0,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert saved.json()["formal"]["origin"] == "human"

    formal = await api.get(f"{HT}/sources/{source_id}/content", params={"kind": "formal"})
    assert formal.status_code == 200, formal.text
    body = formal.json()["content"]
    assert "handwritten invoice total 42" in body
    assert "formal provenance: human-authored" in body
    assert "formal version: human-edited" in body
    # The human body did not invent a machine derivative.
    missing_machine = await api.get(f"{HT}/sources/{source_id}/content", params={"kind": "machine"})
    assert missing_machine.status_code == 404

    detail = (await api.get(f"{HT}/sources/{source_id}")).json()
    assert detail["formal"]["origin"] == "human"
    assert detail["context_selectable"] is True
    assert detail["index"]["lexical"] == "indexed"
    assert detail["reprocess"]["kind"] == "ocr"

    found = await api.get(f"{HT}/search", params={"q": '"handwritten invoice"', "include_global": "true"})
    assert found.status_code == 200, found.text
    assert [hit["source_id"] for hit in found.json()["hits"]] == [source_id]

    conflict = await api.post(
        f"{HT}/sources/{source_id}/formal",
        json={"content": "stale overwrite", "edited_by": "user", "expected_revision": 0},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "revision_conflict"
    unchanged = await api.get(f"{HT}/sources/{source_id}/content", params={"kind": "formal"})
    assert "handwritten invoice total 42" in unchanged.json()["content"]
    assert "stale overwrite" not in unchanged.json()["content"]
