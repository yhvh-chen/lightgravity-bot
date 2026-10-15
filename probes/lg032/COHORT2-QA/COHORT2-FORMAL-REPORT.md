---
title: "LG-032 COHORT2 正式采样报告（STOP：入口 evidence 目录装配缺陷）"
doc_type: report
category: engineering
status: "STOP — cohort2 正式执行在第 1 个 attempt 后因入口/装配缺陷停止（真实 provider 1 attempt，ledger +19）；未完成 4 attempt；032 NOT done；no merge"
experiment_id: lg032-cohort2-formal-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "ec69eff"
entry_commit: "05de3c9"
audit_commit: "7ecf5e8"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 cohort2 入口最终核查 + 真实正式执行 owner；非产品/driver/entry 作者）"
---

# LG-032 COHORT2 正式采样报告

> 由 PM **批准的新完整 cohort2**，条件为独立入口核查 PASS。入口核查 **PASS**（`ENTRY-AUDIT.md`），
> 故按授权执行正式冻结 4 attempt。**第 1 个 attempt 后命中 STOP 条件（入口/装配缺陷），立即停止整个
> cohort2**，未自修、未重跑、未换名 bringup、未补样。旧所有字节保全。032 仍 in-progress，不 mark done，不 merge。

## 0. 结论（先给判断）

- **入口核查 = PASS**（0 real provider），已 commit `7ecf5e8`（`ENTRY-AUDIT.md`）与 `05de3c9`（保全 3 entry 文件）。
- **正式 cohort2 = STOP**：**仅第 1 个 attempt `s1_units__A` 真实执行**（19 次真实 generation reservation），
  该 attempt 因**真实模型无效 tool call** 失败；随后 driver 在写 evidence 时因
  `lg032-cohort2-formal/evidence/` **目录不存在**而 `FileNotFoundError` 崩溃 —— 此属
  **harness/装配错误**（冻结入口在全新独立输出 root 上无法写 evidence），按 PM 指令 ⇒ **立即 STOP 整个 cohort2**。
- **未完成既定 4 attempt**（仅 1/4）；`s1_units__B` / `s2_pipeline__A` / `s2_pipeline__B` **未运行**。
- **mode 协议本身正确**（详见 §3）：A 显式写 `False`、真 bootstrap 后实际 active flags congruent、restore off。
- **ledger 未 reset/未洗**：cohort2 物理 ledger `generation.jsonl` 19 行，`generation.count.json` = `{"count":19}`。
  旧 cohort1 invalid **87 单列永久保留**。032 已知真实总上限仍 = 87 + 192 = **279**；本次实际消耗 19（单列）。
- **不自修**：入口/overlay/harness 缺陷如实上报，交 PM 返修；本轮不新增正式路径。
- **032 仍 in-progress；不 mark done；不 merge main。**

## 1. 阶段 0 — 既有入口保全（byte-preserving）

- 核查前 dirty = **仅** 3 个未跟踪 entry 文件；精确保全 commit：
  - `05de3c9`「preserve formal entry runner + freeze/entry reports（0 real provider）」。
  - staged blob `run_formal.py` sha256 `a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040`
    == 核查前实际字节（未改逻辑、不重放 write）。
- 提交后 tree clean。正式 root / 独立输出 root 核查前后均 **ABSENT**。

## 2. 独立入口核查（PASS，`ENTRY-AUDIT.md`）

