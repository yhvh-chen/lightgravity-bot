---
title: "batch-20261016 第四批集成/任务准备报告（LG-021 增量 QA / LG-036 词法索引；claim 与 worktree）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第四批集成与任务准备报告（唯一 main 小批整合/任务准备 owner）

唯一集成/准备 owner（pi，现有 env DeepSeek，无嵌套派工）。本包**只做只读核对 + 安全合并 + 最小共享装配核对 + 任务记录 + CLI 原子 claim + 本地 worktree 准备**；
**未实施 LG-022/037/038 产品代码、未运行产品真模型验收、未推送/部署/发布**。主代理只 PM。

## 0. 基点与保护

- 集成前 `main` HEAD `e4cef4a`（与主代理预期一致），`git status` 仅 `?? probes/batch-20261016/PREPARE-4.md`（untracked，本包原样保留）。
- 全部旧分支、`/tmp` 与项目旁 worktree、原始 probes/证据、dirty 工作区**全部保留**；**未 reset/clean、未整树覆盖、未重复 pick**，未复制 `.env`。
- 集成分支 `integrate/batch4` 自 `e4cef4a` 起，逐一 `--no-ff` merge，无冲突。
- 两个来源包进程已退出（HEAD 稳定、status clean），本包只核状态，未重放其工具。

## 1. 各包合并前 HEAD / status 核对

| 任务 | 分支 | HEAD | 合并前 status | 证据 |
|---|---|---|---|---|
| LG-021 增量 QA | `qa/lg021-r1` | `5176edf` | clean | `probes/lg021/incremental-r1/REPORT.md`、`evidence/incremental-results.json`（26/26 `ok:true`）、3 张实测像素截图 |
| LG-036 实施 | `dev/lg036` | `ece758c` | clean | `probes/lg036/{REPORT,STATUS,INTEGRATION}.md`、`tests/sources/lexical/**`（25 项） |

- 合并提交：`11c3256`（LG-021 增量 QA，`--no-ff`）、`10b165f`（LG-036，`--no-ff`）。
- 合并后 `integrate/batch4` 与（随后合并的）`main` 均无冲突。

## 2. LG-021 独立增量复验（独立于实施者）

- 同一 QA owner 新上下文增量复验，候选集成 HEAD `e4cef4a`；只补既有门缺口，不重跑 31 条首验、不建通用对比度框架、不改产品代码。
- 真实产品单进程服务（`python -m lightgravity start … --no-executor`，真实 `frontend/dist` + `/api/v1`）+ 真实 Firefox 156.0.1 原生 BiDi；独立临时 data root。
  本包**实际执行** `vite build`。**产品模型调用 0**。
- **新增 26/26 PASS**：1440×900/1024×768/390×844 精确视口（真实 `window.innerWidth/innerHeight`，非文件名）+ 无横溢 + 截图像素独立复核；
  新 reviewer 默认选择（真实 UI+API：409/401/无秘密回显/reload 持久/清空诚实/scope 保持）；5 个未采 meta 对比度类真实 computed style 全部 ≥4.5。
- **旧缺口闭合**：旧「1440 截图实为 1366×682」缺口在确证 1440×900 下闭合。
- **未观测（不写 pass、不判缺陷）**：`:focus-visible` 在 headless BiDi 下不可观测（记为 not-applicable 观察）；真实 `ModelReviewer`/SDK 执行不在本包。
- **真实缺陷：0**。

### 2.1 PM 状态决定：LG-021 `in-progress` → `done`

依据 `qa/lg021` 首验（`43dc3f1`，31 条主要条件真实通过）＋ `qa/lg021-r1` 增量复验（`5176edf`，26/26 真实通过），未发现实质前端缺陷。

- 本门是**前端状态与响应式验收**，**不等于 LG-022 端到端/故障门**，不覆盖产品 SDK worker 真实执行；**不把 frontend 门说成全产品 QA**。
- `:focus-visible` 不可观测**不写成 pass**，仅记为工具环境限制。
- 产品 SDK 真实闭环**归 LG-022，不是 LG-021 成为 done 的前置**；据此**不形成**「LG-022 依赖 LG-021 done 而 LG-021 又须 LG-022 才能 done」的循环。
- 任务卡已据实更新（见 `backlog/tasks/LG-021.md`）。

