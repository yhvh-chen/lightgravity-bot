---
title: "LG-032 METHOD-FINAL attempt 草稿 — s2_pipeline__A"
doc_type: report-draft
category: engineering
status: "attempt 3 of 4: PASS (delivered); real provider count 19 (<=48); 032 NOT done"
experiment_id: lg032-fair-ablation-20261016
attempt_id: s2_pipeline__A
sample: s2_pipeline
arm: A
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner）"
---

# LG-032 METHOD-FINAL attempt 草稿 — `s2_pipeline__A`（#3/4）

## 身份

- 入口：`probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline --arm A`（real provider）。
- UTC 开始：`2026-10-15T20:49:54Z`；elapsed **70.75s**。
- 冻结 hash：driver `d1994948…`、truth s2 `06e2352f…`、seed `6fa0fd00…`。

## 结果（脱敏摘要）

| 项 | 值 |
|---|---|
| rc / ok | 0 / **true** |
| final_phase | `awaiting_acceptance` |
| 机器门 | **7/7** passed（shapes.rect.area、shapes.circle.area、shapes.rect.perimeter、shapes.bad.kind、report.rect、report.circle、no_write_from_verify） |
| 独立 reviewer | `review_completed` outcome=`passed`（validated=`passed`） |
| reviewer teardown | `confirmed=true` |
| session refs（真） | 6 |
| candidate diff | 2（per-node） |
| evidence-present check_record | `passed`（4 evidence refs） |
| accept | `200` confirmed，绑定 `candidate_ref=run_01M50N89DB58YR83KT908M8KXY`、`candidate_plan_hash=3519527fc0cbf9d7…`、`rev=1` |
| 幂等 | `200` confirmed |
| 错 target | `409` |
| seed_head == initial_head | `6fa0fd006ff058a7299f5e6dc42013fa051303de`（同 pin） |
| cleanup.status | `pending`（真适配器 stop 确认过门） |
| **真实转发请求** | **19**（≤48） |
| **物理 ledger after** | **count 66** / 192（+19） |
| **ledger before** | 47 |
| sample_delivered / first_round_machine_pass | true / true |

## 一致性 / 边界

- 14/14 steps PASS，无 `driver_error`；ledger 起始 47，累加同一物理 ledger。
- 无人工介入/repair/recheck/失败/重试。成本：真实转发 **19**；货币/token 无可核 usage 记 **unknown**。
- 未 mark 032 done；未 merge main。

## 下一步

- 按固定顺序继续 attempt 4 `s2_pipeline__B`（最后一个固定 attempt）。
