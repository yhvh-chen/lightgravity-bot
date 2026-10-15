---
title: "batch-20261016 第四批准备报告（LG-036 依赖校正 / LG-017 状态纠正 / claim 与 worktree）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第四批准备报告（串行任务/隔离准备 owner）

准备 owner（pi，现有 env DeepSeek，无嵌套派工）。本包**只做 PM 文档 / CLI 原子 claim / 本地提交 / 持久 worktree 准备**；
**未实施产品代码、未运行 QA、未调用任何产品模型服务、未 push/deploy/发布**。主代理只 PM。

## 0. 开工事实核对（不重放工具、不重复 merge/pick、未 reset/clean）

- 第三批集成进程已结束（exit 143 `max_rounds_reached`，终止发生在最终报告之后）；**本包只核状态，未重放其工具**。
- `main`：branch `main`，准备开工前 HEAD `2296764`，`git status` **clean**；与本包接收到的“main 2296764 clean”一致。
- 第三批产物已提交：`c667434`（Merge integrate/batch3）→ `635489e`（整合）→ `2296764`（补充记录）。其后为本包新增提交（见 §5）。
- 全部旧 worktree（含 `/home/yhvh/code/lightgravity-bot-worktrees/lg017|lg017-r1|lg018|lg019|lg021|lg028-contract|lg029|lg030|lg033-contract|lg034|lg035|lg039|ui-controls` 与 `/tmp/lightgravity-worktrees/*`）、旧分支、原始 probes/证据**全部保留**；**未 reset、未 clean、未整树覆盖、未重复 pick**，未复制 `.env`。
- 第三批声称的整合候选检查（后端 647 passed/1 skip、mypy 124 files、前端 83 passed/type/build）记录于 [INTEGRATION-3.md](INTEGRATION-3.md) §5，本包**未重跑**（非本包职责，属产品检查）。

## 1. LG-036 真实依赖校正（PM 已批准决定）

- 决定文件：`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-15/pm-decision-lg036-20261016.txt`；
  技术依据：`/home/yhvh/lg036-dependency-audit-20261016.md`。
- 已将该只读技术调查作为**不变证据**副本落盘：`probes/lg036/DEPENDENCY-AUDIT.md`（此前不存在，逐字副本 + frontmatter 标注来源）。
- `backlog/tasks/LG-036.md`：`depends_on` 由 `["LG-034","LG-035"]` → `["LG-033","LG-034"]`；正文注明本项需要的是
  **已交付的内容接口**（LG-035 commit `faf7230`/`d7e4391`、第三批集成提交提供的 `/content`/`/download`/`/actions`
  只读通道、source/版本/哈希/权限接口），**而非 LG-035 尚未通过的真实 OCR 质量门**。
- 遵守边界：**不降低 LG-035 验收**（其真实中文/表格质量门与 `in-progress` 不动）、**不改 LG-040 依赖**、
  **不声称图片/PDF 检索质量通过**（无正文/正文不可信来源须诚实 `not_indexed`）。
- PROJECT / PROGRESS / docs06 仅加**简洁实际依赖校正记录**，未重写大段历史。

## 2. LG-017 状态语义纠正（PM 规则，非绕过验收）

- 原 `status` 注释把“待 LG-022 独立集中 QA”当作**本项 done 前置**；而 LG-022 自身 `depends_on` 含 LG-017，形成**错误循环**，
  且违反 agent.md（集中 QA 只在命名大版本完成后开展，不是逐项前置）。
- 第三批报告确认本项实施目标（产品已实现的**独立 ModelReviewer 路径**）已满足、无实缺口：R1 真实受控独立复核 +
  诚实 `unavailable` 默认 + 真实 DeepSeek 探针 `passed` 且程序验真，第三批又补真实 Settings reviewer 默认 UI。
- 据此 `backlog/tasks/LG-017.md`：`status` `in-progress` → **`done`**，标注 **“待 LG-022 集中 QA、非完整版本通过”**，
  移除错误循环注释；**不改 LG-022 依赖**、不宣称版本验收、不降低其它任务验收。

## 3. backlog 专用根与 CLI 原子 claim

