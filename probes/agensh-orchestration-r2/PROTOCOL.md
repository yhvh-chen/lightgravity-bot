---
title: "编排角色对比实验（第二轮）PROTOCOL（冻结）"
doc_type: experiment-protocol
category: engineering
status: frozen-before-formal-run
experiment_id: agensh-orchestration-r2-20261015
branch: experiment/agensh-r2-20261015
worktree: /tmp/lightgravity-worktrees/agensh-r2-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
frozen_at_utc: "2026-10-15T05:53:15Z"
freeze_manifest_sha256: a9fba8f02cc05b09aaa6ae258c6fb20cf333fc7ad0be74fc10cd8797484a9311
updated: "2026-10-15"
---

# 编排角色对比实验（第二轮）：PROTOCOL（先冻结，后运行）

> 本文件在任何正式（真实模型）请求之前写定并冻结。冻结时刻由系统时钟实测记录为
> **2026-10-15T05:53:15Z**；受控输入/提示/参数/验收的快照清单哈希为
> `a9fba8f02cc05b09aaa6ae258c6fb20cf333fc7ad0be74fc10cd8797484a9311`
> （见 `evidence/offline/freeze_manifest.sha256` 与 `freeze_manifest.hash.txt`，共 26 个文件）。
> 正式运行后只允许追加“偏差/失败记录”小节，不得回溯修改假设、fixture 规范、验收测试、
> 提示模板、调度参数或判定阈值。发现致命实现问题应立即停止并如实报告，不补跑覆盖原样本。

## 0. 一句话问题

在固定了确定性调度、文件事实源、程序化原子认领/同伴协商、权限、预算与验收之后，
**是否还需要一个独立的编排模型**（只负责开头一次规划）才能让两名 worker 完成受控编辑协作？

## 1. 实验性质与边界（必须先声明）

- 这是**受控编辑协作比较**，不是产品端到端验证，也**不是**真实 SDK 工具循环。
- 驱动用标准库直接调用 OpenAI 兼容的 DeepSeek Chat Completions。模型只返回 JSON
  （认领/消息/发现、或文件内容），由**程序**做原子认领、租约、base hash、语法、越权、
  整合与验收。模型没有真实文件/命令/网页工具循环，没有多轮会话记忆，没有 SDK 的
  Agent loop、session/skills/hooks。
- 因此本轮**只测**：在相同的程序化认领/同伴协商之下，“开头一次独立规划”的差异；
  **不测**：SDK 工具选择、长会话、恢复/取消、权限沙箱、真实工程规模。
- **无论结果如何，都不能据此直接删除产品中的编排/规划角色。** 本轮只产出“下一轮产品
  SDK 候选”或“没有足够证据”，不作为自动淘汰依据。
- 不切换供应商，不打印/记录密钥，不写认证头。密钥只从进程环境读取 `DEEPSEEK_API_KEY`。

## 2. 两组条件（唯一自变量）

| 组 | 独立编排模型 | 调用 | worker 可见内容 |
|---|---|---|---|
| **B 仅初始规划** | 开头 1 次规划 | 每 run ≤1 次 planner | 目标 + 文件 + 共享发现 + 上轮程序反馈 + **B 的计划文本** |
| **C 无编排模型** | 无 | 0 | 目标 + 文件 + 共享发现 + 上轮程序反馈（**无任何计划/语义任务分解**） |

- 两组**完全相同**：模型与参数、工具/文件权限、程序化认领与原子租约、同伴协商、
  调度、验收程序、轮数、worker 提示模板、上下文检索与整合规则、每轮每 worker 调用数。
- 差异仅在 B 额外有 1 次开头规划，且计划文本额外提供给 B 的 worker。
- 规划模型不得修改文件或验收测试，只输出计划/接口约定文本。
- worker 身份 w1/w2 使用相同模板，仅身份标签不同；**不按 w1/w2 写死文件路径**。

## 3. 固定参数（冻结）

- 模型 `deepseek-v4-flash`，端点 `https://api.deepseek.com/v1/chat/completions`。
- 每请求：`max_tokens=8192`、`temperature=0.0`、`stream=true`、
  `stream_options.include_usage=true`、显式 `thinking={"type": "disabled"}`。
  **claim/planner/edit 使用同一上限**以简化公平；不使用 `response_format`。
