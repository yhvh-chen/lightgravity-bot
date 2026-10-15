---
title: "LG-024 阶段 B 报告（交付准备：文档一致性 + 本地可审阅 L0 包）"
doc_type: report
category: engineering
task: "LG-024"
owner: "agent:pi-lg024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
head: "db3ecea"
updated: "2026-10-16"
---

# LG-024 阶段 B 报告

> **性质**：首版交付准备的**可独立审阅**产物。**本阶段产品真实模型生成 0**；
> **未推送 / 未部署 / 未发布 / 未上传**。所有 runtime / 草案 / 旧记录**未 reset/clean/覆盖/重复 pick**。
> **本交付包只绑定首版核心稳定产品树 `e0a8cec` / `main 66b2b10`**（产品路径逐字节相同）；
> **协作候选 `integrate/lg031-runtime@afcae82` 未合 main、独立 QA R1 进行中，单列不并入本包**。

## 1. 源锚点（核实际）

| 项 | 值 |
|---|---|
| worktree / branch | `/home/yhvh/code/lightgravity-bot-worktrees/lg024` / `dev/lg024` |
| 开工 HEAD | `140c39f`（`dev/lg024`，clean） |
| `main` | `66b2b10` |
| 固定首版稳定产品树 | `e0a8cec845864b387f89934266901e62817aaa9d`；tree `0ff6ad6b7f48c74530e30e32bdd566f72440680d` |
| `git diff e0a8cec HEAD -- <产品路径>` | **空** |
| `git diff e0a8cec main  -- <产品路径>` | **空**（main 产品树 = e0a8cec） |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22`（实测 0.1.22） |
| Python / uv / Node / npm | `3.12.13` / `0.12.1` / `v22.23.2` / `10.9.8` |
| 主工作区 uvicorn | `127.0.0.1:8123` PID `3320750` **未触碰** |
| `integrate/lg031-runtime` | `afcae82`（clean，未合 main；`git diff main afcae82 -- <产品路径>` = 9 文件 +2342/-44） |

## 2. 本阶段交付物（全部 `probes/lg024/**` 与共享 docs）

| 产物 | 路径 | 说明 |
|---|---|---|
| 阶段 B 状态 | `probes/lg024/STAGE-B/STATUS.md` | 开工核对 + 边界 |
| 本报告 | `probes/lg024/STAGE-B/REPORT.md` | — |
| portable 用户说明 | `probes/lg024/STAGE-B/PORTABLE-README.md` | 打包时改名 `README.md` |
| 第三方 NOTICE | `probes/lg024/STAGE-B/NOTICE.md` | 运行时 51 包 + 前端 224 + 参考仓库 |
| 分发清单（终版） | `probes/lg024/STAGE-B/DISTRIBUTION-MANIFEST.md` | L0 include/exclude + 锚点 |
| 打包脚本 | `probes/lg024/STAGE-B/pack-stage-b.sh` | L0 + manifest + anchors |
| 严格校验脚本 | `probes/lg024/STAGE-B/verify-stage-b.sh` | 无 WARN：绝对路径即 FAIL |
| 解包烟测脚本 | `probes/lg024/STAGE-B/smoke-unpack.sh` | 解包离线安装 + 启动烟测 |
| 协作候选记录 | `probes/lg024/STAGE-B/CANDIDATE-LG031-RUNTIME.md` | 单列待版本 QA |
| **L0 包** | `probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-*.tar.gz` | 405 文件 |
| 共享文档 | `README.md`（+首版使用指南）、`docs/06-roadmap.md`、`backlog/tasks/LG-024.md` | 本 owner 落地；**未写 docs/08** |

## 3. L0 包（真实路径 / hash / 内容）

| 项 | 值 |
|---|---|
| 包路径 | `probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.tar.gz` |
| **sha256(tarball)** | **`581f1de603ab8adc6533efa9d4b2ed0506433d17328646b00ab7bbb2761f4de0`** |
| 大小 / 文件数 | ~920 KB / **405 文件** |
| manifest | `...e0a8cec-20261015T183958Z.MANIFEST.sha256`（每文件 sha256，sorted） |
| anchors | `...e0a8cec-20261015T183958Z.PACK-ANCHORS.txt` |
| source_commit / tree | `e0a8cec845864b387f89934266901e62817aaa9d` / `0ff6ad6b7f48c74530e30e32bdd566f72440680d` |
| 含 | 运行时源码、前端源码、**预构建 `frontend/dist`**、tests、锁文件、Makefile、`.env.example`、portable README、NOTICE、design/AGENTS、docs 01..07/09、docs/contracts/LG-028-preparation |
| 排 | 开发/PM 证据（`PROGRESS.md`/`agent.md`/`BACKLOG.md`/`backlog/**`/`PROJECT.md`/`docs/08`/`docs/contracts/LG-033-preparation.md`）、`.env`/凭证/DB/日志/`probes/**`/`qa/**`/`.git`/`.venv`/`node_modules` |

- 打包脚本：`bash probes/lg024/STAGE-B/pack-stage-b.sh probes/lg024/STAGE-B/dist e0a8cec`（**exit 0**）。
- 阶段 A 的 **17 条 `/home/yhvh/` WARN 已在本 L0 消除**：校验脚本对绝对路径**直接 FAIL**，实测 0 命中（详见 `DISTRIBUTION-MANIFEST.md` §4）。
- 处置方式为**范围裁剪**（不打包含路径的开发文档），**未篡改原始实验记录、未盲删源码**。

## 4. 准确命令 + 退出码（真实）

| # | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `npm ci --offline`（frontend） | offline 装 177 包 | **0** |
| 2 | `npm --prefix frontend run build` | `tsc --noEmit` + vite build：`dist/index.html` + CSS 34.79 kB + JS 283.11 kB | **0** |
| 3 | `bash probes/lg024/STAGE-B/pack-stage-b.sh probes/lg024/STAGE-B/dist e0a8cec` | 405 文件 + manifest + anchors | **0** |
| 4 | `bash probes/lg024/STAGE-B/verify-stage-b.sh <tarball>` | `OK (405 files, strictly clean: no abs paths, secrets, deps, DBs, dev docs)` | **0** |
| 5 | `bash probes/lg024/STAGE-B/smoke-unpack.sh <tarball>` | 见 §5 | **0** |
| 6 | `git diff e0a8cec main -- <产品路径>` | 空 | **0** |

## 5. 解包独立烟测（真实，产品模型 0）

- **方式**：解包 L0 tarball 到 `probes/lg024/STAGE-B/smoke-unpack/`（700/600，gitignored），**独立 data / secret 目录**，
  **新 loopback 端口 `18433`**，`--no-executor`（真实 SDK / 模型生成 **0**），`--frontend-dist <解包>/frontend/dist`。
- **结果（全过）**：
  - `uv sync --offline` → **exit 0**（依赖来自已有缓存；不额外网络探测）。
  - `GET /api/v1/health` → **200** `{"status":"ok","contract_version":"1.10.0","capabilities":{...,"sdk_adapter":false}}`。
  - `GET /api/v1/version` → **200**（python `3.12.13`）。
  - `GET /` → **200**；引用静态 JS 资产 `/assets/index-*.js` → **200**（283246 bytes）。
  - 无 token `POST /api/v1/settings/connections` → **401 unauthorized**（敏感写默认拒绝）。
  - `lightgravity stop` → **exit 0**，端口 `18433` **释放**、无 `lightgravity start` 残留；**主 `:8123` PID 不变**。
- **未测（诚实）**：真实 `lightgravity init` 写连接凭证、`status --deep`、浏览器六入口渲染、真实模型闭环。
  **这些不以本次部分烟测冒充通过**（属版本 QA / 授权环境范围）。

## 6. 文档一致性（README / 设计 / 规则）

- **README.md**：新增「首版使用指南」——安装、启动（`start/status/stop/init`，默认 loopback、内存 token 握手、敏感写默认拒绝、
  `lg-default-worker` 有界工具）、Settings（worker `default_worker_connection_ref` + 独立 reviewer
  `default_reviewer_connection_ref`；无 reviewer ⇒ `unavailable` 且阻止 accept；自主开关默认 off）、
  Chat 轻问答与交付 Task、Files 原件与来源、Resources 与恢复入口（`recovery_required`、完整 checkpoint skip 未实现）。
- **docs/06-roadmap.md**：增补阶段 B 集成更新条目（绑定 `e0a8cec`/`main 66b2b10`、L0 包、烟测、许可、未验项、候选单列）。
- **agent.md / PROJECT.md**：规则与首版行为一致（**未新增对外承诺**）；参考仓库路径明确为**开发机参考、非运行必需**（agent.md §9）。
- **docs/08**：**本 owner 未写**（保留 runtime 返修 owner）。链接检查：见 §8「已知链接边界」。

## 7. 许可范围与「公开许可未选」

- **L0 不重分发第三方包体 / SDK / weights**；随附 `NOTICE.md` 汇总**运行时 51 包**（`uv export --no-dev`，实测版本）
  与前端 **224** 条目的许可与来源；`pypdfium2` 捆绑 **CC-BY-4.0**；弱 copyleft `certifi`（MPL-2.0）；**无 GPL/AGPL**。
- 参考仓库 **Olav = BSL-1.1（非宽松）**，仅方法参考、**不搬运受限实现**；Olav OS / Olav Tasks = MIT。
- **本项目自身无 `LICENSE` / `NOTICE`；未选定公开许可证 ⇒ 未授予公开再分发**；**不代用户选择**。
  私有本地评审 / 首版准备已完成；**公开许可仍待发布前决定**（本次不发布，不为普通准备再问用户）。
- 无编造许可：所有条目来自**实际安装元数据与随附 LICENSE 文件**实测；未安装新工具、未跑远程脚本。

## 8. 未测 / 未实现 / 已知边界（不写「全部通过」）

| 项 | 事实 |
|---|---|
| LG-029 / 031 / 032 | 返修**未验**；031 真实运行硬条件未闭合；候选 `afcae82` 未合 main、QA 未完 |
| LG-035 OCR | 真实中文/表格人工真值质量门**阻塞**（端点不可达 + 无许可样本）；**服务可达 / 合成样本 ≠ 转写品质** |
| LG-037 向量 | 真实检索质量**未验**（服务不可达）；Embedding 输出 ≠ 检索/转写品质 |
| LG-039 / 041 | 中文 ASR **负结论** / 质量锁**未解锁** |
| LG-040 | **未开** |
| 完整 checkpoint skip 调度 | **未实现**；未知副作用进 `recovery_required`、不自动重放 |
| LG-022 门内未测 | 真实 DeepSeek 上游 cancel/pause-during-review；重启后 `verifying/repairing → recovery_required`；跨 Run reject/repair；light/浏览器矩阵 |
| LG-023 成本 | 两组小样本**组队无收益**；usage/费用 **unknown**（不当 0）；旧 45（协议违规）+ 4（harness 停止成本）**单列不隐去**，总 65 |
| 本阶段 | 未重跑完整后端 pytest / 完整前端矩阵（**UI 未改**，引用已验锚点）；未跑真实模型闭环 |
| 已知链接边界 | 包内 `docs/01,05` 保留指向 dev 参考仓库（`../olav-*`）与 `docs/06` 指向 `probes/**` 的**开发侧**链接；这些目标不在包内，属开发参考快照，不影响首版用户流程；portable `README.md` 自足、不链接包外文件 |

## 9. 状态

- **LG-024 `in-progress`（阶段 B 交付准备完成，达原门可置 done）**；**仍非发布授权**。
- LG-029/031/032/035/037 `in-progress`；LG-040/041 `todo`；其余首版核心任务 `done`（各门内范围保留）。
- 契约 `1.10.0`、SDK `0.1.22`、**程序最小规则调度**、**真实 SDK 唯一路径**、**自主模式默认 off** 不变。
- **本阶段产品真实模型生成 0**；未推送 / 部署 / 发布 / 上传。**精确本地 commit**：`db3ecea`（`dev/lg024`，本报告提交后）。
