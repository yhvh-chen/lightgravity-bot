---
title: "LG-032 COHORT3 入口 guard 极小返修（prepare 只拒当前 selected attempt）"
doc_type: report
category: engineering
status: "GUARD-FIX COMPLETE — prepare guard limited to current attempt id; synthetic nonce test 5/5; entry sha e8340f90; 0 real provider; formal NOT run; 032 in-progress; no self formal/done"
experiment_id: lg032-cohort3-entry-guard-fix-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "c4f6b55"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-entry-guard-fix（入口 guard 极小返修 owner；0 real provider）"
---

# LG-032 COHORT3 入口 guard 极小返修

> 本文件只修**一个确定缺陷**：`prepare_output_roots()` 的 `_assert_no_attempt_artifacts()` 原先
> 遍历**全部四个**冻结 attempt id，任何旧产物存在即拒绝，导致第 2 个 attempt 在 prepare 阶段不可能
> 运行（独立入口验收 `ENTRY-INDEPENDENT-AUDIT.md` 已据此判 FAIL）。**0 real provider**：未 build
> runtime / Task / proxy / SDK，未发任何模型请求。旧报告/旧成本逐字节保留。

## 0. 结论

- **根因**：guard 范围 = 全部四个 attempt id，而非**当前 selected** attempt id。正式路径每次 attempt
  前都调用同一 `prepare_output_roots()`，故第 1 次 `s1_units__A` 成功后，第 2 次 `s1_units__B` 必被拒。
- **修复**：`_assert_no_attempt_artifacts(current_attempt_id)` / `prepare_output_roots(current_attempt_id)`
  仅对**当前** attempt id 检查其 `runs/<id>/`、`result.json`、`evidence/<id>.json`；**其它**既定
  attempt 产物原样保留、继续下一个 ID；重复**当前** ID 仍拒且不覆盖。
- `--prepare-only` 传 `current_attempt_id=None`：只创建/核根，**不**检查、**不**触碰任何历史文件，幂等。
- 正式 driver 自身的 attempt gate（`run_attempt.py:540`）本就按当前 attempt id，未改；budget / model /
  mode / driver / overlay / stop / product 全未改。
- 合成测试（独立 nonce scratch，700，调用**真实** prepare/guard 函数，仅重定向受控路径）**5/5 通过**。

## 1. 最小 diff（唯一改动文件）

- 文件：`probes/lg032/COHORT3/run_formal.py`
- 变更：`_assert_no_attempt_artifacts(current_attempt_id: str | None = None)` 收窄守卫范围；
  `prepare_output_roots(current_attempt_id=None)` 透传；`normal` 路径由合法 CLI choices 组装
  `current_attempt_id = f"{args.sample}__{args.arm}"` 传入；`--prepare-only` 显式传 `None`；
  prepare 记录字段 `attempt_ids_absent` → `current_attempt_id` / `current_attempt_absent`；docstring 同步。
- 未新增抽象、未重写入口、未改路径守卫 `_assert_controlled` / symlink / pathscope / permissions /
  mkdir 验证。

## 2. 身份核（只读）

| 项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| branch | `fix/lg032-cohort3-entry` | 同 | ✅ |
| base HEAD | `c4f6b55` | 同 | ✅ |
| entry sha256（修复后） | 新 | `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2` | ✅ |
| overlay `mode_config.py` | `df565291…` | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ 未改 |
| driver `run_attempt.py` | `503a807f…` | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ 未改 |
| driver `final_cohort_config.py` | `a04a8f30…` | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ 未改 |
| 产品 tree `HEAD:backend/lightgravity` | `55e4de56…` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | ✅ 未改 |
| caps | total 192 / attempt 48 | 192 / 48 | ✅ 不变 |
| diff 范围 | 仅入口 | `git diff --name-only` = `run_formal.py` | ✅ |

## 3. 合成测试（独立 nonce scratch；0 real provider）

