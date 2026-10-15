# LG-030 实施状态

> owner：`agent:pi-lg030`。分支 `dev/lg030`，worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg030`。
> 性质：**实施记录**（in-progress）。产品模型调用 0；worker 均为程序内替身（真实文件 `FileStore`，
> 非 SDK 真模型）。契约版本 `1.6.0`（LG-028 已串行冻结；本轮只实现，不改 docs/08）。

## 基点与授权

- 基点：`dev/lg030` HEAD `61fad69`（integrate batch2，含 LG-029 已装配的 collaboration 路由），工作区 clean。
- LG-030 已 claim（`assignee: agent:pi-lg030`，`status: in-progress`）；依赖 LG-028（契约 done）、LG-029（done 待版本 QA）均已满足。
- 授权范围（owner）：`backend/lightgravity/collaboration/peer.py` 及必要新 `handoff`/`context` 模块、
  `backend/lightgravity/api/collaboration.py` 的 peer 端点最小面、`tests/collaboration/test_peer*`、
  `probes/lg030/**`、`backlog/tasks/LG-030.md`。禁改 claim/lease/discovery 已有模块、coordinator/verify/
  adapter/store/contracts/api/app.py/settings/frontend/共享 docs。共享装配点（`api/app.py` 若需新挂载）
  只写 `INTEGRATION.md` 交唯一 owner。

## 步骤日志

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 读取 AGENTS/agent.md、PROJECT/PROGRESS/BACKLOG、docs06 §6、docs08 §4.2/§4.3/§5.1/§6.2/§6.3/§6.5、docs09、LG-028/029/030/031 与现有 collaboration 代码 | 完成（只读） |
| 2 | 核 claim 与基点、检查工作区、确认 LG-029 已装配与 `peer.py` 预留空壳 | 完成 |
| 3 | 新建 `probes/lg030/STATUS.md` | 完成 |
| 4 | 实现 `collaboration/handoff.py`（带 hash 产物引用模型与校验） | 完成 |
| 5 | 实现 `collaboration/context.py`（授权摘要/因果绑定值类型） | 完成 |
| 6 | 实现 `collaboration/peer.py`（受控同伴请求、幂等、权限/预算/超时/容量、因果、注入文本不执行） | 完成 |
| 7 | `api/collaboration.py` 加 peer 端点（`POST/GET /runs/{id}/collab_requests`） | 完成 |
| 8 | 编写 `tests/collaboration/test_peer*.py` 局部检查 | 完成 |
| 9 | 运行局部检查 + mypy | 见下 |
| 10 | 写 `probes/lg030/{REPORT,INTEGRATION}.md`；更新 LG-030 任务验证记录 | 完成 |

## 检查结果（命令与退出码）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `uv run pytest tests/collaboration -q` | 见 REPORT.md | — |
| `uv run mypy` | 见 REPORT.md | — |

## 真实/替身边界

- **真实**：文件系统 `FileStore`（真实 flock、原子替换、JSONL 追加）、真实 HTTP 协议链
  （FastAPI 路由 + `ApiContext` + 真实 `FileStore`）、真实 sha256 摘要校验与 `evidence:` 引用解析、
  真实多线程并发请求幂等竞争。
- **替身**：worker 执行身份为程序字符串（`owner`），因受控执行身份注入归 LG-031；`owner` 暂由请求体提供，
  与 LG-029 同一边界（HTTP body 不扩大权限，但 029/030 的端点自身尚不做身份认证）。
- **未实现（归 LG-031，不伪称已完成）**：SDK 真实执行身份注入、Graph 接线（`LeaseManager` 替换
  `SubtaskClaimer`、collab 路由进 coordinator 图）。

## 限制与未知

- 完整 checkpoint skip 未实现（对齐 docs/08 §6.2）：过期后未知副作用只进 `recovery_required`，不自动重放。
- 受控执行身份（HTTP body 自报 `owner`）缺口如实记录，归 LG-031 统一解决；本包不默认信任 body 身份，
  但端点的本地访问边界仍由既有 `AccessPolicy`（loopback + 必要时 `X-LG-Token`）承担。
- 成本未知：pi 开发代理用量未精确计量；产品模型调用 0。
- 本包不新增依赖、不修改参考仓库。
