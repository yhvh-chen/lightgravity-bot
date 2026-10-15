# LG-022 首版端到端与故障独立集中 QA — 报告

- 任务：LG-022「执行首版端到端与故障验收」首版集中 QA 门。
- 执行者：agent:pi-lg022（独立于 LG-017/018/019/021/027 实施者与集成者；主代理只 PM）。
- Worktree/branch：`/home/yhvh/code/lightgravity-bot-worktrees/lg022` / `qa/lg022`。
- 候选 HEAD（未变）：`bf7851cdb14e97f7c32815e1811a83ebdb89e2cb`（`claim: LG-022…`），产品树 = main `7c565fd` 整合候选。
- 产品运行时：`google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`(openai-compat) + 产品 loopback 认证 proxy → 固定 upstream `https://api.deepseek.com/v1`；开发用 pi + 既有 env DeepSeek。
- 授权：本地实施/验收；**未 push / deploy / publish**；未 `reset`/`clean`；未改产品代码（`git status` 仅 `?? probes/lg022/`）。
- 计划：[QA-PLAN.md](QA-PLAN.md)（先固定后执行）。状态：[STATUS.md](STATUS.md)。

## 0. 判定

**本门 `fail`（阻断，不 done）。**

首版最小真实产品路径**无法闭环**：真实独立 `ModelReviewer` 在真实协调器运行路径下**必然报 `unavailable`**（缺陷 D1），因此真实候选永远进不了 `awaiting_acceptance`，人工 accept 不可达。另有结构性缺陷 **D2**：独立复核在运行中同步阻塞事件循环，期间状态查询/暂停/取消无法被服务。两者都与用户点名的“独立 ModelReviewer 生命周期边界”直接相关。LG-017/021 的旧证据（含 1 次真实 reviewer 单轮探针 `passed`）**不能**覆盖真实装配/运行路径，未证明本门目标；本报告不继承其自评。

未消除前不得 done。缺陷由主代理另派返修，QA 不自修、不自判通过。

## 1. 真实调用预算与成本（诚实）

- 硬上限：产品真实 DeepSeek 生成请求 **≤10**；SDK 重试 **0**；单 HTTP timeout 120s；并发 ≤2。
- 实际：本 QA 逐请求记账，**真实 DeepSeek 生成请求次数 = unknown（有界）**。
  - stage1 首跑（`/tmp/lg022-qa-s1`）：Subtask 1 触发上游，命中 `max_proxy_calls=4` 预算停止（`HTTP 429 local auth proxy call budget exhausted`）→ 该次尝试**至少 4 次**上游尝试（含 SDK 内部多轮），未成功交付。
  - stage1 重跑（`/tmp/lg022-qa-s1c`）：2 个 Subtask 均 `passed`，各自真实 DeepSeek 调用（次数产品未导出，记 unknown）。
  - 真实独立 reviewer 在真实路径**0 次成功网络调用**（D1 在 `asyncio.run` 处即失败，早于网络）。
  - 故障/生命周期阶段（stage2/3）使用**受控替身**，真实模型调用 **0**。
- 产品未暴露总调用计数器（与 LG-027 “unknown 非零”一致）；本 QA 以 `executor.model_calls_made` + proxy `call_count` + 上游错误为界，**不宣称**已验证精确上界或受 10 次硬界实测控制。
- 墙钟：单检查 ≤120s；长过程短轮询。多次 2–3 分钟级脚本运行，均在预算内。

## 2. 成功项（真实 / 替身逐项标清）

### 2.1 真实 SDK 写链（真实 DeepSeek，真实 HTTP）

证据：`probes/lg022/evidence/stage1-real-path.json` + `/tmp/lg022-qa-s1c`（保留）。

| 检查 | 结果 | 证据 |
|---|---|---|
| 真实 loopback HTTP 服务（uvicorn + 真实产品 app）健康 | PASS | `health_ok code=200` |
| Settings 受控写：worker 默认受保护、无 token 敏感写拒绝 | PASS | `protected_write_requires_token` 401 |
| worker/reviewer/coordinator 默认正确 pin | PASS | `worker_default_pinned`、`reviewer_default_pinned` |
| 执行就绪（真实 executor 装配） | PASS | `execution_ready reasons=[]` |
| **真实独立 reviewer 装配为 model**（预置配置启动） | PASS | `reviewer_wired_model`：`{reviewer: model, credential_configured: true}` |
| 真实任务 → 队列 → 真实 worker → 真实产物 | PASS | 2 Subtask `passed`；`/tmp/lg022-qa-s1c/ws/ws1/out/result.txt` = `LG022_OK`（真实写入） |
| 状态查询不等待执行 | PASS | `status_query_immediate elapsed=0.027s` |
| 运行 `state: verifying`（未伪造 done） | PASS | `RUN.md state: verifying` |
| 敏感凭证不回显 Settings | PASS | `no_secret_echo_settings`（key 未出现） |

> `light_qa_no_task_created` 在 stage1 首跑的 422 是**本 QA payload 误带 `conversation_id`**（该端点 `extra=forbid`）导致，非产品缺陷；stage3 已用正确 payload 复验通过（见 2.2）。

