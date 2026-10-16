"""F-INTAKE-FIX-R1: native UTF-8 extraction + selected-source error ordering.

This is the R1 repair package for the LG-047 QA findings.  It pins two
**frozen-contract** facts that the QA evidence showed were violated:

1. **Native, model-free text extraction (product defect).**  A plain
   ``text/plain`` / ``text/markdown`` upload through the *real* product app
   (``create_app`` + real lifespan + the shared coordinator ``source_service``)
   must reach a terminal ``extracted`` state with a readable machine body, and
   that body must be selectable — with **no** manual derivative seeding.  The
   product previously only offered an OCR path that refused ``text/plain``.

2. **Selected-source error ordering (docs/10 §5).**  For a valid, existing
   source the frozen order is: existence/cross-Task → ``reference_invalid``
   (422); revoke → ``not_found`` (404); stale version/hash → ``source_stale``
   (409) **even when the body is missing**; missing/unreadable body →
   ``capability_unavailable`` (503).  QA observed a bodyless source reporting
   ``reference_invalid`` for both the stale and the no-body case.

Everything here is offline: real product assembly, real HTTP routes via an
in-process ASGI transport, deterministic coordinator responder, **no model, no
network, no browser, no OCR backend synthesis**.  Embedded binary fixtures are
not valid UTF-8 by construction, so no OCR/raster work is exercised.
"""

from __future__ import annotations

import base64

import httpx

from lightgravity.sources.processing import (
    NATIVE_TEXT_EXTRACTOR,
    ProcessingEngine,
)

# --------------------------------------------------------------- helpers


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _upload(
    api: httpx.AsyncClient,
    *,
    request_id: str,
    filename: str,
    body: bytes,
    media_type: str | None,
) -> dict:
    payload: dict = {
        "request_id": request_id,
        "filename": filename,
        "content_base64": _b64(body),
    }
    if media_type is not None:
        payload["media_type"] = media_type
    response = await api.post("/api/v1/sources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _select_global(
    api: httpx.AsyncClient,
    *,
    message_id: str,
    source_id: str,
    source_version: int | None = None,
    content_hash: str | None = None,
) -> httpx.Response:
    ref: dict = {"source_id": source_id}
    if source_version is not None:
        ref["source_version"] = source_version
    if content_hash is not None:
        ref["content_hash"] = content_hash
    return await api.post(
        "/api/v1/conversations/global/messages",
        json={
            "message_id": message_id,
            "role": "user",
            "content": "summarize the selected source",
            "selected_sources": [ref],
        },
    )


PLAIN_UTF8 = (
    "PROJECT ORION-71 brief\n"
    "owner: Halden Reyes\n"
    "launch: 2027-03-14\n"
    "Ünïcödé 中文 body stays exact.\n"
)
MARKDOWN_UTF8 = "# Brief\n\n- owner: Halden Reyes\n- launch: 2027-03-14\n"
#: Not valid UTF-8 (lone 0xFF/0xFE bytes) — passed as text/plain.
MALFORMED_UTF8 = b"\xff\xfe not utf8 \x80\x81"
#: Opaque binary; neither UTF-8 text nor an image/PDF.
BINARY_BLOB = b"\x00\x01\x02\xff\xfe\xfd\x00binary\x00"


# -------------------------------------------- 1. native extraction (real app)


