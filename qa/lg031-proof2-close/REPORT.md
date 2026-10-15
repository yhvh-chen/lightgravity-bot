---
title: "LG-031 PROOF2-CLOSE 独立审计 REPORT（qa/lg031-close-audit）"
doc_type: report
category: engineering
owner: "LG031 close-audit 独立 QA owner（非 031 源作者/真实 proof/close 作者；pi 现有 DeepSeek；无嵌套代理）"
branch: "qa/lg031-close-audit"
audit_target: "fix/lg031-proof2-close@54e7695"
audit_scope: "只读产品与旧 probes；独立复算/负向对照；不改 harness/产品/旧原件"
base_reviewed: "REAL-PROOF2 dev/lg031-real-proof2@e167724 + PROOF2-CLOSE fix/lg031-proof2-close@54e7695"
source_anchor: "main@91550a9（只读）；qa/lg032-runtime-r1@26ea945"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
product_real_generation: 0
---

# LG-031 PROOF2-CLOSE 独立审计 REPORT

## 0. 结论（一句话）

**判 PASS（含 3 处文档/DTO 准确性补遗，均不动摇「门 7 已由既有产品服务合法收口」这一实质结论）。**
54e7695 在**同一持久候选**（Run `run_01M50GARZGSWF8KVJM2PVRZWWC` / Task `task_01M50GARZ7FDBC1YR46TCFMM18`）上，
用**既有产品** `RunController`/`StateWriter`/`StopResourceStopper`(SessionStopConfirmer 端口)/`ReworkOrchestrator`/
`VerificationService.verify_and_prepare`/`decide(accept)` 走了合法状态迁移，消费**真实捕获的停止事实**（6/6 session 的
`execution_finished(state=succeeded)` 配对）与**原真实 ModelReviewer 结果**（binding 一致），达成绑定 accept。
**本审计独立复算 + 独立负向对照在该产品树上重跑通**，`ledger_unchanged=true`、`new_model_generation=0`。
未见证据伪造、未见非授权门绕过、未见 livefallback、未见 fabricate completion。

**但发现 3 处必须补遗的准确性问题（不改变 PASS 判定，阻塞「报告可逐字采信」）：**

1. **[A1 中] 复用 DTO 的 `unsubstantiated` 被静默改写。** 原真实 review DTO 为 `unsubstantiated=["F1"]`，
   close 证据与产品事件落 `unsubstantiated=[]`；REPORT §2 却称「复用 DTO … 全部一致」。属**记录失真**（outcome=passed 不变，
   F1 非阻塞），须补遗说明，不得表述为「DTO 完全一致」。
2. **[A2 中] REPORT/STATUS 的「收口后工作副本」4 个 hash 锚不可复现。** `TASK.md 2eda2bef…`、`RUN.md 558a66c1…`、
   task events `df1af19b…`、run events `1d110973…` 在全盘**不存在**，与现存 fixture 不符；fixture 在 evidence 落盘后
   （06:52:26 > 06:51:15）被再次写入。须补遗更正为实际可复算的锚，或删除该非权威锚。
3. **[A3 低，披露充分] reviewer 停止事实为 harness 派生（process-exit + turn 正常返回），非产品记录 teardown。**
   `reviewer_cleanup` 由 harness 复刻 `Coordinator._record_reviewer_stop` 的写入形状，但 fact 来源为推断。已如实标注
   `basis=harness-derived:…`，负向对照 N3 证明存活时拒绝。**接受**，但须在报告显著位置标为 authority 最弱环。

**LG-031 可在仅补遗（不改历史/不重开）的前提下 mark `done` 待 032 完整版本 QA。** 本审计**不**宣全产品 pass、**不**宣自动
checkpoint/resume、**不**宣机器门自动执行通过（见 §4）。若无补遗，报告不能逐字采信 A1/A2。

## 1. 审计方法与边界

- 独立 QA owner，非 031 源作者/真实 proof owner/close owner；新持久 worktree `lg031-close-audit`（branch `qa/lg031-close-audit`，
  基于 `54e7695`）；开工核 `lg031-proof2-close` owner 已退出（无 pi/node 进程，worktree clean），未并写。
- **只读**产品源码与旧 probes；原件保全：未 reset/clean/覆盖；未重跑真实 SDK/POST；未新调模型（产品真实生成 0）。
- 独立复算：在**新拷贝**（`fixtures/qa-repro-copy`，已清理）与新输出上跑**实际** `close_proof2.py` + `negative_controls.py`；
  另加本审计自有 3 项负向对照（`qa/lg031-proof2-close/independent_negctl.py`）。
- 未输出 secret；未动 8123/其他服务；不动 main@91550a9 的 PM dirty（`PROGRESS.md`/`RUNTIME-CANDIDATE-INTEGRATION.md`）。

