# SDK 取消语义调查包 — REPORT

- Owner：独立 SDK 取消语义调查/QA owner（非产品返修者、非集成者；独立于前 QA owner）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`），
  开工 HEAD `0a88ab8`（clean）。产品代码**只读**，未做任何产品修改；无嵌套派工/推送/部署/发布。
- 依据：AGENTS.md / agent.md、`backlog/tasks/LG-022.md` 原验收、`docs/06-roadmap.md` 版本门、
  `docs/08-interface-contract.md`（契约 `1.10.0`）§8.1/§9、`qa/lg022-r2/{REPORT,SUPPLEMENT,STATUS}.md`、
  前 harness `qa/lg022-r2/harness/review_cancel_sdk_proof.py` 与其实际产物。
- 预算：wall 900s；round ≤160；noncache ≤220k；idle 180；开发 retry 0。
  **本包真实产品/DeepSeek 生成请求 0**；所有探针单次 ≤45s 可控总时限，退出清自有 loopback/子进程。
- SDK：`google-antigravity==0.1.22`（安装版，固定；未升级/切换）。

## 0. 结论一句话（先落盘）

**SDK 的取消契约是可用且被证实的**：`Conversation.cancel()` 能立即取消一个进行中的真实 SDK 流式 turn
（`is_idle` 置位、SDK 自身抛 `AntigravityCancelledError`、`agent.__aexit__` 正常返回）。
**但产品的 reviewer 停止路径没有把 stop 请求接到 SDK 的取消入口**：它只在 `agent.chat()`/`send()` 阶段轮询
`stop_event`，而 `send()` 立即返回、真正的流式迭代（`async for chunk in response.chunks`）完全在轮询范围之外，
产品路径**无任何** `Conversation.cancel()` 调用。因此复核运行中的 `cancel`/`pause` **永远无法停止真实 reviewer**：
表现为等待满 `stop_timeout` 后诚实返回 `unconfirmed`（有效、非伪造），但复核对**真实 SDK 取消不可达**。
这是 R2 返修（REFIX-R2）未覆盖的**产品生命周期接线缺陷**（D2 家族），构成对 LG-022「暂停取消」验收条件的
**重要缺陷**（非“使用限制”）。

## 1. 只读事实：SDK 0.1.22 公开取消/idle API（源码）

| API | 位置 | 语义 |
|---|---|---|
| `Conversation.cancel()` | `conversation/conversation.py:345` | 转发 `Connection.cancel()`；**请求**取消，不等待 |
| `Conversation.wait_for_idle()` | `conversation/conversation.py:350` | 阻塞至 connection idle |
| `Conversation.is_idle` | `conversation/conversation.py:291` | 透传 `connection.is_idle` |
| `Conversation.disconnect()` | `conversation/conversation.py:371` | 关闭传输、释放资源 |
| `Connection.cancel()` | `connections/connection.py:578` | 抽象默认：pass |
| `LocalConnection.cancel()` | `connections/local/local_connection.py:632` | 置 `_client_cancelled=True` 并发送 `InputEvent(halt_request=True)`；**不等待 idle** |
| `LocalConnection.is_idle` | `.../local_connection.py:414` | `processor.is_idle.is_set()` |
| `LocalConnection.wait_for_idle()` | `.../local_connection.py:537` | `await processor.is_idle.wait()` 并清 step_queue |
| `LocalConnection.disconnect()` | `.../local_connection.py:1578` | cancel background tasks、关 WS/stdin、等 harness 进程退出（超时 terminate→kill） |
| `event_processor` idle | `.../event_processor.py:545,549,560,963–981` | `reset_for_turn` clear；`STATE_RUNNING` clear；`STATE_FULLY_IDLE`/`STATE_CANCELLED` set |
| `Agent.__aexit__` | `agent.py:229` | AsyncExitStack aclose → strategy/disconnect |
| `Agent.conversation` | `agent.py:399` | 返回真实 `Conversation`（可调 cancel/idle） |

**SDK 契约**：公开取消入口是 `Conversation.cancel()`（= `Connection.cancel()`），它是**异步请求**，
真实停止须观察 `is_idle`/`wait_for_idle()`，或 `agent.__aexit__`（`disconnect`）真实返回。
`task.cancel()` **不是** SDK 契约入口（前包旧调试用 `task.cancel()` 属误区）。

## 2. P1：最小真 SDK 取消顺序已复现证明（`evidence/sdk-min-cancel3.json`）

探针：`sdk_min_cancel_probe3.py`（真 `Agent` + 真 `LocalAuthProxy` + 本地 fake SSE 上游；
`real_model_calls: 0`；`timeout 45`）。**保持 drain 任务存活**调用 `conversation.cancel()`，排除
“本地取消 drain 任务本身导致 idle”的混淆。

| 组 | `is_idle`（流中） | 6s 内流是否结束 | SDK 自身异常 | `is_idle`（后） | `agent.__aexit__` |
|---|---|---|---|---|---|
| 控制（不 cancel） | false | **否**（流保持开启） | — | false | ok |
| **cancel** | false | **是（0.05s）** | `AntigravityCancelledError: "The request was cancelled by the client."` | **true** | ok（0.035s） |

⇒ **`cancel_order_proven: true`**。SDK 取消顺序真实、可靠：cancel → SDK 自身流终止 → `is_idle` → aexit 返回。

## 3. P2/P3：产品接线缺陷（`evidence/decisive-product-vs-sdk-cancel.json`、`product-stop-lingering.json`）

探针驱动**真实产品**装配：`ModelReviewer` → `run_review_turn`（真 `Agent`+`LocalAuthProxy`，
上游为本地 fake SSE）→ 真 `ReviewLifecycle` → 真 `ControlService.stop`，Run 有非空 `session_refs`。
`real_model_calls: 0`，`timeout 45`。

### 3.1 A：当前产品停止路径（流式进行中请求 cancel）

| 观测 | 值 |
|---|---|
| `control` | `state=unconfirmed`, `confirmed=false`, `phase=cancelling` |
| `control_stop_elapsed_s` | **5.017**（等满 `stop_timeout`） |
| `resource_stop_report_at_stop` | **`{}`（无 teardown 事实）** |
| `lifecycle_still_reviewing_at_stop` | **true** |
| `upstream_saw_client_gone_at_stop` | false |
| `run.state` / `task.phase` | `verifying` / `cancelling`（停在中间态） |
| `session_refs_preserved` | **true** |
| stop 后 **6s** | `reviewing=true`、`future` 未完成、仍无 teardown 事实、phase 仍 `cancelling` |

⇒ 产品 cancel **没有让真实 reviewer 停止**；`unconfirmed` 是产品对自己“没停成”的**诚实**报告（产品未见伪造 fail），
但根因是停止路径未触达 SDK 取消入口。

### 3.2 B：修复方向（探针内演示，不改产品源码）

在流式迭代中**并发轮询 stop event**（`wait_for(anext, 0.05)`）并在置位时调用 SDK 文档取消入口
`conversation.cancel()` + `wait_for_idle()`：turn **0.013s 停止**，`is_idle=true`，
`resource_stop_report.confirmed=true`（`agent_closed=true`+`proxy_stopped=true`）。

⇒ **最小修复方向确有可实施且有效**：把 stop 轮询纳入流式阶段并显式调用 SDK cancel。

## 4. 根因（精确到文件/行/调用序列）

位置：`backend/lightgravity/verify/review.py`，`run_review_turn._turn()`（约 910–925 行）与
`_await_with_stop()`（829–855 行）。

```python
chat = asyncio.ensure_future(
    asyncio.wait_for(agent.chat(prompt), timeout=timeout_seconds)
)
response = await _await_with_stop(chat, stop_event)   # ← 只守护 send() 阶段
chunks = []
async for chunk in response.chunks:                   # ← 真正的流式阶段，stop 不在轮询范围
    chunks.append(chunk)
