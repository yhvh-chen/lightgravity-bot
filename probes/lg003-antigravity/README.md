# LG-003 Antigravity SDK probes

Isolated probe environment for verifying the installed **`google-antigravity`**
SDK/runtime. Owned by LG-003 (`probes/**`); it is not part of the product package
and must never be imported by `backend/lightgravity`.

- Fixed target: **`google-antigravity==0.1.22`** (PyPI distribution name; the
  GitHub repo is `google-antigravity/antigravity-sdk-python`).
- Independent environment: this directory has its own `pyproject.toml`,
  `.python-version`, `uv.lock` and `.venv` (`uv sync`). It does not touch the
  repository root dependency files.
- Platform: x86_64 Linux; the wheel ships a native `localharness` runtime
  (Go, ~131 MB), so the platform wheel is architecture-specific.

## Setup

```bash
cd probes/lg003-antigravity
uv lock
uv sync
```

## Run

```bash
# Offline probes + canned event self-test (no credentials needed)
./scripts/run_all.sh

# Additionally run bounded live probes against the real DeepSeek model
LG003_LIVE=1 ./scripts/run_all.sh
```

Results are written to `evidence/`. A narrative report is in
`reports/LG-003-report.md`.

## Probes

| Script | What it verifies |
|---|---|
| `p01_environment.py` | SDK/Python/platform versions, native runtime hash, credential presence (booleans only) |
| `p02_offline_capabilities.py` | Endpoint classes, backend validation, tool/skill exclusivity, budget/retry/structured-output/session config |
| `p03_runtime_handshake.py` | Native runtime starts, conversation initializes, sandbox status without a model call; Gemini credential gating |
| `p04_canned_events.py` | Streaming parser (text, usage, stop reason) against a canned local SSE server |
| `p05_live_deepseek.py` | Real model: text, file tools, structured output, budget stop, cancel, session save/resume |
| `p06_skills.py` | Real model with file-based `SKILL.md` and inline skills |
| `p07_web_tools.py` | Real model with `read_url_content` (local server) and `search_web` |
| `openai_compat_proxy.py` | Local OpenAI-compatible endpoint; canned mode or DeepSeek forwarding with injected bearer token |

## Notes / limitations

- The SDK's OpenAI-compatible config (`LocalOpenAIAgentConfig`, the "Gemma
  endpoint") exposes only `base_url`; it has no api_key field. Hosted providers
  that require a bearer token therefore need an explicit auth-injecting proxy.
  The proxy used here is transport/auth plumbing; the answering model is real.
- `search_web` is invoked but returns no usable results through the local
  OpenAI-compatible endpoint (it appears to rely on Gemini-backed search). This
  is reported, not hidden.
- The product's first-version Gemini backend (Developer API / Vertex) cannot be
  exercised in this environment because no Gemini/Google credentials are
  available. That is recorded as unverified.
- Credentials are never written to evidence. Only presence booleans are recorded.
