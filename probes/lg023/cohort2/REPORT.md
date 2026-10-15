---
title: "LG-023 cohort-2 对照评估 REPORT"
doc_type: report
category: engineering
experiment_id: lg023-cohort2-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2
branch: eval/lg023-cohort2
base_commit: "834b262"
product_base_commit: e0a8cec
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
protocol_hash: "8a2375f4357f73fb2faebe4a9e417fa617598e6bd4b0c3e510906f2174701450"
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort2"
---

# LG-023 cohort-2 对照评估 REPORT

> **状态：STOPPED（partial）。** 本 cohort 在**正式 attempt 1 之后**发现 harness 计量缺陷
> （单一 phase ledger 未生效），按停止规则**立即停止整个 cohort**，保留 partial，**未修复重跑**。

## 0. 结论一句话

**本 cohort 不满足「冻结协议完整执行」，因此不宣称 LG-023 done、不宣整产品 pass、不作组队收益结论。**
可核实的一件事：**在修好的独立 driver 下，单个真实 SDK worker 完成了一个小型两文件交付**，机器门 6/6、
独立 `ModelReviewer` `passed`、**真实停止门闭合**（`awaiting_acceptance`）、并**绑定了 accept**（含 plan hash）——
这修正了 cohort 1 因 `_accept` 未接 `session_confirmer` 造成的「停止门未闭合」记录（方法审计 A7）。
**但**本次采样的持久 ledger 落在**每次 attempt 各自的数据目录**，未满足冻结的「全 stage 同一持久 phase ledger」，
属 **harness 计量缺陷**（D1），故按规则**停止**，剩余 3 attempts **未运行**。

## 1. 执行与停止事实

- 起始：main 基点 `834b262`；产品树锚定已通过的 `e0a8cec`（契约 `1.10.0`）；SDK 0.1.22；模型 `deepseek-v4-flash`。
- **离线硬门全部先过**（真实 DeepSeek 生成 0）：P1 fixtures（初始必败/reference 必过 6/6）、P2 冻结合法 plan 过
  真实 `PlanValidator`、P3 worker agent 过真实 `ResourceCompiler`、P4 真 `LocalAuthProxy`+本地 fake upstream
  （每 attempt 12 转发前强制、13th→429、worker/reviewer 同账本、count 非 0）、P5 真 `GraphDispatcher`+
  真 `StoreResourceStopper`（teardown 齐→`awaiting_acceptance`；缺→`unconfirmed`）、P6 真装配 dry-run（本地
  fake upstream，两 arm 跑通）。证据：`evidence/offline/{offline_proof,dry_run_proof,protocol_manifest}.json`。
- **正式 attempt 1（`s1_independent__A`）**：完整跑通（见 §2）。
- **发现 D1 后立即停止**：整 cohort 停止；`s1_independent__B`、`s2_interface__A`、`s2_interface__B` **未运行**。

## 2. attempt 1（`s1_independent__A`）结果——真实交付，但计量口径不符冻结协议

| 项 | 值 |
|---|---|
| 样本 / arm | S1 independent / A（1 个计划写节点） |
| 初始内容树 hash | `795cf3a8…`（fixture `initial/` 逐字节） |
| 阶段轨迹 | `executing → verifying → awaiting_acceptance` |
| 机器门 | **6/6 passed** |
| 独立 reviewer | 真 `ModelReviewer` **`passed`**（`findings=0`，`model_calls=1`） |
| 停止门 | `reviewer_cleanup.confirmed=true`（`agent_closed=true`、`proxy_stopped=true`）；run `cleanup.status=pending`（**未伪造 `done`**） |
| 真实 session refs | 1（`sess_e4b42f…`） |
| 版本验收门 | **accept 绑定成功**：`status=accepted`、`requirements_revision=1`、`deliverable_revision=1`、`candidate_ref=run_01M50BGADVY8745WG1K1YV3587`、`candidate_plan_hash=b95054c5…`（= 冻结合法 plan hash） |
| 真实生成请求 | **4**（worker 3 + reviewer 1） |
| elapsed | 12.08s |
| 首轮机器门 | 通过（单节点一次实施即 6/6） |

- `sample_delivered = true`（机器门 + reviewer passed + accept 绑定）。
- 证据原件（保留、不覆盖）：`runs/s1_independent__A/{result.json,candidate.diff,git.txt,.formal_attempt_started}`、
  attempt ledger `lg023-cohort2-data/attempts/s1_independent__A/data/generation/generation.jsonl`（4 行）。

