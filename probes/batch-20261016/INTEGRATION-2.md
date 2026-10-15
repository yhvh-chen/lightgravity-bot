---
title: "batch-20261016 第二批集成报告（LG-017/018/019/029/034/039）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第二批集成报告

唯一集成 owner（pi，现有 env DeepSeek）。本报告记录**只读核对 + 安全合并 + 共享装配**的实际结果，
不做产品真模型验收（归 LG-021/022/032/040）。

## 0. 基点与保护

- main 集成前 HEAD：`374759b`（含主代理本轮 PROGRESS 管理补充 dirty，已保留并提交，未 reset/clean/覆盖）。
- 全部旧实验分支、`/tmp` worktree 与项目旁 worktree 保留，未 reset/clean/覆盖；未推送、未部署、未发布。
- 集成分支：`integrate/batch2`，从 `374759b` 出发。

## 1. 各包实际 HEAD / status / 证据（合并前核对）

| 任务 | 分支 | HEAD | status（合并前） | 交付证据 |
|---|---|---|---|---|
| LG-017 | `dev/lg017` | `ae85dd1`（前 `99174d8`） | clean | `probes/lg017/{STATUS,INTEGRATION,DOCS08-PROPOSAL}.md` |
| LG-018 | `dev/lg018` | `ad4a10f` | clean | `probes/lg018/{STATUS,INTEGRATION,reports/LG-018-report.md,evidence/*}` |
| LG-019 | `dev/lg019` | `eed0b28` | clean | `probes/lg019/{STATUS,INTEGRATION,evidence/*}`、冒烟脚本 |
| LG-029 | `dev/lg029` | `ddab113` | clean | `probes/lg029/{STATUS,INTEGRATION,REPORT}.md` |
| LG-034 | `dev/lg034` | `3f98f04` | clean | `probes/lg034/{STATUS,INTEGRATION}.md` |
| LG-039 | `dev/lg039` | `e6f3fd5` | clean | `probes/lg039/{STATUS,REPORT,evidence/*}` |

- 三者共同基点 `141809d`（017/018/019），`9ff71ff`（029/034/039），均早于 1.6.0 冻结；
  合并保留 main 最新契约/状态（merge，不整树覆盖、不重复 pick）。
- LG-029 首轮进程退出 0 但回答截断；收尾 pi 已提交 `ddab113`，进程已结束且 clean，方收拢。

## 2. 合并方式

按依赖/冲突面逐分支 `--no-ff` merge（本地允许）：lg017 → lg018 → lg019 → lg034 → lg039 → lg029。
无整体 cherry-pick 重复；共享文件（`api/app.py`、`api/bootstrap.py`）由本 owner 串行处理冲突/装配。

## 3. 共享装配（唯一 owner 串行处理的接线）

1. **LG-019 通知**（包内已写 `api/app.py`/`api/context.py`）：合并后 `GET/POST /api/v1/notifications` 已挂载。
2. **LG-034 sources**：在 `backend/lightgravity/api/app.py` 加
   `from .sources import build_sources_router` + `app.include_router(build_sources_router(), prefix=API_PREFIX)`。
   默认 app 实际含 `/api/v1/sources*`、`/api/v1/intake/jobs/*`、`/api/v1/inbox/messages`。
3. **LG-029 collaboration**：在 `app.py` 加 `build_collaboration_router` 并挂载；
   `/api/v1/runs/{run_id}/discoverable|claim_requests`、`/api/v1/subtasks/{id}/lease/renew|release`
   已装配且**默认关闭**（`needs decision` 之外的开关写入路径、coordinator 改用 LeaseManager、
   受控执行身份注入仍留 LG-031/032）。
4. **LG-018 worktree 隔离**：在 `backend/lightgravity/api/bootstrap.py` 的 `GraphDispatcher(...)`
   传入 `workspaces=GraphWorkspaceProvider(WorktreeManager(settings.workspace_root))`；
   **保持保守默认**，未提高 `max_parallel`，未隔离/非 git 工作区仍串行。

