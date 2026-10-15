---
title: "LG-031 PROOF2-CLOSE — REPORT（0 真实模型确定性 lifecycle 收口）"
doc_type: report
category: engineering
owner: "LG031 REAL-PROOF2-CLOSE owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "fix/lg031-proof2-close"
base: "dev/lg031-real-proof2@e167724"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash（本包新增真实模型调用 = 0）"
updated: "2026-10-16"
---

# LG-031 PROOF2-CLOSE — REPORT

## 0. 一句话结论

对 REAL-PROOF2 的**同一个持久候选**（Run `run_01M50GARZGSWF8KVJM2PVRZWWC` / Task `task_01M50GARZ7FDBC1YR46TCFMM18`），
用**既有产品** `RunController`/`ReworkOrchestrator`/`StoreResourceStopper`/`VerificationService` 在 **0 模型生成**下
走了**合法状态迁移**：`run: executing → verifying → awaiting_acceptance → completed`、`task: verifying → awaiting_acceptance → completed`；
真实 stopgate `confirmed=true`（6/6 真实 session、reviewer 资源均证明已停），真实机器门与候选绑定落 `_open_acceptance`，
`decide(accept)` 真实绑定并幂等。**门 7「绑定 accept」在本收口路径达**（真实产品 service 返回 `confirmed=true`）。
旧 REAL-PROOF2 全部原件/账本/evidence/worktree **字节不变**；全局 generation ledger `count=28` 且 `generation.jsonl` hash 不变；本包新模型调用 **0**。

## 1. 缺口与处置（对应 REAL-PROOF2 §4）

REAL-PROOF2 的 harness 在 `dispatcher.dispatch` 后**未走**产品成功/验证/收口路径，而是手工写 `phase=verifying` + provisional
acceptance、直接调模型 reviewer，Run 停在 `executing`。本包按产品**常规成功路径**（`tests/verify/test_verify_graph_integration.py`
冻结的最小闭环）补落：

| 缺口 | 本包处置（全部既有产品 API，0 模型） |
|---|---|
| 未落 run `executing→verifying` | 重建真实 `DispatchOutcome(state="succeeded", stop_confirmed=None)`，经 `RunController.set_run_state/set_task_phase`（= 产品 `_apply_outcome` 成功分支）合法迁移 |
| 手工写 phase/acceptance | **不**裸写；由产品 `verify_and_prepare._open_acceptance` 生成 binding（`candidate_ref`/`candidate_plan_hash`/`check_records`） |
| review 未走产品 | 严格 `RecordedRealReview` 适配器实现产品 `Reviewer` port，返回原真实 DTO（`kind=model`），经真实 `ReworkOrchestrator.process` 消费 |
| 停止事实未落 Run | 严格 `RecordedStopFactReader`（`SessionStopConfirmer`）+ 产品 `_record_reviewer_stop` 式 `reviewer_cleanup` 写入 |
| 无绑定 accept | 产品 `VerificationService.decide(TASK, "accept", target_run_id=RUN)` |

## 2. 真实 service 结果（`evidence/close-proof2.redacted.json`，sha256 `8859e0a8…`）

- **STEP A（补落完成事件）**：`run.state executing→verifying`（rev 17→18）；`task.phase verifying→verifying`（rev 4→5，无变化，合法幂等）。
- **STEP C（真实复核复用）**：`ReworkOrchestrator.process` 返回 `state=awaiting_acceptance`、`confirmed=true`；绑定
  `run_id`/`plan_hash=85f226e08d87bf…`/`requirements_revision=1`/`resolved_evidence`（2 条真实 diff hash）**全部一致**，
  `refusal_reason=null`；复用 DTO `outcome=passed`、`reviewer_kind=model`、`model_calls=1`（**非新调用**，provenance 标 `recorded-real-review:REAL-PROOF2:model-reviewer(cached)`）。
- **STEP B（真实 stopgate）**：`confirmed=true`、`run_stopped=true`、`sessions_stopped=true`（6/6）、`slot_released=true`、`problems=[]`；
  reader basis：6 个 session 均以原真实 `session_started` + `execution_finished(state=succeeded)` 配对证明 + 6 个真实 SQLite DB；
  reviewer 停止事实（`status=done, confirmed=true`）写入 Run `reviewer_cleanup`。
- **STEP D（真实机器检查 + 候选绑定）**：`verify_and_prepare` 返回 `state=confirmed`、`confirmed=true`、`phase=awaiting_acceptance`；
  `checks.registered=[evidence-present, artifacts-in-workspace]`、`checks.authorized=[]`、`checks.satisfied=true`（见 §5 边界）；
  acceptance 绑定 `candidate_ref`/`candidate_plan_hash`/`deliverable_revision=1`/`requirements_revision=1`。
- **STEP E（绑定 accept）**：`decide(accept, target_run_id=run_01M50…)` → `state=confirmed`、`phase=completed`；
  幂等重放同 `request_id` → `completed`/`confirmed=true`；**错 target** → `AppError: decision targets a different candidate run`（拒）；
  **过期 requirements_revision** → `AppError: decision targets a stale requirements revision`（拒）；`replay_decision` 异 target → `None`（不采信）。
- **终态**：`task.phase=completed` / `task.status=done` / `run.state=completed` / `run.cleanup={status:done}`。

## 3. 合法迁移路径（产品事件流，`formal-work/data/events/**`）

- Run stream：`planning→recruiting→executing`（原真实）→ `executing→verifying`（本包 STEP A）→ `verifying→awaiting_acceptance`（`_open_acceptance`）→ `awaiting_acceptance→completed`（`decide accept`）。
- Task stream：`planning→recruiting→executing`（原真实）→ `verifying→awaiting_acceptance`（`machine checks passed and resources confirmed stopped`）→ `awaiting_acceptance→completed`（`human accepted the candidate`）；并 emit `decision.requested`/`decision.resolved`/`cleanup.updated`（reviewer）。
- 所有迁移均由 `StateWriter.transition_*` 写出，经 `store.validate_transition` 合法校验（Task phase 迁移表）。

