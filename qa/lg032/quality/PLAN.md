# LG-032 阶段 A — 独立机制/语义质量 QA 计划

- 任务：LG-032（QA 阶段 A owner，独立于 LG-028/029/030/031 实施者与集成者）
- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg032`，branch `qa/lg032`
- 基线 HEAD（开工）：`62e96edb01ffcbcea2e401ed4084d2e4d9d9278d`
- 契约：docs/08 `1.10.0`；SDK：`google-antigravity==0.1.22`
- 约束：本包**产品真实 DeepSeek/生成请求 = 0**；不执行成本采样、不写真实 benchmark driver；
  产品代码只读；仅在 `qa/lg032/quality/**` 与必要独立 QA 脚本写新文件；不覆盖旧记录。

## 验收范围（按 LG-028 冻结原文 + LG-031 验收 + LG-032 阶段 A 交接）

1. **竞争/原子授权/身份/fence/脱敏**
   - 跨并发 + 跨进程竞争领取：仅一个获准。
   - 身份 principal 由**程序注入**；请求体自报**不作认证**。
   - capability / scope（Run/Task 边界）约束。
   - fence 拒绝旧 owner 写；receipt 脱敏（无 token/秘密）。
   - 过期租约 ≠ 实际停止；不因 expiry 自动重放未知副作用。
2. **crash/restart/取消/暂停/权限撤销/预算硬拒绝/真实停止再回收**
   - unknown 保留槽与历史；`recovery_required` 反重放；候选与未交付 diff 保留。
3. **受控 peer 提议/交接**
   - hash + 源版本 + 作用域 + 因果引用；篡改拒绝；重复幂等；授权失效拒绝。
   - 程序整合、机器验证 + 独立 review/返修复验生命周期；验收绑定 requirements/candidate/plan_hash。
   - 无常驻模型编排 agent；SDK 内部 delegation 默认关闭；默认旧程序回退可用。
4. **自主语义边界（重点）**
   - 核 program 预先选择了哪些节点、worker 实际 discovery/claim 集合、grant 是否限 `scheduled_node`。
   - 按 LG-028 冻结原文与 LG-031 验收决定「符合 / 不符合」，不夸大也不加组织平台要求。

## 方法

- 只读源码路径审查 + 离线机制探针（真 `FileStore` + 真多进程 flock + 本地 fake SSE，
  明确标注 provider-substitute）+ 少量局部 pytest。
- 不以 Event 假 reviewer 冒充真 SDK；offline 机制证据不代替后续真实样本（阶段 B）。
- 发现重要缺陷：立即持久保存最小 repro/重要性/准确路径/返修建议，不自修自判。
- 局部阻塞时继续其它独立 mechanism 检查，报告未测项。

## 交付

- `qa/lg032/quality/STATUS.md`（每阶段更新）
- `qa/lg032/quality/REPORT.md`（阶段 A 报告）
- `qa/lg032/quality/evidence/**`、`qa/lg032/quality/fixtures/**`、必要独立 QA 脚本
