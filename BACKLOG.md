---
title: "LightGravity Bot 开发任务入口"
doc_type: index
category: planning
updated: "2026-10-18"
---

# LightGravity Bot 开发任务入口

## 任务编号分配（2026-10-18 起）

两个团队并行开发。原号段方案（2026-10-18）未被遵守：资料摄取/ASR 团队按“现有最大编号＋1”取了 LG-211～214，因此改为**先建文件占号**：

- 取号＝`backlog/tasks` 中现有最大编号＋1，并**立即创建该任务文件**；未建文件前不得在 prompt、分支名或提交中引用该编号。
- 已存在或已被引用的编号不复用、不改号；发现冲突时后建方改号。
- 当前归属：LG-201～210、LG-215～228 为 Tasks 工作区/性能/英文UX修复；LG-180、187、188、211～214 为资料摄取/ASR 团队。

## Demo录制前修复批次（2026-10-18，已排期未派工）

依据 [LG-233 摸底报告](probes/demo-readiness-20261018/REPORT.md)；脚本 [content/demo/script.md](content/demo/script.md)；排期 [docs/06 §11](docs/06-roadmap.md)。

- [LG-248 Demo录制前修复批次](backlog/tasks/LG-248.md)（聚合门）
- 后端：[LG-240](backlog/tasks/LG-240.md) · [LG-241](backlog/tasks/LG-241.md) · [LG-244](backlog/tasks/LG-244.md) · [LG-246](backlog/tasks/LG-246.md) · [LG-224](backlog/tasks/LG-224.md) · [LG-249 Task对话仅@bot](backlog/tasks/LG-249.md) · [LG-250 英文文案](backlog/tasks/LG-250.md)
- 前端：LG-240前端 · [LG-242](backlog/tasks/LG-242.md) · [LG-243](backlog/tasks/LG-243.md)＋[LG-216](backlog/tasks/LG-216.md) · [LG-245](backlog/tasks/LG-245.md) · LG-250前端
- 性能：[LG-208](backlog/tasks/LG-208.md)
- [LG-251 串行集成](backlog/tasks/LG-251.md) → [LG-252 重跑摸底/录制前验收](backlog/tasks/LG-252.md)

## 英文UX闭环修复（2026-10-18，仅建任务）

只读审计：配置齐备后仍有代码缺口卡住用户。只修英文，不处理中文。排期见 [docs/06 §10](docs/06-roadmap.md)。未派工。

- [LG-215 英文UX闭环修复版本](backlog/tasks/LG-215.md)
- 诚实状态与提示：[LG-216 执行能力与失败原因](backlog/tasks/LG-216.md) · [LG-217 无模型如实不可用](backlog/tasks/LG-217.md) · [LG-218 @bot 提示](backlog/tasks/LG-218.md) · [LG-219 统一401](backlog/tasks/LG-219.md) · [LG-220 视图跳转与Board自动刷新](backlog/tasks/LG-220.md)
- 资料链路：[LG-221 只选有正文资料](backlog/tasks/LG-221.md) · [LG-222 Reprocess按类型与旧音频补转写](backlog/tasks/LG-222.md) · [LG-223 手动补写正文](backlog/tasks/LG-223.md) · [LG-224 PDF文字层优先](backlog/tasks/LG-224.md) · [LG-225 ASR/OCR/语义状态与文案](backlog/tasks/LG-225.md)
- [LG-226 串行集成](backlog/tasks/LG-226.md) · [LG-227 独立验收](backlog/tasks/LG-227.md)
- [LG-228 8123运行配置补齐（需用户决定）](backlog/tasks/LG-228.md)
- [LG-229 线上demo接入Google Gemini](backlog/tasks/LG-229.md) · [LG-230 移除模型主机白名单与API用量上限](backlog/tasks/LG-230.md)

## Team/资源页面加载性能与会话（2026-10-18，仅建任务）

只读检查：`team/available`每次约8s/4.6MB，会话不持久致重启后401。未派工。

- [LG-208 资源读取按文件版本缓存解析结果](backlog/tasks/LG-208.md)
- [LG-209 精简team/available返回并分页加载](backlog/tasks/LG-209.md)
- [LG-210 团队登录会话持久化](backlog/tasks/LG-210.md)

## Tasks工作区取代Chat主页面（2026-10-18，仅建任务）

设计：[docs/05 §1～4](docs/05-navigation-and-team.md)、design.md §2/§5、PROJECT决策日志。未派工。

- [LG-201 Tasks工作区版本](backlog/tasks/LG-201.md)
- [LG-202 删除Chat主页面，Files改为Tasks](backlog/tasks/LG-202.md)
- [LG-203 New task按钮](backlog/tasks/LG-203.md)
- [LG-204 上下文材料选择移入Tasks工作区](backlog/tasks/LG-204.md)
- [LG-205 Bot Chat历史图标第一期](backlog/tasks/LG-205.md)
- [LG-206 串行集成完整候选](backlog/tasks/LG-206.md)
- [LG-207 独立验收](backlog/tasks/LG-207.md)

## 英文Reader转写与UI接入（2026-10-18）

[设计](docs/15-english-asr-and-ui.md)。用户授权TTS合成英文功能验证，再接UI；不解除中文真人质量门，不部署。

