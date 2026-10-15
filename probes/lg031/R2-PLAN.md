# LG-031 R2-PLAN — 等价续接：闭合真实 SDK 两 worker 自主 discovery/claim

owner（等价续接）：`agent:pi-lg031`
branch：`fix/lg031-r2`（基点整合候选 `17abd78`，HEAD `38e257a`）
日期：2026-10-16

## 0. 继承与保护

- 原 `fix/lg031-r1`（`af6640e`，dirty）、`dev/lg031`（`d4c0815`）与全部 worktree/证据原样保留，
  未 reset/clean/覆盖/复制。
- 旧 1.9.0 契约字段/行为保持；本包只做加性接线与修复。

## 1. 真实调用计数核实（不猜、不重置）

以**原始实际转发记录** `probes/lg031/r1_worker_claim_probe.json` 为准：

- R1：2 个真实 worker（各自自主 discovery→claim 成功领取**不同**节点后均撞 proxy 429）+ 1 次
  真实 reviewer = **3** 次真实生成请求。
- 原包：1 次真实 reviewer。
- **累计 LG-031 = 4 / 10；本续接剩余 ≤ 6**（含 worker/发现/claim/peer/review/失败/返修复验）。
- 交接日志 `turn_end=114` / model 响应 224 是**开发 pi 事件**，不是产品 SDK 生成请求。

## 2. 本次要闭合的真实缺口（不是等 032）

R1 的两个真实 worker **已验证**自主 discovery→claim 拿到不同节点，但在同一 worker turn 内
连续真实请求超过 per-worker proxy 预算被 429；且核心 `graph.py` 自主路径存在**先于执行**的
claim 检查导致永远失败（未完成项）。

本 R2 必须：

1. **修核心计数器**：把 per-worker proxy 预算换成**进程共享**的真实硬上限
   （`GenerationCounter` 注入 executor + 默认 bootstrap 装配），先离线证明跨 worker/会话
   **不归零**，再实测。
2. **修真实配置/能力匹配**：自主路径的 plan 校验必须与真实最小队伍一致（catalog 需同时含
   `implementation` 与 `verification`），不删关键断言、不绕验证。
3. **修自主 claim 时序**：worker 在**自己的执行内**通过受限工具请求领取；程序在执行结束后、
   revoke 前校验「确实自主领取了授权节点」，未领取的结果不得被承认。
4. **程序权威**：worker 只能请求，程序只授权**该 worker 被排度的节点**；越权/预算/身份失败
   一律确定拒绝并记机器理由。
5. **真实最小样本**：2 个真实 SDK worker（各自独立真实 git worktree）+ 1 次独立 ModelReviewer，
   受控带 hash 交接、旧证据保留、机器门+独立复核。
6. 默认关闭/旧确定性回退保留；grant 只由程序冻结注入、不入 prompt/日志/仓库；过期≠停止、
   旧 fence 不可写、未知副作用 `recovery_required` 不重放。

## 3. 预算（硬限，共享持久）

- 本续接真实生成请求 **至多剩余 6**（经审计若更少按更少）。
- 计划实际 HTTP 生成请求：worker A + worker B + reviewer = **3**（返修若触发用确定性
  reviewer，0 真实请求）。
- **进程共享** `GenerationCounter(limit=MAX_CALLS)`，env `LIGHTGRAVITY_MAX_GENERATION_CALLS`
  固定本包硬上限；转发前计数，全 role/session/stage 不归零。
- SDK/API 重试 **0**；输出总 ≤10000 tokens；单 HTTP ≤120s；并发 ≤2。
- usage 未知记 `unknown`，不估零；不打印/落盘 key/secret/grant。

## 4. 验收（真实硬条件）

1. ≥2 真实 SDK worker，各自独立 worktree；
2. worker 自主 discovery→claim（工具调用事件链：真实模型请求→工具→结果）；
3. 程序验证身份/能力/依赖/预算并原子授权 + lease/fencing；
4. 受控带 hash 同伴交接；
5. 最终候选独立 ModelReviewer + 机器门；失败有界返修/复验；旧证据保留；
6. 默认关闭/回退保留；身份只由程序冻结注入；worker 无全局管理 token。

## 5. 非目标

- 不造通用调度平台、不常驻模型编排 agent、不开 SDK 无限委派；
- 不碰 `sources/lexical/vectors/frontend`（已集成，非本包返修范围）；不碰 022 worktree；
- 不 push/部署/发布；不重跑原已成功 review 单点；不扩原 10 上限。

## 6. 通过判定

真实硬条件全部满足 ⇒ LG-031 置 `done`（待 LG-032 独立集中 QA），不因“032 未跑”循环。
缺任一实证 ⇒ 保持 `in-progress` 并具体说明缺哪条，保留 partial/失败与具体缺口。
