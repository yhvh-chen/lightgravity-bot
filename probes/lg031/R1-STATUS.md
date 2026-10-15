# LG-031 R1-STATUS（持久）

owner：`agent:pi-lg031`（等价续接）
branch：`fix/lg031-r1`
基点：`af6640e`（本轮整合 main）；保留原 `dev/lg031` `d4c0815`

## 状态

**in-progress**（R1 进行中）。目标：补真实 SDK 多 worker 自主发现/请求领取闭环。

## 真实请求计数（统一硬限）

- 原任务总上限 10；原包已用 1（reviewer）；**本次剩余至多 9**。
- 本次计划实际 HTTP 生成请求：produce worker 1 + integrate worker 1 + reviewer 1 = 3。
- 已用（本次）：见 R1-REPORT；每步更新。

## 缺口语义（不得弱化）

- 执行身份仅由程序冻结注入（grant 不进模型提示词/日志/仓库）；worker 无全局管理 token。
- 过期≠停止；旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
- 默认新路径关闭/旧确定性回退保留。

## 产出（本次）

- `backend/lightgravity/collaboration/execution_grant.py`：新增 worker 自主发现/领取请求受限工具。
- `coordinator/graph.py`：worker-pool 自主领取接线（加性）。
- `probes/lg031/R1_*`：真实 SDK 两 worker 样本 + 证据。
- `probes/lg031/R1-REPORT.md`：真实每 worker/交接/候选 review/调用与未测边界。
- 相关 tests。
