# REPORT — LG-049 R3 `N-R3-LIFECYCLE` 选定资料交付完整生命周期独立验证

- 日期：2026-10-16
- 任务：**LG-049《验证选定资料交付完整生命周期》**（P0，`parent: LG-047`，`depends_on: [LG-048, LG-046]`）
- Executor / owner：**`agent:pi-proto-lifecycle-qa`**（独立于全部产品实施者）
- Campaign：**`N-R3-LIFECYCLE`**（root PM 显式 R3 授权，hard cap **16**）
- QA worktree：`/home/yhvh/code/lightgravity-bot-worktrees/proto-material-lifecycle-qa-r3-20261016`
- QA branch：**`qa/proto-material-lifecycle-r3-20261016`**（from frozen prep）
- Frozen prep commit：**`08215d8`**（`main` 序列 prep：I `256cd78` + L `d8d8b4e` + PM R3 文档）
- 产品代码：**冻结、零改动**（`backend`/`frontend`/`tests`/`examples` 与 `0188ca2` 逐字节一致，见 §6）
- 结论：**PASS_WITH_LIMITATIONS**（硬流程真实通过；限制明确列出，见 §9）

> 本报告只声明**本 campaign 真实观测到的事实**。不宣告 LG-047 done、不宣告累积成本已知（成本 unknown 非 0）、不代表用户最终验收。所有 raw/evidence/ledger 已持久保存。

---

## 1. 结论摘要（先报早）

在冻结既有产品上，真实跑通**一条完整 SDK 交付生命周期**，全部关键阶段到达且为真实证据：

| 阶段 | 结果 | 证据 |
|---|---|---|
| 原生 API 上传 alpha UTF-8（无 seeded derivative） | **PASS** | `evidence/sdk_lifecycle.json` `steps.upload`（`status=extracted`, `v1`, `content_hash=d34f0ca58b8d…`, receipt `native UTF-8 text extracted (model-free)`） |
| 正文/hash/version/scope 校验 | **PASS** | `steps.source_verify`（2223 chars, ORION+owner, kind=machine）；scope global（`task_ref=null`） |
| EXACT 前失败普通目标 → delivery/create_task | **PASS** | `steps.global_message`（`kind=task`, `intent=delivery`, `creates_task=true`） |
| 程序规则计划 `deliver` + `verify` | **PASS** | `plan_subtasks=["deliver","verify"]`，`plan_source=rules` |
| 真实 SDK file 工具写出 **6 事实全对** | **PASS** | `deliverable_text`；`facts_all_present=true` |
| `deliver` 节点正常执行 | **PASS** | `node_states.deliver=passed`；事件 `running→verifying→passed (minimal machine check passed)` |
| **`verify` 节点正常执行（非 429）** | **PASS** | `node_states.verify=passed`；同事件序列（R2 曾在此 429 失败） |
| 程序机器门通过 | **PASS** | `task.phase_changed verifying→awaiting_acceptance` reason `machine checks passed and resources confirmed stopped` |
| **真实独立 ModelReviewer** | **PASS** | `error.recorded mode=review code=review_completed outcome=passed reviewer=model-reviewer reviewer_kind=model model_calls=1` |
| **worker stop CONFIRMED** | **PASS** | Run `cleanup.status=done`；`member.released`（`run scheduling finished`） |
| **reviewer stop CONFIRMED** | **PASS** | Run `reviewer_cleanup={status:done, agent_closed:true, proxy_stopped:true, confirmed:true}` |
| **stop 均在 QA accept 之前** | **PASS** | accept 前 phase=`awaiting_acceptance`（stop gate 已通过）；见 §5 时序 |
| API accept（乐观 revision）→ done | **PASS** | accept HTTP 200 `confirmed=true` `phase=completed`；Task `status=done` `acceptance.status=accepted` |
| artifact refs → 真实授权内容/download body | **PASS** | `post_accept_verify.json`：两条 `evidence:…@sha256` ref 均 200 且返回真实 diff body |
| Task history Sources 匹配 bindings | **PASS** | `selected_trigger.message_id=msg_r3sdk_1792145837`，`refs=[source_01M523EJTV1K7MAS8W9S5PVDK2]` == 上传 source |

