"""LG-025 real DeepSeek evidence run (bounded, opt-in, never prints the key).

Run explicitly in an environment that already injected ``DEEPSEEK_API_KEY``:

    uv run python tests/settings/evidence/lg025_real_run.py

It exercises the real LG-006 product auth proxy through
:class:`ConnectionTester`, using the first-version model ``deepseek-v4-flash``.
The hard cap is ``REAL_CALL_CAP`` model calls; this script makes exactly one
(model response) and no tool/structured probes.  The key is read from the
environment, written to a tmp permission-restricted store, and never logged or
placed in the evidence JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from lightgravity.adapter.credentials import CredentialResolver
from lightgravity.settings import (
    ConnectionService,
    ConnectionTestLog,
    ConnectionTester,
    FileSecretStore,
)
from lightgravity.store import FileStore

#: Hard upper bound for this script's real model calls.
REAL_CALL_CAP = 3

EVIDENCE_PATH = Path(__file__).with_name("lg025-real-evidence.json")


def _redact(value: object, secret: str) -> object:
    if isinstance(value, str) and secret and secret in value:
        return value.replace(secret, "<redacted>")
    return value


def main() -> int:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key.strip():
        print(json.dumps({"status": "blocked", "reason": "DEEPSEEK_API_KEY absent"}))
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg025-evidence-"))
    data_dir = root / "data"
    secret_dir = root / "secrets"
    store = FileStore(data_dir, data_dir / "workspaces")
    secret_store = FileSecretStore(secret_dir)
    service = ConnectionService(store, secret_store=secret_store)

    credential_version = service.set_credential("deepseek-default", key)
    connection = service.create_connection(
        "deepseek",
        title="DeepSeek",
        credential_ref="deepseek-default",
        actor="lg025-evidence",
        request_id="lg025-evidence-create",
    )

    resolver_protocol_ok = isinstance(service.credential_resolver, CredentialResolver)

    diagnostics = ConnectionTestLog(data_dir / "settings" / "diagnostics")
    tester = ConnectionTester(
        service,
        diagnostics=diagnostics,
        allow_network=True,
        max_network_calls=REAL_CALL_CAP,
        http_timeout=60.0,
        upstream_timeout=60.0,
    )
    result = tester.test(
        "deepseek",
        expected_revision=connection["revision"],
        allow_network=True,
    )

    # A connection edit must make the old test stale, without a hot swap.
    edited = service.update_connection(
        "deepseek",
        expected_revision=connection["revision"],
        actor="lg025-evidence",
        title="DeepSeek (edited)",
    )
    stale_on_connection = result.is_stale(
        edited["revision"], service.credential_status("deepseek-default").version
    )
    # A credential rotation must also make the old test stale (no network call).
    rotated_version = service.set_credential("deepseek-default", key)
    stale_on_credential = result.is_stale(edited["revision"], rotated_version)

    network_layer = result.layer("runtime_network")
    evidence = {
        "status": "ok" if result.overall == "verified" else result.overall,
        "model": result.model,
        "backend": result.backend,
        "base_url_host": result.base_url_host,
        "connection_revision_at_test": result.connection_revision,
        "credential_version_at_test": result.credential_version,
        "overall": result.overall,
        "layers": [layer.to_dict() for layer in result.layers],
        "network": {
            "status": network_layer.status if network_layer else None,
            "detail": network_layer.detail if network_layer else None,
        },
        "real_model_calls": tester.network_calls,
        "real_call_cap": REAL_CALL_CAP,
        "stale_after_connection_edit": stale_on_connection,
        "stale_after_credential_update": stale_on_credential,
        "resolver_satisfies_protocol": resolver_protocol_ok,
        "secret_store_permission_issues": secret_store.check_permissions(),
        "secret_store_outside_repo": not str(secret_dir).startswith(
            str(Path(__file__).resolve().parents[3])
        ),
        "credential_version_rotated": credential_version != rotated_version,
        "diagnostics_latest_test_id": (diagnostics.latest("deepseek") or {}).get("test_id"),
    }

    serialized = json.dumps(evidence, indent=2, sort_keys=True)
    if key in serialized:
        raise SystemExit("refusing to write evidence containing the secret")
    assert key not in json.dumps(result.to_dict())

    EVIDENCE_PATH.write_text(serialized + "\n", "utf-8")
    print(_redact(serialized, key))

    ok = (
        result.overall == "verified"
        and tester.network_calls <= REAL_CALL_CAP
        and stale_on_connection
        and stale_on_credential
        and resolver_protocol_ok
        and not secret_store.check_permissions()
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
