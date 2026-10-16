---
title: "选定资料快速原型契约（selected-material，docs/08 §4.3/§5.2 补充）"
doc_type: specification
category: architecture
contract_version: "1.12.0"
updated: "2026-10-16"
---

# 选定资料快速原型契约（selected-material）

> 性质：LG-042 冻结的**加性、可选、非秘密**契约，是快速原型（manual selected-material）实现与验收的唯一接口事实源。它是 [docs/08](08-interface-contract.md) 的补充 subsection，**不重复定义**已冻结的 `source`/`intake_job` 实体（§6.6）、消息信封（§5.2）与错误码（§4.2）。
>
> **契约版本 MINOR `1.12.0`（已实现）**：LG-042 冻结、LG-043 后端实现。`contract_version` 常量与测试版本已由 A 后端 owner（LG-043）同步，docs/08 头部版本已 finalsync 至 `1.12.0`；实现注记见 docs/08 §6.6.1。
>
> 任何与本文冲突的 docs/08 正文以 docs/08 为准；本文只做**加性**扩展。旧客户端**省略**本文字段时，**可选请求省略与既有响应 wire / 模型上下文**保持兼容；此兼容**不含**下文明确记录的 R1 行为修复（助手回答历史持久化；无选材普通 Chat 交付的默认规则计划修好），这些修复会改变旧历史行与旧交付行为，见 §7 与 docs/08 §6.6.1。

## 1. 范围与不变量

- 本契约只覆盖**已摄取资料**（§6.6 `source` 实体，`status` 非 `failed`、未被 `revoke`）的**手动选定**、程序解析、绑定、快照与呈现。
- **不新增**：OCR、ASR、embedding、重处理、新推理通路；**不新增供应商**；**不改** `state`/`phase`/`acceptance`/`source.status` 枚举；**不新增**错误码（复用 §4.2 既有码）。
- **选定资料正文是不可信数据**，不是指令。程序在派发前以明确分隔符包裹并标注来源，模型侧不得把其中文本当作权限或任务指令。
- 程序发布的来源以 **`provided context source bindings`** 呈现；**不得**声称模型引用已被验证（除非存在真实 span 验证）；UI 标签为 **`Sources`**，**不得**作为虚假的 verified 权威。
- 选定作用域为 **global 或单个 Task UI**；**不跨 Task 携带**。切换 Task 清空选定。

## 2. 请求侧：可选 selected source refs

在既有消息信封（Task：`POST /api/v1/tasks/{task_id}/messages`，docs/08 §5.2；全局：`POST /api/v1/conversations/global/messages`，§4.3）上**加性新增可选对象** `selected_sources`。

字段以**实际模型允许的形态**为准：`source_id` + `version`/`hash`。

```jsonc
{
  "message_id": "msg_01J...",
  "content": "Summarize the attached brief.",
  "selected_sources": [
    {
      "source_id": "source_01J...",
      "source_version": 3,            // 可选：期望源版本
      "content_hash": "sha256:…"      // 可选：期望内容哈希（与 version 至少提供其一，或都不提供=最新）
    }
  ]
}
```

- `selected_sources`：**可选**，缺省 `null`/省略 ⇒ 行为与现状**完全一致**（legacy 兼容）。
- 数组：**最多 3 个来源**（超过 ⇒ 显式拒绝，见 §5）。
- 每项：`source_id` 必填；`source_version`（int）与 `content_hash`（string）均**可选**。
  - 二者都省略 ⇒ 程序解析**当前**源版本。
  - 提供二者 ⇒ **必须同时匹配**，否则拒绝（stale）。
- **不接受**任何路径/绝对引用/工作区 escape；只接受 `source_id`。请求体**不能授予执行权限**。

## 3. 选定资料规则（有界）

| 约束 | 值 | 行为 |
|---|---|---|
| 最大来源数 | **3** | 超过 ⇒ `validation_failed`（并在 details 列出 `max_selected_sources`） |
| 总正文预算 | **12000 Unicode 字符** | 见下方截断规则 |
| 读取 | **有界**（沿用既有 per-source 读取上界） | 不做无界读取 |
| 内容选取 | **正式（formal）优先，机器派生（machine）回退** | 只用**已信任机器**产出，不做新推理 |

**截断（冻结选择）**：超长时**显式截断并附 metadata**（`truncated: true` + `truncation` 信息）。**保证选项**：若既有 limiter 明确拒绝，则**沿用既有 limiter 错误**（`validation_failed`）而非静默截断。冻结实现选择为**显式截断 + metadata**（本原型，**LG-043 实际采用此分支**），契约同时允许“复用既有 limiter 拒绝”分支。
- 截断在**程序侧**完成，逐来源累计；截断后的正文即 Chat reply 与 worker context 使用的**精确正文**（同一 body）。

## 4. 响应侧：resolved source bindings