- 专用根：`backlog/`（非仓库根）。`tasks validate backlog` → **OK: 41 tasks, no diagnostics**。
- 校正后 `tasks ready backlog` 真实候选（校正前为“无就绪任务”）：
  - **LG-031**（`depends_on` LG-029/LG-030/LG-017/LG-018，均 done）
  - **LG-036**（`depends_on` LG-033/LG-034，均 done）
- CLI 原子 claim（均成功，退出码 0）：
  - `tasks claim backlog LG-036 --as agent:pi-lg036` → `in-progress` / `agent:pi-lg036`
  - `tasks claim backlog LG-031 --as agent:pi-lg031` → `in-progress` / `agent:pi-lg031`
- **未 claim LG-022**（其 `depends_on` 含 LG-021，LG-021 仍 `in-progress`，需增量复验真完成）；**未 claim 022**。
- claim 后 `tasks ready backlog` → **No ready tasks**（两项已进入进行中）；`tasks digest backlog` → 41 项、
  **29 done / 4 in-progress（LG-017… 现为 done；进行中为 LG-021、LG-035、LG-031、LG-036）/ 8 todo**，无诊断。

## 4. 持久 worktree 准备（项目旁，无 `.env` 复制，不使用 `/tmp`）

| 用途 | 分支 | 路径 | 基点 | 起点状态 | `.env` |
|---|---|---|---|---|---|
| LG-036 实施 | `dev/lg036` | `/home/yhvh/code/lightgravity-bot-worktrees/lg036` | `e4cef4a`（claim 提交） | clean | 无（未复制） |
| LG-031 实施 | `dev/lg031` | `/home/yhvh/code/lightgravity-bot-worktrees/lg031` | `e4cef4a`（claim 提交） | clean | 无（未复制） |
| LG-021 增量独立 QA | `qa/lg021-r1` | `/home/yhvh/code/lightgravity-bot-worktrees/lg021-r1` | `e4cef4a`（含第三批 reviewer UI 整合提交 `635489e`/`c667434`） | clean | 无（未复制） |

- 三个目标路径**此前均不存在**，已核对后新建；未覆盖任何已有目录/分支。
- `qa/lg021-r1` 供**同一独立 QA owner**对第三批新增 reviewer Settings UI 路径做**增量复验**；旧 `qa/lg021`
  worktree（`43dc3f1`）与证据**原样保留**，不继承旧候选截图。LG-021 原 claim/owner（`agent:pi-lg021`）保持不变。

## 5. 本包提交

- `32d08a9` — PM 依赖校正与 LG-017 状态纠正 + `probes/lg036/DEPENDENCY-AUDIT.md` + PROJECT/PROGRESS/docs06 简洁记录。
- `e4cef4a` — CLI claim LG-036 `agent:pi-lg036`、LG-031 `agent:pi-lg031`（ready 核对无诊断；未 claim 022）。
- 准备后 `main` HEAD = `e4cef4a`，clean。

## 6. 未满足条件 / 未做（供主代理派工判断）

- **LG-022 不就绪**：`depends_on` 含 LG-021（`in-progress`），须 LG-021 增量复验真完成后方可 ready；**本包未 claim、未建 worktree**。
- **LG-021 仍未通过**：第三批判定 `in-progress`（证据精度/未测项/新 reviewer UI 未覆盖）；需在 `qa/lg021-r1` 对同一实施、第三批新 UI 增量复验。
- **LG-035 质量门不动**：真实中文/表格人工真值质量门 + 已授权 OCR 端点不可达，仍 `in-progress`；其质量非 LG-036 前置。
- `LG-025`/`LG-029` 的 settings 写入开关、coordinator `LeaseManager`、执行身份注入仍未装配（归 LG-031）；完整 checkpoint skip 未实现。
- **未满足**：本包未实施产品代码、未运行任何 QA/测试、未调用产品模型；上述 worktree 仅为隔离准备，不代表实施开始。

## 7. 预算与实际消耗

- 预算：4 分钟、最多 35 模型轮、非缓存 tokens 80k 硬限制；命令 60s 超时。
- 实际：产品模型调用 **0**；devAPI 重试 **0**；无 push/deploy/发布；无 `/tmp` worktree、无 `.env` 复制。
- 命令：本包为 PM 文档编辑 + CLI claim + `git worktree add`，均为本地只读/低风险操作。
