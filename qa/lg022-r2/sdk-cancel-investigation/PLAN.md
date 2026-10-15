# SDK 取消语义调查包 — PLAN

- Owner：独立 SDK 取消语义调查/QA owner（非产品返修者、非集成者；本轮独立于前 QA owner）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`）。
- 开工 HEAD：`0a88ab8`（clean；产品只读）。
- 依据：AGENTS.md / agent.md、LG-022 原验收、docs/06 版本门、docs/08 §8.1/§9 SDK 停止契约、
  `qa/lg022-r2/{REPORT,SUPPLEMENT,STATUS}.md`、前 harness `review_cancel_sdk_proof.py` 与其实际产物。
- 预算：wall 900s；round ≤160；noncache ≤220k；idle 180；开发 retry 0；**产品/真实 DeepSeek 请求 0**。
  探针单次 ≤45s，退出清自有 loopback/子进程。不动 8123/031/其他 owner。不 reset/clean/覆盖历史证据。

## 0. 事实基线（前包已确证，不重放）

- 前包 `review_cancel_sdk_proof.py` 实跑产物：`provider-substitute`（真 `google-antigravity==0.1.22`
  `Agent` + 真 `LocalAuthProxy`；上游为 loopback 伪 OpenAI 流），`real_model_calls: 0`。
  - `C1_cancel_confirmed_after_real_sdk_stop=false`，`real_sdk_teardown_fact={}`（空），
    `upstream_saw_client_gone=false`；`C2_unconfirmed_keeps_run_and_refs=true`（产品机制 keep 成立）。
  - 挂点：真 SDK reviewer 在伪上游流式下 5s 内未停止 → 产品 `unconfirmed`（honest）。
- 前包判定：挂起属“QA harness 未跑成 + 真实 SDK 行为 unknown”，**非产品 fail**。本包要**证伪或证实**该判断：
  是有真实 SDK 取消顺序证明，还是产品接线缺陷。

## 1. 只读源码事实（SDK 0.1.22，安装版）

- `google/antigravity/conversation/conversation.py`
  - `Conversation.chat()` = `await send()`（快速返回）后返回 **lazy** `types.ChatResponse(receive_chunks())`。
  - `Conversation.cancel()` → `connection.cancel()`；`Conversation.wait_for_idle()` → `connection.wait_for_idle()`；
    `Conversation.is_idle` → `connection.is_idle`。
- `google/antigravity/connections/local/local_connection.py`
  - `LocalConnection.cancel()`：置 `_client_cancelled=True` 并发送 `InputEvent(halt_request=True)`；**不等待 idle**。
  - `is_idle` = `processor.is_idle.is_set()`（`asyncio.Event`）。
  - `wait_for_idle()`：`await processor.is_idle.wait()` 并清空 step_queue。
  - `disconnect()`：先发 session_end（若有 hook），cancel background tasks、关 WS、关 stdin、等进程退出（升级 terminate/kill）。
- `event_processor.py`：`reset_for_turn()` `is_idle.clear()`；收到 `STATE_RUNNING` → clear；
  `STATE_FULLY_IDLE` → `is_idle.set()`；`STATE_CANCELLED` → 入队 `AntigravityExecutionError` 并 `is_idle.set()`。
- `agent.py`：`Agent.__aexit__` → AsyncExitStack aclose（→ `Conversation`/strategy `__aexit__` → `disconnect()`）。
- 结论（源码契约）：SDK **公开取消入口是 `Conversation.cancel()`（`Connection.cancel()`）**；确认停止须
  观察 `is_idle` / `wait_for_idle()`，或 `agent.__aexit__`（`disconnect`）真实返回。`task.cancel()` 不是 SDK 契约入口。

## 2. 产品接线只读事实

- `backend/lightgravity/verify/review.py::run_review_turn`：
  - `_turn()`：`agent.__aenter__()`；`chat = ensure_future(wait_for(agent.chat(prompt), timeout))`；
    `response = await _await_with_stop(chat, stop_event)`；随后 **`async for chunk in response.chunks:` 迭代整个流**。
  - `_await_with_stop(chat, stop_event)`：仅在 **`chat`（即 `send`/`Conversation.chat` 返回）仍 pending** 时轮询
    `stop_event`，命中时 `chat.cancel()`。由于 `Agent.chat()`→`Conversation.chat()` 先 `await send()` 再**立即返回**
    lazy response，`chat` 几乎立刻完成，`_await_with_stop` 随之返回。
  - **流式迭代 `response.chunks` 完全不在 `_await_with_stop` / `stop_event` 轮询范围内**，且产品路径中**没有任何**
    `conversation.cancel()` / `connection.cancel()` / `wait_for_idle()` 调用。
  - 结果：stop 请求只置 `threading.Event`（`ReviewLifecycle`），真 SDK turn 在流式阶段**永不观察到停止** →
    `resource_stop_report` 的 `finally`（`agent.__aexit__` / `proxy.stop()`）**不会执行** → 无 teardown 事实。
- `review_lifecycle.py`：`request_stop*` 置 `stop_event` 后等待工作线程 `done`，超时返回 `unknown` 且保留槽。

## 3. 待验证假设（本包核心）

- **H1**：`google-antigravity==0.1.22` 的真实取消入口为 `Conversation.cancel()`；调用后 SDK 会向 harness 发
  `halt_request`，harness 回 `STATE_CANCELLED`/`STATE_FULLY_IDLE` → `is_idle` 置位 → `wait_for_idle()` 返回；
  `agent.__aexit__` 真实返回；上游观察到连接断开。
- **H2（产品缺陷假设）**：产品 stop 路径在**流式迭代阶段**不触达 SDK `cancel()`，故真 SDK turn 在 stop 请求后
  不会停止，`unconfirmed` 是接线缺陷的表征（而不仅 harness 问题）。

## 4. 计划步骤（先只读源码，再最小 SDK 验证，再接产品真实 ReviewLifecycle）

1. ✅ 读 SDK 官方安装源码（上 §1）+ 产品接线（§2）+ 前探针实际产物。
2. 写最小本地 fake OpenAI 流式上游：**有效 SSE**（含 `data: {...}` 与 `[DONE]`）、分阶段可控 release、
   **总 timeout**（不得永久 hold 后把 SDK 120s 超时当 5s cancel 失败）。
3. **最小 SDK 验证**（不接产品，独立脚本）：真 `Agent`+`LocalAuthProxy`+fake 上游，流式进行中调用
   `conversation.cancel()`，断言：`wait_for_idle()` 在限时内返回、`is_idle==True`、`agent.__aexit__` 返回、
   上游观察到 client gone。给出**真实 SDK 取消顺序证明**。
4. **接产品真实 `run_review_turn` + `ReviewLifecycle`**（不改产品）：用同一 fake 上游复现流式阶段 stop，
   记录 stop 请求后 SDK turn 是否停止。若 **H2 成立**：给出最小 repro（文件/行/调用序列）。
5. 若可证明修复方向：给出**最小可实施修复建议**（例如：把 `response.chunks` 迭代纳入 stop 轮询，stop 时调用
   `conversation.cancel()` 并 `wait_for_idle()`；或改由 loop 任务持有并在 stop 时 cancel 该任务并等待 agent teardown）。
   **QA 不自修产品**，仅交 PM。
6. 判定：真实 SDK 取消顺序是否有可靠证明；产品/SDK 边界是否确切缺陷；若为明确使用限制则说明支持/不支持行为
   并据 LG-022 原验收给独立裁定（不写模糊“若 PM 认为”）。
7. 全部结论即时落盘于本目录；报告先落盘再精确 commit；不覆盖前脚本/证据。

## 5. 成功门（判定依据）

- **P1**：最小真 SDK（`Agent`+`LocalAuthProxy`+fake 上游）取消顺序**可复现证明**：
  cancel 后 `is_idle`/`wait_for_idle` 在限时内成立且 `agent.__aexit__` 返回、上游见 client gone（真 SDK cancel 契约成立）。
- **P2**：产品 `run_review_turn`/`ReviewLifecycle` 接线在流式阶段 stop 的行为**被准确定位**（确证缺陷或确证可用）。
- **P3**：若为产品缺陷：给出最小 repro（命令、文件、行为差异）+ 最小可实施修复建议（不实施）。
- **P4**：真实/替身分类明确；产品真实 DeepSeek 调用 0；未知保留；资源清理（无残留 loopback/子进程）。