async def test_plain_utf8_upload_extracts_and_is_selectable(
    api: httpx.AsyncClient, app
) -> None:
    """Real upload → terminal receipt → exact content → selectable, no seeding."""

    result = await _upload(
        api,
        request_id="req-r1-plain",
        filename="alpha-brief.txt",
        body=PLAIN_UTF8.encode(),
        media_type="text/plain",
    )
    source_id = result["source"]["source_id"]

    # Terminal native state: extraction ran synchronously on the real path.
    assert result["source"]["status"] == "extracted"
    assert result["job"]["status"] == "succeeded"
    assert result["job"]["stage"] == "done"
    # A real receipt records the terminal extraction (searchable body present).
    receipt = await api.get(f"/api/v1/sources/{source_id}/receipt")
    assert receipt.status_code == 200, receipt.text
    receipt_body = receipt.json()
    assert receipt_body["status"] == "extracted"
    latest = receipt_body["items"][-1]
    assert latest["status"] == "extracted", latest
    assert latest["searchable"] is True
    assert latest["stage"] == "done"
    assert latest["formal_path"] == "derivative/machine.v1.md"

    # The machine body is served by the real content endpoint and contains the
    # exact native text (the derivative wraps it with traceable frontmatter).
    content = await api.get(f"/api/v1/sources/{source_id}/content", params={"kind": "auto"})
    assert content.status_code == 200, content.text
    served = content.json()
    assert served["kind"] == "machine"
    assert PLAIN_UTF8 in served["content"]
    assert "record_type: machine_native_text" in served["content"]
    assert "extractor: native-utf8-text" in served["content"]
    assert served["source_id"] == source_id

    # And it resolves for selection through the shared coordinator resolver with
    # NO manual derivative seeding anywhere in this test.
    selection = await _select_global(api, message_id="msg-r1-plain", source_id=source_id)
    assert selection.status_code == 200, selection.text
    data = selection.json()["data"]
    assert data["resolved_source_bindings"][0]["source_id"] == source_id
    assert data["resolved_source_bindings"][0]["layer"] == "machine"

    # The derivative records model-free provenance (no LLM/OCR was involved).
    service = app.state.source_service
    processing = ProcessingEngine.__new__(ProcessingEngine)
    assert NATIVE_TEXT_EXTRACTOR == "native-utf8-text"
    assert processing.is_native_text("text/plain") is True
    record = service.store.read_source(source_id)
    model_versions = {
        d.get("model_version") for d in record.entity.get("derivatives") or []
    }
    assert model_versions == {"none"}


async def test_markdown_upload_extracts_and_is_selectable(
    api: httpx.AsyncClient,
) -> None:
    result = await _upload(
        api,
        request_id="req-r1-md",
        filename="brief.md",
        body=MARKDOWN_UTF8.encode(),
        media_type="text/markdown",
    )
    source_id = result["source"]["source_id"]
    assert result["source"]["status"] == "extracted"

    content = await api.get(f"/api/v1/sources/{source_id}/content", params={"kind": "machine"})
    assert content.status_code == 200, content.text
    assert MARKDOWN_UTF8 in content.json()["content"]

    selection = await _select_global(api, message_id="msg-r1-md", source_id=source_id)
    assert selection.status_code == 200, selection.text


async def test_upload_without_media_type_does_not_fabricate_a_body(
    api: httpx.AsyncClient,
) -> None:
    """An explicit media type is required to pick the native path (no guessing).

    The product must not assume ``text/plain`` for an unlabelled body; the
    original is preserved and no body is fabricated.
    """

    result = await _upload(
        api,
        request_id="req-r1-notype",
        filename="mystery.txt",
        body=PLAIN_UTF8.encode(),
        media_type=None,
    )
    source_id = result["source"]["source_id"]
    assert result["source"]["status"] == "received"
    content = await api.get(f"/api/v1/sources/{source_id}/content", params={"kind": "auto"})
    assert content.status_code == 404, content.text
    assert content.json()["error"]["code"] == "not_found"