**无** fake executor / fake reviewer / 人为 task 状态 / seeded 文件 / force accept / patch。产品代码零编辑。

**预算**：product 持久账本 **8 / 16**（剩余 8）；独立 campaign 账本核算一致 **8 / 16**。本报告**不**宣告 R3 累积成本已知（成本 unknown 非 0）。

---

## 2. 显式边界与不宣称项（honest boundaries）

- **不宣告 LG-047 done**；LG-047 仍 `in-progress`。**不宣告 LG-049 done**（标 done 留待 root closure 复核本报告）。
- **不宣告累积成本已知**：R1 已知 1 次 + 账目缺口、R2 actual 8 次成本**分别保留**；R3 本 campaign 8 次；**全累积成本 unknown、非 0**（产品未对每次前向报告 token）。
- **不代表用户最终验收**：本轮为技术性 QA 生命周期验证；用户最终验收仍待定。
- **不重跑**：不重跑 I 的真实 UI/chat 浏览器流程（复用），不重跑 L 的 routing 矩阵（复用），不跑全量测试（代码未改，见 §7）。
- **不触** `8123`、不 push/deploy、不 reset/stash/clean、不杀 inflight、不改 I/L/R2 worktree/campaign/ledger。
- **无** browser / OCR / embeddings / 重复连接测试；单次 initialize 自有 dataRoot（R2 根未复用/未重置）。

---

## 3. 真实生命周期证据（逐步）

### 3.1 原生上传（真实，非 seed）

`POST /api/v1/sources`（真实产品 API，原生 UTF-8）：

```json
{ "status": 201, "source_id": "source_01M523EJTV1K7MAS8W9S5PVDK2",
  "status": "extracted", "source_version": 1,
  "content_hash": "d34f0ca58b8dbfbd4c9ac29be31aba7122500cb1a3317e3c19a6ed7b3d59af6f",
  "scope": {"task_ref": null, "project_ref": null, "inbox_ref": null} }
```

receipt #2 detail = **“native UTF-8 text extracted (model-free)”**，`formal_path=derivative/machine.v1.md`，`searchable=true`。**无 OCR / 无 seeded derivative**。fixture 字节 sha256 = `d34f0ca58b8d…`（1601→1701 bytes）与 `examples/…/alpha-brief.txt` 一致。`GET …/content?kind=auto` 返回 2223 chars、含 ORION-71 与 Halden Reyes、`kind=machine`。

### 3.2 EXACT 前失败普通目标 → 程序交付路由

EXACT 目标（含 `approved` 子串，R2 曾误分类为 decision）：

> “Create a Markdown file orion-summary.md using only the selected brief. Include project name, programme owner, primary launch date, **total approved budget**, project ID, and change ticket. Return the file as the deliverable.”

`selected_sources=[source@v1]`。`POST /api/v1/conversations/global/messages` → `kind=task`、`data.intent=delivery`、`data.creates_task=true`、`task_id=task_01M523EJZBG1X1BMTQD8JE7TTH`。**路由正确**（J 修复生效，与 L 的 routing PASS 一致）。

### 3.3 程序规则计划：deliver + verify（两个 SDK 节点）

Run `run_01M523EK321M4KD494CA042R1M`：`plan.source=rules`，`plan_hash` 承载，`subtasks=[deliver, verify]`，`verify.depends_on=[deliver]`，`connection_pin.connection_id=conn-worker`（openai-compat, `deepseek-v4-flash`）。**无模型 planner**。

### 3.4 真实 SDK worker + 6 事实 deliverable

