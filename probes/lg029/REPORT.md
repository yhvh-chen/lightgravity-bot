# LG-029 交付报告（简洁版）

> owner：`agent:pi-lg029`｜分支 `dev/lg029`｜状态：**in-progress（待唯一 owner 整合装配）**
> 契约版本 `1.6.0`（LG-028 已冻结，本轮不改 docs/08）。产品模型调用 0。

## 1. 变更（仅归属范围）

| 路径 | 内容 |
|---|---|
| `backend/lightgravity/collaboration/{__init__,models,errors,discovery,lease,service}.py` | 发现投影、原子领取、租约/fence、幂等、默认关闭策略；`peer.py` 为 LG-030 预留空壳（`PEER_MODULE_IMPLEMENTED=False`） |
| `backend/lightgravity/api/collaboration.py` | 冻结端点路由（discoverable / claim_requests / lease renew / release），**未挂载** |
| `tests/collaboration/**` | 26 项局部检查：并发竞争、权限/能力/依赖/预算拒绝、过期 fencing、cancel/restart、默认关闭、API 层 |
| `probes/lg029/{STATUS,INTEGRATION,REPORT}.md` | 实施记录、装配补丁、本报告 |

未修改任何共享文件（`api/app.py`、`settings/**`、`coordinator/**`、`store/**`、`contracts/**`、`docs/**`）；未推送、未合并、未部署。

## 2. 验证证据（本轮复核）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `uv run pytest tests/collaboration -q` | 26 passed | 0 |
| `uv run pytest -q`（后端全量，上轮） | 508 passed, 4 skipped | 0 |
| `uv run mypy`（上轮） | no issues in 99 source files | 0 |

4 skip 为既有 skip，与 LG-029 无关。复核未改动代码，未重跑全量/mypy。

## 3. 真实 / 替身边界（不得当作完成）

- **真实**：文件系统 `FileStore`（真实 flock、原子替换、JSONL 追加）、真实多进程/多线程并发竞争、真实 fence 持久化与过期时钟。
- **替身**：worker 身份为程序字符串（无 SDK、无真实模型），因本包不接线真实执行。
- **未接线/待装配**（交集成 owner 串行处理，见 `INTEGRATION.md`）：
  1. `api/app.py` 未挂载 collaboration 路由；
  2. `settings/**` 未接受/写入三个开关字段（读取已容错回落为关闭）；
  3. `coordinator/**` 未改用 `LeaseManager`，默认确定性路径不变；
  4. Subtask `fence` schema 静态校验为可选项，未加入 `store/**`；
  5. `peer.py` 为 LG-030 预留空壳，未实现；
  6. 受控 worker 执行身份注入未实现（端点 `owner` 暂由请求体提供）。
- 完整 checkpoint skip 未实现：过期后未知副作用只进 `recovery_required`，不自动重放。

## 4. 状态与后续

任务保持 `in-progress`，直到唯一集成 owner 完成装配（见 `INTEGRATION.md` §4 建议顺序）；集中 QA 归 LG-032，本包未做版本 QA。已知未接线项不视为已完成能力。
