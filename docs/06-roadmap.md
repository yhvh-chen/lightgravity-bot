---
title: "首版与扩展版本滚动排期"
doc_type: plan
category: planning
updated: "2026-10-16"
---

# 首版与扩展版本滚动排期

> **新增实施范围（2026-10-16）**：[LG-050](../backlog/tasks/LG-050.md) 为共享团队聊天与简单认证命名里程碑，接口已加性冻结于 [docs/08 §14](08-interface-contract.md)（1.13.0）。后端认证/消息与前端登录/同步并行，随后串行集成、独立集中 QA；当前实施中。下方 49 任务与 1.12.0 为此前 selected-material 收口时的快照。

> **当前状态（2026-10-16，selected-material 原型命名里程碑闭环）**：**LG-047 选定资料快速原型命名里程碑独立 QA 已 `done`（PASS_WITH_LIMITATIONS），LG-049 完整生命周期验证已 `done`（PASS_WITH_LIMITATIONS）**，依据 LG-049 `N-R3-LIFECYCLE` 真实完整 SDK 交付生命周期（原生 API 上传 alpha `d34f0ca58b8d…`、无 seeded derivative → EXACT 目标交付路由 → 程序规则计划 `deliver`+`verify` → 真实 SDK worker 6/6 事实 → `verify` passed（R2 曾 429）→ **真实独立 ModelReviewer `reviewer_kind=model`/`model_calls=1`/passed** → **worker `cleanup=done`+`member.released` 与 reviewer `reviewer_cleanup.confirmed=true` 于 accept 前 CONFIRMED** → API accept done），**8/16 前向**；本轮 root PM 仅 `--no-ff` 合入 probes/docs（合并 `76f10c7`），产品树 `main` == `0188ca2`。任务 CLI（实测）：`49 tasks / 0 diagnostics`、`digest` **48 done / 1 todo / 0 in-progress**、`ready=[]`。**LG-040 已 `done`**（版本 QA 技术验收；用户最终验收 PENDING、未发布）；**LG-037 已 `done`**（可选向量，机制/ACL/降级已证；旧 G2 冻结图片实验 FAIL / R5 图片硬门为历史保留、不 waived）；**LG-041 仍 `todo`、阻塞于中文 ASR 质量门**。累积成本 unknown **非 0**（R1 已知 1+缺口 / R2 actual 8 / R3 actual 8 分列）。契约 **`1.12.0`**、SDK **`0.1.22`**。详情 [K-RELEASE-CLOSE REPORT](../probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md)。本节以下为历史排期快照（含 LG-040 收口时的 41 任务口径），保留不改。

> 日期：2026-10-14，更新：2026-10-16。规划已落盘，开发已开始。阶段事实：LG-001～012、LG-014、LG-015、LG-020 与 LG-025、LG-026 共 17 项已完成并整合到 `main`（其中 **LG-010 最小真实开发闭环已通过独立版本 QA（pass/done）**，其余 16 项均**待版本 QA**；其中协调器 LG-007/LG-008、设置后端 LG-025、验证/验收 LG-009、查询 API LG-012、Files LG-014、Team/Resources LG-015、本地启动/分发 LG-020 已实现，成果以局部测试与证据为准）；LG-013 接入 Task Chat 与真实看板的**实施已完成并置 `done`**（本包验收：真实 API 接线 + 服务层真实 HTTP + 局部证据；**完整浏览器业务路径仍归 LG-021/022**）；LG-027 设置/凭证专项已独立 QA **pass**（**仅设置/凭证 CLI+HTTP 与 browser 渲染范围**，**不等于完整浏览器 HTTP 端到端**；其真实调用计数产品未暴露，旧上限 5 + 恢复硬上限 4 仅为指令/运行预算，不视为已验证实际次数或精确上界）。首版接口契约当前为 `1.11.0`（2026-10-16 LG-031 runtime/API/SDK 集成落地后的保守加性 MINOR，取代 `1.10.0` 的“实现说明增补（无版本变化）”口径：R1 观察 O3 指出两处公开兼容变化——① 四个去中心化端点请求体 `owner` 由 `1.6.0` 冻结时事实采用的 required/端点采用放宽为 **optional/仅一致性校验、不再授权**；② `ExecutionGrant` 加性新增进程内非持久 `lease_owner`；旧客户端传 `owner` 仍可用但不获授权，无端点/枚举/错误码/实体 schema/迁移方向变化；此前 1.10.0 为 LG-022 第二轮针对性返修 REFIX-R2 加性 MINOR：停止门可接受权威适配器真实停止事实（Run 加性新增可选 `reviewer_cleanup`），全局生成计数改为受控 dataRoot 下持久账本（`GET /api/v1/diagnostics/generation` 加性新增 `persistent`/`corrupt`），转发前持久预留、跨重启不归零、损坏绝不当 0，不新增端点/枚举/迁移方向；此前 `1.9.0` 返修后串行集成收拢加性 MINOR：新增 `source.archived` 可逆归档字段与 `archive`/`unarchive` 动作（归档保留检索/打开/权限，不改 `revoke` 使资料不可用的语义），并挂载默认禁用的可选向量端点 `/vector/status`、`/vector/search`、`/vector/rebuild`；此前 1.8.0 LG-022 首版集中 QA 阻断项 D1/D2 返修 R1 加性 MINOR：新增合法迁移方向 `verifying`/`repairing → recovery_required` 与只读诊断端点 `GET /api/v1/diagnostics/generation`（进程全局上游生成请求计数，转发前计数）；此前 1.7.0 LG-017 返修 R1 加性 MINOR：新增独立复核者设置角色/字段 `default_reviewer_connection_ref`、Task 返修账本 `reviewer`/`reviewer_kind`/`model_usage` 与 review/rework 事件 payload `reviewer_kind`/`model_calls`/`usage`，并明确独立复核语义——程序机器门不等于独立复核、无可用 reviewer ⇒ `unavailable` 且阻止 accept；此前 1.6.0 由单一 owner 串行加性冻结 LG-028 去中心化协作与 LG-033 资料摄取/检索两线接口：Subtask `fence`、发现/领取/续租/释放/协作端点、`source`/`intake_job` 实体、`sources`/`intake`/`search` 端点、相应事件/错误码/默认关闭开关，见 [docs/08](08-interface-contract.md) §4.3/§5.1/§6.3/§6.6/§13；两线均**仅冻结接口、尚未实现**，集中 QA 归 LG-032/LG-040；此前 LG-009 验收字段与全局对话端点登记于 1.3.0，LG-014 文件上传/下载标为已实现并澄清证据引用语义于 1.3.1，LG-015 受控资源写入/Team 端点与 Task 消息 `resource_proposal` 字段登记于 1.4.0，LG-020 `connection_pin` 加性字段与 canonical evidence 预览/下载端点登记于 1.5.0）。用户已确认首版先用 DeepSeek，LG-006 正式 executor + loopback 认证代理已在真实 DeepSeek 上跑通文件写入/diff、结构化结果、用量、预算停止、会话恢复与确认取消（真实调用 12，进程无残留，证据见 [tests/adapter/evidence](../tests/adapter/evidence/README.md)）；LG-020 提供 `lightgravity start/stop/status/init` 与一体分发（默认 loopback、token 内存握手、敏感写默认拒绝、首启种子有界工具 worker、Run/Member `connection_pin`），真实 dist 子进程 start→握手→stop 已验证。LG-010 最小后端闭环经独立版本 QA 判定 **pass/done**（真模型证据基点 `ffe7a63`，真实调用累计 12/14，报告 `probes/lg010/reports/lg010-qa-r2-after-refix.md`）；**该 QA 只覆盖契约 1.3.1 core 的最小后端闭环，并非 1.5 全功能 QA**，LG-015/LG-020 的新资源/启动仍待 LG-027 与 LG-021/LG-022。首版唯一真实路径为已验收的 `google-antigravity==0.1.22` + OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek（契约见 [docs/08](08-interface-contract.md) §8.1）。采用 Olav Tasks 的开发任务格式与依赖图；日历开始/结束日期、人员和每日投入未确定，暂不填写 start_date/end_date、assignee 或 effort，也不把实现速度假定为已知。