- [LG-158 英文EG2 Reader转写与UI接入版本](backlog/tasks/LG-158.md)
- [LG-159 验证TTS英文样本与EG2 Reader真实转写并冻结契约](backlog/tasks/LG-159.md)
- [LG-160 实现英文Reader后端与持久音频摄取接线](backlog/tasks/LG-160.md)
- [LG-161 接入英文转写配置与Chat和Files界面](backlog/tasks/LG-161.md)
- [LG-162 串行集成英文转写完整候选并冻结验收版本](backlog/tasks/LG-162.md)
- [LG-163 独立验收英文TTS至转写索引与UI闭环](backlog/tasks/LG-163.md)
- [LG-164 配置文案修复](backlog/tasks/LG-164.md)
- [LG-165 QA修复串行集成](backlog/tasks/LG-165.md)

## 主机语音服务调查（2026-10-18）

[LG-157](backlog/tasks/LG-157.md)：按用户要求只读调查192.168.8.12开放TCP端口与CosyVoice/ASR服务，不顺带调用模型或部署接入。

## 资料上传与自动索引体验版本（2026-10-18，候选QA通过）

设计：[docs/14](docs/14-material-intake-and-auto-index.md)；阶段排期：[docs/06 §8](docs/06-roadmap.md)。隔离1.19候选已实现，首轮QA问题已修复，第二轮独立QA通过；未部署，线上仍1.18，状态以任务 frontmatter 为准。

- [LG-139 命名里程碑](backlog/tasks/LG-139.md)
- [LG-140 契约与技术核实](backlog/tasks/LG-140.md)
- [LG-146 共享前端接口准备](backlog/tasks/LG-146.md)
- [LG-141 后端自动媒体索引](backlog/tasks/LG-141.md)
- [LG-142 Chat 回执与 Files 管理](backlog/tasks/LG-142.md)
- [LG-143 顶部语义搜索](backlog/tasks/LG-143.md)
- [LG-144 串行集成完整候选](backlog/tasks/LG-144.md)
- [LG-147 摄取取消边界与作业关联修复](backlog/tasks/LG-147.md)
- [LG-148 旧检索重建权限核实与修复](backlog/tasks/LG-148.md)
- [LG-149 权限修复集成与复验候选](backlog/tasks/LG-149.md)
- [LG-150 配置传播修复](backlog/tasks/LG-150.md)
- [LG-151 单来源重建保全](backlog/tasks/LG-151.md)
- [LG-152 失败反馈与纯附件发送](backlog/tasks/LG-152.md)
- [LG-153 首轮QA修复完整集成](backlog/tasks/LG-153.md)
- [LG-154 缓存身份接缝交接](backlog/tasks/LG-154.md)
- [LG-155 并发测试确定性修复](backlog/tasks/LG-155.md)
- [LG-156 最终复验候选冻结](backlog/tasks/LG-156.md)
- [LG-145 独立版本 QA](backlog/tasks/LG-145.md)


## 连接管理入口收敛（2026-10-17）

[LG-103 保留Settings连接管理、移除左侧Connections](backlog/tasks/LG-103.md)：已更新8123，main85d009d，连接引用／旧深链跳到匹配设置，成员权限与Task上下文保持；[交付与截图](probes/settings-connections-20261017/DELIVERY.md)。

## 导航图标统一（2026-10-17）

[LG-102 左侧资源与Settings图标](backlog/tasks/LG-102.md)：已更新8123，main503dca3，23项既有回归和真实前后端浏览器9/9通过。[交付及截图](probes/nav-icons-20261017/DELIVERY.md)。

## 顶栏资料搜索输入框（2026-10-17）

[LG-100 Search materials 改为居中搜索框](backlog/tasks/LG-100.md)：已更新到8123，支持直接输入／Enter真实查询／Escape关闭和Files回链，桌面与390宽度验证通过；[交付证据与截图](probes/centered-search-20261017/DELIVERY.md)。

[LG-101 搜索文案简化为 Search](backlog/tasks/LG-101.md)：已更新8123，main bd3b13b，14项shell回归及构建通过；[交付记录](probes/search-label-20261017/DELIVERY.md)。

## 通用协作与可靠性合入（2026-10-17）

[LG-099 重启8123到已验收版本](backlog/tasks/LG-099.md)：用户授权后已完成，当前运行契约1.16.0；[重启与浏览器冒烟证据](probes/generic-merge-20261017/RESTART.md)。账户／资料与关闭执行设置保留；5173监听资源异常已恢复，18123保持。

[LG-094 整合版本](backlog/tasks/LG-094.md)：[LG-095 隔离筛选集成](backlog/tasks/LG-095.md) → [LG-096 独立验收与主线合入](backlog/tasks/LG-096.md)。用户授权合并八项通用功能及修复；排除游戏角色包、固定招募映射和演示恢复预算配置。pi 集成、独立 pi 集中浏览器 QA，新增缺陷交 Codex 子代理。既有 dirty 与运行服务保持，合入不自动部署／推送。[派工范围](probes/generic-merge-20261017/pi-integration-prompt.md)。

[LG-097 状态词交付初修](backlog/tasks/LG-097.md) 后，独立 QA 仍复现长工作区前缀原始场景，另建 [LG-098 原始 R2 场景完整返修](backlog/tasks/LG-098.md)。QA FAIL 原报告保留，修复及独立复验通过后才合入。

