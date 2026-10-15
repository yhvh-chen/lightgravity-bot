# LG-029 实施状态

> owner：`agent:pi-lg029`。分支 `dev/lg029`，worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg029`。
> 性质：**实施记录**。产品模型调用 0；所有 worker 均为程序内替身（真实文件 Store，非 SDK 真模型）。
> 契约版本 `1.6.0`（LG-028 已串行冻结；本轮只实现，不改 docs/08）。

## 步骤日志

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 读取 AGENTS/agent.md、PROJECT/PROGRESS/BACKLOG、docs06 §6、docs08 §4.2/§4.3/§5.1/§6.2/§6.3/§6.5/§7/§11/§13、docs09、LG-028/029/030/031/032 | 完成（只读） |
| 2 | 定位现有实现：`store/store.py`（Task claim/renew/release，无 fence）、`store/entities.py`（未知字段保留）、`coordinator/scheduler.py`（SubtaskClaimer，无 fence）、`coordinator/graph.py`、`coordinator/state.py`、`settings/models.py`、`api/app.py` | 完成（只读） |
| 3 | 确认 fence 为加性可选字段：现有 Store `merge_maps` 保留未知 frontmatter，写 `fence` 不需要改 `store/**` schema | 完成 |
| 4 | 新建 `probes/lg029/STATUS.md` | 完成 |
| 5 | 实现 `backend/lightgravity/collaboration/**`（本包 claim/lease 模块，030 预留独立 peer 模块） | 完成 |
| 6 | 实现 `backend/lightgravity/api/collaboration.py` 路由 | 完成（未挂载 `api/app.py`） |
| 7 | 编写 `tests/collaboration/**` 局部检查 | 完成 |
| 8 | 运行局部检查 + mypy | 见下 |
| 9 | 写 `probes/lg029/INTEGRATION.md` 装配补丁与接线 | 完成 |
| 10 | 交付收尾：复核归属范围（仅 4 路径，无共享文件改动）、复跑 `pytest tests/collaboration`（26 passed）、补 `probes/lg029/REPORT.md` | 完成 |

> 续接注记：上轮主 pi 进程 `agent_settled`（`aborted:false`）正常退出，最终回答被截断为
> "Only new files in th"（日志 `lightgravity-pi-t8ia_oc7.log` 未记录提交）。本轮不重做实现、
> 不重跑全量/mypy（代码未变），仅补充交付收尾与本地提交。

## 检查结果（命令与退出码）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `uv run pytest tests/collaboration -q` | 26 passed | 0 |
| `uv run pytest -q`（后端全量） | 508 passed, 4 skipped | 0 |
| `uv run mypy` | Success: no issues found in 99 source files | 0 |

基线对比：改前后端约 482 passed；本轮 +26 项 LG-029 专项，未改动既有测试。
4 个 skip 为既有 skip（与 LG-029 无关）。

## 参考实现边界（agent.md §9）

- 定位参考：`olav-os/experiments/t-37-human-ai-swarm-skeleton/lib/run-store.ts`
  （`claimNext` 条件写、`lease_owner`/`lease_until`、外部调用结果未知→`recovery_required`）、
  `lib/work-order.ts`（`claimIfUnassigned` 条件写“只有一个并发 claim 成功”契约）。
- **只读参考语义，未复制代码**：本实现用本项目自己的冻结接口（`Store` flock 原子写 +
  `expected_revision` 乐观并发、`fence` 加性字段、`recovery_required` 既有阶段）独立实现，
  未引入参考仓库的 SQLite/运行依赖。未修改参考仓库。
- 许可：未移植参考源码，故不涉及许可/署名；参考仓库文件保留原位未动。

## 真实/替身边界

- **真实**：文件系统 `FileStore`（真实 flock、原子替换、JSONL 追加）、真实多进程/多线程并发竞争、真实 fence 持久化与过期时钟。
- **替身**：worker 身份为程序字符串（无 SDK、无模型），因为本次不接线真实执行；`settings` 开关默认关闭。
- **未接线**：`api/app.py` 装配、Subtask `fence` 的 schema 校验、settings 开关的持久化读写由集成 owner 串行处理；本包提供独立可接入模块，未装配时如实待集成。

## 限制与未知

- 完整 checkpoint skip 未实现（对齐 docs/08 §6.2）：过期后未知副作用只进 `recovery_required`，不自动重放。
- 成本未知：pi 开发代理用量未精确计量；产品模型调用 0。
- 本包不新增依赖、不修改参考仓库。
