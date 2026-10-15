---
title: "LG-032 FINAL-COHORT narrow-B 调查 WIP REPORT（workspace 边界根因）"
doc_type: report
category: engineering
status: "WIP / 调查完成 + 根因定位 + 待 PM 授权处置"
experiment_id: lg032-final-cohort-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort
branch: qa/lg032-final-cohort
base_commit: "91550a9"
updated: "2026-10-16"
owner: "agent:pi-lg032-final-cohort（续接 owner；非 031 实施者；主代理仅 PM）"
product_real_generation: 0
---

# LG-032 FINAL-COHORT — narrow-B 调查 WIP REPORT（workspace 边界）

> **本报告为 WIP**，完成于前 15 round 内，随后立即 `STATUS` + 精确 WIP commit。
> 本包**产品真实生成 0**；只走真 SDK + loopback fake 上游 / 真产品生命周期。
> **不删任何旧输出**；所有旧 probes / dry / stdout / SDKDB 原样保留。
> 敏感值（凭证/token/grant/绝对 credential）不输出；路径只输出必要前缀。

## 0. 结论（一句话）

**arm B（候选池自主选择）在真实产品正常默认 bootstrap 下不可用**：产品
`GraphDispatcher._selection_workspace` 把「选择期」scratch 目录建在 **Task 的 `save_dir`
（`<data_dir>/native-sessions/<task_id>/...`）之下**，而真 `AntigravityExecutor` 的授权
workspace root 是 **`Settings.workspace_root`**（产品默认 = `<data_dir>/workspaces`，是
`data_dir` 的**子目录**）。两者无包含关系 ⇒ executor 的 `_resolve_workspace` **如实拒绝**
（`AdapterConfigInvalid`），选择期 session 直接 `blocked`，Run 进入 `failed`。

- 这**不是** harness 装配错误：harness 的 `workspace_root = <data_dir>/attempts/<id>/workspaces`
  与**产品默认布局**（`data_dir/workspaces`）在“`workspace_root` 是 `data_dir` 子目录”这一点上等价，
  因此**正常产品默认配置同样触发**。
- 这**是** 032 要找的**真正产品缺陷**：产品自己构造的 selector scratch 落在 executor 禁止 root 外，
  即“合法自主管理的 workspace 路径被错误拒绝”。
- 前 owner 用 `LG032_WIDEN_EXEC_ROOT` 把 executor root 扩到 data 根（甚至项目旁全部 worktrees）
  才能跑通，**属于禁用调试手段**，不代表产品可用。见 §4。

## 1. 复现证据（真实 failedRun，非伪造）

### 1.1 harness 侧 observer 记录（存活原件）

`probes/lg032/FINAL-COHORT/evidence/narrow/diag2/exec_diag.jsonl`（及 `diag1/`）三行均为 selection 期请求，`state: blocked`：

```
"phase": "selection",
"allowed_tools": [],
"custom_tools": ["discover_and_request_claim"],
"workspace": ".../lg032-final-cohort-data-dry-s1_units-B-<UTC>-<nonce>/
              native-sessions/task_01M50JXNTBA7C92P12N9VPW2SZ/
              .lg-pool-selection/run_01M50JXNWG0X1C9FENG4EYMCSC/slot_..._<0|1|2>",
"save_dir":  ".../native-sessions/task_01M50JXNTBA7C92P12N9VPW2SZ",
"outcome": "returned",
"state": "blocked",
"summary": "blocked: workspace '.../.../native-sessions/task_.../.lg-pool-selection/.../slot_..._<n>'
            escapes the authorized root '/home/...'"   ← 前缀被观察器截断，见源码断言
```

对应 dry stdout（存活原件）：
`probes/lg032/FINAL-COHORT/offline/diag2_b_20261015T200910Z.stdout` 与 `…diag_b_20261015T200828Z.stdout`：
`[FAIL] run_reached_awaiting_acceptance {'phase': 'failed', 'phases_seen': ['failed']}`
`[FAIL] real_session_refs_recorded {'session_refs': []}`
`[FAIL] machine_gate_pass`（实现 `NotImplementedError`，符合 initial stub 必败）

> 注：`diag_b_…200828Z` 的 `phases_seen:['executing','failed']` 仍是**选择期失败后整 Run 失败**，
> 不是执行期成功；两轮都是同一根因。

