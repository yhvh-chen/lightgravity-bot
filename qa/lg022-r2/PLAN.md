# LG-022 独立复验 R2 — PLAN（冻结，非实施/集成者复验）

> 本文件由**独立复验 owner**（`agent:pi-lg022-r2` 独立新 pi 上下文；非 LG-022 R2 返修者 `fix/lg022-r2`、
> 非集成者 `integrate/batch7`、非 LG-017/018/019/021/027 实施者）在**执行任何真实 DeepSeek 请求前**冻结
> 基点、门、预算与计数方法。执行后不改动本节样本/基点/预算/成功门；仅以「计划外增补」小节追加，不静默放宽。

## 0. 角色、边界与授权

- 主代理只 PM；本 owner 不做嵌套派工、不 push/deploy/publish；产品代码**只读**，**不自修产品、不自判通过**。
- 允许写范围：`qa/lg022-r2/**`、`probes/lg022/reverify-r2/**`、必要 QA 脚本（`qa/lg022-r2/harness/**`）、LG-022 任务状态/验证记录。
- **不** `reset`/`clean`/整树覆盖；保留全部旧 worktree、dirty、旧失败证据、旧 QA 报告、原始快照。
- 发现真实产品缺陷：如实标 `fail`，给最小 repro + 严重度 + 精准返修目标 + 证据，交主代理另派；QA 不自修。
- 只使用独立 data/workspace/端口；**不碰 root `8123`**（属 `/home/yhvh/code/lightgravity-bot/.venv`，pid 3320750）；
  只精确停止本包签名进程；未知写副作用先确认状态、不自动重放。
- 凭证只来自受控 env（`DEEPSEEK_API_KEY`）；不打印请求头/密钥/runtime grant/prompt。

## 1. 候选与基点（开工核对，精确）

| 项 | 值 |
|---|---|
| 复验 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`） |
| 复验 HEAD（开工） | `0144eb7`（= `integrate/batch7` 整合候选；产品树 == 最终整合 HEAD 产品树，见下） |
| 最终整合 HEAD | `85adc82`（`integrate/batch7` = `0144eb7` + INTEGRATION-7 文档提交；`git diff 0144eb7 85adc82` 仅 4 个文档文件，**产品树完全相同**） |
| LG-022 R2 返修 | `fix/lg022-r2` @ `e59e12a`（合入 `8a92439`，契约 `1.10.0`） |
| LG-031 R2 | `fix/lg031-r2` @ `3821620`（合入 `0144eb7`：自主 claim + 共享生成计数注入） |
| 契约版本 | docs/08 `1.10.0`；本门相关为 `1.10.0` 加性（停止门真实停止事实 + `reviewer_cleanup` + 持久生成账本 `persistent`/`corrupt`） |
| 原 QA 首轮 | `qa/lg022` @ `8e81089`（FAIL D1/D2 + D3）；真实总数 **unknown**（单列保留，不洗 0） |
| R1 复验 | `qa/lg022-r1` @ `6228474`（FAIL：stop-gate 死锁 + counter 跨重启不持久）；真实 **6/10**（单列保留） |
| SDK | `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`（openai-compat）+ 产品 loopback 认证 proxy → 固定 `https://api.deepseek.com/v1` |
| LG-022 claim | 保持 `in-progress`（`agent:pi-lg022`）；本复验不改 claim，结论交主代理 |

- 关键要求：新整合必须**保留 persistent ledger**（`adapter/generation_ledger.py`），
  **不得**回退为 031 内存 `GenerationCounter`。集成者 INTEGRATION-7 §2.2/§3 声称已保证；本门离线独立验证。

## 2. 计量先行（硬门，先于任何真实请求）

- 旧 QA 首轮真实总数 **unknown**，R1 已知 **6/10**，两轮失败记录均保留、**单列**；
  **不得**宣称本任务累计 ≤20 等无证据总数；本 phase 10 为当前授权内**新版本复验预算**，不借改代码/重放未知写入。
- 本 R2 phase 允许**最多 10 次实际向 DeepSeek 转发的生成 HTTP 请求总计**
  （worker/reviewer/直答/Settings 测试/返修/失败/SDK 重试**全部计入**）。
- 共享**持久**账本路径**先在 PLAN 固定**：`<data_dir>/generation/generation.jsonl` + `generation.count.json`，
  经 `GET /api/v1/diagnostics/generation` 读 `{count,limit,remaining,persistent,corrupt?}`；
  约束：**转发前** `reserve()` 原子持久预留、全 worker/reviewer/session/进程共享、**跨重启不归零**、
  **损坏/不可读即拒绝转发并报 unknown（-1 / corrupt），绝不当 0**。
- **先离线独立证明账本语义再耗真请求**（本地伪上游，0 真转发）：
  ①计数随转发递增；②`limit` 用尽 `reserve()` 拒绝且不再转发；③跨 session/role 共享；
  ④**真子进程**重开续读不归零；⑤并发竞争不超（多进程/多线程 reserve，`count == limit` 恰为限）；
  ⑥损坏 ledger 拒绝且报 unknown/`corrupt`，不当 0。
- 账本不可靠则**直接 fail 计量**，不先消耗真请求。
- 缺口说明：若实测「跨重启不归零」不成立或损坏被当 0，则计量门 fail，据实判定。

