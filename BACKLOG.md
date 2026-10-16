---
title: "LightGravity Bot 开发任务入口"
doc_type: index
category: planning
updated: "2026-10-16"
---

# LightGravity Bot 开发任务入口

> 创建：2026-10-14。开发任务由 Olav Tasks 管理，schema 为 `olav.tasks/v1`，编号 LG。状态以单项 Markdown frontmatter 为准，本索引不重复维护状态。

## 当前批次状态（2026-10-16，selected-material 原型命名里程碑闭环；LG-047 与 LG-049 已 done；LG-041 保持 todo）

- **实际闭环（root PM 复核）**：LG-047 命名里程碑独立 QA 据 LG-049 `N-R3-LIFECYCLE` **实际 PASS_WITH_LIMITATIONS** 置 `done`；LG-049 亦置 `done`。真实完整 SDK 交付生命周期跑通（原生 API 上传 alpha `content_hash=d34f0ca58b8d…`、无 seeded derivative → EXACT 前失败目标 `delivery/create_task` → 程序规则计划 `deliver`+`verify` → 真实 SDK worker **6/6 事实** → **`verify` passed（R2 曾 429）** → 机器门 → **真实独立 ModelReviewer `reviewer_kind=model`/`model_calls=1`/passed** → **worker `cleanup=done`+`member.released` 与 reviewer `reviewer_cleanup.confirmed=true` 于 accept 前 CONFIRMED** → API accept（乐观 revision）→ `done`；artifact refs 真实 body + Sources bindings 匹配）。**8/16 前向**（deliver 2 + verify 5 + reviewer 1）。报告 [REPORT-N-R3-LIFECYCLE](probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md)；本轮集成 [K-RELEASE-CLOSE](probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md)。
- **集成（仅 probes/docs）**：`--no-ff` 合入 `qa/proto-material-lifecycle-r3-20261016@dc1a1b2` → 合并提交 **`76f10c7`**（父 `096d796`+`dc1a1b2`）；唯一非 probe 差异 `LG-049.md` 冲突保留 `main` 验证记录，**无代码改动**；产品树 `main` == `0188ca2`（backend `8b4256a4…`/frontend `07618bb2…`/tests `9a37448e…`/examples `63ee05cd…`）。
- **任务 CLI（实测）**：`validate` **49 tasks / 0 diagnostics**；`digest` **48 done / 0 in-progress / 1 todo**；`ready=[]`；唯一 decision = LG-041（质量门）。
- **保留限制（不洗白）**：累积成本 **unknown 非 0**（R1 已知 1+缺口 / R2 actual 8 / R3 actual 8 分列）；浏览器 UI 证据为复用（前端未构建，前端树一致）；未重跑全量测试（代码未改）；`orion-summary.md` 裸名 ref 400 为端点契约行为。用户最终验收仍待定、未 push/deploy、`8123` 未触。

### 上一批次（2026-10-16，selected-material 快速原型 LG-042～049；R3 执行完成待闭环；历史保留）

