#!/usr/bin/env python3
"""LG-047 R2 — minimal HTTP client for the real product app (no model calls)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class Api:
    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["X-LG-Token"] = self.token
        if extra:
            h.update(extra)
        return h

    def request(
        self, method: str, path: str, body: Any = None, *, token: str | None = None
    ) -> dict:
        url = self.base + path
        data = None
        headers = self._headers()
        if token is not None:
            headers["X-LG-Token"] = token
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw.decode("utf-8", "replace")
        return {"status": status, "body": parsed}

    def get(self, path: str) -> dict:
        return self.request("GET", path)

    def post(self, path: str, body: Any = None) -> dict:
        return self.request("POST", path, body)
