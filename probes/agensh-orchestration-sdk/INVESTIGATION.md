---
title: "在真实 Antigravity SDK 内验证「无独立编排 + 程序认领/消息/文件 SoT」——技术调查报告"
doc_type: investigation-report
category: engineering
experiment_id: agensh-sdk-20261015
branch: experiment/agensh-sdk-20261015
worktree: /tmp/lightgravity-worktrees/agensh-sdk-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
created_at_utc: "2026-10-15"
status: investigation-only
model_calls_made: 0
driver_implemented: false
---

# 调查报告：用真实 Antigravity SDK 工具循环重跑编排对比

> **本回合只做只读调查/环境核查/隔离准备。** 没有发起任何模型请求，没有启动 `localharness`，
> 没有实现 driver，没有改产品代码/根依赖/PROJECT/旧实验，没有读 `.env` 或打印凭证。
> 本文件是下一轮“冻协议跑样本”前的接点清单与预算依据，不是实验结果。
> 参照物：`probes/agensh-orchestration-r2/REPORT.md` 与 `PROTOCOL.md`（主工作区未跟踪，未改动）。

---

## 0. 结论先行

**总判定：可行（存在明确的最小路径），但当前 18-run / 1,000,000 token 预算下有 1 个硬缺口和 1 个高概率超支项，必须先做有界校准探针再冻协议。**

1. **可以**通过产品 `AntigravityExecutor` + `LocalAuthProxy` 真实驱动 SDK 的 agent loop，并发生**真实文件读写工具调用**。
   已有正式真机证据（LG-006，已提交）证明：一次 `agent.chat` 展开为多次上游 HTTP，模型实际调用
   `view_file` / `write_to_file` / `replace_file_content`，执行后 workspace diff `passed`，且结构化
   `finish` 输出可用。无需任何 directHTTP 伪装。
2. **硬缺口：SDK 的 openai-compat 配置面没有 `max_tokens` / `thinking` 旋钮。** `LocalOpenAIAgentConfig`
   的 `model_fields` 无这两个字段；harness 侧 `GemmaEndpoint` 只有 `base_url`。因此“强制 `max_tokens=8192`
   + `thinking.type=disabled` 且两组一致”必须在**实验自建、位于产品代理与真实上游之间的轻量仪表/改写中继**
   完成（不改产品代理），并逐请求记录 before/after。**该中继前必须先真机探针确认 harness 默认请求体。**
3. **高概率超支：18 run × 2 轮 × 真实工具循环的 reported `total_tokens` 很可能 >1,000,000。**
   按 LG-006 真机（1 次文件写入 turn = 3 次 HTTP、prompt 15,303 / total 15,706 tokens）外推，
   18 run 约 400–500 次 HTTP，粗略 1.4M–2.3M reported tokens。建议冻协议前先跑 **6-run 校准探针**
   （每类每组 1 次），据此在 18→12（2 重复）或 18→9（1 重复）之间做有依据的缩减。
4. **最短稳定路径**：产品 `AntigravityExecutor` 原样驱动（复用其代理/取消/用量/diff）；
   实验侧只加三件“受控外挂”：① 在 registry 注册 `pre_tool_call_decide` 策略 hook 做工作区/文件边界；
   ② 用 `allow_loopback_upstream=True` 在前方加轻量计费中继；③ 在 registry 注册 `post_tool_call`
   观察 hook 做工具事件计量。claim/planner 走 `response_schema`（SDK `finish` 工具）保证计量公平。
5. **两组一致性与诚实边界**：B 的 planner 也走 SDK（同模型），其计划必须经与 claim 同一套程序校验；
   T3 单文件任务要显式防止“同文件跨 worker 语义拆分”。本轮是**实验 host + 产品 adapter**，
   不是 UI / 完整产品运行时验收。

---

## 1. 已核实的事实基线（本回合实测）

