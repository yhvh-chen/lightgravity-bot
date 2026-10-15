# LG-013 direct-answer probe (integration evidence)

Scope: evidence only. This directory does not change product code, task state,
contracts or dependencies. It documents **one** bounded real-model probe run
during the LG-013 integration to prove the new tool-less direct-answer path
(`backend/lightgravity/coordinator/dialogue.py`, wired via
`create_app(responder=...)`) behaves as specified.

This is **integration-round evidence, not a version QA** and does **not** cover
the full browser HTTP business path (still LG-021/LG-022).

## What was run

`probes/lg013/scripts/lg013_direct_answer_probe.py`, with the DeepSeek
credential from the process environment only (`DEEPSEEK_API_KEY`; no `.env` is
read, no secret is printed or written):

1. Build a temp data/workspace/secret dir.
2. Seed a real `openai-compat` coordinator connection (`deepseek-v4-flash`,
   `https://api.deepseek.com/v1`) and set it as `default_coordinator` **before**
   `build_runtime` (the responder is resolved at startup).
3. `build_runtime` → the real responder is wired.
4. POST a plain read-only question to
   `/api/v1/conversations/global/messages` through the app's own ASGI stack.
5. Assert no Task / Run / Member control files appear and the workspace stays
   empty; scan the record for secret leakage.

Bound: exactly **one** model turn (`model_calls_cap=1`), 120 s wall clock.

## Result (`evidence/lg013-direct-answer-probe.json`)

- `http_status: 200`; `kind: "direct"`, `data.intent: "answer"`,
  `data.creates_task: false`.
- Model reply `"Four."` — a **real** model answer (a deterministic fallback
  would have been the built-in/`unavailable` text, not this). No
  `tool_probe`/structured evidence is claimed.
- `created_tasks=0`, `created_members=0`, `created_runs=0`; workspace file
  inventory empty; `leak_findings=[]`.

## Limits

- One short answer only. It shows the direct path answers a plain question and
  stays tool-less; it does not exercise the delivery/team path (that is
  LG-010/LG-021/LG-022).
- SDK-internal delegation, MCP, Triggers and `run-command`/web tools stay off.
- Not a substitute for the LG-021/LG-022 browser acceptance or LG-027 settings
  QA.
