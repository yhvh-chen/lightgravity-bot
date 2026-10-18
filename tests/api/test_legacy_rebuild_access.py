"""Real ASGI HTTP authorization with file caches and an in-process fake model."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import httpx
import pytest

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.sources import build_source_service
from lightgravity.sources.content import ContentStore
from lightgravity.sources.lexical import LexicalSearchService
from lightgravity.sources.vectors import EmbedResult, VectorSearchService
from lightgravity.team import TeamAccounts


class FakeEmbedding:
    configured = True
    model_id = "lg148-in-process-fake"

    def __init__(self):
        self.calls = []

    def embed(self, item):
        self.calls.append(item.text)
        return EmbedResult(vector=(1.0, 0.0), model=self.model_id, dim=2,
                           input_kind="text", input_sha256=hashlib.sha256(item.text.encode()).hexdigest(),
                           input_bytes=len(item.text), latency_seconds=0,
                           prompt_tokens=None, raw_response="{}")


@pytest.mark.parametrize("team_mode", [False, True], ids=["local-no-token", "team-member"])
@pytest.mark.parametrize("kind", ["keyword", "vector"])
async def test_legacy_full_rebuild_requires_protected_admin_access(settings, team_mode, kind):
    settings = dataclasses.replace(settings, team_mode=team_mode)
    if team_mode:
        accounts = TeamAccounts(settings.team_accounts_path)
        accounts.add("admin", "fixture-admin-password", "admin")
        accounts.add("member", "fixture-member-password", "member")
    app = create_app(settings, access_policy=None if team_mode else LocalAccessPolicy(token="fixture-token"),
                     enable_intake_worker=False)
    async with app.router.lifespan_context(app):
        source_service = build_source_service(data_dir=settings.data_dir)
        for number in range(2):
            received = source_service.receive_inline(
                request_id=f"lg148-{number}", filename=f"doc-{number}.txt",
                content_base64=base64.b64encode(f"alpha corpus {number}".encode()).decode(),
                media_type="text/plain", intake_mode="deferred")
            ContentStore(source_root=source_service.store.source_dir(received.source.source_id)).write_formal(
                f"alpha corpus {number}", edited_by="fixture", expected_revision=None)
        fake = FakeEmbedding()
        lexical = LexicalSearchService(source_service.store)
        vector = VectorSearchService(source_service.store, backend=fake)
        app.state.source_service = source_service
        app.state.lexical_search_service = lexical
        app.state.vector_search_service = vector
        service = vector if kind == "vector" else lexical
        endpoint = "/api/v1/vector/search" if kind == "vector" else "/api/v1/search"
        snapshot = {source.source_id: source.content_hash for source in source_service.store.list_sources()}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            if team_mode:
                assert (await client.post("/api/v1/auth/login", json={
                    "username": "member", "password": "fixture-member-password"})).status_code == 200
                identity = (await client.get("/api/v1/auth/me")).json()
                assert identity["role"] == "member"
            else:
                identity = {"mode": "single-user", "token_supplied": False}
            # Default and explicit false remain read-only, with a missing cache.
            for params in ({"q": "alpha"}, {"q": "alpha", "rebuild_if_missing": "false"}):
                response = await client.get(endpoint, params=params)
                assert response.status_code == 200
                assert not service.index.exists()
                assert fake.calls == []
            # Repeated parameters use the same last-value rule as FastAPI.
            repeated_false = await client.get(endpoint, params=[("q", "alpha"),
                ("rebuild_if_missing", "true"), ("rebuild_if_missing", "false")])
            assert repeated_false.status_code == 200
            assert not service.index.exists()
            assert fake.calls == []
            denied = await client.post("/api/v1/vector/rebuild")
            assert denied.status_code == (403 if team_mode else 401)
            for flag in ("true", "TRUE", "1", "on", "yes", "t", "y"):
                legacy = await client.get(endpoint, params={"q": "alpha", "rebuild_if_missing": flag})
                print(json.dumps({"kind": kind, "identity": identity, "flag": flag,
                                  "post_status": denied.status_code, "legacy_status": legacy.status_code,
                                  "cache_created": service.index.exists(), "embedding_calls": list(fake.calls),
                                  "legacy_body": legacy.json()}))
                assert legacy.status_code == denied.status_code
                assert not service.index.exists()
                assert fake.calls == []
            repeated_true = await client.get(endpoint, params=[("q", "alpha"),
                ("rebuild_if_missing", "false"), ("rebuild_if_missing", "true")])
            assert repeated_true.status_code == denied.status_code
            assert not service.index.exists()
            assert fake.calls == []
            assert snapshot == {source.source_id: source.content_hash for source in source_service.store.list_sources()}
            # Same explicit legacy opt-in remains available to authorized old clients.
            headers = {"X-LG-Token": "fixture-token"}
            if team_mode:
                await client.post("/api/v1/auth/logout")
                assert (await client.post("/api/v1/auth/login", json={
                    "username": "admin", "password": "fixture-admin-password"})).status_code == 200
                assert (await client.get("/api/v1/auth/me")).json()["role"] == "admin"
            allowed = await client.get(endpoint, params={"q": "alpha", "rebuild_if_missing": "true"}, headers=headers)
            assert allowed.status_code == 200, allowed.text
            assert service.index.exists()
            assert len(allowed.json()["hits"]) == 2
            assert len(fake.calls) == (3 if kind == "vector" else 0)  # 2 corpus inputs + query
            print(json.dumps({"kind": kind, "authorized_as": "admin" if team_mode else "local-token",
                              "legacy_status": allowed.status_code, "cache_created": service.index.exists(),
                              "hits": len(allowed.json()["hits"]), "embedding_calls": list(fake.calls)}))
            # Once a cache exists, ordinary members/no-token reads still work.
            if team_mode:
                await client.post("/api/v1/auth/logout")
                await client.post("/api/v1/auth/login", json={"username": "member", "password": "fixture-member-password"})
            calls_before_read = len(fake.calls)
            assert (await client.get(endpoint, params={"q": "alpha"})).status_code == 200
            assert len(fake.calls) == calls_before_read + (1 if kind == "vector" else 0)
            # A cached index does not exempt an explicit protected request.
            calls_before_denial = len(fake.calls)
            source_snapshot = {source.source_id: source.content_hash for source in source_service.store.list_sources()}
            cache_path = service.index.path if kind == "vector" else service.index.db_path
            cache_before_denial = cache_path.read_bytes()
            denied_cached = await client.get(endpoint, params={"q": "alpha", "rebuild_if_missing": "true"},
                headers={"X-LG-Token": "fixture-token" if team_mode else "wrong-token"})
            assert denied_cached.status_code == denied.status_code
            assert len(fake.calls) == calls_before_denial
            assert cache_path.read_bytes() == cache_before_denial
            assert source_snapshot == {source.source_id: source.content_hash for source in source_service.store.list_sources()}