async def test_malformed_utf8_text_fails_honestly_no_fake_body(
    api: httpx.AsyncClient,
) -> None:
    result = await _upload(
        api,
        request_id="req-r1-badutf8",
        filename="bad.txt",
        body=MALFORMED_UTF8,
        media_type="text/plain",
    )
    source_id = result["source"]["source_id"]

    # Honest failure, not a fabricated body and not a 5xx receive.
    assert result["source"]["status"] == "failed"
    assert result["job"]["status"] == "failed"
    assert "not valid UTF-8" in (result["job"]["fail_reason"] or "")

    content = await api.get(f"/api/v1/sources/{source_id}/content", params={"kind": "auto"})
    assert content.status_code == 404, content.text

    # Selection reports the missing body as an explicit capability gap (503),
    # never a fabricated success and never reference_invalid.
    selection = await _select_global(
        api, message_id="msg-r1-badutf8", source_id=source_id
    )
    assert selection.status_code == 503, selection.text
    assert selection.json()["error"]["code"] == "capability_unavailable"


async def test_binary_upload_stays_unreadable_and_never_enters_native_path(
    api: httpx.AsyncClient, app
) -> None:
    result = await _upload(
        api,
        request_id="req-r1-binary",
        filename="blob.bin",
        body=BINARY_BLOB,
        media_type="application/octet-stream",
    )
    source_id = result["source"]["source_id"]
    # Not a native text type and not OCR-able → original preserved, no body,
    # and the synchronous native pump must not have touched it.
    assert result["source"]["status"] == "received"
    assert result["source"]["derivatives"] == []

    selection = await _select_global(
        api, message_id="msg-r1-binary", source_id=source_id
    )
    assert selection.status_code == 503, selection.text
    assert selection.json()["error"]["code"] == "capability_unavailable"


# ------------------------------------- 2. selected-source error ordering (API)


async def test_bodyless_existing_source_missing_body_is_capability_unavailable(
    api: httpx.AsyncClient,
) -> None:
    """A valid, existing, revocable source with no readable body → 503.

    This is the true "unreadable body" API case QA's N5 mislabelled as
    ``reference_invalid``.
    """

    result = await _upload(
        api,
        request_id="req-r1-nobody",
        filename="opaque.bin",
        body=BINARY_BLOB,
        media_type="application/octet-stream",
    )
    source_id = result["source"]["source_id"]
    response = await _select_global(api, message_id="msg-r1-nobody", source_id=source_id)
    assert response.status_code == 503, response.text
    body = response.json()["error"]
    assert body["code"] == "capability_unavailable"
    assert body["retryable"] is True
    assert body["details"]["source_id"] == source_id


async def test_bodyless_stale_version_is_source_stale_not_missing_body(
    api: httpx.AsyncClient,
) -> None:
    """A stale expected version wins over the missing-body gap → 409.

    A valid existing source with no body still has an authoritative version;
    an expired ``source_version`` must be reported as ``source_stale`` (docs/10
    §5), not conflated with the body gap.
    """

    result = await _upload(
        api,
        request_id="req-r1-stale-v",
        filename="opaque.bin",
        body=BINARY_BLOB,
        media_type="application/octet-stream",
    )
    source_id = result["source"]["source_id"]
    actual_version = result["source"]["source_version"]

    response = await _select_global(
        api,
        message_id="msg-r1-stale-v",
        source_id=source_id,
        source_version=actual_version + 5,
    )
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "source_stale"
    assert error["details"]["expected_version"] == actual_version + 5
    assert error["details"]["actual_version"] == actual_version