最终已合入 `main@ca58b35`，契约1.16.0；独立返修复验 PASS_WITH_LIMITATIONS、产品树与候选2024205一致，详见[交付](probes/generic-merge-20261017/DELIVERY.md)。既有服务保持，8123未更新运行版本，未推送／发布。任务当前状态只在各任务 frontmatter 维护。

## 简化安装（2026-10-17）

- [LG-092 简化安装入口与预构建前端交付包](backlog/tasks/LG-092.md)：pi 实施，隔离工作树，源码安装与不依赖 Node.js 的本地交付包；不创建云资源、不触碰既有服务。按小批次局部验收，待后续版本 QA。
- [LG-093 发布到 Gitea 与 GitHub](backlog/tasks/LG-093.md)：用户已授权，沿用两个平台的既有历史边界，发布安装简化源码、公开说明与安装附件。

## 两分钟成片制作（2026-10-17）

[LG-086 成片里程碑](backlog/tasks/LG-086.md)：[LG-087 pi制作与真实视觉探针](backlog/tasks/LG-087.md) → [LG-088 独立pi视觉QA](backlog/tasks/LG-088.md)。HyperFrames+FFmpeg，真实素材时间码/摘要和DeepSeek图像复核；不改变已完成demo与产品账本。

[LG-089 渲染及播放检查故障修复](backlog/tasks/LG-089.md)保留诊断与失败链；[LG-090 清理录制标签与游戏装饰页脚叠字](backlog/tasks/LG-090.md) → [LG-091 清理后最终成片独立复核](backlog/tasks/LG-091.md)。v1核心独立PASS后完成局部后处理，全部版本保留；[最终v2电影、可编辑工程与独立QA](probes/video-20261017/README.md)。

## 双账户小游戏 Demo 本地闭环（2026-10-17）

[本地交付与账号入口](probes/demo-team-game-20261017/DELIVERY.md) · [独立接续QA](probes/demo-team-game-20261017/CONTINUATION-QA.md) · [两分钟runsheet](docs/12-team-game-demo-runsheet.md)。功能运行于固定隔离分支61e2269，主目录未合入以保留5173原页面；当前入口为已完成任务回放。

- [LG-081 用户批准32次追加后的第三次恢复准备](backlog/tasks/LG-081.md)：累计96，保留前64失败，不自动提额。
- [LG-082 修复无候选的失败任务验收按钮](backlog/tasks/LG-082.md)：真实预览发现的前端缺陷。
- [LG-083 隔离产物引用与验证归属](backlog/tasks/LG-083.md) / [LG-084 下载路径与摘要绑定](backlog/tasks/LG-084.md)：96预算运行前审计发现并修复，不消耗产品调用。
- [LG-085 同候选同内容证据副本去歧义](backlog/tasks/LG-085.md)：第三次模型/停止门已过，仅接续无模型试玩与验收；旧QA失败保留。

- [LG-063 里程碑与完整验收](backlog/tasks/LG-063.md)
- [LG-064 差距调查、接口与隔离准备](backlog/tasks/LG-064.md)
- [LG-065 默认 agency 角色导入](backlog/tasks/LG-065.md) 与 [LG-066 Team Chat 交付与跨账户查询](backlog/tasks/LG-066.md)：调查后按 owner 并行。
- [LG-067 串行集成与独立真实浏览器彩排](backlog/tasks/LG-067.md) → [LG-068 本地可复演入口交付](backlog/tasks/LG-068.md)。状态仅在任务原文维护。
- [LG-069 修复交付需求的控制关键词误判](backlog/tasks/LG-069.md)：阻断缺陷，与两条新功能分开修复。
- [LG-070 隔离双账户浏览器与真实模型彩排工具](backlog/tasks/LG-070.md)：与功能开发并行准备；真实调用留到整合候选独立 QA。
- [LG-071 修复查询被界面误报为创建任务](backlog/tasks/LG-071.md)：共享查询回执保持在 Team 频道。
- [LG-072 修复首次配置后的 reviewer 启动顺序](backlog/tasks/LG-072.md)：避免复演依赖隐式预配置。
- [LG-073 长执行断连判据与同任务接续](backlog/tasks/LG-073.md)、[LG-074 真实SDK上下文诊断](backlog/tasks/LG-074.md)、[LG-075 修复工作区误继承宿主Git](backlog/tasks/LG-075.md)：首次真实彩排暴露的问题，保留原始失败和请求账本。
- [LG-076 同任务受控恢复准备](backlog/tasks/LG-076.md)：保全原产物与失败成本，累计预算64内接续，禁止清零或新Task顶替。
- [LG-077 修复恢复彩排历史失败事件判据](backlog/tasks/LG-077.md)
- [LG-078 修复失败任务重试的历史Run与attempt编号](backlog/tasks/LG-078.md)
- [LG-079 本地预览与预算停止证据](backlog/tasks/LG-079.md)：完整验收未通过时提供可检查成果，不追加模型调用。
- [LG-080 修复终止失败后等待吞错](backlog/tasks/LG-080.md)：修复实际QA暴露的等待行为，不新增模型调用。

> 创建：2026-10-14。开发任务由 Olav Tasks 管理，schema 为 `olav.tasks/v1`，编号 LG。状态以单项 Markdown frontmatter 为准，本索引不重复维护状态。

