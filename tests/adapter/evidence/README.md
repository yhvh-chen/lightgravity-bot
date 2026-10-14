# LG-006 real-model evidence

These files are the raw (redacted) evidence for the LG-006 real executor chain.
They are **not** pytest tests and are not collected by `make test`. The
`DEEPSEEK_API_KEY` value is never written here; the executor masks the resolved
secret out of every event/result and each harness re-checks the output before
writing.

| File | Produced by | Content |
|---|---|---|
| `lg006-real-evidence.json` | `uv run python tests/adapter/evidence/lg006_real_run.py --max-calls 9` | File write + unified diff + structured output + usage; budget stop; session seed/recall; proxy call records; process check. |
| `lg006-cancel-evidence.json` | `uv run python tests/adapter/evidence/lg006_cancel_run.py` | A genuine mid-stream cancel with `confirmed=true`, `state=cancelled`, `stop_confirmed=true` and a confirmed proxy stop. |

## How to reproduce

```bash
# The environment must already inject the DeepSeek credential.
DEEPSEEK_API_KEY=... uv run python tests/adapter/evidence/lg006_real_run.py --max-calls 9
DEEPSEEK_API_KEY=... uv run python tests/adapter/evidence/lg006_cancel_run.py
```

Both harnesses use a temporary authorized workspace and delete it afterwards.
They hard-bound real model (chat-completions) calls; the main harness stops
before exceeding `--max-calls`.

## Model identity

Requested model id: `deepseek-v4-flash`; the upstream reports the canonical id
`deepseek-flash`. The executor records both (`result.model`,
`result.upstream_model`) and never silently falls back to another id or backend.
The string `"4.1"` is never used as an API id.

## Limits

- Execution evidence only. Independent version QA is LG-010/LG-022.
- Only the OpenAI-compatible (DeepSeek) backend is exercised. Gemini/Vertex
  remain unverified and are not default executable connections.
- `search_web`, MCP, Triggers and SDK-internal delegation stay off/ unavailable.
- Sandbox isolation was not escape-tested; only the SDK-reported status is
  recorded.
- `resume_recall` was classified `budget_exhausted` because the seed turn
  consumed the session lifetime budget, but the raw `adapter.text` events
  contain the seeded code (`recalled_secret=true`), evidencing recovery.
- The `cancel_confirmed` scenario in `lg006-real-evidence.json` lost a race to a
  fast completion; the confirmed cancel is in `lg006-cancel-evidence.json`.