`deliver` 节点：真实 SDK file 工具 `write_to_file` 在授权 Task 工作区写 `orion-summary.md`。最终正文（`workspaces/tasks/task_01M523EJZBG1X1BMTQD8JE7TTH/orion-summary.md`，sha256 `a4d5012fb98cd36319b7b8bce27a8cc9047fd307232aa506537a72cb163b2eae`）：

| Field | Value |
|---|---|
| Project name | ORION-71 |
| Programme owner | Halden Reyes |
| Primary launch date | 2027-03-14 |
| Total approved budget | 418,250 EUR |
| Project ID | PRJ-ORION-71 |
| Change ticket | CB-8842 |

`facts_all_present=true`（6/6）。**注意**：worker 明确用 “Total approved budget” 而非 finance-held reserve line（37,900 EUR）——正确。

### 3.5 `verify` 节点正常执行（R2 曾 429）

事件（`events/task_01M523EJZBG1X1BMTQD8JE7TTH/events.jsonl`）：

```
subtask …A  running → verifying ("worker returned success") → passed ("minimal machine check passed")   # deliver
subtask …B  running → verifying ("worker returned success") → passed ("minimal machine check passed")   # verify
```

两个 SDK worker 节点均**正常执行并 passed**，**无 429**。R2 的 429 是全局 8 上限耗尽；R3 cap 16 足以完成整链（M 诊断 §4.2 提案 ≥15，本 campaign 实测 8）。

### 3.6 真实独立 ModelReviewer

事件：

```json
{"type":"error.recorded","payload":{"mode":"review","code":"review_completed",
 "outcome":"passed","findings":0,"unsubstantiated":0,
 "reviewer":"model-reviewer","reviewer_kind":"model","model_calls":1,
 "usage":{"unknown":["usage"]}}}
```

**真实独立 model reviewer**（`reviewer_kind=model`，独立 reviewer 连接 `conn-reviewer`），outcome `passed`，`model_calls=1`。这与 R2 从未到达 reviewer 形成对比——**R2 的 UNVERIFIED 项本轮全部到达**。

### 3.7 stop gate（worker + reviewer 均在 accept 前 CONFIRMED）

Run 终态（`runs/run_01M523EK321M4KD494CA042R1M/RUN.md`）：

```yaml
state: completed
cleanup:        {status: done}                                   # worker
reviewer_cleanup: {status: done, agent_closed: true, proxy_stopped: true, confirmed: true}   # reviewer
```

事件：`member.state_changed → released (`run scheduling finished`)`、`member.released`、`cleanup.updated {scope:reviewer, confirmed:true}`。随后 `task.phase_changed verifying→awaiting_acceptance`，reason = **“machine checks passed and resources confirmed stopped”**。

- **worker stop CONFIRMED**：`cleanup.status=done` + `member.released`（stop gate 的 `sessions_stopped` 与 `slot_released` 均通过）。
- **reviewer stop CONFIRMED**：`reviewer_cleanup.confirmed=true`（独立 reviewer 资源真实关闭；非由 worker 推断）。
- **时序**：stop 事实写于 `awaiting_acceptance` 之前；QA user accept 发生在 gate 通过之后（§4 的 accept 步骤）。满足“worker+reviewer stops CONFIRMED/idle/released BEFORE QA user accept”。

### 3.8 API accept（乐观 revision）→ done

```
POST /api/v1/tasks/task_01M523EJZBG1X1BMTQD8JE7TTH/actions
{ "action":"accept", "request_id":"lgr3-accept-…",
  "expected_revision":10, "expected_requirements_revision":1,
  "expected_deliverable_revision":1, "target_run_id":"run_01M523EK321M4KD494CA042R1M" }
→ 200 { "action":"accept", "state":"confirmed", "confirmed":true,
        "phase":"completed", "acceptance":{"status":"accepted",
        "decided_at":"2026-10-16T10:17:42.113Z","decision_ref":"lgr3-accept-msg_r3sdk_1792145837",
        "candidate_ref":"run_01M523EK321M4KD494CA042R1M", "candidate_plan_hash":"07bf8753…",
        "evidence_refs":["orion-summary.md","evidence:run_…/…lg006-diff.patch@sha256:058254de…",
                         "evidence:run_…/…lg006-diff.patch@sha256:4b707df3…"]}}
```

