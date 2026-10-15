---
title: "LG-032 COHORT2 正式采样冻结（补齐 cohort2 正式入口 runner 后）"
doc_type: freeze
category: engineering
status: "RECOMMEND-READY-for-formal-4-attempt（cohort2 正式入口已补齐并只读验证）；formal NOT run；正式 root 未创建；032 still in-progress；real provider 0"
experiment_id: lg032-cohort2-formal-entry-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "ec69eff"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 serial 方法 QA owner）"
---

# LG-032 COHORT2 正式采样冻结（cohort2 正式入口补齐后）

> 本文件补齐 `COHORT2-QA/REPORT-SERIAL-R1.md` §5/§8 记录的**唯一缺口**：cohort2 正式入口 runner。
> 它本身**不跑正式采样、不占用正式预算、不 mark 032 done、不 merge main**。
> 正式命令由 PM 另派 **formal owner** 执行（独立审核 entry/config 后）。**真实 provider 生成 = 0**。
> 旧报告逐字节保留；本包只新增 `probes/lg032/COHORT2-QA/{run_formal.py,ENTRY-REPORT.md,COHORT2-FORMAL-FREEZE.md}`。

## 0. 结论

- SERIAL-R1 门 1/2/3 PASS；门 4 PARTIAL 的缺口**已补齐**：新增 cohort2 正式入口
  `probes/lg032/COHORT2-QA/run_formal.py`（最小加载已验收 cohort2 overlay + 复用同一 `run_attempt`）。
- **只读验证 PASS**：`--freeze-identity` 与 `--help` 均正常；**正式 root 与独立输出 root 前后均不存在**。
- **建议 formal owner 独立审核 entry/config 后**，由 PM 授权正式 `2 sample × A/B × 1 = 4 attempt` 串行采样
  （每 attempt 48，总 192）。**032 仍 in-progress；不 mark done；不 merge。**

## 1. 引用与前置（SERIAL-R1）

- `REPORT-SERIAL-R1.md` §5 记录：修复包提供 cohort2 overlay（`MODE-ISOLATION/mode_config.py`），
  但**无正式入口 runner**；直接旧 `harness/run_attempt.py` 会用冻结的 cohort-ready root。
- §8 推荐：补齐并冻结 cohort2 正式入口 runner 后，方可由 PM 另派执行正式 4 attempt。
- **本文件即该补齐 + 冻结**；不含正式采样结果。

## 2. 新入口身份与验证（只读）

| 项 | 值 |
|---|---|
| 入口 | `probes/lg032/COHORT2-QA/run_formal.py` |
| 入口 sha256 | `a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040` |
| overlay sha256 | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf`（`MODE-ISOLATION/mode_config.py`，只读） |
| driver sha256 | `run_attempt.py` `503a807f…` / `final_cohort_config.py` `a04a8f30…`（与 fix worktree 逐字节同，只读） |
| fixture seed SHA | s1 `53458ac7…` / s2 `6fa0fd00…`（与冻结一致） |
| 产品 tree | `55e4de56…`（`git rev-parse HEAD:backend/lightgravity`，只读） |
| SDK / 契约 / 模型 | `0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` |

**`--freeze-identity` 行为**：在**任何 runtime / proxy / Task / 模型 / 正式 root 创建之前**，只读打印
phaseRoot / ledgerPath / RUNS_DIR / EVIDENCE_DIR / driver+overlay+entry sha / 四 attempt IDs /
192 / 48 / source tree / mode polarity；**不打印 credential/env/secrets 值**。实跑前后
`lg032-cohort2-data` 与 `lg032-cohort2-formal` 均 **ABSENT**（未创建）。`--help` rc=0。

## 3. 唯一实际 phase data_root（贯穿 4 attempt）

- **正式 phase root（冻结）** = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`
  （**尚未创建**；`--freeze-identity` 报告 `phaseRoot_exists=False`）。
- 入口加载已验收 `mode_config.install()`，只 **redirect 路径常量**，不改新核心 driver 策略；
  入口局部把 harness/fixtures 指向本 worktree（driver 字节与 fix worktree 逐字节同，
  fixtures 已含冻结 seed repo），并把输出重定向到独立 cohort2-formal 目录。
