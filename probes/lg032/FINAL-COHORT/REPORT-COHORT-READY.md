---
title: "LG-032 cohort-ready 预检归档与冻结候选（REPORT）"
doc_type: report
category: engineering
status: "PRE-FORMAL — 0 real provider; freeze candidate only; independent-method audit NOT done; NOT ready for formal run"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort-ready
branch: qa/lg032-cohort-ready
phase_data_dir: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort-ready-data   # never started; absent
base_commit: "07cf5fa"
fix_commit: "0814b80"
merge_commit: "a29e94f"
product_tree_commit: "a29e94f"
source_of_truth: "DeepSeek provider real generation = 0 (formal 192 / 4×48 never run)"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort-ready（续接 owner；非 031 实施者；主代理仅 PM）"
---

# LG-032 cohort-ready — 预检结果归档与冻结候选

> 本文只**归档事实 / 冻结候选 / 列最小下一步**。**不跑新 fake、不跑真实模型、不改 harness 逻辑、不重放未知写入**。
> 所有未核实项一律标 **unknown**，不假定通过。真实 provider 生成 **= 0**。

## 0. 一句话结论

- 迁移到 `qa/lg032-cohort-ready` 的 harness 在工作区（**未提交**）3 文件上跑出 **7 次新 dry attempt**：
  **A×2 全绿**、**B×5 中 4 绿 1 红**（`s2_pipeline-B` 首个 dry 机器门失败，重跑修复后绿）。
- 四组合（s1A / s1B / s2A / s2B）**各自都各有过一次完整 0-fake-pass + 实际计量 + 硬门 证据**，但
  **所用 driver 是未提交的工作区版本**，且**未做独立方法 audit** ⇒ 只能作为 **freeze candidate**，**不准正式跑**。
- 状态判定：**PARTIAL**（见 §7）。真实 0 reason：**产品仍未对 DeepSeek 发出过任何正式生成请求**。

## 1. 精确 commit / 源锚

| 项 | 值 |
|---|---|
| 本 worktree HEAD | `a29e94f980603aab6961feb2fa468a0f76adab29`（`Merge commit '0814b80' into qa/lg032-cohort-ready`） |
| 合并父1（final-cohort WIP 基） | `07cf5fae8f0763f88e5af0ebb2258bbb6c58ff2f`（HANDOFF-MINIMAL + 移除 WIDEN_EXEC_ROOT 的 WIP） |
| 合并父2（**实际产品源**） | `0814b80a02f22d7b65623dc7f286650ddffdc6ca`（`fix(lg031-workspace-boundary): root candidate-pool selection scratch inside the executor authorized root`） |
| 独立边界 QA（另一 worktree，已 **PASS**） | `/home/yhvh/code/lightgravity-bot-worktrees/lg031-boundary` @ `70a0fd5`（`82b4357` = BOUNDARY-R1 PASS，0 provider，产品只读未改） |
| 产品真实树 | `a29e94f`（含 `0814b80` 的 `graph.py`/`workspaces/{manager,provider}.py` 修复） |
| 正式 phase data（唯一物理 ledger） | `...lg032-cohort-ready-data` — **不存在 / 未启动**（见 §5） |

> 独立 QA `70a0fd5`/`82b4357` 的**报告为后续合入，未修改 `0814b80` 源**（QA 分支只新增 `probes/lg031-workspace-boundary/qa/**`，产品文件只读）。已核：`git merge-base --is-ancestor 0814b80 HEAD` = **YES**。

## 2. 真实 provider 计数（不洗掉）

- **正式真实 DeepSeek 生成请求（产品，192 / 4×48）= 0**。正式 phase data 目录**根本不存在**。
- 本次 cohort-ready 的所有 dry 均为**本地 loopback fake 上游**（`--fake-upstream`），**无真实 provider**。
- 旧包单列保留，未并入、未清零：旧 023 cohort1 **45** / cohort2 **4** / cohort3 **16**；旧 022（unknown+6+8+5）；旧 031 工程 **86**（34+24+28）。
- **原始旧开发/失败所有成本 shared 计为 unknown，不记 0**（旧 dry 成本无独立账本）。

## 3. 新 cohort-ready fake attempt 全列（pass/fail 不洗掉）

> 数据源：各 dry 根的 `offline_dry_run_output/<sample>__<arm>/result.json` + `offline/cohort-ready-dry*.stdout` 末 40 行 + `offline/dry_captures/*.json`。
> 每个 fake attempt 的 `attempt_limit=48`、`total_limit=192`、`max_parallel=1`。**请求数为 fake 转发计量（非真实 provider）**。