| 项 | 值 |
|---|---|
| base commit | `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef` |
| 新分支 | `experiment/agensh-sdk-20261015` |
| 新 worktree | `/tmp/lightgravity-worktrees/agensh-sdk-20261015`（原本不存在，已创建，未覆盖） |
| 主工作区并发改动 | `M PROJECT.md`、`?? probes/agensh-orchestration/`、`?? probes/agensh-orchestration-r2/` —— **原样保留**，本回合未触碰 |
| SDK | `google-antigravity==0.1.22`（pin 一致） |
| Python | `3.12.13`；使用主仓库 `.venv`，worktree 不重装 |
| localharness | sha256 `65a96a2a…5ecd3`（详见 `ENVIRONMENT.md`） |
| 旧 r2 证据 | 未提交、未改动；本文件只引用其 REPORT/PROTOCOL |

工作归属：新 worktree 下 `probes/agensh-orchestration-sdk/`，只含本报告与 `ENVIRONMENT.md`。
未 commit / push / merge / deploy / 删除文件或进程。

---

## 2. Q1 — 能否真实驱动 SDK agent loop + 工具调用，如何配置

### 2.1 结论

**能，且已有正式真机证据。** 产品链路为：
`AntigravityExecutor.execute()`（`backend/lightgravity/adapter/executor.py:402`）
→ `build_sdk_config()`（`executor.py:532` → `sdk_config.py:110-170`）
→ `Agent(config)` + `agent.chat(prompt)`（`executor.py:585, 798`）
→ SDK 二进制 `localharness` 通过 WebSocket 与本机事件流交互
→ 上游 HTTP 打到 `LocalAuthProxy`（`proxy.py:314`）→ DeepSeek。

已提交真机证据 `tests/adapter/evidence/lg006-real-evidence.json`
（sha256 `3c783558…b4b366`）显示：

- 场景 `file_write_diff_structured`：`state=succeeded`、`diff` 检查 `passed`、
  `structured_output` `passed`；一次 `agent.chat` 产生 **3 次上游 HTTP**
  （proxy `message_count` = 2 → 4 → 6，即 SDK 内 agent tool loop 把上一次的 assistant+tool 结果回灌）。
- 上游真实工具清单（proxy `tool_names`）：`finish, replace_file_content, view_file,
  write_to_file, list_skills, lookup_skill, lookup_skills`。即 `BuiltinTools.CREATE_FILE/EDIT_FILE`
  在 harness 内部映射为 `write_to_file`/`replace_file_content`，`view_file` 保持。
- `usage_metadata` 可用：`prompt/candidates/total/thoughts/cached`（`executor.py:202 _structured_usage`）。
- `upstream_model=deepseek-flash`（`proxy.py:403`）证明回显模型被真实抓到。
- 预算 `StopReason.MAX_MODEL_CALLS_EXCEEDED` 被 `classify_outcome` 识别为 `budget_exhausted`
  （`executor.py:57 _BUDGET_MARKERS`、`executor.py:160-190`）。
- 取消：`cancel` 走 `response.cancel()` → `conversation.is_idle` 确认，返回 `confirmed`
  （`executor.py:297 _request_cancel_inner`、`:942 cancel`）。
- 会话续跑：`request.conversation_id` + `save_dir` → `sdk_config.py:138-149`；LG-006 的
  `resume_seed`/`resume_recall` 证明同一 `Agent` 会话可跨 execute 恢复。

### 2.2 可复用接点（精确路径 / 行号）

