# LG-031 REPORT — 去中心化执行与验证返修闭环整合

owner: `agent:pi-lg031` ｜ branch `dev/lg031` ｜ base `e4cef4a` ｜ 日期 2026-10-16

## 1. 目标与结论

把自主发现/程序原子授权领取、lease/fencing、受控同伴交接接入 Antigravity SDK worker 执行、
真实隔离候选、独立模型复核/有限返修闭环，且**不能仅凭 HTTP + body 自报 worker 身份**。
主代理不接手代码；程序仍控制 scope/权限/状态/预算/验收；无常驻模型编排 agent；
SDK 内部无限委派关闭。**结论：实现完成，待版本 QA（LG-032）**，不自评整体 pass。

## 2. 交付

见 `probes/lg031/INTEGRATION.md`。核心：程序冻结的不透明 execution grant（非全局管理 token）、
受限进程内同伴工具、仅头部认证的身份解析、fenced 领取接线、三开关读写、bootstrap 装配。

## 3. 验证（真实退出码）

| 检查 | 结果 |
|---|---|
| `uv run mypy` | Success, 125 files |
| `uv run pytest -q` | 665 passed, 4 skipped（连续两次一致） |
| 真实 Git 两 worker / 合并 / 冲突暂停 | `tests/collaboration/test_lg031_real_workers.py` 3 passed |
| 身份伪造 / 竞争 / 过期 / 旧 fence | `test_lg031_integration.py` 11 passed |
| 最终候选独立 review + 有界返修 | `test_lg031_review_closure.py` 3 passed |
| 开关读写/回落 | `test_lg031_switches.py` 4 passed |
| 真实模型（装配后 reviewer 角色） | 1 次 DeepSeek 调用，`reviewer_kind=model`/`outcome=passed`/`validated_outcome=passed` |

## 4. 成本（含执行/review/repair/recheck/failures，不预设节省）

- **产品真实 DeepSeek 调用：1 次**（独立 reviewer 单轮，`probes/lg031/review_real_probe.py`），
  输出 tokens **未知**（`usage={"unknown":["usage"]}`，**不当 0**）。SDK 模型重试 0；
  单请求 timeout 120s；并发 1。未用假工具调用或伪造成功。
- review 次数 1；repair/recheck 由确定性测试覆盖（无真实模型），failures 0 次真实模型失败。
- 无返修轮真实模型消耗（确定性返修测试用脚本 reviewer；真实 rework 模型调用归 LG-032 集中对比）。
- 未做与程序调度基线的全生命周期对比；样本/费用上限由 LG-032 在实验前固定。

## 5. 限制与缺口（不夸大）

- 真实 SDK **多 worker 端到端**运行未在本包执行（用真实 Git + 进程内 fake executor）。
- 完整 checkpoint skip 未实现；恢复仅依赖已落盘证据。
- 独立集中 QA（LG-032）与全生命周期成本对比未做，本包不自评版本通过。
- 已知非本包缺陷：`test_claims.py::test_two_owner_race...` 完整套件中偶发 `not_discoverable`
  （既有 discovery/lease 原因竞争），单跑与两次全量通过；未改 LG-029 已验收测试。

## 6. 默认回退

`decentralized_claim_enabled`/`collab_requests_enabled` 任一关闭（或缺省）⇒ 图调度走确定性
`plan_source=rules` 路径、不领取 fenced 租约、不附加任何自定义工具；SDK 内部委派仍关闭。
