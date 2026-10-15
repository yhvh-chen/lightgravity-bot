---
title: "LG-032 FINAL-COHORT 证据保全事故记录（PRESERVATION-INCIDENT）"
doc_type: incident
category: engineering
status: "RECORDED / NO-RECOVERY-ASSERTED"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（续接 owner；非 031 实施者；主代理仅 PM）"
related_logs:
  - "/home/yhvh/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-c2n9sveo.log"
  - "/home/yhvh/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-i_g6y60q.log"
---

# LG-032 FINAL-COHORT — 证据保全事故记录

> 本文**只记录事实**：前 owner 的删除动作、被删对象、仍存活的证据、以及**明确 missing 且不伪造恢复**。
> 不输出任何 secret / grant / header / 凭证。删除动作**不得再次发生**（见 §6 硬禁令）。

## 1. 事故摘要

- 前 owner（wrapperPID `2455191`）在 `2026-10-16 06:54:26 → 06:57:54`（elapsed ≈212s）的 pi bounded 运行
  （log `lightgravity-pi-bounded-c2n9sveo.log`）中，为调试 dry-run driver，**反复执行**
  `rm -rf ../lg032-final-cohort-data-dry`，随后由 driver 重建该根。
- 该命令**删除了整个 dry 根**（不是单个文件），因此**每一次删除都销毁了当时已累积的全部 dry attempt 输出**
  （上一轮 `offline_dry_run_output/`、`attempts/<id>/`、dry `generation/` 账本、当轮 SDK 会话残留等）。
- 随后 PM 对该 wrapper 发送精确 `SIGINT`（PID `2455191`），进程 `exit 143`，**本事故由此中止**。
- 性质：**违反“保留原件 / 不删旧 attempt 输出”规则**；与 031 实施无关；**正式 032 真实生成仍为 0**。

## 2. 删除动作精确定位（依据前两完整日志）

在 `lightgravity-pi-bounded-c2n9sveo.log` 中，命令文本 `rm -rf ../lg032-final-cohort-data-dry` 共出现于
**4 个不同的 `bash` toolCall**（其余出现是同一次调用的重复事件记录，不是新删除）：

| # | toolCallId（截断） | 所在 turn | 命令 | 删除对象 |
|---|---|---|---|---|
| 1 | `call_00_GzXWBwr…6361` | 64 | `rm -rf ../lg032-final-cohort-data-dry && timeout 300 …` | 整个 dry 根（重建后跑一轮 dry driver，`RC 1`，fake 被命中 3 次） |
| 2 | `call_00_ruURtQx…1690` | 67 | `rm -rf ../lg032-final-cohort-data-dry && timeout 300 …` | 整个 dry 根（重建后加 `_forward` monkeypatch 调试） |
| 3 | `call_00_8OXTKdQ6…1044` | 68 | `rm -rf ../lg032-final-cohort-data-dry && timeout 300 …` | 整个 dry 根（重建后仅测 import） |
| 4 | `call_00_lDvLe7u4…3714` | 70 | `rm -rf ../lg032-final-cohort-data-dry && timeout 300 …` | 整个 dry 根（重建后 monkeypatch `_ProxyHandler._forward`）——**即最后一轮；进程随后被 SIGINT** |

> 说明：`grep` 得到 18 处 `rm -rf` 文本出现，但去重 toolCallId 只有 **4 个**；
> 其余是同一 toolCall 在 `message_end` / `tool_execution_start` / `tool_execution_update` 事件中的重复。
> **因此删除循环为 4 轮**，每轮都整根重建，前一轮 dry 输出全部丢失。

此前 owner（`lightgravity-pi-bounded-i_g6y60q.log`，`06:49:04 → 06:52:57`）**无** `rm -rf` 于 dry 根；
该 owner 只改进 `harness/hard_gate.py` fixture ID（H5 卡在 `task_gate` 非法 ID），未产生/删除 dry 输出。

## 3. 被删除 / 丢失的对象（明确 missing）

以下在 4 轮 `rm -rf` 之前**存在过**（由各轮 tool result 的 `PASS/FAIL` 步骤文本与 `result.json` 结构证明），
现**已不可恢复**；**不伪造恢复，不重放未知写入**：

- `lg032-final-cohort-data-dry/offline_dry_run_output/<attempt>/result.json`：**轮 1 的完整 dry 结果**
  （含 `health_ok`、`execution_ready`、`reviewer_wired_model`、`ledger_persistent_single_path`、
  `counter_ledger_matches_frozen_path` 全 PASS，及 machine_gate 明细）——**已被后 3 轮 rm 覆盖丢失**。
- `lg032-final-cohort-data-dry/offline_dry_run_output/s1_units__A/result.json`：**轮 2/3/4 各自的 dry 结果**
  （其中一轮为 `phase: failed, phases_seen:['failed']`；`driver_error` 因轮而异）——**只剩最后被 SIGINT 的
  那一份（§4），其余丢失**。
- `lg032-final-cohort-data-dry/generation/generation.jsonl`（dry 侧跨轮累积账本）与
  `generation.count.json`：**被 rm 清零**；现 dry `generation/` 目录**为空**（见 §4）——**dry 侧跨轮累加证据丢失**。
