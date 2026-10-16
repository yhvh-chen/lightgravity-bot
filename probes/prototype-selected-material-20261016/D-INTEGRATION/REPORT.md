# LG-046 D-INTEGRATION — 选定资料快速原型串行整合报告

- Owner: `agent:pi-proto-integrate`（LG-046 整合 owner）。
- 任务：LG-043 / LG-044 / LG-045 → LG-046 串行整合候选。
- 状态：**实现完成，整合候选已产出；产品代码实现完成，待 LG-047 独立版本 QA。**
- 预算：产品推理 **0**；本包**未发起任何**真实 product 模型/网络/浏览器/SDK 调用；未新增模型/OCR/embedding/ASR；未 push/deploy；未触碰 8123。
- 声明：**非版本 QA 通过**；真实 SDK/DeepSeek 端到端与浏览器验收归 LG-047。

## 1. 源三线（均基于冻结契约 `21e6344`）

| 线 | 分支 | tip | 说明 |
|---|---|---|---|
| A 后端 | `dev/proto-material-backend-20261016` | **`9ac6597`**（产品 = `6515e5c`） | selected-material 后端 + run/message 触发绑定修正 R1；docs/08+docs/10 finalsync `1.12.0`；`9ac6597` 仅追加集成验证回执（无产品代码变化） |
| B 前端 | `dev/proto-material-frontend-20261016` | **`552d839`** | 手动选材 + Sources 回链；owner 已停止；前端树干净 |
| C Demo | `dev/proto-material-demo-20261016` | **`e36df29`** | 英文 sample fixtures + docs/11 可复现指南（初版 `6facb0b` + 事实校正）；owner 已停止 |

- 三线文件 owner 边界互不重叠，合并无产品冲突（仅 `probes/.../{A,B,C}-*/REPORT.md` 在 `main` 上为 LG-042 骨架、在分支上为真实报告，属 add/add 骨架冲突，一律**解析为源分支真实报告**，非产品编辑）。
- 源分支与 worktree **全部保留**，未删除、未 force。

## 2. 整合顺序（全部 `--no-ff`）

| 步骤 | 命令结果 | commit |
|---|---|---|
| PM 记录（先于合并） | 精确 PM 任务 043/044/045/046 + DISPATCH 回执澄清提交到 clean main | `7dd6da0` |
| A | `merge --no-ff dev/proto-material-backend-20261016 @9ac6597` | `37919fe` |
| B | `merge --no-ff dev/proto-material-frontend-20261016 @552d839` | `942d40c` |
| C | `merge --no-ff dev/proto-material-demo-20261016 @e36df29` | `f7a32ac` |

- 合并前 `main` clean = `7dd6da0`（仅 LG-042 之后的授权 PM 改动）。
- 三行合并均**无产品代码编辑**（除 A 分支带来的 docs/08、docs/10 与 probe REPORT；B/C 仅各自前端/demo 文件与 probe REPORT）。
- **产品树等价性（candidate 相对源）**：
  - `HEAD:backend` tree = `69d02e7af1554f89594290d739e457535c358345` = `6515e5c:backend` tree（**逐字节一致**）。
  - `HEAD:frontend` tree = `07618bb29bed372f47422b584070101196ce86bc` = `552d839:frontend` tree（**逐字节一致**）。
  - `examples/selected-material-prototype/**`、`docs/11` 来自 C。
- **DISPATCH 回执澄清**：DISPATCH“所有 worktree 从 `acd7005` 派发”为历史规划口径；**实际**三 worktree 分支基点均为 **`21e6344`**（LG-042 prep 冻结契约提交），`main` 其后推进到 `642fb3d`（PM 任务登记）。已在 DISPATCH.md 加性登记澄清，不重写历史。

## 3. A 绑定修正回执补齐（原 PARTIAL）

A 原报告将 run/message 触发绑定修正标为 **PARTIAL（无完成回执）**。集成 owner 在**已提交**的绑定修正 `6515e5c` 上实跑并落盘 durable EXIT：

```
PYTHONPATH=backend uv run --no-sync pytest tests/sources/test_lg043_selected_material.py -q
# => 42 passed in 3.70s ; EXIT 0
PYTHONPATH=backend uv run --no-sync mypy
# => Success: no issues found in 139 source files ; EXIT 0
PYTHONPATH=backend uv run --no-sync pytest tests/contracts tests/coordinator tests/sources tests/api tests/adapter tests/store -q
# => 550 passed, 1 skipped in 57.19s ; EXIT 0
```

- raw 日志：`probes/prototype-selected-material-20261016/A-BACKEND/raw/integration-verify/`；A REPORT Addendum 已记录。
- 结论：绑定修正的 42 用例（35 首版 + 7 回归）**真实通过**；A 报告“未提交”描述已过时（修正已在 `6515e5c` 提交）。

## 4. 集成候选实际检查（零外部调用）

> 全部在整合候选 `f7a32ac`（HEAD）上实跑；durable 日志见 `raw/`。

