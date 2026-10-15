# LG-032 返修复验 R1 — 独立复验 PLAN

- 任务：LG-032（返修复验 R1；owner：独立 QA，**非** F1/F2/整合实施者，无嵌套派工/推送/部署/发布；主代理仅 PM）
- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-runtime-r1`，branch `qa/lg032-runtime-r1`
- 基点：`integrate/lg031-runtime@afcae82`；安全 merge `main@66b2b10`（非产品，仅 LG-023 评估证据/PROGRESS/backlog）
- 契约：docs/08 `1.10.0`；SDK：`google-antigravity==0.1.22`；自主模式默认 off
- **本包产品真实 DeepSeek/生成请求 = 0**；所有 SDK 模型测试只走**本地受控 fake 上游**（provider-substitute）；
  子进程用受控 dummy 凭证且连接全 roles 强制 loopback，确保无真实 reviewer 触达默认 DeepSeek。
- 文件 owner：仅 `qa/lg032/runtime-r1/**` 与必要独立 QA 脚本；**产品与共享 docs 只读**；**不自修、不自判 done**。

## 1. 输入（已读，事实核对）

- AGENTS/agent/PROJECT/PROGRESS、docs/06、docs/08。
- LG-029/030/031/032 任务卡；`qa/lg032/quality/{REPORT,FINDINGS,STATUS}`（阶段 A：F1 partial / F2 FAIL / F3 可接受）。
- `lg031-runtime@afcae82` 的 `probes/lg031/RUNTIME-AUTH-INTEGRATION/{REPORT,PLAN,STATUS}` + `probe_two_phase_sdk.py` + `evidence/two-phase-sdk.json`。
- F1 `fix/lg031-pool@f2741bb`（POOL-FIX）、F2 `fix/lg029-auth@388f6fa` 边界（PAUSE-HANDOFF/WIP）；LG-031 历史授权边界（R1/R2/R3/phase4）。
- 已验 core stream QA（`qa/lg022-stream`，分支 `qa/lg022-stream`）。

## 2. 开工核对（真实）

- 全部 Git worktree/branch/dirty 保全：`lg031-r1` dirty=8、`/tmp/*experiment*` dirty、`/tmp/no-orchestrator-*` dirty；未 reset/clean/覆盖/重复 pick。
- 真实进程：8123 uvicorn（pid 3320750）、olav-os CLI、open-webui、其它长期 uvicorn——均不触碰。本包只精确清本包签名进程。

## 3. 候选与合并（准确）

- 新 worktree 基于 `afcae82`；`git merge --no-ff 66b2b10`。
- 核对：`git diff afcae82 HEAD -- backend frontend docs tests pyproject.toml uv.lock Makefile` **为空** ⇒ 产品/契约/测试树逐字节同 afcae82。
- main-only 非 probe 变更仅 `PROGRESS.md`、`backlog/tasks/LG-023.md`、`LG-024.md`；未合入任何未验 source。

## 4. 复验关键门（用户指令）

1. **真实 SDK 两阶段**：`build_runtime`/`Graph`/`AntigravityExecutor` + 真 SDK 0.1.22 + 本地 fake 上游；
   同 capability 两 ready 节点、两**不同 member_ref 的 worker**（同权限 profile）在**同一个 Runtime/GraphDispatcher** 内工作；
   worker 能选非首项/非旧预绑定 node；选择期无写工具；执行期真实 SDK 绑定**所选**隔离 workspace/objective/upstream；
   A/B 产物/manifest/状态不串；选别 node 不扩大原 caller 工具/写 scope/connection pin，不冒用另一 member 身份。
2. **竞争/身份**：同 Runtime 两 worker 同时请求同 node，只 1 winner/fence 正确，loser 有界重新发现剩余合法节点；
   HTTP discover/claim/renew/release 无身份/无配置 default-deny 且 SoT 不落盘；token A 不能 body 冒 B、跨 TaskRun、
   capability/write 升权、stale fence、越 `allowed_node_refs`；授权正常流/幂等/租约释放正确；peer 旧边界回归。
3. **资源/预算/恢复**：至少 4 个实际 SDK worker 会话（2 selection + 2 execute）的真实 session_refs/停止事实在真实 Run/Verifier 门完整参与；
   正常 stopgate 只有全停才放行，故障让任一 selector 未停即 held/保留槽/refs；选择+执行+reviewer 实际 proxy 共**同一物理持久账本**/Task 累计预算，
   跨会话/Run 不归零，过限在转发前拒绝，坏账 unknown 非 0；slot 权限回收仅真实 SDK 停后；expiry 不偷取未知写入，不重放完成写节点；
   实际需 Task 预算按正式字段测试。
4. **默认程序回退/核心差异**：新开关 off 时首版正常 SDK/异步 review/stop/绑定 accept 机制不回归；契约 §13 对 body.owner
   从 required→optional / ExecutionGrant.lease_owner 的变更分类是否符合既有变更控制（不机械强升/忽略实际公开 schema 变化）。

## 5. 方法

- 持久目录、create-only 输出；关键 SoT 禁止 TemporaryDirectory 自动清除；敏感原件私有 700/600，仅脱敏摘要/哈希入 repo。
- 独立复验脚本自建（**不**复用 source 探针的临时目录结论）；真实 SDK + 本地 fake 上游；子进程 dummy 凭证 + loopback 强制。
- 必要局部 pytest + mypy / 实际 FileStore 跨进程 / SDK fake 探针；未改 UI 不重跑全矩阵。
- 重要缺陷立即持久最小 repro/严重性/源码位置/返修目标；**QA 不修产品**。

## 6. 交付

- `qa/lg032/runtime-r1/{PLAN,STATUS,REPORT,FINDINGS}.md`
- `qa/lg032/runtime-r1/{evidence,probes,fixtures}/**`（create-only，持久）
- 精确本地 commit；不 add -A；不合入 main；不 push/deploy/publish。

## 7. 预算/边界

- wall 1500s / maxround 260 / noncache 360k / idle 240s / 开发 retry 0；单探针 <=60/90s 有界；避免 100s 超时循环。
- 本包 product real generation 0；pi 开发 QA token/time shared/unknown 单列；旧 031 工程 34 与 023 实际 65 不归零。
- 029 自条件真齐可确认 done；031 真实 provider 条件仍未做 ⇒ inprogress；032 整体 inprogress 直到后续实际同门成本 B。
