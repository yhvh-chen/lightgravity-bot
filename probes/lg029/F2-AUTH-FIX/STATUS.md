# LG-029 F2 返修 — STATUS

> owner：`agent:pi-lg029-auth`｜分支 `fix/lg029-auth`｜基点 `834b262`（clean）
> 产品真实生成请求：**0**｜独立质量门：另 pi 集中复验（本包不自判 LG-032 通过）

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读 AGENTS/agent/PROJECT/PROGRESS、docs08 §4.3、LG-028 约束、LG029/032、qa/lg032 quality | DONE |
| 1 | 核 cwd/分支/基点/dirty/worktrees/claim | DONE（clean @ `834b262`） |
| 2 | 独立确认 F2（四端点 body.owner；peer 已用 worker_identity） | DONE |
| 3 | 写 PLAN/STATUS（本目录） | DONE |
| 4 | 复用 execution_grant 增加 grant 级解析（含 scope/fence） | TODO |
| 5 | 接线 api/context + api/bootstrap（加性，不动 peer） | TODO |
| 6 | 修 `api/collaboration.py` 四端点 default-deny + 程序身份/scope/fence | TODO |
| 7 | 更新 api tests（未认证/伪造/跨scope/陈旧fence/越权/正常/幂等/竞争/默认关闭 + 断言未落盘） | TODO |
| 8 | 局部 pytest + 改动模块 mypy | TODO |
| 9 | F2 最小 HTTP 复现证据（真 ASGI，无模型） | TODO |
| 10 | REPORT + 精确本地 commit | TODO |

## 关键事实（开工快照）

- `git status --short`：空（clean）。`git branch --show-current`：`fix/lg029-auth`。HEAD `834b262` == main。
- `api/bootstrap.py:480` 已把 `resolve_worker_identity` 接到 `ApiContext.worker_identity`。
- `collaboration/execution_grant.py` 已有 `ExecutionGrantRegistry` + `resolve_worker_identity`（header-only，default-deny）。
- `api/collaboration.py:88-152` discover/claim/renew/release 取 `body.owner`，未接 `worker_identity`（F2 缺口）。
- `api/collaboration.py:155-181` peer 端点已用 `ctx.worker_identity`（default-deny）。
- `graph.py` 铸造 pool/node grant 并经 `default_registry()` 与 API 共享。

## 未测 / 待集成

- 待局部回归完成后回填。
- 契约行为变化（端点身份/scope 语义）需 docs08 owner F1 串行登记，见 REPORT。