- 任务 CLI（backlog 根）：LG-042～045 **done**、**LG-046 整合候选已交付**、**LG-047 进行中（R1 FAIL，R2 FAIL/INCOMPLETE，预算 8/8 耗尽，无 PASS/done）**、**LG-048 诊断 done**、**LG-049《验证选定资料交付完整生命周期》`in-progress`（P0，`parent: LG-047`，`depends_on: [LG-048, LG-046]`，`assignee: agent:pi-proto-lifecycle-qa`）**；LG-041 仍 `todo`（质量门阻塞）。
- **PM 选定（root 显式授权）**：依据 LG-048 诊断，PM **明确选定** 049 为下一任务（**非**第三次盲修）；root 授权 **R3 新 campaign `N-R3-LIFECYCLE`，hard cap 16**（含失败/reviewer/连接测试）——**仅一个** fresh delivery Task、**无自动整轮重试**、`retry 0`、串行 90s/请求、生命周期轮询 ≤300s；单次 initialize 自有新 dataRoot+manifest+durable ledger（**绝不用 R2 根/counter reset**）；manifest 缺失/损坏或账本损坏 ⇒ **deny**，转发前持久预留 cap16、跨重启不归零、不自动扩展；R1 已知 1 + R2 actual 8 **分别保留**，累积成本 unknown 非 0。
- **PM 决策（保留护栏）**：保留既有 `deliver`+`verify` SDK 节点、**真实独立 ModelReviewer**、机器门/stopguard；不删除/弱化、不新增 planner/infra。docs/10 §7 与 docs/11“单 worker”措辞已**最小勘误**（文档-only，非行为变更）。
- **序列 prep（`main`，`--no-ff`、probes-only、无冲突、保留全部历史）**：合入 I `qa/proto-material-r2-20261016@a9ba494` → `256cd78`；合入 L `qa/proto-material-route-r2-20261016@11b5848` → `d8d8b4e`。产品树 `main:backend` `8b4256a4…` 与 `3ae4ac0` 一致，无代码改动。
- **R2 结论（`a9ba494`）**：真实 SDK worker 写出含**全部 6 条真实事实且正确**的 deliverable，但第二个（`verify`）SDK 节点撞 **429** 后整 Task `failed`；独立 **ModelReviewer / stop-gate / QA user accept** **从未到达（UNVERIFIED）**。R2 新增产品请求硬上限 **8/8 耗尽**，不可重跑。详见 [REPORT-I-R2](probes/prototype-selected-material-20261016/I-R2-QA/REPORT-I-R2-20261016.md)。
- **PM 决策（root 授权）**：**暂停盲重试/盲修循环**，先拆 **LG-048 零模型只读技术诊断**（**非 LG-049**；不新增 049 直到 PM 依据诊断选定下一任务）。诊断报告 [M-DELIVERY-DIAGNOSIS](probes/prototype-selected-material-20261016/M-DELIVERY-DIAGNOSIS/REPORT.md)。
- **诊断要点**：(a) 429 = 进程全局持久 8 硬上限（`LIGHTGRAVITY_MAX_GENERATION_CALLS=8`+持久账本），**非** per-node；(b) 默认文件交付规则计划 = **`deliver`+`verify` 双 SDK 节点**（非单 worker），与 docs/10 §7 措辞偏差，`verify`≠独立 ModelReviewer，**不假定移除 verify 已授权**；(c) 首个 SDK `1006` = QA harness 提前关闭，**非产品复现**；(d) reviewer/stop-gate/accept 未验证，后续预算提案 ≥15（含失败+reviewer，**未授权**）并须分列节点消耗。
- **实施进展**：042 冻结契约（`pi-proto-prepare`）→ 043 后端（A `6515e5c`）→044 前端（B `552d839`）/045 Demo（C `e36df29`）→ **046 串行整合候选** → **047 QA R1 FAIL** `57809d4` → F/G 并行返修 → H 串行集成候选 → 047 **独立 QA-R2 FAIL/INCOMPLETE** → J 分类器修复 `2352c52` 合入 `7e433c3` → **LG-048 诊断**。契约 [docs/10](docs/10-selected-material-prototype.md) + docs/08 §6.6.1，加性 MINOR **`1.12.0`**。
- **整合实际检查**：D 候选后端 `mypy` 139 files clean + `pytest tests/` **908 passed / 2 skipped**（EXIT 0）、前端 `tsc`/`vite build` EXIT 0；**R1 合并候选**后端 `mypy` 139 clean + **`pytest -q` 930 passed / 2 skipped**（EXIT 0，F+G 联合全量），前端未改动故未重跑；均无真实产品模型调用。
- **预算**：prep/A/B/C/整合/048 产品推理 0；**LG-R2 新增产品请求 8/8 已耗尽（不可重跑）**；R1 已知 1 次真实请求与失败样本单列保留，**不宣称原 12 次 campaign 全程已核实**；成本 unknown 非 0。
- **未宣告 R3 通过、未宣告累积成本已知**；LG-047 仍 `in-progress`（无 done）；**LG-049 保持 `in-progress`**（标 done 留待 root closure 复核报告）；**不改动 R2/I 活动 worktree/campaign/ledger**。

