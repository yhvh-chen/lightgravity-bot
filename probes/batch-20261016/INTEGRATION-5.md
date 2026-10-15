---
title: "batch-20261016 第五批集成/任务准备报告（LG-031 接线合回 / LG-036 词法挂载 / 037·038 claim 与 worktree）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第五批集成与任务准备报告（唯一 main 串行集成 owner）

唯一集成/准备 owner（pi，现有 env DeepSeek，无嵌套派工）。本包只做**只读核对 + 安全合并 + 最小共享装配接线 + docs/project 同步 + CLI 原子 claim + 本地 worktree 准备**；
**未实施 LG-031-r1/037/038 产品代码、未运行产品真模型/外部服务、未推送/部署/发布**。主代理只 PM。

## 0. 基点与保护

- 集成前 `main` HEAD `cfbff64`（与主代理预期一致），`git status` clean。
- 全部旧分支、`/tmp` 与项目旁 worktree、原始 probes/证据、dirty 工作区**全部保留**；**未 reset/clean、未整树覆盖、未重复 pick、未删 worktree**，未复制 `.env`。
- 集成分支 `integrate/batch5` 自 `cfbff64` 起；`--no-ff` merge LG-031，无冲突。
- 031 worktree 进程已退出（`dev/lg031` HEAD `d4c0815` 稳定、status clean，`e4cef4a..HEAD` 单提交），本包只核状态，未重放其工具。

## 1. LG-031 安全合回 main

- 来源：`dev/lg031` HEAD `d4c0815`（base `e4cef4a`，clean，单提交）。
- 合并：`integrate/batch5` 上 `git merge --no-ff d4c0815`，无冲突；合并提交 `ee575c3`。
- 保留 main 最新状态：021 `done`/036 机制/022 claim（`bf7851c`）均未动；未整树覆盖。
- 并入内容：`collaboration/execution_grant.py`（不透明程序冻结 grant + 受限同伴工具 + 仅头部身份解析）、
  `coordinator/graph.py` 加性 `collaboration`/`grant_registry` fenced 领取与 revoke、
  `adapter/{execution,sdk_config,executor}.py` `execution_grant`/`custom_tools` 经 SDK `tools=` 注入、
  `settings/**` 三开关读写（缺省/非法回落关闭）、`api/{app,bootstrap}.py` `worker_identity` 与 `CollaborationService` 装配、
  `docs/08` 加性实现说明（无版本/字段/端点/枚举变化）、21 项新测试。
- **默认保持关闭**：三开关任一关闭 ⇒ 图调度走确定性 `plan_source=rules`、无自定义工具、`enable_subagents` 仍 false；程序权限/状态/预算/验收权威；无常驻模型编排 agent。

## 2. 共享 `api/app.py` 唯一 owner 交接 + LG-036 词法挂载

- 第四批阻塞根因：`api/app.py` 被 LG-031（`worker_identity` 接缝，属其契约职责）与本包（search 挂载）共需。本批 **031 owner 已释放该文件**且已提交，本集成 owner 为唯一 writer。
- 在**同一次提交**（`cfd6855`）中：
  1. 保留 031 已并入的 `worker_identity` 接线；
  2. 加入 1 行 `from .search import build_search_router`；
  3. 加入 1 行 `app.include_router(build_search_router(), prefix=API_PREFIX)`。
- **两侧安全接线**：`grep -c "build_search_router\|worker_identity"` = 4（import+include+参数+context 写入），无并发并写。
- **真实默认 app 验证（装配后，真实 `create_app()` + 真实 FileStore）**：
  - `GET /api/v1/search?q=...` → **200**；空 FileStore 时诚实 `index_status=index_unavailable`、`index_unavailable_reason=cache_missing`、`hits=[]`（非悬挂结果）；
  - `POST /api/v1/search` → **405**（GET 只读，无业务写授权）；
  - `GET /api/v1/sources` → **200**。
