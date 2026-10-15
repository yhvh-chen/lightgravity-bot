---
title: "LG-028 去中心化协作契约准备稿（未冻结）"
doc_type: preparation
category: architecture
status: draft-preparation
updated: "2026-10-16"
---

# LG-028 去中心化协作契约准备稿

> **性质：准备稿，非契约冻结。** 本文件不修改也不替代 [docs/08 接口契约](../../docs/08-interface-contract.md)，
> 不提升 `CONTRACT_VERSION`（当前 `1.5.0`），不定义已冻结语义。正式冻结必须由**单一 docs08 owner**
> 按 docs/08 §13 变更控制升版并处理共享契约冲突。本文件的目标是：把 LG-028 四项验收条件收敛为
> **可直接抄入 docs/08 的加性候选**，并给出字段名、端点、事件、错误码、状态迁移、反例与 LG-029/030/031
> 的可实施 owner 拆分，使后续实现无需再回退做契约调查。

## 0. 执行基点与限制（准备者声明）

- 归属：本文件与 [probes/lg028/PREPARATION.md](../../probes/lg028/PREPARATION.md) 由 `agent:pi-lg028` 独占写入；其余文件只读。
- 分支：`dev/lg028-contract`；基点 `b2bd5eb`（main + LG-028/033 claim），HEAD 含 main，未触碰主 worktree 或其它分支。
- 输入：AGENTS.md、agent.md、PROJECT.md、PROGRESS.md、BACKLOG.md、docs/06（第 6 节）、docs/08（1.5.0 全文）、docs/09、backlog/tasks/LG-028/029/030/031/032、LG-016/017/018，以及现有实现只读引用：`store/store.py`（`claim`/`renew`/`release`）、`coordinator/scheduler.py`（`SubtaskClaimer`/`ArtifactHandoff`）、`coordinator/graph.py`（节点领取/交接）、`store/protocol.py`。
- 参考实现（按 agent.md §9 先定位）：Olav OS `run-store.ts`（lease/`recovery_required`/ fencing 外部调用）与 `scheduler.ts`；只读取接口语义，不引入数据库权威、不复制其架构，不修改参考仓库。
- **未做**：不改 docs/08、不改版本常量、不改任务状态、不新增 API/schema/事件落地、不写产品代码、不跑产品测试、不做模型调用。
- **不可假设**：完整 checkpoint skip **尚未实现**；SDK 内部委派默认关闭；无独立编排是当前默认（`plan_source=rules`），模型提议仅按需且有界。
- 版本建议：**由集成者基于实际落地变更判定**。若本稿全部字段/端点/事件以“加性可选”方式实现，建议 MINOR（如 `1.6.0`）；若改变既有状态迁移方向或错误码语义则为 MAJOR。本稿不预判、不代冻。

## 1. 设计不变量（冻结前必须保持）

1. **程序是唯一控制权威**：worker 只能**提议**（发现→请求领取、请求协作、请求交接、上报结果）；权限状态、预算、验收的判定与写入由 Store/Coordinator/Scheduler/Verifier 程序执行。**不引入常驻模型编排 agent**，模型提议必经同一程序校验。
2. **文件 SoT 不变**：Task/Run/Subtask/Member 状态只在 frontmatter；`events.jsonl`/`conversation.jsonl` 追加历史；索引/看板/向量均只是可重建派生。
3. **默认路径兼容**：现有确定性调度（`plan_source=rules`，程序按依赖顺序执行）保持为默认且不受本扩展破坏；去中心化路径为**可选能力**，默认关闭（见 §8）。
4. **单一 writer**：同一文件同一时间一个写入者；跨文件不宣称事务；控制文件仅经 Store 写。
5. **预算与验收门不变**：所有协作/领取消耗进入同一 Task/Run 预算；worker 自报成功只进入验证，不直接 `passed`/`done`；人工验收不可绕过。
6. **未知副作用不自动重放**：租约到期不等于执行已停止；有副作用的节点不得因租约过期自动重复执行。

