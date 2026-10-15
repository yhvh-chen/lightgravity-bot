---
title: "LG-031 PROOF2-CLOSE — PLAN（0 真实模型确定性 lifecycle 收口）"
doc_type: plan
category: engineering
owner: "LG031 REAL-PROOF2-CLOSE owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "fix/lg031-proof2-close"
base: "dev/lg031-real-proof2@e167724"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash（本包新增真实模型调用 = 0）"
updated: "2026-10-16"
status: "FROZEN-BEFORE-CLOSE"
---

# LG-031 PROOF2-CLOSE — PLAN

> 本包是 **REAL-PROOF2 之后单独授权的 0 模型确定性收口**。REAL-PROOF2（`dev/lg031-real-proof2@e167724`）
> 已完成**同一持久候选**的真实 DeepSeek 工作（27 dispatch）+ 1 次真实独立 ModelReviewer 的真实复核（门 1–6 真实 PASS），
> 但因 **harness 装配缺口** 未驱动产品 `verify_and_prepare` → `decide(accept)`，导致门 7「绑定 accept」未达，
> Run 停在 `executing`、Task 停在 `verifying`（手工写）。旧 STOP 报告/账本/证据**保持原字节**。
>
> **本包目标**：只对**同一个已完成真实工作/复核的持久候选**做 **0 模型**的确定性生命周期收口——用**既有产品**
> `RunController`/`VerificationService`/`StoreResourceStopper` 消费**真实捕获的成功 DispatchOutcome、真实停止事实、真实 review 结果**，
> 走合法状态迁移、真实机器检查/stopgate/`_open_acceptance` 和绑定 `accept`。**不改状态造成功**；不裸写 phase/acceptance；
> 不重跑 worker；不新调模型；不启 live ModelReviewer fallback；不宣自动 checkpoint/resume。

## 0. 授权边界（PM 明确）

- **0 真实模型生成**：本包不得产生任何 DeepSeek/SDK 上游模型生成；开始与结束时**全局 generation ledger count 必须 = 28**，
  `generation.jsonl` **字节 hash 完全不变**。
- 只操作 `probes/lg031/PROOF2-CLOSE/**`（收口记录/harness/证据）。**产品源码与正式契约不改**。
- 旧 `probes/lg031/REAL-PROOF2/**` 的原始 JSON/PLAN/REPORT/ledger/events/worktrees/raw-evidence：**只读，不改写/不删除/不 reset**。
- 不碰 `main@91550a9`（主 PM 的 `PROGRESS.md` + `RUNTIME-CANDIDATE-INTEGRATION` 计数校正 dirty）。
- 不 push/deploy/publish/upload；不动 8123 或他包服务。敏感原件不入 repo/prompt/headers。

## 1. 冻结输入（首动作前记录，只读）

REAL-PROOF2 原件 SHA-256（本包开工时实测，收口前后各核一次，必须不变）：

| 输入 | sha256 |
|---|---|
| `REAL-PROOF2/PLAN.md` | `37c339da8d2749555594e62061eefa369baed5f63341a99cde589d3c9d6926d3` |
| `REAL-PROOF2/STATUS.md` | `e360973644383b0251b713ab02f9f3398188bce2e2ce47f2a876eb83f447e1eb` |
| `REAL-PROOF2/REPORT.md` | `e95d68ce8c0806f8a78471d8c72486a7aaedfeabe9183ea9dc36a7b1aa0b5f1b` |
| `REAL-PROOF2/probe_formal_real2.py` | `fce51ced98b7a9df8d2dd36a56cf9867ade1dfc145392ed970655299423b1db0` |
| `REAL-PROOF2/evidence/formal-real2.redacted.json` | `7caa3d880a6892e9c018feb59a2bc8fbf7670570cf77afe58304bd4a2c2df4a8` |
| `fixtures/formal/data/generation/generation.jsonl`（**持久账本，28 条**） | `e9a1ef785e91f4ecf32cd24f3849f7fedd5a988f052901e839b7e1f0f992e851` |
| `fixtures/formal/data/generation/generation.count.json`（`{"count":28}`） | `48270895c6bf4f32f711afaaa3b45131564a9c92240e6ed2400fa43e2c414d7c` |
| `fixtures/formal/data/runs/run_01M50GARZGSWF8KVJM2PVRZWWC/RUN.md`（rev 17, state=executing） | `721c391fced79f9167c1c918c842f8d555ef755f5bd69c8c18378c13aeeef24b` |
| `fixtures/formal/data/tasks/task_01M50GARZ7FDBC1YR46TCFMM18/TASK.md`（rev 4, phase=verifying） | `65192168fc443832af4fcd06bf69f9548899e1834c6a910b816303c78eadb2e5` |
| `subtasks/...VA2M/SUBTASK.md`（alpha, rev 5, passed） | `fa084d4ae9fdb6d44c92c81c5993cb7247c7ae36e98961ef98935cb035a9907e` |
| `subtasks/...Z7ZKN/SUBTASK.md`（beta, rev 5, passed） | `3818b1f2df7cf2677caa1cd0e0c3a9b257d08c5c4d3ac65c0712078407362a7a` |
| `subtasks/...D44/SUBTASK.md`（verify, rev 5, passed） | `844d20376851f0816475a7349f0db55f7dd7c79c03fda56ff57f68ae55d762d3` |
| `members/member_...RG3GWQC.md`（implementation） | `25c223f788c3293e647cde517f4e17e69cd2ac353174d8538cdcf368333883bf` |
| `members/member_...9E4B.md`（verification） | `3715fcb1aecdab8d4ab2f52f3b4ea4ef757a9b03d0e17d4a00461a8efac445ae` |
| `events/run_.../events.jsonl` | `d47754f73cb488d636dbcefcfb05cd44d8a4f376bec42c4226d0513e305bb553` |
| `events/task_.../events.jsonl` | `3bf09cc1b066b4852d468632627e0d1e499a7e1916d0adeb1f038c12ad56cfa4` |
| `fixtures/raw-evidence/formal-real2.raw.json`（600，私有原件） | `61a30ad2a71b4e5428e11cfb5a2941c0890df93d0555be4071579efaeb2888fe` |

