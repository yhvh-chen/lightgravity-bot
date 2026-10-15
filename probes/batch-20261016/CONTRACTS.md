---
title: "batch-20261016 契约串行冻结与第二批隔离准备 REPORT"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# batch-20261016 — 两条新线契约串行冻结与第二批隔离准备

> 性质：**集成方（唯一共享契约/集成 owner）操作记录**，非产品实现、非 QA、非发布。
> 本轮不 reset/clean/推送/部署/发布；保留全部 dirty、原始记录与既有 worktree。

## 1. 基点与主状态

| 项 | 值 |
|---|---|
| 起始 `main` HEAD | `7928e0f`（Merge integrate/ui-controls into main: LG-013 + LG-016 + LG-027），工作区 clean |
| 起始主线已含 | `7928e0f` + `b2bd5eb`（no-orchestrator 采用、docs/09、LG-028/033 claims）+ bootstrap 后续交付；以实际 Git 为准 |
| 本批结束 `main` HEAD | `9ff71ff` |
| 契约版本 | 起始 `1.5.0` → 结束 **`1.6.0`**（MINOR） |
| 本批产品真实模型调用 | **0** |
| 未执行 | reset / clean / push / deploy / publish；未改 `.env`；未动旧 `/tmp` worktree |

本批 `main` 提交序列（新→旧）：

```
9ff71ff LG-028/033: mark done after serial contract freeze; claim LG-029/034/039
9215a2f LG-028/LG-033: serial freeze two new-line contracts at docs/08 1.6.0
2f35bbc LG-033 preparation: expand contract prep draft and record read-only probe   (cherry-pick of 289a5d1)
dfc3de8 LG-033 preparation: contract prep draft (unfrozen)                          (cherry-pick of a34c915)
6412ba5 LG-028 preparation: freeze-ready collaboration contract draft (unfrozen)    (cherry-pick of e142de9)
6d8418e LG-028 preparation: contract prep draft (unfrozen)                           (cherry-pick of f3e63ad)
141809d LG-017/018/019: claim for second batch implementation
7928e0f Merge integrate/ui-controls into main: LG-013 + LG-016 + LG-027
```

## 2. 两分支归属核对（先 cherry 分析，再精确合入）

- 用 `git merge-base main <branch>` 与 `git log --oneline main..<branch>`、`git diff --stat main...<branch>` 核实：两分支基于**同一 checkpoint `b2bd5eb`**，各含**初稿 + 最终稿**两提交，且**仅各自归属文档**，无交叉文件。

| 分支 | 提交（初稿 → 最终） | 仅改文件 |
|---|---|---|
| `dev/lg028-contract` | `f3e63ad` → `e142de9` | `docs/contracts/LG-028-preparation.md`、`probes/lg028/PREPARATION.md` |
| `dev/lg033-contract` | `a34c915` → `289a5d1` | `docs/contracts/LG-033-preparation.md`、`probes/lg033/PREPARATION.md` |

- 处理方式：**完整 cherry-pick 各自初稿+最终提交**（不遗漏依赖提交），四条 cherry-pick 无冲突。合入后逐文件 `git rev-parse main:<f>` 与 `dev/<branch>:<f>` 一致（4/4 相同）。未只 pick 修改、未重复。

| 文件 | main 与分支 tip sha256（一致） |
|---|---|
| `docs/contracts/LG-028-preparation.md` | `6b940a07d07a35ebdd594b4ef71d0d8d318fe1c6` |
| `probes/lg028/PREPARATION.md` | `622e0e9429e65e2f4fa0920eac6f19d2f23844a0` |
| `docs/contracts/LG-033-preparation.md` | `31b3b176343e4132afef5a203b677a8d9d62315c` |
| `probes/lg033/PREPARATION.md` | `ab5330b4e5383906f3f12f0ba4191fd416694c52` |

## 3. docs/08 串行冻结（唯一 owner，单线）

按 docs/08 §13 变更控制，把两稿收敛为**加性、默认关闭、尚未实现**的候选并**真实升版**：`1.5.0` → **`1.6.0`**（MINOR，非机械沿用）。已登记：