| 能力 | 位置 | 说明 |
|---|---|---|
| 真实 SDK 执行 | `executor.py:344 AntigravityExecutor`、`:402 execute`、`:438 _execute` | 编译→代理→Agent→turn→diff→usage→stop |
| 工具事件流 | `executor.py:811 _drain`、`:917 _emit_chunk` | `ToolCall`/`ToolResult`/`Text`/`Thought` → normalized event |
| 结构化输出 | `executor.py:840 _structured_output`、`sdk_config.py:128 response_schema` | `response_schema` 注入 `finish` 工具；claim/planner 可复用 |
| 会话后续 turn / session | `sdk_config.py:138-149`、`executor.py:580-631` | `conversation_id` + `save_dir`；`SessionRef` |
| 预算 | `compiler.py:49 _BUDGET_KEYS`、`:747 _compile_budget`、`sdk_config.py:135` | `max_model_calls/tool_calls/total_tokens` → `BudgetConfig` |
| 停止确认 | `executor.py:330 ensure_closed`、`:427 _stop_proxy`、`proxy.py:443 stop` | 返回确认；不伪造停止 |
| 用量 | `executor.py:202`、`types.py:1110 UsageMetadata` | turn 级聚合 |
| 上游调用清单 | `proxy.py:408 call_records`、`proxy.py:80 ProxyCallRecord` | 每次上游 HTTP 的脱敏元数据 |
| 写工具安全策略默认值 | `connections/connection.py:82 policies default_factory=[]` + `LocalOpenAIAgentConfig` 注入 `confirm_run_command()` | 默认 allow `*`、deny `run_command` |
| delegation 关闭 | `sdk_config.py:118 enable_subagents=False`、`registry.py:179 invoke-subagent attaches=False`、`:186 run-workflow attaches=False` | SDK 内部子代理/工作流关闭 |

### 2.3 限制（必须随结论阅读）

- **openai-compat 路径无 `max_tokens` / `thinking` 旋钮**（详见 §4）。SDK 只把 `model_name` 与
  `base_url` 交给 `LocalOpenAIConnectionStrategy`（`local_openai_connection_config.py:82-120`），
  `GeminiModelOptions.thinking_level/max_output_tokens` 仅挂在 `GeminiAPIEndpoint.options`，openai 用不到。
- **产品代理只记录元数据，不记录 token/`finish_reason`/cache/reasoning**（`ProxyCallRecord` 字段见 `proxy.py:80-106`）。
- `sandbox` 检查只是 SDK 上报的 `SandboxStatus`，**不是**逃逸/隔离保证（LG-006 limitations）。
- harness 进程 **继承父进程 `os.environ`**（见 §4.4），凭证隔离需要显式处理。

---

## 3. Q2 — 不用 directHTTP 伪装；真实工具读写 + claim→lease→staging→整合

### 3.1 结论

最小路径**不使用** r2 的 `driver/llm_client.py` 直连 HTTP 路径。每个“逻辑 agent-turn”都调用
`AntigravityExecutor.execute()`，让 harness 真实执行文件工具；程序只做 `response_schema` 校验、
租约、base hash、越权拒绝与整合。

### 3.2 建议的最小流程（每 worker/轮）

1. **claim turn（走 SDK）**：`ExecuteRequest(objective=<claim 指令>, response_schema=ClaimSchema,
   allowed_tools=("view-file","finish"), workspace_path=<integrated ws>)`。
   模型用 `view_file` 查看现状后调用 `finish` 返回
   `{"claim": str|null, "message": str, "findings": [str]}`。程序解析 `result` 的结构化输出
   （`executor.py:840`），用与 r2 相同的 `grant_claim`（`run_experiment.py:727`）原子授予租约，
   写 `subtasks/r<n>-<worker>.md` frontmatter（`:812`）。
2. **edit turn（走 SDK，隔离 staging）**：把**当前整合 base**复制到
   `staging/r<n>/<worker>/`，`ExecuteRequest(workspace_path=<staging>, allowed_tools=("view-file",
   "create-file","edit-file","finish"), objective=<含租约文件、base hash、目标、接口约定>)`。
   SDK 真实读/写 staging 内文件。
