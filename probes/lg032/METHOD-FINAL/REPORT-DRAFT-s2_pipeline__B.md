---
title: "LG-032 METHOD-FINAL attempt 草稿 — s2_pipeline__B"
doc_type: report-draft
category: engineering
status: "attempt 4 of 4: PASS (delivered); real provider count 21 (<=48); 032 NOT done"
experiment_id: lg032-fair-ablation-20261016
attempt_id: s2_pipeline__B
sample: s2_pipeline
arm: B
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner）"
---

# LG-032 METHOD-FINAL attempt 草稿 — `s2_pipeline__B`（#4/4）

## 身份

- 入口：`probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline --arm B`（real provider）。
- UTC 开始：`2026-10-15T20:51:16Z`；elapsed **66.47s**。
- 冻结 hash：driver `d1994948…`、truth s2 `06e2352f…`、seed `6fa0fd00…`。
- 唯一自变量：协作开关（本 attempt 内开启）；其余同 A。

## 结果（脱敏摘要）

| 项 | 值 |
|---|---|
| rc / ok | 0 / **true** |
| final_phase | `awaiting_acceptance` |
| 机器门 | **7/7** passed |
| 独立 reviewer | `review_completed` outcome=`passed`（validated=`passed`） |
| reviewer teardown | `confirmed=true` |
| session refs（真） | 6 |
| candidate diff | 2（per-node） |
| evidence-present check_record | `passed`（4 evidence refs） |
| accept | `200` confirmed，绑定 `candidate_ref=run_01M50NAS93313FB267Z0WRN0PW`、`candidate_plan_hash=025cc5d81e0bb7c9…`、`rev=1` |
| 幂等 | `200` confirmed |
| 错 target | `409` |
| seed_head == initial_head | `6fa0fd006ff058a7299f5e6dc42013fa051303de` |
| cleanup.status | `pending`（真适配器 stop 确认过门） |
| **真实转发请求** | **21**（≤48） |
| **物理 ledger after** | **count 87** / 192（+21） |
| **ledger before** | 66 |
| sample_delivered / first_round_machine_pass | true / true |

## 一致性 / 边界

- 14/14 steps PASS，无 `driver_error`；driver 在 arm B 断言 `dispatcher._autonomous_pool=True`（否则 SystemExit），
  exit 0 即证明协作开关真实生效。raw run events 含 `subtask.lease_granted/revoked`（3 对，3 节点计划）。
- 无人工介入/repair/recheck/失败/重试。成本：真实转发 **21**；货币/token 无可核 usage 记 **unknown**。
- 未 mark 032 done；未 merge main。

## 下一步

- 4 个固定 attempt 全部完成（real 87 ≤ 192）。进入收口：写 `FORMAL-REPORT.md`。
