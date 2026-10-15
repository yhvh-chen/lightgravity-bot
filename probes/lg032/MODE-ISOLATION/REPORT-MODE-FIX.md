---
title: "LG-032 MODE-ISOLATION 返修报告（harness 串行 mode 污染；产品源不改）"
doc_type: report
category: engineering
status: "PARTIAL — 协议失败认定完成；harness 隔离修复实现中；real provider 0；032 NOT done"
experiment_id: lg032-mode-isolation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation
branch: fix/lg032-mode-isolation
base_commit: "379c089"
owner: "agent:pi-lg032-mode-isolation（独立返修 owner；主 PM 仅 PM）"
updated: "2026-10-16"
---

# LG-032 MODE-ISOLATION 返修报告

> 本文为 LG-032 首正式 cohort（`probes/lg032/METHOD-FINAL/runs`）串行 mode 污染的真实返修报告。
> **产品 source 不判 bug，问题在独立 QA harness**：4 个 attempt 共享同一 `settings.data_dir` 下唯一
> `settings/settings` 实体，arm B 写 `decentralized_claim_enabled=True` 后 arm A **从未写 `False`**，
> 于是 A 继承 B 模式（`s2_pipeline__A` show 6 refs = 同 B）。**本包 real provider 0，不新增正式请求。**

## 0. 先落明确协议失败认定（前 8 round）

**主 PM 已拒绝首正式 cohort 87 真实请求的 A/B 成本对照资格。** 真实数据（旧 `FORMAL-REPORT.md` §3，逐字节保留）：

| # | attempt | arm | 真实 requests | session refs | 应然 mode | 实际 mode（复算） |
|---|---|---|---|---|---|---|
| 1 | `s1_units__A` | A | **21** | **3** | A（deterministic，pool off） | A ✅ |
| 2 | `s1_units__B` | B | **26** | **6** | B（autonomous pool on） | B ✅ |
| 3 | `s2_pipeline__A` | A | **19** | **6** | A（pool off，应 3 refs） | **B ❌ 继承** |
| 4 | `s2_pipeline__B` | B | **21** | **6** | B | B ✅ |

- **认定：协议失败（serial mode pollution）。** `s2_pipeline__A` 的 session refs=6（而非 A 的 3）表明其
  runtime 实际以 arm B 的横向协作模式（`autonomous_pool=True`）运行；其 `19` 请求数与 A(21)/B(26) 的
  **A/B 成本对照**均**不可用于任何成本结论**。
- **归因（harness，非产品）**：`_seed_resources` 每次都以受控 `ConnectionService.update_settings` 覆写
  worker/coordinator/reviewer ref，但**不显式设定** `decentralized_claim_enabled`（`_UNSET` ⇒ 保持现值）。
  仅 arm B 调 `_enable_decentralized_pool` 写 `True`；arm A **无显式 `False`**。共享 `settings.data_dir`
  的持久 `settings` 实体于是把 B 的 `True` 带给后续 arm A。**产品 `build_runtime` 行为正确**，其读到的
  就是持久实体里那个 `True`。
- **产品 source 不判 bug**：`ClaimPolicyReader.read()` 与 `bootstrap.py:444/450`（`autonomous_claim=decentralized`
  /`autonomous_pool=decentralized`）行为符合契约；**source 默认 off 不变**（`settings/models.py:88` 默认 `False`）。

**旧产物全部保留**：旧报告 / 成本 / Run / SDK / raw / ledger 87 **逐字节保留**；**不改旧字节、不修后补跑
旧 formal、不 main write**。

## 1. 本包目标（返修范围）

只改**独立 QA harness**（`probes/lg032/**`），**不改产品 `backend/lightgravity/**`**：

1. **所有 attempt 显式设定模式**：A ⇒ `decentralized_claim_enabled=False`；B ⇒ `True`，且经产品**现有受控
   settings API/服务**（`ConnectionService.update_settings`）合法设置，**非直接伪造 Run 结果**。