## 前一版本交付：管理员凭据与账户管理（2026-10-17）

账户管理版本 LG-061／062 已完成：main b6c738d、契约 1.15.0，产品／测试树与独立 QA 固定 dbf7b0c 一致。最终独立 QA PASS：30 Chromium E2E、18 独立浏览器检查、3 次导航稳定性检查通过；产品相同树沿用 1061 后端通过／2 跳过、181 前端和跨进程安全证据。当前 http://192.168.8.50:8123（0.0.0.0:8123，PID 1093724）另有 27／27 真实普通浏览器检查通过。用户指定 admin/admin123 已生效，Settings 提供 Accounts 与 My Account；已有账号／资料保持，首次空库初始化不覆盖后来改密。无真实产品模型调用，保留 no-executor／cap0，未远端推送，用户最终验收待定。 [交付记录](probes/accounts-20261017/README.md)。状态以任务 frontmatter 为准。

- [LG-061 设置指定的默认管理员凭据](backlog/tasks/LG-061.md)
- [LG-062 在 Settings 中加入账户管理界面](backlog/tasks/LG-062.md)：依赖 LG-061。


## 运行配置补充（2026-10-17，LG-060）

[LG-060 发布到0.0.0.0](backlog/tasks/LG-060.md) 已完成：当前 http://192.168.8.50:8123 使用团队账号登录，实际普通浏览器36项验证通过；源码与已有修复版本一致。[记录](probes/lan-publish-20261017/README.md)。

## 历史闭环快照（2026-10-17，LG-051 界面修复）

LG-051～059 已完成技术交付。固定 602c7af 独立 pi QA 为 PASS_WITH_LIMITATIONS；主目录 ea6da80 产品树一致，本地 http://127.0.0.1:8123 运行 1.14.0，实际 30 项检查通过。后端 1004 通过／5 跳过，前端 171 通过，Playwright 22+28 通过。任务 CLI：59 tasks／0 diagnostics，58 done／1 todo／0 in-progress，ready=[]；唯一既有待办 LG-041 仍受 ASR 质量门阻塞。[交付证据](probes/ui-repair-20261017/README.md)。用户最终验收待定，未推送。


## 历史批次状态（2026-10-16，selected-material 原型命名里程碑闭环；LG-047 与 LG-049 已 done；LG-041 保持 todo）

- **实际闭环（root PM 复核）**：LG-047 命名里程碑独立 QA 据 LG-049 `N-R3-LIFECYCLE` **实际 PASS_WITH_LIMITATIONS** 置 `done`；LG-049 亦置 `done`。真实完整 SDK 交付生命周期跑通（原生 API 上传 alpha `content_hash=d34f0ca58b8d…`、无 seeded derivative → EXACT 前失败目标 `delivery/create_task` → 程序规则计划 `deliver`+`verify` → 真实 SDK worker **6/6 事实** → **`verify` passed（R2 曾 429）** → 机器门 → **真实独立 ModelReviewer `reviewer_kind=model`/`model_calls=1`/passed** → **worker `cleanup=done`+`member.released` 与 reviewer `reviewer_cleanup.confirmed=true` 于 accept 前 CONFIRMED** → API accept（乐观 revision）→ `done`；artifact refs 真实 body + Sources bindings 匹配）。**8/16 前向**（deliver 2 + verify 5 + reviewer 1）。报告 [REPORT-N-R3-LIFECYCLE](probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md)；本轮集成 [K-RELEASE-CLOSE](probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md)。
- **集成（仅 probes/docs）**：`--no-ff` 合入 `qa/proto-material-lifecycle-r3-20261016@dc1a1b2` → 合并提交 **`76f10c7`**（父 `096d796`+`dc1a1b2`）；唯一非 probe 差异 `LG-049.md` 冲突保留 `main` 验证记录，**无代码改动**；产品树 `main` == `0188ca2`（backend `8b4256a4…`/frontend `07618bb2…`/tests `9a37448e…`/examples `63ee05cd…`）。
- **任务 CLI（实测）**：`validate` **49 tasks / 0 diagnostics**；`digest` **48 done / 0 in-progress / 1 todo**；`ready=[]`；唯一 decision = LG-041（质量门）。
- **保留限制（不洗白）**：累积成本 **unknown 非 0**（R1 已知 1+缺口 / R2 actual 8 / R3 actual 8 分列）；浏览器 UI 证据为复用（前端未构建，前端树一致）；未重跑全量测试（代码未改）；`orion-summary.md` 裸名 ref 400 为端点契约行为。用户最终验收仍待定、未 push/deploy、`8123` 未触。

### 上一批次（2026-10-16，selected-material 快速原型 LG-042～049；R3 执行完成待闭环；历史保留）

