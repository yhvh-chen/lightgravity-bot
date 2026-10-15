---
title: "LG-024 阶段 A 状态（交付准备；不写共享 docs）"
doc_type: status
category: engineering
task: "LG-024"
owner: "agent:pi-lg024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# LG-024 阶段 A 状态

> owner `agent:pi-lg024`。worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg024`（branch `dev/lg024`）。
> **阶段 A 只写 `probes/lg024/**` 与忽略的构建/私有烟测产物**；共享 docs（README、docs/06、PROJECT、agent、
> docs/08）由 `integrate/lg031-runtime` owner 独占，**未释放前不写**。**本阶段产品真实模型生成 0**，未推送/部署/发布。

## 0. 开工核对（真实，只读）

| 项 | 实测 |
|---|---|
| worktree HEAD | `309e839`（`dev/lg024`），`git status --short` **空（clean）** |
| 产品树锚 | `git diff e0a8cec HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` **空** ⇒ 与固定首版稳定树 `e0a8cec` **逐字节相同** |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22` |
| backlog | LG-022 done、LG-023 done（评估门内）、LG-024 `in-progress`/`assignee: agent:pi-lg024` |
| `integrate/lg031-runtime` | **仍 dirty / 半成品**：`c4d4e87`（F2 WIP *unverified*）+ 4 个已改产品源 + 未跟踪 `probes/lg031/RUNTIME-AUTH-INTEGRATION/` ⇒ **共享 docs 未释放，Stage B 仍阻塞** |
| 主工作区 uvicorn | `:8123` PID `3320750`（旧常驻）**未触碰、未 kill、未复用 dataRoot** |
| Python / uv | CPython `3.12.13`；`.venv` 首次 `uv run` 时新建（gitignored） |

## 1. 阶段 A 交付物（全部在 `probes/lg024/**`）

| 产物 | 状态 |
|---|---|
| `PLAN.md` | 已有（前准备 owner），本阶段据实补充 |
| `STATUS.md`（本文件） | 已落 |
| `LICENSE-INVENTORY.md` | 已有，本阶段**大幅加强**（60 个已解析依赖逐包许可证 + 前端 224 包 + 参考仓库 + 分发排除范围 + 许可缺口） |
| `STARTUP-SMOKE-DRAFT.md` | 已有，本阶段据实补充（端口/data 隔离、命令退出码口径） |
| `DISTRIBUTION-MANIFEST-DRAFT.md` | 新增：本地分发/draft source-staging 的 include/exclude、固定 commit+sha256、禁入清单 |
| `pack-local.sh` | 新增：本地 draft source-staging 打包脚本（在 probes 下，非最终 release） |
| `artifacts/STAGE-A-REPORT.md` | 新增：阶段 A 报告（命令/退出码/源锚点/产物路径/缺口/Stage B 接续） |
| `verify-dist-exclusion.sh` | 新增：分发禁入项静态校验脚本 |
| 私有烟测产物（`probes/lg024/smoke/`，700/600） | 启动/健康/受保护接口/停止烟测记录 |

## 2. 阶段 A 结论摘要（准确，不夸大）

- **固定首版稳定产品树 `e0a8cec` / 契约 `1.10.0` / SDK `0.1.22`** 的**已验范围**：LG-010 最小后端闭环（门内）、
  LG-027 设置/凭证、LG-021 前端状态/响应式、LG-022 首版端到端+流式停止（**仅门内范围**，多项未测见 §3）。
- **未验 / 质量不齐 / 未开**：LG-029/031/032 自主协作返修**未验**（031 真实运行硬条件未闭合）；
  LG-035 真实中文/表格 OCR 质量门阻塞；LG-037 向量真实质量未验（服务不可达）；LG-039 中文 ASR **负结论**；
  LG-040 未开；LG-041 质量锁未解锁；**完整 checkpoint skip 调度未实现**。
- **LG-023 两组对照证据**：cohort3 4/4 完成，请求 3/5/3/5（A/B）总 16，**组队无收益**；usage/费用 **unknown**（不当 0）；
  旧 45（cohort1 协议违规）+ 4（cohort2 停止成本）**单列保留不隐去**。
- **许可**：运行 60 个已解析 Python 包 + 前端 224 包全部有许可证文件，**无 GPL/AGPL**；**含 MPL-2.0**
  （certifi/pathspec，文件级弱 copyleft）与 pypdfium2 捆绑 CC-BY-4.0。参考仓库 **Olav 为 BSL-1.1**（不外搬受限实现）。
  **本项目自身无 LICENSE/NOTICE 文件**（缺口，见许可清单 §5）。
- **私人本地 review 与公开发布分开**：本阶段不替用户授予公开许可证、不要求发布确认、不做任何上传/部署/推送。

## 3. 未测 / 边界（诚实清单，供 Stage B 与发布说明）

- LG-022 门内**未测**：真实 DeepSeek 上游下 cancel/pause-during-review、重启后 `verifying`/`repairing → recovery_required`、
  跨 Run 真实 reject/repair、light/浏览器全矩阵。
- LG-031：**真实 SDK 多 worker** 端到端（发现/领取/交接/隔离执行/候选 review）未跑；仅真 Git + 进程内 fake executor。
- LG-029：F2 端点 `owner` body 认证缺陷**返修中**（`fix/lg029-auth` WIP unverified），未集成。
- LG-035/037：真实中文/表格 OCR 与向量检索质量**未验证**；LG-039：已测路径**无可用中文 ASR**（负结论）。
- 分发：**未取得**对外发布的用户授权；**未选定**项目自身公开许可证；依赖/SDK/weights **不重分发**。

## 4. 阶段 B（仍阻塞，待 runtime owner 释放）

- 释放信号：`integrate/lg031-runtime` owner 停止写入共享 `api/{app,bootstrap}.py`、docs/08、README、PROJECT、agent、docs/06，
  且产品源整合候选稳定（届时以真实 main 产品树/契约为准，**不预设**）。
- 释放后**串行**落地 README / docs/06 / 必要 PROJECT·agent·docs/08 一致性，**绑定准确候选 commit**。
- **LG-024 本阶段不 done**：验收要求 README/设计/规则与实际行为一致，须 Stage B 完成后由主代理决定。
