---
title: "编排角色消融实验 PROTOCOL（冻结）"
doc_type: experiment-protocol
category: engineering
status: frozen-before-formal-run
experiment_id: agensh-ablation-20261015
branch: experiment/agensh-ablation-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
updated: "2026-10-15"
---

# 编排角色消融实验：PROTOCOL（先冻结，后运行）

> 本文件在任何正式（真实模型）样本运行之前写定并冻结。正式运行后只允许追加“偏差/失败记录”小节，
> 不得回溯修改假设、fixture 规范、验收测试、判定阈值或调度参数。若实际执行与本文不一致，必须如实记录，
> 不得用事后调整掩盖。允许在正式运行前修正明显的实现错误，但需在本文件“修订历史”中记录时间与原因。

## 0. 一句话问题

在固定了确定性调度、文件事实源、权限、预算与验收程序之后，**独立的 LLM 编排角色**（负责初始分工/
计划、并在第一轮执行后重新规划）能否在小团队协作中带来可观测增益？

## 1. 实验性质与边界（必须先声明）

- 这是**受控编辑协作 pilot**，不是产品端到端验证，也不是真实 SDK 工具循环。
- 驱动通过标准库直接调用 OpenAI 兼容的 DeepSeek Chat Completions。模型只返回 JSON（文件内容/修改
  + 简短发现），由**程序**做路径、base hash、大小与整合检查。模型没有真实的文件/命令/网页工具循环，
  没有多轮会话记忆，没有 SDK 的 Agent loop、session/skills/hooks。
- 因此本实验**只测**：受控编辑协作中“是否有独立编排角色”的差异；**不测**：SDK 工具选择、长会话、
  恢复/取消、权限沙箱、真实工程规模。
- **无论结果如何，都不能据此直接删除产品中的编排/规划角色。** pilot 只能产出“下一轮候选”。
- 不得切换供应商，不打印/记录密钥，不写认证头。密钥只从进程环境读取（`DEEPSEEK_API_KEY`）。

## 2. 三组条件（唯一自变量）

| 组 | 编排模型 | 调用预算 | worker 可见内容 |
|---|---|---|---|
| **A 全程编排** | 初始规划 + 第一轮执行后重新规划 | 每次运行 ≤ 2 次编排调用（各 ≤1 次） | 用户目标 + 文件状态 + 共享发现 + 上一轮程序反馈 + **A 的计划** |
| **B 仅初始规划** | 仅初始规划 | 每次运行 ≤ 1 次编排调用 | 用户目标 + 文件状态 + 共享发现 + 上一轮程序反馈 + **B 的计划** |
| **C 无编排** | 无 | 0 次编排调用 | 用户目标 + 文件状态 + 共享发现 + 上一轮程序反馈（**不含任何人工/模型任务分解**） |

- 三组**相同**：确定性调度、文件事实源（TASK/RUN/SUBTASK + events.jsonl）、权限规则、预算规则、
  验收程序、worker 数量（2）、执行轮数（2）、每轮每 worker 调用上限（1）、模型与参数、上下文来源、
  补丁工具协议、所有 worker 看到相同用户目标/文件状态/共享发现/上一轮程序反馈。
- 差异仅在：**A/B 额外提供编排计划**（计入其调用与成本）；C 由 worker 自行选择/提出工作。
- C 组**保留**共享发现、同伴记录、event 追加等基础设施，不因缺编排而剥夺。
- worker 身份区分（w1 / w2），但使用**完全相同的提示模板**，仅身份标签不同。
- 编排模型（A/B）**不得**直接修改文件或修改验收测试；它只输出计划/分工/接口约定文本，交给 worker。

## 3. 固定调度参数

- 模型：`deepseek-v4-flash`（与现有产品探针一致，端点 `https://api.deepseek.com/v1/chat/completions`）。
- 每请求 `max_tokens=2048`，`temperature=0.0`，`top_p` 不设置（用服务默认），`stream=true`，
  `stream_options.include_usage=true`。**不使用 `response_format`**：该字段在本端点的支持未由既有探针证据证实，
  为保护有限预算改用“提示词要求 JSON + 程序括号匹配容错解析”；解析失败只记该 worker 本轮无有效输出，
  不计入基础设施重试。
