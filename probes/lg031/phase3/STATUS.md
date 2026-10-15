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

**in-progress**。目标：真实产品协调器路径下 2 真实 SDK worker 自主 discovery→申请原子授权 claim →
隔离执行→受控带 hash 交接→程序整合候选→真实独立 review+机器门。

## 真实调用计数（单一事实源，不重置、不猜）

- 旧累计（前两阶段）：原包 1（reviewer）+ R1 3（2 worker + 1 reviewer）+ R2 6 = **10/10**。
- 本 phase3：PM 批准新增 **≤14**；**旧 10 不归零**；**全局已知上限 ≤24**。
- 持久账本固定路径：`probes/lg031/phase3/ledger/generation/`（`generation.jsonl` + `generation.count.json`）。
- 本 phase3 实际已用：**见 `ledger/LEDGER.md`（唯一权威；每次真实转发后更新）**。
- 每请求输出 ≤12000 tokens；单 HTTP ≤120s；并发 ≤2；SDK/API retry 0；usage 未知记 unknown。

## 已知 compat 缺口（本包最小修复）

- **G1**：`api/bootstrap.py` 默认 `GraphDispatcher` 未接 `autonomous_claim`/`grant_registry`，
  开关未读入 —— 产品路径无法启用自主 claim 工具（R2 探针因此绕过产品协调器）。
  修复方向：bootstrap 从 settings 读取开关决定 `autonomous_claim` + 装配 `grant_registry`；默认关闭回退不变。

## 步骤进度

- [x] 核整合 HEAD/clean/dirty/旧资源/claim/预算（旧 10 已核，uvicorn 非本包不触碰）
- [x] 写固定 PLAN/STATUS/LEDGER 与旧成本
- [ ] G1 最小修复 + 离线确定性测试（产品 `GraphDispatcher` 自主链路）
- [ ] 验证持久账本跨进程/重启可靠
- [ ] 真实链：2 SDK worker 自主 claim + 交接 + 整合候选 + 独立 review
- [ ] 报告 / 证据 / 精确本地 commit

## 未达成（实时维护，不伪称）

- 真实链尚未开始（无真实转发之前）。
- 完整 checkpoint skip 仍未实现（沿用既有边界，本包不夸大）。
- LG-032 独立集中 QA 与全生命周期成本对比**不在本包**。

## 边界

默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；
旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
未 push/deploy/发布；未改 sources/vectors/frontend；未碰 022 worktree 与旧 dirty。