最终 Task 实体：`status: done`，`phase: completed`，`acceptance.status: accepted`，`active_run: null`（槽已释放），`deliverable_revision: 1`。**乐观 revision 校验生效**（`expected_revision=10` 匹配）。

### 3.9 artifact refs → 真实授权内容；history Sources 匹配

`evidence/post_accept_verify.json`（post-accept，零模型调用）：

- 两条 `evidence:<run_id>/<name>@sha256:<hex>` ref 经 `/artifacts/content` 均返回 **200**，返回真实 diff body（504 / 427 chars，含 `orion-summary.md` 内容）——**授权内容可达**。
- `selected_trigger.message_id = msg_r3sdk_1792145837`，`refs = [source_01M523EJTV1K7MAS8W9S5PVDK2]` == 上传 source == history 用户消息 `selected_sources` 条目（source_id/version/hash 一致）。**Sources 匹配 bindings**。

---

## 4. 预算与账本对账（cap 16）

### 4.1 独立 campaign 账本（append-only，转发前预留）

- 单次 initialize：`campaign/manifest.json`（campaign `N-R3-LIFECYCLE`，cap **16**，created_ts）；**不**复用/重置 R2 根与 counter。
- guard selftest（`raw/guard_selftest.txt`）全 pass：**deny before init**、corrupt count deny、corrupt history deny、manifest-missing-deny、**no auto-extend**。
- 账本：`history.jsonl` append-only；`count.json` 原子快照。**转发前**持久预留；跨重启不归零。

### 4.2 产品持久账本（durable product generation ledger）

```
campaign/product-data/generation/generation.count.json  = {"count":8}
campaign/product-data/generation/generation.jsonl        = 8 条 reserved（count 1..8，同 pid 3953426）
```

`GET /_lgr3_generation` 引导时 = `{count:0, limit:16, remaining:16, persistent:true, corrupt:false}`；运行后 = 8。

### 4.3 逐请求 role/node 对账（不 dump 秘密）

`raw/ledger_reconciliation.json`：product reserve 逐条与 SDK 会话 `gen_metadata` 对账：

| node | 会话（conversation_id） | gen_metadata（模型调用） | product reserve count |
|---|---|---|---|
| **deliver** | `e40027c09f30de407a2299be08cb40cc` | **2** | 1–2 |
| **verify** | `1b884a218a9dd1338570f476ce5ed5c0` | **5** | 3–7 |
| **ModelReviewer** | （reviewer 连接） | **1**（事件 `model_calls=1`） | 8 |
| **合计** | — | **8** | **8 / 16** |

- 顺序由 SDK 会话 step 时间戳证实：deliver 步骤 ts ≈ `…458.39–458.42 s`，verify ≈ `…458.45–458.53 s`（deliver 先于 verify，与 `verify.depends_on=[deliver]` 一致）；reviewer 最后。
- 独立 campaign 账本核算 = **8 / 16，remaining 8**，与产品持久账本**一致**。
- 说明：`history.jsonl` 第一次追加时因 dict 迭代顺序把 node 标签按 verify-first 写入；已追加**更正行** `kind=reconciliation_correction` 明确正确时序归属（deliver=2, verify=5, reviewer=1）；**count 语义未受影响**。凡此一处均已如实记录，不掩盖。

### 4.4 观察缺口（M 诊断指出）已部分修补

M 诊断 §4.1 指出“全局 429 无法事后区分节点消耗”。本轮通过**逐会话 `gen_metadata` 计数 + product reserve 逐条对账**补上该缺口（deliver=2 / verify=5 / reviewer=1）。**仍未**得到 token/cost（产品 `usage: {unknown:["usage"]}`）——**成本仍 unknown 非 0**。

