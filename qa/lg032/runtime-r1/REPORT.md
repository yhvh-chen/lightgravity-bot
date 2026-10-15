---
title: "LG-032 返修复验 R1 — 独立复验 REPORT"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "独立复验 QA（LG-032 R1；非 F1/F2/整合实施者）"
branch: "qa/lg032-runtime-r1"
base: "integrate/lg031-runtime@afcae82 + merge main@66b2b10"
---

# LG-032 返修复验 R1 — 独立复验 REPORT

- 任务：LG-032（返修复验 R1）。owner 为独立 QA，**非** F1/F2/整合实施者；无嵌套派工/推送/部署/发布；主代理仅 PM。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-runtime-r1`（branch `qa/lg032-runtime-r1`）。
- 基点：`integrate/lg031-runtime@afcae82`；安全 `--no-ff` merge `main@66b2b10`。
- 契约：docs/08 `1.10.0`；SDK：`google-antigravity==0.1.22`；自主模式默认 off。
- **产品真实 DeepSeek/生成请求 = 0**。所有 SDK 探针为**真 SDK 0.1.22 + 本地受控 fake loopback 上游**（provider-substitute）；
  子进程用受控 dummy 凭证且连接全 roles 强制 loopback，无真实 reviewer 触达默认 DeepSeek。
- **文件 owner**：仅 `qa/lg032/runtime-r1/**` 与独立 QA 脚本；**产品与共享 docs 只读**；**不自修、不自判 done**。

## 0. 一句话结论

把 F1 候选池 + F2 程序 grant 认证 + 两阶段 SDK 生命周期按 afcae82 精确复验：**四门均 PASS**（产品真实生成 0）。
真实 SDK 两阶段在**同一 Runtime/GraphDispatcher**、**两个不同 member_ref（同权限 profile）worker**、**四个同能力 ready 节点**下完成
“选非首项 → 程序原子授权 → 独立执行会话绑定所选 node”；竞争/身份在真 HTTP 与同 Runtime 两个层面按正式契约成立；8 个真实 SDK 会话
全部进入真实 Run `session_refs` 并参与 stopgate（未停即 held/保留 refs）；选择+执行+reviewer 共用**同一物理持久账本**（跨 Run 不归零、
corrupt=unknown 非 0、转发前拒绝）；默认 off 回退无回归。发现 **0 阻断缺陷**、**3 观察（O1–O3，非阻断）**。LG-032 整体保持 **in-progress**
（阶段 B 成本对照未做）。

## 1. 开工核对（真实，保全）

- `main@66b2b10` clean；`integrate/lg031-runtime@afcae82` clean；`fix/lg031-r1` dirty=8、`/tmp/*experiment*`、`/tmp/no-orchestrator-*` 均**原样保留**；
  未 reset/clean/覆盖/重复 pick。旧 `qa/lg032`（阶段 A）、`lg031-runtime`、`lg031-r1/r2/r3`、`lg031-pool` 全部分支/worktree 保留。
- 真实进程：8123 uvicorn（pid 3320750）、olav-os CLI、open-webui、其它长期 uvicorn——均未触碰；本包无残留探针进程/端口。
- **候选与合并（准确）**：新 worktree 基于 `afcae82`；`git merge --no-ff 66b2b10`。
  `git diff afcae82 HEAD -- backend frontend docs tests pyproject.toml uv.lock Makefile` **为空** ⇒ 产品/契约/测试树**逐字节同 afcae82**。
  main-only 非 probe 变更仅 `PROGRESS.md`、`backlog/tasks/LG-023.md`、`LG-024.md`（LG-023 评估证据/docs，无产品代码）。未合入任何未验 source。

## 2. 四门独立复验

### 门1 — 真实 SDK 两阶段（PASS）

- 探针：`probes/probe_gate1_two_phase.py`（独立于 source 探针），真 SDK 0.1.22 + 本地 fake 上游；**持久**目录 `fixtures/gate1`。
  证据：`evidence/gate1-two-phase.json`。单次 ~3.4s（有界）。
- 构造：**一个** Run / **一个** `GraphDispatcher`（`autonomous_pool=True`, `max_parallel=2`）；两个 **不同 member_ref** 成员（`tool_policy`/`skill_refs`/`connection_ref`
  **完全相同**，仅 capability 标签不同）；每成员 2 个同能力 ready 写节点（共 4）。QA-only 注入 recruiter（冻结契约本身一 capability→一 member，探针如实标注不冒充）。
- 结果（可观察）：
  - `distinct_member_count=2`；`sdk_session_count=8`（4 selection + 4 execution），远高于门要求“≥4（2selection+2execute）”。
  - 选择会话**未下发任何写工具**：`selection_offers_write_tool=false`，选择期仅 `discover_and_request_claim` + 只读 skill 查询；
    选择 scratch workspace 非产品 workspace、非所选 node worktree。
  - worker **真选非首项**：round1 A 池 `[a1,a2]` 选 **a2**，B 池 `[b1,b2]` 选 **b2**；round2 选 a1/b1。`selected_non_first=true`。
  - 执行会话绑定**所选** node 的隔离 git worktree：`distinct_worktrees=4`，`no_cross_contamination=true`（每节点产物在各自 `<key>/out/<key>.txt`，内容与 key 一致），
    4 节点全 `passed`，`active_grants=[]`。
  - `stop_confirmation.confirmed=true`，`sessions_stopped=8/8`，`proxy_stopped=true`。
- 判定：**PASS**。真实 SDK 会话在同一 dispatcher 内两 worker 两阶段工作；选择期无写；执行期绑定所选 node；A/B 不串。
  未扩大原 caller 工具/写 scope/connection pin（选择期 `allowed_tools=()`；执行请求按所选 node 构建）；无冒用另一 member（见门2 跨 member 拒绝）。

### 门2 — 竞争/身份（PASS）

- 探针：`probes/probe_gate2_identity.py`（真 FastAPI + 真 FileStore，按 `api/app.py` 挂载 collaboration router）、
  `probes/probe_gate2b_race.py`（真 FileStore + 真 flock，同 Runtime 竞争 + 身份边界）。证据：`evidence/gate2-identity.json`、`evidence/gate2b-race.json`。
- HTTP 结果（PASS，逐项）：
  - 无 grant/无 resolver ⇒ `claim_refused`/`unauthenticated`，**SoT 不落盘**；无配置 default-deny 成立。
  - body `owner` 冒他人 principal ⇒ `identity_mismatch`，不落盘（`persisted_owner=None`）。
  - 跨 Run（grant scope run_a 用于 run_b）⇒ 拒绝；越 `allowed_node_refs`（grant 只含 sub_a，body 指 sub_a2）⇒ 拒绝。
  - body `capability` 不能授权/扩大：仅程序授权节点被授予，body capability 被忽略。
  - renew/release 身份取程序 grant（`effective_lease_owner`）；body owner=member_ref 而冻结 owner=dispatcher ⇒ `identity_mismatch`；stale fence ⇒ `stale_lease`；另一 principal 不能偷已持有租约（`not_owner`）。
  - discoverable 投影限定在 grant 授权集合（run-scoped/filtered）；peer 端点 body 自报身份 default-deny（`feature_disabled`）。
- 同 Runtime 竞争（PASS）：两 frozen owner 并发请求同 node ⇒ `one_winner=true`、`fence=1`、loser `held_by_other`；
  loser 有界重发现并领取剩余合法 node（`binding_key=beta`）；越池 ⇒ `node_not_in_candidate_pool`；回执脱敏（无 token）；
  **跨 member 命名他人 node** ⇒ `node_not_in_candidate_pool`，目标 node 保持 `pending`/`owner=null`（不冒用/不扩权）。
- 观察 **O1**（非阻断）：同一 dispatcher 内 `lease_owner` 为 worker 实例（dispatcher），两 member 共享同一 owner；同 node 第二次为幂等
  `already_owned`（fence 不二次递增、无双重真实授予/双写）。详见 FINDINGS.md O1。
- peer 旧边界回归：`tests/collaboration/test_peer.py` 等既有用例在全量套件内通过。

### 门3 — 资源/预算/恢复（PASS）

- 探针：`probes/probe_gate3_resources.py`、`probes/probe_gate3b_reviewer_ledger.py`。证据：`evidence/gate3-resources.json`、`evidence/gate3b-reviewer-ledger.json`。
- 真实会话/停止事实（PASS）：用**真实 Coordinator 的 `_adapter_sink`** 作为 graph emit，使 `run.session_refs` 按产品路径写入。
  `sessions_missing_from_run=[]` —— 适配器启动的 **8/8** 会话（selection + execution）全部进入真实 Run `session_refs`；
  `StoreResourceStopper`（真实停止门，接真 adapter `confirm_stopped`）在 Run 终态 + 全会话已停时 `confirmed=true`。
- 未停即 held（PASS）：向 Run 注入一个**从未关闭的 selector ref** 后，停止门 `sessions_stopped=false`、`confirmed=false`，
  并在 `problems` 报“9 session(s) not confirmed closed”，且**保留该 ref**（`unresolved_ref_retained=true`，retained=9）——不伪造 pass。
- 同一持久账本（PASS）：选择+执行共用同一 executor 注入的进程全局 `GenerationCounter(ledger=PersistentGenerationLedger(dataRoot))`。
  场景 A 计数 20；场景 B（第二 Run，**同一 data root/ledger**）计数 **40**（跨 Run 不归零，非重置）；两 Run 账本路径相同。
  过限**转发前**拒绝；损坏账本 ⇒ `corrupt=true`、`generation_count=-1`（**unknown 非 0**）、Run outcome=failed（拒绝转发）。
- reviewer 共账本（PASS，正面证明；更正源疑点）：`evidence/gate3b` limit=1，worker 真转发 1 次（计数 1）后，真实 reviewer turn 的请求被
  **转发前拒绝**（`reviewer_forwarded=0`，429 budget exhausted），`reviewer_shares_shared_ledger=true`。
  机制：`LocalAuthProxy` 未传 budget 时默认回退进程全局计数器，产品 `configure_generation_ledger(data_dir)` 绑定持久账本。
  观察 **O2** 记录原疑点被证伪（非缺陷）。
- 权限回收仅真实停后 / expiry 不偷未知写 / 不重放完成写节点：由既有真实机制覆盖（`collaboration/lease.py` 过期只使租约可重授予、
  `write=true` 进 `recovery_required`/`waiting_user` 诚实停车；graph `_resume_blocked` 反重放；`tests/collaboration` 全绿）。
- Task 预算按正式字段：`context.budget`（`max_model_calls`/`max_collab_requests`）与全局持久账本共同作用；非以全服务 global cap 替代 Task 约束。

### 门4 — 默认程序回退 / 核心差异（PASS）

- 探针：`probes/probe_gate4_default_off.py`。证据：`evidence/gate4-default-off.json`。
- 开关 off（默认）+ `autonomous_pool=True`：产品走**确定性**路径 ⇒ `plan_source=rules`、`custom_tools=[]`、
  无 `discover_and_request_claim` 工具、无 fence、节点正常 `passed`。`api/bootstrap.py` 默认 `autonomous_pool=decentralized`（缺省/非法回落关闭）。
  首版正常 SDK/异步 review/stop/绑定 accept 机制未回归（全量 813 passed/5 skipped 覆盖既有首版路径）。
- 契约 §13 变更控制（观察 **O3**，非阻断）：`body.owner` 由“端点采用 body”变为“兼容可选、非授权”记录为“**无版本变化**”。
  核判：1.6.0 冻结原文（§2.4 + §4.3 note）本就要求授权不依赖 worker 自报身份，afcae82 属**实现对齐既有冻结语义**；
  `ExecutionGrant.lease_owner` 为进程内非持久内部字段，不进入 HTTP/实体 schema。按“冻结语义未变”读法分类**可辩护且自洽**；
  保留意见：公开请求字段语义放松可与内部字段分开记 MINOR 行或标注 compat-only。既未机械强升，也未忽略公开 schema 变化（已在 §4.3/§13 显式记录）。
  详见 FINDINGS.md O3。

## 3. 检查（真实退出码）

- `uv run --frozen mypy` → **Success: no issues found in 137 source files**。
- `uv run --frozen pytest -q -p no:randomly`（全量后端）→ **813 passed, 5 skipped**（与源材料声明一致，按材料性差异引用）。
- `uv run --frozen pytest tests/collaboration tests/coordinator tests/adapter tests/settings tests/api tests/verify tests/startup -q -p no:randomly` → **538 passed, 4 skipped**。
- `tests/collaboration/test_lg031_pool_selection.py` → **10 passed**。
- 探针退出码均为 0；单探针 <=60/90s 有界（gate1 ~3.4s；gate3 三场景 + gate3b 均 < 15s）；无 100s 超时循环。

## 4. 持久原件（create-only，全部独立新证据）

| 证据 | 路径 | 说明 |
|---|---|---|
| 门1 两阶段 | `evidence/gate1-two-phase.json` + `fixtures/gate1/**` | 真 SDK 8 会话、2 成员 4 节点、非首项选择、4 隔离 worktree、stop 8/8 |
| 门2 HTTP 身份 | `evidence/gate2-identity.json` + `fixtures/gate2/**` | default-deny/冒用/跨run/越权/stale fence/偷租约 |
| 门2b 竞争 | `evidence/gate2b-race.json` + `fixtures/gate2b/**` | 1 winner/fence、loser 有界、越池/跨 member 拒绝、单 dispatcher 幂等 |
| 门3 资源/预算 | `evidence/gate3-resources.json` + `fixtures/gate3/**` | 8 会话入 run.session_refs、stopgate 放行/held、账本跨 Run 20→40、corrupt=-1 |
| 门3b reviewer 账本 | `evidence/gate3b-reviewer-ledger.json` + `fixtures/gate3b/**` | 共享账本 limit=1、reviewer 转发前拒绝 |
| 门4 默认回退 | `evidence/gate4-default-off.json` + `fixtures/gate4/**` | plan_source=rules、无工具、无 fence |

- 敏感原件私有（目录 700、证据文件 600）；仅非秘密摘要/哈希入 repo；**未打印 prompt/headers/grant tokens**；证据无真实密钥值、
  无 grant token（`execution_grant` 为布尔）。未读无关/tmp 用户 session。
- 源探针 `probe_two_phase_sdk.py` 使用 `TemporaryDirectory` 自动删除原件（`/tmp/lg031-runtime-probe-*`）——其 JSON 仅存 summary；
  本包**新独立证据补齐完整保全**（持久目录，未自动清除）；旧已删原件**不补造**。

## 5. 成本（单列，不归零）

- **本包产品真实生成 0**；探针为离线本地 fake 上游（无网络/无模型/无费用）。
- pi 开发 QA token/time：本会话 shared/unknown 单列（受限计量，不按 0 计）；旧 LG-031 工程 **34**、LG-023 实际 **65** **不归零**、不重放。
- 不推全成本节省。

## 6. 状态与后续

- **LG-029**：自条件（程序 grant 认证 + default-deny + 不落盘）真齐，可确认 **done**（待 032 独立复验——本包已完成该复验项，F2 由本包正向确认）。
- **LG-031**：**inprogress** —— 真实 provider 条件仍未做（本包产品真实生成 0）；不因本包 provider-substitute 通过而改。
- **LG-032**：整体 **inprogress** —— 阶段 A（机制/语义）已由 `qa/lg032` 完成、阶段 B 全生命周期成本对照未做；本包为其**返修复验 R1**，不提前 done。
- 下一真实 proof 最小前置（交 PM 冻结）：
  1. 一次真实 DeepSeek 双 worker 最小样本（同 capability 两 ready 写节点、两真实 SDK worker 各自在候选池选非首项、经真实 `GraphDispatcher._claim_for_worker_pool` 授权写各自隔离 worktree）；
  2. 复用两阶段生命周期、同一持久 Task/phase 预算与全局 generation 硬上限；usage unknown 不当 0；真实停止确认后回收租约；
  3. 统一硬计数（不重置、不新增独立 selector 预算）；未完成前 LG-031 保持 inprogress。
- 建议 PM 决策项：O1（lease_owner 粒度）、O3（§13 分类口径）；O2 无需动作（已证共享账本）。

## 7. 复现命令

```bash
uv sync --frozen
uv run --frozen mypy
uv run --frozen pytest -q -p no:randomly
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate1_two_phase.py --work qa/lg032/runtime-r1/fixtures/gate1 --out qa/lg032/runtime-r1/evidence/gate1-two-phase.json
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate2_identity.py --work qa/lg032/runtime-r1/fixtures/gate2 --out qa/lg032/runtime-r1/evidence/gate2-identity.json
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate2b_race.py --work qa/lg032/runtime-r1/fixtures/gate2b --out qa/lg032/runtime-r1/evidence/gate2b-race.json
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate3_resources.py --work qa/lg032/runtime-r1/fixtures/gate3 --out qa/lg032/runtime-r1/evidence/gate3-resources.json
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate3b_reviewer_ledger.py --work qa/lg032/runtime-r1/fixtures/gate3b --out qa/lg032/runtime-r1/evidence/gate3b-reviewer-ledger.json
uv run --frozen python qa/lg032/runtime-r1/probes/probe_gate4_default_off.py --work qa/lg032/runtime-r1/fixtures/gate4 --out qa/lg032/runtime-r1/evidence/gate4-default-off.json
```

## 8. 提交与边界

- 精确本地 commit（只含 `qa/lg032/runtime-r1/**`）；**不 `git add -A`**；**不合入 main**；**不 push/deploy/publish**。
- 未改产品/共享 docs；未触碰 8123 / 别包；未动旧证据/未提交改动/原始运行。

## 参考

- [PLAN](PLAN.md)、[STATUS](STATUS.md)、[FINDINGS](FINDINGS.md)
- 阶段 A：`qa/lg032/quality/{REPORT,FINDINGS,STATUS}.md`
- Runtime 集成：`probes/lg031/RUNTIME-AUTH-INTEGRATION/{REPORT,PLAN,STATUS}.md`
- [接口契约 1.10.0](../../../docs/08-interface-contract.md)
