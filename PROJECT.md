---
title: "LightGravity Bot 项目手册"
doc_type: handbook
category: project
updated: "2026-10-15"
---

# LightGravity Bot 项目手册

> 更新：2026-10-15。阶段：LG-001 契约已冻结（docs/08 当前 1.5.0：1.1.0 将首版真实后端定为 DeepSeek，1.2.0 登记 LG-008 加性控制字段，1.3.0 登记 LG-009 验收字段/端点与全局对话，1.3.1 将 LG-014 文件上传/下载标为已实现并澄清证据引用语义，1.4.0 登记 LG-015 受控资源写入/Team 端点与 Task 消息 `resource_proposal` 字段，1.5.0 登记 LG-020 的 `connection_pin` 加性字段与 canonical evidence 预览/下载端点），LG-002 工程骨架可运行，LG-003 SDK 探针完成（核心能力经真实 DeepSeek 实测通过；Gemini/Vertex 未验收，`search_web` 不可用），LG-004 存储层、LG-005 角色/SDK 资源配置编译（已将 `google-antigravity==0.1.22` 锁定为产品依赖）、LG-006 正式 executor + 产品侧 loopback 认证代理（真实 DeepSeek 验证：文件/diff、结构化结果、用量、预算、会话恢复、确认取消；真实调用 12，进程无残留）、LG-007 消息路由与 Task 队列、LG-008 自动组队与依赖调度、LG-009 产物验证与人工验收、LG-011 前端壳层、LG-012 查询 API 与持久事件订阅、LG-025 模型设置与凭证后端、LG-026 Settings 模型接入页面、LG-014 Files 上传/下载与任务证据预览、LG-015 Team/Resources 管理视图与受控资源写入、LG-020 本地启动/停止与一体分发入口均已完成并整合到 `main`；其中 **LG-010 最小真实开发闭环已通过独立版本 QA（pass/done）**，其余 16 项均**待版本 QA**。LG-013 实施已按真实 API 接线完成并置 `done`（Chat/Board 接入真实历史与 phase，新增 `coordinator/dialogue.py` 无工具直答，未配置默认协调连接/凭证时诚实 `unavailable`，经 `create_app(responder=...)` 注入且保留现有 Resource/Verifier 端口），但**完整浏览器 HTTP 业务路径仍归 LG-021/022**，不等于完整浏览器 HTTP 端到端；LG-027 已就设置/凭证生命周期完成独立专项版本 QA **pass**，其范围限于设置/凭证的 CLI/HTTP 与浏览器渲染，**不等于完整浏览器 HTTP 端到端**，且真实调用计数产品未暴露（报告中的旧上限 5 + 恢复硬上限 4 仅为指令/运行预算，不视为已验证实际调用次数或精确上界）。主前端构建现已挂载 Settings、Files、Team 与 Resources 视图，分别接线 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*` 与 `/api/v1/resources/*`；Files 上传复用 LG-026 运行时 token helper 注入 `X-LG-Token`，无 token 时上传如实返回 `unauthorized`；Team/Resources 受控修改经 Task 对话 `resource_proposal` 提议（sensitive 授权、`message_id` 幂等、`expected_revision` 版本检查，结果写回同一 Task 对话，不创建 Run/不等 worker、不热替换活跃 Member 配置）。LG-020 提供 `lightgravity start/stop/status/init`、默认 loopback、token 内存握手与 `index.html` 注入、Host/Origin 守卫、敏感写默认拒绝、缺认证可读历史/设置；首启幂等种子 `lg-default-worker`（有界文件工具 `view-file`/`create-file`/`edit-file`，无 `run-command`/web 无边界工具），Settings-only 建连接/存凭证/静态测试/设默认后新 Task 可达 executor，Run/Member 固定非秘密 `connection_pin`；canonical evidence 产物经 Task 产物 API（`GET /tasks/{id}/artifacts`、`.../artifacts/content`、`.../artifacts/download`）由 Task/Run evidence resolver 授权预览/下载，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符。敏感写仍由 `LocalAccessPolicy` 默认拒绝。旧 QA“浏览器全 HTTP/fetch 阻断”结论已被 root `probes/browser-diagnostics` 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，**仅顶层 `Page.navigate` 到 `http://` 在本机 headless Chrome 挂起**；原报告作为历史保留（不复述错误当新事实）。不宣称全部页面可用。首版唯一真实执行路径为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek。集成后 `create_app` 已装配 Store/Coordinator/VerificationService 并挂载 `/api/v1` 路由；accept/reject 合并进 API actions，只读 `GET /tasks/{id}/acceptance` 独立挂载，新增单例全局对话 `GET/POST /api/v1/conversations/global/messages`；默认执行器仍是诚实的 `UnavailableExecutor`（未伪装可执行）。真实 SDK 端到端、浏览器验收分别留 LG-010、LG-021/022；LG-010 最小真实开发闭环已经独立版本 QA 复核 **pass/done**（`probes/lg010/reports/lg010-qa-r2-after-refix.md`）：首轮两项阻断（executor 绝对 `diff_ref` 被机器检查误判、交付完成后未自动触发验证）已返修，第 2 轮复验发现的重复 ack(`target_run_id`) 非幂等问题已按 Task 作用域幂等键返修并经独立复验确认消除，`status: done`、`blocked_by` 已移除。**该 QA 只覆盖契约 1.3.1 core 的最小后端闭环（真模型证据基点 `ffe7a63`，真实调用累计 12/14），并非 1.5 全功能 QA**：LG-015/LG-020 的新资源/启动功能仍未验收，分别留 LG-027 与 LG-021/LG-022。27 项任务见 BACKLOG.md；人员、预算、日历日期与部署目标未确定。代码仓库已于 2026-10-14 初始化 Git 并推送 `main` 到内部 Gitea。

## 目标

做一个比 Olav OS 更轻量的 AI 任务助手：用户通过对话提出目标，系统按需组队、执行、验证、交付，在项目目录中保存可复核的结果。

首版用开发任务验证闭环；研究、文档和运维是后续扩展方向，不作为当前已支持能力。

## 优先级原则

1. 先跑通真实任务和交付闭环，再扩展角色、并行度与后端。
2. 保留有效设计思想，组件复用由依赖和成本决定；不因旧代码存在而强制复用，也不为重写而重写。
3. 项目文件是持久事实源，看板与查询索引可重建。
4. 任务执行、验证通过、人验收分别记录，不能相互替代。
5. 小规模临时组队优先，不引入长期员工与复杂组织治理。
6. Task 是派发与用户对话入口；Markdown＋frontmatter 是任务与资源配置事实源，Run 为内部执行尝试。

## 完成的定义

实现完成至少需要：消息分类与轻路径有效；交付指令形成可校验计划；团队按需创建；任务按依赖执行；产物、diff 和验证结果可查看；失败能够进入有限返修或等待用户；待验收时释放执行资源、人工验收后记录完成；下一次指令可以继续原 Task 或创建新 Task。队列、执行中控制消息、网页断线重连与待决通知需要实际验证。

取消、超时、进程异常、并发写入与恢复行为需要明确验证。文档、界面、模拟 executor 或 worker 的成功回复，都不能单独证明闭环已完成。

## 工作约定

- 2026-10-14 本轮工作范围是保存设计与开发约束，尚未开始实现；后续实施按用户的新指令推进，不能把此阶段记录作为永久授权限制。开发规则以根目录 agent.md 为准。
- 写明确认事项、建议默认值和待验证假设，不能把候选接口写成已交付能力。
- 原始资料与运行证据保留；清理临时队伍不得删除未交付成果。
- 实施前核查待复用文件的依赖、许可与署名要求，固定依赖版本。
- 产品运行时的 SDK worker 与开发本项目时使用的代理是两件事；本设计不规定宿主开发代理的派工方式。
- 项目已于 2026-10-14 初始化 Git，默认分支 `main`，并推送设计文档、开发 backlog 与 `.agents/skills/` 技能文件；提交历史自该次初始入库开始。尚无产品代码、构建或运行产物。

## 决策日志

### 2026-10-15：整合 LG-013（Chat/真实看板）与 LG-027（Settings/凭证专项 QA）

- 基点：本整合在独立 worktree `/home/yhvh/code/lightgravity-bot-worktrees/ui-controls`（branch `integrate/ui-controls`，基点 `2ecafdf`，非 root `main`）进行；root `main` 由 Firefox 诊断 writer 只改 `probes/`，LG-016 在其 branch 补 guard，二者本轮均未触碰。
- 整合：按序 `git cherry-pick -x e3a6818` → `2d31831`（LG-013 接入 Task Chat 与真实看板）、`354def4` → `b7a0f7c`（LG-013 收尾置 done）、`fbd8a0e` → `a6d9f3c`（LG-027 QA 报告），三提交均无冲突，保留原作者与消息。
- 保留项核对：Files/Settings/Team/Resources/Runtime、default pin、canonical evidence、自动 verify、ack 幂等均保留；`create_app` 的现有 Resource/Verifier 端口与新加 `responder` 注入共存；`coordinator/dialogue.py` 为新增无工具单只读路径，无默认协调连接/凭证时返回诚实 `unavailable`，不创建 Task/Member、不写控制文件。未接手 LG-016（不改其状态/候选 guard），未领取任务，未 push/deploy，未读 `.env`。
- 文档同步：README/PROJECT/docs/06 记录 013 实施 done（**完整浏览器业务路径仍归 021/022**）、027 设置/凭证专项 pass（**仅设置/凭证 CLI+HTTP + browser 渲染范围**）。**两者均不等同完整浏览器 HTTP 端到端**。
- 精确更正：旧 QA“浏览器全 HTTP/fetch 阻断”已被 root `probes/browser-diagnostics` 推翻——真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，**仅顶层 `Page.navigate` 到 `http://` 在本机 headless 挂起**；原报告按历史保留，只追加更正引用，不复述错误当新事实。
- 调用计量诚实性：027 报告中的“旧上限 5 + 恢复硬上限 4”只是**指令/运行预算**（`model_call_cap=1` 为 harness 设置），产品未暴露调用计数器，无独立计数即记 **未知**，不写成已验证实际硬上界或精确数。
- 验收（整合执行者，非 QA）：`uv run pytest -q` → **410 passed, 1 skipped**（含 LG-013 定向 21 项、LG-027 e2e 设置 9 项；唯一 skip 为需 `LG020_REAL_DEEPSEEK=1` 显式启用的 gated 真实检查）；`uv run mypy` → **Success: no issues found in 86 source files**；`frontend` `npx tsc --noEmit` 通过、`npx vitest run` **75 passed / 11 files**、`npm run build` 成功（90 modules，CSS 30.71 kB / JS 252.03 kB）；任务 frontmatter 以 YAML 解析校验 27 文件结构（`tasks` CLI 本环境不可用，已如实注明）。真实 DeepSeek 调用本轮为 **1 次有界只读直答探针**（`model_calls_cap=1`，证据 `probes/lg013/evidence/lg013-direct-answer-probe.json`）：临时 data 正确配置 `default_coordinator` 连接后，真实模型回答 `"Four."`，且不创建 Task/Run/Member、不写控制文件、workspace 无写入、无秘密泄漏；产品未暴露调用计数器，故不宣称精确总量，不把 unavailable/mock 当真 AI。
- 限制：本轮为整合与文档同步，非 LG-021/022 版本 QA；不宣称完整浏览器 HTTP 端到端或首版完成。仅清理本包签名的临时产物/PID，未杀父/兄弟/root 8123，未改 LG-016。

### 2026-10-15：整合 LG-010 独立重验链（QA 判定 pass/done）

- 基点：上一整合结束于 `66f03d5`（LG-020 + 契约 1.5.0），主工作区 clean。LG-010 独立重验链在 `qa/lg010-r2` 上按序列出 `b418dcf`（第 2 轮独立重验失败报告）→ `ed014c5`（第 2 轮返修：重复 ack 按 Task 作用域幂等键）→ `fd09994`（返修后独立 QA pass）；本轮按顺序精确 `git cherry-pick` 这三提交 → `3a315d1`（b418dcf 报告，QA 作者 `lg010-qa`）→ `0d3278d`（ed014c5 返修）→ `9993ec4`（fd09994 复核），三提交均无冲突，保留原作者与消息。
- 冲突最小化依据：三提交的父链基点 `ffe7a63` 已在 `main` 上，且 `main` 自 `ffe7a63` 起从未改动它们涉及的四个路径（`backend/lightgravity/api/tasks.py`、`backend/lightgravity/verify/service.py`、`backlog/tasks/LG-010.md`、`probes/lg010/**`），经 `git diff` 核实与 `main`~`ffe7a63` 逐字节一致，故 cherry-pick 全部 clean。
- 不取旧树核对：`qa/lg010-r2` 分支树早于 root 的 LG-015/LG-020（缺 `runtime/**`、`api/bootstrap.py`、`cli.py`、种子/`connection_pin`/canonical evidence 等），因此**只取三提交，未 merge/integrate 该分支树**；`git diff --name-status 66f03d5 HEAD` 确认**零删除**，`runtime/**`、`tests/startup/**`（含 `EVIDENCE.md` 真实 dist 证据）、canonical evidence 预览/下载均已保留。
- LG-010 任务状态：三提交中的 QA 报告已将 `status` 置 `done` 并移除 `blocked_by`（依独立 QA 原文），文档不再叙述“in-progress/blocked”。QA 核心证据候选：真模型证据基点 `ffe7a63`（`probes/lg010/evidence/lg010-evidence-r1.json`）与返修基线 `ed014c5`；真实模型调用累计 **12**（硬上限 14，`within_cumulative_cap_14=true`，本轮新增 0 次）。**该 QA 只覆盖契约 1.3.1 core 的最小后端闭环，不是 1.5 全功能 QA**；当前资源/启动（LG-015/020）仍待 LG-027 与 LG-021/LG-022。
- 验收（整合执行者，非 QA；本轮 SDK 路径零改故未重跑真模型/全浏览器）：`uv run pytest -q` → **389 passed, 1 skipped**（含新增 `tests/api/test_tasks_accept_replay.py` 8 项）；`uv run pytest tests/api tests/verify -q` → 36 passed；`uv run mypy` → **Success: no issues found in 85 source files**；`tasks validate` → **OK: 27 tasks, no diagnostics**。真实 DeepSeek 调用本轮 **0 次**。
- 就绪门：`tasks ready` complete、无 diagnostics，就绪项 LG-013/LG-016/LG-027；以 `tasks claim ... --as agent:pi-lg013`/`agent:pi-lg016`/`agent:pi-lg027` 精确领取，提交见对应 claim commit。从新基点建独立分支/worktree：`dev/lg013`→`/tmp/lightgravity-worktrees/lg013`、`dev/lg016`→`/tmp/lightgravity-worktrees/lg016`、`qa/lg027`→`/tmp/lightgravity-worktrees/lg027`（路径此前不存在、未覆盖）；未 push、未 deploy、未复制 `.env`、未清理任何旧 worktree/分支。
- 限制：本轮为整合与文档同步，非新功能实现；不宣称首版完成。LG-010 QA 的真模型/浏览器复测未在本整合轮重跑（依赖 SDK 路径零改 + L0-10 worker 既有证据）；全部结果均为**执行者局部/该 QA 基线证据**，首版集中 QA（LG-021/022/027）仍未进行。

### 2026-10-15：整合 LG-020 本地启动/分发并把契约升至 1.5.0

- 基点：上一整合结束于 `9d5bfe5`（LG-015 + 契约 1.4.0），主工作区 clean。LG-020 在独立 worktree `dev/lg020` 连续完成 `05e6b0e`（本地启动/停止与一体分发入口）与 `8c01dc5`（默认连接解析/新成员 Run pin、运行时种子 agent 与真实 dist 验证），worker 已退出；`fix/lg010-r2` 与其它 worktree 本轮未触碰（不改其代码/分支）。
- 整合：按序 `git cherry-pick 05e6b0e` → `dfa7cf8`（无冲突）；再 `git cherry-pick 8c01dc5`（自动合并，无冲突标记）。两提交均保留作者与消息，无内容丢失，未清理任何 worktree/分支，未 push/deploy、未复制 `.env`。
- 互不覆盖核对：① `coordinator/graph.py` 同时保留 root 的 canonical evidence 导入（`import_evidence`/`_record_evidence`/`evidence_unreadable`）与 LG-020 的默认连接 pin（`_resolve_run_pin`/`_run_pins`/`_member_compiler`/`_materialize_members`/`_config_drift` 的 `pinned_is_current`）；未取单边丢弃。② `adapter/executor.py` 仅新增一行 `connection_ref_override=request.connection_ref`，真实停止/取消边界（`cancel`/`stop` 确认）未变。③ `api/app.py`/`api/context.py` 与主基线一致（LG-020 依赖的 `resolved_coordinator.set_verification(...)`、自动 verify 与 `resource_proposal` 端口保留）。④ `coordinator/service.py` 构造器 `verification` 与 `resource_service` 端口共存。
- 版本与文档同步：docs/08 由 `1.4.0` MINOR 升至 `1.5.0`（§6.2 Run、§6.4 Member 登记加性、非秘密字段 `connection_pin`，说明 Run 招募冻结默认 worker 连接与漂移失败语义）；同步 `contracts/constants.py`、`tests/contracts`、README、PROJECT、agent.md、docs/06；历史 1.0.0–1.4.0 条目与 1.3.1/1.4.0 记录按原文保留。
- 整合期最小兼容接线（不扩大平台）：① 种子 agent 原 `tool_refs: []` 只能回文本、无法处理明确授权的文件交付，现幂等创建并仅引用 `view-file`/`create-file`/`edit-file` 三个 workspace 受限文件工具（不含 `run-command`/web），Task/Run 约束 ceiling 仍可收窄，无授权 workspace 不挂载；② evidence 根不在 workspace 根下，原 `GET /tasks/{id}/artifacts` 只列不解析，现独立列出 evidence 根条目并新增 `GET /tasks/{id}/artifacts/content` 与 `.../artifacts/download`，仅接受 `evidence:<run_id>/<name>@sha256:<hex>` 并经 Task/Run evidence resolver（Task/Run 归属 + 路径包含 + 摘要）解析，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符（docs/08 1.5.0 §4.3 登记）。
- 验收（整合执行者，非 QA）：真正构建最新 `frontend/dist` 并以 CLI `start` 临时 data/workspace：`GET /` 200 + `no-store` + 注入 `__LG_RUNTIME_TOKEN__` + 真实 hashed asset；`GET /api/v1/health` 报 `contract_version: 1.5.0`；缺认证可读 `tasks`/`settings`/`files`（200）；无 token `PATCH /settings` 401；带 token 经 Settings API 建连接（201，凭证只存 ref+`cred_` 版本）、静态测试（200）、设 worker 默认（200）；新 Task 触发 Run，Run/Member 均写入非秘密 `connection_pin`（`deepseek-live` + 不透明 `credential_version`）；临时文件经 `import_evidence` 后由 `.../artifacts/content`/`.../artifacts/download` 正确预览/下载（同 revision/ETag），原始路径 400、摘要不符 404；`stop` 后 pid 记录移除、端口释放、无残留进程。
- 真实检查：`uv run mypy` → **Success: no issues found in 85 source files**；`uv run pytest -q` → **381 passed, 1 skipped**（gated 真实模型默认跳过）；`frontend` `tsc` 通过、`vitest` **62 passed / 8 files**、`vite build` 成功（CSS 28.29 kB / JS 234.89 kB）；`tasks validate` → **OK: 27 tasks, no diagnostics**。真实 DeepSeek 调用本整合轮 **0 次**（LG-020 worker 曾用 2 次，各硬上限 1，凭证仅来自 env）。
- 限制：本轮为整合与必要接线，非 LG-021/022/027 版本 QA；LG-020 待首版 QA。LG-010 的 ack 问题仍待独立复验，**不宣称 LG-010 QA 通过**，其状态/`blocked_by` 未改。种子 agent 现授予有界文件工具（相较原“无工具”语义），已记入 LG-020 任务与 docs/08；真实 dist 仅本机构建，未提交/未部署。

### 2026-10-15：整合 LG-015 Team/Resources 管理视图并把契约升至 1.4.0

- 基点：上一整合结束于 `ffe7a63`（LG-010 返修 + LG-014 Files），主工作区 clean。LG-015 在独立 worktree `dev/lg015` 连续完成 `f8f21a4`（Team/Resources 管理视图与受控资源写入）与 `eb5deec`（补齐 3 项内部接线并登记契约 1.4.0），worker 已退出；root 独立 QA `qa/lg010-r1`（基点 `ffe7a63`）与其它 worktree（含 LG-020）本轮未触碰。
- 整合：精确 `git cherry-pick f8f21a4` → `7c0bd19`（无冲突）；再 `git cherry-pick eb5deec` → `c663486`，4 处 hunk 冲突，按加性语义最小合并：`contracts/constants.py`、`tests/contracts/test_contracts.py`、`docs/08-interface-contract.md`、`coordinator/service.py`。两个提交均保留作者与消息，无内容丢失，未清理任何 worktree/分支，未 push/deploy、未复制 `.env`。
- 冲突处理（保留清单）：① contract 版本最终 `1.4.0`，注释与 change-log 同时完整保留 root `1.3.1` 的 LG-014 上传/下载实现与证据引用语义记录、015 的 3 个新端点与 `resource_proposal`/`resource_result` 字段；② docs/08 frontmatter、概览段、§13 change-log 均按 1.4.0 → 1.3.1 → 1.3.0 逆序排列，§4.3 端点表同时保留 files 两端点（已实现）与 resources/team 三端点；③ `coordinator/service.py` 构造器同时保留 `verification: CandidateVerifier`（root 自动验证端口）与 `resource_service: ResourceService`（015 受控写入端口），`self._verification`/`self._resource_service`/`self._resource_dir` 三者共存。
- 互不遮蔽核对：消息级 `resource_proposal` 分支在 `submit_task_message` 持久化后**同步**调用 `_route_resource_proposal`（仅 `role=user`、`message_id` 幂等、`expected_revision` 版本检查、不创建 Run、不等待 worker、不改活跃 Member `config_hash`），与 `_apply_outcome` 成功进入 `verifying` 后触发的 `_auto_verify`→`verify_and_prepare` 回调位于不同方法、互不遮蔽；`POST /tasks/{id}/messages` 带提议时先经 `AccessPolicy.authorize(request, sensitive=True)`，无 token 默认拒绝。
- 壳层/入口保留：`views/registry.tsx` 同时保留 root 的 Files `./files/FilesView` 挂载与 Settings `./settings/SettingsView`、015 的 `TeamContextRail`/`ResourcesContextRail`/`SettingsRoute` 与可选 `Context`；`frontend/src/views/files/FilesView.tsx` 仍默认 `createFilesApi({ getApiToken: getRuntimeToken })`；未以旧占位覆盖 014/026 页面。
- 版本与文档同步：`CONTRACT_VERSION`、`tests/contracts`、README、PROJECT、agent.md、docs/06 统一到 `1.4.0`；历史 1.0.0–1.3.1 条目按原文保留。
- 真实检查（本机 Python 3.12.13 / uv 0.12.1 / Node v22.23.2）：`uv run mypy` → **Success: no issues found in 76 source files**；`uv run pytest -q` → **333 passed, 1 warning**；`npm --prefix frontend run typecheck` 通过、`test:run` **62 passed / 8 files**、`build` 成功（CSS 28.29 kB / JS 234.89 kB）；`node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate .` → **OK: 27 tasks, no diagnostics**。未新增真实模型调用。
- 限制：本轮为整合与对齐，未做新功能的独立版本 QA；LG-015 受控资源写入/Team 视图属新资源 feature，浏览器/E2E 与真实资源健康检查留 LG-021/LG-022。root 独立 QA `qa/lg010-r1` 仍验证 `ffe7a63` 的后端闭环返修核心，**不把旧 QA 当作 LG-015 新功能验收**。LG-010 状态/`blocked_by` 未改，仍 `in-progress`/blocked 等待独立复验。敏感写默认拒绝、首次启动 token 握手（LG-020）仍未实现。

### 2026-10-15：LG-010 首轮 QA 返修（两项阻断）并整合 LG-014 Files

- 基点：上一整合结束于 `25312d1`，主工作区清洁。本轮精确 `git cherry-pick 8f8266e`（LG-010 独立 QA 报告，仅 `probes/lg010/**` 与 `backlog/tasks/LG-010.md`；QA 失败事实与 `blocked_by` 原样保留）→ `fba9a23`；再 `git cherry-pick b1b93cd`（LG-014 Files 上传/下载与任务证据预览）→ `d3d3f48`；两者均无冲突。未触碰其它独立 worktree，未 push/deploy、未复制 `.env`、未清理任何 worktree。
- 复现：基点用 `uv run python probes/lg010/lg010_check_repro.py` 确认 `artifacts-in-workspace` 把 executor 的绝对 `diff_ref` 当作 workspace 相对路径而 `failed: outside workspace`；返修后同一脚本如实把它判为 `unauthorized absolute artifact ref`（原始绝对路径不再被解析）。
- 返修 1（证据引用语义）：新增 `backend/lightgravity/evidence.py`，把可信 executor 产物导入 Store 拥有的 `<data_dir>/tasks/<task_id>/artifacts/<run_id>/`，记录为 `evidence:<run_id>/<name>@sha256:<hex>`；`verify/checks.py` 只解析授权 workspace 根（相对引用）与 Task/Run evidence 根（canonical 引用），校验归属、路径/符号链接包含与内容摘要，**原始绝对路径一律拒绝**；`coordinator/graph.py` 在记录 Subtask 证据前完成导入（失败按 `evidence_unreadable` 诚实失败），`verify/candidate.py` 按解析后的名字识别 diff。未删除 `diff_ref`、未跳过检查。
- 返修 2（自动验证）：`coordinator/service.py` 新增结构化 `CandidateVerifier` 端口；成功 Run 进入 `verifying` 后自动调用 `VerificationService.verify_and_prepare`，经真实 `ResourceStopper`（Store 停止/释放门）从 `verifying` 到 `awaiting_acceptance`；`api/app.py` 先构建 `VerificationService` 再构建/回挂 `Coordinator`，因此**显式注入 coordinator/dispatcher/executor** 的 `create_app` 分支也共享同一验证服务，不依赖 QA 手动调用或隐藏 HTTP 端点。
- Files 整合：`frontend/src/views/registry.tsx` 的 Files `Main` 由占位 `./FilesView` 改为 `./files/FilesView`，删除旧占位；`FilesView` 默认复用 LG-026 运行时 token helper（`getRuntimeToken`→`createFilesApi({ getApiToken })`）注入上传 `X-LG-Token`，无 token 时只读可用、上传如实 `unauthorized`。未改资源视图与壳层语义。
- 契约与文档：docs/08 由 `1.3.0` PATCH 升至 `1.3.1`（将 planned 的 `POST /files/upload`/`GET /files/download` 标为已实现，声明 `revision` 为 `size-mtime_ns` 变更令牌与跨进程复核属尽力而为，并明确 workspace/evidence 引用语义与拒绝原始绝对路径），同步 `contracts/constants.py`、`tests/contracts` 与 README/PROJECT/agent/docs06 当前事实；历史 1.0.0–1.3.0 条目按原文保留。
- 真实检查（本机 Python 3.12.13 / uv 0.12.1 / Node v22.23.2）：`uv run pytest -q` → **314 passed, 1 warning**（新增证据 canonical 化、canonical evidence 解析、经广播 store 的完整 `verify_and_prepare` 与注入 coordinator 自动验证等回归）；`uv run mypy` → **Success: no issues found in 73 source files**；`npm --prefix frontend run typecheck` 通过、`test:run` **43 passed**、`build` 成功且**首次打包 Files 视图**（CSS 24.67 kB / JS 205.40 kB）。
- 限制：未新增真实模型调用（独立 QA 复测负责）；LG-010 报告两项阻断已返修但**未经独立 QA 复验**，任务保持 `in-progress` 且不删除 `blocked_by`；未做浏览器 QA（LG-021/022）；上传首次启动 token 握手仍归 LG-020；未 push/deploy。

### 2026-10-15：整合 LG-026 Settings 页面并把 LG-015 领取到新基点

- LG-026 在独立 worktree `dev/lg026` 完成 `b3db405`，worker 已退出；LG-010 QA（`dev/lg010`）与 LG-014 Files（`dev/lg014`）仍在各自 worktree，本轮未触碰。主工作区核对干净后精确 `git cherry-pick b3db405` → `5155d07`（无冲突、无内容丢失），新增 `frontend/src/views/settings/**`、`frontend/src/api/settings.ts`、`frontend/src/api/auth.ts`（运行时 token helper）与 `frontend/tests/settings*.tsx`，并把 LG-026 任务置 done。
- 必要整合接线（`0fc66b8`，仅 registry）：`views/registry.tsx` 的 Settings `Main` 由占位 `./SettingsView` 改为 `./settings/SettingsView`（props 全可选，符合 `ComponentType`），删除不再可达的 `views/SettingsView.tsx`，并把 Settings 上下文栏空态改为“Models & Providers is shown in the main panel.”。未改壳层、Files 占位、其它页面、`api/types.ts`、`api/client.ts` 或根依赖。
- 真实检查（本机 Node v22.23.2 / npm 10.9.8）：`make frontend-check` → `tsc --noEmit` 通过、vitest **32 passed**（5 files）；`make frontend-build` 成功，主构建**首次包含 Settings 视图**（CSS 20.29 kB / JS 193.02 kB，此前壳层基线 CSS 16.59 kB / JS 171.08 kB）；未做浏览器 QA（留 LG-021/027）。
- 诚实限制：Settings 页面已挂载并接线 `/api/v1/settings*`，但敏感写仍由后端 `LocalAccessPolicy` 默认拒绝，**首次启动 token 握手未实现（LG-020）**，未就绪前该页只读、写入返回真实 `unauthorized`；`tool_probe`/`structured_output` 仍由后端标 `skipped`；其余业务视图（Chat/Board/Files/Team/Resources）仍为占位/未接入，**不宣称全部页面可用**。LG-026 成果为执行者局部证据，**待版本 QA**（LG-021/LG-022/LG-027）。
- 就绪门：`tasks validate` → **OK: 27 tasks, no diagnostics**；`tasks ready` complete、无 diagnostics，就绪项 LG-015/LG-020。以 `tasks claim ... --as agent:pi-lg015` 精确领取 LG-015（`51d037c`，仅改任务 frontmatter `status`/`assignee`），并以该新 HEAD 建独立分支 `dev/lg015` → `/tmp/lightgravity-worktrees/lg015`（路径此前不存在、未覆盖；分支基点已含共享 `frontend/src/api/auth.ts`）。未 push、未 deploy、未复制 `.env`、未清理任何旧 worktree/分支。
- 给 LG-015 的可用接口与接线限制：Resources 七类可经 `GET /api/v1/resources/{kind}`（`connection`/`conversation`/`hook`/`mcp`/`tool`/`trigger`/`skill`）与 `/{kind}/{id}` 读取，Team Available 用 `kind=agent`；Recruited 成员来自 `GET /api/v1/tasks/{task_id}` 详情 `members`（引用当前 `active_run.team_refs`），需按 `state` 过滤已释放并保留历史；Connections 编辑复用 `frontend/src/api/settings.ts` 同一 Connection 权威，token 只从 `frontend/src/api/auth.ts` 的运行时内存 helper 读取。尚无 `/members`、`/team` 专用端点，资源端点只读（写走 Chat/受控动作），`api/types.ts` 仅含壳层类型，LG-015 应自带端点类型而不复制契约；资源详情 `body` 需按 schema/kind 渲染。

### 2026-10-15：整合 LG-009/LG-012、接线验收与全局对话并把契约升至 1.3.0

- 本轮由整合执行者完成必要整合与接线（不做独立 QA）。LG-009 在 `dev/lg009` 完成 `cce2a59`、LG-012 在 `dev/lg012` 完成 `3759a77`，两 worker 已退出。主工作区核对干净后先提交契约登记 `9d70f01`（docs/08 §4.3/§5.2/§6.1/§13 登记加性字段与端点并升 `1.3.0`），再精确 `git cherry-pick`：`dd8a03e`（009）、`d9aa69f`（012），均无冲突、无内容丢失；未清理任何既有 worktree/分支，未触碰或复制 `.env`。
- 契约登记（加性、MINOR）：Task 可选 `checks` 授权列表；`acceptance` 加性 `candidate_ref`/`candidate_plan_hash`/`check_records`/`note`；只读 `GET /tasks/{task_id}/acceptance`；LG-025 既有 `GET /settings/connections/{id}` 与 `PATCH /settings`；单例全局对话 `GET/POST /conversations/global/messages`；LG-014 **planned、本轮未实现** 的 `POST /files/upload` 与 `GET /files/download`。既有端点语义、错误码、事件类型、枚举与状态迁移均未变化。
- 必要整合与接线（提交 `8ee0c09`）：`verify` 的 accept/reject 分支合入 `api/tasks.py` 既有 `POST /tasks/{id}/actions`（含加性 `expected_requirements_revision`/`expected_deliverable_revision`），只挂载独立只读 `build_acceptance_router`，避免同一路径两个处理器抢占；`create_app` 注入 `VerificationService` + `ResourceStopper` 稳定接口（未注入时用默认 Store 停止门）；`GraphDispatcher`/`executor` 保持可注入，默认仍是诚实的 `UnavailableExecutor`，health 只在注入真实 executor 时报告 `sdk_adapter=true`。新增 `api/conversations.py` 把字面 `global` 映射到固定 `conv_000…` 单例会话，`message_id` 幂等、`request_id` 作二次幂等，`workspace_ref`/`agent_ref` 仅接受授权来源（越界→`path_outside_workspace`，未知 agent→`reference_invalid`），不新建会话平台。
- 版本同步：`contracts/constants.py` 的 `CONTRACT_VERSION` 由 `1.2.0` 升至 `1.3.0`，同步 `tests/contracts` 期望与 README/PROJECT/agent/docs06 当前事实；历史记录（1.1.0/1.2.0 条目、§8.1 标题等）按原文保留，不回写。
- 设置 token 边界：保持 `LocalAccessPolicy` 对敏感写默认拒绝，不放开；docs/08 §4.1 明确令牌只由运行时注入，不写仓库/文档/日志/URL/localStorage/IndexedDB/Markdown；前端与 LG-020 用进程级运行时注入 + 启动握手取得，首次启动握手**尚未实现**，不宣称就绪。
- 真实检查（本机 Python 3.12.13 / uv 0.12.1）：`uv run mypy` → **Success: no issues found in 72 source files**；`uv run pytest -q` → **304 passed, 1 warning**（含新增 `tests/api/test_integration_wiring.py` 的验收接线、stopper 注入与全局对话用例）；`olav-tasks tasks validate .` → **OK: 27 tasks, no diagnostics**。UI 未改，未重复 browser；无真实 SDK/DeepSeek 调用（留 LG-010）。
- 限制：LG-009/LG-012 成果仍为执行者局部证据，**待版本 QA**（LG-010、LG-021/022）；SSE 回放/断线用进程内 ASGI 驱动验证，未经真实 uvicorn/浏览器；files 上传/下载仅登记未实现；首次启动 token 握手未实现；未 push/deploy/启动产品服务。
- 就绪门通过（`tasks ready` complete、validate 无 diagnostics）后以 `tasks claim` 精确领取 LG-010/LG-014/LG-026（不领 LG-015，控制本批三条并行），提交 `6f20971`；从新基点 `6f20971` 建独立分支/worktree：`dev/lg010`→`/tmp/lightgravity-worktrees/lg010`、`dev/lg014`→`/tmp/lightgravity-worktrees/lg014`、`dev/lg026`→`/tmp/lightgravity-worktrees/lg026`；已有路径不覆盖、不复制 `.env`、不删旧分支/worktree。
- 给后续任务接口：LG-010 在 coordinator `_apply_outcome` 成功进入 `verifying` 后调用 `VerificationService.verify_and_prepare`，并向 `create_app` 注入真实 executor 与更强的 `ResourceStopper`；LG-014 owner 拥有 `backend/lightgravity/api/files.py` 的后续写权限，实现 docs/08 已登记的 planned 上传/下载；LG-026 走既有 `/api/v1/settings*` 与运行时 token 注入，秘密不进前端持久化。

### 2026-10-15：整合 LG-008 自动组队与依赖调度并把契约升至 1.2.0

- LG-008 在独立 worktree `dev/lg008` 完成，提交 `44170f0`，worker 已退出。主工作区核对干净后先提交契约登记 `852c4bc`（docs/08 §6.2/§6.3 登记加性字段并升 `1.2.0`），再精确 `git cherry-pick 44170f0`（`5d99a85`），无冲突、无内容丢失，未清理任何 worktree/分支，未触碰 LG-012 的 worktree/分支。
- 契约登记（加性、MINOR）：Run `plan`/`plan_hash`/`plan_source`；Subtask `objective`/`capability`/`key`/`write`/`config_hash`/`owner`/`lease_expires_at`/`fail_reason`/`blocked_by`。语义：`plan` 为校验通过并冻结的完整计划（`source`/`notes`/`subtasks`），`plan_hash` 为其规范化 JSON 的 SHA-256，`plan_source` 只记录来源（如 rules/model），模型提议仍走同一 validator；Subtask `key` 为计划内局部 slug、非运行时 ID，`write=true` 的同工作区写节点串行，`config_hash` 冻结节点运行配置（节点定义 + 成员 `member_config_hash`）、派发前比对、漂移即 `config_invalid`，`owner`/`lease_expires_at` 为 Subtask 执行租约（与 Task `queue` 租约为不同层面，过期可回收、终态拒绝），`fail_reason` 记录失败/阻塞原因，`blocked_by` 指向致其阻塞的上游失败 Subtask 且 `acceptance.status=blocked`。HTTP 端点、错误码、事件类型、枚举与状态迁移均未变化。
- 版本同步：`contracts/constants.py` 的 `CONTRACT_VERSION` 由 `1.1.0` 升至 `1.2.0`，同步 `tests/contracts` 期望、README、PROJECT、docs/06 的当前版本与阶段事实；历史记录（1.1.0 决策条目、§8.1 标题等）按原文保留，不回写。
- 局部检查：`uv run pytest tests/coordinator tests/contracts -q` → **64 passed**；`uv run mypy` → **Success: no issues found in 58 source files**；`olav-tasks tasks validate` 退出码 0（27 tasks, no diagnostics）；`tasks ready` complete、无 diagnostics，唯一就绪项 LG-009。本次仅为加性字段与版本常量，未重复全量后端测试。
- LG-008 成果标注“待版本 QA”；默认 `max_parallel=1`，真实并行写代码与真实 SDK 端到端分别留 LG-018/LG-010。本轮未 push、未 deploy、未启动产品服务。
- 随后以 `agent:pi-lg009` 精确 claim LG-009（`status: in-progress` + `assignee`），并在新 HEAD 建独立 worktree `dev/lg009` → `/tmp/lightgravity-worktrees/lg009`（已有路径不覆盖，不复制 `.env`，不清理旧 worktree）。

### 2026-10-15：实现 LG-006 正式 executor 与产品侧 loopback 认证代理（真实 DeepSeek 验证）

- 在 `backend/lightgravity/adapter/` 与 `tests/adapter/` 实现正式产品执行器 `AntigravityExecutor` 与 `LocalAuthProxy`，并把稳定执行边界（`ExecuteRequest`/`ExecutorResult`/`CancelResult`/`SessionRef`/`ExecutionRef`）固化。执行器调用 LG-005 的 `CompiledAgentConfig`/`build_sdk_config`，拒绝 `executable=False`，解析 `credential_ref` 后启动只监听 loopback、固定 DeepSeek 上游、每会话 token 隔离的产品代理，再把 SDK `base_url` 指向该代理。真实凭证只来自进程环境（`DEEPSEEK_API_KEY`）或 LG-025 受控 store 的 `CredentialResolver`，值不落盘、不回显、不进日志/事件/结果（`Secret.__repr__` 恒为 `<redacted>`，`mask_values` 再做一层防护）。
- 真实路径实测：SDK `0.1.22` + `LocalOpenAIAgentConfig` → `LocalAuthProxy` → `https://api.deepseek.com/v1/chat/completions`；实际发送 model ID `deepseek-v4-flash`，上游返回规范 `deepseek-flash`（两者均记录，不把“4.1”之类版本串当 API ID，不静默 fallback）。临时授权工作区跑通：真实文件写入与 unified diff、结构化 finish 结果、用量、`MAX_MODEL_CALLS_EXCEEDED` 预算停止、跨 `save_dir`+`conversation_id` 的会话恢复、以及**确认的流式中断取消**（`cancel confirmed=true`、`stop_confirmed=true`）。进程前后 `/proc` 扫描无 `localharness` 残留，代理 `stop()` 返回确认。证据见 [tests/adapter/evidence](tests/adapter/evidence/README.md)。
- 有界调用：真实模型调用共 **12**（硬上限 12）——3 次最小模型 ID 发现 + 9 次 LG-006 harness（主链 7、取消链 1、一次竞态失败的取消尝试 1）。未使用 stub/mock 替代真实证据；canned/单元测试仅补失败分支。
- 边界与诚实性：适配器不写任何控制状态（Task/Run/Member），只 `emit(dict)` 事件；`cancel` 只有观察到 SDK 会话 idle 才返回 `confirmed=true`，未确认不写终止状态；MCP/Triggers/`search_web`/SDK 内部委派仍关闭；Gemini/Vertex 仍标未验收、非默认可执行。真实 Gemini/Vertex 与独立版本 QA（LG-010/LG-022）仍未进行。
- 契约与范围：本轮兼任共享后端整合 owner，将 `contracts/constants.py` 的 `CONTRACT_VERSION` 由 `1.0.0` 升至 `1.1.0` 并同步 `tests/contracts`（HTTP 端点/错误码/事件类型/实体字段/枚举/状态迁移均未变）；未新增根依赖，未改 `pyproject.toml`/`uv.lock`；未实现 LG-007 或 LG-025。局部检查：`uv run mypy` 无问题（38 files）、`uv run pytest -q` **157 passed**（adapter 75）、`tasks validate` 退出码 0（27 tasks, no diagnostics），done 7 / todo 20。成果标注“待版本 QA”；本地提交，未推送、未部署。

### 2026-10-15：确认首版真实后端为 DeepSeek（覆盖此前 Gemini 待决）

- 用户明确决定：产品首版先用 DeepSeek，解除此前“首版 Gemini 缺少认证”的阻塞，继续批量开发。本条决策覆盖 2026-10-15“整合 LG-011”条目中“用户选择仍未回复 / 不擅自切换产品后端”的待决状态；该历史条目按原文保留，不回写。
- 首版唯一真实执行路径：已真实验证的 `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`（注册后端 `openai-compat`，只有 `base_url`、无 `api_key` 字段）+ loopback 认证代理接 DeepSeek。不新增 SDK，不保留强制 Gemini 认证门，不新增通用多厂商平台。
- 产品认证代理由 LG-006 作为**产品代码**实现，不复制或依赖 LG-003 探针、参考仓库或开发机绝对路径；代理只监听 loopback，具启动/停止/失败生命周期与停止确认，残留进程必须清理；只从进程环境或受控 secret store 的 `credential_ref` 解析凭证，不读取/输出/记录完整秘密。LG-025 负责 Connection/SETTINGS 写入、凭证引用与分层测试接口。
- 模型首选本环境实际使用的 `deepseek-v4-flash`（`PI_MODEL`）；不把未经该路径实测的版本串（如“4.1”）写成可用 API ID。LG-003 SDK 探针当时使用 `deepseek-chat`，LG-006 须记录并验证实际发送给 SDK 的 model ID 与 `base_url`。
- `search_web` 维持不可用；Gemini/Vertex 及其它未验收后端不得作为默认可执行连接。**凭证事实更正**：派工/任务运行环境已注入 DeepSeek key（LG-003 探针与开发派工使用）；不保证项目 `.env` 内存在可直接使用的 key，也不在文档、日志、事件或响应中输出完整秘密。
- 契约更新：docs/08 由 `1.0.0` MINOR 升至 `1.1.0`（§8.1 首版后端与本地认证代理、§13 变更记录）；HTTP 端点、错误码、事件类型、实体字段、枚举与状态迁移**均未变化**。同步 docs/07、docs/01、docs/03、docs/04、docs/06、README、agent.md 与相关任务（LG-006 移除 `blocked_by` 并保持 `todo`；LG-025/026/027 首版后端要求改为 DeepSeek）。
- 代码不改（本轮只交契约与管理文档）：adapter 中把 Gemini 描述为“产品契约”的注册表/能力注释需由 LG-006 在实现时一并整合更新；当前代码已把 `openai-compat` 标为 `verified=True`、Gemini/Vertex 标为 `verified=False`，与本决策一致。
- 本次提交前运行 `tasks validate` 与文档本地链接/一致性检查；仅本地文档提交，未推送、未部署、未启动产品服务。

### 2026-10-15：整合 LG-011 前端壳层并记录批次阻塞

- 通过 pi 在独立 worktree 完成 LG-011（左侧导航与统一前端壳层），提交 `75107f0` 已完成且 worker 退出。主工作区核对干净后以 `cherry-pick` 精确带回 `main`（`1987874`），无冲突、无内容丢失、未清理任何 worktree/分支，只整合该任务成果。本批未新增镜像测试、未做独立 QA（遵 [agent.md](agent.md) 第 1 节与 [docs/06](docs/06-roadmap.md) 版本 QA 门约定）。
- LG-011 交付 `frontend/src/app/`（`AppShell`/`TopBar`/`NavigationRail`/`ShellProvider`/`uiState`/`tokens.css`/`shell.css` 等）、`frontend/src/components/` 共享组件层、`frontend/src/api/`（`types` 对齐 docs/08、`client`、`/health` 探测）与 `frontend/src/views/` 入口/占位；五工作入口靠左、底部 Settings、顶栏无一级 tabs。
- 整合检查证据：`cherry-pick` 干净；`make check-all` 通过（后端 `mypy` 无问题、pytest **133 passed**；前端 `tsc --noEmit` 无错、vitest **19 passed**）；`make frontend-build` 成功（`dist/index.html` 0.40 kB、CSS 16.59 kB、JS 171.08 kB）；`olav-tasks tasks validate` 退出码 0（**27 tasks, no diagnostics**）；任务计数 done **6**（LG-001～005、011）/ todo **21**。
- LG-011 执行者局部证据：19 个 vitest、**23/23** 无依赖真实 Chrome 浏览器检查（1440／1024／390px 抽屉，含焦点/键盘/窄屏/空错态）、`tsc`/`vite build` 通过；**未做真实后端联调**（无后端时显示真实 `Backend not connected`/`network_error`，业务端点为空态/未接入）。截图保留在 `/tmp/lg011-evidence/`（临时目录，不提交二进制）。本批活动进程核查：LG-011 预览（Vite preview `127.0.0.1:4173`）已不在运行，无本批预览服务需清理；未杀其它进程、未清理 worktree/分支。
- **阻塞与待决（不改产品契约）**：本环境 `.env` 已确认可用 DeepSeek 凭证（开发/探针用），但产品首版 Gemini Developer API／Vertex 无凭证**未认证**；用户关于“保持产品 Gemini 或把产品也改为 DeepSeek”的选择**仍未回复**。不擅自切换产品后端。LG-006 保持 `todo` 并写入 `blocked_by`（首版 Gemini 缺少认证）；未派发 LG-006，不代表不可做不依赖凭证的静态代码。
- 未知成本/耗时：pi worker 的 token/成本在本批次不可得，记录为未知；批次墙钟耗时未由执行器上报，不推算。
- 同步 README 顶部阶段事实与进展表、[docs/06](docs/06-roadmap.md) 顶部阶段、`frontend/README.md` 壳层目录与真实未接入状态；未修改 docs/08 冻结契约、未新增共享依赖、未推送、未部署。LG-011 成果标注“待版本 QA”，不代表版本验收通过。

### 2026-10-15：实现 LG-005 角色与 SDK 资源配置编译

- 按用户授权在 `backend/lightgravity/adapter/` 与 `tests/adapter/` 实现资源配置编译：解析 `skills.source/refs`、已注册 tools/hooks、connection/session profile；按 revision + content_hash 固定每个解析到的资源版本，并输出整体 `config_hash`。
- 权限不扩大：有效工具 = agent `tool_refs` ∩ Task `allowed_tools`（约束只能删不能加），预算取最严格值；MCP、Triggers、`search_web` 与 SDK 内部委派一律标记 `unavailable` 且不挂载；未注册 handler/不存在引用按 `reference_invalid`/`config_invalid` 拒绝。
- 秘密只引用：资源只允许 `credential_ref`，frontmatter 出现明文秘密字段即以 `secret_in_resource` 拒绝；编译输出经脱敏，凭证值从不落盘、日志或响应。
- 固定 SDK 版本 `google-antigravity==0.1.22`（与 LG-003 一致）加入根 `pyproject.toml`/`uv.lock`；因该 wheel 无 `py.typed`，为 `google.*` 增加 mypy `ignore_missing_imports` 覆盖。`executable` 与能力声明明确区分“配置可编译”和“后端已验证/可执行”：Gemini/Vertex 仍标记未验收，缺凭证不阻塞静态编译。
- 未改动 docs/08 冻结契约语义，未修改 `contracts`（仅 import 引用）；未实现 LG-006 executor 或 LG-007 coordinator。adapter 面向 LG-006 的编译结果接口记录在 `backend/lightgravity/adapter/README.md`。
- 局部验证：`uv run pytest tests/adapter` 51 passed、全量后端 133 passed、`uv run mypy` 无问题（34 files）。成果标注“待版本 QA”；真实 Gemini adapter 与闭环仍待具备凭证环境。本地提交，未推送、未部署。

### 2026-10-15：整合 LG-003 SDK 探针与 LG-004 存储层

- 通过 pi 并行工作包完成 LG-003、LG-004（LG-011 仍在独立 worktree 执行，本批未触碰）。两份成果提交在各自 worktree 干净；主工作区核对干净后以 `cherry-pick` 精确带回 `main`，无冲突、无内容丢失、未清理任何 worktree/分支，只整合这两个任务成果。
- LG-003：固定 `google-antigravity==0.1.22`（x86_64 Linux wheel，原生 runtime 握手成功）。核心能力以真实 DeepSeek（OpenAI-compatible 本地代理注入 bearer）有界实测通过：文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content`，并记录真实沙箱状态 `SandboxStatus(available=true)`；证据与限制见 [LG-003 探针报告](probes/lg003-antigravity/reports/LG-003-report.md)。产品首版 Gemini（Developer API / Vertex）后端因本环境无 `GEMINI_API_KEY`/Vertex 凭证**未验收**；`search_web` 在非 Gemini 端点被调用但无可结果，实际不可用。DeepSeek 只是探针可达路径，**不改变 docs/08 冻结的首版 Gemini 产品契约**。
- LG-004：交付 `backend/lightgravity/store/` 与 `tests/store/`，覆盖 frontmatter 保留/重复键拒绝、Task/Run/Subtask/Member 校验与状态迁移、路径越界与符号链接逃逸、`flock` 锁/租约、原子替换与 JSONL 尾部恢复、事件 `seq` 单调与消息幂等、可重建索引。整合后局部 `pytest tests/store` 69 passed、全量后端 82 passed、`mypy` 无问题。
- 两项成果均标注“待版本 QA”，不代表版本验收通过；本次整合为执行与证据核对，主代理未做代码审查。
- 后续：LG-005 可基于 LG-004 的 `Store` 接口与 LG-003 探针结论进行角色/SDK 资源配置编译；LG-006 真实 Gemini adapter 与 LG-010 最小真实闭环仍需具备 Gemini 凭证的环境完成认证后才能验收。
- 同步 README 阶段事实；未修改产品契约、未新增共享依赖、未推送、未部署。

### 2026-10-15：建立可运行工程骨架（LG-002）

- 按用户授权完成 LG-002：建立后端 Python 3.12 + FastAPI/uvicorn/Pydantic/ruamel.yaml、前端 React 18 + TypeScript + Vite 的最小工程；依赖精确锁定在 `uv.lock` 与 `frontend/package-lock.json`。
- 新增 `backend/lightgravity/contracts`：契约常量、状态枚举、错误码与 HTTP/重试映射、错误信封、health/version DTO；作为共享只读模块供后续任务引用，不各自复制。
- 真实端点 `GET /api/v1/health`、`GET /api/v1/version` 与统一错误信封经 uvicorn 实际启动并 curl 验证；前端占位壳经 Vite dev server 启动验证。未安装 Antigravity SDK，未实现 store/adapter/coordinator/verify/settings 业务。
- 统一入口 `Makefile`：`make check`（mypy + pytest）、`make frontend-check`（tsc + vitest）、`make check-all`、`make frontend-build`。数据根 `LIGHTGRAVITY_DATA_DIR`（默认 `./bot-data`）与源码分离并 gitignore；`.env.example` 无真实凭证；路径默认相对工作目录，可分发。
- 局部实测：后端 pytest 13 passed、mypy 无问题；前端 tsc 通过、vitest 1 passed、vite build 成功。已知限制：前端 dev 依赖在 vitest 2/vite 5 范围内有 npm audit 告警，修复需升级到契约未冻结的大版本，故保留并记录。
- 为 `probes/`（LG-003）、`backend/lightgravity/store` 与 `tests/store`（LG-004）、`frontend/src` 业务子目录（LG-011 及后续）保留明确边界，未写入他人 owner 路径。成果标注“待版本 QA”。本地提交，未推送、未部署。

### 2026-10-15：冻结首版接口与状态契约（LG-001）

- 按用户授权完成 LG-001：产出 [首版接口与状态契约](docs/08-interface-contract.md)，契约版本 `1.0.0`、API 前缀 `/api/v1`、实体 schema `lightgravity.bot/v1`，冻结运行时 ID/时间约定、HTTP API 与错误语义、事件/消息契约、Task/Subtask/Run/Member 状态机与合法组合、Store 与 SDK Adapter 接口、工作区授权和后续文件归属。
- 最小技术栈选定：后端 Python 3.12 + FastAPI/uvicorn/Pydantic/ruamel.yaml（uv 管理），前端 React 18 + TypeScript + Vite，事件用 SSE，测试用 pytest/vitest/Playwright；依赖来自 PyPI/npm，精确版本由 LG-002 锁定。本次未安装依赖、未写产品代码。
- 源目录定为 `backend`、`frontend`、`probes`、`tests` 并明确所有权：LG-003 owner `probes` 与独立探针环境，LG-004 owner `backend/.../store` 与独立测试，LG-011 owner `frontend`；共享依赖/根工程文件由整合执行者（首任 LG-002）串行维护，`backend/lightgravity/contracts` 为共享只读模块。
- 在 [docs/06](docs/06-roadmap.md) 区分产品运行时顺序验证与开发并行，并定义版本 QA 门：LG-010 为原型大版本 QA 门，LG-021／022／027 为首版版本集中 QA；基础任务只做局部检查，不追加逐任务独立 QA。
- 同步 README、agent.md 的文档入口。契约与实现层的运行时验证标记为“待版本 QA”，不声称功能已验证。
- 提交本任务精确范围文档（docs/08、README、agent.md、docs/06、PROJECT、LG-001），本地提交，未推送、未部署。

### 2026-10-14：初始化 Git 并推送文档与技能

- 按用户授权在 `/home/yhvh/code/lightgravity-bot` 初始化 Git，默认分支 `main`，将设计文档、27 项 backlog 任务与 `.agents/skills/` 技能文件作为初始提交入库。
- 远端 `http://192.168.8.50:3000/admin/lightgravity-bot.git` 此前为空仓库（`empty: true`，默认分支 `main`），本次为首次推送；未 force push，未覆盖任何历史。
- 提交身份取自 Gitea 认证用户 `admin <admin@admin.com>`，仅写入仓库本地配置；未修改全局 Git 配置。
- 推送使用只从环境读取密钥的临时 askpass（权限 700），关闭持久凭证 helper，密钥不进入 URL、命令行、日志或 Git 配置，结束后清理临时文件。
- 新增最小 `.gitignore`，排除 `.env`、`.env.*`（保留 `.env.example`）、编辑器交换/备份文件、凭证与临时日志；`.env` 与 `.env.swp` 保持未跟踪。
- 提交前核对暂存文件，未发现秘密或临时文件。本次仅做文档与技能初始入库及必要检查，未开发产品功能，未执行代码审查或新增产品测试。

### 2026-10-14：项目管理与 pi 并行开发

- 用户明确要求主代理只做项目管理，不改代码、不审查代码；所有执行任务通过 pi 派出，使用 env 中的 DeepSeek API 配置。
- 开发采用并行工作包与快速原型，小任务保留必要的局部检查，大版本整合后才集中独立 QA；主代理跟踪证据与待 QA 状态。
- 具体协作规则统一维护在 agent.md 第 1 节，优先于已安装技能的原生子代理与逐任务 QA 默认流程；产品运行时的 Antigravity SDK 与验收契约保持原设计。
- 此次仅更新管理规则，未启动 pi、读取凭证或执行开发任务。

### 2026-10-14：安装项目级 Olav Tasks 技能

- 按用户要求从 `http://192.168.8.50:3000/admin/olav-tasks.git` 安装仓库提供的 6 个技能到 `.agents/skills/`，供本项目开发代理发现。
- 固定来源 commit `ab252888bd9e6dc9185a71bcf02b241484e0d4f6`，保留引用文件、MIT 许可证及逐文件 SHA-256；安装内容与来源逐文件核对一致。
- 此次安装技能文件；未安装 Olav Tasks CLI 或 SDK，未启动开发任务。

### 2026-10-14：项目建立与设计落盘

- 用户要求在 `/home/yhvh/code` 新建 `lightgravity-bot`，保存本轮讨论设计。
- 名称采用 LightGravity Bot，仓库目录采用 `lightgravity-bot`。
- 长期定位为通用 AI 助手，首版定位为按需组队的开发任务助手。
- 按轻量重设计推进，参考 Olav OS 与 Olav Tasks，不预设完整复用旧底座。
- 采用文件即事实源，提供 Chat、Board、Files 三个项目视图。
- 执行流程为分析、计划、临时组队、调度、SDK 执行、验证、有限返修、人工验收、释放队伍。
- Antigravity SDK 和 agency-agents 为拟采用组件，实际集成未验证。
- 首版建议限制为一个活跃运行、三个 worker、两个并行任务、一轮返修；不是已验收容量。
- 比赛资格未确认，产品设计与参赛判断分开管理。

### 2026-10-14：补充 skills 与基础工具设计

- 用户要求将 skills、基本文件读写与网页搜索能力写入设计。
- Role 定义职责，Skill 定义工作方法，Tool 提供实际操作；自动组队时分别绑定，技能内容不扩大权限。
- 优先使用 Antigravity SDK 原生 `skills_paths`／`inline_skills` 及内置文件、命令、搜索和 URL 读取工具，不重复实现通用能力。
- SDK 当前源码与官方示例已经核对；安装版本、runtime、技能资源访问与工具执行尚未实测。
- worker 修改工作成果；领取、状态、验收、团队释放等持久控制数据由调度器统一写入。

### 2026-10-14：Task 入口与 Markdown 资源契约

- 用户要求把 Task 目录、任务对话，以及 SDK 的 Agent、Connections、Conversation、Hooks、MCP、Tools、Triggers 纳入设计。
- Task 是用户工作单元，Subtask 是派发节点，Run 是一次执行尝试，Project 是可选的长期背景。Task 不再定义为仅存在于 Run 内的节点。
- 每个 Task 有独立目录和 TASK.md；同一任务的补充、返修与继续执行保留任务 ID 和用户对话。
- 任务、运行、团队成员、子任务和资源描述使用 Markdown＋YAML frontmatter；JSONL 用于消息与事件，SDK 原生存储用于会话恢复，不维护重复当前状态。
- frontend 按 schema/kind 渲染；adapter 校验引用与权限后把描述编译为 SDK 配置，不能把任意 Markdown 当作可执行配置。
- SDK 模块提供执行基础，业务调度、资源生命周期和持久任务状态仍由 LightGravity Bot 控制。详细契约见 docs/02。

### 2026-10-14：SDK 核心能力审计

- 用户要求核对 SDK 核心能力覆盖及 frontmatter 抽象管理的可行性。
- 核对源码快照 `91dc5f84565bb505577ac9524f107f453a6e8d1f` 与示例，补充模型配置、结构化输出、预算、重试、压缩、多模态、观测、取消和委派等映射，详见 docs/03。
- 七类资源保留，额外能力归入配置块或运行操作，不扩张成新的管理平台。
- frontmatter 管理声明和引用，adapter 承接代码与原生 session；展示配置不等于执行能力已验证。
- skills 路径/inline 在核对版本的本地后端互斥；默认能力因配置类型而不同，Bot 需要显式配置。
- 沙箱必须核对实际状态，取消必须确认真实停止；API 重试、输出重试、业务返修与 Task 总预算分别管理。
- 尚未安装 SDK 或测试 runtime；审计不扩大首版范围。

### 2026-10-14：项目更名

- 用户确定项目名为 LightGravity Bot，目录为 `/home/yhvh/code/lightgravity-bot`。
- 同步文档中的项目名、目录名、候选 schema 命名空间与技能配置目录；Olav OS、Olav Tasks 等参考项目名称保留。

### 2026-10-14：补齐常驻 Bot 行为

- 用户要求完善整体设计；新增 docs/04，补齐消息分类、直接回复/工具问答/交付执行三条路径、任务队列、需求变更、暂停取消与重连通知。
- 首版设计采用单用户本地网页入口与常驻后端，浏览器断开不取消任务；外部聊天渠道、云端公开访问与自主触发暂缓。
- 新交付需求才创建 Task，实际写操作关联 Task/Run；简单只读问答不强制组队。
- 待验收前确认 worker 停止并释放执行资源，人工验收保留为独立决定；返修按需重建团队。此决定取代早期“验收后才释放”的流程。
- Task 保留三态 status，Board/活动统计使用详细 phase；队列与验收版本以 TASK.md 为权威。
- Agent 技能字段统一为 skills.source/refs，Member 保存解析后的 skillRefs。
- 此次仅完善文档，实际能力、配置编译、进程恢复与隔离仍待实现验证。

### 2026-10-14：左侧导航与招募视图

- 用户要求一级 tab 采用 Olav OS 风格左侧布局；首版固定窄图标栏提供 Chat、Board、Files、Team，取代上方一级 tabs。
- Team 左侧资源栏提供待招募/已招募纵向入口；候选角色来自长期模板，临时成员来自 Task/Run 队伍记录。
- 当前成员与已释放历史分开显示，全局和 Task 范围有明确默认行为。
- 顶栏负责范围、面板开关与通知；资源栏、主内容和 Chat 按屏宽折叠，页面切换不重置 Task 或会话。
- 参考旧布局，不引入岗位、组织或动态插件运行时；详细交互与验收见 docs/05，仅完成设计。

### 2026-10-14：Agent 合并 Team，资源管理入口落盘

- 用户要求保存 Agent 并入 Team、其他 SDK 模块集中管理的设计。
- 左侧一级入口更新为 Chat、Board、Files、Team、Resources，取代早期四入口设计。
- Team 待招募管理 Agent 模板，已招募管理 Task/Run 临时 Member 实例；不另建 Agent 一级入口。
- Resources 左侧分类为 Connections、Session Profiles、Hooks、MCP、Tools、Triggers、Skills。Session Profiles 只管理会话配置，真实 Conversation 留在 Chat/Task/成员详情。
- 资源继续采用 Markdown/frontmatter 与 canonical 技能文件；模板声明、依赖有效与运行可用分开显示。
- 角色/成员资源引用可导航并返回，运行实例固定配置版本；资源修改不静默影响已招募队伍。
- 同步 README、docs/01、docs/02、docs/05；仅文档设计，未新增运行配置或实现页面。

### 2026-10-14：开发约束

- 用户要求根目录增加 agent.md 约束项目开发。
- agent.md 为唯一规则正文；AGENTS.md 作为自动发现入口引用它，不复制规则。
- 约束首版范围、模块职责、Markdown/frontmatter 事实源、SDK 与资源配置、执行恢复、左侧导航、验证和文档同步。
- 更新历史“当前授权”措辞为阶段记录，避免阻止后续已授权实现。此次仅写规则与文档入口。

### 2026-10-14：补充代码参考清单

- 在 agent.md 明确列出 code 下的 Olav OS、Olav Tasks、Olav 以及在线 Antigravity SDK、agency-agents。
- 记录调度、持久化与导航的具体调查入口和复用用途，要求核查依赖、实际版本与许可。
- 参考位置不成为产品运行依赖；本项目修改不自动授权修改参考仓库。此次仅补充文档。

### 2026-10-14：前端开发与风格约束

- 用户要求在根目录增加 design.md，约束前端开发与风格。
- 采用克制浅色工作台、统一 tokens/组件、固定左侧五入口与可折叠多栏；像素尺寸和颜色为实施起始建议，需实际验证。
- 首版界面标签采用英文，用户输入与产物保留原语言；默认浅色，暗色后续扩展。
- 补齐页面交互、真实状态反馈、窄屏、键盘与浏览器验收要求。
- agent.md 管总体开发规则，design.md 管前端细节；AGENTS.md 与 README 链接到两者，不复制规则。
- 仅完成约束文档，未选定/安装前端框架，也未实现或测试网页。

### 2026-10-14：Olav Tasks 首版排期

- 用户要求开始使用 olav-tasks 写排期；通过本地现有 CLI 的 tasks new 创建 LG-001～024，全部保持 todo。
- 开发任务采用 olav.tasks/v1，存放 backlog/tasks；与未来产品 lightgravity.bot/v1 的 Task/Run 目录分开。
- 建立 BACKLOG.md 和 docs/06 滚动排期，按基础探针、最小真实闭环、左侧五入口、恢复质量、完整验收组织。
- P0 优先暴露 SDK/接口风险并跑通最小闭环；P1 完成管理页、恢复与首版质量门。未分配负责人、工期或模型档位。
- 当前按阶段滚动排期，不假定每日产能或强行写日历日期；若指定演示期限需同时收敛范围。
- 首个实施候选 LG-001；SDK 真实探针需认证与预算，后续以实际情况记录阻塞。
- 此次只规划与验证任务格式/依赖，不 claim、不执行任务、不安装 SDK、不部署服务。

### 2026-10-14：文档元数据与索引补齐

- 按用户要求为 12 份普通 Markdown 补入 title、doc_type、category、updated；不使用任务或产品资源 schema，不改变文档生命周期与执行事实。
- README 补入 AGENTS.md 的链接，任务目录继续由 BACKLOG 索引；不额外建立重复总索引。
- 24 项开发任务的 ID、状态、依赖与正文保持原样。

### 2026-10-14：Settings 设计与排期

- 用户要求补入 Settings 与模型接入排期；左导航底部增加齿轮入口，五个工作入口保留。
- Models & Providers 使用类型化受保护表单，是普通资源通过 Chat 修改的例外；与 Connections 共用权威文件，默认只保存引用，秘密由独立后端管理。
- 首版先 Gemini，其他 SDK 后端标验证状态；模板/默认更改不热切换活跃 Member。
- 新增 LG-025（后端配置/凭证/测试）、LG-026（设置页）、LG-027（专项验收），总计 27 项，全部 todo。
- LG-020 接入 LG-026 的首次配置路径，LG-021 依赖 LG-027，LG-022 增加模型接入覆盖；LG-011/015 同步导航与共享引用要求。
- 新设计文档 docs/07 有文档 frontmatter，并从 README/导航/资源契约索引；任务依赖须经 CLI 校验。未保存真实密钥或启动测试。