### 上一批次（2026-10-16，LG-040 RELEASE-CLOSE 收口；LG-040 done）

- 任务 CLI（**backlog 专用根** `/home/yhvh/code/lightgravity-bot/backlog`）：`validate` **41 tasks / 0 diagnostics**；`digest` **1 todo / 0 in-progress / 40 done**，complete=true；`ready=[]`；唯一 decision = LG-041（质量门）。
- **LG-040 已 `done`（版本 QA 技术验收；用户最终验收仍 PENDING、未发布）**：治理报告 `probes/lg040/TRANSITION-QA-20261016/REPORT.md`（候选 `30029eb`）**PASS_WITH_LIMITATIONS、0 个 open important issue**；收口顺序 `--no-ff` 合并 `925f828`/`8a4560a`/`30029eb`/`7fd0f61` 至 HEAD `7cc94b5`（无冲突）；`backend/`/`tests/`/`docs/` 自 `fc9f74b` 未变，产品增量仅 `frontend/src/app/shell.css`（transition CSS）。详情 [RELEASE-CLOSE REPORT](probes/lg040/RELEASE-CLOSE-20261016/REPORT.md)。
- **历史 8a4560a 明确不采信为收口**：其 `readyAtMs 2592` 用 8000ms 上界，仅作历史保留；修复后 `30029eb` 达标（零溢出 + 2s 几何就绪）。

### 上一批次（2026-10-16，Materials R7 集成；LG-035 done；历史保留）

- 任务 CLI（历史时点）：`validate` **41 tasks / 0 diagnostics**；`digest` **2 todo / 1 in-progress / 38 done**，complete=true；`ready=[]`。
- **R7 集成（2026-10-16）**：A `test/materials-fixtures-r7-20261016@f21d6e3`、B `fix/materials-layout-r7-20261016@8182d36`、C `investigate/materials-endpoint-r7-20261016@1cfa417`、D `test/materials-ocr-cohort-r7-20261016@97c4f8f`、E `fix/materials-table-mode-r7-20261016@4917413` 按序 `--no-ff` 合入 `main`（`89b0cc1`→`7eb88fe`→`e8a8e40`→`95b66bf`→`5f84503`）；合并候选 mypy 138 files clean、`pytest tests/sources` 147 passed/1 skipped；详见 [REPORT](probes/materials-r7-integration-20261016/REPORT.md)。
- **LG-035 已 `done`（待 LG-040 集中版本 QA）**：原始验收条件（真实清晰页、低质量诚实降级、多页、中文印刷、**真实 grid + 人工真值 + 可选表格模式**、混合、机器/正式分离）已由真实 receipt 覆盖。**历史表格 FAIL 保留**，不宣称统计级/全类质量通过。
- **done（历史未收口时点）**：LG-037（可选向量）——R7 取到首次完整真实排名（rank 7/10、margin 0.00037），但旧 R5 图片硬门 **FAIL 不变**、无跨模态质量结论（保留）。
- **todo**：LG-041（中文 ASR 质量锁，未解锁）；LG-040 已于本批次收口为 `done`（见上）。
- **LG-032 已 `done`（仅评估范围）**：独立封账 PASS；default 自主协作仍 **off**。契约 `1.11.0`、SDK `0.1.22`。
- 唯一 future block：候选资料服务**仅历史时点健康** + 跨模态质量未验 + ASR 质量门；续接见 [FINAL-CHECKPOINT/RESUME](probes/batch-20261016/FINAL-CHECKPOINT/RESUME.md)。

### 新真实质量证据（集成入 main，链接有效）

