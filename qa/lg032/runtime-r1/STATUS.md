# LG-032 返修复验 R1 — STATUS

> owner：独立复验 QA（非 F1/F2/整合实施者）｜branch `qa/lg032-runtime-r1`｜基点 `afcae82` + merge `main@66b2b10`
> 产品真实 DeepSeek/生成请求：**0**｜本包**不合入 main**｜本包**不自判版本 pass**

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读规则/docs/任务/QA REPORT·FINDINGS/031-runtime REPORT·PLAN·probe/F1F2 边界 | DONE |
| 1 | 核 Git/worktree/dirty/进程，保全旧证据 | DONE |
| 2 | 建 `qa/lg032-runtime-r1`@afcae82 + 安全 merge main；核产品树逐字节同 afcae82 | DONE |
| 3 | 写 PLAN/STATUS | DONE |
| 4 | 门1 真实 SDK 两阶段（同 Runtime 两 worker、同权限profile、4节点、选非首项、A/B不串、选择期无写工具） | DONE（PASS） |
| 5 | 门2 竞争/身份（1 winner/fence；loser 有界重发现；HTTP default-deny/越权/stale fence/跨run；跨member拒绝） | DONE（PASS，2 观察） |
| 6 | 门3 资源/预算/恢复（8 会话真实 session_refs + stopgate held/放行；同一持久账本跨 Run 不归零；corrupt=unknown；reviewer 共账本） | DONE（PASS；1 观察） |
| 7 | 门4 默认回退 + §13 变更控制 | DONE（PASS；§13 分类 1 咨询项） |
| 8 | 局部 pytest + mypy（材料性差异） | DONE（mypy 137 clean；全量 813 passed/5 skipped） |
| 9 | REPORT + 精确 commit | IN PROGRESS |

## 关键事实

- 新 worktree `qa/lg032-runtime-r1`@`afcae82`；merge `66b2b10` 后产品/契约/测试树 `git diff` **为空**（逐字节同 afcae82）；main-only 非 probe 变更为 `PROGRESS.md`/`LG-023.md`/`LG-024.md`。
- 旧 `qa/lg032`、`lg031-runtime`、`lg031-r1`(dirty 8)、`/tmp/*` 全部原样保留；8123 uvicorn 等独立进程未触碰。
- 真 SDK `0.1.22` + 本地 fake loopback 上游（provider-substitute）；所有探针持久目录、create-only。

## 四门结论（详见 REPORT.md）

- 门1 PASS；门2 PASS（观察 O1：同 dispatcher 冻结 `lease_owner` 为 worker 实例=dispatcher，两 member 同 owner 时遇同 node 第二者为幂等 `already_owned`，无双重真实授予/双写）；门3 PASS（观察 O2：reviewer 经默认进程全局计数器共用同一持久账本，已被正面证明）；门4 PASS（§13 观察 O3：`body.owner` 公开请求字段语义放松记录为“无版本变化”，可辩护但建议以 MINOR 行或 §4.3 明确标 compat-only）。

## 待补

- REPORT 定稿；精确本地 commit。
