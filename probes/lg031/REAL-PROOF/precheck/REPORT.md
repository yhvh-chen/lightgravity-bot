# LG-031 REAL-PROOF — 0 真实生成预检 REPORT

> owner：LG031 接口冻结/真实工程 proof owner｜branch `dev/lg031-real-proof`｜基点 `qa/lg032-runtime-r1@26ea945` + merge `main@3797964`
> **产品真实生成 0**｜**本包不合入 main**｜fakeRoot 与 formalRoot 分离，不混计数

## 结论

复用真实 SDK 0.1.22 + **本地受控 loopback fake 上游**（provider-substitute）+ 真实 `GraphDispatcher` 候选池两阶段生产路径，
在**独立持久** `fixtures/precheck/`（与正式 `fixtures/formal/` 分离）上确认：

| 预检项 | 结果 |
|---|---|
| 冻结 3 节点计划经真实 `PlanValidator` 通过 | **PASS**（keys `alpha,beta,verify`，hash `6a2417d2…`） |
| `max_parallel=1` 下两个 ready 候选**确可见** | **PASS**（首轮 discover `[alpha,beta]`） |
| 可选**非首项** | **PASS**（`beta` 先被领取，`non_first_selected=true`） |
| 选择期**无写工具** | **PASS**（selection 仅 `discover_and_request_claim` + 只读 skill 查询） |
| 执行会话绑定**所选 node 隔离 worktree** | **PASS**（2 distinct worktree，exact 内容 `alpha`/`beta`） |
| 完整选择/执行 session 历史入真实 Run `session_refs` | **PASS**（6/6） |
| 真实 stop 门 | **PASS**（`confirmed=true`，6/6 stopped，`proxy_stopped=true`） |
| verify 节点接收两上游版本化/hash 交接 | **PASS**（alpha+beta，各含 artifact ref + `@sha256:` diff） |
| 持久账本物理路径与 PLAN 一致 | **PASS**（`fixtures/precheck/data/generation/generation.jsonl`，`persistent=true`） |
| 选择后无残留 grant | **PASS**（`active_grants=[]`） |

**未发现真正 runtime 缺陷**；无需自修行为、无需报告 PM 缺陷。

## 关键事实

- 真实 SDK 版本：`0.1.22`（`installed_sdk_version()`）。
- 6 个真实 SDK 会话：2 选择 + 2 执行装（alpha/beta）+ 1 verify 执行 + 1 其余（verify 选择）。
- 首轮 selection 池 `[alpha, beta]`，模型经受限工具选**非首项** `beta`（fence=1），随后 `alpha`，再 `verify`。
- machine truth：`out/alpha.txt`=``alpha``、`out/beta.txt`=``beta``（各自隔离 worktree，无串）。
- 持久账本 `count=14 / limit=200`（precheck-only 上限，fake 无真实 provider；**不混入正式计数**）。

## 边界

- 本预检的 worker 决策由**本地 fake 上游脚本化**，**不冒充**真实 DeepSeek 自主选择；真实 provider 门留 §正式运行。
- 真实 Git worktree 不是 OS 安全沙箱（既有真实限制）。
- 未改产品/reviewer 源码；未触碰 8123 / 其它服务；未复制 `.env`。

## 复现

```bash
uv run --frozen python probes/lg031/REAL-PROOF/precheck/probe_precheck.py \
  --work probes/lg031/REAL-PROOF/fixtures/precheck \
  --out probes/lg031/REAL-PROOF/precheck/precheck-evidence.json
```
