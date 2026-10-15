# LG-022 第 1 轮返修（REFIX-R1）— 计划（冻结）

- 任务：LG-022「执行首版端到端与故障验收」第 1 轮返修（D1/D2/D3）。
- Owner：本包 LG-022 返修 owner（pi + 既有 env DeepSeek）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-r1`（branch `fix/lg022-r1`）。
- 基点：main `ca27160`（= LG-022 QA 证据 merge `8e81089` 后的最新整合主线；LG-041 PMdirty 保留在 root main 未提交）。
- 独立 QA 证据：`probes/lg022/REPORT.md`（候选 `bf7851c`，判定 fail，阻断 D1/D2、诚实性 D3）。

## 0. 角色与边界

- 本 owner 执行调查/代码/测试/集成/控制，不嵌套派工；主代理只 PM。
- 独占 review 生命周期：verify/**、coordinator/service.py、control.py、recovery.py、review 新资源/stop 模块、
  api/tasks/bootstrap 必要接线、相关 tests 及本目录 probes。
- 共享 docs08/README/PROJECT/agent/docs06 本包唯一 owner；契约扩展先文档再实现。
- 禁改 sources/vectors/lexical/frontend/API sources（037/038 owner）；不抢 api/app.py 除核心最小装配。
- 保留 pin/evidence/token/验收幂等/跨 Run 总预算/016 反重放/默认去中心化关闭等旧边界。
- 不 push/deploy/publish；root main 不并发写代码（本包全在独立 worktree）。

## 1. 真实失败（以独立 QA 证据为准）

- **D1（阻断）**：`verify/review.py::run_review_turn` 同步函数内 `asyncio.run(_turn())`；真实协调器
  在已运行事件循环（`Coordinator._run_loop` → `_apply_outcome` → `_auto_verify`）调用 → `RuntimeError`，
  review 永远 `unavailable`，无法 `awaiting_acceptance`。最小复现 `probes/lg022/evidence/repro-d1.json`。
- **D2（阻断）**：review 同步阻塞事件循环（替身实测查询 12.1s），没有 reviewer 生命周期；pause/cancel
  只跟踪 worker `_inflight`，review 阶段无 stop/release 确认。
- **D3（非阻断）**：成功 Run 也写 `fail_reason`（诚实性）。

## 2. 设计方向（复用现有 SDK/adapter 取消与资源边界）

1. **D1 修复**：把 reviewer turn 移出协调器事件循环。采用与 `dialogue.make_sync_responder` 一致的
   **私有事件循环 + 工作线程**模式（而不是在运行循环内嵌套），使真实协调器 async 路径可 review。
   `run_review_turn` 保留**同步入口**以兼容现有 fixture/探针接口，但内部改为：若当前线程已有运行中的
   loop，则在独立线程的新 loop 上跑；否则可兼容旧行为。
2. **D2 修复**：给 review 引入**可取消/可观测的生命周期**；reviewer 的 turn 通过一个
   **可 stop 的 runner**（记录 stop 请求、超时后 honest unknown、释放槽）。协调器 `_auto_verify`
   改为可服务状态/控制：review 在可等待的边界运行，pause/cancel 在 review 中返回明确语义
   （pause → `pending_review`/不写 paused；cancel → 请求 reviewer stop；未知不写终止、不释放槽）。
   scheduler/dispatcher 的 cancel 需同时覆盖 review 阶段资源。
3. **D3 修复**：`_apply_outcome` 仅为真实失败/取消写 `fail_reason`；成功 Run 用非失败字段。

## 3. 成功门（返修自检，非版本验收）

- 真实协调器 running-loop 路径可 review（async 实际路径正确，不用 `to_thread` 掩盖无法取消的后台线程）。
- async status/control **同时**可响应：review 运行中 `GET /tasks` 与 pause/cancel 不被阻塞。
- review 暂停/取消有 **confirmed**；超时 → `unknown` 且**保留槽**；重启不重放未知副作用、旧候选保留。
- 跨 Run 总预算（`max_repair_rounds`/`max_review_rounds` 终身账本）不因新 Run 重置。
- stale accept / 重复 reject 幂等。
- 无 reviewer 诚实 `unavailable`，不退回 ProgramReviewer 假 pass。
- 必须**全局实际 HTTP 生成计数硬上限**（含所有 session/reviewer/retries/失败，转发前计数）才能进入
  独立复验；未完成样本不算交付。

## 4. 本包真实产品模型预算

- **本包真实产品模型预算 0**；不重跑已成功 worker 样本、不重置历史成本。
- 复验由独立 pi 执行；本包不宣称实际 DeepSeek 已验。

## 5. 命令与局部回归

- `uv run mypy`（改动文件）；相关 `pytest`（tests/verify、tests/coordinator、tests/api）。
- 大生命周期变更可全后端一次；失败则新变更局部返修；不为已知 race flake 反复 stash/全量比较。
- 单命令 120s；长检查受控短轮询（≤5s）。

## 6. 证据与报告

- 原始证据存本目录 `evidence/**`；报告本目录 `R1-REPORT.md`；状态 `R1-STATUS.md`。
- 每项绑定候选 commit + 需求 + 候选产物版本；真实/替身逐项标清。
- 最终 HEAD/检查/真实调用 0/需复验清单/031 续接信息，报告先落盘后结束。