| # | 时间戳(UTC) | sample/arm | 请求/48 | 到达阶段 | machine_pass | reviewer | 绑定 accept | 幂等 | 错 target | SDK stop confirmed | SOURCE(路径根) | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 20261015T202353Z | s1_units / A | 6 | awaiting_acceptance | ✅5/5 | ✅passed | ✅confirmed bound | ✅ | ✅409 | ✅(2 sess) | **cohort-ready** | **PASS** |
| 2 | 20261015T202357Z | s2_pipeline / A | 6 | awaiting_acceptance | ✅7/7 | ✅passed | ✅confirmed bound | ✅ | ✅409 | ✅(2 sess) | **cohort-ready** | **PASS** |
| 3 | 20261015T202402Z | s2_pipeline / B | 17 | awaiting_acceptance | ❌5/7 (report.rect/circle NotImplementedError) | ✅passed | ❌skipped(preconditions_unmet) | — | — | ✅(6 sess) | **cohort-ready** | **FAIL**（机器门真败，未 accept） |
| 4 | 20261015T202429Z | s2_pipeline / B | 16 | awaiting_acceptance | ✅7/7 | ✅passed | ✅confirmed bound | ✅ | ✅409 | ✅(6 sess) | **cohort-ready** | **PASS**（修复后重跑） |
| 5 | 20261015T202445Z | s1_units / B | 16 | awaiting_acceptance | ✅5/5 | ✅passed | ✅confirmed bound | ✅ | ✅409 | ✅(6 sess) | **cohort-ready** | **PASS** |
| 6 | 20261015T202324Z | s1_units / B | 16 | awaiting_acceptance | ✅5/5 | ✅passed | ✅confirmed bound | — (旧 driver 无幂等步骤) | — | ✅(6 sess) | final-cohort 根 / cohort-ready 捕获 | PASS（旧 driver，过渡） |
| 7 | 20261015T202344Z | s1_units / B | 16 | awaiting_acceptance | ✅5/5 | ✅passed | ✅confirmed bound | ✅ | ✅409 | ✅(6 sess) | final-cohort 根 / cohort-ready 捕获 | PASS（过渡） |

**过渡/历史（final-cohort 根，前 owner 同源工作，保留不洗）**：

| 时间戳 | sample/arm | 请求 | 结果 |
|---|---|---|---|
| 20261015T202204Z | s1_units / B | 16 | PASS（绑 accept；旧 driver 无幂等/错 target 步骤） |
| 20261015T202100Z | s1_units / B | 48 | **FAIL** — `executing→failed`，**429 fake 请求上限**（fake 误把 execution 判为 selection 死循环；48/48 耗尽），与 narrow-B 后 429 同模式 |
| 20261015T200910Z | s1_units / B | 0 | **FAIL** — `failed`，0 请求 |
| 20261015T200829Z | s1_units / B | 0 | **FAIL** — `executing→failed`，0 请求 |

> 更早的探索性 dry（A×多、B×多，`lg032-final-cohort-data-dry-*`）共 14 个 result.json，多数因 **driver/fake 中间态** 失败或部分通过；已逐条保全，未删除。**这些为开发过程，不作为冻结证据。**

### 3.1 关键：证据对应 **未提交的工作区 driver**，不是 HEAD

- 3 个 harness 文件在 HEAD 与工作区**内容不同**（`git status` = ` M`）：

| 文件 | HEAD sha256(前16) | 工作区 sha256(前16) |
|---|---|---|
| `harness/fake_upstream.py` | `6d80f47e596a2e4b` | `de9d7a3547dd0a99` |
| `harness/final_cohort_config.py` | `fd799d2d0b3d5e88` | `a04a8f309a72626c` |
| `harness/run_attempt.py` | `f6d8e40426a119f4` | `fbbbb81e94fbc858` |

- 已核：HEAD 版 `run_attempt.py` **无** `truths_before_accept` / `accept_idempotent` / `accept_wrong_target` / `candidate_diff_paths`；HEAD 版 `fake_upstream.py` 仍用 `_is_selection`（按工具名判定），即**导致 429 死循环的旧实现**。
- ⇒ 上表 #1–#5 的 PASS **只对工作区（dirty）driver 有效**。**必须精确 commit 这 3 个 dirty harness 文件**（本报告已随附），冻结源 hash 才成立。

