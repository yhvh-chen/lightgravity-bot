"""LG-038 archive semantics: reversible archive vs. unrecoverable revoke.

The first-version integration found that LG-038 reused ``revoke`` (``status
-> archived`` + hit invalidation) as "organizational archive".  That conflates
two different things: tidying a source away is **reversible** and must keep the
source searchable/openable, while revoke makes it unavailable.  These tests
pin the additive, reversible semantics introduced in ``integrate/batch6``.

Real default app + real FileStore + real HTTP; no model/external service call.
"""

from __future__ import annotations

import base64

import httpx

from lightgravity.contracts import API_PREFIX

_HT = "http://testserver" + API_PREFIX


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _seed_machine(app, source_id: str, text: str) -> None:
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
    lexical = app.state.source_service.lexical
    if lexical is not None:
        lexical.index_source(source_id)


async def _create(api: httpx.AsyncClient, text: str, *, request_id: str) -> str:
    resp = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": request_id,
            "filename": "doc.txt",
            "content_base64": _b64(text.encode()),
            "media_type": "text/plain",
            "title": "Doc",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source"]["source_id"]


async def _search(api: httpx.AsyncClient, query: str) -> dict:
    resp = await api.get(f"{_HT}/search", params={"q": query, "limit": 20})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_archive_keeps_searchable_and_openable(api: httpx.AsyncClient, app) -> None:
    source_id = await _create(api, "archived检索保留 archive material", request_id="req-arch-1")
    _seed_machine(app, source_id, "archived检索保留 archive material")

    detail = await api.get(f"{_HT}/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["archived"] is False
    before_status = detail.json()["status"]

    archived = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "archive"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True

    # Reversible archive must NOT change status or invalidate hits.
    after = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert after["archived"] is True
    assert after["status"] == before_status

    # Still searchable.
    hits = await _search(api, "archive material")
    assert any(h["source_id"] == source_id for h in hits["hits"]), hits

    # Still openable.
    content = await api.get(f"{_HT}/sources/{source_id}/content")
    assert content.status_code == 200, content.text

    # Unarchive restores the plain state.
    unarchived = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "unarchive"},
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["archived"] is False
    final = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert final["archived"] is False


async def test_revoke_still_makes_unavailable_and_preserves_original(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(api, "revoke消失 revoke material", request_id="req-rev-1")
    _seed_machine(app, source_id, "revoke消失 revoke material")

    assert (await _search(api, "revoke material"))["hits"]

    revoked = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "revoke"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True

    # Revoke is the unrecoverable path: status archived, hits gone.
    detail = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert detail["status"] == "archived"
    hits = await _search(api, "revoke material")
    assert not any(h["source_id"] == source_id for h in hits["hits"]), hits

    # Original file is preserved (revoke != delete).
    store = app.state.source_service.store
    original_dir = store.original_dir(source_id)
    assert any(p.is_file() for p in original_dir.iterdir())


async def test_archive_idempotent_and_revision_checked(api: httpx.AsyncClient, app) -> None:
    source_id = await _create(api, "idem archive", request_id="req-idem-1")
    first = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "archive"},
    )
    assert first.status_code == 200
    # Idempotent: re-archiving stays archived (no error, no double effect).
    second = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "archive"},
    )
    assert second.status_code == 200
    assert second.json()["archived"] is True

    # An out-of-date expected_revision is rejected with a revision conflict.
    from lightgravity.contracts import ErrorCode

    conflict = await api.post(
        f"{_HT}/sources/{source_id}/actions",
        json={"action": "unarchive", "expected_revision": 0},
    )
    assert conflict.status_code in (409, 412), conflict.text
    assert conflict.json()["error"]["code"] == ErrorCode.REVISION_CONFLICT