## 1. 目标与假设

按单用户本地网页首版推进：轻问答与交付路径、Task 目录/对话、临时组队、执行验证、左侧五工作入口与底部 Settings、恢复与通知。第一条真实开发闭环优先于完整管理 UI。

本排期是依赖和验收门排期，不是四天交付承诺，也不是比赛倒排。当前先以滚动阶段作为规划假设；如用户选择明确日期或演示目标，再调整范围和任务日期，不能仅压缩日期而保持全部范围不变。

建议先串行跑通单 worker 实施与顺序验证，再支持两个并行 Subtask。LG-008 的并发限额机制可以先按 1 配置，代码并行整合只有 LG-018 实测通过后启用。独立 QA 可以顺序启动，不要求长驻全套角色。

### 1.1 产品运行时顺序验证与开发并行的区别

- **产品运行时契约**（要被真实验证的部分）：Task 串行推进；Subtask 先按 `max_parallel=1` 顺序验证，只有 LG-018 实测通过后才启用两个并行 Subtask；一个 Task 同时最多一个非终止 Run。
- **开发本项目**（协作方式）：接口冻结后，依赖已满足、文件归属明确、验证互不依赖的工作包可以并行；共享依赖文件与根工程文件由一个整合执行者串行维护。
- 两者不能互相推导：开发可以并行写代码，不代表产品运行时已支持并行执行；产品顺序验收通过后才开放并行。此约定以 [首版接口与状态契约](08-interface-contract.md) 与 [agent.md](../agent.md) 第 1 节为准。

## 2. 阶段与验收门

| 阶段 | 排入任务 | 可观察交付/完成门 |
|---|---|---|
| A：基础与风险 | LG-001、002、003、004、011 | 接口与工程确定；实际 SDK 能力/限制有报告；文件存储能诊断冲突；前端壳可运行 |
| B：最小真实闭环 | LG-005～010、012；LG-025 接口就绪后推进 | 示例代码真实修改、检查、交付与验收；成员释放有证据；API 能读实际状态；连接/凭证共用受控接口 |
| C：网页可用 | LG-013～015、026 | 五工作入口关联同一 Task，Settings 完成真实接入与测试，Connections 不复制状态 |
| D：恢复与质量 | LG-016～020 | 暂停取消、重启检查、返修、并行整合、通知重连和本地启动经过验证 |
| E：首版验收 | LG-027 → 021～024 | 设置/凭证专项、浏览器与 Bot 故障场景通过，对照评估与分发结果齐备 |

阶段是展示分组，不额外增加假依赖。真实顺序以每项 depends_on 为准；例如 UI 壳层无需等 SDK 探针成功，Files 可以在存储/API/壳层就绪后推进，恢复机制可以在 LG-010 后提前开始。

LG-010 是最小后端闭环验收，不代表已有完整网页或所有恢复机制；LG-013 是网页主要路径接入，不代表五入口全部齐备；LG-022 是完整首版故障/端到端验收。不能把前一个门通过宣传成后一个门通过。旧 QA「浏览器全 HTTP/fetch 阻断」结论已被 root `probes/browser-diagnostics` 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，仅顶层 `Page.navigate` 到 `http://` 在本机 headless Chrome 挂起；原报告按历史保留，只追加更正引用。

### 2.1 版本 QA 门（开发侧）

本项目不做逐任务独立 QA。执行者在任务内完成必要的局部检查并记录真实证据；独立 QA 只在下列命名的大版本/集中门开展，由独立于实施者的执行者承担：

| 版本 QA 门 | 覆盖范围 | 说明 |
|---|---|---|
| LG-010 原型大版本 QA 门 | LG-005～010，LG-012 接口就绪 | 首个可运行原型闭环的独立 QA：真实任务、状态转换、幂等、成员释放与失败/缺资料案例。LG-010 本身即该门的验收执行项。**2026-10-15 已独立复核 pass/done**（契约 1.3.1 core 最小后端闭环）。 |
| LG-027 首版集中 QA | 设置与凭证生命周期 | 与 LG-021／LG-022 并列的首版版本集中 QA 之一。**2026-10-15 已独立 QA pass**，范围限于设置/凭证的 CLI+HTTP 链路与 browser 渲染（`probes/lg027/reports/lg027-qa-report.md`），**不等于完整浏览器 HTTP 端到端**（后者仍归 LG-020/021/022）。 |
| LG-021 首版集中 QA | 前端状态与响应式 | 与 LG-022／LG-027 并列，覆盖浏览器主要路径、空/错/断线与窄屏。 |
| LG-022 首版集中 QA | 端到端与故障 | 完整首版验收门，汇总 LG-027／LG-021 证据。 |

