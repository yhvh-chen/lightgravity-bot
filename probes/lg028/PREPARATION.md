# LG-028 契约准备执行记录

> owner：`agent:pi-lg028`。性质：**准备记录**，非契约冻结、非功能实现、非 QA。
> 分支 `dev/lg028-contract`，基点 `b2bd5eb`。只写本文与
> [docs/contracts/LG-028-preparation.md](../../docs/contracts/LG-028-preparation.md)。

## 1. 输入基点

| 项 | 值 |
|---|---|
| 分支 | `dev/lg028-contract` |
| 基点提交 | `b2bd5eb`（checkpoint: preserve main dirty evidence, no-orchestrator adoption, docs/09, LG-028/033 claims） |
| HEAD 含 main | 是（`git merge-base --is-ancestor main HEAD` 通过） |
| 相对 main 差异 | 仅 `docs/contracts/LG-028-preparation.md`（准备稿） |
| 主 worktree `/home/yhvh/code/lightgravity-bot` | 未触碰（`b2bd5eb [main]`） |
| 契约版本 | `1.5.0`（未改） |
| LG-028 领取 | `status: in-progress`、`assignee: agent:pi-lg028`（claim 提交 `b2bd5eb`） |

## 2. 读取的输入（只读）

- AGENTS.md、agent.md、PROJECT.md、PROGRESS.md、BACKLOG.md
- docs/06-roadmap.md（第 6 节去中心化排期）、docs/08-interface-contract.md（1.5.0 全文）、docs/09-source-intake-and-retrieval.md（§8）
- backlog/tasks/LG-028/029/030/031/032、LG-016/017/018
- 现有实现只读引用：`backend/lightgravity/store/store.py`（`claim`/`renew`/`release`）、`backend/lightgravity/store/protocol.py`、`backend/lightgravity/coordinator/scheduler.py`（`SubtaskClaimer`/`ArtifactHandoff`）、`backend/lightgravity/coordinator/graph.py`（节点领取/交接）
- 参考实现（agent.md §9 先定位）：Olav OS `run-store.ts`、`scheduler.ts`（lease/`recovery_required`/fencing 外部调用）；只读语义，未修改参考仓库

## 3. 执行的命令与结果

| 命令 | 结果 |
|---|---|
| `git branch --show-current` | `dev/lg028-contract` |
| `git worktree list` | HEAD 在 `dev/lg028-contract`；主 worktree 保持 `b2bd5eb [main]` |
| `git merge-base --is-ancestor main HEAD` | 退出码 0（HEAD 含 main） |
| `git diff --stat main -- docs/ probes/ backlog/` | 仅 `docs/contracts/LG-028-preparation.md` |
| `rg` 检索 store/coordinator 租约实现 | 确认现有 owner/lease 语义、无 fence |

- 未运行产品测试、构建、类型检查（本任务为契约准备，非产品变更）。
- 未运行模型调用（产品/开发模型调用均为 0）。

## 4. 交付物

- `docs/contracts/LG-028-preparation.md`：完整准备稿，覆盖 LG-028 四项验收条件，含
  可发现范围、能力匹配、候选请求/程序原子授权、lease/fencing/revoke、竞争/过期/暂停取消/
  崩溃恢复/幂等交接、同伴交接权限与预算、版本化端点/事件/错误/开关/迁移回退、
  docs/08 逐条对接清单、LG-029/030/031 owner 拆分、当前实现差距声明。
- 本文：执行基点、命令、限制与未知项记录。

## 5. 限制与未知项

- **未冻结**：不升 `CONTRACT_VERSION`；建议版本由集成者按实际落地变更判定（加性→MINOR，改迁移/错误语义→MAJOR）。
- **未实现**：本稿为契约准备；无 fence/发现投影/claim/collab 端点/协作预算/开关落地。
- **不可假设**：完整 checkpoint skip 未实现；SDK 内部委派默认关闭；无独立编排为默认。
- **未知项**：最终字段名/端点路径/开关键名有待 docs08 owner 冻结确认；租约默认时长（建议 300s）需实现时按真实验证校准。
- 成本来源：本任务产品模型调用 0；pi 开发代理用量未精确计量，费用未知。
- 无逐任务 QA、无产品全量测试（符合 agent.md §1 与本次授权）。

## 6. 后续（待串行冻结）

- LG-028 保持 `in-progress`；由**单一 docs08 owner**按 docs/08 §13 变更控制串行冻结并处理共享契约冲突。
- 冻结后 LG-029/030 可在独立 worktree 并行（接口以准备稿 §5 为准），LG-031 串行集成，LG-032 集中 QA。
