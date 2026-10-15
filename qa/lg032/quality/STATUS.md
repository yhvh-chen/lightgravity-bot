# LG-032 阶段 A — STATUS

- 更新：2026-10-16
- owner：独立 QA（LG-032 阶段 A），非 028/029/030/031 实施/集成者
- 基线 HEAD：`62e96ed`（branch `qa/lg032`，开工 clean）
- 产品真实生成请求：**0**（本包全程）
- 契约 `1.10.0` / SDK `0.1.22` / 自主模式默认 off（未改）

## 阶段进度

| # | 检查项 | 状态 |
|---|---|---|
| 0 | 开工核对（main/claim/Git/worktree/dirty/文档） | DONE |
| 1 | 竞争/原子授权/身份/fence/脱敏 | DONE（PASS；F2 端点身份缺口） |
| 2 | crash/restart/取消/暂停/权限撤销/预算/回收 | DONE（PASS；F3 可接受） |
| 3 | peer 提议/交接 hash/幂等/篡改/授权失效 | DONE（PASS） |
| 4 | 程序整合/机器验证/独立 review/返修复验/验收绑定 | DONE（离线 PASS；真 SDK 见 031 探针未重跑） |
| 5 | 自主语义边界（program 选点 vs worker discovery/claim/grant scope） | DONE（F1 部分符合） |
| 6 | 默认关闭回退 / 无模型编排 / SDK delegation off | DONE（PASS） |
| 7 | 事件可重放 / 重启不重复副作用 | DONE（PASS） |

## 当前结论

- **阶段 A 门：partial**（核心机制 PASS；F1 部分符合、F2 需返修后复验）。
- **LG-032 整体仍 in-progress**：阶段 B 真实同门成本对照未执行、未预注册收益。
- 详见 `REPORT.md`、`FINDINGS.md`、`evidence/**`。
- QA 不自修、不自判 done；F1/F2 返修由 PM 另派实施 owner。

## 产出（本轮，全部新建，未覆盖旧记录）

- `PLAN.md`、`STATUS.md`、`FINDINGS.md`、`REPORT.md`
- `probe_multiprocess_race.py`、`probe_autonomy_boundary.py`、`probe_discovery_multicandidate.py`、`probe_node_preselection.py`
- `evidence/{multiprocess-race,autonomy-boundary,discovery-multicandidate,node-preselection}.json`、`evidence/local-pytest{,-broad}.txt`
- `fixtures/{race,autonomy-boundary,multicandidate,preselection}/work/**`（持久目录，非 TemporaryDirectory）
