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

## 2026-10-16 第六批集成检查点（唯一串行集成 owner）

本节覆盖旧检查点的最新事实；全部执行仍经 pi + 现有 DeepSeek，未推送/部署/发布。唯一集成 owner；主代理只 PM。产品真实模型/外部服务调用 **0**。

- **集成前核对**：LG-022 R1 返修 owner 已结束（无残留 pi 进程）；`fix/lg022-r1@d07a4a6` clean；`dev/lg037@e713ea2`、`dev/lg038@80cbef7` clean。主代理两项授权 PM dirty（`PROGRESS.md`、`LG-041.md`）已先精确提交 `098c7cc`。
- **整合候选 `integrate/batch6` @ `9698e8a`**（未推送）：`bed3d0c` 合 `fix/lg022-r1`（review 生命周期 D1/D2/D3 + 全局生成计数器）、`cf824be` 合 `dev/lg037`、`0313d04` 合 `dev/lg038`，全部 `--no-ff` 无冲突。旧分支/worktree/probes/dirty **全部保留**，未 reset/clean/覆盖/重复 pick。
- **向量挂载**：`api/app.py` 加 `build_vector_router`（`/vector/status`、`/vector/search`、`/vector/rebuild`），默认禁用、env 配置、候选回源核对；`/search` 未回退。
- **LG-038 归档语义修复（实质）**：原“归档复用 revoke”不能作为整理归档完成证据。新增**可逆归档**——`source.archived` 加性字段 + `archive`/`unarchive` 动作（+ 可选 `expected_revision`）；归档**保留**来源/权限/检索/打开，`revoke` 仍使资料不可用且原件保留。真实 HTTP 回归 3 项（归档后仍可查可开、revoke 失效且原件保留、幂等/版本冲突）+ 前端 2 项冒烟（Archive 绝不调 revoke）。tags 未冻结→明确不实现，不挡本项。038 保持 done 待 LG-040，注释如实更新。
- **契约 `1.8.0 → 1.9.0`**（加性 MINOR，真实变更控制，保留 1.8/1.7/1.6 历史链）：docs08 §4.3/§6.6/§13 + README/agent/docs06/PROJECT 一致。
- **集成检查（绑定 `9698e8a`）**：`uv run pytest -q` **754 passed, 2 skipped**；`uv run mypy` **136 files clean**；定向 sources/api/contracts **179 passed, 1 skipped**；前端 `tsc` 0 错、`vitest` **98 passed**、`npm run build` 成功。真实产品调用 0（已有结果只引用不重跑）。
- **独立 QA 准备**：新分支 `qa/lg022-r1`（基于 `9698e8a`）+ 脚手架 `probes/lg022/reverify-r1/`；**本包未执行 QA**、未发真实请求；LG-022 原 claim 保持 in-progress；新 phase 预算 10，须先证明共享 forward 计数器。
- **LG-031 续接准备**：新分支 `fix/lg031-r2`（基于 `9698e8a`）已把原 `fix/lg031-r1` 的 tracked 改动 + `probes/lg031/R1_*` untracked 证据**精确 WIP commit**（不 `add -A`）；原 `fix/lg031-r1` dirty 原样留存。**真实产品调用以 `probes/lg031/r1_worker_claim_probe.json` 为准**：R1 = 2 worker + 1 reviewer = **3**；原包 1；**累计 4/10，剩 ≤ 6**（交接日志的 turn_end 114/响应 224 是开发 pi 事件，不算产品请求）。未闭合项：autonomous-claim 定向测试在整合候选与原 base **均失败**（`plan_validation failed: config_invalid`，非整合回归），交下一 owner。
- **状态如实**：LG-022 in-progress（待独立复验）；LG-017 done 待 022、不制造循环；LG-037/035 不假 done；LG-038 done 待 040；LG-040 不解锁；LG-041 quality gate 不解锁。未领取 023/024/032/040。
- 本包结束先写持久 REPORT（本文件 + `probes/batch-20261016/INTEGRATION-6.md`），再精确本地 commit；main 未推送。

## 2026-10-16 第七批集成检查点（唯一串行集成 owner，持续执行中）

本节覆盖上文，为当前事实；旧实验、worktree、原始 probes 全部保留，未推送/部署/发布。唯一集成 owner；主代理只 PM。
详细报告见 [probes/batch-20261016/INTEGRATION-7.md](probes/batch-20261016/INTEGRATION-7.md)。

- **集成前核对**：`main` HEAD `29ffbb6`（clean，主代理本轮无 PM dirty）；无残留执行者占用源 worktree。
  `fix/lg022-r2@e59e12a` clean、`fix/lg031-r2@3821620` clean；`main` 与其先前合并关系已核（两分支均自 `29ffbb6`）。
- **整合候选 `integrate/batch7`**（自 `29ffbb6`）：`8a92439` `--no-ff` 合 `fix/lg022-r2`（无冲突，停止门真实停止事实 + `reviewer_cleanup` +
  持久生成账本，契约 **1.10.0** + QA reverify R1 证据）；`0144eb7` `--no-ff` 合 `fix/lg031-r2`（**2 处文本冲突**，见下）。旧分支/worktree/probes/dirty 全部保留，
  未 reset/clean/覆盖/重复 pick，未复制 `.env`。
- **冲突处理（唯一 owner）**：① `adapter/__init__.py` 同时保留 022 `configure_generation_ledger` 与 031 `global_generation_counter` 导出，
  去掉重复 `GenerationCounter`；② `docs/08` §9 保留 **1.10 持久账本为唯一生成限额事实源**，把 031 说明改写为「执行器共享计数接线（1.10.0，无版本/字段/端点变化）」，
  **契约保持 `1.10.0`**（031 未新增版本，不机械升版）。
- **共享装配兼容（关键）**：`api/bootstrap.py` 中 `configure_generation_ledger(settings.data_dir)`（022）先于 `generation_budget=global_generation_counter()`（031）执行，
  031 注入的是**已被换成持久账本**的全局计数，**不被 031 旧内存计数覆盖**。进程内冒烟（本地替身、无真实模型）：
  `snapshot={'count':0,'limit':7,'remaining':7,'corrupt':False,'persistent':True}`、`reserve→True`、count=1、`<data_dir>/generation/` 账本文件真实创建。
- **LG-031 实际修复保留**：`coordinator/graph.py` 自主路径 claim 检查移到**执行后、revoke 前**，程序只授权被排度节点（`node_not_scheduled_for_worker`），
  `_mint_pool_grant`/`_claim_for_worker`/`_claim_tools_for` 完整并入；此前在整合候选与原 base 均失败的
  `test_autonomous_worker_tool_claim_grants_node` **现通过**（本包实跑 1 passed）。**未读旧 dirty `fix/lg031-r1` 覆盖当前**，原 dirty 原样留存。
- **集成检查（真实退出码，绑定 `0144eb7`）**：`uv run mypy` exit 0 → **137 files clean**；`uv run python -m pytest -q` exit 0 → **775 passed, 2 skipped**（79.7s）；
  定向 adapter/verify/coordinator/contracts/collaboration **274 passed**。**本包产品真实模型/外部服务调用 0**；**UI 未改**，未重复整套前端。
