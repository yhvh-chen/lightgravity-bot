# LG-032 阶段 A — 机制/语义发现与证据索引

- 更新：2026-10-16
- owner：独立 QA（LG-032 阶段 A）
- 基线：`62e96ed`（branch `qa/lg032`）
- 产品真实生成请求：0（本包全程）。所有探针为 **provider-substitute**（真 FileStore + 真 flock + 进程内 worker 仿真的离线机制证据，无 SDK/网络/模型）。

## 证据文件

| 证据 | 路径 | 说明 |
|---|---|---|
| 自主语义边界（产品路径） | `evidence/autonomy-boundary.json` | 真 `RuleBasedPlanner` + `GraphDispatcher(autonomous_claim=True)`；记录每 worker 的 discovery 集合、节点绑定、pool grant、claim |
| 多候选 vs 预选 | `evidence/discovery-multicandidate.json` | 两个同能力节点同时 ready 时的 discovery 投影数 + 程序侧 `node_not_scheduled_for_worker` guard |
| 现有局部测试 | `local-pytest.txt` | `pytest tests/collaboration -q` = 77 passed |

## 发现（阶段 A 汇总，详见 REPORT.md）

### F1 — 自主 claim 实为“程序预选唯一节点后挂工具”，非真正多候选自主选择（语义边界，IMPORTANT）

- **契约原文**：`docs/contracts/LG-028-preparation.md` §2.1 规定可发现候选来源为 Run 已校验计划中 `state=ready`/可立即就绪、能力匹配、依赖就绪、预算充足的 Subtask 集合（按 Member 过滤的授权投影），**并未要求程序把一个 worker 预绑定到唯一节点**；§2.4 要求授权不依赖 worker 自报身份。
- **实现**：
  - 计划由**程序** `RuleBasedPlanner` 确定性生成（`plan_source=rules`），节点 `capability` → `role` → member 由 recruiter 程序映射；`_materialize_subtasks` 把每个 Subtask 的 `assignee_member_ref` 预绑定为该 member（`coordinator/graph.py:489-541`）。
  - 自主路径在 `_execute_node` 内对**当前程序调度的 node** `_mint_pool_grant`，pool grant 的 `authorized_node_refs=discover(run_id, owner)`（当时可见集合）。
  - worker 工具 `discover_and_request_claim` 的 claim 回调是 `GraphDispatcher._claim_for_worker`，其中 `if node_ref != node.subtask_id: return {granted: False, reason: "node_not_scheduled_for_worker"}`（`coordinator/graph.py:1081-1101`）。
- **可观察证据**：`evidence/autonomy-boundary.json` 中每个 worker 的 `discovery_count=1`（仅其自身预绑定节点可见，因另一依赖节点尚未/已 passed），`active_grants_before=1`。`evidence/discovery-multicandidate.json` 证明当两个同能力节点**同时** ready 时投影确为 2 个候选（投影本身是多候选的），但产品自主 handler 对“非本 worker 被排度节点”的 claim 一律 `node_not_scheduled_for_worker` 拒绝。
- **判定**：**部分符合**。机制上保留了「worker 自己提出 claim、程序原子授权、fence、发现投影只读、默认关闭」等去中心化要素；但**调度权威未从程序转移**——worker 实际可领取集合在其执行那一刻被程序限定为**唯一预选节点**，不存在“在多个就绪候选中自主选择”的行为。按 LG-031 验收“真实运行覆盖至少两个 worker”，其两个 worker 是**程序顺序调度 + 各自领取自己预绑定节点**，不是竞争同一候选池。
- **重要性与返修建议**：见 REPORT.md（不夸大：不要求组织平台/多租户；仅指出与 LG-028 §2.1/§2.4 语义的差距，及 docs/08 §4.3 “按 Member 过滤”的可发现范围未真正用于多候选选择）。**QA 不自修、不自判 done**。

### F2 — HTTP claim/lease 端点仍接受请求体 `owner`，未接程序认证执行身份（边界，IMPORTANT）

- **契约原文**：LG-028 §2.4「授权结果必须不依赖 worker 自报身份：`owner` 由程序按已注册 Member 推导；worker 不能指定任意 owner」；docs/08 §4.3 note「worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 `owner`」。
- **实现**：`api/collaboration.py` 的 `discover`/`claim`/`renew`/`release` 均从请求体取 `owner`，**未**使用 `ctx.worker_identity`；只有 `POST /runs/{run_id}/collab_requests`（LG-030 peer）使用了 `worker_identity` 接缝（default-deny）。
- **可观察证据**：源码路径 `backend/lightgravity/api/collaboration.py:88-152`（discover/claim/renew/release 无 `worker_identity`）对比 `:155-181`（collab 使用）。LG-029 任务正文自身亦记录「端点 `owner` 暂由请求体提供」为未装配缺口。
- **判定**：**不符合** LG-028 §2.4 的“授权不依赖 worker 自报身份”对**HTTP 领取端点**的要求（程序内部 graph 路径不经此端点，故产品运行时 graph 路径未受影响；但冻结端点语义的独立验收不满足）。
- **返修建议**：见 REPORT.md。

### F3 — `reclaim_expired` 对有副作用节点写 `waiting_user` 而非 `recovery_required`（语义偏差，IMPORTANT/待核）

- **契约原文**：docs/08 §6.3「对有副作用的节点不得自动重跑，须进入 `recovery_required`」；LG-028 §2.5「对 `write=true` 或未知副作用的节点，回收不得触发自动重跑，须进入 `recovery_required`」。
- **实现**：`collaboration/lease.py::reclaim_expired` 对有副作用节点将 `state` 设为 `"waiting_user"` 并写 `fail_reason="recovery_required: ..."`（`lease.py:400-420`），**不是** Run/Subtask 的 `recovery_required` 语义状态。
- **可观察证据**：源码路径 + 需局部复现确认（本阶段调查中）。`Subtask.state` 枚举**无** `recovery_required`（docs/08 §6.3），`Run.state` 有。故 Subtask 层面写入 `waiting_user` + fail_reason 可能是**符合枚举的诚实停车**，但需与 §6.2 的 Run 级 `recovery_required` 迁移口径核对。
- **判定**：**待核**（见 REPORT.md 的复现/澄清项）。

> 注：F1/F2/F3 的最终门判定与本包「不合格项需返修后复验（另派，QA 不自修）」的流程见 REPORT.md。
