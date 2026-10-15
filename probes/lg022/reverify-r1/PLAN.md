# LG-022 独立复验 R1 — PLAN（冻结，非实施者复验）

> 本文件由**独立复验 owner**（`agent:pi-lg022-reverify-r1`，非 LG-022 R1 返修者、非集成者、
> 非 LG-017/018/019/021/027 实施者）在**执行真实请求前**冻结输入/门/预算/计数验证方法。
> 执行后不改动本节的样本、基点、预算、成功门；追加只以「计划外增补」小节标注，不静默放宽。

## 0. 角色、边界与授权

- 主代理只 PM；本 owner 不做嵌套派工、不 push/deploy/publish，产品代码**只读**，**不自修产品、不自判通过**。
- 允许写范围：`probes/lg022/reverify-r1/**`、本项必要 QA 脚本 `tests/e2e/lg022/**`、LG-022 任务验证记录。
- 不 `reset`/`clean`；保留原件、旧 worktree、dirty、旧失败证据、旧 QA 报告。
- 发现真实产品缺陷：如实标 `fail`，给最小复现 + 证据 + 候选 commit，交主代理另派；集中 QA 最多两轮返修。
- 不继承实施者/R1 自评；LG-017/021/027 旧证据仅作参考，须标候选差异。
- 只使用独立 data/workspace/端口；**不碰 root `8123`**（属 `/home/yhvh/code/lightgravity-bot/.venv`）；
  只清本包签名进程；未知写副作用先确认状态、不自动重放。

## 1. 候选与基点（精确，开工核对）

| 项 | 值 |
|---|---|
| 复验 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r1`（branch `qa/lg022-r1`） |
| 复验 HEAD（开工） | `ec2420e`（= `9698e8a` 整合候选 + QA scaffold/docs；**产品树 == `9698e8a`**，`git diff --stat 9698e8a HEAD` 仅 docs/probes） |
| 整合候选 | `integrate/batch6` @ `9698e8a`（契约 `1.9.0`） |
| LG-022 R1 返修 | `fix/lg022-r1` @ `d07a4a6`（已并入 `9698e8a`） |
| 原 QA 候选 | `bf7851c`（FAIL D1/D2，诚实性 D3） |
| 契约版本 | docs/08 `1.9.0`；本门相关为 `1.8.0` 加性（review 生命周期 + 全局生成计数诊断） |
| SDK | `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`（openai-compat）+ 产品 loopback 认证 proxy → 固定 `https://api.deepseek.com/v1` |
| LG-022 claim | 保持 `in-progress`（`agent:pi-lg022`）；本复验不改 claim，结论交主代理 |

## 2. 计量先行（硬门，先于任何真实请求）

- 旧 QA 首轮曾 hit 429 后 rerun，**累计真实生成次数 unknown**；不得洗成 0/首轮通过/≤10。
  旧 phase unknown **单列保留**，本报告**禁止**宣称「整个 LG-022 累计 < 20」等无证据总数。
- 本复验新 phase 允许**最多 10 次实际向 DeepSeek 转发的生成 HTTP 请求总计**
  （worker/reviewer/直答/Settings 测试/返修/失败/SDK 重试**全部计入**）。
- 必须使用返修后的**共享持久 forward 计数器**：`GenerationCounter`
  （`backend/lightgravity/adapter/proxy.py`），经 `GET /api/v1/diagnostics/generation` 读
  `{count,limit,remaining}`；约束为——**转发前** `reserve()`（原子扣减）、**全 session/role/全测试 stage 共享**
  （`_default_generation_counter()` 进程全局单例）、跨 service/进程重启**不归零**（持久数据根内落盘）。
- **先证明计数/拒超限正确**：用**本地伪上游**（loopback 假 OpenAI-compat 上游，不发 DeepSeek）验证
  ①计数随转发递增；②`limit` 用尽后 `reserve()` 拒绝且**不再转发**；③跨 session 共享；④跨进程重启续读。
  计数不可靠就先 **fail 计量**，不先消耗真请求。
- 缺口说明：当前实现是**进程内**全局计数器（同一进程内跨 session/reviewer 共享），
  但需核实「service 重启不归零」是否有**持久化**。若仅进程内存，则「跨重启不归零」不成立，
  按实测如实标注（见执行结果）；本门据实判定是否 fail 计量。
- 失败/未完成样本记 **失败/未交付**，不用失败中位数称收益，不重跑成功主链。

### 请求预算（预先固定，硬上限 10）

| 用途 | 最大次数 |
|---|---|
| 真 Settings/直答 | ≤1 |
| 真 worker 写任务（主链） | ≤2 |
| 真独立 ModelReviewer 复核（主链，同一 Run） | ≤3 |
| 故障/生命周期边界（优先本地替身/伪上游，尽量 0 真请求） | ≤2 |
| 预留（失败重证，优先伪上游） | ≤2 |
| **合计硬上限** | **10** |

- 输出 ≤18000 tokens；单 HTTP timeout 120s；并发 ≤2；SDK/开发重试 **0**。
- 未完成样本不计交付；不把替身当真实 SDK。

## 3. 待复验缺口（R1 声明已修，须真实链路确认）

### D1（阻断 → 须真实闭环）
1. 真实 coordinator event loop 内独立 `ModelReviewer` **可运行**，不再 `asyncio.run` 异常 →
   不再恒 `unavailable`（`_run_coro_sync` 私有 loop/工作线程）。
2. 真实 Settings 默认 worker/reviewer → 真实写 task → **独立 SDK reviewer** → `awaiting_acceptance`。
3. 人工 accept 绑定**需求/候选/计划 hash**；duplicate/stale 拒绝与幂等符合契约。
4. 至少主链是**真 DeepSeek worker + reviewer**，不能全部 fixture 当真实 SDK。

### D2（阻断 → 须真实/受控确认）
1. `reviewing` 阶段状态/控制请求**不阻塞**（真实运行中 `GET /tasks`、pause/cancel 及时返回）。
2. 暂停/取消有**真实 reviewer stop/release 确认**（`confirmed`/`unknown` 诚实裁定）。
3. 超时/未知 → 保持 pending/槽**不释放**。
4. restart 恢复**不重放**已完成写节点/未知副作用。
5. Task 预算**跨 Run 不重置**。
6. 实际 SDK 资源生命周期可用**受控本地流式 transport**作确定性故障注入（明确
   `SDK-real/provider-substitute`），逐项标注。

### D3（诚实性）
- 成功 Run **无伪 `fail_reason`**；失败历史仍留事件。

### 沿用/不越权
- 沿用已通过 LG-021 前端 + LG-027 专项并核材料性差异；新协作**默认关闭**，基线首版功能不被影响。
- `source`/`vectors` 新路径质量**不在本门**，不得越权扩大已有 Task API。
- 最小必要真浏览器增量**可复用旧证据**，不重跑完整 UI 矩阵。

## 4. 成功门（须全部满足才 done；缺任一保持 in-progress/fail）

1. 计量先行通过（伪上游证明计数/拒超限/共享/重启语义），且本 phase 真转发 ≤10 且可精确计数。
2. D1 全链真实闭环（真 worker + 真 reviewer → `awaiting_acceptance` → accept 绑定 + duplicate/stale）。
3. D2 reviewing 不阻塞 + stop/release 确认 + 超时/未知保留槽 + restart 不重放 + 跨 Run 预算。
4. D3 成功 Run 无 `fail_reason`，失败仍留事件。
5. 真实/替身逐项标清；未测项列明；不以 R1 单点成功宣全产品通过。

## 5. 证据与报告

- 原始脱敏证据存 `probes/lg022/reverify-r1/evidence/**`；真实/替身/伪上游逐项标。
- 报告 `probes/lg022/reverify-r1/REPORT.md`；状态 `STATUS.md`；绑定候选 commit + 实际调用计数 + unknown。
- 敏感边界：token/凭证不入 prompt/仓库/日志；请求体/headers 不落日志。
- 精确本地 commit；先写报告再提交。

## 6. 环境与命令

- `uv sync --frozen`（`.venv`）；真实服务 `uv run python -m lightgravity start --data-dir <独立> --workspace-root <独立> --secret-store <独立> --host 127.0.0.1 --port <独立> --frontend-dist frontend/dist`。
- 单检查 ≤120s；长过程短轮询 ≤5s；dev API 重试 0；idle 240s。
