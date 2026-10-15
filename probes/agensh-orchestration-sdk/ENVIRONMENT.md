---
title: "agensh SDK orchestration experiment — environment diagnostics (read-only)"
doc_type: environment-diagnostic
category: engineering
experiment_id: agensh-sdk-20261015
branch: experiment/agensh-sdk-20261015
worktree: /tmp/lightgravity-worktrees/agensh-sdk-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
generated_at_utc: "2026-10-15"
status: offline-only; no model calls, no SDK session started
---

# 环境诊断报告（只读、离线）

> 本回合**没有**发起任何真实模型请求，**没有**启动 `localharness`，**没有**读取 `.env`
> 或任何凭证文件，**没有**打印环境变量值。所有结论来自 `import`/`inspect`、版本元数据、
> 文件哈希与现有已提交/未跟踪证据的只读阅读。

## 1. 解释器与运行时

| 项 | 实测值 | 来源 |
|---|---|---|
| Python | `3.12.13` (CPython) | `python -V` |
| venv 解释器 | `/home/yhvh/code/lightgravity-bot/.venv/bin/python` | `readlink`/`sys.executable` |
| 实际解释器目标 | `/home/yhvh/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12` | `readlink -f` |
| Node | `v22.23.2`（本实验不依赖） | `node -v` |
| 平台 | `linux-x86_64` | `platform` |

worktree 本身**不新建 venv**；诊断使用主仓库既有 `.venv`，通过
`PYTHONPATH=<worktree>/backend` 只读导入 worktree 源码（已验证
`lightgravity.adapter.__file__` 指向 worktree）。

## 2. 关键包版本

| 包 | 版本 |
|---|---|
| `google-antigravity` | `0.1.22`（dist-info: `google_antigravity-0.1.22.dist-info`） |
| `pydantic` | `2.14.1` |
| `protobuf` | `7.36.2` |
| `websockets` | `16.1.1` |
| `pytest` | `8.4.2` |

`SDK_PINNED_VERSION="0.1.22"`（`backend/lightgravity/adapter/capabilities.py:22`）与安装版本一致；
`installed_sdk_version()` 实测返回 `0.1.22`，无 “differs from pinned” 告警。

## 3. SDK 运行时二进制

| 项 | 值 |
|---|---|
| 路径 | `.venv/lib/python3.12/site-packages/google/antigravity/bin/localharness` |
| 类型 | ELF 64-bit LSB, x86-64, statically linked, stripped |
| size | 131,326,296 bytes |
| sha256 | `65a96a2a11c9169f3f1cc9a2da71718112a35a0a8be43e7f286633d48ee5ecd3` |
| 发现顺序 | `ANTIGRAVITY_HARNESS_PATH` env → 传入 env → dist files → importlib.resources → PATH（`connections/local/local_connection.py:772-827`） |

Agent loop、工具执行、重试、预算执行**都在该 Go 二进制内**；Python SDK 只负责 pydantic
配置 → protobuf `HarnessConfig` → stdio 握手 + WebSocket 事件流。

## 4. 关键源码哈希（只读基线，供协议冻结引用）

产品代码 @ `HEAD 9987d4f`（`git show HEAD:<path> | sha256sum`）：

| 文件 | sha256 |
|---|---|
| `backend/lightgravity/adapter/executor.py` | `25968f433f3abf016c8fab6c1af807395ecf8bc2e3d6efcf14a3ab9896c15829` |
| `backend/lightgravity/adapter/proxy.py` | `8b6171eb6557253c352d2def005c7ad4c106ffe054a9e2a215f65430b23cd6da` |
| `backend/lightgravity/adapter/sdk_config.py` | `628567bb3ce506057d43bc1c392a8a928b7c09c16d999823f4bf5addcdba4abc` |
| `backend/lightgravity/adapter/compiler.py` | `300df36c1016a1e9b4f89d9bf790ea567da00467c88af2f0d8a213ad1e7e58a7` |
| `backend/lightgravity/adapter/registry.py` | `8e5605e56d90675bd1bc0dcf0f38607bd542be75ec87c486ddd3ae8b1bd75257` |
| `tests/adapter/evidence/lg006-real-evidence.json` | `3c783558d0b009bfb8f51890620e3c276ee3b1cc30f3806573472857abb4b366` |

已安装 SDK 源码：

| 文件 | sha256 |
|---|---|
| `.../google/antigravity/connections/local/local_connection.py` | `fc93083761dc15d33dcc90f6e5484252c90bd313417884b76cc61066b50bfff1` |
| `.../google/antigravity/types.py` | `bd26bea3cec522cb6a877ce58c99c40f0c60194353162a6083a61c86c4885687` |
| `.../google/antigravity/agent.py` | `0b4517a797cb28a8c0df64532b3ec6275b60a0806f1beea57149283647509310` |

## 5. 已验证的离线事实（本回合）

1. `from google.antigravity import Agent, LocalOpenAIAgentConfig, CapabilitiesConfig, BuiltinTools, RetryConfig, ModelAPIRetryConfig` 全部可导入。
2. `LocalOpenAIAgentConfig` 构造成功；`model_fields` 中**没有** `thinking` 字段，也**没有**
   任何 `max_tokens`/`max_output_tokens` 字段（见 INVESTIGATION §4）。
3. `LocalOpenAIAgentConfig` 默认注入安全策略
   `[confirm_run_command(): deny run_command, allow *]`，因此开启写工具时
   `Agent.__aenter__` 的 “write tools without policy” 检查通过。
4. `BudgetConfig(max_model_calls=...), RetryConfig(api_retry=ModelAPIRetryConfig(max_retries=0))`
   可构造；config 对象（pydantic v2，非 frozen）**可赋值** `retry_config`。
5. `google.antigravity.types` 暴露 `BudgetConfig` / `SessionContinuationMode`（顶层 `ag.*`
   不导出这两个名字），`sdk_config.py:135` 正是从 `types` 模块取用。
6. worktree `experiment/agensh-sdk-20261015` 已创建于 base `9987d4f`，`git status` 干净；
   主工作区未受影响（`M PROJECT.md` 与两个旧 `probes/*` 未跟踪目录保持原样）。

## 6. 本回合明确未做

- 未调用任何模型、未启动 harness、未联网。
- 未读 `.env`/`secrets/`/`bot-data/`，未打印 `DEEPSEEK_API_KEY` 值（仅在环境中确认变量名存在）。
- 未运行 driver，未实现任何 driver。
- 未 commit / push / merge / deploy；未删除任何文件或进程。
