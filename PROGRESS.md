---
title: "2026-10-15 开发进展与续接记录"
doc_type: report
category: project
updated: "2026-10-15"
---

# 当前进展与续接记录

这是 2026-10-15 用户要求保存的本地检查点。以下提交与任务数量为保存前核实结果；任务状态仍以各分支的 backlog/tasks frontmatter 为准，本文不替代任务事实源。尚未完成主分支合并，不把集成分支成果写成已在 main 可用。

## 协作约定

- 主代理只做项目管理，不编写产品代码或审查代码；所有调查、实施、集成、测试和 Git 执行通过 pi。
- 开发和产品先使用环境中的 DeepSeek。当前派工请求模型 ID 为 `deepseek-v4-flash`，成功响应实际模型为 `deepseek-flash`；未证明“4.1”版本号，不切换供应商。
- 并行开发使用独立 worktree、明确文件 owner，共享装配串行处理；快速原型小任务只做必要局部检查，大版本整合后集中独立 QA。
- 用户曾授权推送内部 Gitea，但本次仅保存本地检查点，不推送、发布或部署。密钥不进入文档、提示词、日志和 Git。

## 保存时的分支事实

| 位置 | 分支／提交 | 核实状态 |
|---|---|---|
| 本项目根目录 | `main`，保存前 `b132126` | clean；17 done、3 in-progress、7 todo |
| `/home/yhvh/code/lightgravity-bot-worktrees/ui-controls` | `integrate/ui-controls`，`6e23c7c` | clean；20 done、0 in-progress、7 todo；尚未合回 main |
| `/tmp/lightgravity-worktrees/lg013` | `dev/lg013`，`354def4` | Chat/Board 实施包，已经选入集成分支 |
| `/tmp/lightgravity-worktrees/lg016` | `dev/lg016`，`f7c4412` | 恢复控制与反重放守卫，已经选入集成分支 |
| `/tmp/lightgravity-worktrees/lg027` | `qa/lg027`，`fbd8a0e` | Settings/凭证专项 QA，已经选入集成分支 |

本次保存会在 main 新增文档提交，因此上述 main SHA 是保存前基点，不是保存后的 HEAD。所有旧 worktree、分支和证据保留。主分支任务仍将 LG-013/016/027 记为进行中，这是尚未合入的真实差异，不手工伪造完成。两侧 `tasks digest` 均 complete=true、diagnostics=[]。

集成分支中相对原基点的提交，按应用顺序：

1. `2d31831`：LG-013 Chat/真实看板。
2. `b7a0f7c`：LG-013 实施收尾，完整浏览器验收仍留 LG-021/022。
3. `a6d9f3c`：LG-027 Settings/凭证专项 QA。
4. `c2da464`：上述集成文档同步与一次真实只读直答探针。
5. `8c7214e`：LG-016 暂停/取消确认、中断恢复、跨 Run 原生续接。
6. `71dd30a`：Graph 节点原生 session 数据流。
7. `6e23c7c`：稳定 reuse identity、恢复反重放守卫。

main 的 `b132126` 另含 Firefox 真实同源 HTTP 诊断工具，合并时必须保留，不能用旧分支整树覆盖 main。

## 已有验证和限制

- LG-010 最小后端开发闭环已通过独立 QA，覆盖契约 1.3.1 core；不能视为后续整个首版 QA。报告见 [LG-010](probes/lg010/reports/lg010-qa-r2-after-refix.md)。
- LG-013/027 集成基点 `c2da464`：后端 410 passed、1 skipped，mypy 86 files；前端 75 passed，类型和构建通过。一次真实 DeepSeek 直答返回 HTTP 200，未创建 Task/Run/Member，workspace 无写入，泄漏检查无发现。
- LG-016 最终实施包 `f7c4412`：后端 434 passed、4 skipped，mypy 89 files；Graph session flow 定向 14 passed。本轮未新增真实模型调用，底层真实 SDK 续接沿用既有证据。
- 上述两组测试属于不同候选，不能相加，也不能声称最新集成 HEAD `6e23c7c` 已跑过全部检查。该 HEAD 的合并后全量检查与正式契约同步仍未完成。
- LG-016 对已完成写节点缺少可信复用、未知副作用或配置漂移时保守进入 `recovery_required`，不得静默 fresh 重放。完整 checkpoint skip 调度未实现，不夸大恢复能力。
- LG-027 专项是 CLI/真实 HTTP 与浏览器渲染证据，不是完整浏览器同源 HTTP 全功能端到端。真实调用精确总量未知，旧指令预算不能冒充实测硬上界。
- 首版整体 QA 尚未完成；LG-021/022/023/024 未开始。源代码中的候选能力和局部测试不等于最终用户验收。

