# LG-031 R2-REPORT — 等价续接：真实 SDK 两 worker 自主 claim（**partial**）

owner（等价续接）：`agent:pi-lg031`
branch：`fix/lg031-r2` ｜ 基点 `17abd78` ｜ 本次实现提交 `457a89d` ｜ 日期 2026-10-16
真实样本证据：`probes/lg031/r2_worker_claim_probe.json`

## 1. 结论（不伪称）

**partial / in-progress**。本次真实最小样本证明了两条硬条件的**部分真实成立**，但因**真实
请求硬上限用尽**，未能在同一次运行内闭合完整闭环。**不写 done、不伪造成功。**

## 2. 真实调用计数（以实际转发为准，不猜、不重置）

- 原包 1（reviewer）+ R1 3（2 worker + 1 reviewer）= 累计 **4/10**。
- 本次 R2 单次运行：**进程共享计数 `count=6, limit=6`**（`GenerationCounter` 转发前计数），
  即本次真实转发 **6 次**：worker A 发现/claim/write 4 轮 + worker B 发现 1 次 + reviewer 1 次。
- **LG-031 累计 = 4 + 6 = 10 / 10，剩余 0。**
- 计数来源为 `probes/lg031/r2_worker_claim_probe.json` 的 `shared_generation_counter`，非 pi
  session/model 事件。SDK/API 重试 0；单 HTTP ≤120s；并发 ≤2（worker 串行）。
- usage：worker A `total_tokens=20587`、worker B `3361`、reviewer `usage={"unknown":["usage"]}`
  （未知计 unknown，不当 0）。

## 3. 本次修复（离线已验证，提交 `457a89d`）

| 缺口 | 修复 | 离线证据 |
|---|---|---|
| 自主 claim 检查**先于执行**导致永远失败 | `graph.py` 检查移到执行后、revoke 前；仅 `state=="succeeded"` 时才要求 claim | `test_autonomous_worker_tool_claim_grants_node` 通过 |
| 程序需只授权本 worker 被排度节点 | `_claim_for_worker` 对非本节点返回 `node_not_scheduled_for_worker` | 同上 + 测试断言 |
| 测试 catalog 缺 `verification` 致 plan 校验 `config_invalid` | catalog 补 `verification`→`verifier`（真实最小队伍），**未删断言/未绕验证** | 15/15 通过 |
| per-worker proxy 预算会重置 | `AntigravityExecutor(generation_budget=...)` 加性注入；`bootstrap` 默认装配进程全局 `GenerationCounter` | `test_lg022_generation_budget.py` 新增 3 项 |
| 跨 worker 硬计数会归零 | 进程共享 `GenerationCounter`，env `LIGHTGRAVITY_MAX_GENERATION_CALLS` 固定本包上限 | 离线：limit=1 时第二个 proxy 被 429；本次实测 limit=6 → count=6 |

检查（真实退出码）：`mypy` **136 files clean**；`pytest tests/collaboration tests/coordinator
tests/settings tests/adapter tests/api` → **383 passed**。

## 4. 真实硬条件达成情况

| # | 条件 | 结果 |
|---|---|---|
| 1 | ≥2 真实 SDK worker，各自独立 git worktree | ✅ 2 worker 均真实 SDK，独立 worktree |
| 2 | worker 自主 discovery→claim（真实模型→工具→结果链） | ✅ worker A 自主 discover×2 → **claim 成功（fence=1, granted）**；worker B 自主 discover |
| 3 | 程序验证身份/能力/依赖/预算并**原子授权**+lease/fence | ✅ `request_claim` 原子授权、fence=1，receipt 脱敏（无 token） |
| 4 | 受控带 hash 同伴交接 | ⚠️ 依赖满足程序侧写入（produce→passed + evidence ref），但 worker B **未获预算**完成 integrate，未产生完整交接 |
| 5 | 最终候选独立 ModelReviewer + 机器门；失败有界返修/复验 | ❌ reviewer 真实跑 1 次但 `outcome=unavailable`（候选仅含 `out/produce.txt`，缺 integrate）；旧证据保留 |
| 6 | 默认关闭/回退保留；身份程序注入；worker 无全局 token | ✅ 开关关闭走确定性路径、无自定义工具；grant 不入 prompt/日志/仓库 |

**未达成的主因**：worker A 在一次 turn 内进行了 4 轮真实请求（发现×2 + claim + 写文件），
占满共享硬上限 6 中的 4；worker B 仅剩 2，用 1 次发现后第 6 次被 reviewer 用掉，B 在第 7 次
（超出 limit=6）被 429；reviewer 因候选不完整诚实返回 `unavailable`。**这是真实预算不足，不是
接线缺陷**：共享计数按预期硬停，未归零、未越界。

## 5. 未测 / 缺口（交主代理重新安排工程验证 phase）

- 未在同一次运行内让 **worker B 自主 claim + 写 integrate 文件**并完成**带 hash 交接**。
- 未取得 reviewer 对**完整候选**的真实 `passed`（当前候选缺 integrate）。
- 完整 checkpoint skip 仍未实现；仅实际停止才回收 fence/资源。
- 独立集中 QA（LG-032）未做；全生命周期成本对比未做。
- 已知既有偶发：`tests/collaboration/test_claims.py::test_two_owner_race...` 全量套件中偶发
  `not_discoverable`（既有 discovery/lease 竞争），未改该已验收测试。

## 6. 默认回退与安全语义（保持）

`decentralized_claim_enabled`/`collab_requests_enabled` 任一关闭 ⇒ 确定性 `plan_source=rules`、
不领取 fenced 租约、无自定义工具。执行身份仅由程序冻结注入；grant 不持久、不进 prompt/日志/仓库；
过期≠停止；旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才 revoke。

## 7. 给主代理的下一步（不改任务上限、不扩原 10）

LG-031 真实生成预算已用满 **10/10**。要闭合硬条件 4/5，需主代理**重新安排**工程验证 phase 并
授权新预算（建议 ≥2：worker B claim+write 1、完整候选 reviewer 1），或接受当前 partial 并明确
031 的真实运行硬条件未全部满足。**不得**由本续接擅自扩展原 10 上限。
