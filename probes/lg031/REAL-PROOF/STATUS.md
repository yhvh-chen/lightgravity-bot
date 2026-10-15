# LG-031 REAL-PROOF — STATUS

> owner：LG031 接口冻结/真实工程 proof owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）
> branch `dev/lg031-real-proof`｜基点 `qa/lg032-runtime-r1@26ea945` + merge `main@3797964`
> **本包不合入 main**；旧 worktree/分支/证据全部保留；未 reset/clean/覆盖/重复 pick

## 进度

| # | 步骤 | 状态 |
|---|---|---|
| 0 | 读 AGENTS/agent/PROJECT/PROGRESS/docs06/08 变更控制、029/031/032、R1 REPORT/FINDINGS、RUNTIME-AUTH-INTEGRATION、023 cohort3 共享 ledger 方法 | DONE |
| 1 | 核全部 Git/worktree/dirty/进程；保全旧证据 | DONE |
| 2 | 建 `dev/lg031-real-proof`@`26ea945` + 安全 merge `main@3797964`；核产品树字节同一 afcae82 | DONE |
| 3 | 冻结契约 **1.11.0 MINOR**（docs08 变更控制先行 → constants/测试/README/PROJECT/agent/docs06）；确认 LG-029 done | DONE |
| 4 | 冻结 PLAN（fixture/计划/prompt/tool/caps/ledger 路径） | DONE |
| 5 | 0 真实生成预检（fakeRoot 分离）：两候选可见/非首项/隔离/session/stopgate/账本 — **PASS** | DONE |
| 6 | 正式 harness dry-run（本地 fake，`fixtures/dryrun`）验证全流程 — **PASS** | DONE |
| 7 | 正式真实 DeepSeek **一次**运行（`fixtures/formal`） | DONE（PARTIAL：24/24 上限在 verify 处耗尽） |
| 8 | 真实机器门（alpha/beta 精确/pass）；真实独立 ModelReviewer + 绑定 accept | 机器门 PASS；reviewer/accept **未达**（budget） |
| 9 | REPORT + 私有原件 host + 精准本地 commit | DONE |

## 预注册（首请求前冻结，`2026-10-16`）

- **HEAD**：`fb9c481`（本包唯一 writer；产品树 `backend/frontend/tests/pyproject/uv.lock/Makefile` 字节同一 `afcae82`）。
- **源锚**：`qa/lg032-runtime-r1@26ea945`（R1 四门 PASS）+ `main@3797964`（仅 LG-024 docs/包）。
- **SDK**：`google-antigravity==0.1.22`。
- **实际模型**：`deepseek-v4-flash`（`https://api.deepseek.com/v1`；env `DEEPSEEK_API_KEY` 受控使用，不打印/不落盘）。
- **plan hash**：`6a2417d24cd362b391d148cbd6681695dea3ab284b14fef9562e4538ec4889df`（3 节点 alpha/beta/verify）。
- **probe code hash**：`d7136c09941e7ddcb79817c52bac685535bca332308e6acce85cce0366e66814`。
- **PLAN hash**：`98eb0b6e80e416a663eb9858a056a24f6e966340f3cf3d3fff34796c037c25c5`。
- **初始 commit**：`fixtures/formal/workspaces/task-ws` 固定 `README.md`；commit 在正式运行 evidence 记录。
- **machine truth**：`out/alpha.txt`==`alpha`、`out/beta.txt`==`beta`（各自隔离 worktree，无串）。
- **ledger 物理路径**：`fixtures/formal/data/generation/generation.jsonl`（持久、跨会话/Run 不归零）。
- **caps**：新增真实 DeepSeek 生成总上限 **24**；HTTP 120s；API/SDK retry 0；并发 <=2；每请求 output <=12000（注：产品 openai-compat 路径不参数化输出上限，如实记录实际观测）。
- **仅一次正式 fixture 运行，不重复**；旧 LG031 34/40 不归零、旧 phase 剩 6 不再消费。

## 关键事实

- 契约 **1.11.0**（实际公开兼容变化保守 MINOR）：README/PROJECT/agent/docs06/docs08/constants/测试一致。
- 预检与正式 **fakeRoot/formalRoot 分离**，不混计数。
- `814 passed`（R1）+ 本包新增版本断言通过；`mypy 137 files clean`（R1，未改 runtime 逻辑）。
- 8123 uvicorn（pid 3320750）与其它长期服务未触碰。

## 真实运行结果（`evidence/formal-real.redacted.json`；原始私有 `fixtures/raw-evidence/formal-real.raw.json`）

- **真实生成 24/24**（持久账本 `count=24,limit=24,remaining=0,persistent=true,corrupt=false`）。
- **真实 SDK 会话 6**（3 选择 + 3 执行），全部入真实 Run `session_refs`；真实 stop 门 `confirmed=true`、`6/6 stopped`、`proxy_stopped=true`。
- **alpha/beta 双 worker**：真实模型经 `discover_and_request_claim` 领取（fence=1），各写精确产物（独立机器门 `alpha_exact/beta_exact=true`、无串）。
- **verify 节点**：接收 4 条版本化/hash 上游交接；其执行会话首请求在共享上限被 **429 转发前拒绝**，Run outcome=`failed`。
- **真实自由选择**：正式模型选首项 alpha（`req_alpha_6063caa5`）；预检已证非首项可选且未被程序预绑定。
- **结论：PARTIAL**——门 1–4/6 PASS；门 5（独立 ModelReviewer）与 7（绑定 accept）因预注册预算耗尽未达。**非 runtime 缺陷**（429 为转发前账本拒绝，安全边界正确）。

## 终态

- **HEAD**：本包版本提交；契约 **1.11.0**；R1 四门仍 PASS（产品树字节同一 afcae82）。
- **LG-031 保持 `in-progress`**（真实 provider 门未全齐）；**LG-029 `done`**；**LG-032 `in-progress`**。
- **旧 LG031 34/40 不归零**；新已知整体工程上限 **58**（=34+本次 24）；旧 phase 剩 6 不再消费。
- 下一独立 032 阶段 B 前置：同一冻结 fixture/计划/门 + **更大但同样预注册** 的单一持久 ledger，复验 verify/reviewer/accept；本包不擅自扩额、不重跑、不新 ledger 归零。

## 未测 / 边界

- 若正式运行出现 harness/计量/重要 source 错误 → 停止 proof，不边改边重跑；只最小 repro 报告 PM。
- 真实 Git worktree 不是 OS 安全沙箱（既有真实限制）。
