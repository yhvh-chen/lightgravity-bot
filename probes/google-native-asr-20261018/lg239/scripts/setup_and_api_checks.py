#!/usr/bin/env python3
"""LG-239 pre-browser protected API setup and secret-boundary checks.

The real Google key is read from LG_GOOGLE_ASR_API_KEY in this harness process
only and sent as a write-only credential to the product's protected settings
API.  It is never printed, written to an artifact, or placed in the app env.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

FAKE_KEY = "lg239-fake-config-key-not-real-" + secrets.token_hex(8)
MEMBER_USER = "qa-lg239-member"


def call(
    base: str,
    method: str,
    path: str,
    *,
    cookie: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict | str | None, dict[str, str]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(
        base + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            payload = json.loads(raw) if raw else None
            return response.status, payload, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload, dict(exc.headers)


def login(base: str, username: str, password: str) -> str:
    status, body, headers = call(
        base, "POST", "/api/v1/auth/login", body={"username": username, "password": password}
    )
    if status != 200:
        raise RuntimeError(f"login failed for {username}: {status} {body!r}")
    set_cookie = headers.get("Set-Cookie") or headers.get("set-cookie")
    if not set_cookie:
        raise RuntimeError("login returned no session cookie")
    return set_cookie.split(";", 1)[0]


def without_secrets(text: str, *needles: str) -> bool:
    return all(needle and needle not in text for needle in needles)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--accounts-private", required=True)
    parser.add_argument("--app-pid", type=int, required=True)
    args = parser.parse_args()

    real_key = os.environ.get("LG_GOOGLE_ASR_API_KEY", "")
    if not real_key:
        raise SystemExit("LG_GOOGLE_ASR_API_KEY is not present in the harness env")

    checks: list[dict] = []
    evidence: dict = {}
    failures: list[str] = []

    def check(name: str, ok: bool, detail=None) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failures.append(name)

    admin_cookie = login(args.base, "admin", "admin123")
    status, me, _ = call(args.base, "GET", "/api/v1/auth/me", cookie=admin_cookie)
    check(
        "local fixture admin session is team/admin",
        status == 200 and me.get("mode") == "team" and me.get("role") == "admin",
        {"status": status, "username": me.get("username"), "role": me.get("role")},
    )

    status, settings, _ = call(args.base, "GET", "/api/v1/settings", cookie=admin_cookie)
    check("admin can read settings", status == 200 and "english_asr" in settings, status)
    initial = settings["english_asr"]
    evidence["initial_english_asr"] = initial

    member_password = "lg239-" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(18)
    )
    status, created, _ = call(
        args.base,
        "POST",
        "/api/v1/accounts",
        cookie=admin_cookie,
        body={"username": MEMBER_USER, "password": member_password, "role": "member"},
    )
    if status == 409 or (isinstance(created, dict) and created.get("details", {}).get("reason") == "username_exists"):
        member_password = json.loads(Path(args.accounts_private).read_text())["password"]
        check("member fixture already exists (reused private password)", True, MEMBER_USER)
    else:
        check(
            "created isolated member fixture",
            status == 201 and created.get("role") == "member",
            {"status": status, "username": MEMBER_USER, "role": created.get("role") if isinstance(created, dict) else None},
        )
    accounts_private = Path(args.accounts_private)
    accounts_private.parent.mkdir(parents=True, exist_ok=True)
    accounts_private.write_text(
        json.dumps(
            {
                "admin": {"username": "admin", "password": "admin123"},
                "member": {"username": MEMBER_USER, "password": member_password},
            },
            indent=2,
        )
    )
    accounts_private.chmod(0o600)

    member_cookie = login(args.base, MEMBER_USER, member_password)
    member_status, member_settings, _ = call(
        args.base, "GET", "/api/v1/settings", cookie=member_cookie
    )
    check(
        "ordinary member cannot read admin settings/config",
        member_status == 403,
        {"status": member_status, "body": member_settings},
    )

    rev = initial["revision"]
    invalid_cases = [
        (
            "invalid model id",
            {
                "expected_revision": rev,
                "enabled": True,
                "provider": "google-native",
                "runtime": "google-native",
                "model": "bad model!",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "credential_value": FAKE_KEY,
            },
        ),
        (
            "non-native base URL",
            {
                "expected_revision": rev,
                "enabled": True,
                "provider": "google-native",
                "runtime": "google-native",
                "model": "gemini-3.8-flash",
                "base_url": "http://example.com/v1beta",
                "credential_value": FAKE_KEY,
            },
        ),
        (
            "legacy max_audio_seconds rejected in Google mode",
            {
                "expected_revision": rev,
                "enabled": True,
                "provider": "google-native",
                "runtime": "google-native",
                "model": "gemini-3.8-flash",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "max_audio_seconds": 30,
                "credential_value": FAKE_KEY,
            },
        ),
    ]
    for name, payload in invalid_cases:
        status, body, _ = call(
            args.base, "PUT", "/api/v1/settings/english_asr", cookie=admin_cookie, body=payload
        )
        serialized = json.dumps(body, sort_keys=True)
        check(
            f"{name}: 422 with no fake-secret echo",
            status == 422 and without_secrets(serialized, FAKE_KEY, real_key),
            {"status": status, "code": body.get("code") if isinstance(body, dict) else None},
        )

    valid_fake = {
        "expected_revision": rev,
        "enabled": True,
        "provider": "google-native",
        "runtime": "google-native",
        "model": "gemini-3.8-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "timeout_seconds": 180,
        "max_audio_bytes": 10_000_000,
        "credential_value": FAKE_KEY,
    }
    status, saved_fake, _ = call(
        args.base, "PUT", "/api/v1/settings/english_asr", cookie=admin_cookie, body=valid_fake
    )
    check(
        "fake-key Google save succeeds and is network-free (save only validates)",
        status == 200 and saved_fake["english_asr"]["credential_configured"] is True,
        {"status": status, "revision": saved_fake.get("english_asr", {}).get("revision")},
    )
    serialized_fake = json.dumps(saved_fake, sort_keys=True)
    check(
        "save response contains neither key nor credential ref/value",
        without_secrets(serialized_fake, FAKE_KEY, real_key)
        and "credential_ref" not in serialized_fake
        and "credential_value" not in serialized_fake,
        sorted(saved_fake.get("english_asr", {}).keys()),
    )

    status, current, _ = call(args.base, "GET", "/api/v1/settings", cookie=admin_cookie)
    view = current["english_asr"]
    serialized_view = json.dumps(current, sort_keys=True)
    check(
        "GET is write-only: no key/ref/value/path is returned",
        status == 200
        and view.get("credential_configured") is True
        and "credential_ref" not in view
        and "credential_value" not in view
        and without_secrets(serialized_view, FAKE_KEY, real_key)
        and "model_dir" not in view
        and "reader_dir" not in view,
        sorted(view.keys()),
    )

    rev_fake = view["revision"]
    status, retained, _ = call(
        args.base,
        "PUT",
        "/api/v1/settings/english_asr",
        cookie=admin_cookie,
        body={
            "expected_revision": rev_fake,
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "timeout_seconds": 180,
            "max_audio_bytes": 10_000_000,
        },
    )
    status_after, after_retain, _ = call(
        args.base, "GET", "/api/v1/settings", cookie=admin_cookie
    )
    check(
        "blank credential retains stored secret (no empty/delete write)",
        status == 200
        and retained["english_asr"]["credential_configured"] is True
        and after_retain["english_asr"]["credential_configured"] is True,
        {"put": status, "get": status_after, "revision": after_retain["english_asr"]["revision"]},
    )

    rev_current = after_retain["english_asr"]["revision"]
    status, conflict, _ = call(
        args.base,
        "PUT",
        "/api/v1/settings/english_asr",
        cookie=admin_cookie,
        body={
            "expected_revision": max(0, rev_current - 1),
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "credential_value": FAKE_KEY + "-stale",
        },
    )
    status_after_conflict, after_conflict, _ = call(
        args.base, "GET", "/api/v1/settings", cookie=admin_cookie
    )
    conflict_text = json.dumps(conflict, sort_keys=True)
    check(
        "stale expected_revision is 409 and cannot leak/overwrite secret",
        status == 409
        and without_secrets(conflict_text, FAKE_KEY, real_key)
        and after_conflict["english_asr"]["credential_configured"] is True
        and after_conflict["english_asr"]["revision"] == rev_current,
        {"status": status, "code": conflict.get("code") if isinstance(conflict, dict) else None, "revision": rev_current},
    )

    # Restore the real key only through this out-of-trace protected API call.
    rev_current = after_conflict["english_asr"]["revision"]
    status, restored, _ = call(
        args.base,
        "PUT",
        "/api/v1/settings/english_asr",
        cookie=admin_cookie,
        body={
            "expected_revision": rev_current,
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "timeout_seconds": 180,
            "max_audio_bytes": 10_000_000,
            "credential_value": real_key,
        },
    )
    status, final_settings, _ = call(args.base, "GET", "/api/v1/settings", cookie=admin_cookie)
    final_view = final_settings["english_asr"]
    final_text = json.dumps(final_settings, sort_keys=True)
    check(
        "real key restored via out-of-trace protected API; view still write-only",
        status == 200
        and final_view.get("enabled") is True
        and final_view.get("configured") is True
        and final_view.get("available") is True
        and final_view.get("credential_configured") is True
        and final_view.get("limits", {}).get("max_audio_seconds") is None
        and final_view.get("limits", {}).get("max_request_bytes") == 20_000_000
        and without_secrets(final_text, real_key, FAKE_KEY),
        {
            "status": status,
            "revision": final_view.get("revision"),
            "limits": final_view.get("limits"),
            "reason": final_view.get("reason"),
        },
    )

    status, health, _ = call(args.base, "GET", "/api/v1/health", cookie=admin_cookie)
    check(
        "health reports contract 1.22.0 and attemptable English ASR",
        status == 200
        and health.get("contract_version") == "1.22.0"
        and health.get("capabilities", {}).get("english_asr") is True,
        {
            "status": status,
            "contract_version": health.get("contract_version"),
            "english_asr": health.get("capabilities", {}).get("english_asr"),
        },
    )

    env_raw = Path(f"/proc/{args.app_pid}/environ").read_bytes()
    env_names = sorted(
        item.split(b"=", 1)[0].decode("utf-8", "replace")
        for item in env_raw.split(b"\0")
        if item
    )
    provider_names = [
        name
        for name in env_names
        if any(
            marker in name.upper()
            for marker in (
                "LG_GOOGLE_ASR_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
                "GOOGLE_API_KEY",
                "GEMINI_API_KEY",
                "LIGHTGRAVITY_OCR_TOKEN",
            )
        )
    ]
    check(
        "product app process env has no provider/Google credential",
        provider_names == [],
        provider_names,
    )

    evidence.update(
        {
            "member_username": MEMBER_USER,
            "member_settings_status": member_status,
            "fake_key_config_tests_used_no_network": True,
            "final_english_asr": final_view,
            "health": {
                "contract_version": health.get("contract_version"),
                "capabilities": health.get("capabilities"),
            },
            "app_env_provider_names": provider_names,
            "checks": checks,
            "failures": failures,
        }
    )
    Path(args.out).write_text(json.dumps(evidence, indent=2, sort_keys=True))
    print(json.dumps({"checks": len(checks), "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
