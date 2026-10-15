# 首次真实 Antigravity SDK 实验 — 测量审计（只读，0 模型请求）

- 调查者：pi 只读技术调查执行者
- 时间：2026-10-15T06:50Z（`date -u`；本地 17:50 AEDT）
- 对象（只读，未改）：`/tmp/lightgravity-worktrees/agensh-sdk-20261015/probes/agensh-orchestration-sdk/`
- 本次审计未发起任何模型/SDK 探针，未读 `.env`，未改实验目录，未提交/push。仅离线解析/回放/构造 SDK 事件对象。
- 关键代码指向产品 adapter（只读）：`/tmp/lightgravity-worktrees/agensh-sdk-20261015/backend/lightgravity/adapter/executor.py`。

---

## 0. 结论先行

### 可用（可支撑的结论）
- **真实 SDK 工具循环确实发生**：51 个逻辑 turn 中 46 个 `finish` 正常解析；原始 SDK 会话 DB 含真实 `view_file` / `write_to_file` / `replace_file_content` / `finish` 调用（非 directHTTP 伪装）。
- **文件写入/差异/验收真实**：`workspace` 仅含预期 `src/*.py`；diff 产物非空；用 `fixtures/<task>/acceptance.py` 对 workspace 副本独立复算，**B、C 两组 6 个 run 全过（6/6、6/6、9/9）**。
- **逐 HTTP 计量存在**：relay 记录 `request_before/after`、`usage`、`finish_reasons`、`rewrites`。合计 **158 HTTP / 837,630 reported tokens**，事件时间跨度 `06:41:07Z–06:47:52Z`（约 6.7 min，均在协议硬界内）。
- **写工具防护有实证**：4 次越界写被 guard 拒绝（`/tmp/verify_report_check.py` 等），落地文件均不存在；未授权的工作区内临时文件被 post-hoc 拒绝整合。
- **冻结哈希完整**：`evidence/FREEZE_MANIFEST.txt` 内 32/32 个 sha256 与当前文件匹配（integrity 完好）。

### 失效（不能用于结论）
- **B 组计划全部无效 → B 组实际上等价于 C 组，B/C 对比无效（阻断级）**。
  - `runs/formal/*B*/results.json` 三项 `plan_valid=false`；`plan=None` 使 `experiment.py:363 _plan_block` 对 B 返回与 C 完全相同的“本轮没有提供任何计划或任务分解”文本 → **B 的 worker 从未收到任何计划**，`shared_findings` 也未注入 planner findings。因此不能据此给出“可取消强制独立编排”的判定。
  - 根因有两个（见 §1）：planner `finish` 大输出被驱动侧截断（t1/t3），以及 planner 计划键名不符合 `PlanSchema`（t2 及 t1/t3 的 `files`）。
- **PROGRESS.md 的时间是伪造/占位**：写 `18:00Z–19:35Z`，而 worktree 创建于 `06:25:08Z`、正式 run 事件在 `06:41:07Z–06:47:52Z`。未来时间不能作证据。
- **`view_file` 路径 guard 盲区**：所有 `view_file` hook 决定 `paths=[] allow=true`，原因是真实 wire 键为 `AbsolutePath`，不在识别键内（见 §2）。读越权“未观测到”，但**读防护未被证实**。
- **参数统一未证实**：relay 只强制 `max_tokens=8192`，但 harness 同时发送 `max_completion_tokens=65535` 未被改写；若上游优先使用后者，声明的 8192 输出上限并未真正生效（本批未发生截断，`finish_reasons=['tool_calls']`）。

### 需要先修再重跑（不重跑本次、不删进程）
最小修复：① 持久化/读取完整 `finish`（勿用被 2000 截断的事件）；② 用受限 pydantic 子模型强制 planner 键名；③ `_PATH_ARG_KEYS` 增加 `AbsolutePath`；④ 精确记录 freeze epoch、修正 PROGRESS、明确校准 6-turn 性质。

