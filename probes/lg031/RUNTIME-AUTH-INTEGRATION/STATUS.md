# LG-031 RUNTIME/AUTH INTEGRATION — STATUS

> owner：唯一串行 runtime/API/SDK 集成与返修 owner｜branch `integrate/lg031-runtime`｜基点 `834b262`
> 产品真实 DeepSeek/生成请求：**0**｜本包**不合入 main**｜本包**不自判版本 pass**

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读 AGENTS/agent/PROJECT/PROGRESS/docs06/08、029/031/032、F1 REPORT/PLAN/源码、F2 PAUSE-HANDOFF、qa/lg032 | DONE |
| 1 | 核 main/全部 worktree/dirty/源 HEAD/真实进程 | DONE |
| 2 | 建 branch + worktree + 安全合并 F1/F2（无冲突） | DONE |
| 3 | 写 PLAN/STATUS | DONE |
| 4 | lease owner 程序冻结一致性（`ExecutionGrant.lease_owner` + mint + graph claim/release + API） | DONE |
| 5 | 两阶段 SDK 生命周期（选择会话 → 原子授予 → 执行会话绑定所选 node） | DONE |
| 6 | F2 接线统一（`worker_grant` 接缝 / 四端点 default-deny / owner 兼容语义） | DONE |
| 7 | docs/08 变更控制登记（加性实现说明，无版本/字段/端点变化） | DONE |
| 8 | 真 SDK 0.1.22 + 本地 fake 上游离线端到端探针（两阶段 + 竞争） | DONE |
| 9 | 整合 pytest + mypy | DONE |
| 10 | REPORT + 精准本地提交 | DONE |

## 关键事实

- `main@834b262` clean；F1 `fix/lg031-pool@f2741bb` clean；F2 `fix/lg029-auth@388f6fa` clean。
- 合并：`--no-ff fix/lg031-pool`（无冲突）、`--no-ff fix/lg029-auth`（`api/bootstrap.py` 自动合并）。
- F2 签名缺口（测试 `mint(lease_owner=...)`）已由加性 `ExecutionGrant.lease_owner` 闭合。
- lease owner 一致性：程序冻结 **worker 实例身份** `self._owner`；`member_ref` 保持认证身份；
  HTTP `_grant_owner` 取 `effective_lease_owner`；两 worker 竞争同 node 恰好一 winner。
- 两阶段：phase1 选择 scratch workspace + `allowed_tools=()`（无写权限）+ 仅受限 claim 工具；
  phase2 独立 SDK 会话绑定**所选 node** 的隔离 worktree/objective/上游 hash/权限。
- 探针（真 SDK 0.1.22 + 本地 fake 上游，provider-substitute）：`beta_selected_non_first=true`、
  `writer_collision_into_wrong_node=false`、`sdk_session_count=4`、stop confirmed、竞争 one_winner（fence=1）。

## 真实命令（真实退出码）

- `uv run --frozen mypy` → **Success, 137 files**。
- `uv run --frozen pytest -q -p no:randomly` → **811 passed, 5 skipped**。
- `tests/collaboration` → **99 passed**（含新增两阶段 + 冻结 lease_owner + capability 不可加宽）。
- 探针 `probes/lg031/RUNTIME-AUTH-INTEGRATION/probe_two_phase_sdk.py` → evidence JSON（见 REPORT）。
- 回归：`probes/lg031/POOL-FIX/probe_pool_selection.py`（真 4 进程 flock）仍 1 winner/`held_by_other`。

## 未测 / 保留限制

- **正式真实 DeepSeek provider 端到端验证未做**（留后续 PM 独立预算）；本包探针为本地受控 fake 上游
  （provider-substitute，清楚标注），**不冒充**真实 DeepSeek。
- 完整 checkpoint skip 仍未实现；LG-032 阶段 B 全生命周期成本对照仍暂停。
- 本包不自判版本 pass；LG-031 真条件（正式真实 provider 验证）未齐保持 `in-progress`。
