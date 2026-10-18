---
title: "Settings、模型接入与凭证管理"
doc_type: specification
category: product
updated: "2026-10-18"
---

# Settings、模型接入与凭证管理

> 当前（LG-104已交付）：Settings采用连接列表＋紧凑New/Edit弹窗，支持Provider专属字段、草稿先测试后保存及Advanced。契约1.17.0，新独立QA R2 PASS，8123已更新。Gemini/Vertex开放配置/手动测试，LiteRT静态检查，任务执行/默认仍仅既有DeepSeek路径；任意custom host未放行，真实供应商及LiteRT硬件验证未做。[交付与新截图](../probes/provider-setup-20261017/qa-r2/DELIVERY.md)。

## 1. 入口与职责

左侧提供 Chat、Board、Files、Team 和 Session Profiles／Hooks／MCP／Tools／Triggers／Skills 六类资源入口，底部为齿轮 Settings。Connections 唯一管理入口归 Settings；资源与成员中的连接引用及旧 Connections 深链跳到对应配置。Settings 是全局配置页，访问时保留 Task/Run 返回位置，不能把当前 Task 的配置误改成全局默认。

Settings 首个二级入口为 Models & Providers，提供明确的后端接入表单，这是首版“普通资源通过 Chat 修改”的必要例外。密钥不经过聊天或 Markdown 编辑。未来其他设置按实际需求扩展，不建设通用管理后台。

| 位置 | 职责 |
|---|---|
| Settings → Models & Providers | 完整连接列表、新建/修改、凭证、连接测试和默认模型，唯一连接管理页面 |
| Team／资源连接引用及旧 Connections 深链 | 打开 Settings 并定位稳定 Connection ID；未知 ID 明确提示，普通成员不读取管理员配置 |
| Team 角色与成员 | 角色选择 connection_ref；实例保存实际模型、版本/哈希与有效配置 |

各处通过稳定 Connection ID 使用同一份 `resources/connections/*.md` 权威文件，不创建第二份 provider/model 状态库，也不迁移／删除现有连接。模板与本次实际配置分开显示；外部目标切换及迟到响应不得把表单写回另一个 ID。

## 2. 后端类型与能力状态

注册表描述 Gemini API、Vertex AI、SDK 的 `LocalOpenAIAgentConfig` 和 `LiteRTAgentConfig`，分别声明configurable/testable/executable/vendor_verified。LG-104契约1.17.0已实现并通过独立QA，取代首版planned/unavailable的表单限制；任务执行/默认能力仍保持既有边界。精确字段、能力与草稿测试见docs/08 §18；不将SDK支持、保存成功、静态检查或本地协议探针当作真实厂商已验证。

> 2026-10-18 LG-230：产品不再限制 OpenAI 兼容主机与调用次数，任意配置的主机均可执行/设默认，见 [docs/08 §22](08-interface-contract.md)；线上 demo 用 Google、本地用 DeepSeek＋192.168.8.12，见 PROJECT 决策日志。

任务执行已接通的是 OpenAI-compatible `LocalOpenAIAgentConfig` → DeepSeek（LG-003实测，[docs/08](08-interface-contract.md) §8.1）：固定 `google-antigravity==0.1.22`，loopback代理在执行时注入bearer，首选`deepseek-v4-flash`。Gemini API及Vertex Express/ADC现可配置和显式最小测试，但不是任务执行/默认选项；LiteRT只检查包/授权模型路径/配置，不安装或推理。OpenAI-compatible可以保存多个独立连接/Key/模型，实际proxy仍仅放行api.deepseek.com；自定义域名不能因同一backend枚举而被标为可执行。旧记录/正文/未知字段/默认引用不迁移删除。未添加额外SDK或通用多厂商执行平台。

依据：[Vertex 示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/examples/getting_started/vertex.py)、[本地模型示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/examples/getting_started/local_models.py)。具体字段以固定安装版本校验。

## 3. 字段与默认选择

Connection frontmatter 保存 id、title、revision、adapter、认证模式、模型、非敏感 endpoint/区域/项目参数和 credential_ref；类型相关参数按 schema 展示，不给所有后端一套必须填满的表单。