### 1.2 源码路径与行号（产品，只读）

| 事实 | 位置 |
|---|---|
| 选择期 scratch 建在 `save_dir` 下 | `backend/lightgravity/coordinator/graph.py:1080-1100`，`_selection_workspace`：`base = context.save_dir or context.workspace_path` → `scratch = root / ".lg-pool-selection" / context.run_id / slot_id`（`:1095`） |
| 选择期请求携带该 scratch 作为 `workspace_path` | `backend/lightgravity/coordinator/graph.py:1211` 附近 `_build_selection_request`（`workspace_path=workspace`, `save_dir=context.save_dir`），实现于 `:1190-1215` |
| `context.save_dir` 来源 | `backend/lightgravity/coordinator/service.py:1325-1345`（`_continuation_for`）→ fallback `self._native_session_dir(task.entity_id)`；`_native_session_dir` 定义于 `:1445-1454` = `<self._resource_dir>/native-sessions/<task_id>`；`_resource_dir = resolved_data_dir`（`:327`） |
| executor 授权 root | `backend/lightgravity/adapter/executor.py:374-375`：`root = workspace_root if ... else getattr(store, "workspace_root", None)` → `self._workspace_root = Path(root).resolve()` |
| executor 边界校验（拒绝点） | `backend/lightgravity/adapter/executor.py:825-836` `_resolve_workspace`：`if root is not None and not _is_within(resolved, root): raise AdapterConfigInvalid(f"workspace {resolved!r} escapes the authorized root {root!r}")`；`_is_within` 定义 `:87` `candidate == root or root in candidate.parents` |
| 产品默认 root 取值 | `backend/lightgravity/config.py:48-53`：`workspace_root = Path(source.get(ENV_WORKSPACE_ROOT, str(data_dir / "workspaces")))` ⇒ **`workspace_root` 默认是 `data_dir` 的子目录** |
| bootstrap 装配 root | `backend/lightgravity/api/bootstrap.py:362`（`FileStore(settings.data_dir, settings.workspace_root)`）、`:413`（`AntigravityExecutor(..., workspace_root=settings.workspace_root, ...)`）、`:441`（`GraphWorkspaceProvider(WorktreeManager(settings.workspace_root))`） |

### 1.3 真实配置值（本次 failedRun，脱敏）

- `data_dir`（正式 phase）：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort-data`
- `workspace_root`（harness 每 attempt）：`<data_dir>/attempts/<attempt_id>/workspaces`
- dry 根（唯一化后）：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-final-cohort-data-dry-s1_units-B-20261015T200910Z-9cbde968`
- selection scratch（实际被拒路径）：
  `<dry 根>/native-sessions/task_01M50JXNTBA7C92P12N9VPW2SZ/.lg-pool-selection/run_01M50JXNWG0X1C9FENG4EYMCSC/slot_run_…_<n>`
- 被拒原因：该 scratch 的父链**不含** `workspace_root`（`workspace_root` 是 `data_dir` 的**兄弟/子**关系而非祖先）。

**包含关系**：
- `workspace_root` = `<data_dir>/attempts/<id>/workspaces` ⊂ `<data_dir>`
- selection scratch = `<data_dir>/native-sessions/<task>/.lg-pool-selection/...` ⊂ `<data_dir>`
- 二者**仅共享祖先 `<data_dir>`**，`workspace_root` **不是** scratch 的祖先 ⇒ `_is_within` 返回 False ⇒ 拒绝。

## 2. 根因归属判定

**判定：产品缺陷（selector scratch 与 executor 授权 root 的布局矛盾），非 harness 配置错误。**

论据：
1. 选择期 scratch 的根是**产品代码写死**的（`graph.py:1095` 用 `context.save_dir`），
   而 `context.save_dir` 由产品 `service.py:_native_session_dir` 定为 `data_dir/native-sessions/<task>`。
2. executor 授权 root 由**产品默认配置**（`config.py:48`）定为 `data_dir/workspaces`。
3. `data_dir/native-sessions/...` **永远不**落在 `data_dir/workspaces` 之内 ⇒ 只要产品默认布局 +
   arm B 候选池开启，**必然**被拒。harness 并未“改坏”任何一处：harness 用的
   `<data_dir>/attempts/<id>/workspaces` 与默认 `data_dir/workspaces` 同构（都是 data_dir 子目录）。
