"""HTTP API package.

LG-002 provides the app factory plus the frozen ``/api/v1/health`` and
``/api/v1/version`` endpoints. All other endpoints belong to LG-012/LG-025 and
must be added by their owning tasks (docs/08 §11).
"""

from .app import create_app

__all__ = ["create_app"]
