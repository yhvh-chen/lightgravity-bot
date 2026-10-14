"""Antigravity adapter: static resource/config compilation (LG-005).

Scope: compile Markdown role/resource descriptions into a versioned, redacted,
permission-bounded plan and (optionally) into installed SDK config objects.
This package does **not** execute work (that is LG-006) and does **not** route,
queue or schedule (that is LG-007).  It never starts MCP servers, Triggers or
SDK-internal delegation, and it never resolves a secret value - resources only
carry a ``credential_ref``.
"""

from .capabilities import (
    SDK_DISTRIBUTION,
    SDK_PINNED_VERSION,
    AdapterCapabilities,
    adapter_capabilities,
    installed_sdk_version,
)
from .compiler import (
    CompileConstraints,
    CompiledAgentConfig,
    CompiledConnection,
    CompiledHook,
    CompiledSessionProfile,
    CompiledSkills,
    CompiledTool,
    ConnectionPin,
    DefaultConnectionResolver,
    ResourceCompiler,
    ResourceVersion,
    UnavailableResource,
)
from .credentials import (
    CredentialResolver,
    EnvCredentialResolver,
    InMemoryCredentialResolver,
    Secret,
    default_env_var_name,
)
from .errors import (
    AdapterConfigInvalid,
    AdapterError,
    CapabilityUnavailable,
    ReferenceInvalid,
)
from .execution import (
    CancelResult,
    CheckRecord,
    EventSink,
    ExecuteRequest,
    ExecutionRef,
    ExecutorAdapter,
    ExecutorResult,
    FailureInfo,
    SessionRef,
    Usage,
)
from .executor import (
    AntigravityExecutor,
    ArtifactSink,
    DirectoryArtifactSink,
    classify_outcome,
    diff_snapshots,
    snapshot_tree,
)
from .proxy import (
    AUTHORIZED_UPSTREAM_HOSTS,
    DEEPSEEK_UPSTREAM_URL,
    LocalAuthProxy,
    ProxyCallRecord,
    upstream_chat_completions,
)
from .redaction import REDACTED, is_sensitive_key, mask_values, redact, sensitive_paths
from .registry import (
    ConnectionBackend,
    HookRegistration,
    ImplementationRegistry,
    ToolRegistration,
    default_registry,
)
from .sdk_config import SdkConfigResult, build_sdk_config, sdk_available

__all__ = [
    # capabilities
    "SDK_DISTRIBUTION",
    "SDK_PINNED_VERSION",
    "AdapterCapabilities",
    "adapter_capabilities",
    "installed_sdk_version",
    # compiler
    "CompileConstraints",
    "ConnectionPin",
    "DefaultConnectionResolver",
    "CompiledAgentConfig",
    "CompiledConnection",
    "CompiledHook",
    "CompiledSessionProfile",
    "CompiledSkills",
    "CompiledTool",
    "ResourceCompiler",
    "ResourceVersion",
    "UnavailableResource",
    # credentials
    "Secret",
    "CredentialResolver",
    "EnvCredentialResolver",
    "InMemoryCredentialResolver",
    "default_env_var_name",
    # execution boundary
    "CancelResult",
    "CheckRecord",
    "EventSink",
    "ExecuteRequest",
    "ExecutionRef",
    "ExecutorAdapter",
    "ExecutorResult",
    "FailureInfo",
    "SessionRef",
    "Usage",
    # executor
    "AntigravityExecutor",
    "ArtifactSink",
    "DirectoryArtifactSink",
    "classify_outcome",
    "diff_snapshots",
    "snapshot_tree",
    # proxy
    "AUTHORIZED_UPSTREAM_HOSTS",
    "DEEPSEEK_UPSTREAM_URL",
    "LocalAuthProxy",
    "ProxyCallRecord",
    "upstream_chat_completions",
    # errors
    "AdapterConfigInvalid",
    "AdapterError",
    "CapabilityUnavailable",
    "ReferenceInvalid",
    # redaction
    "REDACTED",
    "is_sensitive_key",
    "mask_values",
    "redact",
    "sensitive_paths",
    # registry
    "ConnectionBackend",
    "HookRegistration",
    "ImplementationRegistry",
    "ToolRegistration",
    "default_registry",
    # sdk config
    "SdkConfigResult",
    "build_sdk_config",
    "sdk_available",
]