2. **在产品真正 `build_runtime`/`CoordinatorWorkerLoop` 之前完成装配**（读回 settings ⇒ build）。
3. **真实 bootstrap 后断言并记录 active dispatcher mode + settings 三开关**与期望一致；**不能只 assert
   字符串 env**；**不能 A 继承 B**。
4. **phase 结束恢复 private-candidate 设置为 off 并记录**；source 默认 off 不变。
5. **必要新协议/overlay 使用全新独立 cohort2 持久 root**：预定 `lg032-cohort2-data`；未来同 4 attempt IDs
   只在新 cohort2；已知首 cohort87 列协议失败成本。
6. **0 验证**：真正共享同一 actual `settings.data_dir`，真实 bootstrap 依次 **A→B→A→B**（非各 nonce 独立
   settingsRoot 掩盖污染）。
7. 记录 source 行为未变 `55e4de56`、driver hash 变化、真正 mode 快照 / selector refs / 账本 before/after /
   机器 checks / accept；**不宣 formalReady、不 mark 032 done、不 main merge**。

## 2. 硬边界（全程）

- **不嵌套代理 / 不 push / 不 deploy / 不 publish / 不 main write**。
- **禁 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖旧输出**；新输出唯一命名，全部持久 `700/600`。
- 0 real provider：只 loopback fake（真 SDK loopback + actual normal Coordinator），**禁外网 POST / 真实
  credentials 用于 fake**。
- 旧 87 + 未来 cohort2 预算**先后单列**；所有 pi 开发/失败 cost **unknown**，**不 0、不预设省 token**。
- 采样/seed/3nodes/权限/模型/预算 48 each 总 192 **不变**；**本包 0 真，不授权新 formal**。
- wall600 / maxround130 / noncache170k / idle150 / retry0；REPORT 每 15 round 更新；70 round 前保存阶段判断。

## 3. 修复实现（harness only，产品源只读）

`probes/lg032/FINAL-COHORT/harness/run_attempt.py`：

1. **build 前显式装配**：`_set_mode(settings, arm)` 在 `build_runtime` 之前经产品受控
   `ConnectionService.update_settings(expected_revision, decentralized_claim_enabled=(arm=="B"))` 写；
   A=`False`、B=`True`。返回 before/after 快照。**所有 attempt 都写**，不再 B-only。
2. **build 后断言实际 mode**：`_assert_active_mode(settings, dispatcher, arm)` 读**真实装配的**
   `dispatcher._autonomous_claim` / `_autonomous_pool` / `dispatcher._decentralized_enabled()`
   与持久 `settings` 实体三开关（`decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`），
   不一致⇒`SystemExit` **STOP**。**不是字符串 env 断言**；**A 不可能继承 B**。记录于
   `result.json:mode_snapshot_after_bootstrap`。
3. **phase 结束恢复 off**：`_safe_restore_mode(settings)` 在 `finally` 把共享 settings 实体写回
   `decentralized_claim_enabled=False` 并记录 `mode_restore`；**产品 source 默认 off 不变**。
4. **删除**旧 B-only `_enable_decentralized_pool`。

新 overlay `probes/lg032/MODE-ISOLATION/mode_config.py`：把冻结协议路径常量重定向到**全新持久 cohort2
root `lg032-cohort2-data`**（未来同 4 attempt IDs 只在新 cohort2）；不创建/读写旧 phase root。

**合规边界**：未宽 root、未 `monkeypatch` stop、未手写 state、未伪造 Run；只经产品现有受控 settings API/服务合法设置。

## 4. 0-real 验证证据

### 4.1 真实 bootstrap 串行 `A→B→A→B`（同一 shared `settings.data_dir`）

`serial_mode_probe.py`，root `lg032-cohort2-serial-{fix,legacy}-<utc>`：

- **fix 场景**：4/4 步 `_assert_active_mode` congruent（实际 dispatcher mode + 三开关均与 arm 一致）。
- **legacy 场景（对照）**：无显式 `False`，第三步 A(after B) `dispatcher_autonomous_pool=True` ⇒ **复现首 cohort 污染**。
- verdict **PASS**；`evidence/serial-mode-20261015T205829Z.json`。
- `real_provider_generation: 0`。

