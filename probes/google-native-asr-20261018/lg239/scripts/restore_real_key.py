#!/usr/bin/env python3
"""Restore the real Google key through the protected product API.

Invoked between the admin-UI fake-key save and the single real audio upload.
It is intentionally outside the Playwright network trace.  Only the resulting
revision is printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def call(base, method, path, cookie=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload, dict(exc.headers)


def main() -> int:
    base = sys.argv[1]
    key = os.environ.get("LG_GOOGLE_ASR_API_KEY", "")
    if not key:
        print("missing LG_GOOGLE_ASR_API_KEY", file=sys.stderr)
        return 2
    status, _, headers = call(
        base, "POST", "/api/v1/auth/login", body={"username": "admin", "password": "admin123"}
    )
    if status != 200:
        print(f"admin login failed: {status}", file=sys.stderr)
        return 1
    cookie = (headers.get("Set-Cookie") or headers.get("set-cookie")).split(";", 1)[0]
    status, settings, _ = call(base, "GET", "/api/v1/settings", cookie=cookie)
    if status != 200:
        print(f"settings read failed: {status}", file=sys.stderr)
        return 1
    view = settings["english_asr"]
    status, saved, _ = call(
        base,
        "PUT",
        "/api/v1/settings/english_asr",
        cookie=cookie,
        body={
            "expected_revision": view["revision"],
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "timeout_seconds": 180,
            "max_audio_bytes": 10_000_000,
            "credential_value": key,
        },
    )
    if status != 200 or not saved["english_asr"].get("credential_configured"):
        print(f"restore failed: {status}", file=sys.stderr)
        return 1
    print(json.dumps({"restored": True, "revision": saved["english_asr"]["revision"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