## 2. 验收条件 1：可发现范围、能力匹配、候选请求与程序原子授权、租约/撤销

### 2.1 可发现任务范围（discovery scope）

- worker 只能**发现**对其实例授权的候选集合。候选来源为 Run 已校验计划（`Run.plan`）中 **`state=ready` 或可立即就绪** 的 Subtask，且满足：
  1. 所属 Task `active_run` 指向该 Run，且 Task `phase ∈ {executing, repairing}`；
  2. 该 Subtask `state ∈ {ready, pending}` 且 `depends_on` 已 `passed`；
  3. `write=true` 的节点在**同一 workspace** 无其它活跃 writer（§7 单 writer）；
  4. 未被暂停/取消（Task `phase ∉ {pausing, paused, cancelling, cancelled}`，Run `state ∉ {pausing, paused, cancelling, cancelled}`）；
  5. 能力匹配（见 2.2）且剩余预算充足。
- **不可发现**：未授权 Task/Project、跨 Task 的 Subtask、已终结（`passed`/`failed`/`cancelled`）节点、`blocked_by` 非空节点、被其它 owner 持有效租约的节点。
- 发现接口为**只读投影**，不带控制副作用；不得因发现动作写状态或消耗预算。

### 2.2 能力匹配（capability match）

- 匹配维度按优先级：`capability`（来自计划节点，必填匹配）→ `role_ref`/`skill_refs`（Member 已解析配置）→ `tool_policy`（所需工具子集必须被 Member 授权）→ workspace 授权范围。
- 匹配由**程序**计算（确定性），不使用模型判断。建议产出布尔匹配 + 缺失项列表（供 `discovery` 响应与诊断）。
- Member 声明的 `enabled` 不等于可用；匹配前须确认连接/凭证可编译（`CompiledAgentConfig.executable`）与 `connection_pin` 未漂移；否则该 Member 不参与候选，不得静默降级。

### 2.3 候选领取请求（claim request，worker → program）

- worker 只提交**候选请求**，不写控制状态。建议加性实体 `ClaimRequest`（非冻结名）：

```yaml
schema: lightgravity.bot/v1
kind: claim_request
id: req_01J...            # 服务端生成的 req_<ULID>（§3.1）
task_ref: task_01J...
run_ref: run_01J...
subtask_ref: subtask_01J...
member_ref: member_01J...
requested_lease_seconds: 300
capability: developer          # 与计划节点 capability 一致，供程序复核
expected_subtask_revision: 4   # 乐观并发：请求基于的 Subtask revision
request_id: req_01J...         # 幂等键（客户端/服务端统一）
at: "2026-10-16T00:00:00Z"
```

- 请求为**提议**；程序复核后才有归属。`request_id` 幂等：同键重复提交返回首次 `ClaimOutcome`，不重复授予、不重复计数。

### 2.4 程序原子授权（atomic grant）

程序（Scheduler/Coordinator）在**单一临界区**内完成：复核发现条件 → 复核能力/预算 → 原子写租约。参考现有 `SubtaskClaimer.claim`（`coordinator/scheduler.py`）与 `Store.claim`（`store/store.py`）：读-改-写期间持实体文件锁（`fcntl.flock`），冲突抛 `lock_conflict`（可重试）。

建议 `ClaimOutcome`（加性，直接沿用现有字段形状）：

```yaml
acquired: true                 # false 时携带 reason
subtask_id: subtask_01J...
state: acquired                # acquired | already_owned | expired_reclaimed | held_by_other | terminal | ineligible
owner: member_01J...           # 租约持有者（Member 实例，非 worker 自报身份）
lease_expires_at: "2026-10-16T00:05:00Z"
fence: 7                       # 见 2.5（加性，单调递增）
reason: null
```

- 授权结果必须**不依赖 worker 自报身份**：`owner` 由程序按已注册 Member 推导；worker 不能指定任意 owner。
- 授权是**全有或全无**：条件不满足返回 `acquired=false` + 稳定 `reason`（不抛未捕获异常），不产生部分写入。

