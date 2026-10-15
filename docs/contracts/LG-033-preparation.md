---
title: "LG-033 资料摄取与检索契约准备稿（未冻结，可交 docs/08 owner 串行冻结）"
doc_type: preparation
category: architecture
status: draft-preparation
updated: "2026-10-16"
---

# LG-033 资料摄取与检索契约准备稿

> **性质：准备稿，非契约冻结。** 本文件不修改也不替代 [docs/08 接口契约](../../docs/08-interface-contract.md)，
> 不升 `CONTRACT_VERSION`（当前 `1.5.0`），不定义已冻结语义，不宣称任何能力已实现。
> 本文件把 [docs/09 资料接入与检索设计](../../docs/09-source-intake-and-retrieval.md)（方向已确认、接口未冻结）
> 收敛为**可实施接口草案**，供**单一 docs/08 owner 串行冻结**：正式冻结必须由该 owner 按 docs/08 §13
> 变更控制升版、同步 `backend/lightgravity/contracts/constants.py`、`tests/contracts`、README、PROJECT、agent.md、docs/06，
> 并处理与既有 Files/Chat 契约的共享冲突。本文件字段/枚举/端点/事件/错误码均为**候选**，冻结时可改名，
> 但语义要求应逐条保留或显式记录取舍。
>
> 并行姊妹稿：LG-028 去中心化协作契约准备稿（位于同机 `lg028-contract` worktree 的 `docs/contracts/LG-028-preparation.md`，**本分支不包含该文件**，故不建相对链接）。两稿共享 docs/08 冻结面，**必须由同一 owner 串行冻结**，
> 不得两个执行者并发改 docs/08。本稿只读引用 LG-028 的 `lease`/`owner` 语义，不复用其运行时实体。

## 0. 基点与证据（本包事实）

- 基点：`dev/lg033-contract`，本稿前一提交 `a34c915`（上一版 50 行准备稿）；本包只改本文件与 `probes/lg033/PREPARATION.md`。
- 契约现状：`CONTRACT_VERSION = "1.5.0"`（`backend/lightgravity/contracts/constants.py`）；docs/08 现无任何资料/摄取/检索端点或 schema。
- 本包模型调用 **0**，无新网络实验，无代码改动；探针事实只**复述** `probes/source-intake/**` 既有归档，不重新推理。
- 依据：[docs/09](../../docs/09-source-intake-and-retrieval.md) 全篇、docs/08 §4.1–§4.3、§5、§6、§7、§9、§10、§13、
  [证据入口](../../probes/source-intake/README.md)、[归档清单](../../probes/source-intake/evidence/MANIFEST.json)、[检查记录](../../probes/source-intake/DOC_CHECKS.md)。
- 不可用/未验证项：中文 ASR（LG-039 未做）、生产级 OCR 质量、Office、多页/混合版式、真实人声、邮箱/抓取。均不得写成已实现。

---

## 1. 目标与边界

- 目标：把资料方向收敛为**受控摄取作业**的可实施接口：原件先落盘 → 提取/OCR/转写 → 归属 → 正式内容版本 → 索引 → 回执 → 查询回源，
  文件（原件 + 资料 frontmatter + 正式内容文件）始终是**唯一事实源**，JSONL 保存历史。
- 保持（继承 docs/09、agent.md §3）：索引/向量仅为**可重建缓存**；权限与归属**不存于索引**，读取时回源核对；
  摄取作业**不自动创建交付 Task/Run/团队**；模型只提议，程序校验并落实授权与归属。
- 不在本文件冻结：具体字段名/枚举 string 的最终拼写、端点最终路径、是否单文件多实体、目录命名。语义要求在下面逐条给出。
- 不做：通用知识库平台；独立向量数据库服务；多租户；组织协作；邮箱全箱同步；自动执行邮件正文指令；外部聊天渠道；自主触发。

---

## 2. 写授权与边界（必须先明确，冻结时**不可弱化**）

这是 LG-033 最容易越界的一点，冻结文本必须显式区分两条写路径。

### 2.1 受控摄取写授权（程序直接写，无需工程交付 Run）

