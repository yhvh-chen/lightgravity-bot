---
title: "LG-032 FORMAL-FREEZE（独立方法审计通过后的正式采样冻结候选）"
doc_type: freeze
category: engineering
status: "RECOMMEND-READY-for-formal-4-attempt; formal NOT run; 032 still in-progress; real provider 0"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final
branch: qa/lg032-method-final
base_commit: "a4b4455"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-method-final（独立方法审计 owner）"
---

# LG-032 FORMAL-FREEZE（方法审计通过）

> **本文件是独立方法审计通过后的正式采样冻结候选。它本身不跑正式采样、不占用正式预算、不 mark 032 done。**
> 正式命令由 PM 另派 owner 执行；执行者可沿用现有 env-controlled secret（**不写 key 值**）。
> **真实 provider 生成 = 0**。旧报告逐字节保留；本包只新增 `probes/lg032/METHOD-FINAL/**`。

## 0. 结论

- **方法审计 PASS**（门A/B/C/D/F）。
- **建议 PM 授权正式 `2 sample × A/B × 1 = 4 attempt` 串行采样**（每 attempt 48，总 192）。
- **正式尝试仍未开始**（`lg032-method-final-data` 不存在）；LG-032 仍 **in-progress**。

## 1. 冻结身份

| 项 | 值 |
|---|---|
| 审计 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final` |
| branch / base | `qa/lg032-method-final` / `a4b4455` |
| 产品 tree 对象 | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f`（== main == `0814b80`，逐字节同） |
| 独立边界 QA | `lg031-boundary@70a0fd5`（产品 tree 同；只读） |
| SDK / 契约 / 模型 | `google-antigravity==0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` |
| 驱动身份（逐字节同 cohort-ready） | `run_attempt.py` `d1994948…`、`fake_upstream.py` `de9d7a35…`、`final_cohort_config.py` `a04a8f30…`、`hard_gate.py` `0067af1c…`、`run_dry.py` `f792da28…` |
| 机器 truth 脚本 | s1 `d39d906c…`、s2 `06e2352f…` |
| seed 实际 commit | s1 `53458ac7…`（tree `119aaa4d…`）、s2 `6fa0fd00…`（tree `bc96ccc4…`），独立可复现 |

## 2. 唯一 phase data_root（贯穿 4 attempt）

