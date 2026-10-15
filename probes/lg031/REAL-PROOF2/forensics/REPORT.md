---
title: "LG-031 REAL-PROOF2 — 0 真实生成 forensics（旧 24 归因，只读）"
doc_type: report
category: engineering
owner: "LG031 REAL-PROOF2 owner"
branch: "dev/lg031-real-proof2"
base: "dev/lg031-real-proof@b819dd3"
updated: "2026-10-16"
real_generation: 0
---

# LG-031 REAL-PROOF2 — 旧 24 归因 forensics

> **只读**。本包产品真实生成 **0**。仅读取旧 proof 已持久化的 event/SoT/ledger；**未**扫描无关/tmp 用户数据；
> **未**打印 prompt/headers/tool 参数/凭证/敏感 body；**未**改动旧 Repo；**未**重放任何旧 Run 副作用。

## 1. 输入（旧 proof 已持久原件，只读）

| 原件 | 路径 |
|---|---|
| 旧持久物理账本 | `REAL-PROOF/fixtures/formal/data/generation/generation.jsonl`（24 条 `reserved`） |
| 旧脱敏 raw 事件 | `REAL-PROOF/fixtures/raw-evidence/formal-real.raw.json`（1144 事件） |
| 旧脱敏摘要 | `REAL-PROOF/evidence/formal-real.redacted.json` |
| 归因脚本（本包新增） | `probes/lg031/REAL-PROOF2/forensics/attribute_old_24.py` |
| 归因输出（本包新增） | `probes/lg031/REAL-PROOF2/evidence/old-24-attribution.json` |

## 2. 归因方法

- 旧账本 24 条条目均为 `reserved`（转发前持久预留），仅含 `count/pid/reserve_id/ts`，**不含** prompt/args。
- 以 `reserved.ts` 对**适配器真实执行窗口**（`adapter.execution_started` → `adapter.execution_finished`）
  做**时间包含**匹配，把每次预留归到 6 个会话（3 选择 slot_0/1/2 + 3 执行 subtask alpha/beta/verify）。
- 归因**可完全对齐**（24/24 落窗、0 unclassified）；窗口互不重叠且相邻，匹配唯一。

## 3. 归因结果（24 次真实生成）

| stage | 会话 | 次数 |
|---|---|---|
| selection | alpha-slot | 5 |
| selection | beta-slot | 3 |
| selection | verify-slot | 4 |
| **selection 小计** | | **12** |
| execute | alpha | 6 |
| execute | beta | 1 |
| execute | verify | 5 |
| **execute 小计** | | **12** |
| **合计** | | **24** |

- **选择/执行分布 = 12 / 12**；verify（第三节点）选择 4 + 执行 5 = **9**，其执行第 6 次请求（工具调用 22 之后）
  在**转发前**被 429 拒绝（`local auth proxy call budget exhausted`），因此 verify 执行未完成 → Run `failed`。
- 每 session 次数均 `< 12`（`max_session=6`）；**per-session cap 12 未触发**。

## 4. 根因判定

- **根因 = 共享 phase 硬上限 24 耗尽**（`ledger_snapshot{count:24,limit:24,remaining:0,persistent:true,corrupt:false}`）。
- **不是** per-session cap（12）触发；**不是**真正 runtime 异常：429 由持久账本在**转发前**拒绝，
  `reserve-before-forward` 与「损坏绝不当 0」行为正确；stop 门 `confirmed=true`、6/6 stopped、proxy stopped。
- 旧工作确实产生了未被消耗的剩余需求（verify 执行只跑了 5 次预留）；属**预注册预算耗尽**，非缺陷。

## 5. 工具/重试可归因性

- 旧事件含 `adapter.tool_call` 22 次（名称集合：`discover_and_request_claim`/`skill_lookup`/`edit_file`/`view_file`），
  可用于**阶段级**计数，但**无法**把每次 `reserved` 精确绑定到某次具体工具调用（账本不记录 tool_call 关联）。
- 因此**工具级/重试级**归因记 **unknown**（不作不可靠推断）；仅 stage/session 级归因可靠。
- SDK retry 设定为 0；旧证据未见额外 retry 条目，但**不**据此宣称「0 重试」为已证事实（记 unknown）。

## 6. 对真实 runtime 的结论

- **未发现重要 runtime 缺陷**。无需最小 repro 交 PM；本包**不自修行为**，按预注册继续真实采样。
- 唯一旧缺口（verify 执行 429）由**共享 cap 24** 引起，本包以**同门 + 上限 48**复验，不改产品。

## 7. 边界

- 本 forensics **不恢复/不修改**旧 failed Run 状态；旧 Run/ledger/worktree/diff 原样保留。
- 旧「无 SDK DB，`save_dir` 没设」事实**准确保留**；本包 observability 差异见 `PLAN.md` §4。
