---
title: "LightGravity Bot 首版使用说明（本地私评包，非发布）"
doc_type: guide
category: engineering
task: "LG-024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# LightGravity Bot 首版使用说明

> 本文件在 **L0 源包**内作为顶层 `README.md` 交付（打包时由 `PORTABLE-README.md` 改名）。
> 它是**第一版使用说明**，绑定**首版核心稳定产品树**
> —— `e0a8cec`（= 打包时 `main` `66b2b10` 的产品路径，逐字节相同）。
> **这是一个私有本地评审 / 首版准备的包，不是公开发布包**：项目自身**尚未选定公开许可证**、
> **未授予公开再分发**；公开许可与发布前由用户决定（本次不发布）。
> 包内**不含**第三方 Python/前端依赖包体、SDK、weights、`.venv`、`node_modules`；
> 接收方按锁文件从公开来源重建（**非离线自含安装**）。

---

## 1. 这是什么（首版事实）

首版是一个**单用户本地网页**的 AI 任务助手：把资料与目标交给它，简单问答直接处理，
需要交付时创建 Task 并按需组队，执行、验证、保存成果；Chat 统一接资料/提目标/看结果，
Files 负责整理、归档、预览与来源追溯，Resources 管理 Connections / Session Profiles /
Hooks / MCP / Tools / Triggers / Skills。

**首版真实执行路径（唯一）**：`google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`
（`openai-compat`）+ loopback 认证代理 → DeepSeek。凭证只来自环境变量或受控 `credential_ref`。

**程序控制调度（不是模型编排）**：明确目标的执行计划由**程序**按规则确定性生成
（`plan_source=rules`，**不调用模型**）；模型只作有界按需提议且必经同一程序校验。
worker 不写控制状态，SDK 内部委派默认关闭。

**自主协作默认 off**：去中心化自主领取 / 同伴协作开关默认关闭，走确定性规则路径。

**首版边界**（不扩）：单用户本地网页；不引入组织 / 岗位、邮箱、外部聊天渠道、多租户、云端。

## 2. 版本要求

| 组件 | 要求 | 本包已验证 |
|---|---|---|
| Python | `>=3.12,<3.13` | CPython 3.12.13 |
| uv | `0.12.x` | 0.12.1 |
| Node.js | 22 LTS（仅重建前端时需要） | v22.23.2 |
| npm | 10.x（仅重建前端时需要） | 10.9.8 |
| GNU make | 统一入口（可选） | `/usr/bin/make` |

## 3. 安装（按锁文件重建依赖）

```bash
uv sync          # 创建 .venv 并按 uv.lock 安装后端依赖（从公开来源 / 本地缓存）
```

- 后端依赖经 `uv.lock` 固定；**包内不含依赖包体**，需能访问公开 PyPI 或本地缓存。
- 前端**预构建静态资源**计划随包提供（见打包 manifest 的含/排记录）；若要自行重建：

```bash
npm --prefix frontend ci     # 按 frontend/package-lock.json 精确安装
npm --prefix frontend run build   # 产出 frontend/dist
```

## 4. 启动与停止

最小一步式本地服务（API + 静态前端同进程，仅 loopback）：

```bash
uv run lightgravity start \
  --data-dir ./bot-data \
  --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets \
  --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/
```

常用子命令（`backend/lightgravity/cli.py`）：

| 命令 | 作用 |
|---|---|
| `lightgravity start` | 构建真实运行时并启动；默认 loopback、端口 8000；`--daemon` 后台并写 `<data-dir>/logs` |
| `lightgravity status [--deep]` | 报告 pid 与（可选）HTTP 健康；`--deep` 额外构建运行时只读并打印执行就绪报告 |
| `lightgravity stop` | 停止由 `start` 记录的进程（SIGTERM→SIGKILL，`--timeout` 默认 10s），确认才写终止 |
| `lightgravity init` | **唯一写配置**的命令，幂等；见 §5 |

也可用 Make 包装：`make serve`（先构建前端再启动）、`make lg-start` / `lg-start-daemon` /
`lg-status` / `lg-stop` / `make lg-init`。

**安全默认（首版事实）**：

- 默认仅绑定 loopback；首个启动在**内存**握手运行时 token 并注入 `index.html`
  （`__LG_RUNTIME_TOKEN__`，前端 `auth.ts` 自动带 `X-LG-Token`）。
- **敏感写默认拒绝**；无认证可读历史 / 设置。
- 首次启动幂等种子 `lg-default-worker`：**仅** `view-file` / `create-file` / `edit-file`
  三个 workspace 受限工具，**无** `run-command` / 无边界 web 工具。

## 5. configure worker 与独立 reviewer（Settings）

设置与凭证走**受保护表单 / 后端接口**（不往 Markdown / 日志 / 提交写真实密钥，只存引用）。

