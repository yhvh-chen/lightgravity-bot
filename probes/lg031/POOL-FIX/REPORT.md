---
title: "LG-031 POOL-FIX — REPORT（多候选自主发现/请求领取能力补齐）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031"
branch: "fix/lg031-pool"
base: "834b262"
---

# LG-031 POOL-FIX — REPORT

- Owner：`agent:pi-lg031`（pi + env DeepSeek；**主代理仅 PM**；无嵌套派工/推送/部署/发布）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-pool`（branch `fix/lg031-pool`，基点 `834b262`，开工 clean）。
- 输入：LG-032 阶段 A `qa/lg032/quality/{REPORT,FINDINGS}.md`（F1）、`probes/lg031/**` phase3/phase4/SALVAGE、
  当前 `coordinator/graph.py`/`collaboration/**`/`adapter/**` 源。
- **产品真实 DeepSeek 生成请求 = 0**。SDK-real 分类：**provider-substitute**（真 `FileStore` + 真 `flock` +
  真多进程 + 真 git worktree + 进程内 fake worker）；**无 SDK、无网络、无模型**。

## 0. 一句话结论

按用户原目标**补齐**了 F1 要求的**多候选自主发现/请求领取**能力：程序不再把 worker 预绑定到唯一
`scheduled_node`，而是冻结一个**合法 ready 候选池**；worker 自己**选择**任一候选并申请领取，程序在 claim
时刻基于持久事实**重新校验**并**原子授权所选 node**，随后绑定所选 node 的隔离 workspace / 上游版本化 hash
上下文 / 成员配置，结果/manifest/状态/交接均归属**所选 node**。并发竞争同 node 仅一 winner，loser 可领取剩余
合法候选；无 claim 不写控制状态。**默认 off / 旧确定性路径与旧单节点自主路径完全保留。** 因**真实自双 worker
SDK 端到端与真实 SDK 按所选 node 绑定隔离 workspace 的两阶段适配未实现/未测**，LG-031 **保持 `in-progress`**，
不因机制齐就写 done，也为后续 PM 单独冻结真实证明保留清晰入口。

## 1. 开工核对与基线（真实）

- `git status` 开工 clean；`fix/lg031-pool` HEAD = `834b262`（`batch11`）。
- 全 Git worktree 列表、旧分支（`dev/lg031`、`fix/lg031-r1/r2/r3`）、旧 dirty、`/tmp/*experiment*`**全部保留**；
  未 reset / clean / 覆盖 / 重复 pick；本包未改 `api/collaboration.py`（F2 owner）、`sources/vectors/frontend/
  评估 harness` 与别包工作区。
- 契约 docs/08 = `1.10.0`；SDK `google-antigravity==0.1.22`；自主路径默认 off；默认并行容量未改（`max_parallel` 默认 1）。

## 2. 根因（QA 可观察，无争议）

- 计划由程序 `RuleBasedPlanner` 生成；`_materialize_subtasks` 预绑定 `assignee_member_ref`。
- 旧自主路径在 `_execute_node` 内对**当前程序调度的唯一 node** 铸 pool grant；`_claim_for_worker` 对
  `node_ref != node.subtask_id` 一律 `node_not_scheduled_for_worker`（`coordinator/graph.py`）。
- 结果：两个同能力节点同时 ready 时发现投影为 2（QA `discovery-multicandidate.json`），但每 worker 真实可领取
  集合被程序限定为 1（`autonomy-boundary.json`），`node-preselection.json` 复现拒绝。**是程序先选 node。**

## 3. 变更（准确路径）

| 文件 | 变更 |
|---|---|
| `backend/lightgravity/collaboration/execution_grant.py` | `ExecutionGrant` 加性 `max_claims`（pool grant claim 预约上界，`None` 为旧无界）；`grant_claim` 据此有界；受限 claim 工具授权成功时加性回传所选 node 的**非秘密 binding**（仍不含 token） |
| `backend/lightgravity/adapter/execution.py` | `ExecuteRequest` 加性 `candidate_bindings`（程序多候选只读元数据；普通/单节点路径为空） |
| `backend/lightgravity/coordinator/graph.py` | 新增候选池 worker slot 调度：`_pool_enabled`/`_legal_candidates`/`_candidate_binding`/`_run_graph_pool`/`_execute_pool_slot`/`_build_pool_request`/`_mint_pool_grant_multi`/`_pool_claim_tools_for`/`_claim_for_worker_pool`/`_live_candidate_refs`/`_release_collaboration_lease`；构造加性 `autonomous_pool` |
| `backend/lightgravity/api/bootstrap.py` | `decentralized_claim_enabled` 开启时启用 `autonomous_pool=True`（仅装配开关；未改其它 api 源） |
| `tests/collaboration/test_lg031_pool_selection.py` | 新增 9 项（见 §5） |
| `probes/lg031/POOL-FIX/**` | PLAN/STATUS/REPORT + 探针 + 证据 + fixtures/.gitignore |
| `docs/08-interface-contract.md` | §6.5 加性实现说明（**无版本/字段/端点/枚举/迁移方向变化**） |
| `backlog/tasks/LG-031.md` | POOL-FIX 记录 |

**程序控制边界（照用户目标）**：执行 / 机器验证 / 独立 review / 返修 / 候选整合 / 停止 / 验收仍由程序控制；
worker 只能请求，不能直接改状态 / 预算 / 验收；无常驻模型编排 agent / 组织平台。

## 4. 选择池 / 授权 / 状态 / 隔离 / 预算 / 停止边界（实现口径）

1. **候选池**：程序按 Run `subtask_refs`、`state ∈ {pending,ready,repairing}`、成员能力覆盖、`depends_on`
   全 `passed`、预算/容量、单 writer 逐轮计算合法集合；只读投影（node_ref/capability/objective/write/binding），
   不含 token。冻结在多候选 pool grant 的 `authorized_node_refs`。
2. **授权**：worker 经受限 `discover_and_request_claim(node_ref=...)` 请求；`_claim_for_worker_pool` 在 claim
   时刻**重新基于 Store 持久事实**校验所选 node 仍在合法集合（越 Task/Run/能力/write/scope、终态、他 owner
   持有、非池内 → 确定拒绝），经 fenced 租约权威原子授权（恰好一个 winner），身份由程序推导。
3. **状态**：未 claim 前候选保持 pending，不写控制状态；授权后仅**所选 node** 经 `RunController` 进入
   `running`，结果/manifest/状态/交接全部归属所选 node。
4. **隔离**：write 候选的独立 worktree 在调度前按 node key 预 provision；绑定所选 node 的 workspace/member/
   上游版本化 hash 交接；文件 SoT 仍为真实 worktree/Store。
5. **预算**：选择与执行同一 Task/phase 预算（`context.budget` 与进程全局 generation 账本）；pool grant claim
   预约次数有界（`max_claims = len(pool)`），无独立常驻 selector 预算。
6. **停止**：执行停止后 revoke node/pool grant 并释放租约；过期 ≠ 停止；stale fence 写回拒绝；未知副作用不自动
   重放；有界尝试耗尽以 `claim_required` 诚实非成功。

## 5. 验证（真实退出码）

- `uv run mypy` → **Success, 137 files**。
- `uv run pytest tests/collaboration/test_lg031_pool_selection.py -q -p no:randomly` → **9 passed**：
  - `test_worker_selects_non_first_candidate_and_result_lands_on_it`：两同能力 write 候选，worker 选**非首项**
    beta；pool=2，结果/evidence 归 beta，alpha 独立执行；grant 全 revoke。
  - `test_pool_selection_uses_isolated_worktree_per_selected_node`：所选 node 在**自己的真实 worktree**，≠ base repo。
  - `test_default_off_has_no_pool_and_no_pool_tools`：无协作/关闭时池惰性，`candidate_bindings=()`、无工具。
  - `test_worker_that_never_claims_writes_nothing`：无 claim → 无 node passed，`owner=None`/`fence=0`，run 非成功。
  - `test_claim_outside_pool_is_refused`：越池 → `node_not_in_candidate_pool`，不写。
  - `test_claim_selects_non_first_node_and_binds_it`：选第二候选 → granted、binding 指向它，未选 node 不变。
  - `test_race_two_owners_same_node_only_one_winner`：两 owner 竞争同 node → 一 winner，`fence=1`，loser 领取剩余。
  - `test_unknown_or_stale_selection_is_refused`：未知/终态 → 拒绝。
  - `test_two_member_pools_run_in_parallel_without_writer_collision`：两成员各自独立 write pool 在 `max_parallel=2`
    下并行，各用独立隔离 worktree，无 writer 碰撞，grant 全 revoke。
- `uv run pytest tests/collaboration tests/coordinator tests/adapter tests/settings tests/api -q` → **409 passed**。
- `uv run pytest -q`（全量 backend）→ **799 passed, 5 skipped**。
- 探针 `probes/lg031/POOL-FIX/probe_pool_selection.py`（真 4 进程 flock barrier，真 FileStore）→ 证据
  `probes/lg031/POOL-FIX/evidence/pool-selection.json`：
  - `discoverable_at_dispatch` = 2；
  - `non_first_selection`：选**非首项** beta（`is_first_candidate=false`），`granted=true`，`binding_key=beta`，
    `leaks_token=false`；
  - `out_of_pool_refusal` = `node_not_in_candidate_pool`；
  - `race_on_same_node`：4 进程竞争同 node → **granted_count=1 / 3×`held_by_other` / final_fence=1**；
  - `loser_reclaims_remaining`：loser 领取剩余合法候选 `granted`；
  - `no_claim_no_write`：`owner=null / fence=0 / state=pending`。

## 6. 复现命令（本地，真实退出码）

```bash
uv sync --frozen
uv run --frozen mypy
uv run --frozen pytest tests/collaboration/test_lg031_pool_selection.py -q -p no:randomly
uv run --frozen pytest tests/collaboration tests/coordinator tests/adapter tests/settings tests/api -q
rm -f probes/lg031/POOL-FIX/evidence/pool-selection.json
uv run --frozen python probes/lg031/POOL-FIX/probe_pool_selection.py \
  --work probes/lg031/POOL-FIX/fixtures/work \
  --out probes/lg031/POOL-FIX/evidence/pool-selection.json
```

## 7. 未测 / 明确限制（不伪称）

- **产品真实 DeepSeek 生成 0**；本包 SDK-real = **provider-substitute**（真 Store/worktree/多进程 fake worker），
  **不冒充**真实 LLM 自主选择。
- **真实 SDK 双 worker 端到端未做**：池内选择后的**真实 SDK 会话按所选 node 绑定隔离 workspace**的两阶段适配
  （选择会话 → 绑定执行会话，共享同一 Task/phase 预算）**未实现**；当前程序侧归属正确，但真实 SDK 写路径仍以
  会话创建的 workspace 为准。此为大缺口，交后续 PM 单独冻结的真实证明 phase。
- **F2（HTTP claim/lease 端点 owner 身份）** 属 `api/collaboration.py` 的 F2 owner 范围，本包**未触碰**；如需接口
  变化，由串行 integrator 处理，本包不抢 owner。
- 完整 checkpoint skip 未实现；独立集中 QA（LG-032）与全生命周期成本对比未做。
- 源码 Git worktree 不是 OS 安全沙箱这一真实限制保留，未冒充更强隔离。
- 旧 34/40 真实工程请求的失败/成功受限链证据**全部保留**，未重放/未归零；本包**新增真实调用 0**。

## 8. 下一真实验证最小方案（交 PM 冻结）

1. 冻结**一次**真实双 worker 最小样本：一个 Run、两个同 capability ready 节点、两真实 SDK worker 各在候选池中
   自主选择（其中一个选非首项），经真实 `GraphDispatcher._claim_for_worker_pool` 授权并写各自隔离 worktree。
2. 在该 phase 实现**两阶段 SDK 生命周期**（选择会话 → 绑定所选 node workspace 的执行会话，同一持久 Task/phase
   预算与全局 generation 硬上限），验证结果/manifest/状态/交接归正确 node，且仅一个 winner/竞争 loser 有界。
3. 统一 hard counter（不重置、不新增独立 selector 预算）；usage unknown 不当 0；真实停止确认后才回收租约。
4. 未完成前 **LG-031 保持 `in-progress`**；不把 provider-substitute 机制证据当真实通过。