### 2.5 租约、fencing 与撤销（lease / fencing / revoke）

- **租约字段**（沿用现有 Subtask `owner`/`lease_expires_at`，加性新增 `fence`）：`owner`（Member 引用）、`lease_expires_at`（ISO-8601 UTC）、`fence`（整数，单调递增；每次成功授予/回收 +1，旧持有者写回携带的 `fence` 必须等于当前值）。
- **续租**：`renew(subtask_ref, owner, lease_seconds)` 仅在 `state=running ∧ owner==owner ∧ 未过期` 时成功；参考 `store.renew`/`SubtaskClaimer.renew`。返回布尔，不抛。
- **过期回收**：`lease_expires_at <= now` 时，程序可将租约回收并授予他人（`state=expired_reclaimed`）。**回收仅表示可重新授予，不表示原执行已停止**：对 `write=true` 或未知副作用的节点，回收不得触发自动重跑，须进入 `recovery_required`（§5.3）。
- **撤销（revoke）**：Task 暂停/取消、Run 终止、Member 释放、配置漂移（`config_invalid`）、预算耗尽时撤销租约：程序写 `owner=null`、`lease_expires_at=null` 并 `fence+1`。撤销后旧持有者的任何写回因 `fence` 不匹配而**被拒绝**（fencing 拒绝，非 last-write-wins）。
- **fencing 校验点**：Subtask 状态写回、产物交接、事件 emit、Member 释放均须校验调用方 `fence == current fence`；不匹配返回 `stale_lease`（新增错误码，见 §6），不落盘。
- **与既有契约关系**：不改变 docs/08 §6.3 Subtask `state` 枚举与迁移；`fence` 与 `ClaimOutcome` 为加性字段。

### 2.6 反例（必须被拒绝或如实降级）

| 反例 | 期望行为 |
|---|---|
| 两个 worker 同时请求同一 ready 节点 | 仅一个 `acquired=true`；另一个 `held_by_other`（可重试），无重复执行 |
| worker 提交超出其 Member 能力的节点 | `ineligible`（能力不符），不授予 |
| worker 领取 `blocked_by` 非空节点 | `ineligible`/`not_ready`，不授予 |
| 预算已耗尽仍请求 | `budget_exhausted`，不授予 |
| 未授权 Task 的节点 | 不可被发现；即使直接请求也 `not_found`/`unauthorized` |
| 旧持有者在租约被回收后用旧 `fence` 写回 | `stale_lease`，拒绝，不覆盖新持有者 |
| 租约过期但节点有写副作用 | 不自动重跑，进入 `recovery_required` |
| 同一 `request_id` 重复领取请求 | 幂等，返回首次结果，不重复计数 |

## 3. 验收条件 2：并发冲突、过期 fencing、暂停取消、崩溃恢复、幂等交接

### 3.1 并发领取冲突

- 竞争在同一临界区串行化：`flock` + `expected_subtask_revision` 乐观并发。并发写返回 `lock_conflict`（可重试）或 `revision_conflict`（须重读），二选一由实现明确并冻结，不得两者混用。
- 冲突**不得**以 last-write-wins 解决；不得因冲突产生重复执行或重复事件。

### 3.2 过期 fencing

- 见 §2.5。关键：**过期 ≠ 停止**；fencing 是防止“僵尸执行者”污染新归属的唯一机制。事件中记录 `fence` 与 `owner`，便于审计与重放。

### 3.3 暂停 / 取消

- 与 docs/08 §9 一致：动作先阻止新调度，再调 adapter `cancel`；`confirmed=false`/超时返回 `cancellation_unconfirmed`，Task 阶段保持 `cancelling`/`pausing`，**绝不**写 `cancelled`/`paused`。
- 暂停/取消确认后，撤销该 Run 下所有活跃 Subtask 租约并 `fence+1`；已确认停止才释放执行槽（与 LG-016 对齐）。
- 待验收（`awaiting_acceptance`）与 `waiting_user` 不占执行槽，不持有 Subtask 执行租约。

