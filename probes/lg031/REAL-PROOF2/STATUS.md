---
title: "LG-031 REAL-PROOF2 — STATUS"
doc_type: status
category: engineering
owner: "LG031 REAL-PROOF2 owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "dev/lg031-real-proof2"
base: "dev/lg031-real-proof@b819dd3"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash"
updated: "2026-10-16"
---

# LG-031 REAL-PROOF2 — STATUS

> 全新隔离测试副本；**不合入 main**；旧 worktree/分支/证据全部保留；未 reset/clean/覆盖/重复 pick。
> 旧工程 34 + 上次 24 = **58 全部保留**；旧 phase 剩 6 **不再消费**；本包只增加**一次**正式运行 + 一个新持久账本上限 **48**。

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读 AGENTS/agent/PROJECT/PROGRESS、031/032、REAL-PROOF 全部 PLAN/REPORT/正式原件/R1、cohort3 成熟物理 ledger 方法 | DONE |
| 1 | 核旧 Run/全部 SDK 已停/原始资料与进程；未知副作用不重放；旧 worktrees/dirty/日志保留 | DONE |
| 2 | 建全新持久 `lg031-real-proof2`（branch `dev/lg031-real-proof2`）基于 `b819dd3` | DONE |
| 3 | 0 真实生成 forensics：旧 24 归因（selection/execute/verify）→ 根因共享 cap 24 | DONE |
| 4 | PM 预注册 proof2：PLAN 冻结（fixture/计划/requirements/提示模板/工具/caps 48/initialcommit/同门） | DONE |
| 5 | 预检（实际 `build_runtime`+SDK+localfake 三节点、startup 后物理 ledger、fakeRoot/formalRoot 隔离、stage count） | DONE（PASS） |
| 6 | 正式真实 DeepSeek **一次**运行（`fixtures/formal`） | IN-PROGRESS |
| 7 | 真实机器门 + 真实独立 ModelReviewer + 真实 stopgate + 绑定 accept | TODO |
| 8 | REPORT + 私有原件 + 精准本地 commit | TODO |

## 预注册（首请求前冻结，`2026-10-16`）

- **HEAD**：`b819dd3`（本包起点；产品树相对 R1 已验 `afcae82` 仅 `contracts/constants.py` + 契约测试的**版本 metadata**变化，核心 runtime 未变）。
- **源锚**：`qa/lg032-runtime-r1@26ea945`（R1 独立 813/5 等四门 PASS）+ `main@3797964`。
- **SDK**：`google-antigravity==0.1.22`（`installed_sdk_version()` 实证）。
- **实际模型**：`deepseek-v4-flash`（env `DEEPSEEK_API_KEY` 受控使用，不打印/不落盘）。
- **PLAN hash**：`37c339da8d2749555594e62061eefa369baed5f63341a99cde589d3c9d6926d3`。
- **forensics 脚本 hash**：`82c3054df37ddb6663e4388b96cbcf572bb3acdea53488719c3f82d0da2cab95`。
- **正式 harness hash**（`probe_formal_real2.py`）：`fce51ced98b7a9df8d2dd36a56cf9867ade1dfc145392ed970655299423b1db0`。
- **预检 harness hash**（`probe_precheck2.py`）：`b37b28d7822e23b915dfbed381fbd88ca8c4376f64aa52f5f02967e5f00c713e`。
- **fake 上游 hash**（=`fake_precheck_upstream.py`）：`5de0631e987e06e657f5766d184bc8b21a41e99b6aa63315c763a4b56e5f1ba9`（与旧 proof 逐字节相同）。
- **初始 commit（旧固定，只读 clone）**：`6cf81ea38456b7a0c3c2536b48985d7af3a55f11`。
- **machine truth**：`out/alpha.txt`==`alpha`、`out/beta.txt`==`beta`（各自隔离 worktree，无串）。
- **ledger 物理路径**：`probes/lg031/REAL-PROOF2/fixtures/formal/data/generation/generation.jsonl`（持久、跨会话/Run 不归零）。
- **caps**：新增真实生成总上限 **48**；HTTP 120s；API/SDK retry 0；并发 <=2；每请求 output <=12000。
- **仅一次正式 fixture 运行，不重复**；旧 LG031 34 与上次 24 不归零、旧 phase 剩 6 不再消费。
- **观测**：事前启用既有公开 `context.save_dir` 到私有 Root；若无 DB 如实记「无 SDK DB」。

## 旧 24 归因（只读 forensics）

- selection 12（alpha-slot 5 / beta-slot 3 / verify-slot 4）+ execute 12（alpha 6 / beta 1 / verify 5）= **24**。
- verify 执行第 6 次请求**转发前** 429；`max_session=6 < 12` ⇒ per-session cap 未触发。
- **根因 = 共享 cap 24 耗尽**；**非 runtime 缺陷**；工具级/重试级归因 **unknown**。

## 终态

- 待更新（预检/正式运行后）。
