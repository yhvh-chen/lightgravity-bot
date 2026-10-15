---
title: "LG-032 阶段 B final-cohort 预注册 PLAN（2 样本 × 2 arm（A 基线 / B 双写节点独立 verify）串行 4 attempt，PM 预注册）"
doc_type: experiment-protocol
category: engineering
status: "FROZEN-BEFORE-FIRST-REAL-REQUEST"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
product_tree_note: "本 worktree 的产品树 = main@91550a9（1.11 候选已 ff 合入）。相对已独立复核的 qa/lg032-runtime-r1@26ea945 仅 contracts/constants.py + 契约测试版本元数据（1.10.0→1.11.0）+ 后续 F1/F2/两阶段 SDK 加性实现，见 §1.3。"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（独立 QA 阶段 B 实验准备 owner；不是 031 实施者；主代理仅 PM）"
---

# LG-032 阶段 B — final-cohort 预注册 PLAN

> 本文件在**任何正式真实 DeepSeek 请求之前**冻结：样本 / arm / 任务形状 / 初始 commit / 工具 / 提示模板 /
> fixture / 机器真值 / 上限 / ledger 物理路径 / 隔离边界 / 离线硬门。产物位置 `probes/lg032/FINAL-COHORT/`。
> 本包**产品真实生成 0**：只做离线预检、冻结与 harness 就绪；**不跑正式样本、不 mark 032 done**。
> 采样后只允许**追加**“偏差/失败记录”，不得事后改样本/门/提示/工具/预算/模型，不得补跑替换失败，不得增额。
>
> **旧预算草案全部作废**：`probes/lg023/cohort2|cohort3` 的 32/8、48/12 及本任务早期 48/12 草案**均不再使用**；
> 旧 023 cohort1 **45**、cohort2 **4**、cohort3 **16**、旧 022（unknown+6+8+5）、旧 031 工程 **86**（34+24+28）
> **全部保留单列，不并入本 cohort、不清零**。

## 0. 一句话问题

在**同一程序调度比较框架**下，对**同一批两个小型三节点仓库任务**，把**单实施节点（arm A）**替换为
**两个同能力写节点（arm B，程序冻结多候选池，worker 真实自主选择非预绑定节点）+ 依赖两者的独立只读验证节点**，
在**同样机器门 + 独立真实 ModelReviewer + 产品绑定 accept**下，是否出现可观测的**质量退化或收益**，以及
**执行 / 验证 / 失败尝试 / 全生命周期**的真实生成成本与耗时。

**不预设**组队省 token。arm A 与 arm B **都包含**独立的 verify 节点与独立 ModelReviewer；两者对差异**只在
“实施写节点数 1 vs 2”**，**不能**把 reviewer/verify 算作 arm B 的收益，**不能**用 agent 数量代替收益。

## 1. 冻结事实（首请求前固定）

### 1.1 环境身份（不切换）

| 项 | 值 |
|---|---|
| worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort`（项目旁，持久，**不自动删除**） |
| branch / 基点 | `qa/lg032-final-cohort` / `91550a9`（另见 §1.3） |
| Python / 环境 | 本 worktree 内 `uv sync` 生成 `.venv`（3.12），镜像冻结依赖 |
| SDK | `google-antigravity==0.1.22`（运行时断言 `installed_sdk_version()`） |
| 契约 | `1.11.0`（运行时断言 `CONTRACT_VERSION`） |
| 模型 / 端点 | `deepseek-v4-flash` @ `https://api.deepseek.com/v1`（pi 现有 env 凭证，**不切换供应商、不嵌套代理**） |
| 凭证 | 仅从进程 env 读取；**不打印 / 不落盘 / 不入 repo / 不进 prompt**；私有原件 `700/600` |
| 默认自主模式 | **保持默认 `off`**；仅 arm B 的候选池实验 switch 在 attempt 内显式开启（见 §3） |
| 产品调度容量 | **不改**：`max_parallel=1`、每 Task 一个非终止 Run、默认开关不动 |

### 1.2 样本与任务形状（两个固定小型三节点仓库 fixture）

每个样本 = **一个独立的小型 Python 仓库 fixture**，其**合法 program plan 冻结为三节点**：

| 节点 | capability | write | depends_on |
|---|---|---|---|
| `alpha` | `implementation` | true | — |
| `beta` | `implementation` | true | — |
| `verify` | `verification` | **false（只读）** | `alpha`, `beta` |

- `alpha`/`beta` 是**两个独立写节点**，终点内容互不依赖，可同时 ready；`verify` **依赖两者**、只读、
  必须读取两个上游产物的**版本化/hash 引用**。
