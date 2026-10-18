---
title: "LightGravity Bot 项目手册"
doc_type: handbook
category: project
updated: "2026-10-18"
---

# LightGravity Bot 项目手册

> **Demo录制修复候选已本地集成（2026-10-18，LG-251；未部署）**：隔离分支 `work/lg248-candidate-20261018` 基于 native Files/hint `cd755da`，按内容去重后串行合入 LG-208 parse cache、LG-244/LG-243/LG-249 后端链、LG-224 PDF 文字层，并把契约升至 **1.23.0**（§24）。新端点/DTO/投影字段为加性，但**不是纯加性批次**：LG-249 有意把 Team Task 普通消息改为默认只记录、仅前导配置 mention 才路由；单用户路由不变。候选包含只读 canonical `TASK.md`、机器检查 required/绑定/验收状态、每 Run 的计划 worker 与真实 reviewer 执行证据、PDF 文字层优先，以及真实 `health.team_bot_mention`。已运行受影响后端/前端测试、typecheck、build；前端完整套件为 **400 通过/1 失败**，`lg120` 分页失败保持 **OPEN/未分类**待 native Files 处置，隔离复跑 5/5 只作线索，不据此判为 flake。候选状态 **PROVISIONAL，LG-251 未完成**；这是开发者集成证据，**不是独立 QA**，公开 8123/5173 仍为 1.20.0，未推送/合根/部署，LG-252 浏览器录制验收待新采集门批准。详细登记见 docs/08 §24。

> **品牌已上线、ASR远端待接通（2026-10-18）**：LG211品牌子集112项独立浏览器检查+29前端测试通过；LG212已将Logo/默认账号说明上线8123，root main8a3f04d7，实际生产44项通过，后端仍原1.20/PID536200、ASR关闭rev1，三个服务未重启、账户/资料保持。5173品牌源码同步，不把其他开发改动算入本包验收。[部署记录](probes/remote-reader-20261018/lg212/DELIVERY.md)。LG213一次现有默认SSH密钥认证被192.168.8.12拒绝，远端帧服务实际部署/转写联调需要可用入口；原质量FAILED与里程碑169待完成保持。Reader容器已构建、加载约640～874MiB，尚未测实际推理峰值。

> **已选实施方案（2026-10-18）**：用户选择“192.168.8.12运行EmbeddingGemma 2编码，本地容器只运行Reader”。音频逐帧特征经远端接口送到本地Reader，转写复用原摄取/frontmatter/索引/回执/UI，不在本机加载编码器、不把池化向量冒充帧特征。2核/2GB为Reader容器起测配置，实际资源待独立测量。先核实llama.cpp与Reader特征接缝（LG175），并行准备Reader容器（LG176），匹配后接入应用（LG177），统一LG172版本QA与LG173部署。远端所需的增量特征接口可在现有服务旁隔离部署，保留原向量/TTS服务；远端部署入口已询问，未收到前不猜凭证。若现有量化模型特征不匹配，保留失败证据并报告，不擅自替换模型或恢复本地编码。

> **ASR部署目标纠正（2026-10-18）**：用户明确ASR应使用192.168.8.12上的EmbeddingGemma模型。此前LG171启用本机CPU编码器/Reader偏离该意图；本机QA已停止，原推理与失败质量记录保留，不作为远端验收。LG174核实远端转写/帧级特征与Reader接口并关闭误启用的本机路径，后续按远端方案接通UI。LG170的Logo与默认登录说明成果保留，尚未部署。

LG174调查已完成：[报告](probes/demo-brand-asr-20261018/lg174/REPORT.md)。本机ASR已关闭、8123健康/账号保持；192.168.8.12:11434现提供EmbeddingGemma2 Q8_0多模态mean pooling向量，尚未找到公开Reader/转写服务。pooling none返回token向量并不自动证明匹配Reader音频帧契约。远端部署入口和产品remote runtime是后续接入缺口，当前尚未接通远端ASR。

> **最新交付（2026-10-17，LG-104 done）**：main df53ead／契约1.17.0／8123 PID2707896已提供连接列表＋紧凑New/Edit弹窗、Provider条件字段、草稿先测后保存及Advanced。独立R2 PASS：真实前后端8浏览器场景、1440/1024/390、受控引用/删除并发与API/秘密/权限回归通过。首轮真实并发缺陷及过多技术说明已由native修复、pi集成后复验，失败历史保留。DeepSeek弹窗540宽、填写591.5高/空617.5高，无裁切；新provider仅配置/手动测试，native任务执行和任意custom host放行未扩展，未做真实供应商或LiteRT硬件验证。全局次数无限额计数0、no-executor、团队身份/账号/资料和其他服务保持；未推送。[独立QA](probes/provider-setup-20261017/qa-r2/QA-R2.md) · [交付与截图](probes/provider-setup-20261017/qa-r2/DELIVERY.md)。下方运行/源码“最新”为此前历史快照。

> **最新连接入口更新（2026-10-17，LG-103）**：main85d009d／8123已保留完整 Settings 连接管理并移除独立侧栏 Connections；其余六资源保持直达。Team／资源引用与旧深链定位 Settings 对应稳定ID，Task/Run保留，未知目标不误选；成员仅得管理员管理提示和MyAccount，未请求管理员配置。68项相关回归、导航Playwright6/6、真实后端浏览器72/72、类型／构建通过；小批次待后续版本QA。源数据／后端API／三个服务PID保持，无模型调用／推送，契约仍1.16.0。[交付与截图](probes/settings-connections-20261017/DELIVERY.md)。

> **最新导航图标更新（2026-10-17，LG-102）**：main503dca3／8123已替换七类资源入口与底部Settings为统一线性SVG，功能、标签、路由、布局保持。23项既有回归、类型／构建及真实前后端Playwright9/9通过，覆盖1440/1024/390；小任务待后续版本QA。后端及另外两服务未重启，原dirty／数据保持，无模型调用／推送。[交付与截图](probes/nav-icons-20261017/DELIVERY.md)。

> **最新文案更新（2026-10-17，LG-101）**：main bd3b13b，8123顶栏搜索框占位及可访问名称简化为Search；布局和真实搜索保持，14项既有shell回归及类型／构建通过，三个服务未重启。[交付](probes/search-label-20261017/DELIVERY.md)。

> **最新界面更新（2026-10-17，LG-100）**：Search materials 已改成顶栏居中的可编辑搜索框，主线 `52ca568`，8123 静态资源已更新、后端未重启，契约仍1.16.0。Enter使用既有真实资料搜索，Escape关闭结果并返回焦点，结果可回链Files；1440/1024居中与390无溢出通过真实前后端Playwright，35项相关回归与类型／构建通过。小任务交付，待后续版本QA，未新增独立版本门。原dirty、用户数据及三个服务PID保持，无模型调用／远端推送。[交付与截图](probes/centered-search-20261017/DELIVERY.md)。

> **最新运行更新（2026-10-17，LG-099）**：用户授权重启后，http://192.168.8.50:8123 已运行 `main@ca58b35`／契约 **1.16.0**，前端生产包与已验收构建摘要一致。健康／静态资产／匿名保护及真实Chrome登录页冒烟通过；原账号／业务文件保持，模型执行关闭、生成计数0→0。旧进程停止超时后CLI强制结束；5173因主机监听资源耗尽退出，已以同端口／代理和轮询监听恢复，18123原进程未变。可能需要重新登录，无远端推送／发布。[重启记录](probes/generic-merge-20261017/RESTART.md)。下方“8123仍旧版本”为此次重启前快照。

> **最新主线交付（2026-10-17，LG-094～098）**：八项通用协作与可靠性改动已选择性合入 `main@ca58b35`，契约 **1.16.0**，完整提交树与独立 QA 候选 `2024205` 一致。独立首轮 QA FAIL 揭露原始长前缀交付误判，原生 Codex 返修后复验 **PASS_WITH_LIMITATIONS**；新真实浏览器 7/7、32 条边界、220 协调器／契约与类型检查通过，未变前端216项及旧14浏览器按同树复用。未导入游戏角色／固定招募映射／演示预算数据，通用角色自动招募仍未完成。既有 dirty／索引／数据保持，8123／5173／18123 未重启；8123 仍运行契约1.15.0的旧进程与构建。未推送／发布／部署，无产品模型调用，用户最终验收待定。[交付与保全证据](probes/generic-merge-20261017/DELIVERY.md) · [独立复验](probes/generic-merge-20261017/qa/QA-R2.md)。下方“最新”均为此前历史快照。