- 首版仅上述四类门需要独立 QA；新增扩展版本集中门见第 6 节；LG-003、LG-004、LG-011 等基础任务以自身局部检查与证据为准，不追加逐任务 QA，也不因未做独立 QA 而阻塞。
- 尚未经过版本 QA 的成果在任务正文标注“待版本 QA”；LG-010 原型大版本 QA 门已通过（2026-10-15，仅覆盖契约 1.3.1 core 最小后端闭环），LG-027 设置/凭证专项 QA 已通过（2026-10-15，仅限设置/凭证 CLI+HTTP 与 browser 渲染范围）；但不代表完整网页、恢复机制或 LG-015/LG-020 的新资源/启动功能通过；后者仍待 LG-021/LG-022。LG-013 实施已 done，其**完整浏览器业务路径仍归 LG-021/022**。

## 3. 建议推进顺序与并行条件

1. 先完成 LG-001，再建立 LG-002。
2. 接口冻结后，LG-003 SDK 探针、LG-004 存储、LG-011 壳层可作为独立工作线；只有文件归属明确、验证独立时才并行。
3. 按 LG-005 → 006 → 007 → 008 → 009 → 010 推进真实后端闭环；LG-012 在存储和消息接口就绪后接入。
4. 前端在稳定 API 后接 LG-013/014/015，不提前依赖虚构响应。LG-025 在 LG-004/005/006 后提供设置后端；LG-026 依赖 LG-011/012/025，提供 Settings 接线。UI mock 可以开发布局但必须标记，不能替代集成。
5. LG-016 完成后，QA/返修、并行 worktree、通知与本地启动按各自依赖推进；共享 Store/API/Coordinator 文件的改动需要串行接线或隔离工作区。
6. LG-020 首次启动验收依赖 Settings 页面 LG-026；LG-027 在 Team/Resources、启动和设置就绪后做专项验收，之后汇总 LG-021。执行完整故障验收 LG-022，再做对照评估与交付准备。

这描述可并行的实施结构，不授权后台自动运行或自行启动开发子代理。执行任务按用户后续指令与宿主能力进行。

## 4. 首个实施项与验证门

首个就绪候选应为 LG-001。其产物至少确定最小技术栈、API/事件 schema、实体状态、Store/Executor 责任、测试入口与目录权限，不为架构讨论无限扩展范围。LG-001 的实际产物为 [首版接口与状态契约](08-interface-contract.md)（LG-001 冻结契约版本 1.0.0；2026-10-15 因首版后端改为 DeepSeek 而 MINOR 升至 1.1.0，同期 LG-008 加性控制字段登记为 1.2.0，LG-009 验收字段与全局对话端点登记为 1.3.0，LG-014 文件上传/下载标为已实现并澄清证据引用语义为 1.3.1，LG-015 受控资源写入/Team 端点与 Task 消息 `resource_proposal` 字段登记为 1.4.0，LG-020 `connection_pin` 加性字段与 canonical evidence 预览/下载端点登记为 1.5.0，LG-028 去中心化协作与 LG-033 资料摄取/检索两线接口串行加性冻结为 1.6.0（仅接口、未实现），LG-017 返修 R1 加性独立复核者设置/账本/事件字段为 1.7.0，LG-022 首版集中 QA 阻断项 D1/D2 返修 R1 加性新增 `verifying`/`repairing → recovery_required` 迁移与全局生成计数诊断端点为 1.8.0，见该文档第 13 节）；后续实现以该契约与各项 depends_on 为准，不在本排期重复状态。

SDK 安装/真实测试属于 LG-002/003 后续实施，不包含在此次写排期。LG-003 需要可用的测试模型认证与预算；缺少这些时可以继续无凭证的存储/壳层工作，但不能将 SDK 测试标 done，也不能用 stub 解锁需要真实能力的后续门。

没有现有 check 命令时不在任务中伪造 check 字段。工程建立后，可为有意义且可机械验证的任务补入真实命令；模型质量、人验收和视觉判断仍需对应证据。

## 5. 未决事项与不在本轮范围

- 真实 SDK runtime/模型认证、测试费用与平台支持，在探针前确认实际配置；规划时不把假设阻塞写成已经发生的 blocked_by。
- Python 服务/API 框架、前端框架和组件基线已由 LG-001 在 [接口与状态契约](08-interface-contract.md) 冻结；本次规划未安装任何依赖。
- 日历排期需要开始时间、每日投入和目标范围；当前 Gantt 会显示未排期，这是如实记录，不表示任务缺少依赖。
- 云端部署、比赛提交与资格、外部 bot 渠道、多用户、自主触发和其他 SDK 不在这 27 项开发任务范围；Settings 首版先接入已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）→ DeepSeek，其他 SDK 后端（Gemini/Vertex/LiteRT 等）只显示验证状态，实际开放另立探针与任务。
- 任务状态以单项 frontmatter 为准。开发验收遵 agent.md；产品用户的最终验收属于运行时契约，两者不能混同。

入口：[BACKLOG](../BACKLOG.md)。任务与依赖可通过 `tasks validate/ready/digest` 检查，本地命令见 backlog。

## 6. 去中心化与 Embedding 扩展排期（2026-10-15）

本轮新增 LG-028～041，共 14 项 todo，总计 41 项开发任务。已排入依赖与验收门，不填写未经约定的日历日期，不代表开始实施。原首版任务与验收门保留；本节是新增版本，不把去掉独立编排 agent 的已有 QA 当作完整去中心化验收。

| 批次 | 去中心化工作线 | 资料与 Embedding 工作线 | 完成门 |
|---|---|---|---|
| 0：先准备契约 | LG-028 协作契约 | LG-033 摄取/检索契约；之后可做 LG-039 中文 ASR 验证 | 冻结可实施协议；语音后端与质量有明确结论，失败不得当作可接入 |
| 1：实现基础 | LG-029 自主发现、原子领取与租约 | LG-034 原件摄取与恢复；LG-035 图片/PDF OCR | 依赖 LG-016 的恢复能力完成并整合；竞争、取消、重启与来源版本可复现 |
| 2：打通协作与查找 | LG-030 同伴交接；LG-031 执行/整合/QA返修闭环 | LG-036 词法与回源；LG-037 可选多模态向量；LG-038 Chat/Files | 协作线接 LG-017/018；资料界面接 LG-013/014；按真实依赖并行 |
| 3：集中验收 | LG-032 去中心化版本 QA 与全生命周期对比 | LG-040 资料与 Embedding 版本 QA | LG-022 首版门通过后，两个整合候选各自独立集中 QA，问题返修复验 |
| 4：条件扩展 | 根据 LG-032 决定是否默认启用新协作路径 | LG-041 中文转写接入与扩展版本 QA | ASR 质量达标才实施；不阻塞图片/PDF与检索版本 |

