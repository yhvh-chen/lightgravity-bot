---
title: "LG-023 cohort-2 对照评估 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort2"
---

# LG-023 cohort-2 STATUS

- Owner：`agent:pi-lg023-cohort2`（新独立 pi 上下文；**非** cohort-1 owner、**非** 方法审计 owner；
  主代理只 PM；无嵌套派工/推送/部署/发布）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2`（branch `eval/lg023-cohort2`，base `834b262`）。
- 产品快照：基于已通过核心产品树 `e0a8cec`（契约 `1.10.0`）；**不拉取** F1/F2 未来 pool 中途改动。
- 产品/共享 docs：**只读**；owner 只负责 `probes/lg023/cohort2/**` 及必要独立 harness/fixtures 与 LG023 记录。
- 旧 `dev/lg023`、`fix/lg023-method` 与全部旧原件：**保留、未 reset/clean/覆盖**。
- SDK `google-antigravity==0.1.22`；模型 `deepseek-v4-flash`。

## 进度

- [x] 核 worktree/claim/dirty（clean）、main 基点、产品只读边界、旧原件保留。
- [x] 逐字节复制 fixtures（`diff -r` 相同）。
- [x] 冻结 `cohort2_config.py`（预算/限制/路径/SDK/契约）。
- [x] 新独立 driver `run_attempt.py`（**不重用**旧会自动删/覆盖的 `run_all` 路径）。
- [x] 离线硬门 P1–P5 全过（`evidence/offline/offline_proof.json`）。
- [x] 离线真实装配 dry-run（本地 fake upstream，**非 DeepSeek**）两 arm 跑通（`evidence/offline/dry_run_proof.json`）。
- [x] 冻结 PLAN；计算 protocol hash；先 commit 离线就绪产物。
- [ ] **正式 4 attempts**（每个 1 次；真实 DeepSeek；需 PM 预注册已就绪 + 离线门全过）。
- [ ] REPORT + 脱敏证据 + 准确计数/局限 + 精确 commit。

## 真实生成计数（防洗数，不归零）

| 阶段 | 真实生成请求 | 状态 |
|---|---|---|
| 旧 LG-023 cohort（`dev/lg023`） | **45/48**（总数可核；逐 attempt 归因不可信） | protocol-deviation 失败成本，单列 |
| 本 cohort-2（`eval/lg023-cohort2`） | **0**（离线：0 次 DeepSeek；dry-run 用本地 fake upstream） | 未采样 |

- 旧 022（unknown+6+8+5/10）与 031（34/40）单列，不并入、不清零。已知 eval 实际上限 45+48=**93**。

## 关键设置

- 唯一自变量 = 计划写节点数（A=1，B=2 依赖）。
- 旧程序调度路径 / 新自主开关 **off**；workspace 隔离两 arm **一致关闭**（见 PLAN §3）。
- 全 stage 单一持久 ledger（`lg023-cohort2-data/generation/`，limit 48），每 attempt ≤12，**转发前**硬限。
- 真正走 `build_runtime`/`create_app`/Coordinator/Graph/VerificationService + 真实 stopgate（`confirm_stopped`）。
- 4 attempts、每个 1 次；不可变 attempt-id 输出 + 一次性 guard；harness/断言/装配/计量错误 → **整 cohort 停止**。
