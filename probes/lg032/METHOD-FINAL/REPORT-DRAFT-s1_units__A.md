---
title: "LG-032 METHOD-FINAL attempt 草稿 — s1_units__A"
doc_type: report-draft
category: engineering
status: "attempt 1 of 4: PASS (delivered); real provider count 21 (<=48); 032 NOT done"
experiment_id: lg032-fair-ablation-20261016
attempt_id: s1_units__A
sample: s1_units
arm: A
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner）"
---

# LG-032 METHOD-FINAL attempt 草稿 — `s1_units__A`（#1/4）

## 身份

- 入口：`probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units --arm A`（real provider）。
- UTC 开始：`2026-10-15T20:45:38Z`（UTC）；elapsed **130.81s**。
- 冻结 hash：driver `d1994948…`、truth s1 `d39d906c…`、seed `53458ac7…`（与执行前核对一致）。
- phaseRoot：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data` 于本次**首次创建**
  （执行前不存在）；唯一 `settings.data_dir`。

## 结果（脱敏摘要）

| 项 | 值 |
|---|---|
| rc / ok | 0 / **true** |
| final_phase | `awaiting_acceptance`（phases_seen：executing→verifying→awaiting_acceptance） |
| 机器门 | **5/5** passed（labels.slugify.basic/runs、numeric.clamp、numeric.in_range、no_write_from_verify） |
| 独立 reviewer | `review_completed` outcome=`passed`（model_calls 1，findings 1，真实独立角色） |
| reviewer teardown | `confirmed=true`，agent_closed=true，proxy_stopped=true |
| session refs（真） | 3（`sess_c4eb46a…`、`sess_c845850…`、`sess_6699f5e…`） |
| candidate diff | 2（per-node `subtask_*-lg006-diff.patch`，带 sha256 绑定） |
| evidence-present check_record | `passed`（4 evidence refs） |
| accept | `200` state=`confirmed`，绑定 `candidate_ref=run_01M50N0FCNNGS0BB0TFPTKZCYJ`、`candidate_plan_hash=f73476375c33091d…`、`requirements_revision=1` |
| 幂等（同 request_id） | `200` confirmed |
| 错 target | `409`（illegal_transition：target_run_id 不匹配 active Run） |
| seed_head == initial_head | `53458ac742b5aa4fd6913000aeeb69ae94cc80c1`（同 pin） |
| cleanup.status | `pending`（但由真适配器 stop 确认过门；非手写 done） |
| **真实转发请求** | **21**（`attempt_generation_requests`，≤48） |
| **物理 ledger after** | **count 21** / 192（JSONL 21 行，persistent，corrupt=false） |
| **ledger before** | 0（phaseRoot 执行前不存在） |
| sample_delivered / first_round_machine_pass | true / true |

## 一致性 / 边界

- 14/14 driver steps PASS；无 `driver_error`。
- `global_ledger` 字段为 server 关闭后的 HTTP 探针 `Connection refused`（非执行期错误）；持久计数以
  `generation_final.count=21` 与物理 JSONL 为准。
- `candidate_patch_applied=false`（机器 truth 对 per-node diff 施加语义，非 run 级碰撞路径）；
  `candidate_diff_count=2` 与 evidence refs 一致。
- 无人工介入；无业务 repair；无 recheck；无失败；无上游重试。
- 仓库仅新增脱敏 `runs/s1_units__A/result.json`（gitignore runs/）与 `evidence/s1_units__A.json`；
  raw SDKDB/隔离 worktree 在 phaseRoot（mode 775/受控），不入 repo。
- **成本**：本 attempt 真实转发 = **21 请求**（< 48）。货币/token 若无可核 usage 记 **unknown**（不当 0）。
- **未做**：不做统计承诺；未 mark 032 done；未 merge main。

## 下一步

- 按固定顺序继续 attempt 2 `s1_units__B`（唯一自变量=协作开关）。本 attempt 失败与否均保留。