- **建连接 / 存凭证**：Settings → Connections，或用非交互 `init`（幂等）：

  ```bash
  uv run lightgravity init \
    --connection-id local-deepseek \
    --backend openai-compat \
    --credential-ref DEEPSEEK_API_KEY \
    --set-worker-default
  ```

  `--credential-ref` **必填**；它指向 secret store 中的引用，**不是**密钥值本身。
- **设 worker 默认**：`PUT /api/v1/settings` 或 Settings 表单设 `default_worker_connection_ref`；
  新 Task 招募时用该默认，Run/Member 冻结**非秘密** `connection_pin`。
- **设独立 reviewer 默认**：设 `default_reviewer_connection_ref`（LG-017 加性字段）。
  reviewer 用自己的默认连接做独立复核；**未配置时诚实 `unavailable` 且阻止 accept**，
  **程序机器门 ≠ 独立复核**，不静默回退 worker。
- **自主协作开关**（默认关闭）：`decentralized_claim_enabled` / `collab_requests_enabled`
  默认 `false`，`claim_lease_seconds` 可选；关闭时走确定性 `plan_source=rules`。

## 6. 用起来：Chat 轻问答 + 交付 Task

- **轻问答**：Chat 里直接问，走无工具单次直答；**未配置默认协调连接 / 凭证时诚实 `unavailable`**，
  不伪造 AI 回复。
- **交付 Task**：Chat 里提目标 → 程序按规则生成最小合法计划 → 招募最小团队 → 依赖调度执行 →
  机器检查 + 独立复核 → 进入待验收（**worker 自报完成只进入待验证，不直接 done**）→
  **人工最终验收**。待验收前确认 worker 停止并释放执行资源。

## 7. Files：资料原件与来源

- Files 浏览获准根目录，只读预览 / 下载 / 上传；检查符号链接与路径逃逸。
- 上传复用运行时 token helper（`X-LG-Token`）；无 token 时只读可用、上传如实 `unauthorized`。
- **资料接入方向**（docs/09）：**Chat 是唯一常规资料接入入口**（上传 / 拖拽 / 粘贴链接），
  Files 负责预览 / 来源追溯 / 归档调整 / 校订 / 重处理 / 下载；原件 + 正式内容 + 元数据以文件为事实源。
  **注意：资料 schema/API 尚未冻结、摄取/检索尚未实现**（见 §9），现有 Files 上传属历史实现。

## 8. Resources 与恢复入口

- **Resources** 纵向分类：Connections、Session Profiles、Hooks、MCP、Tools、Triggers、Skills；
  以渲染、详情、诊断与对话写入为主；资源声明 `enabled` 不等于已运行 / 可用，健康未知如实显示 `unknown`。
- **恢复**：暂停 / 取消 / 断连 / 会话关闭 / 运行完成分别处理；**必须确认真实停止后才写终止状态**；
  浏览器断线不取消常驻后端工作，重连按游标补齐。
- **中断后未知副作用不自动重放**：进入 `recovery_required` 诚实停车，保留 `session_refs`。
  **完整 checkpoint skip 调度尚未实现**（这是明确的已知边界，不夸大恢复能力）。
- 排查入口：只读诊断 `GET /api/v1/diagnostics/generation`（全局生成请求计数，`persistent` 跨重启不归零，
  损坏时给 `corrupt`/`reason`，绝不当 0）。

## 9. 已验范围与**未实现 / 未验**（准确，不宣传）

**本包绑定产品树的已验范围（仅门内，不得向上引申）**：

- LG-010 原型大版本 QA：契约 1.3.1 core **最小后端闭环** — pass/done。
- LG-027 设置 / 凭证：**CLI + HTTP + browser 渲染** — pass。
- LG-021 前端状态 / 响应式（含 `qa/lg021-r1` 26/26）— done。
- LG-022 首版端到端 + 故障：真 SDK + 本地 fake SSE 流式停止 PASS、真 DeepSeek 主链一例 PASS — done（**仅门内**）。

**未验 / 质量不齐 / 未开（不夸大）**：

| 项 | 事实 |
|---|---|
| LG-029 领取 / 租约 | 返修中；端点认证身份缺陷（`fix/lg029-auth`）**未验** |
| LG-031 去中心化整合 | **真实运行硬条件未闭合**（仅真 Git + 进程内 fake executor）；候选 `integrate/lg031-runtime@afcae82` **未合 main、独立 QA 进行中**，**不属于本包** |
| LG-032 去中心化版本 QA | 阶段 A partial、F2 重要缺陷，**阶段 B 暂停** |
| LG-035 图片 / PDF OCR | 机制已实现；真实中文 / 表格人工真值质量门**阻塞**（端点不可达 + 无许可样本） |
| LG-037 可选向量 | 机制 / 降级以替身通过；**真实检索质量未验**（服务不可达） |
| LG-039 中文 ASR | **负结论**：已测服务 4 模型无可用路径，真实人声推理 5 次全失败 |
| LG-040 资料 / Embedding 版本 QA | **未开** |
| LG-041 中文转写接入 | **质量锁未解锁**（阻塞于 LG-039） |
| 完整 checkpoint skip 调度 | **未实现**（见 §8） |
| LG-022 门内未测 | 真实 DeepSeek 上游 cancel/pause-during-review；重启后 `verifying`/`repairing → recovery_required`；跨 Run 真实 reject/repair；light/浏览器全矩阵 |