### 2.2 替身故障/生命周期覆盖（受控替身，真实 HTTP + 真实持久文件）

证据：`probes/lg022/evidence/stage2-lifecycle.json`、`stage3-faults.json`。**明确标 `substitute`**，不代表真实 SDK review 链通过。

| 检查 | 结果 | 证据 |
|---|---|---|
| 轻问答不建 Task | PASS | stage3 `light_question_no_task tasks=0`；`duplicate_global_message_idempotent` |
| 重复全局消息幂等（同 `message_id` 同结果） | PASS | 两次响应逐字节一致，`kind=direct` |
| 重复控制幂等（同 `request_id` 不二次停止/不开新 Run） | PASS | `duplicate_control_idempotent` 两次 200 `confirmed` 一致 |
| 暂停确认写入 `paused` | PASS | stage3 `task_reaches_awaiting_acceptance_substitute phase=paused` |
| SSE 游标重连不重复 | PASS | `sse_cursor_replay_no_duplicate replayed=11 unique=11`（真实 `id:` 游标重放，无重复 seq） |
| accept 绑定准确候选 Run | PASS | stage2 `accept_bound_exact_run candidate_ref=run_…` |
| accept 目标错配被拒 | PASS | stage2 `accept_wrong_target_rejected` 409 `illegal_transition` |
| 重复 accept 幂等（同 request/target 同结果，不作用新候选） | PASS | stage1 `duplicate_accept_idempotent`（在真实 accept 若可达时；本次因 D1 未达真实 accept） |
| pin 漂移路径可复现 | PASS（受限） | stage3 `pin_drift_recorded`（仅路径，未断言下一 Subtask 报 `config_invalid`，标部分未测） |

## 3. 失败项（真实缺陷，阻断）

### D1（阻断）真实独立 reviewer 在真实运行路径必然 `unavailable`