### 请求预算（预先固定，硬上限 10）

| 用途 | 最大次数 |
|---|---|
| 真 Settings/直答（默认 worker+reviewer pin） | ≤1 |
| 真 worker 写任务（主链） | ≤3 |
| 真独立 ModelReviewer 复核（主链，同一 Run） | ≤3 |
| 故障/生命周期边界（优先本地受控 transport / 伪上游，尽量 0 真请求） | ≤1 |
| 预留（失败重证，优先伪上游） | ≤2 |
| **合计硬上限** | **10** |

- 输出 ≤18000 tokens；单 HTTP timeout 120s；并发 ≤2；SDK/开发重试 **0**；wall 1200s；maxround 210；noncache 280k；idle 240s。
- 未完成样本不计交付；不把替身当真实 SDK；`fake` 无 `session_refs` 不能冒充真生命周期。
- usage 未知标 `unknown`，不写 0。

## 3. 待复验缺口（R2 声明已修，须真实链路确认）

### A（D1 阻断 → 须真实闭环）
1. 真实 coordinator event loop 内独立 `ModelReviewer` 可运行，不再恒 `unavailable`。
2. **真实 Settings 默认 worker + reviewer** → **真实 Task** → **实际 SDK 写产物** →
   **coordinator eventloop 异步独立 SDK reviewer** → **真实 worker/reviewer 资源停止证明**
   （非空 `session_refs` 保持历史、不删 refs、不预填 `cleanup=done`、不伪造）→ `awaiting_acceptance`。
3. 绑定 requirements/candidate/planhash 的**人工 accept**；验证**幂等/duplicate/stale 拒绝**。
4. **不能**用 standalone reviewer 替代产品路径；**必须**至少一次真 DeepSeek worker + reviewer 主链。

### D1/D2（须真实/受控确认）
1. `reviewing` 期间 `GET /tasks`/`status`/control **不阻塞**。
2. 暂停/取消有**真实 reviewer 资源 stop/release 确认**；超时/未知 → 保持 pending/槽**不释放**。
3. restart 恢复**不重放**已完成写节点/未知副作用（反重放）；Task 预算**跨 Run 不重置**。
4. 实际 SDK 资源生命周期可用 **actual SDK + 本地受控 transport** 做确定性故障注入，
   明确标 `SDK-real / provider-substitute`；`fake` 无 `session_refs` 不算真生命周期证据。

### D2（R2 停止门）
- 成功 Run：`session_refs` 非空 + `cleanup` 非 `done` 时，停止门须由**权威适配器停止事实**
  （`AntigravityExecutor.confirm_stopped`：`Agent.__aexit__` 关成功 + proxy 停）放行到 `awaiting_acceptance`；
  **未知/仍活跃/关闭失败**保持 `unconfirmed` 且**不释放槽**、保留 `session_refs`。

### B（D2 计量）
- `GenerationCounter` **跨进程/实例/role/session/重启**总额一致；转发前原子预留；竞争不超；
  损坏 fail-closed / unknown 非 0；**不得**回退为纯内存 counter。

### D3（诚实性）
- 成功 Run **无伪 `fail_reason`**；失败历史仍留事件。

### 沿用/不越权
- 沿用已通过 LG-021 前端 + LG-027 专项，**按材料差异引用**；旧 021/027 证据仅作参考。
- 新资料质量与去中心化**不在本门**且默认 off；不夸大全产品。

## 4. 成功门（须全部满足才 done；缺任一保持 in-progress/fail）

1. **计量先行离线通过**（持久 ledger：递增/拒超限/共享/真子进程重启续读/并发不超/损坏 fail-closed unknown 非 0），
   且本 phase 真转发 ≤10 且可精确计数；ledger 为 persistent 而非内存。
2. **A/D1 全链真实闭环**：真 worker + 真 reviewer → `awaiting_acceptance` → 人工 accept 绑定 + duplicate/stale 幂等；
   `session_refs` 保留、无伪 `cleanup=done`、真实停止证明。
3. **D2** reviewing 不阻塞 + stop/release 确认 + 超时/未知保留槽 + restart 不重放 + 跨 Run 预算。
4. **D3** 成功 Run 无 `fail_reason`，失败仍留事件。
5. 真实/替身逐项标清；未测项列明；不以单点成功宣全产品通过。

## 5. 证据与报告

- 原始脱敏证据存 `qa/lg022-r2/evidence/**`；真实/替身/伪上游逐项标。
- 报告 `qa/lg022-r2/REPORT.md`；状态 `qa/lg022-r2/STATUS.md`；绑定候选 commit + 实际调用计数 + unknown。
- 敏感边界：token/凭证不入 prompt/仓库/日志；请求体/headers 不落日志。
- 精确本地 commit；**先写报告再提交**；未通过不可计交付。

## 6. 环境与命令

- `uv sync --frozen`（独立 `.venv`）；真实服务经独立 data/workspace/port。
- 单检查/单长命令 ≤120s；长过程短轮询 ≤5s；dev API 重试 0。
- 两轮返修集中门当前为**第二轮复验**；若仍失败保存准确阻塞供 PM 重拆，不无界修复。