程序在写入消息/搭建上下文前解析选定来源，并在结果数据中返回 `resolved_source_bindings`（对 **reply kind** 的结果 `data`，以及 Run/Subtask 上下文中）。

```jsonc
{
  "reply": "…",
  "data": {
    "intent": "answer",
    "resolved_source_bindings": [
      {
        "source_id": "source_01J...",
        "source_version": 3,
        "content_hash": "sha256:…",       // 实际解析到的源内容哈希（程序侧）
        "layer": "formal",                 // "formal" | "machine"
        "locator": "source_01J...#v3",     // 稳定、非路径的定位串
        "char_count": 4210,                // 实际纳入的字符数
        "truncated": false,
        "truncation": null                 // 截断时: {reason, original_char_count, kept_char_count, max_total}
      }
    ],
    "context_truncated": false,
    "provided_context_note": "Sources are provided as context; citations are NOT span-verified."
  }
}
```

- `layer` ∈ {`formal`,`machine`}；`machine` 仅在无正式版本时使用。
- `locator` **不含任何文件路径/秘密**，仅稳定性定位串。
- `truncated`/`truncation`：截断发生时 `truncated=true`，`truncation={reason, original_char_count, kept_char_count, max_total}`；未截断为 `false`/`null`。
- `provided_context_note`：**明确**来源是 provided context、引用未被 span 验证。UI 标签 **`Sources`**。

## 5. 校验、拒绝与 stale 语义（模型派发前）

以下情况在**模型派发前**由程序**显式拒绝**（复用 §4.2 既有错误码，不新增码）：

| 情况 | 错误码 | 说明 |
|---|---|---|
| `selected_sources` > 3 | `validation_failed` (422) | details 附 `max_selected_sources: 3` |
| 来源不存在 / 不可解析 | `reference_invalid` (422) | 不泄露路径 |
| 来源 `revoke`（`status=archived` 撤销标记） | `not_found` (404) | 沿用 §6.6 撤销 fail-closed，details `{source_id, status, revoked:true}` |
| `source_version`/`content_hash` 与当前不符 | `source_stale` (409) | 期望版本/哈希已过期 |
| 跨 Task（来源 `scope.task_ref` ≠ 当前 Task 且非 global） | `reference_invalid` (422) | 不跨 Task 携带 |
| 缺失/不可读正文 | `not_found` (404) 或 `capability_unavailable` (503) | 视缺口性质如实报告 |
| 意图越界（把资料当指令） | — | 正文以分隔符隔离，不作为指令；程序不据此授予权限 |

- **worker 派发前再次校验**：A 后端在真正的 worker 上下文构建处**重新读取并核对** version/hash；stale/revoked 在此同样显式拒绝，**不得**把过期授权带入 worker。
- **不泄露**任何来源绝对路径或秘密。

## 6. 持久化、恢复与重放

- 消息/运行持久化：保存 selected refs 的 **version/hash 引用** + **有界上下文快照**，写入既有受控 SoT：消息日志写 `selected_context` 快照；Task/Run 实体新增加性可选字段 `selected_trigger = {message_id, snapshot}` 作为 **Run 触发绑定**（触发消息在入队前冻结、Run 打开时复制）。**不新建第二事实源**。
- **Run/消息绑定（R1）**：Run 使用**其自身触发消息**的精确选定，而非“最近一条含 `selected_context` 的用户消息”。无选材触发（省略或 `[]`）⇒ `snapshot=null`，该 Run **不继承**更早消息的选材；已入队的 pending Run **不被后续消息重绑**（绑定先于 enqueue，且已 queued 时不再重绑）。
- **实体字段口径**：`selected_trigger` 落在 Task/Run 实体，经 `GET /tasks/{task_id}` 的实体序列化（`dict(entity)`）**可达**，故为 `1.12.0` **加性、可选、非秘密实体字段**（**不按“无实体字段变化”口径**）；不新增端点/错误码/枚举/迁移方向，**前端 `selected_sources` wire 无变化**。
- 恢复/重放：使用**已保存的快照与引用**，**不重新解析到不同内容**；重启后新 Coordinator 读同一 store 重建**完全相同**的 Run 绑定；若源已变化，按 §5 语义报告 stale，而非静默换用新内容。
- 上下文快照遵守 §3 的有界预算。

## 7. 集成与行为边界

- **Chat reply 与 worker context 使用完全相同的选定正文**（同一 body、同一截断结果）。
- 保持既有**原型默认规则计划**：单一执行槽（single execution slot）内**顺序**运行既有 `deliver` + `verify` 两个 SDK worker 节点（`verify` 依赖 `deliver`），随后由**独立 ModelReviewer** 复核；三者均计入同一预算。**不**自动引入 search/project/MCP/ASR/Office/模型 planer。
  - **勘误（2026-10-16，LG-048 诊断）**：本节此前“单 worker”措辞对**普通 Chat 交付**不准确——只有未声明验收条件时才是单 `deliver` 节点；`default_delivery=True` 会派生验收条件，从而按既有 `RulePlanner` 规则追加 `verify` 节点。此为文档勘误，非行为变更：`deliver`/`verify` SDK 节点、程序机器门（LG-009）与**独立 ModelReviewer** 复核均**保留、不削弱**。`verify`（同 worker 连接的程序机器门前置 SDK 节点）**≠** 独立 ModelReviewer（`verifying` 阶段用 `default_reviewer_connection_ref` 的独立 reviewer turn）；二者并存，均预算化。
