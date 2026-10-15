---
title: "LG-032 METHOD-FINAL 正式 4-attempt 采样报告（real provider）"
doc_type: report
category: engineering
status: "FORMAL-4-ATTEMPT COMPLETE (4/4 delivered); real provider requests 87/192; 032 NOT done; no merge"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final
branch: qa/lg032-method-final
head: "890b6e8c10b1ccf6cd75b7b87c6db444ebec70e0"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
phase_data_root: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data
updated: "2026-10-16"
owner: "agent:pi-lg032-formal-run（formal execution/report owner；新 pi context；非产品/harness 作者）"
---

# LG-032 METHOD-FINAL 正式 4-attempt 采样报告

> 本文 = 正式真实采样执行 owner（PM 授权后）的完整结果。**4/4 attempt 完成且 delivered**；真实 provider
> 转发 **87 ≤ 192**。**不 mark 032 done、不 merge main**，由 PM 依据独立完整门/真实评估收口。
> 旧报告/原件/成本全部保留；本包只新增 `probes/lg032/METHOD-FINAL/**`（脱敏）与 phaseRoot（原始）。

## 0. 结论（先给判断）

- **4 个固定 attempt 全部完成、全部 delivered**（`s1_units__A/B`、`s2_pipeline__A/B`），每 attempt 14/14
  机器步骤 PASS，无 STOP。
- **真实转发请求合计 87**（21+26+19+21），**未超 per-attempt 48 / total 192**；跨 4 attempt **同一物理 ledger**
  累加至 **87 / 192**（持久、不归零）。
- A/B **除协作开关外全部同质**（同 3 节点 plan、同 Member/objectives/权限 tools/输入/actual seed commit/
  机器 truth/caps/模型）；arm B 由驱动断言 `dispatcher._autonomous_pool=True` 真实生效。
- **不将 2 样本结果作为统计承诺**；质量/全成本**不足以**支撑默认启用 → **保留 `defaultoff` / 回退**。
- **LG-032 仍 in-progress**；不 mark done；不 merge main。

## 1. 授权与冻结身份（执行前核对，全 PASS）

- PM 授权：METHOD-FINAL 独立审计 PASS 候选 + 正式 2×A/B×1 采样。
- 授权 head `890b6e8`（branch `qa/lg032-method-final`）；产品 tree `55e4de56`（== main == `0814b80`）。
- 冻结协议：`FORMAL-FREEZE.md` + `REPORT-FINAL.md` + `method-final-freeze-candidate.manifest.json`
  （contract `1.11.0`、SDK `0.1.22`、`deepseek-v4-flash` @ `https://api.deepseek.com/v1`）。
- 执行前核对：driver `d1994948…`、fake_upstream `de9d7a35…`、final_cohort_config `a04a8f30…`、
  hard_gate `0067af1c…`、run_dry `f792da28…`、truth s1 `d39d906c…`/s2 `06e2352f…`、
  seed s1 `53458ac7…`/s2 `6fa0fd00…` — **全部与冻结 manifest 一致**。
- phaseRoot `lg032-method-final-data` 执行前**不存在**；4 attempt 无既有正式输出；无自有冻结进程残留；
  SDK `0.1.22` venv 已核。
- 前 owner（`42379`/log `7boyfpwc`）在 maxround 140 `exit 143` 但已 commit 890b6e8 clean；此后新增本地 gateA0
  复验 `evidence/gateA-20261015T204337Z.json`，与已 commit `gateA-20261015T203739Z.json` **仅 `utc` 不同**，
  仅多一份 **audit 复验证据**（`real_provider_generation: 0`），**已精确保全，未改任何正式行为文件/hash**。

## 2. 执行方式

固定顺序、各唯一一次、逐条经既有正式入口：

```bash
.venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units     --arm A
.venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units     --arm B
.venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline  --arm A
.venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline  --arm B
```

真实 `DEEPSEEK_API_KEY` 仅从受控 env 读取（**未打印/未写入提示词/仓库/日志**）；`run_formal.py` 先装 overlay
把唯一 `settings.data_dir` 指向 phaseRoot，再走字节同 cohort-ready 的冻结驱动 `run_attempt.py`（`dry_run=False`）。
单尝试受控 `timeout 400s`；实测最长 130.81s。

## 3. 逐 attempt 结果（脱敏）

| # | attempt | arm | rc/ok | final phase | 机器门 | reviewer | sessions | cand diff | accept | 幂等 | 错 target | seed_head | **requests** | elapsed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `s1_units__A` | A | 0/true | awaiting_acceptance | **5/5** | passed | 3 | 2 | 200 confirmed | 200 | 409 | `53458ac7…` | **21** | 130.81s |
| 2 | `s1_units__B` | B | 0/true | awaiting_acceptance | **5/5** | passed | 6 | 2 | 200 confirmed | 200 | 409 | `53458ac7…` | **26** | 92.62s |
| 3 | `s2_pipeline__A` | A | 0/true | awaiting_acceptance | **7/7** | passed | 6 | 2 | 200 confirmed | 200 | 409 | `6fa0fd00…` | **19** | 70.75s |
| 4 | `s2_pipeline__B` | B | 0/true | awaiting_acceptance | **7/7** | passed | 6 | 2 | 200 confirmed | 200 | 409 | `6fa0fd00…` | **21** | 66.47s |

