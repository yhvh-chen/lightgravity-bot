---
title: "LG-031 PROOF2-CLOSE — STATUS（0 真实模型确定性 lifecycle 收口）"
doc_type: status
category: engineering
owner: "LG031 REAL-PROOF2-CLOSE owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "fix/lg031-proof2-close"
base: "dev/lg031-real-proof2@e167724"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash（本包新增真实模型调用 = 0）"
updated: "2026-10-16"
---

# LG-031 PROOF2-CLOSE — STATUS

> 单独授权的 0 模型确定性收口。旧 REAL-PROOF2（PARTIAL, 门 1–6 PASS / 门 7 未达）**保持原字节**；
> 不改产品源/契约；不重跑 worker；不新调模型；全局 generation ledger count 恒 28。

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读 AGENTS/agent、031/032 原门、REAL-PROOF2 PLAN/STATUS/REPORT、原始 private raw-evidence、RUNTIME-AUTH-INTEGRATION/R1、cohort3 实际调用方式 | DONE |
| 1 | PLAN/STATUS 立即落盘；核原文件 SHA、旧 28 JSONL、Task/Run/Subtask revision、artifact/initialcommit/requirements_revision/plan_hash/realReview 证据 hash | DONE |
| 2 | 建新持久 worktree `lg031-proof2-close`/branch `fix/lg031-proof2-close`（基于 `e167724`）；旧 proof2 与私有 RawRoot 保留 | DONE |
| 3 | 建收口 harness：真实 typed DispatchOutcome 补落 + RecordedRealReview + RecordedStopFactReader + 产品 verify_and_prepare/decide + 负向对照 | DONE |
| 4 | 0 模型执行收口；保存真实 service 返回/新事件/合法迁移路径；前后 ledger hash 不变 | DONE |
| 5 | REPORT + 精确本地 commit | DONE |

## 终态

- **门 7「绑定 accept」在本 0 模型确定性收口路径达**：产品
  `run: executing→verifying→awaiting_acceptance→completed`、`task: verifying→awaiting_acceptance→completed`；
  `verify_and_prepare` `confirmed=true`（真实 stopgate 6/6 + reviewer 资源 + 候选绑定），
  `decide(accept)` `confirmed=true`（幂等；错 target/过期 revision 拒）。
- 真实 service 结果：`evidence/close-proof2.redacted.json`（`8859e0a8…`）；负向对照 `evidence/negative-controls.redacted.json`（`2a71e343…`）。
- 全局 generation ledger：`generation.jsonl` hash `e9a1ef78…`、`count=28` **收口前后不变**；本包新模型调用 **0**。
- REAL-PROOF2 原件/账本/evidence/worktree **字节不变**；`lg031-real-proof2` worktree `git status` **clean**。
- 已知整体真实生成 **86**（旧 34 + proof1 24 + proof2 28）不变；旧 phase 剩 6 **未消费**。

## 关键 hash / 锚

- 候选：Run `run_01M50GARZGSWF8KVJM2PVRZWWC` / Task `task_01M50GARZ7FDBC1YR46TCFMM18`；`requirements_revision=1`。
- `plan_hash=85f226e08d87bf60628e553489ab56eb77880a1baee28d1abd9835bcb3ccbc98`。
- 初始 commit `6cf81ea38456b7a0c3c2536b48985d7af3a55f11`。
- harness：`close_proof2.py c3d33c15…`、`negative_controls.py 449771fd…`、`redact_close.py 8b9202fe…`；PLAN `ad3e7b8d…`。
- 收口后（工作副本）：`TASK.md 2eda2bef…`、`RUN.md 558a66c1…`、task events `df1af19b…`、run events `1d110973…`。

## 未测 / 边界

- 机器检查授权集 `authorized=[]`（原 Task 无 `checks`）；隔离 worktree 产物不适用共享 workspace 检查；**未改 Task 补授权**。
- reviewer 停止事实为 harness 派生（原进程退出 + turn 正常返回），**如实标注**，不冒充产品记录 teardown。
- 不宣自动 checkpoint/resume/全 checkpointskip；不重跑 worker/不新调模型/不建新 ledger/不消费旧 phase 剩 6。
- 收口在私有只读快照工作副本执行；REAL-PROOF2 原件未移动/覆盖。
