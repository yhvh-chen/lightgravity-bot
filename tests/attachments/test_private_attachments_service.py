"""Unit semantics for the owner-scoped private attachment store (LG-119)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from lightgravity.attachments import PrivateAttachmentService, attachment_service_for


def _service(tmp_path: Path) -> PrivateAttachmentService:
    return attachment_service_for(tmp_path / "data")


def test_upload_is_idempotent_and_owner_scoped(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment_id = "att_01J9Z0000000000000000000AB"
    first, created = service.upload(
        "alice",
        attachment_id,
        filename="notes.txt",
        media_type="text/plain",
        data=b"alice private sentinel",
    )
    assert created is True
    assert first.status == "stored"
    replay, created_again = service.upload(
        "alice",
        attachment_id,
        filename="renamed-by-client.txt",
        media_type="text/plain",
        data=b"alice private sentinel",
    )
    assert created_again is False
    # Server canonical metadata wins; client-supplied name changes nothing.
    assert replay.filename == "notes.txt"
    assert replay.sha256 == first.sha256

    # Same id for a different owner is a separate record (owner digest dir).
    bob, bob_created = service.upload(
        "bob",
        attachment_id,
        filename="bob.txt",
        media_type="text/plain",
        data=b"bob sentinel",
    )
    assert bob_created is True
    assert bob.sha256 != first.sha256
    assert service.get("alice", attachment_id).sha256 == first.sha256

    with pytest.raises(Exception) as excinfo:
        service.upload(
            "alice",
            attachment_id,
            filename="notes.txt",
            media_type="text/plain",
            data=b"different bytes",
        )
    assert getattr(excinfo.value, "code").value == "revision_conflict"


def test_zero_byte_and_size_bound(tmp_path: Path) -> None:
    service = _service(tmp_path)
    empty, created = service.upload(
        "alice",
        "att_01J9Z0000000000000000000AC",
        filename="empty.txt",
        media_type="text/plain",
        data=b"",
    )
    assert created is True
    assert empty.size == 0
    context = service.resolve_text_for_model(
        "alice", [empty.attachment_id], message_id="msg_empty"
    )
    assert context.statuses[empty.attachment_id] == "included"
    assert "empty.txt" in context.text
    assert context.context_chars[empty.attachment_id] == 0

    with pytest.raises(Exception) as excinfo:
        service.upload(
            "alice",
            "att_01J9Z0000000000000000000AD",
            filename="too-big.txt",
            media_type="text/plain",
            data=b"x" * (service.max_upload_bytes() + 1),
        )
    assert getattr(excinfo.value, "code").value == "invalid_request"


def test_attachment_directory_permissions_and_no_raw_owner(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment, _created = service.upload(
        "alice",
        "att_01J9Z0000000000000000000AE",
        filename="a.txt",
        media_type="text/plain",
        data=b"x",
    )
    root = tmp_path / "data" / "private-attachments"
    owner_dirs = [path for path in root.iterdir() if path.is_dir()]
    assert len(owner_dirs) == 1
    assert "alice" not in owner_dirs[0].name
    assert os.stat(owner_dirs[0]).st_mode & 0o777 == 0o700
    attachment_dir = owner_dirs[0] / attachment.attachment_id
    assert os.stat(attachment_dir).st_mode & 0o777 == 0o700
    assert os.stat(attachment_dir / "content.bin").st_mode & 0o777 == 0o600
    metadata = json.loads((attachment_dir / "ATTACHMENT.json").read_text())
    assert "owner" not in metadata
    assert "path" not in json.dumps(metadata)


def test_concurrent_upload_is_idempotent_or_conflicts_atomically(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment_id = "att_01J9Z0000000000000000000AJ"

    def upload(data: bytes) -> bool:
        _attachment, created = service.upload(
            "alice",
            attachment_id,
            filename="race.txt",
            media_type="text/plain",
            data=data,
        )
        return created

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(upload, [b"same", b"same"]))
    assert sorted(same) == [False, True]

    other_id = "att_01J9Z0000000000000000000AK"
    def upload_other(data: bytes) -> str:
        try:
            service.upload(
                "alice",
                other_id,
                filename="race.txt",
                media_type="text/plain",
                data=data,
            )
            return "ok"
        except Exception as exc:  # noqa: BLE001 - assert the real contract code
            return getattr(exc, "code").value

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(upload_other, [b"one", b"two"]))
    assert sorted(outcomes) == ["ok", "revision_conflict"]
    # Exactly one canonical record survives; no temp files are left behind.
    assert service.get("alice", other_id).size == 3
    owner_dir = next((tmp_path / "data" / "private-attachments").iterdir())
    attachment_dir = owner_dir / other_id
    assert sorted(path.name for path in attachment_dir.iterdir()) == [
        "ATTACHMENT.json",
        "content.bin",
    ]


def test_planted_symlink_never_escapes_the_private_root(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment, _ = service.upload(
        "alice",
        "att_01J9Z0000000000000000000AF",
        filename="safe.txt",
        media_type="text/plain",
        data=b"safe",
    )
    root = tmp_path / "data" / "private-attachments"
    owner_dir = next(path for path in root.iterdir() if path.is_dir())
    attachment_dir = owner_dir / attachment.attachment_id
    outside = tmp_path / "outside-sentinel.txt"
    outside.write_text("outside secret")
    content = attachment_dir / "content.bin"
    content.unlink()
    content.symlink_to(outside)
    with pytest.raises(Exception) as excinfo:
        service.content("alice", attachment.attachment_id)
    assert getattr(excinfo.value, "code").value == "invalid_request"
    assert "outside secret" not in str(excinfo.value)


def test_claim_release_and_attached_delete_transition(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment, _ = service.upload(
        "alice",
        "att_01J9Z0000000000000000000AG",
        filename="claim.txt",
        media_type="text/plain",
        data=b"claim",
    )
    claimed = service.claim_for_message("alice", [attachment.attachment_id], "msg_1")
    assert claimed[0].status == "attached"
    assert claimed[0].message_id == "msg_1"
    # Idempotent replay for the same message is allowed; another message is not.
    again = service.claim_for_message("alice", [attachment.attachment_id], "msg_1")
    assert again[0].status == "attached"
    with pytest.raises(Exception) as excinfo:
        service.claim_for_message("alice", [attachment.attachment_id], "msg_2")
    assert getattr(excinfo.value, "code").value == "not_found"
    with pytest.raises(Exception) as excinfo:
        service.delete("alice", attachment.attachment_id)
    assert getattr(excinfo.value, "code").value == "illegal_transition"

    service.release_claims("alice", [attachment.attachment_id], "msg_1")
    assert service.get("alice", attachment.attachment_id).status == "stored"
    service.delete("alice", attachment.attachment_id)
    with pytest.raises(Exception) as excinfo:
        service.get("alice", attachment.attachment_id)
    assert getattr(excinfo.value, "code").value == "not_found"
