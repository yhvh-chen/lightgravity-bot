---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-15"
---

# LightGravity Bot

> 更新：2026-10-16。设计与 27 项首版开发任务已落盘（2026-10-15 新增 14 项扩展任务，共 41 项，见 [BACKLOG](BACKLOG.md)），首版接口契约（docs/08，契约版本 1.5.0）已冻结；用户已确认首版先用 DeepSeek，首版真实执行后端为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek，此前的 Gemini 认证阻塞已解除。LG-001～012、LG-014、LG-015、LG-020、LG-025、LG-026 共 17 项已完成并整合到 `main`（均为**待版本 QA**，其中 LG-010 已通过独立版本 QA）：工程骨架可运行、SDK 探针、存储层、资源配置编译、左侧导航壳层、正式 executor + loopback 认证代理、常驻消息路由与 Task 队列、自动组队与依赖调度、模型设置与凭证后端、产物验证与人工验收、查询 API 与持久事件订阅、Settings 模型接入页面、Team/Resources 管理视图与受控资源写入、本地启动/停止与一体分发入口。集成后已把验证服务与资源停止接口注入 `create_app`，accept/reject 合并进 API actions，并新增只读 `GET /tasks/{id}/acceptance` 与单例全局对话 `GET/POST /api/v1/conversations/global/messages`。主前端构建现已挂载 Settings、Files、Team 与 Resources 视图，分别接线 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*` 与 `/api/v1/resources/*`；Files 上传复用 LG-026 运行时 token helper 注入 `X-LG-Token`，无 token 时上传如实返回 `unauthorized`。Team/Resources 受控修改经 Task 对话提议：`POST /api/v1/tasks/{id}/messages` 携带 `resource_proposal` 时执行 sensitive 授权，`message_id` 幂等、`expected_revision` 版本检查，实际结果写回同一 Task 对话；该路径不创建 Run、不等待代码 worker，也不热替换活跃 Member 配置（docs/08 1.4.0 登记 `PATCH /resources/{kind}/{id}`、`GET /team/available`、`GET /team/members`）。LG-020 已提供 `lightgravity start/stop/status/init` 与一体分发：默认 loopback、`data/workspace/secret/dist` 隔离、首个启动在内存握手运行时 token 并注入 `index.html`（`__LG_RUNTIME_TOKEN__`，前端 `auth.ts` 读取后自动带 `X-LG-Token`），敏感写默认拒绝、缺认证可读历史/设置；首次启动幂等种子 `lg-default-worker`（仅 `view-file`/`create-file`/`edit-file` 三个 workspace 受限工具，无 `run-command`/web 无边界工具），Settings-only 建连接/存凭证/静态测试/设 worker 默认后新 Task 可用默认 worker，Run/Member 在招募时冻结非秘密 `connection_pin`（docs/08 1.5.0）。同时注册 canonical evidence 产物在 Task 产物 API 的预览/下载：`GET /tasks/{id}/artifacts`、`.../artifacts/content`、`.../artifacts/download`，仅接受 `evidence:<run_id>/<name>@sha256:<hex>` 并经 Task/Run evidence resolver 授权，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符。敏感写仍由后端 `LocalAccessPolicy` 默认拒绝。LG-013 已按真实 API 接线把 Chat/Board 接入真实历史与 phase（不再为占位/mock），**实施已通过本包验收并置 done**；其中直答走新增的 `coordinator/dialogue.py`（无工具单次模型轮，未配置默认协调连接/凭证时诚实 `unavailable`，不伪造 AI），经 `create_app(responder=...)` + bootstrap 注入，现有 Resource/Verifier 端口保留；但**真实浏览器 HTTP 业务路径仍归版本门 LG-021/022**，不等于完整浏览器 HTTP 端到端。LG-027 已就设置/凭证生命周期完成独立专项版本 QA 并判定 **pass**（真实 CLI + 真实 HTTP + `file://` 真实构建渲染，范围见其报告），**该范围限于设置/凭证的 CLI/HTTP 与浏览器渲染，不等于完整浏览器 HTTP 端到端**；其真实模型调用计数产品未暴露，报告中的旧上限 5 + 恢复硬上限 4 仅为指令/运行预算，**不视为已验证实际调用次数或精确上界**。旧 QA“浏览器全 HTTP/fetch 阻断”结论已被 root [browser-diagnostics](probes/browser-diagnostics/README.md) 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch`/SSE 可用，仅顶层 `Page.navigate` 到 `http://` 在本机 headless 挂起；原报告作为历史保留。LG-016 恢复反重放守卫（暂停/取消确认、中断恢复、跨 Run 原生会话续接、稳定 reuse identity 与 `recovery_required`）已整合到 `main`；**完整 checkpoint skip 调度尚未实现，不夸大恢复能力**。LG-006 以真实 DeepSeek（实际发送 `deepseek-v4-flash`，上游返回 `deepseek-flash`）在临时授权工作区跑通文件写入/diff、结构化结果、用量、预算停止、会话恢复与确认取消，真实模型调用总数 12（硬上限 12），进程无残留；证据见 [tests/adapter/evidence](tests/adapter/evidence/README.md)。LG-009/LG-012 的真实 SDK 端到端已在 LG-010 完成，浏览器验收仍留 LG-021/LG-022。LG-010 最小真实开发闭环经独立版本 QA 判定 **pass/done**：首轮报告的 executor 绝对 `diff_ref` 误判与交付后未自动触发验证两项阻断已返修，第 2 轮复验又发现携带 `target_run_id` 的重复 ack 非幂等，已按 Task 作用域幂等键返修并由独立 QA 复核确认消除（`probes/lg010/reports/lg010-qa-r2-after-refix.md`）。真实 DeepSeek 链路证据基点 `ffe7a63`（交付后自动到 `awaiting_acceptance`、真实文件/diff/usage、停止释放、绑定版本 accept、stale 拒绝），累计真实调用 12（硬上限 14，`within_cumulative_cap_14=true`）；QA 候选核心证据 `ffe7a63`/`ed014c5`、复现脚本 `lg010_accept_repro_r1.py`/`r2.py` 与 `lg010_check_repro_r1.py`。**此 QA 只覆盖契约 1.3.1 core 的最小后端闭环，并非 1.5 全功能 QA**：LG-015/020 的新资源/启动功能仍未验收，分别留 LG-027 与 LG-021/LG-022；未部署。

**个人 AI 工作助手（执行型 Agent）：把资料和目标交给它，它帮你整理、查找并完成工作，过程与成果保存在你掌握的文件中。**

LightGravity Bot 接收资料、问题和目标：简单问答直接处理，需要交付时创建任务并按需组队，执行、验证、保存成果；Chat 统一接资料、提目标、看结果，Files 负责整理、归档、预览与来源追溯；进入待验收时释放临时队伍，常驻服务继续等待指令。

统一目标定位由原开发任务助手扩展而来：资料整理检索与任务执行验收衔接；原件、正式内容与元数据仍以文件为事实源，词法与可选向量索引只作可重建缓存。**用户掌握文件不等于所有推理都在本地运行**——模型与后端仍走已验收的接入路径。

内部编排不因定位扩展而反转：仍由程序控制权限、状态、预算与调度，worker 按需协作，默认不存在独立常驻模型编排 agent；不声称已实现完整的自主领取或点对点协作。本定位不引入 AIOS、全自动无人值守、外部聊天渠道或企业组织平台，不增加额外承诺。

首版仍以开发任务验证交付闭环：在一个明确的项目工作区里完成小型代码修改，留下代码差异、检查结果与交付说明。资料摄取与检索**待实现、接口未冻结**（方向见 [docs/09](docs/09-source-intake-and-retrieval.md)），中文 ASR 尚未打通，Office 等格式未实测；不宣称当前已全面具备上述能力。

## 为什么重新设计

LightGravity Bot 从 Olav OS 的使用经验中重新设计更小的产品。保留文件即事实源、对话管理项目、任务依赖、人机决策和可复核交付的思想，避免为了复用代码而连带引入完整组织系统、历史运行时和兼容逻辑。

它不是先复制一套 Olav OS 再裁剪，也不预设旧底座为运行依赖。组件是否移植，要根据实际依赖、许可证和维护成本决定。现有技术债的具体范围仍需调查，不能把重写天然视为更便宜。

## 用户入口

| 视图 | 用户用途 |
|---|---|
| Chat | 提出目标、补充信息、查看汇报、作出决定 |
| Board | 查看任务依赖、执行情况、验证结果与阻塞 |
| Files | 查看输入资料、工作成果和验收证据，上传与下载文件 |
| Team | 查看待招募角色和当前 Task／Run 的已招募成员 |
| Resources | 管理 Connections、Session Profiles、Hooks、MCP、Tools、Triggers 与 Skills |
| Settings | 底部齿轮入口，接入模型、管理凭证、测试连接和设置默认模型 |

五个工作入口采用 Olav OS 风格的固定左侧窄图标导航，底部另放 Settings；上方不再放一级 tabs。Agent 合并到 Team，其他配置集中到 Resources。Settings 与 Connections 使用同一份配置，不维护重复模型列表。顶栏显示任务范围、面板开关与通知。

Task 是主要操作入口：一项任务一个目录、一份 TASK.md、一条用户对话历史。工作视图围绕同一任务展示，Resources 提供共享配置与任务实际引用；Project 是可选的共享背景，Run 是内部执行尝试。

任务、角色及 SDK 资源采用 Markdown＋YAML frontmatter 描述与渲染，程序校验后编译为 SDK 配置。日志与 SDK 会话保持各自格式，不重复保存当前业务状态。

## 当前进展（截至 2026-10-15）

| 任务 | 状态 | 实际证据与限制 |
|---|---|---|
| LG-001 契约 | done | [docs/08](docs/08-interface-contract.md) 首版契约已冻结（LG-001 为 1.0.0，2026-10-15 MINOR 升至 1.1.0，首版后端改为 DeepSeek） |
| LG-002 工程骨架 | done | 后端 health/version、前端占位壳、check 入口可用 |
| LG-003 SDK 探针 | done（带限制） | 固定 `google-antigravity==0.1.22`；文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content` 经真实 DeepSeek 实测通过；Gemini Developer API／Vertex 未验收（非首版路径，不作默认）；`search_web` 在非 Gemini 端点不可用。见 [LG-003 报告](probes/lg003-antigravity/reports/LG-003-report.md) |
| LG-004 存储层 | done（待版本 QA） | `backend/lightgravity/store/` + `tests/store/`；整合后局部 69 passed、全量后端 82 passed、mypy 无问题 |
| LG-005 资源编译 | done（待版本 QA） | `backend/lightgravity/adapter/` + `tests/adapter/`；refs/skills/tools/hooks/connection/session 解析、权限不扩大、秘密脱敏、unsupported 标记 unavailable、SDK 配置可编译；局部 51 passed、全量后端 133 passed、mypy 无问题 |
| LG-011 前端壳层 | done（待版本 QA） | `frontend/src/app/` 壳层与路由、`components/` 共享组件、`api/` 客户端与 `/health` 探测、`views/` 入口与占位；局部 19 vitest、23/23 无依赖 Chrome 浏览器检查、`tsc`/`vite build` 通过；**未做真实后端联调**，业务端点显示未接入/空态 |
| LG-006 Executor Adapter | done（待版本 QA） | `backend/lightgravity/adapter/` 正式 executor + loopback 认证代理 + 稳定边界类型；真实 DeepSeek 跑通文件写入/diff、结构化结果、用量、预算停止、会话恢复、确认取消，真实调用 12（上限 12），进程无残留；证据 [tests/adapter/evidence](tests/adapter/evidence/README.md) |
| LG-007 消息路由与队列 | done（待版本 QA） | `backend/lightgravity/coordinator/`（classification/logs/queue/state/dispatcher/service/api）；局部 30 passed、全后端 187 passed、mypy 无问题；执行证据用 in-process `FakeExecutor`（mock），真实 SDK 端到端留 LG-010 |
| LG-008 自动组队与依赖调度 | done（待版本 QA） | `backend/lightgravity/coordinator/`（planner/recruiter/scheduler/graph）；局部 coordinator 57 passed、全后端 247 passed、mypy 无问题（58 files）；默认 `max_parallel=1`，真实并行写代码留 LG-018 |
| LG-025 模型设置与凭证后端 | done（待版本 QA） | `backend/lightgravity/settings/`；局部 33 passed、全后端 189 passed、mypy 无问题（46 files）；分层连接测试 `overall=verified`（`tool_probe`/`structured_output`=skipped） |
| LG-026 Settings 模型接入页面 | done（待版本 QA，已挂载） | `frontend/src/views/settings/**`、`frontend/src/api/settings.ts`、`frontend/src/api/auth.ts`（运行时 token helper）；已由整合 owner 挂到 `views/registry.tsx` 既有 Settings 入口并删除旧占位；局部 `tsc` 通过、vitest 32 passed、`vite build` 成功（主构建含 Settings：CSS 20.29 kB / JS 193.02 kB）；真实接口证据为执行者临时 server + 1 次 DeepSeek 调用；敏感写默认拒绝、首次启动 token 握手未实现（LG-020），浏览器 QA 留 LG-021/027 |
| LG-009 验证与人工验收 | done（待版本 QA） | `backend/lightgravity/verify/`；局部 26 passed、全后端 273 passed、mypy 无问题（64 files）；机器检查只跑程序已注册且 Task `checks` 授权的项，停止门未确认不释放，accept/reject 绑定 requirements/候选版本并按 `request_id` 幂等；真实 SDK 端到端留 LG-010 |
| LG-010 最小真实开发闭环 | **done（独立版本 QA pass）** | 独立 QA 报告 `probes/lg010/reports/lg010-qa-r2-after-refix.md`；真实 DeepSeek 链路（基点 `ffe7a63`）跑通交付后自动 `awaiting_acceptance`、真实文件/diff/usage、停止释放、绑定版本 accept、stale 拒绝；重复 ack 幂等按 Task 作用域键返修并经独立复验消除（`tests/api/test_tasks_accept_replay.py`、`probes/lg010/lg010_accept_repro_r1.py`/`r2.py`）；真实调用累计 12/14；**只覆盖契约 1.3.1 core 最小后端闭环，非 1.5 全功能 QA** |
| LG-012 查询 API 与事件订阅 | done（待版本 QA） | `backend/lightgravity/api/`；局部 30 passed、全后端 246 passed、mypy 无问题（61 files）；tasks/resources/files/SSE/settings 路由真实装配，事件先落盘再广播、游标重放去重、断线不取消 Run；SSE 用进程内 ASGI 驱动验证，真实 uvicorn/浏览器留 LG-021/022 |
| LG-014 Files 上传/下载与证据预览 | done（待版本 QA，已挂载） | `backend/lightgravity/api/files.py`（有界上传/下载、`expected_revision`、原子替换、越界/secret 拒绝，docs/08 §4.3 自 1.3.1 标为实现）、`frontend/src/views/files/**`；已由整合 owner 挂到 `views/registry.tsx` 并删除旧占位；上传默认复用 LG-026 运行时 token helper，无 token 时只读可用、上传如实 `unauthorized`；上传 token 首次启动握手归 LG-020，浏览器 QA 留 LG-021 |
| LG-015 Team 与 Resources 管理视图 | done（待版本 QA，已挂载） | `backend/lightgravity/resources/**`（目录/诊断/引用/受控写入）、`api/resources.py` 的 `PATCH /resources/{kind}/{id}` 与 `GET /team/available`/`GET /team/members`、`coordinator/resource_commands.py` 与 `service.py` 的消息级 `resource_proposal` 分支；`frontend/src/views/{team,resources}/**` 与数据驱动 `Context` 资源栏；整合后前端类型/测试/构建通过；契约 1.4.0 登记 3 个新端点与消息加性字段；无 Task 时只引导不假写，资源健康如实 unknown，浏览器/E2E 留 LG-021/022 |
| LG-020 启动检查与本地分发入口 | done（待版本 QA，已整合） | `backend/lightgravity/runtime/**`、`api/bootstrap.py`、`cli.py`/`__main__.py`、`pyproject` scripts、`Makefile` targets；`lightgravity start/stop/status/init`，默认 loopback、token 内存握手与 `index.html` 注入、Host/Origin 守卫、敏感写默认拒绝、缺认证可读历史/设置；首启幂等种子 `lg-default-worker`（**有界**文件工具 `view-file`/`create-file`/`edit-file`，无 `run-command`/web）；Settings-only 建连接/存凭证/静态测试/设默认后新 Task 可达 executor，Run/Member 固定非秘密 `connection_pin`；真实 dist 子进程 start→握章→stop 验证；真实 DeepSeek 2 次（同一 gated 用例，硬上限各 1）；docs/08 1.5.0 登记 `connection_pin` 与 evidence 预览/下载端点；待首版 QA（LG-021/022/027） |
| LG-013 接入 Task Chat 与真实看板 | done（实施，待版本 QA） | `backend/lightgravity/coordinator/dialogue.py`（无工具单次直答；无默认协调连接/凭证时诚实 `unavailable`，不伪造 AI）、`api/app.py` 与 `api/bootstrap.py` 的 `responder` 注入；`frontend/src/api/{chat,tasks,events}.ts` 与 `frontend/src/views/{chat,board}/**` 真实接线，移除看板 mock 任务；测试 `tests/coordinator/test_dialogue.py`、`tests/api/test_lg013_chat_board_flow.py`、`frontend/tests/{chat,board,chatApi}`；本包实施验收通过（真实 API 接线 + 服务层真实 HTTP + 局部证据），**真实浏览器 HTTP 业务路径仍归版本门 LG-021/022**（本机 Chrome top-level `Page.navigate` 到 loopback 会挂起，见 browser-diagnostics 更正），**不等于完整浏览器 HTTP 端到端**；整合期补做 **1 次**有界同真实模型只读直答探针（`probes/lg013/evidence/lg013-direct-answer-probe.json`，真实答 `"Four."`，不创建 Task/Run/Member、不写控制文件） |
| LG-027 验收模型设置与凭证生命周期 | **done（独立版本 QA pass，范围受限）** | `probes/lg027/reports/lg027-qa-report.md`；真实 CLI + 真实 HTTP 跑通 Settings→分层测试→设默认→新 Task 真实执行（`tests/e2e/settings/**`、`probes/lg027/scripts/lg027_settings_path.py`）；**仅覆盖设置/凭证 CLI+HTTP 链路与浏览器渲染**（`file://` 真实构建渲染证据），**不等于完整浏览器 HTTP 端到端**；密钥不入存储/日志/响应/浏览器；活跃 Member 不热换、新招募用新配置。真实调用计数**未知**：产品未暴露调用计数器，报告中的旧上限 5 + 恢复硬上限 4 只是**指令/运行预算**，不是已验证的实际调用次数或精确上界 |

- 上述 done 为执行者局部证据，**除 LG-010、LG-027 外均不是版本 QA 结论**；LG-003 已实测的 DeepSeek（OpenAI-compatible）路径是 docs/08 v1.5.0 确定的首版真实后端，LG-006 已在该路径上实现正式 executor + 产品侧 loopback 认证代理。LG-010 已通过独立版本 QA（最小后端闭环），但其收尾是**基于契约 1.3.1 core**、不覆盖 1.5 新资源/启动功能；LG-015、LG-020 仍待 LG-021/LG-022 版本 QA 门集中验证（LG-027 已就其设置/凭证子范围 pass）。
- LG-013 实施已按真实 API 接线通过本包验收并置 `done`，但**完整浏览器业务路径（真实浏览器 HTTP 创建/继续任务、交付审阅与验收停止释放）仍归 LG-021/022**，不能据此宣称完整网页可用。
- 旧 QA「浏览器全 HTTP/fetch 阻断」结论已被 root `probes/browser-diagnostics` 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch` 与 SSE 从 `file://`/`about:blank` shell 可用，仅**顶层 `Page.navigate` 到 `http://` 在本机 headless Chrome 挂起**（见 [browser-diagnostics README](probes/browser-diagnostics/README.md)）。原报告按历史保留，更正不改写旧文。
- 下一步：LG-016 已整合到 `main`（恢复反重放守卫；完整 checkpoint skip 调度尚未实现）；LG-013 实施已 done；LG-015 与 LG-020 仍待 LG-021/LG-022 版本 QA；LG-027 已完成设置/凭证专项。**当前资源/启动的新功能与完整浏览器路径仍待验收**。LG-028（去中心化协作契约）与 LG-033（资料摄取/检索契约）已由本包领取，准备稿在各自 worktree，尚未冻结。LG-017/018/019 尚未领取。
- **计划标记（资料接入与检索）**：方向已确认并落盘到 [docs/09](docs/09-source-intake-and-retrieval.md)，2026-10-15 已正式排入资料线 [LG-033～041](BACKLOG.md)，但**未实现、接口未冻结**；其中中文 ASR 先由 LG-039 做质量验证，达标后再由 LG-041 条件接入，且不作为 LG-040 的硬依赖；图片/PDF、词法、可选向量与 Chat/Files 统一由 LG-040 集中 QA。实施前须按 [docs/08 §13](docs/08-interface-contract.md) 变更控制冻结接口并升版；不改变现有 LG 任务状态与优先级。
- **计划标记（去中心化协作）**：[LG-028～032](BACKLOG.md) 已正式排期（契约 → 原子领取/租约 → 同伴交接 → 隔离执行与 QA/返修整合 → 集中版本验收），但**完整自主协作尚未实现、接口未冻结**；不改变现有任务状态，也不把已有“无独立编排”QA 当作去中心化验收。

## 本地运行与检查（工程骨架）

工程骨架由 LG-002 建立，LG-004 已加入后端存储层，LG-005 已加入 adapter 资源配置编译并把 Antigravity SDK `0.1.22` 锁定为产品依赖，LG-006 已实现正式 executor + loopback 认证代理（真实 DeepSeek 路径，见 [tests/adapter/evidence](tests/adapter/evidence/README.md)），LG-007/LG-008 已实现 coordinator 消息路由、队列与自动组队调度，LG-009/LG-012 已实现验证/验收与查询 API，并由 `create_app` 装配 `FileStore`→`BroadcastingStore`→`Coordinator`、挂载 `/api/v1` 全部路由、lifespan 启停常驻 Coordinator。默认执行器仍是诚实的 `UnavailableExecutor`（不伪装可执行）；真实 SDK executor 由 LG-010 注入。前端壳已存在；Settings、Files、Team 与 Resources 视图已挂载并分别接入 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*`、`/api/v1/resources/*`（敏感写与受控资源提议在 LG-020 握手前默认拒绝，只读可用）；Chat/Board 已由 LG-013 接入真实历史与 phase（不再为占位/mock），直答走新增无工具直答路径（未配置默认协调连接时诚实 `unavailable`）；真实浏览器 HTTP 业务路径仍留 LG-021/022。

### 版本要求

| 组件 | 要求 | LG-002 已验证版本 |
|---|---|---|
| Python | `>=3.12,<3.13`（`.python-version` 为 `3.12`） | 3.12.13 |
| uv | `0.12.x` | 0.12.1 |
| Node.js | 22 LTS | v22.23.2 |
| npm | 10.x | 10.9.8 |
| GNU make | 统一入口 | `/usr/bin/make` |

### 启动后端

```bash
uv sync                # 创建 .venv 并按 uv.lock 安装
make run               # 默认 127.0.0.1:8000，仅监听 loopback
curl http://127.0.0.1:8000/api/v1/health
```

### 启动前端壳

```bash
npm --prefix frontend ci      # 按 package-lock.json 精确安装
make frontend-dev             # http://127.0.0.1:5173，/api 代理到后端
```

### 测试、类型与构建入口

```bash
make check            # 后端 mypy + pytest
make frontend-check   # 前端 tsc --noEmit + vitest run
make check-all        # 二者合并
make frontend-build   # 前端生产构建
```

### 配置与数据

- 复制 `.env.example` 为 `.env` 并按需修改；示例文件不含真实凭证，仓库不保存秘密。
- 运行数据根 `LIGHTGRAVITY_DATA_DIR`（默认 `./bot-data`）与源码分离并已 gitignore；工作区根与秘密存储边界见 docs/08 §10。
- 路径默认相对进程工作目录，克隆后无需开发机绝对路径即可运行。

## 文档入口

- [当前进展与续接记录](PROGRESS.md)：2026-10-15 本地检查点、待合并成果、DeepSeek 阻塞与恢复顺序。

- 项目开发技能位于 `.agents/skills/`：已安装 Olav Tasks 的 6 个技能，来源版本与文件哈希见 [.agents/skills/olav-tasks-source.json](.agents/skills/olav-tasks-source.json)，许可证见 [.agents/skills/OLAV-TASKS-LICENSE](.agents/skills/OLAV-TASKS-LICENSE)。
- [开发约束](agent.md)：项目范围、架构、SDK 接入、状态写入、验证与交付规则；[AGENTS.md](AGENTS.md) 提供自动发现入口。
- [前端约束](design.md)：视觉 tokens、左侧多栏布局、组件、页面交互、响应式与浏览器验收。
- [开发看板](BACKLOG.md)：41 项开发任务（27 项首版 + 新增 14 项扩展 LG-028～041），使用 `olav.tasks/v1` 管理。
- [滚动排期](docs/06-roadmap.md)：阶段、依赖、验收门与当前未定的日历安排。
- [模型设置](docs/07-settings-and-models.md)：Settings、Connection 事实源、凭证、分层测试和默认模型。
- [首版接口与状态契约](docs/08-interface-contract.md)：冻结的最小技术栈、API/事件/实体状态、Store/Adapter 边界、错误语义、工作区授权与后续文件归属（契约版本 1.5.0；1.5.0 **未新增**资料/知识库 schema、摄取/检索/邮箱 API）。
- [资料接入与检索设计](docs/09-source-intake-and-retrieval.md)：**方向已确认、待实现**；Chat 为唯一常规资料接入入口、原件/派生/缓存分层、处理与检索生命周期、分阶段验收与实测局限。API/schema **未冻结**，实施前须按 docs/08 §13 冻结接口并升版。
- [项目手册](PROJECT.md)：目标、优先级、完成定义和已确认决策。
- [产品与架构设计](docs/01-design.md)：调度器、executor、组队、文件事实源、状态与首版交付顺序。
- [Task 与 SDK 资源契约](docs/02-task-and-sdk-resources.md)：任务目录、对话、frontmatter 渲染及 Agent／Connections／Conversation／Hooks／MCP／Tools／Triggers 的映射。
- [SDK 能力审计](docs/03-sdk-capability-audit.md)：核心能力覆盖矩阵、frontmatter 配置块、运行时边界及首版取舍。
- [Bot 行为契约](docs/04-bot-behavior.md)：消息路由、轻任务、队列、需求变更、通知、暂停取消、待验收与资源释放。
- [左侧导航、Team 与 Resources](docs/05-navigation-and-team.md)：四栏壳层、五个一级入口、招募视图、SDK 资源管理及关联导航。

## 首版边界

- 一个占用执行槽的交付 Run，其他 Task 可以排队；最多三个 worker、两个并行子任务、一轮自动返修，待运行验证后调整。已停止的待用户或待验收 Run 不占槽。
- 首个执行后端采用 Antigravity SDK，保留 adapter 边界，不同时实现多个 SDK。
- agency-agents 作为候选角色内容来源，从少量开发角色开始。
- 使用 SDK 原生 skills 加载与基础文件、命令、网页工具；按成员绑定角色、技能、工具权限与工作区，不重建通用技能执行层。首版为 `google-antigravity==0.1.22` 的 OpenAI-compatible（`LocalOpenAIAgentConfig`）→ DeepSeek 路径（LG-003 已实测，LG-006 实现产品侧代理）；`search_web` 标记不可用；Gemini/Vertex 未验收，待各自探针通过后开放。
- 临时角色实例随运行创建和释放，项目与产物长期保存。
- **默认不存在独立常驻编排模型**，也不要求每次 Task/Run 先调用模型规划：明确目标由程序生成最小合法计划后直接交 worker；模型拆解是有界按需能力（可注入提议接口保留、**真实模型后端未接线**），仅在显式记录触发原因时采纳，候选计划仍经同一程序校验。程序原子写/租约、文件事实源、机器验证与独立复核、人工验收、停止确认均保留；worker 不写控制态；SDK 内部委派仍关闭。
- 规划/编排取舍的成本按同一验收门下的全交付生命周期（执行＋验证＋返修＋复验＋失败尝试）评估；未完成样本不计作已交付成本，也不用失败高成本样本的中位数推断完整收益。
- 人工最终验收；worker 自报完成只能进入待验证。
- 单用户本地网页入口，简单问答不组队；后台执行独立于浏览器连接，支持 Task 队列与网页未读通知。云端入口、外部聊天渠道和自主触发另行推进。
- 先实现必要的文件树、预览、上传、下载和任务产物关联。
- 资料接入方向已确认：**Chat 是唯一常规资料接入入口**（上传/拖拽/粘贴链接），Files 负责预览/来源追溯/归档调整/校订/重处理/下载；上传处理是**受控摄取作业**，不自动创建交付 Task/Run/团队。现有 Files 上传 API/UI 属历史实现，交互收拢**尚未迁移**；目标设计见 [docs/09](docs/09-source-intake-and-retrieval.md)，**未实现、接口未冻结**。

## 参考与参赛边界

- [Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python)：执行与会话基础，接口、平台支持和云端运行须实测。
- [agency-agents](https://github.com/msitarzewski/agency-agents)：候选角色模板，不能替代调度与执行系统。
- [Olav OS](../olav-os/)：编排与工作台设计参考，不是本项目已确定的运行依赖。
- [Olav Tasks](../olav-tasks/)：Markdown 项目管理、看板和聊天集成参考，不是本项目已确定的运行依赖。

本项目首先按产品目标推进，不以参赛资格作为已确认事实。AI Builder Cup FAQ 明确限制赛前已有项目及基于已有项目的提交；未公开、新建目录、重新命名或重写实现均不能自动证明合格。复用既有代码、角色或其他资产的允许范围，应取得主办方明确答复。[官方 FAQ](https://aibuildercup.com/Faqs.html)