- **arm A（程序调度基线）**：计划把两个写目标合并为**单一写节点**（`deliver` 一次写两个文件）+
  **同一个** `verify` 只读节点。arm A **不使用**候选池/自主 claim（`autonomous_claim`/池 off，旧确定性路径）。
- **arm B（新多候选池）**：计划保持 `alpha` + `beta` 两个同能力写节点 + `verify`；
  `decentralized_claim_enabled=true`、`autonomous_pool=true`，程序**冻结多候选池 grant**，
  worker 经**真实 SDK 工具 `discover_and_request_claim` 真实自主选择任一合法候选**（含**合法非首项**），
  程序在 claim 时刻**原子授权所选 node** 并绑定**所选 node 的隔离 worktree** 执行；
  **选择期 session 无写工具**（`allowed_tools=()`）。
- 两 arm **共享同一个 `implementation` Member 用于两个写候选**：同一 Member 可有多个 ready 候选，
  这正是 F1 要求的能力面；`verify` 使用**独立 `verification` Member**。
- **两 arm 相同**：fixture 初始内容树、需求文本、机器门、独立 ModelReviewer、绑定 accept 门、
  停止门、模型、SDK、契约、预算、工具集、worker 提示模板、初始 commit（A 单节点版 / B 双节点版由同一
  fixture 内容树生成，见 §1.5）、权限、`max_parallel=1`。
- **唯一自变量** = 计划实施写节点数（A=1 合并写 vs B=2 独立写）+ B 的候选池自主选择机制。
- 结论**仅**限本两小型样本、单模型、强制程序合法 plan；**不声称统计显著性**；2 样本**不作统计承诺**。

### 1.3 源锚 / 产品树范围（不重复全套 QA）

- 已存在的独立机制 QA：`qa/lg032-runtime-r1@26ea945`（R1：四门 PASS、**0 阻断**、`813 passed / 5 skipped`、
  mypy `137` files；结论 1.11 仅版本 metadata）。**本包不重复 R1 全套**。
- 本包**必须**核产品 tree 变化范围并注明；相对 `26ea945` 的**实际**产品路径变化 =
  `contracts/constants.py` 版本元数据 + `coordinator/graph.py`（候选池/两阶段 SDK 生命周期）、
  `collaboration/execution_grant.py`（`max_claims`/`lease_owner`/binding）、`adapter/execution.py`
  （`candidate_bindings`）、`api/{app,bootstrap,collaboration}.py`（grant 认证接线）、
  `settings/**`（开关）等**加性实现**（即 F1/F2/两阶段 SDK runtime 集成）。
  逐字节范围与 hash 在 REPORT 中冻结并注明。
- 若发现**产品缺陷**：只写**最小 repro** 交 PM，**不自修产品**。

### 1.4 预算与硬界（PM 最终预注册，**替代所有旧 32/8 及 48/12 草案**）

- **正式真实生成总上限 = 192**：`2 样本 × 2 arm × 1 repeat = 4 attempt`，**每 attempt 48**（`4 × 48 = 192`）。
- **每 attempt 上限 48 与 total 192 都在“转发前”硬拒**；越界 ⇒ `429` **转发前**拒绝，ledger **不增**。
- **全 stage 同 phase 唯一持久 ledger**：selector / 选择期 session / 执行期 session / verify / 独立 reviewer /
  业务返修 / 复验 / **任何失败重试** / 任何 SDK retry **全部**扣同一物理账本；**跨两次 runtime 启动不归零**；
  **损坏绝不当作 0**（fail-closed）。
- `HTTP timeout 120s`、`API/SDK retry 0`、`output <= 16000 tokens/请求`、**默认并发 1**（`max_parallel=1`，
  不改产品调度容量）、tool-call cap 32/worker、model-call cap ≤ 尝试上限。
- **每 attempt 允许至多 1 次产品现有业务修复**（bounded rework，若既有设置支持且真实发生）：
  该修复**必须在预注册中冻结**——**两 arm 次数相同**（各 ≤1/attempt）、**计入同一 48 内**；
  **不新增模型编排 agent**，不改变选择/执行/验证角色边界。
- **预算不等于必须花满**；**禁止**事后增额、改样本、改 prompt/tools/model、补跑替换失败。
- attempt 总数 4、每个**只跑一次**：不可变 attempt-id 输出目录（存在即拒绝）；任何 harness/装配/计量错误
  ⇒ **整 cohort 立即 STOP、如实报告偏差**，不改后重跑、不另建 ledger、不加额。
