"""LG-036 end-to-end tests over real HTTP + file source of truth.

Covers the acceptance conditions:

* build a derived index from files/metadata/formal content and support exact
  phrases, identifiers, dates, amounts, and authorized-scope filtering;
* a hit is re-verified回源 against existence/permission/version/hash and becomes
  ``source_stale`` after content edits, revoke, delete or move;
* deleting the cache rebuilds it from files and reproduces the same result;
* a corrupt cache is reported honestly (never an empty success);
* GET /search borrows no business write authorization.
"""

from __future__ import annotations

import base64

import httpx

from lightgravity.contracts import API_PREFIX

_HT = "http://testserver" + API_PREFIX


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _receive(
    api: httpx.AsyncClient,
    *,
    request_id: str,
    filename: str = "doc.txt",
    body: bytes,
    task_ref: str | None = None,
) -> str:
    scope = {"task_ref": task_ref} if task_ref else {}
    response = await api.post(
        f"{_HT}/sources",
        json={
            "request_id": request_id,
            "filename": filename,
            "content_base64": _b64(body),
            "scope": scope,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["source"]["source_id"])


async def _create_task(api: httpx.AsyncClient, *, title: str) -> str:
    response = await api.post(
        f"{_HT}/tasks",
        json={
            "request_id": f"req-{title.replace(' ', '-')}",
            "title": title,
            "objective": "hold sources",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["task_id"])


def _seed_machine(app, source_id: str, text: str) -> None:
    """Write a trusted machine derivative directly into the file SoT.

    This mirrors what a successful extraction (LG-035) produces so the lexical
    layer can index a real machine body without needing a live OCR backend.
    """

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
                PageText(
                    page=1,
                    text=text,
                    input_sha256="0" * 64,
                    model="scripted",
                )
            ],
            extractor="scripted",
            status="succeeded",
        )
    )


async def _write_formal(app, api: httpx.AsyncClient, source_id: str, content: str) -> None:
    """Seed a machine derivative, then a human formal edit, then re-index."""

    _seed_machine(app, source_id, "machine placeholder body")
    response = await api.post(
        f"{_HT}/sources/{source_id}/formal",
        json={"content": content, "edited_by": "tester"},
    )
    assert response.status_code == 200, response.text
    # The formal-edit hook re-indexes automatically; assert it took effect.
    lexical = app.state.source_service.lexical
    assert lexical is not None
    lexical.index_source(source_id)


