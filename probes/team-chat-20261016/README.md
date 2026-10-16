# LG-050 共享团队聊天与简单认证 — 调查与实施证据

来源与版本：本目录文件由 LG-050 串行集成执行者在**独立 worktree**
`/tmp/lg-team-integration-20261016`（分支 `feat/team-integration-20261016`）产出。
无密钥、无账号口令、无 `.env` 内容；不含真实产品模型调用。

- 基线：`main` `0ecfec8`（PM/docs 提交，已冻结 `docs/08` §14 与契约 `1.13.0`）。
- 后端源：`feat/team-backend-20261016` @ `1df7310`。
- 前端源：`feat/team-frontend-20261016` @ `26dc6f4`。
- 临时接口约定：本目录 [interface-20261016.md](interface-20261016.md)（开发派工资料，非运行依赖）。

## 文件

| 文件 | 内容 |
|---|---|
| [interface-20261016.md](interface-20261016.md) | 后端/前端并行实施前冻结的临时接口约定（端点、配置、角色矩阵、消息作者与 @bot 路由）。 |
| [backend-execution-report.md](backend-execution-report.md) | 后端执行者交付报告（实现、验证命令与结果、限制）。 |
| [backend-contract-notes.md](backend-contract-notes.md) | 后端对接口的精确偏差/加性登记（`forbidden`、登录限流、logout 幂等、admin-only 范围、SSE 会话存活性、Files 保护等）。 |
| [frontend-execution-report.md](frontend-execution-report.md) | 前端执行者交付报告（登录门、作者、轮询、单元测试与限制）。 |
| [INTEGRATION-REPORT.md](INTEGRATION-REPORT.md) | 串行集成报告：合并、契约同步、局部检查证据、启动命令与已知限制。 |

## 状态

**实现与串行集成完成，独立集中 QA 与真实浏览器验收尚未执行。** 未合回 `main`，未发布/部署，不宣称 QA 通过。LG-050 任务状态未在本目录改动。