> **GitHub 推送更新**：2026-10-17 用户要求推送后，已将独立源码导出仓库正常推送至 GitHub main，提交 [376b6bb](https://github.com/yhvh-chen/lightgravity-bot/commit/376b6bb46c3c7ac21f1b9acda3c6e34f68ce4195)。250 个发布文件，应用源码与 main b6c738d 一致，英文 README 已更新；内部开发历史、文档、测试、运行数据及真实密钥未发布。构建／依赖／密钥扫描通过，远端 HEAD 和 main 已核对一致。根工作区既有改动和运行服务保持；Gitea 未推送。 下方“未推送”为此次推送前快照。

### 最新交付（2026-10-17，账户管理版本）

账户管理版本 LG-061／062 已完成：main b6c738d、契约 1.15.0，产品／测试树与独立 QA 固定 dbf7b0c 一致。最终独立 QA PASS：30 Chromium E2E、18 独立浏览器检查、3 次导航稳定性检查通过；产品相同树沿用 1061 后端通过／2 跳过、181 前端和跨进程安全证据。当前 http://192.168.8.50:8123（0.0.0.0:8123，PID 1093724）另有 27／27 真实普通浏览器检查通过。用户指定 admin/admin123 已生效，Settings 提供 Accounts 与 My Account；已有账号／资料保持，首次空库初始化不覆盖后来改密。无真实产品模型调用，保留 no-executor／cap0，未远端推送，用户最终验收待定。 [完整证据](probes/accounts-20261017/README.md)。下方授权及早期运行快照保留历史；旧初始随机密码交接文件已在 LG-061 移除，不再作为登录方式。

### 实施授权（2026-10-17，账户管理版本 LG-061／062）

用户已要求实施既有两项任务。顺序为 LG-061 默认管理员与当前 admin 一次性改密，再 LG-062 Settings 账户管理；整合后由新的独立 pi 集中 QA／Playwright，缺陷交 Codex 子代理。默认初始化不覆盖已存在或用户后来修改的密码；管理能力包含列表、新增、启用／禁用、角色、本人改密及管理员重置，并保护最后一个可用管理员和会话撤销。成员通过 Settings 的个人账户区域改密，管理员管理区域及模型设置保持权限限制。现有 LAN 服务数据与关闭模型执行策略保留，最终更新本地运行入口，不自动推送。

### 历史：新增任务计划（2026-10-17，授权实施之前）

用户要求添加任务：先按指定默认凭据完成管理员登录，再在 UI 中加入账户管理。当时记录 [LG-061](backlog/tasks/LG-061.md) 与依赖它的 [LG-062](backlog/tasks/LG-062.md)，当时均为 todo；具体凭据与验收条件见任务正文。账户管理计划覆盖列表、新增、启用／禁用、角色调整和密码修改／重置，沿用既有认证、账号存储及 Settings 入口。本轮只维护计划，未改当前密码、运行服务、源码或 UI，未启动 pi 或子代理。

> **历史运行更新（2026-10-17，LG-060；现已由 LG-061／062 更新）**：当前入口 **http://192.168.8.50:8123**，监听0.0.0.0:8123，已启用现有团队账号登录，普通浏览器不再卡在单用户 X-LG-Token 页面401。main@ea6da80／契约1.14.0／构建不变，实际登录与退出、导航及设置验证36/36通过。初始账号admin，密码仅在服务器受保护文件，不写入项目文档。Personal私聊，Team共享任务／资料；无执行器、模型生成0／0，未推送。[LAN交付记录](probes/lan-publish-20261017/README.md)。下方LG-051的单用户与loopback运行描述是此次变更前的验证快照。

> **历史交付更新（2026-10-17，LG-051）**：七项界面问题及 QA 暴露的相关缺陷已完成技术交付，主目录 `main@ea6da80`、契约 **1.14.0**。冻结候选 `602c7af` 的 backend/frontend/tests/e2e 子树与主目录一致；独立 pi QA **PASS_WITH_LIMITATIONS**：1004 后端通过／5 跳过、171 前端测试通过、22+28 项 Chromium Playwright 通过。支持的本地入口 **http://127.0.0.1:8123** 实际另有 30 项检查通过，Settings 受保护写入及临时连接清理已验证，真实模型生成保持 count=0/limit=0、`--no-executor`。59 项任务：58 done、1 todo（原 LG-041 质量门）、0 in-progress／0 diagnostics，ready 为空。未推送，用户最终验收待定。[交付记录](probes/ui-repair-20261017/README.md)。下方旧“当前”字段均为历史快照。

### 2026-10-17：界面修复交付决策

- 单一左导航、七类资源直达、顶部资料搜索、简洁输入与 Files 的真实 Task 对话入口已落地，移除第二上下文栏及顶栏 Scope/Run。
- 团队 Personal 是当前身份私聊且仅聊天；共享 Task／资料走 Team。默认单用户仍可在 Personal 中执行原 Task／资料流程，Team 禁用并说明。私有 Task／资料、多租户不在本轮范围。
- 核心界面支持稳定契约 >=1.13,<2；团队 Personal 还要求 >=1.14 与明确 personal_chat 能力。不将缺少接口／身份当作管理员或可用。
- Codex 主代理管理，pi 开发、串行集成与独立浏览器 QA，Codex 子代理修复。确认并修复 WAL 初始化锁竞争、新资料索引缺失、账号草稿／迟到响应串用、Files 及路径摄取私有数据旁路、首次工作目录缺失等具体问题。
- 先前失败、错误测试命令和 fixture 修正均保留，不把后续通过改写为一次全绿；Firefox 未跑、部分异步／身份分支通过单元回归验证。未调用真实产品模型，开发 token／费用未知。
- `.env` 的 deepseek-api 只在 pi 子进程内映射使用，未写入产品配置；已有文档和 .gitignore 修改保留。本轮仅本地更新，GitHub/Gitea 未推送。


> **历史更新（2026-10-16，LG-050）**：共享团队聊天与简单认证已合入 `main@4b0dd20`，契约 **1.13.0**，主目录前端生产包已重建。独立 QA **PASS_WITH_LIMITATIONS**（58 项真实 HTTP 检查、Firefox 双用户独立上下文登录/轮询互见/退出通过）。50 项任务：49 done、1 todo（LG-041 中文 ASR 质量门），0 diagnostics。用户最终验收待定；现有服务未重启，未 push、未发布部署。下方原“当前状态”为 LG-049 收口的历史快照；本次事实以此更新和 [LG-050](backlog/tasks/LG-050.md) 为准。

> 更新：2026-10-16。**当前状态：LG-047 选定资料快速原型命名里程碑独立 QA 已 `done`（PASS_WITH_LIMITATIONS），LG-049 完整生命周期验证已 `done`（PASS_WITH_LIMITATIONS）；LG-040 已 done；LG-037 已 done；LG-041 仍 todo 且阻塞于中文 ASR 质量门。当前契约 `1.12.0`、SDK `0.1.22`。任务 CLI（`backlog` 根，实测）：`49 tasks / 0 diagnostics`、`digest` 48 done / 1 todo / 0 in-progress、`ready=[]`。产品树 `main` == `0188ca2`（backend `8b4256a4…`/frontend `07618bb2…`/tests `9a37448e…`/examples `63ee05cd…`）。用户最终验收仍待定、未发布/未部署。**（此前“当前状态”为 LG-040 收口时的 **41 任务**快照，已过时且具误导性，现更正为当前 49 任务口径；其下阶段描述为早期历史快照（含旧契约版本如 1.7.0），保留不改，最新决策见文末决策日志。）** 阶段：LG-001 契约已冻结（docs/08 当前 1.12.0：1.1.0 将首版真实后端定为 DeepSeek，1.2.0 登记 LG-008 加性控制字段，1.3.0 登记 LG-009 验收字段/端点与全局对话，1.3.1 将 LG-014 文件上传/下载标为已实现并澄清证据引用语义，1.4.0 登记 LG-015 受控资源写入/Team 端点与 Task 消息 `resource_proposal` 字段，1.5.0 登记 LG-020 的 `connection_pin` 加性字段与 canonical evidence 预览/下载端点，1.6.0 由单一 owner 串行加性冻结 LG-028 去中心化协作与 LG-033 资料摄取/检索两线接口，1.7.0 为 LG-017 返修 R1 的加性独立复核者设置角色/字段，1.8.0/1.9.0/1.10.0 为 LG-022 加性返修，1.11.0 为 LG-031 runtime/API/SDK 集成落地后的保守加性 MINOR，1.12.0 为 LG-042/LG-043 selected-material 加性可选字段），LG-002 工程骨架可运行，LG-003 SDK 探针完成（核心能力经真实 DeepSeek 实测通过；Gemini/Vertex 未验收，`search_web` 不可用），LG-004 存储层、LG-005 角色/SDK 资源配置编译（已将 `google-antigravity==0.1.22` 锁定为产品依赖）、LG-006 正式 executor + 产品侧 loopback 认证代理（真实 DeepSeek 验证：文件/diff、结构化结果、用量、预算、会话恢复、确认取消；真实调用 12，进程无残留）、LG-007 消息路由与 Task 队列、LG-008 自动组队与依赖调度、LG-009 产物验证与人工验收、LG-011 前端壳层、LG-012 查询 API 与持久事件订阅、LG-025 模型设置与凭证后端、LG-026 Settings 模型接入页面、LG-014 Files 上传/下载与任务证据预览、LG-015 Team/Resources 管理视图与受控资源写入、LG-020 本地启动/停止与一体分发入口均已完成并整合到 `main`；其中 **LG-010 最小真实开发闭环已通过独立版本 QA（pass/done）**，其余 16 项均**待版本 QA**。LG-013 实施已按真实 API 接线完成并置 `done`（Chat/Board 接入真实历史与 phase，新增 `coordinator/dialogue.py` 无工具直答，未配置默认协调连接/凭证时诚实 `unavailable`，经 `create_app(responder=...)` 注入且保留现有 Resource/Verifier 端口），但**完整浏览器 HTTP 业务路径仍归 LG-021/022**，不等于完整浏览器 HTTP 端到端；LG-027 已就设置/凭证生命周期完成独立专项版本 QA **pass**，其范围限于设置/凭证的 CLI/HTTP 与浏览器渲染，**不等于完整浏览器 HTTP 端到端**，且真实调用计数产品未暴露（报告中的旧上限 5 + 恢复硬上限 4 仅为指令/运行预算，不视为已验证实际调用次数或精确上界）。LG-016 恢复能力已在独立 worktree 完成（暂停/取消确认、中断恢复、跨 Run 原生会话续接、稳定 reuse identity 与显式 `recovery_required` 反重放守卫），本轮已整合到 `main`，但完整 checkpoint skip 调度尚未实现，不夸大恢复能力。主前端构建现已挂载 Settings、Files、Team 与 Resources 视图，分别接线 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*` 与 `/api/v1/resources/*`；Files 上传复用 LG-026 运行时 token helper 注入 `X-LG-Token`，无 token 时上传如实返回 `unauthorized`；Team/Resources 受控修改经 Task 对话 `resource_proposal` 提议（sensitive 授权、`message_id` 幂等、`expected_revision` 版本检查，结果写回同一 Task 对话，不创建 Run/不等 worker、不热替换活跃 Member 配置）。LG-020 提供 `lightgravity start/stop/status/init`、默认 loopback、token 内存握手与 `index.html` 注入、Host/Origin 守卫、敏感写默认拒绝、缺认证可读历史/设置；首启幂等种子 `lg-default-worker`（有界文件工具 `view-file`/`create-file`/`edit-file`，无 `run-command`/web 无边界工具），Settings-only 建连接/存凭证/静态测试/设默认后新 Task 可达 executor，Run/Member 固定非秘密 `connection_pin`；canonical evidence 产物经 Task 产物 API（`GET /tasks/{id}/artifacts`、`.../artifacts/content`、`.../artifacts/download`）由 Task/Run evidence resolver 授权预览/下载，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符。敏感写仍由 `LocalAccessPolicy` 默认拒绝。旧 QA“浏览器全 HTTP/fetch 阻断”结论已被 root `probes/browser-diagnostics` 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，**仅顶层 `Page.navigate` 到 `http://` 在本机 headless Chrome 挂起**；原报告作为历史保留（不复述错误当新事实）。不宣称全部页面可用。首版唯一真实执行路径为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek。集成后 `create_app` 已装配 Store/Coordinator/VerificationService 并挂载 `/api/v1` 路由；accept/reject 合并进 API actions，只读 `GET /tasks/{id}/acceptance` 独立挂载，新增单例全局对话 `GET/POST /api/v1/conversations/global/messages`；默认执行器仍是诚实的 `UnavailableExecutor`（未伪装可执行）。真实 SDK 端到端、浏览器验收分别留 LG-010、LG-021/022；LG-010 最小真实开发闭环已经独立版本 QA 复核 **pass/done**（`probes/lg010/reports/lg010-qa-r2-after-refix.md`）：首轮两项阻断（executor 绝对 `diff_ref` 被机器检查误判、交付完成后未自动触发验证）已返修，第 2 轮复验发现的重复 ack(`target_run_id`) 非幂等问题已按 Task 作用域幂等键返修并经独立复验确认消除，`status: done`、`blocked_by` 已移除。**该 QA 只覆盖契约 1.3.1 core 的最小后端闭环（真模型证据基点 `ffe7a63`，真实调用累计 12/14），并非 1.5 全功能 QA**：LG-015/LG-020 的新资源/启动功能仍未验收，分别留 LG-027 与 LG-021/LG-022。原 27 项首版任务及新增 14 项扩展任务（LG-028～041，去中心化与资料/Embedding 两线，均 `todo`）见 BACKLOG.md；人员、预算、日历日期与部署目标未确定。代码仓库已于 2026-10-14 初始化 Git 并推送 `main` 到内部 Gitea。

## 目标

做一个以用户文件为事实源的**个人与小团队 AI 工作助手**：用户通过 Chat 交付资料和提出目标，系统整理、查找资料，并按需执行任务、验证和交付，在用户掌握的文件中保存过程与可复核的成果。

对外介绍：**把资料和目标交给它，它帮你整理、查找并完成工作，过程与成果保存在你掌握的文件中。**

这是目标定位，首版仍用开发任务验证交付闭环；资料接入与检索按 [docs/09](docs/09-source-intake-and-retrieval.md) 分阶段建设，尚未实现，中文转写仍待验证。研究、文档和运维也是后续扩展方向，不作为当前已支持能力。文件由用户掌握，不代表模型推理全部在本地运行。

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

### 2026-10-18：Demo录制修复批次冻结 1.23.0 本地隔离候选（LG-251，未部署）

- 以 `cd755da`（native Files 任务定义/预览/英文/导航修复、LG216/LG243 UI/LG240 route、LG220 `03cacb4`、LG253 native `e63d039`、LG249 hint）为唯一基线；按内容去重只挑 LG-208 cache `1aaf2d1`、native backend `be3214e→89b4ec4→dff18e2`、LG-243 `2a27aee`、LG-249 `9b5ec83`、LG-224 `60589cb`，不重复导入等价补丁或整条分支。
- 契约按 MINOR 升至 **1.23.0**（docs/08 §24）：新只读端点、Run/Task 字段、PDF `extractor`/record types 与 health `team_bot_mention` 属加性扩展；**LG-249 则有意改变既有 Team Task 普通消息路由**（默认 recorded-only，前导配置 mention 才路由），因此不把整批写成纯加性。单用户路由不变；既有公开 `run.connection_pin`、状态/阶段/验收枚举、迁移方向和错误码不变，旧 Task 缺省检查/验收行为保留。
- LG-244 的默认交付工作区与 required 检查是真实行为：failed/error/unconfigured/skipped/缺失 required 阻止复核与 Accept，stale 报告不静默重跑；旧无策略 Task 只读为 `not_configured`/`satisfied=false`，不伪 passed。LG-243 worker 快照只是计划/冻结连接，不是调用证明；reviewer 仅在真实复核后记录，缺失保持 unknown。
- LG-224 以文字层优先取代旧“PDF 总是光栅化 OCR”说明，稀疏阈值 16 可见字符；没有真实 OCR/模型质量验证。LG-249 Team Task 普通消息只记录、不调分类器/responder/model，前导配置 mention 才路由；health 只发布真实 Team 配置，前端无 `@bot` 兜底。
- 验证为开发者局部检查：53 项新增/聚焦后端测试、既有 123 项 Tasks/Google ASR 回归、受影响 cache/store/lexical/verify/api/coordinator/sources 子集、mypy、前端测试/typecheck/build。前端完整套件实际为 **400 通过/1 失败**，失败为 `lg120-roles` 分页，保持 **OPEN/未分类**待 native Files owner 分诊；隔离复跑 5/5 只是线索，不是分类、豁免或通过证明。默认 `pytest tests` 的重复 basename 收集问题仍已知且未改布局；不宣称单命令全绿或独立 QA。
- **LG-251 状态为 PROVISIONAL/未完成，候选仅作临时身份，不是最终验证冻结。** 不推送、不合根 main、不部署、不重启 8123/5173/18123。原 LG-254 采集门两轮失败后已由 root 重划 LG-257/LG-258；在 root 批准新门禁前不进行 LG-252 业务/模型/浏览器录制，也不导入 capture。

### 2026-10-18：Google 原生音频转写候选通过独立 QA 并串行合入本地 main（LG-235→236/237→238，契约 1.22.0；LG-239 PASS_WITH_LIMITATIONS，未部署）

- 用户明确选择 Gemini 原生音频 REST 作为本轮英文 demo 路径，替代 EG2/Reader 远端帧桥；不部署模型容器/Torch/Reader/帧服务，复用既有资料摄取、machine 正文、索引与回执。
- 契约由 LG-235 以加性 MINOR 冻结（§23），并精确合入已在 main 的 LG-229（取消 OpenAI 兼容主机白名单）/LG-230（取消模型与 API 调用上限，保留计数/超时/取消/并发）。LG-236 后端、LG-237 UI 隔离并行，LG-238 串行装配；本候选源码 `CONTRACT_VERSION=1.22.0`。
- 旧块无 `provider` 时 1.20/1.21 行为逐字保留；Google 凭证只经受保护 Settings 的 write-only 字段进入 `FileSecretStore`，产品不读环境 Google key；原生请求只用 `x-goog-api-key` 头、inline base64 音频与固定 prompt，无 SDK/Files API/自动 fallback/自动重试。
- LG-239 独立版本/浏览器 QA 为 **PASS_WITH_LIMITATIONS**：一次真实 UI 上传音频调用 Google 返回 HTTP 200（约 6.082 秒），正文持久化、关键词检索/回链、Chat 回执/Tasks 预览、正式/机器文本分离、关闭后历史、权限及 1440/1024/390 布局通过；仅有限合成音频，H2 字面 thought 前缀及人名误识别保留，旧 Reader 质量 **FAILED** 不追溯改判。LG-238 装配检查使用记录响应与 fake transport，不冒充真实运行时调用。
- 本次串行集成将 1.21 Tasks 与 1.22 Google ASR 候选合入本地 main；公开 8123/5173 仍为 1.20.0，未部署/推送，用户最终验收与后续部署另按授权处理。

### 2026-10-18：产品不限制模型与 API 用量

- 用户明确：产品不应对模型、API 用量有任何限制。取消 OpenAI 兼容主机白名单与执行器／Task／协作的模型调用次数上限，保留计数与用量展示、超时、取消/停止确认和并发容量。实施见 [LG-230](backlog/tasks/LG-230.md)；LG-229 的“加入 Google 主机”随之被更通用的删除白名单覆盖。

### 2026-10-18：模型来源按环境区分

- 只有线上 demo 用 Google API：对话 `gemini-3.8-flash`，向量 `gemini-embedding-2`（Google API 无 EmbeddingGemma 2），均走 Google 的 OpenAI 兼容端点 `https://generativelanguage.googleapis.com/v1beta/openai`。key 只存仓库根 `.env` 的 `genai_api`（已 gitignore），部署时经 Settings 受保护表单保存，不写入文档、日志或提交。
- 本地开发／测试用 DeepSeek 对话与 192.168.8.12 的 `embeddinggemma-2`（`http://192.168.8.12:11434`，llama.cpp router，无 key；首次请求可能冷启动超时）。
- 产品原只允许 `api.deepseek.com`；[LG-229](backlog/tasks/LG-229.md) 将 Google OpenAI 兼容主机加入执行/代理白名单，并让向量端点接受已带 API 路径的 base_url。线上 demo 具体实例待确认。

### 2026-10-18：Tasks 工作区取代 Chat 主页面（仅设计，待实施）

- 用户确认理想工作方式为“选择 Task 目录 → 进入该 Task 工作区看文件 → 在右侧调用 agent”。左导航删除 Chat，Files 更名 Tasks；右侧 Bot Chat 成为唯一对话界面并绑定当前 Task，未选 Task 时为 Global 对话（Tasks 顶部固定 General）。
- Task 在磁盘上就是 `tasks/<id>/` 目录。Tasks 提供 New task：输入标题后经 `POST /tasks` 由后端建目录、TASK.md 与默认工作区，前端不直接 mkdir；普通文件夹仍不构成 Task（docs/05 §3 不变）。
- 输入框删除 `+` 扩展面板（源码已删按钮）。手动选材料作上下文移到 Tasks 工作区的文件／材料行；按路径引用文件输入删除；Global／Task 范围、数量上限与服务端校验不变。
- Chat 头部 Personal／Team 右侧加历史图标。第一期列出 Team 中有消息的对话（General 与各 Task），点击切换 Task；Personal 保持不挂 Task 的个人私聊。Task 内私聊和每 Task 多会话需后端会话／权限改动，列为第二期另行立项。
- 详细设计见 [docs/05 §1～4](docs/05-navigation-and-team.md)、design.md §2/§5；尚未派工实施。

### 2026-10-17：简化 Provider 接入，核实 SDK 能力后再开放

- 用户要求 Connections 简化为 provider 下拉、API 接入信息和测试按钮；使用固定SDK实际支持的 provider，不以增加静态选项冒充接入完成。LG-104 为命名版本，LG-105 只读调查已完成，LG-106 独立前端候选进行中。
- 官方v0.1.22与安装关键源码一致：Gemini API／Vertex Express API Key／Vertex Standard ADC／OpenAI-compatible／LiteRT；DeepSeek是OpenAI-compatible预设。当前产品只有DeepSeek完整执行路径，其他类型在应用层仍有限制。先收拢表单，SDK支持／应用可配置／执行可用／真实服务验证分别呈现。
- 用户后续决定“先不设上限”，取代此前全局模型调用 cap0；LG-107 已由 pi 更新8123为 PID2516844，移除环境变量，生效 limit=None/count=0，保留历史计数、权限、no-executor 与其他服务。不借用开发密钥或后台发起产品请求。[交付证据](probes/provider-setup-20261017/RUNTIME-BUDGET.md)。新增 provider 到保存测试还是同时用于任务尚待回答；后端／契约最终范围待冻结。用户同时询问多个 OpenAI-compatible API：当前可保存多个独立连接，但执行／测试代理仅放行 api.deepseek.com，不能宣称任意厂商 endpoint 已可用。既有测试器进程累计一次网络测试限制仍待独立缺陷修复，本次运行配置调整未修复该问题。

### 2026-10-17：保留 Settings 的完整连接管理并收拢入口

- 用户确认 Settings 的连接管理更完善，授权保留现有完整页面，移除左侧独立 Connections；其他连接引用及旧入口统一定位 Settings 对应稳定ID。此决策取代此前七类资源全部直接侧栏入口的 UI 规则，底层仍为七类 canonical 资源，其余六类维持直接导航。
- LG-103 由 pi 隔离实施／浏览器验证并合入 main85d009d，已更新8123静态资源，保留原完整连接表单／凭据／测试／默认模型。普通成员权限、未知目标反馈及跨ID迟到响应经真实隔离测试核对，无数据迁移／后端变更／服务重启／模型调用／远端推送。

### 2026-10-17：授权合入演示分支中的通用协作与可靠性改动

- 用户确认合并此前列明的八项：Team 按 Task ID 查询、Board 正式成果下载、查询保留原频道、有效候选验收门、产物归属与路径摘要绑定、交付／控制意图区分、失败重试历史与编号、工作区 Git 隔离。
- LG-094 为命名整合版本，LG-095 由 pi 在独立工作树筛选并串行集成，LG-096 由另一 pi 独立真实前后端 Playwright 验收，通过后 pi 合入主线。发现缺陷交原生 Codex 子代理；主代理仅维护管理文档与核对证据。
- 不引入三个游戏角色、固定能力映射、指定 Task／attempt／96 次预算恢复配置或演示数据。通用角色目录与按任务招募另待完整设计，本轮不宣称已实现。
- 保留 root 既有 dirty/index 与 8123／5173／18123 服务数据；主线源码合入后 5173 的 Vite 可能自动刷新，8123／18123 不自动重启。无产品真实模型调用，不推送／发布。

### 2026-10-17：授权发布安装简化版本到 Gitea 与 GitHub

- 用户明确要求发布两个既有平台。LG-093 由 pi 串行完成源码导出／发布文档适配、敏感值扫描、正常非 force 推送与安装包 release 下载交付；GitHub 延续独立公开源码历史，Gitea 保留既有内部历史，仓库可见性不变。
- 发布基线为 LG-092 的 2c68131（业务 backend/frontend 仍为 b6c738d），不将独立 demo 的 61e2269 自动迁入安装版本。root dirty/index 和运行服务保留；公开 README 移除内部证据／LAN／本地路径链接，准确区分已交付与候选能力。无产品模型调用或云资源创建。
- 发布已完成：GitHub main89ac38d／Gitea maina1bbeaf，两个既有 private 仓库保持可见性与不同历史，正常非force推送。双平台release `install-preview-20261017`均有同一742216字节tar包、SHA及清单；全部附件远端下载校验一致，SHA4527b6df…c1d6d。从公开源码真实打包／无Node安装／团队登录／HTTP／停止通过，待版本独立QA。[交付核对](probes/install-publish-20261017/DELIVERY.md)。root main2c68131、dirty/index和运行服务保持，未创建云资源。

### 2026-10-17：先简化安装

- 用户授权优先简化安装。LG-092 由 pi 在独立工作树实现源码单命令安装与包含已构建前端的本地交付包；目标服务器不要求 Node.js，仍需 uv 和联网下载 Python 运行时／依赖。复用既有 CLI，状态与秘密独立于源码保存，重复安装不得覆盖用户数据。
- 本轮为安装小批次，执行者完成隔离真实安装／启动／状态／停止与前端/API 冒烟；待后续版本 QA，不另设大版本门。无产品模型调用、Google Cloud 资源创建或远端发布，不修改 8123／5173／18123 服务与数据。
- LG-092 已完成局部验收：主目录 main 新增四文件提交 2c68131，backend/frontend 保持 b6c738d，已有 dirty 文件保留。源码与免 Node 包实际安装、团队登录、含空格路径和重装保留账户／配置通过；主目录打包也已验证。最终包 31fa1e48…e00eb，除 RELEASE-INFO 外与实际安装测试包逐字节相同，复用对应安装证据。[交付](probes/install-simple-20261017/DELIVERY.md)。Linux x86_64 范围，待后续版本 QA，未推送。

### 2026-10-17：授权pi制作两分钟Demo视频并接入DeepSeek视觉复核

- 用户在确认本地HyperFrames与FFmpeg后，要求由pi配合DeepSeek视觉精确剪辑。新增LG086成片里程碑、LG087制作/能力探针、LG088独立视觉QA；主代理仅PM，pi制作与新独立pi验收，不影响已完成LG063技术闭环。
- 已确认本地HyperFrames0.8.139、FFmpeg7.0.2；现有DeepSeek配置实际图片探针与成片图像审看完成，请求deepseek-v4-flash返回deepseek-flash别名，无供应商切换。保留空回应／OCR误读探针；准确游戏分数／时间及6×字幕／最终页脚有真实图像响应，精确剪点仍以PTS/ffprobe/事件证据为准，不宣称完美OCR。
- 最终v2实际120秒/1080p/30fps/3600帧已通过LG091新独立pi QA PASS，电影SHA76fb2519…fad29，源码33a69a6。LG090以FFmpeg最终阶段清理85–104秒装饰页脚，复跑逐字节同摘要；原HyperFrames页／素材／EDL／字幕未变。辅助图像累计10/12（含失败与误读），pi创作上下文及费用另计未知；v1/P3/D2和全部原始素材／失败保留。[最终交付](probes/video-20261017/README.md)。
- 默认1920x1080、30fps、严格120秒英文字幕版，依既有runsheet快进准备与等待、保留功能介绍及双账户真实闭环；无新音乐/合成旁白或远端发布。原始录屏/截图与sourceSHA/timecode/EDL、字幕、可复现项目、MP4及QA报告交付；用户可中途纠正默认值。
- 新辅助编辑视觉请求共用独立持久账本，最多12（含失败，制作<=8并预留4给独立QA；pi创作及读图上下文另行审计、费用未知，不把此上限冒充全部视频模型调用），与产品89/96严格分开；不清零产品预算、不触发新Task/Run/Retry/Accept，不动8123/5173/18123及数据。授权必要本地剪辑/渲染与图像复核，未授权发布或自动反馈给第三方。


### 2026-10-17：双账户小游戏本地交付

- 最终18123正常CLI无执行器服务已运行，交付真实浏览器冒烟通过；两账户查看原Task/反馈、已验收Board、canonical摘要下载、桌面游戏和390布局核实，1Task/3Runs、89/96不变。游戏原样副本、受保护账号交接路径、启动/停止命令及证据见 [DELIVERY](probes/demo-team-game-20261017/DELIVERY.md)。
- 源码提交61e2269，固定分支delivery/lg068-local-20261017、持久工作树../lightgravity-bot-worktrees/lg068-local-delivery-20261017；产品树与独立QA一致。主目录main保持b6c738d，因为5173的Vite正监听ROOT/frontend，直接集成会热更新受保护旧页面；后端也未混合迁入。独立delivery/frontend-dist不覆盖8123现有资源。此为本地隔离版本交付，不宣称主目录已合并或远端更新。
- 当前入口回放真实已完成结果，新生成关闭；剩余7次不作为新Task授权或新游戏成功承诺。原始WebM/截图/trace当时尚未剪辑，现已作为两分钟成片来源保留，见上方最终视频交付。技术demo验收已经完成，用户产品最终确认与本次技术交付分开。PM并行更新管理文档，交付执行者未覆盖这些dirty文件或index。


### 2026-10-17：同候选双账户闭环独立技术QA通过

- 新独立pi结论PASS_LINKED，固定61e2269；沿用同产品树R4真实执行/独立模型复核/停止事实，实际同候选下载与摘要、桌面及390各完整30秒、B普通Team反馈、A看到反馈后实际Board Accept全部闭合。03:46:48.714Z accepted，Taskdone/completed、Runcompleted、cleanupdone，需求3/交付1/计划/候选绑定保持；1Task、3Runs，无第4次。见 [最终独立QA](probes/demo-team-game-20261017/CONTINUATION-QA.md)。
- 89/96为真实全生命周期持久调用数，含旧40+24失败及本次24worker+1reviewer；试玩/反馈/验收不增加调用。费用未知。R4失败、临时探针失败和验收后字段核对错误均保留，更正后的只读核对通过，不描述为一次全绿。
- LG067完成，LG068pi负责最后本地交付。若主目录源码会触发既有5173热更新，保留固定隔离源码提供稳定18123，明确主目录未合并，优先守住旧服务；用户没有要求强制合main。当前服务禁用执行器用于真实结果回放，不用剩余7次承诺新任务。


### 2026-10-17：第三次运行通过模型门，接续同候选验收

- 同Task attempt3真实运行完成开发、验证、独立模型复核与停止确认；持久账本89/96，旧64失败调用保留。R4完整QA仍FAIL：下载检查要求唯一URI，但当前候选含两份同SHA游戏证据；此前未试玩、反馈或Accept。见 [R4报告](probes/demo-team-game-20261017/RECOVERY96-FINAL-QA.md)。
- LG085仅调整测试侧等价内容判据：先核对当前候选授权/版本/作用域，再要求唯一内容SHA；保留所有等价引用，不容许不同SHA或历史回退。pi冻结61e2269，产品树与真实运行baca674一致；新独立pi须先判断契约正确性，再实际完成下载、桌面/390完整试玩、B反馈及A界面验收，不增加模型调用。旧QA的重复发布观察及失败原样保留。
- 新独立QA按原始持久预留账本核清：89 = 首次40 + 第二次24 + 第三次25，第三次包括24次worker与1次reviewer。R4报告中“89再加1=90”为重复计数，原报告保留，后续以核清记录为准。
- 同持久数据以无执行器18123重启，原正向复核和停止事实保持，候选未改；此时不是已完成交付。067通过后才执行068根目录串行集成与本地服务交付，已有8123/5173及其静态包保持。


### 96预算运行前产物路径审计与修复

- 新授权工具及验收UI已在bd5aad08隔离整合，95Node/40授权/218前端通过，准备模型调用0。需求3、输入只保留原样design/index，原目标/验收未变，旧3文档归档保留。
- 只读源码审计发现既有产物namespace缺陷：隔离worktree新增文件的相对引用会在旧Task根解析；未变输入没有当前Run canonical证据，下载测试又把Task相对path误作全局path且只核对摘要长度。此为运行前发现，尚无attempt3或新增产品调用。
- LG083修复实际Run交付文件证据归属，LG084按已有canonical证据与摘要下载，不使用全局同名路径降级。两名原生Codex子代理隔离实施；pi整合后再启动新的独立QA。已结束仍在等待候选的旧QA准备pi进程，仅结束其只读等待，无SDK/Task/账本操作。

### 用户批准追加32次产品执行调用

- 用户对“新增最多32次、累计96次、保留全部失败并继续同Task”的提问明确回复“批准”。本次授权覆盖新增最多32次产品SDK调用；既有64次账本、两次失败Run和原文件证据保留，不清零、不换Task、不自动再追加。授权文件 [RECOVERY-96-AUTHORIZATION](probes/demo-team-game-20261017/RECOVERY-96-AUTHORIZATION.json)，旧64次授权作为历史保留。
- pi基于e08678f准备精确受限的第三次恢复工具与新独立QA清单，处理旧历史文档标识引发的重复修改：沿用现有游戏，只补必要交付/验证，旧记录保持历史，不以润色为目标；不降低验收、reviewer、真实停止与当前候选绑定门。准备不产生产品模型调用，新的独立pi点击同Task Retry。
- 本地预览18123可在确认无worker后为恢复有序停启；现有8123/5173不动。QA通过后完成LG-068本地交付与根目录串行集成，不远端推送。

### 2026-10-17：恢复达到累计64上限，保留失败并提供预览

- 精确候选1f5e704独立真实恢复已在同一Task创建attempt2，B查询及A关闭后3.3秒内的归属进展通过；累计40→64后再次失败，开发节点通过，验证3次调用后被本地代理429拒绝，独立reviewer尚未开始、无候选验收。
- 新增24次中21次用于开发成员纠正文档历史标识/验证措辞与读回，3次用于验证；游戏HTML与首次生成字节一致。未发现新的确定性程序缺陷，不以可玩文件当作完整闭环。见 [实际诊断](probes/demo-team-game-20261017/RECOVERY-RUNTIME-DIAGNOSIS.md)。
- 64硬上限保持，不自动追加。LG-079已由pi交付冻结候选的独立认证本地预览 http://192.168.8.50:18123、真实游戏下载和双账户浏览器证据（桌面/390各完整30秒通过），不启用执行器；不合入根main，不修改现有8123/5173，不把LG-067/068或里程碑标完成。
- 已向用户请求是否新增最多32次产品执行调用（累计96）或先交当前预览；此为待决提议，当前未授权，不启动后续模型执行。原有64次与所有失败永久保留，开发用量/金额未知。

### 2026-10-17：真实 Demo 失败后的受控接续（LG-073～076）

- 首次独立真实彩排前5项通过，断连测试因只等Run状态变化在6分钟超时；实际工作继续。完整40次请求上限已触发，原Run因adapter real-model call cap reached失败，产物/会话/账本保留，未清零或盲重跑。
- 真实native轨迹确认产品工作区边界缺陷：嵌套空任务目录误借宿主Git，带入AGENTS/设计/项目文档，额外探索后还发生多次可选润色；不能把全部消耗都归因于一个缺陷。LG-075修复根目录授权；LG-073修复断连判据、显式接续与Play again测试驱动。
- 用户已授权补齐功能并跑通本地demo。依据已确认根因、已生成可复用游戏及待完成验证，PM批准一次有限恢复准备LG-076：保留同一Task，旧Run与40次失败永久计入；修复整合、确认旧worker停止、原样保全输入文件后，由受支持路径建立恢复Run。明确累计硬上限64（已用40+后续最多24），同dataRoot/持久账本不清零，不再自动追加。普通新彩排默认仍40；恢复上限仅显式有限授权配置，不伪装首次通过。
- pi准备/集成，新的独立pi执行真实恢复与浏览器验收；不得强制完成/绕过reviewer/修改生成游戏冒充SDK交付。需求版本与Run变化如实记录，当前尚未完成。

### 2026-10-17：授权实施双账户小游戏 Demo 本地闭环

- 用户要求创建任务、在本地跑通 demo 并补齐缺失功能。建立命名里程碑 LG-063 与子任务 LG-064～068，按两分钟 runsheet 验收 A 发起、B 查询/试玩与反馈、A 验收同一真实 Task。
- Codex 主代理维护计划与证据；pi 调查、新功能、串行集成及独立 Playwright QA；已有缺陷交 Codex 子代理修复。先调查冻结接口与 owner，再并行独立工作包，整合后集中版本 QA。
- 隔离 demo 数据、端口与模型调用账本，保留现有 8123 服务。允许任务所需真实 SDK/DeepSeek 调用，采用有限预算且覆盖失败、验证与复核；具体上限在派工记录中登记后执行。凭证沿用 .env 受控映射，不打印/落文档；不自动远端推送或发布。

### 2026-10-17：双账户 Team Chat 小游戏演练脚本

- 视频要求补充：成片严格两分钟，runsheet v0.2 增加功能与界面速览；部署、模型、角色与建号准备快进压缩至 5 秒，主要篇幅保留 A 发起、B 查询与试玩、A 验收。记录真实执行耗时，快进/省略明确标注，不把成片时长当作生成耗时。
- 用户要求先写 demo runsheet；已落盘 [双账户小游戏 Demo Runsheet](docs/12-team-game-demo-runsheet.md)。主线为管理员创建两个普通成员账户，A 在 Team Chat 发起 PENGUIN POP 开发，B 独立登录查询同一 Task、查看产物并试玩，A 返回查看共享反馈并验收。
- agency-agents 默认角色库作为演练准备要求；实际导入、指令绑定与可用工具仍待实施/核实。沿用 Olav OS 小游戏的设计、交接与验收经验，不将参考项目的运行结果视为本项目通过。
- 本次只写脚本和文档入口，不创建任务或账号、不导入角色、不启动执行器/模型、不修改现有服务。双账户自然语言状态查询、角色实际加载、游戏交付及验收组合路径均待彩排；场前须在隔离 demo 环境配置连接、独立 reviewer 和明确预算。

### 2026-10-17：识别非标准 API 配置并继续修复闭环

- 用户说明 API 已在 .env 中且命名不同，要求执行直到修复完成。已识别非标准 deepseek-api 标签；原文件保持不变，启动 pi 时仅在进程内映射 DEEPSEEK_API_KEY，连接验证 READY 成功。此前只扫描标准变量名导致误报缺凭证，此阻塞已解除。
- pi 新开发／集成执行者在独立 worktree 串行整合 LG-052／053 候选，完成 LG-054 窄范围个人会话与 Playwright 测试接入；之后由独立 pi 执行者进行版本 QA。发现缺陷仍交 Codex 子代理修复，再由 pi 复验。
- 执行假设已向用户说明：Personal 为个人私聊，Team 为现有共享对话。个人消息按服务端身份隔离；现有资料与 Task 仍共享，Personal 不自动创建共享 Task 或上传个人内容到共享资料；若任务交付需引导切换 Team。此为本轮窄范围新增，不承诺私有资料、私有 Task 或多租户。
- 对话草稿、选材、游标与在途响应须按身份／频道隔离；Task 目录打开真实共享 Task 时进入 Team。单用户模式 Team 可显示未启用，不假装多人已经开启。
- 尚未集成、验收或发布；不自动推送 GitHub/Gitea。测试服务使用独立数据与端口，产品真实生成 0，开发 pi 成本另计且未知。

### 2026-10-16：开始界面可用性与交互修复（LG-051）

- 用户授权“现在开始修”。建立命名里程碑 [LG-051](backlog/tasks/LG-051.md)；[LG-052](backlog/tasks/LG-052.md) 与 [LG-053](backlog/tasks/LG-053.md) 已由 CLI claim，分别交 Codex 子代理修复运行兼容性与界面；使用独立 worktree，不覆盖主目录现有修改。
- 已确认运行中 8123 为 1.0.0 骨架，仅健康与版本两个路由；Vite 代理正确。修复需区分源码候选、实际运行服务与版本验收，不能以构建或局部测试冒充用户页面已恢复。
- 导航与布局按用户七项反馈同步 agent.md、design.md 和 docs/05；顶部真实资料搜索、Files 真实 Task 入口、输入框简化，移除第二栏与 Scope/Run 模拟选择。
- [LG-054](backlog/tasks/LG-054.md) 待用户明确个人／团队含义；如新增私聊，须先处理会话和身份范围，按新开发交 pi。
- pi 实测缺少 DeepSeek API key；[LG-055](backlog/tasks/LG-055.md) 串行集成、Playwright 接入与独立 QA 当前受阻，已请求用户在本机配置，不切换后端代替。修复者只交候选与必要局部非浏览器证据，尚未版本验收，不自动推送或发布。
- 实际进展：旧 8123 已从 main 现有后端安全恢复到契约 1.13.0，48 路由，直连及 5173 代理读取接口 200，生成 0。兼容性修复候选 2f6f567（21 前端局部＋15 权限检查）；界面候选 502f1f2（137 非浏览器测试、类型和构建通过）。两候选分别位于 LG-052／053 独立分支，尚未 pi 合并、联合复验或浏览器验收；当前界面仍为 main 布局。模型执行保持未启用。

### 2026-10-16：固定开发、修复与验收分工（取代此前自由选择后端）

- 用户指定：Codex 主代理负责项目管理，pi 负责开发、QA 和浏览器测试，Codex 原生子代理负责修复；已同步 [agent.md](agent.md) §1 与 §8。
- 开发与串行集成交给 pi；已有缺陷定位与修复交给 Codex 子代理，可做必要的非浏览器局部回归。独立 QA、Playwright 浏览器验收和修复后复验由 pi 执行，验收执行者独立于开发者和修复者。
- 对应后端不可用时记录受影响工作包阻塞，不再自动跨职责切换；其他已授权且不受影响的工作继续。保留 worktree 隔离、文件归属、凭证保护与用户最终验收要求。本次只更新规则，不启动修复或测试。

### 2026-10-16：开发执行后端按任务选择

- 用户明确允许根据任务情况使用 Codex 原生子代理（subagent）或 pi；已同步修订 [agent.md](agent.md) §1 与 §8，替代此前仅限 pi 的开发派工要求。
- 主代理保留项目管理职责，按任务、成本、上下文与工具可用性派工；pi 缺少凭证时可使用可用的 Codex 原生子代理继续已授权工作。pi 路径仍沿用已配置的 DeepSeek，原生子代理不要求另配 DeepSeek 凭证。
- 文件归属、并行 worktree 隔离、独立版本 QA 与密钥保护要求保留；此变更不改变产品运行时 Antigravity SDK 后端或验收语义。

### 2026-10-16：页面不可用与界面调整反馈（仅记录，待实施）

本次用户明确要求“先记录下这些问题，不要执行代码”。以下为用户反馈及调整要求；本轮只更新文档，不调查代码、不启动服务、不调用模型、不运行测试、不派工实施。报错尚未复现，原因与影响范围待后续核实，不以历史 QA 结果推断当前页面可用。

1. **多个页面基本不可用。** 用户看到的报错包括 `Scope not found`、`Not Found (not_found)`、`Cannot list files`、`Could not load Team`、`Could not load Models & Providers` 等。记录为页面可用性问题，后续需定位原因并验证相关页面能正常加载；当前不推断是配置、接口或部署问题。
2. **删除左边栏旁的第二个小栏。** 当前“左边栏 → 小栏 → 主视窗 → 对话框”的多栏样式不符合用户预期；保留左边栏，去掉第二个小栏，简化布局。
3. **拆分 Resources 入口。** 将 Connections、Session Profiles、Hooks、MCP、Tools、Triggers、Skills 全部直接放入左边栏，不再需要通过 Resources 下的第二个小栏进入。
4. **Search 放在顶部。** 搜索入口移至页面顶部。
5. **简化对话框。** 当前对话框过于复杂，参考 ChatGPT 的对话框样式调整，具体视觉与交互待后续实施时细化。
6. **补充个人／团队切换标签。** 对话框上方应有“个人”和“团队”切换标签；用户反馈当前缺失。
7. **移除顶部 Scope 和 Run 选择。** 用户需要选择任务时，从 Files 中选择 `task` 目录并进入对应任务对话，无需在顶部另选 Scope 或 Run。此项记录为入口调整，不表示删除底层 Task／Run 数据与执行语义。

上述要求是后续界面调整的依据，涉及第二小栏、Resources 分类入口、顶部任务选择与个人／团队切换的内容，优先于旧版布局描述。现有 [开发规则](agent.md) §7、[前端设计](design.md) §2、[导航设计](docs/05-navigation-and-team.md) 及 [README](README.md) 中的旧布局保留为当前设计记录；后续获准实施时须同步修订，不能据旧布局否定本次要求。本轮未拆分开发任务、未修改任务状态，全部问题保持待处理。
### 2026-10-16：共享团队聊天与简单认证快速原型（LG-050，实施中）

- 用户提出参考 Olav OS 团队聊天，将单人 bot 扩展为多人协作。最小实施假设为一个共享工作区、独立本地账号、共享群聊；私聊、私有资料、多租户与组织治理暂缓。此条为本次新增范围，不把历史单用户边界当作阻止实施的授权门。
- 团队模式显式开启，默认保留已有单用户使用方式；消息作者从服务端登录身份取得，人际消息只持久化，`@bot` 显式触发已有问答/任务路由。管理员负责账号、模型和凭证配置。
- 参考调查由 pi 只读完成：Olav OS `dev_docs/01-ce-design.md:68` 的 mention 策略属于 IM 渠道；网页 `team-chat.tsx`/`chat-file-store.ts` 有目录共享会话与作者，但每条用户消息仍排 bot turn。仅借鉴必要机制，避免把其网页聊天当作已实现 mention 门控。
- 命名里程碑 **LG-050 共享团队聊天与简单认证 MVP**：后端与前端使用独立 worktree、明确接口并行实施；集成候选完成后交独立 pi 集中 QA。验收覆盖双用户共享、身份可信、匿名拒绝、管理员门禁、普通消息零模型触发、显式触发幂等、并发同步与退出失效。任务与证据见 [LG-050](backlog/tasks/LG-050.md)。
- 当前仅调查与实施安排已完成，产品能力尚未交付；未发布、未部署，用户已有 `PROGRESS.md` 改动保留。
- **进展（2026-10-16，串行集成）**：后端 `feat/team-backend-20261016` 与前端 `feat/team-frontend-20261016` 已 `--no-ff` 合并到候选分支 `feat/team-integration-20261016`；公开契约同步为 `1.13.0`（`docs/08` §13/§14）。局部集成检查（team/contracts 后端测试、前端 typecheck/131 tests/build、真实 team 模式 HTTP 冒烟）通过；**独立集中 QA 与真实浏览器验收尚未执行**，未合回 `main`、未宣称 QA 通过。证据见 [probes/team-chat-20261016](probes/team-chat-20261016/README.md)。

### 2026-10-16：LG-049/ N-R3-LIFECYCLE 实际 PASS_WITH_LIMITATIONS 复核闭环 → 置 LG-049 与 LG-047 `done`；PM/docs 集成（root PM）

- **依据**：独立 LG-049 在**冻结既有产品**上真实跑通**一条完整 SDK 交付生命周期**，补齐 I-R2 的全部 FAIL 缺口：原生 API 上传 alpha（`content_hash=d34f0ca58b8d…`，receipt `native UTF-8 text extracted (model-free)`，**无 seeded derivative**）→ EXACT 前失败目标 `delivery/create_task` → 程序规则计划 `deliver`+`verify` → 真实 SDK worker **6 事实全对** → **`verify` 节点 passed（R2 曾 429）** → 机器门通过 → **真实独立 ModelReviewer `outcome=passed`（`reviewer_kind=model`，`model_calls=1`）** → **worker `cleanup=done`+`member.released` 与 reviewer `reviewer_cleanup.confirmed=true` 于 accept 前 CONFIRMED** → API accept（乐观 revision）→ `done` → artifact refs 真实 body + history Sources 匹配。**8/16 前向**（deliver 2 + verify 5 + reviewer 1）。
- **PM 复核**：root PM 以 `events.jsonl`/`RUN.md`/`TASK.md`/`evidence/*.json` 原始事实核对（非仅报告转述）；详见 [K-RELEASE-CLOSE REPORT](probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md)。
- **集成（仅 probes/docs）**：`--no-ff` 合入 `qa/proto-material-lifecycle-r3-20261016@dc1a1b2` → 合并提交 **`76f10c7`**（父 `096d796`+`dc1a1b2`）；唯一非 probe 差异 `backlog/tasks/LG-049.md` 冲突**保留 `main` 的验证记录**，无代码改动；产品树与 `0188ca2` **逐字节一致**。
- **状态**：**LG-049 `done`**、**LG-047 `done`**（历史 R1/R2 FAIL 与成本保留不改）；**LG-048 保持 `done`**、**LG-041 保持 `todo`/阻塞**。CLI 实测 `49 tasks / 0 diagnostics`、`48 done / 1 todo / 0 in-progress`、`ready=[]`。
- **保留限制（不洗白）**：累积成本 unknown **非 0**（R1 已知 1+缺口 / R2 actual 8 / R3 actual 8 分列）；浏览器 UI 证据为复用（前端未构建，前端树一致）；未重跑全量测试（代码未改）。**用户最终验收仍待定、未 push/deploy、8123 未触。**

### 2026-10-16：PM 依据 LG-048 诊断选定下一任务 → root 显式授权 R3 新 campaign `N-R3-LIFECYCLE`（hard cap 16）；创建 LG-049

- **PM 显式选定**：依据 [LG-048 诊断](probes/prototype-selected-material-20261016/M-DELIVERY-DIAGNOSIS/REPORT.md) 与 I-R2 FAIL/INCOMPLETE（`a9ba494`）、L routing PASS（`11b5848`），PM **明确选定**下一任务为**完整生命周期验证**（**非**第三次盲修/盲重试）。经 CLI `tasks new` 创建 **LG-049《验证选定资料交付完整生命周期》**（P0，`parent: LG-047`，`depends_on: [LG-048, LG-046]`），以 `tasks claim --as agent:pi-proto-lifecycle-qa` 领取，执行者**独立于全部产品实施者**。
- **PM 决策（保留护栏，不删除/不弱化、不新增 planner/infra）**：**保留**既有 `deliver` + `verify` SDK worker 节点、**真实独立 ModelReviewer**（`default_reviewer_connection_ref`）与程序机器门（LG-009）/stopguard。
- **docs/10 §7 与 docs/11 勘误（最小、文档-only）**：“单 worker”措辞对**普通 Chat 交付**不准确：`default_delivery=True` 派生验收条件 ⇒ `RulePlanner` 追加 `verify`。勘误为单一执行槽内**顺序**运行 `deliver`+`verify`、随后**独立 ModelReviewer**，三者均预算化并保留。**属文档勘误，非行为变更**；产品代码**零改动**。
- **root PM 显式授权 R3 新 campaign `N-R3-LIFECYCLE`**：
  - **硬上限 16 次**新增产品前向请求总计（含全部 worker/verify/reviewer/失败输出重试/连接测试）；**仅一个** fresh delivery Task；**无自动整轮重试**；模型/代理重试在可配置处为 **0**；**串行 90s/请求**；**生命周期轮询 ≤300s**。
  - **单次** initialize：**自有新 dataRoot** + manifest + **durable product generation ledger**（**绝不用 R2 根 / 不 reset counter**）。既有 manifest 缺失/损坏或账本损坏 ⇒ **deny**；**转发前**持久预留 cap16、跨重启不归零、**不自动扩展**。
  - R1 已知 1 次 + 账目缺口 与 R2 actual **8** 次成本**分别保留**；**全累积成本 unknown、非 0**。
  - 复用 I 的真实 UI proof（4 facts/Sources/history/widths）与 L 的 routing proof（**同一产品哈希组成**）；**无需** chat 调用/重复连接测试/browser/OCR/embeddings。
  - 每个请求 role/node/time 与 SDK 事件及持久账本对账（**不 dump 密钥**）；失败即停车保留证据，cap 不扩展；**不触 8123**、不 push/deploy。
- **序列 prep（`main`，`--no-ff`、probes-only、无冲突、产品树不变、保留全部历史）**：合入 I `qa/proto-material-r2-20261016@a9ba494` → 合并提交 **`256cd78`**；合入 L `qa/proto-material-route-r2-20261016@11b5848` → 合并提交 **`d8d8b4e`**。`main:backend` 树 `8b4256a4…` 与 `3ae4ac0` 一致。
- **状态**：**LG-049 `in-progress`（`assignee: agent:pi-proto-lifecycle-qa`）**，**标 done 留待 root closure 复核报告**；**LG-047 保持 `in-progress`，无 PASS**；LG-041 保持 `todo`。**技术性 QA 用户最终验收仍待定。**

### 2026-10-16：LG-047 R2 FAIL/INCOMPLETE → 暂停盲重试，拆分 LG-048 技术诊断（root 授权）

- **R2 结论**：活动独立 QA worktree `proto-material-qa-r2-20261016`（`qa/proto-material-r2-20261016` @ `a9ba494`，[REPORT-I-R2](probes/prototype-selected-material-20261016/I-R2-QA/REPORT-I-R2-20261016.md)）判 **FAIL — INCOMPLETE**。R2 新增产品请求硬上限 **8/8 已耗尽**（持久账本 `generation.count.json={"count":8}`，remaining 0，不可重跑）。真实 SDK worker 已写出含**全部 6 条真实事实且正确**的 deliverable（`raw/sdk-attempt2/`），但第二个（`verify`）SDK 节点撞 **429** 后整 Task `failed`，独立 **ModelReviewer / stop-gate / QA user accept** **从未到达（UNVERIFIED）**。**LG-047 仍 `in-progress`、无 PASS/done；不再接受任何 R2 请求；不改动 I 活动 worktree/campaign/ledger。**
- **决策（暂停重试循环 + 拆分 048）**：在实施/新 campaign 之前**暂停盲目返修/重试**，先拆出 **LG-048 技术诊断**（P0，`depends_on: [LG-046]`，**非 047** 以避免循环依赖），owner `agent:pi-delivery-diagnosis`，**零模型、只读**，产出可操作诊断报告供 PM 选择下一任务。**不新增 LG-049 直到 PM 依据诊断选定下一任务。**
- **诊断关键结论（[M-DELIVERY-DIAGNOSIS REPORT](probes/prototype-selected-material-20261016/M-DELIVERY-DIAGNOSIS/REPORT.md)）**：
  - **(a)** R2 的 429 是**进程全局持久 8 次硬上限**（`LIGHTGRAVITY_MAX_GENERATION_CALLS=8` + 持久账本 `GenerationCounter`/`PersistentGenerationLedger`，转发前 `reserve()`），**非** per-node/per-session/per-request 配额；raw `generation.jsonl` count 4–8 同 pid 于 ~10s 内推满全局。
  - **(b)** 默认确定性通用文件交付规则计划是 **`deliver` + `verify` 两个 SDK worker 节点**（非单 worker）：`RulePlanner` 仅在 `declared` 非空时追加 `verify`，而 `default_delivery=True` 路径恒派生 `acceptance` ⇒ 普通 Chat 交付必走双节点；与 docs/10 §7“单 worker 原型默认规则计划”措辞**存在偏差**。`verify`（同 worker 连接、机器门前置）**≠ 独立 ModelReviewer**（`verifying` 阶段独立 role/connection 的一次 reviewer turn）。**不假定移除/降级 verify 已授权**——那会削弱 guard，须 PM/契约决策。
  - **(c)** 首个 SDK `1006` = **QA harness 提前 `killpg(SIGTERM)`**（driver poll 误判终态 → teardown mid-turn），**非产品复现**。
  - **(d)** reviewer/stop-gate/accept **未验证**；安全有界后续预算**提案**：全局硬上限 ≥15（deliver≤5 + verify≤5 + reviewer≤2 + 失败余量≤3），若先收敛 verify→程序机器检查则 ≈10；下一 campaign 账本须**分列** deliver/verify/reviewer/retry 前向数。**均为提案、当前未授权任何请求**；先做零模型确认（离线测试即可钉死 (a)(b) 核心断言）。
- 未宣告 R3 通过、未宣告累积成本已知（成本 unknown，非 0）；`LG-041` 保持 `todo` 不变。

### 2026-10-16：LG-047 R1 FAIL → F+G 并行返修 → H 串行集成候选（R2 预算重规划）

- **R1 结论**：独立 QA R1 冻结 `57809d4`（[E-QA REPORT](probes/prototype-selected-material-20261016/E-QA/REPORT.md)）判 **FAIL**，四项缺陷：原生文本上传无正文、普通文件交付规则计划校验失败、选材回答/来源未入历史、零调用负例 N2/N5 错误码偏离冻结 docs/11。该报告与 `seed_machine.py` 辅助正文工具**作为 AUX 保留**，**不得**当作真实上传主流程证明。
- **返修与集成**：F（[F-INTAKE-FIX-R1](probes/prototype-selected-material-20261016/F-INTAKE-FIX-R1/REPORT.md)，`fix/proto-material-intake-r1-20261016` @`1821394`，代码 `09edad2`，owner `sources/**`）修复原生 UTF-8 模型免调用文本接入 + 冻结来源错误顺序；G（[G-DIALOGUE-FIX-R1](probes/prototype-selected-material-20261016/G-DIALOGUE-FIX-R1/REPORT.md)，`fix/proto-material-dialogue-r1-20261016` @`8641010`，owner `coordinator/**`）修复助手历史持久化 + 无选材普通 Chat 的确定性最小交付计划。两线**文件归属互不重叠**，由 H 在 `main` 串行 `--no-ff` 集成（[H-R1-INTEGRATION REPORT](probes/prototype-selected-material-20261016/H-R1-INTEGRATION/REPORT.md)）。
- **集成实际检查**：后端 `mypy` 139 files clean、**`pytest -q` 930 passed / 2 skipped**（EXIT 0，F+G 联合一次全量）；前端未改动（仍绑定 B `552d839`）故未重跑 `tsc`/build；本地零模型 API 冒烟确认 F 原生文本自动泵与 G 历史/计划均接入**实际工厂默认**（fake-models，本地-only，**非 SDK 证据**）。全部**无真实产品模型/网络调用**。
- **契约（docs/10 措辞校正）**：旧“省略字段 ⇒ 逐字节不变”限定为**可选请求省略与既有响应 wire/模型上下文兼容**；**不**包含两项已记录 R1 bug 修复（助手历史持久化使旧历史行数不同；无选材普通文件交付默认规则计划修好），不宣称历史行数逐字节一致。docs/11 记录 R1 事实：原生文本成功无需 OCR、**PDF/图像仍走显式 OCR**、回答历史已持久化、确定性文件计划、`Sources` **非已验证引用**。
- **验收与预算**：LG-047 **仍进行中、未 PASS/done**；保留 `57809d4` QA 候选冻结与全部 raw FAIL/种子辅助。**PM 重规划 R2**：在**新冻结候选**上新建独立 QA-R2 持久工作树/分支，独立 pi 执行；**新增产品请求硬上限 8 次**（含失败/worker/reviewer，retry 0、转发前硬限额、账本跨重启不归零、campaign 不重置）；R1 已知 1 次真实请求与失败样本**单列保留**，**不宣称原 12 次 campaign 全程已核实**。本集成产品推理 0。**041 保持 `todo` 不变**，LG-040 既有结论及所有先前边界/超范围不变。

### 2026-10-16：选定资料快速原型规划——契约 MINOR 1.12.0 预留 + 三并行工作包（LG-042～047）

- **PM 决定**：规划并冻结“手动选定已摄取资料 → Chat 回答 / 单 worker 交付”快速原型。新建任务 LG-042～047（CLI `backlog`）：042 冻结契约（owner `pi-proto-prepare`）→ 043 后端（A，与 044 并行，仅依赖 042）→ 044 前端（B）+ 045 Demo（C）并行 → 046 串行整合 → 047 **命名里程碑独立版本 QA**。**041 保持 `todo` 不变**。
- **契约**：单一 owner 冻结 [docs/10](docs/10-selected-material-prototype.md) + docs/08 §6.6.1，加性 MINOR **`1.12.0` 预留**（仅登记，头部 `contract_version` 值由 A 实现时同步）。消息加性可选 `selected_sources`（≤3 来源、`{source_id, source_version?, content_hash?}`）；结果加性可选 `resolved_source_bindings`/`context_truncated`/`provided_context_note`；总 12000 Unicode 字符有界、显式截断 metadata、正式优先机器回退、派发前 stale/revoked/cross-Task 拒绝、不可信数据隔离、不跨 Task；**不影响 legacy 省略字段**。
- **工作包与 owner**：A `dev/proto-material-backend-20261016`（`backend/**`+Python `tests/**`，唯一后端 writer）、B `dev/proto-material-frontend-20261016`（`frontend/**`）、C `dev/proto-material-demo-20261016`（`examples/selected-material-prototype/**`+`docs/11`）；三 worktree 均建于冻结基线 `acd7005` 之后（本 prep commit）；预派工 **不启动 worker**。派工说明见 [DISPATCH](probes/prototype-selected-material-20261016/DISPATCH.md)。
- **预算**：prep/A/B/C/整合产品推理 0；**LG-047 唯一真实 DeepSeek 预算 12 次**（含 reviewer/retry，retry 0、串行、单请求 ≤90s、持久账本、转发前硬上限），**不经 PM 重规划不自动增长**；不足即诚实 partial 并保持 gate 开放。本 prep 真实调用 0。
- **边界**：无 native 子代理、无产品模型/网络调用、无 push/deploy/破坏性清理/8123；保留所有既有 QA/raw/worktree/默认 OFF 特性；个体 worker 不写任务文件。

### 2026-10-16：选定资料快速原型 LG-043～046 实施完成 + 串行整合候选（契约 finalsync 1.12.0；LG-047 待 QA）

- **PM/集成决定**：LG-043（A 后端，含 run/message 触发绑定修正 R1 = `6515e5c`，集成验证回执提交 `9ac6597`）、LG-044（B 前端 `552d839`）、LG-045（C 示例/指南，初版 `6facb0b`、事实校正 `e36df29`）三线均**实现完成**；LG-046 由 `pi-proto-integrate` 在 `main` **串行 `--no-ff` 整合** A→B→C，整合候选见 [D-INTEGRATION REPORT](probes/prototype-selected-material-20261016/D-INTEGRATION/REPORT.md)。**LG-047 命名里程碑独立版本 QA 尚未开始**。
- **A 绑定修正回执（诚实补齐）**：A 原报告将绑定修正标为 PARTIAL（无完成回执）；集成 owner 在**已提交的** `6515e5c` 上实跑并取得真实 EXIT 0 回执（`pytest tests/sources/test_lg043_selected_material.py` **42 passed**；`mypy` **139 files clean**；相关子集 **550 passed / 1 skipped**）。
- **整合实际检查（候选 commit 见 REPORT）**：后端 `mypy` 139 files clean、`pytest tests/` **908 passed / 2 skipped**（EXIT 0）；前端 `tsc`/`vite build` EXIT 0，且集成后前端树与 B `552d839` **逐字节一致**；C fixture checker EXIT 0。全部**无真实产品模型/网络调用**。
- **契约**：docs/08 头部与 §6.6.1、docs/10 已由 A finalsync 至 **`1.12.0`**（去 reserved）；docs/11 去 reserved。**新增加性可选 Task/Run 实体字段 `selected_trigger={message_id,snapshot}`**（实体序列化可达、非秘密），已在 docs/08 §6.6.1/§13 与 docs/10 §6 登记，**不按“无实体字段变化”口径**；不新增端点/错误码/枚举/迁移方向，旧客户端省略字段行为不变，前端 `selected_sources` wire 无变化。SDK `0.1.22` 不变。
- **状态与下一步**：LG-043/044/045/046 置 `done`/in-progress 按实际证据；**LG-047 仍 `todo`（命名里程碑 QA）**，真实 SDK/DeepSeek 端到端 + 浏览器 390/1024/1440 + stale/revoked/cross-Task/oversize 真实错误验收归其独立预算（12 次，未开始）。本整合产品推理 0、成本 unknown 非 0。**041 保持 `todo` 不变**，LG-040 既有结论不变。

### 2026-10-16：LG-040 RELEASE-CLOSE 收口——依独立治理 QA TRANSITION-QA 置 done（版本 QA 技术验收；用户最终验收 PENDING）

- **PM/integration 收口决定**：LG-040 `status` 置 **`done`**。依据**唯一治理独立 QA** `probes/lg040/TRANSITION-QA-20261016/REPORT.md`（tip `7fd0f61`，候选 **`30029eb`**）**PASS_WITH_LIMITATIONS、0 个 open important issue**，含 **fresh actual** 证据（fresh build EXIT 0 + bundle CSS hash 绑定；transition max overshoot **0**；starvation **0/1986**；宽度 **19/19**；**bounded readiness ready=true @76ms，2s 上界保留、未放宽为 8s**）。
- **顺序 `--no-ff` 合并（无冲突、无意外停车）**：`qa/lg040-final-20261016@925f828`→`88e5d4c`、`qa/lg040-settled-20261016@8a4560a`→`231644f`、`fix/lg040-transition-20261016@30029eb`→`f2b2ef3`、`qa/lg040-transition-20261016@7fd0f61`→收口 HEAD **`7cc94b5`**；四个源 tip 均为 HEAD 祖先。产品树 `backend/frontend/tests` 在 `HEAD == 30029eb == 7fd0f61`；`fc9f74b..HEAD` 产品增量**仅** `frontend/src/app/shell.css`，契约 `1.11.0`/SDK `0.1.22` 不变；收口包**未做运行时改动**。
- **历史 `8a4560a` 明确限定**：其 `readyAtMs 2592` 使用 **8000ms** 上界，违反 2s 要求，**PM 明确不采信为收口证据、仅作历史保留**，其 8s 检查**不洗白**；`30029eb` 达标（全程零溢出 + 2s 几何就绪）。
- **验收边界**：版本 QA **技术验收**按治理报告满足；**用户最终验收仍 PENDING、未发布/未部署**。LG-041 仍 `todo`、阻塞于 ASR/质量门。
- **限制如实结转（不 waived、无广义质量声明）**：G2 冻结图片实验仍 FAIL（图片 rank 2 落后同内容文本 twin rank 1）；TIFF 诚实不支持；原 BROWSER 全局 OCR 计数 **UNKNOWN ≥2**、成本 unknown（**不声称硬预算已核验**）；质量 2 OCR + 17 embedding、英文为主小样本、**任何语言均无 ASR**、中文当前 rank 7；**revoke `404` 门与 `archived` 布尔为分离契约**；Files/CSS 修复为窄范围。后端完整 pytest **863 passed / 5 skipped**（首次有效完成运行；被中断的第二次运行**无效**不计）；前端 `tsc`/`build` 与真实浏览器计数**仅取自独立 QA 报告**。
- **CLI（收口后）**：`validate` **41 tasks / 0 diagnostics**；`digest` **40 done / 1 todo / 0 in-progress**、`ready=[]`；LG-041 质量门阻塞。未新建 Task/Run。详情 [RELEASE-CLOSE REPORT](probes/lg040/RELEASE-CLOSE-20261016/REPORT.md)。

### 2026-10-16：用户明确市场范围——以英文市场为主、中文可接受（前瞻范围决定，非追溯实验通过）

- **用户原话**："> 主要内向英文市场中文可接受"（主要面向英文市场；当前中文表现可接受，限制照实披露）。**根 PM 解读**：目标市场以英文为主；用户接受当前中文表现并接受已披露的限制；**英文为发布 QA 主要语言**。
- **性质**：这是**前瞻性的范围/接受决定**，**不是追溯性实验通过**。它不改变任何已冻结的门、结果或原始证据：**所有 R3–R7 原始报告、冻结门槛/结果与源字节全部保留**，不重算排名、不调阈值、不修改历史报告。
- **对 LG-037（嵌入向量）**：**仅中文图片排名 7 不得单独作为英文导向版本 QA 的阻断项**。LG-037 实现已完成（向量模型/协议/缓存/ACL/降级机制已证），并已有**真实英文图片查询 rank1**（`Q_IMG_EN` rank 1）与音频示例（`Q_AUD_LANG`/`Q_AUD_EARTH` rank 1）等**真实数据点**；但**完整英文语料/浏览器 QA 尚未执行**。旧**中文图片硬门 FAIL（rank 7）作为历史质量结果**保留并披露，但新优先级**取消其作为英文导向版本的独立阻断项**——**不是**把它换名保留。若存在**真正独立的、未满足的原始实现验收条件**，须逐条如实记录，**不把 LG-040 的测试混同为 LG-037 完成**。
- **对 LG-041（中文 ASR）**：中文 ASR 仍**延期/未实现/质量受阻**；**"中文可接受"不批准也不解锁**它，**英文市场不等同于支持英文 ASR**；**不假装任何 ASR 已存在**。既有 SDK/契约/默认 OFF 不变，**不做版本 bump**。
- **不做**：无翻译扫荡、无 UI 实现、本包**不执行任何 QA/不宣称 QA 已通过**；不宣称用户已接受整个产品/QA/发布，也不宣称英文 E2E 已证明。
- **边界不变**：中文以当前水平支持、抽样回归、限制照实披露；英文 UI/正文/表格/图片/查询/错误流（上传/归属/校订/重处理/撤销/重建/ACL/限制/取消/重启）与词法/向量降级归 **LG-040 集中版本 QA**；**安全/数据丢失/权限/假成功在所有语言下始终阻断**，与语言无关。

### 2026-10-16：Materials R7 集成——五包 A→B→C→D→E 真实合并；可选表格模式（默认 OFF）落地；LG-035 依據原始验收条件置 done；LG-037 保持 in-progress

- **PM 决定（普通技术决定）**：本轮为**真实本地集成**（非仅证据），将 A/B/C/D/E 五包按序 `--no-ff` 合入 `main`；报告 [probes/materials-r7-integration-20261016/REPORT.md](probes/materials-r7-integration-20261016/REPORT.md)。**无 push/deploy/publish、无 reset/clean、无新模型探针**（本集成阶段产品 LAN 调用 0）。
- **真实本地集成（无冲突、无重复 pick）**：A `test/materials-fixtures-r7-20261016@f21d6e3`（真实 NIST SP 811 表格 3×8 + 人工真值、混合 2 页 PDF 文本层已核）→ `89b0cc1`；
  B `fix/materials-layout-r7-20261016@8182d36`（可选有界 `layout.py` + init 导出 + `test_layout.py`）→ `7eb88fe`；
  C `investigate/materials-endpoint-r7-20261016@1cfa417` → `e8a8e40`；D `test/materials-ocr-cohort-r7-20261016@97c4f8f` → `95b66bf`；
  E `fix/materials-table-mode-r7-20261016@4917413`（基点 `8182d36`，descends B）→ `5f84503`。最终合并产品树与 E owned 文件逐字节相同；源 tip/worktree 未变；其它历史 worktree/dirty 全保留。
- **PM 决定 1：LG-035 → `done`（待 LG-040 集中版本 QA）**。依据 PM 授权：实现可置 done **仅当**技术 receipt 覆盖**实际原始验收条件**（baseline+new cohorts）——已列如：真实清晰页 CER 0.0000、低质量页诚实记录降级（无倣造 numeric gate）、多页 p1 0.0000/p2 0.0763、中文印刷 Z1 **0.0423**、**真实 grid + 人工真值 PASS（可选表格模式）** E T1 真实 8×3 cell CER **0.0**、符号 7/7、混合 D MIX p1 **0.0295**/p2 **0.0000**、baseline 机器/正式分离与重处理不覆盖。仅改 frontmatter `status` + 追加正文，**assignee/IDs 保留**。
- **表格质量口径（诚实）**：E 表格 PASS 为**单次单样本**（born-digital 网格）；D **默认管线**（表格模式 OFF）对同一真实网格仍 **FAIL**（扁平列表、0 行/列、cell CER 1.0）；**历史 R3/R4/R5/R6/R7-cohort 表格 FAIL 全部保留不改写**；Z2 多列阅读顺序归 LG-040；**不宣称统计级/全类质量通过**。
- **PM 决定 2：LG-037 保持 `in-progress`**。C 取得**首次完整可复算真实排名**（`Q_IMG_ZH` rank **7/10**、score **0.725667**、`margin_to_prev` **0.00037**）；协议逐维一致、唯一确定性差异是 timeout（30 s vs 90 s）；R6 瞬时故障归因**plausible 但未唯一证明**（缺 raw 体/异常类型）、**health 200 ≠ embeddings 容量**、**不证明产品代码缺陷**；旧 R5 图片硬门 **FAIL 不变**、不加新阈值、不在冻结查询上调阈值、**无跨模态质量结论**。
- **契约：无版本 bump（内部扩展）**。`prompt_kind`/`prompt_sha256`/`table_classification` 仅写入不透明本地派生证据（`derivative/ocr_evidence.jsonl` + pages `source_derivative` 文档），**不属**冻结 `source` schema/API/枚举/迁移（docs/08 §6.6/§13 先例同 `LIGHTGRAVITY_OCR_SCALE`）；`LIGHTGRAVITY_OCR_TABLE_MODE` 为可选非秘密 env（缺省 OFF），接受值 `1/true/yes/on` 与 `0/false/no/off`（不区分大小写），其它值显式报错；页/输入上界沿用既有 `ProcessingConfig`。**无 fake 'changed' 声明**；契约保持 **`1.11.0`**、SDK **`0.1.22`**。已写 docs/08 §6.6 + docs/09 + README 使用说明。
- **集成检查（真实 exit，绑定合并候选）**：`mypy` **138 files clean**；`pytest tests/sources -q` **147 passed, 1 skipped**；`test_layout`+`test_table_mode` **28 passed**；`offline_gate.py` **ALL_OK**；Board `validate` **41 / 0 diagnostics**、`digest` **38 done / 1 in-progress / 2 todo**、`ready=[]`。`api/`/`service.py`/`content.py`/`models.py` 逐字节不变（源 API 未改）；无运行期绝对引用依赖。
- **状态与下一步**：**LG-040/041 仍 locked**（LG-037 仍阻塞 LG-040）；下一步为**已命名的 LG-040 集中版本 QA**；向量需更大更平衡跨模态语料 + margin 诊断（不自动采样、不在冻结查询上调阈值）。本集成产品 LAN 调用 **0**、音频 **0**；pi/DeepSeek 成本 unknown 非 0。

### 2026-10-16：Materials R6 集成——OCR 版面原型不合并（scale 不稳）；B/C/D probes-only 合并；接受前瞻协议修正规划；无质量通过

- **PM 决定（普通技术决定）**：本轮只集成**证据**，**无质量通过、无状态变更**。报告 [probes/materials-r6-integration-20261016/REPORT.md](probes/materials-r6-integration-20261016/REPORT.md)。
- **OCR 版面原型（A）不合并**：`layout.py`/`__init__.py`/`test_layout.py` 留在分支 `dev/materials-ocr-layout-r6-20261016@98df131`，不合并：**scale-sensitive**（同一 Z2 页 gutter 模型在 scale 2.0 与 4.0 计数 **2 vs 4** 不稳定）、未集成默认管线、独立 API 过早。仅 `probes/materials-ocr-layout-r6-20261016/**` **12 个 evidence 文件**经 `git restore --source=...` 精确入库（owned commit `72f7125`，逐文件字节一致）；源分支/worktree 全保留，main 保留原默认管线。**新增集成 erratum**：A wrapper 在 evidence+report commit **之后** 才因 `token_budget_exceeded` `exit 143`（**非正常成功**），且版面计数 **2 vs 4 scale 不稳定**——均为**结构性信号证据、非质量通过**；replay 需 A 产品候选 `d996bef`，main 产品未变。
- **B/C/D probes-only `--no-ff` 顺序合并**（无冲突、无重复 pick）：B `d189f43`（向量诊断：旧 margin **UNKNOWN**、未证产品排序缺陷）、C `7069ffe`（证据可观测：真实 2 POST 均 30 s `index_unavailable`、health 1 GET 200、**无真实新排名**、stub `order_match` 仅 WEAK PATH）、D `6bef4ed`（协议调查：`15×3` 错分类）。历史报告字节未改（A REPORT `4923cb23…`、B `4296c4fe…`、C `d22d35b6…`、D DECISION `1a60cb7f…`）；源 tip 未变。
- **接受前瞻协议修正规划**：未支持的 `15×3` 假设**不得作为已证几何真值**；历史 R3/R4/R5 FAIL 维持（段 CER > 0.25 独立成立）、旧协议/JSON 不动、**不宣 Z2 pass**；仍需**真实 grid + 人工 cell 真值 / 新冻结 cohort**，**table cell CER 0.25 / page CER 0.15 阈值不变**；如实记录 **U1（无人眼视觉确认）**、不作实际视觉声明；既有用户授权的普通后续工作**不重新索权、不新增许可阻塞**；**任务状态不变**，真实表格与混合覆盖 UNMET。
- **LG-037 保持 `in-progress`**：超时下**无实际新排名**，旧 R5 图片硬门 FAIL 不变；区分旧负向 top-k NN 无弃答（预期）与 ACL；**不加新阈值/媒体过滤**。
- **未范围外重写**：不新增硬门、不改阈值/协议/产品字节、不宣称质量通过；LG-035/037 仅追加正文、frontmatter 不变。契约 `1.11.0`、SDK `0.1.22` 不变；本集成产品 LAN 调用 **0**、音频 **0**。

### 2026-10-16：Materials R5 收拢——拒绝默认新 OCR 提示词；向量 r5 仅证据合并；记录音频总预算越界 errata

- **PM 决定（普通技术决定）**：本轮只集成**证据**，**无质量通过、无状态变更**。报告 [probes/materials-r5-close-20261016/REPORT.md](probes/materials-r5-close-20261016/REPORT.md)。
- **OCR r5 通用提示词候选：拒绝成为默认**。理由——Z2 表格公平 token 加权段 CER **0.277946** 比 R4 **0.268882** 更差、精确人工行 token **6/15**（R4 8/15）、机器表行 **0**（协议 §4 结构 FAIL）；Z1 整页 CER 0.10582（旧 0.0423，单次非统计）。⇒ 产品分支/默认新提示词**不合并**，仅 `probes/materials-ocr-r5-20261016/**` 证据入库（owned commit `767f1ea`）；源分支 `1a4759c` 与 worktree 全保留，main 保留原产品哈希/原提示词。
- **向量 r5：probes-only 合并**（`--no-ff`，`d08144c`），2 真实音频 + 2 图片 + 6 中文文本如实报告；两侧音频 rank 1、ZH 图片未进 top-5；**冻结图片硬门未过** ⇒ LG-037 保持 `in-progress`。
- **音频总预算越界 errata（新 REPORT 记录，不改源 report 字节）**：授权 **total ≤ 30 s**，实际 **32.048 s**（30 s + 2.048 s），**超 ≈6.8%**；源报告"每 POST ≤30 s"非原始 total 上界。不重跑掩盖、不追溯改预算；R4 旧数字保留；**无 ASR、不解锁 LG-041**。
- **不范围外重写**：不新增硬门，不宣 LG-040 ready/pass；LG-035/037 仅追加正文、frontmatter 不变。下一步 OCR 做**版面/列切分**（非提示词抽奖），向量做**更大语料/margin 诊断**。契约 `1.11.0`、SDK `0.1.22` 不变；本集成产品调用 0。

### 2026-10-16：接口契约冻结 1.11.0（LG-031 runtime/API/SDK 集成公开兼容变化保守 MINOR）

- **PM 普通技术决定**：正式契约由 `1.10.0` 升至 **`1.11.0` MINOR**。依据 R1 独立复验（`qa/lg032-runtime-r1@26ea945`）观察 **O3**：`afcae82` 落地后存在**实际公开兼容变化**——① 四个去中心化端点（`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、`POST /subtasks/{subtask_id}/lease/renew`、`POST /subtasks/{subtask_id}/lease/release`）请求体 `owner` 由 `1.6.0` 冻结时事实采用的 **required/端点采用** 放宽为 **optional/仅一致性校验、不再具有授权含义**；② `ExecutionGrant` 加性新增进程内非持久字段 `lease_owner`。按 docs/08 §13「新增向后兼容字段/语义放宽为 MINOR」**保守**分类为 `1.11.0`，取代此前 `1.10.0` 的“实现说明增补（无版本变化）”口径。
- **精确行为**：四端点 principal/scope/fence 仅从 `ApiContext.worker_grant`（`X-LG-Execution-Grant`）解析的程序冻结 grant 推导；body `owner` 存在且不等于认证 principal ⇒ `claim_refused`/`identity_mismatch` 且**不落盘**；无 resolver/无效 grant ⇒ `claim_refused`/`unauthenticated`；body `capability`/`write`/`scope` 不授予权限。**回退**：旧客户端传 `owner` 仍被接受（仅一致性校验、不获授权），不传亦可用；认证 A 不能冒 B/跨 TaskRun，只读身份不能写。**安全边界**：未配置/未认证一律 default-deny 且不写业务状态；仍不接受浏览器直接指定任意 `owner`；`lease_owner` 不进入 HTTP/实体 schema（进程内非持久）。
- **源锚与非机械覆盖**：本次分类基于 `afcae82` 实际实现（`api/collaboration.py` 四端点经 grant 推导 + `collaboration/execution_grant.py` 的 `lease_owner`/`effective_lease_owner`）与 R1 观察 O3，**不沿用历史拟议的 `1.6.0`**，也不重写任何旧 JSON/PLAN/日志。`1.10.0`/e0 首版 L0 包与所有历史证据**保持原版本**。
- **范围**：本包仅改**接口版本元数据**（`docs/08` 变更控制先行 + `contracts/constants.py` + 当前测试断言 + README/PROJECT/agent/docs06 入口），**不顺带改任何 runtime 行为**。`git diff afcae82 HEAD -- backend frontend tests pyproject.toml uv.lock Makefile` 已证实除版本常量/测试断言外产品树逐字节相同。SDK `google-antigravity==0.1.22`、默认自主 off / `max_parallel=1` 保持。**main 本轮不合此候选**。

### 2026-10-16：核心首版 QA 收口——LG-022 流式停止独立复验合入并 done，LG-023 采样前预算最终修订

- **唯一串行验收证据整合/排期 owner，主代理只 PM，无嵌套派工/推送/部署/发布；本包产品生成 0**（不执行评估/新探针/不重跑模型或测试）。详见 [probes/batch-20261016/CORE-QA-CLOSE.md](probes/batch-20261016/CORE-QA-CLOSE.md)。
- **独立 QA 已退出**：`agent:pi-lg022-stream-qa` 退出，`qa/lg022-stream@49c95f5` clean、**仅 14 个 QA 文件**；结论**门内 PASS、无未修重要缺陷**（硬门 `hard_gate_pass=true`、主链 `ok=true` 真 DeepSeek 5/10 到绑定 accept）。无 fail ⇒ 可 claim 023。
- **merge 仅 QA 证据**：`git merge --ff-only qa/lg022-stream` → **`main@49c95f5`**；`git diff e0a8cec main -- backend/ frontend/ src/ tests/ docs/ pyproject.toml` **为空** ⇒ 产品树与已验候选逐字节相同，**无新代码故不重跑全量 pytest**。旧 worktree/dirty 全保留，未 reset/clean/覆盖/重复 pick、未复制 `.env`。
- **LG-022 → `done`（仅门内范围）**：真 SDK 0.1.22 + 真产品装配 + 本地有效 fake SSE 的流式 pause/cancel 真实停止 PASS；真 DeepSeek 主链一例 PASS；持久生成账本 PASS。**不宣称整产品 pass**：**未测**真实 DeepSeek 上游下 cancel/pause-during-review、重启后 `verifying`/`repairing → recovery_required`、跨 Run 真实 reject/repair、light/浏览器矩阵（引用 021/027 旧证据）；**SDK 取消已用真 SDK+本地 SSE 证明，不冒充 DeepSeek 故障**；旧错误 PASS 标题仅覆盖持久账本+停止门主链、**不覆盖**本次流式修复；历史两轮失败保留。
- **成本不归零**：022 首轮 **unknown**、R1 **6**、R2 **8**（两账本未统一、未执行统一总额硬限，非产品缺陷）、本 phase **5/10**、收口包 **0**；031 工程 **34/40**（原运行 SoT 部分字节丢失，**SDK 原件（3 session DB + 原 stdout）持久备份**、硬条件 4 只读哈希恢复，恢复限制保留）。**源哈希核准**：流式修复源为 **`7d0510d`**，QA 报告叙事 `7d0510c` 为笔误（仓库不存在该提交），本汇总引用正确哈希、不篡改原证据。
- **LG-023 排期决策**：`validate`/`digest` 确认 complete/无诊断且 LG-023 `ready` 后 **CLI 原子 claim `LG-023 --as agent:pi-lg023`**（不直接绕 claim），基于最终 main/claim commit 创建全新持久 worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg023`（`dev/lg023`，路径存在先核不覆盖）。**本包不执行评估**。
- **LG-023 预算决定（PM 文档明确；采样前最终修订，非看实验结果后改额）**：样本与成功门**固定为两任务 × 两 arm × 一次**；预算为 **4 attempts / 总 48 真实 DeepSeek 生成 / 每 attempt 12**；**全 stage 同 phase 持久 ledger**（不分账）；**output ≤ 16000 tokens、HTTP 120s、retry 0、并发 ≤ 2**。**旧 16/24/6 只是未执行草稿、作废**，不构成额度；按已见真实双 worker 链约 **10 calls**，为**双方 arm 设同样足够 cap**，不以一方预算不足误判失败。
- **LG-032 暂不 claim**：原任务 ready ≠ 要立刻占有；待 023 评估后与 **LG-024** 并行排期。**LG-035/037 保持 `in-progress`**、**LG-040/041 不解锁**。**契约保持 `1.10.0`、SDK `0.1.22` 不变**；未推送/部署/发布。

### 2026-10-16：第七批集成——LG-022 R2 持久停止/账本 + LG-031 R2 自主领取/共享计数整合

- **集成前核对**：`main` `29ffbb6`（clean）；`fix/lg022-r2@e59e12a`、`fix/lg031-r2@3821620` 均 clean，`main` 与其先前合并关系已核。整合候选 `integrate/batch7`：`8a92439` 合 022-r2（无冲突）、`0144eb7` 合 031-r2（2 处文本冲突，逐条保留）。旧分支/worktree/probes/dirty 全部保留，未 reset/clean/覆盖/重复 pick、未复制 `.env`。
- **持久账本为唯一生成限额事实源**：`api/bootstrap.py` 中 `configure_generation_ledger(settings.data_dir)`（022）先于 `generation_budget=global_generation_counter()`（031）执行，031 注入的是**已被换成持久账本**的全局计数，**不被 031 旧内存计数覆盖**。进程内冒烟（本地替身、无真实模型）`snapshot` 报 `persistent: True`、`reserve` 递增持久 count、`<data_dir>/generation/` 账本文件真实创建。**契约保持 `1.10.0`**（031 未新增版本，不机械升版）。
- **LG-031 实际修复保留**：`coordinator/graph.py` 自主路径 claim 检查移到**执行后、revoke 前**，程序只授权被排度节点；此前失败的 `test_autonomous_worker_tool_claim_grants_node` 现通过；**未读旧 dirty `fix/lg031-r1` 覆盖当前**。
- **集成检查（真实退出码，绑定 `0144eb7`）**：`mypy` exit 0 → **137 files clean**；`pytest -q` exit 0 → **775 passed, 2 skipped**。**本包产品真实模型/外部服务调用 0**；UI 未改、未重跑整套前端。
- **状态如实**：**LG-022 仍 in-progress 待独立 QA（`qa/lg022-r2`）**；**LG-031 仍 in-progress**（真 2 worker+交接+候选 review 仍缺，续接 `fix/lg031-r3`）；LG-035/037 in-progress（质量门/端点不可达）；**LG-023/032 todo 未 claim**；**LG-040/041 不解锁**。
- **成本账本**：LG-031 累计真实产品请求 **10/10**（原 1 + R1 3 + R2 6）；主代理新 phase3 另行授权**最多 14**，合计**上限 24**，**不是 032 对照实验**；LG-022 首轮 QA 总数 unknown、R1 **6/10**，**两轮失败记录都保留**。报告 [probes/batch-20261016/INTEGRATION-7.md](probes/batch-20261016/INTEGRATION-7.md)。

### 2026-10-16：第五批集成——031 接线合回、036 词法挂载、031 保持 in-progress（真实缺口）

- **LG-031 安全合回 `main`（`dev/lg031` `d4c0815`，`--no-ff`）**：保留 main 最新 021 状态/036 机制/022 claim；031 owner 已释放共享 `api/app.py`/`bootstrap.py`/docs08，本集成 owner 为唯一 writer，在同一次提交中一并加装 LG-036 `build_search_router()`（1 import + 1 `include_router`），`worker_identity`/`execution_grants` 注入保留，两侧安全接线。新协作默认关闭、程序权限/状态/预算/验收权威、无常驻模型编排。
- **LG-036 `in-progress` → `done`（待版本 QA LG-040）**：真实默认 app 上 `GET /api/v1/search` → 200、缺失缓存诚实 `index_unavailable`/`hits=[]`、`POST` → 405（GET 只读）；集成候选 `pytest -q` **693 passed, 1 skipped**、mypy **130 files clean**。装配条件满足故 done；**不降 LG-035 真实 OCR 门、不动 LG-040 门**，无向量（LG-037 未实现）、无 Chat/Files UI（LG-038 未实现）。
- **LG-031 保持 `in-progress`（真实运行硬条件未满足，非错误等 032 版本门）**：031 的 1 次 DeepSeek 只是**独立 reviewer**，不是 SDK 多 worker；**真实 Git + 进程内 fake executor** 不等于“真实 SDK 两 worker 发现/领取/交接/隔离执行”。不把完整 checkpoint skip 未实现夸大，不扩大恢复重放。预留连续实施分支 `fix/lg031-r1`（保留原 `dev/lg031`）。
- **契约升至 `1.10.0`（LG-022 第二轮针对性返修 REFIX-R2，加性 MINOR）**：① **停止门可接受真实停止事实**——成功 Run 记录真实 `session_refs`/reviewer 资源时 `cleanup` 常为 `pending`，停止门除 `cleanup=done` 外接受权威适配器停止确认（SDK session `Agent.__aexit__` / loopback 代理真实关闭）作为 session/reviewer 已停止证明，Run 加性新增可选 `reviewer_cleanup`；未知/仍活跃/关闭失败/损坏保持 `unconfirmed` 并保留 `session_refs`，不伪造 `cleanup=done`。② **持久生成账本**——全局生成计数（`GET /api/v1/diagnostics/generation`）改为受控 dataRoot 下持久账本（append-only JSONL 事实源 + 可重建原子计数快照），**转发前持久预留**，跨 worker/reviewer/session/进程重启不归零，损坏/不可读即**拒绝转发并报 unknown，绝不当 0**；诊断加性新增 `persistent`（及损坏时 `corrupt`/`reason`）；账本仅记计数与最小非秘密元数据，不落输入/prompt/header/凭证/grant。**不新增端点/枚举/迁移方向/错误码**。此前 **契约升至 `1.9.0`（返修后串行集成收拢，加性 MINOR）**：新增 `source.archived` 可逆归档字段与 `archive`/`unarchive` 动作（归档保留来源/检索/打开/权限，不是使资料不可用的 `revoke`；含可选 `expected_revision` 乐观并发），并挂载默认禁用的可选向量端点 `GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（后端仅环境变量配置、候选回源核对、不可用时词法/原件仍可用）。此前 **契约升至 `1.8.0`（LG-022 R1，加性 MINOR）**：新增合法迁移方向 `verifying → recovery_required`、`repairing → recovery_required`（复核/返修阶段重启后未知副作用诚实停车，不重放）与只读诊断端点 `GET /api/v1/diagnostics/generation`（进程全局上游生成请求计数，转发前计数，供集中 QA 约束/观测全局硬上限）；D1/D2 为 reviewer 实现与生命周期修复，不改既有端点/枚举语义。037 向量与 038 UI 未实现如实标。
- **就绪任务 CLI claim**：LG-031 合回后 LG-037（`agent:pi-lg037`）、LG-038（`agent:pi-lg038`）依赖满足，持久 worktree `lg037`/`lg038` 基于同一 claim commit；不复制 `.env`、不覆盖已有；LG-022 仍 `in-progress`，保留不重 claim。
- **已知风险**：`tests/collaboration/test_claims.py::test_two_owner_race...` 为既有 discovery/lease 竞争偶发 `not_discoverable`；本轮全量单跑一次通过、单跑连跑 3 次通过，**未宣称其无害/无缺陷**，留 LG-032 固定判定口径。
- 产品模型/外部服务调用 **0**；本项报告 [probes/batch-20261016/INTEGRATION-5.md](probes/batch-20261016/INTEGRATION-5.md)。

### 2026-10-16：LG-036 真实依赖校正与 LG-017 状态语义纠正

- **LG-036 依赖校正（真实依赖，非降门）**：依据只读技术调查（副本 [probes/lg036/DEPENDENCY-AUDIT.md](probes/lg036/DEPENDENCY-AUDIT.md)）与 PM 决定（`checkpoints/2026-10-15/pm-decision-lg036-20261016.txt`），将 LG-036 `depends_on` 由 `[LG-034, LG-035]` 校正为 `[LG-033, LG-034]`。本项需要的是**已交付的内容接口**（LG-035 commit `faf7230`/`d7e4391`、第三批集成提交提供的 `/content`/`/download`/`/actions` 只读通道、source/版本/哈希/权限接口），与 LG-035 **尚未通过的真实 OCR 质量门**无关。**不降低 LG-035 验收、不改 LG-040 依赖、不声称图片/PDF 检索质量已通过**：无派生正文或正文不可信的来源须诚实 `not_indexed`。
- **LG-017 状态语义纠正**：LG-017 原 `status` 注释把“待 LG-022 独立集中 QA”当作本项 done 的前置，而 LG-022 自身 `depends_on` 含 LG-017，形成错误循环，违反 [agent.md](agent.md) 第 1/8 节（集中 QA 只在命名大版本完成后开展，不是逐项前置）。本项实施目标——产品已实现的独立 ModelReviewer 路径——已由 R1（真实受控独立复核 + 诚实 `unavailable` 默认 + 真实 DeepSeek 探针 passed 且程序验真）与第三批 Settings reviewer 默认 UI 满足，未发现实缺口。据此置 **`done` 并标注“待 LG-022 集中 QA、非完整版本通过”**，移除错误循环注释；**不改 LG-022 依赖**、不宣称版本验收。
- **证据**：LG-036 依赖校正与 LG-017 纠正均由 PM 决定，具体任务/CLI claim/worktree 准备记录见 [probes/batch-20261016/PREPARE-4.md](probes/batch-20261016/PREPARE-4.md)。产品模型调用 0，未运行 QA。

### 2026-10-15：排入去中心化协作与 Embedding 资料工作线

- 用户要求两条工作线正式排期。新增 LG-028～041 共 14 项 todo，连同原 27 项共 41 项；不修改既有任务状态、负责人和验收记录，不自动开始实施。
- 去中心化按契约 → 原子领取/租约 → 同伴交接 → 隔离执行与 QA/返修整合 → 集中版本验收推进（LG-028～032）。模型提议和领取请求必须经程序授权，不引入常驻模型编排 agent，不放弃文件 SoT、权限、预算与人工验收。
- 资料线按契约 → 原件摄取 → 图片/PDF OCR → 词法索引 → 可选 EmbeddingGemma 2 → Chat/Files 整合与集中验收推进（LG-033～040）。中文 ASR 先独立验证（LG-039），达标再接入及验收（LG-041）；不以向量代替文字，不要求独立向量数据库。
- 契约和 ASR 验证可先准备，独立实现按真实依赖并行，共享 Store/Coordinator/API 由单 owner 串行集成；两个新版本的最终验收在既有 LG-022 首版验收后开展。LG-032 必须比较相同验收门下执行、QA、返修、复验与失败尝试的完整成本，不预先承诺收益。
- 排期为阶段、依赖与验收门顺序，未承诺日历日期；中文 ASR 不达标不阻塞图片/PDF 与检索版本。邮箱、文件夹增量、网页抓取、Office 完整支持暂缓，不隐含纳入这次交付。当前契约已升 1.10.0（LG-022 第二轮针对性返修 REFIX-R2 加性：停止门真实停止事实 + 持久生成账本诊断字段；1.9.0 为返修后串行集成收拢加性：可逆归档字段/动作与可选向量端点挂载；1.8.0 LG-022 R1 加性：`verifying`/`repairing → recovery_required` 与全局生成计数诊断端点；1.7.0 为 LG-017 返修 R1 加性：独立复核者设置角色/字段 `default_reviewer_connection_ref`、Task 返修账本 `reviewer`/`reviewer_kind`/`model_usage` 与 review/rework 事件 payload，明确程序机器门不等于独立复核、无 reviewer ⇒ `unavailable` 阻止 accept；1.6.0 的 LG-028 去中心化协作+LG-033 资料摄取/检索均仅接口、未实现），实现以该版为准，详见 [滚动排期](docs/06-roadmap.md)。

### 2026-10-15：产品定位扩展为个人 AI 工作助手

- 用户确认将产品类型与定位写入文档：从以开发交付验证闭环的 AI 任务助手，扩展为能使用用户资料完成任务的个人 AI 工作助手。核心价值包括资料整理、查找与任务执行、验收，资料接入服务于后续工作，不止于保存和检索。
- Chat 统一承接资料、目标与结果反馈，Files 负责整理归档与来源追溯；原件、正式内容与元数据保持文件 SoT，索引为可重建派生。资料接入不自动创建交付 Task/Run，执行仍遵授权与验收边界。
- 去中心化编排属于内部执行架构方向，不替代面向用户的产品定位；保持程序控制权限、状态、预算与调度，worker 按需协作，默认不设独立常驻模型编排 agent。完整的自主领取、发现与点对点协作尚未产品化，不因定位调整而宣称已实现。
- 本次只同步定位文档，不扩大首版已验证能力，不改变接口契约、开发任务状态或实施优先级。资料接入与检索仍待实现，首版开发任务交付闭环及既有验收范围保持原定义。

### 2026-10-15：Chat 统一接入资料，文件保持 SoT，Files 负责整理与追溯

- 用户确认以 Chat 统一管理资料接入，并要求开始写文档。上传、拖拽、粘贴链接，以及未来文件夹/邮箱接入都由对话发起；选择器或授权页返回同一对话。Files 用于浏览、预览、校订、归档调整、来源追溯与重新处理，不让用户在多个页面重复上传。现有 Files 上传接口与界面尚未迁移，本条是目标交互决策，不将目标描述为已实现。
- 资料接入先受控保存原件，再提取内容、确定归属、形成正式文件、建立索引并回执。沿用明确的 Task/Project 范围；全局无归属资料先进入会话关联的受控收件区，不为保存资料强建交付 Task。存在实质归属歧义才询问；模型给建议，程序校验授权并落实。接收资料不自动创建交付 Run/团队；用户要求据此修改工程时，仍走已有 Task/Run、验证和人工验收。
- 原始媒体、资料 frontmatter 与正式内容文件保留事实和来源，JSONL 保留历史；机器提取、页图、片段与索引均有明确的派生关系。人工校订保存为正式文件版本，重处理不得覆盖。词法索引及可选向量只作可重建缓存，不保存独有权限、归属或控制状态；命中后回源核对存在性、内容哈希、版本和访问范围，撤销/删除来源使旧命中失效。
- 索引不要求独立向量数据库服务，也不增加常驻编排 agent。文字 OCR/转写与媒体直接向量检索是不同能力，可以按需组合；不将向量输出当成文字提取。邮箱和文件夹接入是后续资料连接器，不复用现有模型 Connection 的冻结配置语义，不默认全邮箱同步或自动执行邮件内容。
- 已有隔离探针仅证明：两份干净合成中文截图/扫描页经 qwen3.8-27b OCR，归一化后与原文一致，并已生成 Markdown、完成词法检索/索引重建/过期来源拒绝；EmbeddingGemma 2 的语义查询只得到小样本排序证据。已测 Qwen 与 embedding 模型的音频成文均未打通，其他生成模型未测试，中文 ASR/Reader 后端仍待验证与接入。不得将上述结果扩展为生产级 OCR、中文转写或完整产品已交付。
- 本轮已完成 [资料接入与检索设计](docs/09-source-intake-and-retrieval.md)，同步 README、agent.md、docs/01、02、04、05、08 与进展记录。补清了摄取目录写入授权、跨来源/跨 Task 去重不合并权限、接入请求幂等和来源版本更新的区别。新增资料实体/schema/API 已随后续 LG-028/033 串行冻结升至 1.6.0（2026-10-16）；具体实现仍待 LG-034～041，且仅接口未实现。
- 已将两个既有探针的 28 项报告、指标与必要样本逐字节归档（952,781 字节），[证据入口](probes/source-intake/README.md) 标明原型与转写验证局限，[清单](probes/source-intake/evidence/MANIFEST.json) 保存来源与 SHA-256。文档执行者复核 125 条相对链接、frontmatter、归档摘要及 diff 空白检查通过，见 [检查记录](probes/source-intake/DOC_CHECKS.md)。本轮未改代码、依赖、模型配置，未启动连接器或新推理实验，未新增或改动开发任务状态，未提交或发布；文档检查不代表功能或版本 QA 通过。

### 2026-10-15：无独立编排改动独立 QA 通过，首轮接口缺陷已返修复验

- 用户要求对刚集成的退役改动做 QA，本次范围为该改动，不替代全产品版本 QA。独立 pi 执行者只读候选代码并独立复现，结果为 **FAIL**，详见 [首轮 QA 报告](probes/no-orchestrator-adoption/qa-r1/REPORT.md)。
- 发现：ModelPlanner 的实例级调用计数跨 Run 共用，第二个显式规划请求会失败，且请求上限未实际落实；PlanningRequest 未完整校验 trigger/requested_by，可能在派发时产生未捕获异常。原新增测试未覆盖这些边界。
- 默认无模型编排路径、计划校验及既有验收闭环检查通过；独立重跑为 397 passed、1 skipped，mypy 通过，但测试全绿不覆盖上述缺陷。本次无产品真实 SDK 新调用。
- pi 已在新隔离 worktree 返修并精确集成，详见 [返修记录](probes/no-orchestrator-adoption/fix-r1/REPORT.md)：程序按 run_id 检查和消耗 PlanningRequest.max_calls，调用失败也计数；不同 Run 各自计数，默认共享 ModelPlanner 不再设置实例级调用上限。合法 trigger 字符串规范化，非法 trigger/requested_by 在构造时拒绝，记录步骤异常转为明确失败结果。新增真实 ModelPlanner 配合本地假提议函数的边界回归。
- 第二个独立 pi 执行者只读复核当前候选并补充负向/并发复现，最终判定 **PASS（仅本次改动及返修范围）**，见 [第二轮 QA 报告](probes/no-orchestrator-adoption/qa-r2/REPORT.md)。跨 Run/并发计数隔离、同 Run 超限与失败尝试计数、非法请求拒绝、无效计划不落盘、计划哈希一致及默认程序路径均通过。首轮原复现脚本未修改，复跑退出码 0；审查前后候选哈希一致。
- 独立复跑：聚焦 45 passed，契约 7 passed，全量后端 416 passed、1 skipped，mypy 86 个源文件通过。唯一 skip 为真实 DeepSeek 门控测试；本次 QA/返修产品真实 SDK 新调用为 0，未提交或发布，首轮失败证据保留。
- 限制：按需模型后端与用户触发端点未实现；调用预算只覆盖每 Run 的提议次数，不等同 Task 完整 token/费用预算；请求和计数仅存于进程内、不持久化，计数尚未清理。独立 QA 另记录了 HEAD 已存在的自定义 planner 返回非法结构时的异常处理缺口，与本次默认路径无关，不将其当本次回归。结论不扩展到全产品版本 QA、新真实 SDK E2E 或成本收益证明。

### 2026-10-15：采用无独立编排方案，淘汰常驻模型编排与必经初始模型规划

- 用户明确决定采用新方案并淘汰旧方案。本条取代下列实验阶段“暂不改变产品默认行为”的临时处理：产品默认不设置独立常驻编排 agent，不把初始模型规划作为每次交付的前置步骤。程序 Coordinator、Scheduler、Store、计划校验、权限/预算与验收闭环继续保留；开发本项目仍按 agent.md 通过 pi 派工，与产品角色退役无关。
- 明确目标由 worker 执行，程序维护最小执行记录与合法计划快照。规划保留为按需能力：提议需要程序校验，不自行取得控制状态写入权，也不形成隐形常驻编排循环。实际已实现能力与设计预留须分开说明。
- pi 现状调查确认：正式 bootstrap 原本使用确定性的 RuleBasedPlanner，并没有常驻编排模型；ModelPlanner 只是未接线的可注入接口。因此本次淘汰主要落实为架构规范退役与调用边界调整，不虚称删除了原本不存在的运行进程，也不将原有程序最小计划误作待删模型能力。
- 决策依据是现有小任务可行性与用户对复杂度/完整交付成本的取舍，并非已经证明全生命周期成本改善 15%。纠正版固定轮次实验中 B 消耗 441,700 reported tokens、代码验收通过 2/3；C 消耗 403,523、通过 3/3。有规划组尚有未交付任务，后续 QA、返修与复验成本未测量；无规划组也未经过新增的同标准独立 QA。失败后仍需支出的成本不能视为零。
- 后续成本评估采用同一验收门下执行、QA、返修、复验与失败尝试的完整成本；未完成样本单独报告，不当作已交付样本。原先固定轮次中位数门限只保留为历史实验判据，不能代替完整交付成本。
- pi 已在隔离 worktree 完成调查、实施及精确白名单集成：默认使用程序最小计划；即使注入 planner，也只有携带触发原因的显式 PlanningRequest 才在单次派发中调用一次，采纳结果经原有计划校验并保存原因快照。首轮实施将 ModelPlanner 实例上限设为 1，后经上述 QA 返修改为默认无实例上限，由程序按 Run 落实请求调用预算（默认 1），失败尝试也计数；无隐形模型编排循环。真实按需模型后端及用户触发端点尚未实现，当前只保留内部提议接口，不宣称已有完整按需模型规划功能。
- agent.md、README 与 docs/01、02、03、04、08 已同步；无公开 API/schema/事件变更，契约保持 1.5.0。集成后执行者自检：全量后端 pytest 为 397 passed、1 skipped，mypy 86 个源文件无问题；聚焦规划/调度测试 18 passed、契约 7 passed、验证与 API 集成 52 passed。详情见 [退役实施报告](probes/no-orchestrator-adoption/REPORT.md) 与 [局部检查日志](probes/no-orchestrator-adoption/logs/main-integration.log)。
- 本包产品真实 SDK 新调用为 0，未追加对比实验，未提交或发布，未改写既有实验原始证据；既有 r2 原始 YAML 诊断保留。原实施自检之后已按用户要求完成上述变更范围独立 QA；全产品仍待现有里程碑版本 QA，不将局部或旧版 QA 结论自动扩展为全产品验收。

### 2026-10-15：真实 SDK 纠正版对比完成，无编排可运行但收益未达到删除门槛

- 用户授权的真实 SDK 验证及必要返修已完成。首轮 SDK 的无效对比保留在 `probes/agensh-orchestration-sdk/`；纠正版独立保存在 [实验入口](probes/agensh-orchestration-sdk-corrected/README.md)、[协议](probes/agensh-orchestration-sdk-corrected/PROTOCOL.md) 与 [结果报告](probes/agensh-orchestration-sdk-corrected/REPORT.md)。冻结时间为 `2026-10-15T07:07:11Z`，正式执行 `07:07:30Z–07:13:42Z`。两个批次不混入同一对比统计。
- 有效性修复：3/3 B 计划通过严格 schema 且实际注入各自 8 个 worker turn；完整 finish 从 SDK 原生钩子取回并与 session DB 交叉核对；识别真实 `AbsolutePath`/`TargetFile`，未知文件参数拒绝；实际发送删除冲突的 `max_completion_tokens`，只保留 `max_tokens=8192`；51/51 turn 有实验侧正向停止观测。未修改产品 executor 源码，也没有把正常返回的 `stop_confirmed=null` 假写成 true。
- 结果（每类每组 1 次，共 6 个新样本）：B 仅初始规划全部代码验收通过 2/3（17/21 条目），C 无独立编排 3/3（21/21）。三类均有真实 SDK 文件读写与 diff；B 在需求变更任务的 writer 触及每 turn 模型调用限额，新增功能未交付（5/9），不能推断为规划普遍有害。部分 SDK turn 失败或预算耗尽仍计入数据，不把代码验收通过等同所有 turn 均成功。
- 最终成本口径采用中继实际 upstream reported usage：B/C 中位样本 tokens 为 144,758/131,961，C 减少 8.84%；耗时中位数为 57.653s/55.829s，减少 3.16%，均未达到预先设定的 15% 收益门。驱动/SDK 快照少计一个失败 turn 中已发生的 7,997-token 请求，因此不采用该快照计算的 12.29% 节省比例；差异根因未进一步验证，不猜测。
- 用量：纠正版校准 2 turn、6 HTTP、26,628 reported tokens、12.17s；正式 51 turn、154 HTTP、845,223 reported tokens、约 372s；合计 160 HTTP、871,851 tokens，在纠正包预算内。初始校准 helper 误检查两个文件，已对原有单租约产物离线复核，未追加模型样本且原始失败记录保留。旧 SDK 包校准/正式另计；pi 开发与调查代理用量不包含在上述实验指标中，费用未知。
- 权限/SoT：15 次非租约或授权根外的访问尝试在工具执行前被拒绝，未观测到实际越界读写或未授权整合；本轮状态文件标准 YAML/重复键及状态引用检查通过。此结论只覆盖实验检查范围，不等于操作系统沙箱或完整产品安全验收。
- 当前判断：对这三类明确目标的小任务，无独立编排的 SDK 路径可行；但该小样本未达到成本删除门，不支持据此直接删除所有规划能力。建议保留程序 Coordinator/Scheduler/Store，模型规划作为按需能力；本轮只交付实验与证据，不更改产品默认行为，不声称 UI/完整产品运行时端到端、长会话/恢复取消或版本 QA 已通过。

### 2026-10-15：真实 SDK 首轮路径已跑通，但对比失效；修复测量后单独重跑

- 用户要求开始真实 SDK 验证，先由 pi 调查现有 `google-antigravity==0.1.22`、正式 executor 与 loopback 认证代理的可复用接口，再冻结协议与预算。被测 worker 必须真实运行 SDK agent loop 和文件工具，不以 direct HTTP JSON 编辑或开发 pi 代理替代。对比仍为 B 仅初始规划与 C 无独立编排模型，两组共享程序认领、消息、文件 SoT、权限及验收；本轮不提前改产品默认行为。
- 核对第二轮原始文件时发现：未认领的部分 Subtask 写成 `lease_path: -`，标准 YAML 语法无效（例：[r1-w2 原始记录](probes/agensh-orchestration-r2/runs/t3_evolving__B__r0/subtasks/r1-w2.md)）。docs 检索报告 `invalid-frontmatter`；上一轮自定义一致性检查未覆盖标准 YAML 解析。因此先前“18/18 SoT 一致”只代表该自定义检查的范围，不代表全部 frontmatter 可被标准解析器接受。代码验收与原始 token 指标不因本项自动失效，但严格的完整 SoT 候选门尚未证实。
- 原始第二轮文件保留不覆盖；本轮须验证所有 frontmatter 的标准 YAML 解析、重复键与当前状态/租约一致性，未认领路径用合法 `null` 或明确的字符串。新实验归属仅 `probes/agensh-orchestration-sdk/`，当前处于隔离准备与接口调查阶段，尚无真实 SDK 对比结果。
- 接口调查已完成：复用正式 executor/认证代理及 SDK 文件工具；openai-compat 配置缺少输出上限/thinking 参数，采用新实验目录内的上游计量中继统一参数，不修改产品代理。调查尚未进行模型校准，不能把源码与旧证据等同本轮结果。
- 已派实施/校准/执行包：校准硬界为 6 次逻辑 SDK turn、24 次上游请求、100,000 reported tokens、5 分钟；正式预算为至多 350 次上游请求、1,500,000 reported tokens、30 分钟。校准后按预算预测优先选择 12 个正式样本（3 类×2 组×2 重复），超出预算则在正式前缩为 6 个，仍不可行就停止报告；样本数与全部输入在正式前冻结。校准与正式统计分开，SDK 内部请求与重试均计量，pi 开发用量另计。
- 首次 SDK 实测已交付：[报告](probes/agensh-orchestration-sdk/REPORT.md)。正式采用 6 个样本，B/C 均 3/3 代码验收通过，有真实 SDK 文件工具、diff 与原生会话证据；正式 158 次上游请求、837,630 reported tokens、约 405 秒。校准实际 7 次逻辑 turn、20 请求、93,658 tokens，**超过预定 6-turn 硬上限 1 次**；原报告称其 soft cap 不准确，偏差保留，不事后软化。
- 对比有效性阻断：B 的 3 份计划均未生效，worker 实际收到与 C 相同的无计划文本。根因包括 schema 未约束计划项字段、从 2,000 字符截断的 emitted 工具事件提取完整计划。此次数据只能证明 SDK 无编排路径可完成这些小任务，不能用于比较有效规划的收益。另有 13 次 staging 内非租约临时校验脚本写入被拒绝整合，不能混同为工具调用前已拦截。
- 只读调查进一步确认：真实 `view_file` 使用 `AbsolutePath` 参数，而路径钩子未识别，导致 `paths=[]` 时仍放行；本次未观测到越界读取，但读防护未被证实。中继也未清除原 `max_completion_tokens=65535`，不能只凭新增 `max_tokens=8192` 声称唯一上限已固定。精确冻结时刻与逐 turn 停止确认仍有记录缺口；不得用手填进度时间补造。原始 SDK 数据保留。
- 已派纠正包，归属仅新目录 `probes/agensh-orchestration-sdk-corrected/`：修复无损结构化结果提取、严格计划 schema 与实际注入证据、真实工具参数解析/未知参数拒绝、单一输出上限、逐 turn 正向停止证据与精确冻结记录。校准上限 2 次逻辑 SDK turn/12 HTTP/60,000 tokens/3 分钟；正式 6 个新样本，上限 51 turn/220 HTTP/1,300,000 tokens/15 分钟；旧新数据分开，产品文件与默认行为不改。纠正包尚无运行结果。

### 2026-10-15：完成第二轮编排角色对比，无独立编排进入产品 SDK 验证候选

- 用户要求继续，启动第二轮受控代码编辑实验：B 仅初始规划与 C 无独立编排模型均获得相同的程序原子认领、同轮消息传递、文件 SoT、权限及验收。每类任务每组独立重复 3 次，3 类共 18 个样本；每样本 2 名 worker、2 轮，编排、认领与编辑调用均计入组内总开销。
- 纠正首轮混淆：显式关闭模型 thinking，输出上限统一为 8,192 tokens，记录 finish_reason 与 reasoning usage；有截断则如实计入失败并保留混淆，不事后补跑。worker 提议认领，由程序检查并更新 Markdown 中的租约；不按 worker 身份写死语义分工。
- 正式请求预算：正常调用至多 153 次、基础设施重试至多 9 次、HTTP 至多 162 次、reported total tokens 至多 600,000、首个正式请求起墙钟至多 25 分钟；pi 开发代理用量另计。协议须在正式运行前记录真实冻结时间与输入哈希。文件归属仅限新目录 `probes/agensh-orchestration-r2/`，第一轮成果与其他代理工作保留。
- 预注册去编排候选门：C 的 9 个样本全部通过、每类质量不低于 B，无额外 SoT/越权问题且无截断；C 的中位样本 tokens 或耗时较 B 改善至少 15%，另一指标中位数不恶化超过 10%。这只是下一轮产品 SDK 验证的候选门，不自动删除角色、不声称统计非劣或产品验收。
- 实测：18 个样本均已运行；B 全部验收通过 8/9（60/63 条目），C 9/9（63/63 条目）。正式调用 153 次、0 重试，provider reported total tokens 合计 179,851，约 195 秒；B/C 各自总 tokens 为 99,451/80,400，组内样本总耗时 106.613s/87.931s。样本 tokens 中位数为 11,114/9,081（C 减少 18.3%），耗时中位数为 11.911s/9.865s（C 减少 17.2%）。这些指标不含 pi 开发代理用量，费用未知。
- 证据：两组共 153 次响应均 `finish_reason=stop`、reasoning tokens 为 0；0 截断、0 认领/编辑冲突、0 越权，18/18 样本 SoT 一致性检查通过。精确冻结时间 `2026-10-15T05:53:15Z`，首个正式请求为 `05:53:56Z`，冻结清单与原始响应保留。入口见 [第二轮实验](probes/agensh-orchestration-r2/README.md)、[协议](probes/agensh-orchestration-r2/PROTOCOL.md)、[报告](probes/agensh-orchestration-r2/REPORT.md)。
- 判定：C 满足全部预注册候选门，列为“独立编排可移除”的产品 SDK 验证候选。B 唯一失败发生在单文件需求变更任务：初始计划把同一文件的不同函数分给不同 worker，与每文件单 writer 规则不兼容，最终漏做 median。这不证明规划普遍有害，也不能把两轮实验间的差异只归因于认领机制（本轮同时改变了输出参数与协作流程）。
- 当前处理：实验已完成并保存，产品默认行为与首版运行契约保持现状。结果只覆盖三类明确目标的小任务、每类每组 3 次重复和有界结构化编辑，不覆盖完整 SDK 工具循环、长会话、恢复取消、模糊需求或真实工程规模；下一步建议在真实产品 SDK 中复核，不自动删除规划能力，不声称统计非劣或版本 QA 通过。

### 2026-10-15：先做编排角色消融实验，产品角色暂不移除

- 用户要求先通过实验比较编排 agent 的价值，再决定是否淘汰。首轮为隔离的受控代码编辑 pilot，比较 A 全程编排、B 仅初始规划、C 无编排模型；三组均保留程序调度、文件 SoT 与验收，2 名 worker、2 轮执行，3 类任务各运行一次，共 9 个样本。协议及结果见 [实验入口](probes/agensh-orchestration/README.md)、[协议](probes/agensh-orchestration/PROTOCOL.md) 与 [报告](probes/agensh-orchestration/REPORT.md)。
- 基准 `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`；正式实验 45 次 DeepSeek 请求、0 次重试，provider reported total tokens 为 106,949。A/B/C 全部验收通过的样本分别为 2/3、3/3、1/3；组内样本总耗时分别为 86.04s、55.45s、38.56s，总 tokens 分别为 48,907、34,589、23,453。以上只计 pilot，不包含 pi 开发/收尾代理用量；费用未知。
- 解释限制：每种条件每类任务只有一个样本；6 次输出被 2,048-token 上限截断。C 没有同轮编辑前的协商/认领往返，且整文件内容不同即拒绝整合，出现 7 次冲突；不是完整 Agensh 自组织实验。结果不能证明中央编排模型不可替代，也不能证明重新规划本身有害。
- 当前处理：不移除产品编排/规划能力、不修改运行契约或默认配置。B 仅作为下一轮优先复测的候选；后续比较需消除输出截断，给无编排组提供程序原子认领/同伴协商，并在真实 SDK 与重复样本上复核。这些是建议，尚未启动下一轮。
- 实验 schema 与 driver 仅用于 probes，不代表产品已支持共享发现或运行中计划修订；局部检查不作为版本 QA 或产品验收。原始实验 worktree 保留，未提交、未发布。
### 2026-10-15：整合 LG-013（Chat/真实看板）与 LG-027（Settings/凭证专项 QA）

- 基点：本整合在独立 worktree `/home/yhvh/code/lightgravity-bot-worktrees/ui-controls`（branch `integrate/ui-controls`，基点 `2ecafdf`，非 root `main`）进行；root `main` 由 Firefox 诊断 writer 只改 `probes/`，LG-016 在其 branch 补 guard，二者本轮均未触碰。
- 整合：按序 `git cherry-pick -x e3a6818` → `2d31831`（LG-013 接入 Task Chat 与真实看板）、`354def4` → `b7a0f7c`（LG-013 收尾置 done）、`fbd8a0e` → `a6d9f3c`（LG-027 QA 报告），三提交均无冲突，保留原作者与消息。
- 保留项核对：Files/Settings/Team/Resources/Runtime、default pin、canonical evidence、自动 verify、ack 幂等均保留；`create_app` 的现有 Resource/Verifier 端口与新加 `responder` 注入共存；`coordinator/dialogue.py` 为新增无工具单只读路径，无默认协调连接/凭证时返回诚实 `unavailable`，不创建 Task/Member、不写控制文件。未接手 LG-016（不改其状态/候选 guard），未领取任务，未 push/deploy，未读 `.env`。
- 文档同步：README/PROJECT/docs/06 记录 013 实施 done（**完整浏览器业务路径仍归 021/022**）、027 设置/凭证专项 pass（**仅设置/凭证 CLI+HTTP + browser 渲染范围**）。**两者均不等同完整浏览器 HTTP 端到端**。
- 精确更正：旧 QA“浏览器全 HTTP/fetch 阻断”已被 root `probes/browser-diagnostics` 推翻——真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，**仅顶层 `Page.navigate` 到 `http://` 在本机 headless 挂起**；原报告按历史保留，只追加更正引用，不复述错误当新事实。
- 调用计量诚实性：027 报告中的“旧上限 5 + 恢复硬上限 4”只是**指令/运行预算**（`model_call_cap=1` 为 harness 设置），产品未暴露调用计数器，无独立计数即记 **未知**，不写成已验证实际硬上界或精确数。
- 验收（整合执行者，非 QA）：`uv run pytest -q` → **410 passed, 1 skipped**（含 LG-013 定向 21 项、LG-027 e2e 设置 9 项；唯一 skip 为需 `LG020_REAL_DEEPSEEK=1` 显式启用的 gated 真实检查）；`uv run mypy` → **Success: no issues found in 86 source files**；`frontend` `npx tsc --noEmit` 通过、`npx vitest run` **75 passed / 11 files**、`npm run build` 成功（90 modules，CSS 30.71 kB / JS 252.03 kB）；任务 frontmatter 以 YAML 解析校验 27 文件结构（`tasks` CLI 本环境不可用，已如实注明）。真实 DeepSeek 调用本轮为 **1 次有界只读直答探针**（`model_calls_cap=1`，证据 `probes/lg013/evidence/lg013-direct-answer-probe.json`）：临时 data 正确配置 `default_coordinator` 连接后，真实模型回答 `"Four."`，且不创建 Task/Run/Member、不写控制文件、workspace 无写入、无秘密泄漏；产品未暴露调用计数器，故不宣称精确总量，不把 unavailable/mock 当真 AI。
- 限制：本轮为整合与文档同步，非 LG-021/022 版本 QA；不宣称完整浏览器 HTTP 端到端或首版完成。仅清理本包签名的临时产物/PID，未杀父/兄弟/root 8123，未改 LG-016。

### 2026-10-16：整合 LG-016 恢复反重放守卫到 main

- 基准：本批从 `9987d4f` 检查点 `b2bd5eb` 合并 `integrate/ui-controls`（`6e23c7c`）；LG-013/LG-027 与无编排改动按原消息保留，docs/09 与 LG-028～041、各 probes 实验记录保留。
- 合并：唯一 owner 在 main 执行 `git merge integrate/ui-controls`，四处内容冲突按加性合并：`dispatcher.py` 的 `DispatchContext` 同时保留 `planning_request` 与 `continuation_mode`/`prior_run`；PROJECT/README/docs06 文档按最新事实合并。graph.py 自动合并无冲突标记，保留只读直答、Resource/Verifier、自动验证、ack Task 作用域幂等、`connection_pin`、canonical evidence 授权、runtime token 与反重放边界。
- 恢复能力诚实性：完整 checkpoint skip 调度尚未实现，不夸大。`recovery_required` 对缺可信复用/未知副作用/配置漂移保守进入，不静默 fresh 重放。

### 2026-10-15：整合 LG-010 独立重验链（QA 判定 pass/done）
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

### 2026-10-17：账户管理版本交付决策

- 默认管理员只在团队空库首次初始化；已有账号、自定义角色和后续改密重启保留。当前 admin 按用户要求一次性设置为指定密码，不保留登录后门。
- Settings 页内 Accounts 管理员管理账号；My Account 所有团队用户可改自己密码，成员不拉取管理员账户列表／Models。用户名不可变、没有账号删除／邀请／注册。
- 启用状态／角色／口令受控写入由同主机 POSIX flock 包围读取、版本检查、末位管理员检查和原子替换，CLI 与服务共用稳定锁。请求时刷新身份与会话版本，失效事件流约 2 秒重校验。
- 首轮独立 QA 原并发丢失更新 FAIL 保留；Codex R1 修复跨进程锁，pi 集成与独立复验。R2 修正既有 E2E 误认侧栏输入框为导航完成的等待条件，保留原 Back 断言；最终新独立 pi PASS。
- 本轮已精确集成／本地部署，无远端推送；全部证据见 probes/accounts-20261017。费用及总用量未知，不把缺失账目计作零。

### 2026-10-17：新增五项问题，先记录再逐项确认

- 登记 LG-117～121：Embedding API 设置入口、Chat 文案精简、Personal 附件及输入框、主线默认 agency-agents 角色库、自动组队与真实测试，详见 [backlog](BACKLOG.md#j-2026-10-17-用户问题记录与逐项确认)。均为计划，未实施。
- 用户明确要求移除重复说明、把 Personal/Team 上移、文件按钮直接选择文件、发送 icon 置输入框右下、输入框向上自增高并去除上方横线。
- Personal 私有附件超出 LG-054 原“仅私聊”范围，需明确服务端附件隔离；删除说明不代表允许私人内容共享。
- LG-037 已有可选向量后端/env 配置证据；不能据此声称 Settings 配置入口或当前运行服务已启用。
- LG-065 仅为独立 Demo 角色包交付；主线整合排除游戏角色及固定招募映射，默认完整角色库与通用招募仍需补齐。
- “真实人物测试”原话保留，真人协作/真实任务含义待轮到该项时确认。本轮未更改源码、服务、凭证或执行真实模型测试。

### 2026-10-17：确认 Embedding API 配置方案（LG-117）

- 用户确认 Settings → Models & Providers 增加独立 Embedding 配置：API 地址、模型名称、可选 API Key、启用开关与测试按钮，与聊天模型分别设置。
- 测试返回实际模型和向量维度，不可用时保留词法搜索。实际端点和认证在实施时核对，凭证沿用受保护机制。
- 本次确认方案，任务仍为 todo，尚未启动实施；继续逐项确认 LG-118～121。

### 2026-10-17：确认 Chat 精简方案（LG-118）

- 用户确认删除 LG-118 列出的 Chat 重复标题、Private、说明文字和空态文案；Personal / Team 移到对话区顶部，下方直接显示消息，导航栏 Chat 入口保留。
- 本次确认方案，任务仍为 todo，尚未启动实施；继续逐项确认 LG-119～121。

### 2026-10-17：确认 Personal 附件与输入框方案（LG-119）

- 用户确认 Personal 上传仅本人私聊可用，Team 上传供团队共享；实施时须由服务端保证可见范围。
- 上传按钮位于输入框内，悬停提示“上传文件”、点击直接打开文件选择器；删除两段底部说明及输入框上方横线，发送采用右下角图标。
- 输入框底部固定，随文字增加向上增高，达到最大高度后内部滚动。
- 本次确认方案，任务仍为 todo，尚未启动实施；继续逐项确认 LG-120～121。

### 2026-10-17：确认完整 agency-agents 默认角色库（LG-120）

- 用户确认完整角色库随产品默认安装，在 Team → Available 可浏览，执行任务时按需招募。
- 固定来源版本，保留许可和署名；升级不覆盖用户修改，角色可执行性按实际能力显示。
- 本次确认方案，任务仍为 todo，尚未启动实施；继续确认 LG-121 自动组队与真实测试。

### 2026-10-17：确认自动组队、解散及多任务队伍（LG-121）

- 用户明确测试一个小型真实任务，验证按目标自动组队、工作完成验证后确认停止并自动解散；保留队伍历史和产物，待人工验收不占执行资源。
- Team 按 Task 展示各任务的独立队伍、成员分工和真实状态。同一角色模板可产生属于不同任务的独立成员。
- 用户可能同时运行多个任务：纳入多任务调度、上下文/工作目录/成员隔离及全局容量配置；真实验收需至少两个任务执行重叠，不能用完全串行排队冒充并发。一个任务完成或取消不得解散另一个任务的队伍。
- 原“真实人物测试”已澄清为真实任务测试；五项需求均已确认，仍为 todo，本轮仅完成记录与范围确认。

### 2026-10-17：补齐多任务 Team 设计与派工门

- 现有设计只含模板/实例和释放基础，缺少多任务页面线框、状态与异常交互；新增 [docs/13](docs/13-chat-and-task-teams.md) 作为已确认需求的详细设计及派工依据，尚未实现。
- 细化 Recruited 按任务分组、Active/History、Available 全库搜索、跨任务导航、自动解散与停止未知、并发容量和私人附件隔离，清理 design.md/docs/05 中相冲突的旧设计语句。
- 新增 LG-122 pi 接口/容量/owner 准备门，LG-117/119/120/121 依赖其契约；LG-118 可独立。命名版本为“Chat 与多任务团队版本”，LG-123 集中独立 pi QA。派工要求引用设计章节、真实接口、文件 owner 与验收场景。
- 具体端点/状态字段映射、生产默认容量仍需 pi 技术调查，不以产品设计冒充技术调查结果；本轮只改文档和排期，未派工、未改代码或运行服务。

### 2026-10-17：用户授权同步派 PI 开工

- 用户要求本批派 PI 开工，覆盖 LG117～123 的实施编排；此前“本轮仅记录”是历史阶段说明，不再阻止既有范围实施。LG118 本包按这次明确 PI 要求执行，其余缺陷仍遵原生子代理修复默认分工。
- 已验证开发 DeepSeek V4 Flash/medium READY，启动独立 worktree 内的 LG122 接口/容量调查与 LG118 Chat 精简，两包已认领。精确 owner/白名单/提示词/基点与 overlay 哈希见 [派工记录](probes/chat-task-teams-20261017/DISPATCH.md)。
- 依赖不跳过：LG117/119/120 待 LG122 契约；LG121 还依赖 LG120；LG123 待整合候选。后续就绪包沿本次授权推进，不重复请求开工确认。
- 当前只用开发凭证运行 pi，未开启产品执行器/调用产品模型、改动真实数据或重启服务，不推送/发布。真实业务验收仍需明确单次测试输入、边界及授权环境。

### 2026-10-18：继续实施并核对上一轮交付

- 用户要求“开始”，继续本批既有授权；LG118 隔离局部交付核对通过（238前端及类型/构建），待集成/版本QA，不改变运行服务。
- LG122 初报告的附件“存储但不供私聊上下文”与用户确认语义不符，且 Released 条件须包含真实停止/cleanup证据，已由 pi 原契约 owner 做R2文档更正，先不解锁后续开发。
- 新增 LG124 串行增量整合包，LG123最终依赖其固定候选。隔离worktree内允许本批精确本地提交形成可追溯依赖产物，主目录既有dirty/服务/数据保持，不推送或发布。

### 2026-10-18：三项新功能已并行进入实现

- LG122R2契约准备已核对完成，LG118四文件由pi精确集成，隔离候选4d60cac（reference773bd2d）在42重点/238全前端、类型/构建检查通过。LG124仅基点阶段完成，整体仍进行中。
- LG117 Embedding设置、LG120全量agency角色库、LG119私聊附件/输入框均已认领并实际启动独立pi进程/会话。角色来源已枚举282个角色文件（固定上游652b269…），尚未宣称功能或版本通过。LG119从4d60cac起步，避免覆盖Chat修复。
- 三包范围/owner/白名单/禁止路径与当前进度见 probes/chat-task-teams-20261017。LG121仍待角色包可追溯交付和集成，LG123待最终固定候选。
- 已准备QA-PLAN：两个小型真实任务及新的测试请求边界24，仅隔离测试环境、开发凭证的进程内引用，不改变当前服务产品凭证/执行策略。此时真实业务测试尚未执行；OCR/ASR/真实embedding调用0，不把计划写成验收事实。

### 2026-10-18：状态核实与接续集成

- 三个开发pi均已结束，隔离交付67b9033（Embedding）、2e94b04（私人附件/输入框）、6700f82（完整282角色库）；已核对报告、实际提交与检查日志，记各自局部交付done、待版本QA。
- 前一轮结束后没有自动启动依赖任务；当前停在串行集成，LG121自动组队/多任务Team尚未开工，真实任务与独立浏览器版本QA尚未执行。此次对话按原实施授权接续LG124阶段2，不把旧in-progress当作持续有人推进。
- 接续pi先精确串行集成三个提交，实际挂载私人附件路由/能力并检验组合语义，然后提供LG121基点；保持主目录dirty/运行服务/真实数据不变。

### 2026-10-18：继续推进自动组队的并行实施

- 用户要求继续；LG124阶段2已将三包提交串行接入至6f29b0d，正在做组合接线与检查，未宣称集成完成。
- LG121拆LG125前端与LG126后端并行，均消费6f29b0d和R2同一接口，拥有独立worktree与不交叉文件owner；不用等待不相关最终app接线才能开发Team UI。真实SDK和浏览器集中验收仍归LG123，LG121局部交付与真实业务验收分列。

### 2026-10-18：阶段2集成通过，新Team前后端并行实施中

- 已核对pi阶段2报告49eca08：Embedding/私人附件/282角色库在隔离应用组合通过，含实际app挂载而非仅手动测试router。257前端、87API、101设置及语义/类型/构建通过；初次collection冲突保留。仍为内部1.17候选，不是完整版本QA。
- LG125/126 pi进程实际运行，基点6f29b0d已含全部功能源代码；共享接线后继49eca08由最终集成owner保留，前后端子包不修改app/health/版本。最终候选必须包含两包并升1.18后才做独立QA，不能基于中间结果宣称自动组队已验收。

### 2026-10-18：README自动组队与Swarm说明同步

- 用户询问README是否包含自动组队/Swarm，核对已有Multi-Agent Orchestration/HITL/Agentic Workflows/RAG/traceability与Swarm专节后，补充Automatic task teams状态表和目录入口。明确完整282角色库/分组UI仅隔离局部交付，通用角色招募/并发释放后端仍实施中，真实SDK/独立版本QA未完成；Swarm仍为探索方向。旧“Dynamic team assembly is implemented”收窄为基础规则招募已实现，避免被理解为本轮完整能力验收。

### 2026-10-18：用户授权提交到Gitea和GitHub

- 用户明确要求两个远端commit/push；沿既有独立源码导出边界、私有仓库各自历史。当前完整版本未QA，先发布49eca08+1077018和最新README的可审阅开发快照到同名development/task-teams-20261018，不把LG126未提交实现纳入、不把开发快照宣称验收完成。
- PI发布包LG127与后端实施并行；使用独立clone/worktree/index、正常非force推送及远端readback，秘密/运行数据/内部研发资料不新增，保留完整开源角色原件与许可。原功能/QA目标继续，不重启现有服务。

### 2026-10-18：Gitea与GitHub开发快照已推送

- 用户授权的LG127完成：同名development/task-teams-20261018，GitHub4c57eea、Gitea2d4003e，正常非force推送和最终refs/浅克隆回读一致；初始提交及后续分发脚本修正历史均保留。
- 发布源6568da9=49eca08+1077018+最新README说明；GitHub独立source-only历史839文件，Gitea保留原内部历史且仅同步allowlist产品路径，完整282角色原件/模板/manifest/许可均在包内。所有共享产品字节一致，秘密/路径/包/链接/构建检查通过，主目录与运行服务保持。
- main/tags/releases/可见性未改，完整版本及真实SDK/浏览器QA仍待完成；后端LG126仍运行，不把发布动作当成版本验收。后续同授权可将完整验收候选更新到该开发分支，保留当前快照记录。

### 2026-10-18：完整候选最终整合与后续远端同步门

- LG126局部交付7771735已核对（14新增、316组合、380相关回归、8角色、159源文件类型检查）；初始失败/早期启动输出已从原pi会话恢复证据，不把局部最终通过写成首次全绿。两子包完成后LG121按CLI正常claim为in-progress，继续等待完整候选整合与真实QA。
- pi final-integration已启动，精确把1077018和7771735串行接入49eca08，保留已验证app接线，完成team/groups/health/版本1.18和必要组合检查后冻结独立QA候选。
- 新增LG128跟进原双远端授权：完整候选通过独立QA后更新同名开发分支，保留LG127初始快照历史，不再重复征求同一提交推送授权。

### 2026-10-18 完整候选冻结并进入独立验收

LG124最终候选f1f071a/tree8c7809e、契约1.18.0已接齐Chat/私人附件/独立Embedding/282角色/自动组队与多任务Team。1282后端、265前端、mypy159及真实ASGI接线通过，首轮/tmp配额导致的失败保留并改TMPDIR重跑。LG121/124按既定拆包门记局部实现交付，真实SDK并行、真实停止自动释放、浏览器与隐私版本门由新的独立pi LG123执行，不以单测代替业务验收。当前root/main与8123/5173/18123保持，双远端LG127仍是先前开发快照；待LG123通过后LG128补齐完整候选。

### 2026-10-18 真实QA首轮观察调查

LG129隔离调查未确认停止释放缺陷：文案任务实际2/2会话及代理已停止，保留session refs为契约允许的历史；HTML样本正文在首2000字节证据片段之外，复核诚实unavailable/waiting_user，不能计作交付。13局部回归通过，无代码或模型调用；保留LG123真实失败样本，最终业务验收仍未通过。

### 2026-10-18 LG130有界复核证据覆盖修复

基于LG129可复现事实，PM将固定前2000字节漏掉6.4KB小HTML正文的行为作为当前复核能力的有界缺陷修复处理，而非通过调整真实测试让重要事实挤入前缀。原生Codex LG130在独立worktree修复小产物完整覆盖/大产物诚实截断，保留单文件和总体上下文上界、不可信包装及路径/哈希/权限边界；不新增reviewer工具/联网/自动通过/公开schema。原始失败样本保留，pi串行集成后独立复验，QA整批24次调用账本不重置；此为首轮实际修复。

### 2026-10-18 首轮复核修复已整合

LG130/131局部交付：cd4e258/tree96eb623，契约1.18.0，只改review.py和对应回归；86相关/27API安全/44功能保全/mypy159/启动导入通过，前端和docs同树复用。旧候选f1f071a独立QA仍在执行，其失败记录/请求账本不重置；新候选尚待独立真实复验与最后双远端同步。

### 2026-10-18 独立QA尾段与排队取消观察

首轮真实请求已达24止损线，仍保持保护不再调用；私聊/普通问答真实探针失败原因待独立报告，无模型机制回归与断线恢复继续。LG132新的独立pi已在cd4e258准备复验，原QA结束/数据交接前不得调用或修改其环境。原第三排队Task取消后queue等待残留是否为产品缺陷由原生Codex LG133在另一worktree调查，不把浏览器观察断言失败先当实际缺陷；真实从未启动与未知仍在运行必须分开，不伪造清理状态。

### 2026-10-18 首轮独立QA失败包与派发否定语义修复

原独立报告总体FAILED：D1未执行排队Task取消后队列/Team历史错误；D2有界证据覆盖缺口；真实普通问答及私聊上下文探针尚缺证据，24请求已全部持久记录。真实A/B执行重叠、A2完成B2继续、双产物和Board操作验收、UI/隐私/Embedding等已获证据，不能掩盖未通过项。报告将`不要创建任务`误派发归为harness措辞，PM依据明确否定新建Task和用户派发不跑偏要求，另记LG134现有路由缺陷：保留原失败句并修复确定性分类，不通过删否定语句规避。LG133修取消/队列及声明后取消竞态，LG134独占classification.py并行修语义；均从cd4e258隔离，不触碰同一源码。

LG132首个新PI准备进程因Node写入配额errno122在39s退出，未交接/未模型调用/未出独立 verdict；原日志保留。下轮PI进程本身及fixture均指定主文件系统TMPDIR，不调整全局环境。完成全部缺陷集成后重启独立复验；24上界目前仍保持，需新调用时先依据实际缺口和调用计划重排止损边界，不重置账本或盲重试。

### 2026-10-18 修复复验止损重排（PM测试边界，不是用户新增功能）

首轮严格24请求止损并FAILED封存后，PM按用户继续完成原目标授权固定新阶段最多16额外请求/累计40，以补原始否定措辞问答、Personal真实文本+二进制诚实处理、原6422B模板实际SDK产物/复核/双Task重叠/队列取消。原24数字为PM测试止损并非用户指定，新的上界在新候选/旧进程安全交接后才实施；前24行账本前缀校验保留，转发前持久预留，guard只改隔离测试进程，生产无限额策略/服务不变。每项失败/到40必须停止报告，不继续自动加额。详见QA-RETEST-R2-CALL-PLAN.md，真实请求/费用未知保持。

### 2026-10-18 R2尾段新发现：先停止晋级并重拆LG136

R2真实Personal回复含正确文本码且无二进制哨兵，但程序前缀说unsupported/bin未读、模型正文却说没有无法读取附件。原生LG136实际无网络ModelDialogue-turn输入捕获确认确定性缺口：成功文本进入模型，unsupported文件名/状态未进入，仅在答复后追加应用通知。此为既有上下文信息缺口，不是泛化模型幻觉问题。按修复轮次治理先停版本PASS/发布晋级，记录新证据并重拆为单一attachments/service.py可读性事实修复及直接测试；保持总12000上下文字符/3文件/64KiB上界、owner/不可信包装/不读二进制，无新功能/schema/前端。LG132旧候选原始输出与其他真实Task证据保持，不能因旧测试前缀匹配通过而隐藏正文矛盾。

新修复待pi串行集成后由独立PI只补该变更及实际私聊探针（原phase2的第二个允许请求），其余实际SDK并行/产物/取消路径仅在字节未变且证据充分时复用。仍在已固定16额外/累计40请求以内，不新增上限、不盲重试或重复不变任务。此重排在用户继续原功能授权内，未扩大媒体读取或新增外部动作。

### 2026-10-18 R2独立通过阶段与最终私聊事实门

独立qa-final-r2报告对beb0395判定阶段PASSED：真实原负向问句答4且无新Task、6.4KB模板经实际SDK工具/独立复核交付、B文案111中文字、实际A/B执行重叠且A结束B继续、新第三Task真实排队取消/History/无Run、Board双验收、角色/T9/E6/隐私/UI均有证据。该报告把私聊正文矛盾列模型质量观察，原文保留；原生LG136另用真实turn输入捕获证明程序遗漏unsupported事实，已有有界补齐提交9c2c0fe，44相关/mypy159通过。主代理不将R2阶段PASS推广到未复验的新候选，LG137集成后只补该变更。

R2结束计数35/40（本阶段11新请求），前24行哈希保持；后端/浏览器/代理已停。新最终独立探针复用同物理计数文件，35前缀/24前缀哈希交接保留，只允许1新私聊请求（phase2总第2次）；测试进程可收紧guard36以阻止额外自动重试，原阶段累计40最大不提高。新回复检查模型正文与程序未读事实一致，不能仅匹配应用前缀；其余未变Task/role/review/UI路径按hash复用充分真实证据。

### 2026-10-18：完整里程碑独立QA通过，准备最终双远端同步

最终独立PI报告对94571a0/tree ea0dc663整体PASSED：新增真实私聊验证码及二进制未读事实一致，10+8测试/mypy159/实际浏览器通过；R2真实双Task/复核/停止释放/排队取消/Board及其余UI按精确未变路径独立审核复用。累计36/40请求，原24/35前缀保留，测试服务/浏览器/代理已停。原失败与模型虚构文件链接等限制保留。README同步实际能力与Swarm探索边界。LG132/LG123按事实完成，用户最终验收及LG128提交推送、部署分别记录；现有服务未更新。

### 2026-10-18：完整验收源码已提交双远端

LG128完成，GitHub634aa18/Gitea2cf0d42，均为development/task-teams-20261018正常fast-forward且新克隆回读确认。产品94571a0+文档源c65cd9c，567角色及共享产品字节一致，公开README含自动组队、真实并发释放与Swarm探索界限。QA/分发/推送记录分别保留；main、标签、release和在线服务不改。见publish-LG128-DELIVERY；无遗留本轮实施/QA/推送任务，ASR历史质量门LG041另计。

### 2026-10-18：用户新增部署并提交授权（LG138）

用户明确“部署并提交”，授权已验收1.18源码集成根main、部署现有8123并正常同步双远端main/开发分支；安装预览release与18123保持。pi独占集成/部署/浏览器/提交，主代理PM维护状态；保留根既有dirty、账号/资料/任务/凭据/计数，现有no-executor和无限计数策略不因部署改变，无新增真实模型调用。按实际部署状态更新公开README，标签/release不变，出现故障先恢复服务。

### 2026-10-18：LG138部署并提交完成

pi已将验收产品94571a0以b29cd7b合入根main，既有12份dirty原字节保留；8123实际1.18.0，19无模型局部测试及8123/5173×桌面/手机4组真实浏览器通过，282角色成功补齐、既有账号/资源/计数保持。首次tmpfs配额问题迁移无活跃进程的旧pytest临时缓存后恢复，失败/回滚材料保留。两个远端main及开发分支均正常快进并回读确认：GitHub2f9f927/Gitea164990f。线上no-executor/无限计数策略与18123原服务保持；标签/release不变，不泛化QA范围。详见[probes/chat-task-teams-20261017/lg138/deploy-LG138-DELIVERY.md](probes/chat-task-teams-20261017/lg138/deploy-LG138-DELIVERY.md)。

### 2026-10-18：资料上传与自动索引体验设计及排期

用户要求将前端接入方案落入设计并排期。已记录 [docs/14](docs/14-material-intake-and-auto-index.md)，新增命名里程碑 LG-139 及 LG-140～145：契约核实 → 后端/Chat与Files/搜索分包 → 串行集成 → 独立版本 QA。P1，按依赖阶段排序，不承诺未经约定的日历日期。本轮只改项目文档和任务，未派工或修改产品/运行服务。

确认范围为 Chat 一次提交、后端保存原件/资料 frontmatter 并按能力独立建立词法/已启用的媒体向量、真实分项回执、Files 追溯/重处理、顶部 Keyword/Semantic 和来源回链。团队 Personal 保持私有附件边界，暂缓私有知识库及媒体理解，LG-041 ASR 质量门保持；保存配置不触发旧资料全库模型调用。现有自动触发缺口由 LG-140 核实，不把配置可用或历史 QA 当当前端到端已实现。

开发/集成/独立 QA 经 pi，缺陷经原生 Codex 子代理；主代理仅 PM。真实测试服务、样本和模型/媒体预算在实施时预先固定，不授权使用真实产品密钥；部署/推送另记。

### 2026-10-18：用户授权实施资料自动索引版本

用户明确“实施”，授权推进 LG-139～145 的已确认设计。LG-140 已由 pi 在隔离 worktree 启动技术调查和契约准备，开发使用 env DeepSeek V4 Flash / medium；模型凭证仅子进程内存映射，不进入提示词/文档/日志。主代理 PM、pi 功能开发/集成/独立浏览器 QA、Codex 子代理修复分工保持。先冻结接口与文件 owner 后并行开发，不改现有运行服务，不推送/部署。本次授权覆盖必要局部构建/测试及隔离候选准备，真实媒体测试在明确隔离服务和固定预算后进行，不擅用真实产品密钥。

派工证据：[probes/material-intake-20261018/DISPATCH.md](probes/material-intake-20261018/DISPATCH.md)。

### 2026-10-18：资料版本首轮QA与修复

隔离1.19候选已完成后端/Chat/Files/搜索，首轮独立QA真实PNG与WAV主线通过，但判定整体FAILED：设置传播、旧GET重建授权、失败提示、单来源重建保全及纯附件发送共5项缺陷。保留[原报告](probes/material-intake-20261018/lg145/REPORT.md)。LG148～154原生修复与pi串行集成后再由新独立pi复验；运行服务和生产数据仍保持1.18不动。持久推理账本固定4OCR/20embedding/15秒音频，已用3/14/11.874558，不重置，不重复完整音频调用。

### 2026-10-18：资料自动索引候选独立验收通过

LG145-R2全新独立pi对c3796ab/tree1cd44bf给出PASS，5项首轮缺陷全部关闭。[独立报告](probes/material-intake-20261018/lg145-r2/REPORT.md)包含327后端+1skip/64前端、149项实时机制与交互检查、22截图；真实新PNG主线通过，首轮真实合成中文音频证据按边界复用，ASR仍不可用。累计账本4OCR/17embedding/11.874558秒，原34行前缀不变。原FAILED与重型检查缺口保留。

本地1.19候选在integrate/lg156-intake-final-20261018，用户最终验收另计；本轮不合入运行中的根main、不推送或部署，root/8123继续1.18与既有数据。旧缓存缺少服务/模型身份须显式管理员重建，保存与搜索不隐式重建。

### 2026-10-18：192.168.8.12端口调查澄清

用户指出CosyVoice部署，LG157由pi完成全TCP扫描与只读服务识别，发现10开放端口。7860确认为CosyVoice3 TTS/Lazy Gateway，页面包含参考音频的内部ASR自动识别提示，公开网关文档未给出独立ASR接口；9996尚未识别。此前LG039只测11434，不能推断整台主机无ASR；项目未接入转写与服务可能含内部ASR是不同事实。详见[端口调查](probes/host-192-168-8-12-20261018/REPORT.md)。本轮0推理调用、无远端修改，LG041质量门与产品接线不变。

### 2026-10-18：EmbeddingGemma 2 Reader 转写路径澄清

用户指出ASR原计划为EmbeddingGemma 2路线。公开eg2-transcribe已描述冻结音频编码器逐帧特征+训练Reader/CTC输出英文文字；因此LG039标准/v1/audio/transcriptions在embeddings模式返回无logits，只能否定当次接口用法，不能否定EG2+Reader可行性。项目记录为Reader未接入/未验证；后期虽取得真人音频，但未跑Reader链路，不能把其状态写作Reader质量失败或模型本身不能ASR。当前产品音频向量可用、Reader转写尚未接通，适配/样本真值/质量仍需分别验证；中文不能由英文Reader指标推定。此澄清不变更LG041状态、不安装模型、不新增推理调用。参考：https://github.com/john-rocky/eg2-transcribe 与docs/09 §参考。

### 2026-10-18：授权TTS英文Reader转写并接UI

用户明确“使用tts生成测试，先完成英文，然后接通到ui”。新增LG158英文转写里程碑，基于c3796ab；英文合成样本功能门独立于LG041中文真人质量门。允许必要本地隔离Reader/公开模型准备及现有CosyVoice TTS调用，先真实原型再后端/UI并行、pi集成、独立浏览器QA；不改远端运行服务与生产数据、不推送部署。预算为本里程碑新独立累积账本，旧账本不重置；固定上限/质量口径见[派工](probes/english-asr-20261018/DISPATCH.md)。设计见[docs15](docs/15-english-asr-and-ui.md)。

### 2026-10-18：英文TTS原型首轮结果与固定复测

官方英文对照EG2+Reader WER约4.17%，三段固定eSpeak合成样本平均24.735%且关键信息有丢失，未通过20%功能门；CosyVoice文档请求500保留。PM明确安排同3文本/同判据/同Reader的自然英文神经TTS复测，不混选最好样本、不冒充真人质量。调用额度按[BUDGET-REVISION-1](probes/english-asr-20261018/BUDGET-REVISION-1.md)显式重排并续同账本，保留全部旧消耗与11次迟记审计，不自动放宽质量门或提前接UI宣称完成。

### 2026-10-18：英文Reader实施就绪（保留精确匹配限制）

同3固定文本的Piper自然英文TTS复测平均WER3.858%，数字日期关键事实全部保留；逐字关键短语12/13，scanned→scan使原strict gate仍false，原记录不改。PM接受该词形误差为WER容差内非阻塞已知限制，推进后端/UI，非独立QA或用户最终验收。详见[就绪决定](probes/english-asr-20261018/IMPLEMENTATION-READINESS.md)。配置可管理性与english_asr处理可用性分开判断，default-off不能阻止管理员配置；旧后端无设置view时不显示新表单。

### 2026-10-18 英文ASR独立质量门失败与修复

LG163真实新留出样本H1/H2 WER分别8%/21.739%，平均14.869%，关键专名3项丢失，原质量门失败不改阈值或真值。上传→真实EG2 Reader→持久正文/回执/检索与停用后历史读取已有通过证据，完整首轮QA仍在运行。按agent.md原生Codex执行LG166通用解码缺陷调查/修复，最多2次已授权账本Reader诊断、0新TTS，不与QA争用模型。不能硬编码留出文本或以PM豁免冒充质量通过；若模型限制则交付事实及后续方案。LG164文案修复已交付待LG165串行集成；LG165等待完整QA与LG166交付，LG163独立复验后才判断里程碑。生产1.18未变，无推送部署。

### 2026-10-18 优先直接复用现有开源ASR

用户指出已有开源ASR可直接复用。沿用此指导：优先完整复用许可允许的上游推理路径，不重复造解码算法。已核实john-rocky/eg2-transcribe公开README：Apache-2.0，Reader v2固定200k英语整词、greedy CTC且无语言模型；当前已采用其公开Reader权重。LG166核对本地适配与上游差异、是否遗漏配套步骤；需要原版对照则使用相同失败音频和累计账本，不换真值/挑成功片段。上游性能数字不能替代本项目实测，直接复用也不能宣称解决固定词表外实体。来源：https://github.com/john-rocky/eg2-transcribe 。

### 2026-10-18 原版对照完成、保留质量阻塞

LG167实际原版完整float32 H2推理成功，逐字复现当前机器正文：WER21.739%、关键实体3/5；直接复制同一开源实现不是此例的质量修复。H1原版因子进程分配保护未运行forward，不能概括所有音频等价。两个前置脚本失败与H1加载失败均保守计入累计账本，Reader30/36、TTS9/10、embedding7/20、OCR0、0open；预算硬上限未扩大，原失败记录/旧资料账本不变。静态已证明fixed200k整词词表没有eastside；不把任意拼词/答案注入当修复。LG165集成文案及PCM32通用解码修复并同步质量状态，最终独立针对性复验计划0模型。所有功能通过也不能替代原注册质量FAILED；下一质量方向应单独验证开放词表方案，不继续以同一固定词表无界试错。无部署推送。


2026-10-18：英文本轮最终状态：LG163-R2独立复验完成，46/46浏览器、PCM32与31秒前模型拒绝通过，0新推理；整体verdictFAILED，候选2fbff57/tree5be57d3。仅质量目标阻塞，LG163退回todo/blocked_by、父158保留todo/blocked_by，不把功能完成写成版本PASS。所有自有测试服务/Chrome及pi执行进程退出。未推送部署，根main/线上1.18不变；用户所指其他开源项目待澄清，后续质量提升需单独验证开放词表路线。

### 2026-10-18 用户授权更新线上UI

用户问UI是否部署，获知未部署后明确指令“更新”。本轮授权部署2fbff57功能/UI候选到现有8123与5173使用的源码/静态构建，承接1.19摄取；不推送远端、不发布release。英文ASR维持默认关闭、不配置模型、不调用真实模型，不覆盖原质量FAILED或将LG163/158写done。按LG138已有部署方式由pi串行完成备份、产品路径集成、构建、受支持重启与实际浏览器冒烟，保留现有数据/账号/配置/凭证引用/计数、no-executor、team模式、无限生成计数及18123演示服务，root全部dirty PM文档保持。历史“不部署”记录由本次明确授权前瞻性覆盖。


2026-10-18当前部署：LG168部署完成：用户“更新”的明确授权已落实，main1ab4d7b（精确产品来源2fbff57）、8123 PID495846与5173代理均1.20，ASR关闭/未配置；18123与5173原PID保留。73/73公共桌面/390px浏览器冒烟、46相关无模型测试+2skip/typecheck/build通过。账号/资源/持久数据hash保持，仅runtime PID/token记录更新，旧构建/不公开的备份与回滚路径可用；执行者核对所有原dirty文件未改变，PM随后更新文档。认证后生产页面未登录验证（同源隔离46项证据复用），5173既有favicon404保留。0产品模型/索引重建，未推送/发布。ASR识别质量FAILED、LG163/158阻塞不变，不能把部署成功改写为质量验收。执行者exit0、临时浏览器清理，生产服务保持正常。

### 2026-10-18 用户明确开启Demo ASR并添加品牌/默认登录说明

用户明确“开启ASR，现在只是demo”，覆盖LG168的off运行配置决策；允许准备必要CPU依赖/稳定本地模型、配置并实际启用、重启与demo转写冒烟，不以原质量失败阻止本次demo使用，也不把原质量FAILED改写为通过。用户要求复用pitch/lightgravity_bot_logo_showcase.html的现有logo到登录页及登录后主界面品牌区，登录说明改为默认admin/admin123并提醒立即改密；采用明确中文文案，不更改/重置实际密码。范围包含部署到现有8123/5173，保留账号/业务数据/no-executor/team/计数与18123，不推送远端。拆分LG169里程碑、170前端/171运行时配置并行、172独立QA、173部署；同一既有English账本剩余额度内明确验证分配见demo-brand-asr/DISPATCH，不重置原失败或扩大硬限。


### 2026-10-18 Demo核心优先与ASR冻结（用户最新指令）

用户明确冻结ASR功能，优先最快完成Chat/Tasks改造以开始demo视频。关键路径LG202→LG203/204/205→LG206→LG207；LG219认证作为集成前置与202并行，LG221选材缺陷并行修复。性能208/209与会话持久210后排，不再阻挡核心。ASR未完成的实施、联调、QA和部署不再派发；既有候选/质量失败保留。派工与证据见[demo核心派工](probes/demo-tasks-20261018/DISPATCH.md)。


### 2026-10-18 Demo核心改造技术交付与视频开工

LG201核心里程碑技术交付：Tasks取代Chat主页面/Files，General与真实Task工作区、唯一右侧Bot Chat、New task、正文选材/chip、Team历史及统一401处理已组成隔离候选8d869fff（1.21.0）。345前端与98相关后端、类型/构建通过；独立LG207为PASS_WITH_LIMITATIONS，修正主浏览器28/28、针对误断言的R2 6/6与空实例2/2通过。无确认产品缺陷；首轮验收脚本被覆盖的历史证据限制、单用户横幅仅单元、短暂旧资料行及无真实执行等见[独立QA](probes/demo-tasks-20261018/lg207/QA.md)。未合根/部署/推送，8123仍1.20；用户最终验收待定。LG232已开始采集约20秒新版核心操作素材用于demo剪辑，不把本项写成完整新版两分钟成片。ASR继续冻结。

LG232核心操作素材已交付：[20秒1080p/30fps MP4](probes/demo-tasks-20261018/video-core/core-workspace-20s.mp4)，全片解码/元数据验证通过；真实浏览器操作与demo数据标记，无SDK成功声明，非完整新版两分钟成片。8123原服务与旧影片保持，ASR冻结。


### 2026-10-18 用户选择Google原生音频转写

本轮demo改走Google Gemini原生音频API：音频原件→原生API→机器转写正文→已有索引与Chat/Tasks回执。复用根.env的genai_api仅作进程内测试凭据引用，不写入提示/日志/源码；开发pi仍DeepSeek。旧EG2/Reader质量FAILED与远端部署未完成记录保留；仅启用Google新路径实施，旧本机编码/远端帧服务/Reader工作继续冻结。不创建Cloud资源、不改变聊天和向量默认连接，不自动部署/推送。命名里程碑LG234，子项见probes/google-native-asr-20261018/TASKS.md；先真实两段旧音频与契约，再后端/UI并行、pi集成与独立真实浏览器QA。


### 2026-10-18 Google原生转写候选技术交付

LG234及子项235–239技术交付完成，固定候选`ecda49f692097b07d6f574652f9ed72b6387919a`、契约1.22.0；包含Chat/Tasks核心改造及Google原生音频转写。集成检查123后端、35资料、353前端及类型/构建通过；轻量环境mypy172文件通过，另一次根环境mypy超时记录保留。独立pi QA为 **PASS_WITH_LIMITATIONS**：真实UI上传音频调用Google一次HTTP200、6.082秒，正文持久化、关键词检索/回链、Chat回执/Tasks预览、正式/机器文本分离、关闭后历史、权限及1440/1024/390布局通过；无需Torch/Reader。调用前后本机RSS约64→70MiB，不代表Cloud Run实测。仅有限合成音频验证，H2字面thought前缀及人名误识别保留，旧Reader质量FAILED不变。候选未合根/部署/推送，8123仍1.20；独立测试服务已停止，用户最终验收待定。证据见[独立QA](probes/google-native-asr-20261018/lg239/QA.md)与[集成交付](probes/google-native-asr-20261018/lg238/DELIVERY.md)。
