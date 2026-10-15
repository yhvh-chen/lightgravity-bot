---
title: "LG-031 RUNTIME/AUTH INTEGRATION — REPORT"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "唯一串行 runtime/API/SDK 集成与返修 owner"
branch: "integrate/lg031-runtime"
base: "834b262"
---

# LG-031 RUNTIME/AUTH INTEGRATION — REPORT

- Owner：唯一串行 runtime/API/SDK 集成与返修 owner（pi + env DeepSeek；**主代理仅 PM**；无嵌套派工/推送/部署/发布）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-runtime`（branch `integrate/lg031-runtime`，基点 `834b262`，开工 clean）。
- 输入：F1 `fix/lg031-pool@f2741bb`（POOL-FIX REPORT/PLAN/源码）、F2 `fix/lg029-auth@388f6fa`（PAUSE-HANDOFF/PLAN/源码）、
  `qa/lg032/quality/{REPORT,FINDINGS,STATUS}.md`（F1/F2/F3）、docs06/08、LG-029/031/032。
- **产品真实 DeepSeek/生成请求 = 0**。探针 SDK-real 分类：**真 SDK 0.1.22 + 本地受控 fake 上游（provider-substitute）**；
  **无网络、无 DeepSeek、无真实模型**；worker 决策由本地 fake upstream 脚本化。

## 0. 一句话结论

把 F1 的候选池机制与 F2 的程序 grant 认证**串行整合**，并补齐**受控两阶段 SDK 生命周期**与**程序冻结 lease owner 一致性**：
真实 SDK 的选择会话在**无写权限**的 scratch workspace 中选节点并通过受限工具申请 claim，程序原子授权**所选 node** 后，
**另一个**真实 SDK 执行会话按所选 node 的隔离 workspace/objective/上游 hash/权限运行；结果只归所选 node。
F2 四端点（`discoverable`/`claim_requests`/`lease/renew`/`lease/release`）改为从程序冻结 grant 推导 principal/scope/fence，
body `owner` 降为兼容可选、非授权，未认证 default-deny 不落盘。两真实 worker 竞争同 node 恰好一 winner。
**本包不合入 main**，**不自判版本 pass**；LG-031 真条件（正式真实 provider 验证）留后续 PM 独立预算。

## 1. 开工核对（真实，保全）

- `main@834b262` clean，无 dirty；F1 `fix/lg031-pool@f2741bb` clean；F2 `fix/lg029-auth@388f6fa` clean。
- 全部旧 worktree/分支/dirty/`/tmp/*experiment*` **保留**；未 reset/clean/覆盖/重复 pick；未复制 `.env`/headers/grant secrets。
- 真实进程：LG023 cohort3 runtime（pid 2114867）、本包 runtime（pid 2129239）、8123 uvicorn（pid 3320750）——均不触碰。
- 新建全新持久 worktree `lg031-runtime` / branch `integrate/lg031-runtime`，`--no-ff` 合 F1（无冲突）、`--no-ff` 合 F2
  （`api/bootstrap.py` 自动合并）。合并后由本唯一 owner 串行解决一致性。

## 2. 变更（准确路径）

| 文件 | 变更 |
|---|---|
| `backend/lightgravity/collaboration/execution_grant.py` | `ExecutionGrant` 加性字段 `lease_owner`（程序冻结租约权威；`effective_lease_owner` = `lease_owner or member_ref`）；`mint(lease_owner=None)`；`to_dict` 加性 |
| `backend/lightgravity/coordinator/graph.py` | **两阶段池生命周期**：`_execute_pool_slot` 拆为 phase1 选择会话 → 程序原子授权 → phase2 执行会话（`_build_request(所选 node)`）；新增 `_build_selection_request`（`allowed_tools=()`、选择 scratch workspace）、`_selection_workspace`、`_run_executor_task`、`_execution_stopped`；池 claim/release 用程序冻结 `self._owner` 并铸 `lease_owner=self._owner` 的 node grant |
| `backend/lightgravity/api/collaboration.py` | F2 四端点 default-deny + 程序 grant principal/scope/fence；`_grant_owner` 取 `effective_lease_owner`；body `owner` 兼容校验（`identity_mismatch`）；body `capability` 恒不授权 |
| `backend/lightgravity/api/{app,context,bootstrap}.py` | F2 `worker_grant` 接缝（`ApiContext.worker_grant` ← `resolve_request_grant`），与既有 `worker_identity` 并存 |
| `tests/collaboration/test_lg031_pool_selection.py` | `PoolWorkerSim` 重写为两阶段；新增 `test_two_phase_sdk_lifecycle_selects_then_binds_selected_node`；断言更新 |
| `tests/collaboration/test_api_collaboration.py` | `_mint(lease_owner=...)` 闭合签名缺口；新增 `test_frozen_lease_owner_distinct_from_member_is_authoritative`、`test_claim_body_capability_cannot_widen_scope` |
| `probes/lg031/RUNTIME-AUTH-INTEGRATION/**` | PLAN/STATUS/REPORT + 探针 + evidence |
| `docs/08-interface-contract.md` | §4.3 执行身份边界 + F2 实现对齐；§6.5 两阶段/lease owner 加性实现说明；§13 加性实现说明行（**无版本变化**） |

**程序控制边界**：执行/机器验证/独立 review/返修/整合/停止/验收仍由程序控制；worker 只请求；无常驻 selector/orchestrator；
默认 off / 旧确定性路径与默认 `max_parallel=1` 不变。

## 3. 两阶段 SDK 生命周期（实现口径）

1. **候选池**（F1 保留）：程序按 Run 授权/成员能力/依赖就绪/预算/容量/单 writer 计算合法 ready 候选集合，
   冻结为多候选 **pool grant**（`authorized_node_refs` + 有界 `max_claims`）。
2. **阶段 1（选择会话）**：真实 SDK 会话，workspace = 专用选择 scratch（`<save_dir>/.lg-pool-selection/<run>/<slot>`），
   `allowed_tools=()`（**不下发任何成员写工具**）、objective 标注 PHASE 1、仅附受限 `discover_and_request_claim`。
   worker 自己选择候选（探针选**非首项** beta）并申请 claim。**选择前无写权限、不产生产物。**
3. **原子授权**：`_claim_for_worker_pool` 在 claim 时刻基于**持久化** Run/Subtask 事实重校验（越 Task/Run、越能力、
   越 write/scope、终态、他 owner、非池内 → 确定拒绝），经 fenced 租约权威原子授权**所选 node**，铸 node grant
   （`member_ref`=认证身份，`lease_owner`=worker 实例身份，`fence`=授权 fence）。选中后立即 revoke pool grant。
4. **阶段 2（执行会话）**：**另一个**真实 SDK 会话，由 `_build_request(所选 node)` 构建：所选 node 的**隔离 git worktree**、
   objective/acceptance、上游版本化 hash 交接、该 node 的成员权限与 connection pin。结果/manifest/状态/交接**只归所选 node**。
5. **预算/停止**：两阶段共用同一 `context.budget` 与**同一进程全局持久生成账本**（同一 executor 实例 + bootstrap 注入账本）；
   两会话的真实停止事实均经 `confirm_stopped` 确认并参与 stopgate；未确认保持 held。
6. **禁止常驻编排**：选择会话按需在 slot 执行内创建，无独立常驻 selector/orchestrator。

## 4. F2 执行身份边界（实现口径）

- 四端点从 `ApiContext.worker_grant`（bootstrap 接 `X-LG-Execution-Grant`）解析程序冻结 grant，仅从中推导：
  principal（`member_ref` → `effective_lease_owner`）、Run scope（`grant.run_id == path run_id`）、
  可发现/领取节点（`authorized_node_refs` 子集）、fence（renew/release 只许 `grant.fence`）。
- body `owner` 兼容可选：存在且 != 冻结 owner ⇒ `claim_refused`/`identity_mismatch`，**不落盘**；
  无 resolver / 无效 grant ⇒ `claim_refused`/`unauthenticated`；**未配置/未认证 default-deny 且不写业务状态**。
- body `capability`/`lease_seconds` 仅提示；**不授予** capability/write/scope（capability 由程序 grant + discovery 决定）。
- **lease owner 一致性**：程序冻结 worker 实例身份（`self._owner`），`member_ref` 仍为认证身份；两真实 worker 竞争同 node
  恰好一 winner（loser `held_by_other`）；HTTP renew/release 解析同一冻结 owner。
- peer（LG-030）身份接缝与默认拒绝保持**不变**。

## 5. 验证（真实退出码）

- `uv run --frozen mypy` → **Success, no issues found in 137 source files**。
- `uv run --frozen pytest -q -p no:randomly` → **811 passed, 5 skipped**（全量 backend）。
- 定向：`tests/collaboration` → **99 passed**；`tests/collaboration tests/api tests/coordinator tests/adapter` → **373+ passed**。
- 回归：`probes/lg031/POOL-FIX/probe_pool_selection.py`（真 4 进程 flock）→ `granted_count=1` / 3×`held_by_other` /
  `final_fence=1`；非首项选择 `granted`、`leaks_token=false`。

### 5.1 真 SDK 0.1.22 + 本地受控 fake 上游端到端探针（provider-substitute）

`probes/lg031/RUNTIME-AUTH-INTEGRATION/probe_two_phase_sdk.py` → `evidence/two-phase-sdk.json`（单次 ~2.6s，远低于 90s 有界）：

- **真 SDK 版本**：`0.1.22`（`installed_sdk_version()`）。
- **场景 1（两阶段选择 → 领取 → 绑定执行）**：
  - 真实 SDK 会话：selection ×2（每 slot 1 个，discover→claim→finish）+ execution ×2（write→finish）= `sdk_session_count=4`；
  - phase1 请求 `tool_names` 无写工具、仅 `discover_and_request_claim`（选择前无写权限）；
  - worker 选**非首项** beta（`beta_selected_non_first=true`）；
  - 两候选 alpha/beta 各自**通过**并在**各自隔离 worktree**写出各自产物，
    `writer_collision_into_wrong_node=false`（B 结果不可能写成 A）；artifact sha256 记录；
  - `stop_confirmation.confirmed=true`、`sessions_stopped=4/4`、`proxy_stopped=true`、`active_grants=[]`。
- **场景 2（两真实 worker 竞争同 node）**：两个真实 SDK 选择会话（不同 worker 实例 owner，同一 member）竞争同一 node →
  `granted_count=1`、`final_fence=1`、loser `held_by_other`、`one_winner=true`、`owner_consistent=true`、
  回执脱敏（`redacted=true`）。
- **清楚标注 provider-substitute**：`provider=local-fake-openai-sse`、`provider_substitute=true`、`product_real_generation=0`；
  **不使用 FakeExecutor 冒充 SDK**——探针走真实 `AntigravityExecutor` + `LocalAuthProxy` + 真实 SDK `Agent` 会话。

## 6. 未测 / 明确限制（不伪称）

- **正式真实 DeepSeek provider 端到端验证未做**：本包探针使用本地受控 fake 上游（provider-substitute），
  worker 的“选择/写哪个文件”由 fake upstream 脚本化；**不冒充**真实 DeepSeek 模型自主选择。正式验证留后续 PM 独立预算。
- 完整 checkpoint skip 仍未实现；LG-032 阶段 B 全生命周期成本对照仍暂停。
- 真实 Git worktree 不是 OS 安全沙箱这一既有真实限制保留。
- **本包不自判版本 pass**；LG-031 真条件（正式真实 provider 验证）未齐保持 `in-progress`；
  LG-029 F2 自条件（程序 grant 认证 + default-deny + 不落盘）已齐，可 `done` 待 **LG-032 独立复验**。
- 旧 F1/F2/LG-031 累计 34/40 与 LG-023 旧 49（旧累计 93）真实工程成本**全部保留单列**；本包新增产品真实生成 **0**。

## 7. 成本 / 独立列（不归零）

- 本包**产品真实生成 0**；探针为离线本地 fake 上游（无网络/无模型/无费用）。
- 旧 F1/F2 工程请求、LG-031 34/40、LG-023 旧 49 均**不重放、不归零、另列**。

## 8. 后续真实 proof 最小方案（交 PM 冻结）

1. 冻结**一次**真实 DeepSeek 双 worker 最小样本：同 capability 两个 ready 写节点、两真实 SDK worker
   各自自主在候选池中选择（其中一个选非首项）、经真实 `GraphDispatcher._claim_for_worker_pool` 授权并写各自隔离 worktree。
2. 复用本包两阶段生命周期（选择会话 → 原子授权 → 执行会话），同一持久 Task/phase 预算与全局 generation 硬上限；
   验证结果/manifest/状态/交接归正确 node，且竞争 loser 有界。
3. 统一硬计数（不重置、不新增独立 selector 预算）；usage unknown 不当 0；真实停止确认后才回收租约。
4. 未完成前 LG-031 保持 `in-progress`；不把 provider-substitute 机制证据当真实通过。

## 9. 复现命令

```bash
uv run --frozen mypy
uv run --frozen pytest tests/collaboration tests/api tests/coordinator tests/adapter -q -p no:randomly
uv run --frozen pytest -q -p no:randomly
uv run --frozen python probes/lg031/RUNTIME-AUTH-INTEGRATION/probe_two_phase_sdk.py \
  --out probes/lg031/RUNTIME-AUTH-INTEGRATION/evidence/two-phase-sdk.json
```

## 10. 资源清理 / 提交

- 探针临时目录自动删除；无残留进程/端口；探针 single-run 有界（~2.6s）。
- 精准本地提交（不 `git add -A`）；**不合入 main**；未触碰 8123 / 别包。
