# LG-025 real DeepSeek evidence

`lg025_real_run.py` is an opt-in, bounded evidence run for the LG-025 connection
tester against the real first-version backend. It reuses the product LG-006
`LocalAuthProxy` (no probe or reference repo import); the script reads
`DEEPSEEK_API_KEY` from the process environment, writes it to a temporary
`0600` secret store, and never prints or persists it.

## How it was run

```bash
uv run python tests/settings/evidence/lg025_real_run.py
```

- Environment: uv-managed venv, `google-antigravity==0.1.22` installed,
  `DEEPSEEK_API_KEY` injected by the task environment (value never shown).
- Real model calls: **1 of a hard cap of 3** (one `runtime_network` request).
- Result: `overall=verified`; `model=deepseek-v4-flash` sent,
  `upstream_model=deepseek-flash` returned; proxy `stop_confirmed=True`;
  `proxy_calls=1`.
- Staleness: editing the connection and rotating the credential version both
  mark the recorded result stale.
- Secret store: directory/file permission check reports no issues and the store
  is outside the repository; the evidence JSON contains no secret.

The machine-readable result is stored in [lg025-real-evidence.json](lg025-real-evidence.json).

## Limits (not claimed)

- The `tool_probe` / `structured_output` layers are reported `skipped`; LG-025
  did not run SDK tool/structured-output probes (they need an isolated SDK
  session with its own workspace and budget, and would consume the call cap).
- `capability` is the SDK capability *declaration* (`adapter_capabilities`), not
  a runtime verification; it is deliberately not merged with the network result.
- Gemini/Vertex remain unverified and cannot be saved as executable connections.
- The secret store is permission-protected, not encrypted at rest.
- This is a task-level check (one real call); it is not the LG-027 version QA.