### 6.1 顺序与并行约束

> 2026-10-16 第二批集成更新：LG-017/018/019/029/034/039 已由唯一集成 owner 串行合并到 `main`（merge `2558c2a`，报告 [probes/batch-20261016/INTEGRATION-2.md](../probes/batch-20261016/INTEGRATION-2.md)）。其中 LG-018/019/034/039 与 LG-029 为 `done`（待版本 QA）；**LG-017 保持 `in-progress`**（默认 `ProgramReviewer` 只是机器检查换名，非独立模型/角色复核，目标未满足，留 LG-022 复验）；LG-041 保持 `todo` 并记 `needs decision`。LG-039 报告限定为本轮已测路径负结论，不等于完整中文质量验收。LG-021/030/035 已 claim，其余待依赖。
>
> 2026-10-16 第三批集成更新：LG-017 返修 R1（真实受控独立 `ModelReviewer` + 诚实 `unavailable` 默认，真实 DeepSeek 探针 1 次通过、usage unknown）、LG-030（受控同伴交接，默认关闭；集成 owner 加程序认证接缝 + 默认拒绝后协议自身安全）、LG-035（图片/PDF OCR 与机器/人工正式版本分层）已由唯一集成 owner 串行合并到 `main`（merge `c138537`→集成分支，报告 [probes/batch-20261016/INTEGRATION-3.md](../probes/batch-20261016/INTEGRATION-3.md)）。
> - **LG-017 仍为 `in-progress`**（实施条件已满足，但按任务硬条件须 LG-022 独立集中 QA 复验后方可 done，本包不自评完整版本 pass）；新增设置字段 `default_reviewer_connection_ref` 已最小接线到 Settings 界面（reviewer 默认选择，显式、不静默回退 worker）。
> - **LG-030 为 `done`（待版本 QA LG-032）**：协议在受保护 HTTP + 真实 `FileStore` 上满足验收；body 自报身份不作认证，程序认证接缝已就位且默认拒绝；真实 worker 身份注入与 Graph 接线归 LG-031，不再是 030 阻塞项。
> - **LG-035 仍为 `in-progress`**：产品 Python 3.12 环境真实 OCR（真实清晰页/多页 PDF，预注册阈值通过）与机器/人工分层已实现，但真实中文/表格人工真值质量门阻塞（已授权端点不可达 + 无许可明确样本），不以合成样本当真实品质。
> - 契约保持 `1.7.0`（第三批未新增字段/端点/错误码；030 执行身份边界为集成澄清）。LG-021 独立 QA 仍在 `qa/lg021` worktree 运行，本批不碰其工作区。
>
> 2026-10-16 依赖校正与状态纠正（主代理 PM，准备 owner 落盘）：**LG-036 `depends_on` 由 `[LG-034, LG-035]` 校正为 `[LG-033, LG-034]`**（技术依据 [probes/lg036/DEPENDENCY-AUDIT.md](../../probes/lg036/DEPENDENCY-AUDIT.md)，PM 决定 `checkpoints/2026-10-15/pm-decision-lg036-20261016.txt`；本项只需已交付的内容接口 `faf7230`/`d7e4391`/第三批集成提交，非 LG-035 尚未通过的真实 OCR 质量门）；**不降低 LG-035 验收、不改 LG-040 依赖、不声称图片/PDF 检索质量通过**。**LG-017 由 `in-progress` 纠正为 `done`（待 LG-022 集中 QA、非完整版本通过）**：原注释将“待 LG-022”当本项 done 前置，与 LG-022 `depends_on` 含 LG-017 形成错误循环，按 agent.md 集中 QA 非逐项前置纠正；实现目标（独立 ModelReviewer 路径）已由 R1+第三批 UI 满足。**不改 LG-022 依赖、不宣称版本验收**。这两项使 LG-031/LG-036 可按真实依赖 ready；LG-022 仍待 LG-021 增量复验。

> 2026-10-16 第四批集成更新（唯一集成 owner，报告 [probes/batch-20261016/INTEGRATION-4.md](../probes/batch-20261016/INTEGRATION-4.md)）：LG-021 增量 QA（`qa/lg021-r1` `5176edf`，26/26 真实通过）与 LG-036 词法索引（`dev/lg036` `ece758c`）已合并；**LG-021 置 `done`**（前端状态/响应式门，不等于 LG-022 端到端门）；LG-036 因 `api/app.py` 与 LG-031 并发 owner 冲突**保持 `in-progress`**（机制已实现、尚未接入默认 app）。CLI claim 仅 LG-022（`agent:pi-lg022`，`bf7851c`）；LG-037/038 依赖未满足，未 claim、未建 worktree。

