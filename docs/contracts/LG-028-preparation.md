---
title: "LG-028 去中心化协作契约准备稿（未冻结）"
doc_type: preparation
category: architecture
status: draft-preparation
updated: "2026-10-16"
---

# LG-028 去中心化协作契约准备稿

> **性质：准备稿，非契约冻结。** 本文件不修改也不替代 [docs/08 接口契约](../../docs/08-interface-contract.md)，
> 不升 `CONTRACT_VERSION`（当前 `1.5.0`），不定义已冻结语义。正式冻结必须由 LG-028 实施者按 docs/08 §13
> 变更控制升版并处理共享契约冲突。本文件仅供 LG-028 后续派工参考。

## 1. 目标与边界

- 目标：把 worker 自主发现、原子领取/租约、受控同伴交接的**产品边界**收敛为可实施协议，**不重新引入常驻模型编排 agent**。
- 保持：程序 Coordinator/Scheduler/Store 仍是控制与权限权威；文件 SoT + JSONL 历史不变；预算、权限与人工验收门不变。
- 不做：外部聊天渠道、多租户、全邮箱同步、自主触发；不把模型提议直接授予控制状态写入权。

## 2. 待冻结协议面（候选，未冻结）

1. **可发现任务范围**：哪些 Task/Subtask 对 worker 可发现；能力匹配维度（capability/role/skill）与过滤规则。
2. **候选领取请求**：worker 只能提出请求，不直接写控制状态；程序执行原子授权。
3. **租约语义**：`lease_expires_at`、过期 fencing、并发领取冲突、撤销；与既有 Subtask 字段（docs/08 §6.3）关系。
4. **暂停/取消/崩溃恢复**：与 LG-016 恢复语义对齐；未知副作用不自动重放；幂等交接键。
5. **受控同伴交接**：请求协议、共享产物引用、权限范围与总预算；禁止私建无限委派与绕过验收。
6. **版本化接口、事件、开关与兼容迁移计划**：实施前按 docs/08 §13 升版。

## 3. 与既有契约的衔接点（只读引用）

- docs/08 §6.2 Run（`plan`/`plan_hash`/`plan_source`）、§6.3 Subtask（`capability`/`key`/`owner`/`lease_expires_at`/`blocked_by`）。
- docs/08 §6.4 Member（`connection_pin`、config 漂移语义）。
- docs/02 Task 与 SDK 资源契约；docs/04 Bot 行为（消息、队列、停止、通知、验收）。
- LG-016 恢复反重放边界：完整 checkpoint skip **尚未实现**，不得在契约中夸大。

## 4. 验收条件对应（来自 backlog/tasks/LG-028.md）

- [ ] 可发现范围、能力匹配、候选领取请求、程序原子授权、租约及撤销语义
- [ ] 并发领取冲突、过期 fencing、暂停取消、崩溃恢复、幂等交接
- [ ] 受控同伴请求/共享产物协议、权限与总预算
- [ ] 版本化接口/事件/开关与兼容迁移计划

## 5. 明确不做（本准备稿）

- 不改 docs/08，不改 `CONTRACT_VERSION`，不新增 API/schema/事件。
- 不实现代码，不跑模型调用，不提交产品行为变更。
- 不在本文件中冻结字段名或枚举。
