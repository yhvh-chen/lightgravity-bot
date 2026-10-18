---
title: "Settings、模型接入与凭证管理"
doc_type: specification
category: product
updated: "2026-10-18"
---

# Settings、模型接入与凭证管理

> 阶段：设计。Settings 纳入首版；首版唯一真实后端为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）→ DeepSeek 路径；Gemini/Vertex 及其它 SDK 后端只声明验证状态，不在本次扩大为多厂商执行实现。

## 1. 入口与职责

左侧保留 Chat、Board、Files、Team、Resources 五个工作入口；底部增加齿轮 Settings。Settings 是全局配置页，访问时保留 Task 返回位置，不能把当前 Task 的配置误改成全局默认。

Settings 首个二级入口为 Models & Providers，提供明确的后端接入表单，这是首版“普通资源通过 Chat 修改”的必要例外。密钥不经过聊天或 Markdown 编辑。未来其他设置按实际需求扩展，不建设通用管理后台。

| 位置 | 职责 |
|---|---|
| Settings → Models & Providers | 新建/修改模型连接、管理凭证、连接测试和默认模型 |
| Resources → Connections | 同一连接的详细声明、能力、诊断与被引用关系，链接到 Settings 修改 |
| Team 角色与成员 | 角色选择 connection_ref；实例保存实际模型、版本/哈希与有效配置 |

三处通过稳定 Connection ID 使用同一份权威文件，不创建第二份 provider/model 状态库。模板与本次实际配置分开显示。

## 2. 后端类型与能力状态

注册表可以描述 Gemini API、Vertex AI、SDK 的 `LocalOpenAIAgentConfig` 和 `LiteRTAgentConfig`。SDK 有相关示例不代表 LightGravity 已验证全部后端；未验收后端不允许保存为可执行默认连接。

首版真实接通的是 OpenAI-compatible `LocalOpenAIAgentConfig` → DeepSeek 路径（LG-003 已实测，契约见 [docs/08](08-interface-contract.md) §8.1）：固定 `google-antigravity==0.1.22`，由 LG-006 实现 loopback 认证代理在执行时注入 bearer；首选模型 `deepseek-v4-flash`。Gemini Developer API 与 Vertex 在本环境未验收，LiteRT 未探索，均显示 planned/unavailable，不得作为默认连接。不得以“OpenAI-compatible”承诺任意第三方云 API 完全兼容，不在本次添加额外 SDK 或通用多厂商平台。

依据：[Vertex 示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/examples/getting_started/vertex.py)、[本地模型示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/examples/getting_started/local_models.py)。具体字段以固定安装版本校验。

## 3. 字段与默认选择

Connection frontmatter 保存 id、title、revision、adapter、认证模式、模型、非敏感 endpoint/区域/项目参数和 credential_ref；类型相关参数按 schema 展示，不给所有后端一套必须填满的表单。

- OpenAI-compatible（首版）：`backend: openai-compat`、`base_url`、`model` 与该 adapter 实际支持的认证方式。SDK 的该配置**没有 api_key 字段**，凭证由 LG-006 的 loopback 认证代理在执行时注入；`credential_ref` 只保存引用。
- Gemini API：模型与 API key 引用；endpoint 修改只在 adapter 支持时提供；本环境未验收，显示 planned/unavailable。
- Vertex：区分 Express API key 与 Project/Location + ADC，不能混填成一个不明确认证模式；未验收。
- LiteRT：授权范围内的 model_path 与本机 runtime 可用性；不是 API key 表单；未探索。

首版首选模型为 `deepseek-v4-flash`（本环境 pi 开发派工实际使用的 DeepSeek 模型）。LG-003 SDK 探针当时使用 `deepseek-chat`，LG-006 须记录并验证实际发送给 SDK 的 model ID 与 `base_url`；不把未经该路径实测的版本串（例如“4.1”）写成可用 API ID。