- **R4 OCR-scale 机制修复 + 有界复测**（[REPORT](probes/materials-ocr-r4-20261016/REPORT.md)，merge `575f84a`）：可选 `LIGHTGRAVITY_OCR_SCALE`（缺省 2.0 不变、非法拒绝）；Z2 第 2 页整页 CER 0.2991→**0.2508**、公平段 CER 0.3172→**0.2689** 仍 **> 0.25**、结构未验证 ⇒ **表格质量仍 FAIL**；Z1 印刷页 **0.0423** 通过；ASR/embedding 0 POST。集成说明见 [R4 集成 REPORT](probes/materials-r4-integration-20261016/REPORT.md)。

### 新真实质量证据（2026-10-16 集成入 main，链接有效）

- **retry r2 smoke**（[REPORT](probes/materials-retry-20261016-r2/REPORT.md)，merge `d2f733a`）：3/3 GET 200；2/2 POST；OCR 真实 Z1 **CER 0.0423 PASS**；embedding 768 维 finite；ASR 0 POST。
- **LG-040 gate-prep 独立审计**（[REPORT](probes/lg040/GATE-PREP-20261016/REPORT.md)，merge `ab78f37`）：r2 数字逐项复现；**QA-PLAN 非版本判定**。
- **quality r3 真实质量**（[REPORT](probes/materials-quality-20261016-r3/REPORT.md)，merge `d8edb22`）：16/18 POST；OCR **Z2 表格页 FAIL**；vector Recall@5 1.0 vs lexical 0.7（7 docs/7 queries，仅 indicative）。
- **R3 独立审计 + errata**（[REPORT](probes/materials-r3-audit-20261016/REPORT.md)、[ERRATA-DELIVERY](probes/materials-r3-audit-20261016/ERRATA-DELIVERY.md)，merge `dd1cc37`）：Z2 整页 CER 0.2948 复现、修正段 ≈0.3172 仍 FAIL；R3 段评分器有 bug、结构判据自创；渲染 ~144 DPI 非 300；**负向 top-5 非 ACL 泄漏**；图片向量可调用 ≠ 跨模态质量。

### 仍缺/未达标（不称全通过）

- **LG-040 未执行、未就绪**：单列印刷页 PASS，但**表格页 FAIL、混合 born-digital+扫描类缺失、跨模态检索质量未验**。
- **LG-041 阻塞**：真实 ASR 不可用/质量门未过。
- LG-037 负向 false hits 需报告，但**不以此关闭跨模态质量、不在同一 7 查询上校准阈值**。服务仅**记录时点健康**，非未来承诺。

本目录的任务是**开发 LightGravity Bot 的工作**，与未来产品的 Task/Run/Member 文件及 `lightgravity.bot/v1` 完全分开。

## 排期与执行原则

- [滚动排期](docs/06-roadmap.md)：按验收门推进，未承诺日历日期。
- P0：核心接口、SDK 风险与最小可操作闭环；P1：首版工作入口与设置、恢复和完整质量门。优先级不是权限，不代表依赖可跳过。
- 计划保持 todo；实际执行再 claim/更新状态。ready 是候选快照，不能作为任务已被领取或可自动后台执行的证据。
- 每项任务正文有验收与证据要求；未解决重要失败不置 done。

## A. 基础与探针

- [LG-001 冻结首版接口与状态契约](backlog/tasks/LG-001.md)
- [LG-002 建立可运行工程骨架](backlog/tasks/LG-002.md)
- [LG-003 验证 Antigravity SDK 核心能力](backlog/tasks/LG-003.md)
- [LG-004 实现 Markdown 事实源与可靠写入](backlog/tasks/LG-004.md)
- [LG-011 实现左侧导航与统一前端壳层](backlog/tasks/LG-011.md)

## B. 最小真实闭环

- [LG-005 实现角色与 SDK 资源配置编译](backlog/tasks/LG-005.md)
- [LG-006 实现 Antigravity Executor Adapter](backlog/tasks/LG-006.md)
- [LG-007 实现常驻消息路由与 Task 队列](backlog/tasks/LG-007.md)
- [LG-008 实现自动组队与依赖调度](backlog/tasks/LG-008.md)
- [LG-009 实现产物验证与人工验收](backlog/tasks/LG-009.md)
- [LG-010 验收最小真实开发闭环](backlog/tasks/LG-010.md)
- [LG-012 实现查询 API 与持久事件订阅](backlog/tasks/LG-012.md)