---

## 1. Q1 — `finish` 结构化提取与 planner 校验

### 1.1 数据丢失链（驱动侧，非模型侧）
1. 产品 executor 对工具调用参数做 `_bounded`，所有字符串 `value[:2000]`：`executor.py:1042,1050`。
2. 驱动只从 `adapter.tool_call` 事件取 `args`：`driver/host.py:317 _turn_record` → `driver/host.py:357 extract_finish_output` 读 `args["output_string"]`（`host.py:364`）；`json.loads` 失败即返回 `None`（`host.py:347` 把 parse 失败与“无 finish”一律标成 `"no_finish_output"`，措辞误导）。
3. 产品提供的 `structured` 对象本身也被截断到 500）：`executor.py:890 detail=repr(structured)[:500]`（驱动记为 `structured_repr`，`host.py:329-348`）。因此全量 plan 在既有产物中被丢两次。
4. **完整 plan 仍存在于 SDK 原生 session DB**：`runs/formal/<run>/sessions/planner/*.db` 表 `steps`（BLOB `step_payload`），可离线还原。relay 也证明模型确实输出完整内容（t1 planner 末次 `completion_tokens=1625`、`finish_reasons=['tool_calls']`、`response_bytes=523476`）。

### 1.2 逐项结果（离线回放；全量来自 session DB）

| run | 事件中 `output_string` | session DB 全量 | 当前提取 | `validate_plan` 结果（复算） |
|---|---|---|---|---|
| `t1_independent__B__r0` | 2000（截断；`json.loads` 报 `Unterminated string ... char 942`） | 6110 chars，step idx7 | `finish_payload=null`，`no_finish_output` | `plan_not_a_list` → `None` |
| `t2_interface__B__r0` | 1196（完整） | 1196 chars，step idx9 | 解析成功为 dict | items 用 `assignee/task/interface`，缺 `worker` → `plan_bad_worker:None`×2 → `None` |
| `t3_evolving__B__r0` | 2000（截断；`Unterminated string ... char 1900`） | 7690 chars，step idx9 | `finish_payload=null`，`no_finish_output` | `plan_not_a_list` → `None` |

**即便修复截断，plan 仍不可用**（复算结果）：
- t1 计划项键为 `assigned_files`（非 `files`）、`tasks`（非 `objective`），另有 1 条 `worker=None` 的协调项；修复后 `validate_plan` 会返回非空但 `objective=""`、`files=[]`。
- t3 计划项键为 `owns_files`（非 `files`）、`interface_contract`（非 `objective`）；修复后同样 `objective/files` 为空。
- t2 计划项 `assignee`（非 `worker`），仍被拒。
- 只有 `PlanSchema.plan = list[dict[str, Any]]`（`driver/host.py`）对 item 键零约束，模型才自由用别名；SDK 端 JSON schema 未强制 `worker/objective/files`。

### 1.3 claim/edit 解析受影响程度
- 51 个 turn：`finish_parse_error!=null` 仅 5 个。
- 被“截断”影响的 **只有 2 个 planner**（上表 t1/t3）；**worker 的 finish 无一被截断**（48 个 worker finish 中 46 个 `<2000` 且解析成功）。
- 其余 3 个无 finish 是 turn 失败/预算，不是提取问题：
  - `t1_independent__B__r0/turns/r1-edit-w2.json`：`state=failed`，`AntigravityExecutionError ... 429 local auth proxy call budget exhausted`。
  - `t1_independent__C__r0/turns/r1-edit-w1.json`、`t2_interface__C__r0/turns/r2-claim-w1.json`：`state=budget_exhausted`。
- 结论：**claim/edit 提取基本可靠；失效集中在 planner，并直接导致 B 组拿不到有效 plan。**

---

## 2. Q2 — hook 真实 `view_file` 参数、`paths=[]`、guard 漏检与越权

