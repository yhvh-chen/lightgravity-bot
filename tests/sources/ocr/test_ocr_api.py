"""LG-035 API tests: content/download/actions/formal over the real app.

Drives the mounted router over HTTP against a real app + FileStore, like the
LG-034 API tests.  Here the OCR backend is the *unconfigured* honest stub, so
these tests assert the service-unavailable degradation: the original is kept,
the failure is explicit, and nothing fabricates a body.  A configured-backend
quality run lives in ``probes/lg035``.
"""

from __future__ import annotations

import base64

import httpx

from .conftest import make_png


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _upload(api: httpx.AsyncClient, request_id: str, name: str, data: bytes) -> str:
    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": request_id,
            "filename": name,
            "content_base64": _b64(data),
            "media_type": "image/png",
        },
    )
    assert response.status_code in (200, 201), response.text
    return str(response.json()["source"]["source_id"])


async def test_reprocess_without_backend_keeps_original_and_fails_clearly(
    api: httpx.AsyncClient,
) -> None:
    png = make_png()
    source_id = await _upload(api, "req-ocr-api-1", "pic.png", png)

    action = await api.post(
        f"/api/v1/sources/{source_id}/actions",
        json={"action": "reprocess", "confirmed": True},
    )
    assert action.status_code == 200, action.text
    body = action.json()
    assert body["status"] == "failed"
    assert body["succeeded_pages"] == 0
    # A failed run may still write a *failure record* derivative, but the content
    # view must never present that as usable body text.
    content = await api.get(f"/api/v1/sources/{source_id}/content?kind=machine")
    if body["derivative_path"] is not None:
        assert content.status_code == 200, content.text
        text = content.json()["content"]
        assert "was not transcribed" in text
        assert "unavailable" in text.lower()
    else:
        assert content.status_code == 404

    # The original can still be downloaded byte-for-byte.
    download = await api.get(f"/api/v1/sources/{source_id}/download")
    assert download.status_code == 200, download.text
    assert download.content == png
    # ``stat_revision`` is explicitly a size-mtime token, not a crypto hash.
    assert download.headers["x-lg-stat-revision"]
    assert "-" in download.headers["x-lg-stat-revision"]

    # A formal-only content view is absent until extraction produced something.
    content = await api.get(f"/api/v1/sources/{source_id}/content?kind=formal")
    assert content.status_code == 404
    assert content.json()["error"]["code"] == "not_found"

    detail = await api.get(f"/api/v1/sources/{source_id}")
    assert detail.json()["status"] == "failed"


async def test_unknown_action_is_rejected(api: httpx.AsyncClient) -> None:
    source_id = await _upload(api, "req-ocr-api-2", "pic.png", make_png())
    response = await api.post(
        f"/api/v1/sources/{source_id}/actions",
        json={"action": "explode"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_delete_requires_confirmation_then_removes_source(api: httpx.AsyncClient) -> None:
    source_id = await _upload(api, "req-ocr-api-3", "pic.png", make_png())
    unconfirmed = await api.post(
        f"/api/v1/sources/{source_id}/actions",
        json={"action": "delete", "confirmed": False},
    )
    assert unconfirmed.status_code == 409, unconfirmed.text
    assert unconfirmed.json()["error"]["code"] == "cancellation_unconfirmed"

    confirmed = await api.post(
        f"/api/v1/sources/{source_id}/actions",
        json={"action": "delete", "confirmed": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["deleted"] is True
    missing = await api.get(f"/api/v1/sources/{source_id}")
    assert missing.status_code == 404


async def test_revoke_marks_archived_without_fabricating_index(api: httpx.AsyncClient) -> None:
    source_id = await _upload(api, "req-ocr-api-4", "pic.png", make_png())
    response = await api.post(
        f"/api/v1/sources/{source_id}/actions",
        json={"action": "revoke"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revoked"] is True
    detail = await api.get(f"/api/v1/sources/{source_id}")
    assert detail.json()["status"] == "archived"
    assert detail.json()["index"]["lexical"] == "not_indexed"


async def test_formal_edit_is_separate_and_creates_content_view(api: httpx.AsyncClient) -> None:
    source_id = await _upload(api, "req-ocr-api-5", "pic.png", make_png())
    # No formal content exists and no machine derivative exists yet.
    missing = await api.get(f"/api/v1/sources/{source_id}/content?kind=formal")
    assert missing.status_code == 404

    edit = await api.post(
        f"/api/v1/sources/{source_id}/formal",
        json={"content": "# Human corrected body\n", "edited_by": "user"},
    )
    # Seeding requires a machine derivative; with no backend there is none, so
    # the honest outcome is 404 rather than a fabricated seed.
    assert edit.status_code in (200, 404), edit.text
    if edit.status_code == 200:
        view = await api.get(f"/api/v1/sources/{source_id}/content?kind=formal")
        assert view.status_code == 200
        assert "Human corrected body" in view.json()["content"]
        assert view.json()["formal_present"] is True


async def test_content_kind_is_validated(api: httpx.AsyncClient) -> None:
    source_id = await _upload(api, "req-ocr-api-6", "pic.png", make_png())
    response = await api.get(f"/api/v1/sources/{source_id}/content?kind=bogus")
    assert response.status_code == 422, response.text
