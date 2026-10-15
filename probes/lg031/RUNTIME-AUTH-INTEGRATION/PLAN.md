# LG-031 RUNTIME/AUTH INTEGRATION — PLAN

> Owner：唯一串行 runtime/API/SDK 集成与返修 owner（pi + env DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）
> Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-runtime`｜branch `integrate/lg031-runtime`
> 基点：`main@834b262`（核实际 clean）｜本包**不合入 main**
> 产品真实 DeepSeek/生成请求：**0**（本包全程）

## 1. 输入与开工事实（真实核对）

- F1 原 owner 已退出：`fix/lg031-pool@f2741bb` clean，9 局部测试 + 4 进程 flock 探针 + 799pass5skip/mypy137；
  REPORT 明确其 SDK-real 仅为 **Store/worktree/fake-worker** 机制，**真实 SDK 两阶段适配未实现**。
- F2 原 owner 已退出：`fix/lg029-auth@388f6fa` WIP 已保全 clean、**暂停未验**。
- `main@834b262` clean，仍为稳定 core e0 快照；无 dirty。
- 已确认（源码）F2 测试引用 `registry.mint(lease_owner=...)`，而冻结 `execution_grant.ExecutionGrantRegistry.mint()` **无** `lease_owner` 形参。
- 已确认（源码）F1 池路径 claim/release 用 `self._owner = graph-dispatcher:<pid>`（调度器身份），
  而 F2 HTTP `_grant_owner()` 用 `grant.member_ref`（worker 成员）——**lease owner 不一致**。
- 保留：所有旧分支/worktree/dirty/原始记录未 reset/clean/覆盖/重复 pick；未复制 `.env`/secrets。
- LG023 cohort3 在旧 core 快照另一工作区只读评估，未触碰其进程/源码。

## 2. 合并（安全，本包内）

- `git merge --no-ff fix/lg031-pool`（F1 最终）→ 无冲突。
- `git merge --no-ff fix/lg029-auth`（F2 WIP，`api/bootstrap.py` 自动合并）→ 无冲突。
- 合并后由本唯一 owner 串行解决真实新授权类型（lease owner 一致性 / bootstrap 接缝 / 两阶段 SDK 生命周期）。

## 3. 目标（用户指令）

1. 完成受控**两阶段 SDK 生命周期**（或同等等价可验方案）：on-demand worker 在程序授权候选池（>=2）选择并申请 claim，
   程序原子授予所选 node 后，真实 SDK 执行会话绑定**所选** node 独立 workspace/objective/upstream 版本/hash 与权限；
   选择前无写权限；选择/执行共用 worker 授权/Task 累计预算/全局持久生成限额；selector 与 execution session 历史与
   真实停止事实记录并参与 stopgate；禁止新增独立常驻 selector/orchestrator。
2. 两真实 program worker 身份竞争同 node 必须一 winner；所选 member 身份/connection pin/工具 cap 不能被另 node 配置悄悄扩大；
   授权与 `lease_owner` 程序冻结且一致；跨 TaskRun/capability/write/scope 拒绝；stale fence/expiry≠实际停/unknown 不重放。
3. 完成 F2 discover/claim/renew/release HTTP 使用程序认证 principal + 授权范围 + 有效 grant/fence；
   body.owner/capability/write 不能授予身份或扩大权限；未配置/未认证 default-deny 且不落盘；
   认证 A 不能冒 B 或越 TaskRun；只读不能写；peer 现有身份接线保持。
4. 保持核心 e0 流式 SDK cancel/idle/aexit 同 loop 与真实 stopfacts、持久 generation ledger、pin/token/evidence/幂等/反重放、
   docs/08 变更控制（不机械升版本）；F3 诚实说明。
5. 本包真实 DeepSeek/产品生成 0；必须做真 SDK 0.1.22 + 本地受控 fake 上游的离线端到端探针（清楚 provider-substitute）。

## 4. 实施步骤（唯一 owner 串行）

1. **lease owner 一致性（加性）**：`ExecutionGrant` 加 `lease_owner`（程序冻结的租约权威，缺省= `member_ref`）；
   `mint(lease_owner=None)`；`to_dict` 加性；`grant_claim` 返回的 receipt binding 不泄露 token/秘密。
   - graph 池 claim/release 改用 grant 冻结的 `lease_owner`；API `_grant_owner` 返回 `grant.lease_owner`。
2. **两阶段 SDK 生命周期**：池 slot 执行拆为
   (a) **选择会话**：真实 SDK 会话按 slot 上下文运行，仅暴露受限 discover/claim 工具，**无写权限**（程序冻结只读 workspace 或只读工具集）；
   (b) 程序原子授予所选 node；
   (c) **执行会话**：真实 SDK 会话按**所选 node** 的隔离 workspace/objective/upstream hash/权限构建并运行；
   结果/manifest/状态/交接归所选 node。选择会话与执行会话共享同一 Task/phase 预算与全局持久账本；历史/真实停止事实记录。
3. **F2 接线**：修 `mint(lease_owner=...)` 签名缺口；`worker_grant` 接缝在 `app/context/bootstrap` 串行统一；
   四端点 default-deny + 程序 principal/scope/fence；peer 保持。
4. **docs/08**：按真实变更控制登记加性说明（若确有新加性字段/可选请求字段则依规则升版，否则仅加性说明）。
5. **探针**：真 SDK 0.1.22 + 本地受控 fake 上游（provider-substitute），两阶段选择→领取→绑定执行/写隔离 workspace；
   同 capability 两 ready 候选选非首项；两 worker 真实程序身份竞争一次；所有 SDK session 结束/历史保留/stopconfirmer 放行。
6. **检查**：必要一次整合 `pytest` + `mypy`；未涉 UI 不重跑前端矩阵。
7. 及时写 PLAN/STATUS/REPORT；精准本地提交；不 add -A；不碰 8123/别包。

## 5. 验收/边界

- 本包**不自判版本 pass**；LG-031 真条件未齐保持 `in-progress`，LG-029 自条件齐可 `done` 待 032 独立复验。
- 探针单次 <=60/90s 有界；缺陷先保存不反复 timeout 试错。
- 正式真实 provider 验证留后续 PM 独立预算。
- 新增产品真实生成 0；工程探针可离线/本地 fake 上游。
