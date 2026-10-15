---
title: "LG-032 METHOD-FINAL attempt 草稿 — s1_units__B"
doc_type: report-draft
category: engineering
status: "attempt 2 of 4: PASS (delivered); real provider count 26 (<=48); 032 NOT done"
experiment_id: lg032-fair-ablation-20261016
attempt_id: s1_units__B
sample: s1_units
arm: B
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner）"
---

# LG-032 METHOD-FINAL attempt 草稿 — `s1_units__B`（#2/4）

## 身份

- 入口：`probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units --arm B`（real provider）。
- UTC 开始：`2026-10-15T20:48:09Z`；elapsed **92.62s**。
- 冻结 hash：driver `d1994948…`、truth s1 `d39d906c…`、seed `53458ac7…`。
- 唯一自变量：协作开关（`decentralized_claim_enabled`/`autonomous_pool`）本 attempt 内开启；
  同 3 节点 plan / 同 Member / 同 objectives / 同权限工具 / 同输入 / 同 seed / 同机器 truth / 同 caps / 同模型。

## 结果（脱敏摘要）

| 项 | 值 |
|---|---|
| rc / ok | 0 / **true** |
| final_phase | `awaiting_acceptance` |
| 机器门 | **5/5** passed |
| 独立 reviewer | `review_completed` outcome=`passed`（validated=`passed`） |
| reviewer teardown | `confirmed=true` |
| session refs（真） | **6**（B 多候选 claim → 更多 worker 会话） |
| candidate diff | 2（per-node `subtask_*-lg006-diff.patch`） |
| evidence-present check_record | `passed`（4 evidence refs） |
| accept | `200` confirmed，绑定 `candidate_ref=run_01M50N521SK0N6679WX6QE061P`、`candidate_plan_hash=4301bd0384e9fb23…`、`rev=1` |
| 幂等 | `200` confirmed |
| 错 target | `409` |
| seed_head == initial_head | `53458ac742b5aa4fd6913000aeeb69ae94cc80c1` |
| cleanup.status | `pending`（真适配器 stop 确认过门） |
| **真实转发请求** | **26**（≤48） |
| **物理 ledger after** | **count 47** / 192（+26，累加不归零） |
| **ledger before** | 21 |
| sample_delivered / first_round_machine_pass | true / true |

## 一致性 / 边界

- 14/14 steps PASS，无 `driver_error`。
- `ledger_persistent_single_path` 起始 count 21 且 `physical_history_exists_at_freeze=true` ⇒ **跨 attempt
  同一物理 ledger 累加**，未重置。
- 无人工介入/业务 repair/recheck/失败/上游重试。
- 成本：真实转发 **26**；货币/token 无可核 usage 记 **unknown**（不当 0）。
- 未 mark 032 done；未 merge main。

## 下一步

- 按固定顺序继续 attempt 3 `s2_pipeline__A`。