## 当前外部阻塞

DeepSeek 出现间歇性过载及仅保活等待，导致 pi 生成通道长期停留 assistant pending。诊断通过 pi RPC 工具通道完成，未修改产品代码或全局模型配置。

- 模型列表同凭证请求 200，约 0.36 秒；生成接口捕获 503 `service_unavailable_error` / `Service is too busy`。
- 部分最小流式请求可在约 2 秒成功，说明并非持续网络或鉴权失败。
- 真实复现 pi 请求：HTTP 200 后约 36 秒只有 3 条 SSE keep-alive，没有生成数据；原生 pi 最小调用 60 秒未完成。
- pi 实际发送 `max_tokens=384000`。同轮改官方模型名并降至 32 后仍只有保活，尚不能证明别名或输出上限是根因。
- pi 默认 HTTP idle timeout 为 300000ms；排队保活和派工脚本缺少独立有效输出期限/等待心跳会造成长时间没有可见进展。原始挂起请求未作线缆级捕获，不能声称它们每次都返回了 503。
- 挂起的本次 pi 请求及诊断探针均已精确停止，未留作后台续跑；提交、dirty 来源、历史证据和 worktree 均保留。已有 root 8123 服务与长期其它 pi 进程未清理。

详见 [DeepSeek 诊断证据](probes/dispatch/deepseek-2026-10-15.md)。后续可先给派工层增加有效输出期限、等待提示和有限退避；工具执行期间不得仅因模型等待超时误杀工具，未知写副作用也不可自动重放。

## 恢复执行的顺序

1. 先用 env 凭证做有界 DeepSeek 健康检查，不打印密钥。通过后继续派 pi 集成执行者，cwd 为上面的 `ui-controls` worktree，避免重复 cherry-pick。
2. 续接集成兼容性检查：保留只读直答、Resource/Verifier 装配、自动 verify、Task 作用域 ack 幂等、connection_pin、canonical evidence、runtime token、LG-016 反重放守卫。同步 docs/08 至拟定加性契约 1.6.0，并同步入口文档；版本号与字段最终以实际实现为准，当前正式契约仍为 1.5.0。
3. 跑最新集成候选必要检查、提交，然后由 pi 合并回 clean main。保留本次进度文档和 main Firefox 诊断；发生文档冲突按最新事实合并，不 reset 或覆盖。
4. 重新运行 tasks ready，complete=true 且无诊断后再用 CLI claim LG-017/018/019。集成分支目前三项已就绪，但 main 尚未就绪；它们均未领取、未开始。
5. 基于同一 claim 提交，在 `/home/yhvh/code/lightgravity-bot-worktrees/` 新建 lg017、lg018、lg019 独立 worktree，使用 pi + DeepSeek 并行派出。旧 /tmp worktree 保留，新依赖不要再放 /tmp（曾发生配额耗尽）。
6. 三包分别负责：017 独立候选验证/有限返修/总预算；018 真实隔离 worktree/两个并行写节点/候选整合；019 持久通知/SSE 游标重连/准确版本回复。预制提示词已经划定 owner；共享装配点由后续集成者串行接线。
7. 实施整合后依次推进 LG-021 浏览器验收、LG-022 首版端到端/故障验收、LG-023 单 agent 对照、LG-024 交付准备。发现缺陷通过 pi 返修与独立复验，不能由主代理接手改代码或代码审查。

## 本地续接材料