### 2.1 真实 wire 形状
- SDK 会话 DB 中 `view_file` 的参数键是 **`AbsolutePath`**（例：`.../t1_independent__B__r0/sessions/planner/*.db` 的 `steps`，值如 `/…/workspace/src/slugs.py`）。
- 写工具参数键是 **`TargetFile`**（`write_to_file` / `replace_file_content`）。
- SDK 侧只有 `WIRE_PATH_ARGUMENT_KEYS` 会被归一化并生成 `canonical_path`：`.../google/antigravity/connections/local/local_connection_config.py:66`，含 `path,file_path,directory_path,TargetFile,output_path,script_path,ScriptPath` —— **不含 `AbsolutePath`**。`hook_router.py:66,209` 因此对 `view_file` 得到 `canonical_path=None`。
- 驱动 `hooks.py:49 _PATH_ARG_KEYS` 也没有 `AbsolutePath`（只有小写 `file_path/absolute_path`），于是 `extract_paths` 返回 `[]`（`hooks.py:64-81`），`check_paths` 判 allow（`hooks.py:84`）。这解释了所有 `view_file` 的 `paths=[] allow=true`。

### 2.2 离线复现 guard 漏检（构造真实 SDK 事件，0 模型）
用 venv python 构造 `types.ToolCall` 并按 SDK hook_router 的规则派生 `canonical_path`：

```
view_file  {"AbsolutePath":"/etc/passwd"}      canonical=None  paths=[] allow=True  reason=allowed   <-- 漏检
create_file{"TargetFile":"/etc/shadow"}        canonical=/etc/shadow paths=[...] allow=False        <-- 正常拦截
create_file{"file_path":"/tmp/evil.py"}        allow=False
```

即：**读路径完全绕过 guard；写路径受 guard 约束。**

### 2.3 本次真实越界副作用（区分“未观测到”与“已证实”）
- 写越界（已被拦截，实证）：4 次 `allow=false`，均因 `escapes the staging workspace`：
  `t2_interface__B__r0/turns/r1-edit-w2`（`/tmp/verify_report_check.py`）、
  `t1_independent__C__r0/turns/r1-edit-w1`（`…/verify_slugs_check.py`）、
  `t1_independent__C__r0/turns/r2-edit-w1`（`/tmp/verify_spec_t1c.py`）、
  `t3_evolving__C__r0/turns/r1-edit-w1`（`/tmp/verify_stats_w1.py`）。
  复核上述文件**均不存在**。
- 工作区内未授权文件（6 处，如 `_verify_ranges.py`、`_check_slugs.py`、`verify_geometry.py`）：被 `validate_edits` 记 `overreach` 并**拒绝整合**；最终 workspace 仅剩 `src/*.py`。
- 读越界：观测到的所有 `view_file` 目标都在各自 run 目录内（脚本扫描 6 个 run 的全部 session DB），**未观测到读越权**；但因 §2.1 的盲区，**不能声称读防护已证实**。
- 结论：**写防护=已证实有效；读防护=未观测到越权，但 guard 客观漏检。**

### 2.4 最小修复与离线回放测试建议
- 修复：`hooks.py:_PATH_ARG_KEYS` 增加 `AbsolutePath`（并同时纳入 `TargetFile`、`absolute_path` 等真实/别名键）；`extract_paths` 继续以 `canonical_path` 为辅，但不得只依赖它。
- 测试：在 `driver/selftest_offline.py` 增加离线用例：构造 `view_file {AbsolutePath: <root外>/etc/passwd}` 断言 `extract_paths` 非空且 `check_paths` 返回 `allow=False`；再构造 `write_to_file {TargetFile: <root外>}` 断言拒绝。
- 边界声明：guard 的真实拦截效果仍需一次**有界真实探针**确认 harness 会执行 `pre_tool_call_decide` 的 deny（本次未执行）。

---

