---
title: "LG-024 阶段 A 本地分发清单草案（draft source-staging，非最终 release）"
doc_type: draft
category: engineering
task: "LG-024"
contract: "1.10.0"
updated: "2026-10-16"
---

# 本地分发清单草案（Stage A，draft / 非 release）

> **性质**：可审阅的**本地 draft source-staging** 草案，用于把「发布准备」变成可机械复核的范围。
> **不是最终 release**，**不推送/不上传/不部署**，**不代表最新 main 可发布**。
> 若最终候选仍待 `integrate/lg031-runtime` 源整合释放，本草案**只作占位**，Stage B 必须**绑定届时真实候选 commit**后重出。
> 打包脚本：`probes/lg024/pack-local.sh`；校验脚本：`probes/lg024/verify-dist-exclusion.sh`。

## 1. 绑定锚点（本草案生成时）

| 锚点 | 值 |
|---|---|
| 固定首版稳定产品树 | `e0a8cec`（本 worktree 产品路径与其**逐字节相同**，见 STATUS §0） |
| 本 worktree HEAD | `309e839`（`dev/lg024`，clean） |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22` |
| Python | `>=3.12,<3.13`（实测 CPython 3.12.13） |

> 打包脚本会把**实际计入的 source commit/tree + 每文件 sha256** 写入 `MANIFEST.sha256`。
> 若 source 含未提交改动（本阶段产品树无），脚本标注 `dirty` 并**拒绝**当 release。

## 2. 分发层级（明确区分）

- **L0 源码包（source archive）**：本项目自有源码 + 工程/文档/锁文件。**默认不含**第三方包体、`frontend/dist`、任何运行数据。← 本草案默认层级
- **L1 一体构建包（可选）**：L0 + 构建后端与前端 `dist`。**仅在确实需要一体分发时构建前端**；须重新处理许可证随附。
- **L2 运行数据/凭证**：**永不入包**（见 §4）。

## 3. L0 include 范围（白名单）

| 类别 | 路径 | 说明 |
|---|---|---|
| 后端源码 | `backend/lightgravity/**` | 产品实现（只读快照） |
| 前端源码 | `frontend/src/**`, `frontend/index.html`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/README.md` | 源码，非 dist |
| 测试 | `tests/**` | 供接收方自检 |
| 依赖锁 | `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json` | **不打包体**，供重建 |
| 工程入口 | `Makefile`, `.python-version`, `.env.example`, `.gitignore` | `.env.example` 无真值 |
| 共享文档 | `README.md`, `PROJECT.md`, `agent.md`, `design.md`, `AGENTS.md`, `BACKLOG.md`, `PROGRESS.md`, `docs/**`, `backlog/**` | 阶段 B 会更新，届时绑新候选 |
| 应用资源 | `backend/lightgravity/**` 内角色/技能 Markdown | 随源码 |

> **是否含 `qa/`、`probes/`**：默认**不含**（开发证据，见 §4）。若用户要"可审阅证据"随附，须**逐目录筛查**后单独列白名单，
> 且**必须**先移除 `probes/**/*.db`、原始上游日志、`raw/**`。

## 4. L0 exclude 范围（禁入，硬清单）

| 禁入项 | 模式/路径 | 原因 |
|---|---|---|
| 环境/凭证 | `.env`, `.env.*`（保留 `.env.example`）, `*.pem`, `*.key`, `credentials.json`, `secrets.json`, `secrets/**` | 秘密 |
| 运行数据 | `bot-data/**`, 任意 `**/secrets/**` | 私有数据 |
| SDK 会话/DB | `**/*.db`, `**/*.sqlite`, `**/*.sqlite3`（含旧 `probes/**/*.db` 111 个） | 会话/轨迹，可能含内容 |
| 原始日志/上游 | `**/*.log`, `probes/**/raw/**`, `probes/**/*stdout*.txt` | 可能含秘密/上游 body |
| 依赖实体 | `.venv/**`, `node_modules/**`, `frontend/dist/**`（L0）, `**/__pycache__/**`, `*.py[cod]` | 体积/可重建 |
| 缓存/构建 | `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.tsbuildinfo` | 可重建 |
| 本机绝对路径 | 任何含 `/home/yhvh/` 的**提交内容** | 环境泄漏 |
| 敏感/个人 | 用户个人资料、私有文档、导入原件 | 隐私 |

## 5. 打包与校验流程（本地）

1. `bash probes/lg024/pack-local.sh <outdir>`：在**临时 staging 目录**按 §3 白名单 `git archive` 出对应 commit 的 L0 树，
   写入 `MANIFEST.sha256`（每文件 sha256 + 总 tree），`tar.gz` 落 `outdir`。**不触碰** worktree、**不 clean/reset**。
2. `bash probes/lg024/verify-dist-exclusion.sh <outdir>`：静态扫描产物，**命中 §4 任一模式即 fail**（非 0 退出）。
3. 私有烟测：`probes/lg024/smoke/`（`700`），只读记录 PID/端口/状态/退出码；**不入 repo、不入包**。

## 6. 诚实边界

- 本草案**不能**宣称"最新 main 可发布"：`main` 与 `integrate/lg031-runtime` 均在并行演进，且 031 共享 docs 未释放。
- **未取得**对外发布授权；**未选定**项目自身公开许可证（见 `LICENSE-INVENTORY.md` §5）。
- 依赖/SDK/weights **不重分发**：接收方按锁文件从公开来源重建；若目标环境不便，脚本如实说明"非离线自含安装"。
- L1（含 `dist`）**仅在分发确实需要前端产物时才构建**；UI 未改则不重复跑完整前端矩阵。
