---
title: "LG-032 COHORT2 正式入口 runner 补齐（ENTRY-REPORT 初版）"
doc_type: report
category: engineering
status: "初版：新增 cohort2 正式入口 run_formal.py（最小加载已验收 mode_config.install() + 复用同一 run_attempt）+ 只读 --freeze-identity；0 real provider；正式 root 未创建；032 NOT done；no merge"
experiment_id: lg032-cohort2-formal-entry-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "ec69eff"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 serial 方法 QA owner）"
---

# LG-032 COHORT2 正式入口 runner 补齐（ENTRY-REPORT 初版）

> 补齐 `REPORT-SERIAL-R1.md` §5/§8 记录的唯一缺口：**cohort2 正式入口 runner**。
> **0 real provider**。产品源 / 现有 driver / overlay 只读。本包只新增
> `probes/lg032/COHORT2-QA/run_formal.py` 与 `ENTRY-REPORT.md`（后续另加 `COHORT2-FORMAL-FREEZE.md`）。
> **不 mark 032 done、不 main merge、不 push/deploy/publish。**

## 0. 目标与边界（初版记录）

- 缺口（唯一）：`REPORT-SERIAL-R1.md` §5/§8 门 4 PARTIAL —— 修复包提供 cohort2 overlay
  （`MODE-ISOLATION/mode_config.py`），但**无 cohort2 正式入口 runner**；直接旧 `harness/run_attempt.py`
  会用冻结的 cohort-ready root，**不会**加载 cohort2 overlay。
- 本包补齐：新增 `probes/lg032/COHORT2-QA/run_formal.py`，**最小加载已验收的 cohort2
  `mode_config.install()`**，再调用**同一个已验收** `run_attempt`（不复制逻辑、不改策略）。
- 冻结**唯一实际 root** `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`；
  正式 `runs`/`evidence` 落在**新的独立 cohort2 formal 输出目录**（不是 METHOD-FINAL / FINAL-COHORT）。
- 四 `sample__arm` IDs 各一次、存在即拒；sample/seed/caps/model/契约全同；产品 harness 逻辑不改。
- `--freeze-identity`：在任何 runtime / Task / 模型 / 正式 root 创建**之前**只读打印非敏感配置身份。

## 1. 身份核对（初版）

| 项 | 值 |
|---|---|
| QA worktree / branch | `lg032-cohort2-qa` / `qa/lg032-cohort2`@`ec69eff` |
| 产品 tree | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f`（只读，未改） |
| driver `run_attempt.py` sha256 | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208`（只读） |
| overlay `mode_config.py` sha256 | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf`（只读） |
| seed SHA s1 / s2 | `53458ac7…` / `6fa0fd00…`（与冻结一致） |
| 正式 root | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`（**未创建**） |
| 预算 | 4 attempt × 48 = 192；已知 032 请求上限 279（旧 invalid 87 单列） |

## 2. 结果（本版已落）

### 2.1 新增入口（只读驱动，不复制逻辑）

- 入口 `probes/lg032/COHORT2-QA/run_formal.py`，sha256
  `a7477753d4b016ad2ac8a9e68d1b749b5583ff20fc53a9d8f30bb0ac8c763040`。
- 流程：**先** 最小加载已验收 cohort2 overlay（`probes/lg032/MODE-ISOLATION/mode_config.py::install()`，
  sha256 `df565291…`，只 redirect 路径常量），**再** 调用**同一个已验收** `run_attempt.run_attempt(..., dry_run=False)`。
  不复制 driver 逻辑、不改新核心 driver 策略、不切供应商。
- 入口局部仅：把 harness/fixtures 指向本 worktree（driver 字节与 fix worktree 逐字节同；fixtures 已含冻结
  seed repo），并把输出重定向到独立 cohort2-formal 目录。**未编辑任何 driver / overlay 字节。**
- 冻结唯一实际 root `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`；
  独立正式 runs/evidence：
  - `RUNS_DIR` = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/runs`
  - `EVIDENCE_DIR` = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/evidence`
  （**非** METHOD-FINAL / FINAL-COHORT；连 root 一起未创建。）
- 四 `sample__arm` IDs 各一次、存在即拒（driver 内既有 gate）；sample/seed/caps/model/契约全同。

### 2.2 只读验证（root 前后均不存在）

- `--freeze-identity` rc=0：在任何 runtime / proxy / Task / 模型 / 正式 root 创建之前打印
  phaseRoot / ledgerPath / RUNS_DIR / EVIDENCE_DIR / driver+overlay+entry sha / 四 attempt IDs /
  192 / 48 / source tree `55e4de56…` / mode polarity；**不打印 credential/env/secrets 值**。
- `--help` rc=0。
- `lg032-cohort2-data` 与 `lg032-cohort2-formal` 在 identity 与 help 运行**前后均 ABSENT**（未创建）。
- 未发送任何真实 provider 请求；未创建 0-fake 新链；旧 serial QA 门 1/2/3 有效不重复。

### 2.3 正式命令 / 冻结文档

- 冻结候选：`probes/lg032/COHORT2-QA/COHORT2-FORMAL-FREEZE.md`（引用 SERIAL-R1 §5/§8 + 新身份验证）。
- 正式 4 条绝对入口命令与 cwd（四条同 cwd = QA worktree）见 FREEZE §6；controlled env key 仅
  `DEEPSEEK_API_KEY`，**secret 值绝不入文档**。
- 预算：cohort2 **4 × 48 / 总 192**；旧 invalid **87 单列**；已知 032 请求上限 **279**；
  实际 model calls / tokens **unknown**（**不记 0**）；shared pi QA 成本不记 0；开关 **默认 off**。
- 由 PM 另派 **formal owner 独立审核 entry/config 后**执行正式采样。

### 2.4 边界确认

- 产品源 tree `55e4de56…` 未改；现有 driver / overlay 只读；旧 reports 逐字节保留。
- 未创建正式 root / 独立输出 root；未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名。
- 未 mark 032 done / 未 formal / 未 main merge / 未 push/deploy/publish。
- 本包 pi 开发/QA 成本 = **unknown**（不记 0）。

## 3. 修订历史

- 2026-10-16（初版）：记录缺口、目标、边界与身份。
- 2026-10-16（本版）：落 `run_formal.py` 并实跑只读 `--freeze-identity` / `--help`（root 前后 ABSENT）；
  写 `COHORT2-FORMAL-FREEZE.md`；补结果 / sha / 原件路径 / root 未创建确认。**不采样 / 不 done / 不 merge。**