- 持久操作备份：`~/.cache/lightgravity-bot/checkpoints/2026-10-15/`，不是产品运行依赖，也不含 env 文件或真实密钥。
- 包括 `lightgravity-pi-worker.py`、`lightgravity-pi-rpc-diag.py`、集成原提示词/续接提示词、LG017/018/019 三份批量派工提示词。恢复时优先使用这份持久副本，不依赖 /tmp 长期存在。
- Git 全分支 bundle 也保存在该目录，实际路径与校验结果由本次保存执行输出；bundle 用于本机灾备，不自动发到远端。
- 受保护原始派工日志：`~/.cache/lightgravity-bot/dispatch-logs/`；完整成本与 token 仅部分可计量，未知项不按零计算。
- 运行包装器只在进程内注入环境密钥，当前开发凭证 fallback 来源是本机相邻参考项目的 env；没有复制其密钥到本项目。这是本机派工约定，不能成为发布产品依赖。
- 任务 CLI（无需重新安装）：`node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest|ready|validate <项目目录>`；claim 语法参照 `tasks claim <项目目录> <ID> --as agent:<标识>`。
- 可用真浏览器：`/snap/bin/firefox` 156，原生 BiDi；复用 [浏览器诊断入口](probes/browser-diagnostics/README.md)。Snap profile/截图位于 `~/snap/firefox/current`，不要再把 Chrome 顶层导航挂起误报为全部 HTTP 不可用。
- 内部 Git 远端：`http://192.168.8.50:3000/admin/lightgravity-bot.git`。本批新增开发成果仍未推送；推送时使用现有 env 的受控凭证，不放进 URL、命令参数或 Git 配置。

保存工作只更新文档、备份与 Git 检查点，不认领新任务、不改任务状态、不启动实施/服务/部署。

---

## 本轮补充：资料接入与检索方向文档落盘（2026-10-15）

由单一文档执行者完成；**未改产品代码/依赖，未跑新模型请求，未提交/发布，未改任务状态，未写 `PROJECT.md`**。

- **新增设计**：[docs/09-source-intake-and-retrieval.md](docs/09-source-intake-and-retrieval.md)（方向已确认、**未实现**；API/schema/事件/状态**未冻结**；实施前须按 docs/08 §13 冻结并升版）。含 Chat 唯一常规入口、摄入生命周期与回执、文件/派生/缓存分层、索引与检索边界、分阶段验收、实测与局限、参考。
- **入口同步**：README（文档入口 + 计划标记 + 首版边界）、docs/01（架构链接）、docs/02（文件/资料边界）、docs/04（摄取写边界，摄取不自动建交付 Task/Run）、docs/05（Chat/Files 目标与当前实现差异）、docs/08（1.5.0 **无**新资料 schema/API/search/email，后续见 09）、agent.md（设计入口与摄取原则）。`design.md` 视觉 tokens **未改**。
- **证据归档**：[probes/source-intake/](probes/source-intake/README.md)，含两个探针 REPORT、原始 `DOC_CORRECTION.md`、指标/查询与重建 JSON、原始 OCR 响应、ASR 失败结果、必要合成 fixtures、真实提取 MD 的**逐字节副本**与 [MANIFEST.json](probes/source-intake/evidence/MANIFEST.json)（28 条、952781 字节、目标 sha256 全部一致、≤3 MiB）。`/tmp` 原件保留未动，未归档脚本代码。
- **检查**：[probes/source-intake/DOC_CHECKS.md](probes/source-intake/DOC_CHECKS.md)（Markdown 相对链接/frontmatter、入口与 SoT/Task 边界一致、归档 sha256 与大小、`git diff --check`）。**未跑**后端/前端测试、构建或真实推理。
- **范围**：不改 `CONTRACT_VERSION`（仍 1.5.0），不新增 API/枚举，不改现有端点语义，不新增 backlog 任务或改旧状态。
- **关键限制**：证据 A/B 均为合成小样本/隔离原型，只证明“**已测 Qwen 的 OCR 成功、已测 embedding 模型的转写失败**”，`gemma4-mtp` 等其它模型与 reader 接线未测；原型运行在系统 Python 3.14 + 临时脚本，**不是**产品 Python 3.12 依赖验收或 adapter 接入。
- **本仓库当前 dirty 的 no-orchestrator 代码/文档改动与其他旧证据均已保留**，未覆盖、未提交。


## 本轮补充：去中心化与 Embedding 正式排期（2026-10-15）

- 用户要求排期；新增 LG-028～041 共 14 项 todo，总计 41 项，既有任务状态与验收证据保留。
- 去中心化 LG-028～032：契约、原子领取/租约、受控同伴交接、真实执行与 QA/返修整合、集中验收与全生命周期成本对比。
- 资料与 Embedding LG-033～040：契约、原件摄取、图片/PDF OCR、词法索引、可选多模态向量、Chat/Files、中文 ASR 验证与集中验收；LG-041 在 ASR 质量达标后实施并集中验收中文转写扩展。
- 更新 [滚动排期](docs/06-roadmap.md) 第 6 节、[任务入口](BACKLOG.md) 与 PROJECT 决策。两线契约可并行准备；保留首版集中验收顺序与程序权限边界，不引入常驻模型编排 agent 或独立向量数据库。
- backlog 目录专项校验：41 项、无诊断；未修改代码、任务旧状态、凭证或当前 1.5.0 接口版本，未开始实施、模型实验或提交发布。日历日期未约定，当前为依赖与版本门排期。