> **注意**：**服务可达 / 合成样本 / Embedding 输出 ≠ OCR 转写品质**。不要把本包当作完整产品 pass。

## 10. LG-023 对照评估证据（不洗成收益）

- **cohort-3（正式）**：4/4 attempts 全部真实交付；请求 A/B = 3/5/3/5（总 16，单持久 phase 账本）；
  A 总 elapsed 25.17s、B 33.43s。**组队 arm 在完成率上无增益、成本更高 ⇒ 这两小样本不支持组队收益**。
  样本小、单模型、强制计划；**usage / cost 为 `unknown`，不当 0**。
- **旧失败成本单列保留、不隐去**：cohort-1 **45**（协议违规）+ cohort-2 **4**（harness 停止成本）；
  **总实际 eval 请求 = 45 + 4 + 16 = 65**。已测次数与 elapsed **不等同**完整 token / 费用；
  shared 开发-QA 成本未知，不与此混算。

## 11. 许可与再分发（重要）

- **本项目自身暂无 `LICENSE` / `NOTICE` 文件** ⇒ **未授予公开再分发**。本包仅供**私有本地评审 / 首版准备**；
  **公开许可证与发布前由用户选择**（本次不发布）。
- L0 源包**不含第三方 Python / 前端依赖包体、SDK、weights**；随附**第三方 NOTICE**（见 `NOTICE.md`）
  汇总本包实际引用到的依赖许可与来源版本，供接收方按锁文件重建时保留署名。
- 弱 copyleft 提醒：Python `certifi` / `pathspec`（MPL-2.0，文件级）、`pypdfium2` 捆绑 CC-BY-4.0；
  前端 `caniuse-lite`（CC-BY-4.0 数据）。**无 GPL / AGPL**。
- 参考仓库 **Olav = BSL-1.1（非宽松）**，仅作方法参考、**不搬运受限实现**；Olav OS / Olav Tasks = MIT。

## 12. 包内文档索引（本包实际包含的文件）

| 文件 | 说明 |
|---|---|
| `README.md` | 本使用说明（本文件的打包版） |
| `NOTICE.md` | 第三方软件许可与来源版本 |
| `docs/01..07,09` | 产品与架构设计、Task 资源契约、SDK 能力审计、Bot 行为、导航、排期、设置、资料接入方向 |
| `docs/contracts/LG-028-preparation.md` | 协作契约准备稿 |
| `design.md` / `AGENTS.md` | 前端约束 / 规则发现入口 |
| `backend/lightgravity/**` | 运行时源码（只读快照） |
| `frontend/src/**`（+ 预构建 `frontend/dist/**`） | 前端源码 / 预构建静态资源 |
| `tests/**` | 供接收方自检 |
| `pyproject.toml` / `uv.lock` / `frontend/package*.json` | 依赖锁（不打包体） |
| `Makefile` / `.env.example` / `.python-version` / `.gitignore` | 工程入口（`.env.example` 无真值） |

> **不在包内**（repo 保留、不分发）：`PROGRESS.md`、`agent.md`、`BACKLOG.md`、`backlog/**`、`PROJECT.md`、
> `docs/08-interface-contract.md`、`docs/contracts/LG-033-preparation.md`、`probes/**`、`qa/**`（开发/PM 证据，
> 含开发机绝对路径）。因此本 README 不链接这些文件。

## 13. 已知的安全 / 分发边界

- **不打包开发机绝对路径**：本 L0 包已排除含个人绝对路径的开发/PM 文档（`PROGRESS.md`、`agent.md`、
  `BACKLOG.md`、`backlog/**`、`PROJECT.md`、`docs/08-interface-contract.md`、`docs/contracts/LG-033-preparation.md`），
  这些**在 repo 保留但不分发**（不篡改原始实验记录，只做范围裁剪）。
- **禁入**：`.env` / 凭证 / secret store、SDK 会话 DB（`**/*.db`）、`bot-data/**`、原始含 secret 日志、
  工作区状态、`.git`、`.venv` / `node_modules`、个人资料。
- 源码无实际运行依赖开发绝对路径（`.env.example` 明确说明路径默认相对进程工作目录）。
