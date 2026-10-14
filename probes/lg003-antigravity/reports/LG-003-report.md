---
title: "LG-003 Antigravity SDK 核心能力探针报告"
doc_type: report
category: sdk
task: LG-003
executor: agent:pi-lg003
updated: "2026-10-15"
status: verified-with-limitations
---

# LG-003 — Antigravity SDK 核心能力探针报告

> 执行者 `agent:pi-lg003`，工作区 `/tmp/lightgravity-worktrees/lg003`（独立 worktree，分支 `dev/lg003`）。
> 性质：本报告是探针证据记录，不代表产品功能、adapter 或首版 Gemini 契约已完成验收。
> 所有真实模型调用均有界且最小；凭证值从未写入探针、日志或本报告。

## 1. 结论摘要

- 固定安装 **`google-antigravity==0.1.22`**（PyPI 分发名；上游仓库 `google-antigravity/antigravity-sdk-python`，Apache-2.0），x86_64 Linux 平台 wheel，随包原生 runtime `localharness` 实际启动并完成会话握手。
- **核心能力已用真实模型（DeepSeek）实测通过**：文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content`，以及真实报告的沙箱状态。
- SDK 是 **Gemini 优先**库（依赖 `google-genai`，默认模型 `gemini-3.8-flash`）。本环境**没有 Gemini/Google 凭证**，因此产品首版 Gemini 后端路径（Developer API / Vertex）**未验收**；这是唯一实质性阻塞项。
- 在本环境可用凭证下，SDK 真实支持的可达后端是 **OpenAI-compatible 本地端点**（`LocalOpenAIAgentConfig`，即 "Gemma endpoint"）。该端点配置**只有 `base_url`、没有 api_key 字段**，因此接入 DeepSeek 需外部注入 bearer token；探针用一个本地认证代理完成，模型响应来自真实远程模型。
- `search_web` 通过该非 Gemini 端点**被调用但返回无可结果**，实际不可用；已如实记录。
- 产品首版 Gemini 契约**未被修改**；DeepSeek 只是探针可达路径，不改变首版后端选择。

## 2. 环境与版本

| 项 | 值 |
|---|---|
| SDK 分发 | `google-antigravity` **0.1.22**（固定） |
| 平台 wheel | `google_antigravity-0.1.22-py3-none-manylinux_2_17_x86_64.musllinux_1_1_x86_64.whl` |
| 原生 runtime | `google/antigravity/bin/localharness`，131,326,296 bytes，sha256 `65a96a2a11c9169f3f1cc9a2da71718112a35a0a8be43e7f286633d48ee5ecd3` |
| Python | 3.12.13（`.venv` 由 uv 独立创建） |
| uv | 0.12.1 |
| 平台 | Linux 7.0.0-28-generic x86_64, glibc 2.43 |
| 关键依赖 | google-genai 2.30.1、pydantic 2.14.1、mcp 2.3.0、uvicorn 0.54.0、websockets 16.1.1、protobuf 7.36.2、absl-py 2.5.1 |
| 可用凭证 | `DEEPSEEK_API_KEY` = 有；`GEMINI_API_KEY` / `GOOGLE_API_KEY` / `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CLOUD_PROJECT` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` = 无 |
| 证据 | `evidence/p01_environment.json` |

完整依赖解析见 `probes/lg003-antigravity/uv.lock`（独立于根 `uv.lock`）。

## 3. 方法与可复现性

探针位于 `probes/lg003-antigravity/`，独立 `pyproject.toml` / `uv.lock` / `.venv`，不进入产品 import 路径。

```bash
cd probes/lg003-antigravity
uv lock && uv sync
./scripts/run_all.sh                 # 离线探针 + canned 事件自测
LG003_LIVE=1 ./scripts/run_all.sh    # 追加有界真实模型探针（需 DEEPSEEK_API_KEY）
```

真实模型用量有界：每次运行最多 30 次上游调用（代理计数硬上限），本轮全部场景合计 **19 次**真实模型调用；canned 自测不产生模型费用。代理只在内存读取 `DEEPSEEK_API_KEY`，不打印、不落盘。

### 实际命令 / 退出码 / 产物

| 命令 | 退出码 | 产物 |
|---|---|---|
| `uv lock` | 0 | `uv.lock`（Resolved 48 packages） |
| `uv sync` | 0 | `.venv`（google-antigravity 0.1.22 + 依赖） |
| `uv run python scripts/p01_environment.py` | 0 | `evidence/p01_environment.json` |
| `uv run python scripts/p02_offline_capabilities.py` | 0 | `evidence/p02_offline_capabilities.json` |
| `uv run python scripts/p03_runtime_handshake.py` | 0 | `evidence/p03_runtime_handshake.json`（stderr 含预期凭证异常栈） |
| `uv run python scripts/p04_canned_events.py --port 18083` | 0 | `evidence/p04_canned_events.json`、`p04_proxy_requests.jsonl` |
| `uv run python scripts/p05_live_deepseek.py --scenario {text,file,structured,budget,cancel,resume}` | 全 0 | `evidence/p05_live_*.json`、`p05_proxy_requests.jsonl` |
| `uv run python scripts/p06_skills.py --scenario {file,inline}` | 全 0 | `evidence/p06_skills_*.json` |
| `uv run python scripts/p07_web_tools.py --scenario {read_url,search_web}` | 全 0 | `evidence/p07_web_*.json` |

