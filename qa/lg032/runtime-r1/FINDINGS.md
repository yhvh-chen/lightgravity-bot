# LG-032 返修复验 R1 — FINDINGS

- 更新：2026-10-16
- owner：独立复验 QA（非 F1/F2/整合实施者）
- 基线：`integrate/lg031-runtime@afcae82` + merge `main@66b2b10`
- 产品真实生成请求：**0**；所有 SDK 探针为真 SDK 0.1.22 + 本地受控 fake loopback 上游（provider-substitute）

## 结论

四门独立复验**未发现阻断级产品缺陷**（no blocking defect）。门1/门2/门3/门4 均 PASS。
记录 **3 项观察（O1–O3）**，非阻断、非负收益代质量失败，交 PM/实施 owner 决策，QA 不自修。

## O1（门2，观察，非缺陷）— 同一 Runtime 内 `lease_owner` 为 worker 实例（dispatcher），两 member 同 owner

- **事实**：`coordinator/graph.py` 冻结 `self._owner = owner or f"graph-dispatcher:{os.getpid()}"`；池路径 `_claim_for_worker_pool`
  以 `owner=self._owner` 请求租约，铸 node grant 时 `lease_owner=self._owner`。故**同一 `GraphDispatcher` 内所有 slot 共享同一 lease owner**。
- **可观察证据**（`evidence/gate2b-race.json` → `single_dispatcher_race`）：同一 dispatcher 对同一 node 的两次并发 claim，
  结果为 `granted` + `already_owned`（幂等回放，`fence` 均 1，final fence=1），**无双真实授予、无双写、无双 fence 递增**。
- **对照任务口径**：任务要求“两 worker 同时请求同 node...不能共同 coordinator.owner 被当相同 worker 而双赢”。
  实测**未双赢**（第二者只是幂等 `already_owned`，不产生第二次副作用）。但 lease owner 粒度是**worker 实例（dispatcher）而非 member**，
  同 dispatcher 内两个不同 `member_ref` 在租约权威侧不可区分。因池路径按 `assignee_member_ref` 把候选限定给成员，跨 member 同 node 竞态
  在产品构造下不发生；跨 member 命名他人 node 被 `node_not_in_candidate_pool` 拒绝（`cross_member_node_refused`，目标 node 保持
  `pending`/`owner=null`，无冒用）。
- **判定**：**非缺陷 / 观察**。契约 §6.5（afcae82）明确将 `lease_owner` 定义为“worker 实例身份”，与实现一致；且不产生双写。
  建议（交 PM）：若后续要求“两 worker 同 node 恰好一 winner 且 loser 为 definite refusal”，可在 member 维度细化 `lease_owner`；
  当前不做产品修改（QA 不自修）。

## O2（门3，观察，非缺陷）— reviewer proxy 共用同一持久账本已正面证明

- 源读取曾疑 `verify/review.py::run_review_turn` 自建 `LocalAuthProxy` 未传 `generation_budget` ⇒ 疑绕过共享账本。
- **复核更正**：`adapter/proxy.py::LocalAuthProxy.__init__` 在未显式传 `generation_budget` 时**默认**回退到进程全局
  `_default_generation_counter()`；产品启动 `api/bootstrap.py:404` 调 `configure_generation_ledger(settings.data_dir)` 把该全局计数器
  绑定到受控 dataRoot 的持久账本。故 reviewer 与 worker/executor **共用同一物理持久账本**。
- **可观察证据**（`evidence/gate3b-reviewer-ledger.json`）：账本 `limit=1`；worker 真实转发 1 次（计数 1）；随后真实 reviewer turn
  的请求被**转发前拒绝**（`reviewer_forwarded=0`，`reviewer_refusal=... 429 local auth proxy call budget exhausted`），
  `reviewer_shares_shared_ledger=true`。
- **判定**：**非缺陷 / 正向确认**（原疑点被独立证伪）。此探针在 QA harness 内以 loopback-allowing 子类替换 reviewer 代理的
  **上游主机策略**（产品源码未改、明确标注），不影响账本结论。

## O3（门4，咨询项，非阻断）— 契约 §13 对 `body.owner` 语义放松的分类

- **变更事实**（afcae82）：`discoverable`/`claim_requests`/`lease/renew`/`lease/release` 四端点改为从程序冻结 grant 推导
  principal/scope/fence；请求体 `owner` 由“端点采用 body owner”变为**兼容可选、非授权**。§13 记一行“**无版本变化**”。
- **§13 规则**：新增向后兼容字段/事件为 MINOR；**改字段语义**/枚举/状态迁移/删除端点为 MAJOR。
- **核判**：1.6.0 冻结原文（§2.4 的 LG-028 推导 + §4.3 note「不接受浏览器直接指定任意 `owner`」）**本就要求授权不依赖 worker 自报身份**。
  故 afcae82 是**实现对齐既有冻结语义**，而非改变冻结语义；`ExecutionGrant.lease_owner` 是**进程内非持久**内部 dataclass 字段，
  非 HTTP/实体 schema 字段，不进入契约版本。按“冻结语义未变”读法，`无版本变化`**可辩护且与 §13 自洽**。
- **保留意见**：该行把(a)内部加性字段与(b)**公开请求字段**的授权语义放松合并记为一处“无版本变化”。若按“公开字段语义变化即 MINOR”的
  严格读法，建议单独 MINOR 行或至少在 §4.3 端点表明确标 `owner` 为 compat-only（§4.3 注释已部分如此）。
- **判定**：**非阻断咨询项**。既未机械强升，也未忽略公开 schema 变化（变更已在 §4.3 与 §13 显式记录）；交 PM/契约 owner 定分类口径。

## 未测 / 限制

- 正式真实 DeepSeek provider 端到端**未做**（本包产品真实生成 0）；本包 SDK 探针为 provider-substitute，worker “选/写哪个文件”由
  本地 fake 上游脚本化，**不冒充**真实 DeepSeek 自主选择。
- 完整 checkpoint skip 未实现（既有真实限制）；真实 Git worktree 非 OS 安全沙箱。
- 真 SDK scripted fake 只证机制，不叫真实 DeepSeek 自主选择；LG-031 真实 provider 硬条件仍未闭合。
- 未重跑前端矩阵（未改 UI）。
