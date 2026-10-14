---
title: "Antigravity SDK 核心能力审计与 frontmatter 映射"
doc_type: audit
category: sdk
updated: "2026-10-14"
---

# Antigravity SDK 核心能力审计与 frontmatter 映射

> 核对日期：2026-10-14。源码快照：`91dc5f84565bb505577ac9524f107f453a6e8d1f`。依据源码与官方示例，未安装 runtime、未执行真实模型调用。本文补充 docs/01 和 docs/02，不代表所有功能均为首版交付。

## 1. 结论

前版覆盖了 Agent、Connections、Conversation、Hooks、MCP、Tools、Triggers 七类入口，但没有完整展开模型配置、结构化输出、预算、重试、压缩、多模态、流式观察、取消、子 agent 与 workflow 等能力。现补充配置映射和首版取舍。

这些能力可以用 Markdown＋frontmatter 描述、关联和渲染，但不能全部变成纯 YAML 执行。frontmatter 表达声明式参数和注册引用，Python adapter 构建 SDK 对象；会话、流、进程、回调函数和执行结果仍由实际运行时承接。

依据：[官方示例目录](https://github.com/google-antigravity/antigravity-sdk-python/tree/91dc5f84565bb505577ac9524f107f453a6e8d1f/examples/getting_started)、[AgentConfig](https://github.com/google-antigravity/antigravity-sdk-python/blob/91dc5f84565bb505577ac9524f107f453a6e8d1f/google/antigravity/connections/connection.py)、[SDK 类型](https://github.com/google-antigravity/antigravity-sdk-python/blob/91dc5f84565bb505577ac9524f107f453a6e8d1f/google/antigravity/types.py)。这是核心表面审计，不是每一个内部 API 的穷尽审计。

## 2. 覆盖矩阵

“已有”表示前版设计已有明确位置；“补充”表示本次明确映射。全部运行行为仍待固定安装版本的探针验证。

| 核心能力 | 前版覆盖 | frontmatter 配置归属 | 运行/渲染方式 | 首版范围 |
|---|---|---|---|---|
| Agent 生命周期与指令 | 已有 | Agent：persona、指令模式、引用 | 程序创建/关闭实例，正文提供指令 | 接入 |
| Connections 与认证 | 已有 | Connection：adapter、模型目标、认证引用、区域 | 凭证由环境解析，展示健康状态 | 首个 Gemini 后端 |
| 本地模型／其他端点 | 未展开 | Connection：后端专属配置 | 每种后端单独验证兼容性 | 暂缓，不承诺任意模型 |
| 模型推理与服务档位 | 补充 | Connection：thinking、service tier、输出上限 | 映射 ModelTarget/endpoint options，显示有效配置 | 基本模型选择，其余可选 |
| Conversation 保存与恢复 | 已有 | Conversation：continuation、存储策略 | 原生 session 存储，显示可恢复/不可恢复 | 实测后支持 |
| Skills 与依赖 | 已有，补充约束 | Agent：skill source、skill refs | 路径或 InlineSkill，保存版本与依赖 | 文件技能优先 |
| 文件／命令／网页工具 | 已有 | Tools＋Agent capabilities | 真正内置工具调用，记录结果 | 接入 |
| 自定义工具与 ToolContext | 已有，补充上下文 | Tool：registered handler、输入 schema | 程序绑定 callable/ToolContext | 少量任务工具 |
| MCP 服务与输出大小 | 已有，补充限制 | MCP＋capabilities | 建立实际 stdio/HTTP 连接，长输出引用文件 | 按任务需要启用 |
| 工具可见性与调用策略 | 已有，补充区别 | Agent capabilities＋Hooks/policies | 隐藏工具与运行时拒绝分开 | 接入 |
| 人机问答与批准 | 已有，补充 SDK 桥接 | Hooks：question/approval handler；Agent behavior | 转成 Task Chat 待决项，回复回传会话 | 接入 |
| 结构化输出 | 补充 | Agent：response_schema_ref | 注册 Pydantic/JSON Schema，程序验证结果 | Planner、outcome 优先 |
| session 预算与停止原因 | 泛化，现补充 | Agent：budget_config | 调用/令牌上限，展示 usage 与 stop reason | 接入 |
| API/模型输出重试 | 未展开 | Agent：retry_config | SDK 有限重试，记录实际行为 | 接入 |
| 上下文压缩 | 未展开 | Conversation：compaction_config | SDK 压缩历史，用户原始消息保留 | 可选，验证后启用 |
| 工具输出截断/落盘 | 未展开 | Agent capabilities | 截断摘要与原始文件链接 | 接入相关设置 |
| 多模态附件与图像生成 | 未展开 | Task：attachment refs；Agent：工具选择 | 附件转换 SDK Content，产物按媒体类型预览 | 文档/图片输入；生成暂缓 |
| SDK 原生 subagents | 仅提及边界 | Agent：subagent refs、深度与技能继承 | 真实内部会话纳入事件与预算 | 默认关闭 |
| SDK workflow | 仅提及边界 | workflow_ref 指向获准脚本描述 | Python 定义/脚本由程序执行，非 Markdown 自动执行 | 暂缓，标记 beta |
| Hooks 与错误处理 | 已有，补充错误分类 | Hook：注册 handler、事件、参数 | 程序处理真实异常并记录 | 接入 |
| Triggers 与 schedule | 已有，补充工具区别 | Trigger 描述＋Agent tool selection | session trigger 与常驻队列分开 | 默认关闭自主触发 |
| 流式文本／工具事件／可取得的 thoughts | 泛化，现补充 | Conversation：输出订阅偏好 | 流由程序消费，Task Chat/Activity 展示 | 文本与工具事件；其余可选 |
| usage、调试与观测 | 泛化，现补充 | Agent：debug/observability profile | 用量和日志为运行结果，不能手填成事实 | 接入基本记录 |
| cancel／idle／disconnect | 已有，补充 SDK 对接 | Conversation：操作允许项与超时策略 | API 动作，记录事件，确认实际停止 | 接入 |
| workspace／命令沙箱／daemon | 已有隔离原则，现补充 SDK 状态 | Agent：workspace policy、run_command config | 核对 sandbox_status，管理实际进程 | 验证隔离；daemon 暂缓 |
| Slash commands／interactive mode | 未展开 | 注册 command refs＋Agent behavior | SDK 支持的命令通过 adapter 传入 | 可选，避免绕过调度 |

以上字段名称中的应用 profile/ref 是拟定义抽象；SDK 的具体字段、取值和后端支持按固定版本校验，不把未实现资源渲染为“可用”。

## 3. 最小抽象：七类资源＋配置块

沿用 docs/02 的七类资源，不为预算、重试和压缩再建独立平台。它们作为 Agent、Connection、Conversation 的配置块；任务附件归 Task。可重复使用的配置允许引用，但首版无需全部拆成文件。

例如 Agent 的候选 frontmatter：

```yaml
---
schema: lightgravity.bot/v1
kind: agent
id: developer
title: "开发者"
enabled: true
revision: 1
connection_ref: antigravity-primary
conversation_ref: task-worker
instruction_mode: append_defaults
skills:
  source: paths
  refs: [implementation, test-report]
tool_refs: [view-file, create-file, edit-file, run-checks]
hook_refs: [task-policy, execution-events]
response_schema_ref: task-outcome-v1
capabilities:
  agent_behavior: autonomous
  enable_subagents: false
  run_command_config:
    enable_sandbox: true
budget_config:
  scope: lifetime
  max_model_calls: 20
  max_tool_calls: 40
retry_config:
  api_retry:
    max_retries: 2
  model_output_retry:
    max_retries: 1
---
```

这些数值只为说明格式，不是已选定运行预算。adapter 需转换 SDK enum、解析 refs、合并基线约束并验证目标后端。工具列表由 tool_refs 编译，避免额外 enabled_tools 字段与其冲突；frontmatter 不复制 SDK 的每一种配置入口。

Conversation 可增加 `compaction_config.token_threshold` 与应用存储策略。Connection 可增加模型与 endpoint options。UI 使用同一个 schema registry 渲染字段、正文、引用和诊断：资源卡显示配置，运行页显示实际生效配置、能力可用性、用量与停止原因。

## 4. 不能省略的约束

- **文件技能与 inline skills 不能任意混用。** 核对版本的 BaseLocalAgentConfig 拒绝同时设置 skills_paths 与 inline_skills；选择一个 source，再由 adapter 编译。InlineSkill 有 allowed_tools、dependent_tools、dependent_skills 等字段，但技能依赖不得扩大 Task 授权。[本地配置校验](https://github.com/google-antigravity/antigravity-sdk-python/blob/91dc5f84565bb505577ac9524f107f453a6e8d1f/google/antigravity/connections/local/local_connection_config.py)
- **工具不可见与运行时拒绝不同。** enabled_tools/disabled_tools 影响模型看到的能力；policy 处理真实调用。两套设置都要显示，配置中不能同时指定互斥的 allowlist/denylist。
- **重试有三层。** SDK API 重试处理瞬时模型错误，模型输出重试处理格式问题；Bot 返修处理未满足验收。它们不代表可以自动重放副作用不明确的任务。SDK 重试的后端支持有差异，应用层需按 adapter 声明实际支持范围。
- **session 预算不等于 Task 总预算。** 多成员、多 Run 和返修需由 Bot 汇总限制；预算停止原因不能解释为工作完成。
- **SDK 分层默认值不能笼统概括。** 本快照的基础 AgentConfig 配置与 BaseLocalAgentConfig 默认能力/策略不同。Bot 明确设置所需工具与政策，不依赖 README 的简化默认说明。
- **启用沙箱不证明隔离生效。** SDK 沙箱例子与 SandboxStatus 表明环境不支持时命令可能仍无沙箱运行。Bot 对要求隔离的任务应检查实际状态或使用已验证外部隔离；不允许静默降级后继续宣称隔离。[沙箱示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/91dc5f84565bb505577ac9524f107f453a6e8d1f/examples/getting_started/sandboxing.py)
- **取消是动作，不能只改 Markdown 状态。** 调用 Conversation/ChatResponse 的取消接口并确认实际停止，再写终止状态；disconnect 与保存/恢复是不同语义。[Conversation](https://github.com/google-antigravity/antigravity-sdk-python/blob/91dc5f84565bb505577ac9524f107f453a6e8d1f/google/antigravity/conversation/conversation.py)
- **回调和 workflow 仍是代码。** Markdown 只保存获准 handler/schema/script 引用，不能任意 import/eval。workflow 的执行与声明版本须固定，beta 接口不能成为首版必需依赖。
- **多模态附件与事件不是 frontmatter 正文。** frontmatter 保存路径、媒体类型、来源等引用；文件存原始内容，流和观测写入事件。SDK 返回何种信息就记录何种信息，不编造未返回的推理内容。

## 5. 首版验证与范围控制

首版需要验证配置编译、真实工具/技能、结构化计划/outcome、用户问答桥接、usage/停止原因、有限重试、cancel、保存/恢复与实际隔离。各项以安装版本和探针记录为准，源码快照不能替代 runtime 兼容结论。

本地模型、图像生成、SDK 内部 subagents、beta workflow、自主后台触发和 daemon 暂缓。记录它们的映射是保留扩展边界，不扩大首版交付范围。

实现前固定 PyPI 版本与平台 wheel，比较其公开 API 和本审计源码；不支持的字段直接报告，不能无声忽略。验收记录需要同时给出声明配置、实际编译配置及运行结果，才能证明 frontmatter 管理真正生效。