- **LG-028 去中心化协作**：Subtask 加性可选 `fence`（§6.3）；发现/领取/续租/释放/协作端点（§4.3，默认关闭）；事件 `subtask.lease_*`/`subtask.claim_refused`/`collab.*`/`handoff.*`（§5.1）；错误码 `stale_lease`/`claim_refused`（§4.2）；设置开关 `decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`（§6.5，均默认关闭）；协作预算与 `recovery_required` 说明（§6.2）。
- **LG-033 资料摄取/检索**：新实体 `source`/`intake_job`（§6.6）与 ID 前缀（§3.1）；端点 `sources`/`intake`/`search`/`inbox`（§4.3）；事件 `source.*`/`intake.*`（§5.1）；错误码 `source_conflict`/`source_stale`/`index_unavailable`（§4.2）。

保留/未弱化：程序权限与状态权威、预算与验收边界；`connection_pin`/evidence 1.5.0；ack 幂等、自动 verify、runtime token、`recovery_required` 反重放。**“过期 ≠ 停止”与 `fence`/`owner` 语义不弱化**。**完整 checkpoint skip 仍未实现**——在 §6.2、§13 与 §6.6 如实记录。

冻结接口 vs 未实现 API：所有新端点在 §4.3 明确标注“冻结接口（未实现…）”，调用方须以 `404`/`not_ready` 处理；**不伪称可用**。两稿命名与实际代码兼容：`fence` 为 `owner`/`lease_expires_at` 的加性扩展，`source`/`intake_job` 为全新实体，未与既有 `File`/`Run` 冲突；必要处已在准备稿与 docs/08 对齐。展示状态**不加入** Task `phase` 枚举。

版本常量与既有版本测试同步（必要、非大范围重构）：

- `backend/lightgravity/contracts/constants.py`：`CONTRACT_VERSION = "1.6.0"` + 1.6.0 注释。
- `backend/lightgravity/contracts/enums.py`：新增错误码与事件枚举成员（与 docs/08 §4.2/§5.1 一致）。
- `backend/lightgravity/contracts/errors.py`：新错误码 HTTP/retryable 映射（满足 `tests/contracts` 全覆盖约束）。
- `tests/contracts/test_contracts.py`：版本断言更新为 `1.6.0`。

入口同步（减少重复巨大状态段，未重写）：README、agent.md、PROJECT.md、docs/06、docs/09 的契约版本引用更新为 1.6.0，并标注“仅接口、未实现”。

## 4. backlog 专用任务根校验与 CLI claim

- **`olav-tasks tasks digest backlog` → `complete=true`、`diagnostics=[]`**，`counts` 起始 `{todo:19, in-progress:2, done:20}`，结束 `{todo:16, in-progress:3, done:22}`。
- 根目录 `tasks digest .` 仍报 `complete=false` + 12 条诊断，**全部位于未跟踪的历史实验** `probes/agensh-orchestration-r2/runs/t3_evolving__*/subtasks/*.md`（`lease_path: -` 旧问题）。按“根目录原始 probe YAML 不可修改 / 排除原始实验非任务”，**本批未修改这些文件**；backlog 任务根本身 0 诊断。以此为准声明“backlog 专用任务根 complete=true 无诊断”。（根 CLI claim 会因这些非任务文件拒绝，故 claim/digest/ready 使用 `backlog` 项目根。）

CLI claim（同一 `backlog` 根，claim 失败不绕过）：

| 任务 | claim 结果 | assignee | claim 提交 |
|---|---|---|---|
| LG-017 | Claimed | `agent:pi-lg017` | `141809d` |
| LG-018 | Claimed | `agent:pi-lg018` | `141809d` |
| LG-019 | Claimed | `agent:pi-lg019` | `141809d` |
| LG-029 | Claimed（依赖合格后） | `agent:pi-lg029` | `9ff71ff` |
| LG-034 | Claimed（依赖合格后） | `agent:pi-lg034` | `9ff71ff` |
| LG-039 | Claimed（依赖合格后） | `agent:pi-lg039` | `9ff71ff` |

## 5. 隔离 worktree 准备（持久目录，基于同一 claim 提交，不覆盖）