> 2026-10-16 第五批集成更新（唯一集成 owner，报告 [probes/batch-20261016/INTEGRATION-5.md](../probes/batch-20261016/INTEGRATION-5.md)）：
> - **LG-031 `dev/lg031` `d4c0815` 已合并到 `main`**（`--no-ff`，无冲突）；031 owner 已释放共享 `api/{app,bootstrap}.py` 与 docs08，本集成 owner 成为唯一 writer，在同一次提交中一并加装 LG-036 `build_search_router()`（1 import + 1 `include_router`），两侧安全接线。
> - **LG-036 由 `in-progress` 置 `done`（待版本 QA LG-040）**：真实默认 app 上 `GET /api/v1/search` → 200、缺失缓存诚实 `index_unavailable`/`hits=[]`、POST → 405（GET 只读）；`uv run pytest -q` **693 passed, 1 skipped**、mypy **130 files clean**。**无向量**（LG-037 未实现）、**无 Chat/Files UI**（LG-038 未实现），图片/PDF 检索质量不声称通过。
> - **LG-031 保持 `in-progress`（非错误等 032 版本门）**：本项验收的**真实运行硬条件未满足**——031 的 1 次 DeepSeek 只是独立 reviewer，不是 SDK 多 worker；真实 Git + **进程内 fake executor** 不等于“真实 SDK 两 worker 发现/领取/交接/隔离执行”。据此**不置 done**，理由是本项真实运行硬条件未满足，**不是**“错误等待 032 版本门”（032 反依赖 031）；不把完整 checkpoint skip 未实现夸大，不扩大恢复重放。原 owner 等价续接分支 `fix/lg031-r1` 已建（保留原 `dev/lg031`）。
> - 契约升至 **`1.10.0`（LG-022 第二轮针对性返修 REFIX-R2 的加性 MINOR）**：停止门除 `cleanup=done` 外接受权威适配器真实停止确认（SDK session `__aexit__` / loopback 代理真实关闭，Run 加性新增可选 `reviewer_cleanup`；未知/活跃/失败保持 `unconfirmed` 与 `session_refs`，不伪 `done`）；`GET /api/v1/diagnostics/generation` 加性新增 `persistent`/`corrupt`，全局生成计数改为受控 dataRoot 下持久账本、转发前持久预留、跨重启不归零、损坏绝不当 0。此前 **`1.9.0`（返修后串行集成的加性 MINOR）**：新增 `source.archived` 可逆归档字段与 `archive`/`unarchive` 动作（归档保留检索/打开/权限，区别于使资料不可用的 `revoke`；含可选 `expected_revision`）并挂载可选向量端点（默认禁用、不可用时词法/原件仍可用）。此前 **`1.8.0`（LG-022 首版集中 QA 阻断项 D1/D2 返修 R1 加性 MINOR）**：新增合法迁移方向 `verifying`/`repairing → recovery_required`（复核/返修阶段重启后未知副作用诚实停车、不重放/不假终态）与只读诊断端点 `GET /api/v1/diagnostics/generation`（进程全局上游生成请求计数 `{count,limit,remaining}`，转发前计数，供集中 QA 约束/观测全局硬上限）；D1（reviewer turn 在运行中事件循环内 `asyncio.run` ⇒ 永远 `unavailable`）与 D2（复核阻塞循环、无 reviewer 生命周期）为 reviewer 实现与生命周期修复，不改既有端点/枚举语义。
> - 就绪任务 CLI claim：LG-037 `agent:pi-lg037`、LG-038 `agent:pi-lg038`（持久 worktree `lg037`/`lg038`，基于同一 claim commit）；LG-022 仍 `in-progress`，保留不重 claim。

> 2026-10-16 第七批集成更新（唯一集成 owner，报告 [probes/batch-20261016/INTEGRATION-7.md](../probes/batch-20261016/INTEGRATION-7.md)）：
> - **集成前置核对**：`main` `29ffbb6`（clean）；`fix/lg022-r2@e59e12a`（停止门真实停止事实 + 持久生成账本 + QA reverify R1 证据）与 `fix/lg031-r2@3821620`（自主领取时序 + 共享计数注入，partial）均 clean，均自 `29ffbb6`。
> - **整合候选 `integrate/batch7`**：`8a92439` `--no-ff` 合 022-r2（无冲突）、`0144eb7` `--no-ff` 合 031-r2（`adapter/__init__.py` 与 `docs/08` §9 **两处文本冲突**，逐条保留）。旧分支/worktree/probes/dirty 全部保留，未 reset/clean/覆盖/重复 pick。
> - **共享装配保持 1.10 持久账本为唯一限额事实源**：`bootstrap` 中 `configure_generation_ledger` 先于 031 的 `generation_budget=global_generation_counter()`，031 注入的是持久账本，不被旧内存计数覆盖。契约**保持 `1.10.0`**（031 未新增版本）。
> - **集成检查（绑定 `0144eb7`）**：`mypy` exit 0 → **137 files clean**；`pytest -q` exit 0 → **775 passed, 2 skipped**。**本包产品真实调用 0**；UI 未改。
> - **持久 QA/续接 worktree（基于 `0144eb7`）**：`lg022-qa-r2`（`qa/lg022-r2`）、`lg031-r3`（`fix/lg031-r3`）；**未执行 QA/真模型**，旧 worktree 全保留。
> - **状态**：**LG-022 仍 `in-progress` 待独立 QA**；**LG-031 仍 `in-progress`**（真 2 worker + 交接 + 候选 review 仍缺，续接 `fix/lg031-r3`）；LG-035/037 `in-progress`；**LG-023/032 `todo` 未 claim**；**LG-040/041 不解锁**。
> - **成本**：LG-031 累计 **10/10**，主代理新 phase3 另行授权**最多 14**，合计**上限 24**，**非 032 对照实验**；LG-022 首轮 unknown、R1 **6/10**，两轮失败记录均保留。

