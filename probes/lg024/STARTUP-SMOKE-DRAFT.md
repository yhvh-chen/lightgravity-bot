---
title: "LG-024 阶段 A 启动/安装入口烟测草案"
doc_type: draft
category: engineering
task: "LG-024"
updated: "2026-10-16"
---

# 启动/安装入口烟测草案（阶段 A，不部署）

> 基于**当前产品树实际入口**（`pyproject.toml`、`Makefile`、`backend/lightgravity/cli.py`）整理，供阶段 B 写入 README。
> **本文件不执行真实启动/模型调用**；命令为可审阅草案，实际行为以运行时为准，不宣传未实现能力。

## 1. 版本要求

- Python `>=3.12,<3.13`（`pyproject.toml`）。
- 依赖经 `uv`（`Makefile sync`）或等价虚拟环境安装。

## 2. 常用 Make 入口（工程）

| 目标 | 作用 |
|---|---|
| `make lock` / `make sync` | 锁定/同步依赖 |
| `make type` | mypy 类型检查（`backend/lightgravity`） |
| `make test` | pytest（`tests/`） |
| `make check` | type + test |
| `make run` / `make serve` | 运行服务（`serve` 先构建前端） |
| `make check-all` | 后端 + 前端检查 |
| `make clean` | 清理 |

## 3. CLI 入口（`lightgravity` / `lg`）

`backend/lightgravity/cli.py` 提供单命令式 `start / stop / status / init`：

- **`start`**：构建真实运行时并启动本机服务；默认 loopback（`127.0.0.1`）、默认端口 **8000**；
  路径选项含 `--data-dir`（默认 `./bot-data`）、`--workspace-root`、`--secret-store`、`--frontend-dist` 等。
- **`stop`**：停止由 `start` 记录的进程（SIGTERM→SIGKILL，`--timeout` 默认 10s）。
- **`status`**：报告 pid 与可选 HTTP 健康探测（`--deep`）。
- **`init`**：**唯一写配置**的命令，幂等；需 `--connection-id`，可选 `--connection-title`、`--backend`（默认 `openai-compat`）。
- Make 包装：`lg-start` / `lg-start-daemon` / `lg-status` / `lg-stop` / `lg-init`。

## 4. 敏感写与安全默认（草案要点）

- 默认 loopback 绑定；首个启动在内存握手运行时 token 并注入 `index.html`（`__LG_RUNTIME_TOKEN__`，前端 `auth.ts` 自动带 `X-LG-Token`）。
- 敏感写（`LocalAccessPolicy`）**默认拒绝**；缺认证可读历史/设置。
- 首次启动幂等种子 `lg-default-worker`：仅 `view-file`/`create-file`/`edit-file` 三个 workspace 受限工具，
  **无** `run-command`/web 无边界工具。

## 5. 烟测草案（阶段 B 执行，本阶段不跑）

1. `make sync` → 依赖就绪。
2. `lightgravity init --connection-id <id>` → 幂等资源就绪（**不打印凭证**）。
3. `lightgravity start` → 服务起于 loopback；`lightgravity status --deep` → 健康。
4. 打开前端壳，确认 Chat/Board/Files/Team/Resources/Settings 渲染与 token 注入。
5. `lightgravity stop` → 确认真实停止（无残留进程）。
6. **真实模型调用**仅在明确测试环境/预算下进行，记录版本/输入/结果/限制；**不伪造工具调用或成功日志**。

## 6. 未实现能力（不宣传可用）

- 资料摄取/检索（docs/09）：**方向已确认、接口未冻结、待实现**。
- 中文 ASR：未打通。
- Office 等格式：未实测。
- 完整 checkpoint skip 调度：未实现。
- 自主模式（去中心化协作自主领取）：**默认 off**。
