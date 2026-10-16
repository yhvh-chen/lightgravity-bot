"""LG-040 REVOKE-FIX-R1 real-TCP proof harness (independent-retest evidence).

Reproduces the confirmed MAJOR QA defect end-to-end over **real loopback TCP**
(real uvicorn + real ``FileStore`` + real ``create_app``), then proves the fix:

* BEFORE revoke: ``GET content`` / ``GET download`` = 200 with the marker bytes;
* ``revoke`` = 200 setting ``status=archived``;
* search hits = ``[]`` (already correct);
* AFTER revoke (fresh TCP request, ``Cache-Control: no-store``): ``GET content``
  and ``GET download`` are **refused** (existing ``not_found`` 404 mapping with
  ``details.revoked=true``) and **no marker byte is served in any kind**
  (``auto``/``formal``/``machine`` content; ``original``/``formal``/``machine``
  download);
* reversible ``archive``/``unarchive`` keeps the source openable + searchable;
* repeated ``revoke`` is idempotent; ``reprocess``/``formal`` cannot resurrect;
* a truly missing source still yields ``not_found``.

Isolation: OCR/vector target env vars are **unset**; zero external/LAN/model
calls; zero retries.  The machine derivative is a mechanical scripted seed and
is **not** quality evidence.  Server is stopped in ``finally``.

Run:  PYTHONPATH=<worktree>/backend python tcp_revoke_proof.py
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Fail loudly if any external target is configured (isolation guard).
for _var in (
    "LIGHTGRAVITY_OCR_BASE_URL",
    "LIGHTGRAVITY_OCR_MODEL",
    "LIGHTGRAVITY_VECTOR_BASE_URL",
    "LIGHTGRAVITY_VECTOR_MODEL",
    "LIGHTGRAVITY_VECTOR_TOKEN",
):
    os.environ.pop(_var, None)

MARKER = "REVOKE-FIX-MARKER-8f3a2c"

RESULTS: list[dict] = []


def record(case: str, ok: bool, detail: object) -> None:
    RESULTS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {detail}")


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _request(
    method: str, url: str, body: dict | None = None
) -> tuple[int, bytes, dict]:
    data = None
    headers = {"Cache-Control": "no-store"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, raw, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def main() -> int:
    import uvicorn

    from lightgravity.api.access import LocalAccessPolicy
    from lightgravity.api.app import create_app
    from lightgravity.api.sources import build_sources_router
    from lightgravity.config import Settings
    from lightgravity.contracts import API_PREFIX

    tmp = Path(tempfile.mkdtemp(prefix="lg040-revoke-fix-"))
    settings = Settings(
        data_dir=tmp / "data",
        workspace_root=tmp / "data" / "workspaces",
        secret_store=tmp / "secrets",
    )
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    app.include_router(build_sources_router(), prefix=API_PREFIX)

    port = _free_port()
    assert port != 8123, "must not use 8123"
    base = f"http://127.0.0.1:{port}{API_PREFIX}"

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for readiness (real TCP).
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            sock.close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        print("server did not start")
        return 2

    try:
        # --- create source + seed machine + formal through real endpoints -----
        status, raw, _ = _request(
            "POST",
            f"{base}/sources",
            {
                "request_id": "req-revoke-fix-1",
                "filename": "doc.txt",
                "content_base64": base64.b64encode(f"{MARKER} original".encode()).decode(),
                "media_type": "text/plain",
                "title": "Doc",
            },
        )
        assert status == 201, (status, raw)
        source_id = json.loads(raw)["source"]["source_id"]

        # Mechanical machine seed directly on the real store (no model call).
        from lightgravity.sources.content import ContentStore, MachineDraft, PageText

        store = app.state.source_service.store
        record_obj = store.read_source(source_id)
        content = ContentStore(source_root=store.source_dir(source_id))
        content.write_machine(
            MachineDraft(
                source_version=record_obj.source_version,
                filename="doc.txt",
                model="scripted",
                pages=[PageText(page=1, text=f"{MARKER} machine", input_sha256="0" * 64, model="scripted")],
                extractor="scripted",
                status="succeeded",
            )
        )
        app.state.source_service.lexical.index_source(source_id)
        st, _, _ = _request(
            "POST",
            f"{base}/sources/{source_id}/formal",
            {"content": f"{MARKER} formal", "edited_by": "user"},
        )
        assert st == 200, st

        # --- BEFORE revoke: content/download 200 with the marker --------------
        before: dict[str, object] = {}
        for kind in ("auto", "formal", "machine"):
            st, body, _ = _request("GET", f"{base}/sources/{source_id}/content?kind={kind}")
            before[f"content_{kind}"] = {"status": st, "serves_marker": MARKER.encode() in body}
        for kind in ("original", "formal", "machine"):
            st, body, _ = _request("GET", f"{base}/sources/{source_id}/download?kind={kind}")
            before[f"download_{kind}"] = {"status": st, "serves_marker": MARKER.encode() in body}
        record(
            "BEFORE content/download all kinds 200 + marker",
            all(v["status"] == 200 and v["serves_marker"] for v in before.values()),
            before,
        )

        # --- revoke ----------------------------------------------------------
        st, body, _ = _request("POST", f"{base}/sources/{source_id}/actions", {"action": "revoke"})
        revoke = json.loads(body)
        record("revoke 200 + status archived + revoked true", st == 200 and revoke.get("status") == "archived" and revoke.get("revoked") is True, {"status": st, "body": revoke})

        st, body, _ = _request("GET", f"{base}/sources/{source_id}")
        record("detail status archived (diagnosis view kept)", st == 200 and json.loads(body)["status"] == "archived", {"status": st, "status_field": json.loads(body)["status"]})

        st, body, _ = _request("GET", f"{base}/search?q={MARKER}&limit=20")
        hits = json.loads(body)["hits"] if st == 200 else None
        record("search hits [] after revoke", st == 200 and hits == [], {"status": st, "hits": hits})

        # --- AFTER revoke: refused, no marker bytes --------------------------
        after: dict[str, object] = {}
        for kind in ("auto", "formal", "machine"):
            st, body, _ = _request("GET", f"{base}/sources/{source_id}/content?kind={kind}")
            payload = json.loads(body)
            after[f"content_{kind}"] = {
                "status": st,
                "code": payload.get("error", {}).get("code"),
                "revoked": payload.get("error", {}).get("details", {}).get("revoked"),
                "serves_marker": MARKER.encode() in body,
            }
        for kind in ("original", "formal", "machine"):
            st, body, _ = _request("GET", f"{base}/sources/{source_id}/download?kind={kind}")
            payload = json.loads(body)
            after[f"download_{kind}"] = {
                "status": st,
                "code": payload.get("error", {}).get("code"),
                "revoked": payload.get("error", {}).get("details", {}).get("revoked"),
                "serves_marker": MARKER.encode() in body,
            }
        record(
            "AFTER content/download all kinds refused (404 not_found revoked) + no bytes",
            all(
                v["status"] == 404
                and v["code"] == "not_found"
                and v["revoked"] is True
                and not v["serves_marker"]
                for v in after.values()
            ),
            after,
        )

        # original + formal preserved on disk (no deletion/rollback).
        original_dir = store.original_dir(source_id)
        record(
            "original preserved on disk after revoke",
            any(p.is_file() for p in original_dir.iterdir()),
            sorted(p.name for p in original_dir.iterdir()),
        )

        # --- repeated revoke idempotent --------------------------------------
        st, body, _ = _request("POST", f"{base}/sources/{source_id}/actions", {"action": "revoke"})
        record("repeat revoke 200 idempotent", st == 200 and json.loads(body).get("revoked") is True, {"status": st})

        # --- adjacent paths cannot resurrect --------------------------------
        st, body, _ = _request("POST", f"{base}/sources/{source_id}/actions", {"action": "reprocess"})
        record("reprocess refused on revoked (no resurrection)", st == 404 and json.loads(body)["error"]["code"] == "not_found", {"status": st, "code": json.loads(body)["error"]["code"]})
        st, body, _ = _request("POST", f"{base}/sources/{source_id}/formal", {"content": f"{MARKER} edit", "edited_by": "user"})
        record("formal edit refused on revoked (no resurrection)", st == 404 and json.loads(body)["error"]["code"] == "not_found", {"status": st, "code": json.loads(body)["error"]["code"]})
        st, body, _ = _request("GET", f"{base}/sources/{source_id}/content")
        record("still refused after resurrection attempts", st == 404 and not MARKER.encode() in body, {"status": st})

        # --- archive/unarchive stays open + searchable -----------------------
        st, raw, _ = _request(
            "POST",
            f"{base}/sources",
            {
                "request_id": "req-revoke-fix-archive",
                "filename": "arch.txt",
                "content_base64": base64.b64encode(f"{MARKER} arch".encode()).decode(),
                "media_type": "text/plain",
                "title": "Arch",
            },
        )
        arch_id = json.loads(raw)["source"]["source_id"]
        rec2 = store.read_source(arch_id)
        ContentStore(source_root=store.source_dir(arch_id)).write_machine(
            MachineDraft(
                source_version=rec2.source_version,
                filename="arch.txt",
                model="scripted",
                pages=[PageText(page=1, text=f"{MARKER} arch machine", input_sha256="0" * 64, model="scripted")],
                extractor="scripted",
                status="succeeded",
            )
        )
        app.state.source_service.lexical.index_source(arch_id)
        _request("POST", f"{base}/sources/{arch_id}/actions", {"action": "archive"})
        st_c, _, _ = _request("GET", f"{base}/sources/{arch_id}/content")
        st_d, _, _ = _request("GET", f"{base}/sources/{arch_id}/download?kind=original")
        st_s, body_s, _ = _request("GET", f"{base}/search?q={MARKER}&limit=20")
        archived_hits = [h["source_id"] for h in json.loads(body_s)["hits"]] if st_s == 200 else None
        record(
            "archive keeps openable + searchable",
            st_c == 200 and st_d == 200 and archived_hits is not None and arch_id in archived_hits,
            {"content": st_c, "download": st_d, "search_hits": archived_hits},
        )
        _request("POST", f"{base}/sources/{arch_id}/actions", {"action": "unarchive"})
        st, body, _ = _request("GET", f"{base}/sources/{arch_id}")
        record("unarchive restores status != archived", st == 200 and json.loads(body)["status"] != "archived", {"status": json.loads(body)["status"]})

        # --- missing source unchanged ----------------------------------------
        st, body, _ = _request("GET", f"{base}/sources/source_01MISSINGMISSINGMISSING/content")
        record("missing source content 404 not_found", st == 404 and json.loads(body)["error"]["code"] == "not_found", {"status": st})
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        # port released
        released = False
        for _ in range(50):
            try:
                s2 = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                s2.close()
                time.sleep(0.1)
            except OSError:
                released = True
                break
        record("cleanup: server stopped / port released", released, {"port": port})

    failures = [r for r in RESULTS if not r["ok"]]
    out = Path(__file__).parent / "raw"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tcp_revoke_proof.json").write_text(
        json.dumps({"results": RESULTS, "failures": len(failures)}, indent=2) + "\n"
    )
    print(f"\n{len(RESULTS) - len(failures)}/{len(RESULTS)} PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