- 每轮每 worker 最多 1 次模型调用；编排每运行 A=2、B=1、C=0。
- 轮数固定 2。每轮结束都运行同一验收程序并把**相同的程序检查反馈**提供给下一轮（t1/t2 两轮检查相同；
  t3 见 §4.3）。不因看到某组成绩额外补跑或优化提示。
- 每轮内 2 名 worker 的模型调用允许并发（≤2 并发），结果按 w1/w2 固定顺序收集，保证确定性。
- 集成：本轮所有 worker 提案从同一 base 状态出发；每名 worker 的提案先应用到各自隔离 checkout 做校验，
  再统一整合。
- 冲突规则：同一路径若仅一方修改→应用；多方修改且内容完全一致→应用；多方修改且内容不同→
  **记为冲突，保持 base 不变，不采用任一方**（不无条件后写覆盖），并在反馈与 events 中如实记录。
- 样本隔离：每个样本从同一 fixture 初始 hash 启动到独立 run 目录，样本之间不共享结果。

## 4. Fixtures 与验收（在运行前写定）

所有 fixture 位于 `fixtures/<id>/`：`initial/`（可注入模型上下文的初始代码）、`acceptance.py`
（客观验收，**不进入模型上下文**）、`reference/`（参考正确解，**不进入模型上下文**，仅用于离线自检）。
模型上下文只列出 `initial/` 下允许的文件，排除 `acceptance.py`、`reference/`。

验收以子进程运行：清理凭证相关环境变量、设置超时、隔离 cwd（workspace）、禁用网络不承诺（仅断言无凭证）。
验收脚本输出 JSON：`{"checks":[{"name":...,"passed":bool,"detail":...}], "passed":n, "total":m}`。

### 4.1 T1 独立修改（independent）

初始文件：

```
src/__init__.py                 # 空
src/slugs.py                    # def slugify(title: str) -> str: raise NotImplementedError
src/ranges.py                   # def clamp(value, lo, hi): raise NotImplementedError
                                # def in_range(value, lo, hi) -> bool: raise NotImplementedError
```

用户目标（模型可见，组长相同）：实现 `slugify`、`clamp`、`in_range`，语义与验收一致：

- `slugify(title)`：转小写；把连续的非字母数字字符替换为单个 `-`；去掉首尾 `-`。
- `clamp(value, lo, hi)`：低于 lo 返回 lo，高于 hi 返回 hi，否则返回 value。
- `in_range(value, lo, hi)`：lo ≤ value ≤ hi 时为 True。

验收条目（每轮相同，共 6 项）：
`slug.case`、`slug.multi`、`slug.trim`、`clamp.low`、`clamp.high`、`in_range`。

### 4.2 T2 跨模块接口依赖（interface）

初始文件：

```
src/__init__.py                 # 空
src/geometry.py                 # def area(shape): raise NotImplementedError
                                # def perimeter(shape): raise NotImplementedError
src/report.py                   # from .geometry import area, perimeter
                                # def describe(shape): raise NotImplementedError
```

接口在用户目标中**显式写定**（公平，不隐藏知识）：`shape` 为 dict，`kind` ∈ {`rect`,`circle`}；
`rect` 用 `width,height`，`circle` 用 `radius`；未知 kind 抛 `ValueError`；
`area`/`perimeter` 对 circle 用 `math.pi`；`describe(shape)` 返回
`f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"`。

验收条目（每轮相同，共 6 项）：
`geo.rect.area`、`geo.circle.area`、`geo.rect.perimeter`、`geo.bad.kind`、`report.rect`、`report.circle`。
`report.*` 依赖 `geometry`，构成跨模块依赖链。

### 4.3 T3 第二轮新增明确要求（evolving）

初始文件：

```
src/__init__.py                 # 空
src/stats.py                    # def mean(nums): raise NotImplementedError
                                # def median(nums): raise NotImplementedError
```

- 第一轮用户目标：实现 `mean`、`median`（median 对偶数长度取中间两数平均；空列表抛 ValueError）。
- 第二轮开始前，**所有组同样**注入用户新增要求：新增 `mode(nums)`（众数，平局取最小）与
  `stdev(nums)`（总体标准差，空列表抛 ValueError）；且 `mean([])` 必须抛 `ValueError`。
