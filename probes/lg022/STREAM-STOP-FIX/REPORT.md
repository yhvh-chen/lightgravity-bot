# LG-022 「复核流式停止接线」修复包 — REPORT

- Owner：`agent:pi-lg022-stream`（pi + env DeepSeek；主代理只 PM，**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-stream-fix`（branch `fix/lg022-stream`）。
- 基点：`integrate/batch7@85adc82`（契约 `1.10.0`）+ merge `qa/lg022-r2@cea87ab`（**仅证据**，无产品改动）。
- SDK：`google-antigravity==0.1.22`（安装版，固定；**未升级/切换供应商/版本**）。
- **本包产品真实 DeepSeek 生成请求 = 0**（全部本地替身/真 SDK + 本地 fake SSE；未重放旧失败真实链）。
- 依据：AGENTS.md / agent.md、`backlog/tasks/LG-022.md`、`docs/08`（§8.1/§9）、
  `qa/lg022-r2/sdk-cancel-investigation/REPORT.md`（独立已证实 D2 接线缺陷）与全部最小复现/探针源码。

## 0. 结论一句话

已把复核运行中 `pause`/`cancel` 的 stop 请求接到 **SDK 0.1.22 公开取消入口**：stop 轮询现在覆盖真正的
**流式读取阶段**，停止时调用 `Conversation.cancel()` + 有界 `wait_for_idle()`，并让 reviewer 的 `finally`
产出**真实 teardown 事实**。真 SDK + 本地 fake SSE 探针下，产品停止从修复前**等满 5s 仍 `unconfirmed`、
reviewer 仍在运行**，变为 **~0.13s `confirmed`、SDK idle=true、teardown confirmed=true、无残留 reviewer、
`session_refs` 保留**。既有语义（未确认不伪 done、不释放槽、保留 refs/历史、不新增状态/端点/字段/供应商、契约仍
`1.10.0`）全部保持不变。

## 1. 缺陷（独立已证实，本包不重跑旧失败真实链）

位置：`backend/lightgravity/verify/review.py::run_review_turn._turn()`（修复前 ~910–925 行）与
`_await_with_stop()`（829–855 行）。

```python
chat = asyncio.ensure_future(asyncio.wait_for(agent.chat(prompt), timeout=timeout_seconds))
response = await _await_with_stop(chat, stop_event)   # 只守护 send() 阶段
chunks = []
async for chunk in response.chunks:                   # 真正流式阶段，stop 不在轮询范围
    chunks.append(chunk)
