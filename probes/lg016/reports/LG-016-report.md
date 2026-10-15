# LG-016 实施记录：暂停、取消与中断恢复

- 日期：2026-10-15（UTC）
- worktree：`/tmp/lightgravity-worktrees/lg016`，agent `pi-lg016`
- 基线 commit：`b8251b5c63`（上轮 dirty；本轮已本地 commit，保留中断记录）
- 环境：Python 3.12.13、`.venv`；真实上游 DeepSeek `api.deepseek.com/v1`

## 0. 环境恢复说明（不是重新开工）

本包上一进程因 `/tmp` 配额耗尽（派工日志 writer `EDQUOT`）中断，**不是功能验收
失败**。恢复时：清理已完成任务的 gitignored 依赖释放 3.9GB；本 worktree、
`.venv`、全部 dirty 源改动与证据完整保留；HEAD 仍为 `b8251b5c63`，未提交、未
reset、未覆盖任何已有证据。日志改写到 home 缓存并过滤重复 delta。

恢复时发现中断残留的**残缺源文件**并如实修复（不是把不完整文件当通过）：

- `backend/lightgravity/coordinator/service.py::_open_run` 调用了**未定义**的
  `self._continuation_from(...)`，且返回类型注解与实际返回值不一致。该调用会让
  worker 循环对**所有** Task 抛 `AttributeError`，因而 pause/resume/cancel 的
  真实路径全部无法运行（`tests/control/test_api_actions.py` 两个用例超时）。
  已删除该未实现、也不应发明的 SDK continuation 调用，恢复 `_open_run -> str`
  并让新 Run 以空 `session_refs` 开始。**本轮（2026-10-15）已按已安装 SDK 能力真实实现跨 Run 原生会话续接**（见 §2b）：不是重新引入未定义的调用，而是用已安装 SDK 0.1.22 的 `SessionContinuationMode` + `conversation_id` + `save_dir`，且以专门的 `ContinuationPlanner` 安全判定点驱动。

## 1. 真实模型调用计数（诚实边界）

- 旧（中断进程）的真实调用数**无法完整核实**：中断前未见落盘证据，故按未知处理。
- 上轮恢复新增硬上限 4；本轮（续作）新增真实调用硬上限 **3**。
- 上轮实际：新增 4 次真实调用（一次 cancel/pause 真实闭环），证据
  `lg016-control-evidence.json` 保留。
- **本轮实际：新增 3 次真实调用**（原生续接探针：首次尝试因 workspace 路径错误
  为 0 次；第二次 1 次首回合；第三次 2 次首回合+续接回合），在硬上限 3 内。
  因已达上限，**未重复运行**控制探针（其路径上轮已过且证据保留）。
- 不主张精确历史总量，也不做不受限重试。
- 复用 006/010 既有证据：session `resume` 底层能力来自 LG-003 探针结论
  (`probes/lg003-antigravity/reports/LG-003-report.md` §保存/恢复)，本包未重复
  验证该底层能力。

## 2. 实现范围