## 3. Q3 — 协议时间/预算/源文件 freeze/停止/验收的证据范围

### 3.1 时间（可核实 vs 必须 unknown）
- 真实时钟：`2026-10-15T06:50Z`。
- 可核实：worktree 创建 `06:25:08Z`（`stat %W`）；正式 run 事件 ts `06:41:07Z–06:47:52Z`（`events.jsonl` 334 条带 `ts`；relay `started_at` 同）；`PROTOCOL.md` mtime `06:40:48Z`。
- **伪造**：`PROGRESS.md` 写 `18:00Z–19:35Z`，为未来时间，且早于 worktree 创建时刻，**不得作为证据**。
- **必须标 unknown**：`PROTOCOL.md` 只有 `frozen_at_utc: "2026-10-15"`（日期，无精确时刻）；`FREEZE_MANIFEST.txt` 无时间戳。mtime 仅能“近似” `06:40:48Z`，不是权威冻结时刻，**不可据此宣称精确 freeze**。`INVESTIGATION.md` 的 `created_at_utc` 同样只有日期。

### 3.2 源文件 freeze 完整性
- `FREEZE_MANIFEST.txt` 的 32 个 sha256 与当前文件**全部匹配**，`base_commit 9987d4f…` 存在（`git cat-file -t` = commit）。→ 证明“文件集合未被事后改动”，但不能证明“冻结发生在正式运行之前多久/精确时刻”。worktree 内该目录 git 状态为 `?? probes/agensh-orchestration-sdk/`（未提交，符合预期）。

### 3.3 SDK turn 是否真实停止
- 现在 `ps -C localharness` **无进程**（未删任何进程，仅观测），无遗留 harness。
- 但 turn 记录里 `stop_confirmed` **全为 `None`**：产品只在 cancel/timeout 路径设置它（`executor.py:658-664`）；正常完成路径不设置。驱动也未持久化 `auth_proxy_stopped` check 记录。
- 结论：**“真实停止”只有当前无残留 + 每 turn 在 `execute` 的 `finally` 调 `ensure_closed/_stop_proxy` 这样的弱证据；既有产物未提供逐 turn 正向停止确认。** 应标为“停止未逐 turn 证实”。

### 3.4 工具事件/diff/验收是否真实
- 真实：session DB 内含真实工具调用与参数；`sdkdata/artifacts/*/lg006-diff.patch` 非空（t1B 1762/1131B，t2B 3953/2492B，t3B 2390B）；workspace 文件非 stub。
- 验收真实（独立复算，非仅采信报告）：t1 `6/6`、t2 `6/6`、t3 `9/9`，B/C 均同。
- 但存在 infra 噪声：`runs/formal_run.log` 记录 `invalid tool call (invalid_json)`、`argument Overwrite not found`、`HTTP 429 local auth proxy call budget exhausted`；`t1_independent__B__r0/r1-edit-w2` 因此 `state=failed`。验收仍通过，但这些失败应纳入分母并显式标注。

### 3.5 预算与校准偏差
- 正式：51 逻辑 turn、158 HTTP、837,630 reported tokens、墙钟约 404s（≤协议 350/1.5M/1800s）。
- 校准：`CALIBRATION.md`/`CALIBRATION_SUMMARY.json` 明确 6+1=7 逻辑 turn；`PROTOCOL.md` §“校准”把 ≤6 写成硬界，报告却称其为 “soft cap”。这是**事后软化措辞**，应保留“违反 ≤6 字面约束”的原始披露。

---

## 4. Q4 — 纠正对比所需的最小额外真实样本与预算（不执行，仅建议）

### 4.1 前置（0 模型，必须）
- 在新 attempt 目录冻结修复版本 + 新协议（精确 `frozen_at_utc` epoch、PROGRESS 用真实时间）。
- 离线回放验证：用本次 session DB 的完整 planner JSON 跑新 `validate_plan`，确认修复后 t1/t3 能产出**非空 objective/files**；不行就先改提示/schema。
- 冻结前先确认 planner 计划真的进入 worker objective：可先用 1 个 B 校准 run（planner+2 worker）核验 objective 文本含计划块。

