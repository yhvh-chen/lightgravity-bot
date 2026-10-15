# LG031-BOUNDARY-INTEGRATION — main 集成记录（BOUNDARY-R1）

- **角色**：唯一 main 整合 owner（独立于修复 owner 与 QA owner）。本包不改产品代码，不审查代码，只做项目管理文档与安全集成。
- **集成时间**：2026-10-16。
- **结果**：`qa/lg031-boundary` 已 `--no-ff` 安全并入 main；LG-031 按独立 `BOUNDARY-R1 PASS` 重新 mark `done`（**仅限 BOUNDARY-R1 范围**）。
- **真实 provider 主生成**：**0**（本集成包与 QA 均未调用真实 DeepSeek；QA 用 loopback fake SSE）。
- **产品是否全 pass**：**否**。不宣全产品 pass。

## 1. 祖先与安全 merge（无重复 pick）

| 项 | 值 |
|---|---|
| 集成前 main | `3def294`（LG-031 close-audit 集成点） |
| `merge-base(main, qa/lg031-boundary)` | `3def2941a3f147aded25ac509d3c91d1bd3bd245` |
| QA 分支头 | `70a0fd5`（含 `82b4357` QA PASS、`0814b80` 修复） |
| 先精确保全 root-PM dirty | `f9ffaba` |
| merge commit（`--no-ff`） | `8c4c551` |
| 冲突 / 覆盖 / 重复 cherry-pick | 无 / 无 / 无 |

- 集成前 main 存在两份**预期内** root-PM dirty：`PROGRESS.md` 新增「PM 更新：LG-031 正常启动边界待修复」段，
  `backlog/tasks/LG-031.md` 将 `status` 由 `done` 改为 `in-progress` 并追加「PM 再开」附录。
- 先**精确提交**这两份变更（`f9ffaba`），保全全部再开历史/收口/失败/成本记录，**不丢弃/不覆盖/不 reset**，再 merge。
- `qa/lg031-boundary` 直接基于 `3def294`，故 merge 为线性并入；修复提交 `0814b80` 不重复 pick。
- 无其他意外变更；merge 后 `git status --porcelain` 为空。

## 2. 变更面与产品 hash（与独立 QA 逐字节一致）

产品仅 3 文件（+ 测试 + 探针）：

| 文件 | sha256（集成后 = QA 报告） |
|---|---|
| `backend/lightgravity/coordinator/graph.py` | `1aebbde175ab3832e491bdc41c324d6ee5dbc59713410dcaf1affcfe064245cf` |
| `backend/lightgravity/workspaces/manager.py` | `849417478888a7bc1187e79fe3af2155dd5fb135a49a84d8208da2eb54f91648` |
| `backend/lightgravity/workspaces/provider.py` | `c8d14b56c4d2c27d653172f6be8f65cc85abb1f4d3f033047acb26c621eb7934` |

