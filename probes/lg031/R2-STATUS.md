# LG-031 R2-STATUS（持久，等价续接）

owner：`agent:pi-lg031`（等价续接）
branch：`fix/lg031-r2`
基点：`17abd78`（整合候选）；续接起点 `38e257a`
日期：2026-10-16

## 状态

**in-progress / partial**（R2 已发真实请求；预算用满，未闭合全部硬条件）。
目标：闭合 R1 未完成的真实 SDK 两 worker 自主 discovery/claim 闭环；已离线验证共享硬计数，
并完成一次真实最小样本。

## 真实请求计数（统一硬限，不重置）

- 原任务总上限 10；原包 1（reviewer）；R1 3（2 worker + 1 reviewer）= 累计 **4/10**。
- 本续接**剩余至多 6**；R2 实测 `GenerationCounter count=6, limit=6` → 本次用 **6**。
- **LG-031 累计 = 10/10，剩余 0**。SDK/API 重试 0；并发 ≤2；单 HTTP ≤120s。
- 详细计数与 usage：`probes/lg031/r2_worker_claim_probe.json` 与 `R2-REPORT.md`。

## 已完成

### 离线修复（提交 `457a89d`，已通过 mypy/383 pytest）

- `coordinator/graph.py`：自主路径 claim 检查从执行前移到执行后、revoke 前；程序只授权该
  worker 被排度的节点（`node_not_scheduled_for_worker`）。
- `tests/collaboration/test_lg031_integration.py`：`autonomous_claim` 测试 catalog 补
  `verification`→`verifier`（真实最小队伍），未删断言/未绕验证。
- `adapter/executor.py`：加性 `generation_budget` 注入每个 worker proxy。
- `api/bootstrap.py`：默认装配注入进程全局 `GenerationCounter`（真实硬上限不归零）。
- `tests/adapter/test_lg022_generation_budget.py`：离线硬计数验证（跨 executor/proxy 共享、
  默认回退全局计数、共享 limit=1 第二个 worker 被 429）。

### 真实最小样本（本次，partial）

- worker A：真实 SDK 自主 discover×2 → **claim 成功**（fence=1 granted）、写出 `out/produce.txt`；
  程序原子授权、receipt 脱敏无 token。
- worker B：真实 SDK 自主 discover 到 integrate 候选；因共享硬上限 6 已被 worker A（4）+ B 发现（1）
  + reviewer（1）占满，B 第 7 次请求被 429。
- reviewer：真实模型 1 次，但候选仅含 `out/produce.txt`（缺 integrate）→ 诚实 `unavailable`。

## 未达成（不弱化）

- 硬条件 4/5 未闭合：worker B 未自主 claim+写 integrate、未完成受控带 hash 交接、reviewer 未对
  完整候选给出 passed。
- 完整 checkpoint skip 仍未实现；独立集中 QA（LG-032）与全生命周期成本对比未做。
- 真实预算已用满 10/10，须主代理重新安排工程验证 phase；本续接不擅自扩原 10 上限、不写 done。
