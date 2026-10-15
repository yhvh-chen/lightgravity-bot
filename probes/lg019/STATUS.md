---
title: "LG-019 实施进度（pi-lg019）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# LG-019 持久通知 / 事件游标重连 / 版本定位 — 实施进度

只读核对用；细节证据与限制在 `probes/lg019/reports/`。

## 步骤

- [x] 读 AGENTS/agent/PROJECT/PROGRESS/BACKLOG/docs06/docs08/09/design；rg 定位 docs08 事件/通知/版本回复段。
- [x] 勘查现有 events.py / eventbus.py / api/app.py / coordinator 事件投影边界。
- [x] 后端 `notifications/**`（投影 + 持久 read/read 状态 + 版本定位 + 过期回复守卫）。
- [x] `api/notifications.py` 路由 + `api/app.py` 最小装配（import 通过，路由已挂）。
- [x] 前端 api/notifications client + cursorStore + useNotifications/useEventStream store + 壳通知组件真实接线。
- [x] 前端 typecheck/build 通过；前端 12 files / 81 tests 通过。
- [x] 后端测试 + mypy：97 files mypy clean；全 pytest 490 passed / 1 skipped；前端 12 files / 81 tests 通过。
- [x] 真实 uvicorn HTTP/SSE 断开续游标冒烟（probes/lg019/evidence/sse-smoke.json，ok=true）。
- [x] Firefox BiDi 壳通知冒烟（evidence/shell-smoke.json，ok=true，firefox/156.0.1）。
- [ ] INTEGRATION.md / 精确 commit（记录 HEAD/基点/checks/集成点/限制）。

## 关键约束

- 事件先落盘后广播（已有 BroadcastingStore）；通知基于 durable 事件投影，不侵入 coordinator/service.py。
- 用户明确：本包产品真实模型调用预算 0；不使用 sleep 盲等。