3. **程序校验/整合**：用 `snapshot_tree`/`diff_snapshots`（`executor.py:96,124`）或等价快照比较
   staging vs base，得到 `produced/removed`。**只接受租约路径**；其余路径记 `overreach` 并拒绝整合
   （复用 r2 `validate_edits` 语义，`run_experiment.py:738-772`）。整合只把租约文件写回 integrated ws。
4. **验收**：复用 r2 `run_acceptance`（`:1077`）+ `clean_env()`（`:193`），`acceptance.py`/`reference/`
   永不进模型上下文。

### 3.3 复用 vs 缺口

**可复用**：租约/SoT schema、`writable_paths`（`:226`）、`grant_claim`（`:727`）、
`validate_edits`（`:738`）、`check_sot`（`:844`）、`copy_initial`/`write_files`（`:205/215`）、
fixture 与 acceptance（§6）。

**缺口（需实验侧补，不改产品）**：

- **每文件写权限的程序外强制**：SDK 侧只能限制到 `workspaces` 目录（`CapabilitiesConfig.enabled_tools`
  + harness workspace），**没有 per-file policy**。因此“限定可写已认领文件”只能是**事后 diff 校验 + 拒绝整合**。
  这是可接受的最小方案，但必须在协议里写明“模型可能先写了未认领文件，程序拒绝整合”。
- **工作区外读取边界**：产品 `build_sdk_config` **不设置 policies**（`sdk_config.py` 无 policies 分支），
  默认策略 allow `*`（仅 deny `run_command`）。若模型请求绝对路径 `view_file`，存在越界读取风险。
  → 建议在 registry 注册一个 `pre_tool_call_decide` hook 工厂（`hooks/hooks.py:405`），
  拒绝任何解析后不在 staging 工作区内的文件参数；该 hook 会被 `_hook_objects`
  （`sdk_config.py:79-86`）与 `compiler._compile_hooks` 自动挂上，并同时满足 `Agent.__aenter__`
  的“写工具需安全策略/decide hook”检查（`agent.py`）。
- **delegation 关闭**：已由 `enable_subagents=False` + `invoke-subagent`/`run-workflow`
  `attaches=False` 保证；实验侧不得注册这两者，不得设 `max_subagent_depth`/`allowed_subagents`。

### 3.4 必须真机验证的边界

1. harness 默认请求体（含 `max_tokens`、`thinking`、`stream_options`、tools schema）。
2. 一次 claim turn 的实际 HTTP 次数与 token（可能含 `view_file`）。
3. `view_file` 越界绝对路径在默认策略下是否真的被 harness 放行（决定 decide hook 是否必需）。
4. 结构化 `finish` 返回与 `response_schema` 的一致性（LG-006 已证，但 claim schema 需复验）。
5. 同一 Agent 会话内多轮 turn（claim→edit）与跨 execute 续跑（`conversation_id`+`save_dir`）的
   工具历史是否正确回灌。

---

## 4. Q3 — 完整计量、强制参数、隔离与资源回收

### 4.1 产品代理现有计量 vs 缺口

**有**（`proxy.py:80-106`）：`call`（序号）、`path`、`model`（请求体回显）、`stream`、
`message_count`、`has_tools`、`tool_names`、`has_response_format`、`forwarded`、`status`；
另有 `upstream_model`（从 SSE 抓 `"model"`，`proxy.py:403`）与 `call_count`（用于预算）。

**缺**：每次 HTTP 的 `prompt/completion/total_tokens`、`cached`、`reasoning`、`finish_reason`、
以及请求体的 `max_tokens`/`thinking`。SDK 的 `usage_metadata` 只给 **turn 聚合**，不给
**每 HTTP**，且 `stop_reason` 是 turn 级 `StopReason`（`types.py:1376`），不是 `finish_reason`。

### 4.2 推荐的轻量仪表中继（不改产品代理）

利用产品 `AntigravityExecutor(allow_loopback_upstream=True)` 已支持的路径：

