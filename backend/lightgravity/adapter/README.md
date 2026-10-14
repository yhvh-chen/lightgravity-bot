# Antigravity adapter (LG-005 / LG-006)

This package resolves Markdown role/resource descriptions into a versioned,
permission-bounded, redacted plan, and runs that plan through the real
Antigravity SDK via a loopback authentication proxy (LG-006).  It is the only
place in the product that imports the SDK.
`ResourceCompiler` never executes anything; `AntigravityExecutor` is the formal
executor.

## Public interface

| Symbol | Purpose |
|---|---|
| `ResourceCompiler(store, registry=...)` | Reads `agent`/resource entities through the `Store` protocol and produces a `CompiledAgentConfig`. |
| `CompileConstraints` | Task/run authorization from the coordinator: tool ceiling, budget ceilings, timeout, workspace, conversation id. |
| `CompiledAgentConfig` | Immutable plan: redacted connection (only `credential_ref`), session profile, skills, effective tools/hooks, budget, `unavailable` resources, `resource_versions`, `config_hash`, `executable` + `executable_reasons`. |
| `build_sdk_config(compiled, workspaces=..., base_url=..., save_dir=..., response_schema=...)` | Constructs the concrete SDK config (`LocalAgentConfig` / `LocalOpenAIAgentConfig`). Raises `CapabilityUnavailable` only when the SDK/connection is missing. |
| `adapter_capabilities()` | Conservative capability snapshot for `/health`, resources UI and diagnostics. |
| `default_registry(...)` | Program-registered tool/hook/connection-backend handlers; Markdown may only reference ids that exist here. |
| `LocalAuthProxy` | Product loopback auth proxy: ephemeral port, per-session token, fixed authorized upstream, credential injection, confirmed stop. |
| `AntigravityExecutor` | docs/08 §8 executor: compiles, resolves credentials, starts the proxy, runs the SDK session, normalizes events, classifies the outcome and returns `ExecutorResult`. |
| `ExecuteRequest` / `ExecutorResult` / `CancelResult` / `SessionRef` / `ExecutionRef` | Stable executor boundary for LG-007. |
| `Credentials` (`EnvCredentialResolver`, `InMemoryCredentialResolver`, `Secret`) | In-memory `credential_ref` resolution; LG-025 plugs a controlled store here. |
| `ArtifactSink` / `DirectoryArtifactSink` | Optional artifact persistence for the produced diff. |

## Contract with LG-006 (real executor)

1. Call `compile_agent(...)` and treat `executable=False` as **not runnable**;
   never let the SDK attempt a session and infer readiness from that.
2. `build_sdk_config(...)` returns an SDK config object, but a built config is
   *not* an authenticated or verified run. LG-006 owns:
   - resolving `credential_ref` (via `lightgravity.settings`, LG-025) and
     injecting it at execution time — the OpenAI-compatible backend has **no**
     `api_key` field, so injection is explicit through `LocalAuthProxy`;
   - creating/resuming the SDK session, event normalization, `emit`, cancel
     confirmation, usage capture and returning the structured result;
   - honesty about the Gemini/Vertex path: it is unverified in this environment
     until LG-003 is re-run with credentials.
3. Extend the registry with real handlers via
   `default_registry(tools=..., hooks=..., backends=...)`; nothing is registered
   implicitly from resource files.

## LG-006 executor boundary (stable for LG-007 / LG-025)

- `ExecuteRequest` carries the frozen docs/08 fields plus additive adapters
  fields: `agent_ref` (the LG-005 `agent` to compile) and optional `save_dir`,
  `conversation_id`, `response_schema`.
- `AntigravityExecutor.execute(request, emit)` calls `emit(dict)` for every
  normalized adapter event; it never writes control state. The coordinator
  persists events/results through the `Store`.
- `cancel(execution_ref)` returns `confirmed=False` unless the SDK conversation
  is observed idle; callers must not write `cancelled` otherwise. `close`
  releases the session and stops the proxy.
- Outcome classification: `succeeded | failed | blocked | cancelled |
  budget_exhausted | timeout`; `stop_confirmed` is the honest stop flag.
- Credentials come from `EnvCredentialResolver` (environment) or an injected
  `CredentialResolver` (LG-025 controlled store); values never leave memory.

## Guarantees

- **No permission expansion**: effective tools = agent `tool_refs` ∩ task
  `allowed_tools`; budgets take the most restrictive value.
- **No implicit execution surface**: MCP, Triggers, `search_web` and SDK-internal
  delegation are always reported `unavailable` and never attached.
- **Secrets are references only**: plaintext secret-like fields are rejected
  with `secret_in_resource`; compiled output is redacted, and the executor masks
  the resolved value out of every result/event.
- **Loopback, single-session proxy**: binds `127.0.0.1` on an ephemeral port,
  serves only its own token path, forwards only to the authorized upstream and
  never logs the `Authorization` header. `stop()` returns a confirmation.
- **Fixed version/hash**: every resolved entity contributes `revision` +
  `content_hash`; the pinned SDK version is `0.1.22`.