---

## 5. 时序证明（stop 先于 accept）

```
upload → global message(create_task) → run.created → recruiting
→ executing → deliver subtask running→verifying→passed (artifact.produced)
→ verify  subtask running→verifying→passed (artifact.produced)
→ verifying → [review model-reviewer passed, model_calls=1]
→ cleanup.updated(reviewer, confirmed=true) ; member.released(worker)
→ awaiting_acceptance  ("resources confirmed stopped")
→ *** QA user accept (HTTP 200, phase=completed) ***
→ done
```

stop 事实（worker done + reviewer confirmed）**全部写于** `awaiting_acceptance` 之前；accept 之后。满足验收条件“BEFORE QA user accept”。

---

## 6. 产品冻结（零代码改动）

QA worktree HEAD = frozen prep `08215d8`。产品树哈希与 `0188ca2` 逐字节一致：

| tree | `08215d8` | `0188ca2` | match |
|---|---|---|---|
| `backend` | `8b4256a412cccd010dcbbfd9966f9530413c4172` | `8b4256a412cccd010dcbbfd9966f9530413c4172` | ✅ |
| `frontend` | `07618bb29bed372f47422b584070101196ce86bc` | `07618bb29bed372f47422b584070101196ce86bc` | ✅ |
| `tests` | `9a37448e61af6023d0306c59067864c9ae8b31cc` | `9a37448e61af6023d0306c59067864c9ae8b31cc` | ✅ |
| `examples` | `63ee05cd045a4233f28205c182d798d114f2f910` | `63ee05cd045a4233f28205c182d798d114f2f910` | ✅ |

工作树除 `probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/**` 外无改动。**产品/测试/依赖/前端零编辑**。

---

## 7. 复用证据与 hash 绑定（不重跑）

| 复用证据 | 来源 | 绑定产品哈希 | 说明 |
|---|---|---|---|
| 真实 UI：upload→原生提取→选材→真实 DeepSeek 回答→Sources→reload→widths（390/1024/1440、transition overshoot 0） | I-R2-QA `evidence/chatflow-19of20/flow_chat.json` (+`raw/chatflow-19of20/`) | I 绑定候选 `56a2dd9`：backend `179167936b…`，frontend `07618bb2…` | I 与 frozen prep 的 **backend 唯一差异 = J 的 `classification.py` 修复**；UI/answer/select/Sources/width 路径不受 classification.py 影响。**同一前端树 `07618bb2…`**。 |
| Routing：EXACT 目标 delivery/create_task + 负例不建 Task + 程序计划 deliver+verify + brief 到 worker | L-R2-ROUTING-QA `REPORT.md` + `raw/*` | L 绑定 base `0188ca2`：backend `8b4256a4…` | **与 frozen prep backend 完全相同**。 |
| 后端类型检查（139 files clean） | H-R1-INTEGRATION `raw/mypy.log` | R1 合并候选（139 files） | 代码未变；未重跑全量。 |
| 后端全量（930 passed / 2 skipped） | H-R1-INTEGRATION `raw/pytest-full.log` | R1 合并候选 | 代码未变；未重跑。 |
| 定向集合（240 passed） | L-R2-ROUTING-QA `raw/checks.log.txt` | base `0188ca2` | 与 frozen prep 一致。 |

**本 campaign 未新增非模型单元测试运行**（代码未改，遵“不为纯复用重跑全量”）。真实 SDK 生命周期证据见 §3。

---

## 8. 边界声明（本 campaign 做/不做）

**做**：自有持久 worktree + branch（from frozen prep）；自有 probe `probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/**`；绑定 `PYTHONPATH=own/backend`（`raw/` 记录解析到本 worktree，非 main）；真实产品 API factory + **实际 lifespan**；env `DEEPSEEK_API_KEY` 仅作 `credential_ref`（**未打印/未存储**）；复用 I 的 `launch_app.py`/`with_server.py` 思路并**选择性**改造；`sdk_lifecycle.py` 修正 attempt-1 bug（phase 恒非空 → 2s 提前 teardown）为**显式终态集合 + ≤300s 有界轮询**。

