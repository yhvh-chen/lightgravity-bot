---
title: "LG-032 独立只读封账审计（CLOSE-AUDIT）— 报告 v1"
doc_type: audit
category: engineering
status: "ROUND-<45 DRAFT; independent read-only; real provider 0; 032 NOT touched; PM to decide done"
experiment_id: lg032-close-audit-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-close-audit
branch: qa/lg032-close-audit
base_commit: "271fefb448a77fcd0f419acba7d26e024d3aa658"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-close-audit（独立封账审计 owner；非产品/driver/entry/正式执行者；只读）"
---

# LG-032 独立只读封账审计（报告 v1）

> 独立新 pi context。**真实 provider 0**（未运行任何 SDK/测试/POST/runner，未 build runtime/Task/proxy）。
> 不嵌套、不 main merge / push / deploy / publish。产品/所有旧报告/driver **只读**；本 owner 仅新增
> `probes/lg032/CLOSE-AUDIT/**`。私有原件只解析必要键，**不打印正文/headers/credential/raw model content**。
> 032 任务状态**未写**；交 PM 判断 done。旧原件/worktree/字节全部保留，未 rm/rmtree/reset/clean/覆盖。

## 0. 结论（v1，先给判断）

- 任务 032 声称的 cohort3 事实经**实际 raw 结果 / SoT / 物理 JSONL / 源码 hash 只读核对**，**全部复现一致**；
  v1 未发现证据绑定 / 模式 / 计量的重要缺陷。**建议 032 评估范围可判 done**（终判在报告 v2/封账；本 v1 为早期稿）。
- 结论**不等于全产品 pass**；覆盖范围为下述 4 个 tiny code case 与机制/成本门，明确列出 unknown 与不能覆盖项。

## 1. 身份与不可变性（只读实测）

| 项 | 期望（冻结/报告） | 实测 | 判定 |
|---|---|---|---|
| worktree/branch | lg032-close-audit / qa/lg032-close-audit | 同 | ✅ |
| HEAD | 271fefb（fix/lg032-cohort3-entry） | 271fefb448a77fcd0f419acba7d26e024d3aa658 | ✅ |
| tracked diff | clean | 空 | ✅ |
| 产品 tree `HEAD:backend/lightgravity` | 55e4de56… | 55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f（== base == main） | ✅ |
| entry `run_formal.py` sha256 | e8340f90…90e2 | 同 | ✅ |
| overlay `mode_config.py` sha256 | df565291…88bf | 同 | ✅ |
| driver `run_attempt.py` sha256 | 503a807f…6208 | 同 | ✅ |
| driver `final_cohort_config.py` sha256 | a04a8f30…a117 | 同 | ✅ |
| 旧 cohort2 entry sha | a7477753…（须不变） | a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040 | ✅ |

- **COHORT3 分支对产品/driver/entry/overlay 零字节改动**：`git diff --stat b634238 271fefb` 仅新增
  `COHORT3-FORMAL-REPORT.md`(+215) 与 `ENTRY-INDEPENDENT-AUDIT-R1.md`(+165)，合计 2 files。
- overlay `mode_config.py` 仅重定向路径常量（WORKTREE/PHASE_DATA_DIR/LEDGER/RUNS/EVIDENCE/FIXTURES），
  grep 确认**无** model/budget/prompt/tool/truth/seed/cap/plan/profile/provider 语义字段。

## 2. 物理 ledger 与计量（只读，单一路径）

- cohort3 物理 ledger `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data/generation/`：
  `generation.count.json` = `{"count":84}` sha256 `fef0bd52e61e58a2f6200194bf7af5219a5d8c1f9ffd2dcbd7335fb81d92e68f`；
  `generation.jsonl` 84 行 sha256 `a266e2fd8fa80cbc828746b14d5b7aaaf0923d90c97331b42665295971aa3f72`。
  **与报告 §7.2 逐字一致。**
- 逐 attempt `generation_final.count` = 20 → 40 → 57 → 84（`persistent=true`、`corrupt=false`、`limit=192`）；
  单 attempt requests = 20/20/17/27，合计 **84 ≤ 192**，无 attempt 超 48。`phase_data_dir` 四齐同指 cohort3-data。
- **usage `{"unknown":["usage"]}`** 四齐 ⇒ SDK 不回报 token，**真实 token/实际费用 = unknown（不记 0）**。
- 旧账本**未洗、未混、未归零**：
  - cohort1 method-final `{"count":87}` sha `609946be…a01e68`；jsonl 87 行 sha `beba08e0…871abd`。
  - cohort2 `{"count":19}` sha `be90a0f9…658585`；jsonl 19 行 sha `15a4bb00…595fbb`。
- **成本口径（分列）**：旧 032 协议失败 106 = cohort1 87（mode-invalid）+ cohort2 19（entry assembly STOP）+
  有效 84 ⇒ **032 本轮真实合计 190**；cohort3 上限 192 / attempt 48 / 已知上限 298 **未超**。
  A 合 37（20+17）/ B 合 47（20+27），**请求数差 ≠ 完整 token 花费**。
- 开发 pi / shared pi cost：引用 `LG032-SHARED-PI-COST-AUDIT.md`（snapshot `2026-10-15T21:24:34Z`，metadata 只读解析、
  **工具自报估计非账单**）：LG032 confident 26 logs / 1574 unique calls / noncache_in 1,678,454 / out 517,978 /
  cacheRead 124,136,832 / costEst 9.728773；shared 51 UNASSIGNED logs 另列；使用文件缺失 42 记 unknown。

