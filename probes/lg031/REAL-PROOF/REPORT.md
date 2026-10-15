---
title: "LG-031 真实工程 proof — REPORT（真实 DeepSeek，单次正式运行）"
doc_type: report
category: engineering
owner: "LG031 接口冻结/真实工程 proof owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "dev/lg031-real-proof"
base: "qa/lg032-runtime-r1@26ea945 + merge main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash"
updated: "2026-10-16"
---

# LG-031 真实工程 proof — REPORT

## 0. 一句话结论

在**真实 DeepSeek** provider 下执行**唯一一次**正式 fixture：真实双逻辑 worker 经产品 `GraphDispatcher` 候选池两阶段
生命周期，真实模型通过 SDK 工具调用 `discover_and_request_claim` 并各自写出精确产物 `out/alpha.txt`=`alpha`、
`out/beta.txt`=`beta`（各自隔离 worktree、无串），`verify` 节点**真实接收两个已通过节点的版本化/hash 上游交接**（4 条 ref）。
**但 verify 节点的真实执行在共享生成上限 24/24 处被 429 拒绝（转发前拒绝），因此独立 ModelReviewer + 绑定 accept 门未到达。**
按预注册「仅一次、不重复、不归零」记录为 **PARTIAL**：真实 provider 的 1–4 项通过，5–7 项因预算耗尽未达。
LG-031 保持 **in-progress**（真实 provider 门未全齐）。

## 1. 预注册事实（首请求前冻结）

| 项 | 值 |
|---|---|
| HEAD | `fb9c481`（产品树 `backend/frontend/tests/pyproject/uv.lock/Makefile` 字节同一 `afcae82`） |
| 源锚 | `qa/lg032-runtime-r1@26ea945` + `main@3797964` |
| SDK | `google-antigravity==0.1.22`（`installed_sdk_version()` 实证） |
| 实际模型 | `deepseek-v4-flash` @ `https://api.deepseek.com/v1`（env 凭证，不打印/不落盘） |
| plan hash | `6a2417d24cd362b391d148cbd6681695dea3ab284b14fef9562e4538ec4889df` |
| probe code hash | `d7136c09941e7ddcb79817c52bac685535bca332308e6acce85cce0366e66814` |
| ledger 路径 | `fixtures/formal/data/generation/generation.jsonl`（持久） |
| caps | 真实生成 24；HTTP 120s；retry 0；并发 <=2；output <=12000（产品 openai-compat 不参数化输出上限） |
| 初始 commit | `fixtures/formal/workspaces/task-ws`（固定 `README.md`） |

## 2. 真实运行数据（`evidence/formal-real.json`）

- 真实生成请求：**24 / 24**（持久账本 `count=24, limit=24, remaining=0, persistent=true, corrupt=false`；24 条 JSONL 全 `reserved`）。
- 真实 SDK 会话：**6**（3 选择 + 3 执行：alpha/beta/verify），全部进入真实 Run `session_refs`（`sessions_in_run_refs=true`）。
- 真实 stop 门：`confirmed=true`，`sessions_stopped=6/6`，`proxy_stopped=true`。
- 真实工具调用 22 次；选择会话均先 `discover_and_request_claim` 后领取。
- elapsed：**56.495s**（< 480s 有界）。
- 失败事件 1 条：`AntigravityExecutionError: HTTP 429 local auth proxy call budget exhausted`（verify 执行会话首请求**转发前**被拒）。

## 3. 逐门结果