| 检查 | 命令 | 结果 | EXIT |
|---|---|---|---|
| 后端类型 | `PYTHONPATH=backend uv run --no-sync mypy` | `Success: no issues found in 139 source files` | **0** |
| 后端全套 | `PYTHONPATH=backend uv run --no-sync pytest tests/ -q` | **908 passed, 2 skipped**, 1 warning (101.73s) | **0** |
| 前端类型 | `cd frontend && npx tsc --noEmit` | 无错误 | **0** |
| 前端构建 | `cd frontend && npm run build` | `tsc --noEmit && vite build`，103 modules，built in 1.48s | **0** |
| C fixture | `python3 examples/selected-material-prototype/check_fixtures.py` | `ALL_OK: fixture checks passed`（含 docs 链接解析） | **0** |
| TS shape 绑定 | `grep` 于 `frontend/src/api/chat.ts` | `SelectedSourceRef`/`ResolvedSourceBinding`/`selected_sources`/`resolved_source_bindings` 与 docs/10 §9 一致 | — |
| 契约常量 | `backend/lightgravity/contracts/constants.py` | `CONTRACT_VERSION = "1.12.0"` | — |
| DTO 字段 | `backend/.../coordinator/api.py`、`api/conversations.py` | `selected_sources: list[dict] | None = None`（Task + global，`extra="forbid"` 保持） | — |

- **前端全套复跑说明**：集成后 `HEAD:frontend` 与 B `552d839:frontend` **逐字节一致**，B 已在 `552d839` 上跑过 `tsc`/`vitest 112/112`/`build`（EXIT 0）；按 LG-046 指令，前端树相同且检查有效时**不重复全量 vitest**，仅做**源绑定核对 + 集成后 fresh build**（`tsc`/`build` EXIT 0，已在整合候选上执行）。
- **后端全套说明**：因 A 绑定修正新增实体字段，按指令在**整合后**跑一次完整 `pytest tests/`（908 passed / 2 skipped），覆盖 A 未自行完成的 full-suite 回执（A 仅有相关子集）。
- **契约版本 / SDK**：`1.12.0` / `google-antigravity==0.1.22` 不变。

## 5. 冻结接口核对（practical）

- **请求**：`selected_sources` 可选、≤3、仅 `source_id` opaque；省略时 legacy 行为不变（`extra="forbid"` 保持）。Task 与 global 两条消息路由一致。
- **响应**：reply `data` 含 `resolved_source_bindings`（version/hash/layer/locator/char_count/truncated/truncation）、`context_truncated`、`provided_context_note`。
- **持久化 / 回链**：程序侧 `selected_context` 快照写入既有消息日志；加性可选 Task/Run 实体字段 `selected_trigger={message_id,snapshot}`（实体序列化可达、非秘密），Run 只用自身触发消息的精确选定；前端以 Sources 标签展示 provided context（**不宣称模型引用已验证**），Files 回链用真实 `source_id`。
- **global + Task selection**：前端选材 hook 按 Task 隔离、切换清空、不跨 Task 携带。
- **版本常量/docs/test**：`CONTRACT_VERSION=1.12.0`；`tests/contracts/test_contracts.py` 断言已更新；docs/08 头部 + §6.6.1 + §13、docs/10、docs/11 均 `1.12.0`（去 reserved）。
- 上述为**接口事实核对**（源码/常量/文档一致），**不等于**端到端行为通过；A/B 各自 local 检查，**未做完整 E2E**（归 LG-047）。

## 6. Docs / README / PROJECT / BACKLOG 最小更新

- docs/08、docs/10：由 A 分支 finalsync 至 `1.12.0`（合并携带）。docs/11：去除 `1.12.0-reserved`，加性登记“LG-046 已整合，字段已存在”状态说明，保留 pre-integration 历史说明。
- README：顶部契约版本 `1.11.0`→`1.12.0`；docs/08 引用行更新为 1.12.0 描述；新增一段 LG-042～047 当前进度事实。PROJECT：新增 2026-10-16 LG-043～046 决策日志。BACKLOG：当前批次状态更新为“046 已整合候选、047 待 QA”。
- **无大范围历史重写**；旧 `1.11.0`/历史口径保留。

## 7. 已知限制 / 剩余风险（如实结转）

- **未做真实 SDK/DeepSeek 端到端**：A worker-context 同一 body 的验证为 in-process FakeExecutor 单元证据，**非真实 SDK 证明**；真实模型+浏览器主线归 LG-047。
- **未做浏览器验收**：前端 390/1024/1440 响应式、过渡、真实 API 联调未在本包验证；B 为本地 mock 组件测试。
- **持久化 backlinks**：前端从 POST `data` 及（防御性）message row 读取 additive 字段；若 A 仅在 POST 返回而未持久化到 message row，重开历史将不显示 Sources（fail-open-to-legacy，非伪造）。**待 LG-047 核实持久化形态**。
- **global-list 过滤**：Task 作用域下 picker 读取未过滤 `GET /sources` 以恢复 global 行；若 A 收紧授权，picker 会如实报错——**集成待核实点**。
- **未知限制**：多 Run 并发绑定时序、跨进程/多写者竞争未验证（unknown，非 pass）。
- 成本 **unknown，非 0**（无调用）；LG-047 预算 12 次**未开始**、per-campaign 持久账本转发前硬上限未消费。
- 本整合候选**未 push/deploy**；无后台进程残留；8123 未触碰。

## 8. 状态

product code implemented **pending LG-047**。

## 9. 候选与 QA 基础

- 整合候选 commit：**`f7a32ac6bf99e668abf577e57f28254da6fda227`**（及后续 PM 记录提交，产品树不变）。
- LG-047 建议 QA worktree base：`candidate`（frozen integrated code）→ 见 `docs/10`/DISPATCH 与任务 LG-047。