- 任务 CLI（backlog 根）：LG-042～045 **done**、**LG-046 整合候选已交付**、**LG-047 进行中（R1 FAIL，R2 FAIL/INCOMPLETE，预算 8/8 耗尽，无 PASS/done）**、**LG-048 诊断 done**、**LG-049《验证选定资料交付完整生命周期》`in-progress`（P0，`parent: LG-047`，`depends_on: [LG-048, LG-046]`，`assignee: agent:pi-proto-lifecycle-qa`）**；LG-041 仍 `todo`（质量门阻塞）。
- **PM 选定（root 显式授权）**：依据 LG-048 诊断，PM **明确选定** 049 为下一任务（**非**第三次盲修）；root 授权 **R3 新 campaign `N-R3-LIFECYCLE`，hard cap 16**（含失败/reviewer/连接测试）——**仅一个** fresh delivery Task、**无自动整轮重试**、`retry 0`、串行 90s/请求、生命周期轮询 ≤300s；单次 initialize 自有新 dataRoot+manifest+durable ledger（**绝不用 R2 根/counter reset**）；manifest 缺失/损坏或账本损坏 ⇒ **deny**，转发前持久预留 cap16、跨重启不归零、不自动扩展；R1 已知 1 + R2 actual 8 **分别保留**，累积成本 unknown 非 0。
- **PM 决策（保留护栏）**：保留既有 `deliver`+`verify` SDK 节点、**真实独立 ModelReviewer**、机器门/stopguard；不删除/弱化、不新增 planner/infra。docs/10 §7 与 docs/11“单 worker”措辞已**最小勘误**（文档-only，非行为变更）。
- **序列 prep（`main`，`--no-ff`、probes-only、无冲突、保留全部历史）**：合入 I `qa/proto-material-r2-20261016@a9ba494` → `256cd78`；合入 L `qa/proto-material-route-r2-20261016@11b5848` → `d8d8b4e`。产品树 `main:backend` `8b4256a4…` 与 `3ae4ac0` 一致，无代码改动。
- **R2 结论（`a9ba494`）**：真实 SDK worker 写出含**全部 6 条真实事实且正确**的 deliverable，但第二个（`verify`）SDK 节点撞 **429** 后整 Task `failed`；独立 **ModelReviewer / stop-gate / QA user accept** **从未到达（UNVERIFIED）**。R2 新增产品请求硬上限 **8/8 耗尽**，不可重跑。详见 [REPORT-I-R2](probes/prototype-selected-material-20261016/I-R2-QA/REPORT-I-R2-20261016.md)。
- **PM 决策（root 授权）**：**暂停盲重试/盲修循环**，先拆 **LG-048 零模型只读技术诊断**（**非 LG-049**；不新增 049 直到 PM 依据诊断选定下一任务）。诊断报告 [M-DELIVERY-DIAGNOSIS](probes/prototype-selected-material-20261016/M-DELIVERY-DIAGNOSIS/REPORT.md)。
- **诊断要点**：(a) 429 = 进程全局持久 8 硬上限（`LIGHTGRAVITY_MAX_GENERATION_CALLS=8`+持久账本），**非** per-node；(b) 默认文件交付规则计划 = **`deliver`+`verify` 双 SDK 节点**（非单 worker），与 docs/10 §7 措辞偏差，`verify`≠独立 ModelReviewer，**不假定移除 verify 已授权**；(c) 首个 SDK `1006` = QA harness 提前关闭，**非产品复现**；(d) reviewer/stop-gate/accept 未验证，后续预算提案 ≥15（含失败+reviewer，**未授权**）并须分列节点消耗。
- **实施进展**：042 冻结契约（`pi-proto-prepare`）→ 043 后端（A `6515e5c`）→044 前端（B `552d839`）/045 Demo（C `e36df29`）→ **046 串行整合候选** → **047 QA R1 FAIL** `57809d4` → F/G 并行返修 → H 串行集成候选 → 047 **独立 QA-R2 FAIL/INCOMPLETE** → J 分类器修复 `2352c52` 合入 `7e433c3` → **LG-048 诊断**。契约 [docs/10](docs/10-selected-material-prototype.md) + docs/08 §6.6.1，加性 MINOR **`1.12.0`**。
- **整合实际检查**：D 候选后端 `mypy` 139 files clean + `pytest tests/` **908 passed / 2 skipped**（EXIT 0）、前端 `tsc`/`vite build` EXIT 0；**R1 合并候选**后端 `mypy` 139 clean + **`pytest -q` 930 passed / 2 skipped**（EXIT 0，F+G 联合全量），前端未改动故未重跑；均无真实产品模型调用。
- **预算**：prep/A/B/C/整合/048 产品推理 0；**LG-R2 新增产品请求 8/8 已耗尽（不可重跑）**；R1 已知 1 次真实请求与失败样本单列保留，**不宣称原 12 次 campaign 全程已核实**；成本 unknown 非 0。
- **未宣告 R3 通过、未宣告累积成本已知**；LG-047 仍 `in-progress`（无 done）；**LG-049 保持 `in-progress`**（标 done 留待 root closure 复核报告）；**不改动 R2/I 活动 worktree/campaign/ledger**。

### 上一批次（2026-10-16，LG-040 RELEASE-CLOSE 收口；LG-040 done）

- 任务 CLI（**backlog 专用根** `/home/yhvh/code/lightgravity-bot/backlog`）：`validate` **41 tasks / 0 diagnostics**；`digest` **1 todo / 0 in-progress / 40 done**，complete=true；`ready=[]`；唯一 decision = LG-041（质量门）。
- **LG-040 已 `done`（版本 QA 技术验收；用户最终验收仍 PENDING、未发布）**：治理报告 `probes/lg040/TRANSITION-QA-20261016/REPORT.md`（候选 `30029eb`）**PASS_WITH_LIMITATIONS、0 个 open important issue**；收口顺序 `--no-ff` 合并 `925f828`/`8a4560a`/`30029eb`/`7fd0f61` 至 HEAD `7cc94b5`（无冲突）；`backend/`/`tests/`/`docs/` 自 `fc9f74b` 未变，产品增量仅 `frontend/src/app/shell.css`（transition CSS）。详情 [RELEASE-CLOSE REPORT](probes/lg040/RELEASE-CLOSE-20261016/REPORT.md)。
- **历史 8a4560a 明确不采信为收口**：其 `readyAtMs 2592` 用 8000ms 上界，仅作历史保留；修复后 `30029eb` 达标（零溢出 + 2s 几何就绪）。