| 项 | 实测 | 判定 |
|---|---|---|
| entry sha256 | `a7477753…3040` | ✅ |
| overlay sha256 | `df565291…88bf` | ✅ |
| driver `run_attempt.py` | `503a807f…6208`（`--freeze-identity` OK），git blob `b1cc6c55…` == fix HEAD `8098514` | ✅ |
| config `final_cohort_config.py` | `a04a8f30…a117`，git blob `307ea0dd…` == fix HEAD | ✅ |
| driver/overlay bytes vs fix worktree | **逐字节 diff 空** | ✅ |
| phaseRoot | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`（核查时 `exists=False`） | ✅ |
| RUNS/EVIDENCE | `…/lg032-cohort2-formal/{runs,evidence}`（非 METHOD-FINAL/FINAL-COHORT） | ✅ |
| seed SHA s1/s2 | `seed.git` HEAD = `53458ac7…` / `6fa0fd00…` == pin == 冻结 | ✅ |
| 入口无核心逻辑复制/不放权限 | grep + 代码级只读确认 | ✅ |
| `--freeze-identity` / `--help` | rc=0，只读，无 runtime/Task/forward/Root 写；root 前后 absent | ✅ |
| 旧报告 driver 短 hash 描述差异 | 经 actual git object + 实际 sha256 比对为**描述性差异，非实质不一致** | ✅ 无 STOP |

**核查判定 PASS ⇒ 授权执行正式 4 attempt。**

## 3. 正式执行（STOP 于第 1 attempt 后）

### 3.1 固定协议（冻结）

- 顺序 **s1_units__A → s1_units__B → s2_pipeline__A → s2_pipeline__B**，各唯一一次、不补跑。
- 每 attempt：显式写 A=`False` / B=`True`；真 bootstrap 后 assert 实际 active flags；结束 restore off。
- 预算 cohort2 4×48=192；唯一正式 root `lg032-cohort2-data`；输出 `lg032-cohort2-formal/{runs,evidence}`。
- 入口命令（freeze §6）：`DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/COHORT2-QA/run_formal.py --sample … --arm …`，控制 timeout 400。

### 3.2 attempt 1 — `s1_units__A`（真实执行，失败）

| 项 | 值 |
|---|---|
| UTC start / end | `2026-10-15T21:12:18Z` / `2026-10-15T21:14:15Z` |
| elapsed | `116.14s`（rc=1，未超 timeout） |
| final_phase | `failed`；phases_seen `['executing','failed']` |
| 真实模型症状 | `System step error (HTTP 0): model produced an invalid tool call ("…unsupported mime type application/octet-stream")`；`HTTP 2: agent executor … HTTP 400 upstream error` |
| driver_error | `AppError: task has no active run candidate` |
| machine_gate / review / session_refs / cleanup / reviewer_cleanup | 均 **null**（未到达） |
| 真实 SDK session DB | 3 个（`task_01M50PH9D8HJ0FQYVNFH35RPCV/*.db`）——真实 SDK 双/多 worker 已起 |
| 真实 Task / subtasks | `task_01M50PH9D8HJ0FQYVNFH35RPCV`；3 subtasks |
| 真实产物 | `artifacts/run_01M50PH9G1HE2Y1TEFZWJS2GTQ/lg006-diff.patch` sha256 `8ac86de5…4b77` |

**该 attempt 属「模型真失败」型有效 attempt 失败**（可继续既定下一个）；**但因下述装配缺陷，未继续。**

### 3.3 mode 协议证据（attempt 1，正确）

```json
{
  "arm": "A", "expected_enabled": false,
  "settings_switches": {"decentralized_claim_enabled": false, "claim_lease_seconds": 300,
                        "collab_requests_enabled": false, "default_worker_connection_ref": "lg032-worker"},
  "dispatcher_autonomous_claim": false, "dispatcher_autonomous_pool": false,
  "dispatcher_decentralized_enabled": false, "congruent": true, "problems": []
}
```
`mode_restore.restored_off = true`（结束恢复 off）。⇒ **A 显式 False + 真 bootstrap 后实际 active flags 全 False**，协议正确。

### 3.4 ledger（物理、连续、未 reset）

| 项 | 值 |
|---|---|
| 物理路径 | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data/generation/generation.jsonl` |
| ledger before（attempt 1 前） | 不存在（count 0，`physical_history_exists_at_freeze=false`） |
| ledger after（attempt 1 后） | **19**；`generation.count.json` = `{"count":19}`，sha256 `be90a0f9606c3c25a422bc22dc637c2b99af3e4d3b9d9179c5aee6aa78658585` |
| `generation.jsonl` sha256 | `15a4bb003f844a7095632fa8a4ac97419b6f3a48d53858107b1bc4bf89595fbb`（19 行，均 `kind:"reserved"`） |
| 计数器身份 | `counter_is_global=true`；`counter_ledger_matches_frozen=true`；`persistent=true`；`limit=192` |
| 归因 | 全 19 次均为本次 attempt1 真实 reservation（pid 2599290），无旧数据、未归零 |

> 计量随真实执行推进而**前移**，非 reset。因 STOP，剩 48×3=144 预算未消耗。

### 3.5 **STOP 原因：harness/装配缺陷（未自修）**

```
FileNotFoundError: [Errno 2] No such file or directory:
  '/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/evidence/s1_units__A.json'
  at run_attempt.py:888  (C.EVIDENCE_DIR / f"{attempt_id}.json").write_text(...)
```

- **根因（确定性、可复现、非瞬态）**：`run_formal.py` 将 `EVIDENCE_DIR` 重定向到**全新**独立输出 root
  `lg032-cohort2-formal/evidence`，但**入口与 driver 都不创建该目录**：
  - driver 仅 `mkdir` `RUNS_DIR/<attempt_id>`（`run_attempt.py:532/540/552/559/561`），**从不**创建 `EVIDENCE_DIR`；
  - 入口 `run_formal.py` 仅设置/断言 `C.EVIDENCE_DIR`，**无 mkdir**。
  - 旧布局 `EVIDENCE_DIR = COHORT/evidence` 是**已 commit 的 repo 目录**（预先存在），故旧 cohort-ready /
    method-final 从未暴露此缺陷；新独立 root 首次暴露。
- 结果：`runs/…/result.json` 写出成功，但 evidence 副本写入失败，入口 rc=1。
- **按 PM 指令「harness/装配…错误 ⇒ 立即 STOP 整 cohort2；别继续/自修/换名 bringup/补样」⇒ STOP。**
  本 owner **不自修 entry/harness**；缺陷交 PM 返修（QA/入口作者），修好并重新冻结后方可再执行。

## 4. 完成度 / 质量 / 成功门

- **attempts 完成**：**1 / 4**（仅 `s1_units__A`，且失败）。
- **成功率**：`s1_units__A` = **0/1**（模型真失败，非协议失败）。
- **first-pass machine pass**：0（未到达 machine gate）。
- **elapsed**：attempt1 = 116.14s；cohort2 总 wall ≈ 12:18Z→12:15Z/12:16Z（含只读核查与保全）。
- **角色 calls**：真实 generation reservations = **19**（worker 为主；reviewer 因 task failed 未达）。
- **QArepair/recheck/fail cost**：本次执行内 0 次 business repair（未达 repair 阶段）；本失败的 19 次计入 cohort2 成本单列。
- **usage unknown 不记 0**：真实 model calls/tokens 精确分布 **unknown**（仅 reservation 计数 19）；货币成本 **unknown**（不记 0）。

## 5. 成本台账（单列，不洗、不混）

| 项 | 值 |
|---|---|
| 旧 cohort1（@379c089，判 AB invalid） | **87** = 21+26+19+21，**逐字节保留**（`lg032-method-final-data/generation/count=87`） |
| 旧 LG-031 | 86（单列） |
| 旧 023 cohorts / eval | 45 / 4 / 16 / 65（单列） |
| core | **unknown**（不记 0） |
| 本次 cohort2 已消耗 | **19**（attempt1 only，单列） |
| 本次 cohort2 未执行剩余 | 144（48×3，因 STOP 未消耗） |
| 032 已知真实总上限 | **279** = 87 + 192（未变） |
| PI 开发/QA（shared） | **unknown**，不 0、不分摊；shared unknown |
| 本 owner 追加 pi 成本（入口核查 + 执行） | **unknown**（不记 0，不预设省 token） |

## 6. 保全路径（全部实际存在）

| 内容 | 绝对路径 |
|---|---|
| 正式 phase root | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`（real 775；ledger/secrets 子目录） |
| 物理 ledger | `…/lg032-cohort2-data/generation/generation.jsonl`（19 行）+ `generation.count.json` |
| 正式 output root | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal`（`runs/s1_units__A/`；`evidence/` **缺失**，即 STOP 证据） |
| attempt1 result | `…/lg032-cohort2-formal/runs/s1_units__A/result.json` sha256 `aa77b38a03fb57168219675f403670778f55b383e9bfa36dcde8d0ead36f35f1` |
| native SDK sessions | `…/lg032-cohort2-data/native-sessions/task_01M50PH9D8HJ0FQYVNFH35RPCV/*.db`（600） |
| 入口审核报告 | `probes/lg032/COHORT2-QA/ENTRY-AUDIT.md`（commit `7ecf5e8`） |
| 入口/冻结/初版报告 | `probes/lg032/COHORT2-QA/{ENTRY-REPORT.md,COHORT2-FORMAL-FREEZE.md,run_formal.py}`（commit `05de3c9`） |
| 私有运行日志（700，项目旁、非 /tmp） | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-private-logs-20261015T211153Z/`（STATUS/REPORT-DRAFT/stdout/stderr/result 副本） |
| 旧 cohort1 原件 | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data/**`（未碰，count=87） |

## 7. 模式前后 & SDK stop & seed/candidate

- **mode before/after**：attempt1 before=default off；after(A 写)=False（显式）；真 bootstrap 后实际 dispatcher flags 全 False；restore off=true。**s1_units__A 无继承污染**（首个 attempt，无前序 B）。
- **s2_pipeline__A 不得继承 B**：**未验证**（未执行；因 STOP）。
- **SDK stop**：真实 SDK 起 3 个 session DB；worker 因模型 invalid tool call 失败，task `failed`；ideal stop/reviewer teardown **未到达**（未 produce delivered run）。
- **seed hash**：s1 `53458ac742b5aa4fd6913000aeeb69ae94cc80c1`（initial_head == seed_head）。
- **candidate hash**：仅有 run 级 `lg006-diff.patch` sha256 `8ac86de5…4b77`；per-node diff / 绑定 accept **未到达**。

## 8. cohort1 无效结论补遗（不覆写原 PASS 报告）

- 第一正式 **cohort1** 因 **mode 污染**（shared `settings.data_dir` 下 B 写 True、A 未显式写 False ⇒ `s2_pipeline__A` 继承 B）
  判 **AB invalid**；其 87 真实请求**永久保留、单列、不洗**。原 `REPORT-SERIAL-R1.md` 的 PASS 记录**逐字节保留**，
  本报告**不覆写**，仅补遗：cohort2 入口核查虽 PASS，但正式执行因入口装配缺陷 STOP，**cohort2 未产出有效 AB 结论**。

## 9. 正/负边界

- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖原件；旧所有字节保全。
- 未 nested proxy / push / deploy / publish / main write；未碰 `8123` 或他包进程。
- 未改产品源（tree `55e4de56…` 未变）；未改 driver/overlay 任何字节；未改 caps/prompt/plan/tool；未换 provider。
- 真实 credential 仅受控 env（`DEEPSEEK_API_KEY`），**未打印/未写提示词/未入仓库**；仓库只脱敏摘要/sha。
- 未自修 entry/harness；STOP 后未继续、未重跑、未换名 bringup、未补样。
- **未 mark 032 done / 未 formal 完成 / 未 main merge**。

## 10. 交接（明确）

| 项 | 状态 |
|---|---|
| branch / HEAD | `qa/lg032-cohort2` @ **`7ecf5e8`**（含 05de3c9 保全 + 7ecf5e8 入口审核；本报告 commit 见下） |
| clean | **clean**（工作区无未提交改动，报告提交后仍 clean） |
| 四状态 | 入口核查 **PASS**；正式 cohort2 **STOP**；032 **in-progress（未 done）**；无 merge |
| 是否 STOP | **是**（harness/装配错误） |
| 待 PM 动作 | 指派入口/harness 作者**修复**：入口（或 driver）在真实 formal 运行前创建 `EVIDENCE_DIR`（等价旧 tracked evidence 目录语义），修好后**重新冻结入口并重跑入口核查**，再由 PM 授权是否重执行 cohort2（**不得**以本次 19 次成本当有效 AB；该 19 单列留存） |

## 11. 修订历史

- 2026-10-16：保全 3 entry 文件（`05de3c9`）；独立入口核查 **PASS**（`ENTRY-AUDIT.md`，`7ecf5e8`）；
  执行正式 attempt 1 `s1_units__A`（真实 19 reservations，模型失败 + evidence 目录装配缺陷）⇒
  **STOP 整个 cohort2**；本报告先于补充调查/commit 落盘。
