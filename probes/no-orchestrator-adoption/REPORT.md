# no-orchestrator-adoption — REPORT

- worktree: `/tmp/lightgravity-worktrees/no-orchestrator-adoption-20261015`
- branch: `experiment/no-orchestrator-adoption-20261015`
- base HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- integration: copied to main working tree by exact whitelist; **no commit / no stage / no push / no publish**
- product real SDK/DeepSeek calls in this package: **0**（没有启动新的真实付费 SDK 对比）
- 本包为执行者自检，**未做独立版本 QA**，不宣称版本 QA 通过

## 1. 现状调查（真实默认装配）

| 问题 | 调查结论 | 证据 |
|---|---|---|
| 是否存在“独立常驻编排模型”？ | **否**。默认装配从不构造任何模型 planner。 | `bootstrap.build_runtime` 构造 `GraphDispatcher(...)` **未传 `planner=`**；`GraphDispatcher.__init__` 走 `planner or RuleBasedPlanner()`（base 版 `coordinator/graph.py`） |
| 是否有“每次必经的模型规划”？ | **否**。默认计划是程序规则：一个 `deliver` 写节点，有 acceptance 时追加依赖它的 `verify` 节点；不调用模型。 | `RuleBasedPlanner`（`coordinator/planner.py`） |
| 是否存在“模型提议接口”？ | 存在但**从未接线**：`ModelPlanner` 仅在调用方注入 `propose` callable 时可用；无默认装配、无 env 开关、无真实模型后端。 | 全仓 grep：生产代码无 `new ModelPlanner`，无 `planner=` |
| 是否有一条不经计划图的直接交付路径？ | 是 `SingleSlotDispatcher`（planning→recruiting→executing 直接调 executor，不写 plan 快照），但 bootstrap 未用它，bootstrap 用 `GraphDispatcher`。 | `coordinator/dispatcher.py` |

**重要澄清：原系统不存在可被删除的“LLM 常驻编排实现”。** 本包做的是：把程序计划职责说清楚、把“模型提议”从架构必备降级为有界按需，并防止注入的模型 planner 变成每 Run 必经。

### 保留且未改动的程序控制边界

- `PlanValidator`：key slug/重复/依赖无环/能力存在/acceptance 非空/write 需 workspace 边界。
- `GraphDispatcher`：把校验通过的 `plan`/`plan_hash`/`plan_source` 写入 Run 快照。
- 程序原子写/租约：`SubtaskClaimer` + `StateWriter`/`RunController`，SoT 只在 frontmatter。
- worker 不能写控制态：executor 只 `emit`，控制写入只经 `RunController`/`Store`。
- 机器验证 / 独立复核 / 人工验收（`verify/**` + `_auto_verify`）、停止确认（cancel 需 adapter 确认）。
- SDK 内部委派关闭：`sdk_config.py:enable_subagents=False`、`capabilities.subagents=False`、compiler 标 `subagents_disabled`；`invoke-subagent`/`run-workflow` 仍 unavailable。

## 2. 具体变化

1. **新增 `coordinator/planning.py`**：`PlanningTrigger`（`user_request`/`ambiguous_requirement`/`blocked`/`repair_cap`）与 `PlanningRequest`（`trigger`、非空 `reason`、`requested_by`、有界 `max_calls`，构造即校验）。只定义有界按需请求契约，不含模型调用，不建隐藏编排循环。
2. **`DispatchContext` 新增内部字段 `planning_request`**（默认 `None`）。这是 Python 内部 seam，不是 HTTP/wire 契约字段。
3. **`GraphDispatcher` 默认程序计划，模型提议按需**：
   - 无注入 planner：永远用程序 `RuleBasedPlanner` 生成最小合法计划（`plan_source=rules`）。
   - 注入了 planner：**仅当** `context.planning_request` 存在时才调用，且每个 Run **最多一次**；否则仍走程序计划。
   - 按需采纳时把 `trigger`/`reason`/`requested_by`/`max_calls` 冻结进已校验计划的 `notes`（可审计）；候选计划仍经同一 `PlanValidator`。
   - 新增只读属性 `GraphDispatcher.planner`（默认为 `None`）。
4. **`ModelPlanner` 语义收口**：docstring 明确“未接线的注入式提议接口、无真实模型后端、非默认装配”，默认 `max_calls` 由 2 降为 1。
5. **文档同步**：删除“每个交付必经 Planner→Recruiter→…”的字段/图/流程冲突，区分程序控制与模型能力；成本判据改为同一验收门下的全交付生命周期。

### 契约版本判断

- **无 wire schema / API / 事件 / 错误码 / 枚举 / 状态迁移变更**，因此 `CONTRACT_VERSION` 保持 `1.5.0`，不升版。
- 变化属**纯默认策略/架构澄清**：已在 `docs/08` §6.2 `plan_source` 注记“默认策略澄清，不新增字段/端点/事件，不改变本版既有语义”，并在 `agent.md`、README、docs/01/02/03/04 记录。
- `PROJECT.md` 由主代理 owner，本包**未改**；主代理应把“采用无独立编排、规划为按需能力”的产品决策与成本判据写入 PROJECT.md。

## 3. 改 / 增文件列表（精确白名单，已逐文件 sha256 校验后覆盖）