### 上一批次（2026-10-16，Materials R7 集成；LG-035 done；历史保留）

- 任务 CLI（历史时点）：`validate` **41 tasks / 0 diagnostics**；`digest` **2 todo / 1 in-progress / 38 done**，complete=true；`ready=[]`。
- **R7 集成（2026-10-16）**：A `test/materials-fixtures-r7-20261016@f21d6e3`、B `fix/materials-layout-r7-20261016@8182d36`、C `investigate/materials-endpoint-r7-20261016@1cfa417`、D `test/materials-ocr-cohort-r7-20261016@97c4f8f`、E `fix/materials-table-mode-r7-20261016@4917413` 按序 `--no-ff` 合入 `main`（`89b0cc1`→`7eb88fe`→`e8a8e40`→`95b66bf`→`5f84503`）；合并候选 mypy 138 files clean、`pytest tests/sources` 147 passed/1 skipped；详见 [REPORT](probes/materials-r7-integration-20261016/REPORT.md)。
- **LG-035 已 `done`（待 LG-040 集中版本 QA）**：原始验收条件（真实清晰页、低质量诚实降级、多页、中文印刷、**真实 grid + 人工真值 + 可选表格模式**、混合、机器/正式分离）已由真实 receipt 覆盖。**历史表格 FAIL 保留**，不宣称统计级/全类质量通过。
- **done（历史未收口时点）**：LG-037（可选向量）——R7 取到首次完整真实排名（rank 7/10、margin 0.00037），但旧 R5 图片硬门 **FAIL 不变**、无跨模态质量结论（保留）。
- **todo**：LG-041（中文 ASR 质量锁，未解锁）；LG-040 已于本批次收口为 `done`（见上）。
- **LG-032 已 `done`（仅评估范围）**：独立封账 PASS；default 自主协作仍 **off**。契约 `1.11.0`、SDK `0.1.22`。
- 唯一 future block：候选资料服务**仅历史时点健康** + 跨模态质量未验 + ASR 质量门；续接见 [FINAL-CHECKPOINT/RESUME](probes/batch-20261016/FINAL-CHECKPOINT/RESUME.md)。

### 新真实质量证据（集成入 main，链接有效）

- **R4 OCR-scale 机制修复 + 有界复测**（[REPORT](probes/materials-ocr-r4-20261016/REPORT.md)，merge `575f84a`）：可选 `LIGHTGRAVITY_OCR_SCALE`（缺省 2.0 不变、非法拒绝）；Z2 第 2 页整页 CER 0.2991→**0.2508**、公平段 CER 0.3172→**0.2689** 仍 **> 0.25**、结构未验证 ⇒ **表格质量仍 FAIL**；Z1 印刷页 **0.0423** 通过；ASR/embedding 0 POST。集成说明见 [R4 集成 REPORT](probes/materials-r4-integration-20261016/REPORT.md)。

### 新真实质量证据（2026-10-16 集成入 main，链接有效）

- **retry r2 smoke**（[REPORT](probes/materials-retry-20261016-r2/REPORT.md)，merge `d2f733a`）：3/3 GET 200；2/2 POST；OCR 真实 Z1 **CER 0.0423 PASS**；embedding 768 维 finite；ASR 0 POST。
- **LG-040 gate-prep 独立审计**（[REPORT](probes/lg040/GATE-PREP-20261016/REPORT.md)，merge `ab78f37`）：r2 数字逐项复现；**QA-PLAN 非版本判定**。
- **quality r3 真实质量**（[REPORT](probes/materials-quality-20261016-r3/REPORT.md)，merge `d8edb22`）：16/18 POST；OCR **Z2 表格页 FAIL**；vector Recall@5 1.0 vs lexical 0.7（7 docs/7 queries，仅 indicative）。
- **R3 独立审计 + errata**（[REPORT](probes/materials-r3-audit-20261016/REPORT.md)、[ERRATA-DELIVERY](probes/materials-r3-audit-20261016/ERRATA-DELIVERY.md)，merge `dd1cc37`）：Z2 整页 CER 0.2948 复现、修正段 ≈0.3172 仍 FAIL；R3 段评分器有 bug、结构判据自创；渲染 ~144 DPI 非 300；**负向 top-5 非 ACL 泄漏**；图片向量可调用 ≠ 跨模态质量。

### 仍缺/未达标（不称全通过）

- **LG-040 未执行、未就绪**：单列印刷页 PASS，但**表格页 FAIL、混合 born-digital+扫描类缺失、跨模态检索质量未验**。
- **LG-041 阻塞**：真实 ASR 不可用/质量门未过。
- LG-037 负向 false hits 需报告，但**不以此关闭跨模态质量、不在同一 7 查询上校准阈值**。服务仅**记录时点健康**，非未来承诺。