- 现象：真实产品 `build_runtime` 装配 `ModelReviewer`（`reviewer_wired_model` PASS），真实 worker 交付后进入复核，`ReworkOrchestrator.process` → `ModelReviewer.review` → `run_review_turn` 报错，`review_completed outcome=unavailable`，任务被置 `waiting_user`，真实候选**永远进不了 `awaiting_acceptance`**，accept 不可达。
- 根因：`backend/lightgravity/verify/review.py::run_review_turn` 是**同步**函数，内部 `asyncio.run(_turn())`（约 line 831）。真实协调器在**已运行的事件循环**（`Coordinator._run_loop` → `_auto_verify`）内调用它，`asyncio.run` 抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`；异常被 `except Exception` 捕获并归类为 `unavailable`（诚实不假 pass，但等于真实复核永不可用）。
- 最小复现：`probes/lg022/harness/repro_d1_asyncio_run.py` → `evidence/repro-d1.json`：
  `"raised": "RuntimeError: asyncio.run() cannot be called from a running event loop"`，`defect_d1_manifest: true`。真实运行日志同步出现 `RuntimeWarning: coroutine 'run_review_turn.<locals>._turn' was never awaited`（review.py:701）。
- 对照：`coordinator/dialogue.py::make_sync_responder` **已**用独立线程事件循环处理同一问题；reviewer 路径未采用，属独立缺口。
- 为何 LG-017 探针 `passed` 却漏掉：`probes/lg017/review_real_probe.py` 从**同步**入口调用 `run_review_turn`（无运行循环），未走真实协调器调用路径。**这正说明“1 次 reviewer 成功只证明最小功能”**。
- 影响：首版“独立 SDK reviewer 检查最终候选”验收条件在真实路径**不成立**。**阻断本门。**
- 复验建议：改为在独立线程/事件循环（或 async 端口）运行 reviewer turn，并新增**从真实协调器调用路径**触发的真实模型复核回归；同时把 reviewer 的 `last_error` 写入 `review_completed` 事件（当前事件无 `reason` 字段，只报 `unavailable`，可诊断性不足）。

### D2（阻断，与 D1 同域）复核运行中阻塞事件循环，状态/控制不可服务

- 现象（受控替身，真实 HTTP）：`stage2-lifecycle.json` `control_served_during_review` **FAIL**，`status_latency=12.123s`（整个复核期间状态查询被阻塞），pause 只能在复核结束后以 `not_ready` 被处理。
- 根因：`ModelReviewer.review` 是**同步**调用，在协调器 async worker 循环里直接执行；D1 修复后真实网络复核同样会长时间阻塞该事件循环，期间 `GET /tasks`、pause/cancel 等全部无法被服务。
- 用户点名的边界：**“暂停/取消/重启须包含独立 ModelReviewer 正在运行阶段，并确认 reviewer 实际停止/释放”**——当前在复核期间**根本无法接受暂停/取消请求**，也无 reviewer 停止/释放确认；调度器的 `cancel` 只跟踪执行器 `_inflight`（worker 执行），**不跟踪 review 阶段**。stage1 真实运行中 `_inflight` 在复核时为空。
- 证据类型：受控替身（真实同步阻塞行为，与产品 `review()` 同步签名一致）；真实 reviewer 因 D1 未进入长网络阶段，故本项**未以真实模型复现**，如实标 `substitute`，但结构缺陷可从代码与真实 `RuntimeWarning` 佐证。
- 影响：复核期间无响应；pause/cancel 无法在复核阶段生效，更谈不上确认 reviewer 停止。**阻断本门**（属用户明确要求的边界）。
- 复验建议：将 reviewer 移出事件循环并纳入可取消/可观测的生命周期；对“review 运行中”的 pause/cancel 返回明确 pending/暂停评审语义，并提供 reviewer 停止/释放确认。

### D3（非阻断，诚实性）

- 现象（真实）：成功交付的 Run（`state: verifying`，“all 2 subtask(s) passed”）被写入 `fail_reason: all 2 subtask(s) passed; candidate handed to verification`（`/tmp/lg022-qa-s1c/data/runs/*/RUN.md`）。
- 根因：`Coordinator._apply_outcome`：`if outcome.failure_message or outcome.summary: run_extra["fail_reason"] = …`，对**成功** Run 也写 `fail_reason`。
- 影响：界面/看板可能把成功 Run 误呈失败原因；非本门唯一阻断项，但属真实诚实性缺陷，应随返修一并修。
- 复验建议：仅在实际失败时写 `fail_reason`，成功改用非失败字段。

## 4. 未验证 / 阻断（如实）

1. **真实独立 SDK review 链闭环**：被 D1 阻断，未取得真实证据。**阻断本门。**
2. **复核运行中的 pause/cancel/restart 与 reviewer 停止确认**：仅受控替身覆盖，真实模型路径未复现（被 D1 间接阻断）。**阻断本门**（用户明确边界）。
3. **两个并行节点 + 真实 worktree 隔离 + 最终整合候选**：LG-018 有独立交付与真实 Git 证据（`probes/lg018/reports/LG-018-report.md`），但**本 QA 未在候选 `bf7851c` 上重跑真实并行 worktree 整合 + 独立 review 链**；因 D1 真实 review 链不可达，本门该项**未完成**。真实 Git/受控替身可覆盖故障，但“至少真实 SDK 写 + 独立 review 链”中的 review 链缺失。
4. **重启恢复不重放未知副作用**：本 QA 未对候选做真实进程重启+恢复扫描；沿用 LG-016 交付证据但未在候选复验，标未测。
5. **Task 总预算跨 Run**：有代码路径（`max_repair_rounds`/`max_review_rounds` 终身账本）与 LG-017 局部测试，但真实返修 + 预算停止未在本门真实复现（受 D1 阻断，返修永远因 `unavailable` 停），标未测。
6. **真实浏览器端到端**：本 QA 未重跑完整 UI 矩阵（沿用 LG-021 授权增量）；LG-021 亦为 `in-progress`，其 31+26 项在其候选上通过，**不等于**本候选真实浏览器业务路径。
7. **凭证不进浏览器持久状态/导出**：沿用 LG-027 与 LG-021 增量证据，未在本候选重取浏览器样本。
8. **真实调用精确计数**：产品未暴露，记 `unknown`；未宣称受 10 次硬界实测控制。

## 5. 结论与建议

- **不 done。** 首版门因 D1（真实独立 reviewer 不可用）与 D2（复核阻塞且不可暂停/取消）**阻断**；D3 为伴随诚实性缺陷。
- 建议主代理另派返修（同一 owner 串行）：
  1. 修 D1：reviewer turn 改线程/async 运行，脱离运行中的事件循环；补真实协调器路径的真实模型复核回归；`review_completed` 事件补 `reason`。
  2. 修 D2：reviewer 生命周期可取消/可观测，review 期间 pause/cancel 有明确语义并确认 reviewer 停止/释放。
  3. 修 D3：成功 Run 不写 `fail_reason`。
- 返修后复验重点（本门重开）：真实协调器路径下的完整链 `Settings(reviewer 默认) → 写任务 → 真实 worker → 真实 ModelReviewer(只读候选) → awaiting_acceptance → accept 绑定版本`，以及**复核运行中** pause/cancel/restart 的确认与释放。成功样本需绑定新 commit + 真实调用计数（unknown 亦须如实）。
- 本报告仅覆盖候选 `bf7851c`；**不宣称**扩展版本 LG-032/LG-040 通过。

## 6. 证据索引

- 计划：`probes/lg022/QA-PLAN.md`；状态：`probes/lg022/STATUS.md`
- 真实路径：`probes/lg022/harness/stage1_real_path.py` → `probes/lg022/evidence/stage1-real-path.json`（另有 `/tmp/lg022-qa-s1c` 真实写入/产物保留）
- D1 最小复现：`probes/lg022/harness/repro_d1_asyncio_run.py` → `probes/lg022/evidence/repro-d1.json`
- 生命周期替身：`probes/lg022/harness/stage2_lifecycle.py` → `probes/lg022/evidence/stage2-lifecycle.json`
- 故障替身：`probes/lg022/harness/stage3_faults.py` → `probes/lg022/evidence/stage3-faults.json`
