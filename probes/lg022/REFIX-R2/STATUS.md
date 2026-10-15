---
title: "LG-022 第二轮针对性返修（REFIX-R2）— STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
---

# LG-022 REFIX-R2 — STATUS

- Owner：`agent:pi-lg022-r2`（pi + env DeepSeek；主代理只 PM，无嵌套派工/推送/部署）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-r2`（branch `fix/lg022-r2`）。
- 基点：`main` @ `29ffbb6`（开工前核 clean；工作区无改动）。
- 输入：独立 QA 复验 R1 `qa/lg022-r1` @ `6228474` 的 `probes/lg022/reverify-r1/REPORT.md`（判定 FAIL）。
- 不重新调查已定位错误、不扩功能；只修两个阻断 + 必要回归/证据。
- **本包产品真实模型调用 0**（全部本地替身/确定性证据）。
- 不含 LG-031 任何试验/模型重放；原 031 dirty/分支/worktree 保持不动。

## 本轮阻断（QA 实证）

- **A（阻断）**：`verify/stopgate.py::StoreResourceStopper` 要求 `not session_refs or cleanup.status=="done"`；
  真实成功 Run 落盘 2 个 `session_refs` 但正常成功路径从不写 `cleanup=done`（仅 stale/recovery/人工 accept 后写），
  `verify_and_prepare` 恒 `unconfirmed`，Task 停在 `verifying` 无法 accept。
- **B（计量硬门）**：`adapter/proxy.py::GenerationCounter` 仅进程内内存，跨进程重启归零。

## 状态

- [x] 安全 merge QA `6228474`（仅 QA/任务/计时刷新证据）
- [x] 保全 `r1-review-lifecycle.json` 原始字节（sha256 `9853bca4…`）+ 另存 QA 刷新版（`feb2d1e4…`）
- [x] STATUS/PLAN
- [x] A 真实资源完成链修复（`StopConfirmation`/`confirm_stopped`/stopgate 事实门/`reviewer_cleanup`）
- [x] B 持久预算账本（`generation_ledger.py` + `dataRoot` 注入 + 损坏不当 0）
- [x] 局部回归 + mypy + 一次全量 pytest（765 passed, 5 skipped）
- [x] 契约/文档 `1.10.0` 一致性（constants/tests/docs08/README/PROJECT/agent/docs06）
- [x] REPORT（`REFIX-R2/REPORT.md`，含退出码/未测/账本路径/停止证明来源/独立 QA 最小清单）
- [ ] 精确本地 commit（收尾步骤）

**LG-022 仍 `in-progress`**；本包不自判集中门 pass，修复后须新独立 QA 复验。
本续接产品真实模型调用 **0**；未在真实链验证 A/B（见 REPORT §5）。
