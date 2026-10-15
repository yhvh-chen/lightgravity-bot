# LG-022 独立复验 R1 — STATUS

- 状态：**FAIL / 未达成功门**（决定性命中：真实主链停在 `verifying`，stop gate 死锁）。
- 复验 owner：本包（非 LG-022 R1 返修者、非集成者）；主代理只 PM。
- 候选：`qa/lg022-r1` @ `ec2420e`（= `integrate/batch6` 整合候选 `9698e8a` 的产品树；契约 `1.9.0`）。
- 报告：同目录 `REPORT.md`（含最小复现、真实快照、控制组、逐门裁定）。
- **LG-022 保持 `in-progress`**：真实全部门未满足，不得记为 done，也不得因 R1 单点成功宣全产品通过。
- 真实预算：本 phase 已用 **6/10**，剩余 **4**；本续接收尾 **0** 真实请求（仅本地确定性探针）。
- 旧 phase 真实调用：**unknown**（单列，未 reset）。
- 需返修（交主代理另派）：① `verify/stopgate.py` + 成功 Run 的 session 停止/`cleanup=done` 生命周期（阻断验收门）；
  ② `adapter/proxy.py::GenerationCounter` 跨重启持久化（计量硬门）。
- 本包未改产品代码、未手改状态、未绕过验收；QA 脚本导入缺陷（`CancelResult` 缺 `state`）已在 `harness/deterministic_probe.py` 修正。
