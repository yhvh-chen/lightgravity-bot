"""LG-040 revoke fix: a revoked source must be unavailable, fail-closed.

Confirmed MAJOR QA finding (``probes/lg040/API-R1-20261016/ACL-ADDENDUM.md``):

* before the fix, ``GET /sources/{id}/content`` and
  ``GET /sources/{id}/download`` still returned **200 with the bytes** after
  ``revoke`` (search was already correctly suppressed).
* docs/08 §6.6 / §4.3: ``revoke`` makes the material **unavailable**
  (``status=archived`` + hit invalidation), while the reversible
  ``archive``/``unarchive`` keeps the source searchable **and openable**.

These tests pin the fix end-to-end with a **real** ``FileStore`` + real
``create_app`` + real HTTP via the app's ASGI transport, over a fresh request
after the revoke (no stale response object).  No OCR/vector/env, no model or
external call; the machine derivative is seeded mechanically only.
"""

from __future__ import annotations

import base64

import httpx

from lightgravity.contracts import API_PREFIX
from lightgravity.contracts import ErrorCode

_HT = "http://testserver" + API_PREFIX

_MARKER = "REVOKE-MARKER-DEADBEEF"

_KINDS_CONTENT = ("auto", "formal", "machine")
_KINDS_DOWNLOAD = ("original", "formal", "machine")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _seed_machine(app, source_id: str, text: str) -> None:
    """Write a trusted machine derivative and index it (mechanical seed)."""

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


async def _seed_formal(api: httpx.AsyncClient, source_id: str, text: str) -> None:
    """Write a human formal version through the real formal-edit endpoint."""

    resp = await api.post(
        f"{_HT}/sources/{source_id}/formal",
        json={"content": text, "edited_by": "user"},
    )
    assert resp.status_code == 200, resp.text


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


async def _revoke(api: httpx.AsyncClient, source_id: str) -> httpx.Response:
    return await api.post(
        f"{_HT}/sources/{source_id}/actions", json={"action": "revoke"}
    )


async def _search(api: httpx.AsyncClient, query: str) -> dict:
    resp = await api.get(f"{_HT}/search", params={"q": query, "limit": 20})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_revoked_refusal(resp: httpx.Response, source_id: str) -> None:
    """The refusal is the existing ``not_found`` (404) fail-closed mapping."""

    assert resp.status_code == 404, resp.text
    error = resp.json()["error"]
    assert error["code"] == ErrorCode.NOT_FOUND
    assert error["details"]["revoked"] is True
    assert error["details"]["source_id"] == source_id
    # The revoked bytes must never appear in the refusal body.
    assert _MARKER not in resp.text


