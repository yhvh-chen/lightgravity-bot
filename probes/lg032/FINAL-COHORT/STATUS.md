---
title: "LG-032 阶段 B final-cohort 预检 STATUS（保全返修续接包）"
doc_type: status
category: engineering
status: "NARROW-B ROOT CAUSE LOCATED (product workspace-boundary defect); WIP REPORT written; awaiting PM-authorized minimal fix worktree; product real calls 0"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（续接 owner；非 031 实施者；主代理仅 PM）"
---

## ★ 本轮新增（narrow-B 调查，2026-10-16）

- **根因已定位（产品缺陷，非 harness 错配）**，详见 `REPORT-NARROW-B.md`：
  产品 `GraphDispatcher._selection_workspace`（`backend/lightgravity/coordinator/graph.py:1095`）
  把 arm B 选择期 scratch 建在 `<data_dir>/native-sessions/<task>/.lg-pool-selection/...`，
  而真 `AntigravityExecutor._resolve_workspace`（`adapter/executor.py:825-836`）的授权 root 是
  `Settings.workspace_root`（产品默认 `config.py:48` = `<data_dir>/workspaces`，是 `data_dir` **子目录**）
  ⇒ 不含 ⇒ 如实拒绝 `escapes the authorized root` ⇒ selection session `blocked` ⇒ Run `failed`。
- 真实 failedRun 证据：`evidence/narrow/diag{1,2}/exec_diag.jsonl` + `offline/diag*_b_*.stdout`（存活原件）。
- **判定**：符合 PM 授权 3)——“产品正常默认 bootstrap 构造 selector scratch 落在 executor 禁止 root 外”。
- **禁用调试手段标记**：`harness/run_attempt.py:_enable_loopback_for_dry_run` 的 `LG032_WIDEN_EXEC_ROOT`
  直接改写 `executor._workspace_root`；**正式路径不得使用**，须移除；快照在本 WIP commit 保留。
- **产品真实生成 0**；未跑正式样本；未删任何旧输出；未 push/deploy；未动 8123/他包。
- **下一步（待 PM 授权 2)/3)）**：新 worktree `lg031-workspace-boundary-fix`@`main 3def294`
  branch `fix/lg031-workspace-boundary` 做最小修复 + harness 移除 widen + 新增 root 内/越 root 回归；
  0 fake 至多 1B 新 unique attempt 证根因解除；交独立 QA。

---

# LG-032 阶段 B — final-cohort 预检 STATUS（保全返修续接）

## 0. 本包性质与硬边界（不变）

- 本包**产品真实生成 = 0**；**不准正式采样**；只走 loopback fake 上游 + 真实 SDK/产品生命周期。
- 正式采样由 PM 后续派工，依赖 031；本包只交付**可续接**的预检 + 冻结 + REPORT/STATUS。
- **任何路径禁止 `rm`/`rmtree`/`reset`/`clean`/覆盖旧 attempt 输出或目录**（事故后硬禁令，见 §1）。
- 保留所有已运行 0-fake 尝试原件；新输出**唯一命名**；**不清理**原件；每次 fake 失败**独立重定向保存**完整 stdout。
- 产品源**只读**、**不自修产品**；owner 仅 `probes/lg032/FINAL-COHORT/**`；不碰 root dirty / 031 task / 共享 docs / 8123。
- 无嵌套 agent / 无 push/deploy/publish；wall900 / round180 / noncache220k / idle180 / retry0。

## 1. 保全事故（本包第一交付；详见 `PRESERVATION-INCIDENT.md`）

- 前 owner（wrapperPID `2455191`，log `lightgravity-pi-bounded-c2n9sveo.log`，06:54:26→06:57:54，exit143）
  为调试 dry-run driver **反复执行 `rm -rf ../lg032-final-cohort-data-dry` 共 4 轮**（turn 64/67/68/70，
  4 个不同 toolCallId），每轮**整根删除**并重建 ⇒ 各轮 dry 输出全部丢失；随后被 PM 精确 SIGINT。
- **丢失（不可恢复，不伪造）**：前 3 轮 dry `offline_dry_run_output/*/result.json`、
  dry 侧跨轮累积 `generation/` 账本、对应 candidate-ws / SDK 会话残留、各轮未重定向的原始 stdout。
- **仍存活**：`evidence/offline/hard_gate.json`（H1..H6 全 PASS，`real_generation:0`）、
  `../lg032-gate-sandbox/gate-phase/`（H3/H4 真账本）、
  `../lg032-final-cohort-data/attempts/_gate_save_dir/`（H6）、
  末轮残缺 dry `result.json`（`ok:false`，`BrokenPipeError`，被 SIGINT 截断）、前两 pi bounded 日志。