### 4.2 真 SDK loopback fake 串行 `B→A`（同一 shared `settings.data_dir`）

`serial_sdk_fake.py`（真 SDK + 真 `GraphDispatcher` + 真 `CoordinatorWorkerLoop` + 真 verify/review；
loopback fake upstream；dummy credential，无真实 credentials 外发）：

| 项 | B | A(after B) |
|---|---|---|
| rc/ok | 0/true | 0/true |
| session refs | **6** | **3** |
| fake 相位 | execution, review, **selection**, verify | execution, review, verify（**无 selection**）|
| dispatcher pool | **True** | **False** |
| settings 开关 | `decentralized_claim_enabled=True` | `False` |

- 同一物理 ledger 累加 **16→23**（persistent、不归零）；`mode_restore.restored_off=true`。
- 关键：首 cohort 的 `s2_pipeline__A` 是 **6 refs**（B-like）；本包修复后 A-after-B 为 **3 refs 且无 selection 相位**。
- verdict **PASS**；`evidence/sdk-serial-mode-20261015T205924Z.json`（已脱敏）。

### 4.3 源与驱动 hash

| 项 | 值 |
|---|---|
| 产品源 tree（`backend/lightgravity`）| `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` — **base==main==本包 未变** |
| driver `run_attempt.py` | 基 `4c564836131a5d142245a9618f5de265bea74084` → 本包 `7fc515ef445ed5a0622045839f2cbde877ebe8ad`（**变化，harness 修复**）|
| extract commit | `c433ffc`（harness fix）；本文件含后续 selftest/report 更新 |

### 4.4 单 attempt 回归（固定 harness 未破坏正常路径）

- `run_dry.py --sample s1_units --arm A`：14/14 步 PASS；机器门 5/5；3 真实 session；
  accept confirmed/idempotent/409；`mode_snapshot_after_bootstrap.dispatcher_autonomous_pool=False`；
  `mode_restore.restored_off=true`。
- `fairness_selftest.py`：**PASS**（同 3 节点 plan A==B、seed SHA arm 无关、
  新 mode 不变量 `_set_mode`/`_assert_active_mode`/`_safe_restore_mode` 均在、旧 B-only writer 已移除）。
- 证据：`evidence/single-A-dry-fixed-20261016.json`、`evidence/fairness-selftest-20261016.txt`。

### 4.5 保全说明

- 单 A dry 由冻结 `run_dry.py` 默认写入了另一个 worktree 的新 unique capture；为不污染他包，
  该**新文件已原样移至本包** `MODE-ISOLATION/offline/`（未删除字节）；被碰 worktree 已复核 clean。

## 5. 正/负边界

- **本包 0 真**：不发送任何真实 provider 请求；`real_provider_generation=0`（两证据均记录）。
- 未改旧字节（旧 87 / Run / SDK / raw / ledger 逐字节保留）；未后补跑旧 formal；未 `main` write。
- 未创建 formalRoot、未发真实；`lg032-cohort2-data` 由 overlay 预定但**本包未创建**。
- 禁止 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖——全程只新增 unique 输出。

## 6. 成本（不洗 0）

- 本 cohort2（首正式 87）**协议失败**，其 87 真实请求**单列**为失败/协议代价，不计入任何 A/B 成本。
- 未来 4 attempt（新 cohort2）预算 48 each / 192 **未开始**；独立单列。
- 本包 pi 开发 / fake / 失败尝试 cost = **unknown**（**不记 0**，不预设省 token）。

## 7. 修订历史

- 2026-10-16（round 1–8）：建 worktree；认定协议失败；落 REPORT+STATUS。
- 2026-10-16（round 9–30）：实现 harness `_set_mode`/`_assert_active_mode`/`_safe_restore_mode`；新建
  cohort2 overlay；0-real 串行 bootstrap 4 步 + 真 SDK A-after-B 验证 PASS；commit `c433ffc`。
  **交独立 serial 方法 QA；本包不自宣 formalReady / 不 mark 032 done / 不 main merge。**