| 文件 | 变更 |
|---|---|
| `backend/lightgravity/coordinator/continuation.py` | **新增** `ContinuationPlanner`：持久化非秘密原生会话标识（`conversation_id`+`save_dir`+`continuation_mode`+固定 `config_version`），只对「已确认暂停且 cleanup=done 且有完整原生标识」的旧 Run 判定 `resume`；中断/不确定一律 `recovery_required`，失败/取消/无标识为 `fresh`（新会话，不重放） |
| `backend/lightgravity/coordinator/control.py` | 新增 `ControlService`：pause/cancel 停确认门、resume/retry/reopen/enqueue 重排队；重排队时把停止的 Run 记到 Task `last_run`，保留可续接的原生会话源 |
| `backend/lightgravity/coordinator/recovery.py` | 新增 `RecoveryScanner`/`ProcessProbe`：重启核对进程/产物/副作用，不确定进 `recovery_required` |
| `backend/lightgravity/coordinator/service.py` | `request_control` 委派 `ControlService`；`start()` 先跑一次恢复扫描；`_open_run` 先用 `plan_continuation` 判定并写入新 Run 的 `continuation`；`_build_context` 把 `conversation_id`/`save_dir`/`continuation_mode` 传入 `ExecuteRequest`；Task 用稳定 `native-sessions/<task_id>` 作为原生存储；`_record_result_session` 持久化适配器**回合结束后**才产生的真实 `conversation_id`；`_apply_outcome` 增加陈旧 Run 守卫、保留 late pause 结果 |
| `backend/lightgravity/adapter/execution.py` | `ExecuteRequest` 新增加性 `continuation_mode` 字段（不改变冻结字段语义） |
| `backend/lightgravity/adapter/sdk_config.py` | `build_sdk_config` 支持运行时 `continuation_mode` 覆盖（映射到 SDK 原生 `SessionContinuationMode`），保留 RESUME 缺 conversation_id 的降级守卫 |
| `backend/lightgravity/adapter/executor.py` | 把 `request.continuation_mode` 透传给 SDK 配置；`session_state` 按实际 continuation 标注 |
| `backend/lightgravity/coordinator/dispatcher.py` | `DispatchContext` 透传 `continuation_mode` 到 `ExecuteRequest` |
| `backend/lightgravity/coordinator/graph.py` | 节点级 `ExecuteRequest` 同样透传 `continuation_mode` |
| `backend/lightgravity/api/tasks.py` | actions 接入 pause/resume/cancel/retry/reopen/enqueue；保留已 QA 的 accept/reject 幂等/revision/targetRun 分支 |
| `backend/lightgravity/coordinator/__init__.py` | 导出 control/recovery/continuation 类型 |
| `tests/control/**` | 32 项控制/恢复/续接单测（+ `test_continuation.py` 10 项） |
| `tests/adapter/test_sdk_config.py` | +2 项运行时 `continuation_mode` 覆盖到 SDK 原生 RESUME 的验证 |
| `tests/api/test_tasks.py` | 最小断言修正：resume 已实现，错误按真实 phase 返回（跨 owner，见 §5） |
| `probes/lg016/**` | 有界真实 SDK cancel/pause/close 与**原生会话续接**证据 |

## 2b. 跨 Run 原生会话续接（本轮补的实际缺口）

上轮遗留缺口：协调器不持久化 `conversation_id`，新 Run 不能续接同一原生会话，`_open_run` 曾因删除未实现的续接调用而在“newRun”上产生空 `session_refs`。本轮：

- `ContinuationPlanner.plan_continuation` 是唯一判定点，安全规则保守：只从 `paused` 且 `cleanup.status==done` 且带完整非秘密原生标识的 Run 续接；`recovery_required` 或 cleanup 非 done 一律拒绝自动续接；失败/取消/无标识为 `fresh`。
- 判定结果写入新 Run 的 `continuation`（非秘密：`conversation_id`/`save_dir`/`continuation_mode`/`config_version`/`source_run_id`/`decision`）。
- `_build_context` 把该三元组透传 `ExecuteRequest`→adapter→SDK 原生 `SessionContinuationMode.RESUME`。
- SDK 只在回合结束后才分配 `conversation_id`（`agent.conversation_id` 文档与实测一致），所以协调器从 **`ExecutorResult.session_ref`** 记录最终标识（仅 `session_started` 事件会丢失它）；`tests/control/test_continuation.py::test_final_result_session_ref_is_persisted_for_continuation` 固定该行为。
- 为防控制/worker 竞态导致“暂停丢失并被自动重放”，`_apply_outcome` 增加陈旧 Run 守卫，`_process_one` 仅在仍持有 `claimed` 时释放租约。

## 2c. Graph 节点级原生 session 数据流（主线补接线，2026-10-15 续作）

主代理核对发现的关键缺口：上轮只做了 **Run 级** 续接，而产品默认执行路径是
`GraphDispatcher`（一个 Run 是真实多节点图）。Graph 路径下每个节点的原生 session
标识被丢弃：`member.session_ref` 恒为 `None`，`outcome.result` 为 `None`（图聚合了
节点结果），因此 Run 级 `_record_result_session`/续接判定拿不到原生身份，实际续接
不可达。本轮做**有界补接线**，只改 Graph/Member 原生 session 数据流：

- **新增 `coordinator/session_flow.py`**（唯一数据流模块）：从可信终结源
  （`ExecutorResult.session_ref`，或可信终结事件）抽取**完整非秘密**原生 session；
  `record_node_session` 统一持久化到三处：执行节点的 `member.session_ref`、Run 的
  `node_sessions`（按 subtask 运行时 ID 的**节点映射**）、Run 的 `session_refs`（停止门
  用不透明 id）。幂等（按 `session_id`）；缺 `conversation_id` 时**不写**，不伪造身份。
- **`graph.py`**：`_Node` 增加稳定 `member_id`；`_apply_result` 对每个终结节点
  （passed/failed/cancelled）调用 `_record_node_session`；`_build_request` 用
  `_resolve_node_continuation` 把**该节点自己的** `conversation_id`/`save_dir`/原生
  `resume` 透传 `ExecuteRequest`，否则回落到 Run 级或 fresh 新会话——多变图不再把所有
  成员塞进同一个会话。