## 2. PM 逐项判定

### 2.1 capturedDispatchOutcome → RunController 迁移是否相当正常成功路径（非仅凑状态）— **PASS（带一处如实降级）**

- `controller.set_run_state("verifying")` / `set_task_phase("verifying")` 经 `StateWriter.transition_run/transition_task`，
  与产品 `Coordinator._apply_outcome` 成功分支使用**同一状态原语**，并经 `store.validate_transition` 合法校验。
- 但**并非消费一个「真实 captured DispatchOutcome 对象」**：原 probe 的 `emit` 绕过了 `_apply_outcome`，故 `DispatchOutcome`
  对象未落盘；harness **重建** `DispatchOutcome(state="succeeded", summary="all 3 subtask(s) passed", stop_confirmed=None)`。
  重建依据为原真实 `outcome_state=succeeded` + 节点 `{alpha,beta,verify}=passed` + 真实机器门 `pass=true`。
  `state`/`stop_confirmed` 与 `GraphDispatcher._final_outcome` 一致；`summary` 措辞不同（原为
  `"all N subtask(s) passed; candidate handed to verification"`），对成功分支语义**无影响**（`_apply_outcome` 仅对
  failed/cancelled 用 summary 写 `fail_reason`）。
- **判定**：迁移**相当**正常成功路径、非任意造状态；但证据链是「原真实成功事实 + 重建 typed outcome」，**不是**原对象直取。
  报告已在 §1/§4 如实说明，**不构成伪造**。

### 2.2 6 SDK refs 是否完整来自真实事件、stop inference 是否权威 — **PASS（worker 权威；reviewer 推断，见 A3）**

- 6 个 `session_ref` 与 Run `session_refs` 完全一致；每个 session 在原事件中同时有 `session_started` 与
  `execution_finished(state=succeeded)`（本审计独立计数 6/6 pairing）。
- **`execution_finished` 是权威 teardown 证据**：产品 `adapter/executor.py` 在成功/失败路径均先 `await handle.ensure_closed()`
  再 `self._stop_proxy(handle)`，**之后**才 emit `execution_finished`（源码核对：执行成功路径 ~L722-779、失败路径 ~L1087-1103）。
  故「finished ⇒ SDK agent 关 + loopback proxy 停」是**程序事实**，非推断。
- **exact 旧 process/proxy/DB 证据**（非仅 pid 消失）：
  - 原进程 pid `2403385` 有**原始记录**依据：28 条 `generation.jsonl` 全部 `"pid":2403385`，
    且真实事件 `lease`/`release` payload 记 `owner="graph-dispatcher:2403385"`（本审计在原 `lg031-real-proof2` 私有原件核对）。
  - 6 个真实 SQLite conversation DB 在私有 save_dir 内真实存在（`SQLite format 3` 头，file 实证）。
  - 本审计独立负向对照：将某 session 的 `execution_finished.state` 翻成 `failed` → `confirmed=false`（5/6，unknown 该 session）；
    指向无 DB 目录 → `confirmed=false`（0/6）。**证明 reader 非恒 True**。
- **残留弱环（如实）**：DB 腿只校验「存在 `>= len(session_refs)` 个 SQLite DB」，**不映射 session↔conversation DB**
  （harness 源码注释自认）。authoritative 部分是 per-session 事件配对；DB 为**补充**证据。此弱环已在 harness 源码注明，
  未粉饰；不影响 per-session 停止成立。

### 2.3 reviewer_cleanup = 原 finally teardown + pid exited？是否合法产品回调？— **接受，但为 authority 最弱环（A3）**

- 原 probe 的 `_review_sync` **未传** `resource_stop_report` sink（`ReviewContext` 无该参数）⇒ 产品**未捕获** reviewer teardown；
  这是**真实缺失**，不可补造。harness 未伪造该 sink。
- harness 写入 `reviewer_cleanup` 的**形状**与 `Coordinator._record_reviewer_stop` 逐字一致
  （`write_run({"reviewer_cleanup":{...}})` + `CLEANUP_UPDATED` 事件，源码核对一致）。**不是**裸写一个与产品回调无关的假字段。
- 但 fact **来源**是 harness 推断：`_reviewer_stop_fact()` = 原 reviewer turn 正常返回（⇒ `finally` 已跑）**且** pid `2403385` 已退出
  （`os.kill(pid,0)` 现测 + 原始 `pid` 记录）。`confirmed=true` 由此推断得出，**非**产品记录的 teardown。harness **如实标注**
  `basis="harness-derived: original real reviewer turn returned normally + originating process exited"`，负向对照 N3 拒绝对存活进程给 confirmed。
