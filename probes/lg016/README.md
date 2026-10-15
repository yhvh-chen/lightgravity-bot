# LG-016 bounded real-SDK control/recovery evidence

`lg016_control_e2e.py` is a bounded evidence harness (not product code, not a
pytest test).  It drives the **product** control path against the pinned SDK
(`google-antigravity==0.1.22`) + loopback auth proxy + real DeepSeek upstream:

1. a real Task reaches `executing`
   (`GraphDispatcher` → `AntigravityExecutor` → DeepSeek);
2. `POST /api/v1/tasks/{id}/actions` `cancel` and `pause` ask the real executor
   to stop and only write `cancelled`/`paused` after the adapter confirms the
   stop (docs/08 §9);
3. the real SDK session created during that Run is closed through the adapter
   `close` path and no SDK `localharness` process leaks;
4. a restart scan over a Run whose worker died never auto-replays it and marks
   `recovery_required`.

Unit coverage of the same semantics lives in `tests/control/` (mock dispatcher).

## Run

```bash
DEEPSEEK_API_KEY=... uv run python probes/lg016/lg016_control_e2e.py \
    --max-proxy-calls 2 --model-calls-cap 4 --prior-calls <prior> --timeout 240
```

Raw hard caps: `--max-proxy-calls` per execution (2) and `--model-calls-cap`
(4) per run.  The credential is read only from the process environment and
never written to the evidence file.

## Native session continuation (`lg016_native_continuation.py`)

`lg016_native_continuation.py` is a second, smaller bounded harness that proves
the **native SDK session continuation** data flow the product relies on for a
confirmed pause→resume:

1. a real `ExecuteRequest` creates a fresh native session and reports its
   non-secret identity (`session_id`, `conversation_id`, `save_dir`);
2. a second real `ExecuteRequest` carrying that run's `conversation_id` +
   `save_dir` + `continuation_mode=resume` (exactly the tuple the coordinator's
   `ContinuationPlanner` produces) must attach to the **same** native session —
   the adapter reports `state: resumed` and the same `conversation_id` — instead
   of creating a new one.

```bash
DEEPSEEK_API_KEY=... uv run python probes/lg016/lg016_native_continuation.py \
    --max-proxy-calls 2 --model-calls-cap 4
```

It proves the SDK's native `session_continuation_mode=resume` + `conversation_id`
+ `save_dir` mechanism, not the full product resume gate (that is unit-tested in
`tests/control/test_continuation.py`).  Evidence:
`evidence/lg016-native-continuation-evidence.json`.

## Evidence

`evidence/lg016-control-evidence.json` — the raw, redacted result of the last
real control/recovery run.  See `reports/LG-016-report.md` for the console
summary and limits.