- **未动**：所有旧真实 proof / 旧 cohorts、正式 032 phase 根（正式 attempt 0）、Git（HEAD `91550a9`，
  仅 `probes/lg032/` 未跟踪）、他包进程与 `127.0.0.1:8123`。
- **效力降级**：前 fake 预检**不是正式采样**、**不计 192 预算**、且**部分原件丢失 ⇒ 不能称完整证据**；
  仅 hard_gate 结果完整存活。

## 2. 前包暂停点（续接起点）

- 前包（`bounded-i_g6y60q`）前序停在 `hard_gate.py` H5 的非法 fixture ID（`task_gate`，非 runtime ULID），
  **非产品缺陷**（产品校验正确，docs/08 §3.1）。
- 紧前 owner（`bounded-c2n9sveo`）已：修 H5 fixture ID → **H1..H6 全 PASS**（写 `evidence/offline/hard_gate.json`）
  → 进入 dry-run driver 调试 → **卡在 loopback fake 上游转发**（`upstream URLError` / 502；
  最后定位到 `_ProxyHandler._forward` monkeypatch 方向）→ 被 SIGINT。
- 紧前 owner **未产出 STATUS/REPORT/commit**；**正式产品请求 = 0**。

## 3. 前包已完成（保留，不重做）

- `PLAN.md`（预注册：2 样本 × 2 arm × 1 = 4 attempt / 每 48 / 总 192）。
- `harness/final_cohort_config.py`（冻结路径/上限/身份）。
- `harness/run_attempt.py`（正式与离线同一 driver；真 `build_runtime` + 真 product uvicorn lifespan 启动
  `CoordinatorWorkerLoop` + 真 `VerificationService` + 真 `ModelReviewer`；`_FrozenPlanner` arm A/B；
  `_AttemptGuard` per-attempt 48）。
- `harness/hard_gate.py`（H1..H6 硬门，**当前全部 PASS**）。
- `fixtures/{s1_units,s2_pipeline}/{initial,reference,acceptance.py}`（原始保留）。
- 硬门证据 `evidence/offline/hard_gate.json`（存活）。

## 4. 本包续接计划（立即执行）

1. ✅ 写 `PRESERVATION-INCIDENT.md`（本包第一交付，保全交接）。
2. ✅ 更新本 STATUS。
3. **改 harness 唯一路径**：dry 基根 + `UTC 时间戳 + nonce`（`dry_root()`），旧固定 `-dry` path **原样保留**；
   dry `out_dir` 覆盖改为**唯一目录、不 rmtree**；每次 fake 调用的完整 stdout/stderr **独立重定向保存**；
   `_init_repo` 的 rmtree 仅限本 attempt 唯一 candidate-ws。**正式 `PHASE_DATA_DIR` / 4 个冻结 attemptID 不变**。
4. 定位并修 **真 SDK loopback fake 上游** 转发（此前卡 `proxy/upstream` 配置/端口/fixtureID；
   用已有 SDK 探针已验证的 fake 实现，最小化 debug，**不改产品**）。
5. 跑 dry-run driver（同一 driver，仅换上游/基目录）验证真正常产品入口全链：
   真 product 启动 → Task → CoordinatorWorkerLoop → finalization → 异步真 review → **机器 truth** →
   stopgate → 绑定 accept → 幂等 → 错 target 拒绝；真实 worker/reviewer proxy 计数落**同一物理 ledger**。
6. 全部 0 门达到后（或发现**产品阻断**则写准确 repro）：冻结 PLAN+driver+inputs/hashes，
   写 `REPORT.md`/STATUS，**精确 commit**，STOP 等 PM。

## 5. 关键保全路径

| 项 | 路径 | 备注 |
|---|---|---|
| worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort` | 持久 |
| 正式 phase data（唯一物理 ledger） | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort-data` | **固定，不变** |
| 预期物理 ledger | `<phase>/generation/generation.jsonl` | 正式 attempt 未开始 |
| dry 基根（**唯一化后新建，旧 `-dry` 保留**） | `...-data-dry-<UTC>-<nonce>` | 不删旧 |
| immutable attempt 输出（正式） | `probes/lg032/FINAL-COHORT/runs/<sample>__<arm>/` | 存在即拒 |
| 硬门/协议证据 | `probes/lg032/FINAL-COHORT/{evidence,offline}/` | |
| 事故记录 | `probes/lg032/FINAL-COHORT/PRESERVATION-INCIDENT.md` | 本包新增 |
| 前两 pi bounded 日志 | `~/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-{i_g6y60q,c2n9sveo}.log` | 700 |

## 6. 真实生成计数

- **正式真实产品生成：0**（本 STATUS 落盘时）。
- dry fake 上游调用：见各唯一 dry 输出与 pi 日志（部分原件丢失，见 §1）；**不计正式预算**。
- 旧 023（45/4/16）、旧 022、旧 031（34+24+28=86）**单列保留**，未并入本 cohort、未清零。