## 3. 逐 attempt 实际交付（非只信报告）

物理 `lg032-cohort3-formal/runs/<id>/result.json` 与 `evidence/<id>.json` **逐字节相同**，sha 与报告 §7.1 一致：

| attempt | result.json sha256 | delivered | machine | gen | elapsed(s) | repair |
|---|---|---|---|---|---|---|
| s1_units__A | b54d3c01…a4d00 | ✅ | 5/5 | 20 | 105.38 | 0 |
| s1_units__B | 09c237d9…bc309 | ✅ | 5/5 | 20 | 59.21 | 0 |
| s2_pipeline__A | 0bf3c823…e6f7f6 | ✅ | 7/7 | 17 | 96.83 | 0 |
| s2_pipeline__B | fe0bf73e…97620d | ✅ | 7/7 | 27 | 115.49 | 0 |

- 四齐 `final_phase=awaiting_acceptance`、`phases_seen=['awaiting_acceptance','executing','verifying']`、
  14 个 `steps` 全 `ok=true`；`initial_head == seed_head`（s1 `53458ac7…`，s2 `6fa0fd00…`）。
- elapsed 逐样本取自 raw `elapsed_seconds`（非失败 median 推断）。
- 私有副本 `lg032-cohort3-private-logs-.../attemptN_*.result.json` sha 与 formal 输出**同值**；rc=0、stderr 空。

## 4. mode-isolation（独立复现）

- `mode_snapshot_after_bootstrap`：A（第 1/3）`expected_enabled=false`、dispatcher
  `_autonomous_claim/_autonomous_pool/_decentralized_enabled()` 全 false、`congruent=true`；
  B（第 2/4）全 true、`congruent=true`。
- **run events jsonl 实测**：A 运行 `subtask.lease_granted=0`；B 运行 `lease_granted=3`/`lease_revoked=3`
  （B 用 `claim_*` request_id 走候选池 claim/lease；第 1 个 alpha 用 `req-alpha-01`）。
  ⇒ **A3 refs 无 selector、B6 有 selector/lease3**（selector 语义即 claim/lease；data 内无字面 "selector" 字符串）。
- **特别确认第 3 个 attempt `s2_pipeline__A` 紧接 `s1_units__B`(on) 之后仍实测 off**：session_refs=3、
  lease_granted=0、mode 全 false（独立复现 SERIAL-R1「旧 cohort1 s2A=6 refs B-like 污染已修」）。
- `mode_restore.restored_off=true` 四齐；最终 `SETTINGS.md` 持久 `decentralized_claim_enabled=false`。

## 5. 授权 / 审查 / 停止（独立复现）

- `accept_response.acceptance`：四齐含 `candidate_plan_hash`（4 个唯一值）、`check_records=[{check_id:"evidence-present",
  status:"passed",detail:"4 evidence ref(s) recorded"}]`、`requirements_revision=1`、`deliverable_revision=1`。
- `accept_idempotent_response` = 同 request 二次 accept `state=confirmed`（幂等）；
  `accept_wrong_target_response` = 409 `illegal_transition`（target_run_id mismatch）→ **same candidate plan
  requirements 绑定 + 幂等 + wrong target 拒 均实测成立**。
- 独立 review：`reviewer_kind=model`、`outcome=passed`、`unsubstantiated=0`、`model_calls=1`、`usage unknown`
  四齐；`reviewer_wired_model` step 记 `connection_id=deepseek-v4-flash`、`credential_configured=true`。
- `reviewer_cleanup` = `status=done, agent_closed=true, proxy_stopped=true, confirmed=true` 四齐。
- 资源停止：`member.state_changed ready→released`（reason "run scheduling finished"）+ `member.released`；
  `cleanup.updated` reviewer `agent_closed/proxy_stopped/confirmed`。
- 真实 SDK worker：native-sessions `*.db` **18 个（600）**，分布 3/6/3/6 = A/B；`session_refs` 3/6/3/6。
  候选 diff 落盘于 `artifacts/run_*/lg006-diff.patch`（真 SDK 产物）。

## 6. 覆盖范围与限制（不宣全产品 pass）

- 本审计可引用只读范围：核心 022/R1、032 stageA→返修 R1、BOUNDARY-R1、SERIAL-R1 独立源质量证据；**0 本包不重跑全套**。
- **不能被这 4 个 tiny code case 覆盖**：full checkpoint skip / 自动 resume（未实现）、OS security sandbox
  （非 Git worktree）、资料 OCR/embedding 真实质量、中文 ASR 门；未来外部 quality block 不造循环。
- 结论只指 032「固定条件比较、独立机制 QA、发现缺陷返修复验、默认 off 负结果记录」本身，不是全产品 pass。

## 7. 待完成（v2/封账前）

- 必要时最小补核：SERIAL-R1 与老两 cohort STOP/invalid 补遗（已据只读摘要，不再长 log / 全库重复调查）。
- 输出封账 **PASS/FAIL** + 证据路径 + unknown；精确 commit 仅新增脱敏 QA 报告 + 小 metadata。
- 交 PM：是否 032 done（本包不自判 done、不写任务状态）。

## 8. 修订历史

- 2026-10-16（round ~12，真实 provider 0）：身份/ledger/mode/review/accept/stop 独立只读核对全部一致；
  写报告 v1；cot 未发现重要缺陷。