- 验收分两阶段：
  - `--stage 1`（5 项）：`mean.basic`、`mean.empty`、`median.odd`、`median.even`、`median.empty`。
    此阶段是首轮验收。
  - `--stage 2`（9 项）：stage 1 全部 + `mode.basic`、`mode.tie.min`、`stdev.basic`、`stdev.empty`。
    最终验收。
- 说明：`mean/median` 空列表均抛 ValueError；参考解第一轮即满足 stage 1。新增要求为 `mode` 与 `stdev`。

## 5. 样本与顺序

- 3 类任务 × 3 组 = 9 个样本，每类每组各 1 次。
- 组顺序用**固定 seed** 打乱（seed 在 driver 中常量 `ORDER_SEED`，并记录实际顺序）。
- 每个样本从 fixture 初始 hash 启动；测试/要求一致；样本互不共享结果。

## 6. 预算与硬界

- 正式 pilot 正常模型调用：**≤45**（worker 36 + A 编排 6 + B 规划 3）。
- 基础设施失败重试：**≤3**，且**额外计数**，不得掩盖失败（每次重试都在 events/raw 中标注。
  模型输出解析失败**不算**基础设施失败，不占用重试额度，按该 worker 本轮无有效输出记录）。
- 累计 HTTP 请求：**≤48**。
- 每请求输出上限：2048 tokens。
- 墙钟上限：**15 分钟**，从 pilot 首个正式请求开始计。
- 累计 provider reported `total_tokens` 上限：**200000**；下一次调用前预留输出预算（2048）。
- 若 usage 缺失：明确记 `usage_unknown`，按保守估算（prompt 字符数/4 + 输出字符数/4，向上取整）计入，
  并声明“未据此声称硬 token 预算被精确执行”。
- 每请求有独立的首个有效输出期限与总超时；不能被 SSE keep-alive 无限拖住。
- 上游持续失败：停止并报告，不自动扩大预算。
- 不额外跑真模型调试；先离线验证 driver。
- 上游持续失败阈值：连续 3 次基础设施失败即停止 pilot（保留已有证据）。
- 驱动 pi 自身用量与 pilot 用量分开记录，不混算。

## 7. 文件事实源与事件

每个 run 目录：

```
workspace/            # 当前整合代码（每轮验收对象）
staging/w1, w2/       # 隔离 checkout（应用提案并校验）
TASK.md RUN.md SUBTASK.md   # frontmatter 保存实验专用状态；控制状态只由 driver 写
events.jsonl          # 只追加：协作发现/消息/变更历史/冲突/重试
raw/                  # 脱敏请求体 + 响应内容 + usage（无密钥/无认证头）
results.json          # 可重建输出（索引/结果）
```

- `TASK.md` frontmatter：task id、fixture、初始 hash、用户目标、阶段、状态。
- `RUN.md` frontmatter：group、round、pilot 起止、编排调用数、worker 调用数、tokens、状态。
- `SUBTASK.md` frontmatter：worker、轮次、base hash、是否有效输出、是否重试。
- 实验专用 schema，不声称现有产品 schema 已支持。
- 一致性检查（`check_sot`）：结果 JSON 与 frontmatter 状态一致；worker 未写控制状态；所有应用变更与冲突
  都在 events 中有对应记录；引用的 run/worker 存在。

## 8. 指标

每样本：全部验收通过（bool）、通过条目数、首轮通过情况、最终通过情况、实际总耗时、编排耗时、
provider 真实 input/output/cache tokens（若可得）、冲突数、重复编辑数、返修数、失败重试数、SoT 一致性。
费用：无真实价格来源则记 `unknown`，不猜费率。所有失败样本纳入分母。

比较同时呈现：固定 worker 执行机会（36 次 worker 调用）下的质量/成本，以及**包含编排开销**的总成本
（A/B 的编排调用计入）。首轮**不声称**等总计算预算实验，也不声称统计显著性。

## 9. 预注册决策规则（仅用于下一轮候选，不用于淘汰）

