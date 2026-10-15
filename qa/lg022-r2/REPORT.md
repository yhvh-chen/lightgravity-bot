# LG-022 独立复验 R2 — REPORT

- 复验 owner：独立新 pi 上下文（`agent:pi-lg022-r2` 复验角色；非 LG-022 R2 返修者 `fix/lg022-r2`、非集成者 `integrate/batch7`、非 017/018/019/021/027 实施者）。主代理只 PM；**无嵌套派工/推送/部署/发布**。
- 复验 worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`）。
- 开工 HEAD：`0144eb7`（= `integrate/batch7` 整合候选）。
- 最终整合 HEAD：`85adc82`（`integrate/batch7` = `0144eb7` + INTEGRATION-7 文档提交）。**`git diff 0144eb7 85adc82` 仅 4 个文档文件，产品树完全相同**，故复验基点 `0144eb7` 即最终整合产品树。
- 契约：docs/08 `1.10.0`（`backend/lightgravity/contracts/constants.py::CONTRACT_VERSION` 一致）。
- 输入：`PLAN.md`（冻结门/预算）、`probes/lg022/REFIX-R2/REPORT.md`（R2 返修自检，真模型 0）、`probes/lg022/reverify-r1/REPORT.md`（R1 FAIL）、`probes/batch-20261016/INTEGRATION-7.md`、`probes/lg022/REPORT.md`（原 QA FAIL）。
- **判定：PASS（成功门全满足）**。LG-022 仍 `in-progress`（本包不自改 claim/状态，交主代理）；本报告不宣称 LG-032/LG-040 或去中心化/资料检索通过。

> 结论一句话：R1 暴露的两个阻断（stop-gate 死锁、生成计数跨重启不持久）都已在最终整合候选上**独立复验通过**：
> 真实链在真 DeepSeek 下到达 `awaiting_acceptance` 并完成绑定人工 accept；持久账本跨进程/实例/role/session/重启一致、
> 转发前原子预留、并发不超、损坏 fail-closed/unknown 非 0；D2/D3 全过。本 phase 真转发 **8/10**。

## 0. 计量边界（先列，避免洗数）

| 阶段 | 真实生成请求 | 证据 |
|---|---|---|
| 旧 QA 首轮（`qa/lg022` @ `8e81089`） | **unknown**（单列保留；含 429 后 rerun；不视为 0） | `probes/lg022/REPORT.md`、`PLAN.md` §2 |
| R1 复验（`qa/lg022-r1` @ `6228474`） | **6/10**（单列保留；已知） | `probes/lg022/reverify-r1/REPORT.md` |
| **本 R2 phase（`0144eb7`）** | **8/10**（主链 7 + light QA 1；`remaining=2`） | `evidence/real-chain.json`、`evidence/light-qa.json`、`/tmp/lg022-r2-real/data/generation/*` |

- 不把未知旧量洗成 0；**不宣称整个 LG-022 累计 ≤20**（无证据总数）；失败/未完成样本不计交付成本。
- 本 phase 10 是当前授权内**新版本复验预算**，未借改代码或重放未知写入。
- usage 未知标 `unknown`，不写 0。

## 1. 离线计量先行（硬门，先于任何真请求）——**PASS**

### 1.1 单元级账本证明 `evidence/ledger-proof.json`（`real_model_calls: 0`）

| 检查 | 结果 | 依据 |
|---|---|---|
| C1 转发前持久预留（history+快照落盘） | ✅ | 首 reserve 后 `generation.jsonl` 已存在，count=1→3 |
| C2 达上限拒绝、不再转发 | ✅ | limit=3 第 4 次 `granted=false, reason="limit reached"` |
| C3 跨 role（worker+reviewer counter）同账本共享不超 | ✅ | 两 counter 交替 6 次 → 4 granted，两 count 均 4 |
| C4 **真子进程**重启续读不归零 | ✅ | 本进程 count=2 → fresh interpreter count=2，`persisted_across_restart=true` |
| C5 并发竞争不超 | ✅ | 6 真子进程各试 5 次、limit=10 → 总 granted=10、账本 count=10 |
| C6 历史损坏 fail-closed / unknown 非 0 | ✅ | snapshot `{count:null,corrupt:true}`；reserve `granted=false,corrupt=true`；`counter.count=-1` |
| C6b 快照损坏同样 fail-closed | ✅ | `{count:null,corrupt:true}`；reserve 拒绝 |

### 1.2 服务/代理级账本证明（真 `LocalAuthProxy` + 本地伪上游，`real_model_calls: 0`）

- `evidence/service-ledger-forward.json`：3 次真 HTTP 经 proxy 转发到**本地 fake OpenAI-compat 上游** → count=3、`persistent=true`、`remaining=0`；第 4 次 **429** 且上游调用数**零增**（`P3_denied_no_forward=true`）。
- `evidence/service-ledger-read.json`：**独立新进程** `configure_generation_ledger` 重建 → count=**3** 不归零（`P2_persisted=true`）。
- `evidence/service-ledger-corrupt.json`：手工损坏历史后 snapshot `{count:null,corrupt:true,reason:...}`、proxy **429 且上游 0 调用**（`P4`）。

### 1.3 结论

- 最终整合候选**保留了 persistent ledger**（`backend/lightgravity/adapter/generation_ledger.py`），**未回退为 031 内存 counter**。
  `api/bootstrap.py::build_runtime` 在 proxy 启动前 `configure_generation_ledger(settings.data_dir)`；LG-031 注入的 `global_generation_counter()` 即该持久账本（INTEGRATION-7 §3 声称，实测成立）。
- **计量硬门 PASS**。转发前 `_ProxyState.begin_call()` 先 `reserve()` 再 `_forward()`（proxy.py），符合“转发前原子预留”。

## 2. 离线 stop-gate 释放证明 `evidence/stopgate-proof.json`（`real_model_calls: 0`）——**PASS**

驱动**真实** `StoreResourceStopper` + `VerificationService`（按 `api/app.py` 真实装配注入 `session_confirmer`）：

| case | session_refs | cleanup | confirmer | stop.confirmed | task.phase | refs 保留 |
|---|---|---|---|---|---|---|
| **R2A** 真形态+适配器确认停止 | `[a,b]` | pending | 全关 | **true** | **awaiting_acceptance** | ✅ `[a,b]` |
| **R2B** 有 session 未关 | `[a,b]` | pending | b 开 | false | verifying（held） | ✅ `[a,b]` |
| **R2C** reviewer 未确认停止 | `[a]` | pending | 全关 | false | verifying（held） | ✅ `[a]` |
| R2D 对照 cleanup=done | `[a,b]` | done | 无 | true | awaiting_acceptance | ✅ |
| R2E 对照无 session | `[]` | pending | — | true | awaiting_acceptance | ✅ |

- 不变量成立：`session_refs` **从不删除**；`cleanup` **不被伪造为 done**（R2A 后仍 `pending`）；
  未知/未关/reviewer 未确认 → 保持 `unconfirmed`、槽不释放。R1 死锁已消除。

## 3. 真实全链（真 DeepSeek worker + 真独立 ModelReviewer）——**PASS**

`evidence/real-chain.json`（真实 uvicorn + 真 HTTP + 真 Antigravity SDK 0.1.22 + loopback 认证 proxy → `https://api.deepseek.com/v1`；**非** ASGI in-process、**非** mock executor）。

- 真 Settings 默认 worker/reviewer pin：`worker_default_pinned`/`reviewer_default_pinned` ✅；敏感写无 token **401** ✅。
- 执行就绪 `execution_ready=true`；`reviewer_wired_model` reviewer=`model`/`deepseek-chat` ✅。
- **真 Task → 真 worker（SDK 写 `out/result.txt`）→ 异步独立 SDK reviewer → `awaiting_acceptance`**：
  `run_reached_awaiting_acceptance: ok=true, phase=awaiting_acceptance` ✅（R1 停在 `verifying` 的阻断已消除）。
- 停止门（R2 关键）：
  - `r2_session_refs_preserved_nonempty` ✅ `session_refs=[sess_1a4f…, sess_282a…]`（2 个真实 SDK session，**保留历史**）。
  - `r2_cleanup_not_fabricated_done` ✅ `cleanup={"status":"pending"}`（**未预填 done**）。
  - `r2_reviewer_stop_fact_recorded` ✅ `reviewer_cleanup={"status":"done","agent_closed":true,"proxy_stopped":true,"confirmed":true,"problems":[]}`（**真实 reviewer teardown 事实**，非假定）。
- `reviewing` 期间状态查询不阻塞：`max_status_latency_s=1.198 < 2.0`，`review_phase_observed=true` ✅。
- 人工 accept 绑定 requirements/candidate/planhash：`accept_bound_exact_run` ✅
  `candidate_ref=run_01M50640S3B25PPZR270SQFF3Q`、`requirements_revision=1`、`deliverable_revision=1`、
  `candidate_plan_hash=6a76344a…`、evidence refs 真实。
- 幂等/duplicate/stale：`duplicate_accept_idempotent` ✅（同一 candidate/acceptance）；`stale_accept_rejected` ✅（409 `illegal_transition`，target_run_id 不匹配）。
- 持久账本诊断：`r2_generation_persistent` ✅ `{count:7,limit:10,persistent:true}`；`r2_ledger_files_present` ✅（含 `.jsonl`/`.count.json`）。
- **D3**：`d3_success_run_no_fail_reason` ✅ `fail_reason=""`。

### 3.1 真 light Q&A（`evidence/light-qa.json`）

- 首个链的 light-QA 步骤因**QA harness 使用了旧 body schema**（多传 `conversation_id`）被产品 422 拒绝（**0 真调用**）。这是 QA 脚本漂移，非产品缺陷。
- 修正后独立探针跑通：真 DeepSeek 直答 200、`kind=direct`、**未创建 Task**、账本 `{count:1,persistent:true}` ✅。

### 3.2 真实/替身标注

| 项 | 类别 | 证据 |
|---|---|---|
| worker 真写产物、真 SDK session | **SDK-real / DeepSeek-real** | `real-chain.json` `stop_gate.session_refs` |
| 独立 ModelReviewer 真运行 + 真 teardown | **SDK-real / DeepSeek-real** | `real-chain.json` `stop_gate.reviewer_cleanup` |
| 到 `awaiting_acceptance` + accept 绑定 | **real** | `real-chain.json` steps |
| reviewing 不阻塞 | **real** | `max_status_latency_s=1.198` |
| D3 无伪 fail_reason | **real** | `run_md_fail_reason=""` |
| light Q&A 直答 | **real** | `light-qa.json` |
| 持久账本语义 | **offline（真子进程/真 proxy + 本地伪上游）** | `ledger-proof.json`、`service-ledger-*.json` |
| stop-gate 释放/held | **local-deterministic（替身 confirmer）** | `stopgate-proof.json` |

## 4. D2 生命周期/故障确定性探针 `evidence/deterministic-probe-r2.json`（`real_model_calls: 0`）——**PASS**

驱动**真实** coordinator worker loop / `RecoveryScanner` / `ReworkOrchestrator`，受控替身为 `deterministic-double`：

| 检查 | 结果 | 依据 |
|---|---|---|
| **restart 不重放** | ✅ | 真 `RecoveryScanner`+注入死 worker probe → `recovery_required`、`queue=not_queued`、`attempt` 仍 1（无重放/无新 Run） |
| **跨 Run 预算不重置** | ✅ | Task 前端 `rework` 账本 `review_rounds=2/repair=1` 在新 Run 后不变 |
| **cancel-during-review 真停止** | ✅ | cancel 在 reviewer **真的观察 stop 并停止**后才 `confirmed=true`，task/run=`cancelled` |

- 另：本 worktree 全量 `pytest -q -p no:randomly` → **772 passed, 5 skipped**（退出 0）；定向
  `tests/control tests/verify tests/coordinator tests/collaboration` → **299 passed**；
  `tests/verify/test_lg022_r2_stopgate_resources.py` 等 R2 新测试 → **21 passed**。
  产品自带 `tests/coordinator/test_lg022_review_lifecycle.py` 亦断言 status 不阻塞、pause/cancel 真停止、restart 不重放、成功 Run 无 fail_reason —— 作为独立产品证据补充（非本包自评）。
- `SDK-real/provider-substitute` 说明：真实 SDK 资源生命周期在 3.2 由真链证明；故障注入以受控替身/伪上游完成，
  明确标 `deterministic-double`/`local-fake-upstream`；**fake 无 `session_refs` 未冒充真生命周期**。

## 5. 成功门逐条裁定（`PLAN.md` §4）

| 门 | 结果 | 依据 |
|---|---|---|
| 1. 计量先行离线通过 + 本 phase 真转发 ≤10 且可精确计数 + persistent 非内存 | **PASS** | §1；8/10；诊断 `persistent=true` |
| 2. A/D1 全链真闭环（真 worker+reviewer→awaiting→accept 绑定/duplicate/stale；session_refs 保留、无伪 cleanup=done、真停止证明） | **PASS** | §3 |
| 3. D2 reviewing 不阻塞 + stop/release 确认 + 未知保留槽 + restart 不重放 + 跨 Run 预算 | **PASS** | §3（不阻塞）、§2（held/释放）、§4（反重放/预算） |
| 4. D3 成功 Run 无 fail_reason，失败仍留事件 | **PASS** | §3 |
| 5. 真实/替身逐项标清；未测项列明；不以单点成功宣全产品通过 | **PASS** | §0/§3.2/§6 |

⇒ 成功门全满足，**PASS**。

## 6. 未测 / 明确未证实（不夸大）

- **真实 reviewer 的通过/返修决策**在真链里 reviewer `passed` 且进 `awaiting_acceptance`；但**拒绝→返修新 Run→再验**的完整真实返修闭环未在本 phase 用真模型复跑（由 §4 确定性探针 + 产品测试覆盖机制；非本门硬性要求）。
- **真实 pause（非 cancel）during review** 未在真链复跑（确定性探针覆盖 cancel；产品测试覆盖 pause）。
- **跨两次真实服务重启**的端到端计数核对：§1.2 用“真 proxy + 独立新进程”证明持久；未做两次真 `lightgravity start` 全链重启（时间/预算内以等价新进程重建证明）。
- **真实 reviewer teardown 故障（`__aexit__` 抛错）** 的端到端 hold：由 §2 R2C（未确认 → held）覆盖机制，未用真实 SDK 抛错复跑。
- **LG-021 前端 / LG-027 设置专项**：沿用旧证据（021 `5176edf` 26/26；027 `qa/lg027` pass），**按材料差异引用**；本门未重跑完整浏览器矩阵。新资料检索/去中心化**不在本门**且默认 off。
- 全量 pytest 772 passed / 5 skipped 与 INTEGRATION-7 记录的 775/2 不同：**非回归**——差异为 QA worktree 中需显式授权/env 的条件跳过（LG037 真向量、LG020 真 DeepSeek），本 worktree 条件触发；所有执行到的用例均通过。

## 7. 成本 / 真实计数 / 资源清理

- 本 phase 真实 DeepSeek 生成请求：**8/10**（主链 7 + light QA 1）；`remaining=2`；SDK/开发重试 **0**；输出/HTTP/并发遵守冻结上限。
- 旧 QA 首轮 unknown、R1 6/10 **单列保留**，未 reset、未重放。
- 资源：所有 QA harness/uvicorn 已退出（`pgrep` 无 QA 进程）；**root 8123 未触碰**（pid 3320750 仍为原 owner）；所有旧 worktree/dirty/证据保留；未 `reset`/`clean`。

## 8. 需返修（无阻断）

- 本门未发现新的阻断性产品缺陷。唯一非产品项：QA harness（R1 脚本沿用）的 light-QA body schema 漂移，已在本包新探针修正。
- 建议主代理：LG-022 可据本报告推进 `done`（成功门全满足），但**最终 done 由主代理/用户决定**；本包不自改状态。

## 9. 基线命令 / 退出码

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python qa/lg022-r2/harness/ledger_proof.py …` | 0 | C1–C6 全 pass |
| `.venv/bin/python qa/lg022-r2/harness/service_ledger_proof.py forward/read/corrupt …` | 0/0/0 | P1–P4 pass |
| `.venv/bin/python qa/lg022-r2/harness/stopgate_proof.py …` | 0 | R2A–R2E pass |
| `LG022_GEN_LIMIT=10 .venv/bin/python qa/lg022-r2/harness/real_chain_r2.py …` | 1\* | 主链关键项全 PASS；仅旧 schema 的 light-QA 步骤失败（\* 已由 `light_qa_probe.py` 单独通过） |
| `DEEPSEEK_API_KEY=… .venv/bin/python qa/lg022-r2/harness/light_qa_probe.py …` | 0 | 真直答 200、无 Task、persistent |
| `.venv/bin/python qa/lg022-r2/harness/deterministic_probe_r2.py …` | 0 | 三场景 pass |
| `.venv/bin/python -m pytest -q -p no:randomly` | 0 | 772 passed, 5 skipped |

## 10. 证据路径

- 计划/状态：`qa/lg022-r2/PLAN.md`、`STATUS.md`。
- 账本：`qa/lg022-r2/evidence/ledger-proof.json`、`service-ledger-forward.json`、`service-ledger-read.json`、`service-ledger-corrupt.json`。
- 停止门：`qa/lg022-r2/evidence/stopgate-proof.json`。
- 真链：`qa/lg022-r2/evidence/real-chain.json`、`light-qa.json`、`real-chain-dry.json`。
- D2/D3：`qa/lg022-r2/evidence/deterministic-probe-r2.json`。
- Harness：`qa/lg022-r2/harness/*.py`。
- 候选：`qa/lg022-r2` HEAD（产品树 == `85adc82`）。