- **安全匹配（不降级）**：`node_session_for_resume` 只在 plan `key` + 节点 `config_hash`
  （含 `member_config_hash`）+ 稳定 `role_ref` + 原生 state 可续接 + 同时有
  `conversation_id`/`save_dir` 时返回；`config_hash` 漂移、成员/授权变更、`closed`、缺
  标识一律返回 `None`（fresh），**绝不**重挂旧会话。跨 Task/Run 授权、固定配置/credential
  pin、`recovery_required`/未知副作用规则均由既有 `plan_continuation`/`_config_drift` 保持。
- **Run 级回落**：`service._record_run_continuation_from_nodes` 在图聚合（无
  `outcome.result`）时从 `node_sessions` 派生 Run 级 `continuation`（首个带原生化身份的
  节点 + `primary_node_key`），使默认 Graph 路径暂停后的新 Run 能拿到非秘密续接源；
  `_build_context` 对 `decision == 'resume'` 把源 Run 实体作为 `DispatchContext.prior_run`
  交给图，节点级续接由此可用。
- **已完成节点/产物保留**：`completed_keys` 从 `node_sessions` 报告已 `passed` 的 plan key
  （连同 `member.session_ref` 与 `node_sessions` 里的产物版本引用），供上游调度避免静默
  从头重放；完整节点级跳过调度属 LG-008 图调度范围，本轮只保证原生会话不被 fresh 重放
  且节点身份/产物记录保留（见 §5 限制）。
- **测试**：`tests/control/test_graph_session_flow.py`（11 项）——纯函数（抽取需原生
  `conversation_id`、按 key/config/member 匹配、closed/缺失不续接、completed 报告）、
  `record_node_session` 幂等写入 Member+Run、真实 `Coordinator`+`GraphDispatcher`
  端到端 pause→resume，断言续接节点的 `ExecuteRequest.continuation_mode=='resume'` 且
  `conversation_id/save_dir` 等于**该节点自己**的旧会话（非 Run 级单一会话），以及双节点
  各自续接各自会话。

## 3. 局部检查（实际结果）

```bash
.venv/bin/python -m mypy          # Success: no issues found in 89 source files
.venv/bin/python -m pytest -q     # 431 passed, 4 skipped, 1 warning in 32.1s
.venv/bin/python -m pytest tests/control -q   # 43 passed
.venv/bin/python -m pytest tests/control/test_graph_session_flow.py -q  # 11 passed
```

本轮（Graph 数据流补接线）**未新增真实模型调用**：底层 SDK 原生续接已由上轮探针
（`resumed_same_conversation=true`）与 LG-003 证实，本轮按指令优先「局部 Graph
集成与保存/恢复映射测试」，用 `Coordinator`+`GraphDispatcher` 端到端单测验证续接
参数实际进入图构建的 `ExecuteRequest`，不重复底层探针，也不消耗新模型调用。

真实路径（bounded，复用上轮 cancel/pause 证据）：

```bash
# 上轮已完成并保留：真实 cancel→cancelled、pause→paused、真实 session close、无泄漏
probes/lg016/evidence/lg016-control-evidence.json   # model_calls_this_run=2, total=4, findings=[]
# 本轮新增：原生会话续接 2 次真实调用
DEEPSEEK_API_KEY=... .venv/bin/python probes/lg016/lg016_native_continuation.py \
  --max-proxy-calls 2 --model-calls-cap 4
# passed=true, model_calls_this_run=2, reported_session_state=resumed,
# resumed_same_conversation=true, same_save_dir=true
```

原始证据：`probes/lg016/evidence/lg016-control-evidence.json`、
`probes/lg016/evidence/lg016-native-continuation-evidence.json`。

### 本轮真实调用计数（诚实边界）

- 旧（中断进程）真实调用数仍无法完整核实，按未知处理；上轮控制探针 2 次为已记录历史。
- 本轮新增真实调用 **3** 次（原生续接探针两次运行：1 次首回合 + 1 次续接回合；首次尝试因 workspace 路径错误为 0 次），在新模型调用硬上限 3 内。
- 因此**未重复运行**控制探针（其 cancel/pause/close 路径上轮已通过且证据保留）；控制语义改动由单测覆盖。不主张精确历史总量，也不做不受限重试。

## 4. 验收条件对照

- **暂停/取消确认停止后更新，超时显示未确认及诊断**：真实 cancel→`cancelled`、
  pause→`paused` 且 `cleanup=done`、槽位 `not_queued`；未确认时保持
  `cancelling`/`pausing`、保留 Run 与恢复点、写 `cancellation_unconfirmed`
  诊断，返回 409（单测 + 真实 confirmed 分支）。