### 4.2 样本与预算估计（基于本次实测外推）
- 提议：3 类 × 2 组 × 1 重复 = **6 个新 run**（约 51 逻辑 turn），外加上述 1 个 B 前置校准 run。
- 本次 6-run 实测：158 HTTP / 837,630 tokens / ~6.7 min（事件 ts 跨度）。
- 修复后计划会进入每个 B worker 上下文（interface_notes 可达 1–2KB/turn），token 略增；前置校准再增约 30–50 HTTP、约 0.15–0.25M tokens、1–2 min。
- 判断：
  - **HTTP ≤220：很可能满足**（158→约 190–210）。
  - **墙钟 ≤15 min：很可能满足**（约 7–9 min）。
  - **reported tokens ≤1M：不能保证**。基线 837k 只剩约 16% 余量；加计划注入、校准与方差后可能逼近或越过 1M。
- 结论：**HTTP/时间有信心；token 上限不确定**。若坚持 1M，建议先把 6-run 预算按 1.0M 设硬界并接受可能失败；否则把 token 预算上调到约 1.3M。**在执行前无法用现有证据确认 ≤1M。**

---

## 5. 最小修复 / 验收清单（建议，未实施）

1. `driver/host.py`：`extract_finish_output` 改为读取**完整**结构化结果（session DB 或产品结构化对象），不要以 `_bounded` 事件为唯一来源；`finish_parse_error` 区分 `no_finish_call` / `invalid_json` / `truncated`。
2. `driver/host.py`：给 `PlanSchema.plan` 用受限子模型（`worker: Literal["w1","w2"]`、`objective: str`、`files: list[str]`），并让 `_planner_objective`/系统提示重复这些精确键。
3. `driver/hooks.py:49`：`_PATH_ARG_KEYS` 增加 `AbsolutePath`（及 `TargetFile` 等），并在 `selftest_offline.py` 增加 §2.4 的离线回放断言。
4. 协议：记录精确 `frozen_at_utc` epoch；PROGRESS 只用真实 `ts`；校准 6/7 turn 表述保持一致并如实披露。
5. 计量：处理 relay 未改写的 `max_completion_tokens=65535`，使“输出上限”声明与实际生效参数一致。
6. 验收：把 turn 级 `auth_proxy_stopped`/`stop_confirmed` 与失败 turn 显式落盘纳入分母；独立复算 acceptance（本审计已复算通过）。

---

## 6. 证据索引（原路径 + 原始样例）

- planner 截断与校验：
  - `runs/formal/t1_independent__B__r0/turns/planner.json`（`finish_parse_error=no_finish_output`，`finish_payload=null`，`tool_call_names=[...,"finish"]`）
  - `runs/formal/t3_evolving__B__r0/turns/planner.json`（同上）
  - `runs/formal/t2_interface__B__r0/turns/planner.json`（`finish_parse_error=null`，plan items 用 `assignee`）
  - 全量 plan：`runs/formal/<run>/sessions/planner/*.db` → `steps`（t1 idx7=6110B、t2 idx9=1196B、t3 idx9=7690B）
  - `runs/formal/summary.json`（三项 `plan_valid=false`，`relay_total_calls=158`，`relay_total_tokens=837630`）
  - `runs/formal/*B*/events.jsonl`（`planner_invalid` 事件）
- 代码根因：
  - `backend/lightgravity/adapter/executor.py:1042,1050`（`_bounded` / `value[:2000]`）
  - `backend/lightgravity/adapter/executor.py:890`（`repr(structured)[:500]`）
  - `driver/host.py:317,347,357,364`
  - `driver/experiment.py:363,489,873`
  - `driver/hooks.py:49,64,84`
  - `.venv/.../google/antigravity/connections/local/local_connection_config.py:66`（`WIRE_PATH_ARGUMENT_KEYS`）
  - `.venv/.../google/antigravity/connections/local/hook_router.py:66,209`