- **判定**：**符合「严格从真实源路径/原进程记录佐证」的最低可接受标准，但权威等级低于 worker session**（后者有真实 typed 事件）。
  报告必须显著标明这是**inference/degraded authority**；不得写成「产品记录 teardown」。**未构成常量 confirmed / 未把 model 自报当程序事实。**
- 源码核对：`ModelReviewer._run_turn → run_review_turn` 的 `finally` 会 `agent.__aexit__` + `proxy.stop()`，
  且该 `finally` 在 `resource_stop_report` 非 None 时本会填充它（原 probe 传 None 故未捕获）。因原 turn 返回
  `validated_outcome=passed`（`review` 会捕获 `_run_turn` 异常并降级 `unavailable`，故 passed ⇒ turn 正常返回），
  该推断在**真实源路径**上有据，非凭空。
- **边界声明**：若采用最严格口径（无 `resource_stop_report` ⇒ reviewer `unknown held`），则应记 reviewer 停止为未证实、
  stopgate 仅凭 worker session 事件成立；本审计采用「真实正常返回 + 原始 pid 记录 + 进程已退出 + 如实标注 basis」口径
  判**接受**（A3 低），并**明确**该口径分歧点交 PM/032 裁量。

### 2.4 原 Task 未授权 checks；`authorized=[]` 是否被宣称为「机器门执行通过」— **PASS（未夸大）**

- 原 `TASK.md` frontmatter **确无** `checks` 字段；产品 `authorized_checks()` 对缺省返 `()`；
  `CheckReport.satisfied` 对空授权集为 `True`（产品既有语义「nothing to check」，源码核对）。
- close 证据如实记 `checks.registered=[evidence-present, artifacts-in-workspace]`、`authorized=[]`、`results=[]`、`satisfied=true`；
  REPORT §5 明确写明「原 Task 无 checks ⇒ 授权集为空 … **非**本包放宽」，并说明隔离 worktree 产物对共享 workspace 检查不适用。
- **判定**：**未**把「授权空」宣称为「机器门执行通过」；外部只读机器 truth（alpha/beta hash + no-cross）为**独立复算**，绑定
  同一候选产物（sha256 `b6a98d9c…`/`f2c82dec…` 与原 REAL-PROOF2 逐字节一致）。不同 artifact/worktree/hash **绑定同一候选**
  （run_id/plan_hash/requirements_revision/evidence set 全部一致，见 2.5）。**遗留**：产品**自动**机器门（非本 fixture 授权集）
  仍由 **LG-032 同门集中验收**——本审计明确不隐瞒此点。

### 2.5 reviewer_cleanup 声称 same candidate + requirements + plan + resolved artifact hash — **PASS**

- `RecordedRealReview._bind()` 严格核：`candidate.run_id == RUN_ID`、`plan_hash == 85f226e0…`、`requirements_revision == 1`、
  `resolved_evidence` 集合与原记录相等；任一不符 → `unavailable`。
- 本审计独立复算：把 `requirements_revision` 改 999 → `unavailable`（refusal 明确）；把 run/plan/evidence 改 → `unavailable`
  （原 N4 已证）。bindings 与 close 证据一致。
- 原真实 review 原本 `status=ran`、`validated_outcome=passed`、`reviewer_kind=model`、`model_calls=1`、`usage={"unknown":["usage"]}`
  （unknown 不当 0），close 复用一致（除 A1 的 unsubstantiated，见下）。

### 2.6 A1 详述：`unsubstantiated` 被静默改写（记录失真）

- 原真实 DTO（`REAL-PROOF2/evidence/formal-real2.redacted.json` 与私有 raw 一致）：`findings=[]`、`unsubstantiated=["F1"]`。
- close 适配器取 `unsubstantiated=tuple(recorded.get("unsubstantiated", []))` = `["F1"]`，但产品 `validate_findings` 会**重算**
  `dropped`（输入 `findings=()` ⇒ `dropped=()`），最终 `report.unsubstantiated=()`。故 close 证据/产品事件落 `[]`。
- 影响：**outcome 不变**（`passed` 仍非阻塞）、accept 绑定不受影响；但 close **丢失**了「原真实 reviewer 有 1 条未经证实的
  finding」这一事实，且 REPORT §2 的「复用 DTO … 全部一致」**不准确**。属**truthfulness 补遗**，非伪造 pass。
- 最小纠正方案：REPORT 增补「复用 DTO 除 `unsubstantiated` 外一致；原 `["F1"]` 经产品 `validate_findings` 重算为空，
  此为产品验证语义，非原 reviewer 结果改变」，或保留原值并在适配器显式区分。

### 2.7 A2 详述：最终工作副本 hash 锚不可复现