```

- `Agent.chat()` 立即返回 lazy `ChatResponse` → `chat` future 在流式开始前几乎即可完成 →
  `_await_with_stop` 的 stop 轮询**在流式阶段从不生效**。
- 产品路径**无任何** `conversation.cancel()` / `wait_for_idle()`；`chat.cancel()` 只取消 `send` 阶段 task，
  不会取消已开始的 SDK turn。
- 结果：复核运行中 `pause`/`cancel` 等满 `stop_timeout`(默认 5s) → 诚实 `unconfirmed`（安全兜底正确，保留），
  但真实 reviewer **不可达停止**，`finally` 的 `resource_stop_report` 从不执行。
- QA 证据：`qa/lg022-r2/sdk-cancel-investigation/evidence/decisive-product-vs-sdk-cancel.json`
  场景 A：`control_stop_elapsed_s=5.027`、`state=unconfirmed`、`lifecycle_still_reviewing_at_stop=true`、
  无 teardown 事实；场景 B（探针内演示修复方向）毫秒级停止。

## 2. 实现（仅 `backend/lightgravity/verify/review.py`，185+/49-）

1. **流式阶段承载 stop**：新增 `_drain_stream_with_stop(response, stop_event, agent)`。
   - stop 为 `None`（同步 fixture 路径）时行为与原先 `async for chunk in response.chunks` 完全一致（全量 drain）。
   - stop 非 `None` 时把每次 `anext` 包成**独立 task**，用 `asyncio.wait({pull}, timeout=0.05)` 短等：
     **不取消 pending pull**，只用于周期性重查 `stop_event`。
   - 关键发现（本包实测）：直接对 `response.chunks.__aiter__()` 做 `asyncio.wait_for(anext, 0.05)`，
     超时会**取消 SDK 内部共享 cursor 的 pull**，把底层流提前关闭 → 之后全部 chunk 丢失
     （实测 drain 返回 **0 chunks / 0.05s**）。因此改为「pull 作为不取消的 task + 短等重查」。
     已收 chunk 逐个 append，**不丢/不重**（`anext` 只在产值后消费一次）。
2. **停止时触达 SDK 取消入口**：新增 `_cancel_sdk_turn(agent)`，调用
   `agent.conversation.cancel()` 后有界 `wait_for_idle()`（`_CANCEL_IDLE_TIMEOUT_SECONDS=5s`）；
   仅当 SDK 确认 idle 才返回 `True`，取消请求失败/超时一律 `False`（**不假装已停**）。
   stop 命中时：`await _cancel_sdk_turn(agent)` → `pull.cancel()` + 丢弃 → `raise ReviewStopped`，
   让上层 `finally` 做真实 teardown。发送阶段 stop 走 `_await_with_stop(..., agent)` 同样先 `_cancel_sdk_turn`。
3. **teardown 与 turn 同 loop**（顺带修复真缺陷）：原先 `_turn()` 与 `agent.__aexit__` 分别经两次
   `_run_coro_sync` 跑在**不同私有 loop**，`__aexit__` 的 `disconnect()` 在已关闭 loop 上
   `call_soon` → `RuntimeError('Event loop is closed')`，导致 teardown 偶发 `agent_closed=False`。
   现改为**同一个协程 `_turn_with_teardown()` 内**完成 enter/chat/stream/stop/teardown（含 `__aexit__` 有界
   `_AGENT_CLOSE_TIMEOUT_SECONDS=10s` 与 `proxy.stop()`），一次 `_run_coro_sync` 执行。
4. **不变量**：`ReviewStopped` 语义、`ReviewLifecycle` 未确认 `unknown`+保留槽、`session_refs` 从不删除、
   `cleanup` 不伪 `done`、`resource_stop_report.confirmed = agent_closed and proxy_stopped` 未改。
   **不新增端点/字段/枚举/迁移/SDK/供应商；契约保持 `1.10.0`**（无接口变化，故未升版）。

## 3. 验证

### 3.1 真 SDK + 本地 fake SSE 探针（`provider-substitute`，产品请求 0）

探针：`probes/lg022/STREAM-STOP-FIX/stream_stop_probe.py`（真 `google-antigravity==0.1.22` `Agent` +
真 `LocalAuthProxy`；上游为本目录 `continuous_fake_upstream.py` 持续分块 SSE，非 DeepSeek）。
驱动**真产品** `ModelReviewer.review` → `run_review_turn` → 真 `ReviewLifecycle` → 真 `ControlService.stop`。

| 组 | 修复前（QA A） | 本包修复后 |
|---|---|---|
| `ControlService.stop` 耗时 | **5.027s**（等满 stop_timeout） | **0.132s** |
| `control.state` / `confirmed` | `unconfirmed` / false | **`confirmed` / true** |
| `lifecycle_still_reviewing_at_stop` | **true** | **false** |
| `resource_stop_report` | `{}`（无事实） | `{agent_closed:true, proxy_stopped:true, confirmed:true}` |
| 到达 SDK `conversation.cancel()` | **否** | **是（1 次）** |
| `conversation.is_idle` after cancel | n/a | **true** |
| `session_refs` 保留 | true | **true** |
| 无 stop 正常路径（控制组） | — | 正常返回，teardown confirmed |

证据：`probes/lg022/STREAM-STOP-FIX/evidence/stream-stop-fix.json`（`fix_confirmed: true`；
`real_model_calls: 0`；`sdk_version: 0.1.22`）。连续 5 次重跑一致（stop 0.146–0.223s，均 `fix_confirmed=true`）。

### 3.2 局部 unit（`tests/verify/test_lg022_stream_stop.py`，10 项）

覆盖：流式阶段 mid-stream stop 触达 SDK cancel + idle、已收 chunk 不丢不重、无 stop 全量 drain、
自然结束不被误判停止、`_cancel_sdk_turn` 无 idle/取消失败/无 conversation 均诚实返回 False 且有界、
pending pull 时 stop 到达仍保留前置 chunk 并调 cancel、**unknown-held**（reviewer 不响应 stop →
`request_stop_async` 返回 `unknown` 且 `is_reviewing` 仍 true、槽保留）。全部为确定性替身，不冒充真实 SDK 取消。

### 3.3 实跑命令 / 退出码

| 命令 | 退出码 | 结果 |
|---|---|---|
| `timeout 90 .venv/bin/python probes/lg022/STREAM-STOP-FIX/stream_stop_probe.py probes/.../evidence/stream-stop-fix.json` | 0 | `fix_confirmed: true` |
| `timeout 90 .venv/bin/python -m pytest tests/verify/test_lg022_stream_stop.py -q` | 0 | 10 passed |
| `timeout 90 .venv/bin/python -m pytest tests/verify tests/coordinator/test_lg022_review_lifecycle.py tests/coordinator/test_lg022_r2_resource_chain.py -q -p no:randomly` | 0 | 85 passed |
| `timeout 200 .venv/bin/python -m pytest tests/ -q -p no:randomly -k "review or stop or cancel or pause or lifecycle or lg022"` | 0 | 134 passed, 1 skipped |
| `timeout 240 .venv/bin/python -m pytest tests/verify tests/coordinator tests/adapter -q -p no:randomly` | 0 | 285 passed |
| `timeout 120 .venv/bin/mypy backend/lightgravity/verify/` | 0 | Success: no issues found in 9 source files |

均为单次 ≤ 上限、可控退出；每个探针/测试退出时清理自有 loopback server、子进程与 SDK agent。

## 4. 未测 / 遗留（不夸大）

- **真实 DeepSeek 上游端到端** cancel/pause-during-review **未跑**（本包授权产品请求 0；缺陷位于
  产品↔SDK 调用序，与上游是 DeepSeek 还是 fake 无关）。真实主链复验交**新的独立 QA**。
- 自动复核运行中由协调器 `_record_reviewer_stop` 落 `run.reviewer_cleanup` 的**真实主链**未在本包重跑
  （本地探针走 `ControlService.stop` 手动取消路径，故 `reviewer_cleanup=null` 属预期；teardown 事实本身
  已 `confirmed=true`）。需独立 QA 在真实/受控主链覆盖 `pause`、`cancel`、重启与 `reviewer_cleanup` 落盘。
- `timeout_seconds` 到时的既有超时语义未改（非本缺陷）；SDK `__aexit__` 抛错时的端到端 hold 由既有
  R2 stop-gate 保障，本包仅保证**同 loop** 与**有界**，未注入伪造异常做端到端。
- 未全量 pytest（仅相关 verify/coordinator/adapter 285 项 + 关键词 134 项），如独立 QA 需要可全量复跑。

## 5. 资源清理与预算

- 残留资源：无新增常驻进程/端口；探针 loopback server 与子进程在退出时清理
  （`ContinuousFakeUpstream.close()` / `LocalAuthProxy.stop()` / `Agent.__aexit__`，有界）。
- 凭证/密钥/请求头/请求体未进入本报告或任何文件（fake 凭证为显式非秘密占位串）。
- 预算：产品真实模型调用 **0**；未重放旧 phase6/031；API 重试 0；未改 `adapter/executor.py`（031 owner）、
  `bootstrap`/`app`/`source`/`vector`/`frontend`/`PROJECT.md`/`docs08` 等共享 owner。

## 6. 提交与后续独立 QA 最小清单

- 本包 commit：见 `git log -1 --format=%H`（branch `fix/lg022-stream`）；仅本包归属改动；
  `integrate/batch7` root 的 PROGRESS dirty 与全部旧 worktree/原始失败证据**未动**。
- 独立 QA 最小清单：
  1. 真实（或受控真 SDK）主链中，复核运行中 `pause` 与 `cancel` 在 `stop_timeout` 内真实停止 reviewer 并
     `confirmed`；`session_refs` 保留、无残留 reviewer 线程。
  2. `verifying` 下 pause 经 `waiting_user → paused` 两步落位；cancel 直接 `cancelled`；未确认时保持
     `cancelling`/`pausing` 且不释放槽。
  3. 自动复核路径 `run.reviewer_cleanup.status=done` 仅在真实 teardown 事实存在时写入；teardown 失败保持
     `pending`/unconfirmed。
  4. 无 stop 的正常成功 review 仍完整 drain 且 teardown confirmed（无回归）。
  5. 契约仍 `1.10.0`，无新增端点/字段/枚举。
