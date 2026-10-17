#!/usr/bin/env python3
"""LG-112 independent HTTP/API/security/provider probe.

Runs the real candidate app over actual loopback HTTP with fresh temp roots and
the controlled fake protocol upstream.  It records exact requests/responses,
snapshot deltas, secret canaries and the reference/delete concurrency schedule.

No real vendor/key/model is used.  The fake upstream is explicitly not a vendor.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from qa_common import (
    DUMMY_KEYS,
    QA_ADMIN,
    QA_ADMIN_PW,
    QA_MEMBER,
    QA_MEMBER_PW,
    build_runtime,
    sanitize_environment,
)

RESULTS: dict[str, Any] = {}


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def snapshot(root: Path, *, exclude_generation: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if exclude_generation and rel.startswith("generation/"):
            continue
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def scan_for(root: Path, needle: str, *, skip: tuple[str, ...] = ()) -> list[str]:
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(item) for item in skip):
            continue
        try:
            if needle in path.read_text("utf-8", "ignore"):
                hits.append(rel)
        except OSError:
            continue
    return hits


def run_server(runtime: Any, port: int) -> tuple[Any, threading.Thread]:
    import uvicorn

    config = uvicorn.Config(
        runtime.app, host="127.0.0.1", port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="lg112-http-probe", daemon=True)
    thread.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1)
            if response.status_code == 200:
                return server, thread
        except Exception:  # noqa: BLE001 - startup polling
            pass
        time.sleep(0.1)
    raise RuntimeError("qa app did not become healthy")


def login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


def main() -> int:
    sanitize_environment()
    base = Path(tempfile.mkdtemp(prefix="lg112-http-probe-"))
    runtime = build_runtime(
        data_dir=base / "data",
        log_dir=base / "logs",
        upstream_port=free_port(),
    )
    port = free_port()
    server, thread = run_server(runtime, port)
    url = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=url, timeout=30)
    member = httpx.Client(base_url=url, timeout=30)
    anon = httpx.Client(base_url=url, timeout=30)
    try:
        RESULTS["base_url"] = url
        RESULTS["data_dir"] = str(runtime.data_dir)
        RESULTS["upstream_base_url"] = runtime.upstream.base_url
        RESULTS["health"] = client.get("/api/v1/health").status_code

        # ---------------------------------------------------------- auth gates
        anon_checks = {
            "get_connections": anon.get("/api/v1/settings/connections").status_code,
            "get_settings": anon.get("/api/v1/settings").status_code,
            "draft": anon.post(
                "/api/v1/settings/connections/test-draft",
                json={"connection": {"backend": "gemini", "model": "m"}},
            ).status_code,
            "delete": anon.request(
                "DELETE",
                "/api/v1/settings/connections/qa-custom",
                json={"expected_revision": 0},
            ).status_code,
        }
        RESULTS["anonymous_statuses"] = anon_checks
        assert anon_checks == {
            "get_connections": 401,
            "get_settings": 401,
            "draft": 401,
            "delete": 401,
        }, anon_checks

        assert login(client, QA_ADMIN, QA_ADMIN_PW).status_code == 200
        assert login(member, QA_MEMBER, QA_MEMBER_PW).status_code == 200
        member_checks = {
            "get_connections": member.get("/api/v1/settings/connections").status_code,
            "get_settings": member.get("/api/v1/settings").status_code,
            "draft": member.post(
                "/api/v1/settings/connections/test-draft",
                json={"connection": {"backend": "gemini", "model": "gemini-3.8-flash"}},
            ).status_code,
            "delete": member.request(
                "DELETE",
                "/api/v1/settings/connections/qa-custom",
                json={"expected_revision": 0},
            ).status_code,
        }
        RESULTS["member_statuses"] = member_checks
        assert member_checks == {
            "get_connections": 403,
            "get_settings": 403,
            "draft": 403,
            "delete": 403,
        }, member_checks
        RESULTS["member_my_account"] = member.get("/api/v1/account").status_code
        RESULTS["member_accounts_admin"] = member.get("/api/v1/accounts").status_code

        # ------------------------------------------------- draft no-write static
        canary = "sk-static-canary-do-not-persist-112"
        before = snapshot(runtime.data_dir)
        expected_before = runtime.upstream.records.__len__()
        static = client.post(
            "/api/v1/settings/connections/test-draft",
            json={
                "connection": {
                    "backend": "gemini",
                    "model": "gemini-3.8-flash",
                    "auth_mode": "api_key",
                },
                "credential_value": canary,
                "allow_network": False,
            },
        )
        after = snapshot(runtime.data_dir)
        RESULTS["draft_static"] = {
            "status": static.status_code,
            "draft": static.json().get("draft"),
            "connection_id": static.json().get("connection_id"),
            "connection_revision": static.json().get("connection_revision"),
            "overall": static.json().get("overall"),
            "layers": static.json().get("layers"),
            "snapshot_diff": diff(before, after),
            "canary_in_response": canary in static.text,
            "canary_in_data": scan_for(runtime.data_dir, canary),
            "upstream_delta": len(runtime.upstream.records) - expected_before,
        }
        assert static.status_code == 200, static.text
        assert canary not in static.text
        assert RESULTS["draft_static"]["snapshot_diff"] == {
            "added": [],
            "removed": [],
            "changed": [],
        }
        assert RESULTS["draft_static"]["canary_in_data"] == []
        assert RESULTS["draft_static"]["upstream_delta"] == 0
        assert static.json()["draft"] is True
        assert static.json()["connection_id"] is None
        assert static.json()["connection_revision"] is None
        assert [layer["name"] for layer in static.json()["layers"]] == [
            "config_parse",
            "credential",
            "capability",
            "runtime_network",
            "tool_probe",
            "structured_output",
        ]

        # --------------------------------------------- draft fake protocol network
        def draft_network(model: str, key: str) -> httpx.Response:
            return client.post(
                "/api/v1/settings/connections/test-draft",
                json={
                    "connection": {
                        "backend": "openai-compat",
                        "model": model,
                        "base_url": runtime.upstream.base_url + "/v1",
                        "auth_mode": "proxy_api_key",
                    },
                    "credential_value": key,
                    "allow_network": True,
                },
            )

        gen_before = client.get("/__qa__/state").json()["generation"]["count"]
        up_before = len(runtime.upstream.records)
        snap_before = snapshot(runtime.data_dir, exclude_generation=True)
        canary_net = "sk-network-canary-do-not-persist-112"
        network = draft_network("qa-echo", canary_net)
        snap_after = snapshot(runtime.data_dir, exclude_generation=True)
        gen_after = client.get("/__qa__/state").json()["generation"]["count"]
        up_after = len(runtime.upstream.records)
        last_record = runtime.upstream.records[-1] if up_after > up_before else {}
        RESULTS["draft_network"] = {
            "status": network.status_code,
            "overall": network.json().get("overall"),
            "layers": network.json().get("layers"),
            "snapshot_diff": diff(snap_before, snap_after),
            "generation_delta": gen_after - gen_before,
            "upstream_delta": up_after - up_before,
            "upstream_path": last_record.get("path"),
            "upstream_model": last_record.get("model"),
            "upstream_authorization": last_record.get("authorization"),
            "upstream_body": last_record.get("body"),
            "canary_in_response": canary_net in network.text,
            "canary_in_data": scan_for(runtime.data_dir, canary_net),
        }
        assert network.status_code == 200, network.text
        assert network.json()["overall"] == "verified"
        assert RESULTS["draft_network"]["generation_delta"] == 1
        assert RESULTS["draft_network"]["upstream_delta"] == 1
        assert RESULTS["draft_network"]["upstream_authorization"] == f"Bearer {canary_net}"
        assert canary_net not in network.text
        assert RESULTS["draft_network"]["canary_in_data"] == []
        assert '"max_tokens": 1' in str(last_record.get("body"))
        assert '"tools"' not in str(last_record.get("body"))

        # repeat + concurrent: each click is exactly one request, no lifetime cap
        repeat_results = [draft_network("qa-echo", "sk-repeat-a"), draft_network("qa-echo", "sk-repeat-b")]
        RESULTS["draft_repeat"] = {
            "statuses": [r.status_code for r in repeat_results],
            "overalls": [r.json().get("overall") for r in repeat_results],
            "upstream_delta": len(runtime.upstream.records) - up_after,
        }
        assert RESULTS["draft_repeat"]["upstream_delta"] == 2

        up_before = len(runtime.upstream.records)
        gen_before = client.get("/__qa__/state").json()["generation"]["count"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(draft_network, "qa-echo", "sk-concurrent-a"),
                pool.submit(draft_network, "qa-echo", "sk-concurrent-b"),
            ]
            concurrent = [f.result(timeout=30) for f in futures]
        up_after = len(runtime.upstream.records)
        gen_after = client.get("/__qa__/state").json()["generation"]["count"]
        auths = [record.get("authorization") for record in runtime.upstream.records[-2:]]
        RESULTS["draft_concurrent"] = {
            "statuses": [r.status_code for r in concurrent],
            "overalls": [r.json().get("overall") for r in concurrent],
            "upstream_delta": up_after - up_before,
            "generation_delta": gen_after - gen_before,
            "authorizations": auths,
        }
        assert RESULTS["draft_concurrent"]["upstream_delta"] == 2
        assert RESULTS["draft_concurrent"]["generation_delta"] == 2
        assert sorted(auths) == ["Bearer sk-concurrent-a", "Bearer sk-concurrent-b"]

        # ---------------------------------------------------- inline failure case
        fail = draft_network("qa-fail-model", "sk-fail-dummy")
        RESULTS["draft_failure"] = {
            "status": fail.status_code,
            "overall": fail.json().get("overall"),
            "network": [x for x in fail.json().get("layers", []) if x["name"] == "runtime_network"],
            "canary_in_response": "sk-fail-dummy" in fail.text,
        }
        assert fail.json()["overall"] == "failed"
        assert "sk-fail-dummy" not in fail.text

        # ------------------------------------------------- saved test persists
        saved = client.post(
            "/api/v1/settings/connections/qa-tested/test",
            json={"expected_revision": 0, "allow_network": False},
        )
        view = client.get("/api/v1/settings/connections/qa-tested")
        RESULTS["saved_test"] = {
            "status": saved.status_code,
            "draft": saved.json().get("draft"),
            "connection_id": saved.json().get("connection_id"),
            "revision": saved.json().get("connection_revision"),
            "last_test": view.json().get("last_test"),
        }
        assert saved.status_code == 200
        assert saved.json()["draft"] is False
        assert view.json()["last_test"]["connection_revision"] == 0
        assert "credential_ref" not in view.json()["last_test"]

        # ----------------------------------------------- custom host honest block
        from lightgravity.settings import ConnectionTester
        from lightgravity.settings.testing import DraftConnectionSpec

        blocked_tester = ConnectionTester(
            runtime.service,
            allow_network=True,
            allow_loopback_upstream=False,
            http_timeout=5,
            upstream_timeout=5,
        )
        up_before = len(runtime.upstream.records)
        blocked_error: dict[str, Any] = {}
        try:
            blocked = blocked_tester.test_draft(
                DraftConnectionSpec(
                    backend="openai-compat",
                    model="qa-echo",
                    base_url=runtime.upstream.base_url + "/v1",
                    auth_mode="proxy_api_key",
                ),
                credential_value="sk-blocked-dummy",
                allow_network=True,
            )
            blocked_error = {
                "raised": False,
                "overall": blocked.overall,
                "network": blocked.layer("runtime_network").to_dict(),
            }
        except Exception as exc:  # noqa: BLE001 - product refusal evidence
            blocked_error = {
                "raised": True,
                "type": type(exc).__name__,
                "message": str(exc),
            }
        RESULTS["custom_host_blocked"] = {
            **blocked_error,
            "upstream_delta": len(runtime.upstream.records) - up_before,
            "canary_in_error": "sk-blocked-dummy" in json.dumps(blocked_error),
        }
        assert RESULTS["custom_host_blocked"]["upstream_delta"] == 0
        assert "not authorized" in json.dumps(blocked_error)

        # ------------------------------------------------ default capability gate
        current_settings = client.get("/api/v1/settings").json()
        gemini_default = client.patch(
            "/api/v1/settings",
            json={
                "expected_revision": current_settings["revision"],
                "default_worker_connection_ref": "qa-gemini",
            },
        )
        custom_default = client.patch(
            "/api/v1/settings",
            json={
                "expected_revision": current_settings["revision"],
                "default_worker_connection_ref": "qa-custom",
            },
        )
        RESULTS["default_gates"] = {
            "gemini": {
                "status": gemini_default.status_code,
                "code": gemini_default.json().get("error", {}).get("code"),
                "detail": gemini_default.json().get("error", {}).get("details", {}).get("detail"),
            },
            "custom": {
                "status": custom_default.status_code,
                "code": custom_default.json().get("error", {}).get("code"),
                "detail": custom_default.json().get("error", {}).get("details", {}).get("detail"),
            },
        }
        assert gemini_default.status_code == 422
        assert custom_default.status_code == 422

        # ----------------------------------------------------- delete semantics
        created = client.post(
            "/api/v1/settings/connections",
            json={
                "id": "qa-deletable",
                "title": "QA deletable",
                "backend": "openai-compat",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com/v1",
                "auth_mode": "proxy_api_key",
                "credential_ref": "qa-delete-key",
                "credential_value": "sk-delete-dummy-not-real",
            },
        )
        assert created.status_code == 201, created.text
        wrong_rev = client.request(
            "DELETE",
            "/api/v1/settings/connections/qa-deletable",
            json={"expected_revision": 9},
        )
        deleted = client.request(
            "DELETE",
            "/api/v1/settings/connections/qa-deletable",
            json={"expected_revision": 0},
        )
        missing = client.request(
            "DELETE",
            "/api/v1/settings/connections/qa-deletable",
            json={"expected_revision": 0},
        )
        secret_after_delete = (runtime.secret_dir / "qa-delete-key.secret").is_file()
        RESULTS["delete"] = {
            "wrong_revision": {
                "status": wrong_rev.status_code,
                "code": wrong_rev.json().get("error", {}).get("code"),
            },
            "deleted": {"status": deleted.status_code, "body": deleted.json()},
            "missing": {
                "status": missing.status_code,
                "code": missing.json().get("error", {}).get("code"),
            },
            "secret_file_preserved": secret_after_delete,
        }
        assert wrong_rev.status_code == 409
        assert deleted.status_code == 200 and deleted.json() == {
            "deleted": True,
            "id": "qa-deletable",
        }
        assert missing.status_code == 404
        assert secret_after_delete is True

        before_settings = client.get("/api/v1/settings").json()
        before_agent = client.get("/api/v1/resources/agents/qa-agent").json()
        blocked_delete = client.request(
            "DELETE",
            "/api/v1/settings/connections/qa-deepseek",
            json={"expected_revision": client.get("/api/v1/settings/connections/qa-deepseek").json()["revision"]},
        )
        after_settings = client.get("/api/v1/settings").json()
        after_agent = client.get("/api/v1/resources/agents/qa-agent").json()
        RESULTS["referenced_delete"] = {
            "status": blocked_delete.status_code,
            "error": blocked_delete.json().get("error"),
            "settings_unchanged": before_settings == after_settings,
            "agent_unchanged": before_agent == after_agent,
            "still_exists": client.get("/api/v1/settings/connections/qa-deepseek").status_code,
        }
        assert blocked_delete.status_code == 422
        assert blocked_delete.json()["error"]["details"]["detail"] == "connection_still_referenced"
        assert before_settings == after_settings
        assert before_agent == after_agent

        # ---------------------------------------------- validation input redaction
        bad = client.post(
            "/api/v1/settings/connections/test-draft",
            json={
                "connection": {"backend": "gemini", "model": "gemini-3.8-flash"},
                "credential_value": "sk-redact-canary-112",
                "unexpected_field": "x",
            },
        )
        RESULTS["validation_redaction"] = {
            "status": bad.status_code,
            "canary_in_response": "sk-redact-canary-112" in bad.text,
            "body": bad.text[:1000],
        }
        assert bad.status_code == 422
        assert "sk-redact-canary-112" not in bad.text

        cross = client.post(
            "/api/v1/settings/connections/test-draft",
            json={"connection": {"backend": "gemini", "model": "gemini-3.8-flash"}},
            headers={"Origin": "https://evil.example"},
        )
        RESULTS["cross_origin"] = {"status": cross.status_code, "body": cross.text[:500]}
        assert cross.status_code == 401

        # ------------------------------------------ native SDK fake protocol path
        up_before = len(runtime.upstream.records)
        gemini = client.post(
            "/api/v1/settings/connections/test-draft",
            json={
                "connection": {
                    "backend": "gemini",
                    "model": "gemini-3.8-flash",
                    "auth_mode": "api_key",
                },
                "credential_value": "sk-qa-gemini-native-dummy",
                "allow_network": True,
            },
        )
        vertex_http = client.post(
            "/api/v1/settings/connections/test-draft",
            json={
                "connection": {
                    "backend": "vertex",
                    "model": "gemini-3.8-flash",
                    "auth_mode": "adc",
                    "project": "qa-project",
                    "location": "us-central1",
                },
                "allow_network": True,
            },
        )
        new_records = runtime.upstream.records[up_before:]
        RESULTS["native_sdk_protocol"] = {
            "gemini_http": {
                "status": gemini.status_code,
                "overall": gemini.json().get("overall"),
                "network": [x for x in gemini.json().get("layers", []) if x["name"] == "runtime_network"],
            },
            "vertex_adc_http_missing_prereq": {
                "status": vertex_http.status_code,
                "overall": vertex_http.json().get("overall"),
                "credential": [x for x in vertex_http.json().get("layers", []) if x["name"] == "credential"],
                "network": [x for x in vertex_http.json().get("layers", []) if x["name"] == "runtime_network"],
            },
            "upstream": [
                {
                    "path": r.get("path"),
                    "authorization": r.get("authorization"),
                    "model": r.get("model"),
                }
                for r in new_records
            ],
            "note": "installed SDK against controlled loopback fake Gemini; not a real vendor",
        }
        assert gemini.json()["overall"] == "verified", gemini.text
        assert vertex_http.json()["overall"] != "verified", vertex_http.text
        assert "no gcloud or metadata request" in json.dumps(vertex_http.json())
        assert len(new_records) == 1
        assert "/v1beta/models/" in (new_records[0].get("path") or "")

        # Vertex ADC SDK shape: QA injects only the *static prerequisite* flag
        # and the loopback protocol seam; no metadata/gcloud/vendor call.
        from lightgravity.settings import ConnectionTester as Tester

        adc_calls: list[Any] = []

        def adc_runner(spec: Any, credential: Any, endpoint: Any, timeout: float) -> tuple[bool, str]:
            adc_calls.append((spec, credential, endpoint))
            return True, "fake ADC probe stop_confirmed=True"

        adc_tester = Tester(
            runtime.service,
            allow_network=True,
            adc_available=True,
            allow_loopback_native=True,
            native_base_url=runtime.upstream.base_url,
            native_runner=adc_runner,
        )
        adc_result = adc_tester.test_draft(
            DraftConnectionSpec(
                backend="vertex",
                model="gemini-3.8-flash",
                auth_mode="adc",
                project="qa-project",
                location="us-central1",
            ),
            allow_network=True,
        )
        RESULTS["native_sdk_protocol"]["vertex_adc_injected_seam"] = {
            "overall": adc_result.overall,
            "network": adc_result.layer("runtime_network").to_dict(),
            "native_calls": len(adc_calls),
            "credential_is_none": adc_calls[0][1] is None if adc_calls else None,
            "endpoint": adc_calls[0][2] if adc_calls else None,
            "note": "adc_available=True is a QA static-prerequisite injection only",
        }
        assert adc_result.overall == "verified"
        assert adc_calls and adc_calls[0][1] is None

        # --------------------------------------------------- LiteRT static only
        model_file = runtime.data_dir / "workspaces" / "qa-model.litertlm"
        model_file.write_text("not a real model", encoding="utf-8")
        litert = client.post(
            "/api/v1/settings/connections/test-draft",
            json={
                "connection": {
                    "backend": "litert",
                    "auth_mode": "none",
                    "model_path": str(model_file),
                    "litert_backend": "GPU",
                },
                "allow_network": True,
            },
        )
        RESULTS["litert"] = {
            "status": litert.status_code,
            "overall": litert.json().get("overall"),
            "config": [x for x in litert.json().get("layers", []) if x["name"] == "config_parse"],
            "network": [x for x in litert.json().get("layers", []) if x["name"] == "runtime_network"],
        }
        assert litert.status_code == 200
        assert litert.json()["overall"] == "not_run"
        assert "static_only=true" in json.dumps(litert.json())

        # --------------------------------------------------- cap 0 / corrupt ledger
        from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
        from lightgravity.adapter.proxy import GenerationCounter
        from lightgravity.settings import ConnectionTester as Tester

        calls: list[Any] = []

        def never_called(spec: Any, credential: Any, endpoint: Any, timeout: float) -> tuple[bool, str]:
            calls.append(spec)
            return True, "should not run"

        cap_tester = Tester(
            runtime.service,
            allow_network=True,
            native_runner=never_called,
            generation_counter=GenerationCounter(0),
        )
        capped = cap_tester.test_draft(
            DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
            credential_value="sk-cap-dummy",
            allow_network=True,
        )
        cap_calls = len(calls)
        corrupt_dir = base / "corrupt-ledger"
        corrupt_history = corrupt_dir / "generation" / "generation.jsonl"
        corrupt_history.parent.mkdir(parents=True)
        corrupt_history.write_text("{not-json}\n", encoding="utf-8")
        corrupt_counter = GenerationCounter(
            None, ledger=PersistentGenerationLedger(corrupt_dir, limit=None)
        )
        corrupt_tester = Tester(
            runtime.service,
            allow_network=True,
            native_runner=never_called,
            generation_counter=corrupt_counter,
        )
        corrupt = corrupt_tester.test_draft(
            DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
            credential_value="sk-corrupt-dummy",
            allow_network=True,
        )
        corrupt_calls = len(calls) - cap_calls
        RESULTS["budgets"] = {
            "cap0": {
                "network": capped.layer("runtime_network").to_dict(),
                "native_calls": cap_calls,
            },
            "corrupt": {
                "network": corrupt.layer("runtime_network").to_dict(),
                "native_calls": corrupt_calls,
            },
        }
        assert capped.layer("runtime_network").status == "skipped"
        assert "budget exhausted" in capped.layer("runtime_network").detail
        assert corrupt.layer("runtime_network").status == "skipped"
        assert "corrupt" in corrupt.layer("runtime_network").detail
        assert calls == []

        RESULTS["request_log_tail"] = [
            json.loads(line)
            for line in runtime.request_log.read_text("utf-8").splitlines()[-20:]
        ]
        RESULTS["upstream_log_lines"] = len(
            runtime.upstream_log.read_text("utf-8").splitlines()
        )
        assert RESULTS["upstream_log_lines"] > 0

        return 0
    finally:
        client.close()
        member.close()
        anon.close()
        server.should_exit = True
        thread.join(10)
        try:
            runtime.upstream.stop()
        except Exception:  # noqa: BLE001
            pass
        out = Path(__file__).resolve().parent / "logs" / "http-probe-results.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(RESULTS, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (Path(__file__).resolve().parent / "logs" / "http-probe.log").write_text(
            json.dumps(RESULTS, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        out = Path(__file__).resolve().parent / "logs" / "http-probe-results.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(RESULTS, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
