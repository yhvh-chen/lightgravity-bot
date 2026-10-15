---
title: "LG-031 POOL-FIX（F1 多候选自主发现/领取）实施 PLAN"
doc_type: plan
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031"
branch: "fix/lg031-pool"
base: "834b262"
---

# LG-031 POOL-FIX — 实施 PLAN

owner：`agent:pi-lg031`（pi + env DeepSeek；主代理只 PM；无嵌套派工/推送/部署/发布）。
worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-pool`（branch `fix/lg031-pool`，基点 `834b262`）。
产品真实 DeepSeek 生成请求：**0**（本包离线机制实现 + 真 Store/worktree 验证）。

## 目标（照用户原目标，不以改名降能力）

按 LG-032 阶段 A 的 F1：当前自主路径是「程序把 worker 预绑定到**唯一** scheduled_node，
worker 只在自身节点上完成一次程序授权的领取」。要求补齐：**程序按 Run 授权 / worker 能力 /
权限 / 预算 / 容量提供合法 ready 候选集合，worker 真实选择其中任一并申请 claim，
程序原子授权后绑定所选 node / 隔离 workspace / 上游版本化 hash 上下文，执行 / 机器验证 /
独立 review / 返修 / 候选整合 / 停止 / 验收仍由程序控制。**

约束：
- 不能在另处偷偷预选唯一 node；不能只改拒绝条件却把 B 结果写到原 A 节点。
- 计划生成与规则调度保留；无常驻模型编排 agent / 组织平台。
- 默认 off / 旧确定性路径回退保留；默认并行容量不擅改（`max_parallel` 默认 1）。
- 程序仍是唯一控制权威：worker 只能请求，不能直接改状态 / 预算 / 验收。
- 独立 worktree 与文件 SoT 不能被缓存 / 模型记忆替代；租约回收真实停止后才发生。

## 选择池 / 授权 / 状态 / 隔离 / 预算 / 停止边界（先记录，后实现）

### 1. 候选池（selection pool）
- 程序在派发一个 **worker slot**（member，非某个预绑定 node）时计算合法候选集合：
  - 同一 Run（`run.subtask_refs`）；
  - `state` 可领取（`CLAIMABLE_SUBTASK_STATES`，或 `running` 且租约过期）；
  - 能力匹配该 worker member 的 capabilities（`capability ∈ member.capabilities`）；
  - 依赖已就绪（`depends_on` 全部 `passed`）—— 复用 `DiscoveryService` 的同一判定；
  - 预算 / 容量允许（Task/Run 剩余预算 > 0；未超 `max_parallel`）；
  - 单 writer / write scope：同一 workspace 已有 writer 持有的 write 节点不进入池。
- 候选集合由**程序**计算并冻结；worker 只能在其授权集合内选择。
- 池是**只读投影**；worker 拿到的是候选元数据（node_ref/capability/objective/write），不含 token。

### 2. 授权（authorization）
- worker 通过受限 `discover_and_request_claim(node_ref=X)` **请求**领取 X。
- `_claim_for_worker` 在 claim 时刻**重新计算**合法池（防止 TOCTOU：worker 选择后依赖/预算/竞争可能变化），
  要求 `X ∈ 合法池` 且原子 reserve（`ExecutionGrantRegistry.grant_claim` 的 pool grant 一次性/renewable 有界）。
- 通过 `CollaborationService.request_claim` 走 **fenced lease authority** 原子授予（恰好一个 winner）；
  loser 得到确定性 `claim_refused`/`held_by_other`，可重新发现剩余合法候选。
- 授权身份由**程序**推导（`owner=self._owner`），不依赖 worker 自报身份；body owner 永远不作认证。
- 不预设唯一 node：程序授权的是 worker **所选**且仍在合法池内的 node。

### 3. 状态（state）
- worker 未 claim 前：候选 node 保持 `ready`，不写控制状态。
- claim 成功后：仅**所选 node** 经 `RunController.transition_subtask` 进入 `running`（程序写入）。
- 结果 / manifest / handoff / 状态 / 交接全部归属**所选 node**；绝不写到程序原预调度节点之外。
- worker 不能直接改状态 / 预算 / 验收；所有写入经程序 controller。

### 4. 隔离（isolation）
- 每个 write 候选 node 的独立 worktree 在调度前由 `isolate_write_nodes` **预 provision**（按 node key）。
- worker 选定 X 后，ExecuteRequest 使用 X 的隔离 workspace（`workspace_for_node(run, X.key)`）与 X 的
  `node.member`（能力/工具/连接 pin）与 X 的上游版本化 hash 交接（`encode_handoffs`）。
- 文件 SoT 仍是真实 worktree / Store，不缓存、不由模型记忆替代。

### 5. 预算（budget）
- 选择与执行**同一 Task/phase 持久预算**：`context.budget`（含 `max_collab_requests` / `max_workers`）
  与进程全局 generation 账本；不新增独立常驻 selector/orchestrator 预算。
- 每次 claim 是**有界**的（pool grant 的 `claims_granted` 上限 = 候选数或冻结上限），尝试次数有界。

### 6. 停止（stop）
- 只有**真实停止确认后**才回收：executor `result.stop_confirmed` 或 finally 关 session/停代理；
- 执行停止即 `revoke_grant`（node grant），pool grant 在执行结束时 revoke；
- 租约过期 ≠ 停止：`reclaim_expired` 对有副作用节点写 `waiting_user` + `recovery_required` reason，
  不自动重放；
- stale fence 写回拒绝（`StaleLease`），unknown 副作用不自动重放。

## 实施步骤

1. **PLAN/STATUS**（本文件 + STATUS.md）。
2. `execution_grant.py`：pool grant 支持**多候选**授权集合（`authorized_node_refs` 已存在，补充
   `candidate_bindings` 只读元数据 + 「选择后一次性 node 绑定」语义）；保留 pool→node 升级；
   失败/未知保持拒绝。
3. `coordinator/graph.py`：新增 **pool slot dispatch** —— 程序按 member 计算合法候选集合，
   mint 多候选 pool grant，worker 选择后由 `_claim_for_worker` 校验「所选 ∈ 合法池」并原子授权，
   绑定所选 node 的 workspace/upstream/member，执行结果归属所选 node。
   保留旧 `autonomous_claim` 单预绑定路径作为**兼容**（默认仍是确定性路径）。
4. 测试（`tests/collaboration/test_lg031_pool_selection.py`）：
   - 同 capability 两 ready 候选，worker 申请**非首项/非预绑定项** → 合法授权并真正执行所选 node，
     结果/manifest/状态/交接归正确 node；
   - 并发两 worker 竞争同 node → 仅一 winner，loser 可重新发现剩余合法候选且有界；
   - 无 claim 不能写；越 TaskRun/capability/write/scope 拒绝；
   - stale fence / expiry≠stop / unknown 反重放；
   - worker 只能请求，不能改状态/预算/验收。
5. 离线探针（`probes/lg031/POOL-FIX/`）：真 FileStore + 真 flock 多进程（provider-substitute），
   记录失败与证据；不重跑旧 fixture，不新增真实模型调用。
6. 持久 REPORT，再精确本地 commit。

## 不做 / 未测声明

- 产品真实 DeepSeek 生成 **0**；本包机制齐后，LG-031 **保持 in-progress**，
  待后续 PM 单独冻结真实双 worker 证明。
- 真实 SDK 双 worker 端到端由后续 PM 冻结的真实证明 phase 覆盖；本包用
  provider-substitute（真 Store + 真 worktree + 进程内/多进程 fake worker）离线机制验证，
  **不冒充**真实 LLM 自主选择。
- 不写 api 文件（`api/collaboration.py` 归 F2 owner；`api/app.py` 亦归 F2 owner）；
  如必须接口变化在 REPORT 提出供串行 integrator 处理。