async def test_revoked_source_content_and_download_refused_all_kinds(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(
        api, f"{_MARKER} original body", request_id="req-revoke-all-kinds"
    )
    _seed_machine(app, source_id, f"{_MARKER} machine body")
    await _seed_formal(api, source_id, f"{_MARKER} formal body")

    # BEFORE revoke: every content/download kind is served with bytes.
    for kind in _KINDS_CONTENT:
        before = await api.get(
            f"{_HT}/sources/{source_id}/content", params={"kind": kind}
        )
        assert before.status_code == 200, (kind, before.text)
        assert _MARKER in before.json()["content"], kind
    for kind in _KINDS_DOWNLOAD:
        before = await api.get(
            f"{_HT}/sources/{source_id}/download", params={"kind": kind}
        )
        assert before.status_code == 200, (kind, before.text)
        assert _MARKER.encode() in before.content, kind

    assert (await _revoke(api, source_id)).status_code == 200

    # AFTER revoke (fresh requests): every kind is refused, no body bytes.
    for kind in _KINDS_CONTENT:
        after = await api.get(
            f"{_HT}/sources/{source_id}/content", params={"kind": kind}
        )
        _assert_revoked_refusal(after, source_id)
    for kind in _KINDS_DOWNLOAD:
        after = await api.get(
            f"{_HT}/sources/{source_id}/download", params={"kind": kind}
        )
        _assert_revoked_refusal(after, source_id)

    # Search was already suppressed before the fix and stays suppressed.
    hits = await _search(api, _MARKER)
    assert not any(h["source_id"] == source_id for h in hits["hits"]), hits


async def test_revoke_keeps_original_on_disk_and_diag_view(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(
        api, f"{_MARKER} preserved", request_id="req-revoke-preserve"
    )
    _seed_machine(app, source_id, f"{_MARKER} preserved machine")
    store = app.state.source_service.store
    original_dir = store.original_dir(source_id)
    before_files = sorted(p.name for p in original_dir.iterdir() if p.is_file())
    assert before_files

    revoked = await _revoke(api, source_id)
    assert revoked.status_code == 200
    payload = revoked.json()
    assert payload["revoked"] is True
    assert payload["status"] == "archived"

    # Raw bytes / evidence are preserved on disk (revoke != delete): the fix
    # must not delete anything.
    after_files = sorted(p.name for p in original_dir.iterdir() if p.is_file())
    assert after_files == before_files

    # The metadata/status diagnosis view is preserved so a client can see why.
    detail = await api.get(f"{_HT}/sources/{source_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "archived"


async def test_archive_and_unarchive_remain_openable_and_searchable(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(
        api, f"{_MARKER} archive-open", request_id="req-archive-open"
    )
    _seed_machine(app, source_id, f"{_MARKER} archive-open")

    archived = await api.post(
        f"{_HT}/sources/{source_id}/actions", json={"action": "archive"}
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True

    # Reversible archive: still searchable AND openable (docs/08 §6.6).
    hits = await _search(api, _MARKER)
    assert any(h["source_id"] == source_id for h in hits["hits"]), hits
    content = await api.get(f"{_HT}/sources/{source_id}/content")
    assert content.status_code == 200, content.text
    assert _MARKER in content.json()["content"]
    download = await api.get(
        f"{_HT}/sources/{source_id}/download", params={"kind": "original"}
    )
    assert download.status_code == 200, download.text
    assert _MARKER.encode() in download.content

    unarchived = await api.post(
        f"{_HT}/sources/{source_id}/actions", json={"action": "unarchive"}
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["archived"] is False
    # The reversible flag never set the revoke marker status.
    detail = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert detail["status"] != "archived"


async def test_revoke_is_repeatable_and_idempotent(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(api, f"{_MARKER} idem", request_id="req-revoke-idem")
    _seed_machine(app, source_id, f"{_MARKER} idem")

    first = await _revoke(api, source_id)
    assert first.status_code == 200
    assert first.json()["revoked"] is True

    # A repeated revoke is a safe no-op: still 200, still revoked, still refused.
    second = await _revoke(api, source_id)
    assert second.status_code == 200, second.text
    assert second.json()["revoked"] is True
    detail = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert detail["status"] == "archived"
    _assert_revoked_refusal(
        await api.get(f"{_HT}/sources/{source_id}/content"), source_id
    )


async def test_reprocess_cannot_resurrect_revoked_source(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(
        api, f"{_MARKER} no-resurrect", request_id="req-revoke-reprocess"
    )
    _seed_machine(app, source_id, f"{_MARKER} no-resurrect")
    assert (await _revoke(api, source_id)).status_code == 200

    # Reprocess rewrites ``status`` via the processing path; on a revoked source
    # it must fail closed rather than restore availability.
    reprocess = await api.post(
        f"{_HT}/sources/{source_id}/actions", json={"action": "reprocess"}
    )
    assert reprocess.status_code == 404, reprocess.text
    assert reprocess.json()["error"]["code"] == ErrorCode.NOT_FOUND

    # The source stays revoked and unavailable after the attempted reprocess.
    detail = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert detail["status"] == "archived"
    _assert_revoked_refusal(
        await api.get(f"{_HT}/sources/{source_id}/content"), source_id
    )
    _assert_revoked_refusal(
        await api.get(f"{_HT}/sources/{source_id}/download"), source_id
    )


async def test_formal_edit_cannot_resurrect_revoked_source(
    api: httpx.AsyncClient, app
) -> None:
    source_id = await _create(
        api, f"{_MARKER} no-formal", request_id="req-revoke-formal"
    )
    _seed_machine(app, source_id, f"{_MARKER} no-formal")
    await _seed_formal(api, source_id, f"{_MARKER} original formal")
    assert (await _revoke(api, source_id)).status_code == 200
    hits_before = await _search(api, _MARKER)
    # The pre-existing formal version is still present but now unavailable.
    _assert_revoked_refusal(
        await api.get(f"{_HT}/sources/{source_id}/content", params={"kind": "formal"}),
        source_id,
    )

    # The formal-edit path writes + re-indexes; it must refuse a revoked source
    # so availability cannot be recreated around the revocation.
    formal = await api.post(
        f"{_HT}/sources/{source_id}/formal",
        json={"content": f"{_MARKER} human edit", "edited_by": "user"},
    )
    assert formal.status_code == 404, formal.text
    assert formal.json()["error"]["code"] == ErrorCode.NOT_FOUND

    detail = (await api.get(f"{_HT}/sources/{source_id}")).json()
    assert detail["status"] == "archived"
    # The refused edit must not have advanced the existing formal revision.
    assert detail["formal"]["revision"] == 1
    hits_after = await _search(api, _MARKER)
    assert not any(h["source_id"] == source_id for h in hits_after["hits"])
    assert hits_after["hits"] == hits_before["hits"]
    _assert_revoked_refusal(
        await api.get(f"{_HT}/sources/{source_id}/content"), source_id
    )


async def test_normal_nonrevoked_source_unaffected(api: httpx.AsyncClient, app) -> None:
    """Guard against over-broadening: a live source behaves exactly as before."""

    source_id = await _create(
        api, f"{_MARKER} normal", request_id="req-normal-unaffected"
    )
    _seed_machine(app, source_id, f"{_MARKER} normal")

    hits = await _search(api, _MARKER)
    assert any(h["source_id"] == source_id for h in hits["hits"])

    content = await api.get(f"{_HT}/sources/{source_id}/content")
    assert content.status_code == 200
    assert content.json()["kind"] == "machine"
    assert _MARKER in content.json()["content"]

    download = await api.get(
        f"{_HT}/sources/{source_id}/download", params={"kind": "original"}
    )
    assert download.status_code == 200
    assert _MARKER.encode() in download.content

    detail = await api.get(f"{_HT}/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] != "archived"


async def test_missing_source_still_not_found(api: httpx.AsyncClient) -> None:
    """Existing not-found behavior for a truly missing source is unchanged."""

    missing = "source_01MISSINGMISSINGMISSING"
    for path in ("content", "download"):
        resp = await api.get(f"{_HT}/sources/{missing}/{path}")
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == ErrorCode.NOT_FOUND