## 3. LG-036 词法索引与回源（机制证据 vs 装配）

- 已合并 `dev/lg036`（`ece758c`）：`sources/lexical/**`（stdlib `sqlite3` FTS5 可重建缓存，无独立 DB 服务）、`api/search.py`（`GET /api/v1/search` 路由工厂）、
  `sources/service.py` 最小索引钩子、`tests/sources/lexical/**`（25 项，真实 `create_app` + 真实 `FileStore` + 文件 SoT + 真实 HTTP）。
- **候选集成验证（真实运行）**：`uv run pytest tests/sources tests/api tests/contracts -q` → **133 passed**；`uv run mypy` → **Success: no issues found in 129 source files**。
- **真实默认 app 检查（诚实）**：在 `create_app()` 真实默认 app 上 `GET /api/v1/search` → **404（未挂载）**；`GET /api/v1/sources` → 200。
- 即：端点工厂/缓存/回源核对/授权过滤**机制实现完成且有真实 HTTP 测试**，但**尚未接入默认 app**（需 1 行 import + 1 行 `include_router`）。

### 3.1 装配阻塞：单文件 owner 冲突（本包不并写，等待交接）

- `backend/lightgravity/api/app.py` 由本包声明为唯一 owner（只加 search 挂载）。集成核对发现：
  **并发 owner LG-031 在其 worktree `dev/lg031` 已未提交修改同一文件**（`git status` 显示 ` M backend/lightgravity/api/app.py`，diff 为 **+5 行**,
  新增 `worker_identity` 执行身份接缝并传入 `ApiContext`）。LG-031 仍 `in-progress`、尚无提交（`e4cef4a..HEAD` 为空）。
- `worker_identity` 是 docs/08 §4.3 明确的 **LG-031 契约职责**（真实 worker 身份注入属 LG-031）。故 `api/app.py` 实为**两方共需**文件，
  按**单文件 owner 串行**规则，本包**不与其并发并写**；**报告并等待该单文件 owner 交接**后再由单一 owner 一次性加装。
- 据本项装配条件「实际装配满足才 done」，**LG-036 保持 `in-progress`**（不 done、不宣称版本通过、不降低 LG-040 门）。
- 拟议最小挂载与 docs08 措辞（交 owner）见 `probes/lg036/INTEGRATION.md`；**本包未改 `docs/08`**（docs08 单一 writer）。

## 4. 未尽 / 依赖状态

- **LG-031 in-progress**：其 worktree 含大量未提交执行身份/协作/设置开关改动；本包**未改其状态/文档**、未碰其 worktree。
- **LG-036 装配未完成**：因 §3.1 单文件冲突，等 `api/app.py` owner 交接。
- **LG-035 质量门不动**：真实中文/表格 OCR 质量门仍阻塞、`in-progress`；非 LG-036 前置，未被本包绕过。
- **docs/08 未改**：契约保持 `1.7.0`；`§4.3 /search` 状态行与 `§5.1 source.indexed` 说明的更新由 docs08 writer 决定。

## 5. backlog CLI 原子 claim 与 worktree 准备

- 专用根 `backlog/`；`tasks validate backlog` → **OK: 41 tasks, no diagnostics**。
- **LG-022/037/038 就绪性与 claim**（依赖不满不绕过）：见 §5.1。

### 5.1 本次实际结果