- **重启核对进程/产物/副作用，不确定进入 recovery_required**：`RecoveryScanner`
  对 dead/unknown worker 一律不自动重放，写 `recovery_required` 并记录原因；
  存活 worker 不动；终态 Run / 待验收 Run 释放残留 claim（单测 + 真实扫描）。
- **恢复排队无双 writer，等待/待验收停止后不占槽，清理失败独立记录**：resume
  经 store lease + `active_run` 守卫，最多一个非终止 Run；awaiting_acceptance/
  paused 停后释放 claim；cleanup 失败写 Run 字段 + `cleanup.updated(failed)` 事
  件，不掩盖已确认的停止，也不删除原始 diff/worktree/历史。
- **恢复同一 Task 的原生会话/剩余工作，不静默从头重放（本轮补齐 + 主线数据流）**：确认暂停后，
  新 Run 携带旧 Run 的非秘密 `conversation_id`+`save_dir`+`continuation_mode=resume`，
  SDK 原生续接同一会话（真实证据 `resumed_same_conversation=true`）；默认 `GraphDispatcher`
  路径下每个节点携带**自己**的原生标识续接（`tests/control/test_graph_session_flow.py`
  `Coordinator`+`GraphDispatcher` 端到端断言参数进入 `ExecuteRequest`）；`config_hash`/成员/授权
  不匹配则 fresh，不确定副作用的 Run 不自动续接，保持 `recovery_required` 并保留 Task ID/历史。

## 5. 真实限制与接线需求

- **shutdown 与用户取消区分**：`Coordinator.stop()` 只取消 worker 循环、不写任何
  Task 终态；中断遗留的 Run 由下次启动扫描判为 `recovery_required`（单测
  `test_shutdown_is_not_user_cancel`）。
- **跨 Run 的 SDK 会话续接已实现（本轮补齐）**：协调器现在持久化**非秘密**原生会话标识（`conversation_id`+`save_dir`+`continuation_mode`+固定 `config_version`），并只对可证明安全的「已确认暂停且 cleanup=done」旧 Run 用 SDK 原生 `SessionContinuationMode.RESUME` 续接同一 Task 的原生会话；不静默用初始目标从头重放已执行写副作用。真实证据：原生续接探针 `resumed_same_conversation=true`（§3）。
- **SDK 原生会话标识的实际语义（实测）**：SDK 在回合结束后才分配 `conversation_id`（`session_started` 时为空），因此协调器从 `ExecutorResult.session_ref` 记录最终标识；`save_dir` 为 SDK 原生 trajectory 存储目录。`conversation_id` 需满足 SDK 校验 `[a-zA-Z0-9-]` 且 ≥32 字符（`LocalOpenAIAgentConfig` 实测），协调器只存储适配器回报的值、不自行编造。
- **不确定副作用仍不自动恢复**：`recovery_required`/中断 Run/cleanup 未 done 的 Run，`_open_run` 拒绝开新 Run 并保持 `recovery_required`，需人工用 resume/retry/cancel 明确决定，不为 green 自动重放。
- **Graph 节点级数据流本轮已补齐（主线）**：每个真实节点从 `ExecutorResult.session_ref` 抽取完整非秘密 session，统一写入 `member.session_ref` + Run `node_sessions` 节点映射 + `session_refs`；确认暂停后新 Run 按 plan `key`/`config_hash`/`role_ref` 匹配，把**对应节点自己的** `conversation_id`/`save_dir`/原生 `resume` 透传 `ExecuteRequest`（端到端单测证明参数进入图构建的请求）。`tests/control/test_graph_session_flow.py` 覆盖。
- **完整节点级跳过调度仍属 LG-008 图调度范围（非本包引入）**：现有调度器在一个新 Run 里重新物化并执行所有节点；LG-016 保证续接节点走**同一原生会话**（非 fresh 重放），并以 `completed_keys` 与 `node_sessions` 保留已完成节点、成员 session 与产物版本引用，但“直接跳过已 passed 写节点”的图调度改动不在本轮 bounded 范围，已在 §2c 如实说明，未冒充已实现。
- **跨 owner 改动**：`tests/api/test_tasks.py` 属 LG-012；因 LG-016 实现了
  resume，原「resume 未实现」断言失效，做了 5 行最小修正。如需回退接线，请由整
  合执行者串行处理。