- 429 / 预算不足 = 该 attempt **真实失败/partial**：**如实计入**，**不重跑**、**不追加**。

### 1.5 初始 commit 与机器真值（machine truth）

- 每样本一个持久 fixture 仓库（`fixtures/<sample>/repo`），初始 commit **首请求前固定并记录**
  `git rev-parse HEAD`；文件为最小 stub（实现缺失 ⇒ 机器门初始必败）。
- A / B 两 arm 的初始内容树**逐字节相同**（由同一 fixture 内容树生成），差异**仅**在计划写节点数。
- 机器门（独立于模型，子进程隔离 cwd、清理凭证 env、有界超时）：
  逐产物**精确内容**断言 + `verify` 只读（无写入）+ `verify` 至少 2 条版本化/hash 上游交接。
  机器门脚本**不进模型上下文**。
- 独立 reviewer：真 `lightgravity.verify.review.ModelReviewer`（真 DeepSeek，独立上下文），
  `unavailable`/`failed` **不降级**；仅 `passed`/`validated_outcome=passed` 才可继续。

## 2. 必须走真实产品入口（禁止伪造状态）

正式 attempt **必须**经**实际产品**启动/协调链，**不得**直接 `Graph.dispatch` 后手写 Run/Task phase/acceptance：

1. 真 `build_runtime(...)`（或 `create_app`）装配：真 `FileStore`、真 `AntigravityExecutor`、
   真 `GraphDispatcher`、真 `CollaborationService`/grant registry、真 `VerificationService`
   （`StoreResourceStopper(session_confirmer=executor.confirm_stopped)`）、真独立 `ModelReviewer`。
2. 真 `Coordinator.start()` **CoordinatorWorkerLoop**：Task 经真实队列被 claim → 真 Run → 真 Graph dispatch
   → 真 worker SDK session（A=1 / B=2）→ 真 `RunController` phase 迁移。
3. 真 **finalization**：`_apply_outcome` → `verifying` → **异步**独立 review（`_auto_verify_async`，
   off-loop）→ 真 `VerificationService.verify_and_prepare`（真实机器检查 + 真实 stop 门 + `_open_acceptance`
   候选绑定）→ `awaiting_acceptance`。
4. 真 **human accept**：`POST /tasks/{id}/actions {action: accept, target_run_id, expected_requirements_revision}`
   绑定 `candidate_ref`/`candidate_plan_hash`/`requirements_revision`；再验证幂等与**错 target 拒绝**。
5. **不得**手工预填 `cleanup=done`、删 `session_refs`、造 `confirmed`、跳过 SDK 停门或漏掉产品收口。
   **不存在受控合法接入产品入口**时：**明确报告缺口（STOP）**，**不**用伪造状态把 harness 跑绿。

## 3. arm B 机制（F1 能力面，真实 SDK）

- 选择期（phase 1）session：专用 scratch workspace、`allowed_tools=()`（**无写工具**）、仅附受限
  `discover_and_request_claim`；程序**不**预绑定/代选节点。
- claim 时刻程序基于**已持久化 Run/Subtask 事实**重新校验所选 node 仍在合法候选集合内，
  经 fenced 租约**原子授权所选 node**（`fence=1`），随后**立即 revoke** pool grant；lease owner =
  程序冻结的 worker 实例身份。
- 执行期（phase 2）session：由**独立 SDK 会话**按**所选 node** 的隔离 git worktree / objective /
  acceptance / 上游版本化 hash / 成员权限构建；结果/manifest/状态/交接**只**归所选 node。
- 两阶段共用同一 Task/phase 预算与进程全局持久账本；两会话真实停止事实参与 stopgate（`confirm_stopped`）。

## 4. 离线硬门（先于任何正式请求；全部通过才可采样；**真实生成 0**）

使用**真 SDK 0.1.22 + 本地受控 fake 上游**（provider-substitute；dummy 凭证；**不**走 FakeExecutor 冒充 SDK）：

- **H1 fixtures**：两样本 `initial/` 机器门**必败**；`reference/` 机器门 **6/6 必过**。
- **H2 冻结合法 plan**：A=1 写节点 + verify（依赖）、B=2 依赖写节点 + verify，均过**真实 `PlanValidator`**。
- **H3 真实产品启动链**：真 `build_runtime`/`create_app` + 真 `Settings.from_env`；断言
  `configure_generation_ledger(settings.data_dir)` 生效、**startup 后物理 ledger 路径 == 期望**、
  **不可仅 env override 后又被 bootstrap 覆盖**；**worker/verifier/reviewer 全部角色指向同一个 actual
  `settings.data_dir`**；**不只测未被注入的 helper**。