- REPORT §7/STATUS §关键 hash 声称「本包收口（工作副本）终态：`TASK.md 2eda2bef…`、`RUN.md 558a66c1…`、
  task events `df1af19b…`、run events `1d110973…`」。本审计全盘搜索**不存在**这些 hash；现存 fixture 实际为
  `TASK.md 74f3ca…`、`RUN.md 4ad7f6…`、task events `bdf410fc…`、run events `c032dc61…`。
- 时序：committed evidence `close-proof2.json` mtime 06:51:15（finished_at 一致），但 `formal-work` 的 TASK/RUN/events
  在 **06:52:26** 被再次写入（晚于 evidence），提交于 06:52:39。⇒ 该 4 个锚对应**evidence 落盘后的再次写入**，非最终态，不可复算。
- **不影响**：committed **redacted evidence**（`8859e0a8…`）内部自洽，且本审计在新拷贝上**独立复跑得到相同实质终态与
  `ledger_unchanged=true`/`new_model_generation=0`**。故 main proof（evidence JSON）可信，仅 prose 锚逾期。
- 最小纠正方案：STATUS/REPORT 将该 4 锚更正为**可复算的 committed evidence 锚**（如 evidence sha256）或注明「fixture 在
  记录后被再次运行，prose 锚作废，以 `evidence/close-proof2.json` 为准」。

## 3. 原件保全 / 计费（独立复核）

- REAL-PROOF2 原件在本审计前后**字节不变**：`PLAN.md 37c339da…`、`STATUS.md e3609736…`、`REPORT.md e95d68ce…`、
  `probe_formal_real2.py fce51ced…`、`evidence/formal-real2.redacted.json 7caa3d88…`、
  `generation.jsonl e9a1ef78…`（28 条）、`generation.count.json {"count":28}`；`lg031-real-proof2` worktree clean。
- close commit `54e7695` 相对 `54e7695~1 == e167724` 仅新增 `probes/lg031/PROOF2-CLOSE/**`（9 文件），
  **无** `backend/docs/frontend/tests` 改动。
- 收口在**只读快照工作副本**上执行；REAL-PROOF2 原 private store/raw/worktree 未移动/覆盖。
- 账本：本审计独立复跑前后 `generation.jsonl` hash 恒 `e9a1ef78…`、`count=28`；`new_model_generation=0`。
- 计数口径：旧 34 + proof1 24 + proof2 28 = 已知整体 **86 不变**。REPORT/STATUS 的「旧 phase 剩 6」指 **phase4**
  新增上限 16 实际用 10 所余，与 REAL-PROOF2 cap 48（用 28 余 20）**不同预算**；措辞易混，属**文档 errata**（非账本归零）。
  「oldremaining6」若被读成 REAL-PROOF2 余量即为**误读**，应以 `cap48 用 28 余 20` 为准（补遗澄清即可，**不改旧原报告**）。

## 4. 未测 / 不宣（NO 全产品 pass）

- **不宣**全产品 pass；**不宣**产品**自动**机器门执行通过（原 Task `authorized=[]`，外部只读机器 truth 有效但非产品自动门）。
- **不宣**自动 restart / checkpoint skip / 全 checkpointskip（产品该能力未实现，本包未新增运行时功能）。
- 产品自动机器门、版本级行为、全生命周期成本对照（LG-032 阶段 B）**仍待 032 同门集中验收**，本审计**不**预判其结论。
- 真实 Git worktree 非 OS 安全沙箱（既有真实限制，未变）。
- 本包**不合 main**（并行 032 准备 owner 只读 main@91550a9，不冲突）；无 push/deploy/publish/upload。

## 5. 建议（不自行修改产品/harness）

若判 LG-031 可 `done`：**仅由本 QA owner 添加补遗澄清**（A1/A2/A3 与「旧 phase 剩 6」口径），
mark `031 done` 待 **032 完整门**；frontmatter 更改须**保留历史重开/失败记录**（不得抹去 031 曾被 QA 重开为 in-progress 的史实）。
若坚持逐字证据标准，可要求 close owner 另派最小纠错包更正 A1/A2（**本审计不自修 harness/产品**）。
**本包无需新真实 review；建议 0。**

## 6. 证据

- `qa/lg031-proof2-close/evidence/negctl-independent.json`（本审计独立复跑原 4 负向对照，全拒）
- `qa/lg031-proof2-close/evidence/independent-negctl.json`（本审计自有 X1/X2/X3，全拒）
- `qa/lg031-proof2-close/independent_negctl.py`（独立对照脚本，只读 snapshot，写新输出）
- `qa/lg031-proof2-close/evidence/qarepro-close.json`（新拷贝独立复跑 close，实质终态与 committed evidence 一致）