- **持久 QA/续接 worktree（全新，基于 `0144eb7`）**：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`）、
  `/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`（branch `fix/lg031-r3`）。**未执行 QA/真模型**；旧 worktree 全部保留。
- **成本与历史账本（准确，不重置/不洗白）**：**LG-031 累计 10/10**（原 1 + R1 3 + R2 6），主代理新 phase3 另行授权**最多 14**，合计**上限 24**，
  **且不是 032 对照实验**；**LG-022 首轮 QA 实际总数 unknown**、R1 新阶段 **6/10**，**两轮失败记录都保留**（`probes/lg022/REPORT.md`、`probes/lg022/reverify-r1/REPORT.md`）。
  旧 031 交接日志 `turn_end=114`/响应 224 是开发 pi 事件，不计产品请求。**本包实际产品请求 0**。
- **状态如实**：**LG-022 仍 in-progress 待独立 QA（`qa/lg022-r2`）**；**LG-031 仍 in-progress**（真 2 worker + 交接 + 候选 review 仍缺，续接 `fix/lg031-r3`）；
  **LG-035/037 in-progress**（质量门/端点不可达，不假 done）；**LG-023/032 todo 未 claim**（不 claim 依赖未过）；
  **LG-040 不解锁**；**LG-041 质量门阻塞不解锁**。
- backlog 专用根：`validate` **41 tasks, no diagnostics**；`digest` complete=true → **32 done / 4 in-progress / 5 todo**。
- 未完成质量门：LG-022 独立 R2 复验、LG-031 真闭环（新预算内）、LG-035/037 真实质量、LG-040 版本 QA、完整 checkpoint skip。`main` 未推送。

## 2026-10-16 持久检查点：core R2 补证与 LG-031 phase4

- 主工作区 `integrate/batch7@85adc82`，`main@29ffbb6` 尚未快进收拢；产品候选 `0144eb7`，契约 **1.10.0**。串行整合检查：775 passed / 2 skipped，mypy 137 files clean，见 `probes/batch-20261016/INTEGRATION-7.md`。旧 dirty/worktree/原始实验均保留。
- 独立 core QA `qa/lg022-r2@0a88ab8` 的真实主链已到 `awaiting_acceptance` 并绑定 accept，实际生成 **8**（主链7+直答1）。**补查已更正原“8/10统一硬限”表述：两阶段使用不同账本，实际8可核实但未执行统一总额硬限；不是产品持久账本缺陷。** 原首轮 unknown、R1 6 均保留。见 `qa/lg022-r2/{REPORT,SUPPLEMENT,STATUS}.md`。真实 SDK 活跃复核的 cancel/stop 直接补证尚未跑成，LG-022 **暂不 done**，不以原 PASS 标题覆盖后续补遗。
- 首个 SDK cancel 补证开发包 bounded-uuv5ekyo 到 wall600/exit143；后续只读收尾已保全临时探针与清理签名进程。无新增 DeepSeek 生成，未知副作用不重放。已另拆零真实模型调用调查包，查 SDK 官方安装 API 与本地流式替身协议，避免反复100秒超时试错；报告落于独立 QA worktree 的 `qa/lg022-r2/sdk-cancel-investigation/`。
- LG-031 phase3 交付 `fix/lg031-r3@faacb90`：G1 bootstrap 开关接线、G2 discovery 目标/写范围投影已修；真实 **14/14** 耗尽，仍缺完整双worker交接/整合候选 review，故 in-progress。原累计10+14=**24**，全部 partial/失败成本保留。见该分支 `probes/lg031/phase3/{REPORT,LEDGER}.md`。
- 同一隔离分支已续接 phase4：先零模型离线定位，再一个固定 fixture 的真实闭环；新增最多 **16** 次全role/stage共享持久扣减，已知工程累计上限40。不是 LG-032 对照实验，不改未来样本/收益门，不开默认自主模式。此时 owner 正执行，不能提前 merge 其未完工作。
- LG-023 尚未启动/claim；预注册拟2样本×2arm×1repeat=4 attempts，PM在执行前确定总24次、每attempt最多6、单一持久账本，计入执行/QA/返修/复验/失败。等待022补证裁定后由串行集成者收拢并原子claim。LG-024、032同样按实际依赖推进。
- 资料候选服务本轮只读复查 `/health`、`/v1/models` 均连接失败，POST0；035/037质量仍阻塞，040未解锁，041仍受039负结果质量门限制。私有证据 `/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/MATERIALS-RECHECK.md`。普通实现不需用户确认；真正外部待项为服务恢复/另授权端点及可用真实中文/表格truth样本。
- 续接：先核当前两个 pi owner 是否退出及准确HEAD/REPORT，再按补证真实判定处理022；勿重跑未知写入或覆盖旧worktree。未来所有生成阶段共用同一phase data_dir/ledger，不得分账后声称统一硬限。所有开发执行仍仅pi+env DeepSeek，主代理只PM；未推送/部署/发布。

## 2026-10-16 LG-031 phase3 工程验证检查点（owner `agent:pi-lg031-r3`，partial）

本节覆盖 LG-031 相关上文；全部经 pi + 现有 DeepSeek，未推送/部署/发布；主代理只 PM，无嵌套派工。详细报告 [probes/lg031/phase3/REPORT.md](probes/lg031/phase3/REPORT.md)。

- **基点/保护**：worktree `lg031-r3`（branch `fix/lg031-r3`）@ 整合候选 `0144eb7`（契约 `1.10.0`），开工 `git status` clean。旧全部 worktree/分支/实验/失败证据/`fix/lg031-r1` 原 dirty **未触碰**，未 reset/clean/覆盖/删 worktree；主 worktree 2026-10-15 的 uvicorn（端口 8123，**非本包**）未 kill/接线/复用 dataRoot。
- **真实调用（不重置、不猜）**：旧累计 **10/10**（原 1 + R1 3 + R2 6，保留为失败/partial 成本）；本 phase3 PM 另批 **≤14**，实际 **14/14 用尽**（运行 1/2/3 = 4/5/5）；**旧 10 + 新 14 = 24**（全局已知 ≤24）。单一事实源：`probes/lg031/phase3/ledger/generation/`（持久账本，`count=14,limit=14,remaining=0,corrupt=false,persistent=true`）。**转发前已验证跨进程/重启**：进程1 预留 5 → 新进程再成功 9（合计14）→ 第三进程读到 14（不归零）→ 损坏 `raise`（**绝不当 0**）。SDK/API retry 0；单 HTTP ≤120s；并发 ≤2；输出 ≤12000 tokens；usage 未知记 unknown。
- **发现并修复两个真实缺陷（离线先证，均在产品路径）**：**G1** `api/bootstrap.py` 默认 `GraphDispatcher` 未接 `autonomous_claim`/`grant_registry` 且不读开关 ⇒ 产品路径无法启用自主 claim 工具（R2 探针因此绕过产品协调器）；修复为开关开启才启用 + 进程内 `ExecutionGrantRegistry`，关闭/缺省走旧确定性路径。**G2** `collaboration/execution_grant.py` 受限 claim 工具发现投影缺程序拥有的 `objective`/`write`（经产品 planner `key` 必须是 slug，worker 学不到产物）；加性补齐。测试：`tests/startup/test_lg031_r3_bootstrap_autonomous.py`（2）、`tests/collaboration/test_lg031_r3_product_path_closure.py`（1，离线证明产品路径 2-worker 闭环：独立 worktree、原子授权 fence=1、脱敏 receipt、带 hash 交接）。
- **真实链结果（partial）**：产品 `GraphDispatcher._claim_for_worker` 路由下，真实 worker **自主**调用 `discover_and_request_claim()`→`discover_and_request_claim(node_ref)`（硬条件 2 真实成立）；reviewer 真实调用 3 次均因候选不完整**诚实 `unavailable`**（未降级门）。**硬条件 4/5 未闭合**（integrate worker 未跑完、无带 hash 交接、无完整候选 review passed），根因 14 用尽 + worker 回合效率。**未写 done、未伪造、未偷偷归零。**
- **检查（真实退出码）**：`uv run mypy` **137 files clean**；`uv run pytest -q -p no:randomly` **775 passed, 5 skipped**；定向 **249 passed**。与 INTEGRATION-7 基点（775/2）一致，多出的 skip 为条件门。
- **契约/文档**：G1/G2 为实现接线与内部 SDK 工具投影，**无 HTTP 契约字段/端点/枚举/版本变化**，docs/08 §9 加性实现说明，**契约保持 `1.10.0`（不机械升版）**。1.9 归档/向量/检索/UI/token/pin/证据/反重放语义未回退。
- **状态如实**：**LG-031 保持 `in-progress`（partial）**——真实门未齐；031 不因“032 未跑”循环，也不宣称 done。**不替 LG-032 预注册样本/预算/成功标准，不预设节省。**
- **剩余门**：integrate worker 自主 claim+写、带 hash 交接、完整候选独立 reviewer `passed`；完整 checkpoint skip 仍未实现。下次真实 phase（若另批）可用修正 prompt（worker 据 objective 判产物）+ G1/G2 修复直接闭合，无需改门/降级。`main` 未推送。

## 2026-10-16 LG-031 phase4 工程验证检查点（owner `agent:pi-lg031-r3`，核心通过 / 交接原文缺 ⇒ partial）

本节覆盖 LG-031 相关上文；全部经 pi + 现有 DeepSeek，未推送/部署/发布；主代理只 PM，无嵌套派工。详细报告 [probes/lg031/phase4/REPORT.md](probes/lg031/phase4/REPORT.md)。

- **基点/保护**：worktree `lg031-r3`（branch `fix/lg031-r3`）@ phase3 检查点 `faacb90`，开工 `git status` clean。旧全部 worktree/分支/实验/失败证据/`probes/lg031/{R1,R2,phase3}` **未触碰**，未 reset/clean/覆盖/删 worktree；主 worktree 的 uvicorn（端口 **8123**，**非本 worktree、非本包**）未 kill/接线/复用 dataRoot。
- **§A 零模型定位 phase3 失败点**：SDK `BudgetConfig.max_model_calls` 与 loopback proxy `max_proxy_calls` 是**两个独立上限**；proxy 先 429 时**掩盖** SDK 真实停止原因（`MAX_MODEL_CALLS_EXCEEDED`），多步 worker 在写入前被杀，dependent worker 从未调度（run1=`MAX_MODEL_CALLS`、run2/3=proxy `429`；证据 `probes/lg031/phase3/evidence/`）。
- **加性最小修复**：`adapter/executor.py::execute` 把 per-session proxy 上限对齐到 coordinator 冻结的 `request.budget.max_model_calls`（`min(max_proxy_calls, remaining, request_model_calls)`）；未设 model budget 时行为不变。测试 `tests/adapter/test_lg031_r3_generation_ceiling_alignment.py`（5）。**未平台化**，无契约字段/端点/版本变化。
- **离线硬门全绿**（零模型/零网络，证据 `probes/lg031/phase4/OFFLINE-GATES.md`）：持久账本跨进程/重启**不归零**、损坏 `corrupt=true` 且**拒绝转发**（绝不当 0）；两 worker 权限（body 永不认证）；objective 投影（G2 回归）；依赖带 hash 交接；真实 bootstrap & Graph 配置（G1 回归）；**真实 `RuleBasedPlanner`（不注入）** 产品路径闭环 `tests/collaboration/test_lg031_r4_real_planner_closure.py`。
- **真实调用（不重置、不猜）**：旧累计 **24**（原 1 + R1 3 + R2 6 + phase3 14，保留）；本 phase4 PM 另批 **≤16**，**一次**真实 attempt 用 **10**（worker ≈9 + reviewer 1），剩 6；**全局已知累计 = 34/40**。单一事实源 `probes/lg031/phase4/ledger/generation/`（`count=10,limit=16,remaining=6,corrupt=false,persistent=true`）。SDK/API retry 0；单 HTTP ≤120s；并发 1；输出 ≤12000；usage 未知记 unknown（不当 0）。
- **真实闭环结果**：真实产品 `RuleBasedPlanner` → `deliver`(write) → `verify`(依赖)；2 个真实 SDK worker 各自自主 `discover_and_request_claim`（4 条工具调用，产品 router `GraphDispatcher._claim_for_worker`）；程序原子授权 fence=1、脱敏；dispatcher **succeeded**；真实独立 ModelReviewer + 机器门 **`passed`/`validated=passed`**，候选完整可复源（`out/deliver.txt` + diff `@sha256:820a…`）；耗时 25.07s。G1/G2 修复在真实产品路径下生效。
- **未闭合（诚实，不伪称）**：**硬条件 4「带 hash 同伴交接」的真实原文未捕获**——探针从 `subtasks/*.md` 提取，实体实际在 `subtasks/<id>/SUBTASK.md`，故 `handoff_refs=[]`。产品侧交接**已发生**（verify 节点仅在 deliver 通过后才被领取并执行；deliver 产物在 reviewer 证据中可见），离线已证机制（`<subtask>@<64hex>:out/deliver.txt`）。一次完整复验需 ≈10 转发，本包剩 6，**不重跑同一 fixture**；探针提取 bug 已修复，留后续 phase 的**唯一**一次复验。**未降低任何复核/机器门/停止/验收门。**
- **检查（真实退出码）**：`uv run mypy` **137 files clean**；`tests/adapter` **102**、`tests/collaboration` **77**、`tests/coordinator`（+collab）**187**、`tests/verify`+`tests/api`（+adapter）**233**、`tests/startup` **39 (+4 skip)**、`tests/settings` **46** 全通过；`py_compile` 探针 OK。
- **状态如实**：**LG-031 保持 `in-progress`（partial）**——真实 loop 已闭合，但硬条件 4 真实原文证据缺失；不写 done、未偷偷归零、未重跑探过。**不替 LG-032 预注册样本/预算/成功标准，不预设节省。** `main` 未推送。

## 2026-10-16 LG-031 phase4 同次运行证据恢复检查点（owner `agent:pi-lg031-r3`，硬条件 4 闭合 ⇒ done 待 032）

本节覆盖 LG-031 phase4 相关上文；经 pi + 现有 DeepSeek，未推送/部署/发布；主代理只 PM，无嵌套派工。详细报告 [probes/lg031/phase4/SALVAGE-REPORT.md](probes/lg031/phase4/SALVAGE-REPORT.md)、[SALVAGE-STATUS.md](probes/lg031/phase4/SALVAGE-STATUS.md)。

- **前 owner 停止核实**：前 spwchdnn 于 `maxround 65` 停止、进程 `exit 143`；**现无残留进程**（仅内核线程）；HEAD `8073830` clean（仅 2 个未跟踪恢复文件）；未 reset/clean/覆盖旧记录。
- **恢复路径（只读、零模型）**：同次运行 `run_01M5079F4W8V37RHRTN7W6WWV6` 的 `data/store/worktrees` 已被探针 `TemporaryDirectory` 删除，但**3 个 SDK session DB 与原 stdout 存活**（`sha256` 逐一核对，与恢复 JSON 一致）；用 `sqlite3 mode=ro` 提取，**未写回原 store、未补字段、未编造收据**。
- **硬条件 4 真实原文已复原**（产品构建 verify 节点 prompt 的 `Upstream artifacts:` 块）：`subtask_01M5079F7MS9XM6AJRDJD4D7HM@1a6053…a64d:out/deliver.txt` 与带独立 `@sha256:820a554a…` 的 diff 证据引用；diff patch 正文重取重算 **match=true**（69B）。
- **授权**：源/目标节点 `reason=granted, fence=1`、程序原子授权、脱敏（`sandbox_set_has_secret=false`）；reviewer 真实 1 次 `outcome=passed`/`validated=passed`、usage `unknown`。
- **契约判定（docs08 §6.3）**：依赖放行须传递上游产物引用与**版本/哈希**；workspace 相对产物**不要求**自身带 `@sha256:`（仅 executor evidence 属 `…@sha256:` 命名空间）。**硬条件 1–7 真实成立**。残余仅 `content_hash` 原始字节随临时目录删除（已记录事实，非伪造）。
- **计数**：本恢复真实调用 **0**；全局已知累计仍 **34/40**（旧 24 + phase4 10，不重放、不归零）；usage `unknown` 不当 0。
- **状态**：**LG-031 更新为 `done`**（硬条件 1–7 真实成立）；版本级行为由 **LG-032 独立集中 QA 复验**，不制造待 032 循环。未降低任何复核/机器门/停止/验收门；未改契约、未删断言。`main` 未推送。

## 2026-10-16 第八批串行集成检查点（唯一集成 owner，`main` 已本地收拢）

本节为当前事实；旧实验、worktree、原始 probes、旧 dirty 全部保留，未推送/部署/发布。唯一集成 owner；主代理只 PM。详细报告 [probes/batch-20261016/INTEGRATION-8.md](probes/batch-20261016/INTEGRATION-8.md)。

- **集成前核对（真实）**：`integrate/batch7@85adc82` + 主代理 PM dirty `PROGRESS.md`（已独立只读保全至私有 checkpoint，`sha256=73e4fe9e…bf94`，再精确提交 `cef379a`）；`main@29ffbb6` 未收拢；`fix/lg022-stream@1dd5c67`（**已精确暂存 8 项**，未 commit）；`fix/lg031-r3@2f04654`（clean）。**无源 owner 残留进程**（仅本集成 owner 的 bounded pi 包装）。未 reset/clean/重复 pick、未复制 `.env`。
- **合入 022 流式停止接线**：唯一收尾 commit `7d0510d`（8 文件，仅源 owner 暂存集合），`git merge --no-ff` → `eecbf05`（**无冲突**）。产品修复仅 `verify/review.py`：真正流式阶段承载 stop（不取消 pull + 有界重查，不丢/不重 chunk）+ 停止调 `Conversation.cancel()`/有界 `wait_for_idle()`（仅 SDK 确认 idle 才为真）+ enter/chat/stream/stop/teardown 同 loop（消除已关闭 loop 偶发 `RuntimeError`）。真 SDK+本地 fake SSE：stop **0.132s confirmed**（修复前 5.027s unconfirmed）、`session_refs` 保留、无残留 reviewer。
- **合入 031 r3 闭环**：产品加性——`adapter/executor.py` proxy 上限对齐冻结 `budget.max_model_calls`；`api/bootstrap.py` G1 开关接线自主 claim + `ExecutionGrantRegistry`（缺省确定性路径）；`collaboration/execution_grant.py` G2 投影加性补 `objective`/`write`。`PROGRESS.md` 唯一内容冲突**同时保留双方**（root 最新状态 + r3 phase3/phase4/SALVAGE 检查点）。`git merge --no-ff` → **`975afc2`**。
- **幸存原件私有保全已复核**：3 个 SDK session DB + 原 stdout 复制到 `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`（`700`/`600`），4 个 `sha256` 与 `MANIFEST`/`salvaged_handoff_evidence.json` 逐一相符且与 `/tmp` 原件 `cmp` 字节相等；原件未动，未重复制/删除/运行模型，秘密原件不入 repo。
- **`main` 本地收拢**：`git checkout main && git merge --ff-only integrate/batch7` → **`main@975afc2`**（**未推送**）。不止停在 integrate 分支。
- **集成检查（真实退出码，绑定 `975afc2`）**：`mypy` exit 0 → **137 files clean**；`pytest -q -p no:randomly` exit 0 → **794 passed, 2 skipped**（82.49s）；backlog 根 `validate` ok **41 tasks/0 diagnostics**、`digest` complete → **33 done / 3 in-progress / 5 todo**。**本包产品真实模型/外部服务调用 0**；UI 未改，未重跑完整前端。
- **状态如实**：**LG-022 仍 `in-progress`** 待**新独立 QA `qa/lg022-stream`**（新持久 worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream`，基于最终 main 候选 `975afc2`，**不覆盖旧路径**）；**最新 `cea87ab` 独立调查确认重要缺陷是 stream 阶段没 cancel/deadlock（流式 stop 未接线，不是单纯限制）**，旧 a41 PASS 标题不覆盖新修复。**LG-031 `done`（待 LG-032 独立集中 QA）**。**LG-023/032 `todo` 未 claim**（依赖 022 未 done，保留后续步骤）。**LG-035/037 `in-progress`**；**LG-040/041 不解锁**。自主模式默认 off；不重新引入模型编排。
- **成本（全部旧失败保留）**：LG-022 首轮 unknown、R1 6/10、`qa/lg022-r2` 真实 8（**两阶段不同账本，未执行统一总额硬限**，非产品账本缺陷）；LG-031 累计 **34/40**（旧 24 + phase4 10，不重放/不归零）。**本包产品真实请求 0**。**契约保持 `1.10.0`，SDK `0.1.22` 不变。**

## 2026-10-16 核心首版 QA 收口检查点（唯一串行验收证据整合/排期 owner）

本节为当前事实；旧实验、worktree、原始 probes、旧 dirty 全部保留，未推送/部署/发布。唯一收口 owner；主代理只 PM，无嵌套派工。
详细报告见 [probes/batch-20261016/CORE-QA-CLOSE.md](probes/batch-20261016/CORE-QA-CLOSE.md)。**本包产品生成 0**（不执行评估/新探针/不重跑模型或测试）。

- **开工核对（真实）**：`main@e0a8cec` clean；`qa/lg022-stream@49c95f5` clean、**仅 14 个 QA 文件**（纯 `qa/lg022-stream/**`，产品/ docs 零改动）；`fix/lg031-r3@2f04654` 已由 INTEGRATION-8 合入 main。`ps` 仅见本收口 owner 的 bounded pi；**无 022-stream QA owner/源 owner 残留**。旧 `lg031-r1` dirty=8、`/tmp/*experiment*` dirty 全部保留未触碰；未 reset/clean/覆盖/重复 pick、未复制 `.env`；主 worktree uvicorn(:8123) 未 kill/未复用 dataRoot。
- **独立 QA 退出与结论**：`agent:pi-lg022-stream-qa` 已退出。证据复核（只读不重跑）：`stream-stop-hard-gate.json` **`hard_gate_pass=true`**（真 SDK 0.1.22 + 真产品装配 + 本地 fake SSE；流式 pause/cancel 0.21s/0.22s 真实 confirm；unknown held）；`main-chain-verdict.json` **`ok=true`**（真 DeepSeek 5/10 主链到绑定 accept）。**结论：门内 PASS、无未修重要缺陷**（无 fail ⇒ 可 claim 023）。
- **merge（仅 QA 证据）**：`git merge --ff-only qa/lg022-stream` → **`main@49c95f5`**（`e0a8cec..49c95f5`，14 文件）。**产品树证明**：`git diff e0a8cec main -- backend/ frontend/ src/ tests/ docs/ pyproject.toml` **为空** ⇒ 产品树与已验候选逐字节相同，故**不重跑全量 pytest**（无新代码）。未推送。
- **LG-022 → `done`**（仅「首版端到端 + 本次流式停止缺陷独立真实复验」**门内范围**，**不宣称整产品 pass**）。旧错误 PASS 标题仅覆盖持久账本+停止门主链、不覆盖本次流式修复；历史两轮失败（首轮 fail、R1 FAIL、R2 scope 修正）如实保留。
- **准确门范围/未测保留**：真 SDK+本地 fake SSE 的流式停止 PASS；真 DeepSeek 主链一例 PASS；**未测：真实 DeepSeek 上游下 cancel/pause-during-review、重启后 `verifying`/`repairing → recovery_required`、跨 Run 真实 reject/repair、light/浏览器矩阵（引用 021/027 旧证据）**；**provider-substitute**：流式硬门上游为本地 fake SSE（非 DeepSeek），**SDK 取消已用真 SDK+本地 SSE 证明，不冒充 DeepSeek 故障**。
- **022 成本（旧 unknown+6+8 与新 phase 分别记录）**：首轮 real **unknown**（含 429 rerun）；R1 **6**；R2 **8**（主链 7 + light 1，**两账本未统一、未执行统一总额硬限**，非产品账本缺陷）；**本 phase 5/10**（唯一持久 ledger）；本收口包 **0**。旧轮不归零/不洗白。
- **031 已知工程 34/40**（旧 24 + phase4 10，不重放/不归零）；**原运行 SoT 部分字节丢失**（探针 `TemporaryDirectory` 删 `data/store/worktrees`），但 **SDK 原件（3 session DB + 原 stdout）持久备份**于 `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`（`700`/`600`），**硬条件 4 由只读哈希恢复**；恢复限制（未写回原 store/未补字段/未编造收据）如实保留。031 保持 `done`。
- **源提交短哈希核准**：流式修复源为 **`7d0510d`**（`git show` 核准）；QA 报告叙事一处 `7d0510c` 为**笔误**，仓库内**不存在** `7d0510c` 提交（tracked 文件亦无该字符串）。本汇总按 git 引用正确哈希并**补注**，**不篡改原 QA 测试证据**。
- **LG-023 排期（原子 claim + 新 worktree）**：`validate`→**41 tasks/0 diagnostics**、`digest` **complete=true**、LG-023 `ready` 后，**CLI 原子 claim `LG-023 --as agent:pi-lg023`**（不直接绕 claim）；创建**全新持久 worktree** `/home/yhvh/code/lightgravity-bot-worktrees/lg023`（branch `dev/lg023`），基于最终 main/claim commit；路径若存在**先核不覆盖**。**本包不执行评估**。
- **预算（采样前最终修订，非看结果后改额；样本/门固定 2 任务 × 2 arm × 一次）**：**4 attempts / 总 48 真实 DeepSeek 生成 / 每 attempt 12**；**全 stage 同 phase 持久 ledger**；**output ≤ 16000 / HTTP 120s / retry 0 / 并发 ≤ 2**；**旧 16/24/6 只是未执行草稿、作废**（不构成额度）；按已见真实双 worker 链约 **10 calls**，为**双方 arm 设同样足够 cap**。
- **LG-032 暂不 claim**（原 ready ≠ 立刻占有；待 023 评估后与 **LG-024** 并行排期）。
- **状态如实**：**LG-022 `done`（门内）**；**LG-031 `done`（待 032）**；**LG-023 claim 后 `in-progress`**；**LG-032 `todo` 暂不 claim**；**LG-035/037 `in-progress`**、**LG-036/038 `done` 待 040**、**LG-040/041 `todo` 不解锁**。自主模式默认 off。**契约保持 `1.10.0`、SDK `0.1.22` 不变**。本包产品生成 **0**，未推送/部署/发布。

## 2026-10-16 LG-032 排期检查点（主代理 PM，claim + worktree 准备；产品真实生成 0）

本节为当前事实，覆盖上文 LG-032 相关表述；旧实验、worktree、原始 probes、旧 dirty 全部保留，
未 reset/clean/覆盖/重复 pick，未推送/部署/发布。主代理只 PM，无嵌套派工；执行经 pi + 现有 DeepSeek。

- **开工核对（真实）**：`main@03c7db6` **clean**；`dev/lg023@fa9401d` 与 `fix/lg023-method@fa9401d` 均 clean
  （LG-023 方法审计独立 worktree，本包 **未触碰**）；backlog 专用根 `validate` **OK 41 tasks/no diagnostics**、
  `digest` complete=true、`ready` = **LG-032**。`/home/yhvh/code/lightgravity-bot-worktrees/lg032` **不存在**（先核后建，不覆盖）。
- **依赖判定（不机械等 023）**：LG-032 `depends_on: [LG-031, LG-022]` **均已 `done`**（022 门内 done、031 done 待 032）。
  LG-032 **不依赖 LG-023**；023 与 032 是**不同评估**，032 不重用 023 的对照数据（023 是单 agent vs 组队实施 worker 开发对照；
  032 是去中心化**版本 QA + 程序调度基线 vs 新协作路径**的全生命周期成本对比）。**不把 LG-023 当 032 前置**。
  LG-024 `depends_on: [LG-022, LG-023]` 仍 **todo**，因 023 未完成评估而等待；024 与本包无关。
- **LG-023 状态如实**：保持 **`in-progress`**。首 cohort `45/48` 真实生成后发生**预算冻结**；已确认
  「**提示/工具在 bring-up 中被变更**（worker 提示修正 + 加 `edit-file`）」「**样本结果被新 attempt 覆盖**（1# 结果被 4# 覆盖）」
  与「**版本验收 stopgate 未闭合**（`cleanup='pending'`，两 arm 共有）」三项，组队 arm 与 S2 未在最终 harness 下取得可比结果。
  **新方法审计只做 0 真实生成**，**不合并未经完成的 `fa9401d` 评估记录、不解锁 024**。
- **LG-032 排期（本次，先 QA 阶段 A，不提前跑成本样本）**：
  1. **阶段 A：独立机制/语义质量 QA（产品真实生成 0）**——由独立于实施者的 pi 复核去中心化版本候选
     的**机制与语义**：竞争领取/原子授权与 fence、过期租约、崩溃恢复、取消、权限/身份、带 hash 交接、
     有界返修与复验、默认关闭回退、事件可重放/重启不重复副作用。**只读/离线/替身证据，不运行产品生成样本**，
     不预注册成本样本、不预设节省。**失败须修复后复验**（另派；QA 不自修、不自判 done）。
  2. **阶段 B：全生命周期成本对照（另行冻结，且必须先验证实验 harness）**——仅在阶段 A 机制/语义无阻断后，
     由 PM **另行冻结**固定样本/次数/费用上限与成功门，并**先验证实验 harness**（起点/任务/模型/预算/验收门/重复策略一致，
     单一持久 ledger 全 stage 共用、跨重启不归零、损坏绝不当 0、转发前预留、usage 未知记 unknown）。
     比较**程序调度基线 vs 新协作路径**，逐样本成功率/耗时/执行+QA+返修+复验+失败尝试 token 与人工介入；
     **未完成样本不计已交付成本**；**旧 LG-023 混淆数据（提示/工具变更 + 结果覆盖）不能代替 032 对照**。
     只有质量不退化且结果支持收益才建议默认启用，否则保留可选开关/回退并记录结论。
- **预算（本轮 claim/prep 阶段记录，非采样；采样前最终值须在各自阶段另行冻结）**：阶段 A 产品真实生成 **0**；
  阶段 B 的 **wall 400s / maxround 100 / noncache 100k / idle 120s / retry 0** 为本轮派工/运行上限草案，
  **样本与费用上限仍须阶段 B 另行冻结**，不预先宣称节省、不据 023 结果改额。
- **契约/SDK/默认不变**：契约 **`1.10.0`**、SDK **`google-antigravity==0.1.22`**、**自主模式默认 off** 不动；
  不扩状态、不跑产品代码/测试（本 PM 包仅 `tasks`/git relation/PM 文档）。
- **claim/worktree（本次，原子）**：backlog 根 `validate`/`digest`/`ready` 确认 complete 无诊断后，
  CLI **原子 claim `LG-032 --as agent:pi-lg032`**；创建**全新持久 worktree**
  `/home/yhvh/code/lightgravity-bot-worktrees/lg032`（branch **`qa/lg032`**），基于最终 main/claim commit。
  精确本地提交 PM/claim。**本包不运行产品代码/测试，不执行 QA，不跑真实模型。**
- **状态如实**：**LG-032 `todo → in-progress`（claim 后）**；**LG-031 `done`（待 032）**；**LG-022 `done`（门内）**；
  **LG-023 `in-progress`（partial，新方法审计 0 真实生成、不解锁 024）**；**LG-024 `todo`**；**LG-035/037 `in-progress`**、
  **LG-036/038 `done` 待 040**、**LG-040/041 `todo` 不解锁**。本包产品生成 **0**，未推送/部署/发布。
  handoff 报告落 `probes/batch-20261016/LG032-QUALITY-HANDOFF.md` 后精准 commit。

## 2026-10-16 检查点：首版核心门闭合，023 方法返修 / 032 独立机制门并行

- `main@62e96ed`（本段为主代理 PM 新增 dirty，续接集成须保留）；产品树仍 `e0a8cec` / 契约1.10.0 / SDK0.1.22，自主模式默认off。LG022已据独立 `qa/lg022-stream@49c95f5` 正式门内证据done：真实主链5/10单账本到绑定accept，真SDK+本地SSE的流式pause/cancel约0.21/0.22s确认，pytest791/5skip与mypy137；未验证场景明确保留，不宣称全产品通过。见 CORE-QA-CLOSE。
- LG031 done待032，真实单次工程链10请求；原SDK资料只读恢复hash交接，工程累计34/40不归零。临时SoT部分字节丢失如实记录；幸存3SDKDB/stdout已在私有持久 `checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/` 保全且hash/cmp一致，原件未删。
- **LG023首评估未完成**：`dev/lg023@fa9401d` clean，实际45/48请求，采样中提示/工具变更、重复S1/A、旧输出覆盖、逐attempt count=0及停止门装配未闭合，不能称冻结合规对照或推断收益。任务保持in-progress；主代理已拒绝以该混淆结果解锁024。新独立pi方法审计在持久 `lg023-method` / `fix/lg023-method`，预算wall1200/round220/noncache300k、**真实生成0**，先恢复/保全原件、修harness停止接线/计量/协议守卫；产品只读，不重跑未知写入。旧45与所有失败都必须保留，不能补造历史硬限或洗成0。
- **LG032已原子claim** `agent:pi-lg032`，依赖仅031/022，不机械等待023。新持久worktree `lg032` / `qa/lg032@62e96ed`，独立机制/语义质量阶段A，预算wall1200/round220/noncache300k、**真实生成0**；检查竞争领取、租约/fence、身份权限、重启反重放、受控hash交接、返修验收、默认回退及“自主发现”真实边界。只读产品，有重要缺陷由PM另派返修；本阶段不能代表成本实验已完成。成本阶段B尚未启动，必须先验证harness后另行冻结样本与总额，不复用023混淆数据。
- LG024仍todo等待023完成；035/037质量仍in-progress，040/041不解锁。最后资料GET复查服务未连通，POST0；用户尚未提供恢复端点/真实质量样本信息。继续独立核心任务，普通实现选择不需用户确认。
- 下一步：核两个在途pi owner实际退出/HEAD/审计REPORT，先解决方法守卫与032质量缺陷；023只在同等最终条件的4个真实样本和可复现门证据齐后done。禁止派工脚本自动重放旧真实写入；未来实验runtime/原始Task/Run/Subtask/worktree必须持久保存，新增attempt输出不可覆盖。所有执行仍pi+现有DeepSeek，不使用宿主原生子代理；未push/deploy/publish。

## 2026-10-16 检查点：QA/方法审计证据集成 + AUTH/POOL/EVAL 三线返修与排期（唯一串行 PM，产品真实生成 0）

- 开工保全主代理 PM dirty：`4174e23 pm: preserve main-agent PROGRESS checkpoint (batch10 follow-up, main@62e96ed)`。随后**仅证据/harness/PM 文档**安全合并：`qa/lg032@ad3d97b`→`6a7fe72`、`fix/lg023-method@99ad735`→**`51b7c9e`**；均无冲突、双方内容保留，旧 dirty/worktrees/原始记录不 reset/clean/覆盖/重复 pick。**产品树核准**`git diff --stat 62e96ed HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` 为空 ⇒ **无产品变更故不重跑全量测试**。详情 [probes/batch-20261016/AUTH-POOL-EVAL-HANDOFF.md](probes/batch-20261016/AUTH-POOL-EVAL-HANDOFF.md)。
- **LG-032 阶段 A（qa/lg032@ad3d97b，产品真实生成 0）**：门 partial——核心机制（原子领取唯一授权/fence/过期≠停止/重启反重放/默认关闭回退/受控 peer 交接/独立 review+有界返修/SDK delegation off/无常驻模型编排 agent）PASS；**F2 claim/lease HTTP 端点接受请求体 `owner`、未接程序认证身份 = 重要缺陷**（不符合 LG-028 §2.4/docs08 §4.3 note）；**F1 自主 claim=程序预选唯一节点后挂工具 = 部分符合（语义偏差，非契约违背）**；F3（`reclaim_expired` 写 `waiting_user`+fail_reason）可接受非缺陷。
- **PM 决定（用户原目标，无需再确认）**：**F2 返修**（LG-029 重新打开）；**F1 按原排期补齐多候选真正 worker 自主申请**（LG-031 重新打开），**不以文档改名代替能力补齐**。**LG-029 `done→in-progress`**（`fix/lg029-auth`，owner 只 `api/collaboration.py` 及相应 api tests/029 报告，复用既有 `ctx.worker_identity`，不碰 `api/app.py`/`bootstrap.py`/`docs08`）；**LG-031 `done→in-progress`**（`fix/lg031-pool`，owner coordinator/adapter/collaboration 模块/settings/bootstrap/必要 `api/app.py` 与共享文档，不写 `api/collaboration.py` 或其 API tests）。**保留原 assignee/历史 done/已成功受限链证据，注明新返修 owner 等价续接**。**LG-032 保持 `in-progress`/partial，阶段 B 暂停**；**LG-023 保持 `in-progress`**，024 仍 `todo`；035/037/040/041 质量门不动。
- **新建 3 个全新持久 worktree/分支**（先查不存在不覆盖，基于最终 main `51b7c9e`，开工 clean）：`lg029-auth-fix`/`fix/lg029-auth`、`lg031-pool`/`fix/lg031-pool`、`lg023-cohort2`/`eval/lg023-cohort2`。第三个**只评估 harness/fixtures/probes/LG023**，产品/共享 docs 只读，基于已通过核心首版产品树 e0 快照、不等待未来 pool；**两 arm 统一旧程序调度路径**（不把新自主模式混成自变量），比较计划写节点数 **1 vs 2**。**029/F1 实施包产品请求 0**，独立版本复验后再另行预算真实多 worker 新 pool 验证，不在此默认授权模型真写样本。
- **023 新独立 cohort PM 预注册（任何新真实请求前）**：**2 样本×2 arm×1 repeat = 4 attempt，每正式 run 仅 1 次**；**总 48 / 每 12**，全 role/stage 共享单一持久 ledger、**实际 proxy 转发前硬限**；**旧 45 失败另列**，eval 已知总实际上限 **93**。workerprompt/tool/model/SDK budgets/initial commit/accept gate **先离线验证并冻结**，harness 错误**整 cohort 停止、不改后继续**；运行目录/TaskRunSubtask/原件/worktree **持久不自动清理、不可覆盖 attempt 输出**；双方同 **toolcap 32**（旧 10 过低实证，采样前固定）、**modelcall 每 worker≤12 且同 attempt 总≤12**、**output≤16000/HTTP120/retry0/并发≤2**；**必须真正走完整 Coordinator+stopconfirmer**；**旧混淆 45 不得计交付成本也不删**。
- **证据与限制如实**：**旧 023 运行 SoT/TMD 丢失及 17 SDK DB 私有持久保全真实限制保留**；旧 45 总数可核（ledger 45 行）但逐 attempt 无法可靠归因（旧 guard count=0 + 采样中改动），**不能洗 0**；审计引用准确——**「旧停止门不是产品 bug」**（`fix/lg023-method` A7 离线复现：teardown 齐→`awaiting_acceptance`，旧 `unconfirmed` 来自未接 confirmer 的旧 `_accept`）。旧 022（unknown+6+8+5/10）、031（34/40）单列不归零。
- 契约 **`1.10.0`**、SDK **`0.1.22`**、自主模式默认 **off** 不动；本包**产品真实生成 0**，**未实施代码/新 QA/新真实 cohort**；结束仅事实交接，**未 push/deploy/publish**。

## 2026-10-16 LG-023 证据/PM 收拢 + LG-024 准备检查点（主代理 PM 独立复核；产品真实生成 0）

本节为当前事实，覆盖上文 LG-023/024 相关表述；旧实验、worktree、原始 probes、旧 dirty 全部保留，
未 reset/clean/覆盖/重复 pick，未推送/部署/发布。主代理只 PM，无嵌套派工；执行经 pi + 现有 DeepSeek。
详细报告 [probes/batch-20261016/LG023-CLOSE-LG024-PREP.md](probes/batch-20261016/LG023-CLOSE-LG024-PREP.md)。

- **开工核对（真实）**：`main@834b262` clean；`eval/lg023-cohort3@7e0b702` clean（唯一物理证据）；
  `integrate/lg031-runtime@c4d4e87` **有产品源 dirty**（`backend/**`、`tests/...` + 未跟踪 `probes/lg031/RUNTIME-AUTH-INTEGRATION/`），
  **本包未触碰其 branch/文件/index**（该 owner 独占产品源与 docs/08、README、PROJECT、agent、docs/06）。主工作区 uvicorn(:8123) 未 kill/未接线。
- **安全 merge（仅证据/评估 harness/任务）**：`git merge --ff-only eval/lg023-cohort3` → **`main@7e0b702`**（`834b262..7e0b702`，83 文件，仅 `backlog/`+`probes/`）。
  **产品树证明**：`git diff e0a8cec HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` **为空** ⇒ 逐字节同已验产品锚，**不重跑全量 pytest**。未 push。
- **LG-023 独立只读复核（非只看 summary 标题）**：protocol hash `c8f83417…` **独立重算 MATCH**；harness 7 文件 + fixtures 24 文件 sha256 **全 MATCH**；
  **唯一** `generation.jsonl`（16 行、`count=16`、`corrupt=false`、`persistent=true`）；4 份 `result.json` 机器门 **6/6（具名不同检查）**、
  独立 reviewer **`passed`/findings=0**、真实停止门 **`confirmed`（agent_closed+proxy_stopped）**、**绑定 accept**（`state=confirmed`）、
  session_refs **1/2/1/2** 与节点数一致；账本 **0→3→8→11→16** 单调累加、**转发前预留**；elapsed 11.95/15.92/13.22/17.51s。
- **比较目标满足 ⇒ LG-023 `done`（仅评估门内，不是整产品 pass）**：2 样本 × 2 arm × 1 repeat = 4 attempts，每个 1 次；初始 commit/树/工具资源/门由 protocol hash+sha256 绑定；
  四例 6/6 机器门 + 独立 review + stopgate + 绑定 accept；数据（A 6 请求/25.17s，B 10 请求/33.43s）**不支持这两样本的组队收益**。不删产品编排/评审能力；样本小/单模型/强制计划局限保留。
- **措辞修正（不覆盖旧原件字节，仅 `EVIDENCE-CLOSE` 补注）**：cohort-3 “cost higher/lower” **仅指已测请求数/elapsed 代理量**；
  **完整 token/费用/shared 开发-QA 未知**，**不得**引申为完整生命周期成本或货币节省。
- **usage/token 真实边界（零调用只读）**：`usage/cost=unknown`；只读核对已持久 6 个 SDK session DB 的 `gen_metadata`（protobuf），
  **仅含 system prompt/step 结构/model_enum，无可核 provider token/费用字段** ⇒ **保持 unknown**（**不逐 attempt 追加 metrics**、**不重跑模型补 token**、
  **不把估计称 provider 计费 tokens**、不扫无关用户/tmp 全部 session）。未抽取/未持久化任何 prompt/headers/密钥/raw body；敏感原件不入 repo。
- **旧成本保留、总数 65**：旧 cohort-1 **45**（protocol-deviation 失败，原 ledger 45 行保留）+ cohort-2 **4**（harness D1 停止）**另行单列、不清零、不并入** cohort-3 的 **16**；
  **总实际 eval = 45+4+16 = 65**（**不得用 16 覆盖旧 49**；**不当作所有旧失败原件都齐**——旧部分运行 SoT 已丢失，METHOD-AUDIT 明示）。
  **不因无法取得费用阻止合法评估 done**。
- **LG-024 排期（原子 claim + 新 worktree）**：backlog 专用根 `validate` → **ok 41 tasks/0 diagnostics**、`digest` **complete=true**（33 done/6→5 in-progress/3 todo）、
  `ready` = LG-024 后，CLI **原子 claim `LG-024 --as agent:pi-lg024`**（不绕 claim）。精确提交 PM/claim **`b7db2c7`**。
  创建**全新持久 worktree** `/home/yhvh/code/lightgravity-bot-worktrees/lg024`（branch `dev/lg024`，基于 `b7db2c7`；路径/分支先核**不存在**、不覆盖）。
  > 注：对整个仓库根跑 `validate` 会命中旧实验 `probes/agensh-orchestration-r2/runs/**` 已跟踪样例的重复 frontmatter 键（`b2bd5eb` 既存），非 backlog 任务；backlog 任务根为 0 诊断，此差异如实记录、不在本包修旧实验。
- **LG-024 阶段 A（已落，`dev/lg024@db84849`）**：**只写 probes/本地产物**——许可与来源清单、启动/安装入口烟测草案、阶段 A 计划。
  **关键发现**：参考仓库 **Olav 为 Business Source License 1.1（非宽松）** ⇒ 仅方法参考、**不外搬受限实现**；Olav OS/Olav Tasks 为 MIT；运行依赖全为 MIT/BSD-3-Clause/Apache-2.0、无 copyleft 传染项。
  **阶段 B 等待** `integrate/lg031-runtime` 释放共享 docs 后**串行**落地 README/docs06/PROJECT/agent/docs08 并**绑定届时准确候选**。**LG-024 不提前 done**。
- **状态如实**：**LG-023 `done`（评估门内）**；**LG-024 `in-progress`（阶段 A，未 done）**；**LG-029/031/032 `in-progress`**（重要返修/QA 不动）；
  **LG-035/037 `in-progress`**；**LG-040/041 `todo` 不解锁**；**LG-022 `done`（门内）**、**LG-031 `done`（待 032 独立集中 QA）** 保留。
  **契约 `1.10.0`、SDK `0.1.22`、自主模式默认 off 不变**。**本包产品真实生成 0**，未推送/部署/发布。
- **handoff/边界**：`main@b7db2c7`（clean）；LG-024 HEAD `db84849`（clean）；metrics 原件边界：cohort-3 唯一物理 ledger `lg023-cohort3-data/generation/generation.jsonl`（16 行）、
  逐 attempt `probes/lg023/cohort3/runs/**`（不可变）、旧 cohort1 ledger `probes/lg023/ledger/generation/generation.jsonl`（45 行）、cohort2 `lg023-cohort2-data/attempts/**`（4）。
  退出无残留本包进程；下一步阶段 B 待共享 docs owner 释放。

## 2026-10-16 LG-024 首版交付准备收口检查点（主代理 PM，产品真实生成 0 / 外部服务 0）

本节为当前事实，覆盖上文 LG-024 相关表述；旧实验、worktree、原始 probes、旧 dirty 全部保留，
未 reset/clean/覆盖/重复 pick，未推送/部署/发布/上传。主代理只 PM，无嵌套派工。
详细报告见 [probes/batch-20261016/LG024-CLOSE.md](probes/batch-20261016/LG024-CLOSE.md)。

- **开工核对（真实，只读）**：主工作区 `main@66b2b10` clean；源 024 owner 已退出、`dev/lg024@73f570c` clean；
  `main` 为 `dev/lg024` 直接祖先（`git merge-base --is-ancestor` = YES）⇒ **可 fast-forward、无冲突**。
  变更范围仅 `README.md`/`backlog/tasks/LG-024.md`/`docs/06-roadmap.md` + `probes/lg024/**`，**无产品代码、无 `docs/08`、无 `qa/**`**。
  主工作区 uvicorn(`:8123` PID 3320750) **未触碰**；在途签名 `lg032-runtime-r1` 独立 QA（PID 2233535）**未 kill、未碰其 branch/文件/index/worktree**。
- **安全收拢**：`git merge --ff-only dev/lg024` → `main` 前进到 **`73f570c`**。**不合**未验 `integrate/lg031-runtime@afcae82`；**不碰** `qa/lg032-runtime-r1`。
  README/PROJECT/agent/docs06 无冲突（main 未改这些文件），双方内容保留，未复制秘密，**docs/08 本包不写**。
- **包锚点复核（逐字节，PM 独立核）**：首版稳定 product tree **`e0a8cec`**（= 收拢前 `main` `66b2b10` 产品路径，`git diff` 空）；契约 `1.10.0`、SDK `0.1.22`；
  tarball **`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.tar.gz`**；
  **sha256 = `581f1de603ab8adc6533efa9d4b2ed0506433d17328646b00ab7bbb2761f4de0`**（工作区实体 + `git cat-file blob | sha256sum` **双核一致**）；
  **405 文件**（`tar` 条目 = manifest 行数 = 405）；`sha256sum -c`（除 manifest 自身）**全 MATCH exit 0**；`verify-stage-b.sh` → **`OK (405 files, strictly clean)`，exit 0**（无 `/home/yhvh/`、秘密、DB、日志、依赖体、开发/PM 证据）。
- **已验 scope**：私有本地 L0 包（运行时/前端源码 + 预构建 `frontend/dist` + tests + 锁文件 + 用户文档）；解包离线 `uv sync` + health/version/index/静态资产 200 + 无 token 敏感写 401 + stop 释放
  （脚本 `smoke-unpack.sh`：专用端口 `18433`、独立 data/secret、`--no-executor`、产品真实 SDK/模型 0、**不碰 `:8123`**）。
  **未测保留**：真实 `lightgravity init` 写凭证、`status --deep`、浏览器六入口渲染、真实模型闭环；**未重跑**无变更的完整 pytest/前端矩阵（产品树无变更，引用已验锚点）。
- **许可范围**：L0 不重分发第三方包体/SDK/weights；`NOTICE.md` 列运行时 51 包 + 前端 224 + `pypdfium2` 捆绑 CC-BY-4.0、弱 copyleft MPL-2.0、无 GPL/AGPL；
  **项目自身无 `LICENSE`/`NOTICE`、公开许可证未选定 ⇒ 未授予公开再分发**；NOTICE 列上游许可但不授公开再分发（**不代用户选公开许可证**）；私有 review 准备范围准确。
- **协作候选单列**：`integrate/lg031-runtime@afcae82` **未合 main、独立 QA R1 进行中**，**未来协作 source 不是本包已验内容**；
  若集入 main 需**另包候选并刷新绑定届时真实 product tree**，**不把 `e0a8cec` 旧包冒称最新全产品**。
- **措辞边界（不泛化）**：组队成本「更高/更低」只能指**已测请求数 / elapsed**（cohort-3 A 6 请求/25.17s、B 10 请求/33.43s），**不泛指完整费用**；
  **provider token / 费用 / sharedpiQA 仍 `unknown`**（不当 0）；**023 旧 45+4 历史不洗白**（另行单列）。
- **状态如实**：**LG-024 `in-progress → done`**（仅**首版交付准备原门**内，**仍非发布授权**）；`main@73f570c`（+ 本 PM 收口 commit）。
  **LG-029/031/032 仍 `in-progress`**（source candidate 未合 main / 独立 R1 进行）；**LG-035/037 `in-progress`**；**LG-036/038 `done` 待 040**；**LG-040/041 锁不动（`todo`）**。
  契约 `1.10.0`、SDK `0.1.22`、程序最小规则调度、真实 SDK 唯一路径、自主模式默认 off **不变**。
  **本包产品真实生成 0、外部服务调用 0**；未推送/部署/发布/上传。所有旧包/实验/路径保留。

## 2026-10-16 续接：LG031 契约冻结 1.11.0 + 真实工程 proof（branch `dev/lg031-real-proof`）

- **本包 owner**：LG031 接口冻结/真实工程 proof owner（pi 现有 DeepSeek，无嵌套派工/推送/部署/发布，主代理仅 PM）。源实施 / 独立 R1 / LG-024 文档 owner 已退出。
- **worktree/branch**：全新持久 `/home/yhvh/code/lightgravity-bot-worktrees/lg031-real-proof`（branch `dev/lg031-real-proof`），基于 `qa/lg032-runtime-r1@26ea945`，**安全 `--no-ff` merge** `main@3797964`（仅 LG-024 docs/包，无产品代码）。**未 reset/clean/覆盖/重复 pick**；所有旧 worktree/branch/dirty/进程保留。
- **产品树字节同一**：`git diff afcae82 HEAD -- backend frontend tests pyproject.toml uv.lock Makefile` 为空（除本包版本常量/测试断言外）；相对 R1 基 `26ea945` 仅新增 `main` 的 `probes/lg024/**` 与 `docs/06` LG-024 行。
- **契约冻结 1.11.0 MINOR**（PM 决定，详见 PROJECT 决策日志）：按 R1 观察 O3 的实际公开兼容变化（四端点 body `owner` required→optional/非授权 + `ExecutionGrant.lease_owner` 加性）保守升 MINOR；先改 `docs/08` §13/§4.3/头部，再同步 `contracts/constants.py`（`CONTRACT_VERSION="1.11.0"`）、`tests/contracts/test_contracts.py` 与 README/PROJECT/agent/docs06 入口。**1.10/e0 首版包与历史证据保持原版本，不重写旧 JSON/PLAN/日志**；**未改任何 runtime 行为**。
- **局部验证**：`uv run --frozen pytest tests/contracts tests/api/test_health.py -q` → **11 passed**；`uv run --frozen mypy` → **137 files clean**。
- **状态**：LG-029 待确认为 `done`（R1 正向证据齐）；LG-031 真实 provider 门未做前保持 `in-progress`；LG-032 保持 `in-progress`（阶段 B 暂停）。真实 proof 见 `probes/lg031/REAL-PROOF/**`，本包产品真实生成随时间记录，旧 LG031 累计 34/40 不归零。