- hook / 越权：
  - `t1_independent__B__r0/turns/r1-edit-w2.json`（view_file `paths=[] allow=true`；create_file 越界 `allow=false`）
  - `t2_interface__B__r0/turns/r1-edit-w2.json`、`t1_independent__C__r0/turns/r1-edit-w1.json`、`t1_independent__C__r0/turns/r2-edit-w1.json`、`t3_evolving__C__r0/turns/r1-edit-w1.json`（4 次拒绝）
  - `runs/formal/*/results.json` 的 `overreach` 列表
- 时间/预算/freeze：
  - `PROTOCOL.md`（`frozen_at_utc: "2026-10-15"`）、`CALIBRATION.md`、`CALIBRATION_SUMMARY.json`、`evidence/FREEZE_MANIFEST.txt`、`PROGRESS.md`（伪造 18:00–19:35Z）
  - `runs/formal/t2_interface__B__r0/events.jsonl` 首行 `ts=2026-10-15T06:41:07Z`；末事件 `06:47:52Z`
  - `runs/formal_run.log`（429 / invalid tool call 告警）
- 停止/验收：
  - `ps -C localharness` 无输出；`executor.py:658-664`（正常路径 `stop_confirmed=None`）
  - 独立复算：对 workspace 副本执行 `fixtures/<task>/acceptance.py`，结果 `6/6,6/6,9/9`（B/C 同）

**最终给主代理的一句话**：首次数据的“SDK 真实工具循环/文件写入/验收/写防护”可用；但 **B 组 plan 全失效使 B≡C，B/C 对比无效**，读 guard 存在已被离线证实的漏检，PROGRESS 时间为伪造、freeze 精确时刻应标 unknown。报告位于 `/tmp/lightgravity-sdk-measurement-audit-20261015/AUDIT.md`；须先按 §5 修复并在新 attempt 冻结后重跑，0 本次重跑。

---

## 附：与产出方后续产物的事后交叉印证（只读，2026-10-15T06:55Z 后新增）

本审计进行期间，实验执行者又产出了 `driver/recover_planner.py`、`evidence/planner_recovery.json`、`runs/formal/analysis.json`、`REPORT.md`，并更新 `PROGRESS.md`。独立核对结论一致：

- `evidence/planner_recovery.json`：3/3 B planner 从 SDK session DB 恢复成功，但 `program_valid=false`，issues 与本审计 §1.2 完全一致（`plan_files_missing_or_not_list`、`plan_bad_worker:None`）。
- `driver/recover_planner.py` 文件头明确写出根因：产品 `executor._bounded` 把工具参数截断到 2000 字符；恢复仅作诊断，**不改变 worker 当时所见**。
- `runs/formal/analysis.json`：B 6 / C 7 次（工作区内）overreach、0 length 截断、B 1 failed + 1 budget turn、C 3 budget turn；`improvement.tokens_pct=-3.59`、`elapsed_pct=4.32`（均未达 15% 门）。
- `REPORT.md`：`candidate gate NOT met; B arm invalid`，明确“B ≡ C + 1 次被丢弃的 planner 调用，本轮 B/C 对比不成立，不建议据此删除规划”。
- `PROGRESS.md` 已把原先伪造的 `18:00–19:35Z` 改为真实 `06:28–06:55Z`（与本审计 §3.1 一致），`status: complete`。

即：本审计的核心阻断结论（B 组计划失效、B≡C、planner 提取截断、schema 键名不符）已被产出方自身证据独立确认；本审计额外补充了 read guard 的 `AbsolutePath` 漏检离线复现、精确时间线、以及 `max_completion_tokens=65535` 未改写这一计量保真问题。
