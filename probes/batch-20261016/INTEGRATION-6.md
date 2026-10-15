---
title: "batch-20261016 第六批集成报告（LG-022 R1 收拢 / LG-037·038 集成 / 可逆归档语义修复 / LG-031 续接准备）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第六批集成报告（唯一串行集成 owner）

唯一集成 owner（pi，现有 env DeepSeek，主代理只 PM，无嵌套派工/推送/部署/发布）。
本包只做**安全合并 + 最小共享装配接线 + 必要语义修复 + 契约加性升版 + docs/project 同步 +
独立 QA/续接分支准备**；**未运行产品真实模型/外部服务（产品调用 0）**，未推送/部署/发布。

## 0. 基点与保护

- 集成前 `main` HEAD `ca27160` + 主代理两项**已授权 PM dirty**（`PROGRESS.md`、`backlog/tasks/LG-041.md`）。
- 开工条件核对：LG-022 R1 返修 owner 已结束（无残留 pi 进程，仅本集成 wrapper 运行）；
  `fix/lg022-r1@d07a4a6` clean；`dev/lg037@e713ea2`、`dev/lg038@80cbef7` 已退出且 clean。
- **保留**全部旧分支/worktree/probes/原始证据/dirty：`fix/lg031-r1` 原样（HEAD `af6640e`，dirty）、
  `dev/lg031@d4c0815` 未动、038 旧 upload 兼容与证据、037 替身证据、旧 QA 失败样本。
  **未 reset/clean/整树覆盖/重复 pick/删 worktree**，未复制 `.env`。
- PM dirty 先**精确提交**（仅那两文件）：`098c7cc`。

## 1. 安全逐分支合并（`integrate/batch6`，自 `098c7cc` 起）

| 来源 | 合并提交 | 结果 |
|---|---|---|
| `fix/lg022-r1@d07a4a6` | `bed3d0c` | 无冲突；带入 review 生命周期 D1/D2/D3 + 全局生成计数器（契约 1.8.0） |
| `dev/lg037@e713ea2` | `cf824be` | 无冲突；带入可选向量机制（39 检查）+ `api/vector.py` 路由（未自挂载） |
| `dev/lg038@80cbef7` | `0313d04` | 无冲突；带入 Chat 唯一常规接入/Files 同源面/搜索引用/深链 |

- 合并全部 `--no-ff`，无冲突；未覆盖 main 最新状态；未改他人分支。
- `git merge-base` 核对：037/038 均自 `dda78f2`（`ca27160` 祖先），合并干净。

## 2. 向量路由挂载（LG-037，集成 owner 唯一 writer of `api/app.py`）

- 在 `api/app.py` 加 1 行 import + 1 行 `include_router(build_vector_router(), prefix=API_PREFIX)`。
- **真实默认 app 验证**：`create_app()` 上 `GET /api/v1/vector/status`、`GET /api/v1/vector/search`、
  `POST /api/v1/vector/rebuild` 均已注册；`/search`、`/sources/.../actions` 仍在。
- **默认禁用**、后端仅由环境变量配置、候选回源核对；向量不可用时词法检索与原件查看照常可用（037 保证）。

## 3. LG-038 实质语义修复：可逆归档 ≠ 撤销

原 LG-038 自评把「归档」复用 `revoke`（`status→archived` + 命中失效），**不能作为整理归档的完成证据**。
本包做**最小受保护可逆归档**，先加性冻结独立字段/动作以避免改旧 `revoke` 语义：

- **契约加性（1.9.0）**：`source` 新增加性布尔字段 `archived`（默认 `false`）；
  `POST /sources/{id}/actions` 新增 `archive`/`unarchive` 与可选 `expected_revision`（乐观并发，冲突 `409 revision_conflict`）。
  `archive` 只置 `archived=true`，**不改 `status`、不动索引、不影响检索/打开/权限/来源**；`unarchive` 复位。
  `revoke`/`delete` 语义**保持不变**（撤销仍 `status=archived` + 失效命中；原件保留）。
- **后端**：`sources/{models,store,service,intake}.py`、`api/sources.py`（动作请求加可选 `expected_revision`）。
- **前端**：`FilesMaterialsPanel` 加 Archive/Unarchive 按钮（复用 source SoT/`expected_revision`/`sourceAction`），
  `SourceView.archived` 与 `sourceAction` 请求体扩展。
- **真实 HTTP 回归**（`tests/sources/test_lg038_archive_semantics.py`，真实默认 app + 真实 FileStore + 真实 HTTP）：
  ① archive 后仍可检索、可打开，`status` 不变；② revoke 仍使命中失效且原件保留；
  ③ archive 幂等；④ 陈旧 `expected_revision` → `409 revision_conflict`。
- **UI 局部冒烟**（vitest，2 项）：Archive 调 `sourceAction(action=archive, expected_revision)` 且**绝不调 revoke**；
  已归档显示 Unarchive。
- **tags 未冻结**：本包**明确不实现标签**，不伪造（不挡本项归档闭合）。

> 结论：038 归档缺口**本包最小闭合**（可逆、保留来源/检索/打开/权限，撤销才使之不可用）；
> 038 保持 `done # 待版本 QA LG-040`，但注释已更新为如实记录该修复，且**真实 OCR/vector/ASR 质量仍未验证**。

## 4. 契约与文档（真实变更控制，加性 MINOR）

- **契约 `1.8.0 → 1.9.0`**（加性 MINOR）：`contracts/constants.py`、`tests/contracts/test_contracts.py`。
- `docs/08` 同步：frontmatter、顶部说明、§4.3（actions 行 + 3 个 vector 端点行）、§6.6（`archived` 字段 + 归档≠撤销语义）、
  §13（新增 1.9.0 变更行）。