```
SDK/harness ──HTTP──> LocalAuthProxy(注入 Bearer) ──HTTP──> [实验仪表中继 127.0.0.1:port] ──HTTPS──> api.deepseek.com
```

- 产品代理 `LocalAuthProxy` 支持 `allow_loopback_upstream=True`
  （`proxy.py:340`、`AUTHORIZED_UPSTREAM_HOSTS` 扩展）；把连接 `base_url` 指到中继即可。
  这**不修改产品代理源码**，只是运行参数；已有离线测试
  `tests/adapter/test_executor_canned.py:149-176` 用本地 upstream 跑通同一链路。
- 中继逐请求记录：完整请求体关键字段（`model`、`max_tokens`、`thinking`、`stream_options`、tool 数）、
  响应 SSE 的 `usage`、`finish_reason`、`reasoning_content`、以及是否重试。
- 中继是唯一注入 `max_tokens=8192`、`thinking={"type":"disabled"}` 的地方（若 harness 未自带），
  并记录改写前后值，**不静默**。两组使用同一中继与同一常量。
- 中继必须只绑定 loopback、只转发到固定 DeepSeek 主机、不落盘 Authorization。

> 备选（更弱）：只用产品代理的 `call_records` + SDK `usage_metadata`。这能满足“HTTP 次数/模型回显/聚合 token”，
> 但**无法**给出每 HTTP 的 `finish_reason`/cache/reasoning，也**无法**强制 `max_tokens`/`thinking`。
> 因此对 Q3 的完整计量，中继是必要的。

### 4.3 参数一致性

- `max_tokens=8192`、`thinking.type=disabled`：若 harness 默认已带，中继只做断言与记录；
  若缺失/不同，中继统一改写并记录。两组必须字节级同参。
- 模型不改：仍 `deepseek-v4-flash` / 上游 `api.deepseek.com`，不切供应商。
- `temperature/top_p` 由 harness 决定；需探针确认并对两组一致（若不支持，如实记录为不可控变量）。

### 4.4 凭证、文件、停止与回收

- **验收/测试子进程无凭证**：复用 r2 `clean_env()`（`run_experiment.py:193-202`）与
  `subprocess.run(..., env=clean_env(), cwd=workspace, timeout=30)`（`:1077-1091`）。
- **harness 子进程凭证**：SDK 在 `local_connection.py:1518` 计算
  `merged_env = {**os.environ, **env_map} if self._env is not None else None`，并在 `:1525`
  `Popen(env=merged_env)`。注意传 `env={}` **不能**清空（仍 `{**os.environ}`），传 `env=None`
  时直接继承父环境。→ 要保证 harness 无凭证，**必须在 spawn 前把 key 从 `os.environ` 移除**，
  并用 `InMemoryCredentialResolver({"deepseek-api-key": key})`（`credentials.py:139`）把值留在内存。
  产品代理只需要内存里的 `Secret`，不需要环境变量。
- **SDK 工具不可读控制/秘密文件**：工作区仅指到 staging；再加 §3.3 的 `pre_tool_call_decide`
  hook 做路径白名单。控制文件（TASK/RUN/SUBTASK/events）只由 driver 写，且**不放进 staging**。
- **停止与回收**：`executor._execute` 的 `finally` 调 `handle.ensure_closed()`
  （`executor.py:330`）与 `_stop_proxy`（`:427`）；`proxy.stop()` 只有 socket/线程真正消失才返回
  `True`（`proxy.py:443-466`）。harness 进程在 `LocalConnection.disconnect`/`__aexit__` 内
  close stdin → wait → terminate → kill（`local_connection.py:600-626`）。可复用 LG-006 的
  `/proc` 扫描 `_find_localharness_pids()`（`tests/adapter/evidence/lg006_real_run.py:44`）
  在运行前后做泄漏核对。

### 4.5 尚待真实探针