> 2026-10-16 第八批集成更新（唯一集成 owner，报告 [probes/batch-20261016/INTEGRATION-8.md](../probes/batch-20261016/INTEGRATION-8.md)）：
> - **集成前核对**：`integrate/batch7@85adc82` + 主代理 PM dirty `PROGRESS.md`（先独立只读保全再精确提交 `cef379a`）；`main@29ffbb6` 未收拢；`fix/lg022-stream@1dd5c67`（**已精确暂存 8 项**，未 commit）与 `fix/lg031-r3@2f04654`（clean）最终 HEAD 均核。全部旧分支/worktree/dirty/原始失败证据保留，未 reset/clean/重复 pick、未复制 `.env`；无源 owner 残留进程。
> - **合入 022 流式停止接线**：唯一收尾 commit `7d0510d`；`git merge --no-ff` → `eecbf05`（**无冲突**）。产品修复仅 `verify/review.py`：真正流式阶段承载 stop（不取消 pull + 有界重查，不丢/不重 chunk）+ 停止调 SDK `Conversation.cancel()`/有界 `wait_for_idle()`（仅 SDK 确认 idle 才为真）+ enter/chat/stream/stop/teardown 同 loop（消除已关闭 loop 偶发 `RuntimeError`）。真 SDK+本地 fake SSE：stop **0.132s confirmed**（修复前 5.027s unconfirmed），`session_refs` 保留、无残留 reviewer。
> - **合入 031 r3**：产品加性——`adapter/executor.py` proxy 上限对齐冻结 `budget.max_model_calls`；`api/bootstrap.py` G1 开关接线自主 claim + `ExecutionGrantRegistry`（缺省确定性路径）；`collaboration/execution_grant.py` G2 投影加性补 `objective`/`write`。`PROGRESS.md` 唯一内容冲突**同时保留双方**（root 最新状态 + r3 phase3/phase4/SALVAGE 检查点）；`git merge --no-ff` → **`975afc2`**。
> - **幸存原件私有保全已复核**：3 个 SDK session DB + 原 stdout 复制到 `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`（`700`/`600`），4 个 `sha256` 与 `MANIFEST`/`salvaged_handoff_evidence.json` 逐一相符且与 `/tmp` 原件 `cmp` 字节相等；原件未动、秘密原件不入 repo；`SUBTASK.md` 原始字节丢失限制如实保留。
> - **`main` 本地收拢**：`git merge --ff-only integrate/batch7` → **`main@975afc2`**（**未推送**），不止停在 integrate 分支。
> - **集成检查（真实退出码，绑定 `975afc2`）**：`mypy` exit 0 → **137 files clean**；`pytest -q -p no:randomly` exit 0 → **794 passed, 2 skipped**；backlog 根 `validate` **41 tasks/0 diagnostics**、`digest` complete → **33 done / 3 in-progress / 5 todo**。**本包产品真实调用 0**；UI 未改，未重跑完整前端。
> - **状态**：**LG-022 仍 `in-progress`**，待**新独立 QA `qa/lg022-stream`**（新持久 worktree `lg022-qa-stream`，基于 `975afc2`，不覆盖旧路径）；最新独立调查确认**重要缺陷是 stream 阶段没 cancel/deadlock（流式 stop 未接线，非单纯限制）**，旧 a41 PASS 标题不覆盖新修复。**LG-031 `done`（待 LG-032 独立集中 QA）**。**LG-023/032 `todo` 未 claim**（依赖 022 未 done）。**LG-035/037 `in-progress`**；**LG-040/041 不解锁**。**契约保持 `1.10.0`、SDK `0.1.22` 不变**，自主模式默认 off，不重新引入模型编排。
> - **成本**：LG-022 首轮 unknown、R1 **6/10**、`qa/lg022-r2` 真实 **8**（两阶段不同账本，未执行统一总额硬限，非产品账本缺陷）；LG-031 累计 **34/40**（旧 24 + phase4 10，不重放/不归零）；**本包产品真实请求 0**。

> 2026-10-16 核心首版 QA 收口更新（唯一串行验收证据整合/排期 owner，报告 [probes/batch-20261016/CORE-QA-CLOSE.md](../probes/batch-20261016/CORE-QA-CLOSE.md)）：**本包产品生成 0**（不执行评估/新探针/不重跑模型或测试）。
> - **独立 QA 退出**：`agent:pi-lg022-stream-qa` 已退出，worktree `qa/lg022-stream@49c95f5` clean、**仅 14 个 QA 文件**（产品/ docs 零改动）；结论**门内 PASS、无未修重要缺陷**（`stream-stop-hard-gate.json` `hard_gate_pass=true`；`main-chain-verdict.json` `ok=true`，真 DeepSeek 5/10 到绑定 accept）。
> - **merge（仅 QA 证据）**：`git merge --ff-only qa/lg022-stream` → **`main@49c95f5`**（`e0a8cec..49c95f5`）；产品树与 `e0a8cec` **逐字节相同**（`git diff` 产品路径为空）⇒ **不重跑全量 pytest**。旧 worktree/dirty 全保留，未 reset/clean/覆盖/重复 pick、未复制 `.env`。
> - **LG-022 → `done`（仅门内范围）**：仅「首版端到端 + 本次流式停止缺陷独立真实复验」；**不宣称整产品 pass**，旧错误 PASS 标题不覆盖本次流式修复，历史两轮失败如实保留。**准确门范围**：真 SDK+本地 fake SSE 流式停止 PASS、真 DeepSeek 主链一例 PASS；**未测**：真实 DeepSeek 上游下 cancel/pause-during-review、重启后 `verifying`/`repairing → recovery_required`、跨 Run 真实 reject/repair、light/浏览器矩阵；**SDK 取消已用真 SDK+本地 SSE 证明，不冒充 DeepSeek 故障**。
> - **成本（不归零）**：022 首轮 **unknown**、R1 **6**、R2 **8**（两账本未统一、未执行统一总额硬限，非产品缺陷）、本 phase **5/10**、本收口包 **0**；031 工程 **34/40**（原运行 SoT 部分字节丢失，但 SDK 原件（3 session DB + stdout）持久备份、硬条件 4 只读哈希恢复，恢复限制保留）。**源哈希核准**：流式修复源为 **`7d0510d`**，QA 报告叙事 `7d0510c` 为笔误（仓库不存在该提交），本汇总按 git 引用正确哈希、不篡改原证据。
> - **LG-023 排期**：`validate` 41 tasks/0 diagnostics、`digest` complete、LG-023 `ready` 后 **CLI 原子 claim `--as agent:pi-lg023`**，创建全新持久 worktree `lg023`（`dev/lg023`，基于最终 main/claim；路径存在先核不覆盖）；**本包不执行评估**。**预算（采样前最终修订，非看结果后改额；样本/门固定 2 任务×2 arm×一次）**：**4 attempts/总 48/每 attempt 12**，全 stage 同 phase 持久 ledger，**output ≤16000/HTTP 120s/retry 0/并发 ≤2**；**旧 16/24/6 为未执行草稿作废**；按已见真实双 worker 链约 10 calls 为**双方 arm 设同样足够 cap**。
> - **LG-032 暂不 claim**（原 ready ≠ 立刻占有；待 023 评估后与 LG-024 并行排期）。
> - **状态**：**LG-022 `done`（门内）**、**LG-031 `done`（待 032）**、**LG-023 claim 后 `in-progress`**、**LG-032 `todo` 暂不 claim**、**LG-035/037 `in-progress`**、**LG-036/038 `done` 待 040**、**LG-040/041 `todo` 不解锁**；自主模式默认 off；**契约保持 `1.10.0`、SDK `0.1.22`**；未推送/部署/发布。