本目录的任务是**开发 LightGravity Bot 的工作**，与未来产品的 Task/Run/Member 文件及 `lightgravity.bot/v1` 完全分开。

## 排期与执行原则

- [滚动排期](docs/06-roadmap.md)：按验收门推进，未承诺日历日期。
- P0：核心接口、SDK 风险与最小可操作闭环；P1：首版工作入口与设置、恢复和完整质量门。优先级不是权限，不代表依赖可跳过。
- 计划保持 todo；实际执行再 claim/更新状态。ready 是候选快照，不能作为任务已被领取或可自动后台执行的证据。
- 每项任务正文有验收与证据要求；未解决重要失败不置 done。

## A. 基础与探针

- [LG-001 冻结首版接口与状态契约](backlog/tasks/LG-001.md)
- [LG-002 建立可运行工程骨架](backlog/tasks/LG-002.md)
- [LG-003 验证 Antigravity SDK 核心能力](backlog/tasks/LG-003.md)
- [LG-004 实现 Markdown 事实源与可靠写入](backlog/tasks/LG-004.md)
- [LG-011 实现左侧导航与统一前端壳层](backlog/tasks/LG-011.md)

## B. 最小真实闭环

- [LG-005 实现角色与 SDK 资源配置编译](backlog/tasks/LG-005.md)
- [LG-006 实现 Antigravity Executor Adapter](backlog/tasks/LG-006.md)
- [LG-007 实现常驻消息路由与 Task 队列](backlog/tasks/LG-007.md)
- [LG-008 实现自动组队与依赖调度](backlog/tasks/LG-008.md)
- [LG-009 实现产物验证与人工验收](backlog/tasks/LG-009.md)
- [LG-010 验收最小真实开发闭环](backlog/tasks/LG-010.md)
- [LG-012 实现查询 API 与持久事件订阅](backlog/tasks/LG-012.md)

## C. 工作入口与设置

- [LG-025 实现模型设置与凭证后端接口](backlog/tasks/LG-025.md)
- [LG-026 实现底部 Settings 与模型接入页面](backlog/tasks/LG-026.md)
- [LG-013 接入 Task Chat 与真实看板](backlog/tasks/LG-013.md)
- [LG-014 实现 Files 与任务证据预览](backlog/tasks/LG-014.md)
- [LG-015 实现 Team 与 Resources 管理视图](backlog/tasks/LG-015.md)

## D. 恢复与质量

- [LG-016 实现暂停取消与中断恢复](backlog/tasks/LG-016.md)
- [LG-017 实现独立 QA 与有限返修](backlog/tasks/LG-017.md)
- [LG-018 实现隔离 worktree 与并行整合](backlog/tasks/LG-018.md)
- [LG-019 完善网页通知与断线重连](backlog/tasks/LG-019.md)
- [LG-020 实现启动检查与本地分发入口](backlog/tasks/LG-020.md)

## E. 首版验收

- [LG-027 验收模型设置与凭证生命周期](backlog/tasks/LG-027.md)
- [LG-021 完成前端状态与响应式验收](backlog/tasks/LG-021.md)
- [LG-022 执行首版端到端与故障验收](backlog/tasks/LG-022.md)
- [LG-023 完成单 agent 对照评估](backlog/tasks/LG-023.md)
- [LG-024 整理首版交付文档与发布准备](backlog/tasks/LG-024.md)

## F. 去中心化协作版本

- [LG-028 冻结去中心化协作契约](backlog/tasks/LG-028.md)
- [LG-029 实现任务发现与原子领取租约](backlog/tasks/LG-029.md)
- [LG-030 实现受控同伴交接与上下文传递](backlog/tasks/LG-030.md)
- [LG-031 整合去中心化执行与验证返修闭环](backlog/tasks/LG-031.md)
- [LG-032 验收去中心化版本并比较全生命周期成本](backlog/tasks/LG-032.md)

## G. 资料接入与 Embedding 版本

- [LG-033 冻结资料摄取与检索接口契约](backlog/tasks/LG-033.md)
- [LG-034 实现原件接收与可恢复摄取作业](backlog/tasks/LG-034.md)
- [LG-035 接入图片和 PDF OCR 与正式内容版本](backlog/tasks/LG-035.md)
- [LG-036 实现可重建词法索引与来源核验](backlog/tasks/LG-036.md)
- [LG-037 接入 EmbeddingGemma 2 可选多模态向量索引](backlog/tasks/LG-037.md)
- [LG-038 打通 Chat 资料接入与 Files 归档检索体验](backlog/tasks/LG-038.md)
- [LG-039 验证中文语音转写后端与质量](backlog/tasks/LG-039.md)
- [LG-040 集中验收资料接入与 Embedding 版本](backlog/tasks/LG-040.md)
- [LG-041 质量达标后接入中文转写与音频来源索引](backlog/tasks/LG-041.md)

## H. 共享团队版快速原型

- [LG-050 共享团队聊天与简单认证 MVP（命名里程碑）](backlog/tasks/LG-050.md)

## I. 连接接入与弹窗版本

