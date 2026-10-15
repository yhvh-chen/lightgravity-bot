---
title: "LG-031 phase3 — PLAN（真实 SDK 两 worker 自主闭环 + 机器门/独立 review）"
doc_type: plan
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "0144eb7"
---

# LG-031 phase3 — PLAN

owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM，无嵌套派工/推送/部署/发布）。
worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`；分支 `fix/lg031-r3`；基点整合候选 `0144eb7`。

本包是**新的工程验证 phase3**。前两阶段累计 **10** 真实请求（原包 1 reviewer + R1 3 + R2 6），
全部为失败/partial 成本，**不归零、不重放**。PM 另批准本 phase3 **最多 14** 次实际 DeepSeek
生成转发尝试；**旧 10 + 新 ≤14 = 全局已知上限 ≤24**。本包**不是** LG-032 收益比较，
**不替 032 预注册样本/预算/成功标准，不预设节省**。

## 0. 旧资源核实与保护（不得重放未知副作用）

- 全部旧 worktree/分支/实验/失败证据**原样保留**；`git status` 开工核为 clean。
- 旧 `fix/lg031-r1` @ `af6640e` 原 dirty、`dev/lg031` @ `d4c0815`、`fix/lg031-r2` @ `3821620`
  一律**未触碰**。严禁去旧 dirty `lg031-r1` 工作区写入。
- 主 worktree `/home/yhvh/code/lightgravity-bot` 上有一个 **2026-10-15 起**的 uvicorn（端口 8123，
  自带 `LIGHTGRAVITY_DATA_DIR`）。**非本包启动、非本 worktree**，未知副作用；**不 kill、不接线、不复用其 dataRoot**。
  本包探针使用**独立临时 dataRoot + 独立 loopback 代理端口**。
- 未发现可归属于本包的残留 SDK 会话/代理进程。

## 1. 目标（补齐的真实硬条件）

驱动**真实产品协调器路径**（`GraphDispatcher`），用**真实 Antigravity SDK worker**（非 fake executor、
非手搓 harness）完成：

1. ≥2 真实 SDK worker，各自**独立真实 git worktree**；
2. worker **自主** discovery→**申请**原子授权 claim（真实模型→受限工具→程序决策的事件链）；
3. 程序验证身份/能力/依赖/预算并**原子授权 + lease/fencing**；worker 只申请、程序控制权限/状态/预算/fence/验收；
4. 受控**带 hash 同伴交接**；
5. 程序产出**整合候选** → **真实 coordinator 异步独立 review + 机器门**；
6. 失败有界返修/复验；旧证据保留；
7. 默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；旧 fence 不可写；
   未知副作用 `recovery_required` 不重放。

**不得**：fake executor 冒充真实、程序先选节点冒充 worker 自主、standalone reviewer 绕真实闭环。

## 2. 已知 compat 缺陷修复（最小、局部离线先证）

R2 探针**绕过了产品 `GraphDispatcher`**（手搓 pool grant 与 `claim_callback`），因此它证明的不是
“产品协调器自主 claim 闭环”。核代码发现真实缺口：

- **G1**：`api/bootstrap.py` 的默认 `GraphDispatcher` **从不传** `autonomous_claim` / `grant_registry`，
  且开关（`decentralized_claim_enabled`）在 bootstrap **未读入**用于开启自主工具 —— 产品路径即使
  打开开关也**无法启用**自主 claim 工具。
- 修复方向：bootstrap 从 settings 读取 `decentralized_claim_enabled` 决定 `autonomous_claim`，
  并装配进程内 `grant_registry`；缺省/关闭完全走旧确定性路径（无工具、无 grant）。**加性、可回退**。
- 另核：worker 一轮内多次真实请求会吃预算（R2 教训）。fixture 需**最小轮次**（每 worker 少轮、
  工具调用集中），使 2 worker + 1 reviewer 落在 14 内。

先**离线**用确定性 fake executor 证明产品 `GraphDispatcher` 自主链路（含 G1 接线）后再真链。

## 3. 固定 fixture（简单、可真实闭环）

- 2 个依赖节点：`produce`（写 `out/produce.txt`）→ `integrate`（依赖 produce，写 `out/integrate.txt`）。
- 2 个真实 SDK worker，各**独立 git worktree**（真实 `git worktree add`）。
- 每个 worker 拿到**程序冻结的 pool grant** + 受限 `discover_and_request_claim` 工具（+ 受控 peer 工具）。
- reviewer 为**真实独立 ModelReviewer**（经产品 `verify.review` 路径），对**完整整合候选**给机器门可校验的结论。
- **关键断言不删、review 不降级、stopgate 不放宽**。

## 4. 预算（硬限，持久、跨进程）

- phase3 真实生成转发尝试**至多 14**；旧 10 不归零；**全局已知 ≤24**。
- 单一事实源：`PersistentGenerationLedger`（契约 1.10 持久账本），固定路径
  `probes/lg031/phase3/ledger/`（`LIGHTGRAVITY_GENERATION_LEDGER_DIR`），**转发前持久预留**，
  跨 worker/reviewer/session/**进程重启**读同一账本；损坏**绝不当 0**。
- 探针启动前必须**先**验证账本跨进程/重启可靠（子进程读写一致性），再调用真实转发。
- 请求参数：每请求输出 ≤12000 tokens、单 HTTP ≤120s、并发 ≤2、SDK/API retry **0**。
- usage 未知记 `unknown`，**不当 0**；不打印/落盘 key/secret/grant/token。

## 5. 验收门（真实硬条件，全部满足才可 done 候选）

真实硬条件 1–7（§1）+ 每 worker 的工具/隔离/交接/候选 review/停止证据 + 输入与源码版本 +
旧 10 + 新实际数 + 成本（未知单列）+ 剩余门。缺任一 ⇒ 诚实 partial，不写 done，不偷偷开新账本归零。

## 6. 非目标

- 不造通用调度平台/常驻模型编排 agent；不开 SDK 无限委派；产品 runtime 仍 SDK 0.1.22、内部 delegation off。
- 不改 `sources/vectors/frontend`（037/038 线）；不碰 022 worktree（只读快照）。
- 不 push/部署/发布；不扩原 10；不重跑已成功旧探针；不降低任何既有断言/门。
- 不替 LG-032 预注册样本/预算/成功标准。