- 每 attempt：`sample_delivered=true`、`first_round_machine_pass=true`、`driver_error=null`、14/14 steps PASS。
- 机器门绑定真实 `check_records`（`{check_id: evidence-present, status: passed}`，4 evidence refs）。
- 每 attempt reviewer 真 teardown `confirmed=true`（agent_closed/proxy_stopped true）；`cleanup.status=pending`
  但由真适配器 `confirm_stopped` 授权过门（**非手写 done**）。
- 每 attempt accept 绑定 `candidate_ref` + `candidate_plan_hash` + `requirements_revision=1`；同 request_id
  幂等 `200`；错 target `409`。
- 每 attempt `seed_head == initial_head`（与 pin 一致 ⇒ A/B 从同一 actual commit 出发）。
- per-node candidate diff 2 条（`subtask_*-lg006-diff.patch` + sha256），非 run 级碰撞路径。

### 真实转发与 ledger 累加（唯一物理 ledger）

| attempt | ledger before | ledger after | 本 attempt 请求 |
|---|---|---|---|
| `s1_units__A` | 0（phaseRoot 新建） | 21 | 21 |
| `s1_units__B` | 21 | 47 | 26 |
| `s2_pipeline__A` | 47 | 66 | 19 |
| `s2_pipeline__B` | 66 | **87** | 21 |

物理 ledger：`<phaseRoot>/generation/generation.jsonl` = **87 行**；`generation.count.json` = `{"count":87}`；
`limit 192`、`corrupt=false`、`persistent=true`。**跨 4 attempt 累加，未重置**。

## 4. 各角色 model calls / SDK session / stop / checkrecords

- **角色模型调用**（协议冻结）：每 attempt 独立 reviewer `model_calls=1`（`review_completed`）。worker/selector/
  verifier 调用计入同一 48 与同一物理 ledger（见 §3 请求数）；`reviewer_model_calls=1` 不超。
- **SDK session**：每 attempt 真 session refs 记录（A=3、B=6、s2_A=6、s2_B=6），全部 teardown（reviewer
  confirmed；worker 会话随 run 结束真实停止）。
- **check_records**：每 attempt `evidence-present=passed`（4 evidence refs）绑定于 accept。
- **执行/QA 阶段**：无业务 repair（0）、无 recheck、无 failure、无上游 retry（SDK retry 0）。所有失败/重试
  累计计数 = 0（本 cohort 未发生）。
- **人工介入**：0（human accept 为协议规定的真实验收动作，非故障介入）。

## 5. 成本（准确、不洗 0、不把失败中位数推收益）

- **本 cohort 真实转发请求 = 87**（唯一物理 phase ledger 计数）。
- **货币/token 成本**：运行期无可核 usage 明细 ⇒ 记 **unknown**（**不当 0**）。
- **开发 pi 控制器 usage/time**：如 dispatch usage 可得则单列 **estimated/shared/unallocated**；否则 **unknown**。
- **旧工程成本单列不清零**：旧 LG-031 工程 **86**；旧 023 cohort1 **45** / cohort2 **4** / cohort3 **16**；
  023 eval **65**；core **unknown**；所有预检 QA 失败与修复保留为平台开销；pi 开发 QA / shared = **unknown**。
- **不把 request/time 代理当作完整成本节省**；2 样本不做统计承诺。

## 6. 质量判断与产品结论

- 4/4 attempt `sample_delivered=true`（机器门 + 独立 reviewer + 真 stop + accept 绑定全过）。
- **但 2 样本不足以下统计承诺**；质量与全成本**不支持默认启用**协作开关 ⇒ 建议**保留 `defaultoff` / 回退**。
- 若后续独立完整门/真实评估发现产品质量重要缺陷（尤其 arm B 多候选路径），**必须返修验收**，不 source fake fix。

## 7. 冻结未变 / 原件路径 / 边界

- **冻结未变**：`run_attempt.py` `d1994948…`、`fake_upstream.py` `de9d7a35…`、`final_cohort_config.py`
  `a04a8f30…`、`hard_gate.py` `0067af1c…`、`run_dry.py` `f792da28…`、truth s1/s2 上文 hash、产品 tree
  `55e4de56` — 执行后**逐字节不变**（已复核）。
- **原件路径（持久，不入 repo）**：
  - phaseRoot：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data`
    （`generation/`、`tasks/`、`events/`、`subtasks/`、`artifacts/`、`native-sessions/`、`attempts/<id>/{workspaces,secrets}`）。
  - 逐 attempt 结果（gitignore runs/，仅本地）：`probes/lg032/METHOD-FINAL/runs/<attempt-id>/result.json`。
  - 脱敏 evidence（入 repo）：`probes/lg032/METHOD-FINAL/evidence/<attempt-id>.json`。
  - raw SDKDB / 隔离 worktree / secrets：phaseRoot 下（受控权限，**不删**，不入 repo/提示词）。
- **边界**：未 `rm`/`rmtree`（仅驱动对自身 attempt 内的 candidate-ws 重建，属协议内）、未 reset/clean/TMD/
  覆盖；0 push/deploy/publish；未改源 switch 默认（仍 off）；未嵌套代理；未碰 `8123`；未 mark 032 done；
  未 main merge。
- **限制明确交接**：本包仅完成正式 4-attempt 采样与报告；done/mainmerge 由 PM 依据独立完整门与真实评估收口。

## 8. 修订历史

- 2026-10-16：PM 授权后执行 4 个固定 attempt（各一次，real provider），4/4 delivered，real 87/192；
  写本报告与逐 attempt 草稿（`REPORT-DRAFT-*.md`）、`FORMAL-STATUS.md`；不 mark done、不 merge。
