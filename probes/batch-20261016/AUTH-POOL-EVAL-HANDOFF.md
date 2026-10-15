---
title: "AUTH/POOL/EVAL 返修与排期交接（LG-029 F2 / LG-031 F1 / LG-023 cohort2）"
doc_type: handoff
category: engineering
tasks: ["LG-023", "LG-029", "LG-031", "LG-032"]
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
owner: "agent:pi-pm-integration"
---

# AUTH-POOL-EVAL 交接

> 本包为**唯一串行 PM / 证据集成准备**，主代理只 PM，**无嵌套派工、不推送/部署/发布**，**产品真实生成 0**。
> 未实施代码、未执行新 QA、未跑真实 cohort、未解锁 LG-024。所有旧 worktree/分支/原始记录/dirty **全部保留**，
> 未 reset/clean/覆盖/重复 pick。

## 1. 开工与集成事实

- 开工：root `main@62e96ed` 有主代理新增 dirty（`PROGRESS.md` 9 行）。**先精准提交保全**：
  `4174e23 pm: preserve main-agent PROGRESS checkpoint (batch10 follow-up, main@62e96ed)`。
- 合并 **仅证据/评估 harness/PM 文档，无产品变更**：
  - `git merge --no-ff qa/lg032@ad3d97b` → `6a7fe72`（无冲突）。
  - `git merge --no-ff fix/lg023-method@99ad735` → **`51b7c9e`**（无冲突）。
- **产品树核准**：`git diff --stat 62e96ed HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` **为空** ⇒
  集成合并**无产品代码变更**，因此**不重跑全量测试**。
- 合并双方内容均保留（无冲突，无需取舍）；全部旧 45 失败记录与审计事实并入 main。
- **未** `mark` 任何任务完成，**未**解锁 LG-024（仍 `todo`）。
- 最终 main HEAD：**`51b7c9e59fc8c861643ba22310856e640c4ed2bb`**，clean。

## 2. 任务状态（PM 决定，用户原目标，不需再确认）

| 任务 | 状态 | 说明 |
|---|---|---|
| LG-029 | **`done` → `in-progress`（含原 `done`）** | 依据 QA F2 重要缺陷返修；原 assignee `agent:pi-lg029`、历史 `done`、已成功受限链证据保留；`fix/lg029-auth` 等价续接 |
| LG-031 | **`done` → `in-progress`（含原 `done`）** | 依据 QA F1 语义偏差 + 真实硬条件未闭合；原 assignee `agent:pi-lg031`、历史 `done`、`dev/lg031@d4c0815`/R2/R3 与 34/40 请求证据保留；`fix/lg031-pool` 等价续接 |
| LG-032 | **`in-progress`（partial）** | 阶段 A 完成（partial）；阶段 B 暂停，待 029/031 返修复验后另行冻结 |
| LG-023 | **`in-progress`（partial）** | 方法审计已并入；新 cohort2 预算 PM 预注册，产品真实生成 0 |
| LG-024 | **`todo`** | **不解锁** |
| LG-035 / LG-037 | `in-progress` | 质量门不动 |
| LG-040 / LG-041 | `todo` | 质量门不动 |

- **F2 = 重要缺陷**（claim/lease HTTP 端点接受请求体 `owner`，未接程序认证身份）⇒ 返修。
- **F1** 按原排期**补齐多候选真正 worker 自主申请**，**不以文档改名代替能力补齐**。
- 审计引用准确：**「旧停止门不是产品 bug」**——旧 LG-023 记录的 `unconfirmed` 来自未接 `session_confirmer` 的旧 `_accept`，
  离线复现证明停止门本身正确（`fix/lg023-method` A7）；**不归咎旧 LG-022 R2 产品缺陷**。

## 3. 新建持久 worktree（3 个全新，基于最终 main `51b7c9e`；先查不存在，不覆盖）