### 3.4 崩溃恢复

- 启动扫描：清理残留临时文件；JSONL 尾部不完整行截断到最后完整记录并记 `error.recorded`（沿用 docs/08 §7）。
- 对持有租约但进程已消失的 Subtask，按**副作用可知性**分派：
  - 无写副作用且可安全重做 → 可回收租约并按程序重新调度（记录原因事件）；
  - 有写副作用或副作用未知 → **不自动重放**，置 `recovery_required`（Task 或 Run 级），等待人工/有界恢复决定。
- **不得假设**完整 checkpoint skip 已实现：恢复只能依赖已落盘的元数据与采集证据；缺证据时保守进入 `recovery_required`。

### 3.5 幂等交接（idempotent handoff）

- 交接以稳定键幂等：`(run_ref, subtask_ref, fence)` 或业务键 `(run_ref, node.key, attempt)`。重复提交返回首次结果。
- 产物交接绑定**版本/哈希**：沿用现有 `ArtifactHandoff`（`coordinator/graph.py`）编码 `<subtask>@<content_hash>:<artifact>`；下游只接受校验通过（存在、归属、摘要一致）的引用。
- 交接失败可诊断并恢复：写 `fail_reason`/`blocked_by`，不伪造 `passed`。

## 4. 验收条件 3：受控同伴交接、权限与总预算

### 4.1 同伴发现与请求协议

- worker 可发现**同一 Run 内**的其它 Member（只读投影），并按需请求协作。请求为**提议**，经程序校验。
- 建议加性实体 `CollabRequest`（非冻结名）：

```yaml
schema: lightgravity.bot/v1
kind: collab_request
id: req_01J...
run_ref: run_01J...
from_member_ref: member_A
to_member_ref: member_B
correlation_id: msg_01J...      # 因果关联：来源 Subtask / 消息 ID
objective: "…"                   # 获准摘要，不含来源正文
handoff:                          # 可选：请求的产物引用
  artifacts: ["subtask_01J...@sha256:…:diff.patch"]
  mode: summarize | review | execute
budget_request: { max_calls: 1, max_tokens: 4000, timeout_seconds: 60 }
expected_run_revision: 9
at: "2026-10-16T00:00:00Z"
```

- 每个请求携带 `task/run/node`、`correlation_id`（消息 ID）与因果链；重复、越权、过期请求返回明确结果（§6）。

### 4.2 权限边界

- 只传递**获准摘要**与带版本/哈希的产物引用；**不传递来源正文当作控制指令**（来源正文不可解释为授权或验收）。
- 拒绝：跨 Task 泄漏、失效来源引用、超出请求者/响应者授权的产物、把摘要文本当作可执行指令。
- 响应者权限不得因请求而扩大；协作不产生新的 Task 授权或控制状态写权限。

### 4.3 总预算与容量

- 协作请求受**总预算、次数、超时与容量**控制：`max_workers`、`max_parallel`、`max_repair_rounds`（Task `budget`）之外，新增/复用协作计数；所有请求与响应计入**同一** Task/Run 预算。
- **禁止私建无限委派**：worker 不得创建新 Run、新 Task、无限递归协作；等待同伴不得形成无限循环（超时/次数到达即停）。
- **禁止绕过验收**：协作产物与普通产物走同一验证链；worker 自报通过无效。

### 4.4 反例

| 反例 | 期望行为 |
|---|---|
| worker 请求跨 Task 产物 | 拒绝（`path_outside_workspace`/`reference_invalid`），不泄漏 |
| worker 请求创建新 Run/Task 做无限委派 | 拒绝（`illegal_transition`/`budget_exhausted`），不产生新控制实体 |
| 协作响应中携带失效/摘要不符产物 | 交接失败，`fail_reason` 记录，不伪造 `passed` |
| 把来源正文当指令要求改权限 | 视为普通文本，不授予权限 |
| 等待同伴导致循环等待 | 超时/次数上限触发 `budget_exhausted`，可诊断恢复 |