- `top_p` 不设置（服务默认）。
- 首个有效输出期限 30s，每请求总超时 90s；有界 SSE 客户端保证不被 keep-alive 无限拖住。
- 顺序 seed `ORDER_SEED=20261015`，对 18 个 run spec 做固定打乱。
- `repeat` 0/1/2 的“先认领者”固定为 w1/w2/w1（交替）；同一 repeat 的 B、C 使用相同的
  先认领顺序（配对一致）。
- worker 输出长度限制（两组一致）：message ≤240 字符；findings ≤3 条、每条 ≤160 字符；
  summary ≤200 字符；单文件内容 ≤20000 字节。

## 4. 单 run 流程（2 轮）

每 run：2 名 worker、2 轮；t3 第二轮在开始前对所有组**同样**注入用户新增要求。

每轮：

1. **认领/协商阶段（顺序）**：先调用先认领者 1 次，其 claim 提议与消息由程序原子
   检查/授予后，**立即对后认领者可见**；再调用后认领者 1 次。每名 worker 每轮最多
   提议认领 1 个可写文件，也可 claim=null 只复核。
2. **编辑/复核阶段（并行）**：两人都拿到本轮完整的 claims、messages 与相关发现后，
   各自再提交 1 次（可并行）；所有编辑针对**同一个冻结 base**，写入各自 staging 目录。
   只有持有对应路径租约的 worker 才可提交该文件的写；否则越权被拒（不可暗中调度语义替其选文件）。

因此每轮 4 次 worker 调用（2 claim + 2 edit），每 run 8 次 worker 调用；B 另有 1 次 planner。
18 run 正常调用上限 = 144 worker + 9 planner = **153**。

- 每 worker 每轮最多占 1 个可写文件（通用资源公平规则，两组相同，**不是**程序语义任务分解）。
- 已被认领的文件不能再给另一 writer；后者可选其他文件或只复核并留言。
- **可写文件**由通用规则定义：workspace 内除包入口 `__init__.py` 之外的所有文件；两组相同。
- 若某轮只有 1 个可写文件，另一 worker 只能复核；报告真实 writer 利用率，不把 2 worker 说成 2 并行 writer。
- 所有 worker 知道团队身份与程序规则，可发表接口约定、请求与发现；消息同轮送达
  （claim 阶段先者→后者；edit 前全员可见）。
- 程序对 B/C 使用同一套处理：越权、base hash 不符、语法错误、真实冲突。
- driver 不得利用验收结果选择某一 worker 的正确实现；测试只针对统一整合版本。
- worker 不能写 TASK/RUN/SUBTASK/events 或测试；租约、owner、revision 只由 driver 写。
- 足以自我声明的限制：这是**有界两轮同步**流程，不是任意多轮异步 Agensh。

## 5. Fixtures 与验收（沿用第一轮规范与验收代码）

fixture 自第一轮源复制，逐文件哈希见 `evidence/offline/source_fixtures.sha256`；
`initial/` 可进入模型上下文，`acceptance.py` 与 `reference/` **绝不进入模型上下文**。

- **T1 independent**：`src/slugs.py`（slugify）、`src/ranges.py`（clamp、in_range），验收 6 项。
- **T2 interface**：`src/geometry.py`（area、perimeter）、`src/report.py`（describe），
  跨模块依赖，接口在用户目标中显式写定，验收 6 项。
- **T3 evolving**：`src/stats.py`；第一轮 mean/median（stage1 5 项）；第二轮开始前对**所有组同样**
  注入 mode/stdev 新要求（stage2 共 9 项）。

验收以子进程运行：清理凭证环境、超时 30s、隔离 cwd=workspace。输出
`{"checks":[...],"passed":n,"total":m}`。首轮原始验收不泄漏给模型，只给已产生的 pass/fail 反馈。

## 6. 样本、重复与顺序

- 3 类任务 × 2 组 × 3 次真正独立重复 = **18 run**；每组 9 run、每类每组 3 run。
- 每次重复都**重新请求**，不复用缓存输出；每样本从同一 fixture 初始 hash 启动；
  样本间不共享结果、无跨 run 结果泄漏。
- 顺序由固定 seed `ORDER_SEED` 打乱并记录实际顺序；`repeat` 交替 w1/w2 先认领，
  报告身份/顺序敏感性。
