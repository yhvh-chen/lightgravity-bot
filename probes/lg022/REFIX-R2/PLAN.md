---
title: "LG-022 第二轮针对性返修（REFIX-R2）— PLAN"
doc_type: plan
category: engineering
updated: "2026-10-16"
---

# LG-022 REFIX-R2 — PLAN

## 0. 范围与边界

- Owner：`agent:pi-lg022-r2`。主代理只 PM；不嵌套派工、不 push/deploy/publish。
- 只修 R1 独立 QA 实证的两个阻断（A 资源完成链死锁、B 生成计数不跨重启），不扩平台/诊断功能。
- 产品真实模型预算 **0**；不重放任何 LG-031 试验/模型；原 031 dirty/分支/worktree 保持。
- 保留 D1 异步 review、D2 查询/控制非阻塞/取消未确认不释放/恢复不重放、D3 成功 Run 无伪 fail_reason、
  pin/evidence/token/验收幂等/Task 跨 Run 预算/新协作默认关闭。

## 1. 安全收编 QA 证据（不丢原始记录）

- `qa/lg022-r1` @ `6228474` 仅改 QA/任务 + 计时刷新证据，`git merge` 入 `fix/lg022-r2`（不重复 cherry-pick）。
- `probes/lg022/evidence/r1-review-lifecycle.json` 在 QA 处被**本地重跑刷新计时**（`elapsed` 0.0022→0.0023、
  `loop_served_latency` 0.5302→0.5286）。处置：
  1. 保留 R1 原提交 `d07a4a6` 的**原始字节**（`main`/R1 当前即原字节，sha `9853bca4…`）作为权威 R1 证据；
  2. QA 刷新版另存 `probes/lg022/reverify-r1/evidence/r1-review-lifecycle-refreshed.json` 并记 sha；
  3. 两个版本均有可核路径/sha，不丢原始记录，不 `reset`/`restore` 覆盖未保全资料。

## 2. A：真实资源完成链（阻断）

**根因**：成功 Run 真实落盘 `session_refs`，但成功路径从不记录 session/执行资源的真实关闭事实，`cleanup` 停在 `pending`；
stopgate 因此恒 `unconfirmed`。

**修复方向（只修真链，不绕门）**：
- 在真实 `adapter`/`dispatcher`/`RunController` 层，当节点/worker 与 reviewer 的执行资源**真实停止**后，记录
  **stop-confirmed 事实**（session 关闭确认 + proxy 停止确认），由 `RunController`/`StateWriter` 写入
  `run.cleanup`（`status=done` + 证据），**不删 `session_refs`、不伪造**。
- adapter 增加权威停止确认端口：`ensure_closed()`/`close(session_ref)` 的真实结果 + proxy stop 确认为事实来源；
  graph 节点结束后对该节点 session 落 stop-confirmed；coordinator 在 Run 进入 `verifying` 前对 Run 的
  `session_refs` 逐一经真实 `close`/`stop` 确认，仅全部确认后写 `cleanup=done`。
- **reviewer 资源也必须真正停**：review 生命周期（`ReviewLifecycle`）结束后记录 reviewer 资源 stop 事实，
  不只停 worker。
- stopgate 允许“真实 stop-confirmed 事实”证明 session 关闭（不只 `cleanup=done`）；
  unknown/close 失败/仍活跃 → `pending`/hold 槽，`cleanup` 不置 done，失败与历史资料保留。

## 3. B：持久预算账本（计量硬门）

**根因**：`GenerationCounter` 仅 `self._count` 内存。

**修复方向（最小、单事实源）**：
- 在**受控 `dataRoot`** 下做最小持久预算账本：转发前**锁/原子持久预留**，跨 worker/reviewer/session/进程重启
  读同一事实源；文件 SoT/JSONL 历史 + 可重建索引；避免第二套权威 JSON/DB。
- 计数损坏/未确认状态**不能当 0**（保守：读取失败即拒绝转发/报告 unknown）。
- 保守预留与确认转发分别标明；**不声称远端 exactly-once**。
- **输入/headers/prompt/凭证/grant 不得进 ledger**（只记计数与最小元数据）。

## 4. 局部必要回归

- `session_refs` 非空的真实资源形态 fixture：success 真实 stop 证明 → `cleanup=done` → `awaiting_acceptance` 可达；
  stop 未知/活跃/cleanup 失败仍 `unconfirmed`，不清 refs；review 阶段 stop 也包含。
- coordinator 完整 running-loop + 真实 FileStore/HTTP 路由同型替身（不再用无 `session_refs` 假体掩盖门）；
  D1/D2/D3 全回归。
- 两个独立进程/实例同 ledger：`limit=1` 仅一个预留成功；进程 1 消耗退出、进程 2 读旧 count 拒超限；
  损坏不归零、读取诊断不泄露、重启不重放；共享 proxy/worker/reviewer 出站硬 cap。
- `mypy` + 相关 tests；确有大整合全后端一次。产品真实模型 0；独立复验另 pi。

## 5. 契约与文档

- 新增账本/字段/端点语义先经契约控制真实升版；`docs/08`、`README`、`PROJECT`、`agent.md`、`docs/06` 本包唯一 owner。
- 旧 1.9 来源/可逆归档/search/vector/Chat UI 不能回退；不改 `sources/frontend/collaboration` 自治逻辑非必要。

## 6. 预算

- 15 分钟墙钟提示、最多 120 开发模型轮、非缓存 tokens 200k 硬界；devAPI 重试 0、idle 240s；
  单命令 120s 长检查短轮询；未知写入不重放。