- 集成前 `tasks ready backlog` → **No ready tasks**（LG-031/LG-036 in-progress）。
- **LG-021 置 done 后**、LG-036 仍 in-progress 时：LG-022（`depends_on` LG-017/018/019/020/**LG-021**，均 done）**变为 ready**；
  LG-037（依赖 LG-033/**LG-036**，LG-036 仍 in-progress）**未 ready**；LG-038（依赖 LG-013/014/LG-034/**LG-036**）**未 ready**。
- 据「依赖不满不绕过」：**只 claim 真正 ready 的 LG-022**；**LG-037/LG-038 在 LG-036 完成（含 `api/app.py` 挂载）前不 claim、不建 worktree**。

实际 CLI 输出（`olav-tasks` v0.1.1，`node dist/cli.js`）：

```
$ tasks validate backlog           -> OK: 41 tasks, no diagnostics.
$ tasks ready backlog
LG-022  tasks/LG-022.md  执行首版端到端与故障验收
$ tasks claim backlog LG-022 --as agent:pi-lg022
Claimed LG-022 for agent:pi-lg022 (tasks/LG-022.md)      # exit 0
$ tasks claim backlog LG-037 --as agent:pi-lg037
Olav Tasks: LG-037 is not ready: waiting for LG-036.      # 拒绝，未 claim
$ tasks claim backlog LG-038 --as agent:pi-lg038
Olav Tasks: LG-038 is not ready: waiting for LG-036.      # 拒绝，未 claim
```

- claim 提交：`bf7851c`（`backlog/tasks/LG-022.md`：`status: todo` → `in-progress`，`assignee: agent:pi-lg022`）。
- **LG-037/LG-038 状态与任务卡保持 `todo` 不变**，未建分支/worktree（依赖 LG-036 尚未完成，不绕过）。

### 5.2 持久 worktree 准备（项目旁，无 `.env` 复制）

| 用途 | 分支 | 路径 | 基点 | 状态 | `.env` |
|---|---|---|---|---|---|
| LG-022 首版端到端/故障验收 | `qa/lg022` | `/home/yhvh/code/lightgravity-bot-worktrees/lg022` | `bf7851c`（claim 提交） | clean，新建 | 无（未复制） |

- 目标路径/分支**此前均不存在**，核对后新建，未覆盖任何已有目录/分支。
- **LG-037/LG-038 worktree 未建**：依赖 LG-036 未满足，不先建后绕。

## 6. 预算与操作诚实

- 预算：10 分钟、最多 85 模型轮、非缓存 tokens 150k 硬边界；devAPI 重试 0；idle 240s；命令 120s 超时/长检查短轮询。
- 产品真实模型/外部服务调用 **0**；无 push/deploy/发布；无 `/tmp` 新建 worktree、无 `.env` 复制；未知副作用不重放。
- 唯一 `rm` 类清理为 LG-021 增量 QA 自述已确认无引用的 `/tmp/lg021-incr.*`（发生在其包内，非本包）。

## 7. 待回填 / 后续交接

- **LG-022**：`qa/lg022` worktree 就绪（`bf7851c`），实施由主代理另派；本包未实施。
- **LG-037/LG-038**：未 claim、未建 worktree；待 **LG-036 完成**（含 `api/app.py` 单一 owner 挂载交接）后再就绪。
- **`api/app.py` owner 交接**：待 LG-031 提交或释放 `api/app.py` 后，由单一 owner 一次性加装 `build_search_router()`（1 import + 1 `include_router`），
  LG-036 方可满足实际装配、再评估 done 与 docs08 §4.3/§5.1 更新。

## 8. 本包提交（实际 SHA）

- `11c3256` — LG-021 增量 QA `--no-ff` merge（`qa/lg021-r1` `5176edf`）。
- `10b165f` — LG-036 `--no-ff` merge（`dev/lg036` `ece758c`）。
- `b0bbfd2` — LG-021 done 状态决定 + LG-036 集成记录 + `probes/batch-20261016/INTEGRATION-4.md` + `PREPARE-4.md` 入库。
- `7c565fd` — `integrate/batch4` `--no-ff` merge 到 `main`。
- `bf7851c` — CLI claim LG-022 `agent:pi-lg022`。
- 本包结束时 `main` HEAD = `bf7851c`（clean）；`probes/batch-20261016/PREPARE-4.md` 已由本包提交（逐字保留原内容）。
