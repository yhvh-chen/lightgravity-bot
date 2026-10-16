#!/usr/bin/env python3
"""LG-047 E-QA — thin real-HTTP API client for the isolated QA app.

Everything here talks to the **real** product over loopback HTTP (never an
in-process ASGI transport, never a mock). The runtime token is read from the
page the product serves. No credential ever appears here.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

TOKEN_RE = re.compile(r'window\.__LG_RUNTIME_TOKEN__="([^"]+)"')


class Api:
    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token or self._fetch_token()

    def _fetch_token(self) -> str:
        req = urllib.request.Request(self.base + "/", method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
        m = TOKEN_RE.search(html)
        if not m:
            raise RuntimeError("runtime token not found in served page")
        return m.group(1)

    def _raw(self, method: str, path: str, body: bytes | None = None, extra: dict | None = None):
        req = urllib.request.Request(self.base + path, data=body, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("X-LG-Token", self.token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.read().decode("utf-8", "replace")

    def request(self, method: str, path: str, json_body=None) -> tuple[int, dict | list | str]:
        data = json.dumps(json_body).encode() if json_body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("X-LG-Token", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, _maybe_json(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            return exc.code, _maybe_json(raw)

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body):
        return self.request("POST", path, body)

    # ----------------------------------------------------------- convenience
    def health(self):
        return self.request("GET", "/api/v1/health")

    def generation(self):
        # Evidence-only route returning the product's persistent ledger snapshot.
        return self.request("GET", "/_lg047_generation")

    def create_task(self, *, request_id: str, title: str, objective: str) -> dict:
        status, body = self.post(
            "/api/v1/tasks",
            {
                "request_id": request_id,
                "title": title,
                "objective": objective,
                "acceptance_criteria": ["deliver the requested artifact"],
            },
        )
        return {"status": status, "body": body}

    def upload_inline(self, *, request_id: str, filename: str, text: str,
                      task_ref: str | None = None, media_type: str = "text/plain",
                      title: str | None = None) -> dict:
        payload = {
            "request_id": request_id,
            "filename": filename,
            "content_base64": base64.b64encode(text.encode("utf-8")).decode(),
            "media_type": media_type,
            "title": title or filename,
            "scope": {
                "task_ref": task_ref,
                "project_ref": None,
                "inbox_ref": None,
            },
        }
        status, body = self.post("/api/v1/sources", payload)
        return {"status": status, "body": body}

    def receipt(self, source_id: str):
        return self.request("GET", f"/api/v1/sources/{source_id}/receipt")

    def source_content(self, source_id: str, kind: str = "auto"):
        return self.request("GET", f"/api/v1/sources/{source_id}/content?kind={kind}")

    def source_action(self, source_id: str, action: str):
        return self.post(f"/api/v1/sources/{source_id}/actions", {"action": action})

    def task_message(self, task_id: str, *, message_id: str, content: str,
                     selected_sources=None) -> dict:
        body = {"message_id": message_id, "role": "user", "content": content}
        if selected_sources is not None:
            body["selected_sources"] = selected_sources
        status, resp = self.post(f"/api/v1/tasks/{task_id}/messages", body)
        return {"status": status, "body": resp}

    def global_message(self, *, message_id: str, content: str, selected_sources=None,
                       request_id: str | None = None) -> dict:
        body = {"message_id": message_id, "role": "user", "content": content}
        if selected_sources is not None:
            body["selected_sources"] = selected_sources
        if request_id:
            body["request_id"] = request_id
        status, resp = self.post("/api/v1/conversations/global/messages", body)
        return {"status": status, "body": resp}

    def task(self, task_id: str):
        return self.request("GET", f"/api/v1/tasks/{task_id}")

    def task_messages(self, task_id: str):
        return self.request("GET", f"/api/v1/tasks/{task_id}/messages")

    def global_messages(self):
        return self.request("GET", "/api/v1/conversations/global/messages")

    def artifacts(self, task_id: str):
        return self.request("GET", f"/api/v1/tasks/{task_id}/artifacts")

    def task_action(self, task_id: str, *, action: str, request_id: str, **extra):
        body = {"action": action, "request_id": request_id, **extra}
        return self.post(f"/api/v1/tasks/{task_id}/actions", body)


def _maybe_json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw
