# LG-022 首版端到端与故障独立集中 QA — 计划（QA-PLAN）

> 在执行真实请求前固定。执行后不改动本节已冻结的样本/基点/预算/成功门；如需追加，
> 只以「计划外增补」小节追加并明确标注，不静默放宽。

## 0. 角色、边界与授权

- 本门 owner 为 LG-022 的**独立 QA 执行者**（agent:pi-lg022），不属于 LG-017/018/019/021/027 实施者或集成者。
- 主代理只 PM；本 owner 不做嵌套派工、不修改产品代码。产品代码**只读**。
- 允许写范围：`probes/lg022/**`、必要的 `tests/e2e/lg022/**`、LG-022 任务记录的验证记录。
- 授权：本地实施与验收；**不 push / deploy / publish**。不 `reset` / `clean`；保留原件、旧 worktree、dirty。
- 发现真实产品缺陷：如实标 `fail`，给出准确最小复现、证据与候选 commit，交主代理另派返修；**QA 不自修产品、不自判通过**。
- 不继承实施者自评（LG-017/018/019/021/027 的 pass/证据仅作参考，须标候选差异后自行验证）。

## 1. 候选与基点（精确）

| 项 | 值 |
|---|---|
| QA worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg022`（branch `qa/lg022`） |
| 候选 HEAD（起点） | `bf7851cdb14e97f7c32815e1811a83ebdb89e2cb` |
| 产品树等价 | main `7c565fd` 整合候选（batch3 `635489e` reviewer UI + batch4 LG-021 增量 verdict、LG-036） |
| 参考旧候选 | LG-021 首验 `61fad69`、增量 `e4cef4a`（**须标候选差异**，不冒充已验新路径） |
| 契约版本 | docs/08 `1.7.0` |
| SDK | `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`（openai-compat）+ 产品 loopback 认证 proxy → 固定 upstream `https://api.deepseek.com/v1` |

## 2. 实际模型、资源与计数（硬约束）

- 产品真实 DeepSeek HTTP 生成请求：**硬上限 10 次**（统一计数，逐请求记录非秘密元数据：序号/用途/模型/时间/结果/是否为故障注入）。
- SDK 重试：**0**（不重试；一次 HTTP 失败即记录失败，不自动重放）。
- 总输出 ≤18000 tokens；单 HTTP timeout 120s；并发 ≤2。
- 计数方式：产品未暴露总计数器时，**以 proxy 侧 `call_count` + 逐请求元数据为实际计数**；无法确证次数的项标 `unknown`，不写「受上限控制」。
- 故障注入**本地替身不得当真模型**：替身仅用于故障路径（HTTP 错误/超时/断连），与真实模型调用分开计。
- 凭证：仅受控进程 env（`DEEPSEEK_API_KEY`）/ `credential_ref`；不输出、不写提示词仓库、不复制 `.env`。敏感 Settings 请求体不得进入日志原文。

### 请求预算分配（预先固定）

| 用途 | 最大次数 |
|---|---|
| Settings 模型连通/直答（coordinator 单轮轻问答） | 1 |
| 写任务 worker 真实执行（主链路） | 1 |
| 独立 ModelReviewer 复核（主链路） | 1 |
| 返修新 Run worker + 复验 reviewer（若触发） | 2 |
| 故障/生命周期边界（可用替身则不耗真调用） | ≤2 |
| 预留（失败重证/未预期） | ≤3 |
| **合计硬上限** | **10** |

### 资源

- 独立 data root / workspace / secret store（`/tmp/lg022-qa.*`），`frontend/dist` 用真实构建。
- 专用 loopback 端口（随机空闲端口），**不碰 root `8123`**、不碰其它 worktree/worker 进程。
- 只清理自有签名 PID/临时根；未知副作用不自动重放。
- 真实浏览器沿用 LG-021 必要增量（真实 Firefox native BiDi），不重跑全 UI 矩阵。

## 3. 成功门（必须全部满足，缺一不得 done）

1. **最小真实产品路径**（真实 HTTP + 真实 DeepSeek，非 unit/mock）：
   - Settings 受控配置 worker 默认 + reviewer 默认（含 runtime token/受保护写、pin 正确）。
   - 轻问答**不建 Task/Run**（直答，真实模型或诚实 unavailable）。
   - 真实写任务 → 队列 → worker 真实执行 → 真实产物。
   - 独立 SDK reviewer 检查**最终候选**（真实模型、独立连接/上下文、只读候选、不写控制状态）。
   - 有限返修/新 Run 与**旧候选保留**；复验。
   - 人工 accept 绑定**准确版本**；重复/过期请求不作用新候选。
2. **并行两节点 + 真实 worktree 隔离 + 最终整合候选**：至少真实 Git/受控替身覆盖故障；**至少含真实 SDK 写 + 独立 review 链**。
3. **独立 reviewer 只读候选、不写控制状态；缺 reviewer ⇒ 诚实 `unavailable` 且 accept 不开放。**
4. **故障与生命周期**：
   - 状态查询不等待执行；
   - 变更（PATCH/乐观 revision）；
   - 暂停/继续/取消确认与超时未知停止；
   - **暂停/取消/重启须包含「独立 ModelReviewer 正在运行」阶段**，并确认 reviewer 实际停止/释放（不能把 worker 已停当作 reviewer 已停）；
   - 浏览器断线后台继续 / SSE 游标重连不重复；
   - 重启恢复不重放未知副作用；
   - 重复消息/重复验收/写冲突/Task 总预算跨 Run；
   - pin 漂移 / 原生 session 续接 / 资源释放。
5. **敏感边界**：token/凭证不进浏览器持久状态、对话、任务/日志/导出。
6. **诚实标注**：真实 SDK 与故障注入替身逐项标清；不以预期异常伪造成功日志；未验证项列明。

> 判定：任一重要缺陷未消除且阻断 → 本门 `fail`（不 done）。unit/mock、真实 Git、浏览器 `--no-executor` 均**不得**冒充 SDK 闭环。

## 4. 证据与报告要求

- 原始脱敏证据存 `probes/lg022/evidence/**`；每项绑定候选 commit + 需求 + 候选产物版本。
- 报告 `probes/lg022/REPORT.md` 列：成功 / 失败 / 未验证 + 重要性 + 是否阻断本门。
- 完整尝试成本（真实调用数、unknown、墙钟、轮数）。
- 精确本地 commit；基于真实结果更新 LG-022 任务记录。
- 输出 commit / 证据 / 缺陷 / 复验建议；**不宣称扩展版本 LG-032/LG-040 也通过**。

## 5. 执行命令与长过程策略

- 真实服务：`uv run python -m lightgravity start --data-dir … --workspace-root … --secret-store … --host 127.0.0.1 --port <free> --frontend-dist frontend/dist`（默认接真实 executor；故障注入用受控替身/参数）。
- 浏览器：复用 LG-021 的 Firefox BiDi helper 模式（必要增量），单检查 ≤120s。
- 单检查 ≤120s；长过程受控短轮询（≤5s 间隔），不 `sleep 60` 盲等；dev API 重试 0；idle 240s。

## 6. 已知候选差异（预登记）

- LG-021 首验候选 `61fad69` **内无 reviewer UI**；增量 `e4cef4a` 已补，但**真实 ModelReviewer 执行**仍未在 021 覆盖，属本门。
- LG-027 未暴露真实调用计数（记 unknown）；本门用 proxy `call_count` 自建计数。
- LG-017 仅有 1 次真实 reviewer 单轮成功探针；**不证明** reviewer 运行中的暂停/取消/重启生命周期边界。
