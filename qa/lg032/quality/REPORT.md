# LG-032 阶段 A — 独立机制/语义质量 QA 报告

- 任务：LG-032（阶段 A，owner：独立 QA，非 028/029/030/031 实施/集成者）
- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg032`（branch `qa/lg032`）
- 基线 HEAD：`62e96edb01ffcbcea2e401ed4084d2e4d9d9278d`（开工 clean）
- 契约：docs/08 `1.10.0`；SDK：`google-antigravity==0.1.22`；自主模式默认 off（未改）
- **本包产品真实 DeepSeek/生成请求 = 0**；未执行成本采样；未写真实 benchmark driver；未推送/部署/发布。
- 证据均为 **provider-substitute**（真 `FileStore` + 真 `flock` + 真多进程 + 进程内 worker 仿真，无 SDK/网络/模型）。
  offline 机制证据**不代替**存储真实样本（阶段 B）。

## 0. 结论摘要

去中心化候选的**核心机制**（原子领取唯一授权、fence 防旧 owner 写、过期≠停止、重启幂等/反重放、
默认关闭回退、受控 peer 交接的 hash/作用域/因果/篡改/幂等/预算、独立 review + 有界返修 + 无 reviewer 阻止 accept、
SDK delegation 默认关闭、无常驻模型编排 agent）**在离线机制层面成立且有可观察证据**。

但本阶段发现两项与 **LG-028 冻结契约/文档明文**存在差距的语义事项（F1、F2），其中：

- **F2（HTTP 领取端点接受请求体 `owner`，未接程序认证身份）**：与 LG-028 §2.4「授权结果必须不依赖 worker 自报身份」
  及 docs/08 §4.3 note 明文**不符合**。这是**冻结端点语义**的验收缺口（产品 graph 运行路径不经该端点，故运行时未受影响）。
- **F1（自主 claim 实为“程序预选唯一节点后挂工具”）**：按 LG-028 §2.1/§2.3/§2.4 与 LG-031 验收判定为**部分符合**——
  去中心化要素齐备（worker 自主提出 claim、程序原子授权、发现投影只读且**确实多候选**、fence、默认关闭），
  但**调度权威未从程序转移**：worker 在其执行那一刻可领取集合被程序限定为**唯一预选节点**，
  不存在“在多个就绪候选中自主选择”的行为；LG-031 的两个 worker 是**程序顺序调度 + 各自领取自身预绑定节点**。

> 判定口径严格遵守指令：**不**把“先选唯一节点再挂工具”不加说明宣为“完整去中心化”；**亦不**超正式契约加组织平台要求。

**阶段 A 门范围判定：partial**（核心机制 PASS；F1 语义范围偏差部分符合；F2 冻结端点语义不符合 ⇒ 需返修后复验，另派）。
**LG-032 整体仍 in-progress**，直到阶段 B 真实同门成本对照完成（本包未执行，未预注册有结果收益）。

## 1. 开工核对（真实）

- `main@03c7db6` clean；本 worktree `qa/lg032@62e96ed`（`batch10: LG-032 PM scheduling + atomic claim`）clean。
- 全 Git worktree 列表、旧分支、旧 dirty（`fix/lg031-r1` dirty=8、`/tmp/*experiment*`）**全部保留**，未 reset/clean/覆盖/重复 pick。
- 依赖：`uv sync --frozen` 从 `uv.lock` 安装（**无模型、无网络产品调用**）；本地 venv 为本 QA 新建，不与主 worktree 共享 dataRoot。
- 契约 `1.10.0`、SDK `0.1.22`、自主模式默认 off 未改。

## 2. 机制检查与证据

| # | 检查项 | 方法 | 结果 | 证据 |
|---|---|---|---|---|
| M1 | 跨进程竞争仅一个获准、fence 恰好 +1 | 真 6 进程 + 真 FileStore flock 同步 barrier | **PASS**：1 granted，5×`held_by_other`，final_owner 唯一，final_fence=1 | `evidence/multiprocess-race.json` |
| M2 | 幂等重复 claim 不重复授予（跨重启） | `pytest tests/collaboration`（真 FileStore） | **PASS**：`test_claim_request_id_is_idempotent`、`test_same_request_id_after_restart_does_not_grant_again` | `evidence/local-pytest.txt` |
| M3 | 旧 fence 写回拒绝且不落盘（fencing≠LWW） | 真 FileStore | **PASS**：`StaleLease`，entity 未变 | 同上 |
| M4 | 过期≠停止；有副作用节点不自动重放 | 真 FileStore + FakeClock 前进 | **PASS**：`stopped=False`；`recovery_required=True`，node 变 `waiting_user` 且不可再发现 | 同上 + §3-F3 |
| M5 | 取消释放租约、重启不重复写 | 真 FileStore | **PASS**：`test_cancel_releases_lease_and_restart_does_not_duplicate_write` | 同上 |
| M6 | 默认关闭回退（缺省/SETTINGS 缺失/非法） | `ClaimPolicyReader` + `test_default_off_*`、`test_default_path_has_no_grants_or_extra_tools` | **PASS**：enabled=False ⇒ 空投影、拒绝、无 grant、无自定义工具、`plan_source=rules` | 同上 |
| M7 | 身份 principal 程序注入（peer 端点） | 真 HTTP（ApiContext.worker_identity）+ `test_worker_identity_resolver_reads_grant_header_only` | **PASS**：body 自报身份 default-deny（`unauthenticated`/`identity_mismatch`），仅头部 grant 解析 | 同上 |
| M8 | peer 交接 hash/源版本/作用域/因果 | `pytest tests/collaboration/test_peer.py`（真 FileStore + 真 evidence root） | **PASS**：跨 Task/Run 拒绝、digest 不符拒绝、`<subtask>@<hash>:<artifact>` 解析、因果绑定强校验 | 同上 |
| M9 | peer 篡改/重复幂等/授权失效拒绝 | 同行 | **PASS**：`handoff.rejected` 事件；request_id 并发幂等；stale fence 拒绝；revoked pool grant 拒绝 | 同上 |
| M10 | 预算硬拒绝/超时上限（协作） | 同行 | **PASS**：`max_collab_requests` 耗尽 definite `budget_exhausted`；超时上限拒绝 | 同上 |
| M11 | 独立 review/有界返修/无 reviewer 阻止 accept | `pytest tests/coordinator/test_lg031_review_closure.py`（真 FileStore 协调器，ScriptedReviewer=fake reviewer） | **PASS（离线）**：worker 自报不达 accepted；rework 开新 Run、旧候选保留；无 reviewer ⇒ `unavailable` 阻止 accept | 同上 |
| M12 | 验收绑定 requirements/candidate/plan_hash | 源码 + verify/candidate.py | **PASS（源码）**：`candidate_ref` 绑定 `requirements_revision`+`plan_hash`；accept 需 `expected_*` 否则 `acceptance_stale` | 源码路径 |
| M13 | 无常驻模型编排 agent；SDK delegation 默认关闭 | 源码审查 | **PASS**：`enable_subagents=False` 于 `adapter/sdk_config.py:127`、`adapter/executor.py`、`coordinator/dialogue.py:128`、`verify/review.py:1019`；默认 `RuleBasedPlanner`（无模型） | 源码路径 |
| M14 | 事件可重放/重启不重复副作用 | `_RequestLog` 由 lease 事件重放；`test_side_effect_node_is_not_replayed_after_restart` | **PASS** | 同上 |
| M15 | 真实隔离 worktree + 带 hash 交接（真实 Git） | `pytest tests/collaboration/test_lg031_real_workers.py`（真 Git worktree） | **PASS（离线真 Git）** | 同上 |

离线真 Git 多 worker 隔离、原子授权、带回款交接在 `test_lg031_real_workers.py` 全部通过（本包复核运行）；但仍是**进程内 fake/仿真 worker**，
**真实 SDK 多 worker 端到端**由 LG-031 phase4 的真实探针覆盖（10 次真实转发 + 只读哈希恢复），本 QA 承认其证据但**未重跑**（产品真实生成 0）。

## 3. 语义边界（重点）

### F1 — 自主 claim = 程序预选唯一节点后挂工具（部分符合）

见 `evidence/autonomy-boundary.json`、`evidence/discovery-multicandidate.json`、`evidence/node-preselection.json`。

**事实链（可观察）**：

1. 计划由**程序**确定性生成（`plan_source=rules`），节点经 recruiter 映射到 member，`_materialize_subtasks` 预绑定
   `assignee_member_ref`（`coordinator/graph.py:466-541`）。
2. 自主路径在 `_execute_node` 内对**当前程序调度的 node** 铸 `pool` grant（`_mint_pool_grant`，`graph.py:1050-1079`）。
3. worker 的 `discover_and_request_claim` claim 回调 = `_claim_for_worker`，其中
   `if node_ref != node.subtask_id: return {granted: False, reason: "node_not_scheduled_for_worker"}`（`graph.py:1081-1101`）。
4. 独立探针：两同能力节点**同时 ready** 时，发现投影返回 **2 个候选**（`discovery-multicandidate.json`），
   但 claim 非本 worker 被排度节点 ⇒ `node_not_scheduled_for_worker` 拒绝（`node-preselection.json`）。
   产品真实流中每 worker 执行时 `discovery_count=1`（`autonomy-boundary.json`）。

**对照 LG-028 冻结原文**：
- §2.1 候选来源为“Run 已校验计划中可立即就绪、能力匹配、依赖就绪、预算充足”的 Subtask 集合（按 Member 过滤的只读投影），**未要求程序将 worker 预绑定到唯一节点**；
- §2.3 worker **只提交候选请求**，不写控制状态；§2.4「授权不依赖 worker 自报身份，`owner` 由程序推导」——本项实现**满足**（grant 身份来自程序）；
- §1 项 1「程序是唯一控制权威；worker 只能提议」——本项实现**满足**，且更保守。

**判定：部分符合。**
- 满足：程序单一控制权威、worker 只提议、程序原子授权、fence、投影只读多候选、默认关闭、无模型编排。
- 不满足“完整去中心化语义”：worker 实际可领取集合在其执行时被限定为**唯一**预选节点；不存在多候选自主选择；
  LG-031「至少两个 worker」是程序顺序调度 + 各自领取自身预绑定节点。
- **不夸大**：LG-028 也未要求 worker 自由跨 Run 抢单或组织平台能力；故这不构成“契约违背”，而是**语义范围偏差**，
  需实施 owner 在 docs/08 实现说明或任务正文**明确标注**“程序把节点预绑定到 worker，worker 仅在自身节点上完成一次程序授权的领取”，
  避免把“先选唯一节点再挂工具”宣为“完整去中心化”。

**返修建议（交 PM 另派实施 owner，QA 不自修）**：
- 选项 A（文档澄清，最小）：在 docs/08 §6.5/§4.3 加性说明自主 claim 的实际语义为“程序按计划把节点预绑定到 member；
  worker 在自己的授权集合内提出领取请求”，并同步 LG-031/LG-032 记录的准确范围。
- 选项 B（能力增强，较大）：让同一 member 的多个就绪同能力节点进入一个可选池，由 worker 选择其一（仍程序原子授权 + fence）；
  需重新评估单 writer 串行与预算。
- 建议先 A 后择机 B；**不得**把当前实现无说明地宣为“完整去中心化通过”。

### F2 — HTTP 领取端点接受请求体 `owner`，未接程序认证身份（不符合，冻结端点语义）

**契约原文**：
- LG-028 §2.4：「授权结果必须**不依赖 worker 自报身份**：`owner` 由程序按已注册 Member 推导；worker 不能指定任意 owner」。
- docs/08 §4.3 note：「worker 侧调用须经受控执行身份，**不接受浏览器直接指定任意 `owner`**」。

**实现**：`backend/lightgravity/api/collaboration.py`
- `GET /runs/{run_id}/discoverable`（`owner` 查询参数）、`POST /runs/{run_id}/claim_requests`（body `owner`）、
  `POST /subtasks/{subtask_id}/lease/renew`、`.../lease/release`（body `owner`）**均直接采用调用方提供的 `owner`**，**未**使用 `ctx.worker_identity`。
- 仅 `POST/GET /runs/{run_id}/collab_requests`（LG-030）使用 `ctx.worker_identity` 且 default-deny（`api/collaboration.py:155-181`）。
- `build_collaboration_router()` 已挂载到默认 app（`api/app.py:257`），端点**真实可达**（受 `LocalAccessPolicy` token 保护，默认关闭开关）。
- LG-029 任务正文自述「端点 `owner` 暂由请求体提供」为未装配缺口。

**判定：不符合** LG-028 §2.4 对**领取/续租/释放端点**的身份要求。
- 缓释：产品 coordinator graph 的自主领取走**进程内** `GraphDispatcher` 路径（pool/node grant 身份），**不经**这些 HTTP 端点，
  故**当前产品运行时未受影响**；且端点默认关闭。缺口在**冻结端点本身**：独立调用方（含浏览器）可指定任意 `owner`（在开关开启时）。
- 这与 LG-031 声称的“程序冻结执行身份”只覆盖 peer 端点与进程内 graph 路径，**未覆盖** claim/lease HTTP 端点。

**返修建议（交 PM 另派实施 owner）**：
- 在 `claim_requests`/`lease/renew`/`lease/release`（及 `discoverable` 的 worker 过滤）接线 `ctx.worker_identity`：
  以认证身份作为 `owner`，body 的 `owner`（若保留）必须与认证身份一致，否则 default-deny（复用 peer 端点的 `unauthenticated`/`identity_mismatch` 语义，不落盘）；
  未接身份接缝时保持 default-deny。**需按 docs/08 变更控制**：若改变 body 字段语义（`owner` 由必填改可选/改为“声明”），属 MINOR/需明确；建议加性：认证身份优先，body 不一致则拒。
- 复验绑定本报告 F2 与 `probe_multiprocess_race`（进程内路径已安全，端点需独立 HTTP 复验）。

### F3 — `reclaim_expired` 对写节点写 `waiting_user` + `fail_reason`（待核/可接受）

**契约原文**：docs/08 §6.3「对有副作用的节点不得自动重跑，须进入 `recovery_required`」；LG-028 §2.5 同义。
**实现**：`collaboration/lease.py:430-470` 对 `write=true` 节点写 `state="waiting_user"` +
`fail_reason="recovery_required: unconfirmed side effects after lease expiry"`，`recovery_required=True` 返回。

**分析**：`SubtaskState` 枚举（`contracts/enums.py:75-82`）**无** `recovery_required`（该项在 `RunState`/`TaskPhase`，`enums.py:33/62`）。
因此 Subtask 层面无法写 `recovery_required` 状态；实现选择**枚举内最接近的诚实停车状态** `waiting_user` +
可机器解析的 `fail_reason` + `blocked_by=[]` + 使节点不可发现。这是**可接受的诚实映射**，且与 docs/08 §6.2 的 Run 级
`recovery_required`（已在 1.8.0 新增 `verifying/repairing → recovery_required`）不冲突。
**判定：可接受（非缺陷）**，但建议实现/契约 owner **明确**“Subtask 级停车状态为 `waiting_user`，Run 级才用 `recovery_required`”的口径，
避免读者按 §6.3 字面误以为 Subtask 会写 `recovery_required`。

> 另注（非缺陷，记录未测）：`LeaseManager.reclaim_expired` 未在 `coordinator/graph.py` 实时接线；运行中过期由 executor 停止路径 +
> LG-016 resume guard（`_resume_blocked` → Run `recovery_required`）承接。即“过期回收机制已实现但**未在实时图中自动调用**”，
> 属**集成层未测项**（阶段 B/后续真实运行覆盖），本阶段不判为缺陷。

## 4. 未测 / 明确限制

- **产品真实 DeepSeek/生成请求 0**：本包不跑真实模型；所有离线机制证据不代替阶段 B 真实样本。
- **真实 SDK 多 worker 端到端**：由 LG-031 phase4 真实探针（10 真实转发 + 只读哈希恢复）覆盖，本 QA **未重跑**（尊重产品真实 0）。
- **真实独立 reviewer 对完整候选 `passed`**：phase4 真实证据存在（1 次真实 ModelReviewer passed），本 QA 未重跑；
  `tests/coordinator/test_lg031_review_closure.py` 用 **ScriptedReviewer（fake reviewer，明确标注）**，**不冒充真 SDK**。
- **031 工件原运行 SoT 部分字节丢失**：承认保全缺口；SDK sessionDB 原件持久备份 + 版本/hash 引用已恢复（只读，未重跑）；
  `content_hash` 原始字节随临时目录删除为**已记录事实**。本 QA 未写回原 store、未补字段、未编造收据。
- **跨真实进程/真实上游的 cancel/pause-during-review、重启后 `verifying/repairing → recovery_required`** 未在真实上游下复验（属 022/LG-032 后续）。
- **完整 checkpoint skip** 未实现（docs/08 §6.2 明记）。
- **阶段 B 成本对照**未执行、未预注册有结果收益；LG-023 混淆数据不用于本对照。

## 5. 门判定（阶段 A 范围）

| 范围 | 判定 |
|---|---|
| 原子领取/竞争/唯一授权/fence/脱敏 | **PASS** |
| 过期≠停止 / 反重放 / recovery 诚实停车 | **PASS**（F3 可接受） |
| crash/restart/取消/幂等 | **PASS** |
| 权限/身份（**进程内 graph 路径 + peer 端点**） | **PASS** |
| 权限/身份（**claim/lease HTTP 冻结端点**） | **FAIL（F2）** |
| 受控 peer 交接（hash/作用域/因果/篡改/幂等/预算/授权失效） | **PASS** |
| 独立 review/有界返修/无 reviewer 阻止 accept/验收绑定 | **PASS（离线；真 SDK 见 031 探针未重跑）** |
| 默认关闭回退 / 无模型编排 / SDK delegation off | **PASS** |
| 自主语义边界（程序预选唯一节点） | **部分符合（F1）** |

**阶段 A 门：partial** — 核心机制通过；F1 需**文档/语义澄清或增强**，F2 需**返修后独立复验**（另派，QA 不自修自判）。
LG-032 整体 **in-progress**（阶段 B 未执行）。

## 6. 复现命令（本地，真实退出码）

```bash
# 依赖（无模型）
uv sync --frozen

# 局部机制测试
uv run --frozen pytest tests/collaboration -q -p no:randomly          # 77 passed
uv run --frozen pytest tests/collaboration tests/coordinator tests/adapter tests/api tests/settings -q -p no:randomly  # 400 passed

# 独立机制探针（provider-substitute，无 SDK/网络/模型）
uv run --frozen python qa/lg032/quality/probe_multiprocess_race.py \
  --work qa/lg032/quality/fixtures/race/work --out qa/lg032/quality/evidence/multiprocess-race.json
uv run --frozen python qa/lg032/quality/probe_autonomy_boundary.py \
  --work qa/lg032/quality/fixtures/autonomy-boundary/work --out qa/lg032/quality/evidence/autonomy-boundary.json
uv run --frozen python qa/lg032/quality/probe_discovery_multicandidate.py \
  --work qa/lg032/quality/fixtures/multicandidate/work --out qa/lg032/quality/evidence/discovery-multicandidate.json
uv run --frozen python qa/lg032/quality/probe_node_preselection.py \
  --work qa/lg032/quality/fixtures/preselection/work --out qa/lg032/quality/evidence/node-preselection.json
```

## 7. 下一阶段前置（交 PM）

1. **F2 返修**（另派实施 owner）：claim/lease HTTP 端点接程序认证执行身份并 default-deny；不落盘/不越权。
2. **F1 决策**（PM）：文档澄清（选项 A）或能力增强（选项 B）；无论何者，**不得**把当前实现无说明地宣为“完整去中心化通过”。
3. **F3 口径澄清**（文档 owner）：Subtask 级 `waiting_user` vs Run 级 `recovery_required`。
4. **阶段 B**：仅在阶段 A 无阻断后由 PM 另行冻结固定样本/次数/费用上限与成功门，并先验证 harness
   （单一持久 ledger 全 stage 共用、跨重启不归零、损坏绝不当 0、转发前预留、usage unknown 不当 0）；
   比较程序调度基线 vs 新协作路径；未完成样本不计已交付成本；不以投入成本强行宣布成功。
5. LG-032 整体保持 **in-progress**；本报告为阶段 A 证据，不代表成本对照已通过。