```

根因链：
1. `Agent.chat()` → `Conversation.chat()`（`conversation.py:258`）先 `await self.send(prompt)` 再**立即返回
   lazy `ChatResponse(receive_chunks())`**。故 `chat` future 在**流式开始前几乎立即完成**。
2. `_await_with_stop` 的 `while True: if stop_event.is_set(): chat.cancel()` 只在 `chat` 仍 pending 时才有意义；
   `chat` 已完成 → `await wait_for(shield(chat), 0.1)` 立即返回 → **`stop_event` 在流式阶段从不被检查**。
3. 产品路径中**没有任何** `conversation.cancel()` / `connection.cancel()` / `wait_for_idle()`；
   `_await_with_stop` 的 `chat.cancel()` 即便触发，也只会取消 `send` 阶段的 task，**不会**取消已开始的 SDK turn。
4. SDK turn 只有在**上游自然结束**（模型正常完成）或 `timeout_seconds`（默认 30s reviewer）到时才结束；
   期间 `ReviewLifecycle.request_stop_async` 只能等满 `stop_timeout`（默认 5s）→ `unconfirmed`，
   `run_review_turn` 的 `finally`（`resource_stop_report`）**未执行**。
5. 结果：复核运行中的 `cancel`/`pause` 对真实 reviewer **不可达**；`cancelling`/`pausing` 停在中间态，
   直到 reviewer 自然结束。

## 5. 最小可实施修复建议（交 PM/返修者；QA 不自修）

目标：复核运行中 `pause`/`cancel` 能在 `stop_timeout` 内让真实 SDK turn 真实停止并产出 teardown 事实。
建议（最小、局部于 `verify/review.py::run_review_turn`，不新增端点/字段/供应商）：

1. **在流式迭代中承载 stop**：把 `_turn()` 里 `async for chunk in response.chunks` 改为每步
   `await asyncio.wait_for(anext, 0.05)` 的循环，并在循环内检查 `stop_event`（与探针 B 同构）。
2. **停止时调用 SDK 文档入口**：`await agent.conversation.cancel()` 后 `await agent.conversation.wait_for_idle()`
   （有界 `wait_for`），再退出 `_turn()`；让 `finally` 正常执行并写 `resource_stop_report.confirmed=true`。
3. **兜底**：`finally` 已有 `agent.__aexit__`/`proxy.stop()` 的诚实记录；建议 `__aexit__` 也加有界
   `wait_for`，避免 stop 路径在极端情况再次长时间不返回。
4. 保持现有语义不变：`ReviewLifecycle` 未确认时继续 `unconfirmed`+保留槽/refs；只有真实 teardown 后才确认
   `cancelled`/`paused`。**不新增状态、不伪造 done。**

最小 repro（本包可复跑，均 0 真实模型调用）：
```
timeout 45 .venv/bin/python qa/lg022-r2/sdk-cancel-investigation/sdk_min_cancel_probe3.py \
    qa/lg022-r2/sdk-cancel-investigation/evidence/sdk-min-cancel3.json
