---
title: "LG-032 MODE-ISOLATION STATUS（每 15 round 更新）"
doc_type: status
category: engineering
status: "round 9–35：harness mode 隔离修复 + 0-real 串行 bootstrap/SDK A-after-B/单A回归/fairness 全 PASS；交独立 QA；real provider 0"
experiment_id: lg032-mode-isolation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation
branch: fix/lg032-mode-isolation
base_commit: "379c089"
updated: "2026-10-16"
owner: "agent:pi-lg032-mode-isolation"
---

# LG-032 MODE-ISOLATION STATUS

## 当前阶段（round 9–28）

- **协议失败认定完成**（见 `REPORT-MODE-FIX.md` §0）：首正式 cohort 的 `s2_pipeline__A` 继承 arm B mode；
  87 真实请求的 A/B 成本对照资格**已被 PM 拒绝**。
- **根因**：harness `_seed_resources` 每 attempt 覆写 settings 但 `decentralized_claim_enabled` 用 `_UNSET`
  保持现值；仅 B 写 `True`，A 不写 `False` ⇒ 共享 `settings.data_dir` 串行污染。**产品源不判 bug。**
- **本包 real provider 0**；未改产品 `backend/**`；旧产物逐字节保留。

## harness 修复（已实现，commit 待定）

`probes/lg032/FINAL-COHORT/harness/run_attempt.py`（仅 harness，非产品源）：

- `_set_mode(settings, arm)`：build **之前** 逐 attempt 显式经产品受控 `ConnectionService.update_settings`
  写 A=`False` / B=`True`；返回 before/after 快照。
- `_assert_active_mode(settings, dispatcher, arm)`：真 bootstrap **之后** 读**实际装配对象**
  `_autonomous_claim`/`_autonomous_pool`/`_decentralized_enabled()` + 三个持久开关，与期望不一致
  **直接 SystemExit STOP**（非字符串 env 断言；不 A 继承 B）。结果记录于 `mode_snapshot_after_bootstrap`。
- `_safe_restore_mode(settings)`：`finally` 中把共享 settings 实体恢复为产品默认 off，并记录；
  产品 source 默认 off 不变。
- 删除旧 B-only `_enable_decentralized_pool`。
- `probes/lg032/MODE-ISOLATION/mode_config.py`：新 overlay → **全新 cohort2 持久 root `lg032-cohort2-data`**。

## 0-real 验证（已完成）

- `serial_mode_probe.py`：`lg032-cohort2-serial-{fix,legacy}-*` 各一个共享 `settings.data_dir`，
  真实 `build_runtime` 串行 **A→B→A→B**。
  - **fix 场景 4/4 步 congruent**（真实 dispatcher mode + 三开关均与 arm 一致）。
  - **legacy 场景复现原错误**：A(after B，无显式 False) `autonomous_pool=True` 继承。
  - verdict **PASS**（`evidence/serial-mode-20261015T205829Z.json`）。
- `serial_sdk_fake.py`：真 SDK loopback fake + 真 Coordinator，同一 `settings.data_dir` 串行 **B→A**。
  - **B**：6 refs，含 `selection` 相位，pool=True（自治池真实生效）。
  - **A(after B)**：**3 refs，无 selection 相位，pool=False**（= 正确确定性 A；修复首 cohort 的
    `s2_pipeline__A` 6 refs 缺陷）。
  - 同一物理 ledger 累加 16→23（persistent，不归零）；`mode_restore.restored_off=true`。
  - verdict **PASS**（`evidence/sdk-serial-mode-20261015T205924Z.json`，已脱敏）。

## 已完成

- [x] 新持久 worktree `lg032-mode-isolation` / branch `fix/lg032-mode-isolation` 基 `379c089`。
- [x] `REPORT-MODE-FIX.md` + `STATUS.md` + `QA-HANDOFF.md`。
- [x] harness 显式 mode 装配（A=false/B=true，build 前）。
- [x] 真实 bootstrap 后 active mode + 三开关断言/记录 + STOP 失败闭合。
- [x] phase 结束恢复 off 并记录。
- [x] 新 cohort2 持久 root + overlay（`lg032-cohort2-data`）。
- [x] 0-real 共享 data_dir 串行 A→B→A→B bootstrap 验证（fix+legacy）。
- [x] 0-real 真 SDK loopback A-after-B 复现/修复。
- [x] fairness selftest（新不变量）PASS；单 A dry 14/14 PASS（回归）。
- [x] 精确 commit `c433ffc` + `f08a12f`（+ 本 commit）。
- [x] 交独立串行方法 QA（`QA-HANDOFF.md`）。

## 阶段判断（round 30+；70 round 前保存）

**本包交付完成，可交独立 QA**。已实现 harness 修复 + 0-real 双向验证；**不宣 formalReady / 不 mark 032 done /
不 main merge**。剩余工作（由 PM 决定）：独立 serial 方法 QA 复核；是否授权新 cohort2 正式 4 attempt。

## 硬边界

不嵌套代理/push/deploy/publish/mainwrite；禁 rm/rmtree/reset/clean/覆盖；0 real provider；
预算 48 each/192 不变但本包 0 真；cost unknown 不 0。
