---
title: "LG-032 COHORT3 独立入口验收（阶段 0，0 real provider）— FAIL（不可用于完整四次顺序）"
doc_type: audit
category: engineering
status: "INDEPENDENT-AUDIT FAIL — entry prepare helper refuses any pre-existing frozen attempt id ⇒ full 4-attempt sequential chain cannot run; 0 model; STOP; no self-fix; hand to PM"
experiment_id: lg032-cohort3-entry-independent-audit-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "fb261d8"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-independent-audit（独立入口验收 owner；非产品/driver/entry 作者；0 real provider）"
---

# LG-032 COHORT3 独立入口验收（阶段 0）

> 独立于入口作者的新 `pi` context。**0 real provider**（未 build_runtime / Task / proxy / SDK；未发任何真实
> provider 请求；未加载/运行 model）。**未自修任何代码**。所有合成验证只在独立 nonce scratch（700）进行，
> **绝不**写正式 attempt id / 正式 output root / phase data root。旧报告/旧成本逐字节保留。

## 0. 结论（先给判断）

- **阶段 0 独立入口门 = FAIL。** 原因**唯一且确定性**：新入口新增的 `prepare_output_roots()`
  调用 `_assert_no_attempt_artifacts()`，该函数对**全部四个**冻结 attempt id **无条件**拒绝任何已存在产物
  （`probes/lg032/COHORT3/run_formal.py:172-195`）。而正式路径在**每次** attempt 前都调用同一
  `prepare_output_roots()`（`run_formal.py:468`）。
- 后果：**第 1 次 attempt（`s1_units__A`）成功后，第 2 次 attempt（`s1_units__B`）在 prepare 阶段即被拒**
  ⇒ 冻结的「2 sample × A/B × 1 = 4 attempt 顺序链」**不可能跑完**。这正是 PM 预设的失败模式：
  「不能 helper 无条件拒所有历史 attempt 导致第二次 STOP」。
- 实测复现（独立 nonce scratch，调用**同一个真实** prepare 函数，仅重定向其路径参数）：见 §3。
- 按授权：**FAIL ⇒ 0 模型、不执行任何真实 attempt、不自修代码、STOP 并把本报告交 PM 修**。
- 032 仍 in-progress；未 mark done；未 merge main；旧 cohort1 87 / cohort2 19 **未删未改未归零**。

## 1. 独立身份核（只读；sha / tree / 版本全部一致）

| 项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| worktree / cwd | `lg032-cohort3-entry` | 同 | ✅ |
| branch | `fix/lg032-cohort3-entry` | 同 | ✅ |
| HEAD | `fb261d8` | `fb261d8296663ce5a0950fc0fe085b52dafe8794` | ✅ |
| tracked diff | clean | 空（`git status --porcelain` 空） | ✅ |
| entry `run_formal.py` | `3efff406…54cd` | `3efff40668ea73728e01037c718bc1c2b4b8e8d30c5373afb23b8e737de954cd` | ✅ |
| overlay `mode_config.py` | `df565291…88bf` | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ |
| driver `run_attempt.py` | `503a807f…6208` | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ |
| driver `final_cohort_config.py` | `a04a8f30…a117` | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ |
| 旧 cohort2 入口 `COHORT2-QA/run_formal.py` | 原字节 | `a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040` | ✅ 未动 |
| 产品 tree `HEAD:backend/lightgravity` | `55e4de56…` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | ✅ |
| SDK / contract / model | `0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` | 同（`--freeze-identity` 打印） | ✅ |
| caps | total 192 / attempt 48 / worker 12 / reviewer 1 | 同（`final_cohort_config.py:59/61/70/73`） | ✅ |

- `git rev-parse HEAD:backend/lightgravity` = `55e4de56…`（与 freeze / SERIAL-R1 base 一致）。
- 入口 sha 与 `COHORT3-FORMAL-FREEZE.md` / `REPORT-DIR-FIX.md` 声明一致；driver/overlay sha 与 SERIAL-R1
  冻结一致。

## 2. mode / bootstrap / restore / 装配路径核（PASS）

- **显式 mode（A=False / B=True）**：`run_attempt.py:950` `decentralized_claim_enabled=(arm == "B")`，
  在 `build_runtime` **之前**经产品受控 `ConnectionService.update_settings` 写入（`_set_mode`，line 923-953）；
  arm A 显式写 `False`、arm B 显式写 `True`，**不继承**前次 attempt。