在**资料接入授权范围**内，程序可直接写以下内容，**不要求交付 Task/Run/团队**：

| 允许程序直接写 | 位置（候选，未冻结） | 说明 |
|---|---|---|
| 原件 | 受控资料根下（如 `<data_dir>/sources/…`，候选） | 先落盘，命名/分片属实现细节 |
| 资料记录（frontmatter） | 资料目录内 `SOURCE.md`/等价物（候选） | 来源、版本、归属、哈希、派生引用 |
| 机器提取件 | 派生目录 | 带源版本，随来源变动失效 |
| 人工正式版本 | 独立正式内容文件 | 与机器提取分离，重处理不覆盖 |
| 索引/向量缓存 | 缓存目录 | **可整体删除重建** |
| 摄取事件/回执 | JSONL / 现有事件机制 | 参见 §5 |

边界（**不得扩大授权**）：

- 摄取写**不等于**工程写。**工程源码修改（`frontend/**`、`backend/**`、共享依赖等）仍必须走既有 Task/Run、验证与人工验收门**。
- 摄取**不得**修改任何 Task/Run/Member 的**运行控制状态**（`status`/`phase`/`queue`/`acceptance`/`active_run`），
  不得领取工件、不得释放队伍、不得写验收决定。资料写与交付写是不同层。
- **上传资料不自动创建交付 Task/Run/团队**，不占执行槽、不排队交付。"上传了文件"**不等于**"开始了交付"。
- **有界工具问答仍只读**：摄取不授予工具问答任何写权限。
- **上传文件自身 frontmatter 不是受信 Task/资源配置或指令**（docs/09 §5 信任边界）：只作资料元数据，须经程序 schema 校验，
  未知字段保留但**不获得执行语义**（不得 import/eval、不得启动 MCP/Trigger、不得改控制状态）。
- **实质归属歧义才询问**用户，不把每次上传变成确认门。

### 2.2 工程写路径（沿用既有契约，摄取不替代）

- 用户在**同一轮**既交资料又要求改工程时：资料部分走本节摄取授权，**工程修改部分仍走 Task/Run + 验证 + 人工验收**。
  两者可由同一对话发起、**拥有不同写边界**，不得因混合意图而放宽工程侧权限。

---

## 3. 实体与文件分层（事实源）

### 3.1 分层

| 层 | 内容 | 权威性 | 重处理行为 |
|---|---|---|---|
| **原件** | 用户交付的原始字节 | **SoT**，不可变（新版本另存） | 永不覆盖 |
| **资料记录** | 来源 frontmatter（来源、版本、归属、引用） | **SoT** | 版本化更新 |
| **机器提取** | OCR/转写/结构化文本 | **带源版本的派生** | 可重建/可失效，**不覆盖人工校订** |
| **正式内容文件** | 人工校订后的正式正文 | **SoT 正式版本** | 新版本保存，旧版本保留 |
| **索引/向量** | 词法 postings、向量 | **可重建缓存** | 删除重建，不承载唯一事实 |
| **历史** | 消息/事件 JSONL | 只追加历史 | 不修改，不删除 |

### 3.2 来源记录候选 schema（实体 `source`，**未冻结**）

沿用 docs/08 命名约定：运行时实体 ID `source_<ULID>`，时间 ISO-8601 UTC `Z`，JSON `snake_case`，枚举小写 `snake_case`。

