# LG-017 返修 R1 — 独立受控 SDK reviewer（收尾）

Owner: pi-lg017-r1（现有 env DeepSeek，主代理只 PM，无嵌套派工，不推送/部署/发布）。
Worktree: `../lightgravity-bot-worktrees/lg017-r1`，branch `fix/lg017-r1`，基点 `c138537`（main 最新）。

> 本文件此前为“待填/0 调用”的过期 checkpoint，现按真实实现与真实探针结果如实纠正。

## 输入基点与缺口（R1 目标）

- main HEAD = `c138537`；LG-017 集成后被复核为 **in-progress**：默认 `ProgramReviewer`
  只是把 LG-009 机器检查在本进程内换名重跑，不是独立的模型/角色/上下文，且无受控 reviewer
  配置与真实装配路径（见 `probes/batch-20261016/INTEGRATION-2.md` §6、`probes/lg017/INTEGRATION.md`）。
- R1 目标：补齐**真实最小受控 SDK reviewer 路径**——独立角色/上下文、经既有 DeepSeek 连接 pin +
  credential_ref 装配、结构化 finding 经程序 `validate_findings` 校验（模型不能判 done）、
  未配置 reviewer 时明确 `unavailable` 且**阻止 accept**；不新增供应商/秘密表单。
- 保留项：返修 Task 总预算跨 Run、SDK 重试/业务返修分离、旧候选证据保留、幂等 reject/ack、
  停止确认、pin/evidence/runtime token/016 反重放。

## 契约变更（本包 owner 已落，additive，MINOR 1.6.0 → 1.7.0）

- `SETTINGS.md` 加性字段 `default_reviewer_connection_ref`（默认 `null`）。
- 新角色常量 `reviewer`（仅用于默认解析/引用，不改变 `state`/`phase`/`acceptance` 枚举）。
- review 事件/报告加性字段 `reviewer_kind` ∈ {`program`,`model`,`unavailable`}、`model_calls`、
  `usage`（未知计 `unknown`，不得当 0）。
- Task `rework` 账本加性字段 `reviewer`、`reviewer_kind`、`model_usage`。
- 不新增端点；`reject` 响应既有加性 `rework` 对象不变。
- docs/08 frontmatter 与 §5.1/§6.1/§6.5/§9/§13 已升 1.7.0；README/PROJECT/agent/docs06 已同步。

## 变更清单（本包 owner 范围）

- `backend/lightgravity/settings/{models,repository,service,router}.py`：reviewer 角色/默认字段（加性）。
- `backend/lightgravity/verify/review.py`：`ModelReviewer`（真实最小受控 SDK 工具无关单轮，
  独立系统提示/上下文，结构化输出经程序校验）。
- `backend/lightgravity/verify/rework.py`：账本/事件如实记录 reviewer kind 与真实 usage。
- `backend/lightgravity/api/bootstrap.py`：按 reviewer 连接是否可解析装配真实 reviewer；否则 `UnavailableReviewer`。
- `backend/lightgravity/coordinator/service.py`：默认 program-only 改为诚实 `UnavailableReviewer`（不称独立复核）；
  无真实 reviewer 时阻止 accept。
- `tests/verify/**`、`tests/coordinator/**`、`tests/settings/**`、`tests/startup/**`、`tests/api/**`：新增/更新。
- `docs/08`、`README.md`、`PROJECT.md`、`agent.md`、`docs/06`：本包唯一 owner 同步。
- `probes/lg017/REFIX-R1.md`、`STATUS.md`。

## 真实命令结果（本地，真实退出码）

- `uv run pytest tests/verify tests/settings tests/startup -q` → **exit 0**，135 passed, 4 skipped。
- `uv run pytest tests/verify tests/coordinator/test_rework_integration.py -q` → **exit 0**，28 passed。
- `uv run mypy backend/lightgravity/verify/{review,rework}.py backend/lightgravity/api/bootstrap.py` → **exit 0**，Success。
- 真实模型探针 `probes/lg017/review_real_probe.py` → **exit 0**，写 `probes/lg017/review_real_probe.json`。

## 真实模型调用计数（前一调用，未重跑）

- **1 次真实 DeepSeek 调用**（`review_real_probe.json`：`status=ran`、`model_calls=1`、
  `reviewer_kind=model`、`outcome=passed`、`validated_outcome=passed`、证据 `out/result.txt`
  含 `hello review`、`usage={"unknown":["usage"]}` 即 **usage unknown/成本部分覆盖**）。
- 本次续接收尾 **新增产品模型调用 0**：未重放成功探针、未盲目重放工具/模型。
- 产物预算：原计划最多 2 次，实际真实调用 1 次。

## 已知限制 / 剩余门

- **独立集中 QA（LG-022）仍未通过**；本包不自评完整版本 pass，状态 `in-progress`（待 022）。
- 真实多 worker 隔离、浏览器路径未在本包覆盖。
- 收尾修复：`validate_findings` 重建报告时曾丢失 `reviewer_kind`/`model_calls`/`usage`，已保留并加回归测试。