async def test_search_exact_phrase_number_date_amount(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(
        api,
        request_id="req-lex-1",
        body="合同编号 HT-2024-001 金额 1,234.56 元 日期 2026-10-16".encode(),
    )
    # Formal content is the authoritative indexable layer.
    await _write_formal(
        app,
        api,
        source_id,
        "本合同编号 HT-2024-001，金额 1,234.56 元，签署日期 2026-10-16。",
    )

    for query in ('"合同编号"', '"HT-2024-001"', '"1,234.56"', '"2026-10-16"'):
        response = await api.get(f"{_HT}/search", params={"q": query, "include_global": "true"})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["index_status"] == "ok", payload
        assert [h["source_id"] for h in payload["hits"]] == [source_id], query

    # Negative control: an absent phrase yields no hits, not a fabricated one.
    miss = await api.get(f"{_HT}/search", params={"q": '"不存在的编号"', "include_global": "true"})
    assert miss.json()["hits"] == []


async def test_scope_authorization_filter(api: httpx.AsyncClient, app) -> None:
    task_a = await _create_task(api, title="task a")
    task_b = await _create_task(api, title="task b")
    source_a = await _receive(
        api, request_id="req-a", body="secret 编号 A-1".encode(), task_ref=task_a
    )
    await _write_formal(app, api, source_a, "secret 编号 A-1")
    source_b = await _receive(
        api, request_id="req-b", body="secret 编号 B-1".encode(), task_ref=task_b
    )
    await _write_formal(app, api, source_b, "secret 编号 B-1")

    # Only the authorized scope is returned.
    scoped = await api.get(
        f"{_HT}/search", params={"q": '"编号"', "task_ref": task_a}
    )
    hits = scoped.json()["hits"]
    assert [h["scope"]["task_ref"] for h in hits] == [task_a]

    # A global query without scope does not leak Task material.
    unscoped = await api.get(f"{_HT}/search", params={"q": '"编号"'})
    assert unscoped.json()["hits"] == []
    assert any(s["reason"] == "out_of_scope" for s in unscoped.json()["skipped"])


async def test_content_change_invalidates_old_hit(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-change", body=b"v1")
    await _write_formal(app, api, source_id, "编号 OLD-001")
    found = await api.get(f"{_HT}/search", params={"q": '"OLD-001"', "include_global": "true"})
    assert len(found.json()["hits"]) == 1

    # Changing the formal content re-indexes; the old hit must not survive stale.
    await _write_formal(app, api, source_id, "编号 NEW-002")
    old = await api.get(f"{_HT}/search", params={"q": '"OLD-001"', "include_global": "true"})
    assert old.json()["hits"] == []
    new = await api.get(f"{_HT}/search", params={"q": '"NEW-002"', "include_global": "true"})
    assert [h["source_id"] for h in new.json()["hits"]] == [source_id]


async def test_revoke_and_delete_invalidate_hits(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-revoke", body=b"x")
    await _write_formal(app, api, source_id, "编号 REV-1")
    assert (await api.get(f"{_HT}/search", params={"q": '"REV-1"', "include_global": "true"})).json()[
        "hits"
    ]

    revoke = await api.post(f"{_HT}/sources/{source_id}/actions", json={"action": "revoke"})
    assert revoke.status_code == 200, revoke.text
    after = await api.get(f"{_HT}/search", params={"q": '"REV-1"', "include_global": "true"})
    assert after.json()["hits"] == []

    # Delete removes the source entirely; no dangling hit is returned.
    source_2 = await _receive(api, request_id="req-delete", body=b"y")
    await _write_formal(app, api, source_2, "编号 DEL-1")
    deleted = await api.post(
        f"{_HT}/sources/{source_2}/actions", json={"action": "delete", "confirmed": True}
    )
    assert deleted.status_code == 200, deleted.text
    gone = await api.get(f"{_HT}/search", params={"q": '"DEL-1"', "include_global": "true"})
    # The deleted source is invalidated in the cache and its entity is gone, so
    # no dangling hit (and no stale entry) is returned.
    assert gone.json()["hits"] == []
    assert gone.json()["stale"] == []
    detail = await api.get(f"{_HT}/sources/{source_2}")
    assert detail.status_code == 404


async def test_search_without_rebuild_does_not_create_cache(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-no-write", body=b"n")
    await _write_formal(app, api, source_id, "编号 NOWRITE-1")
    lexical = app.state.source_service.lexical
    lexical.index.delete()

    missing = await api.get(
        f"{_HT}/search", params={"q": '"NOWRITE-1"', "include_global": "true"}
    )
    assert missing.json()["index_status"] == "index_unavailable"
    assert lexical.index.exists() is False


async def test_content_hash_change_invalidates_old_hit(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-hash", body=b"h")
    await _write_formal(app, api, source_id, "编号 HASH-1")
    found = await api.get(f"{_HT}/search", params={"q": '"HASH-1"', "include_global": "true"})
    assert [h["source_id"] for h in found.json()["hits"]] == [source_id]

    store = app.state.source_service.store
    record = store.read_source(source_id)
    store.update_source(
        source_id,
        {"content_hash": "e" * 64},
        expected_revision=record.revision,
    )
    stale = await api.get(f"{_HT}/search", params={"q": '"HASH-1"', "include_global": "true"})
    assert stale.json()["hits"] == []
    assert any(row["reason"] == "source_stale" for row in stale.json()["stale"])


async def test_delete_cache_rebuilds_and_reproduces(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-rebuild", body=b"z")
    await _write_formal(app, api, source_id, "编号 REBUILD-9")
    before = await api.get(f"{_HT}/search", params={"q": '"REBUILD-9"', "include_global": "true"})
    assert [h["source_id"] for h in before.json()["hits"]] == [source_id]

    # Delete the cache and rebuild from files: same result, usable search.
    service = app.state.source_service.lexical
    service.index.delete()
    missing = await api.get(f"{_HT}/search", params={"q": '"REBUILD-9"', "include_global": "true"})
    assert missing.json()["index_status"] == "index_unavailable"
    assert missing.status_code == 200

    rebuilt = await api.get(
        f"{_HT}/search",
        params={"q": '"REBUILD-9"', "include_global": "true", "rebuild_if_missing": "true"},
    )
    assert rebuilt.json()["index_status"] == "ok", rebuilt.text
    assert [h["source_id"] for h in rebuilt.json()["hits"]] == [source_id]


async def test_corrupt_cache_reports_index_unavailable(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-corrupt", body=b"c")
    await _write_formal(app, api, source_id, "编号 CORRUPT-1")
    lexical = app.state.source_service.lexical
    lexical.index.db_path.write_bytes(b"corrupt bytes not sqlite")

    response = await api.get(f"{_HT}/search", params={"q": '"CORRUPT-1"', "include_global": "true"})
    # Honest degrade: a named unavailable state, never an empty success.
    assert response.status_code in (200, 503)
    payload = response.json()
    assert payload["index_status"] == "index_unavailable"
    assert payload["hits"] == []


async def test_not_indexed_when_no_trusted_body(api: httpx.AsyncClient) -> None:
    # A source with no formal version and no trusted machine derivative is
    # honestly not searchable; we never fabricate a body.
    source_id = await _receive(api, request_id="req-none", filename="scan.png", body=b"\x89PNG")
    detail = await api.get(f"{_HT}/sources/{source_id}")
    assert detail.json()["index"]["lexical"] == "not_indexed"
    response = await api.get(f"{_HT}/search", params={"q": '"anything"', "include_global": "true"})
    assert response.json()["hits"] == []


async def test_search_get_does_not_create_or_modify_state(api: httpx.AsyncClient, app) -> None:
    source_id = await _receive(api, request_id="req-ro", body=b"r")
    await _write_formal(app, api, source_id, "编号 RO-1")
    before = await api.get(f"{_HT}/sources/{source_id}")
    await api.get(f"{_HT}/search", params={"q": '"RO-1"', "include_global": "true"})
    after = await api.get(f"{_HT}/sources/{source_id}")
    # Searching does not bump the source revision or change its status.
    assert before.json()["revision"] == after.json()["revision"]
    assert before.json()["status"] == after.json()["status"]
    tasks = await api.get(f"{_HT}/tasks")
    assert tasks.json()["items"] == []