- **H4 跨两次 runtime 启动 + 跨角色计数**：真 `CoordinatorWorkerLoop` + worker/reviewer 经真
  `LocalAuthProxy` 实际转发，计数落在**同一物理 `generation.jsonl`**、**跨启动累加**；显示
  **唯一物理 ledger**；**每 attempt 48 与 total 192 在转发前硬拒**；**corrupt ⇒ fail-closed**
  （`corrupt=true`、绝不当 0）。fakeRoot 与 formalRoot **分离**。
- **H5 正常产品收口**：同一 driver 下走真 `Coordinator`/`CoordinatorWorkerLoop` → 真 finish →
  **stopgate**（teardown 齐 ⇒ `awaiting_acceptance`；缺 ⇒ `unconfirmed` + held）→ **异步 review** →
  **绑定 accept** → **幂等**（重复 accept 同 request_id 幂等）→ **错 target 拒绝**。
- **H6 真实 SDK 生命周期**：真 SDK session；`context.save_dir` **启用**并落在**授权 workspace root 内**；
  会话真实停止事实入 `session_refs`；**0 真实生成**（fake 上游）。
- **H7 driver 一致性**：正式与离线预检**同一 driver 代码路径**（只换上游/基目录 + 是否发正式请求）。
- **H8 dry-run**：真 driver 在本地 fake 上游下对 A/B 两 arm 各跑通（本地假行动者/最小脚本化上游），
  物理 ledger 落**单一** formal 路径（dry 用 sibling `-dry` 根，**不污染** formal ledger）、跨 arm 累加、
  reviewer teardown confirmed、**无** per-attempt `data_dir` swap。

证据：`offline/{hard_gate,dry_run,protocol_manifest}.json`（+ 各探针原始输出）。

## 5. 持久保全（**不自动删除**）

- 所有 SDK / worktrees / SoT / 未交付 diff / 原始 stdout 持久于**项目旁**目录，**禁止 `TemporaryDirectory`**
  承载关键运行或未交付 diff，**禁止**自动清理。
- 私有原件（SDK session DB、原始证据含 model text、secrets）`700/600`，**不入 repo / 不入 prompt / 不打印
  secret/grant/headers/凭证**。
- 仓库仅提交**脱敏**摘要 / manifest / evidence / sha256。
- **只停本包自有精确进程**；保持现有 `127.0.0.1:8123` 及他人进程不动。
- **不 push / deploy / publish / upload**；不合入 main。

## 6. 记录指标（每 attempt）

完成率（是否到达**绑定 accept**）· 首轮机器门通过 · 全周期 elapsed（首个真实请求→终态）·
真实生成拆分（selector/执行/verify/reviewer/返修/失败）· input/cache/output/usage（缺失记 `unknown`，**不当 0**）·
人工介入次数 · 与 §1.4 上限对比。**未完成样本不计已交付成本**；**不用失败中位数推收益**。

## 7. 判定规则（仅用于下一轮候选；本包不判定）

- **支持默认启用候选**：B 两样本均完成，质量（机器门+reviewer+绑定 accept）**不退化**，且全生命周期成本/耗时可接受。
- **保留 off/回退**：B 未完成或质量退化或成本劣势 ⇒ 默认保持 `off`，保留开关与回退。
- **不确定**：样本 2、单模型、强制 plan ⇒ **不作统计承诺**，不因局部少调用即默认 on。

## 8. 交付物（本包 = 实验准备）

`PLAN.md`、`STATUS.md`、`REPORT.md`、`harness/**`（driver + 硬门 + fake 上游）、`fixtures/**`、
离线证据 `offline/**`、准确计数/缺陷/局限、本地精确 commit。**不跑正式样本、不 mark 032 done。**

## 9. 修订历史

- 2026-10-16（**首个正式请求之前**）：创建并冻结本 PLAN。确立 2 样本三节点 fixture、arm A/B、
  总 192 / 每 attempt 48、全 stage 单一持久 ledger、每 attempt ≤1 冻结业务修复（双方相同）、
  output ≤16000 / HTTP 120 / retry 0 / 并发 1、真实产品入口全链（start/workerloop/finalization/
  异步 review/绑定 accept）、离线硬门 H1–H8。**真实生成 0。**

## 10. 偏差与失败记录（采样后只追加）

- 暂无（**尚未发出任何正式真实请求**）。
