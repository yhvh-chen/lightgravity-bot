---
title: "LG-032 METHOD-FINAL PLAN 补遗（独立方法审计）"
doc_type: addendum
category: engineering
status: "FROZEN-BEFORE-FIRST-REAL-REQUEST (addendum only; does not edit PLAN.md)"
experiment_id: lg032-fair-ablation-20261016
base-8s: "a4b4455"
updated: "2026-10-16"
owner: "agent:pi-lg032-method-final（独立方法审计 owner）"
---

# LG-032 METHOD-FINAL — PLAN 补遗

> 本补遗**不改** `FINAL-COHORT/PLAN.md`（冻结，只读）。它记录独立方法审计对本 worktree 正式采样的**补充冻结**。
> **旧 `REPORT-COHORT-READY.md` §4 的混淆协议已被 PM 拒绝**，不作为新标准；当前唯一正确协议 =
> **A/B 同 3 节点、同 Member/plan/objectives/权限工具/输入/初始实际 commit/机器 truth/caps/模型**，
> **唯一差异 = 协作开关**（见 `FAIRNESS-CORRECTION.md`）。

## 1. 本 worktree 的正式路径冻结

- **正式 phase data_root（唯一持久，贯穿 4 attempt）**：
  `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data`
- **正式 attempt 输出**：`probes/lg032/METHOD-FINAL/runs/<attempt-id>/`（不可变，存在即拒）
- **正式脱敏 evidence**：`probes/lg032/METHOD-FINAL/evidence/<attempt-id>.json`
- **boundary 独立 scratch**（计量门专用，与 formalRoot 无混淆）：
  `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-boundary`
- **overlay**：`method_config.install()` 在导入驱动前改 `PHASE_DATA_DIR`/`RUNS_DIR`/`EVIDENCE_DIR`；
  产品源、既有 harness 逻辑、`FINAL-COHORT/PLAN.md` **字节不变**。

## 2. 独立方法门（本包，全部 0 real）

| 门 | 内容 | 结果 |
|---|---|---|
| A | canonical plan/profile/caps/objective/tools/truth-hash A==B；seed actual SHA 两 arm 同 pin | PASS |
| B | 真 `build_runtime`×2 + 真 executor `_make_proxy` & 真 `run_review_turn` 同物理 ledger 累加；独立 scratch `48`/`192` 转发前拒 + corrupt fail-closed | PASS |
| C | 机器 truth 绑定（空 checks vacuous 危险 + `evidence-present` 真绑 `check_records`）+ 静态无伪造（不手写 phase/cleanup/accepted、不 monkeypatch stop/root、无 FakeExecutor） | PASS |
| D | 独立跑 B 的 s1/s2 各一次 0-fake（真 SDK selection/执行/verify/reviewer/accept） | PASS 2/2 |
| F | formal 唯一 phase root / 唯一 4 attempt id / 无 env pin 被 bootstrap 覆盖 | PASS |

## 3. A 证据引用规则

- 本 worktree 的 `run_attempt.py` sha256 = `d1994948…`，与 `qa/lg032-cohort-ready@a4b4455` **逐字节相同**。
- 因此 `s1_units__A`（`20261015T203344Z-s1A-fair`）与 `s2_pipeline__A`（`20261015T203351Z-s2A-fair`）
  的 **0-fake A 证据可在精确 hash 一致前提下引用**。
- **旧 B 证据不可引用**：其 driver 为旧 `fbbbb81e…` / 旧混淆 4-node 计划；本包已用新驱动**重跑 B**（门D），
  不改 pin、不洗旧失败。
- seed 实际重建须与 pin 比对（门A 已比），**不改 pin**。

## 4. 预算与开关（不变）

- 正式 = `2 sample × A/B × 1 = 4 attempt`，每 attempt 48，总 192；转发前硬拒；失败同 ledger。
- 唯一自变量 = 协作开关；除它外 A/B 全同。
- `decentralized_claim_enabled`/`autonomous_pool` **默认 off**。
- 至多 1 业务 repair（两 arm 相同，随 48 计入）。

## 5. 边界

- 不改产品源 / 既有 harness 逻辑；只新增 `METHOD-FINAL/**` + 冻结 manifest + 本补遗。
- 不正式采样、不外网 POST、不嵌套代理、不发布、不 merge main。
- 保留所有 raw/失败/SDKDB/worktree；禁 `rm`/`rmtree`/`reset`/`clean`/`TMD`/覆盖。
- secret 不入 repo / 提示词 / 日志。

## 6. 修订历史

- 2026-10-16（真实 provider=0）：新建本补遗，冻结本 worktree 正式路径、独立方法门与 A 证据引用规则。