```yaml
schema: lightgravity.bot/v1
kind: source
id: source_01J...            # 运行时前缀建议新增 source（冻结时登记进 §3.1）
title: "2026-10 报销单扫描件"
title_origin: user           # user | derived（派生标题不覆盖用户标题）
status: received             # received | processing | extracted | attributed | indexed | archived | partial | failed（草案，见 §6）
revision: 0                  # 资料记录写入版本，非负整数，每次成功提交 +1
scope:                       # 作用域与归属（程序校验后落定）
  task_ref: null             # 明确 Task 归属；全局上传为 null
  project_ref: null
  inbox_ref: null            # 归属未知时指向受控收件区
origin:                      # 来源类别与外部标识
  kind: upload               # upload | link | folder | email | audio（本轮仅 upload/link 先行）
  external_ref: null         # URL / 原路径（仅记录，未抓取即未入库）
  fetched: false             # 链接是否已抓取：false 时不得声称已入库
content_hash: null           # 当前源版本内容的 SHA-256（内容是否变化）
stat_revision: null          # 文件写入令牌（如 size-mtime_ns），**非密码学哈希**，与 content_hash 严格区分
source_version: 1            # 源版本序号；内容 hash 变化时 +1（见 §7.4）
original:                    # 原件引用
  path: null                 # 受控资料根内相对路径（经 Store.resolve_path 授权）
  media_type: null
  bytes: null
  archived_at: null
derivatives: []              # 派生引用列表：{kind, path, source_version, content_hash, model_version}
formal:                      # 正式内容版本
  path: null                 # 人工校订后的正式正文
  revision: null
  edited_by: null            # user | none
index:                       # 索引状态（**只是缓存视图，不是权威**）
  lexical: not_indexed       # not_indexed | indexed | stale | failed
  lexical_hash: null         # 建立索引时的源内容 hash
  vector: disabled           # disabled | not_ingested | indexed | stale | unavailable | failed（可选，见 §8）
  vector_model: null         # 模型标识+版本（见 §8）
receipt_ref: null            # 最近一次回执事件引用
created_at: null
updated_at: null
```

规则：

- `content_hash` 与 `stat_revision` **不得互相冒充**（docs/09 §5；docs/08 §4.3 已声明文件端点 revision 非密码学哈希）。
- 机器提取与人工正式版本**位置分离**；`derivatives` 携带 `source_version`，重处理只新写派生，**不 touch** `formal`。
- 未知 frontmatter 字段**保留**，不因解析丢弃（docs/08 §7）。

---

## 4. 摄取作业（Job）与受控收件区

### 4.1 摄取作业候选 schema（实体 `intake_job`，**未冻结**）

```yaml
schema: lightgravity.bot/v1
kind: intake_job
id: intake_01J...
source_ref: source_01J...
status: queued              # queued | running | succeeded | partial | failed | cancelled | recovery_required（草案）
revision: 0
request_id: req_01J...      # 稳定接入请求 ID（幂等键，见 §7.1）
payload_hash: null          # 请求负载规范化 SHA-256，用于检测同 request_id 不同 payload
idempotency_scope: null     # 由服务端确定；不信任客户端自报作用域
stage: received             # received → extracting → attributing → formalizing → indexing → done（草案，展示用）
attempt: 1
budget:                     # 有界：限定模型调用/时限/重试
  max_model_calls: 0
  timeout_seconds: null
  max_retries: 1
cancel:
  requested: false
  confirmed: false          # 只有确认停止才写 cancelled（沿用 docs/08 §9 语义）
fail_reason: null
created_at: null
updated_at: null
```

- Job 是**逻辑边界**，不是第二套业务状态库（docs/09 §6）：权威状态仍在文件（原件 + 资料 frontmatter + 正式内容 + JSONL）。
  若保留 `intake_job` 实体，其 frontmatter 只是作业记录，**索引/看板不得据此另建权威状态**。
- 摄取作业与被 docs/08 冻结的 Run/Subtask/Member **是不同层面**：不因一次上传占用执行槽或排队交付。
- 有界：程序编排 + 按需模型调用，限定预算，支持取消与有限重试；**不需要常驻编排 agent**。
- **失败诚实**：失败**不造空成功正文**；**失败说明不作为知识正文参与检索**（避免把报错当资料）；原件与历史事件保留，可重试或换方式。

### 4.2 受控收件区（inbox）

- 归属未知的资料落入**受控会话收件区**（候选：`inbox` 类受控区域，独立于 Task/Project 目录），不直接写进某 Task/Project。
- 当前 Task/Project **可靠**时沿用其归属；否则先放收件区，并记录 `scope.inbox_ref`。
- 全局上传**不强建 Task**；未来 Project 共享需要**独立边界**，不与 Task 目录混用。
- 收件区路径必须经 `Store.resolve_path` 授权（拒绝 `..`/绝对路径越界/逃逸符号链接，docs/08 §10）；`realpath` 落在授权根外即拒。
- 拒绝越界路径和未授权来源；`path_outside_workspace` / `reference_invalid` 沿用既有错误码。