## 2026-10-16 批量推进检查点（持续执行中）

本节覆盖上文旧检查点的当前事实；历史实验记录和旧 worktree 均保留。所有实施、调查、测试与集成经 pi + 现有 DeepSeek，主代理只协调；不推送、部署或发布。

- 原 main dirty 已由 pi 保全为 `b2bd5eb`；持久备份与完整第一批证据在 `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/REPORT.md`，排除凭证。原始 probes 中 12 个 YAML 诊断不改，开发任务 CLI 改以 **本仓库 `backlog/` 专用根**运行，41 项完整扫描、无诊断。
- 第一批 `integrate/ui-controls` 已以 merge `7928e0f` 收拢，未重复 cherry-pick；LG-013/016/027 为 done。main 同候选后端 **485 passed、1 skipped**，mypy 91 files；前端 **75 passed**，tsc/build 通过。此次产品模型调用 0；不代表完整首版 QA 通过。完整 checkpoint skip 仍未实现。
- LG-028/033 准备稿分别由隔离 pi 交付，再由单一 owner 串行冻结为 **1.6.0**（`9215a2f`，加性、默认关闭/未实现接口，非机械升版），两项 done。定向 contracts/API **65 passed**、mypy 通过。证据：[契约整合报告](probes/batch-20261016/CONTRACTS.md)。报告内若称“未跟踪实验”或把 Git blob ID 写作 sha256，均仅为表述问题：原始实验现已在保全提交中跟踪；40 位值是 Git blob ID。
- 当前管理基点 main `374759b`；backlog digest **22 done、6 in-progress、13 todo**。LG-017/018/019（共同基点 `141809d`）正在项目旁 `lightgravity-bot-worktrees/lg017|lg018|lg019` 由不同 pi owner 并行实施；共享接线与正式契约后续由唯一集成者串行处理。
- LG-029/034/039 已 claim（基点 `9ff71ff`），持久 worktree 已备；LG-039 已派出有界服务/真实语音质量验证，产品服务 health/models ≤4、推理 ≤6，无自动重试；样本/许可与质量不达标不得解锁 LG-041。LG-029/034 尚待派出（不是已实施）。
- 派工提示词与原始受保护日志位于 `~/.cache/lightgravity-bot/checkpoints/2026-10-15/*20261016.txt` 与 `~/.cache/lightgravity-bot/dispatch-logs/`。恢复须先核对各 worktree 最新 HEAD/status 与 REPORT/STATUS，不能盲目重放进程或 pick。开发 pi 用量仅部分可计量，不把未知当零。
- 下一步：收取 LG-017/018/019 必要局部证据 → 唯一 pi owner 集成并处理实际兼容性 → LG-021/022 独立集中 QA/返修复验；独立的 LG-029/034 可穿插。主代理不得接手代码。后续 LG-023/024、LG-030～032、LG-035～040 仍按真实依赖和集中门推进。

## 2026-10-16 第二批集成检查点（唯一集成 owner，持续执行中）

本节覆盖上文，为当前事实；旧实验与 worktree 全部保留，未推送/部署/发布。详细报告见
[probes/batch-20261016/INTEGRATION-2.md](probes/batch-20261016/INTEGRATION-2.md)。

