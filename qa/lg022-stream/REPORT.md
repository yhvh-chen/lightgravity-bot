# LG-022 流式停止缺陷包 — 独立复验 REPORT

- Owner：`agent:pi-lg022-stream-qa`（新独立 pi 上下文；**非** stream 修复者/集成者/031 实施者；产品只读，未改产品代码）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream`（branch `qa/lg022-stream`）。
- 核准确整合候选 HEAD：`e0a8cec`（= `main` = batch8 记录 commit；产品树 == INTEGRATION-8 集成点 `975afc2`，
  含 stream 修复 `7d0510c`）。
- SDK：`google-antigravity==0.1.22`（安装版固定；未升级/切换）。契约 `1.10.0`（无接口变化）。
- 依据：AGENTS.md / agent.md、PROJECT/PROGRESS/BACKLOG、docs06 集中门、docs08 §8.1/§9、LG-022 原验收、
  既有 022 QA（`qa/lg022`）/R1/R2/SUPPLEMENT、SDK 调查包（`qa/lg022-r2/sdk-cancel-investigation`）、
  `probes/lg022/STREAM-STOP-FIX`、`probes/batch-20261016/INTEGRATION-8.md`。
- 持久 QA 目录：`qa/lg022-stream/**`；runtime/账本持久目录：`lg022-qa-stream-data/`（**非** TemporaryDirectory；
  证据/账本跨进程保留）。无嵌套派工/推送/部署/发布。

## 0. 结论一句话

**门内 PASS（仅 LG-022 流式停止缺陷包范围）**：在真 SDK 0.1.22 + 真产品装配 + 有效本地 fake SSE 下，
复核运行中的 **pause 与 cancel 都在流式阶段触达 SDK 公开取消入口**（`Conversation.cancel()` + 有界
`wait_for_idle()`），观察到 **真实 `is_idle`**，且**只有真实 Agent 关闭 + loopback proxy 停止后才 confirm**
（0.21s/0.22s，远小于 `stop_timeout` 5s）；未确认保持 `unconfirmed` + 槽保留 + `session_refs` 保留；
无 stop 的正常流完整 drain。第二真实主链（真 DeepSeek 5/10）走完 Settings→Task→真 worker 写产物→
真异步 review→awaiting_acceptance→绑定 requirements/candidate/planhash 的 accept，并回归
duplicate/stale/control/token/pin。持久 generation ledger 为全 phase 唯一路径，跨重启/跨进程不归零、
损坏 fail-closed。**本报告不宣称整产品 pass**；最终 `done` 由主代理按授权决定（见 §7）。

## 1. 第一离线硬门（先于任何 DeepSeek 请求，0 真实模型调用）

探针：`qa/lg022-stream/harness/stream_stop_hard_gate.py`（真 `Agent`/`Conversation`/`LocalAuthProxy`
+ 真产品 `ModelReviewer`→`run_review_turn` + 真 `ReviewLifecycle` + 真 `ControlService.stop`；
上游为本目录自有 `fake_sse_upstream.py` 持续分块 SSE，**非 DeepSeek**；`timeout 90` 有界单进程）。
证据：`evidence/stream-stop-hard-gate.json`（`hard_gate_pass=true`，连续 3 次重跑一致）。

| 场景 | 结果 |
|---|---|
| **S1 cancel（流式中）** | stop **0.21s** 内 `control.state=confirmed`；SDK `cancel` 触达=1；`wait_for_idle`=1；`is_idle=true`；teardown `{agent_closed:true,proxy_stopped:true,confirmed:true}`；无残留 review；run=`cancelled`；`session_refs` 保留 |
| **S2 pause（流式中）** | stop **0.22s** 内 `confirmed`；同样触达 SDK cancel/idle/真实 teardown；run=`paused`，task 经合法 `verifying→waiting_user→paused` 两步落 `paused`；`session_refs` 保留 |
| **S3 unknown-held** | 确定性替身（**明确不冒充真实 SDK 取消**）不响应 stop：`control.state=unconfirmed`/`confirmed=false`，task 停在 `cancelling`，槽保留，`session_refs` 保留，review 仍 held |
| **S4 normal drain（真 SDK）** | 无 stop：真 SDK 流完整 drain（400 chunks 全部收到，文本含 `tick-0`），teardown `confirmed`——轮询不破坏成功流 |

- **注意（诚实标注）**：`upstream_saw_client_gone`（fake server 观察到 EPIPE）为**软观测**，S1/S2 均为 false：
  SDK 读侧关闭可先于 fake 写侧观察 EPIPE。**权威停止事实**是真实 SDK `Agent.__aexit__`（`agent_closed`）
  + loopback proxy 停止（`proxy_stopped`）+ 观察到的 `Conversation.is_idle`（docs08 §9 明确接受该
  adapter 真实停止确认）。故**不作为通过门**，记录在 `observations`。
- `session_refs` 在本探针中为**fixture ref（形态）**；真实对象是 SDK `Conversation`/`Agent`（真）。
  S3 的替身**不**用于宣称真实 SDK 取消（与 fix 探针 §3.2 同口径）。

## 2. 持久 generation ledger 离线门（同一路径/limit，0 真实模型调用）

探针：`qa/lg022-stream/harness/ledger_proof.py`；证据：`evidence/ledger-proof.json`（L1–L5 全 pass）。

| 检查 | 结果 |
|---|---|
| L1 单账本跨实例（重启模拟）持久 | reserve×2 → count=2；新 `PersistentGenerationLedger` → count 仍 **2**（不归零） |
| L2 真跨进程累积 | **独立解释器**读同一路径 reserve → count=3（真跨进程，非仅同实例） |
| L3 硬上限 | limit=2 下第 3 次 `granted=false`、`remaining=0`、`count=2` |
| L4 损坏 fail-closed | 损坏 history：`reserve` 拒绝 `corrupt=true`；`snapshot.corrupt=true`/`count=null`；`count()` 抛 `GenerationLedgerCorrupt`（**绝不当 0**） |
| L5 唯一路径接线 | `phase_env()` 把 `LIGHTGRAVITY_GENERATION_LEDGER_DIR`/`DATA_DIR`/`MAX_GENERATION_CALLS=10` 传给所有 stage；`ledger_root_from_env()` 解析到冻结路径 |

- **统一路径/limit 冻结**：`harness/unified_phase_ledger_config.py` 先冻结
  `PHASE_DATA_DIR=<worktree>-data`、`PHASE_GENERATION_LIMIT=10`，所有 stage 共用；**不再分两个 ledger**。
- **031 上限对齐不扩大授权**：持久账本的 limit 只来自 `LIGHTGRAVITY_MAX_GENERATION_CALLS`（QA 冻结为 10），
  产品侧 `bootstrap` 把同一 `global_generation_counter()` 注入执行器；**本门不是 031/032/040**，
  不扩大任何程序授权预算（031 模式默认 off，未在本门启用）。

## 3. 第二主链一例（真实 DeepSeek，唯一 fixture，5/10）

Harness：`qa/lg022-stream/harness/main_chain.py`（真 uvicorn loopback + 真 HTTP + 真 executor/reviewer +
真 DeepSeek）；证据：`evidence/main-chain.json`（原始）+ `evidence/main-chain-verdict.json`（修正后裁定）。
命令：`LG022_QA_HEAD=$(git rev-parse HEAD) timeout 600 .venv/bin/python .../main_chain.py ...`，退出码 0（原始），
`main-chain-verdict.json` `ok=true`。

| 步 | 结果 |
|---|---|
| Settings worker/reviewer 默认 pin | `default_worker_connection_ref`/`default_reviewer_connection_ref` 与预置一致 |
| 受保护写无 token | `PATCH /settings` → **401** |
| 执行就绪 / reviewer 装配 | `execution_ready=true`；`reviewer.reviewer="model"` |
| 账本 | `persistent=true, limit=10`；路径为冻结唯一 ledger |
| Task 创建 + duplicate | 创建成功；同 `request_id` 幂等返回**同一** task_id |
| 真 worker 写产物 | 磁盘 `workspace/ws1/out/result.txt` = `LG022_STREAM_OK` |
| 真异步 review → awaiting | phase 轨迹 `executing→verifying→awaiting_acceptance`；review 期间 status 查询最大 **0.226s**（不阻塞） |
| 真 `session_refs` | 非空 2 个（`sess_…`），保留 |
| `cleanup` | `status=pending`（**未伪造 done**）；Run 门由真实停止事实放行 |
| 真实 reviewer 停止证明 | `run.reviewer_cleanup={status:done, agent_closed:true, proxy_stopped:true, confirmed:true}`（落 RUN.md） |
| connection pin | `connection_pin.connection_id=deepseek-worker-qa-stream, role=worker`（+content_hash/config_hash） |
| accept 绑定 | `confirmed`；`candidate_ref==run_id`、`candidate_plan_hash==run.plan_hash`、`requirements_revision==1`（绑定一致） |
| duplicate accept | 同 `request_id` 幂等，acceptance 与首答一致 |
| stale/wrong-target accept | 新 request_id + 错 target → **409 illegal_transition**（拒绝） |
| terminal 上的 control | cancel → **409**，`confirmed` 非 true（**不伪造停止**） |
| 账本终值 | `count=5, limit=10, remaining=5, persistent=true`；`generation.jsonl` 5 条 reserved，**无** prompt/header/凭证 |

**Harness 断言修正（非产品缺陷，已如实记录）**：首版 harness 两处谓词写错，已在 live 运行后的
`main_chain_reeval.py` 用修正谓词对**同一份原始证据**重评（**不重复跑主链**）：
① `worker_connection_pin_present` 原读 `pin['ref']`，实际字段是 `connection_id`（+`role`）；
② `control_on_terminal_not_applicable` 原期望 HTTP200 `not_applicable`，实际 API 以 **409 illegal_transition**
拒绝（更严格、诚实）。产品行为本身正确。

## 4. 交叉核（独立于 fix 自证）

- 真 SDK + 本地 fake SSE：`hard_gate_pass=true`（第一离线硬门），与 fix 包 `stream_stop_probe` 独立实现同结论。
- 独立跑 fix 包探针：`probes/lg022/STREAM-STOP-FIX/stream_stop_probe.py` → `fix_confirmed=true`（11/11 verdict）。
- 产品源码确认真实调用 SDK 公开入口：`backend/lightgravity/verify/review.py:900`
  `await conversation.cancel()` + `wait_for_idle()`（有界 5s）；流式阶段 `_drain_stream_with_stop` 每 chunk 重查 stop。

## 5. 全量检查（真实退出码，绑定 `e0a8cec`）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:randomly` | 0 | **791 passed, 5 skipped**（84.96s） |
| `.venv/bin/python -m pytest tests/verify tests/coordinator -q -p no:randomly` | 0 | 188 passed |
| `.venv/bin/python -m pytest tests/verify/test_lg022_stream_stop.py -q` | 0 | 10 passed |
| `.venv/bin/python -m mypy` | 0 | **Success: no issues found in 137 source files** |
| `.venv/bin/python -m mypy backend/lightgravity/verify/` | 0 | Success: no issues found in 9 source files |
| 硬门 / 账本门 / 主链探针 | 0 | 见 §1–§3 |

- 5 个 skip 全为**门控真实检查**（非失败）：向量真实质量（LG-037 端点不可达，未授权）、
  真实 DeepSeek 设置路径（需 `LG020_REAL_DEEPSEEK=1`）、3× 真实前端 dist（本 worktree 未 build，
  **UI 未改**故未 build/未重跑浏览器矩阵）。INTEGRATION-8 的 2 skip 与本环境差异源于此。

## 6. 未测 / 遗留（不夸大）

- **真实 DeepSeek 上游下的 cancel/pause-during-review 未跑**（本 phase 授权 10，主链已用 5；
  stop 缺陷位于产品↔SDK 调用序，与上游是 DeepSeek 还是 fake 无关；已用真 SDK + fake SSE 覆盖）。
- **重启后 verifying/repairing → recovery_required** 与**跨 Run 真实返修**未在本 phase 重跑；
  按现有证据（`qa/lg022-r2` D2/D3 确定性 + R1 stopgate repro）与局部回归引用，
  **不宣称**此前未跑的真实 `reject/repair` 等已跑。
- **light 问答/浏览器**：按材料差异引用既有证据（021/027 旧证据），本 phase **不**重复额外 provider 调用或完整浏览器矩阵。
- **032/040 版本门**明确不在本门；031 模式默认 off，未在本门启用。
- fix 包 REPORT §4 已声明：协调器自动复核路径由 `_record_reviewer_stop` 落 `reviewer_cleanup` 的真实主链
  本包已覆盖（主链 `reviewer_cleanup.confirmed=true` 落 RUN.md）；局部探针手动 cancel 路径的 `reviewer_cleanup=null` 属预期。

## 7. 独立裁定（仅门内范围）

依据 LG-022 原验收（「暂停继续、取消」+「重要缺陷修复重验才完成」）、docs08 §9（复核运行中 pause/cancel
必须有真实停/释放确认；未确认计 unknown、不写终态、不释放槽），本包基于**独立真实证据**裁定：

1. **流式停止接线缺陷（D2 家族）已修复并通过独立复验**：pause 与 cancel 都在流式阶段触达 SDK 公开
   `cancel`/`wait_for_idle`，观察真实 `is_idle`，仅真实 teardown 后 confirm；unknown 保持 held。
   该修复**不新增**端点/字段/枚举，契约保持 `1.10.0`。
2. **真实主链一例通过**：Settings→Task→真 worker 产物→真异步 review→真实停止证明→awaiting_acceptance→
   绑定 accept；回归项（duplicate/stale/control/token/pin）通过。
3. **持久 generation ledger 门内通过**；本 phase 唯一路径/limit=10，真实用量 **5/10**。

**结论**：在**本流式停止缺陷包门内**，LG-022 满足其验收；主代理已授权依独立真实通过证据标 `LG-022 done`
（无需问用户普通实施确认），**但仅限门内范围，不构成全产品 pass**。历史两轮失败（首轮 fail、R1 FAIL、R2
scope 修正未闭环）与旧错误 PASS 标题**如实保留**：旧 PASS 标题只覆盖持久账本+停止门主链，**不覆盖**本次
流式修复；其已被 SDK 调查阻断并随后修复（`fix/lg022-stream`），本报告不洗历史。

## 8. 成本账本（不归零、单列）

| 阶段 | 真实生成请求 | 说明 |
|---|---|---|
| 首轮 QA（`8e81089`） | **unknown**（含 429 rerun） | 单列保留，不当 0 |
| R1 复验（`6228474`） | **6** | 单列保留 |
| R2（`cea87ab`） | **8** = 主链 7 + light 1（两账本未统一） | 单列保留 |
| **本 phase** | **5/10**（唯一持久 ledger：真 worker + 真 reviewer） | 门内通过 |

- 旧轮成本**不归零、不洗白、不宣称本任务累计总费用**。本 phase 未跑额外 light/浏览器/QA 返修。
- 离线硬门/账本门/交叉探针 **0** 真实模型调用。API/开发 retry **0**。

## 9. 资源、边界与提交

- 无新增常驻进程/端口；探针 fake server/子进程退出清理；未碰 8123/其它任务/其它 owner。
- 凭证仅来自受控 env（`DEEPSEEK_API_KEY`），**未输出、未写 prompt、未写 raw 请求**；账本仅计数/单调序号/时间戳/opaque reserve_id。
- 原文件/worktree/日志/旧证据全保留；runtime fixture/账本持久在项目旁 `lg022-qa-stream-data/`（非临时）。
- 本包新增仅 `qa/lg022-stream/**`；**产品与 docs 未改**。报告先持久后精确 commit。
