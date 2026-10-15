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