- **未重复运行**：控制探针（cancel/pause/close）本轮未重跑以避免超新模型调用硬上限 3；上轮真实证据保留，控制语义改动由 32 项控制单测覆盖。
- **未运行**：未做前端接线（LG-013 等）与逐任务独立 QA；首版 QA 由 027/021/022
  执行。未 push/deploy（本包按用户指令本地 commit）。

## 6. 续作补接线：稳定 reuse identity 与 anti-replay guard（2026-10-15）

上一执行者在 guard 模型请求长时间无输出时被 SIGINT；5 个 dirty 文件完整保留。
本轮不改 reset/覆盖，先 `git diff` 定位已有部分，再修复其已发现的真实逻辑缺陷并
完成最小必要闭环。**无新增真实模型调用**（底层 SDK 续接能力已由 §3 证据证实）。

### 6.1 已修复的真实缺陷：`config_hash` 含续接坐标

`CompiledAgentConfig.config_hash` 经 `member_config_hash` 进入 subtask 的
`config_hash`，而它折入了 session profile 的 `conversation_id`
（`ResourceCompiler._compile_session` → `CompileConstraints.conversation_id`）。
恢复时新 Run 的会话坐标与旧 Run 不同，故该 hash **必然**不同，原「按
`config_hash` 比较复用/续接」永远失配 —— 该失配不能退化成 fresh 重放写副作用。

修复（计划 B，最小面）：为节点计算并持久化**稳定 reuse identity**——由 plan spec
（key/objective/capability/acceptance/depends_on/write/order）+ 有效 member
角色/tool/skill/连接 pin/权限（allowed_tools）/capability/模板版本组成，**排除**
`conversation_id`/`save_dir` 这类续接坐标。实现上用中性
（`conversation_id=None`）`CompileConstraints` 重编译取值，不改全局
`compile_agent`/`config_hash` 语义。`NodeSession.reuse_identity` 随 session 持久化，
`reusable_completed_node`/`node_session_for_resume` 改比较该值（旧记录无该字段时
回退 `config_hash`，保持严格）。关键字段（模型/连接/workspace/工具/技能/模板/
权限）漂移**仍**改变 identity，不会被掩盖；Task 总预算仍受约束。

### 6.2 anti-replay guard 语义

恢复 Run 若旧 Run 存在已 `passed` 的写节点：能通过上述稳定 identity + 冻结
handoff（content hash + artifact refs）证明可复用时，标记跳过复用产物、**不重执行、
不产生新写**；否则 fail-closed 返回显式 `recovery_required`，且**不派发任何节点**
（尤其不再 execute 已完成写节点 A）。配置/计划/权限漂移、closed session、缺可信原生
标识或未知副作用一律不得静默 fresh 重放。fresh 仅用于被证明未执行/用户明确新尝试。

### 6.3 本轮检查（有界、无真实模型调用）

- `uv run mypy` → **Success: no issues found in 89 source files**。
- `uv run pytest -q` → **434 passed, 4 skipped**（原 431 passed；新增 3 项 guard/identity 集成测试）。
- `tests/control/test_graph_session_flow.py` → **14 passed**，含两个核心断言：
  1. `test_reuse_identity_stable_across_conversation_coordinate_change`：用**真实
     `GraphDispatcher` + 真实 `ResourceCompiler`**（非固定 hash 的 fake）证明仅移动
     恢复会话坐标时稳定 identity 不变，而权限收窄（`tool_refs=`）时改变；同时断言原始
     `compiled.config_hash` 随坐标变化（确认所防缺陷真实存在）。
  2. `test_coordinator_resume_without_trusted_reuse_fails_closed`（端到端 `Coordinator`）
     与 `test_no_trusted_reuse_blocks_resume_without_redispatch`（dispatcher）：已完成写
     节点无可信复用时 resume 显式 `recovery_required`，且 A 不被再次 execute。
- 无新增真实模型调用；控制探针未重跑（路径上轮已过、证据保留）。

### 6.4 明确保守拒绝的剩余功能

完整 checkpoint 复用/节点级 skip 调度仍**未实现**；本轮以保守、显式
`recovery_required` 拒绝不安全 resume，不等价于通用 checkpoint 复用，也不自称大版本
QA 通过。安全限制：identity 只覆盖上述关键字段，不覆盖运行期用量/连接凭据版本等
非配置维度，故仅作**复用准入**用途，不扩大任何权限。

## 7. 状态

按自身验收条件实现（含跨 Run 原生会话续接 + 节点级 anti-replay guard）并附真实
关键路径证据；本轮已本地 commit（保留中断记录）。标 **in-progress → 待首版 QA**
（`awaiting version QA`），不宣称版本验收通过。