耗时（wall）：text 1.3s、file 5.3s、structured 1.1s、budget 1.8s、cancel 2.6s、resume 3.4s；离线探针各 < 10s。全部探针进程在结束后终止，未留 `localharness` / 代理进程。

## 4. 真实支持的后端与配置（安装版本实测）

`HarnessConfig.ModelConfig` 端点为 proto 字段：`gemini_api_endpoint | vertex_endpoint | gemma_endpoint | custom_endpoint`。安装版本公开配置映射：

| 后端 | 配置入口 | 认证 | 本环境状态 |
|---|---|---|---|
| Gemini Developer API | `LocalAgentConfig(api_key=...)` / `GeminiAPIEndpoint` | `GEMINI_API_KEY` 或 `api_key` | **未验收**（无凭证；会话启动抛 `AntigravityValidationError`） |
| Vertex AI | `LocalAgentConfig(vertex=True, project=, location=)` / `VertexEndpoint` | project+location 或 api_key | **未验收**（无凭证） |
| OpenAI-compatible 本地端点 | `LocalOpenAIAgentConfig(base_url=, model=)`（"Gemma endpoint"） | **无 api_key 字段**，仅 `base_url` | **实测可达**（DeepSeek），需外部注入 bearer |
| LiteRT 端侧 | `LiteRTAgentConfig` / `LiteRTBackend` | — | 未测试（首版范围外） |
| `custom_endpoint` | proto 存在，公开配置未暴露 | — | 未探索 |

证据：`evidence/p02_offline_capabilities.json`
（`gemini_endpoint_no_key`、`vertex_endpoint_no_auth`、`openai_endpoint_requires_base_url`、`proto_gemma_endpoint_fields: ["base_url"]`）。
`LocalOpenAIAgentConfig` 在 0.1.22 顶层导出（`google.antigravity.LocalOpenAIAgentConfig`，在 `__all__` 中），定义位于 `google.antigravity.connections.local.local_openai_connection_config`。

**认证阻塞**：`LocalOpenAIAgentConfig` 的 endpoint 只有 `base_url`。为让真实模型调用可行，探针用 `scripts/openai_compat_proxy.py` 在本地 `127.0.0.1` 转发到 `https://api.deepseek.com/v1/chat/completions` 并注入 `Authorization: Bearer`。这是认证/传输适配，不是模型 mock；回答来自真实 DeepSeek。
> 集成含义（待 LG-006/LG-025 处理）：若产品坚持 Gemini 首版契约，则无需该代理；若未来支持非 Gemini 后端，adapter 必须解决凭证注入，不能依赖 SDK 原生 api_key（该字段不存在）。

## 5. 能力验证结果

| 能力 | 结果 | 证据 |
|---|---|---|
| SDK/runtime/平台版本 | 已记录 | `p01_environment.json` |
| 原生 runtime 启动/会话握手 | 通过（`started=true`、`is_idle=true`） | `p03_runtime_handshake.json` |
| 实际沙箱状态 | 通过：`SandboxStatus(available=true, unavailable_reason=null)`，在 `enable_sandbox=True` 下握手即报告 | `p03`、`p04` |
| skills — 文件 `SKILL.md` | 通过：模型读取 skill 并回答标记 `banana-77` | `p06_skills_file.json` |
| skills — inline | 通过：模型调用 `skill_lookup` 并回答标记 `mango-31` | `p06_skills_inline.json` |
| skills 路径与 inline 互斥 | 通过：两者同设抛 `ValidationError` | `p02_offline_capabilities.json` |
| 文件操作 | 通过：真实创建 `hello.txt` 内容 `hello-lg003`，并 `edit_file`/`view_file` 工具事件可见 | `p05_live_file.json` |
| 网页工具 `read_url_content` | 通过：抓取本地 URL 并回报标记 `WEB-TOOL-MARKER-9f3` | `p07_web_read_url.json` |
| 网页工具 `search_web` | 被调用但**不可用**：返回 "no usable results / redirect note" | `p07_web_search.json` |
| 结构化输出 | 通过：`response_schema` 注入 finish tool，返回 `{"summary": "The probe ran.", "risk_level": 1}` | `p05_live_structured.json` |
| 工具事件 | 通过：`ChatResponse.tool_calls` 实时产出 `ToolCall`（file/read_url/skill_lookup） | `p05_live_file.json`、`p06`、`p07` |
| 取消 | 通过：`resp.cancel()` 中断在途上游连接（代理记录 `BrokenPipeError`），会话回到 idle | `p05_live_cancel.json`、`p05_proxy_requests.jsonl` |
| 预算停止 | 通过：`BudgetConfig(max_model_calls=1)` → `StopReason.MAX_MODEL_CALLS_EXCEEDED` | `p05_live_budget.json` |
| 保存/恢复 | 通过：`save_dir`+`conversation_id`+`SessionContinuationMode.RESUME` 跨进程恢复并回忆 `zebra-4271` | `p05_live_resume.json` |
| 用量/停止原因 | 通过：`usage_metadata`（prompt/candidates/total）与 `stop_reason` 可取得 | `p05_live_*.json` |
| 流式解析（离线自测） | 通过：canned SSE → 文本 `pong`、usage 解析 | `p04_canned_events.json` |