全局默认引用放在 `bot-data/settings/SETTINGS.md`，采用应用 frontmatter `kind: settings`，只保存 `default_coordinator_connection_ref`、`default_worker_connection_ref` 和 revision 等偏好，不复制 Connection 参数或凭证。角色可显式选 connection_ref；否则 worker 使用全局默认。协调器使用协调默认。没有有效连接时停止相关执行并提供配置入口，不静默切到其他付费或外部后端。

新会话/招募解析并固定引用版本；默认修改只影响后续使用，活跃 Run 不热切换。禁用/删除默认或被引用连接时显示影响，首版阻止留下悬空引用。

## 4. 凭证管理

API key 使用独立受保护输入和后端凭证接口。首版可选择 OS keyring 或权限受限、位于源码/任务之外的本地秘密存储；由实现任务明确选择与威胁边界，不能因文件不在 Git 就宣称加密。凭证来源可以是进程环境（如运行环境已注入的 DeepSeek key）或受控 secret store 的 `credential_ref`；**不假设项目 `.env` 一定含可用 key**，不在文档、日志、事件或响应中输出完整秘密。云端后续另选平台秘密存储。

Connection 文件只保存 credential_ref。浏览器不写 localStorage/IndexedDB 或聊天草稿，不在 URL 传密钥；后端响应仅返回引用/是否配置，不返回原值。表单提交后清空秘密输入，日志、异常、事件与 SDK 配置展示进行脱敏。引用存在不等于认证成功。

支持新建、更新、移除引用；区分“保留已有密钥”和“移除密钥”，空输入不能无意删除。环境凭证可只读显示来源，页面不得暗示能够删除环境变量。首版本地认证代理只监听 loopback，具明确的启动/停止/失败生命周期；停止需确认，残留代理/worker 进程必须清理；代理日志、异常与事件对凭证脱敏。Task 数据导出不包含秘密；配置导出只含引用并说明目标环境需重新配置。

仅本地单用户也需要验证敏感写入的请求来源/保护策略，默认 loopback。具体防护在接口契约里确定；网页预览、跨站请求和普通聊天不能调用秘密管理接口。

## 5. Test Connection

显式测试分层返回结果：配置解析、runtime/网络、认证、模型响应、所选工具/结构化输出探针。普通测试只做最小模型请求；工具探针单独启动，在临时隔离环境验证，不执行用户任务或自动创建队伍。

网络连通或文本响应成功不代表 tool calling、skills、structured output 都成功。结果显示模型/adapter、配置版本、时间、各检查项和实际错误。保存成功不直接显示“已验证”；参数/凭证更新后旧测试标为过期。

实际测试可能消耗模型费用，按钮旁清楚说明；测试有超时、取消与有限预算，不使用无限重试。结果保存为独立诊断记录并引用配置版本，不成为第二份 Connection 状态配置。

## 6. 页面反馈与首次使用

缺默认模型时主流程显示“Configure model”并打开 Settings，不要求用户先理解 Resources。设置过程保留未涉及秘密的表单草稿，切换 Task 不串改配置；秘密不持久缓存。

页面区分未配置、已保存未测试、测试中、已验证、部分能力通过、失败、不可用、旧测试过期。展示认证失败、模型不存在、超时和不支持能力的具体下一步，不吞成统一失败 toast。

连接编辑检测 revision 冲突，重新读取并合并；模板/默认引用更新通过 Store 校验和可恢复写入。若凭证保存与连接文件写入部分失败，保留事务诊断/补偿记录，不能留下无提示孤立秘密或坏引用。

## 7. 验收与排期

- LG-006：实现产品侧 loopback 认证代理与 DeepSeek 执行；代理是产品代码，不复制或依赖 LG-003 探针路径。
- LG-025：统一 Connection/Settings 写入、后端凭证与分层测试接口。
- LG-026：底部 Settings、类型化表单、默认选择及 Resources/Team 关联。
- LG-027：认证错误、更新冲突、测试过期、秘密脱敏、默认变更不影响活跃成员等专项验收。