> 2026-10-16 QA/方法审计证据集成与 AUTH/POOL/EVAL 三线返修排期（唯一串行 PM，报告 [probes/batch-20261016/AUTH-POOL-EVAL-HANDOFF.md](../probes/batch-20261016/AUTH-POOL-EVAL-HANDOFF.md)）：**本包产品真实生成 0**（不实施代码/新 QA/新真实 cohort）。
> - **集成**：先保全主代理 PM dirty（`4174e23`），再**仅证据/harness/PM 文档**安全合并 `qa/lg032@ad3d97b`（→`6a7fe72`）与 `fix/lg023-method@99ad735`（→**`51b7c9e`**），均无冲突、双方保留；产品路径 diff 为空 ⇒ 不重跑全量测试；旧 dirty/worktrees/记录不 reset/clean/覆盖/重复 pick。
> - **LG-032 阶段 A（partial）**：核心机制 PASS；**F2 claim/lease HTTP 端点接受请求体 `owner`、未接程序认证身份 = 重要缺陷**（不符 LG-028 §2.4）；**F1 自主 claim=程序预选唯一节点后挂工具 = 部分符合**。**LG-029 `done→in-progress`**（F2 返修，`fix/lg029-auth`）；**LG-031 `done→in-progress`**（F1 补齐多候选真正 worker 自主申请，`fix/lg031-pool`）；保留原 assignee/历史 done/受限链证据，等价续接。**LG-032 保持 `in-progress`/partial，阶段 B 暂停**；**LG-023 保持 `in-progress`**，**LG-024 仍 `todo` 不解锁**。
> - **新建 3 个持久 worktree/分支**（基于 `51b7c9e`，先查不存在不覆盖）：`lg029-auth-fix`/`fix/lg029-auth`、`lg031-pool`/`fix/lg031-pool`、`lg023-cohort2`/`eval/lg023-cohort2`（只评估 harness，产品/共享 docs 只读，两 arm 统一旧程序调度路径，比较计划写节点数 1 vs 2）。029/F1 实施包产品请求 0。
> - **023 新 cohort PM 预注册**：2 样本×2 arm×1 repeat=4 attempt、每 run 仅 1 次；总 48/每 12、全 stage 单持久 ledger、转发前硬限；旧 45 另列，eval 已知总实际上限 **93**；双方同 toolcap 32、modelcall 每 worker≤12 且同 attempt≤12、output≤16000/HTTP120/retry0/并发≤2；必须真正走完整 Coordinator+stopconfirmer；旧混淆 45 不计交付成本也不删。**旧停止门不是产品 bug**（harness 缺陷）。契约 `1.10.0`/SDK `0.1.22`/自主 off 不动。

> 2026-10-16 LG-024 阶段 B（交付准备：文档一致性 + 本地可审阅 L0 包；owner `agent:pi-lg024`，报告 [probes/lg024/STAGE-B/REPORT.md](../probes/lg024/STAGE-B/REPORT.md)）：**本包产品真实模型生成 0**；**未推送/部署/发布/上传**。
> - **绑定首版核心稳定产品树 `e0a8cec`（= `main` `66b2b10` 产品路径，逐字节相同）**；契约 `1.10.0`、SDK `0.1.22`。**协作候选 `integrate/lg031-runtime@afcae82` 未合 `main`、独立 QA R1 进行中，单列待版本 QA，不入本包**。
> - **串行落地共享文档**（阶段 B 起共享 docs 已释放）：README 新增「首版使用指南」（安装/启动/Settings worker+独立 reviewer/Chat 轻问答与交付 Task/Files 原件与来源/Resources 与恢复入口）；docs/06 本条目增补。**docs/08 仍归 runtime 返修 owner，本包不写**。
> - **L0 源包**（`probes/lg024/STAGE-B/dist/*.tar.gz` + `MANIFEST.sha256` + `PACK-ANCHORS.txt`，405 文件）：严格无 `/home/yhvh/` 绝对路径/秘密/DB/日志/依赖体；**排除**开发/PM 证据（`PROGRESS.md`/`agent.md`/`BACKLOG.md`/`backlog/**`/`PROJECT.md`/`docs/08`/`docs/contracts/LG-033-preparation.md`，repo 保留不分发）。修正 Stage A 的 17 条绝对路径 WARN。
> - **真实解包烟测**（专用端口 `18433`、独立 data/secret、`--no-executor`）：离线 `uv sync` 成、health 200（契约 `1.10.0`/`sdk_adapter=false`）、version 200、index 200 + 静态 JS 资产 200、无 token 受保护写 **401**、stop 0 且端口释放；**不碰 `:8123`**；产品真实模型 0。
> - **许可**：L0 不重分发第三方包体/SDK/weights；随附 `NOTICE.md`（运行时 51 包版本与许可、前端 224、pypdfium2 捆绑 CC-BY-4.0、Olav=BSL-1.1 不搬运）；**项目自身无 LICENSE/NOTICE、未选公开许可证⇒未授予公开再分发**（不代用户选）；**未发布**。
> - **范围如实**：029/031/032 返修未验；035/037 真实质量未齐；039 负结论/041 锁；040 未开；完整 checkpoint skip 未实现；023 两小样本组队无收益且 usage/费用 unknown（旧 45+4 单列）。**服务可达/合成样本/Embedding 输出 ≠ OCR 转写品质**；本包**不宣扬完整产品 pass**。
> - **状态**：LG-024 阶段 B 达原交付准备门后可置 `done`（**仍非发布授权**）；契约/SDK/自主 off 不变。