## 5. 版本化接口、事件、开关与兼容迁移

### 5.1 新增 HTTP 端点（候选，加性；仅冻结路径与最小语义）

| 方法与路径 | 用途 | 状态 |
|---|---|---|
| `GET /api/v1/runs/{run_id}/discoverable` | worker 可发现候选投影（只读，按 Member 过滤） | 候选 |
| `POST /api/v1/runs/{run_id}/claim_requests` | 提交候选领取请求（幂等 `request_id`） | 候选 |
| `POST /api/v1/subtasks/{subtask_id}/lease/renew` | 续租（`owner`+`lease_seconds`） | 候选 |
| `POST /api/v1/subtasks/{subtask_id}/lease/release` | 主动释放（仅持有者或程序） | 候选 |
| `POST /api/v1/runs/{run_id}/collab_requests` | 受控同伴请求（幂等 `request_id`） | 候选 |
| `GET /api/v1/runs/{run_id}/collab_requests` | 协作请求与结果（只读，游标） | 候选 |

> 上述端点均需 `expected_revision`/幂等键与本地认证（`X-LG-Token`）语义，沿用 docs/08 §4.1。worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 owner。

### 5.2 新增事件（加性，消费方忽略未知类型）

`subtask.lease_granted`、`subtask.lease_renewed`、`subtask.lease_expired`、`subtask.lease_revoked`、`subtask.claim_refused`、`collab.requested`、`collab.resolved`、`handoff.produced`、`handoff.rejected`。事件 `payload` 含 `subtask_ref`/`owner`/`fence`/`reason`（如适用），沿用 §5.1 事件信封。

### 5.3 状态与错误（加性）

- `recovery_required` 已存在于 Task/Run 枚举；崩溃恢复使用它，不新增终态。
- 新增错误码：`stale_lease`（409，否）、`claim_refused`（409，否）；复用 `lock_conflict`（可重试）、`budget_exhausted`、`illegal_transition`、`not_ready`、`capability_unavailable`。错误信封沿用 §4.2。
- 状态迁移**不新增方向**：仍按 docs/08 §6.1 迁移图；租约与协作只影响同一 `executing`/`repairing` 内部的节点归属与阻塞。

### 5.4 开关与默认

- 建议开关（写入 `bot-data/settings/SETTINGS.md`，非秘密）：`decentralized_claim_enabled`（**默认 false**）、`collab_requests_enabled`（默认 false）、`claim_lease_seconds`（默认建议 300，可配置）。
- **默认关闭**：关闭时行为与现状完全一致——程序按 `plan_source=rules` 顺序调度，无发现/领取/协作端点副作用（端点可返回 `not_ready` 或只读空投影，由实现明确并冻结）。
- SDK 内部委派（`enable_subagents`）仍默认关闭，且不因本扩展自动开启。

### 5.5 兼容迁移与回退（migration & rollback）

- **向后兼容**：所有新增字段为可选；旧 Run/Subtask 无 `fence` 时按 `fence=0` 处理并给出诊断，不阻断执行。
- **回退**：关闭开关后不再产生新租约/协作事件，进行中的租约按程序回收策略处理（确认停止后释放），保留历史与非交付 diff/worktree/证据，不删除。
- **不改变**文件 SoT、目录布局、事件信封、既有错误码、既有状态枚举与迁移方向；实现不得先于契约扩展语义。
- 迁移步骤建议由 docs08 owner 冻结后拆为 LG-029/030/031 实施：契约版本 MINOR 升版 → 字段/端点/事件落地（默认关闭）→ 开关启用与真实闭环验证（LG-031）→ 集中 QA（LG-032）。

## 6. 与 docs/08 的具体对接清单（供 docs08 owner 逐条落版）