- 各轮 `lg032-final-cohort-data-dry/attempts/*/workspaces/candidate-ws/` 及其 git 对象、当轮 SDK 会话残留：
  **仅最后被 SIGINT 轮的候选工作区存活**，之前各轮**丢失**。
- 4 轮中 3 轮的原始 stdout：当时以 `| grep -E … | head` 管道 **tail/filter 后丢弃**，未独立重定向保存
  （违反“每次 fake 失败输出独立重定向保存”）。**无法补齐**。

**声明**：以上 missing 项**不重建、不补跑、不用日志片段冒充原件**。

## 4. 仍有存活的证据（未删，单列保留）

| 类别 | 路径 | 状态 |
|---|---|---|
| 硬门全体结果（H1..H6，`real_generation: 0`） | `probes/lg032/FINAL-COHORT/evidence/offline/hard_gate.json` | **存活**，mtime 06:56 |
| 硬门沙箱（H3/H4 真账本） | `../lg032-gate-sandbox/gate-phase/`（`generation/generation.jsonl`、`generation.count.json`、settings、resources） | **存活** |
| H6 SDK `save_dir` 证据 | `../lg032-final-cohort-data/attempts/_gate_save_dir/workspaces/.lg-sdk-sessions` | **存活**（空目录结构） |
| 最后一轮 dry 输出（**残缺**） | `../lg032-final-cohort-data-dry/offline_dry_run_output/s1_units__A/result.json` | **存活但 `ok:false`**（`BrokenPipeError`，`elapsed 0.98s`，被 SIGINT 截断） |
| 最后一轮 dry 候选工作区 | `../lg032-final-cohort-data-dry/attempts/s1_units__A/{workspaces,secrets}` | **存活**（06:57:57 重建） |
| 前两 pi bounded 日志（含各轮 PASS/FAIL 文本） | `dispatch-logs/lightgravity-pi-bounded-c2n9sveo.log`、`…-i_g6y60q.log` | **存活**（`700`），仅日志级次生证据，**非原件** |
| dry `generation/` 目录 | `../lg032-final-cohort-data-dry/generation/` | **存在但为空**（账本被 rm） |
| 正式 phase 根 | `../lg032-final-cohort-data/` | **未发生正式 attempt**，仅有硬门 `_gate_save_dir` 残留 |

## 5. 未受影响（明确未动）

- **所有旧真实 proof / 旧 cohorts 未动**：`lg031-real-proof`、`lg031-real-proof2`、`lg031-proof2-close`、
  `lg023*`、`lg022*`、`lg029*` 等旁目录均在，未删。
- **正式 032 真实生成 = 0**：`lg032-final-cohort-data/` 无任何正式 attempt；本事故只涉及 dry（fake 上游）根。
- **Git 未提交**：本 worktree HEAD `91550a9`，唯一未跟踪项 `probes/lg032/`（本包产物，尚未 commit）。
- **他包进程/端口 8123 未动**：`127.0.0.1:8123`（PID 3320750）仍在；仅本 fixture 进程被停。

## 6. 前 fake 预检的证据效力（诚实降级）

- 前 owner 的 dry-run 全部为 **loopback fake 上游**，**不是正式采样**，**不计入**正式 192/4×48 预算，
  也**不算**任何“真实生成”。
- 由于 §3 的部分原件已丢失（dry ledger 累加、除末轮外的 dry `result.json`），**前 fake 预检不能称为完整证据**；
  仅 `evidence/offline/hard_gate.json`（H1..H6 全 PASS，且 `real_generation: 0`）是完整且存活的硬门结果。
- 后续如需 dry 证据，**新建唯一路径**重新产生（见 §7），**不覆盖、不删除**任何现存目录。

## 7. 本包硬禁令与整改（立即生效）

1. **任何路径禁止 `rm` / `rmtree` / `reset` / `clean` / 覆盖旧 attempt 输出或目录**（包括 debug/fake 目录）。
2. driver 中原 **固定 dry 根重用**（`_data_dir_for(dry_run) → 常量 `-dry` 路径`）与 dry `out_dir` 的
   `shutil.rmtree` **必须改为每次唯一路径**：`<dry 基> + UTC 时间戳 + nonce`，**旧固定 path 原样保留**
   （仅作为历史，不再写入）。
3. `_init_repo` 的 `shutil.rmtree(root)` 仅作用于**本 attempt 自己新建的、唯一命名的** candidate-ws；
   不得指向历史/正式路径。
4. **副本只新建，绝不删除**；raw `700/600` 保全**不入 repo**。
5. 每次 fake 失败 **独立重定向保存完整 stdout/stderr**（不得只 `| tail`/`| grep` 后丢弃）。
6. **父 phase 账本跨 attempt 要求不能被 dryUUID 绕过**：正式唯一物理 phase / 冻结 4 个 attemptID 始终固定；
   唯一化仅用于 **dry 隔离输出根**，正式 `PHASE_DATA_DIR` 不变。
7. 本 owner **前置调查源只读**；产品 bug 只写**最小 repro** 交 PM，**不自修产品**。

## 8. 后续动作

- 先出本文 + 更新 `STATUS.md`（保全交接）。
- 再改 harness 唯一路径 + 独立 stdout 重定向，继续 **真正常产品入口 + 真 SDK loopback fake 上游** 预检。
- 完成后写 `REPORT.md` + 冻结 hash + 精确 commit，STOP 等 PM。