- 方法：`importlib` 加载**真实**入口 `run_formal.py`，**仅**重定向其模块级受控路径
  （`FORMAL_OUTPUT_DIR/RUNS_DIR/EVIDENCE_DIR/PHASE_DATA_DIR` 与 sanctioned parent `WORKTREES_DIR`）到
  全新 nonce scratch（`/tmp/lg032-guard-synth-*`，700）；调用**真实** `prepare_output_roots()` /
  `_assert_no_attempt_artifacts()`；**不重写、不仿制** guard。合成 attempt 产物标记 `synthetic: true`，
  **绝不**写正式 attempt id / 正式 root / phase data root。

| # | 场景 | 期望 | 实测 |
|---|---|---|---|
| 1 | fresh scratch：`prepare(current=s1_units__A)` + 真 mkdir + writeJSON | PREPARED、700、可写 | ✅ prepared；runs/evidence 700；write JSON OK；phaseRoot ABSENT |
| 2 | 同根**前一个 otherID**（`s1_units__A`）产物存在 → 准备 nextID（`s1_units__B`） | 允许 | ✅ prepared；`s1_units__A` result/evidence sha256 **不变** |
| 3 | 重复**当前** `s1_units__B` | 拒且不覆盖 | ✅ REFUSED（`attempt dir already exists`）；当前 bytes **不变** |
| 4 | `runs/` 为指向 root 外目录的 symlink | 拒 | ✅ REFUSED（`must not traverse a symlink`） |
| 5 | `--prepare-only`（`current_attempt_id=None`）连跑两次 | 幂等、refuse nothing、不覆盖 | ✅ prepared×2、`created_now=[]`、历史 result/evidence bytes **不变** |

- 结果字段：`all_ok=true`；`real_generation=0`；`entry_sha256=e8340f90…`。
- 合成脚本 `sha256 = 3cd2433409abd22ba3e62c1d72e680aacc4e9d5edb84f7f64f0cccc1bfb900d6`；结果 `sha256 = 5a8b7b0ac443190806ba1ecff89b2f9aefa8c07c2fd03dd3baebbaa9f8a4d91b`；路径均为 `/tmp/lg032-guard-synth-*`（脱敏，非正式 ID/root）。

## 4. 正式目录状态（证据）

| 项 | 状态 | 判定 |
|---|---|---|
| phase data root `lg032-cohort3-data` | **ABSENT**（`--prepare-only`/identity 前后均缺） | ✅ 未创建 |
| outputRoot `lg032-cohort3-formal` | 存在，`runs/` 与 `evidence/` 均 700 **空** | ✅ |
| 四 attemptID / `result.json` / `evidence/*.json` | 不存在 | ✅ 无 formal 产物 |
| 旧 cohort2 ledger | `{"count":19}` 保留 | ✅ |
| 旧 cohort1（87）/ cohort2 reports、cohort2-formal runs | 未删未改未覆盖 | ✅ |
| `--help` / `--freeze-identity` / `--prepare-only` | rc=0；只读或幂等；root 状态不变 | ✅ |

- 旧 cohort1 87 + cohort2 19 = **106 协议失败成本保留**；cohort3 预算 192/48/298 不变，**不再额外 cohort**。

## 5. 边界与合规

- **只修一个确定缺陷**（guard 范围）；未改 budget / model / mode / driver / overlay / stop / product，
  未改 symlink / pathscope / permissions / mkdir 验证，未新增抽象，未重写入口。
- **0 real provider**：未 build runtime / Task / proxy / SDK，未发模型请求，未加载 model。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖任何正式或旧产物；合成验证只在 nonce scratch。
- 未 nested proxy / push / deploy / publish / main merge；未 mark 032 done；未自 formal。
- 旧 report 逐字节保留。

## 6. 结论 / 下一步

- guard 缺陷已最小修复并通过合成顺序链验证 ⇒ **交独立入口复验**（须含完整 4 attempt 顺序 prepare 证据）
  PASS 后，方可由 PM 派 formal owner 发真实模型。
- **032 仍 in-progress；不 mark done；不 merge main。**

## 7. 修订历史

- 2026-10-16（0 real provider）：guard 收窄至当前 attempt id；合成 nonce 5 例通过；写本报告 + 新 freeze
  补遗；精确 commit 入口 diff + 本报告；clean 退出。