- `temperature=0` 不保证重复独立随机采样；**不宣称统计显著性**。

## 7. 预算与硬界

- 正式第一个请求起墙钟硬上限 **25 分钟（1500s）**。
- 正常模型调用上限 **153**（144 worker + 9 planner）。
- 基础设施失败额外重试上限 **9**（整个实验累计），不掩盖失败，每次重试在 raw/events 标注。
- 累计 HTTP 硬上限 **162**。
- provider reported `total_tokens` 累计硬上限 **600000**；发起调用前为并发 inflight
  预留“估计输入 + 8192 输出”。usage 缺失记 `usage_unknown`，按字符数/4 保守计入，
  **不宣称 token 硬界被精确执行**。
- 每请求总超时 90s；HTTP 基础设施失败有限退避重试并计入预算。
- 连续 3 次基础设施失败即停止实验。
- 语义/JSON/权限失败**不增加模型输出重试**，失败计入分母。
- 不额外真模型调试；先离线 mock 客户端/协议。
- 费用：无可核验价格来源则记 `unknown`，不猜费率。

## 8. 截断与 reasoning 控制（本轮重点）

- 显式 `thinking.type=disabled`，`max_tokens=8192`。
- 原始记录保存：实际请求参数、`finish_reason`、usage（含 reasoning 字段）、响应回显模型名
  （若提供）与正文。
- 任何 `finish_reason=="length"` 或检测到 JSON 截断 → 该样本照记失败并标“混淆”，
  **本轮不声称已消除截断，也不事后补跑**。
- 若服务不接受 thinking 配置（4xx）或仍出现 reasoning token/内容 → 保存原错并**停止**，
  不偷偷修改参数或切模型。

## 9. 文件事实源、索引与事件

每个 run 目录：

```
workspace/                当前整合代码（每轮验收对象，代码事实源）
staging/r<n>/<worker>/    隔离 checkout（应用提案并校验）
TASK.md RUN.md            实验状态 frontmatter（只由 driver 写）
subtasks/r<n>-<worker>.md 每 worker/轮次独立子任务；当前 owner/revision/lease/status 的权威
events.jsonl              只追加：claim 提议/接受/冲突、消息投递、发现、应用、验收、重试、中止
raw/                      每次 HTTP 尝试的脱敏请求/响应/usage/finish_reason/reasoning
calls/<logical>.json      逻辑调用日志（恢复时不重复请求，可重建）
results.json              可重算的逐样本结果（派生）
```

- 当前 lease/owner/revision 的权威是 `subtasks/r<n>-<worker>.md` frontmatter，
  **不另维护 claims.json 作为权威**。
- events.jsonl 只保存 history/message/finding/claim 结果等追加事件，不保存“当前状态”。
- `results.json`、`analysis.json`、`summary.json` 均是可从 raw + events + subtask 重算的派生报告。
- 一致性检查：结果与 frontmatter 状态一致；worker 未写控制状态；应用变更与冲突都在 events 有记录；
  引用的 run/worker 存在；subtask 的 base_revision 与当轮 base 一致。
- 接受验收的进程环境不含凭证；凭证只由 driver 进程持有。

## 10. 指标（预注册）

每 run：首轮/最终全部通过与条目数、总 token 与 input/output/cache/reasoning、
planner/claim/edit 分项 token 与调用、端到端耗时与到首次通过的耗时（仅已观察检查点）、
失败/截断/重试、冲突/越权/无效编辑、真实 writer/idle（按租约轮次）、SoT 一致性。
按任务类 × 配对 repeat 及总组呈现，不只总均值；**所有失败纳入分母**。
B/C 总成本包括 planner/claim/edit/协商/基础设施重试；这是固定 worker 机会实验，
**不自称等总 token 预算对比**。

## 11. 预注册判定规则（只用于下一轮候选，不用于淘汰）

“独立编排可移除候选”必须**同时**满足：

1. C 组 **9/9** 全部客观验收通过；
2. 每类任务 C 的通过 run 数 **不低于** B（每类 3 run）；
3. C 组 **0** 额外 SoT/越权问题（sot_issues=0 且 overreach=0）；
4. C 组 **0** 截断；
5. 相对 B 的**中位 run token** 或**中位耗时**改善 ≥15%，且另一指标中位数不恶化 >10%
   （即：token 改善 ≥15% 时耗时中位改善 ≥−10%，或耗时改善 ≥15% 时 token 中位改善 ≥−10%）。