- 集成前 main HEAD `374759b`；主代理本轮 PROGRESS 管理补充 dirty 已保留并随集成提交，未 reset/clean/覆盖。集成分支 `integrate/batch2`。
- 按实际 HEAD/status 收拢六包（均 clean）：LG-017 `ae85dd1`、LG-018 `ad4a10f`、LG-019 `eed0b28`、LG-029 `ddab113`（收尾 pi 已退出并提交）、LG-034 `3f98f04`、LG-039 `e6f3fd5`。逐分支 `--no-ff` merge，未重复 pick、未整树覆盖。
- 共享装配（唯一 owner）：`api/app.py` 挂载 sources（LG-034）、collaboration（LG-029，默认关闭）、notifications（LG-019）；`api/bootstrap.py` 按 LG-018 加性接线 `GraphDispatcher(..., workspaces=GraphWorkspaceProvider(WorktreeManager(settings.workspace_root)))`，**保持保守默认**未提高 `max_parallel`。
- 契约：`docs/08` 保持 `1.6.0`，仅更新 §4.3 的 LG-034/LG-029 状态行与 §5.1 事件实际产生说明。
- 整合候选检查：后端 `uv run mypy` 109 files clean、`uv run pytest -q` **545 passed, 1 skipped**；前端 tsc 0、vitest **81 passed**、vite build 通过。**产品真实模型调用 0**（mock/Git/HTTP 冒烟非完整 SDK 验收）。
- 状态：LG-018/019/034/039 与 LG-029 `done`（待版本 QA）；**LG-017 保持 `in-progress`**——默认 `ProgramReviewer` 只是机器检查换名，非独立模型/角色复核，目标未满足，留 LG-022 真实门复验；LG-041 保持 `todo` 并记录 `needs decision`。
- **LG-017 返修 R1（2026-10-16，branch `fix/lg017-r1`，基点 `c138537`）**：已补齐真实独立复核——新增角色/「默认字段 `default_reviewer_connection_ref`（加性）、真实最小受控 `ModelReviewer`（独立连接/上下文、无工具单轮、经程序 `validate_findings` 绑定可解析候选证据，模型不能判 done）、无 reviewer 时诚实 `UnavailableReviewer` 且阻止 accept；docs/08 加性升 **1.7.0** 并同步 README/PROJECT/agent/docs06。真实命令：`pytest tests/verify tests/settings tests/startup -q` exit 0（135 passed/4 skipped）、`mypy`（改动文件）exit 0；**真实 DeepSeek 探针 1 次调用成功**（`probes/lg017/review_real_probe.json`：`status=ran`/`model_calls=1`/`reviewer_kind=model`/`outcome=validated_outcome=passed`，`usage={"unknown":["usage"]}` 即 **usage unknown/成本部分覆盖**）；本次续接**新增产品模型调用 0**（未重放）。收尾修复 `validate_findings` 丢失 `reviewer_kind`/`model_calls`/`usage` 的 bug + 回归测。**仍 `in-progress`**（待 LG-022 独立集中 QA），本包不自评完整版本 pass；旧交付物/探针/未提交记录全保留。
- **LG-017 R1 新增检查**：`docs/08` 等文档 1.6.0→1.7.0 同步一致性；R1 相关 `tests/verify tests/coordinator/test_rework_integration.py -q` exit 0（28 passed）。
- LG-039 报告口径限定“本轮已测模型/路径无可用 ASR、LG-041 不解锁”，未泛化；`done` 仅指有界可行性负结果，不等于完整中文质量验收。
- 就绪任务已 claim（不代跑）：LG-021 → `qa/lg021`（基于整合候选，供新上下文独立 QA），LG-035 → `dev/lg035`（持久），LG-030 → `dev/lg030`（持久）。LG-022/023/024、LG-031/032、LG-036～040 仍按依赖推进。
- backlog 专用根校验：41 项、无诊断；27 done、1 in-progress、13 todo。
- 未完成质量门：首版集中 QA（021/022）、资料版（035～040）、去中心化版（030～032）；LG-017 独立 QA 缺口（R1 已补齐实现与 1 次真实模型复核，**仍待 022 独立集中 QA**）；LG-029 settings 写入/coordinator LeaseManager/执行身份注入；完整 checkpoint skip。

## 2026-10-16 第三批集成检查点（唯一集成 owner，持续执行中）

本节覆盖上文，为当前事实；旧实验、worktree、原始 probes 全部保留，未推送/部署/发布。
详细报告见 [probes/batch-20261016/INTEGRATION-3.md](probes/batch-20261016/INTEGRATION-3.md)。

- 集成前 main HEAD `c138537`（与预期一致）；集成分支 `integrate/batch3`。逐分支 `--no-ff` merge，无冲突，
  未重复 pick、未整树覆盖：`fix/lg017-r1` `8fbdedb` → `dev/lg030` `f029152` → `dev/lg035` `d7e4391` → `qa/lg021` `43dc3f1`（均 clean）。
