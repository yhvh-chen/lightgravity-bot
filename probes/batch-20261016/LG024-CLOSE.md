---
title: "LG-024 收拢报告：首版交付准备（文档一致性 + 本地可审阅 L0 包）收口与 main 收拢"
doc_type: report
category: engineering
task: "LG-024"
owner: "agent:pi-lg024-close"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# LG-024 收拢报告（首版交付准备收口）

> 由**主代理 PM（只做项目管理，无嵌套派工 / 无推送 / 无部署 / 无发布）**收口。
> **本包产品真实模型生成 0、外部服务调用 0**：不重跑模型、不重跑无变更的测试、不执行新探针，只做只读核对 + 文档/任务状态更新 + 精确本地 commit + 安全 fast-forward 合并。
> **本报告不授予公开发布 / 公开再分发授权**；项目公开许可证仍**未选定**（不代用户选择）。
> 旧实验、worktree、dirty、原始记录全部保留，未 reset/clean/覆盖/重复 pick。

## 1. 开工核对（真实，只读）

| 项 | 实测 |
|---|---|
| 主工作区 | `/home/yhvh/code/lightgravity-bot`，branch `main`，开工 HEAD `66b2b10`，**clean**（`git status --porcelain` 空） |
| `dev/lg024` | `/home/yhvh/code/lightgravity-bot-worktrees/lg024`，HEAD **`73f570c`**，**clean** |
| `main` → `dev/lg024` | `git merge-base --is-ancestor main dev/lg024` = **YES**（main 为直接祖先，**可 fast-forward**，无冲突） |
| 变更范围 | `git diff --name-status main dev/lg024` = 仅 `README.md`、`backlog/tasks/LG-024.md`、`docs/06-roadmap.md` + `probes/lg024/**`；**无** `backend/`、`frontend/`、`src/`、`tests/`、`docs/08`、`qa/**`、`integrate/lg031-runtime` |
| 源 024 owner | 已退出（无残留），`dev/lg024@73f570c` clean |
| 主工作区 uvicorn | `127.0.0.1:8123` PID `3320750`（旧常驻，**非本包**）**未触碰** |
| 在途签名进程 | `lg032-runtime-r1` 独立 QA（PID 2233535，worktree `lg032-runtime-r1`）**仍在运行**，**未 kill、未触碰其 branch/文件/index/worktree** |

- backlog 专用根（`<repo>/backlog`）：`validate` = **41 tasks / 0 diagnostics**；`digest` complete=true。
- 产品树锚：`git diff e0a8cec main -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` = **空** ⇒ 产品树逐字节同已验首版核心稳定树 `e0a8cec`，契约 `1.10.0`、SDK `0.1.22`。

## 2. 首版稳定产品树与包锚点（逐字节复核）