- 若满足 → 列“独立编排可移除候选”（仅候选，非自动淘汰）。
- 若 C 质量低（未 9/9 或某类低于 B）→ 列“保留相应规划能力候选”。
- 其余 → “没有足够证据/无明显收益”。
- 小样本不证明普遍非劣，**不能据此直接删产品角色**。

## 12. 修订历史

- 2026-10-15T05:53:15Z：创建并冻结本协议（正式真实模型请求前）。冻结 manifest 哈希见文首。
  本轮相对第一轮的受控变化：去掉 A 组；B/C 均加入程序化原子认领/同伴协商；
  `max_tokens` 2048→8192、显式 `thinking.type=disabled`；每类每组 1 次→3 次独立重复；
  第一轮弱无编排基线（同步整文件冲突拒绝）不再使用。

## 13. 偏差与失败记录（运行后只追加）

**正式运行：首请求 `2026-10-15T05:53:56Z`，最后事件 `2026-10-15T05:57:11Z`，约 195s。**

1. **预算实测**：HTTP 153/162、正常调用 153/153（72 worker + 9 planner 的 B，72 worker 的 C）、
   重试 0/9、`total_tokens=179851`（<600000）、`usage_unknown_calls=0`、`reserved_tokens=0`、
   无 fatal、无 abort、无 driver 异常。
2. **截断/reasoning**：`thinking.type=disabled` 被接受，153 次响应 `finish_reason` 全为 `stop`，
   `reasoning_tokens=0`，`finish_reason=length` 0 次。本轮**不声称**已普遍消除截断，仅记录本配置下未发生。
3. **唯一质量失败（B，t3_evolving__B__r2，2/5→6/9）**：B 的规划把同一个 `src/stats.py` 同时分给
   w1（mean）与 w2（median）；程序“每轮每文件一名 writer”规则下，先认领者两轮都占住该文件，
   第二轮漏做 median。这是规划语义拆分与共享程序规则的交互，不是 driver bug，也不是截断/解析失败
   （该 run 冲突/越权/无效/截断均为 0）。C 在 t3 的 3/3 全过。详见 REPORT §4。
4. **过程质量**：18/18 run SoT 一致；两组 claim/edit 冲突 0、越权 0、无效编辑 0、解析失败 0；
   未发现无条件后写覆盖；`runs/` 内无密钥/认证头。
5. **运行后离线修正（不影响任何真实模型请求）**：
   - `driver/analyze_results.py` 中预注册判定的实现有一处类型错误：`REPEATS` 在该脚本内是列表 `[0,1,2]`，
     导致 `expected = len(TASKS) * REPEATS` 变成列表、`C_all_9_pass` 恒为 False。已在**所有 153 次模型调用结束后**
     改为 `len(REPEATS)`，使离线重算与冻结的判定规则文本（§11）一致。冻结规则文本、fixture、验收、
     提示、参数均未改动；raw/results 未改动。
   - 新增纯离线核对脚本 `evidence/finalize/finalize_checks.py`（在 `evidence/` 下，不在冻结的 `driver/` 输入集内）。
   - 因此 `evidence/offline/freeze_manifest.sha256` 对 `driver/analyze_results.py` 的哈希与当前文件不再一致；
     **实验输入（`fixtures/` 全部、`config_snapshot.json`、`prompt_snapshot.json`、其余 driver 文件）哈希未变**，
     该变化仅影响离线分析工具本身。PROTOCOL 预运行哈希为
     `8b580fdf9a414ce4c270ac3d5d74b53fdd94e826f04703b2ed1a86373b4d3a7f`（本小节追加前）。
6. **身份/顺序敏感性**：repeat 0/1/2 交替 w1/w2 先认领，同 repeat 的 B/C 一致；B 的唯一失败发生在
   repeat 2（w1 先）。n=3 无法区分稳定身份效应。
7. **与第一轮的差异**：第一轮弱无编排基线（无认领、整文件冲突即拒绝）使 C 近乎全冲突失败；
   本轮加入原子认领/同伴协商后两组冲突均为 0，C 9/9。第一轮“C 不可行”主要是弱基线造成，不能外推。