> 2026-10-16 最终批次收拢与 LG-032 评估范围关闭（唯一 main 最终整合/PM 文档 owner，报告 [probes/batch-20261016/FINAL-BATCH-REPORT.md](../probes/batch-20261016/FINAL-BATCH-REPORT.md)）：**本包产品真实生成 0**。
> - **安全收拢（串行、无重复 pick）**：`prep/lg035-real-truth@9ad8315`（ff-only，main 为直接祖先）→ main `9ad8315`；`qa/lg032-close-audit@4d175113`（`--no-ff`，merge-base `0814b80`）→ merge `d0c0c4e`。**产品树未变**（`HEAD:backend/lightgravity = 55e4de56…`，产品路径 diff 为空）⇒ 不重跑产品全套测试；旧 worktree/实验/失败证据全部保留。
> - **LG-032 → `done`（仅「评估范围」）**：独立封账 `probes/lg032/CLOSE-AUDIT/CLOSE-REPORT.md` 判 **PASS**。有效 cohort3 `4/4` 各唯一次全真实 delivered/first-pass，actual mode `off/on/off/on + restored off`，唯一物理 ledger `0→20→40→57→84`（84≤192），异步真实独立 ModelReviewer passed/0 unsubstantiated。**旧 106**（cohort1 87 invalid + cohort2 19 STOP）**永久单列**；032 本轮真实已知 **190=106+84**，上限 298 未超。**default off/回退保留**；**全 cost unknown、收益不支持默认启用**；**非全产品 pass**；2 tiny case 无统计承诺。
> - **LG-035 `in-progress`**：TRUTH-PREP 已备两份严格配对真实中文样本（Z1 PD 书页扫描 + 人工 level-3；Z2 PD 表格扫描 PDF 18 页无 text layer）；**真实 OCR/embedding/ASR 0 新调用、quality NOT measured**；GET `13/12` 超 1 保留 + 授权补 Z2 → 累计 14；**不解锁 040/041**。**LG-037 `in-progress`**（真实 vectors quality 未达）。**LG-040/041 `todo` 不解锁**（041 中文 ASR 质量锁）。
> - **唯外部 block**：候选资料服务 `192.168.8.12:11434` 仍不可达（health/models HTTP 000、无 TCP、0 POST；llama.cpp/OpenAI-compatible）；恢复后先 health/models/预算 freeze → OCR/embedding 质量门 → 040；ASR 独立达标才 041。**不因 XFUND NC/普通实现选择要求用户确认**。
> - **CLI 实读**：41 tasks / 0 diagnostics；`2 todo / 2 in-progress / 37 done`；`ready=[]`（可执行部分已完成，非未认领）。契约 `1.11.0`/SDK `0.1.22`/自主 off 不变。

- 当前优先收拢 LG-013、LG-016、LG-027 已有隔离成果，继续 LG-017/018/019 与既有首版集中验收；单独 worktree 的交付不视为 main 已集成。不在本次排期中改变其状态。
- LG-028 与 LG-033 可独立准备；LG-039 可在 LG-033 后验证。实现以任务 depends_on 为准，两个新版本的 LG-022 依赖是保留首版验收的排序门，非新功能代码依赖。
- 多条线共享 Store、Coordinator、API 或前端入口时指定单一 owner 串行集成；开发执行仍经 pi，不因排期自动派工，不采用宿主原生子代理替代。
- 不以 Embedding 作为摄取/OCR/词法索引的前置；LG-038 不依赖 LG-037，向量后端故障仍可查看原件和词法查询。LG-040 同时覆盖可选向量路径。

### 6.2 新增版本集中验收门

- **去中心化协作版本（LG-032）**：覆盖 LG-028～031；权限和状态仍由程序控制，真实竞争领取、崩溃恢复、同伴交接、隔离整合、独立复核与有限返修均需验证。同任务/基点/模型/预算/验收门比较程序调度基线与新路径，统计执行＋QA＋返修＋复验＋失败尝试的 token、耗时、成功率及人工介入。预先固定样本、次数与费用上限，结论不支持时保留开关或回退，不预先宣称降低成本。
- **资料接入与 Embedding 版本（LG-040）**：覆盖 LG-033～038 的图片/PDF、Chat、Files、词法与多模态向量检索；验证真实界面、来源权限、校订版本、失效与重建、服务不可用降级。LG-039 的验证结果如实披露，中文转写不作为该门硬依赖。
  - **语言政策（2026-10-16 用户市场范围决定）**：本门验收**以英文为主线**——英文正文/表格/图片/查询/UI/错误流（上传/归属/校订/重处理/撤销/重建/ACL/限制/取消/重启）与词法/向量降级，版本 PASS 前必须先覆盖完整英文质量/端到端。中文以当前水平支持、抽样回归、限制照实披露；**中文图片排名 7 本身不再单独阻断英文导向版本的 QA**（旧中文图片硬门 FAIL 作为历史质量结果保留）。**安全/数据丢失/权限/假成功无论语言始终阻断**。这是**前瞻性范围/接受决定，非追溯实验通过**；**不表示英文 E2E 已证明**，也**不解除 LG-041 中文 ASR 锁**（英文市场不等同支持英文 ASR）。
- **中文转写扩展版本（LG-041）**：LG-039 的报告完成不足以解锁，必须质量结论达标；实现后集中独立 QA 真实人声到成文、索引与时间范围回源。没有合格 ASR 则继续保留原件与明确失败状态，不宣传支持转写。

任务内只做必要局部检查；独立 QA 在上述整合版本门开展。验收者独立于实施者，经 pi 派出。不得将派工平台、模型端点可达、合成样本或局部构建通过作为完整产品验收。

### 6.3 边界与暂缓项

文件与 frontmatter 保持 SoT，JSONL 记录历史；词法和可选向量均为可重建缓存。EmbeddingGemma 2 作为候选接入现有已测服务，地址与模型可配置，不硬编码 LAN 依赖；不保证中文 Reader、生产 OCR 或检索质量已经达标。LG-028/033 已由单一 owner 串行加性冻结为契约 1.6.0（**仅接口、未实现**，去中心化默认关闭）；LG-017 返修 R1 的独立复核者设置角色/字段、Task 返修账本与 review/rework 事件 payload 加性登记为契约 1.7.0（**加性、非秘密、不新增端点/枚举**；程序机器门不等于独立复核，无可用 reviewer ⇒ `unavailable` 且阻止 accept）。LG-022 首版集中 QA 阻断项 D1/D2 返修 R1 加性升 `1.8.0`（新增 `verifying`/`repairing → recovery_required` 与全局生成计数诊断端点）。返修后串行集成收拢加性升 `1.9.0`（`source.archived` 可逆归档 + `archive`/`unarchive` + 可选向量端点挂载）；LG-022 第二轮针对性返修（REFIX-R2）加性升 `1.10.0`（停止门真实停止事实 + `reviewer_cleanup` + 持久生成账本诊断字段 `persistent`/`corrupt`）。第三批集成（LG-017 R1 / LG-030 / LG-035）契约保持 `1.7.0`（未新增字段/端点/错误码），实现以该版为准，集中 QA 归 LG-032/LG-040。

Office 完整转换、文件夹增量、网页正文抓取、邮箱连接器与外部聊天渠道本轮暂缓。链接仅记录时明确未抓取，不制造已入库结果。暂无人力/每日投入/截止日期依据，因此此处承诺依赖顺序与验收范围，不承诺完成日期。
