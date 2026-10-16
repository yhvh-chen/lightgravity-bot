"""Single-service static frontend serving for local distribution (LG-020).

The first version avoids a second Vite origin in normal use: the same process
serves ``frontend/dist`` and the frozen ``/api/v1`` routes.  This module:

* serves real build files (JS/CSS/assets) under the dist root, rejecting path
  escape and symlinks that resolve outside the root;
* falls back to ``index.html`` for SPA deep links so the client router works;
* injects the runtime token into the served HTML at request time (never into
  the file on disk) and marks HTML ``no-store`` so the token is not cached;
* when the build is missing, serves a minimal honest bootstrap page that still
  performs the in-memory token handshake instead of pretending the UI exists.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from .token import inject_runtime_token

#: Stable name of the SPDX-less minimal page; not a product UI.
_MINIMAL_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LightGravity Bot — backend running</title>
  </head>
  <body>
    <main>
      <h1>LightGravity Bot backend is running</h1>
      <p>
        The frontend build was not found at <code>__DIST__</code>. The API is
        available under <code>/api/v1</code>; build the frontend with
        <code>make frontend-build</code> and restart, or pass
        <code>--frontend-dist</code>.
      </p>
      <p id="lg-status">Checking backend health…</p>
    </main>
    <script>
      fetch('/api/v1/health')
        .then((response) => response.json())
        .then((data) => {
          document.getElementById('lg-status').textContent =
            'backend health: ' + (data.status || 'unknown');
        })
        .catch(() => {
          document.getElementById('lg-status').textContent =
            'backend health could not be read';
        });
    </script>
  </body>
</html>
"""


def _safe_file(root: Path, relative: str) -> Path | None:
    if not relative:
        return None
    candidate = (root / relative).resolve()
    if candidate == root or root in candidate.parents:
        if candidate.is_file():
            return candidate
    return None


def mount_frontend(
    app: FastAPI,
    dist_dir: Path | str,
    token: str,
    *,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Register the SPA route; return ``True`` when a real build was found."""

    root = Path(dist_dir).resolve()
    index_path = root / "index.html"
    has_build = index_path.is_file()
    if log is not None:
        log(f"frontend build {'found' if has_build else 'not found'} at {root}")

    def _index_response() -> HTMLResponse:
        if has_build:
            try:
                html = index_path.read_text("utf-8")
            except OSError:
                html = _MINIMAL_PAGE.replace("__DIST__", str(root))
        else:
            html = _MINIMAL_PAGE.replace("__DIST__", str(root))
        body = inject_runtime_token(html, token)
        return HTMLResponse(
            body,
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:  # pragma: no cover - thin wrapper
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        static_file = _safe_file(root, path)
        if static_file is not None:
            return FileResponse(static_file)
        return _index_response()

    return has_build


__all__ = ["mount_frontend"]