## C. 工作入口与设置

- [LG-025 实现模型设置与凭证后端接口](backlog/tasks/LG-025.md)
- [LG-026 实现底部 Settings 与模型接入页面](backlog/tasks/LG-026.md)
- [LG-013 接入 Task Chat 与真实看板](backlog/tasks/LG-013.md)
- [LG-014 实现 Files 与任务证据预览](backlog/tasks/LG-014.md)
- [LG-015 实现 Team 与 Resources 管理视图](backlog/tasks/LG-015.md)

## D. 恢复与质量

- [LG-016 实现暂停取消与中断恢复](backlog/tasks/LG-016.md)
- [LG-017 实现独立 QA 与有限返修](backlog/tasks/LG-017.md)
- [LG-018 实现隔离 worktree 与并行整合](backlog/tasks/LG-018.md)
- [LG-019 完善网页通知与断线重连](backlog/tasks/LG-019.md)
- [LG-020 实现启动检查与本地分发入口](backlog/tasks/LG-020.md)

## E. 首版验收

- [LG-027 验收模型设置与凭证生命周期](backlog/tasks/LG-027.md)
- [LG-021 完成前端状态与响应式验收](backlog/tasks/LG-021.md)
- [LG-022 执行首版端到端与故障验收](backlog/tasks/LG-022.md)
- [LG-023 完成单 agent 对照评估](backlog/tasks/LG-023.md)
- [LG-024 整理首版交付文档与发布准备](backlog/tasks/LG-024.md)

## F. 去中心化协作版本

- [LG-028 冻结去中心化协作契约](backlog/tasks/LG-028.md)
- [LG-029 实现任务发现与原子领取租约](backlog/tasks/LG-029.md)
- [LG-030 实现受控同伴交接与上下文传递](backlog/tasks/LG-030.md)
- [LG-031 整合去中心化执行与验证返修闭环](backlog/tasks/LG-031.md)
- [LG-032 验收去中心化版本并比较全生命周期成本](backlog/tasks/LG-032.md)

## G. 资料接入与 Embedding 版本

- [LG-033 冻结资料摄取与检索接口契约](backlog/tasks/LG-033.md)
- [LG-034 实现原件接收与可恢复摄取作业](backlog/tasks/LG-034.md)
- [LG-035 接入图片和 PDF OCR 与正式内容版本](backlog/tasks/LG-035.md)
- [LG-036 实现可重建词法索引与来源核验](backlog/tasks/LG-036.md)
- [LG-037 接入 EmbeddingGemma 2 可选多模态向量索引](backlog/tasks/LG-037.md)
- [LG-038 打通 Chat 资料接入与 Files 归档检索体验](backlog/tasks/LG-038.md)
- [LG-039 验证中文语音转写后端与质量](backlog/tasks/LG-039.md)
- [LG-040 集中验收资料接入与 Embedding 版本](backlog/tasks/LG-040.md)
- [LG-041 质量达标后接入中文转写与音频来源索引](backlog/tasks/LG-041.md)

## CLI

当前机器 PATH 未发现 olav-tasks，可使用已存在的本地构建，不为本次规划安装包：

```bash
node /home/yhvh/code/olav-tasks/dist/cli.js tasks list /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks ready /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot --json
```

绝对路径是当前开发环境入口，不是产品运行依赖。其他环境使用已安装的 `olav-tasks` 执行同等命令。

> **任务根约定**：本仓库开发任务的**实际根目录是 `backlog/`**（`olav.tasks/v1`，LG 编号），**不是项目根**。
> 对项目根跑 `validate` 会命中历史实验 `probes/agensh-orchestration-r2/runs/**` 既存样例的重复 frontmatter 键，属旧实验、非 backlog 任务。
> 正确命令（已核 41 tasks / 0 diagnostics）：`node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot/backlog --json`（`digest`/`ready` 同理，根为 `.../backlog`）。