| worktree | 分支 | 基点提交 | 状态 |
|---|---|---|---|
| `/home/yhvh/code/lightgravity-bot-worktrees/lg017` | `dev/lg017` | `141809d`（017/018/019 共同 claim） | clean，未实施 |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg018` | `dev/lg018` | `141809d` | clean，未实施 |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg019` | `dev/lg019` | `141809d` | clean，未实施 |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg029` | `dev/lg029` | `9ff71ff`（029/034/039 共同 claim） | clean，未实施 |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg034` | `dev/lg034` | `9ff71ff` | clean，未实施 |
| `/home/yhvh/code/lightgravity-bot-worktrees/lg039` | `dev/lg039` | `9ff71ff` | clean，未实施 |

- LG-017/018/019 **未实施**（按本包范围只准备），由主代理后续分别派工；LG-029/034/039 依赖合格后同样只准备、先不实现。
- 旧 `/tmp` worktree、`lg028-contract`/`lg033-contract`/`ui-controls`、历史实验分支**全部保留**，未覆盖。

## 6. 任务状态

| 任务 | 状态 | 依据 |
|---|---|---|
| LG-028 冻结去中心化协作契约 | **done** | 四项验收条件全部由 docs/08 1.6.0 冻结满足；准备稿+执行记录保留；集中 QA 归 LG-032 |
| LG-033 冻结资料摄取与检索接口契约 | **done** | 四项验收条件全部由 docs/08 1.6.0 冻结满足（含“按 §13 冻结并升版”）；集中 QA 归 LG-040 |
| LG-017/018/019 | in-progress | 已 claim，worktree 就绪，**未实施**，待主代理派工 |
| LG-029/034/039 | in-progress | 依赖合格后已 claim，worktree 就绪，**未实施**，待主代理派工 |

## 7. 真实检查结果（局部，timeout ≤ 120s）

| 检查 | 命令 | 结果 |
|---|---|---|
| 契约与 API 测试 | `.venv/bin/python -m pytest tests/contracts tests/api -q` | **65 passed**（退出码 0） |
| 类型检查 | `.venv/bin/python -m mypy` | **Success: no issues found in 91 source files**（退出码 0） |
| backlog 任务根校验 | `tasks digest backlog --json` | `complete=true`、`diagnostics=[]` |
| worktree 核对 | `git worktree list` / `git -C <wt> status` | 6 个新 worktree clean，基点为对应 claim 提交 |
| cherry-pick 一致性 | `git rev-parse main:<f>` vs `dev/<branch>:<f>` | 4/4 文件 sha256 相同 |
| 文档链接 | 对 docs/08、docs/09、docs/06、README、agent、PROJECT 逐一解析相对 `.md` 链接 | 无缺失 |

**未运行 / 部分覆盖**：未跑后端全量 `pytest`、前端构建/测试、真实浏览器、真实模型调用（本批产品调用 0）；未跑全量 bootstrap 复检（已通过项不重复）。版本常量影响的定向检查（`tests/contracts`、`tests/api`、`mypy`）已覆盖。

## 8. 未测 / 成本 / 限制

- 新增端点/实体/事件/开关均为**接口冻结点**，**未实现、未运行时验证**；去中心化默认关闭。
- 完整 checkpoint skip **未实现**；恢复仅依赖已落盘证据与保守 `recovery_required`。
- 两线实现（LG-029～031、LG-034～041）与集中 QA（LG-032、LG-040）**均未开始**。
- 本批 pi 开发代理 token/费用**未知**，不做推算；产品真实模型调用 **0**；无新网络探针。
- 未推送/部署/发布；本地提交与 worktree 均保留。

## 9. 后续（由主代理分别派工，共享文件仍串行接线）

1. 由主代理基于 `141809d` 向 `lg017`/`lg018`/`lg019` 分别派工（接口 owner 见各任务正文）；共享 `coordinator/**`、`api/**`、`store/**` 仍由集成者串行接线。
2. LG-029/030 可在 `lg029` 等独立 worktree 并行，接口以 docs/08 1.6.0 §4.3/§5.1/§6.3 冻结点为准；LG-034/035/036 资料线以 §4.3/§6.6 为准。
3. 实现整合后集中 QA：LG-032（去中心化）、LG-040（资料与 Embedding）；LG-039 中文 ASR 质量不合格**不阻塞** LG-040。