- OpenAI-compatible（首版）：`backend: openai-compat`、`base_url`、`model` 与该 adapter 实际支持的认证方式。SDK 的该配置**没有 api_key 字段**，凭证由 LG-006 的 loopback 认证代理在执行时注入；`credential_ref` 只保存引用。
- Gemini API：模型与API key引用，可配置/手动测试；HTTP不开放任意native endpoint覆盖，未做真实厂商验证。
- Vertex：Express API key或Project/Location+ADC，不能混填；可配置/显式测试，缺ADC诚实提示，不自动运行gcloud或探测metadata。
- LiteRT：workspace授权范围内model_path与CPU/GPU/NPU配置，静态检查本机runtime/文件；无API Key，不安装/下载/推理。

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

LG-104采用“填表→草稿测试→保存”的弹窗流程，Test不以保存为前置且不偷偷保存。新增 `POST /api/v1/settings/connections/test-draft` 只用当前请求内存凭据；编辑时受版本及provider/endpoint身份校验后可沿用已有秘密。草稿测试不写Connection/secret store/持久诊断/defaults/Task，只允许真实请求的安全计数与必要无秘密日志；修改字段后结果失效，不作为已保存版本的验证事实。旧saved-test端点继续工作并按版本保存安全诊断。

网络连通或文本响应成功不代表 tool calling、skills、structured output 都成功。结果显示模型/adapter、配置版本、时间、各检查项和实际错误。保存成功不直接显示“已验证”；参数/凭证更新后旧测试标为过期。

实际测试可能消耗模型费用，按钮旁清楚说明；测试有超时、取消与有限预算，不使用无限重试。结果保存为独立诊断记录并引用配置版本，不成为第二份 Connection 状态配置。

## 6. 页面反馈与首次使用

缺默认模型时主流程显示“Configure model”并打开 Settings，不要求用户先理解 Resources。设置过程保留未涉及秘密的表单草稿，切换 Task 不串改配置；秘密不持久缓存。

2026-10-17用户确认：Settings主区为连接列表和独立默认模型区；New connection/Edit打开同一紧凑弹窗（桌面480–560px，窄屏近全屏）。主字段为Provider、Name、API Key/必要认证信息和Model；Custom OpenAI-compatible必须直接显示Base URL，其执行/测试host限制如实报告。高级参数折叠，ID与credential_ref自动管理。底部Test connection、Cancel、Save，失败保留输入；关闭脏草稿需确认放弃，保存后关闭并定位真实记录。焦点、Escape、迟到请求与深链保持规则见design.md。全局调用上限已由LG107取消，仍正常计数；每次显式测试有最小请求/超时/无重试边界。

页面区分未配置、已保存未测试、测试中、已验证、部分能力通过、失败、不可用、旧测试过期。展示认证失败、模型不存在、超时和不支持能力的具体下一步，不吞成统一失败 toast。

连接编辑检测 revision 冲突，重新读取并合并；模板/默认引用更新通过 Store 校验和可恢复写入。若凭证保存与连接文件写入部分失败，保留事务诊断/补偿记录，不能留下无提示孤立秘密或坏引用。

## 7. 验收与排期

- LG-006：实现产品侧 loopback 认证代理与 DeepSeek 执行；代理是产品代码，不复制或依赖 LG-003 探针路径。
- LG-025：统一 Connection/Settings 写入、后端凭证与分层测试接口。
- LG-026：底部 Settings、类型化表单、默认选择及 Resources/Team 关联。
- LG-027：认证错误、更新冲突、测试过期、秘密脱敏、默认变更不影响活跃成员等专项验收。

LG-003 早期 SDK 探针可使用明确测试环境凭证，不依赖尚未完成的设置页；运行配置来源由 adapter 汇合到同一解析流程。LG-020 的首次启动/本地分发验收须包含设置页路径，LG-021/022 包含设置专项结果。

首版真实任务后端由2026-10-15用户决定为DeepSeek。2026-10-17 LG104已将SDK provider配置/手动测试与连接弹窗交付，公开字段/秘密存储路径见docs/08 §18；开发验收使用隔离数据、dummy Key与SDK本地协议，不擅用真实凭据、厂商调用或安装/启动LiteRT模型。原先“仅设计/待探针开放”为此前范围快照，不再表示新provider不能配置。


> **2026-10-18最终状态**：隔离候选94571a0/契约1.18.0已通过LG123独立QA的有界真实样本验收。下文“待QA”为集成冻结时的历史门描述，已由[最终独立报告](../probes/chat-task-teams-20261017/qa-LG123-final/REPORT.md)补齐；8123仍1.17.0，未部署更新。

## 8. 独立Embedding配置（LG-117；隔离完整候选已实现，待LG-123版本QA）

