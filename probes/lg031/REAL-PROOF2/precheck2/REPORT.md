---
title: "LG-031 REAL-PROOF2 — 0 真实生成预检 REPORT（实际 build_runtime + localfake 三节点）"
doc_type: report
category: engineering
owner: "LG031 REAL-PROOF2 owner"
branch: "dev/lg031-real-proof2"
updated: "2026-10-16"
real_generation: 0
---

# LG-031 REAL-PROOF2 — 预检 REPORT

> 产品真实生成 **0**｜fakeRoot `fixtures/precheck2/` 与 formalRoot `fixtures/formal/` **分离**，不混计数。
> 未改产品/reviewer 源码；未触碰 8123/其它服务；未复制 `.env`；未打印 prompt/headers/凭证。

## 结论

复用真实 SDK 0.1.22 + 本地受控 loopback fake 上游（provider-substitute）+ **实际 `build_runtime` 启动路径**
+ 真实 `GraphDispatcher` 候选池两阶段生产组件，在**独立持久** `fixtures/precheck2/`（create-only，不 rmtree）上确认：

| 预检项 | 结果 |
|---|---|
| **实际 `build_runtime` 启动**后物理 ledger 路径 == 期望 | **PASS**（`<settings.data_dir>/generation/generation.jsonl`，`persistent=true`，`count` 前进） |
| env pin **未**被 bootstrap 静默改写到别处 | **PASS**（`env_pin_matches_resolved=true`） |
| 所有 role 共用**同一** actual `settings.data_dir` 账本 | **PASS**（单一 `generation.jsonl` 从前到后计数 1→15） |
| 三节点计划经真实 `PlanValidator` 校验 | **PASS**（keys `alpha,beta,verify`，hash `6a2417d2…`，与冻结模板一致） |
| `max_parallel=1` 下两个 ready 候选**确可见** | **PASS**（`first_pool_had_two=true`） |
| 可选非首项（本预检 fake 脚本化为非首项） | **PASS**（beta 先被领取；选择期无写工具） |
| 选择期无写工具 | **PASS**（`selection_offers_write_tool=false`） |
| 执行会话绑定所选 node 隔离 worktree + 精确产物 | **PASS**（`distinct_worktrees=2`，`machine_truth_ok=true`） |
| verify 接收两上游版本化/hash 交接 | **PASS**（4 条 handoff） |
| 完整选择/执行 session 历史入真实 Run `session_refs` | **PASS**（`sessions_in_run_refs=true`） |
| 真实 stop 门 | **PASS**（`confirmed=true`，6/6 stopped，`proxy_stopped=true`） |
| 选择后无残留 grant | **PASS**（`active_grants=[]`） |
| **每 stage ledger count 记录**（默认串行） | **PASS**（`ledger_stages` 14 条，含 `before/after_dispatch` 与每 execution 起止） |

**未发现真正 runtime 缺陷**；无需自修行为、无需报告 PM 缺陷。全 0 本地 fake 预检输出与源码/hash 已固定。

## 关键事实

- 真实 SDK 版本：`0.1.22`（`installed_sdk_version()`）。
- `part_b` 三节点运行 outcome `succeeded`；6 真实 SDK 会话（3 选择 + 3 执行）全部入真实 Run `session_refs`。
- 持久账本：`fixtures/precheck2/data/generation/generation.jsonl`（precheck-only 上限 200；fake 无真实 provider；**不混入正式计数**）。
- 预检 root **create-only**：若已存在则拒绝运行（不覆盖、不 rmtree）。
- 计划 hash `6a2417d24cd362b391d148cbd6681695dea3ab284b14fef9562e4538ec4889df` 与旧 proof 冻结计划模板一致。

## 边界

- 本预检 worker 决策由**本地 fake 上游脚本化**，**不冒充**真实 DeepSeek 自主选择；真实 provider 门留正式运行。
- 真实 Git worktree 不是 OS 安全沙箱（既有真实限制）。
- `save_dir` 观测在正式 harness 中经既有公开 `context.save_dir` 启用；本预检不写正式 SDK 存储。

## harness 装配注意（非产品缺陷）

- 正式 harness 首次把 `context.save_dir` 放在授权 `workspace_root` **之外**时，产品正确拒绝：
  选择期 scratch workspace 由 `save_dir` 派生，逃出授权 root ⇒ `config_invalid`（execution_blocked）。
- 处置：把 `save_dir` 放在**授权 `workspace_root` 内部**（`<workspace_root>/.lg-sdk-sessions`），
  scratch 仍落在授权 root 内；dry-run 随即 `pass=true`。
- 这是 **harness 装配**修正（我们放置私有 Root 的位置），**非产品缺陷**：产品对越界 workspace 的拒绝是正确安全行为。
- 附带观测：设置 `save_dir` 后 SDK **真实生成 6 个 SQLite trajectory DB**（每会话一个，含 `trajectory_meta/steps` 等表），
  与旧 proof「未设 `save_dir` ⇒ 无 SDK DB」形成**明确 observability 差异**（见正式 REPORT）。

## 复现

```bash
uv run --frozen python probes/lg031/REAL-PROOF2/precheck2/probe_precheck2.py \
  --work probes/lg031/REAL-PROOF2/fixtures/precheck2 \
  --out probes/lg031/REAL-PROOF2/precheck2/precheck2-evidence.json
```
