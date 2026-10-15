---
title: "LG-032 METHOD-FINAL 正式采样执行 STATUS（owner: pi formal-run runner）"
doc_type: status
category: engineering
status: "AUTHORIZED; formal execution in progress; real attempts recorded below; 032 NOT done"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final
branch: qa/lg032-method-final
head_at_authorization: "890b6e8c10b1ccf6cd75b7b87c6db444ebec70e0"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner；非产品/harness 作者；新 pi context）"
---

# LG-032 METHOD-FINAL 正式采样执行 STATUS

> 本文件由**正式采样执行 owner**（新 pi context，非产品/driver 作者）维护。它记录 PM 授权、执行前核对、
> 每个固定 attempt 的开始/结束（ID/UTC/ledger count/冻结 hash/实际 state）。**不 mark 032 done、不 merge main**。

## 0. PM 授权与冻结协议（执行前记录）

- **PM 授权**：主 PM 批准 METHOD-FINAL 独立审计 PASS 候选并**授权现在执行**（2 sample × A/B × 1 = 4 attempt）。
- **冻结协议文件**（本包，最终协议）：`FORMAL-FREEZE.md` + `REPORT-FINAL.md` +
  `method-final-freeze-candidate.manifest.json`（contract `1.11.0` / SDK `0.1.22`）。
- **授权 head**：`890b6e8`（branch `qa/lg032-method-final`，源 tree `55e4de56` 同 main `5df1956`/`0814b80`）。
- **执行入口**（唯一）：`probes/lg032/METHOD-FINAL/probes/run_formal.py --sample <s> --arm <A|B>`（先装 overlay，
  再走字节同 cohort-ready 的冻结驱动 `run_attempt.py`）。
- **唯一 phase root**：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data`（执行前**尚不存在**）。
- **唯一 attempt IDs**：`s1_units__A`、`s1_units__B`、`s2_pipeline__A`、`s2_pipeline__B`，各唯一一次。
- **顺序**：s1_units A → s1_units B → s2_pipeline A → s2_pipeline B。
- **预算**：per-attempt 48 / total 192，转发前硬拒，同一物理 ledger 累加；**旧成本不清零**。
- **caps（protocol 冻结，不改）**：output ≤ 16000、HTTP 120s、SDK retry 0、max_parallel 1、
  worker 12 model / 32 tool、reviewer 1、至多 1 业务 repair；模型 `deepseek-v4-flash`。
- **唯一自变量**：协作开关（`decentralized_claim_enabled`/`autonomous_pool`）；**默认 off，仅 arm B attempt 内开**。

## 1. 执行前核对（owner，2026-10-16，real provider 0）

| 项 | 期望（冻结） | 实测 | 结果 |
|---|---|---|---|
| git HEAD | `890b6e8` | `890b6e8c10b1ccf6cd75b7b87c6db444ebec70e0` | PASS |
| 工作区 | 仅方法审计副产品（gateA0 复验） | 1 个 untracked `evidence/gateA-20261015T204337Z.json` | PASS |
| 产品 tree | `55e4de56` == main == 0814b80 | `backend/lightgravity` = `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | PASS |
| driver `run_attempt.py` | `d1994948…` | `d19949480e17d9fe457ac1b87448052f31bdb6edf017f60206ba641933d50d64` | PASS |
| `fake_upstream.py` | `de9d7a35…` | `de9d7a3547dd0a99e615d8cf1f2d899cf31e5d82f34a47fbb482db15a515a045` | PASS |
| `final_cohort_config.py` | `a04a8f30…` | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | PASS |
| `hard_gate.py` | `0067af1c…` | `0067af1cd9927b26f12f6c33792a2ea435a2cc07f167914f0ebe2df20b7c09d7` | PASS |
| `run_dry.py` | `f792da28…` | `f792da2842def8edd6accb14fd09eb0a32b8063d7a2186972fbec8da676ac559` | PASS |
| 机器 truth s1 | `d39d906c…` | `d39d906c746d8e6a753268e5fc55a16aaddb8e145cc1146482c0245e148169fb` | PASS |
| 机器 truth s2 | `06e2352f…` | `06e2352f6808969257fcbb1925c756ccbdb2ecf08e376b036ec36af387bdca59` | PASS |
| seed pin s1 | `53458ac7…` | `53458ac742b5aa4fd6913000aeeb69ae94cc80c1` | PASS |
| seed pin s2 | `6fa0fd00…` | `6fa0fd006ff058a7299f5e6dc42013fa051303de` | PASS |
| phaseRoot | 不存在 | 不存在 | PASS |
| 4 attempt 正式输出 | 无 | `METHOD-FINAL/runs/` 不存在、无 `evidence/<attempt>.json` | PASS |
| 自有冻结进程 | 无残留 | 无 run_formal/run_attempt | PASS |
| SDK | `0.1.22` | venv 已核 | PASS |
| DEEPSEEK_API_KEY | env 存在（不打印值） | 存在（bool） | PASS |

**前 owner 交接核对**：前 owner（`42379`/log `7boyfpwc`）在 maxround 140 `exit 143`，但已 commit `890b6e8` clean；
此后本地 gateA0 复验新增 `evidence/gateA-20261015T204337Z.json`。经比对：该文件与已 commit 的
`gateA-20261015T203739Z.json` **仅 `utc` 字段不同**（其余 JSON 全等，`real_provider_generation: 0`），
即**只多一份 gateA 复验 audit 证据**，非正式抽样、不影响任何正式行为文件/hash。**精确保全该新证据**，
不改动任何影响正式行为的文件/hash。

