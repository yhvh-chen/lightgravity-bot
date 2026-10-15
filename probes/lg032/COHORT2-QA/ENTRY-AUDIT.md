---
title: "LG-032 COHORT2 入口最终独立核查（ENTRY-AUDIT）"
doc_type: audit
category: engineering
status: "PASS — cohort2 入口/装配/mode/计量冻结身份与实际 git object 一致；允许按 PM 授权执行正式 4 attempt"
experiment_id: lg032-cohort2-formal-entry-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "ec69eff"
entry_commit: "05de3c9"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 cohort2 入口最终核查 + 真实正式执行 owner；非产品/driver/entry 作者）"
---

# LG-032 COHORT2 入口最终独立核查（ENTRY-AUDIT）

> 独立于产品 / driver / entry 作者的最终核查。**0 real provider**。
> 本核查只读 agent / `REPORT-SERIAL-R1.md` / `ENTRY-REPORT.md` / `COHORT2-FORMAL-FREEZE.md`
> 及 entry/overlay/driver 必要局部；未做全库调查、未 dispatch 长日志。
> 结果 **PASS** ⇒ 允许按 PM 授权执行正式 4 attempt。

## 0. 结论

**PASS。** cohort2 入口 runner 正确加载**已验收** driver 与 fixtures/pinned seed，phase/RUNS/EVIDENCE
实际指向 cohort2（**非** METHOD-FINAL / FINAL-COHORT 旧 root），driver/overlay 字节与实际 git object
同 fix worktree `8098514`；`--freeze-identity` / `--help` 只读、无 runtime/任务/forward/Root 写副作用。
正式 root 与独立输出 root 核查前后均 **ABSENT**。**无 STOP 条件。**

## 1. 阶段 0 — 保全既有 3 entry 文件（未改逻辑）

- 核查前 dirty：**仅** 3 个未跟踪 entry 文件（`git status --porcelain` = 正好
  `?? run_formal.py` / `?? ENTRY-REPORT.md` / `?? COHORT2-FORMAL-FREEZE.md`），无其他改动。
- 精确 **byte-preserving** commit（不重放 write、不改逻辑）：
  - `entry_commit` = **`05de3c9`**（`lg032 cohort2: preserve formal entry runner + freeze/entry reports`）。
  - 提交后 tree **clean**，无残留 dirty。
  - staged blob `run_formal.py` sha256 = `a7477753…3040` == 核查前实际字节 == `ENTRY-REPORT.md` §2.1 声明。
- **正式 root 与独立输出 root 核查前后均不存在**（见 §4）。

## 2. 独立入口核查（逐项）

### 2.1 加载链正确（实际加载同一已验收 driver + fixtures/pinned seed）