| 真实门 | 结果 | 证据 |
|---|---|---|
| ① 真实至少 2 逻辑 worker | **PASS** | 2 个实现节点 `passed`，同 `implementation` Member 两次 claim（fence=1） |
| ② 候选池 >=2 且可选非首项 | **PASS（能力）/ 事实选择首项** | 预检证池 `[alpha,beta]` 可见、非首项可选；正式真实模型**自由选择 alpha（首项）**（`req_alpha_6063caa5` 首授予），未程序预绑定 |
| ③ 所选 node 真实隔离执行 + 精确产物 | **PASS** | alpha/beta 各在自己的 `.lg-worktrees/<run>/<key>` worktree；独立机器门 `alpha_exact/beta_exact=true`、`no_cross_contamination=true` |
| ④ verify 接收版本化/hash 上游交接 | **PASS** | `verify.upstream_artifact_refs` 4 条（alpha+beta，各含 artifact ref + `@sha256:` diff 证据） |
| ⑤ 真实独立 ModelReviewer | **未达**（budget） | verify 执行 429，Run outcome=`failed`，未生成完整候选进入 review |
| ⑥ 真实 stopgate | **PASS** | `confirmed=true`，6/6 stopped，proxy stopped |
| ⑦ 绑定 accept | **未达** | 因 ⑤ 未达，无 `awaiting_acceptance` |

**机器门（独立于 reviewer）**：`alpha_exact=true, beta_exact=true, no_cross_contamination=true, verify_no_write=true,
verify_has_two_handoffs=true, all_nodes_passed=false` ⇒ **`pass=false`**（仅因 verify 预算耗尽）。

## 4. 缺口与性质

- **缺口**：verify 节点真实执行在共享上限 24 被 429 拒绝；独立 reviewer + accept 未执行。
- **性质**：**预注册预算耗尽**，不是 runtime 缺陷——429 于**转发前**由持久账本拒绝，`reserve-before-forward` 与
  `corrupt=false/绝不当 0` 行为正确；stop 门与隔离/交接均成立。
- **不重复**：按预注册「仅一次正式运行、不重复、不归零」，本包**不重跑**；旧 LG031 34/40 不归零，新已知整体工程
  上限 58（=34 + 本次 24）。
- **模型自由选择**：真实模型选了首项 alpha。要求为「多候选时允许取非首项以检验合法自由选择」，**未**程序预绑定或代选；
  预检已证非首项可选（fake 脚本化），正式由真实模型自由决定。

## 5. 持久原件（私有，create-only，700/600）

- 全部产品 SoT：`fixtures/formal/data/{tasks,runs,subtasks,members,events,artifacts,generation,settings,locks}/**`。
- 真实 worktree 与未交付 diff：`fixtures/formal/workspaces/.lg-worktrees/<run>/{alpha,beta}/**`。
- 独立机器门核验：alpha/beta 精确内容 + sha256 与账本记录一致（本次 REPORT 附）。
- 脱敏 evidence：`evidence/formal-real.json`（无 prompt/headers/令牌/密钥；`real_base_url`、模型名非秘密）。
- **无 SDK session DB**（本次未设置 SDK `save_dir`，会话为进程内；如实记录，不补造）。
- 未读无关/tmp 用户数据；未复制 `.env`；未触碰 8123 / 其它服务。

## 6. 计费/计量

- 本包真实生成 **24**（唯一正式运行）；预检/dry-run 均为本地 fake 上游（**0 真实**），fakeRoot 与 formalRoot 分离。
- known token：SDK 事件未汇总 reported usage（Run outcome=failed 于 verify），如实记 **unknown**（绝不当 0）。
- 旧 LG031 工程 **34（10+14+10）不归零**；LG-023/022 旧成本单列 unknown；总旧 + 新 **58**。
- 非 032 成本对照，不预设省 token。

## 7. 状态与后续（交 PM）

- **LG-031 保持 `in-progress`**：真实 provider 门 5–7（独立 reviewer / 绑定 accept）因预注册预算耗尽未达。
- **LG-029 `done`**（R1 门2 正向确认；本包再确认一次执行身份 default-deny/不落盘边界保持）。
- **LG-032** 保持 `in-progress`（阶段 B 暂停，依赖 031 真实门）。
- **下一独立 032 阶段 B 前置建议**：以**同一冻结 fixture/计划/门**、**更大但同样预注册的单一持久 ledger 上限**
  （verify 只读节点需要额外预算）复验一次；本包不擅自扩额、不重跑、不新 ledger 归零。
- 本包**不合入 main**；HEAD/契约/protocolhash/真实次数见 STATUS。