- 测试：`tests/collaboration/test_lg031_pool_selection.py`（+112 行）。
- 探针：`probes/lg031-workspace-boundary/**`（DEFECT-REPRO、proof_boundary、qa/**）。
- **根 1.11.0 的 default-off / API / token / stop / fence / source 机制不变**。
- `collaboration/**`（grant/lease/fence/handoff）与 `adapter/**`（executor/budget）**未被修复触碰**。

## 3. 独立门 BOUNDARY-R1（引自 `qa/lg031-boundary@70a0fd5` 的 `qa/REPORT.md`）

**Verdict：PASS**（机制修复 + 真 SDK 产品默认布局，0 主 provider）。逐项：

1. 真实默认 `bootstrap`/`create_app` + 合法 3 节点池场景 — PASS
2. selector scratch 真正位于 SDK 授权 root 内（`scratch_inside_root=true`）— PASS
3. 选择阶段无写工具；选择后真实 SDK 绑定被选节点 worktree（beta 非首节点被选，无写串）— PASS
4. 全部 ref 进 stopgate；`sessions_stopped=4/4`、`proxy_stopped=true`、`unknown_sessions=[]` — PASS
5. 越 root 真实拒绝（含真实 `execute` 集成负向：blocked / `config_invalid` / 「escapes the authorized root」/ 未起 session）— PASS
6. 真 SDK `0.1.22` + loopback fake 上游（非 FakeExecutor 冒充 SDK），无出站 POST — PASS
7. 未放宽 root / 未把 `data_dir` 当写权限 / 未 monkeypatch executor 或 stopgate — PASS
8. 新 `workspaceprovider` 接口向后兼容（optional、`getattr`；无方法 provider 回退；`None` 不成为新 root）— PASS
9. 独立负向 + 产品默认布局复现原最小 repro — PASS
10. 小范围 pytest/mypy — PASS

**实际命令与退出码（q a/evidence/**）**：

| 命令 | 结果 | exit |
|---|---|---|
| `uv run --frozen python probes/lg031-workspace-boundary/proof_boundary.py` | ok=true | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_boundary_probe.py` | all checks pass | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_default_bootstrap_probe.py` | all checks pass | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_product_default_two_phase_sdk.py` | ok=true, failed_gates=[] | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_real_executor_negative.py` | ok=true | 0 |
| `uv run --frozen pytest tests/collaboration/test_lg031_pool_selection.py -q -p no:randomly` | 13 passed | 0 |
| `uv run --frozen pytest tests/collaboration tests/coordinator tests/workspaces tests/adapter -q -p no:randomly` | **329 passed** | 0 |
| `uv run --frozen mypy backend/lightgravity/coordinator/graph.py backend/lightgravity/workspaces/` | Success, 5 files | 0 |

> 本集成包**不重复全部产品 tests**（产品 code 有实际 fix，但只核集成产品 hash 与独立 QA 一致，并引用既有 QA check 报告）。

## 4. 限制与不宣（honest non-claims）

- **真实主 provider 生成 0**：QA 真实 SDK 运行使用本地 fake OpenAI SSE 上游（loopback），**不冒充真实 DeepSeek 端到端**。
- **真实 provider 86 仍旧限定门**：旧真实工程 86（34+24+28）**不归零、不重跑**。
- **真实 SDK 由 fake 证明默认布局**（边界/生命周期机制，非模型质量）。
- **完整 `CoordinatorWorkerLoop` + 真实模型质量/成本对照仍归 LG-032，未过**。
- **本集成不宣全产品 pass**。
- 低危接口注记（非阻断）：`GraphDispatcher._selection_scratch_root` 自身未 `try/except`，依赖 provider 吞 `WorkspaceError`；现装 provider 已吞。
- 既有 errata：越 root 真实拒绝的 failure code 为 `config_invalid`（非专用 `path_outside`），属 `_resolve_workspace` 既有行为，修复未触碰。

## 5. 状态 / backlog / 成本（以 CLI 实读为准）

- 集成后 backlog 根 `validate`：**41 tasks / 0 diagnostics**（exit 0）；`digest` **complete**。
- 计数（集成后）：**36 done / 3 in-progress / 2 todo**（032、035、037 为 in-progress；040、041 为 todo）。
- LG-031：`done`（**仅 BOUNDARY-R1 范围**；保留 2026-10-16 close-audit 收口与再开全部历史）。
- LG-032：**依赖恢复可满足，但仍 `in-progress`、未正式采样**；阶段 B 预算固定 **4×48 / 总 192**，**本包不执行**。
- 并行 032 harness owner 仅新 worktree 报告，**不合入未验 harness**。
- **共享 docs/08 无公开契约变化 ⇒ 不升版**（仍 1.11.0）；**release L0 旧 `e0`/1.10 包不动**，不假称最新 source 1.11。
- 成本：**本集成包产品真实生成 0**；旧真实工程 86 不归零；provider token/费用 unknown 不当 0。

## 6. 证据引用

- QA 报告：`probes/lg031-workspace-boundary/qa/REPORT.md`、`qa/STATUS.md`、`qa/evidence/**`
- 缺陷复现：`probes/lg031-workspace-boundary/DEFECT-REPRO.md`
- 前序收口/审计：`probes/batch-20261016/LG031-AUDIT-CLOSE.md`、`qa/lg031-close-audit/**`
- 本记录：`probes/batch-20261016/LG031-BOUNDARY-INTEGRATION.md`
- 任务：`backlog/tasks/LG-031.md`、`backlog/tasks/LG-032.md`、`PROGRESS.md`