- pilot **不能据此直接淘汰**任何角色。
- **去编排候选**：若 C 组 3 个样本全部客观验收通过、无额外 SoT 一致性问题，且相对 A 的
  总 tokens 或总耗时改善 ≥20%（`(A-C)/A ≥ 0.20`，任一指标），列为下一轮“去编排”候选。
- **按需/初始规划候选**：若 B 质量 ≥ A（最终验收通过条目数不低于 A）且开销更低
  （总 tokens 或总耗时更低），列为“按需/初始规划”候选。
- **保留规划能力**：若关键依赖/变更任务（T2/T3）中 C 失败而 A/B 通过，则先保留相应规划能力。
- 其余情形记为“不确定”。
- 局部场景结论不推广到所有任务类型。

## 10. 交付物

`PROTOCOL.md`、可复现 driver/fixtures/验收测试、原始脱敏请求输出与 usage、逐样本结果、`REPORT.md`
（中文，先结果后限制，明确未覆盖真实 SDK / 恢复取消 / 大规模）。正式 pilot 通过的 driver 离线自检记录
命令、基准 hash、具体成功失败，但不称版本 QA。

## 11. 修订历史

- 2026-10-15（**精确冻结时刻未记录**；原始记录写作占位符 `05:2xZ`）：创建并冻结本协议（正式真实模型样本运行前）。
- 2026-10-15（运行前，仍在冻结阶段；**精确时刻未记录**，原始记录写作占位符 `05:2xZ`）：把 T3 验收条目数从草稿的
  6/8 修正为 **5/9**（stage1 5 项，stage2 新增 4 项），与 `fixtures/t3_evolving/acceptance.py` 实现一致；
  把固定参数从 JSON mode 改为**不使用 `response_format`**。以上均在首个正式真实模型请求之前完成，不属于事后修改。
- 注：本协议冻结的精确墙钟时间未在任何运行前记录中保存。首个正式请求时间 `2026-10-15T05:26:40Z` 由
  `runs/pilot_state.json` 的 `pilot_start_epoch` 推出；冻结发生在此之前，但不得据此补写或反推冻结时刻。
- 收尾静态核对（不重跑、不改动验收）：`fixtures/t1_independent/acceptance.py`=6 项、`t2_interface`=6 项、
  `t3_evolving` stage1=5 项 / stage2=9 项，各条目名称与本协议 §4.1–§4.3 所列一致，**当前协议与验收代码无条目偏差**。
  历史上唯一的条目变更（草稿 6/8 → 冻结前 5/9）已记录在上。

## 12. 偏差与失败记录（运行后只追加）

**正式 pilot 于 2026-10-15T05:26:40Z 开始（首个请求），2026-10-15T05:29:40Z 最后调用结束，墙钟约 180s。**

1. **输出上限与思维链 token（重要偏差/混淆）**：模型在 `completion_tokens` 内产生了大量 reasoning token（本次 45 次调用中
   reasoning 合计 24966 / completion 合计 55199，约 45.2%）。`max_tokens=2048` 被思维与正文共享，导致 **6/45 次调用**
   在 2048 处被截断（`completion_tokens>=2048`），其中 A 组 3 次（t3 第 2 轮：编排 replan、w1、w2）、C 组 3 次
   （t2 第 2 轮 w1，t3 第 2 轮 w1+w2）。截断的 worker 输出 JSON 不完整 → 记为 `no_valid_json`（模型输出失败，不占基础设施重试）。
   本次按协议未设置 `thinking.type=disabled`。这是一个**未预先控制的混淆因素**：A 组 t3 失败与 C 组部分失败直接由截断造成，
   因此 A/C 的质量差距被放大，不能全部归因于编排本身。已如实计入全部失败样本。
2. **基础设施重试未发生**：45 次正式调用全部 HTTP 成功，`retry_calls=0`；重试/连续失败停止逻辑只在离线 mock 中验证过。
3. **预算**：正常调用 45/45，HTTP 45/48，`total_tokens=106949`（<200000），`usage_unknown_calls=0`，墙钟约 180s（<900s）。
4. **无其它偏差**：文件 SoT 一致性检查 9/9 通过；无冲突被无条件覆盖（C 组 7 次冲突均保持 base）；未写密钥/认证头。
5. 未复核上游实际模型名（请求 `deepseek-v4-flash`；本 pilot 未记录上游回显名称）。