- **LG-021 收尾进程**：集成开始时其收尾 pi（`bounded-lfsw8w5a`）仍在运行、`qa/lg021` 有未跟踪 `probes/lg021/`；本 owner **未触碰其 index/工作区**，先收其它三个已结束分支，末尾确认其退出且 commit clean 后方合并。
- 共享装配：后端三包无文件重叠；`uv sync --frozen` 成功（035 新增 `pypdfium2>=5,<6`，许可 BSD-3-Clause+Apache-2.0，自包含、懒加载、无 poppler）。默认 `create_app()` 实含 sources/intake/inbox/collab 端点（默认关闭）；`/content`/`/download` 仅经 `resolve_path` 读文件，不调用 OCR、不执行外部正文。
- **最小兼容修复（集成 owner）**：① LG-017 reviewer 默认连接接入 Settings 界面（`settings.ts` 类型 + `DefaultsEditor` 第三角色选择器 + 测试；显式语义，**不静默回退 worker**，不加新表单平台）——补上“无 reviewer→配置→独立复核”闭环；② LG-030 加程序认证接缝 `ApiContext.worker_identity` + `PeerService.request(authenticated_member_ref=...)`，**默认拒绝**（`unauthenticated`/`identity_mismatch`，不落盘），body 自报身份不作认证；真实身份注入/Graph 接线归 031，**不制造 030 永久 in-progress**。
- 契约：docs/08 保持 **1.7.0**（第三批未新增字段/端点/错误码；030 边界为集成澄清）。§4.3 LG-030/035 行更新为已实现（待 QA），加执行身份边界说明；§5.1 补 035 实际产生 `source.attributed`/`intake.failed`；docs/06 §6.1 加第三批更新。
- 整合候选检查（真实退出码，本批**确实改前端**故重跑）：后端 `uv run mypy` **124 files clean**、`uv run pytest -q` **647 passed, 1 skipped**；`tests/collaboration` **57 passed**；协议链复现 5 行符合；前端 tsc 0、vitest **83 passed**、vite build 通过。**本轮产品真实模型调用 0**（017 的 1 次真实 DeepSeek 复核沿用原始证据，未重放）。
- 状态：**LG-030 → done（待版本 QA LG-032）**（协议安全满足，真实身份/Graph 归 031）；**LG-017 保持 in-progress**（R1+UI 已补齐，仍待 022 及 021 增量独立集中 QA，不自评 pass）；**LG-035 保持 in-progress**（真实中文/表格人工真值质量门阻塞、已授权端点两次不可达，不以合成页当真实品质）；**LG-021 保持 in-progress**（独立 QA 主要路径 31/31 通过但存在证据精度/未测/新 reviewer UI 未覆盖，判定与最小复验清单见其 REPORT）。
- backlog 专用根校验：**41 项、无诊断**；`tasks ready` **无就绪任务**（LG-022/031/036 前置未真 done）。**未 claim LG-022/031/036，未建其 worktree**（不就绪则不伪造 claim commit）。
- 未完成质量门：首版集中 QA（LG-021 增量、LG-022 含 LG-017 独立复核真实门）；去中心化（LG-031 真实身份/Graph 接线、LG-032）；资料（LG-036 依赖 035、LG-037/038、LG-040）；LG-035 真实中文/表格质量门 + 已授权 OCR 端点不可达（外部阻塞，主代理已向用户发异步可选样本路径/服务恢复问题，尚无回复）；完整 checkpoint skip 未实现。

### 第三批集成补充事实（准确续接）

- 集成分支已合回 `main`（merge commit），集成前 main `c138537`、集成后 main 见本文件提交时的 `git rev-parse HEAD`；**未推送**。
- 集成分支 `integrate/batch3` 与来源分支 `fix/lg017-r1` `8fbdedb`、`dev/lg030` `f029152`、`dev/lg035` `d7e4391`、`qa/lg021` `43dc3f1` 全部保留。
- 未创建 LG-022/031/036 的 claim/worktree：集成后 `tasks ready` 无就绪任务（前置 LG-017/021/035 仍 in-progress），不就绪则不伪造 claim commit。
- 测试工具隔离怪癖（非本批引入）：`tests/startup/*` 的 `from conftest import make_settings` 在同一会话与 `tests/api` 同收集时冲突；`c138537` 已存在，全量 `pytest -q` 正常。
- `git diff --check` 仅报 LG-035 gold 真值 fixture 的尾随空白（字节保真，不改）。

### 第四批准备：依赖校正与状态语义纠正（2026-10-16，准备 owner）