| 路径 | 分支 | owner 范围 |
|---|---|---|
| `/home/yhvh/code/lightgravity-bot-worktrees/lg029-auth-fix` | `fix/lg029-auth` | 只 `api/collaboration.py` 及相应 api tests / 029 报告；**复用既有 `ctx.worker_identity`**；不碰 `api/app.py`/`bootstrap.py`/`docs08` |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg031-pool` | `fix/lg031-pool` | coordinator/adapter/collaboration 模块/settings/bootstrap/必要 `api/app.py` 与全部 docs08/README/PROJECT/agent/docs06 共享文档；**不写 `api/collaboration.py`（029 唯一 owner）或其 API tests** |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2` | `eval/lg023-cohort2` | 只评估 harness/fixtures/probes/LG023；产品/共享 docs **只读**；基于**已通过核心首版产品树 e0 的快照**，**不等待未来 pool 功能**；两 arm **统一旧程序调度路径**（不把新自主模式混成自变量），比较计划写节点数 **1 vs 2** |

- 三 worktree 开工均 clean，HEAD 均 `51b7c9e`。**产品仍控制权限/状态/预算/验收，无常驻模型编排 agent/组织平台，自主模式默认 off。**
- 029/F1 实施包**产品请求 0**；独立版本复验后再另行预算真实多 worker 新 pool 验证，**不在此默认授权模型真写样本**。

## 4. 后续 023 新独立 cohort 预算（PM 在任何新真实请求前预注册）

- 样本：**2 样本 × 2 arm × 1 repeat = 4 attempt**；**每个正式 run 仅 1 次**。
- 预算：**总 48 / 每 12**；**所有 role/stage 共享单一持久 ledger**；**实际 proxy 转发前硬限**。
- **旧 45 失败另列**；**eval 已知总实际上限 = 45 + 48 = 93**。
- workerprompt / tool / model / SDK budgets / initial commit / accept gate **先离线验证并冻结**；
  出现 harness 错误**整 cohort 停止**，**不改后继续**。
- 运行目录 / TaskRunSubtask / 原件 / worktree **必须持久不自动清理、不可覆盖 attempt 输出**。
- 新 cohort 双方同 **toolcap 32**（由旧 10 过低实证，采样前固定）；**modelcall 每 worker ≤12 且同 attempt 总 ≤12**；
  **output ≤16000 / HTTP 120 / retry 0 / 并发 ≤2**。
- **必须真正走完整 Coordinator + stopconfirmer**；**旧混淆 45 不得计已交付成本，也不删**。

## 5. 旧证据与限制（如实保留）

- **旧 LG-023 运行 SoT / TaskRunSubtask 丢失**：原 FileStore 控制状态、candidate worktree/diff/初始 commit 对象随
  `TemporaryDirectory` 删除，记 `unknown`，**不推断补造**（`fix/lg023-method` A9）。
- **17 SDK DB 私有持久保全**：真实 SDK session DB + 恢复的 per-generation usage 存
  `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg023-survivors/`（700/600 + hash/cmp），原件未删。
- **旧 45 总数可核、逐 attempt 不可靠**：`ledger/generation.jsonl` 45 行、`generation.count.json=45` 可核；
  逐 attempt 归因因旧 guard `count=0` 与采样中改动而**不可靠**，**不能洗 0**。
- **旧 45 = protocol-deviation 失败成本**，单列、不入未来 cohort、不删。
- 旧 022（unknown+6+8+5/10）、031（**34/40**）单列、不并入、不归零。
- **审计事实引用**：**「旧停止门不是产品 bug」** —— `fix/lg023-method` 离线复现（真 `GraphDispatcher` + 真 `StoreResourceStopper`）
  在 teardown 事实齐时达 `awaiting_acceptance`；旧 `unconfirmed` 是 harness 缺陷（未接 confirmer 的旧 `_accept`）。

## 6. 验证与边界

- **产品真实生成 0**；**未实施代码/新 QA/新真实 cohort**。
- **无新产品代码 ⇒ 不重跑全量测试**（产品树与 `62e96ed` 逐字节相同）。
- 契约保持 **`1.10.0`**、SDK **`0.1.22`**、自主模式默认 **off** 不变。
- 结束仅事实交接；**不推送/部署/发布**。