- [LG-104 简化Provider接入与Antigravity SDK支持对齐版本](backlog/tasks/LG-104.md)
- [LG-105 SDK认证与应用能力调查](backlog/tasks/LG-105.md)
- [LG-106 简化Provider前端候选](backlog/tasks/LG-106.md)
- [LG-107 取消全局调用上限](backlog/tasks/LG-107.md)
- [LG-108 修复重复连接测试额度](backlog/tasks/LG-108.md)
- [LG-109 Provider配置与草稿测试后端](backlog/tasks/LG-109.md)
- [LG-110 连接列表与新增编辑弹窗](backlog/tasks/LG-110.md)
- [LG-111 串行集成候选](backlog/tasks/LG-111.md)
- [LG-112 独立版本验收与本地交付](backlog/tasks/LG-112.md)
- [LG-113 修复连接引用与删除并发完整性](backlog/tasks/LG-113.md)
- [LG-114 集成并发修复](backlog/tasks/LG-114.md)
- [LG-115 收敛弹窗主字段与说明](backlog/tasks/LG-115.md)
- [LG-116 冻结最终复验候选](backlog/tasks/LG-116.md)

## CLI

当前界面修复批次入口：

- [LG-051 界面可用性与交互修复版本（命名里程碑）](backlog/tasks/LG-051.md)
- [LG-052 修复旧后端运行与兼容性误判](backlog/tasks/LG-052.md)
- [LG-053 修复导航布局、资料搜索与任务对话入口](backlog/tasks/LG-053.md)
- [LG-054 明确并实现个人与团队对话切换](backlog/tasks/LG-054.md)
- [LG-055 串行集成修复并执行独立 Playwright 验收](backlog/tasks/LG-055.md)
- [LG-056 修复并发索引初始化锁竞争](backlog/tasks/LG-056.md)
- [LG-057 修复首轮 Playwright 暴露的界面与用例缺陷](backlog/tasks/LG-057.md)
- [LG-058 阻止 Files 暴露 Personal 私有消息文件](backlog/tasks/LG-058.md)
- [LG-059 修复资料接入后的即时搜索索引更新](backlog/tasks/LG-059.md)

当前机器 PATH 未发现 olav-tasks，可使用已存在的本地构建，不为本次规划安装包：

```bash
node /home/yhvh/code/olav-tasks/dist/cli.js tasks list /home/yhvh/code/lightgravity-bot/backlog --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks ready /home/yhvh/code/lightgravity-bot/backlog --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest /home/yhvh/code/lightgravity-bot/backlog --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot/backlog --json
```

绝对路径是当前开发环境入口，不是产品运行依赖。其他环境使用已安装的 `olav-tasks` 执行同等命令。

> **任务根约定**：本仓库开发任务的**实际根目录是 `backlog/`**（`olav.tasks/v1`，LG 编号），**不是项目根**。
> 对项目根跑 `validate` 会命中历史实验 `probes/agensh-orchestration-r2/runs/**` 既存样例的重复 frontmatter 键，属旧实验、非 backlog 任务。
> 正确命令（2026-10-17 已核 59 tasks / 0 diagnostics）：`node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot/backlog --json`（`digest`/`ready` 同理，根为 `.../backlog`）。

## J. 2026-10-17 用户问题记录与逐项确认

本批先记录与确认，未启动实施；优先级 P1。UI 两项可并行于配置/角色库调查，自动组队依赖角色库。

- [LG-117 补齐 EmbeddingGemma 2 API 设置入口](backlog/tasks/LG-117.md)
- [LG-118 精简 Chat 头部与空态文案](backlog/tasks/LG-118.md)
- [LG-119 补齐 Personal 私有附件与简洁自适应输入框](backlog/tasks/LG-119.md)
- [LG-120 将 agency-agents 角色库默认接入主线 Team](backlog/tasks/LG-120.md)
- [LG-121 接入角色库自动组队并完成真实场景测试](backlog/tasks/LG-121.md)

本批命名里程碑为“Chat 与多任务团队版本”，设计与派工门见 [docs/13](docs/13-chat-and-task-teams.md)。

- [LG-122 接口、容量与派工契约准备](backlog/tasks/LG-122.md)
- [LG-123 整合候选的独立版本 QA](backlog/tasks/LG-123.md)

- [LG-124 串行增量集成与冻结QA候选](backlog/tasks/LG-124.md)

- [LG-125 按任务分组的Team界面](backlog/tasks/LG-125.md)（LG121子包）
- [LG-126 自动招募与全局容量/释放](backlog/tasks/LG-126.md)（LG121子包）

- [LG-127 Gitea与GitHub开发快照提交推送](backlog/tasks/LG-127.md)

- [LG-128 完整验收候选同步双远端开发分支](backlog/tasks/LG-128.md)

- [LG-166：英文Reader独立样本实体误识别修复](backlog/tasks/LG-166.md)

- [LG-167：运行上游ASR原版对照](backlog/tasks/LG-167.md)

- [LG-168：部署资料摄取与英文转写UI更新](backlog/tasks/LG-168.md)

- [LG-169：Demo品牌与ASR启用](backlog/tasks/LG-169.md)
- [LG-170：登录与主界面Logo及默认说明](backlog/tasks/LG-170.md)
- [LG-171：CPU运行时与ASR启用](backlog/tasks/LG-171.md)
- [LG-172：Demo独立QA](backlog/tasks/LG-172.md)
- [LG-173：Demo部署与实际转写验证](backlog/tasks/LG-173.md)