- **bootstrap 实际 assert**：`run_attempt.py:630` `_assert_active_mode`（line 956-1000）在真 `build_runtime`
  之后读**实际** dispatcher 对象（`_autonomous_claim` / `_autonomous_pool` / `_decentralized_enabled()`）
  与三持久开关，`is not want` 即 `SystemExit`（fail-closed；在 uvicorn/Task 之前）。
- **restore off 未变**：`run_attempt.py:882` `finally` 调 `_safe_restore_mode`（line 1010-1035），恢复
  `decentralized_claim_enabled=False` 并记 `restored_off`。
- **入口只做路径适配**：`_load_overlay_config()`（`run_formal.py:274-310`）仅重定向
  `WORKTREE/COHORT/HARNESS_DIR/MODE_DIR/RUNS_DIR/EVIDENCE_DIR/FIXTURES_DIR/PHASE_DATA_DIR/LEDGER*` 路径常量；
  **不改** model/plan/profile/tools/truth/caps/seed，不复制 driver 逻辑，不换供应商。四 attemptID 同入口加载
  cohort3 实际常量（`--freeze-identity` 打印 `ATTEMPTS` 与 192/48）。无 fake/sink/stop/root 绕过。
- 结论：mode / 装配 / 版本 / caps 层面**与冻结/SERIAL-R1 一致（PASS）**。

## 3. 关键核：prepare 函数能否承载完整四次顺序（**FAIL**）

### 3.1 代码事实（只读）

- `prepare_output_roots()`（`run_formal.py:198-274`）在开头与结尾各调用一次
  `_assert_no_attempt_artifacts()`（line 226 / 259）。
- `_assert_no_attempt_artifacts()`（line 172-195）**遍历全部四个** `ATTEMPT_IDS`，任一
  `runs/<id>/` 或 `runs/<id>/result.json` 或 `evidence/<id>.json` 存在即 `SystemExit`。
- 正式路径（`run_formal.py:468`）与 `--prepare-only`（line 393）调用**同一** `prepare_output_roots()`。
- 对照：**driver 自身**的 attempt gate 是**按当前 attempt id 范围**的（`run_attempt.py:540`
  `out_dir = C.RUNS_DIR / attempt_id`，只在该 attempt 目录已存在时拒绝）——即 driver 层**允许**顺序链，
  **仅**新入口 helper 破坏之。

### 3.2 实测复现（独立 nonce scratch；0 real provider）