| 锚 | 值 |
|---|---|
| 首版核心稳定 product tree | **`e0a8cec845864b387f89934266901e62817aaa9d`**；tree `0ff6ad6b7f48c74530e30e32bdd566f72440680d` |
| `main`（收拢前） | `66b2b10`（产品路径与 `e0a8cec` 逐字节相同） |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22` |

## 3. 可 review 的 L0 包（仓库内确切路径 / source anchor / hash / 已验 scope / 未测）

**包路径（repo 内，已随 `dev/lg024@73f570c` 提交）**：

- 目录：`probes/lg024/STAGE-B/dist/`
- tarball：`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.tar.gz`
- manifest：`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.MANIFEST.sha256`（405 行，逐文件 sha256，sorted）
- anchors：`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.PACK-ANCHORS.txt`

**source anchor / hash（实测，PM 独立核对）**：

| 项 | 值 |
|---|---|
| source_commit | `e0a8cec845864b387f89934266901e62817aaa9d` |
| source_tree | `0ff6ad6b7f48c74530e30e32bdd566f72440680d` |
| **sha256(tarball)**（工作区实体 + git blob 双核） | **`581f1de603ab8adc6533efa9d4b2ed0506433d17328646b00ab7bbb2761f4de0`** |
| 文件数 | **405**（`tar tzf` 非目录条目 = 405；manifest 行数 = 405） |
| manifest 完整性 | `sha256sum -c`（除 manifest 自身）**全部 MATCH，exit 0** |
| 严格 exclusion | `bash probes/lg024/STAGE-B/verify-stage-b.sh <tarball>` → **`OK (405 files, strictly clean: no abs paths, secrets, deps, DBs, dev docs)`，exit 0** |

**已验 scope（L0 包，private/local review，非发布）**：

- 只含项目自有源码 + 用户文档 + 工程入口 + 依赖锁 + **预构建 `frontend/dist`**；**不含**第三方包体 / SDK / weights / `.venv` / `node_modules` / 运行数据。
- **严格无**开发机绝对路径（`/home/yhvh/` 直接 FAIL，实测 0 命中）、秘密 / `.env`（仅留值‑free `.env.example`）、`*.db`/`sqlite`、`.log`、`probes/**`、`qa/**`、依赖实体；开发/PM 证据（`PROGRESS.md`/`agent.md`/`BACKLOG.md`/`backlog/**`/`PROJECT.md`/`docs/08`/`docs/contracts/LG-033-preparation.md`）**repo 保留、不分发**。
- 解包独立烟测（脚本 `probes/lg024/STAGE-B/smoke-unpack.sh`，**专用端口 `18433`**、独立 data/secret、`--no-executor`、产品真实 SDK/模型 **0**，**不碰 `:8123`**）：离线 `uv sync` → exit 0；`GET /api/v1/health` → 200（`sdk_adapter=false`）；`GET /api/v1/version` → 200；`GET /` → 200 + 静态 JS 资产 → 200；无 token 敏感写 `POST /api/v1/settings/connections` → **401**；`lightgravity stop` → exit 0 且端口释放、无残留；主 `:8123` PID 不变。
- 许可：L0 **不重分发**第三方包体 / SDK / weights；随附 `NOTICE.md`（运行时 51 包 + 前端 224 + `pypdfium2` 捆绑 CC-BY-4.0；弱 copyleft `certifi`/`pathspec` MPL-2.0；**无 GPL/AGPL**）；**项目自身无 `LICENSE`/`NOTICE`、公开许可证未选定 ⇒ 未授予公开再分发**；**NOTICE 列上游许可但不授公开再分发**；私有 review / 首版准备范围准确。

**未测（诚实，不冒充通过）**：

- 真实 `lightgravity init` 写连接凭证、`status --deep`、浏览器六入口渲染、真实模型闭环。
- 本收拢包**未重跑**完整后端 `pytest` / 完整前端矩阵（产品树无变更，引用已验锚点）；**未跑真实模型**。
- 包内 `docs/01,05` 保留指向 dev 参考仓库（`../olav-*`）与 `docs/06` 指向 `probes/**` 的**开发侧**链接（目标不在包内，属开发参考快照，不影响首版用户流程）；portable `README.md` 自足。

## 4. 协作候选 `integrate/lg031-runtime@afcae82`（单列，不入本包）

- `main` 与其并行演进；该候选**未合 main**、**独立 QA R1 进行中**（本包不参与该 QA）。
- 已由源 024 owner 单列记录于 `probes/lg024/STAGE-B/CANDIDATE-LG031-RUNTIME.md`。
- **未来协作 source 不是本包已验内容**：若后续集成该候选，需**另产新候选包并重新绑定届时真实 product tree、重新版本 QA**；**不把本 L0 包（`e0a8cec` 旧包）冒称最新全产品**。

## 5. main 安全收拢（fast-forward，仅文档 / 打包脚本 / probes / 忽略资产）

- `git merge --ff-only dev/lg024`（main 为 `dev/lg024` 直接祖先）⇒ `main` 前进到 `dev/lg024` HEAD。
- **不合**未验 `integrate/lg031-runtime@afcae82`；**不碰** `qa/lg032-runtime-r1` owner / index / worktree；**不杀**任何签名进程。
- 收拢内容仅：`README.md`（首版使用指南）、`backlog/tasks/LG-024.md`、`docs/06-roadmap.md`、`probes/lg024/**`（含 L0 tarball / manifest / anchors / 脚本 / 报告）；**无产品代码、无 `docs/08`**。
- README/PROJECT/agent/docs06 若存在冲突，保留已授权双方；本包**未复制任何秘密**；**docs/08 本包不写**。

## 6. 状态如实

- **LG-024 `in-progress → done`**（仅**首版交付准备原门**内：README/设计/规则与实际行为一致、来源许可完整、可审阅分发/演示材料就绪；**仍非发布授权**，不代用户选公开许可证）。
- **source candidate 未合 main / 独立 R1 仍进行**；**LG-029/031/032 仍 `in-progress`**；**LG-035/037 `in-progress`**；**LG-040/041 锁不动**（`todo`，未解锁）。
- 契约 `1.10.0`、SDK `0.1.22`、程序最小规则调度、真实 SDK 唯一路径、自主模式默认 off **不变**。
- **本包产品真实生成 0、外部服务调用 0**；未推送 / 部署 / 发布 / 上传。

## 7. 措辞边界（组队成本，不泛化）

- LG-023 cohort-3「组队成本更高 / 更低」**只能指已测请求数 / elapsed 代理量**（A 6 请求 / 25.17s，B 10 请求 / 33.43s），**不得**引申为完整生命周期费用或货币节省。
- **provider token / 费用 / sharedpiQA 仍 `unknown`**（不当 0）；**023 旧 45+4 历史不洗白**（旧 cohort-1 45 protocol-deviation 失败 + cohort-2 4 harness 停止，另行单列）。