---

## 5. 回执、事件与查询接口

### 5.1 逐文件回执（**候选**）

按**每个文件**明确状态：`received` / `processing` / `succeeded` / `partial` / `failed`。回执至少含：
来源、产物位置（原件/提取件/正式文件）、是否可检索、失败原因（若失败）、`source_version`、`request_id`。

- 多文件/多页允许**部分成功**，回执**如实区分**成功与失败，不把失败伪装成成功。
- Chat 回执与 Files 读取**同一份**文件状态，不另建状态（docs/09 §6）。
- 回执不进入知识正文（失败说明不参与检索）。

### 5.2 事件（**候选，MINOR 新增**）

沿用 docs/08 §5.1 事件信封（`evt_`/`stream_id`/`seq`/`type`/`payload`，只追加、游标 `v1:<stream_id>:<seq>`）。候选新事件类型：

- `source.received`、`source.version_changed`、`source.attributed`、`source.indexed`、`source.invalidated`、`source.deleted`
- `intake.stage_changed`、`intake.receipt`、`intake.failed`、`intake.cancelled`

规则：新增事件类型属 **MINOR**；消费方**必须忽略未知类型**而非崩溃（docs/08 §5.1）。事件仅追加、不修改、不删除。

### 5.3 查询/检索接口（**候选，MINOR 新增**）

统一语义：**授权候选 → 回源核对（存在/哈希/版本/权限）→ 真实位置**。

| 方法/路径（候选） | 用途 | 关键语义 |
|---|---|---|
| `POST /api/v1/sources` | 登记一次接入请求（幂等：`request_id`） | 只登记+落盘原件，**不创建 Task/Run**；同 `request_id` 同 payload 返回首次结果，不同 payload 冲突 |
| `GET /api/v1/sources` | 资料列表（分页/作用域过滤） | 只返回调用者**已授权**的资料 |
| `GET /api/v1/sources/{source_id}` | 资料详情（含状态、派生、正式版本引用） | 不回显越界路径 |
| `GET /api/v1/sources/{source_id}/receipt` | 最近逐文件回执 | 与 Files 同一份状态 |
| `GET /api/v1/sources/{source_id}/content` | 预览正式内容/原件（只读） | 经 `resolve_path` 授权；Markdown/HTML 不执行脚本 |
| `GET /api/v1/sources/{source_id}/download` | 下载原件/正式内容 | 附 stat 型 revision，**非密码学哈希** |
| `POST /api/v1/sources/{source_id}/actions` | 控制动作：`reprocess` / `cancel` / `revoke` / `delete` | `cancel` 需确认停止；`reprocess` 不覆盖人工校订；`revoke`/`delete` 使命中失效 |
| `GET /api/v1/intake/jobs/{job_id}` | 摄取作业状态 | 逻辑视图，非第二套状态库 |
| `POST /api/v1/intake/jobs/{job_id}/actions` | `cancel` / `retry` | 未知副作用的中断**不自动重放**（docs/08 §9） |
| `GET /api/v1/search` | 词法优先检索（授权过滤） | 返回候选 + 来源证据引用；命中**必须回源核对**；损坏/处理中如实显示 |
| `POST /api/v1/inbox/messages`（或复用全局对话） | 归属未知资料入收件区 | 全局上传**不强建 Task** |

- 端点最终路径、是否与现有 Files 端点合并，由 docs/08 owner 决定；**本节语义要求不可丢**。
- 检索**不要求独立向量库服务**（docs/09 §7）；词法优先、向量可选。
- `POST /api/v1/sources` 与既有 `POST /api/v1/files/upload`（docs/08 §4.3，已实现）的**迁移/兼容路径**见 §9。

### 5.4 错误码（复用既有，必要时 MINOR 新增）