真实候选绑定量（不变量）：Run `run_01M50GARZGSWF8KVJM2PVRZWWC`、Task `task_01M50GARZ7FDBC1YR46TCFMM18`、
`requirements_revision=1`、`plan_hash=85f226e08d87bf60628e553489ab56eb77880a1baee28d1abd9835bcb3ccbc98`、
validated plan hash `37e5c771a7e1c9c41543180e71b79e08de79205fa687cfcca3385a00137b8e8e`、初始 commit `6cf81ea38456b7a0c3c2536b48985d7af3a55f11`。
产物精确内容：`out/alpha.txt==alpha`（sha `b6a98d9c…`）、`out/beta.txt==beta`（sha `f2c82dec…`），隔离无串。
真实交接 diff：alpha `@sha256:6f94ea5f…`、beta `@sha256:a975a8c5…`。
真实复核（原始 ModelReviewer）：`reviewer_kind=model`、`outcome=passed`、`validated_outcome=passed`、`model_calls=1`、usage `{"unknown":["usage"]}`。
真实停止（REAL-PROOF2 记录的 executor `confirm_stopped`）：`confirmed=true`、`sessions_stopped=6/6`、`proxy_stopped=true`。
6 个真实 session：`sess_71642b2e…`、`sess_70d2218f…`、`sess_30a2f91b…`、`sess_3ece31f8…`、`sess_ee17a17e…`、`sess_c2fff92a…`
（均在 Run `session_refs`；各有真实 SQLite conversation DB，均与 `execution_finished`(state=succeeded) 配对）。

## 2. 缺口（REAL-PROOF2 §4，如实保留）

正式 harness 在 `dispatcher.dispatch` 后：
1. **未**走产品 coordinator 成功路径（`_apply_outcome`）落 `run: executing → verifying`；Run 停在 `executing`。
2. 用 `writer.write_task(phase="verifying", acceptance=…)` **裸写** Task 阶段与 provisional acceptance（非产品路径）。
3. 直接调 `_review_sync`（真实 ModelReviewer）而**未**经产品 `ReworkOrchestrator`，故 review 结果未落产品 ledger/未绑 `reviewer_cleanup`。
4. 调 `executor.confirm_stopped` 得真实停止事实，但**未**将其写回 Run（进程退出后 in-process cache 消失）。

## 3. 收口策略（全部 0 模型，只用既有产品 API）

按产品**常规成功路径**（`tests/verify/test_verify_graph_integration.py` 冻结的最小闭环）合法补落：

1. **补落未消费的完成事件**：重建原真实 `DispatchOutcome(state="succeeded", stop_confirmed=None)`（来自原
   `outcome_state=succeeded` + 真实机器门 `pass=true`），经既有 `RunController`/`StateWriter` 走合法迁移
   `run: executing → verifying` + `task: verifying → verifying`（Task 已在 verifying，幂等无变化）——即产品 `_apply_outcome`
   对成功 outcome 所做之事。**不裸写** task phase / acceptance，**不**改 `cleanup`。