## 4. 合同契约同步

- `docs/08` 保持 `1.6.0`（不机械升版；LG-034/019/029 均按已冻结接口实现，无新端点/枚举语义变化）。
- 仅更新 §4.3 状态标记：LG-034 `sources`/`intake`/`inbox` 行 → "已实现（待版本 QA LG-040）"；
  LG-029 四端点 → "已实现（默认关闭；待版本 QA LG-032）"。
- §5.1 `source.*`/`intake.*` 事件说明：LG-034 实际产生 `source.received`、`source.version_changed`、
  `intake.stage_changed`、`intake.failed`、`intake.cancelled`；其余仍仅冻结。

## 5. 整合候选检查（真实退出码）

命令在整合候选（本报告提交前）执行：

| 检查 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 后端类型 | `uv run mypy` | Success, 109 source files | 0 |
| 后端测试 | `uv run pytest -q` | **545 passed, 1 skipped** | 0 |
| 定向 | `uv run pytest tests/collaboration tests/sources tests/api -q` | 110 passed | 0 |
| 装配冒烟 | `create_app()` 路由枚举 | sources/intake/inbox/notifications/collaboration 全部在册 | 0 |
| 前端类型 | `npx tsc --noEmit` | 0 errors | 0 |
| 前端测试 | `npx vitest run` | 12 files, **81 passed** | 0 |
| 前端构建 | `npx vite build` | built | 0 |

- **产品真实模型调用 0**。mock/真实 Git/HTTP 冒烟**不等于**完整 SDK 验收。

## 6. 任务状态结论（诚实）

- **LG-018 / LG-019 / LG-034 / LG-039**：`done`（待版本 QA；LG-018/019→021/022，LG-034/039→040）。
- **LG-029**：`done`（待版本 QA LG-032）；路由已装配且默认关闭，未装配项如实保留为缺口。
- **LG-017**：**保持 `in-progress`**。默认运行时的 `ProgramReviewer` 只是把 LG-009 机器检查
  换个名字重跑，**不是独立模型/角色复核**，且无受控 reviewer 配置与真实装配路径；
  "独立 QA 检查候选版本"目标未满足，不置 done，留 LG-022 真实门复验。
- **LG-041**：保持 `todo`，记录 `needs decision`（仅确需用户授权新服务/安装 ASR 模型时请求），不阻其它任务。

## 7. LG-039 报告口径

- 报告只支持"**本轮已测模型/路径未获得可用 ASR，LG-041 不解锁**"，未泛化"所有服务/任何模型永远无 ASR"。
- `gemma4-mtp` 加载失败**不**证明该模型不支持；真实样本许可（CC BY-SA 3.0）与 sha256 已核实。
- 覆盖维度缺口（口音/噪声/长音频/时间戳/中英混合）如实保留；CER 因无输出为**不适用**。
- 任务 `done` 仅指**有界可行性验证负结果**，明确**不等于**完整中文质量验收；已补此说明。

## 8. 未完成 / 剩余质量门

- 首版集中 QA：LG-021（已 claim，`qa/lg021` worktree）、LG-022。
- 资料与 Embedding：LG-035（已 claim，`dev/lg035`）、LG-036/037/038、LG-040。
- 去中心化：LG-030（已 claim，`dev/lg030`）、LG-031、LG-032。
- LG-017 独立 QA 缺口；LG-029 settings 写入/coordinator LeaseManager/执行身份注入；完整 checkpoint skip。
- 产品真实模型路径未在本候选中运行（0 调用）。

## 9. 管理表述更正（保留原始实验）

- 早期报告若称实验"未跟踪"、或把 40 位 Git blob ID 写作 "sha256"，均为**表述问题**：
  原始实验已在保全提交中跟踪；40 位值是 **Git blob ID**，非 sha256。**不改**原始实验内容。
