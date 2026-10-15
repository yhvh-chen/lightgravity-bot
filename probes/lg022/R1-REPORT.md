# LG-022 首版集中 QA 第 1 轮返修（REFIX-R1）— REPORT

- Task：LG-022「执行首版端到端与故障验收」第 1 轮返修（D1/D2/D3）。
- Owner：本包 LG-022 返修 owner（pi + 既有 env DeepSeek）；主代理只 PM，无嵌套派工。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-r1`（branch `fix/lg022-r1`）。
- 基点：main `ca27160`（= LG-022 QA 证据 merge `8e81089` 之后的最新整合主线）。
- 独立 QA 输入：`probes/lg022/REPORT.md`（候选 `bf7851c`，判定 fail，阻断 D1/D2、诚实性 D3）。
- **本包真实产品模型调用 0**；不重跑旧成功/失败真实样本，不 reset 历史成本。

> 状态：**in-progress（返修自检完成，待新的独立复验 QA）**。本包不宣称版本验收通过。

## 1. 缺陷与修复

| 缺陷 | 真实问题（QA 证据） | 本包修复 | 关键文件 |
|---|---|---|---|
| **D1（阻断）** | `verify/review.py::run_review_turn` 在运行中的事件循环内 `asyncio.run(_turn())` → `RuntimeError`，真实协调器路径 review 永远 `unavailable` | `_run_coro_sync()`：若当前线程已有运行 loop，则在**私有 loop + 工作线程**上跑（对齐既有 `dialogue.make_sync_responder` 边界），不再嵌套 `asyncio.run`；同步入口保留以兼容 fixture/探针 | `backend/lightgravity/verify/review.py` |
| **D2（阻断）** | review 同步阻塞协调器 loop，且无 reviewer 生命周期；pause/cancel 只跟踪 worker `_inflight` | 新增 `ReviewLifecycle`（worker 线程运行 review、协作式 `threading.Event` stop、`confirmed`/`unknown` 诚实裁定，`unknown` 保留槽）；协调器 `_pending_auto_verify` 队列 + `_auto_verify_async` 用 `run_in_executor` 跑 review，loop 持续服务 status/control；`restart` 阶段 pause/cancel 经合法两步停位；`verifying`/`repairing → recovery_required` 加性迁移 | `verify/review_lifecycle.py`(新)、`coordinator/service.py`、`coordinator/control.py`、`store/entities.py` |
| **D3（诚实性）** | 成功 Run 也写 `fail_reason` | `_apply_outcome` 仅在 `run_state ∈ {failed, cancelled}` 且确有 failure/summary 时写 `fail_reason` | `coordinator/service.py` |
| **全局生成计数** | QA 无法给出真实产品模型调用上限（每 proxy 预算随 session/reviewer/retry 重置） | `GenerationCounter` 进程全局、线程安全，**转发前** `reserve()`；默认所有 proxy 共享；`GET /api/v1/diagnostics/generation` 只读报告 `{count,limit,remaining}`（`limit` 来自 `LIGHTGRAVITY_MAX_GENERATION_CALLS`，`None` 仅计数）；不暴露凭证/prompt | `adapter/proxy.py`、`api/health.py` |

## 2. 契约 / 文档 / 版本常量一致性

- `CONTRACT_VERSION` `1.7.0 → 1.8.0`（加性 MINOR）：`backend/lightgravity/contracts/constants.py`、`tests/contracts/test_contracts.py`。
- docs08 同步（frontmatter `contract_version`、§4.3 端点行、§6.1 迁移、§9 复核生命周期/全局计数、§13 变更记录）与 README/agent.md/docs06/PROJECT.md 一致性更新。
- `GET /api/v1/diagnostics/generation` 登记为「已实现（`1.8.0`）」。

## 3. 检查证据（本地，均绑定 HEAD）

- **HEAD**：本包返修 commit `fix(lg022-r1): repair D1/D2/D3 + global generation counter (contract 1.8.0)`，基于 `ca27160`；branch `fix/lg022-r1`（自引用哈希不内嵌，以 `git log -1 fix/lg022-r1` 为准）。
- **完整后端 `uv run pytest -q`**：**706 passed, 4 skipped**（73.9s）。其间出现的
  `Exception occurred during processing of request from ('127.0.0.1',…)` 为本地认证 proxy 的连接重置日志，**非测试失败**（进程退出码 0）。
- **相关子集**（`tests/contracts tests/verify tests/coordinator tests/adapter tests/api tests/control tests/store`）：444 passed（42.6s）。
- **新增/相关文件**：`tests/verify/test_verify_review_lifecycle.py`（10 passed）、`tests/api/test_health.py`（4 passed，含新增 diagnostics 回归）、`tests/coordinator/test_lg022_review_lifecycle.py`（8 passed）、`tests/adapter/test_lg022_generation_budget.py`。
- **`uv run mypy`**（6 个改动源文件）：Success, no issues。
- **确定性探针**（0 模型调用）：`probes/lg022/harness/r1_review_lifecycle_probe.py` →
  `probes/lg022/evidence/r1-review-lifecycle.json`：D1 running-loop 调用未抛异常；D2 复核期间 loop 持续调度（100 ticks）；`confirmed` stop 释放槽、`unknown` stop 保留槽。

### 3.1 真实 / 替身声明

- 上列 D1/D2/D3 与全局计数检查**全部为替身/确定性证据（0 真实 DeepSeek 调用）**，用于证明修复的机制与状态机正确。
- **真实 DeepSeek + 真实协调器 running-loop 的端到端复核未在本包执行**（本包真实产品模型预算 0），与旧 QA 策略一致，留待独立复验 owner；**不以替身结果宣称真实 DeepSeek 已通过**。

## 4. 未测 / 需独立复验

- 真实 DeepSeek reviewer 在真实协调器 loop 下产出的 review（D1 的真实上游验证）。
- 真实 review 进行中 pause/cancel 的**真实 stop 确认**与长连接取消边界；真实超时 → `unknown` 保留槽。
- `LIGHTGRAVITY_MAX_GENERATION_CALLS` 在真实多 session/reviewer/retry 下共享同一硬上限（仅单测覆盖计数器语义与默认共享，未跑真实多 session）。
- 浏览器/HTTP 全路径（LG-021/022 版本门范围）。
- 旧 QA 真实请求数：**unknown**（单列，不视为 0，不 reset 成本）。

## 5. 源码 / 提交

- 本包归属改动：上表 6 个后端源文件 + 1 新源文件 + 4 个新测试 + `tests/api/test_health.py` + `tests/contracts/test_contracts.py` + docs/README/PROJECT/agent/docs06 + 本目录 probes（R1-PLAN/R1-STATUS/R1-REPORT/evidence/harness）。
- 精确本地 commit（不 `git add -A`，不含未知/秘密文件）；原 LG-031 wip/checkpoint 保持原样，未合并。
- 提交：单个本地 commit（subject 见 §3），`git log -1 fix/lg022-r1` 取最终哈希（自引用哈希不内嵌于被提交文件，避免 amend 循环）；工作区 clean。

## 6. 原 LG-031 owner 交接（继承，未重放）

- 交接记录（绝对路径）：`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-lg031-r1-handoff/owner-handoff-lg031-r1.md`。
- 备份目录：`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-lg031-r1-handoff/`（`tracked.diff`、`untracked/`、`HEAD.txt`、`branch.txt`、`wrapper-26vw_kwk.log` 等）。
- 031 runtime 调用计数（日志侧，交接时，**unknown 精确总量**）：wrapper `bounded-26vw_kwk`；`turn_start`=115、`turn_end`=114、`message_end`=258、model 响应记录=224（`deepseek-flash`）；`usage.json` 未生成 ⇒ 成本/调用总量 unknown，**不按零计**。
- 停止：仅向唯一匹配 wrapper PID `1741666` 发 SIGINT，进程组退出、无残留；未广泛 kill；未触碰 root 8123/022/037/038。**不重放任何 031 工具/推理**。
- 续接条件：本包 release review 生命周期 owner 后，由原 031 owner 从上述 checkpoint 对照现场续接 `fix/lg031-r1`（HEAD `af6640e`，dirty 保真）。

## 7. 剩余预算与复验计数器用法

- 本包真实产品模型预算：**0**（已用 0）。
- 复验 owner 可用全局硬上限：设 `LIGHTGRAVITY_MAX_GENERATION_CALLS=<n>` 后，`GET /api/v1/diagnostics/generation` 读
  `generation.count`（转发前计数，跨 session/reviewer/retry 不归零）、`generation.remaining`；`remaining==0` 时新请求按 429 预算拒绝。
- 开发模型轮/非缓存 tokens：本包在 65 轮 / 120k 硬边界内收尾。

## 8. 任务状态交接（不改他人状态）

- **LG-022**：保持 `in-progress`，待新的独立 QA（本包不自判版本通过）。
- **LG-017**：按真实修复条件应记「待 022 复核」；不因旧 QA 的循环依赖误设阻塞（已在 `backlog/tasks/LG-017.md` 记录 done + 待 022 集中 QA 说明）。
- **LG-037/038**：已交付，**只读未碰**。