timeout 45 .venv/bin/python qa/lg022-r2/sdk-cancel-investigation/decisive_product_vs_sdk_cancel.py \
    qa/lg022-r2/sdk-cancel-investigation/evidence/decisive-product-vs-sdk-cancel.json
timeout 45 .venv/bin/python qa/lg022-r2/sdk-cancel-investigation/product_stop_lingering.py \
    qa/lg022-r2/sdk-cancel-investigation/evidence/product-stop-lingering.json
```

## 6. 真实 / 替身分类（诚实标注）

| 证据 | 类别 | 说明 |
|---|---|---|
| `evidence/sdk-min-cancel3.json` | **real-SDK（provider-substitute）** | 真 `google-antigravity==0.1.22` `Agent`+真 `LocalAuthProxy`；上游为本地 fake SSE，**非 DeepSeek**，0 真实模型调用 |
| `evidence/decisive-product-vs-sdk-cancel.json` | **real-SDK + real-product-lifecycle（provider-substitute）** | 真产品 `ModelReviewer`/`run_review_turn`/`ReviewLifecycle`/`ControlService`；模型侧 fake 上游 |
| `evidence/product-stop-lingering.json` | 同上 | 证明 stop 后 6s reviewer 仍在运行 |
| `evidence/sdk-min-cancel{,2}.json` | real-SDK 早期迭代 | 探针演进留档（v1/v2），不覆盖 |

- **无**任何被验收的产品行为用“普通 asyncio Event 假 reviewer 冒充实际 SDK 取消”作为结论依据；
  本包停止证据全部来自**真 SDK 对象**（`Conversation`/`Agent`）与**真产品生命周期**。
- `session_refs` 为真实形态 ref（探针 seed），未冒充真实 DeepSeek session；但 `Conversation`/`Agent` 是真实的。

## 7. 独立裁定（基于来源，据 LG-022 原验收）

来源：
- `backlog/tasks/LG-022.md` 验收条件：「覆盖……**暂停继续、取消**和验收返修」「覆盖……不确定副作用」；
  「重要缺陷修复重验才完成」。
- `docs/06-roadmap.md` §2：D 阶段含“暂停取消、重启检查、返修、并行整合”。
- `docs/08` §9「独立复核生命周期与停确认（1.8.0，LG-022 R1）」：复核运行中的 `pause`/`cancel` **必须对 reviewer
  有真实 stop/释放确认**；未确认计 `unknown`（不写终止态、不释放槽）。`PROJECT.md`：`cancel` 只有观察到
  SDK 会话 idle 才返回 `confirmed=true`。

裁定：
1. **是重要缺陷，必须修复**。产品声称并在契约中要求“复核运行中 pause/cancel 对 reviewer 有真实 stop 确认”，
   但当前实现**无法让真实 reviewer 停止**：SDK 提供可用取消入口，产品停止路径**未调用**它，
   因而该验收条件中的“取消/暂停复核中的真实 reviewer”路径**实际不可达**（只能停在 `cancelling` 直到 reviewer 自然结束）。
   这属于“重要缺陷未修复重验”，**阻断 LG-022 最终 `done`**。
2. **在现有 SDK 范围内可修**：SDK 0.1.22 已提供 `Conversation.cancel()`/`wait_for_idle()`，且探针 B 证明
   在流式阶段并发轮询 stop + 调用 `cancel()` 可在毫秒级真实停止并产出确认 teardown。修复是**局部接线**，
   不新增 SDK/版本/端点/字段/供应商。
3. **不是“产品行为已满足契约但有使用限制”**：产品当前 `unconfirmed` 的“诚实保留”是**正确的安全兜底**，
   但“停止真实 reviewer”这一契约能力本身缺失，不能降格为使用限制。产品机制中“未确认不伪 done”这部分**已正确**，
   缺陷在**未接入 SDK 取消入口**。
4. **前包挂起的重新定性**：前包 `review_cancel_sdk_proof.py` 的挂起**不是**“QA harness 未跑成 + SDK 行为 unknown”，
   而是**产品接线缺陷的真实现象**：产品 stop 路径不触达 SDK cancel。前包 C2（unconfirmed 保留）仍为有效产品机制证据。

## 8. 未测 / 遗留（不夸大）

- 真实 DeepSeek 上游下的端到端 cancel-during-review **未跑**（本包 0 真实模型调用，授权不变；fake 上游已足够
  复现接线缺陷，因为缺陷位于产品↔SDK 调用序，与上游是 DeepSeek 还是 fake 无关）。
- 修复后需由**新的独立 QA** 复验（含真实主链 pause/cancel during review），本包不自修自判。
- 历史统一账本缺口仍属前包 scope（另包处理），不混入本包。

## 9. 提交与资源

- 新增（仅本目录）：`PLAN.md`、`STATUS.md`、`REPORT.md`、`fake_upstream.py`、`sdk_min_cancel_probe{,2,3}.py`、
  `product_stop_probe.py`、`product_stop_lingering.py`、`decisive_product_vs_sdk_cancel.py`、
  `evidence/{sdk-min-cancel,sdk-min-cancel2,sdk-min-cancel3,product-stop,product-stop-lingering,decisive-product-vs-sdk-cancel}.json`。
- 未改产品代码、未改历史证据/账本、未动 `docs/`、未动 8123/031/其他 owner。
- 残留资源：本包无新增常驻进程/端口；所有探针 loopback server 与子进程在进程退出时清理
  （`timeout 45` 有界；`FakeUpstream.close()`/`LocalAuthProxy.stop()`/`Agent.__aexit__`）。
- 凭证/密钥/grant/请求头/请求体未进入本报告或任何文件（fake 凭证为显式非秘密占位串）。