优先复用 docs/08 §4.2：`invalid_request`、`unauthorized`、`path_outside_workspace`、`not_found`、`revision_conflict`、
`lock_conflict`、`not_ready`、`illegal_transition`、`cancellation_unconfirmed`、`config_invalid`、`reference_invalid`、
`validation_failed`、`budget_exhausted`、`capability_unavailable`、`internal_error`。

候选**加性**新增（若确有必要，MINOR）：
- `source_conflict`（409）：同 `request_id` 不同 payload；
- `source_stale`（409）：候选命中回源时源版本/哈希已变；
- `index_unavailable`（503）：索引损坏或处理中，**词法降级仍可用**或明确不可用，不返回悬空结果。

---

## 6. 生命周期（草案，展示用，**不加入 Task phase 枚举**）

`received → processing → extracted → attributed → indexed → archived`；分支 `partial`、`failed`。

- 这是**摄取作业/文件**层面的展示状态示意，**不加入** docs/08 §6.1 的 Task `phase` 枚举，不改既有状态机。
- 撤销/删除、来源变动、取消、恢复的转换必须在冻结时给出合法迁移表与非法组合（401 复用 `illegal_transition`）。

---

## 7. 幂等、去重、来源版本、撤销与恢复（最小规则）

### 7.1 幂等（绑定请求 ID，**不是"同一 URL 永远跳过"**）

- 同一上传/链接/来源的重复提交按**稳定接入请求 ID**（`request_id`）返回**首次结果**，不重复建资料、不重复跑模型。
- 同一 `request_id` 若 payload 不同，按**冲突**处理并如实回执（候选 `source_conflict`），**不静默接受或覆盖**。
- `request_id` 幂等作用域由**服务端**确定，不信任客户端自报跨 Task 作用域。

### 7.2 去重（**作用域内**）

- 按**来源 + 内容 hash** 识别**同一来源、同一授权范围**内的重复提交；同一内容不同名**不重复建权威记录**。
- **跨来源/跨 Task 不合并**：相同字节来自**不同来源**或**不同 Task/Project** 时，保留各自的来源记录、作用域、权限与引用；
  即便未来共享底层 blob，也**不得自动合并授权、抹掉来源或扩大可见范围**。去重**只去重存储/处理，不去重权限**。

### 7.3 权限与归属只能在文件 SoT

- 权限和归属**不可只存在索引/向量**：索引/向量只是可重建缓存，**不含独有权限/归属/正文/控制状态**。
- 检索只返回调用者**被授权**的候选；**读取时回源核对**存在、哈希、版本与访问范围。
- 索引损坏/被删后，从文件**重建**不得改变归属或扩大可见范围。

### 7.4 来源版本与失效

- 来源内容 hash 变化时生成**新的源版本**（`source_version + 1`），**重建**其派生/索引/向量；旧版本对应命中**失效**（`source_stale`）。
- `stat_revision` 变化但内容 hash 不变**不**构成新源版本。
- 旧源版本与人工校订版本**保留**，不静默删除。

### 7.5 撤销与删除

- 来源被**撤销/删除**时，对应命中**失效**，**不得返回悬空结果**；原件/历史事件按策略保留或标记删除，不伪造成功。
- 撤销/删除**不**自动删除其它来源或其它 Task 的相同字节记录。

### 7.6 重处理不覆盖人工校订

- 重跑提取**不覆盖**人工正式版本；新派生带当前 `source_version`，人工版本独立保存并版本化。

### 7.7 恢复与取消

- 写用**原子替换 + 版本检查**（docs/08 §7）；进程中断后先检查已落盘原件与不完整派生/索引，
  **不静默重放副作用不明的处理**（docs/08 §9；LG-016 反重放边界）。
- 取消需**确认停止**（`cancel.confirmed`）才写 `cancelled`；未确认保持状态并允许重试（docs/08 §9）。
- 浏览器断线不取消后台摄取；重连按游标补齐（docs/08 §4.4）。

---

## 8. 索引与向量（**可重建缓存**）

### 8.1 词法索引（LG-036）