## 4. 严格适配器（非恒 True / 非伪调用）+ 负向对照

`RecordedStopFactReader`（`SessionStopConfirmer`）与 `RecordedRealReview`（`Reviewer`）**拒绝**不满足原始事实的输入。
`evidence/negative-controls.redacted.json`（sha256 `2a71e343…`）四例全部**拒绝**：

| 对照 | 期望 | 实测 |
|---|---|---|
| N1 reader 收到未记录的 run | 拒 | `confirmed=false`，`recorded stop facts do not cover this run/session set` |
| N2 reader 收到未知 session id | 拒 | `confirmed=false`，全部 session 列 unknown |
| N3 原进程被报告仍存活 | 拒 | `confirmed=false`，`loopback auth proxy not confirmed stopped from recorded facts` |
| N4 recorded-review 绑定不符（run/plan/req/evidence） | `unavailable` | `outcome=unavailable` + 逐项 mismatch |

## 5. 未测 / 边界（如实）

- **机器检查 `authorized=[]`**：原 Task frontmatter 无 `checks` 字段 ⇒ 产品 `verify_and_prepare` 授权集为空、`results=[]`、
  `satisfied=true`（产品对无授权 Task 的既有语义，**非**本包放宽）。本包在**只读**下独立复算 REAL-PROOF2 的机器门
  （`alpha_exact/beta_exact/no_cross_contamination/pass=true`，alpha sha `b6a98d9c…`、beta sha `f2c82dec…`）。
  说明：本 fixture 的真实产物落在**隔离 worktree**（`.lg-worktrees/<run>/<key>/out/*.txt`），不在共享 `task-ws/out/`，
  故标准 `artifacts-in-workspace`（相对共享 workspace 解析）对本 graph 隔离流不适用，未被授权执行——**未改 Task 去补授权**。
- **reviewer 停止事实**：原 `_review_sync` 未传产品 `resource_stop_report` sink，故产品记录的 teardown **未捕获**。本包按 PM 授权
  「核原进程/记录」：真实 reviewer turn 正常返回（`finally` teardown 完成）+ 原进程 pid `2403385` 已退出 ⇒ `confirmed=true`，
  **如实标注** `basis=harness-derived:…`，**不冒充**产品记录的 teardown。
- 本包**只**对候选做收口：不重跑 worker、不新调模型、不建新 ledger、不消费旧 phase 剩 6；
  **不宣**自动 checkpoint/resume/全 checkpointskip 能力（产品该能力未实现，本包未新增运行时功能）。
- 收口在**私有只读快照**（`fixtures/formal-src-snapshot`，originals 逐项 hash 一致）的**工作副本**（`fixtures/formal-work`）上执行；
  REAL-PROOF2 原 private store/RawRoot/worktree **未移动、未覆盖、字节不变**。
- 真实 Git worktree 不是 OS 安全沙箱（既有真实限制）。

## 6. 计费/计量（不变）

- 本包真实模型生成 **0**；`generation.jsonl` 收口前后同 hash `e9a1ef78…`、`count=28`（未增/未归零/无双计）。
- 旧 34 + proof1 24 + proof2 28 = 已知整体 **86 不变**；旧 phase 剩 6 未消费。
- 本包 elapsed 为 harness 直跑（约 0.6s 服务调用）；**完整闭环 elapsed** 应包含原真实模型运行（REAL-PROOF2 `91.267s`）
  + 本收口/harness 延迟，**不沿用**旧执行秒数当完整闭环时间。

## 7. 原件保全 / hash 锚

- REAL-PROOF2 原件（本包开工/结束两次核对，**不变**）：
  `PLAN.md 37c339da…`、`STATUS.md e3609736…`、`REPORT.md e95d68ce…`、`probe_formal_real2.py fce51ced…`、
  `evidence/formal-real2.redacted.json 7caa3d88…`、`generation.jsonl e9a1ef78…`、
  `RUN.md 721c391f…`、`TASK.md 65192168…`、`raw-evidence/formal-real2.raw.json 61a30ad2…`。
- 本包收口（工作副本）终态：`TASK.md 2eda2bef…`、`RUN.md 558a66c1…`、
  task events `df1af19b…`、run events `1d110973…`、ledger `e9a1ef78…`（不变）。
- harness：`close_proof2.py c3d33c15…`、`negative_controls.py 449771fd…`、`redact_close.py 8b9202fe…`；PLAN `ad3e7b8d…`。
- 私有 RawRoot（本包）：`fixtures/formal-src-snapshot/**`（只读参照）、`fixtures/formal-work/**`（收口工作副本）、
  `fixtures/raw-evidence-formal-real2.raw.json`（600）；**不提交**（`.gitignore` 仅提交脱敏 evidence）。

## 8. 结论与后续（交 PM）

- **门 7「绑定 accept」在本 0 模型确定性收口路径达**（产品真实 `verify_and_prepare` + `decide(accept)` 返回 `confirmed=true`，
  `awaiting_acceptance → completed`，绑定 `candidate_ref`/`candidate_plan_hash`/`requirements_revision`）。
- 若判 LG-031 全门齐 → 可 `done` 待 032 版本完整 QA（**不**因未来 QA 循环等待）；本报告**不**自行改 project/backlog 状态。
- **未宣**自动恢复/checkpointskip；若 PM 要求“产品自动且无需人工 accept 步进”，需另立运行时增强任务（本包不做）。
- 本包不合入 main；无 push/deploy/publish/upload。
