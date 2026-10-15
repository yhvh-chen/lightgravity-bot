# STATUS — 复核流式停止接线修复

| 项 | 状态 |
|---|---|
| Worktree / branch | `/home/yhvh/code/lightgravity-bot-worktrees/lg022-stream-fix` / `fix/lg022-stream` |
| 基点 | `integrate/batch7@85adc82`（契约 1.10.0） |
| QA 证据 merge | `qa/lg022-r2@cea87ab`（仅证据，无产品改动，clean merge） |
| SDK | `google-antigravity==0.1.22`（固定，未切版本/供应商） |
| 产品真实 DeepSeek 请求 | 0 |
| 缺陷定位 | `verify/review.py::run_review_turn._turn()` 流式阶段未轮询 stop、未调 SDK cancel |
| 修复实现 | done（`verify/review.py`：流式 stop 接线 + SDK cancel + 同 loop teardown） |
| 局部测试 | done（`tests/verify/test_lg022_stream_stop.py`，10 passed） |
| 真 SDK + fake SSE 探针 | done（`fix_confirmed=true`，0 真实模型调用，5/5 一致） |
| mypy | done（`backend/lightgravity/verify/` 9 files clean） |
| 相关回归 | done（verify+coordinator+adapter 285 passed） |
| REPORT | done（`probes/lg022/STREAM-STOP-FIX/REPORT.md`） |
| commit | pending |

## 进度日志

- [x] 读 AGENTS/agent/docs08 §8.1/§9、LG-022、QA `sdk-cancel-investigation/REPORT.md` 与全部探针源码。
- [x] 核现有分支/路径/root dirty（`integrate/batch7` root 仅 PROGRESS.md dirty，保留不动）。
- [x] 创建持久 worktree + branch，基于 `integrate/batch7@85adc82`，安全 merge QA 证据。
- [x] 实现 `verify/review.py` 流式 stop 接线（流式阶段轮询 + `Conversation.cancel()`/`wait_for_idle()` +
      同 loop 有界 teardown）。
- [x] 局部 unit（10）+ 真 SDK/fake SSE 探针（fix_confirmed）。
- [x] mypy + 局部 pytest（verify/coordinator/adapter 285 passed）。
- [x] REPORT。
- [ ] commit。

## 复现命令（0 真实 DeepSeek）

```
timeout 90 .venv/bin/python probes/lg022/STREAM-STOP-FIX/stream_stop_probe.py \
    probes/lg022/STREAM-STOP-FIX/evidence/stream-stop-fix.json
timeout 90 .venv/bin/python -m pytest tests/verify/test_lg022_stream_stop.py -q
```
