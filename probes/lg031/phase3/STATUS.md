---
title: "LG-031 phase3 — STATUS（持久，实时）"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "0144eb7"
---

# LG-031 phase3 — STATUS

owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM）。分支 `fix/lg031-r3` @ 基点 `0144eb7`。

## 状态

**partial / in-progress**。真实产品协调器路径下的自主 claim 接线（G1）与发现投影（G2）已修复，
离线已证产品路径 2-worker 闭环；但**真实 14/14 预算用尽**，硬条件 4/5 未闭合。
**不写 done、不伪称、未偷偷归零。**

## 真实调用计数（单一事实源，不重置、不猜）

- 旧累计（前两阶段）：原包 1 + R1 3 + R2 6 = **10/10**。
- 本 phase3：**14/14 用尽**（运行 1/2/3 = 4/5/5）；**旧 10 + 新 14 = 24**（全局已知 ≤24）。
- 持久账本固定路径：`probes/lg031/phase3/ledger/generation/`；最终
  `count=14, limit=14, remaining=0, corrupt=false, persistent=true`。
- 每请求输出 ≤12000 tokens；单 HTTP ≤120s；并发 ≤2；SDK/API retry 0；usage 未知记 unknown。

## 已知 compat 缺口（本包已修）

- **G1**：`api/bootstrap.py` 未接 `autonomous_claim`/`grant_registry`，开关未读入 → 已修 + 测试。
- **G2**：受限 claim 工具发现投影缺 `objective`/`write`，产品路径 worker 学不到产物 → 已修 + 离线闭环测试。

## 步骤进度

- [x] 核整合 HEAD/clean/dirty/旧资源/claim/预算（旧 10 已核；uvicorn 非本包不触碰）
- [x] 写固定 PLAN/STATUS/LEDGER 与旧成本
- [x] G1 最小修复 + 离线确定性测试（产品 `GraphDispatcher` 自主链路）
- [x] 验证持久账本跨进程/重启可靠（转发前：5 → +9=14 → 重启读到 14；损坏 raise 不当 0）
- [x] 真实链 3 次运行（共 14 转发）— 硬条件 2/3/6 真实成立；4/5 未闭合
- [x] G2 修复 + 离线产品路径闭环测试（2 worker/独立 worktree/原子授权/带 hash 交接/完整候选）
- [x] REPORT / 证据 / LEDGER（14 行）
- [ ] 精确本地 commit

## 未达成（诚实，不伪称）

- 真实硬条件 4/5：integrate worker 未自主 claim+写、无带 hash 交接、无完整候选 reviewer `passed`。
  根因：真实预算 14 用尽 + worker 回合效率。
- 完整 checkpoint skip 仍未实现（沿用既有边界，本包不夸大）。
- LG-032 独立集中 QA 与全生命周期成本对比**不在本包**。
- **LG-031 保持 `in-progress`（partial）**；031 真实门未齐，不宣称 done，也不制造待 032 才 done 的循环。

## 边界

默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；
旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
未 push/deploy/发布；未改 sources/vectors/frontend；未碰 022 worktree 与旧 dirty。
