"""App factory wiring: lifespan lifecycle and the dispatcher/executor seams."""

from __future__ import annotations

import httpx

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings

from api_helpers import FakeExecutor


async def test_lifespan_starts_and_stops_coordinator(settings: Settings) -> None:
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    coordinator = app.state.coordinator
    assert getattr(coordinator, "_loop_task", None) is None
    async with app.router.lifespan_context(app):
        assert getattr(coordinator, "_loop_task", None) is not None
        # The API Store is the broadcasting proxy over the same authority.
        assert app.state.context.store is app.state.store
    assert getattr(coordinator, "_loop_task", None) is None


async def test_executor_injection_seam(settings: Settings) -> None:
    executor = FakeExecutor()
    app = create_app(
        settings,
        executor=executor,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    assert app.state.context.real_executor is True
    assert app.state.coordinator.dispatcher.executor is executor
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get("/api/v1/health")
    assert health.json()["capabilities"]["sdk_adapter"] is True