- 拟议 docs08 措辞见 [probes/lg036/INTEGRATION.md](../../probes/lg036/INTEGRATION.md)；已在 §4 同步实际状态。

## 3. 集成候选检查（真实退出码）

| 检查 | 结果 |
|---|---|
| `uv run mypy` | **Success: no issues found in 130 source files** |
| `uv run pytest -q`（全量，含新适配器/Graph 面） | **693 passed, 1 skipped**（75.14s） |
| 定向 `tests/{sources,api,contracts,collaboration,settings} + test_lg031_review_closure.py` | **253 passed** |
| 真实默认 app `/search` 检查（见 §2） | 200 / cache_missing / 405 / sources 200 |

- **本轮产品真实模型/外部服务调用 0**。031 的 1 次真实 DeepSeek 探针沿用其原始证据，**未重放**。
- **前端未改，不重复无关 type/build**（本批无 UI 变更）。

## 4. LG-031 状态判断：保持 `in-progress`（真实运行硬条件未满足）

- 这是本包核 031 REPORT 的**核心结论**：031 的“真实运行”证据是**真实 Git worktree/FileStore/HTTP + 进程内 fake executor**，
  外加上 **1 次 DeepSeek**——但该 1 次只是**独立 reviewer**（单轮复核），**不是 SDK 多 worker**。
- 因此**真实 Git + 进程内 fake executor ≠ “真实 SDK 两 worker 发现/领取/交接/隔离执行”**。
  任务卡验收条件第一条“真实运行覆盖至少两个 worker、独立 worktree、依赖交接及冲突处理”的**真实 SDK 硬条件未满足**。
- 据此 **LG-031 保持 `in-progress`**，理由是本项**真实运行硬条件未满足**，**不是**“错误地等待 032 版本门”——LG-032 **反依赖** LG-031。
- **不夸大**：不把完整 checkpoint skip 未实现写成已实现；不扩大恢复/重放能力；不把 fake executor 当真实 SDK 通过。
- 原 owner 等价续接：分支 `fix/lg031-r1`（基于本轮整合 main `af6640e`，保留原 `dev/lg031`），本包**未在此实施**。

## 5. LG-036：`in-progress` → `done`（待版本 QA LG-040）

- 装配条件（默认 app 实际挂载 + GET 只读 + 缺 cache/权限/陈旧诚实）已满足并经真实默认 app 验证。
- 故按本项验收“实际装配满足才 done”置 **`done`**，标注**待版本 QA LG-040**、非完整版本通过。
- **不降 LG-035 真实 OCR 质量门、不动 LG-040 门**：无正文/正文不可信 → 诚实 `not_indexed`；图片/PDF 检索质量**不声称通过**。

## 6. 契约与文档同步（无新 schema 行为，不机械升版）

- **契约保持 `1.7.0`**：本批**无新字段/端点/错误码/枚举/迁移变化**，不机械升版。
- `docs/08` §4.3：`GET /api/v1/search` 行 `冻结接口（未实现，向量可选）` → **`已实现（2026-10-16 集成挂载；待版本 QA LG-040；无向量、无 Chat/Files UI）`**。
- `docs/08` §5.1：注明 **LG-036 已实际产生** `source.indexed` 与 `source.invalidated`（`source.deleted` 以 `source.invalidated`+`reason=deleted` 代替），`source.deleted`/`intake.receipt` 仍留 LG-037～038。
- `docs/06` §6.1：加第五批集成更新段（031 合回、036 挂载 done、037/038 claim）。
- `PROJECT.md`：加第五批决策日志条目。
- `PROGRESS.md`：见 §8 追加段。
- **037 向量与 038 UI 未实现，如实标注**（no vectors / no Chat-Files UI）。

## 7. backlog CLI：validate / ready / claim / worktree

