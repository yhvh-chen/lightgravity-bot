# DISPATCH — 选定资料快速原型（LG-042..047）

> 由 LG-042 prep owner（`pi-proto-prepare`）冻结。

## 冻结基线

- **Baseline commit**：`acd7005`（`main`，clean；LG-040 收口后）。所有 worktree 从此 commit 派发。
- **契约**：`docs/10-selected-material-prototype.md`（新）+ `docs/08-interface-contract.md` §6.6.1 与 §13 变更控制（加性 MINOR `1.12.0` 预留）。**唯一 owner**：`pi-proto-prepare`（本任务）。实现不得先于契约扩展语义。

## 三份 worktree / 分支 / owner 边界

| 工作包 | Worktree | 分支 | Owner 文件 | 任务 |
|---|---|---|---|---|
| A 后端 | `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-backend-20261016` | `dev/proto-material-backend-20261016` | `backend/**`、`tests/**`（Python）、docs/08 实现注记 + docs/10 技术补充（**契约冻结、不擅改字段**） | LG-043 |
| B 前端 | `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-frontend-20261016` | `dev/proto-material-frontend-20261016` | `frontend/**` + `probes/prototype-selected-material-20261016/B-FRONTEND/**` | LG-044 |
| C Demo | `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-demo-20261016` | `dev/proto-material-demo-20261016` | `examples/selected-material-prototype/**`、`docs/11-selected-material-demo.md` + `probes/prototype-selected-material-20261016/C-DEMO/**` | LG-045 |

- **A 为唯一后端 writer**，包括 bootstrap/coordinator/adapter 改动。
- **不跨 owner 改文件**；B/C 不改共享后端或 docs/08。
- 每个 probe 目录含 `REPORT.md` + raw 命令 + stop state。
- **个体 worker 不写任务文件**（防 PM 合并冲突）；任务状态由 PM 在中心 `main` 维护。
- 三者均报告**实现完成、待 LG-047 版本 QA**，**不宣称版本通过**。

## 顺序

1. LG-042（本 prep，已冻结契约 + 三 worktree 创建，**不启动 worker**）。
2. LG-043 / LG-044 / LG-045 **并行**（044 依赖 042 而非 043；均依赖 042）。
3. LG-046 串行整合 → 4. LG-047 独立版本 QA。

## Worker 操作与工具约束

- 一律经既有 `pi` + env DeepSeek；**禁止 native 子代理**；不推送/部署/破坏性清理/不使用 8123。
- **参考 SDK 实际工具**：后端用 `google-antigravity==0.1.22` 的真实 `Agent`/`LocalOpenAIAgentConfig`（见 `backend/lightgravity/adapter/proxy.py`、`coordinator/dialogue.py`）；**不新增只读 SDK 工具集、不伪造工具调用**。
- 有效回答路径复用既有真实 `ModelDialogue`；回答不得伪造。
- **测试依赖**：后端 `uv run pytest`（相关子集）+ `uv run mypy`；前端 `npm run build` / `tsc` / vitest。测试聚焦**上下文授权边界与真实 worker 上下文**；前端聚焦 **selection Task 隔离 / API / 错误 / backlink 有意义**；**不镜像 CSS**。
- **积分/凭据**：env only，不打印/复制密钥。

## 预算（严格）

- prep / A / B / C / 整合：**产品推理 0**；不发起真实 product 模型/网络调用。
- C 可选离线 fixture：**人工撰写、明确标注 sample，不假 OCR 真值**。
- **LG-047 唯一预算**：product DeepSeek 真实请求**全程最多 12 次**（含所有 attempt/retry 及 reviewer），**retry 0，串行**，**单请求 wall ≤90s**；副作用未确认即停；**per-campaign 持久账本**，**不重置**；credentials 仅 env；**硬上限须在转发前强制**，而非仅 prompt 提示。
- 无 LAN OCR/embedding 额外调用；QA 用**英文纯文本 fixture 上传**做功能性验证；**先前 OCR QA 管线不变**，若变更须 flag。
- **R1 QA 分配 12 次**，未经 PM 重规划**不自动增长**。若 12 次不足，诚实记录 partial，**保持 gate 未关闭**。
- 本 prep **不发起任何真实调用**。

## 恢复与提交纪律

- 工具 wrapper 不可靠，常在未提交工作时 wall。**每个 worker 必须尽早写 REPORT**，并在**最后约 10 轮预留提交**，避免丢失未提交成果。
- REPORT 需含：变更文件、真实验证命令与 exit、限制如实说明、剩余风险与 stop state。

## 不改动

- 保留所有既有 QA 报告、raw 证据、worktree 与**默认 OFF 特性**（table mode 等）。
- LG-041 保持 `todo` + 质量门阻塞，**不变**。