## 4. A/B 同质性核对（唯一 mode 变量）

| 维度 | arm A | arm B | 是否相同 |
|---|---|---|---|
| 3 节点计划 | `deliver`(impl,write) → `verify`(verif,read-only) | `alpha`(impl,write) + `beta`(impl,write) → `verify`(verif,read-only；依赖两者) | **节点数/依赖不同 = 唯一自变量** |
| capability / 角色目录 | `LIGHTGRAVITY_ROLE_CATALOG` 固定 `implementation→[lg032-worker]`、`verification→[lg032-verifier]` | **同** | ✅ |
| Member / 权限 | `lg032-worker`（写）/ `lg032-verifier`（只读） | **同** | ✅ |
| 开工工具集 | 冻结 prompt（`_WORKER_PROMPT`/`_VERIFY_PROMPT`），禁 `view_file`，`create_file/edit_file` | **同 prompt 模板**；arm B 另开 `autonomous_pool` 开关使选择期 session `allowed_tools=()` 仅 `discover_and_request_claim` | ✅（B 的候选池机制 = 自变量 2，属 PLAN §1.2 预注册） |
| 模型 / SDK / 契约 | `deepseek-v4-flash` / `google-antigravity==0.1.22` / `1.11.0` | **同** | ✅ |
| 初始 commit | `_init_repo` 从同一 `fixtures/<sample>/initial/` 生成（A/B 逐字节相同） | **同** | ✅ |
| 任务 input（objective/acceptance/`workspace_ref=candidate-ws`） | `SAMPLE_SPEC` 同一份 | **同** | ✅ |
| 机器 truth | 同一 `fixtures/<sample>/acceptance.py`，子进程隔离 cwd | **同** | ✅ |
| 独立 ModelReviewer | 真 `verify.review.ModelReviewer`（真模型；fake 上游下 fake 应答） | **同** | ✅ |
| 停止门 | `StoreResourceStopper(session_confirmer=executor.confirm_stopped)` | **同** | ✅ |
| 预算 / 并发 | `max_parallel=1`、total 192、attempt 48、output≤16000、HTTP 120、retry 0 | **同** | ✅ |

**唯一 mode 变量 = ①实施写节点数（A=1 合并写 vs B=2 独立写）②arm B 候选池自主选择机制。** 无其他差异。

### 4.1 前作者为方便 fake 是否改了正式 prompt/tool/caps/真预算？

- 已核 `git diff`（3 dirty 文件）**只**改：fake 上游 phase 判定/终止、driver 候选 diff 收集 + accept 前置真值门 + 幂等/错 target 步骤、worktree/data 路径常量。
- **未改**：产品 `max_parallel`、total/attempt 预算、`output≤16000`、HTTP/timeout、`PHASE 1` 产品 prompt 来源（`graph.py:965` 真实存在）、工具权限、`LIGHTGRAVITY_ROLE_CATALOG`。
- 对被移除的 `LG032_WIDEN_EXEC_ROOT`（前 owner 曾用于 fake 时宽松化 executor root）：现**改为显式拒绝**（`run_attempt.py` 设置该 env 即 `SystemExit`）——即**更严格**，非放宽。
- **裁定**：**未见**为方便 fake 而偷偷放宽正式 prompt/tool/caps/真预算的 diff。**但**：**此判定仅为快照 diff 审查，尚未经独立方法 audit**，故标注为**未正式冻结候选**（见 §7）。

## 5. 物理 ledger / 保全

| 项 | 状态 |
|---|---|
| 正式 ledger `lg032-cohort-ready-data/generation/generation.jsonl` | **不存在**（formal 未启动）；dry ledger 均落各 `-dry-<stamp>-<nonce>` sibling 根，**互不污染、跨 arm 各自累加、`corrupt=false`** |
| 各 dry attempt 计量 | 见 §3 `请求/48` 列；每个 dry 根 `generation_final.count` = 该 attempt 请求数（A=6, B=16/17, 429 失败=48） |
| 硬门（G5 冻结） | 每次 dry `ledger_persistent_single_path` + `counter_ledger_matches_frozen_path` 均 **PASS**，`physical_history_exists_at_freeze=false`（干净起点） |
| **损坏绝不当作 0** | `corrupt=false` 显式记录；fail-closed 设计保留 |
| 旧 dry 删除事故 | 记录于 `PRESERVATION-INCIDENT.md`；**禁令生效**：禁 `rm/rmtree/reset/clean/覆盖` |
| SDKDB / raw payload / secret | **不入 repo**；dry_captures 仅 harness 自身脱敏元数据（phase/path/tool_names/roles/tail/full=假上游请求记录，无凭证）；已扫描无 `sk-`/`BEGIN`/`api_key`。**私有原件保留于 ignored 路径** |

