# LG-031 R1-PLAN — 真实 SDK 多 worker 自主发现/请求领取闭环

owner（等价续接）：`agent:pi-lg031`（原 owner 同人等价续接）
branch：`fix/lg031-r1`（基点 `af6640e`，保留原 `dev/lg031` `d4c0815`）
日期：2026-10-16

## 1. 本次要补的真实缺口（不是等待 LG-032）

INTEGRATION-5 已定：原包“真实 Git + 进程内 fake executor”不等于“真实 SDK 多 worker”。
唯一 1 次真实 DeepSeek 是 **reviewer**，没有证明：

- worker **自主发现 / 提出领取请求**（不是程序选节点代领后附 peer 工具）；
- 程序对**执行身份/能力/依赖/预算**验证并**原子授权** + lease/fencing；
- **受控带 hash 同伴交接**；
- 最终候选**独立 ModelReviewer + 机器门**、失败有界返修/复验、旧证据保留。

本 R1 用**最小真实产品 SDK 闭环**补上以上，必要最小返修；默认关闭/旧确定性回退保留。

## 2. 固定最小真实样本

- **2 个真实 Antigravity SDK worker**（`LocalOpenAIAgentConfig` → loopback 认证代理 → DeepSeek），
  各自**独立 worktree**（真实 Git）。
- 2 个节点：`produce`（写）→ `integrate`（依赖 produce，写）。
- 每个 worker 只拿到**自己**的 pool grant + 受限 `discover_and_request_claim` 工具（+ peer 工具）。
- worker **自己**调用工具发起发现/领取请求；程序认证身份（grant）、校验可发现性/能力/依赖/预算，
  通过 `CollaborationService.request_claim` **原子授权**并 lease/fence + mint 节点 grant。
- 依赖满足后 produce worker 经**受控带 hash 交接**（`PeerService` handoff）→ integrate worker。
- 最终候选由**独立 ModelReviewer** 复核（1 次真实请求）+ 程序机器门。
- 失败 => 有界返修（≤1 轮，确定性脚本 reviewer，不额外真实请求），旧证据保留。

## 3. 预算（硬限）

- 本次**剩余至多 9 次真实 HTTP 生成请求**（含 worker/发现/peer/reviewer/失败/返修复验）。
  计划：produce worker 1 + integrate worker 1 + reviewer 1 = **3 次**；返修若触发用确定性 reviewer
  （0 真实请求）。统一计数，SDK/API 重试 0。
- 输出总 ≤12000 tokens，单 HTTP timeout 120s，并发 ≤2。
- 未知 usage 记 `unknown`，不估零。不打印/落盘真实 key/secret/grant。
- 不重跑原 review 成功探针（`review_real_probe.json` 原样保留）。

## 4. 验收（真实硬条件）

1. ≥2 真实 SDK worker，各自独立 worktree；
2. worker **自主**发现/提出领取请求（工具调用事件链证明：真实模型请求 → 工具 → 结果）；
3. 程序验证身份/能力/依赖/预算并**原子授权** + lease/fencing（竞争只有一个赢家）；
4. 受控带 hash 同伴交接；
5. 最终候选独立 ModelReviewer + 机器门；失败有界返修/复验；旧证据保留；
6. 默认关闭/旧确定性回退保留；执行身份只由程序冻结注入；grant 不进提示词/日志/仓库；
   worker 无全局管理 token；过期≠停止，旧 fence 不可写，未知副作用 `recovery_required` 不重放；
   实际停止后才回收权限；
7. Task 总预算含 review/repair/failures。

## 5. 通过判定

真实硬条件全部满足 ⇒ LG-031 可置 `done`（待 LG-032 独立集中 QA），不因“032 还没跑”循环。
缺任一实证 ⇒ 保持 `in-progress` 并具体说明缺哪条。

## 6. 非目标

- 不造通用调度平台、不引入常驻模型编排 agent、不开启 SDK 无限委派；
- 不碰 `sources/lexical/vectors/frontend/API-sources`（独立 037/038 线）；
- 不改 `app.py` 最新 search 挂载；不碰 022 独立 QA worktree；不 reset/clean/删旧 worktree；
- 不 push/部署/发布。
