# LG-018 报告 — 隔离 worktree 与并行整合

- 任务：[LG-018](../../backlog/tasks/LG-018.md)，实施者 `agent:pi-lg018`
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg018`（branch `dev/lg018`）
- 基点 commit：`141809daf8552fd43371baccd5d3f95697e955d0`
- 环境：`uv` + Python 3.12、真实本地 `git 2.53.0`
- 本包真实模型调用：**0**（SDK 真实模型端到端留 LG-022）

## 交付内容

### 新增产品包 `backend/lightgravity/workspaces/`

- `git.py`：边界化的 git 子进程运行器。`GIT_CONFIG_NOSYSTEM=1`、
  `GIT_CONFIG_GLOBAL/SYSTEM` 指向隔离位置、`core.hooksPath` 指向空目录、
  子进程环境为 allow-list（继承的秘密环境变量不转发）。
- `manager.py`：`WorktreeManager` / `WorktreeSession`。真实 `git worktree add`
  在**冻结 base commit** 上为每个写节点建独立 worktree/branch；`integrate`
  在独立 integration branch/worktree 合并候选；冲突真实暂停并保留；
  `cleanup` 仅在**确认停止且分支已显式交付**时删除；路径越界/符号链接/`.git`
  组件一律拒绝。
- `provider.py`：`WorkspaceProvider` 协议 + `GraphWorkspaceProvider`，作为
  dispatcher 的最小注入 seam；非 git / 越界工作区返回 `None`（保守串行，不假并行）。

### 最小接线 `coordinator/graph.py`（owner 文件内）

- `GraphDispatcher(..., workspaces=...)` 加性构造参数（默认 `None`，行为不变）。
- 调度前对每个 `write` 节点创建隔离 worktree；`_build_request` 把
  `ExecuteRequest.workspace_path` 设为该节点自己的 worktree；`_config_drift`
  与编译用同一路径（`CompiledAgentConfig.config_hash` 不含 `workspace_path`，
  故 LG-016 `reuse_identity` 反重放守卫不受影响）。
- `_writer_key`：已隔离的写节点以节点为 writer key，允许两个隔离写节点并发；
  未隔离时保持原单 writer 串行。`build_graph_dispatcher` 同步透传 `workspaces`。

### 未触碰的共享装配点

`api/bootstrap.py`（共享，集成者所有）未改。真实装配调用点、字段语义、可选
清理/整合接线与边界声明见 [INTEGRATION.md](../INTEGRATION.md)。**默认仍保守**：
不注入 provider 时不启用并行，`max_parallel` 不擅自提高。

## 真实验证（真实本地 Git，非 mock）

- `uv run pytest tests/workspaces -q` → **14 passed**（下述全部真实临时 Git 库）。
  - 并行写隔离：两写节点获得不同真实 worktree，互不可见对方文件；
  - 非冲突整合：候选 merge 到 integration branch，final candidate commit 以
    冻结 base 为祖先，元数据记录 base commit 与各节点 branch；
  - 冲突暂停：同文件冲突 → `conflicted=True`、真实冲突路径 `code.txt`，
    worktree/ conflicted 树保留，`cleanup(confirmed_stop=True)` 对未交付候选
    返回 `[]`（不清理）；
  - 用户 dirty HEAD 保留：staged/untracked/分支/HEAD 均未被改动；
  - 停止锁：未确认停止时 `cleanup` 抛 `cancellation_unconfirmed`（不释放锁）；
    确认停止但未交付仍保留；显式交付后才可删除；
  - 恢复保留：新 `WorktreeManager` 实例（模拟重启）仍能列出 paused worktree
    与非提交的 WIP；元数据 `paused=true`；
  - 边界：仓库 hook 不执行、继承秘密环境不转发、`.git`/符号链接/越界拒绝、
    非 git 工作区明确拒绝而非伪造。
- `tests/workspaces/test_graph_isolation.py`：真实 `GraphDispatcher` + 真实
  worktree，两写节点 `ExecuteRequest.workspace_path` 不同且 `peak_concurrent==2`；
  不注入 provider 时共享同一 workspace 且 `peak_concurrent==1`（保守串行）。
- `probes/lg018/lg018_worktree_probe.py`（可重跑真实 Git 探针）→
  `passed=true`，证据 [evidence/lg018-worktree-evidence.json](../evidence/lg018-worktree-evidence.json)：
  隔离路径不同、原工作区 clean、candidate 以 base 为祖先、冲突暂停并保留。
- `uv run mypy` → **Success: no issues found in 95 source files**。
- `uv run pytest -q`（全量一次）→ **496 passed, 4 skipped**。
- 定向回归：`pytest tests/coordinator tests/control -q` → 139 passed。

## 真实 vs 替身

- **真实**：所有 worktree/branch/merge/冲突/dirty/锁/路径边界证据均来自真实
  本地 Git 仓库与真实 `WorktreeManager`；dispatcher 接线测试用真实
  `GraphDispatcher` + 真实 worktree。
- **替身**：测试中的 “executor” 是进程内 fake（不调模型、不调 SDK）；它只把
  文件写进分到的 worktree，用于证明隔离与并发调度。真实 SDK/DeepSeek 端到端
  与真实模型调用 **未在本包执行**，留 LG-022。

## 未测 / 限制（不夸大）

- 不是安全沙箱：worktree 仍共享对象库与宿主进程；不能约束恶意进程。凭证边界
  仍属 adapter 的 loopback 代理与工具策略（docs/08 §8.1）。
- Git 子进程环境已 allow-list 化，但 executor 自身的模型/工具子进程不在本包
  边界内。
- `api/bootstrap.py` 未接线：本包只提供真实、可测的隔离与最小 seam，实际并行
  需集成者按 INTEGRATION.md 注入 provider 后再提升 `max_parallel`；未接线时保持
  保守串行，不宣称产品已启用并行。
- 候选整合/清理尚未接入 `verify/**`（LG-017 owner），故“整合候选 → 验收”的
  端到端编排由集成者串行接线。
- 未 push、未 deploy、未合并、未改共享 docs08/README/PROJECT/PROGRESS。

## 文件 owner 与交付

新增：`backend/lightgravity/workspaces/**`、`tests/workspaces/**`、
`probes/lg018/**`。修改：`backend/lightgravity/coordinator/graph.py`、
`coordinator/dispatcher.py`（未改，仅引用）。未改 `coordinator/service.py`、
`verify/**`、`api/tasks.py`、`api/app.py`、frontend、根 pyproject。