## 2. attempt 记录

> 每个 attempt 开始前记录：ID / UTC / ledger before / 冻结 hash；结束后记录：结果的脱敏摘要、
> ledger after、hash、实际 state，再决定下一次。

### Attempt 1 — `s1_units__A`  ✅ PASS (delivered)

- **开始 UTC**：`2026-10-15T20:45:38Z`
- **ledger before**：phaseRoot 不存在 ⇒ count `0`
- **冻结 hash**：driver `d1994948…`；truth `d39d906c…`；seed `53458ac7…`
- **结果**：rc 0，ok true，final_phase `awaiting_acceptance`；机器门 5/5；reviewer `passed`（teardown
  confirmed）；session refs 3；per-node candidate diff 2；evidence-present check_record `passed`；accept
  `200`/confirmed 绑定 candidate_ref+plan_hash+rev；幂等 `200`；错 target `409`；elapsed 130.81s。
- **ledger after**：count **21** / 192（21 行 JSONL，persistent）。真实转发 21（≤48）。
- **state**：sample_delivered=true，first_round_machine_pass=true；无人工介入/repair/recheck/失败/重试。
- **草稿**：`REPORT-DRAFT-s1_units__A.md`。

### Attempt 2 — `s1_units__B`  ✅ PASS (delivered)

- **开始 UTC**：`2026-10-15T20:48:09Z`
- **ledger before**：count `21`（同一物理 ledger）
- **冻结 hash**：driver `d1994948…`；truth `d39d906c…`；seed `53458ac7…`
- **结果**：rc 0，ok true，final_phase `awaiting_acceptance`；机器门 5/5；reviewer `passed`（teardown
  confirmed）；session refs **6**（B 多候选 claim）；per-node candidate diff 2；evidence-present
  check_record `passed`；accept `200`/confirmed 绑定 candidate_ref+plan_hash+rev；幂等 `200`；错 target
  `409`；elapsed 92.62s。
- **ledger after**：count **47** / 192（+26，累加不归零）。真实转发 26（≤48）。
- **state**：sample_delivered=true，first_round_machine_pass=true；无人工介入/repair/recheck/失败/重试。
- **唯一自变量**：协作开关开启；其余 A/B 全同。
- **草稿**：`REPORT-DRAFT-s1_units__B.md`。

### Attempt 3 — `s2_pipeline__A`  ✅ PASS (delivered)

- **开始 UTC**：`2026-10-15T20:49:54Z`
- **ledger before**：count `47`
- **冻结 hash**：driver `d1994948…`；truth s2 `06e2352f…`；seed `6fa0fd00…`
- **结果**：rc 0，ok true，final_phase `awaiting_acceptance`；机器门 **7/7**；reviewer `passed`
  （teardown confirmed）；session refs 6；per-node candidate diff 2；evidence-present check_record
  `passed`；accept `200`/confirmed 绑定 candidate_ref+plan_hash+rev；幂等 `200`；错 target `409`；
  elapsed 70.75s。
- **ledger after**：count **66** / 192（+19）。真实转发 19（≤48）。
- **state**：sample_delivered=true，first_round_machine_pass=true；无人工介入/repair/recheck/失败/重试。
- **草稿**：`REPORT-DRAFT-s2_pipeline__A.md`。

### Attempt 4 — `s2_pipeline__B`  ✅ PASS (delivered)

- **开始 UTC**：`2026-10-15T20:51:16Z`
- **ledger before**：count `66`
- **冻结 hash**：driver `d1994948…`；truth s2 `06e2352f…`；seed `6fa0fd00…`
- **结果**：rc 0，ok true，final_phase `awaiting_acceptance`；机器门 **7/7**；reviewer `passed`
  （teardown confirmed）；session refs 6；per-node candidate diff 2；evidence-present check_record
  `passed`；accept `200`/confirmed 绑定 candidate_ref+plan_hash+rev；幂等 `200`；错 target `409`；
  elapsed 66.47s。
- **ledger after**：count **87** / 192（+21）。真实转发 21（≤48）。
- **state**：sample_delivered=true，first_round_machine_pass=true；无人工介入/repair/recheck/失败/重试。
- **唯一自变量**：协作开关开启（驱动断言 `_autonomous_pool=True`）。
- **草稿**：`REPORT-DRAFT-s2_pipeline__B.md`。

## 3. 执行结果（终止）

- **4/4 固定 attempt 完成且 delivered**；无 STOP；真实转发合计 **87 / 192**（唯一物理 ledger 累加至 87）。
- 最终报告：`FORMAL-REPORT.md`；逐 attempt 草稿 `REPORT-DRAFT-*.md`。
- **冻结未变**、产品 tree `55e4de56` 未变、repo 除本包脱敏新增外 clean。
- **不 mark 032 done、不 merge main**；交 PM 依据独立完整门/真实评估收口。

## 4. 边界

- 不重跑、不补样、不调 prompt/tools/caps；normal failure 保留为有效失败。
- 任何 harness/装配/计量/ledger 身份/协议 hash/真实副作用不明错误 ⇒ 整个 cohort STOP，如实报告。
- 不 mark 032 done、不 merge main、不 push/deploy/publish；raw/SDKDB/隔离 worktree 持久 700/600，不入 repo。