- **正式 phase root** = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data`（本 worktree 冻结，**尚未创建**）。
- 所有 4 attempt 共用该 **唯一 `settings.data_dir`**；产品 `bootstrap.configure_generation_ledger(settings.data_dir)`
  与驱动 env pin（`LIGHTGRAVITY_GENERATION_LEDGER_DIR`/`LIGHTGRAVITY_DATA_DIR`）**同指一个目录**，不存在
  env pin 又被 bootstrap 覆盖的分歧（门F）。
- 物理 ledger：`<root>/generation/generation.jsonl`；跨 2 次 runtime 启动累加不归零（门B）。
- **不每 arm 重置物理 ledger**；selector/执行/verify/reviewer/repair/recheck/所有失败扣**同一 ledger**。

## 3. 固定 4 attempt IDs（不可变，存在即拒）

| # | attempt id | sample | arm |
|---|---|---|---|
| 1 | `s1_units__A` | s1_units | A |
| 2 | `s1_units__B` | s1_units | B |
| 3 | `s2_pipeline__A` | s2_pipeline | A |
| 4 | `s2_pipeline__B` | s2_pipeline | B |

- 输出目录 `runs/<attempt-id>/` 只建一次；已存在即拒（门F）。
- 任何 harness/装配/计量错误 ⇒ **整 cohort STOP、如实报告**，不重跑替换、不加额。
- 未知副作用的 write 不自动 retry；`API/SDK retry 0`。

## 4. 预算与设置（不改源容量）

- **per-attempt 48 / total 192，均在“转发前”硬拒**（`429`，ledger 不增；门B 实测 48 与 192 边界）。
- `output ≤ 16000` tokens/请求、`HTTP timeout 120s`、`SDK retries 0`、**默认并发 1**（`max_parallel=1`）。
- worker `model_calls ≤ 12` / `tool_calls ≤ 32`；reviewer `≤ 1`；**每 attempt 至多 1 次业务 repair**
  （产品 `max_repair_rounds` 默认 1；**两 arm 相同**，随同一 48 计入；不新增编排 agent）。
- 不改产品默认容量、不宽 root、不改 readonly source、不切换供应商。

## 5. 完整成功门（每 attempt）

1. 真 `build_runtime` + 真 `CoordinatorWorkerLoop`（经 FastAPI lifespan 启动）→ 真 Run → 真 Graph dispatch。
2. 真 worker SDK session（A/B 同 3 节点 `alpha`/`beta`/`verify`；arm B 经真 `discover_and_request_claim`
   自主选择合法非首项候选，程序原子授权所选 node 并绑定其隔离 worktree）。
3. 真 finalization → `verifying` → **异步**真 `ModelReviewer`（独立角色/上下文）。
4. 真 `VerificationService.verify_and_prepare`：真机器检查（授权 `evidence-present`，绑定真实
   `check_records`）+ 真 stop 门（`StoreResourceStopper(session_confirmer=executor.confirm_stopped)`）→
   `awaiting_acceptance`。**不手写 phase/cleanup=done/accepted，不 monkeypatch stop/root，不用 FakeExecutor。**
5. 真 human accept：`POST /tasks/{id}/actions {action: accept, target_run_id, expected_requirements_revision}`
   绑定 `candidate_ref`/`candidate_plan_hash`/`requirements_revision`；**同 request_id 幂等**；**错 target 拒绝（≥400）**。
6. 机器 truth 对 **per-node 真实候选 diff**（`subtask_*‑lg006-diff.patch`，非碰撞的 run 级路径）施加后判定。

**normal failure vs STOP 区别**：单 attempt 的模型/机器门/预算真实失败 = **normal failure**，如实记入该 attempt，
**不重跑替换**（占该 attempt 名额）；harness/装配/计量/ledger 身份错误 = **STOP 整 cohort**，不写正式结果。

## 6. 日志保全 / usage / 成本

- 每次运行 UTC nonce 唯一 stdout/SDKDB/SoT 持久；原始 raw/失败/worktree **不删**。
- 私有原件（SDKDB、原始证据、secrets）`700/600`，**不入 repo / 不入 prompt / 不打印**。
- 仓库仅提交脱敏摘要/manifest/evidence/sha256。
- usage 缺失记 **unknown**（不当 0）。
- **旧成本单列不清零**：旧 LG-031 工程 86、旧 023 cohort1 45 / cohort2 4 / cohort3 16、023 eval 65、
  core **unknown**；所有 pi 开发 QA / shared 成本 **unknown**。

## 7. 开关

- `decentralized_claim_enabled` / `autonomous_pool` **默认 off**；仅 arm B 在 attempt 内显式开启（唯一自变量）。
- 除该协作开关外，A/B 的 plan/Member/objectives/权限工具/输入/初始 commit/机器 truth/caps/模型 **全部相同**（门A）。

## 8. 正式命令（由 PM 另派 owner 执行）

```bash
# METHOD-FINAL overlay 优先：正式入口已把 phase root 冻结到本 worktree；
# 每个 attempt 只跑一次（attempt id 存在即拒）：
DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units --arm A
DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units --arm B
DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline --arm A
DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s2_pipeline --arm B
```

> `run_formal.py` 在调用冻结驱动（`run_attempt.py`，字节同 cohort-ready）**之前**先加载本包
> `method_config.install()` overlay，把 `PHASE_DATA_DIR` 指到 `lg032-method-final-data`、把
> `RUNS_DIR`/`EVIDENCE_DIR` 指到 `METHOD-FINAL/{runs,evidence}`。不会误用 cohort-ready 路径；
> **不写 key 值**；secret 只从 env 读取。

## 9. 修订历史

- 2026-10-16（真实 provider=0）：独立方法审计门 A/B/C/D/F 全 PASS 后写入；建议 Ready 进入正式 4 attempt，
  但**不执行**、**不 mark 032 done**、不 merge main。