修改（8 代码/测试 + 5 文档 + agent.md/README）：
- `backend/lightgravity/coordinator/dispatcher.py`
- `backend/lightgravity/coordinator/graph.py`
- `backend/lightgravity/coordinator/planner.py`
- `backend/lightgravity/coordinator/__init__.py`
- `tests/coordinator/graph_helpers.py`
- `tests/coordinator/test_graph_dispatcher.py`
- `README.md`
- `agent.md`
- `docs/01-design.md`
- `docs/02-task-and-sdk-resources.md`
- `docs/03-sdk-capability-audit.md`
- `docs/04-bot-behavior.md`
- `docs/08-interface-contract.md`

新增：
- `backend/lightgravity/coordinator/planning.py`
- `tests/coordinator/test_planning.py`
- `probes/no-orchestrator-adoption/PROGRESS.md`、`REPORT.md`、`logs/main-integration.log`（本工作记录）

未触碰：`PROJECT.md`（主代理 owner，主目录原有 dirty 保留）、四个旧 `probes/agensh-orchestration*`（未跟踪，原样保留，**未提交/未暂存/未删除**）、其它 worktree/分支、`.env`。

## 4. 默认行为 / 按需能力的实际状态

- **产品默认（`bootstrap.build_runtime`）**：`GraphDispatcher` 无 model planner；明确目标由程序生成最小合法计划并直接派发 worker。默认路径**不依赖任何 planner 模型**。
- **模型按需规划**：接口（`PlanningRequest` + 注入式 `ModelPlanner.propose`）保留；**真实模型后端未实现、未接线、无用户可见触发端点**。`probes` 中的纠正版 SDK 是独立实验，不是产品按需规划实现。
- **不能声称的能力**：不能声称已有“用户请求拆解即调用模型规划”的产品功能；当前只有内部有界 seam + 触发/原因记录契约。
- 保留：计划校验、程序原子写/租约、SoT、机器验证/独立复核/人工验收、停止确认、SDK 内部委派关闭、worker 不写控制态。

## 5. 测试（命令 / cwd / 退出码）

worktree 自检（`cwd=/tmp/lightgravity-worktrees/no-orchestrator-adoption-20261015`，PYTHONPATH 指向 worktree backend）：

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m mypy` | 0 | Success: no issues found in 86 source files |
| `.venv/bin/python -m pytest -q` | 0 | 394 passed, 4 skipped |

集成后主目录自检（`cwd=/home/yhvh/code/lightgravity-bot`，日志 `probes/no-orchestrator-adoption/logs/main-integration.log`）：

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m pytest tests/coordinator/test_planning.py tests/coordinator/test_graph_dispatcher.py -q` | 0 | 18 passed |
| `.venv/bin/python -m pytest tests/contracts -q` | 0 | 7 passed（版本仍 1.5.0） |
| `.venv/bin/python -m pytest tests/verify/test_verify_graph_integration.py tests/api -q` | 0 | 52 passed |
| `.venv/bin/python -m mypy` | 0 | Success: no issues found in 86 source files |
| `.venv/bin/python -m pytest -q`（全量） | 0 | 397 passed, 1 skipped（基点 389 passed/1 skipped，+8 为本包新增用例） |

新增用例覆盖：默认路径即使注入 planner 也 **0 次调用**（程序计划）；显式 `PlanningRequest` 时 planner **恰好 1 次**且 `trigger/reason` 写入计划快照；默认 `GraphDispatcher.planner is None`；`PlanningRequest` 触发枚举与 reason/max_calls 校验。

**未运行 / 已知诊断**：`olav-tasks tasks validate .` 退出码 1，12 条 `Invalid YAML` 全部位于**未跟踪的历史实验** `probes/agensh-orchestration-r2/**`（PROJECT 已记录的 `lease_path: -` 旧问题），**非本包引入**，且按“不修改旧实验原始结果”要求保持原样；backlog 任务 0 诊断。

## 6. 成本判据（准确引用，无新付费实验）

- 同一验收门下的**全交付生命周期**口径：执行＋验证＋返修＋复验＋失败尝试；未完成样本不得计作已交付成本，不用失败高成本样本的中位数推断完整收益（已写入 README、agent.md）。
- 已完成真实 SDK 纠正版（`probes/agensh-orchestration-sdk-corrected/REPORT.md`）：按 run 级**代码验收** B 2/3、C 3/3；relay reported tokens 合计 **B 441,700 / C 403,523**；中位/run 改善 8.84% tokens、3.16% 时间，均 < 15% 门。
- 纠正版正式 51 turn 中 44 succeeded、7 `budget_exhausted`/`failed`；**只有固定轮次代码检查，全生命周期 QA 未补跑**。
- 结论：**不能宣称完整成本 15% 优势已经证实**；也不反向宣称“独立 planner 无收益”。本包不启动新的真实付费 SDK 对比。

## 7. 已知限制与待版本 QA

- 不宣称版本 QA 通过；集中独立版本 QA 仍按现有里程碑（LG-021/022/027）。
- 真实模型按需规划**未实现**：仅有注入式 seam 与请求契约，无模型后端、无用户可见触发端点、未接 SDK。
- `planning_request` 目前只在进程内 `DispatchContext` 上传递，未持久化、未暴露 HTTP；跨进程重启会丢失未消费的按需请求。这是有意的最小实现，避免为未实现的模型能力新增持久 schema。
- 四个旧 `probes/agensh-orchestration*` 与 PROJECT.md 的原有 dirty 保持原样；工作记录不含任何密钥。
- 前端未改动（无需 design.md 流程）。
