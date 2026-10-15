---
title: "LG-031 phase4 — PLAN（零模型定位 phase3 失败点 + 最小修复 + 单次完整真实产品闭环）"
doc_type: plan
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "faacb90"
---

# LG-031 phase4 — PLAN

owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM；**无嵌套派工/推送/部署/发布**）。
worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`；branch `fix/lg031-r3`；基点 `faacb90`
（phase3 诚实 partial 检查点，clean）。

本包是 PM 新拆的**小工作包**，包含两段：

- **§A 先零模型调用**：以既有 phase3 失败原件为唯一事实源，定位真实失败点并给出**必要最小修复**，
  离线先证（无网络、无模型、无真实请求）。
- **§B 再做一次**新的 phase4 **单次完整真实产品闭环**验证（一个固定 fixture 端到端 attempt，
  含其 worker/独立 review/失败/返修/复验所有 stage/role）。

**核心约束（PM 明确）**：
- 旧累计 **24（10 + 14）不归零**；phase4 新增**最多 16** 实际 DeepSeek 生成转发尝试；
  全局已知工程累计上限 **40**。
- **只一个**新固定 fixture 的端到端 attempt；**不得**在预算内对同一 fixture 默默重跑多次
  （每 fixture/阶段的一次性完整 attempt 是允许的；反复重跑同一 fixture 探能否过不允许）。
- 真实开始前先写本 PLAN/STATUS/成本/持久 ledger 路径；离线验证**全 stage 硬限、两 worker 权限、
  节点 objective 明确、依赖交接、真实产品 bootstrap & Graph 配置**。
- **不得**在真实调用中边猜产品接线边跑 3 轮。
- **不得**为省预算降低独立复核/机器门/停止确认/验收门。未完成如实 partial。
- 产品 runtime 仍 SDK `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`/`openai-compat`
  → loopback 认证代理 → DeepSeek；**不切厂商**；产品默认 **off**/旧确定性回退保留。
- phase3 的 **G1/G2 已修**，本包重点按 **objective 而非 slug** 找产物、工具收据交接/整合可达；
  worker 失败候选未完整**不得虚构 passed**；**不**为探 reviewer 是否过而重复调用。
- 保持 1.10 持久账本 / stopconfirmation / reviewer_cleanup / 非空 session 历史 / 反重放 /
  token / pin / 验收幂等 / 资料 1.9 等全部兼容。
- core 独立 QA 另有 0 请求 SDK 停止补证，与本包**互相隔离**。

## §A 零模型 forensics：phase3 真实失败点（判定与证据）

**事实源**（只读，原样保留，不重放）：
- `probes/lg031/phase3/evidence/run1_probe_output.json.txt`
- `probes/lg031/phase3/evidence/run2_probe_output.json.txt`
- `probes/lg031/phase3/evidence/run3_real_worker_closure.json`
- `probes/lg031/phase3/ledger/generation/generation.jsonl`（14 条 reserved，pid 1934241:4/1936962:5/1940208:5）
- `probes/lg031/phase3/{REPORT,LEDGER,STATUS}.md`

**结论（真实失败点，唯一）**：phase3 三次运行都**只跑到 produce worker 的自主 claim**，
integrate worker 从未被调度执行。三次的失败机制分两类：

| Run | 转发 | 真实终止机制 | 触发条件 |
|---|---|---|---|
| 1 | 4 | SDK `StopReason.MAX_MODEL_CALLS_EXCEEDED` | `context.budget.max_model_calls=3` 太紧，worker 未写完文件 |
| 2 | 5 | per-worker proxy `429 local auth proxy call budget exhausted` | `max_proxy_calls=6`，worker 第 4 次请求后耗尽 |
| 3 | 5 | 同上（6 次 `adapter.tool_call` 后 429） | worker 反复调用工具，6 步用尽前未到写入步 |

真实 worker 的自主调用链本身**成立**（Run2/Run3 `autonomous_claim_chain`：
`discover_and_request_claim()` → `discover_and_request_claim(node_ref=...)`，经
`GraphDispatcher._claim_for_worker`），但**每个工具调用消耗一次上游生成请求**（SDK agent loop
每 step 一次模型 turn；`_emit_chunk` 的 `adapter.tool_call` 即一次 turn 的可观测证据）。

**根因（真实、最小、非平台化）**：phase3 的 worker prompt 允许（且模型实际发生）**重复 discovery /
探索性工具调用**，导致一个 worker 在到达写文件步骤前就耗尽**两个 per-worker 上限之一**：
- SDK `BudgetConfig.max_model_calls`（`MAX_MODEL_CALLS_EXCEEDED`），或
- loopback proxy 的 `max_proxy_calls`（429）。
集成 worker 因此永不被调度；reviewer 对不完整候选**诚实 `unavailable`**（未降级门，正确）。

**必要最小修复（不改门、不平台化）**：
1. **fixture 侧**：把 worker prompt 收敛为**固定最少步**（一次 discover → 一次 claim → 一次
   写目标文件 → 结束），并按 **objective**（而非 slug）判定产物路径；这是 phase3 §3 G2 已定方向
   的落实（G2 已让投影携带 `objective`/`write`）。属 probe fixture（`probes/lg031/phase4/`），
   不改产品语义。
2. **产品侧（仅当离线证明确有必要才动，加性、最小）**：使 per-node 执行的 **SDK 模型调用上限**与
   loopback proxy **调用上限**在**同一语义**下对齐，避免出现“SDK 报 `MAX_MODEL_CALLS_EXCEEDED`
   但代理仍可转发”或“代理先 429 掩盖真实停止原因”的**两个不一致上限**。只做足以让一次最小闭环
   可达的最小改动；不新增平台层、不改冻结契约、不改既有枚举/端点。
3. 保留 `PersistentGenerationLedger` 为**唯一全局硬上限事实源**；per-worker 上限只作为**单节点
   防御**，不替代全局账本。

**不做**：不把 fixture 写死成绕过产品 planner；不手工预建 subtask；不在真实调用里试错接线；
不重复调用 reviewer 只为探能否过；不为省预算削弱独立复核/机器门/停止确认/验收门。

## §B phase4 固定 fixture（唯一，一次完整真实 attempt）

phase3 的探针把 `TwoNodePlan` **注入为 model planner**（`GraphDispatcher(planner=TwoNodePlan())`），
绕过**真实产品 `RuleBasedPlanner`**；它因此不证明产品 planner 路径。phase4 改为使用**真实产品
程序 planner**（不注入）：

- **真实 `RuleBasedPlanner`（model-free、确定性）**对含 acceptance 的 Task 产出：`deliver`
  （`implementation`，`write=True`，程序 objective = task objective）→ `verify`（`verification`，
  `write=False`，依赖 `deliver`，objective = `独立验证：<objective>`）。**两节点、真实依赖、
  真实 slug key 与程序 objective 分离**——这正是“按 objective 而非 slug 找产物”的检验。
- **2 个真实 SDK worker**：`deliver`（developer，写节点）在**独立真实 git worktree**（产品
  `GraphWorkspaceProvider(WorktreeManager)`）执行；`verify`（verifier，只读节点）按产品设计共享
  workspace（产品只对 `write` 节点 provision worktree）。两个 worker **各自**拿程序冻结的 pool grant
  + 受限 `discover_and_request_claim` 工具，**自主** discover→申请原子授权 claim；程序验证身份/能力/
  依赖/预算并原子授权 + lease/fencing。诚实记录：`verify` 非写节点，无独立 worktree（产品语义）。
- 依赖满足后，program 生成**带 hash 的版本化交接**（`<subtask>@sha256:<hex>`）传给 `verify`。
- 程序产出 Task **候选** → **真实独立 ModelReviewer**（产品 `verify.review.ModelReviewer`，经
  `ConnectionService.resolve_default("reviewer")` + `resolve_reviewer_support`）+ `validate_findings`
  机器门。**独立复核 = 真实模型 reviewer，不是 `verify` worker 自评。**
- 失败 => **有界返修（≤1 轮）** + 复验；旧证据保留；worker 不能自评 passed。
- 停止：`AntigravityExecutor.execute` 在 finally 关 session + 停 loopback 代理（权威停止事实）；
  grant 执行结束即 revoke（`active_grants()==0`）。

**硬条件 1 的诚实口径**：≥2 真实 SDK worker、依赖交接、隔离执行。产品对 `write` 节点做真实
worktree 隔离；`verify` 为只读共享（产品设计）。若“每 worker 独立 worktree”只能靠 phase3 式
注入双写 plan 才成立，则如实报告该产品语义差异，**不伪造**第二个写 worktree。

**一次性**：本包对该 fixture 只做**一次**端到端真实 attempt（含其所有 stage/role：2 worker +
reviewer + 失败/返修/复验若触发）。**不得**在同一 phase4 预算内默默重跑同一 fixture 多次。
若真实结果失败：如实记录失败与缺口，保持 partial，不重跑探过；剩余预算留作**具体失败的最小修复**
后的**唯一**一次复验（若有），并明确记录“第几次、为何、剩余多少”。

## 预算（硬限，持久、跨进程、单一事实源）

- 旧累计 **24**（原 1 + R1 3 + R2 6 + phase3 14），**不归零、不重放**。
- 本 phase4 新增**至多 16** 实际 DeepSeek 生成转发尝试；**全局已知工程累计上限 40**（24 + 16）。
- 单一事实源：`PersistentGenerationLedger`（契约 1.10 持久账本），固定路径
  `probes/lg031/phase4/ledger/generation/`（env `LIGHTGRAVITY_GENERATION_LEDGER_DIR`），
  **转发前持久预留**，跨 worker/reviewer/session/**进程重启**读同一账本；损坏**绝不当 0**。
- 真实调用前**先离线**验证账本跨进程/重启可靠（子进程读写一致、损坏 `raise`）。
- 请求参数：每请求输出 ≤**12000** tokens；单 HTTP ≤**120s**；并发 ≤**2**；SDK/API retry **0**。
- usage 未知记 `unknown`，**不当 0**；不打印/落盘 key/secret/grant/token。

## 离线硬门（真实调用前必须全绿）

1. 全 stage 硬限：持久账本跨进程/重启不归零、损坏不当 0；每请求/超时/并发/retry 参数固定。
2. 两 worker 权限：body 永不认证（仅 `X-LG-Execution-Grant`）；越权/预算/失效确定拒绝；
   程序只授权该 worker 被排度的节点（`node_not_scheduled_for_worker`）。
3. 节点 objective 明确：discovery 投影携带程序拥有的 `objective`/`write`，worker 据 objective
   判定产物（G2 回归）。
4. 依赖交接：program 产出带 hash 的版本化 handoff（64 hex）。
5. 真实产品 bootstrap & Graph 配置：`api/bootstrap` 读 `decentralized_claim_enabled` →
   `autonomous_claim=True` + `ExecutionGrantRegistry`；关闭/缺省走旧确定性路径（G1 回归）。
6. 产品路径 2-worker 闭环（确定性 sim）：独立 worktree、原子授权 fence=1、脱敏 receipt、
   带 hash 交接、`active_grants()==0`。

## 验收门（真实硬条件，全满足才可 done 候选）

真实硬条件 1–7（见 phase3 PLAN §1 同义）+ 每 worker 的工具/隔离/交接/候选 review/停止证据 +
输入与源码版本 + 旧 24 + 新实际数 + 成本（未知单列）+ 剩余门。缺任一 ⇒ 诚实 partial，
不写 done，不偷偷开新账本归零，不重跑探过。

## 非目标

- 不造通用调度平台/常驻模型编排 agent；不开 SDK 无限委派；不新增供应商、不改默认 enable。
- 不改 `sources/vectors/frontend`；不碰 022 worktree 与 core 独立 QA 的 0 请求补证；不碰主目录集成者。
- 不 push/部署/发布；不扩旧 24；不重跑已成功旧探针；不降低任何既有断言/门。
- 不替 LG-032 预注册样本/预算/成功标准；不制造 032↔031 依赖循环。
- 不为省预算降低独立复核/机器门/停止确认/验收门。