- harness 默认请求体（`max_tokens`/`thinking`/`stream_options`）。
- 每 HTTP 的 `finish_reason` 与 usage 是否可由中继稳定解析（含 SSE `include_usage`）。
- 默认 `retry_config`（产品不设）与重试是否发生；若要固定，可在拿到 config 后
  `config.retry_config = RetryConfig(api_retry=ModelAPIRetryConfig(max_retries=0))`（已离线验证可赋值），
  但产品 `build_sdk_config` 不暴露该字段——不经产品 executor 直接构造 Agent，或用实验侧
  注入，二选一需在下一包定稿。
- `view_file` 越界路径在该 SDK 版本下的实际行为。

---

## 5. Q4 — 18-run / 153-turn / ≤500 HTTP / ≤1,000,000 token / 30min 可完成性

### 5.1 逻辑 turn 与 HTTP 展开

原协议：`2 worker × 2 轮 × 2 次(claim+edit) = 8/run`，18 run = 144，B 另加 9 次 planner = **153 逻辑
agent-turn**（与旧预算精确相等，没有余量）。claim/planner 也走 SDK 后**逻辑数不变**，但每次
`agent.chat` 因工具循环展开为多次上游 HTTP。

真机观测（LG-006，小 workspace）：

| 场景 | 逻辑 turn | 上游 HTTP |
|---|---|---|
| 文件写入（含 view/write/finish） | 1 | 3 |
| 预算耗尽（无文件写） | 1 | 1 |
| cancel / resume seed / resume recall | 各 1 | 各 1 |

保守估计（每 edit turn 3–4 HTTP、每 claim turn 1–3 HTTP、planner 1–3 HTTP）：

```
HTTP ≈ 72 claim × 2 + 72 edit × 3.5 + 9 planner × 2 = 144 + 252 + 18 = 414
```

落在 500 以内，但**没有安全余量**；若模型多调一次 `view_file` 就会逼近上限。

### 5.2 token 估算（关键超支项）

LG-006 文件写入场景单 turn `total_tokens=15,706`（`prompt 15,303`），3 次 HTTP。
按“每次 HTTP 平均 3,000–5,000 reported tokens、约 400–450 次 HTTP”外推：

```
405 × 3,000 ≈ 1.22M        （乐观）
414 × 5,000 ≈ 2.07M        （接近真机均值）
```

**结论：1,000,000 reported tokens 的上限在 18-run × 2 轮下大概率不可满足**，与旧 r2 的
179,851（仅 JSON 文本）不可比。旧 r2 不能作为 SDK 工具循环的 token 依据。

### 5.3 墙钟

LG-006 每个 execute 含一次 harness spawn：3-call 场景 4.48s，1-call 场景 1.1–2.1s。
按 153 次 execute、每次 spawn ~1s + 调用 ~1–3s：

```
153 × ~4s ≈ 610s ≈ 10min（乐观，小 fixture）
```

30min 上限在乐观情形可行；但真实 fixture 更大、文件写更长时可能逼近。**必须探针实测。**

### 5.4 建议（不擅自运行）

冻协议前先做 **6-run 校准探针**（3 类 × B/C × 1 次），硬界
`max_proxy_calls`、`max_total_tokens` 各留安全系数，测出：每次 claim/edit/planner 的
HTTP 数、reported tokens、墙钟。据此二选一：

- 若 18 run 外推 ≤ 1,000,000 且有 <10% 余量 → 维持 18 run。
- 否则 **缩到 12 run（每组每类 2 重复）或 9 run（1 重复）**，并如实声明样本更小、统计功效更低。
  12-run 的 153→约 102 逻辑 turn、HTTP 约 280、token 约 0.8–1.4M；9-run 更低。
  **缩减依据必须写进冻结协议，不能事后改。**

### 5.5 两组一致的可观察规则

- B 的 planner 必须走 SDK 且计入同模型成本；planner 输出先用与 claim 相同的程序规则校验
  （JSON/字段/文件存在/不得把同一文件分给两名 worker）；无效计划记事件并置空，
  **不得**让 worker 在无计划与有坏计划之间被静默区别对待。
