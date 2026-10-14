"""Run the API directly: ``uv run python -m lightgravity.api``."""

from __future__ import annotations

import uvicorn

from .app import create_app


def main() -> None:
    app = create_app()
    settings = app.state.settings
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