**不做**：不 import 旧 browser driver；不重跑旧 stub 循环；不 fake executor/reviewer/状态；不 seed 文件；不 force accept；不打 patch；不触 `8123`；不 push/deploy；不 reset/stash/clean；不扩 cap；不杀 inflight（live 状态未知时 bounded poll + 诚实报告）。

---

## 9. Verdict — PASS_WITH_LIMITATIONS

**所需真实流程全部满足**：真实 SDK artifact 写入（6 事实全对）+ `deliver`/`verify` 双节点正常执行 + **真实独立 ModelReviewer passed** + 程序机器门 + **worker/reviewer stop CONFIRMED 于 accept 前** + **QA accept 真实 `done`** + artifact refs 真实内容 + I/L 覆盖 sufficient。

**限制（必须保留，不得洗白）**：

1. **成本 unknown 非 0**：产品未报告 token/cost；R1(1+gap)/R2(8)/R3(8) 成本分别保留，**全累积成本 unknown**。
2. **前端未构建**：QA worktree `frontend/dist` 不存在，`launch_app` 提示 “serving minimal bootstrap page”；本 campaign 为 API 级生命周期，未跑浏览器（浏览器 UI 证据复用 I 的真实 UI proof，见 §7）。
3. **orion-summary.md 直接 ref 经 `/artifacts/content?evidence_ref=orion-summary.md` 返回 400**：该端点要求 `evidence:<run>/<name>@sha256:<hex>` 形态；deliverable 经**授权 Task 工作区**判定，两条 diff evidence ref（200，真实 body）证明其内容。属端点契约行为，非缺陷。
4. **R3 campaign 不能证明未来运行**：R2’s 429 blocker 在本 cap16 下***本次***不出现（实测 8/16）；不据此推断所有预算情形。
5. **未重跑全量测试**：代码未改，复用 H/L 证据（§7）；若需全量回归归后续版本 QA。

**不是 FAIL / INCOMPLETE**：所有必需的硬流程真实到达且通过（与 I-R2 的 FAIL/INCOMPLETE 相对）。

---

## 10. 证据索引（本 campaign）

- Lifecycle raw：`evidence/sdk_lifecycle.json`；产品数据 `campaign/product-data/**`（tasks/runs/events/artifacts/sources/native-sessions/workspaces/generation）
- Post-accept：`evidence/post_accept_verify.json`
- Boot readiness（0 调用）：`evidence/ready_boot.json`、`raw/boot_readiness.json`
- 账本：`campaign/manifest.json`、`campaign/history.jsonl`、`campaign/count.json`、`raw/ledger_reconciliation.json`、`raw/guard_selftest.txt`、`raw/campaign_init.json`
- 复用：I-R2-QA `evidence/chatflow-19of20/`、L-R2-ROUTING-QA `REPORT.md`+`raw/`、H-R1-INTEGRATION `raw/{mypy,pytest-full}.log`
- 脚本：`scripts/{api,launch_app,with_server,campaign_ledger,sdk_lifecycle,boot_readiness,post_accept_verify,reconcile_ledger}.py`

---

## 11. 交接（root PM 闭环）

- QA branch：**`qa/proto-material-lifecycle-r3-20261016`** @（本报告提交，见 commit）
- 候选/冻结 hash：**产品树 = `0188ca2`**（backend `8b4256a4…` / frontend `07618bb2…`），frozen prep **`08215d8`**
- 真实调用计数：**8 / 16**（deliver 2 + verify 5 + reviewer 1）
- stop：worker **CONFIRMED (done+released)**，reviewer **CONFIRMED (agent_closed+proxy_stopped)**
- **未合并回 main**；**未标 LG-047/LG-049 done**（留待 root closure 复核本报告）；用户最终验收仍待定。
