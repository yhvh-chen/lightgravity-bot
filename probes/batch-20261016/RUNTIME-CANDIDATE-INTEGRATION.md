---
title: "运行时候选收拢报告：1.11 候选（F1/F2 + 两阶段 SDK）安全 ff 合入 main"
doc_type: report
category: engineering
owner: "唯一串行本地候选收拢 owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# RUNTIME-CANDIDATE-INTEGRATION — 运行时候选收拢（唯一串行 PM owner）

> 唯一串行本地候选收拢 owner（pi + env DeepSeek；**主代理只 PM**，**无嵌套派工 / 无推送 / 无部署 / 无发布**）。
> **本包产品真实生成 0、外部服务调用 0**：不重跑模型、不运行 SDK 测试、不创建新成本 cohort、不重跑无变更的完整 pytest/UI。
> 只做只读核对 + 安全 fast-forward 合并 + 任务状态如实 + PM 文档 + 精确本地 commit。
> 旧实验、worktree、dirty、原始记录全部保留，未 reset/clean/覆盖/重复 pick。

## 1. 开工核对（真实，只读）

| 项 | 实测 |
|---|---|
| 主工作区 | `/home/yhvh/code/lightgravity-bot`，branch `main`，开工 HEAD `3797964`，**clean**（`git status --porcelain` 空），无 stash |
| 候选 | `dev/lg031-real-proof@b819dd3`，**clean** |
| `main` → 候选 | `git merge-base --is-ancestor main b819dd3` = **YES**（main 为直接祖先）⇒ **可 `--ff-only`、无冲突、无需重复 pick** |
| 合并基点 | `git merge-base main b819dd3` = `3797964`（即 main 自身） |
| 产品树（相对 afcae82） | `git diff --stat afcae82 HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock Makefile` = **仅** `backend/lightgravity/contracts/constants.py` + `tests/contracts/test_contracts.py`（**版本元数据**） |
| 主工作区 uvicorn | `127.0.0.1:8123` PID `3320750`（旧常驻，**非本包**）**未触碰** |
| 在途 worktree | 全部 **clean**；`dev/lg031-real-proof2@475c3b1`（新隔离 **只 harness**，b819dd3 后裔，产品 diff 空）**未碰、未合** |
| backlog CLI | `tasks validate backlog` → `{"ok":true,"tasks":41,"diagnostics":[]}`；`tasks digest backlog` → `complete=true`，`counts={todo:2,in-progress:5,done:34}`；`tasks ready backlog` → `[]` |

## 2. 收拢动作（本包唯一写动作）

- `git merge --ff-only b819dd3` → **`main@b819dd3`**（`3797964..b819dd3`，10,406 插入 + 70 删除，64 文件）。
- 变更构成：**11 产品/测试**（`backend/…` 9 + `tests/…` 3，其中 `tests/collaboration/test_api_collaboration.py` 为改、
  `tests/collaboration/test_lg031_pool_selection.py` 为新增）、**5 任务/入口 docs**（`PROGRESS/PROJECT/README/agent/docs06/docs08` + `LG-029/LG-031`）、
  其余 48 为 `probes/…` 与 `qa/lg032/runtime-r1/**` 证据/harness。
- **不合** `dev/lg031-real-proof2`（b819dd3 后裔，仅 probes/harness，cap 48 **尚未实际运行、未报告**）；**不碰** `integrate/lg031-runtime`、`qa/lg032-runtime-r1`、`fix/*` 等任何分支/worktree/index。
- 未 `git add -A`；未 push。

## 3. 产品树核准（逐字节，PM 独立核）

- 相对 `integrate/lg031-runtime@afcae82`（F1/F2/两阶段 SDK 集成候选）：**除版本常量与测试断言外产品树逐字节相同**，**无新 runtime 逻辑**。
  - `constants.py`：新增 `1.11.0`/`1.10.0` 注释块，末尾 `CONTRACT_VERSION = "1.10.0" → "1.11.0"`。
  - `test_contracts.py`：`assert CONTRACT_VERSION == "1.10.0" → "1.11.0"`。