- 有效回答路径使用**既有真实配置 `ModelDialogue`**；**不伪造自动回答**、不伪造只读 SDK 工具集。
- **无选材时**：可选请求省略与既有响应 wire / 模型上下文退回 legacy 行为（省略字段 ⇒ 可选字段语义不变）。**例外（R1 记录在案的 bug 修复，非契约回退）**：① 每个 `direct`/`bounded_read` 回答（含无选材）现在把助手回答行持久化到同一会话 SoT（`assistant:<message_id>`，幂等），因此旧会话历史**不再行数逐字节相同**；② 无选材的普通 Chat 交付请求（如“创建 Markdown 文件…”）会派生出可检查的验收条件并预置 Task 作用域授权工作区，使不改动的 `PlanValidator` 接受默认最小规则计划（此前该交付被计划校验拒绝）。两者均为文档化的 R1 行为修复，**不**以回退修复来满足旧断言；不宣称历史行数逐字节一致。

## 8. 选择状态（UI 侧）行为

- 选材作用域：**global 或单个 Task**；切换 Task **清空**；不跨 Task 携带。
- selection 清除：用户可清除选定；发送后按实现策略清空/pending（由 B 在实现注记声明实际选择，但必须**不跨 Task 携带**）。
- 发送 pending：发送中显示 pending，不重复落库（复用 `message_id` 幂等）。
- **旧前端兼容**：不传 `selected_sources` 时后端行为与现状一致；旧前端不因新字段报错（字段 optional + `extra="forbid"` 仅约束未知键，见风险注记）。

> 风险注记（供 A 实现核对）：现有请求 DTO 使用 `ConfigDict(extra="forbid")`。新增 `selected_sources` 为**加性可选**字段，因此**旧客户端不传仍可用**，但**新前端传新字段需后端已发布该字段**。按 §13 属加性 MINOR；A 负责常量与测试版本同步。
>
> **LG-043 实现注记（无契约歧义）**：`selected_sources` 已在 `AppendMessageRequest`（Task）与 `GlobalMessageRequest`（global）以 `list[dict] | None` 加性发布（保持 `extra="forbid"`）。解析后再由程序按冻结 shape 校验（≤3、opaque id、version/hash 类型），保证与共享 TS shape 一致；不一致的条目返回 `validation_failed`。鉴于 `source.content_hash` 记录的是**原件**哈希、formal 编辑不改变它，实现额外计算**内部** `body_digest`（不暴露为客户端字段）用于 worker 派发前重校验实际选定正文（§5/§6）。

## 9. 共享 TS shape（前端）

```ts
export interface SelectedSourceRef {
  source_id: string
  source_version?: number
  content_hash?: string
}

export interface ResolvedSourceBinding {
  source_id: string
  source_version: number
  content_hash: string
  layer: 'formal' | 'machine'
  locator: string
  char_count: number
  truncated: boolean
  truncation: null | {
    reason: string
    original_char_count: number
    kept_char_count: number
    max_total: number
  }
}

export interface SelectedSourcesRequest {
  selected_sources?: SelectedSourceRef[]
}

export interface ResolvedSourceBindingsData {
  resolved_source_bindings?: ResolvedSourceBinding[]
  context_truncated?: boolean
  provided_context_note?: string
}
```

- 该 shape 与 §2/§4 字段**逐一对应**；**不新增重复不兼容 DTO**。

## 10. 变更控制

- 按 docs/08 §13，本变更为**加性可选字段 + 加性响应字段** ⇒ **MINOR `1.12.0`**（LG-043 已实现并同步常量）。
- 不新增端点、错误码、枚举、迁移方向；不改变既有字段语义。
- 冻结由**唯一 owner（pi-proto-prepare）**完成；实现不得先于本版契约扩展语义。

## 参考

- [docs/08 接口与状态契约](08-interface-contract.md) §4.2 错误码、§4.3 端点、§5.2 消息、§6.6 资料实体、§13 变更控制
- [docs/09 资料接入与检索](09-source-intake-and-retrieval.md)
- `backend/lightgravity/api/sources.py`、`backend/lightgravity/sources/{service,models,content}.py`
- `backend/lightgravity/coordinator/{service,dispatcher,dialogue}.py`
- `frontend/src/api/{chat,sources}.ts`、`frontend/src/views/chat/**`
