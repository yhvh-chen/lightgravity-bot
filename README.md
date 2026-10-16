---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-16"
---

# LightGravity Bot

**把资料和目标交给团队 Bot，让 AI 团队执行工作、检查结果，交付你能验收的成果。**

LightGravity Bot 是面向个人与小团队的 AI 工作空间。它把资料、对话、任务与交付记录放在一起：你提出目标，系统按需组织 AI 执行者完成工作，经过检查与独立复核，再交给你决定是否验收。

基于 **Antigravity SDK** 构建执行能力，接入 **EmbeddingGemma 2** 作为可选语义检索后端。任务和资源以 Markdown 文件描述，过程与成果保存在用户掌握的文件中。

[快速开始](#快速开始) · [团队模式](#团队模式) · [技术架构](#技术架构) · [验证与当前限制](#验证与当前限制) · [文档](#文档)

> **开发预览 · 2026-10-16**：已有真实 SDK 交付与共享团队聊天的专项验证。当前用户反馈多个页面出现 `Scope not found`、`Not Found` 等加载错误，尚待定位修复；界面简化也待实施。以下介绍区分现有机制、验证范围与探索方向，不代表当前安装即可获得完整可用体验。[问题记录](PROJECT.md#2026-10-16页面不可用与界面调整反馈仅记录待实施)

## 从资料到交付

一项工作往往需要同时处理资料、上下文、执行进度和结果检查。LightGravity 围绕任务保存这些内容，让每次补充、返修和验收都有可以继续的工作记录。

```text
资料 + 目标
    ↓
对话与任务 → 按需组队 → 执行与产物
                            ↓
                     机器检查 + 独立复核
                            ↓
                       用户验收与返修
```

- **用同一份资料推进工作。** 手动选定已摄取资料，将有版本绑定的文本上下文交给对话或执行任务。
- **围绕交付组织 AI 团队。** 普通问答直接处理；需要交付时创建任务，按规则生成计划、选择角色并协调执行。
- **查看结果与检查依据。** 保留产物、代码差异、检查记录与来源绑定，支持后续补充和返修。
- **掌握自己的工作文件。** Markdown + YAML 保存任务与配置，JSONL 保存消息和事件，检索索引作为可重建缓存。

适合先在一个明确的工作区里尝试有边界的开发任务，或复现“选定资料 → 生成文件 → 复核验收”的示例。研究、文档与其他知识工作是扩展方向，具体可用范围见下方验证记录。

## 一个团队 Bot，两种协作

**人和人共享工作。** 在团队模式下，每个人使用独立账号，在同一工作区共享聊天、任务与资料。普通群聊保存为团队上下文，显式 `@bot` 才触发助手；Task 内消息按任务对话规则处理。

**AI 按任务组队。** 系统根据任务选择角色与技能，协调执行者、检查与独立复核。临时 AI 成员随运行创建和释放，工作记录与成果持续保留。人类账号与 AI 成员是两类实体。

当前团队版提供单共享工作区、管理员与普通成员角色。管理员管理账号、模型与凭证；现阶段全部团队资料共享，暂不提供私聊、私有资料或多租户隔离。

## 任务本体：让工作有明确的结构

我们用“任务本体（Task Ontology）”描述 LightGravity 的工作模型：明确有哪些对象、对象如何关联、允许哪些动作，以及完成需要什么证据。

| 对象 | 表达什么 |
|---|---|
| Task | 用户目标、需求与验收条件 |
| Run / Subtask | 一次执行尝试及其中的工作节点 |
| Role / Member | 角色模板与本次实际参与的 AI 成员 |
| Source / Artifact | 输入资料与交付产物，以及版本和来源 |
| 资源与验收记录 | 执行依赖、检查结果与用户决定 |

当前基础是显式 schema、稳定引用和程序校验的状态转换。“任务本体”是对这套结构的概括；通用本体推理、知识图谱推理与自动业务建模仍不在当前承诺内。详见 [Task 与资源契约](docs/02-task-and-sdk-resources.md)及[接口与状态契约](docs/08-interface-contract.md)。

## 向受控的自组织 Swarm 演进

我们希望探索：**多个 Agent 如何围绕共同目标分工协作，在明确权限和预算内交付可验收的成果。**

当前由程序负责计划校验、组队、依赖调度和状态写入，worker 负责执行；自主领取与协作请求默认关闭，SDK 内部委派关闭。动态组队是已有机制，**自组织 Swarm 是进一步探索的方向**。

演进中持续保留三条边界：

- 工作由明确任务和授权驱动，Agent 的角色或技能不扩大权限。
- 预算覆盖执行、验证、返修与失败尝试，成本按完整交付生命周期评估。
- 执行结果经过检查与复核，由用户最终验收；结束或中断需确认真实停止。

## 技术架构

| 层 | 技术与职责 |
|---|---|
| 工作空间 | Python 后端与网页界面，连接对话、任务、资料和团队 |
| 协调与控制 | 程序管理路由、计划校验、依赖调度、权限、预算和状态 |
| Agent 执行 | **Antigravity SDK**：承接 Agent 执行、工具调用与原生会话 |
| 当前生成模型路径 | `google-antigravity==0.1.22` → `LocalOpenAIAgentConfig` → loopback 认证代理 → **DeepSeek** |
| 可选向量检索 | **EmbeddingGemma 2** 服务：补充语义与媒体检索；未配置或不可用时保留词法检索和原件查看 |
| 持久化 | Markdown + YAML、JSONL 与 SDK 原生会话存储；索引可删除重建 |

[Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python) 提供执行基础；LightGravity 在其上连接任务、资料、团队和交付验收流程。“基于 Antigravity SDK”不表示当前生成模型使用 Gemini，Gemini / Vertex 路径尚未验收。

[EmbeddingGemma 2](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2?hl=en) 支持统一多模态向量表示。项目通过可配置服务接入，默认禁用，不绑定开发机端点。现有跨模态验证仍有质量限制，模型支持的模态不等于产品已完成全部接入；embedding 也不等于 OCR 或语音转写。

用户掌握文件与部署环境，模型请求仍会发送到所配置的服务；当前不承诺全离线推理或任意模型即插即用。

## 快速开始

### 版本要求

- Python `>=3.12,<3.13`
- uv `0.12.x`
- Node.js `22 LTS`、npm `10.x`
- GNU make（使用统一开发命令时需要）

以下在仓库根目录执行。命令沿用现有启动流程；当前页面问题见[验证与当前限制](#验证与当前限制)。

### 安装与启动

```bash
uv sync
npm --prefix frontend ci
npm --prefix frontend run build

uv run lightgravity start \
  --data-dir ./bot-data \
  --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets \
  --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/`。端口已被占用时选择其他端口。运行数据、工作区与秘密存储应使用各自目录，真实凭证不要写进仓库或对话。

### 接入模型

1. 在 **Settings → Models & Providers / Connections** 创建连接并保存凭证。
2. 测试连接，设置协调问答连接与默认 worker 连接。
3. 为交付验收配置独立 reviewer 连接；缺少可用 reviewer 时无法完成验收。

凭证通过受保护接口保存引用；模型与默认配置的详细说明见[模型设置](docs/07-settings-and-models.md)。首次尝试建议使用已有真实验证的 DeepSeek 路径。

### 尝试一条交付流程

从明确的小任务开始，例如在授权工作区内生成一份文件。检查任务状态、文件内容和复核记录，再决定验收或返修。

也可以按照[选定资料示例指南](docs/11-selected-material-demo.md)，使用[示例资料](examples/selected-material-prototype/README.md)复现资料绑定与文件交付。示例采用人工编写的样本资料，有独立真实 SDK 生命周期验证记录；它不代表所有输入类型或任务都已验证。

服务提供 `lightgravity start / status / stop` 生命周期命令；浏览器关闭或断线不会自动取消后台任务。

## 团队模式

先创建账号，口令通过交互输入：

```bash
uv run lightgravity user add --username alice --role admin --data-dir ./bot-data
uv run lightgravity user add --username bob --role member --data-dir ./bot-data
```

启动时显式开启团队模式：

```bash
LIGHTGRAVITY_TEAM_MODE=1 uv run lightgravity start \
  --data-dir ./bot-data \
  --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets \
  --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/` 登录。默认使用单用户模式；不设置 `LIGHTGRAVITY_TEAM_MODE` 即可保留该方式。

多人访问远端实例时，可在各自电脑使用 SSH 转发：

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

团队消息约每 3 秒轮询同步，后台标签页恢复可见后补齐；登录会话随服务重启失效。默认保持 loopback 监听，LAN 部署与访问限制见[接口契约](docs/08-interface-contract.md)。

## 验证与当前限制

下列是截至 2026-10-16 的专项证据，各报告的范围和限制仍适用：

| 范围 | 已有证据 | 证据边界 |
|---|---|---|
| 选定资料交付 | 原生文本上传 → SDK 执行与验证节点 → 独立模型复核 → 停止确认 → 人工验收 API；独立 QA 为 PASS_WITH_LIMITATIONS | 冻结候选上的一条完整生命周期；不代表所有任务或资料类型通过。[报告](probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md) |
| 团队协作 | 58 项真实 HTTP 检查，Firefox 双用户登录、消息互见与退出；独立 QA 为 PASS_WITH_LIMITATIONS | 该专项使用确定性 responder，未重新验证真实模型交付。[报告](probes/team-chat-20261016/qa/QA-REPORT.md) |
| 资料接入与检索 | 资料处理、检索与界面整合已有集中版本 QA | 质量样本有限，中文图片检索历史失败保留，不宣称广义跨模态质量通过。[报告](probes/lg040/TRANSITION-QA-20261016/REPORT.md) |

当前重点限制：

- **页面可用性待修复。** 用户反馈 Files、Team、Models & Providers 等页面加载失败；原因尚未核实。导航、搜索、对话框及个人／团队切换的调整已记录、待实施。
- **来源绑定不等于引用核验。** 选定资料作为提供给模型的上下文，尚未逐段验证模型引用。
- **媒体能力有边界。** PDF / 图片走显式 OCR 处理；当前无可用 ASR，中文转写待质量门通过，Office 等格式未全面实测。
- **恢复能力有边界。** 未知副作用不会自动重放；完整 checkpoint 跳过调度尚未实现。
- **部署与最终验收分开。** 本地集成和历史 QA 不代表当前服务已更新、已发布或已获用户最终验收。

## 开发与参与

欢迎围绕可复现的问题、真实任务样本和有明确验收条件的改进参与。报告问题时请附版本、重现步骤、预期与实际结果；日志中移除凭证与个人资料。

```bash
make run               # 后端，默认 127.0.0.1:8000
make frontend-dev      # 前端开发服务，默认 127.0.0.1:5173
make check             # 后端类型检查与测试
make frontend-check    # 前端类型检查与测试
make check-all         # 前后端检查
make frontend-build    # 前端生产构建
```

开发前阅读 [AGENTS.md](AGENTS.md) 与 [agent.md](agent.md)，涉及前端再读 [design.md](design.md)。运行配置示例见 [.env.example](.env.example)。依赖与复用内容的许可须按各自声明核对；上游许可不自动代表本仓库全部内容采用同一许可。

## 文档

| 入口 | 内容 |
|---|---|
| [项目手册](PROJECT.md) · [进展记录](PROGRESS.md) | 定位、决策、开发历史与已知问题 |
| [开发看板](BACKLOG.md) · [滚动排期](docs/06-roadmap.md) | 任务、依赖与阶段验收 |
| [架构设计](docs/01-design.md) · [Task 与资源](docs/02-task-and-sdk-resources.md) | 工作模型、模块边界与资源配置 |
| [SDK 审计](docs/03-sdk-capability-audit.md) · [Bot 行为](docs/04-bot-behavior.md) | 执行基础、消息路由与运行规则 |
| [导航设计](docs/05-navigation-and-team.md) · [模型设置](docs/07-settings-and-models.md) | 现有页面设计、连接与凭证；最新界面调整以项目手册反馈为准 |
| [接口与状态契约](docs/08-interface-contract.md) | 当前契约 1.13.0，API、状态、权限与变更记录 |
| [资料接入与检索](docs/09-source-intake-and-retrieval.md) | 原件、派生内容、索引与质量边界 |
| [选定资料原型](docs/10-selected-material-prototype.md) · [示例指南](docs/11-selected-material-demo.md) | 资料绑定机制与可复现流程 |

执行基础来自 Antigravity SDK，可选向量检索接入 EmbeddingGemma 2；角色内容与设计参考见 [agent.md](agent.md)。本项目的运行不依赖开发机上的 Olav OS 或 Olav Tasks 参考目录。