> **未知写入不能重放**：429 失败 attempt（48/48）与 0 请求 attempt 的副作用**未重放**；仅 `git status`/只读核。

## 6. 四组合「是否各自有完整 0-fake-pass + 实际计量硬门证据」

| 组合 | 当前 driver 版本完整 PASS | 证据齐 | 备注 |
|---|---|---|---|
| s1_units / A | ✅ (#1) | ✅ | 5/5 检查、req=6、绑 accept、幂等、错 target |
| s1_units / B | ✅ (#5) | ✅ | 5/5、req=16、6 session、绑 accept、幂等、错 target |
| s2_pipeline / A | ✅ (#2) | ✅ | 7/7、req=6、绑 accept、幂等、错 target |
| s2_pipeline / B | ✅ (#4) | ✅ | 7/7、req=16、6 session、绑 accept、幂等、错 target（首个 #3 真败，重跑绿） |

**结论：四组合均依赖工作区 driver 各有一份完整 0-fake-pass + 实际计量 + 硬门证据。** 但：

1. 证据绑定的是 **dirty（未提交）** driver，**必须先 commit 冻结**；
2. **独立方法 audit 尚未做**；
⇒ 满足「可冻结 manifest **候选**」条件，**不满足正式跑条件**。

## 7. 状态判定：**PARTIAL**（含最小下一步）

### 缺门（最小下一步，不改逻辑、不补跑）

1. **commit 冻结**：精确提交 3 个 dirty harness 文件 + 本 REPORT + 脱敏证据（不含 SDKDB/rawpayload/secret/私有 fixture）。← 本任务已执行，见 §8。
2. **源 hash manifest 候选**：记录 3 文件 sha256 + 产品树 `a29e94f` + fixture 初始 head。← 随 commit 落定。
3. **独立方法 audit（必须由独立 owner 做）**：审 fake 上游 phase 判定是否与真实产品 phase 一致、driver accept 前置真值门是否真绑机器 truth（非 Task checks 空假门）、幂等/错 target 是否为真实产品语义、A/B 同质性。**未做 → 不准正式跑。**
4. **正式命令（仅在 1–3 通过后）**：
   ```
   DEEPSEEK_API_KEY=… .venv/bin/python probes/lg032/FINAL-COHORT/harness/run_attempt.py \
       --sample s1_units --arm A      # 4 个：s1A / s1B / s2A / s2B，串行，各一次
   ```
   total 192 / each 48 / default parallel 1；**不改产品 caps / 不扩大 root**。

### 未知 / unknown（不重试）

- **前 owner `23608` / log `c8n8bi2n` max-noncache 160k、`exit 143`、elapsed 368，于 s1B 最后 fake 试跑后**：
  该次运行**未产出可核 result.json**（s1B 最后落盘完整件为 #5 = `20261015T202445Z` PASS）。
  ⇒ 该次**按 unknown 归档，不重试**（与指令一致）。副作用**仅只读核**，未重放未知写入。
- 旧 dry 阶段更多中间失败（§3 尾注 14 件）**不逐条重跑**。

## 8. 交付与交接

| 项 | 路径 |
|---|---|
| 本报告 | `probes/lg032/FINAL-COHORT/REPORT-COHORT-READY.md` |
| 状态 | `probes/lg032/FINAL-COHORT/STATUS.md`（APPEND cohort-ready 段） |
| driver（冻结候选） | `harness/{run_attempt,fake_upstream,final_cohort_config}.py` |
| 新 dry stdout | `offline/cohort-ready-dry*.stdout` |
| 脱敏捕获 | `offline/dry_captures/*.json`、`evidence/cohort-ready/**` |

**未做**：不正式跑、不 mark 032 done、不 main merge、不 push/deploy/publish、不嵌套代理、不新增 provider 调用、不改产品 caps/root、不改 harness 逻辑。

## 9. 修订历史

- 2026-10-16（**首个正式真实请求之前**，真实 provider=0）：归档 cohort-ready 预检 7 次新 fake attempt（A×2 全绿、B×5 四绿一红）+ 过渡件；核 A/B 唯一 mode 变量；判 **PARTIAL**；冻结候选交独立 audit。