- `docs/06`、`README.md`、`agent.md`、`PROJECT.md` 一致性更新为 1.9.0 并保留历史版本链。
- **不机械覆盖**：1.8.0/1.7.0/1.6.0 记录全部保留，仅追加 1.9.0。

## 5. 集成检查（真实退出码，绑定 `9698e8a`）

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `uv run pytest -q` | **754 passed, 2 skipped**（76.5s） |
| 后端类型 | `uv run mypy` | **Success: no issues found in 136 source files** |
| 定向（sources/api/contracts） | `uv run pytest tests/sources tests/api tests/contracts -q` | **179 passed, 1 skipped** |
| 归档回归 | `uv run pytest tests/sources/test_lg038_archive_semantics.py -q` | **3 passed** |
| 前端类型 | `npx tsc --noEmit` | **0 错误** |
| 前端测试 | `npx vitest run` | **98 passed（13 files，含新增 2）** |
| 前端构建 | `npm run build` | **成功** |
| 真实默认 app 路由 | 进程内核对 | vector/status、vector/search、search、actions 均在；`/api/v1/search` 未回退 |

- **本轮产品真实模型/外部服务调用 0**（已有结果只引用不重跑；031 R1 的结果引用其原始证据，未重放）。
- 前端确有合并 UI 变化（038 材料面 + 归档按钮），故前端 type/test/build 实跑。

## 6. 独立 QA 与续接准备（本包不执行 QA）

- **独立 QA 分支**：`qa/lg022-r1`（基于整合候选 `9698e8a`）；脚手架
  `probes/lg022/reverify-r1/{PLAN,STATUS}.md`：非实施者复验 D1/D2/D3 + 真实链 + 全局请求计数；
  **LG-022 原 claim 保持 `in-progress`**，本包**未**执行复验、**未**发真实请求。
- **LG-031 续接**：分支 `fix/lg031-r2`（基于 `9698e8a`），已把原 `fix/lg031-r1` 的 tracked 改动 +
  `probes/lg031/R1_*` untracked 证据**精确 WIP commit**（不 `add -A`）；原 `fix/lg031-r1` dirty 原样留存。
  - **真实产品调用计数（以 `probes/lg031/r1_worker_claim_probe.json` 为准，非日志侧 pi 事件）**：
    R1 = 2 真实 worker（各自自主 discovery→claim 领取不同节点后撞 proxy 429）+ 1 reviewer = **3**；
    原包已用 1（reviewer）；**累计 4 / 10，剩余 ≤ 6**。交接 §6 的 `turn_end=114`/model 响应 224 为**开发 pi 事件**，不算产品请求。
  - **已知未闭合（交下一 owner）**：`tests/collaboration/test_lg031_integration.py::test_autonomous_worker_tool_claim_grants_node`
    在整合候选与原 R1 base 上**均失败**（`plan_validation failed: config_invalid`），属 R1 自身未完成项，**非整合回归**；其余 14 项通过。
  - **新 `api/app.py` 的 search/vector 挂载未回退**。
- 未领取 023/024/032/040（依赖未过）。

## 7. 任务状态（如实，不自判版本通过）

- **LG-022**：`in-progress`（R1 已并入候选；待独立复验）。
- **LG-017**：`done # 待 LG-022 集中 QA`（R1 真实受控独立 reviewer 已实现；不制造循环）。
- **LG-037**：`in-progress`（机制/降级替身验证；端点不可达、真实质量/Recall 未测；LG-040 不解锁）。
- **LG-038**：`done # 待版本 QA LG-040`（归档语义缺口已最小闭合，注释如实记录；真实 OCR/vector/ASR 未验证）。
- **LG-031**：`in-progress`（真实运行硬条件未满足；R1 调用 3、累计 4/10；续接分支就绪）。
- **LG-035**：`in-progress`（真实中文/表格/OCR 质量门未过）。
- **LG-040**：`todo`（依赖未过，不解锁）。**LG-041**：`todo` + `blocked_by` ASR quality gate（不因 LG-039 report done 解锁）。

## 8. 分支与候选

| 用途 | 分支 | HEAD | 说明 |
|---|---|---|---|
| 整合候选 | `integrate/batch6` | `9698e8a` | 本包集成成果；**未推送** |
| 022 独立复验 | `qa/lg022-r1` | `beb28cf` | 基于 `9698e8a`；QA 脚手架 |
| 031 续接 | `fix/lg031-r2` | `7a2889d` | 基于 `9698e8a`；R1 精确 WIP |
| 原 R1 保全 | `fix/lg031-r1` | `af6640e`（dirty） | 原样保留 |
| 原 022 R1 | `fix/lg022-r1` | `d07a4a6` | clean，未动 |

- 主候选 `main` 未推送；本包结束时先写持久 REPORT，再精确本地 commit。成本/真实调用：**unknown 单列**（本包产品 0）。

## 9. 未测 / 需独立复验

- LG-022 真实 DeepSeek reviewer 在真实 coordinator loop 下的 D1/D2/D3（本包只做机制集成，未真跑）。
- 全局生成计数在多 session/reviewer/retry 下的真实共享硬上限（仅单测 + 路由挂载核对）。
- LG-037 真实向量质量/Recall（端点不可达）、LG-038 真实 OCR/vector/ASR 质量、LG-035 OCR 质量门。
- LG-031 真实 SDK 两 worker 自主发现/领取/交接/候选 review 闭环（续接分支已备，未闭合）。
- 浏览器全路径版本门（LG-021/022）；本包仅必要局部 UI 冒烟。
