---
title: "LG-032 COHORT3 正式采样冻结候选（入口目录装配返修后）"
doc_type: freeze
category: engineering
status: "CANDIDATE-freeze；待独立新 formal context 审核 entry/实际 prepare/无 attempt 产物后再 conditional 冻结；formal NOT run；pattern root 未创建；032 still in-progress；real provider 0"
experiment_id: lg032-cohort3-formal-entry-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "08d6d43"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-entry（入口目录装配最小返修 owner）"
---

# LG-032 COHORT3 正式采样冻结候选

> 本文件是 COHORT3 正式采样的**冻结候选**：入口目录装配缺陷已最小返修并预检（`REPORT-DIR-FIX.md`）。
> 它本身**不跑正式采样、不占正式预算、不 mark 032 done、不 merge main**。正式执行须由 PM 另派
> **formal owner**，在**独立新 formal context 审核** entry / 实际 prepare / 无 attempt 产物通过后，
> **conditional 执行**。**真实 provider 生成 = 0**。旧报告/旧成本逐字节保留。

## 0. 结论

- COHORT2 STOP 的唯一根因（evidence 父目录缺失）已最小返修：新入口新增 `prepare_output_roots()`。
- `--prepare-only` 调用**同一** prepare 函数，已在全新根预检通过（`runs`/`evidence` 700 空目录、
  phaseRoot 仍 ABSENT、四 attemptID 不存在）；负例（软链/既有产物）均被拒。
- **建议 formal owner 独立审核 entry/config 后**，由 PM 授权正式 `2 sample × A/B × 1 = 4 attempt`
  串行采样（每 attempt 48，总 192）。**032 仍 in-progress；不 mark done；不 merge。**

## 1. 入口身份与只读验证

| 项 | 值 |
|---|---|
| 入口 | `probes/lg032/COHORT3/run_formal.py` |
| 入口 sha256 | `3efff40668ea73728e01037c718bc1c2b4b8e8d30c5373afb23b8e737de954cd` |
| overlay sha256 | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf`（`MODE-ISOLATION/mode_config.py`，只读） |
| driver sha256 | `run_attempt.py` `503a807f…` / `final_cohort_config.py` `a04a8f30…`（只读，字节同 cohort2-qa） |
| 产品 tree | `55e4de56…`（`git rev-parse HEAD:backend/lightgravity`，只读） |
| SDK / 契约 / 模型 | `0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` |

**`--freeze-identity` 行为**：在任何 runtime / proxy / Task / 模型 / 输出 root 创建之前，只读打印
phaseRoot / ledgerPath / RUNS_DIR / EVIDENCE_DIR / driver+overlay+entry sha / 四 attemptID / 192 / 48 /
source tree / mode polarity；**不打印 credential/env/secrets 值**；**不创建任何目录**。实跑前后
`lg032-cohort3-data` 与 `lg032-cohort3-formal` 均按状态如实反映（identity 前 ABSENT）。`--help` rc=0 且不写目录。

## 2. 唯一实际 phase data_root（贯穿 4 attempt）

- **正式 phase root（冻结候选）** = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data`
  （**尚未创建**；`--prepare-only` 报告 `phase_data_dir_exists=False`）。
- 入口加载已验收 `mode_config.install()`，只 **redirect 路径常量**，不改核心 driver 策略；产品
  `bootstrap.configure_generation_ledger` 与驱动 env pin **同指一目录**；物理 ledger
  `<root>/generation/generation.jsonl` 跨 runtime 累加不归零。
- **该 root 由 driver 在真实 attempt 内创建**（本包不预先创建 phaseRoot）。

## 3. 独立 COHORT3 正式 runs/evidence（**非** cohort2-formal / METHOD-FINAL / FINAL-COHORT）

| 项 | 绝对路径 |
|---|---|
| RUNS_DIR | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal/runs` |
| EVIDENCE_DIR | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal/evidence` |

- 新目录（mode `700`），`--prepare-only` 已在**全新根**预创建，**独立于** cohort2-formal /
  METHOD-FINAL / FINAL-COHORT / cohort-ready 输出。
