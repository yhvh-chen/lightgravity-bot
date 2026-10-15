---
title: "LG-032 FINAL-COHORT 最小交接（HANDOFF-MINIMAL）"
doc_type: handoff
category: engineering
status: "WIP saved — minimal reviewable handoff; no new experiments; not done"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（续接 owner）"
---

# LG-032 FINAL-COHORT — 最小交接（仅保存 WIP，不调查、不重放、不 claim done）

> 本文件**只固化已知交接事实**，不新增调查、不读 dispatch log、不跑测试探针、不改 driver。
> 未核实项一律标 **待核 / unknown**，不假定已通过。

## 1. 状态一句话

narrow-B 根因已定位为**产品 bug**（选择期 selector scratch 越出 executor 授权 `workspace_root`）；
独立修复分支已存在并过局部 check/proof；**Bdry 已越过原越界点但随后 `executing → failed`（429 fake 请求上限）**，
**无法完整 pass**；**正式真实 provider0 从未执行（192/4×48 全部未跑）**。

## 2. 精确 commit（现有，已落地）

| 项 | 值 |
|---|---|
| 本 worktree HEAD（上一 owner 实际调查 commit） | `6901c4f`（narrow-B root cause located） |
| 前一 WIP commit | `ee4f6d9` |
| 独立 fix 源（另一 worktree） | `fix/lg031-workspace-boundary@0814b80`（`fix(lg031-workspace-boundary): root candidate-pool selection scratch inside the executor authorized root`） |
| fix 基 | `main@3def294`（`3def2941a3f147aded25ac509d3c91d1bd3bd245`） |
| rootmain 3def294 两处 PM dirty（031 再开 / PROGRESS） | **本包不碰** |

## 3. 已知必要事实（全部）

1. **默认 bootstrap selector scratch 越出 executor `workspace_root` = 产品 bug**（非 harness 错配）。
   - 选择期 scratch 由产品 `GraphDispatcher._selection_workspace` 建在 Task `save_dir`
     （`<data_dir>/native-sessions/<task>/.lg-pool-selection/...`）；
   - executor 授权 root = `Settings.workspace_root`，产品默认 `<data_dir>/workspaces`；无包含关系 ⇒ 如实拒绝。
2. **独立 fix** `fix/lg031-workspace-boundary@0814b80`：修**最小 root 内 scratch**，
   作者**局部 check / proof 通过**（**准确数字：当前文档未记载 ⇒ unknown，不再调查**）。
3. **Bdry 已越过原越界点**，随后 `executing → failed`：**429 fake 请求上限** ⇒ **不能完整 pass**。
4. **正式真实 provider0、总 192 / 4×48 从未执行**（真实产品生成 = 0）。
5. **A/B 已统一 3 nodes**；**剩余 driver 状态按实际文档**，**未记载的 = 待核 / unknown**。

## 4. 原件路径

| 项 | 路径 |
|---|---|
| 根因报告 | `probes/lg032/FINAL-COHORT/REPORT-NARROW-B.md` |
| 状态 | `probes/lg032/FINAL-COHORT/STATUS.md` |
| 保全事故记录 | `probes/lg032/FINAL-COHORT/PRESERVATION-INCIDENT.md` |
| narrow 证据 | `probes/lg032/FINAL-COHORT/evidence/narrow/{diag1,diag2}/exec_diag.jsonl` |
| 最新 offline 日志（末轮 FAIL stdout） | `probes/lg032/FINAL-COHORT/offline/diag2_b_20261015T200910Z.stdout` |
| 产品修复 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg031-workspace-boundary-fix` |
| 正式 phase data（唯一物理 ledger） | `...lg032-final-cohort-data`（正式 attempt 未开始） |
| 独立 boundary QA | 另一 owner 在跑（QA 分支另 scope，本包不碰） |

## 5. 上一 finalizer 退出（仅记录，不重放）

- `finalizer72404` / log `96hy_6mr`：因读取长日志 token 40k 超额，`exit 143`，elapsed ≈29s。
- 副作用**仅 `git status` 核查**，**不重放**该运行。

## 6. Preservation 事故（旧 dry 删除，已记录）

- 前 owner 曾 `rm -rf ../lg032-final-cohort-data-dry`（4 轮），旧 dry 输出 / dry ledger 已丢失；
  详见 `PRESERVATION-INCIDENT.md`。
- **后续硬禁令**：严禁 `rm` / `rmtree` / `reset` / `clean` / 覆盖；**所有新 raw / 失败输出一律保留**。

## 7. 所需下一步（未执行，交 PM）

1. **PM 决定**是否将独立 fix `0814b80` 集成 / 走独立 QA 复验（本包不自宣 pass、不 main merge）。
2. harness 侧需移除 `LG032_WIDEN_EXEC_ROOT` 正式路径（快照已在 git 历史保留）——
   **本 WIP 已含该改动**（见 STATUS §3），但**未跑新实验验证**。
3. 剩余 driver 状态待核（见 §3.5）；正式 192/4×48 仍未执行。
4. 冻结 hash + 最终 REPORT 交独立 QA（**后话，未做**）。

## 8. 未完成清单（明确 not done）

- [ ] 正式真实 provider0 采样（192 / 4×48）：**未执行**。
- [ ] Bdry 完整 pass：**未达成**（429 fake 上限，executing→failed）。
- [ ] `0814b80` 集成 / 独立 QA 复验：**未做**。
- [ ] 剩余 driver 状态：**待核 / unknown**。
- [ ] 最终 REPORT + 冻结 hash：**未做**。
- [ ] **未** mark 032/031 done；**未** main merge；**未** push/deploy/publish。