- T3 单文件任务：显式规则“每轮每文件仅一名 writer”，planner 若提出同文件拆分，程序拒绝该拆分
  并把拒绝原因作为可观察事件，避免复现旧 B 的弱基线交互。
- 越权/无效编辑/base hash 不符在两组使用同一代码路径与同一判定。

---

## 6. Q5 — r2 可复用 / 必须替换 / 诚实边界

### 6.1 可复用（只拷所需并记录 hash）

fixture 与验收（源哈希，`probes/agensh-orchestration-r2/evidence/offline/source_fixtures.sha256`）：

| 文件 | sha256 |
|---|---|
| `t1_independent/acceptance.py` | `1d470550…b523bfd` |
| `t1_independent/initial/src/slugs.py` | `28588d8f…97b34` |
| `t1_independent/initial/src/ranges.py` | `40d0747f…56a97d` |
| `t2_interface/acceptance.py` | `7968e563…881fc9` |
| `t2_interface/initial/src/geometry.py` | `93a838a5…841023` |
| `t2_interface/initial/src/report.py` | `cb62c807…8bd956` |
| `t3_evolving/acceptance.py` | `f1e70e8c…8a1e33` |
| `t3_evolving/initial/src/stats.py` | `1fe36ee8…e039e0` |
| 所有 `__init__.py` | `e3b0c442…b785b2`（空文件） |
| reference/ 与 reference_round1/ | 见 `source_fixtures.sha256` |

机制代码：租约/SoT schema（TASK/RUN/SUBTASK/events）、`clean_env`、
`writable_paths`、`grant_claim`、`validate_edits`、`check_sot`、`run_acceptance`、
fixture 哈希校验 `validate_fixtures.py`。均位于
`probes/agensh-orchestration-r2/driver/run_experiment.py`（行号见 §3.3）。

### 6.2 必须替换为真实 SDK 行为

| r2 机制 | 处置 |
|---|---|
| `driver/llm_client.py`（标准库 direct HTTP、模型只回 JSON 内容） | **禁用**。改用 `AntigravityExecutor`。 |
| 模型返回文件内容、程序写文件 | 改为 SDK 真实 `write_to_file`/`replace_file_content` 在 staging 执行 |
| 程序直接写 integrated workspace | 改为程序只整合**租约路径**的 staging diff |
| r2 `raw/*.json`（含 usage/finish_reason） | 计量源改为产品代理 `call_records` + 实验中继逐 HTTP 记录（§4.2） |
| claim/edit/planner 提示 | 保留 JSON schema 语义，但以 `response_schema`（SDK `finish` 工具）+ SDK 系统指令承载 |
| 每 run 独立 HTTP 预算模型 | 改为“逻辑 turn + HTTP 展开”双层预算（§5） |

### 6.3 诚实边界

本轮是**实验 host（driver/租约/整合/验收）+ 产品 adapter（AntigravityExecutor/LocalAuthProxy/compiler）
+ 官方 SDK/harness**。它**不是**：

- UI 验证；
- 完整产品运行时验收（无产品 coordinator、MCP、Triggers、真实工程规模）；
- 对 Gemini/Vertex 后端的验证（仅 openai-compat/DeepSeek）；
- 沙箱逃逸/隔离保证（只有 SDK 上报状态 + 实验侧路径白名单）。

因此结论只能用于“产品 SDK 候选”，不能作为删除产品编排/规划角色的自动依据。

---

## 7. 证据等级（哪些仅源码存在 / 已离线核查 / 待真机探针）