- scratch：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-audit-scratch-20261015T212036Z-26a290a65b22`
  （mode `700`，唯一 nonce）。
- 方法：`importlib` 加载**真实**入口 `probes/lg032/COHORT3/run_formal.py`，**仅**把其模块级
  `FORMAL_OUTPUT_DIR/RUNS_DIR/EVIDENCE_DIR/WORKTREES_DIR` 重定向到 scratch（**非** SDK 根 / **非**核心授权）；
  调用**真实** `prepare_output_roots()` / `_assert_no_attempt_artifacts()`。**不重写、不仿制** guard。
- 合成「前一次其它 attempt 已完成」的方式**与 driver 写产物一致**：创建 `runs/<id>/result.json` +
  `evidence/<id>.json`，记录 `synthetic: true`，**绝不**写正式 id / 正式 root。

| 步骤 | 场景 | 期望 | 实测 |
|---|---|---|---|
| 1 | 空 scratch 首次 prepare | PREPARED | ✅ PREPARED，创建 output root/runs/evidence（700） |
| 2 | 幂等复跑（无 attempt 产物） | PREPARED | ✅ PREPARED，`created_now=[]` |
| 3 | **`s1_units__A` 产物已存在 → prepare 下一 attempt（`s1_units__B`）** | 应 PREPARED | ❌ **REFUSED**：`frozen attempt dir already exists …/runs/s1_units__A` |
| 4 | 前两次产物已存在 → prepare 第三次 | 应 PREPARED | ❌ REFUSED（同因，指向 `s1_units__A`） |
| 5 | 重复**当前** attempt id | 应 REFUSED 且不覆盖 | ✅ REFUSED；内容 `content_unchanged=true` |
| — | fresh EVIDENCE_DIR 真 mkdir + writeJSON | 可写 | ✅ 目录 700，`writeJSON` 成功写文件 |

- 脚本与结果 sha256：
  - `seq_prepare_test.py` = `e273c829d7137f44b5b20089f0c44f2dee099599d473c8bc872ad5dce4fb1a68`
  - `seq_prepare_test_result.json` = `40566f81d229e6c680deb3d27b8e68da4895f1871765bccf058ffedfa06ce16d`
- 结果字段：`sequential_two_distinct_attempts_possible=false`、`current_attempt_repeat_refused=true`、
  `current_attempt_content_unchanged=true`。

### 3.3 判定

- **「前一次其它 attempt id 产物已存在时，下一新 attempt 仍可准备/保存」= 不成立 ⇒ 门 FAIL。**
- 「重复当前 attempt id 必须拒绝、不覆盖」= 成立（但这是必要非充分条件）。
- 「fresh EVIDENCE_DIR 真 mkdir 且能 writeJSON」= 成立。
- 只证明「空目录 prepare」不足；本核专门验证顺序链，发现 helper **无条件拒所有历史 attempt**，
  会导致**第二次 attempt STOP**——即 PM 明示的 FAIL 判据。

## 4. 正式目录状态（证据，独立核验）

| 项 | 状态 | 判定 |
|---|---|---|
| phase data root `lg032-cohort3-data` | **ABSENT**（identity 前后均缺） | ✅ 须未创建 |
| outputRoot `lg032-cohort3-formal` | 存在，`runs/` 与 `evidence/` 均 700 **空** | ✅ 允许已 prepare 为空 700 |
| 四 attemptID / `runs/<id>` / `result.json` | **不存在** | ✅ 无 formal 产物 |
| formal `evidence/*.json` | **不存在** | ✅ |
| formal ledger / task | **不存在** | ✅ |
| 旧 cohort1 ledger | `{"count":87}` | ✅ 保留 |
| 旧 cohort2 ledger | `{"count":19}` | ✅ 保留 |
| cohort2-formal `runs/`（STOP 证据） | 保留未碰 | ✅ |
| `--help` | rc=0，不写目录 | ✅ |
| `--freeze-identity` | rc=0，只读；root 前后状态不变 | ✅ |

- scratch 内全部合成产物**仅在**独立 scratch root，**未**写正式 attempt id / 正式 root / phaseRoot。
- **0 forward / 0 real provider**：全程未 build runtime / Task / proxy / SDK，未发模型请求。

## 5. 边界与合规

- **未自修代码**：entry / driver / overlay / 产品源**零字节改动**；tracked diff 空。
- **0 real provider**；mode 未运行；无新 fake/real。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖正式产物；合成验证只在独立 nonce scratch（700）。
- 未 nested proxy / push / deploy / publish / main merge；未 mark 032 done。
- 旧 reports 逐字节保留；旧失败成本 106（cohort1 87 + cohort2 19）未删未改未归零。
- **不 routine 询问用户**：按授权 FAIL 即 STOP、保存报告、commit 退出。

## 6. 缺陷定位（交 PM 修的精确引用，非本 owner 修改）

- 文件：`probes/lg032/COHORT3/run_formal.py`
- 症状函数：`_assert_no_attempt_artifacts()`（line 172-195），被 `prepare_output_roots()`（line 226/259）调用，
  后者被正式路径（line 468）**每次** attempt 前调用。
- 根因：guard 范围 = **全部四个** attempt id，而非**当前** attempt id。修复方向（**由 PM 另派入口作者**决定，
  本 owner 不自修）：把「已存在即拒」的检查限定为**当前 attempt id**（`runs/<current>/`、`<current>.json`），
  并可选：在 cohort 起点仅校验「四 id 均不存在」一次，之后每 attempt 只校验自身。**不得**放松正式不可变性
  （重复当前 id 仍须拒、不覆盖）。
- 交付要求：修复后须重新走**独立入口验收**（含完整 4 attempt 顺序 prepare 证据）PASS 后，方可发真实模型。

## 7. 结论 / 下一步

- **阶段 0 独立入口门 = FAIL** ⇒ **0 模型、未发任何真实请求、STOP**。
- 本报告 + 证据提交（精确 commit，仅新增本报告；不含 secret/raw/正式产物）。
- **不以任何别名 bringup / 不另起 cohort / 不由本 owner 自修**；交 PM 决定返修入口后再派独立复验。
- 032 仍 in-progress；不 mark done；不 merge main。

## 8. 修订历史

- 2026-10-16（阶段 0，0 real provider）：独立入口验收核身份/mode/装配/正式目录状态 **PASS**；核
  prepare 顺序链 **FAIL**（helper 无条件拒历史 attempt ⇒ 第二次 STOP）；写本报告；STOP，不自修。