- **因此不重跑完整 pytest / 前端矩阵**：产品无新 runtime 变更。已有 version 局部 checks（`tests/contracts` + `tests/api/test_health.py` → 11 passed；`mypy` → 137 files clean）**引用其原始证据**，不失真重跑。

## 4. 契约 1.11.0 MINOR（已冻结落 main）

- 依据 R1 独立复验（`qa/lg032-runtime-r1@26ea945`）观察 **O3** 的两处**实际公开兼容变化**：
  1. 四个去中心化端点（`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、
     `POST /subtasks/{subtask_id}/lease/renew`、`POST /subtasks/{subtask_id}/lease/release`）请求体 `owner`
     由 `1.6.0` 冻结时事实采用的 **required/端点采用** 放宽为 **optional/仅一致性校验、不再具有授权含义**（授权仅取程序冻结 grant `X-LG-Execution-Grant`）。
  2. `ExecutionGrant` 加性新增进程内非持久 `lease_owner`（`effective_lease_owner = lease_owner or member_ref`）。
- 按 docs/08 §13「新增向后兼容字段/语义放宽为 MINOR」**保守**记为 `1.11.0`，取代此前 `1.10.0` 的“实现说明增补（无版本变化）”口径。
- **`1.10.0` / e0 首版包与历史证据保持原版本**：docs/08 §13 新增 `1.11.0` 行 + 保留“`1.10.0`（实现说明增补，已被 `1.11.0` 取代保留）”历史行，**不重写任何旧 JSON/PLAN/日志**。

## 5. 首版包锚点（未改，PM 独立核）

| 项 | 值 |
|---|---|
| tarball | `probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.tar.gz` |
| **sha256**（工作区实体 + `git cat-file blob \| sha256sum` 双核） | **`581f1de603ab8adc6533efa9d4b2ed0506433d17328646b00ab7bbb2761f4de0`** |
| 文件数 | **405**（未改） |
| source 锚 | 首版稳定 product tree `e0a8cec`、契约 `1.10.0` |

- README 保留 **024 首版历史锚**（更新说明段“绑定首版核心稳定产品树 `e0a8cec`…契约 `1.10.0`”）与**当前 source**（更新说明段“契约版本 `1.11.0` 已冻结”）的**区别**。
- **不把 e0/1.10 旧包改称 1.11 最新版**；公开许可证仍**未选定、未授外发布**；本包**不发新 approval 问题**（不代用户选公开许可证）。

## 6. 门、证据与真实边界（不把局部 pass 当产品 pass）

- **独立机制复验（已落 main）**：`qa/lg032/runtime-r1@26ea945`——真 SDK 0.1.22 + 本地受控 fake loopback 上游（provider-substitute）四门 **PASS**：
  门1 两阶段（8 真 SDK 会话/2 成员/非首项选择/4 隔离 worktree）；门2/2b 竞争与身份（default-deny、冒用/跨 Run/越权/stale fence/偷租约被拒，1 winner/fence）；
  门3/3b 资源/预算/恢复（8 会话入 `run.session_refs`、未停即 held、同一持久账本跨 Run 20→40、corrupt=-1 非 0、reviewer 共账本转发前拒绝）；门4 默认 off 回退（`plan_source=rules`、无工具、无 fence）。
  **0 阻断缺陷、3 观察（O1 lease_owner 粒度 / O2 已证共享账本 / O3 §13 分类口径）**。**产品真实生成 0**。
- **正式真实 proof（已落 main，PARTIAL）**：`dev/lg031-real-proof@b819dd3`——真实 DeepSeek 单次正式 fixture **24/24 cap**：
  门 1–4/6 PASS（2 逻辑 worker 各自隔离 worktree 精确产物 alpha/beta、verify 接收 4 条版本化 hash 交接、真实 stopgate 6/6 stopped）；
  **门 5 独立 ModelReviewer 与门 7 绑定 accept 因共享上限在 verify 处 429 转发前拒绝未达**（**非 runtime 缺陷**——`reserve-before-forward` 与 `corrupt=false/绝不当 0` 行为正确）。
- **⇒ 允许把已独立机制复验、default-off 的候选代码收拢 main，但不宣版本完整通过、不 mark LG-031/032 done。**

## 7. 状态如实（counts 真实，任务 CLI）

- backlog 根 `validate` = **41 tasks / 0 diagnostics**；`digest` = **complete=true**（**todo 2 / in-progress 5 / done 34**）；`ready` = **[]**。
- 卡状态：**LG-029 `done`**（R1 门 2 **正向**确认 F2 返修——四端点程序 grant 认证 + default-deny + 不落盘 + 冻结 `lease_owner` 一致，跨 member 冒用被拒；历史重新打开期证据/原 `ddab113` 保留）；
  **LG-031 `in-progress`**、**LG-032 `in-progress`**（**保留，不 mark done**）；**LG-035/037 `in-progress`**；**LG-040/041 `todo` 不动**；**LG-036/038 `done` 保留**。
- 契约 `1.11.0`、SDK `0.1.22`、程序最小规则调度、真实 SDK 唯一路径、自主模式 **默认 off** 不变。

## 8. 成本（单列不洗）

- **旧 LG031 工程 34** + **新真实 proof 24** = 已知整体工程上限 **58**（`=34+24`；旧 phase 剩 6 **不再消费**）。
- 与 **LG-023 旧实际 65（cohort-1 45 + cohort-2 4 + cohort-3 16）分列、不合并、不洗白**。
- **`dev/lg031-real-proof2` 新 cap 48 只有上限、尚未实际报告**（**不计 0 完成、不称成功**）。
- provider token / 费用 / shared pi QA **仍 `unknown`**（**不当 0**）；不预设省 token。

## 9. 未闭合与下一步（交 PM）

- **LG-031 最终真实门未齐**：仍需**真实 provider 下 `verify`/独立 ModelReviewer/绑定 accept** 的真实 proof（同上冻结 fixture/计划/门，单一持久 ledger、更大但同样预注册的上限）。
- **LG-032 阶段 B 未做**：需 029/031 返修独立复验闭合后，由 PM **另行冻结**固定样本/次数/费用上限与成功门，并**先离线验证 harness**（同一持久 ledger、跨重启不归零、损坏绝不当 0、转发前预留、usage unknown 不当 0），做**同门全生命周期成本对照**。**不把局部机制 pass 当产品 pass**。
- **本包产品真实生成 0、外部服务调用 0**；未创建 B 成本 cohort、未运行 SDK 测试、未调用模型；**未 push/deploy/publish**。

## 10. 提交与边界

- 精确本地 commit（`PROGRESS.md` + 本报告）；**不 `git add -A`**；**不 push/deploy/publish**。
- 未改产品/共享 docs（除已随候选 ff 落 main 的 1.11 版本元数据外）；未触碰 8123 / 任何别包 worktree/branch/index；未动旧证据/未提交改动/原始运行。

## 参考

- 独立机制复验 R1：`qa/lg032/runtime-r1/{REPORT,FINDINGS,STATUS}.md`
- 正式真实 proof：`probes/lg031/REAL-PROOF/{REPORT,STATUS}.md`
- 运行时集成：`probes/lg031/RUNTIME-AUTH-INTEGRATION/{REPORT,PLAN,STATUS}.md`
- 池选择 F1：`probes/lg031/POOL-FIX/{REPORT,STATUS}.md`
- F2 身份返修：`probes/lg029/F2-AUTH-FIX/{PLAN,STATUS}.md`
- 首版包：`probes/lg024/STAGE-B/`、`probes/batch-20261016/LG024-CLOSE.md`
- [接口契约 1.11.0](../../docs/08-interface-contract.md)

## PM 后续直接 CLI 校正（2026-10-15T19:26:11Z）

本报告原34 done/5 in-progress计数与随后直接CLI不符；以完整扫描的实际结果为准：**35 done / 4 in-progress（LG031/032/035/037）/ 2 todo（040/041）**，diagnostics=[]，LG029与LG024 frontmatter均done。源代码/包校验和与本报告其余已核事实不变；工程proof2 cap48为在途上限而非已完成或实际消耗。
