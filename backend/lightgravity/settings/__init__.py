"""LG-025 settings backend: connections, defaults, credentials and tests.

Public surface (docs/07, docs/08 §4.3/§6.5/§8.1):

* :class:`FileSecretStore` / :class:`SecretStoreCredentialResolver` - the
  controlled, owner-only secret store that plugs into the LG-006 executor.
* :class:`ConnectionService` - Store-backed connection + SETTINGS.md policy,
  credential lifecycle, reference blocking and revision pinning.
* :class:`ConnectionTester` / :class:`ConnectionTestLog` - layered tests whose
  results are bound to connection revision + credential version.
* :func:`build_settings_router` - the settings HTTP router factory, mounted by
  LG-012 (this package does not edit ``lightgravity.api``).
* Private value types in :mod:`lightgravity.settings.models`; no frozen
  ``lightgravity.contracts`` field is redefined here.

Everything is Store-authoritative: Connections and ``settings/SETTINGS.md`` are
the same facts the adapter compiler reads; no second provider/model database is
created.  Secret values never enter Markdown, responses, events or logs.
"""

from .errors import (
    ConnectionReferenceInvalid,
    CredentialUnavailable,
    SecretStoreError,
    SettingsConfigInvalid,
    SettingsError,
)
from .models import (
    DEFAULT_BASE_URL,
    DEFAULT_EXECUTABLE_BACKEND,
    DEFAULT_ROLES,
    PREFERRED_MODEL,
    ROLE_COORDINATOR,
    ROLE_EXPLICIT,
    ROLE_REVIEWER,
    ROLE_WORKER,
    Connection,
    ConnectionReferences,
    ConnectionTestResult,
    CredentialStatus,
    GlobalSettings,
    PinnedConnection,
    TestLayerResult,
)
from .repository import ConnectionRepository
from .router import build_settings_router
from .secret_store import (
    SOURCE_ENVIRONMENT,
    SOURCE_SECRET_STORE,
    FileSecretStore,
    SecretStoreCredentialResolver,
)
from .service import ConnectionService
from .testing import (
    ConnectionTestLog,
    ConnectionTester,
    default_http_post,
)

__all__ = [
    # errors
    "SettingsError",
    "SettingsConfigInvalid",
    "ConnectionReferenceInvalid",
    "CredentialUnavailable",
    "SecretStoreError",
    # models
    "Connection",
    "GlobalSettings",
    "CredentialStatus",
    "ConnectionReferences",
    "PinnedConnection",
    "TestLayerResult",
    "ConnectionTestResult",
    "ROLE_COORDINATOR",
    "ROLE_WORKER",
    "ROLE_REVIEWER",
    "ROLE_EXPLICIT",
    "DEFAULT_ROLES",
    "DEFAULT_EXECUTABLE_BACKEND",
    "PREFERRED_MODEL",
    "DEFAULT_BASE_URL",
    # repository
    "ConnectionRepository",
    # secrets
    "FileSecretStore",
    "SecretStoreCredentialResolver",
    "SOURCE_SECRET_STORE",
    "SOURCE_ENVIRONMENT",
    # service
    "ConnectionService",
    # testing
    "ConnectionTester",
    "ConnectionTestLog",
    "default_http_post",
    # api
    "build_settings_router",
]