1. §4.3 端点表新增 §5.1 六个候选端点（标注“加性、默认关闭”）。
2. §5.1 事件类型最小集新增 §5.2 九个事件。
3. §4.2 错误码表新增 `stale_lease`、`claim_refused`。
4. §6.3 Subtask 新增加性可选字段 `fence`；`owner`/`lease_expires_at` 语义补充“过期≠停止、fencing 拒绝旧持有者”。
5. §6.2 Run 说明协作预算与恢复进入 `recovery_required` 的触发条件（不新增迁移方向）。
6. §6.5 Settings 建议项新增 `decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`（默认关闭）。
7. §13 变更记录新增一条 MINOR（若实现保持加性）或 MAJOR（若改迁移/错误语义），并同步 README/PROJECT/agent.md/docs/06 的契约引用。
8. §11 文件归属表补充去中心化相关 owner（§7）。

## 7. LG-029/030/031 可实施 owner 拆分（供派工）

| 任务 | owner 文件范围（建议） | 交付 | 依赖 |
|---|---|---|---|
| LG-029 发现与原子领取租约 | `backend/lightgravity/store/**`（租约/fence）、`backend/lightgravity/coordinator/scheduler.py`（发现/领取）、`backend/lightgravity/api/**`（发现/领取端点）、`tests/store/**`、`tests/coordinator/**` | 竞争唯一授予、续租/过期/fencing、撤销、幂等；默认路径兼容 | LG-028、LG-016 |
| LG-030 受控同伴交接 | `backend/lightgravity/coordinator/**`（协作路由/预算）、`backend/lightgravity/store/**`（collab 持久）、`backend/lightgravity/api/**`（collab 端点）、`tests/coordinator/**` | 因果关联、获准摘要+版本化产物、权限/预算/超时、失败可诊断 | LG-028、LG-029 |
| LG-031 执行/整合/QA 返修闭环 | `backend/lightgravity/coordinator/**`、`backend/lightgravity/verify/**`、`tests/e2e/**`、开关接线 | 两个 worker + 独立 worktree + 冲突处理 + 独立复核 + 有界返修；开关与回退 | LG-029、LG-030、LG-017、LG-018 |

约定：共享 `coordinator/**`、`api/**`、`store/**` 与 docs/08 由**单一 owner 串行集成**；LG-029 与 LG-030 可先在**独立 worktree**并行，接口以本稿 §5 冻结点为准，实际合并由集成者串行接线。

## 8. 与当前实现的差距（诚实声明）

- 现状：`Store.claim`/`renew`/`release` 与 `SubtaskClaimer` 已实现 **owner + lease_expires_at** 语义，但**尚无 `fence`、发现投影、claim/collab 端点、协作预算、开关**。
- 现状：无独立编排且默认 `plan_source=rules`；SDK 内部委派默认关闭。
- 现状：完整 checkpoint skip **未实现**；恢复仅依赖已落盘证据与保守 `recovery_required`。
- 本稿为**契约准备**，不代表上述任一能力已实现或验证；LG-032 集中 QA 前不得宣称去中心化版本通过。

## 9. 本准备稿范围

- 不改 docs/08、不改 `CONTRACT_VERSION`、不改任务状态、不新增落地 API/schema/事件。
- 不写产品代码、不跑模型调用、不跑产品全量测试。
- 版本升级与最终字段名由集成者按实际变更控制判定；LG-028 保持 `in-progress`，待串行冻结。

## 参考（只读）

- [docs/08 接口契约](../../docs/08-interface-contract.md)（1.5.0）
- [docs/06 滚动排期 §6](../06-roadmap.md)
- [docs/09 资料接入与检索](../09-source-intake-and-retrieval.md)（§8 幂等/恢复）
- [LG-028 任务](../../backlog/tasks/LG-028.md)、[LG-029](../../backlog/tasks/LG-029.md)、[LG-030](../../backlog/tasks/LG-030.md)、[LG-031](../../backlog/tasks/LG-031.md)、[LG-032](../../backlog/tasks/LG-032.md)
- [开发规则](../../agent.md)（§9 本地/在线参考）