- 专用根 `backlog/`；`tasks validate backlog` → **OK: 41 tasks, no diagnostics**。
- LG-036 置 `done` 后：`tasks ready backlog` → **LG-037、LG-038、LG-041**。
- claim（依赖不满不绕过；LG-041 未 claim，留后续）：

```
$ tasks claim backlog LG-037 --as agent:pi-lg037   -> Claimed LG-037 for agent:pi-lg037      # exit 0
$ tasks claim backlog LG-038 --as agent:pi-lg038   -> Claimed LG-038 for agent:pi-lg038      # exit 0
```

- claim 提交：`dda78f2`（`backlog/tasks/LG-037.md`、`LG-038.md`：`todo` → `in-progress`，assignee 各自 agent）。
- **LG-022 仍 `in-progress`（`agent:pi-lg022`，`bf7851c`），保留不重 claim**。

### 7.1 持久 worktree（项目旁，无 `.env` 复制、不覆盖已有）

| 用途 | 分支 | 路径 | 基点 | 状态 | `.env` |
|---|---|---|---|---|---|
| LG-031 等价续接 | `fix/lg031-r1` | `.../lightgravity-bot-worktrees/lg031-r1` | `af6640e`（本轮整合 main） | clean，新建 | 无 |
| LG-037 向量索引 | `dev/lg037` | `.../lightgravity-bot-worktrees/lg037` | `dda78f2`（同一 claim commit） | clean，新建 | 无 |
| LG-038 Chat/Files | `dev/lg038` | `.../lightgravity-bot-worktrees/lg038` | `dda78f2`（同一 claim commit） | clean，新建 | 无 |

- 目标路径/分支此前均不存在，核对后新建，**未覆盖任何已有目录/分支**；`.env` 未复制。
- LG-037/LG-038 **基于同一 claim commit `dda78f2`**（满足“基于同一 claim commit”要求）。

## 8. 本包提交（实际 SHA）

- `ee575c3` — LG-031 `dev/lg031` `d4c0815` `--no-ff` merge（`integrate/batch5`）。
- `cfd6855` — LG-036 search 挂载 + 031 接线整合 + docs08/06/PROJECT + LG-031/036 任务卡。
- `dda78f2` — CLI claim LG-037 `agent:pi-lg037` + LG-038 `agent:pi-lg038`。
- `af6640e` — `integrate/batch5` `--no-ff` merge 到 `main`（merge commit）。
- 本包结束时 `main` HEAD = `af6640e`（**clean**）。
- 新 worktree 基点：`fix/lg031-r1` @ `af6640e`；`dev/lg037`/`dev/lg038` @ `dda78f2`。

## 9. 预算与操作诚实

- 预算：10 分钟、最多 90 模型轮、非缓存 tokens 170k 硬边界；devAPI 重试 0；idle 240s；命令 120s 超时/长检查短轮询。
- 产品真实模型/外部服务调用 **0**；无 push/deploy/发布；无 `/tmp` 新建 worktree、无 `.env` 复制；未知副作用不重放。
- 累计产品模型预算：**原任务 10，原包已用 1，本包未新增，剩 9**（未重置旧尝试；031 的 1 次真实调用为其包内既有证据，未重放）。

## 10. 已知风险与未尽（不宣称无害）

- `tests/collaboration/test_claims.py::test_two_owner_race...` 既有 discovery/lease 竞争偶发 `not_discoverable`：
  本轮全量单跑一次通过、单跑连跑 3 次通过；**未自动宣称其无害/无缺陷**，留 LG-032 固定判定口径。
- **LG-031 真实运行硬条件**（真实 SDK 两 worker）留 `fix/lg031-r1` 续接与 LG-032 集中 QA。
- 完整 checkpoint skip 仍**未实现**。
- **LG-037 向量 / LG-038 Chat-Files UI 未实现**。
- LG-035 真实中文/表格 OCR 质量门、LG-040 门**未动**。
- `main` 未推送（遵本包“无推送部署发布”）。
