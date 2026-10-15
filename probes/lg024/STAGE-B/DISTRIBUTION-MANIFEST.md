---
title: "LG-024 阶段 B 本地分发清单（L0 首版源包，私有本地评审）"
doc_type: manifest
category: engineering
task: "LG-024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# L0 首版源包分发清单（阶段 B）

> **性质**：可审阅的**本地 L0 源包**，用于私有本地评审 / 首版准备。
> **不是公开发布包**：项目自身**无 `LICENSE`/`NOTICE`、未选定公开许可证 ⇒ 未授予公开再分发**；**未推送/上传/部署/发布**。
> 打包脚本 `probes/lg024/STAGE-B/pack-stage-b.sh`；校验脚本 `verify-stage-b.sh`；解包烟测 `smoke-unpack.sh`。
> 本清单取代阶段 A 的 `DISTRIBUTION-MANIFEST-DRAFT.md`（草案不再作为最终依据）。

## 1. 绑定锚点（实测）

| 锚点 | 值 |
|---|---|
| 固定首版核心稳定产品树 | **`e0a8cec`**（`main` `66b2b10` 的产品路径与它**逐字节相同**） |
| `main` | `66b2b10` |
| 打包时本 worktree HEAD | 见 `probes/lg024/STAGE-B/REPORT.md`（打包后落盘） |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22` |
| Python / uv / Node / npm | `3.12.13` / `0.12.1` / `v22.23.2` / `10.9.8` |

> 打包脚本把**实际 source commit + tree + 每文件 sha256** 写入 `MANIFEST.sha256` / `PACK-ANCHORS.txt`。
> 若产品树脏，脚本**拒绝**（exit 3）。

## 2. 分层

- **L0 源包（本清单默认，已产出）**：本项目自有源码 + 用户文档 + 工程入口 + 依赖锁 + **预构建静态前端**。
  **不含**第三方包体 / SDK / weights / `.venv` / `node_modules` / 运行数据。
- **L1 一体构建包（未做）**：如需一体分发，另行处理许可随附；本阶段 UI 未改，不重复完整前端矩阵。
- **L2 运行数据 / 凭证**：**永不入包**（见 §4）。

## 3. L0 实际内容（白名单，405 文件）

| 类别 | 路径 | 说明 |
|---|---|---|
| 运行时源码 | `backend/lightgravity/**`（158 文件） | 产品实现（只读快照） |
| 前端源码 | `frontend/src/**`（90）、`frontend/index.html`、`frontend/tsconfig.json`、`frontend/vite.config.ts`、`frontend/README.md` | 源码 |
| 前端预构建静态资源 | `frontend/dist/**`（5：`index.html` + JS/CSS/assets） | 由同源 `npm ci --offline && npm run build` 产出 |
| 测试 | `tests/**` | 供接收方自检 |
| 依赖锁 | `pyproject.toml`、`uv.lock`、`frontend/package.json`、`frontend/package-lock.json` | **不打包体**，供重建 |
| 工程入口 | `Makefile`、`.python-version`、`.env.example`、`.gitignore` | `.env.example` 无真值 |
| 用户文档 | `README.md`（portable 使用说明，来自 `PORTABLE-README.md`）、`NOTICE.md`、`design.md`、`AGENTS.md`、`docs/01..07,09`、`docs/contracts/LG-028-preparation.md` | 无绝对路径 |
| 包元数据 | `MANIFEST.sha256`、`PACK-ANCHORS.txt` | 复核用 |

## 4. L0 排除（硬清单，实测通过）

| 禁入项 | 模式 / 路径 | 结果 |
|---|---|---|
| 开发机绝对路径 | 任何含 `/home/yhvh/` 的内容 | **0 命中**（严格无，不再有 WARN） |
| 环境 / 凭证 | `.env`、`.env.*`（保留 `.env.example`）、`*.pem`、`*.key`、`credentials.json`、`secrets/` | 0 |
| 运行数据 | `bot-data/**` | 0 |
| SDK 会话 / DB | `**/*.db`、`**/*.sqlite*` | 0 |
| 原始日志 | `**/*.log` | 0 |
| 依赖实体 / 缓存 | `.venv/**`、`node_modules/**`、`__pycache__/**`、`*.pyc`、`.pytest_cache`、`.mypy_cache` | 0 |
| **开发 / PM 证据** | `PROGRESS.md`、`agent.md`、`BACKLOG.md`、`backlog/**`、`PROJECT.md`、`docs/08-interface-contract.md`、`docs/contracts/LG-033-preparation.md` | 0（**repo 保留、不分发**） |
| 开发证据目录 | `probes/**`、`qa/**`、`.git/` | 0 |

> **为何排除上述 7 个文档**：它们含开发机绝对路径 / 开发过程记录（见阶段 A 的 17 条 WARN）。
> 处置方式为**范围裁剪**（不打包），**不篡改原始记录、不盲删源码**；原始文件在 repo 与 worktree 完整保留。
> 这是任务允许的「减少 L0 / 开发证据在 repo 保留但不分发」路径，未对 staging 文档做任何内容改写。

## 5. 产物与校验（真实命令 + 退出码）

| # | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `bash probes/lg024/STAGE-B/pack-stage-b.sh probes/lg024/STAGE-B/dist e0a8cec` | 405 文件 tar.gz + manifest + anchors | **0** |
| 2 | `bash probes/lg024/STAGE-B/verify-stage-b.sh <tarball>` | `OK (405 files, strictly clean)` | **0** |
| 3 | `bash probes/lg024/STAGE-B/smoke-unpack.sh <tarball>` | 解包离线安装 + health/version/index/asset/401/stop 全过 | **0** |

- 包路径：`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-<UTC>.tar.gz`
- tarball sha256：见 `PACK-ANCHORS.txt` 与 `REPORT.md`（打包后记录）。
- 解包烟测原始记录：`probes/lg024/STAGE-B/smoke-unpack/`（700/600，gitignored，不入包）。

## 6. 诚实边界

- **不宣称最新 main / 协作候选可发布**：`main` 与 `integrate/lg031-runtime` 并行演进，后者未合 main、QA 未完（见 `CANDIDATE-LG031-RUNTIME.md`）。
- **未取得**对外发布授权；**未选定**项目公开许可证；依赖 / SDK / weights **不重分发**。
- 接收方需按锁文件从公开来源 / 本地缓存重建依赖；**非离线自含安装**（本次离线安装能成仅因本机有 npm/PyPI 缓存，属环境事实，非包能力）。