- **约定「outputroot 预创建合法」**：正式采样开始时 output root + `runs` + `evidence` 已存在（700、空）。
- **四 attemptIDs / runs/<id> / result.json / ledger / task 不得存在**（prepare 后实测不存在）；
  driver 内既有 gate：任一 `runs/<id>/` 已存在 ⇒ 拒跑。
- 旧 cohort1 87、旧 cohort2 19、旧 METHOD-FINAL/cohort-ready/023/022/LG-031 输出**逐字节保留**。

## 4. 固定 4 attempt IDs（不可变，存在即拒）

| # | attempt id | sample | arm |
|---|---|---|---|
| 1 | `s1_units__A` | s1_units | A |
| 2 | `s1_units__B` | s1_units | B |
| 3 | `s2_pipeline__A` | s2_pipeline | A |
| 4 | `s2_pipeline__B` | s2_pipeline | B |

## 5. 正式命令（由 PM 另派 formal owner 执行，独立审核 entry/config 之后）

**cwd（四条同）**：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry`

```bash
# 绝对入口；每个 attempt 只跑一次（attempt id 存在即拒）。
# 入口在真实 attempt 前调用同一 prepare_output_roots()，保证 evidence 父目录存在。
# secret 只从 env 读取，值绝不写入本文档 / 命令之外的任何文件。
DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry/probes/lg032/COHORT3/run_formal.py \
  --sample s1_units --arm A

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry/probes/lg032/COHORT3/run_formal.py \
  --sample s1_units --arm B

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry/probes/lg032/COHORT3/run_formal.py \
  --sample s2_pipeline --arm A

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry/probes/lg032/COHORT3/run_formal.py \
  --sample s2_pipeline --arm B
```

> controlled env key 仅 `DEEPSEEK_API_KEY`（secret，**值绝不入文档**）。正式入口加载 cohort3 overlay 后
> 调用同一 `run_attempt.run_attempt(..., dry_run=False)`：不复制逻辑、不改策略、不切供应商。
> 后续正式路径同已冻结路径，**不走别 helper**。

## 6. 预算（冻结候选；before 正式新调用再冻）

- per-attempt **48** / total **192**（4 × 48），均在“转发前”硬拒（429，ledger 不增）。
- **旧 invalid 106 永久单列** = cohort1 87（mode-invalid）+ cohort2 19（entry FileNotFound）。**不洗、不补
  attempt、不假装 validAB、不归零。**
- **032 已知请求上限 = 旧 106 + 新 192 = 298**。
- 旧 LG-031 86、旧 023（cohort1 45 / cohort2 4 / cohort3 16）、023 eval 65、core **unknown**，
  全部单列不清零。
- **补遗纠正**：旧 COHORT2 报告「剩余 144」不精确；32 位口径下属 cohort2 未执行剩余应为
  **192−19 = 173**。仅在 `REPORT-DIR-FIX.md` §7 补遗纠正，原历史报告逐字节保留。
- **本 owner pi 开发/QA 成本 = unknown**（**不记 0**，不预设省 token）。shared pi QA 成本 **不记 0**。
- `output ≤ 16000` tokens / `HTTP timeout 120s` / `SDK retries 0` / concurrency 1 /
  worker ≤12 model / ≤32 tool / reviewer ≤1 / 每 attempt ≤1 business repair；两 arm 相同。
- 开关 **默认 off**；仅 arm B 在 attempt 内显式开启（唯一自变量）。same 4 sample/arm、seed、3 plan、
  48 cap 等其余协议**不改**。

## 7. 正/负边界

- 本包 **0 real provider**（未 build_runtime / Task / proxy / SDK，未发任何真实 provider 请求）；**mode 未运行**；无新 fake/real。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名；旧 raw/Run/ledger/report/worktree 未删改。
- 未 nested proxy / push / deploy / publish / main write；未动 `8123` 或他包进程。
- 未改产品源（tree `55e4de56…`）；未改任何现有 driver / overlay / 旧 entry 字节；旧 reports 逐字节保留。
- 未 mark 032 done / 未 formal / 未 main merge。**待独立新 formal context 审核后 conditional 执行。**

## 8. 修订历史

- 2026-10-16（真实 provider=0）：COHORT3 入口目录装配最小返修 + `--prepare-only` 预检；写本冻结候选。
  **不执行正式采样、不 mark 032 done、不 merge。**