| 条目 | 等级 |
|---|---|
| 产品 executor/proxy/compiler/registry 接口与行号 | **仅源码存在**（本回合只读核对，未运行真实执行） |
| LG-006 工具循环/用量/diff/取消/续跑 | **已有真机证据**（已提交 JSON，本回合只读重算） |
| SDK 无 `max_tokens`/`thinking` 旋钮、`GemmaEndpoint` 仅 `base_url` | **已离线核查**（`inspect`/`model_fields`/proto descriptor） |
| `enable_subagents=False`、delegation 关闭 | **已离线核查**（源码 + config 构造） |
| `allow_loopback_upstream` 中继链路 | **已离线核查**（canned 测试路径存在）；**待真机探针** |
| harness 请求体默认值、每 HTTP usage/finish_reason 解析 | **待真机探针** |
| harness 继承 `os.environ`、需 spawn 前移除凭证 | **已离线核查**（源码行号）；**待真机探针**验证无泄漏 |
| `view_file` 越界行为、decide hook 必要性 | **待真机探针** |
| 18-run token/时间外推 | **估算**（基于 LG-006 真机 + 假设），**待 6-run 校准探针** |
| 缩减建议（12/9 run） | **建议**，需校准数据支撑后写进冻结协议 |

---

## 8. 风险与未决

1. **计量缺口是硬风险**：不建中继就无法满足 Q3 的“每 HTTP usage/finish_reason/参数一致性”，
   也无法强制 `max_tokens=8192` + `thinking.disabled`。
2. **token 预算**：1,000,000 上限在 18-run 下大概率不可满足；必须校准后缩减或放宽（需用户决定）。
3. **写边界**：per-file 写权限只能事后校验；越界读需 decide hook，且该 hook 的真实拦截效果待验。
4. **默认重试**：产品不设 retry，探针前无法确定重试是否发生；若发生需计入预算并考虑固定。
5. **资源残留**：harness 应用数据目录默认 `~/.gemini/antigravity`、`save_dir` 未指定时会 mkdtemp
   （`local_connection_config.py:214-220`）；实验应显式指定 `save_dir`/`app_data_dir` 到隔离临时目录，
   并在运行前后做 PID 扫描。
6. **公平性**：claim/planner/edit 都走 SDK 后，工具 schema 与系统指令成为固定成本；两组必须
   使用同一 agent 模板、同一工具集、同一中继参数。

---

## 9. 下一包可执行工作建议（不擅自运行）

**包 A（离线，0 模型调用）— 先做，成本低**
1. 在 `probes/agensh-orchestration-sdk/` 写 `driver/` 骨架：复用 r2 租约/SoT/验收函数；
   定义 `ClaimSchema`/`PlanSchema`；定义 `pre_tool_call_decide` 路径白名单 hook 与
   `post_tool_call` 计量 hook（注册进 `ImplementationRegistry`）。
2. 写 `driver/relay.py`（轻量仪表中继，loopback，固定上游，记录字段，支持一致性断言/改写）。
3. 写离线 selftest：用 canned upstream（参照 `test_executor_canned.py`）验证
   executor→proxy→relay→canned 的计量字段与 claim 结构化输出，0 联网。
4. 写 `PROTOCOL.md` 草案（含缩减决策点与校准规则）与冻结 manifest。

**包 B（真实校准探针，需显式授权）— 6 run 上限**
- 3 类 × B/C × 1 次，硬界 HTTP/ token/墙钟；测出每 turn 的 HTTP 数、reported tokens、
  `finish_reason`、请求体参数、工具调用率、PID 残留。
- 输出校准报告，据此决定 18 / 12 / 9 run，并冻结正式协议。

**包 C（正式运行，需再次授权）**
- 按冻结协议跑，写 `runs/`、`raw/`、`events.jsonl`、分析报告，并明确标注
  “实验 host + 产品 adapter，不是 UI/完整运行时验收”。

**建议并行产出**：把 `SOURCE-ONLY` / `OFFLINE-VERIFIED` / `PROBE-REQUIRED` 标签保留到
每个结论，避免下一轮把估计当实测。