### 配置面结论（离线）

- `CapabilitiesConfig` 的 `enabled_tools` / `disabled_tools` 互斥；`enable_subagents=False` 时禁止 `max_subagent_depth`/`allowed_subagents`。
- 默认工具集（`BuiltinTools.default()`）：`view_file, create_file, edit_file, run_command, invoke_subagent, run_workflow, generate_image, search_web, read_url_content, schedule, finish`；`list_directory/search_directory/find_file` 默认关闭（deprecated）。
- `LocalAgentConfig` 默认策略为 `run_command` DENY + `*` APPROVE；写工具无策略时启动会拒绝（安全护栏）。
- 模型面向的工具名与 SDK 名映射：`write_to_file`/`replace_file_content`/`manage_task`/`run_command`/`view_file`（见代理请求记录），adapter 需按此映射统计工具事件，而非直接用 `BuiltinTools` 值。
- 预算/重试/结构化/session 续接模式（`resume|create_or_resume|create_only`）均可配置。

## 6. 未验收 / 阻塞项（如实记录）

1. **Gemini Developer API 与 Vertex 后端未验收** — 本环境无 `GEMINI_API_KEY`/Vertex 凭证；会话启动在无凭证时抛 `AntigravityValidationError`（`p03`）。产品首版契约要求的 Gemini 路径必须由具备凭证的环境重跑本探针后才能宣称支持。
2. **`search_web` 不可用** — 在 OpenAI-compatible / 非 Gemini 端点下被调用但无结果，疑似依赖 Gemini 搜索能力。
3. **SDK 内部 subagents、workflows、MCP、Triggers、多模态、图像生成** — 首版默认关闭或范围外，本轮未做真实调用验证；`p02` 仅确认配置可解析。
4. **沙箱“强制隔离”未做逃逸验证** — 只确认 runtime 报告 `available=true`；未验证命令确实被 exebox 约束。
5. **`custom_endpoint`** proto 字段未在公开 Python 配置中暴露，未探索。
6. **仅 x86_64 Linux 平台 wheel 实测**；其他平台 wheel 未验证。

## 7. 集成所需改动（不擅自修改禁写路径）

以下为给整合执行者/后续任务的必要变更建议，LG-003 未改动任何产品/根依赖文件：

1. `pyproject.toml` 增加固定依赖：`google-antigravity==0.1.22`（仅在 adapter 实现后加入；平台 wheel 由 uv 自动选择 x86_64 manylinux/musllinux）。依赖链含 `google-genai>=1.0`、`mcp>=1.0,<3`、`websockets`、`protobuf`、`absl-py`。
2. `backend/lightgravity/adapter/**` 实现时须注意：
   - 唯一导入 SDK 的位置；`LocalOpenAIAgentConfig` 可由顶层 `google.antigravity` 导入（0.1.22 `__all__` 含此项）。
   - 工具事件名称需做 `write_to_file`/`replace_file_content` 等到 `BuiltinTools` 的映射。
   - 非 Gemini 后端的凭证注入方案必须显式实现（SDK 的 OpenAI/Gemma endpoint 无 api_key 字段）。
3. `docs/08` §8 的 `AdapterCapabilities` 可按实测填充：`structured_output=true`、`sandbox` 报告 `available`（本机 true）、`skills_paths` 与 `inline_skills` **不可同时**、`cancel` 可确认、session resume 可用。**未经验证的 Gemini 后端不得据此声明支持**。
4. 若采纳 DeepSeek/OpenAI-compatible 作为可选后端，属于契约变更（MAJOR/MINOR 由 LG-001 决定），本任务不自动改产品首版 Gemini 契约。

## 8. 证据索引

- `evidence/p01_environment.json`
- `evidence/p02_offline_capabilities.json`
- `evidence/p03_runtime_handshake.json`（+ `.stderr` 预期凭证异常）
- `evidence/p04_canned_events.json`、`evidence/p04_proxy_requests.jsonl`
- `evidence/p05_live_{text,file,structured,budget,cancel,resume}.json`、`evidence/p05_proxy_requests.jsonl`
- `evidence/p06_skills_{file,inline}.json`
- `evidence/p06_p07_proxy_requests.jsonl`（p06/p07 的 9 次真实调用记录）
- `evidence/p07_web_{read_url,search}.json`
- `evidence/diag_capture_initial.jsonl`（首次协议探测：请求路径 `/v1/chat/completions`、SSE 流式、无 Auth 头）

## 9. 限制与后续

- 本报告是执行者局部证据，非版本 QA 结论。核心能力已用真实模型验证；Gemini 后端符合性待具备凭证的环境或 LG-006/LG-022 复核。
- 探针环境为临时安装，已清理活动进程；`.venv` 与 `uv.lock` 保留以复现。