4. 现有 LG-031 池测试 `tests/collaboration/test_lg031_pool_selection.py` 用 **`PoolWorkerSim`（假 executor）**，
   **不做 workspace-root 校验**，故该缺陷从未被测试覆盖（`tests/…:340` 仅断言路径含 `.lg-pool-selection`）。

**结论**：这是 032 发现的**真正产品缺陷**——「产品正常默认 bootstrap 构造 selector scratch 落在
executor 禁止 root 外」。符合 PM 授权 3) 的判定条件。

## 3. 影响范围（最小）

- **触发条件**：`decentralized_claim_enabled=true` + `autonomous_pool=true`（arm B / 候选池路径）
  + 真 `AntigravityExecutor`（真实 workspace 边界校验生效）。
- **不触发**：arm A（确定性单节点路径，不做 selection 期 scratch）；`PoolWorkerSim` 类假 executor。
- **受影响功能**：F1 候选池自主选择（LG-031 POOL-FIX / 1.11 候选）在**产品默认配置下不可用**。
- **不影响**：arm A 正常路径、grant/lease/fence/预算/stopgate 逻辑本身、`max_parallel`、真实 stopgate。
- **契约**：若修复只是让“合法自主管理的 scratch 落在正确 root 内”，**无公开 API/枚举/错误码变化**，
  预计**不升契约版本**（待 PM/独立复验确认；docs/08 共享文档若无行为变化只做必要说明）。

## 4. 禁止的调试手段（已标记，正式路径移除）

前 owner 在 `harness/run_attempt.py` 的 `_enable_loopback_for_dry_run` 中留有：

```python
if os.environ.get("LG032_WIDEN_EXEC_ROOT") and executor is not None:
    widened = Path(os.environ["LG032_WIDEN_EXEC_ROOT"]).resolve()
    executor._workspace_root = widened   # 直接扩 root，绕过产品边界
```

**裁定**：该手段把 executor 授权 root 扩到 `data_dir` 甚至项目旁全部 worktrees，**属于 PM 明令禁止**的
“靠 `LG032_WIDEN_EXEC_ROOT` 把根扩到项目旁全部 worktrees”。**正式路径不得使用，必须移除**；
原调试代码快照在 WIP commit 中保留（见 §5 / STATUS）。

## 5. 下一步（本 WIP 之后的授权动作）

1. **先提交本 harness WIP 报告 + STATUS + 精确 commit**（本报告即为交付）。
2. 依 PM 授权 2)/3)：在**新独立持久 worktree** `lg031-workspace-boundary-fix`
   （branch `fix/lg031-workspace-boundary`，基 `main@3def294`）做**最小产品修复**：
   - 让**选择期 scratch**（以及任何合法自主管理的 workspace）落在**实际受控正确 root**
     （即 executor 授权 root / `workspace_root`）之内；**权限不扩大**、**不宽化到其他 worktree**。
   - 保持真正隔离、程序授权/lease/fence/预算/真实 stopgate 不变、default off。
   - **不**修改 `max_parallel` / 调度容量 / 授权语义。
3. **harness 侧**：移除 `LG032_WIDEN_EXEC_ROOT` 正式路径用法（快照保留），
   将 fixture 所需 scratch/workspaces 置于**实际受控正确 root**；**新增回归**覆盖
   「root 内合法 selector 通过」与「越 root 拒绝」；不镜像实现、不跑无关全套。
4. 实际 **0 fake 至多 1B 新 unique attempt** 证根因解除（不是正式 032 采样）。
5. 写最终 REPORT + 冻结 hash + 精确 commit，交独立 QA；**不自行宣 pass**。

## 6. 未做 / 保留

- **产品真实生成：0**；**未跑正式样本**；**未 mark 032/031 done**。
- **未删除** 任何旧 probes / dry / stdout / SDKDB；`LG032_WIDEN_EXEC_ROOT` 调试快照保留。
- 未 push / deploy / publish；未动 8123 及他包进程。
- 未在正式路径使用 widen；未 monkeypatch executor root/stopgate；未手写 state 凑绿。