- 所有 4 attempt 共用该唯一 `settings.data_dir`；产品 `bootstrap.configure_generation_ledger`
  与驱动 env pin **同指一目录**；物理 ledger `<root>/generation/generation.jsonl` 跨 runtime 累加不归零。

## 4. 独立 cohort2 正式 runs/evidence（**非** METHOD-FINAL / FINAL-COHORT）

| 项 | 绝对路径 |
|---|---|
| RUNS_DIR | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/runs` |
| EVIDENCE_DIR | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/evidence` |

- 新目录，**独立于** METHOD-FINAL / FINAL-COHORT / cohort-ready 输出；连 root 一起 `outputRoot_exists=False`。
- attempt id 存在即拒（driver 内既有 gate）：任一 `runs/<id>/` 或固定 4 ID 已存在 ⇒ 拒跑。
- 旧 cohort1 87、旧 METHOD-FINAL/cohort-ready/023/022/LG-031 输出**逐字节保留**。

## 5. 固定 4 attempt IDs（不可变，存在即拒）

| # | attempt id | sample | arm |
|---|---|---|---|
| 1 | `s1_units__A` | s1_units | A |
| 2 | `s1_units__B` | s1_units | B |
| 3 | `s2_pipeline__A` | s2_pipeline | A |
| 4 | `s2_pipeline__B` | s2_pipeline | B |

## 6. 正式命令（由 PM 另派 formal owner 执行，独立审核 entry/config 之后）

**cwd（四条同）**：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa`

```bash
# 绝对入口；每个 attempt 只跑一次（attempt id 存在即拒）。
# secret 只从 env 读取，值绝不写入本文档 / 命令之外的任何文件。
DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/probes/lg032/COHORT2-QA/run_formal.py \
  --sample s1_units --arm A

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/probes/lg032/COHORT2-QA/run_formal.py \
  --sample s1_units --arm B

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/probes/lg032/COHORT2-QA/run_formal.py \
  --sample s2_pipeline --arm A

DEEPSEEK_API_KEY=<env-secret> \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/.venv/bin/python \
  /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa/probes/lg032/COHORT2-QA/run_formal.py \
  --sample s2_pipeline --arm B
```

> controlled env key 仅 `DEEPSEEK_API_KEY`（secret，**值绝不入文档**）。正式入口加载 cohort2 overlay 后
> 调用同一 `run_attempt.run_attempt(..., dry_run=False)`：不复制逻辑、不改策略、不切供应商。
> 后续正式路径同已冻结路径，**不走别 helper**。

## 7. 预算（冻结，before 正式新调用）

- per-attempt **48** / total **192**（4 × 48），均在“转发前”硬拒（429，ledger 不增）。
- **旧 invalid 87 单列**（旧 cohort1 = 21+26+19+21，判 AB invalid，不洗不归零）。
- **已知 032 请求上限 = 旧 87 + 新 192 = 279**。
- 旧 LG-031 86、旧 023（cohort1 45 / cohort2 4 / cohort3 16）、023 eval 65、core **unknown**，
  全部单列不清零。
- **本次补入口的 pi 开发/QA 成本 = unknown**（**不记 0**，不预设省 token）。实际 model calls/tokens
  未知；shared pi QA 成本 **不记 0**。
- `output ≤ 16000` tokens / `HTTP timeout 120s` / `SDK retries 0` / concurrency 1 /
  worker ≤12 model / ≤32 tool / reviewer ≤1 / 每 attempt ≤1 business repair；两 arm 相同。
- 开关 **默认 off**；仅 arm B 在 attempt 内显式开启（唯一自变量）。

## 8. 正/负边界

- 本包 **0 real provider**（未发送任何真实 provider 请求）；未创建正式 root / 独立输出 root。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名；私有原件 600。
- 未 nested proxy / push / deploy / publish / main write；未动 `8123` 或他包进程。
- 未改产品源（tree `55e4de56…`）；未改任何现有 driver / overlay 字节；旧 reports 逐字节保留。
- 未 mark 032 done / 未 formal / 未 main merge。formal owner 独立审核 entry/config 后执行。

## 9. 修订历史

- 2026-10-16（真实 provider=0）：补齐 cohort2 正式入口 `run_formal.py` 并只读验证（`--freeze-identity`
  与 `--help`，root 前后 absent）；写入本冻结候选。**不执行正式采样、不 mark 032 done、不 merge。**