## 3. 缺陷 D1（harness，非产品）——trigger 了停止

- **冻结要求**：全 stage（worker/reviewer/返修/复验/失败）**同一持久 phase ledger**，转发前硬限。
- **实际**：ledger 落在 `lg023-cohort2-data/attempts/s1_independent__A/data/generation/`，
  而**不是** `lg023-cohort2-data/generation/`。即每次 attempt 各自一个 ledger。
- **根因**：`backend/lightgravity/api/bootstrap.py:build_runtime` 无条件调用
  `configure_generation_ledger(settings.data_dir)`，**覆盖**了 driver 设置的
  `LIGHTGRAVITY_GENERATION_LEDGER_DIR`，使 phase 级 ledger 未生效。
- **影响**：总 48 上限在单 attempt 层面仍硬（每 attempt 上限生效），但**跨 attempt 的 phase 总账未统一**，
  故计量口径不满足冻结协议。
- **最小 repro**：`LIGHTGRAVITY_GENERATION_LEDGER_DIR=<phase> build_runtime(...)` 后
  `global_generation_counter().snapshot()` 的 ledger 根为 `settings.data_dir`，非 `<phase>`。
- **处置**：**停止整个 cohort**，保留 partial；**不**修复重跑同一 attempt；**不**用剩余预算重复 attempt。
  下一 phase 需在 `build_runtime` **之后**把 counter 重新 pin 到 phase 根（或让 driver 用 phase 根作
  `settings.data_dir` 并在 attempt 下放 workspace），并重新离线证实后再采样。
- 证据：`evidence/cohort2-D1.json`（含哈希与最小 repro）。

## 4. 计数与成本（准确，未知不当 0）

| 阶段 | 真实生成 | 说明 |
|---|---|---|
| 本 cohort-2 | **4/48** | 仅 attempt 1；离线与 dry-run 用本地 fake upstream，**0 次 DeepSeek** |
| 旧 LG-023 cohort | **45/48** | protocol-deviation 失败成本，**单列、不清零、不并入** |
| 旧 LG-022 | unknown+6+8+5/10 | 单列 |
| 旧 LG-031 | 34/40 | 单列 |

- 已知 eval 真实生成**实际上限 45+48=93**；本 cohort 实际 4。
- **usage/费用**：provider 未回传可核总费用 ⇒ 记 `unknown`，**不当 0**；**不据失败样本中位数推收益**。
- **人工干预**：修 driver（ledger 接线、路径、review 事件解析、workspace 隔离开关）属开发侧成本，
  **单列/shared**，不当 runtime 收益。

## 5. 局限（明确）

- **样本小（仅 attempt 1）、单模型、强制冻结合法 plan**：不声称统计显著性；不推广到所有任务类型。
- **未取得 4 attempts 齐的同条件数据**：不能就组队 vs 单 worker 的完成率/成本作任何结论。
- **本 cohort 不满足冻结协议完整执行**（D1 计量），**LG-023 不能标记 done**。
- **workspace 隔离两 arm 一致关闭**（见 PLAN §3）：为保持唯一自变量=计划写节点数，是明确冻结的实验设置，
  不代表产品隔离能力。
- 未覆盖浏览器/恢复/取消/长会话/真实工程规模。
- **未宣整产品 pass**；最终 done 由主代理按授权决定。

## 6. 产物与证据索引

- PLAN / STATUS / REPORT：`probes/lg023/cohort2/{PLAN,STATUS,REPORT}.md`。
- Driver：`harness/run_attempt.py`；配置 `harness/cohort2_config.py`；离线 `harness/{offline_proof,dry_run_proof,fake_sse_upstream}.py`。
- 离线证据：`evidence/offline/{offline_proof,dry_run_proof,protocol_manifest}.json`；protocol hash `8a2375f4…`。
- 缺陷证据：`evidence/cohort2-D1.json`。
- Attempt 1 原件：`runs/s1_independent__A/**`；持久 runtime `lg023-cohort2-data/attempts/s1_independent__A/**`。
- 旧 cohort 原件（`probes/lg023/**`、`dev/lg023`、`fix/lg023-method`）**保留、未改**。

**不推送 / 不部署 / 不发布。LG-023 保持 `in-progress`。**