- **LG-036 依赖校正（PM 决定）**：`depends_on` 由 `[LG-034, LG-035]` 改为 `[LG-033, LG-034]`；技术依据副本 [probes/lg036/DEPENDENCY-AUDIT.md](probes/lg036/DEPENDENCY-AUDIT.md)，PM 决定 `checkpoints/2026-10-15/pm-decision-lg036-20261016.txt`。引用已交付内容接口 `faf7230`/`d7e4391`+第三批集成提交；**不降 LG-035 验收、不改 LG-040 依赖、不声称图片/PDF 检索质量通过**。
- **LG-017 状态语义纠正（PM 决定）**：`in-progress` → `done`，标注“待 LG-022 集中 QA、非完整版本通过”；移除“须 LG-022 方可 done”的错误循环注释（LG-022 依赖 LG-017；集中 QA 非逐项前置）。**不改 LG-022 依赖**、不宣称版本验收。LG-035 质量门不动，LG-021 仍待增量复验。
- 据此 ready 候选：LG-036、LG-031；本批 CLI claim 与 worktree 准备详见 [probes/batch-20261016/PREPARE-4.md](probes/batch-20261016/PREPARE-4.md)。产品模型调用 0。

## 2026-10-16 第五批集成检查点（唯一集成 owner，持续执行中）

本节覆盖上文，为当前事实；旧实验、worktree、原始 probes 全部保留，未推送/部署/发布。
详细报告见 [probes/batch-20261016/INTEGRATION-5.md](probes/batch-20261016/INTEGRATION-5.md)。

- 集成前 main HEAD `cfbff64`（clean）；集成分支 `integrate/batch5`，`--no-ff` merge `dev/lg031` `d4c0815`（clean，base `e4cef4a`），无冲突；合并提交 `ee575c3`，main merge `af6640e`。
- **LG-031 安全合回 main**：保留 main 最新 021 `done`/036 机制/022 claim（`bf7851c`）；并入 `collaboration/execution_grant.py`、`coordinator/graph.py` fenced 领取/revoke、`adapter/**` execution_grant/custom_tools、`settings/**` 三开关、`api/{app,bootstrap}.py` `worker_identity`+`CollaborationService`。**默认关闭、可回退**；程序权限/状态/预算/验收权威；无常驻模型编排 agent。
- **共享 `api/app.py` 唯一 owner 交接**：031 owner 已释放并提交，本集成 owner 为唯一 writer，在**同一次提交**中一并加装 LG-036 `build_search_router()`（1 import + 1 `include_router`），两侧安全接线、无并发并写。
- **LG-036 `in-progress` → `done`（待版本 QA LG-040）**：真实默认 app 上 `GET /api/v1/search` → 200、空 FileStore 诚实 `index_unavailable`/`cache_missing`/`hits=[]`、`POST /search` → 405（GET 只读）、`GET /sources` → 200。**不降 LG-035 真实 OCR 门、不动 LG-040 门**。
- **LG-031 保持 `in-progress`（真实运行硬条件未满足，非错误等 032 版本门）**：031 的 1 次 DeepSeek 只是**独立 reviewer**，**不是 SDK 多 worker**；**真实 Git + 进程内 fake executor ≠ “真实 SDK 两 worker 发现/领取/交接/隔离执行”**。据此不置 done，理由是本项真实运行硬条件未满足（032 **反依赖** 031）。不把完整 checkpoint skip 未实现夸大，不扩大恢复重放。等价续接分支 `fix/lg031-r1` 已建（基于 `af6640e`，保留原 `dev/lg031`），本包未实施。
- **契约保持 `1.7.0`**（无新 schema 行为，不机械升版）；docs08 §4.3 `GET /search` 行同步为“已实现（集成挂载；待版本 QA LG-040）”、§5.1 注明 `source.indexed`/`source.invalidated` 已实际产生；docs06 §6.1 加第五批更新；PROJECT 加第五批决策。**037 向量与 038 UI 未实现如实标**。
- 集成分支候选检查（真实退出码）：`uv run mypy` **130 files clean**；`uv run pytest -q` **693 passed, 1 skipped**（75s）；定向 sources/api/contracts/collaboration/settings+review_closure **253 passed**。**本轮产品真实模型/外部服务调用 0**；前端未改、未重复无关 type/build。
- **backlog 专用根**：`validate` **OK 41 tasks, no diagnostics**；LG-036 done 后 `ready` = LG-037/LG-038/LG-041。CLI claim **LG-037 `agent:pi-lg037`、LG-038 `agent:pi-lg038`**（提交 `dda78f2`）；**LG-022 仍 in-progress，保留不重 claim**。
- 持久 worktree（项目旁，无 `.env` 复制、不覆盖已有）：`fix/lg031-r1` @ `af6640e`；`dev/lg037`/`dev/lg038` @ **同一 claim commit `dda78f2`**；`main` HEAD `af6640e`（clean）。
- **累计产品模型预算**：原任务 10、原包已用 1、**本包未新增、剩 9**（未重置旧尝试；031 的 1 次真实调用为其包内既有证据，未重放）。
- **已知风险（不宣称无害/无缺陷）**：`tests/collaboration/test_claims.py::test_two_owner_race...` 既有 discovery/lease 竞争偶发 `not_discoverable`；本轮全量单跑一次通过、单跑连跑 3 次通过，留 LG-032 固定判定口径。完整 checkpoint skip **仍未实现**；LG-037 向量/LG-038 UI 未实现；LG-035 质量门、LG-040 门未动；main 未推送。