- 基于**文件、元数据、正式内容**建立**派生**索引，支持精确短语、编号、日期、金额及**授权范围过滤**。
- 命中**回源核对**文件存在、权限、版本与哈希；删除、撤销、移动、校订后旧命中**失效**。
- 删除缓存**可从文件重建**并复现查询；索引损坏/处理中**如实显示**；**不启动独立数据库服务**。
- 本地参考实现（只读借鉴，不照搬）：[olav-tasks `src/docs-kb.ts`](/home/yhvh/code/olav-tasks/src/docs-kb.ts) —— 字面量正则检索 + frontmatter 校验 + 路径包含检查 + **无持久索引**（每次扫描文件）。MIT（`olav-tasks/LICENSE`）。

### 8.2 向量索引（LG-037，**可选**）

- embedding 是**可选派生**，**不是**摄取/OCR/词法索引的前提；**向量服务不可用时词法检索与原件查看仍可用**（降级保留）。
- **不要求独立向量库服务**：`vectors.npy` / `items.json` 之类只是**参考实现**，未冻结。
- **能力区分**：文本 embedding、多模态 embedding、OCR/ASR 的**能力、模型与预算不同**。
  **embedding ≠ OCR/ASR 转写**；**向量输出不等于文字提取**，不得用一条通路的结论推断另一条。
- 必须记录：模型标识、版本、维度、内容/片段哈希、来源与缓存版本；**模型切换触发重建**，不混用不兼容向量。
- 媒体可**直接建向量**，**不伪造**成文字；OCR/ASR 成文是**另一条通路**。
- 查询与命中回源均受**权限控制**；向量缓存可删除重建，**不承载唯一业务事实**。

### 8.3 端点事实（只读复述，**不作运行默认或产品依赖**）

- `192.168.8.12:11434` 是 **llama.cpp `llama-server` router**（**非 Ollama**：`/api/version`、`/api/tags` → 404），
  报告版本 `b11641-843e7dcc1`（[证据入口](../../probes/source-intake/README.md)）。
- `embeddinggemma-2-Q8_0` 文本嵌入返回 **768 维**、有限、L2=1.0（与元数据 `n_embd=512` 不一致，以实测 768 为准）；
  不同有效媒体内容改变向量（第二图 cos 0.888551、第二音 cos 0.978952）——这是**输入消费**证据，**非**语义/识别质量结论。
- 该端点是 **OpenAI-compatible 的 llama.cpp**，不是 Ollama；**地址与模型必须可配置**，**不得硬编码**为产品依赖。
- **本包只读既有探针结果，不再推理**；未做 checkpoint hash 验证，身份仍 `unknown`。

---

## 9. 与既有契约的衔接、迁移与反例

### 9.1 只读引用点

- docs/08 §4.3 现有 `POST /files/upload`、`GET /files/download`、`GET /files`、`GET /files/content`：**历史实现，语义不变**。
  资料接入的目标交互逐步收拢到 Chat，**当前尚未迁移**。
- docs/08 §5.2 消息 `attachments`（`{path, media_type}`）与 `resource_proposal`：资料消息可复用 `attachments`，
  **不新增**与 `resource_proposal` 混淆的字段；`resource_proposal` 仅受控资源写，不用于资料摄取。
- docs/08 §6.5 Connection 与邮箱连接器**是不同概念**；邮箱连接器不得暗加到已冻结 Connection/资源 schema（docs/09 §2）。
- 既有 Store/原子写/路径授权（§7/§10）直接复用，不新造持久层。

### 9.2 迁移计划（候选）

- **兼容路径**：既有 `POST /files/upload` 保留；新摄取入口（`POST /sources`）在冻结期可内部复用同一有界上传 + 原子写逻辑，
  但**返回摄取语义回执**。迁移不得静默改变既有端点语义（docs/08 §4.1：破坏性变更只能 `/api/v2`）。
- **版本策略**：新增资料 schema/端点/事件属 **MINOR**；改既有 Files/Chat 端点语义或有损迁移属 **MAJOR**，须走 `/api/v2`。
- **前置**：实现前**必须**先由 docs/08 owner 冻结并升版；本稿与 LG-028 共享 docs/08，**串行冻结**。

