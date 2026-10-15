# no-orchestrator-adoption — PROGRESS

worktree: `/tmp/lightgravity-worktrees/no-orchestrator-adoption-20261015`
branch: `experiment/no-orchestrator-adoption-20261015`
base HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
date: 2026-10-15

## 现状调查（第一步，先于实施）

### 真实默认装配（`backend/lightgravity/api/bootstrap.py:build_runtime`）

- `build_runtime` 构造 `GraphDispatcher(store, executor, catalog=..., compiler=..., connections=...)`，
  **没有传 `planner=`**。`GraphDispatcher.__init__` 因此走 `planner or RuleBasedPlanner()`
  （`coordinator/graph.py:140`）。
- `RuleBasedPlanner`（`coordinator/planner.py:267`）是**确定性程序计划**：总是产生一个
  `deliver` 写节点；当 Task 有 acceptance 时追加依赖它的 `verify` 节点。**不调用任何模型**。
- `ModelPlanner`（`coordinator/planner.py:320`）只在 `propose` 可注入时存在；`propose` 是调用方
  提供的 callable，SDK/DeepSeek 后端**未实现、未装配、无默认开关、无 env 配置**。
  `grep` 全仓：生产代码没有任何地方 new `ModelPlanner`，也没有 `planner=`。
- `RoleCatalog`/`Recruiter` 是能力→agent 的程序匹配（`recruiter.py`），非模型。
- `SingleSlotDispatcher`（`dispatcher.py`）是真正“直接单 agent 交付”路径（planning→recruiting→
  executing 直接调 executor，不写 plan 快照），但 bootstrap 未用它，bootstrap 用 GraphDispatcher。

**结论：当前默认架构里不存在“独立常驻编排模型”，也没有每次必经的模型规划调用。**
存在的是：程序计划/校验/招募/调度 + 一个从未接线的模型提议接口。

### 保留的程序控制边界（不能误删）

- `PlanValidator`（planner.py）：校验 key slug/重复/依赖无环/能力存在/acceptance 非空/write 需
  workspace 边界，通过后才生成 `Plan`。
- `GraphDispatcher` 把 `plan`/`plan_hash`/`plan_source` 写入 Run 快照；程序原子写/租约
  （`SubtaskClaimer` + `StateWriter`/`RunController`），SoT 只在 frontmatter。
- worker 不能写控制态：executor 只 `emit`；控制写入经 `RunController`/`Store`。
- 机器验证/独立复核/人工验收（`verify/**` + auto-verify）、停止确认（cancel 需 adapter 确认）。
- SDK 内部委派关闭：`sdk_config.py:enable_subagents=False`、`capabilities.subagents=False`、
  compiler 对 `subagents` 标 `subagents_disabled`；`invoke-subagent`/`run-workflow` 仍 unavailable。
- `Run` 初始 state=`planning`、Task phase=`planning` 由 `Coordinator._open_run` 写；这是程序流程，
  非模型前提。

### 冲突点（文档层面）

- `docs/01` §3 架构图与 §4 表把 `Planner` 列为必经组件；§7 步骤 2 “生成并校验计划”读起来像
  每个交付的运行前置。实际默认是程序规则计划。
- `docs/01` §4/§5、`docs/04` §3 用 “Planner 可以建议…” 的措辞，未区分“程序最小计划”与
  “模型提议”。
- `docs/02` §3 “计划只在 PLAN.md 声明…” 与 Run `plan` 快照并存，措辞需统一到 program/model。
- `agent.md` §3 “Planner 提出计划；Recruiter 选择…” 未标注 Planner 默认是程序规则。
- README “完成定义” “交付指令形成可校验计划” — 可保留，但需说明计划由程序生成/校验。

### 成本判据（用户要求）

- 纠正版真实 SDK 已完成：`probes/agensh-orchestration-sdk-corrected/REPORT.md`
  §3 表与 §9：按 run 级**代码验收** B 2/3、C 3/3；分项合计 relay tokens B 441,700 / C 403,523
  （§5 分项表）。中位/run 8.84% tokens、3.16% 时间，均 < 15% 门。
- 只有**固定轮次代码检查**，全生命周期 QA（执行+QA+返修+复验+失败尝试）**未补跑**，
  B 有 7 个 turn `budget_exhausted`。**不能宣称完整成本 15% 优势已证实**。
- 本包不启动新的真实付费 SDK 对比。

## 实施计划

1. 把“模型提议”明确降级为**有界按需**：注入 `planner` 时默认不每 Run 调用；仅当
   `DispatchContext.planning_request`（trigger+reason，同一 Run 内单次、有调用上限）存在时才调用；
   否则程序构建最小计划。默认（无注入）永远程序计划。
2. `ModelPlanner` 文档标注“未接线、无真实模型后端、注入式提议接口”。
3. 计划快照/校验/租约/SoT/验证/验收/停止确认全部保留。
4. 同步 agent.md、README、docs/01、docs/02、docs/04、docs/08；删除“必经 Planner→Recruiter→…”
   的冲突表述，区分程序控制与模型能力。PROJECT.md 主代理 owner，本包不改。
5. 更新成本判据表述（agent.md/README/docs），准确引用纠正版数据。

（后续实施进展追加在本文件下方。）

## 实施结果（已完成，集成到主目录，未提交）

- 新增 `backend/lightgravity/coordinator/planning.py`：`PlanningTrigger` + `PlanningRequest`（有界、须有 reason）。
- `DispatchContext.planning_request`（内部 seam，默认 None）。
- `GraphDispatcher`：默认程序最小计划；注入 planner 仅在有 `planning_request` 时按需调用一次，trigger/reason 写入已校验计划快照；新增 `planner` 只读属性（默认 None）。
- `ModelPlanner` 默认 `max_calls=1`，docstring 标注未接线/无真实模型后端。
- 文档：agent.md、README、docs/01、02、03、04、08 去冲突并区分程序控制 vs 模型能力；成本判据改为全交付生命周期。
- 契约版本保持 `1.5.0`（无 schema/API/事件/枚举变更）；PROJECT.md 未改（主代理 owner）。
- 测试：worktree mypy 0 / pytest 394 passed,4 skipped；主目录集成后 mypy 0 / pytest **397 passed,1 skipped**；聚焦日志 `logs/main-integration.log`。
- 未提交、未暂存、未推送、未发布；未删旧实验/worktree；无新真实 SDK/DeepSeek 调用。
- 详细见同目录 `REPORT.md`；diff 见 `no-orchestrator-adoption.patch`。
