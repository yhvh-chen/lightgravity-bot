# Antigravity adapter — configuration compilation (LG-005)

This package resolves Markdown role/resource descriptions into a versioned,
permission-bounded, redacted plan and (optionally) into installed SDK config
objects. It **does not execute** anything: no session is created, no model is
called, no MCP server/Trigger/subagent is started, and no secret value is
resolved.

## Public interface

| Symbol | Purpose |
|---|---|
| `ResourceCompiler(store, registry=...)` | Reads `agent`/resource entities through the `Store` protocol and produces a `CompiledAgentConfig`. |
| `CompileConstraints` | Task/run authorization from the coordinator: tool ceiling, budget ceilings, timeout, workspace, conversation id. |
| `CompiledAgentConfig` | Immutable plan: redacted connection (only `credential_ref`), session profile, skills, effective tools/hooks, budget, `unavailable` resources, `resource_versions`, `config_hash`, `executable` + `executable_reasons`. |
| `build_sdk_config(compiled, workspaces=...)` | Constructs the concrete SDK config (`LocalAgentConfig` / `LocalOpenAIAgentConfig`). Raises `CapabilityUnavailable` only when the SDK/connection is missing. |
| `adapter_capabilities()` | Conservative capability snapshot for `/health`, resources UI and diagnostics. |
| `default_registry(...)` | Program-registered tool/hook/connection-backend handlers; Markdown may only reference ids that exist here. |

## Contract with LG-006 (real executor)

1. Call `compile_agent(...)` and treat `executable=False` as **not runnable**;
   never let the SDK attempt a session and infer readiness from that.
2. `build_sdk_config(...)` returns an SDK config object, but a built config is
   *not* an authenticated or verified run. LG-006 owns:
   - resolving `credential_ref` (via `lightgravity.settings`, LG-025) and
     injecting it at execution time — the OpenAI-compatible backend has **no**
     `api_key` field, so injection is explicit;
   - creating/resuming the SDK session, event normalization, `emit`, cancel
     confirmation, usage capture and writing control state through the `Store`;
   - honesty about the Gemini/Vertex path: it is unverified in this environment
     until LG-003 is re-run with credentials.
3. Extend the registry with real handlers via
   `default_registry(tools=..., hooks=..., backends=...)`; nothing is registered
   implicitly from resource files.

## Guarantees

- **No permission expansion**: effective tools = agent `tool_refs` ∩ task
  `allowed_tools`; budgets take the most restrictive value.
- **No implicit execution surface**: MCP, Triggers, `search_web` and SDK-internal
  delegation are always reported `unavailable` and never attached.
- **Secrets are references only**: plaintext secret-like fields are rejected
  with `secret_in_resource`; compiled output is redacted.
- **Fixed version/hash**: every resolved entity contributes `revision` +
  `content_hash`; the pinned SDK version is `0.1.22`.