### 9.3 反例（冻结/实现/验收时的负向清单）

1. **把摄取当交付**：上传资料后自动创建 Task/Run/团队，或占执行槽 → **禁止**（§2.1）。
2. **借摄取改工程**：以资料接入为由写 `frontend/**`/`backend/**` 而不走 Task/Run 验收 → **禁止**。
3. **索引即权限**：权限/归属只存索引，索引删除或跨 Task 查询即泄权 → **禁止**（§7.3）。
4. **跨 Task 合并**：相同字节自动合并授权、抹掉来源、扩大可见范围 → **禁止**（§7.2）。
5. **URL 永久跳过**：把幂等做成"同一 URL 永远不入库"，使合法重试无法更新来源 → **禁止**（§7.1）。
6. **重处理覆盖校订**：重跑 OCR/转写写回 `formal`，冲掉人工版本 → **禁止**（§7.6）。
7. **悬空命中**：来源撤销/删除/移动后仍返回旧命中 → **禁止**（§7.5、§8.1）。
8. **失败当资料**：把错误文本/空正文写入派生并参与检索 → **禁止**（§4.1）。
9. **向量冒充文字**：把 embedding 输出当 OCR/ASR 正文，或用一条通路结论推断另一条 → **禁止**（§8.2）。
10. **硬编码端点**：把 `192.168.8.12:11434` 写死为运行默认 → **禁止**（§8.3）。
11. **强行重放**：未知副作用的中断自动重放 → **禁止**（§7.7）。
12. **未确认即取消**：无停止确认就写 `cancelled` → **禁止**（§7.7）。
13. **上传 frontmatter 当指令**：上传文件的未知字段获得执行语义/触发 MCP/Trigger → **禁止**（§2.1）。
14. **合成样本充质量**：用两类合成 OCR 样本或单 batch 向量余量 0.048 充当生产质量/检索质量 → **禁止**（§0、§8.3）。

---

## 10. LG-034～040 可实施分包接口（依赖与 owner 提示）

所有实现均为 `todo`、依赖满足后才 claim；共享 Store/Coordinator/API/前端入口由**单 owner 串行集成**（docs/06 §6.1、docs/08 §11）。

| 任务 | 消费本稿哪些冻结面 | 产出（接口层） | 依赖 |
|---|---|---|---|
| [LG-034](../../backlog/tasks/LG-034.md) 原件接收与可恢复摄取 | §2 写授权、§3 来源记录、§4 收件区/Job、§7.1/7.7 幂等与恢复 | `POST/GET /sources`、原件落盘、`request_id` 幂等、收件区 | LG-033、LG-016 |
| [LG-035](../../backlog/tasks/LG-035.md) 图片/PDF OCR 与正式版本 | §3.1 派生/正式分层、§7.6 不覆盖校订、§4.1 失败诚实 | 机器提取件 + 人工正式版本分离；`source_version` 关联 | LG-034 |
| [LG-036](../../backlog/tasks/LG-036.md) 词法索引与回源 | §5.3 查询、§7.3 权限回源、§7.5 失效、§8.1 | `GET /search`；可重建词法缓存；`source_stale` | LG-034、LG-035 |
| [LG-037](../../backlog/tasks/LG-037.md) 可选向量 | §8.2 向量边界、§8.3 端点事实、§5.3 权限 | `vector.disabled/indexed/stale/unavailable`；模型版本记录；词法降级 | LG-033、LG-036 |
| [LG-038](../../backlog/tasks/LG-038.md) Chat/Files 整合 | §2.1 Chat 入口、§5.1 回执、§9.2 迁移 | Chat 上传/拖拽/链接记录；Files 同源状态；不重复入口 | LG-013、014、034、036 |
| [LG-039](../../backlog/tasks/LG-039.md) 中文 ASR 验证 | §8.2 能力区分、§0 未验证项 | 后端/许可/预算结论；CER 等指标；**合成不替真人声** | LG-033 |
| [LG-040](../../backlog/tasks/LG-040.md) 集中验收 | 全稿验收要求 | 独立 QA：真实上传/归属/OCR/校订/检索/重处理/撤销/重建/降级 | LG-035/036/037/038、LG-022 |
| [LG-041](../../backlog/tasks/LG-041.md) 中文转写接入 | §8.2、§7 一致行为 | 转写+时间戳+后端版本+来源哈希；独立版本 QA | LG-039、LG-034、LG-036 |

