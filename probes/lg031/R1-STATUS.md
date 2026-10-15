# LG-031 R1-STATUS（持久）

owner：`agent:pi-lg031`（等价续接）
branch：`fix/lg031-r1`
基点：`af6640e`（本轮整合 main）；保留原 `dev/lg031` `d4c0815`

## 状态

**in-progress**（R1 进行中）。目标：补真实 SDK 多 worker 自主发现/请求领取闭环。

## 真实请求计数（统一硬限）

- 原任务总上限 10；原包已用 1（reviewer）；**本次剩余至多 9**。
- 本次计划实际 HTTP 生成请求：produce worker 1 + integrate worker 1 + reviewer 1 = 3。
- 已用（本次）：见 R1-REPORT；每步更新。

## 缺口语义（不得弱化）

- 执行身份仅由程序冻结注入（grant 不进模型提示词/日志/仓库）；worker 无全局管理 token。
- 过期≠停止；旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
- 默认新路径关闭/旧确定性回退保留。

## 产出（本次）

- `backend/lightgravity/collaboration/execution_grant.py`：新增 worker 自主发现/领取请求受限工具。
- `coordinator/graph.py`：worker-pool 自主领取接线（加性）。
- `probes/lg031/R1_*`：真实 SDK 两 worker 样本 + 证据。
- `probes/lg031/R1-REPORT.md`：真实每 worker/交接/候选 review/调用与未测边界。
- 相关 tests。

## 合并续接（2026-10-16，integrate/batch6 集成 owner）

- 本分支 `fix/lg031-r2` 基于整合候选 `9698e8a`（契约 `1.9.0`），已把原 `fix/lg031-r1`
  的 tracked 改动与 `probes/lg031/R1_*` untracked 证据**精确 WIP commit**（`8383bba`），
  未盲 `add -A`，未覆盖/删除原 dirty 与 handoff 备份。
- **真实产品调用计数（以 `probes/lg031/r1_worker_claim_probe.json` 为准，非日志侧 pi 事件）**：
  R1 实测 2 个真实 worker（各自自主 discovery→claim 成功领取一个不同节点后均撞 proxy 429 预算）
  + 1 次 reviewer 模型调用 = **3 次真实生成请求**；原包已用 1（reviewer）。
  **累计 LG-031 = 4 / 10，剩余 ≤ 6**。交接日志 §6 的 `turn_end=114`/model 响应 224 为**开发 pi 事件**，
  不得当产品 SDK 生成请求或剩余预算。
- **已知未闭合（交下一 owner）**：`tests/collaboration/test_lg031_integration.py::test_autonomous_worker_tool_claim_grants_node`
  在整合候选与原 R1 base 上均失败（`plan_validation failed: config_invalid`，program plan 校验未过），
  属 R1 自身未完成项，非整合回归；其余 14 项通过。续接需补真实 SDK 两 worker 自主发现/领取/交接/候选 review
  闭环，并在合并前让该定向测试真实通过。
- 原 `fix/lg031-r1` worktree 原样保留（HEAD `af6640e`，dirty），`dev/lg031` `d4c0815` 未动。