## 2026-10-16 首版集中门失败后的返修检查点（主代理 PM）

本节覆盖旧检查点的最新事实，全部执行仍经 pi + 现有 DeepSeek；未推送/部署/发布，旧 worktree/实验记录均保留。

- main 已合入 LG-021 独立 31 条 + 增量 26 条证据，LG-021 done（仅前端门；headless focus-visible 仍明确未观测）。LG-036 已真实挂载 search，done 待 LG-040。此前 main e61ca70，后因收取 LG-022 失败证据前进到 ca27160（最新以 git 核实）。
- LG-022 独立候选 bf7851c 首轮 QA FAIL，证据提交 qa/lg022@8e81089，已合 main；见 probes/lg022/REPORT.md。D1：真实 coordinator event loop 中同步 reviewer 调用 asyncio.run 失败，无法进入待验收。D2：review 阻塞状态/控制请求且无真实停止生命周期。D3：成功 Run 仍有伪 fail_reason。全产品首版门未通过，不能以旧单点 reviewer passed 替代。
- 首轮真实生成请求总数 unknown：代理达到 429 后曾 rerun，未证明在 10 次全局上限内。失败尝试/原始记录保留，不按零计；下一复验必须先验证共享持久实际转发计数，不重置旧成本。
- LG-022 R1 正在持久 lg022-r1 / fix/lg022-r1 实施（产品模型预算 0），日志 lightgravity-pi-bounded-curntgtw.log，提示词 lg022-refix-r1-20261016.txt。独占 review/控制生命周期文件，后续必须另派独立复验。
- 为避免共享 runtime 双写，LG-031 R1（lg031-r1 / fix/lg031-r1）已由 R1 owner 精确 SIGINT 保全，原始日志 lightgravity-pi-bounded-26vw_kwk.log，stop reason signal_2、sideEffects unknown。原 dirty、试验/模型调用记录必须先核实，不盲目重放；待核心 reviewer 生命周期修复后等价续接。主线 LG-031 仍 in-progress；原 d4c0815 只真测 reviewer 1 次，并未真测多 worker。
- LG-037 已结束 dev/lg037@e713ea2：可选向量机制 39 检查通过，真实向量是替身；服务仍不可达，POST 0，Recall/排序未测，保持 in-progress，LG-040 不解锁。
- LG-038 已结束 dev/lg038@80cbef7：Chat/Files 接入、预览校订检索与浏览器局部检查通过，尚待串行整合；其“归档复用 revoke”存在语义缺口，下一集成包必须区分可逆归档与撤销，不能以撤销充当整理归档完成。真实 OCR/vector/ASR 质量未宣通过。
- LG-041 主代理已补 blocked_by 明确中文 ASR quality gate，防止因 LG-039 可行性报告 done 而错误 ready；不改变其 todo。该 PM dirty 与本节需由下一 pi 集成 owner 精确提交，禁止覆盖。
- 当前待续接：结束 R1 → 合并 R1/037/038 并修最小归档语义 → 新独立 lg022-qa-r1 复验 → 核 LG-031 原 dirty/调用/残留进程再续接真实 SDK 闭环。准备提示词均在 ~/.cache/lightgravity-bot/checkpoints/2026-10-15/，原始受保护日志在 dispatch-logs；候选 OCR 服务恢复/授权样本异步问题尚未收到答复，继续其他独立任务。