**关键排序与降级**：

- **向量故障降级**：LG-037 的向量后端不可用/损坏时，**词法检索与原件查看必须仍可用**（docs/06 §6.1）。
- **中文 ASR 不阻塞**：LG-039 质量门失败**不阻塞** LG-040（图片/PDF/词法/可选向量版本）；LG-041 仅在 LG-039 **质量达标**后实施。
- **embedding ≠ OCR/转写**：LG-037 不依赖 LG-039/LG-041；OCR/ASR 成文与向量检索是两条通路。
- **合成样本不充质量验收**：LG-035/LG-037/LG-039 的质量判据必须用固定真值 + 授权真实样本；探针合成小样本**只作**已有证据，不作产品验收。

---

## 11. 验收条件对应（来自 [backlog/tasks/LG-033.md](../../backlog/tasks/LG-033.md)）

- [x] 来源记录、原件/机器提取/人工正式版本、摄取作业、受控收件区、回执及查询接口；与 Task/Run 分离 → §2、§3、§4、§5
- [x] 幂等请求与来源版本、跨 Task 去重不合并权限、撤销与删除、重处理不覆盖人工校订、恢复与取消 → §7
- [x] 索引/向量模型版本、内容哈希、更新失效与可重建缓存边界；权限和归属不可只存在索引 → §7.3、§8
- [ ] 按 docs/08 §13 冻结新增 schema/API 并升版 → **本稿未做，留给 docs/08 owner**（§9.2、§12）
- 附加覆盖（任务派工要求）：JSONL 历史（§3.1）、Chat 统一接入（§2.1/§5.1）、Files 整理追溯（§5.3/§10）、
  上传不创建交付 Task/Run（§2.1）、具体 schema/端点/事件/错误/迁移/反例（§3–§9）、034～040 分包接口（§10）、
  受控摄取写授权与工程写边界（§2）、向量降级（§8.2/§10）、中文 ASR 不阻塞（§10）、
  端点事实（§8.3）。

---

## 12. 交付给 docs/08 owner 的最小接入简报

1. **冻结清单（建议顺序）**：
   1) 新实体 `source` / `intake_job`（或等价物）字段与 `kind` 登记（docs/08 §6 新增小节 + §3.1 ID 前缀）；
   2) 新端点登记进 §4.3 表（`sources`/`search`/`intake`/`inbox`）；
   3) 新事件类型登记进 §5.1（MINOR）；
   4) 新错误码（若采纳 `source_conflict`/`source_stale`/`index_unavailable`）登记进 §4.2；
   5) 状态/生命周期迁移表（摄取层，**不改** §6.1 Task phase 枚举）；
   6) §13 变更记录新增 MINOR 行 + `CONTRACT_VERSION` 升 MINOR；
   7) 同步 `backend/lightgravity/contracts/constants.py`、`tests/contracts`、README、PROJECT、agent.md、docs/06、docs/09。
2. **共享冲突**：docs/08 同时被 LG-028（去中心化）修改；**单一 owner 串行**冻结两稿，先合并不冲突的加性面，再处理 §4.3/§6 共享段落。
3. **不可弱化的语义**（冻结文本必须保留）：§2 写边界、§7.2 去重不并权限、§7.3 权限只在文件 SoT、§7.6 不覆盖校订、§7.7 不自动重放/未确认不取消、§8.2 向量可选且不等于文字、§9.3 反例。
4. **可改名项**：字段名、枚举拼写、端点路径、目录命名、是否单实体——改名不影响语义验收。
5. **本稿非实现**：不宣称任何能力已实现；LG-034～041 全部仍 `todo`；LG-033 保持 `in-progress` 等待串行冻结。
