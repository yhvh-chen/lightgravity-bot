"""In-process session lifecycle: TTL expiry and revocation (LG-050)."""

from __future__ import annotations

from lightgravity.team.sessions import SessionRegistry


def test_session_expires_after_ttl() -> None:
    now = {"value": 1000.0}
    registry = SessionRegistry(60, clock=lambda: now["value"])
    session = registry.create("alice", "member")
    assert registry.resolve(session.session_id) is not None
    now["value"] += 61
    assert registry.resolve(session.session_id) is None


def test_session_revocation_is_immediate() -> None:
    registry = SessionRegistry(60)
    session = registry.create("alice", "member")
    assert registry.revoke(session.session_id) is True
    assert registry.resolve(session.session_id) is None
    assert registry.revoke(session.session_id) is False
