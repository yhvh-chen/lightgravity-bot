---
title: "LG-032 阶段 B final-cohort STATUS（narrow-B 根因定位 + WIP 交接）"
doc_type: status
category: engineering
status: "NARROW-B ROOT CAUSE LOCATED (product defect); WIP REPORT + commit landed; PM-authorized minimal fix worktree created; product real calls 0"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（续接 owner；非 031 实施者；主代理仅 PM）"
---

# LG-032 阶段 B — final-cohort STATUS（narrow-B 根因定位续接）

## 0. 本包性质与硬边界（不变）

- 产品**真实生成 = 0**；不许正式采样；只走 loopback fake 上游 + 真 SDK/产品生命周期。
- **任何路径禁止 `rm`/`rmtree`/`reset`/`clean`/覆盖旧 attempt 输出或目录**（事故后硬禁令）。
- 保留所有旧 probes/dry/stdout/SDKDB；新输出唯一命名；不清理原件。
- 无嵌套 agent / 无 push/deploy/publish；不动 8123 / 他包 / rootmain。
- 单条 check <= 90s；真实 SDK 只 loopback fake；禁外部 POST；凭证不外泄。
- wall420 / maxround90 / noncache130k / idle150 / retry0。

## 1. narrow-B 根因（本包核心交付；详见 `REPORT-NARROW-B.md`）

**产品缺陷，非 harness 错配。**

- arm B 选择期 scratch 由产品 `GraphDispatcher._selection_workspace`
  （`backend/lightgravity/coordinator/graph.py:1095`）建在
  `<data_dir>/native-sessions/<task>/.lg-pool-selection/<run>/<slot>`
  （`context.save_dir` ← `coordinator/service.py:_native_session_dir` ← `data_dir`）。
- 真 `AntigravityExecutor._resolve_workspace`（`adapter/executor.py:825-836`）授权 root =
  `Settings.workspace_root`，产品默认（`config.py:48`）= `<data_dir>/workspaces`（`data_dir` 的**子目录**）。
- 无包含关系 ⇒ 如实拒绝 `escapes the authorized root` ⇒ 选择 session `blocked` ⇒ Run `failed`。
- **正常产品默认 bootstrap 同样触发** ⇒ 属于 032 要找的真正产品缺陷
  （合法自主管理的 workspace 路径被错误拒绝）。符合 PM 授权 3)。
- 真实 failedRun 证据（存活原件）：
  `evidence/narrow/diag{1,2}/exec_diag.jsonl`、`offline/diag{,_2}_b_*.stdout`。

## 2. 禁用调试手段（已标记，须从正式路径移除）

`harness/run_attempt.py:_enable_loopback_for_dry_run` 内 `LG032_WIDEN_EXEC_ROOT` 直接改写
`executor._workspace_root`。**正式路径不得使用**；快照在本 WIP commit 保留，待 harness 侧改为
“把 scratch 放进受控正确 root”，而非 widen 授权。

## 3. 已完成（本续接包）

1. ✅ `REPORT-NARROW-B.md`（根因 + 源码 path:line + 真实配置值 + 影响范围 + 下一步）。
2. ✅ 本 `STATUS.md`（每 8-round 交接）。
3. ✅ 精确 WIP commit：`ee4f6d9`（仅 `probes/lg032/**`，产品源只读未改）。
4. ✅ PM 授权 3) 独立持久 fix worktree：
   `../lg031-workspace-boundary-fix`，branch `fix/lg031-workspace-boundary`，基 `main@3def294`
   （`3def2941a3f147aded25ac509d3c91d1bd3bd245`）。

## 4. 下一步（授权范围最小修）

1. 在 fix worktree 做**最小产品修复**：让选择期 scratch 落在**受控正确 root**
   （executor 授权 root / `workspace_root`）之内，**权限不扩大**、**不宽化到其他 worktree**、
   真正隔离、程序授权/lease/fence/预算/真实 stopgate 不变、default off。
2. harness 侧移除 `LG032_WIDEN_EXEC_ROOT` 正式路径用法（快照保留），把 fixture scratch/workspaces
   置于受控正确 root。
3. 新增回归：**root 内合法 selector 通过** + **越 root 拒绝**；不镜像实现、不跑无关全套。
4. 0 fake 至多 **1B 新 unique attempt** 证根因解除（**不是**正式 032 采样）。
5. 写最终 REPORT + 冻结 hash + 精确 commit，交**独立 QA**；不自行宣 pass。
6. 031 状态可保留 done 历史；报告建议 PM 重开等待独立复验。

## 5. 关键保全路径（不变）

| 项 | 路径 |
|---|---|
| worktree（QA 原，不混源） | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort` |
| 正式 phase data（唯一物理 ledger） | `...lg032-final-cohort-data`（正式 attempt 未开始） |
| 根因报告 | `probes/lg032/FINAL-COHORT/REPORT-NARROW-B.md` |
| 事故记录 | `probes/lg032/FINAL-COHORT/PRESERVATION-INCIDENT.md` |
| narrow 证据 | `probes/lg032/FINAL-COHORT/evidence/narrow/**` |
| 产品修复 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg031-workspace-boundary-fix` |

## 6. 真实生成计数

- **正式真实产品生成：0**。
- 旧 023（45/4/16）、旧 022、旧 031（86）单列保留，未并入本 cohort、未清零。
