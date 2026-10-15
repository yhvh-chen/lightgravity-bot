# LG-022 「复核流式停止接线」修复包 — PLAN

- Owner：`agent:pi-lg022-stream`（pi + env DeepSeek；主代理只 PM，**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-stream-fix`（branch `fix/lg022-stream`）。
- 基点：`integrate/batch7@85adc82`（契约 `1.10.0`）+ merge `qa/lg022-r2@cea87ab`（**仅证据**，无产品改动）。
- 输入缺陷：`qa/lg022-r2/sdk-cancel-investigation/REPORT.md`（独立已证实 D2 接线缺陷）。

## 1. 缺陷（独立已证实，不重跑旧失败真实链）

`backend/lightgravity/verify/review.py::run_review_turn._turn()` 中：

```python
chat = asyncio.ensure_future(asyncio.wait_for(agent.chat(prompt), timeout=timeout_seconds))
response = await _await_with_stop(chat, stop_event)   # 只守护 send() 阶段
chunks = []
async for chunk in response.chunks:                   # 真正流式阶段，stop 不在轮询范围
    chunks.append(chunk)
```

- `Agent.chat()` 立即返回 lazy `ChatResponse`，故 `chat` future 在流式开始前几乎立即完成；
  `_await_with_stop` 的 `while True` 轮询对已完成的 future 恒立即返回，**流式阶段从不检查 `stop_event`**。
- 产品路径**无任何** `Conversation.cancel()` / `wait_for_idle()` 调用；`chat.cancel()` 只取消 `send` 阶段的 task，
  不会取消已开始的 SDK turn。
- 结果：复核运行中 `pause`/`cancel` 等满 `stop_timeout`(默认 5s) → 诚实 `unconfirmed`（安全兜底正确），
  但真实 reviewer **不可达停止**；`finally` 的 `resource_stop_report` 不执行。
- SDK 0.1.22 已有公开取消入口：`Conversation.cancel()` / `wait_for_idle()` / `is_idle` / `disconnect()`。

## 2. 修复目标（最小、局部）

- 在**流式迭代阶段**承载 stop：逐步 `asyncio.wait_for(anext, 0.05)`，每步检查 `stop_event`。
- 停止时调用 SDK 公开入口 `agent.conversation.cancel()` + 有界 `wait_for_idle()`，
  再退出 `_turn()`，让 `finally` 写真实 `resource_stop_report.confirmed`。
- `finally` 的 `agent.__aexit__` 加有界 `wait_for`，避免极端情况长期不返回。
- 保持全部既有语义：`ReviewLifecycle` 未确认真实停止仍 `unconfirmed` + 保留槽/refs；
  只在真实 teardown 事实后 confirmed。不伪造 `done`，不新增状态/端点/字段/供应商/版本，不切 SDK。

## 3. 范围（owner 白名单）

- `backend/lightgravity/verify/review.py`（主改动）。
- 确实必要的同 verify 目录文件（如需要，仅限本缺陷接线）。
- `tests/verify/` 局部测试；`probes/lg022/STREAM-STOP-FIX/**`。
- **不碰**：`adapter/executor.py`（031 owner）、`bootstrap`/`app`/`source`/`vector`/`frontend`/`PROJECT.md`/`docs08`
  等共享 owner；不改契约版本（保持 `1.10.0`；如真发现接口变化先报告）。

## 4. 验证计划（0 真实 DeepSeek）

1. **局部 unit**：pause / cancel / timeout / 流持续（stop 后不再读 chunk、不丢已收 chunk）/ close 异常 /
   unknown-held（无真实停止事实保持 unconfirmed 且保留槽）。
2. **真 SDK + 本地 fake SSE 探针**（复用 QA `fake_upstream.py` 模式，`provider-substitute`，0 DeepSeek）：
   驱动真实 `ModelReviewer`/`run_review_turn`/`ReviewLifecycle`/`ControlService`，证明
   stop 触达 SDK cancel、观察真实 idle、有界 teardown、`resource_stop_report.confirmed=true`。
   - 禁止仅用普通 `asyncio.Event` 假 reviewer 冒充真实 SDK 取消作为通过依据。
3. `mypy` 改动模块；`pytest` 局部相关测试（无必要不全量）。
4. 命令单次 ≤45/90s 可控退出；退出清理自有 loopback/子进程。

## 5. 交付

- `probes/lg022/STREAM-STOP-FIX/REPORT.md`（真实命令/退出码、源码基点、SDK 版本、产品请求 0、未测、资源清理）。
- 精确本地 commit（仅本包归属），不改 LG-022 done，交新独立 pi QA 复验。

## 6. 预算

- wall 900s；round ≤170；noncache ≤230k；idle 180；开发 retry 0；产品真实 DeepSeek 生成请求 **0**。
