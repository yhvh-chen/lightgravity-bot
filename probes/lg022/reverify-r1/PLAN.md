# LG-022 独立复验 R1 — PLAN（交独立 QA owner）

- 本目录由**集成 owner** 建立，用于**独立于实施者**的 LG-022 R1 复验。
- 候选基点（claim 状态保持）：`qa/lg022-r1` 基于整合候选 `9698e8a`
  （`integrate/batch6`，契约 `1.9.0`，含 LG-022 R1 `fix/lg022-r1` + LG-037/038 集成 + 可逆归档）。
- **LG-022 原 claim 保持 `in-progress`（`agent:pi-lg022`）**；本复验不自行判 pass，结论交主代理。

## 1. 输入

- `probes/lg022/REPORT.md`（原独立 QA，候选 `bf7851c`，FAIL D1/D2，诚实性 D3）。
- `probes/lg022/R1-REPORT.md` / `R1-PLAN.md` / `R1-STATUS.md`（返修 owner 自检，**替身/确定性证据，0 真实调用**）。
- `probes/batch-20261016/INTEGRATION-6.md`（本轮集成报告：合并、归档语义修复、契约 1.9.0、检查计数）。
- 契约 `docs/08` §9（review 生命周期、全局计数）、§4.3（`GET /api/v1/diagnostics/generation`）。

## 2. 待复验缺口（R1 声明已修，但需真实链路确认）

- **D1**：真实 coordinator event loop 内独立 `ModelReviewer` 可运行（不再 `asyncio.run` 异常 → 永远 `unavailable`）；
  真实 Settings 默认 worker/reviewer → 真实写 task → 独立 SDK reviewer → `awaiting_acceptance`，
  人工 accept 绑定需求/候选/计划 hash，duplicate/stale 拒绝与幂等符合契约。
- **D2**：`reviewing`/`verifying` 阶段状态/控制请求**不阻塞**；pause/cancel 有真实 reviewer stop/release 确认；
  超时/未知保持 pending/槽不释放；restart 恢复不重放已完成写节点/未知副作用；Task 预算跨 Run 不重置。
- **D3**：成功 Run 无伪 `fail_reason`；失败历史仍留事件。

## 3. 计量先行（硬门，先于任何真实请求）

- 旧 QA 首轮曾 hit 429 后 rerun，**累计真实生成次数 unknown**，不得洗成 0/首轮通过/<=10。
- 本 phase 允许**最多 10 次实际向 DeepSeek 转发的生成 HTTP 请求总计**（worker/reviewer/直答/Settings 测试/返修/失败/SDK 重试均包括）。
- 必须用返修后的**共享持久 forward 计数器**（`GET /api/v1/diagnostics/generation`，转发前原子扣减、全 session/role/stage 共享、service 重启不归零）。
  **必须先用本地伪上游证明计数/拒超限正确，才发真实请求**；计数不可靠就先 fail 计量。
- 旧 phase 未知单列；禁止宣称整个 LG-022 累计 < 20 等无证据总数。所有未完成样本记失败/未交付。

## 4. 边界

- 产品仍 `google-antigravity==0.1.22` + 现有受控 loopback proxy + DeepSeek；凭证仅受控 env/`credential_ref`；
  敏感请求体/headers 不落日志；grant/runtime token 不入 prompt/仓库。
- 只使用独立 `data`/`workspace`/端口；精确清本包签名进程，不碰 root 8123/其他任务；未知写副作用先确认状态不可自动重放。
- owner 仅 `probes/lg022/reverify-r1/**`、本项必要 QA 脚本 `tests/e2e/lg022/**`、LG-022 记录；产品只读。
- 沿用已通过 LG-021 前端 + LG-027 专项并核材料性差异；新协作默认关闭；最小必要真浏览器增量可复用旧证据。
- 关键门仍缺则保持 `in-progress`/fail 并给明确返修目标；全部门证据满足才 done。集中 QA 最多两轮返修。

## 5. 环境

- 运行入口与端口以本包 `STATUS.md` 记录为准；不得占用 root `8123`。
- 真实请求前先确认 `LIGHTGRAVITY_MAX_GENERATION_CALLS` 与 `GET /api/v1/diagnostics/generation` 读数。