async def test_bodyless_stale_content_hash_is_source_stale(
    api: httpx.AsyncClient,
) -> None:
    result = await _upload(
        api,
        request_id="req-r1-stale-h",
        filename="opaque.bin",
        body=BINARY_BLOB,
        media_type="application/octet-stream",
    )
    source_id = result["source"]["source_id"]

    response = await _select_global(
        api,
        message_id="msg-r1-stale-h",
        source_id=source_id,
        content_hash="sha256:deadbeef",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "source_stale"


async def test_extracted_source_stale_version_still_409(api: httpx.AsyncClient) -> None:
    """The real QA N2 case: an uploaded (now extracted) source, stale version."""

    result = await _upload(
        api,
        request_id="req-r1-extracted-stale",
        filename="alpha.txt",
        body=PLAIN_UTF8.encode(),
        media_type="text/plain",
    )
    source_id = result["source"]["source_id"]
    actual_version = result["source"]["source_version"]
    assert result["source"]["status"] == "extracted"

    response = await _select_global(
        api,
        message_id="msg-r1-extracted-stale",
        source_id=source_id,
        source_version=actual_version + 5,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "source_stale"


async def test_nonexistent_source_is_reference_invalid(api: httpx.AsyncClient) -> None:
    response = await _select_global(
        api,
        message_id="msg-r1-missing",
        source_id="source_01M51Y7PCE017H50P1DD51DBWT",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "reference_invalid"


async def test_revoked_source_is_not_found_404(api: httpx.AsyncClient) -> None:
    result = await _upload(
        api,
        request_id="req-r1-revoke",
        filename="alpha.txt",
        body=PLAIN_UTF8.encode(),
        media_type="text/plain",
    )
    source_id = result["source"]["source_id"]
    revoke = await api.post(
        f"/api/v1/sources/{source_id}/actions", json={"action": "revoke"}
    )
    assert revoke.status_code == 200, revoke.text

    response = await _select_global(api, message_id="msg-r1-revoke", source_id=source_id)
    assert response.status_code == 404, response.text
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"].get("revoked") is True


async def _create_task(api: httpx.AsyncClient, *, title: str) -> str:
    response = await api.post(
        "/api/v1/tasks",
        json={
            "request_id": f"req-{title.replace(' ', '-')}",
            "title": title,
            "objective": "hold sources",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["task_id"])


async def test_cross_task_selection_is_reference_invalid_unchanged(
    api: httpx.AsyncClient,
) -> None:
    """A real, extracted source still fails cross-Task resolution (422).

    The native-text fix makes the body real (not seeded), so this proves the
    cross-Task guard is enforced on a *resolvable* source, not masked by the
    old missing-body branch.  The error code is the frozen
    ``reference_invalid`` and is unchanged by the R1 repair.
    """

    task_a = await _create_task(api, title="r1 task a")
    task_b = await _create_task(api, title="r1 task b")
    uploaded = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-r1-cross",
            "filename": "scoped.txt",
            "content_base64": _b64(PLAIN_UTF8.encode()),
            "media_type": "text/plain",
            "scope": {"task_ref": task_a},
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    source_id = uploaded.json()["source"]["source_id"]
    # The scoped native upload really extracted (a resolvable body exists).
    assert uploaded.json()["source"]["status"] == "extracted"

    # Selecting task A's source from task B is refused before any body read.
    response = await api.post(
        f"/api/v1/tasks/{task_b}/messages",
        json={
            "message_id": "msg-r1-cross",
            "content": "summarize",
            "selected_sources": [{"source_id": source_id}],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "reference_invalid"


async def test_oversized_native_text_fails_honestly_no_fake_body(
    api: httpx.AsyncClient,
) -> None:
    """A native text original above the extraction bound fails honestly.

    The bound is a *product* limit (never a silent truncation into a fake
    body): the original is preserved, the source is ``failed`` and the body is
    genuinely absent.
    """

    from lightgravity.sources.processing import NATIVE_TEXT_MAX_BYTES

    oversized = b"A" * (NATIVE_TEXT_MAX_BYTES + 1)
    result = await _upload(
        api,
        request_id="req-r1-oversize",
        filename="huge.txt",
        body=oversized,
        media_type="text/plain",
    )
    source_id = result["source"]["source_id"]
    assert result["source"]["status"] == "failed"
    assert result["job"]["status"] == "failed"
    assert "size limit" in (result["job"].get("fail_reason") or "")

    content = await api.get(f"/api/v1/sources/{source_id}/content", params={"kind": "auto"})
    assert content.status_code == 404, content.text

    selection = await _select_global(
        api, message_id="msg-r1-oversize", source_id=source_id
    )
    assert selection.status_code == 503, selection.text
    assert selection.json()["error"]["code"] == "capability_unavailable"
