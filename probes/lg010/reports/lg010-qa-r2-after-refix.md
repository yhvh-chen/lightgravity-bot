# LG-010 独立 QA 复核报告（第 2 轮返修后）

- 判定：**pass / done**
- QA 基点：`ed014c5`（父 `b418dcf`；第 2 轮返修）
- 真模型证据基点：`ffe7a63`（`probes/lg010/evidence/lg010-evidence-r1.json`，未改）
- 候选根版本：契约 1.3.1 core（不冒充 root 的 1.4/1.5 新 feature）
- 本轮新增真实模型调用：**0 次**（真实调用累计 12，来源见下）
- 审查范围：本次 4 文件差异 + 关联验收逻辑 + 现有两轮证据
- 未改产品实现、其它任务或依赖；未读 `.env`、未输出秘密；未 push/deploy。

## 结论

第 2 轮返修的**唯一**新阻断（问题 3：携带 `target_run_id` 的重复 ack 非幂等）已独立确认消除；Graph/SDK/工具/stop 路径零改动，原真实链路核心证据（自动 `awaiting_acceptance`、真实文件/diff/usage、停止释放、正确首次 accept、stale 拒绝）仍适用。LG-010 判 **pass**，`status: done`，已移除 `blocked_by`。

## 真实证据复用（明确来源）

`lg010-evidence-r1.json`（head `ffe7a63`）：真实 DeepSeek（请求 `deepseek-v4-flash`，上游 `deepseek-flash`，未静默回退）经 loopback 代理；交付后自动验证到 `awaiting_acceptance`；停止/释放门真实运行（`all_members_released=true`、`no_member_running=true`）；真实文件 `demo_target.txt=LG010_REAL_CLOSURE`（sha256）；canonical 证据 `evidence:<run>/...@sha256:2fe9...`；版本绑定 accept `200 completed`；stale `409 acceptance_stale`；错 target `409 illegal_transition`；失败案例 `config_invalid` 0 调用。累计真实调用 12/14，`within_cumulative_cap_14=true`。

## 本轮独立执行

| 命令 | 结果 |
|---|---|
| `uv run python probes/lg010/lg010_accept_repro_r1.py` | `duplicate_accept_idempotent=true`；cross-run `409`；stale `409`；`final_phase=completed`（原第 2 轮为 `false`） |
| `uv run python probes/lg010/lg010_accept_repro_r2.py` | `all_pass=true`，11 项安全边界全过 |
| `uv run pytest tests/api/test_tasks_accept_replay.py -q` | 8 passed |
| `uv run pytest tests/api tests/verify tests/coordinator -q` | 135 passed |
| `uv run mypy` | Success: no issues found in 73 source files |

### 安全边界（r2 探针，真实 ASGI app，模型无关）

- 重复 ack（带/不带 target）与首次逐字节一致，ETag 一致；无重复控制写。
- 同 `request_id` 换动作、换 target、跨 Task、stale revision 全部拒绝或按契约返回。
- 跨 Task 同 `request_id` 不误重放。
- 非 loopback 无 token 重复 ack → `401`；带 token 首次与重复一致。
- 存量旧键 `verify:decision:<request_id>`：不逐字命中，但已决定候选仍经 acceptance 状态重放返回一致结果。

## 真实限制

- 未重跑真模型闭环（新增调用 0 次）；真模型结论复用 ffe7a63 证据。
- 幂等键由 `verify:{kind}:{request_id}` 改为 Task 作用域；旧格式未在 docs/ 记录、无 schema 版本，真实运行目录无持久旧键记录，故无迁移遗漏；仅“旧版本进行中写入旧键后重启到本版本”的极端在途场景不再逐字重放（候选已决定时仍一致）。
- 不含完整网页/UI 与全部恢复故障验收（LG-021/LG-022）；仅 openai-compat 后端。
- 安全边界探针使用 Store fixture 预置 `awaiting_acceptance`（`checks` 本版本无 HTTP setter）。

## 证据文件

- `probes/lg010/lg010_accept_repro_r2.py`、`probes/lg010/evidence/lg010-accept-repro-r2.json`（本轮新增，脱敏）。
- `probes/lg010/evidence/lg010-evidence-r1.json`、`lg010-accept-repro-r1.json`、`lg010-check-repro-r1.json`（前序，未改）。