| 项 | 实际值 | 判定 |
|---|---|---|
| 入口 | `probes/lg032/COHORT2-QA/run_formal.py` sha256 `a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040` | ✅ |
| overlay | `MODE-ISOLATION/mode_config.py` sha256 `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ |
| driver | `FINAL-COHORT/harness/run_attempt.py` sha256 `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ OK |
| config | `FINAL-COHORT/harness/final_cohort_config.py` sha256 `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ OK |
| SDK / contract | `0.1.22` / `1.11.0`（venv 实测 `importlib.metadata` = 0.1.22） | ✅ |
| seed SHA s1 / s2 | `seed.git` HEAD 实测 `53458ac742b5aa4fd6913000aeeb69ae94cc80c1` / `6fa0fd006ff058a7299f5e6dc42013fa051303de` == `seed.sha256` pin == 冻结 | ✅ |

- 加载顺序正确：`_load_overlay_config()`（overlay `install()` 先 patch `final_cohort_config` 路径常量 +
  `phase_env`）**先于** `import run_attempt`；driver 模块级 `os.environ.update(C.phase_env())` 因此看到
  cohort2 root。`run_formal.py` 内 `import run_attempt` 仅出现在 `_print_identity` / `main`（两者都在
  install 之后）。✅
- 入口**不复制核心逻辑**：grep 确认 entry 内无 `build_runtime` / `Coordinator` / `_set_mode` / `_assert`
  实现，仅有路径适配（`WORKTREE`/`HARNESS_DIR`/`FIXTURES_DIR` 指向本 worktree）+ 委托
  `R.run_attempt(sample, arm, dry_run=False)`。✅
- 入口**不放权限**：不写 key、不切 provider、不改 caps/plan/prompt/tool、不改 source。✅

### 2.2 driver/overlay 与 fix worktree `8098514` 及 SERIAL-R1 执行版本 bytes 一致

- 实际 bytes：`run_attempt.py` / `final_cohort_config.py` / `mode_config.py` 与
  `/home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation`（HEAD `8098514`）**逐字节 diff 空**。✅
- **实际 git object 比对**（不猜、不靠短 hash 描述）：QA HEAD `ec69eff` 与 fix HEAD `8098514` 的 blob id
  完全相同：
  - `run_attempt.py` = `b1cc6c550c0408fa304c2a2c9c5d76160e14b98a`
  - `final_cohort_config.py` = `307ea0dda7307ec12c881056ed6a315fc7ba5016`
  - `mode_config.py` = `bc36b80b350af195fbeadc26f03d67c7a663fac3`
- 旧报告 `REPORT-SERIAL-R1.md` §1「注（文档精度）」所述 driver 短 hash 描述差异（`4c564836…/7fc515ef…`
  为中间 git blob，最终 HEAD blob `b1cc6c55…`）经 actual git object + 实际 sha256 比对确认为**描述性差异，
  非实质不一致**；QA 与 fix 最终 HEAD 的 driver/config/overlay **substance 一致**。**无 STOP。**
- fixtures：tracked 内容（`initial/`、`reference/`、`acceptance.py`、`seed.sha256`）clean 且与 fix 一致；
  `seed.git/` 为 `.gitignore` 显式排除的**可确定性再生**运行时 seed 对象库（fixed author/committer/date），
  其 `seed.sha256` pin 一致、实际 commit SHA 相同，故非实质差异。✅

### 2.3 phase/RUNS/EVIDENCE 实际指向 cohort2（非旧 root）

`--freeze-identity` 实测（rc=0）：

| 项 | 实际值 |
|---|---|
| `phaseRoot` | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`（**唯一正式 root**，`phaseRoot_exists=False`） |
| `ledgerPath` | `<phaseRoot>/generation/generation.jsonl` |
| `RUNS_DIR` | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/runs` |
| `EVIDENCE_DIR` | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/evidence`（`outputRoot_exists=False`） |
| `attempt_ids` | `['s1_units__A','s1_units__B','s2_pipeline__A','s2_pipeline__B']` |
| `total_limit` / `attempt_limit` | `192` / `48` |
| `source_tree` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` |
| mode_polarity | A=explicit False（program-scheduler/autonomous_pool off）；B=explicit True（candidate-pool on） |

- **不指** METHOD-FINAL（`lg032-method-final-data`）/ FINAL-COHORT / cohort-ready 旧 root。✅
- 入口内 assert：`C.PHASE_DATA_DIR == FORMAL_PHASE_DATA_DIR`、`C.RUNS_DIR == FORMAL_RUNS_DIR`、
  `C.EVIDENCE_DIR == FORMAL_EVIDENCE_DIR`。✅

### 2.4 `--freeze-identity` / `--help` 无副作用（无 runtime/任务/forward/Root 写）

- `--freeze-identity` rc=0、`--help` rc=0，均**不打印** credential/env/secret 值（打印
  `<not printed; read from env DEEPSEEK_API_KEY>`）。✅
- 两次只读运行**前后**：`lg032-cohort2-data` 与 `lg032-cohort2-formal` 均 **ABSENT**；`git status` 不变
  （仅原 3 未跟踪，commit 后 clean）。无 runtime / 无 Task / 无 proxy / 无 model forward / 无 Root 写。✅

## 3. mode 协议（代码级只读确认，与 SERIAL-R1 一致）

- `run_attempt.py:588` `_set_mode(settings, arm)`：经产品受控 `ConnectionService.update_settings` **每 attempt
  显式写** A=`False` / B=`True`（build 前），消除 shared `settings.data_dir` 的跨 attempt 继承。✅
- `run_attempt.py:630` `_assert_active_mode(settings, dispatcher, arm)`：真 `build_runtime` 后读**实际**
  dispatcher `_autonomous_claim` / `_autonomous_pool` / `_decentralized_enabled()` + 三持久开关；不一致
  `SystemExit`（fail-closed，且断言在 uvicorn/Task/forward 之前）。✅
- `run_attempt.py:882`（`finally`）`_safe_restore_mode`：恢复 off，`restored_off` 记录。✅
- attempt-id gate：`RUNS_DIR/<id>` 存在即拒（`refusing to overwrite existing attempt output`）。✅

## 4. 边界与保全

- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；旧 cohort1 87 字节与旧报告**逐字节保留**。
- 未 nested proxy / push / deploy / publish / main write；未碰 `8123` 或他包进程。
- 未改产品源（tree `55e4de56…`）；未改 driver/overlay 任何字节；本核查仅新增 `ENTRY-AUDIT.md` 并只读。
- 0 real provider；正式 root / 输出 root 未创建。

## 5. 判定

**PASS ⇒ 允许按 PM 授权执行正式 cohort2 的 4 attempt**（s1A→s1B→s2A→s2B，各唯一一次）。
无 FAIL、无 STOP 条件（无 harness/装配/mode/计量/协议 hash/未知写副作用错误）。

## 6. 修订历史

- 2026-10-16（真实 provider=0）：保全 3 entry 文件（commit `05de3c9`）；独立核查入口加载链 / driver-overlay
  bytes 与 actual git object / phase 指向 / 只读无副作用。**PASS，无 STOP。**