> **状态**：本节接口与实现已进入隔离完整候选（设置路由已挂载，`GET /settings.embedding`、`PUT /settings/embedding`、`POST /settings/embedding/test-draft`可用，健康能力`embedding_settings`按真实装配声明），并通过局部整合检查；候选契约为1.18.0，公开8123服务与运行时仍为1.17.0且未更新，LG-123独立QA未执行。
>
> 公开接口细节以docs/08 §19.4为准；未完成版本QA前不得在页面声称已生产可用或检索质量已验证。

- **位置与边界**：Settings → Models & Providers 内新增独立`Embedding`用途区，不新增主导航；聊天默认模型、coordinator/worker/reviewer连接选择不得出现Embedding记录。字段为API地址、实际模型ID、可选API Key、启用、Test；高级超时可折叠。
- **权威与凭证**：保存值写入`SETTINGS.md`的可选`embedding`块，凭证只保存`credential_ref`（服务端稳定`embedding-api`）并复用现有受保护secret store；响应/日志/测试结果不回显密钥、哈希或指纹。`GET /settings`返回非秘密视图与实际凭证来源。
- **优先级**：已保存块存在时以保存值为准；显式`enabled:false`忽略环境变量。无保存块时才回退`LIGHTGRAVITY_VECTOR_BASE_URL/MODEL/TOKEN/TIMEOUT_SECONDS/COLD_TIMEOUT_SECONDS`，并报告`source="environment"`。已保存`credential_ref`但secret缺失时视为未配置，不静默改用环境token。
- **Test**：使用当前草稿内存值，不隐式保存；`allow_network=false`只做静态校验，显式网络测试最多一次最小embeddings请求、无工具/无自动重试、有超时和真实停止确认。结果显示请求模型、响应报告模型、真实维度、耗时、凭证来源与分层检查；不能用聊天响应或配置值冒充实际模型/维度。修改字段后旧结果失效；关闭/重开/切换后迟到结果不得回填。
- **缓存与降级**：模型/地址/启用变化使旧测试失效，并使不兼容向量缓存提示重建；不混用旧向量。禁用或不可用时词法检索和原件查看仍可用。连通/维度成功不代表检索质量通过，页面不得写“检索质量已验证”。
- **与私有附件分离（R2）**：Personal 附件的模型上下文只允许 LG-119 的本地文本解析器按 owner 读取；不得调用 Embedding 配置、向量索引、OCR/ASR 或网络，也不得把私有附件登记为共享 `source`。
- **权限**：团队模式仅管理员可读写/测试；匿名401、成员403 `forbidden`；单用户沿用受保护settings的token/同源/loopback边界。前端隐藏不是授权。
- **实现门**：局部整合检查已核对`GET /settings`视图、草稿测试不落盘、secret不回显、模型变更缓存失效与词法降级；LG-123独立QA通过前不得标记为版本交付。

## 9. 自动摄取索引的设置衔接（2026-10-18，计划）

[docs/14](14-material-intake-and-auto-index.md) 的 LG-139～145 复用既有独立 Embedding 区与权限/优先级，不创建第二套模型配置。隔离1.19候选启用后对后续 Team/单用户资料摄取自动建立向量；旧资料显式重建，保存设置不隐式全库调用。LG140已冻结docs08 §20，候选接线和配置传播已实现、LG145第二轮独立QA通过，线上仍1.18。新配置于下一语义操作生效，地址/模型身份失配或旧缓存身份缺失须显式重建；保存不调用模型。团队 Personal 私有附件的索引/OCR/ASR 禁止边界保持。


### 英文转写UI更新（2026-10-18，已部署、ASR关闭）

1.20隔离候选新增默认关闭的共享英文Reader转写及Settings/Chat/Files接入，最长30秒、路径只写留空保留、机器provenance、无词时间戳；已存正文停用后仍可读取，Team Personal隔离不变。独立LG163功能/UI/权限路径通过，质量门FAILED（WER8%/21.739%、关键实体丢失）；上游原版H2输出相同，H1原版未验证。最终候选2fbff57的文案/PCM32修复与独立针对性复验已完成，46项浏览器检查通过，整体质量门仍FAILED；生产/根源码现为1.20（main 1ab4d7b），LG168已部署UI与后端，ASR仍关闭且未配置，无远端推送。见[英文设计](15-english-asr-and-ui.md)与[契约§21](08-interface-contract.md)。
