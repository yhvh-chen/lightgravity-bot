# LG-010 prototype-V0 minimal backend closed-loop QA

Independent version-QA evidence for the LG-010 gate (LG-005..010, LG-012
interface readiness).  These files are **not** product code and **not** pytest
tests; they reproduce the user delivery entry against the integrated app.

## Files

| File | Purpose |
|---|---|
| `lg010_e2e.py` | Drives `POST /api/v1/tasks` → Coordinator → GraphDispatcher → real `AntigravityExecutor` + loopback proxy → DeepSeek → Store → `VerificationService` → acceptance/decision endpoints. |
| `lg010_check_repro.py` | Model-free reproduction of the verification check blocker. |
| `evidence/lg010-evidence.json` | Redacted raw evidence from the real run (results, usage, raw diff, events, calls). |
| `evidence/lg010-check-repro.json` | Output of the model-free check reproduction. |

## What was real

- The pinned SDK (`google-antigravity==0.1.22`) executed a real DeepSeek turn
  through the product loopback auth proxy.  Requested model `deepseek-v4-flash`,
  upstream reported `deepseek-flash`.  **3** upstream calls in the successful
  primary run (6 more in the first, over-tight attempt), **9 total** across this
  QA — under the 10-call hard cap.
- The worker really modified the example git workspace:
  `demo_target.txt` content `LG010_REAL_CLOSURE`, sha256 recorded, `git status`
  shows the new file.
- The graph dispatcher created a member, ran a subtask, produced an artifact
  handoff and released the member.
- A missing-workspace Task failed honestly (`config_invalid`) with **0** model
  calls.

## Harness-only wrappers (not product behavior)

- `RecordingExecutor` delegates to the real executor and keeps the structured
  `ExecutorResult` / adapter events that the coordinator's sink intentionally
  does not persist.
- A single-node rule planner is used because the independent QA itself is
  capped to 10 upstream calls; the product's default two-node deliver+verify
  graph is covered by LG-008 unit evidence.
- Task `checks:` authorization is written directly to the Store because this
  version has no HTTP setter for that documented frontmatter field.

## Reproduce

```bash
DEEPSEEK_API_KEY=... uv run python probes/lg010/lg010_e2e.py \
    --max-proxy-calls 4 --model-calls-cap 4 --planner rules-single --prior-calls 6
uv run python probes/lg010/lg010_check_repro.py
```

The credential is never read from `.env` and never written to the evidence file.