LG-003 早期 SDK 探针可使用明确测试环境凭证，不依赖尚未完成的设置页；运行配置来源由 adapter 汇合到同一解析流程。LG-020 的首次启动/本地分发验收须包含设置页路径，LG-021/022 包含设置专项结果。

实现前仍要固定实际字段与秘密存储方案。首版真实后端选择已由 2026-10-15 用户决定更新为 DeepSeek；Gemini/Vertex 待后续探针通过后另行开放。此次只完成设计和开发任务，不保存真实凭证、不发起连接测试、不安装或启动模型。

## 8. 英文音频转写（English ASR，契约 1.20/1.22）

Settings 内的 English ASR 是独立的机器转写配置，不是模型连接，不参与默认 coordinator/worker 选择。它只处理英文音频并写入资料的 machine 派生正文；人工正式版、检索、下载与撤销/归档语义不变。

| 项 | 线上 8123（1.20） | 1.22 候选（未部署） |
|---|---|---|
| provider | 旧块无 `provider`，等价 `eg2-reader` + `inprocess` | 旧块行为逐字保留；新配置可用 `google-native` |
| 运行依赖 | 固定版本 EG2 编码器/Reader 权重与 `english-asr` 运行时 | 仅标准库 HTTPS 调用原生 REST，无 Torch/numpy/transformers/Reader/模型容器/`192.168.8.12` |
| 音频边界 | 旧 30 秒/字节/线程等字段不变 | raw `max_audio_bytes` 默认 10,000,000、上限 14,000,000；序列化请求总量只读上限 20,000,000（base64 膨胀已计入）；无数字 `max_audio_seconds` |
| 质量记录 | 旧 Reader 独立质量门 **FAILED**；不追溯改判 | Google 仅 LG-235 两次真实小样本原型，**不宣称质量通过** |

### 8.1 Google native 轻量用法（1.22 候选）

1. 管理员在 Settings → English ASR 选择 **Google native audio**。Model 默认 `gemini-3.8-flash`；Base URL 固定为 `https://generativelanguage.googleapis.com/v1beta`（实际端点 `/v1beta/interactions`），拒绝 `/v1beta/openai`、http、其他 host、userinfo/query/fragment 与代理 URL。
2. API key 是**只写**字段，经既有受控 `FileSecretStore` 保存；GET 视图只返回 `credential_configured`，不回显 key/ref/路径。产品**不读取** `LG_GOOGLE_ASR_API_KEY` 或任何环境变量作为 Google 产品凭证。留空保存表示保留已存 key；显式 `null`/空串返回 `422`，不会静默清空。
3. 保存只做 schema/host/secret/上限校验：不验证 key、不发网络请求、不加载模型、不推理、不自动重处理旧资料。`available=true` 仅表示可尝试，不代表 key/model/网络已核实；单文件成功只由 `source.receipt` 与正文证明。
4. Google 表单不显示/不写入 `model_dir`、`reader_dir`、`device`、`threads`，不显示 Reader/30 秒限制文案；`max_audio_seconds` 省略或 `null`。旧的 EG2/Reader 表单与字段保持原义，切换 provider 不重处理旧来源。
5. 每次作业最多一次 ASR 尝试（既有 `max_asr_calls=1` 有界语义），失败（401/403、429、模型不可用、5xx、超时/取消未确认等）如实报告且**不自动换模型/供应商、不回退 Reader、不自动重试**；手工 `reprocess` 是新的显式尝试。发送后超时/取消按未知副作用停车，不写部分正文。
6. machine 正文按原样保存模型输出（包括已知缺陷，如原型 H2 的字面 `thought` 前缀），不按样本清洗或注入标准答案；receipt 记录 provider/model/endpoint/prompt version/音频 hash/字节/latency/非秘密 usage，不伪造 Reader/编码器与时间戳。

**部署边界**：上述 1.22 行为只存在于隔离候选，独立 LG-239 真实浏览器与一次真实 Google 摄取验证仍待执行；公开 8123/5173 仍是 1.20.0，旧 Reader 质量 FAILED 与 §21 限制不变。
