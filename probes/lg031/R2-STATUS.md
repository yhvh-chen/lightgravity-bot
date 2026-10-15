# LG-031 R2-STATUS（持久，等价续接）

owner：`agent:pi-lg031`（等价续接）
branch：`fix/lg031-r2`
基点：`17abd78`（整合候选）；续接起点 `38e257a`
日期：2026-10-16

## 状态

**in-progress**（R2 进行中）。目标：闭合 R1 未完成的真实 SDK 两 worker 自主 discovery/claim
闭环，先离线验证共享硬计数，再最小真实样本实测。

## 真实请求计数（统一硬限，不重置）

- 原任务总上限 10；原包 1（reviewer）；R1 3（2 worker + 1 reviewer）= 累计 **4/10**。
- 本续接**剩余至多 6**（含 worker/发现/claim/peer/review/失败/返修复验）。
- 计划：worker A + worker B + reviewer = 3；返修 0 真实请求。
- 进程共享 `GenerationCounter(limit=LIGHTGRAVITY_MAX_GENERATION_CALLS)`，转发前计数。
- 已用（本次）：0（尚未发真实请求；先离线验证）。

## 已完成的离线修复（未发真实请求）

- `coordinator/graph.py`：自主路径 claim 检查从**执行前**移到**执行后、revoke 前**；
  程序只授权该 worker 被排度的节点（`node_not_scheduled_for_worker` 拒绝越权）。
- `tests/collaboration/test_lg031_integration.py`：`autonomous_claim` 相关测试 catalog 补
  `verification`→`verifier`（真实最小队伍配置），**未删断言/未绕验证**。
- `adapter/executor.py`：加性 `generation_budget` 参数，注入每个 worker proxy。
- `adapter/proxy.py` 未改默认行为；`api/bootstrap.py` 默认装配注入进程全局 `GenerationCounter`。
- `tests/adapter/test_lg022_generation_budget.py`：新增离线硬计数验证（跨 executor/proxy 共享、
  默认回退全局计数、共享 limit=1 第二个 worker 被 429）。

## 待办

- [ ] 真实最小样本（R2 probe）：2 worker 自主 claim + reviewer，验证硬条件 1–6。
- [ ] R2-REPORT、必要 mypy/pytest、精确 commit、main 待整合差异与剩余门。

## 缺口（不弱化）

- 完整 checkpoint skip 仍未实现；仅实际停止才回收 fence/资源。
- 独立集中 QA（LG-032）未做。