2. **真实独立复核复用**：用一个**严格 `RecordedRealReview` 适配器**（实现产品 `Reviewer` protocol）返回**原真实 DTO**
   （`outcome=passed`、`reviewer_kind=model`、`model_calls=1`），且**严格核绑定**：当前候选/需求/计划/配置/实际 cited
   evidence hash 必须与原始记录一致；否则返回 `unavailable`（不伪造）。经**既有产品 `ReworkOrchestrator.process()`**
   消费，产出真实 `ReworkResult(state=awaiting_acceptance)` 并把 reviewer 真实停止事实写入 Run `reviewer_cleanup`。
   **不冒充新调用**（适配器 `name` 标明缓存重用来源）。
3. **真实停止事实**：`StoreResourceStopper(session_confirmer=RecordedStopFactReader)`。reader **严格校验**：
   每个 `session_ref` 必须在**原真实 captured 事件**中同时出现 `session_started` 与 `execution_finished`(state=succeeded)，
   且有对应真实 SQLite conversation DB（save_dir 内、file 实证 SQLite）；reviewer 停止事实按 §4 处理。
   **不是恒 True 替身**；任一无法证明 → `confirmed=False`（unknown held，不伪 `cleanup=done`、不删 refs）。
4. **真实机器检查 + 候选绑定**：产品 `VerificationService(store, stopper=…).verify_and_prepare(task_id, request_id=…)`
   → 真实 `run_checks`（`evidence-present`/`artifacts-in-workspace`）+ stopgate + `_open_acceptance`
   （task `verifying → awaiting_acceptance`，绑定 `candidate_ref`/`candidate_plan_hash`/`check_records`；run `→ awaiting_acceptance`）。
5. **绑定 accept**：产品 `VerificationService.decide(task_id, "accept", request_id=…, target_run_id=…)` →
   task `awaiting_acceptance → completed`、run `→ completed`（`cleanup=done` 由产品在 accept 写，非本包伪造）。
6. **幂等/错 target 拒**：重复 `accept`（同 `request_id`）幂等；不同 `target_run_id` 必须拒绝（`acceptance_stale`）。

## 4. Reviewer 停止事实（严格、不伪）

原 `_review_sync` 传 `ReviewContext(resource_stop_report=…)` 为 **None**，故原真实 reviewer 的 teardown **未捕获到产品 sink**。
按 PM 授权「只能核**原进程**/记录」：
- 真实 reviewer turn 返回**完整 validated report**（`_review_sync` 正常返回），说明 `run_review_turn` 的 `finally`
  （`agent.__aexit__` + `proxy.stop()`）**正常完成**（否则会抛出，report 不会返回）；
- 原进程 pid `2403385` **已退出**（本包实测 `os.kill(pid,0)`/进程表确认），其 SDK agent/loopback proxy 资源随进程消失。
- `RecordedReviewerStopFact` 仅在「原 review 真实 ran 且绑定一致」+「原进程确认已退出」时给 `confirmed=True`，
  并**如实标注 basis**（process-exit + normal-return），**不冒充产品记录的 teardown**；否则 `confirmed=False` → held。

## 5. 禁止项（本包红线）

- 不 `write_task(phase=…)`/`write_task(acceptance=…)` 裸写；不裸 `write_run(state=…)`；不改 YAML；不建 fake passed 节点。
- 不调 `dispatch`/`queue` 重跑已完成写节点；不消费旧 phase 剩 6；不建新 generation ledger；不增 cap。
- 不调用任何真实模型（含 live ModelReviewer fallback）；不伪造 hash/findings/评语。
- 不删 refs、不伪 `cleanup=done`；未知即 held。
- 不改旧 REAL-PROOF2 任何原件；本包记录独立目录。

## 6. 交付

- `probes/lg031/PROOF2-CLOSE/{PLAN,STATUS,REPORT}.md` + `harness/` + `evidence/`（create-only）。
- 结束时先落盘、再精准本地 commit（新 worktree `lg031-proof2-close` / branch `fix/lg031-proof2-close`，基于 `e167724`）。
- 报告含：真实 service 返回 / 合法迁移路径 / 绑定 hash / 前后 ledger hash / 新调用 0 / 未测边界。

## 7. 预算/边界

- wall 900s / maxround 180 / noncache 240k / idle 180 / dev retry 0；单命令 <= 90s。
- 新真实模型调用 **0**；新 Provider 生成 **0**；全局 ledger count 恒 **28**。
- 「门 7 是否达」由产品 service 真实结果决定；不因未来 QA 循环等待；未达则保持 in-progress。
