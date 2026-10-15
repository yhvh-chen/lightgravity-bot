---
title: "LightGravity Bot 项目手册"
doc_type: handbook
category: project
updated: "2026-10-15"
---

# LightGravity Bot 项目手册

> 更新：2026-10-16。阶段：LG-001 契约已冻结（docs/08 当前 1.7.0：1.1.0 将首版真实后端定为 DeepSeek，1.2.0 登记 LG-008 加性控制字段，1.3.0 登记 LG-009 验收字段/端点与全局对话，1.3.1 将 LG-014 文件上传/下载标为已实现并澄清证据引用语义，1.4.0 登记 LG-015 受控资源写入/Team 端点与 Task 消息 `resource_proposal` 字段，1.5.0 登记 LG-020 的 `connection_pin` 加性字段与 canonical evidence 预览/下载端点，1.6.0 由单一 owner 串行加性冻结 LG-028 去中心化协作与 LG-033 资料摄取/检索两线接口——均**仅冻结接口、尚未实现**，去中心化默认关闭；1.7.0 为 LG-017 返修 R1 的加性独立复核者设置角色/字段、Task 返修账本与 review/rework 事件 payload，明确程序机器门不等于独立复核、无可用 reviewer ⇒ `unavailable` 阻止 accept），LG-002 工程骨架可运行，LG-003 SDK 探针完成（核心能力经真实 DeepSeek 实测通过；Gemini/Vertex 未验收，`search_web` 不可用），LG-004 存储层、LG-005 角色/SDK 资源配置编译（已将 `google-antigravity==0.1.22` 锁定为产品依赖）、LG-006 正式 executor + 产品侧 loopback 认证代理（真实 DeepSeek 验证：文件/diff、结构化结果、用量、预算、会话恢复、确认取消；真实调用 12，进程无残留）、LG-007 消息路由与 Task 队列、LG-008 自动组队与依赖调度、LG-009 产物验证与人工验收、LG-011 前端壳层、LG-012 查询 API 与持久事件订阅、LG-025 模型设置与凭证后端、LG-026 Settings 模型接入页面、LG-014 Files 上传/下载与任务证据预览、LG-015 Team/Resources 管理视图与受控资源写入、LG-020 本地启动/停止与一体分发入口均已完成并整合到 `main`；其中 **LG-010 最小真实开发闭环已通过独立版本 QA（pass/done）**，其余 16 项均**待版本 QA**。LG-013 实施已按真实 API 接线完成并置 `done`（Chat/Board 接入真实历史与 phase，新增 `coordinator/dialogue.py` 无工具直答，未配置默认协调连接/凭证时诚实 `unavailable`，经 `create_app(responder=...)` 注入且保留现有 Resource/Verifier 端口），但**完整浏览器 HTTP 业务路径仍归 LG-021/022**，不等于完整浏览器 HTTP 端到端；LG-027 已就设置/凭证生命周期完成独立专项版本 QA **pass**，其范围限于设置/凭证的 CLI/HTTP 与浏览器渲染，**不等于完整浏览器 HTTP 端到端**，且真实调用计数产品未暴露（报告中的旧上限 5 + 恢复硬上限 4 仅为指令/运行预算，不视为已验证实际调用次数或精确上界）。LG-016 恢复能力已在独立 worktree 完成（暂停/取消确认、中断恢复、跨 Run 原生会话续接、稳定 reuse identity 与显式 `recovery_required` 反重放守卫），本轮已整合到 `main`，但完整 checkpoint skip 调度尚未实现，不夸大恢复能力。主前端构建现已挂载 Settings、Files、Team 与 Resources 视图，分别接线 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*` 与 `/api/v1/resources/*`；Files 上传复用 LG-026 运行时 token helper 注入 `X-LG-Token`，无 token 时上传如实返回 `unauthorized`；Team/Resources 受控修改经 Task 对话 `resource_proposal` 提议（sensitive 授权、`message_id` 幂等、`expected_revision` 版本检查，结果写回同一 Task 对话，不创建 Run/不等 worker、不热替换活跃 Member 配置）。LG-020 提供 `lightgravity start/stop/status/init`、默认 loopback、token 内存握手与 `index.html` 注入、Host/Origin 守卫、敏感写默认拒绝、缺认证可读历史/设置；首启幂等种子 `lg-default-worker`（有界文件工具 `view-file`/`create-file`/`edit-file`，无 `run-command`/web 无边界工具），Settings-only 建连接/存凭证/静态测试/设默认后新 Task 可达 executor，Run/Member 固定非秘密 `connection_pin`；canonical evidence 产物经 Task 产物 API（`GET /tasks/{id}/artifacts`、`.../artifacts/content`、`.../artifacts/download`）由 Task/Run evidence resolver 授权预览/下载，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符。敏感写仍由 `LocalAccessPolicy` 默认拒绝。旧 QA“浏览器全 HTTP/fetch 阻断”结论已被 root `probes/browser-diagnostics` 诊断推翻并精确更正：真实 loopback HTTP 的 `fetch`/SSE 从 `file://`/`about:blank` shell 可用，**仅顶层 `Page.navigate` 到 `http://` 在本机 headless Chrome 挂起**；原报告作为历史保留（不复述错误当新事实）。不宣称全部页面可用。首版唯一真实执行路径为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek。集成后 `create_app` 已装配 Store/Coordinator/VerificationService 并挂载 `/api/v1` 路由；accept/reject 合并进 API actions，只读 `GET /tasks/{id}/acceptance` 独立挂载，新增单例全局对话 `GET/POST /api/v1/conversations/global/messages`；默认执行器仍是诚实的 `UnavailableExecutor`（未伪装可执行）。真实 SDK 端到端、浏览器验收分别留 LG-010、LG-021/022；LG-010 最小真实开发闭环已经独立版本 QA 复核 **pass/done**（`probes/lg010/reports/lg010-qa-r2-after-refix.md`）：首轮两项阻断（executor 绝对 `diff_ref` 被机器检查误判、交付完成后未自动触发验证）已返修，第 2 轮复验发现的重复 ack(`target_run_id`) 非幂等问题已按 Task 作用域幂等键返修并经独立复验确认消除，`status: done`、`blocked_by` 已移除。**该 QA 只覆盖契约 1.3.1 core 的最小后端闭环（真模型证据基点 `ffe7a63`，真实调用累计 12/14），并非 1.5 全功能 QA**：LG-015/LG-020 的新资源/启动功能仍未验收，分别留 LG-027 与 LG-021/LG-022。原 27 项首版任务及新增 14 项扩展任务（LG-028～041，去中心化与资料/Embedding 两线，均 `todo`）见 BACKLOG.md；人员、预算、日历日期与部署目标未确定。代码仓库已于 2026-10-14 初始化 Git 并推送 `main` 到内部 Gitea。

## 目标

做一个以用户文件为事实源的**个人 AI 工作助手**：用户通过 Chat 交付资料和提出目标，系统整理、查找资料，并按需执行任务、验证和交付，在用户掌握的文件中保存过程与可复核的成果。

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
