---
title: "LG-032 COHORT3 正式采样报告（4/4 attempt 全部真实交付）"
doc_type: report
category: engineering
status: "FORMAL COMPLETE — 4/4 attempts delivered (2 sample x A/B x 1); 84 real generation requests <= 192; mode isolation A=off(0 selector)/B=on(selector) confirmed; independent review passed 0 unsubstantiated; 0 business repair; old 106 preserved separate; 032 still in-progress (NOT done); no merge"
experiment_id: lg032-cohort3-formal-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "b634238"
audit_commit: "7d1c7a3"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-formal（独立入口验收 + 正式执行 owner；非产品/driver/entry 作者；真实 provider 4 attempt）"
---

# LG-032 COHORT3 正式采样报告

> 由 PM **条件批准**的全新 cohort3 4 attempt：条件为**阶段 0 独立入口门 PASS**。入口门 R1 **PASS**
> （`ENTRY-INDEPENDENT-AUDIT-R1.md`，commit `7d1c7a3`），故按**已授权**执行正式冻结 4 attempt。
> **4/4 attempt 全部真实交付**；未 STOP；未自修；未补跑；未换名 bringup；未新增 cohort。旧所有字节保全。
> 032 仍 in-progress，**不 mark done，不 merge main**。

## 0. 结论（先给判断）

- **阶段 0 独立入口门 R1 = PASS**（0 real provider，commit `7d1c7a3`）。旧 FAIL 的唯一根因（入口 prepare
  guard 无条件拒全部四个 attempt id ⇒ 第 2 次 attempt STOP）已由 `b634238` 收窄为「只拒当前 attempt id」，
  独立复验证明**完整四次顺序链可跑**。
- **正式 cohort3 = 完成（4/4）**：`s1_units__A → s1_units__B → s2_pipeline__A → s2_pipeline__B`，
  每个唯一一次，**全部 `sample_delivered=true`、`ok=true`、machine gate 首轮通过、独立 model reviewer
  `outcome=passed`（0 unsubstantiated）**。
- **真实 generation 请求合计 84 ≤ 192**（20 + 20 + 17 + 27），单 attempt 均 ≤ 48；物理 phase ledger 单一路径
  跨 4 runtime 累加，末值 `{"count": 84}`。
- **mode-isolation 实测成立**：A（第 1/3 attempt）`expected_enabled=False`、dispatcher 三开关全 False、
  **`subtask.lease_granted=0`（无 selector）**；B（第 2/4 attempt）`expected_enabled=True`、三开关全 True、
  **`subtask.lease_granted=3`（候选池 selector/claim 生效）**；每次结束 `restored_off=true`。
  **特别确认第 3 个 attempt（s2_pipeline__A）为 off**（未继承前一次 B 的 pool 模式）。
- **0 business repair**（`repair_rounds_spent=0` 四齐）；**无 harness/mode/assembly/meter/hash 错误**，故不触发 STOP。
- **旧失败协议成本 106 单列保留**：cohort1 87 + cohort2 19，逐字节不变；032 新已知上限 298 = 106 + 192，
  本 cohort3 实际真实 84，未归零、未混入、未补旧。

## 1. 身份核（只读）

| 项 | 值 | 判定 |
|---|---|---|
| worktree / cwd | `lg032-cohort3-entry` | ✅ |
| branch | `fix/lg032-cohort3-entry` | ✅ |
| base HEAD（执行点） | `b6342388375b407913f1d3d7e895a8b9436277e4` | ✅ |
| audit commit | `7d1c7a3792dc3cac4b744c481b5419c9859ef14f` | ✅ |
| entry `run_formal.py` sha256 | `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2` | ✅ 未改 |
| overlay `mode_config.py` sha256 | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ 未改 |
| driver `run_attempt.py` sha256 | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ 未改 |
| driver `final_cohort_config.py` sha256 | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ 未改 |
| 产品 tree `HEAD:backend/lightgravity` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | ✅ 未改 |
| SDK / contract / model | `0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` | ✅ 同冻结 |
| python / venv | `/home/yhvh/code/lightgravity-bot/.venv/bin/python`（venv freeze §5 指定） | ✅ |

- phaseRoot `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data`：执行前 ABSENT，由 driver 在
  第 1 attempt 内创建；**跨 4 runtime 单一路径不变**。
- outputRoot `lg032-cohort3-formal/{runs,evidence}`：执行前已 prepare 空 700；执行后仅含本 cohort3 四产物。

## 2. 冻结协议与本执行一致性

| 协议项 | 冻结 | 实测 |
|---|---|---|
| attempt 顺序 | `s1_units__A→s1_units__B→s2_pipeline__A→s2_pipeline__B`，各一次 | ✅ 同 |
| 真实上限 | total 192 / attempt 48 | ✅ M 全满足（84 总） |
| mode | 仅协作 mode；A 显式 off / B 显式 on；同 3 nodes/2 member/plan/objectives/input/permissions/tools/seed/truth/model/caps | ✅ mode 实测 & 恢复见 §4 |
| output / http / retry / parallel | `output≤16000` / `HTTP 120s` / `SDK retries 0` / concurrency 1 | ✅ 同名入口加载，未改 |
| worker / reviewer / repair | worker ≤12 model / ≤32 tool / reviewer ≤1 / repair ≤1 | ✅ 未改；repair 实耗 0 |
| controlled env | 仅 `DEEPSEEK_API_KEY`（值未打印/未入文档/repo） | ✅ |
| 入口 | 同 `COHORT3/run_formal.py`，不另起 helper，不切供应商 | ✅ |

## 3. 逐 attempt 结果（真实）

| # | attempt | delivered | ok | machine | 1st-round | elapsed(s) | gen reqs | ledger after | mode(期望) | restored_off | review | findings | unsub | repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `s1_units__A` | ✅ | ✅ | 5/5 | ✅ | 105.38 | 20 | 20 | False (A) | ✅ | passed | 3 | 0 | 0 |
| 2 | `s1_units__B` | ✅ | ✅ | 5/5 | ✅ | 59.21 | 20 | 40 | True (B) | ✅ | passed | 0 | 0 | 0 |
| 3 | `s2_pipeline__A` | ✅ | ✅ | 7/7 | ✅ | 96.83 | 17 | 57 | False (A) | ✅ | passed | 1 | 0 | 0 |
| 4 | `s2_pipeline__B` | ✅ | ✅ | 7/7 | ✅ | 115.49 | 27 | 84 | True (B) | ✅ | passed | 1 | 0 | 0 |

- 合计真实 generation **84**；总 wall（4 attempt 串行，含启动/验收）约 **≈ 6.5 分钟**。
- 每 attempt 均 `phases_seen=['awaiting_acceptance','executing','verifying']`、`final_phase=awaiting_acceptance`，
  经 human acceptance 绑定 `accept_response`（`status=accepted`），**幂等 same-request 二次 accept 返回 confirmed**，
  **错 target accept 返回 409 `illegal_transition`**；`check_records=[{"check_id":"evidence-present","status":"passed","detail":"4 evidence ref(s) recorded"}]`。
- `task_id`/`run_id`/`candidate_plan_hash`/seed head 见 §7；seed head 同 sample 内一致
  （s1 = `53458ac742b5aa4fd6913000aeeb69ae94cc80c1`，s2 = `6fa0fd006ff058a7299f5e6dc42013fa051303de`），
  `initial_head == seed_head`（运行前无外部写）。

## 4. mode-isolation 实测证据（同 cohort 单 settings.data_dir 跨 4 attempt）

- 入口 `_set_mode` 在 `build_runtime` **之前**经产品受控 `ConnectionService.update_settings` 写
  `decentralized_claim_enabled=(arm == "B")`；`_assert_active_mode` 在真 `build_runtime` 之后读**实际**
  dispatcher（`_autonomous_claim` / `_autonomous_pool` / `_decentralized_enabled()`）与三持久开关，
  任一不符即 fail-closed。
- 实测（`mode_snapshot_after_bootstrap`）：

| attempt | arm | expected | dispatcher claim | pool | decentralized() | congruent |
|---|---|---|---|---|---|---|
| `s1_units__A` | A | False | False | False | False | ✅ |
| `s1_units__B` | B | True | True | True | True | ✅ |
| `s2_pipeline__A` | A | False | False | False | False | ✅ |
| `s2_pipeline__B` | B | True | True | True | True | ✅ |

- **selector / claim 事件差**（run events jsonl，A 无 selector、B 有 selector）：
  `s1_units__A` lease_granted=0；`s1_units__B` lease_granted=3 / revoked=3；
  `s2_pipeline__A` lease_granted=0；`s2_pipeline__B` lease_granted=3 / revoked=3。
  ⇒ B 走候选池 claim/lease 调度，A 走程序调度，**模式边界清晰**。
- `mode_restore.restored_off=true` 四齐：每 attempt `finally` 显式恢复 `decentralized_claim_enabled=False`。
- **特别确认第 3 个 attempt 为 off**：`s2_pipeline__A` 紧接在 `s1_units__B`（on）之后，仍实测全 False，
  证明未继承前次 pool 模式。

## 5. 交付与审查（非 partial）

- 4/4 attempt `sample_delivered=true`，每个产生 **2 个 candidate diff**（2 subtask），
  `candidate_diff_count=2`；独立 reviewer 为 **真 model reviewer**（`reviewer_kind=model`、
  `connection_id=deepseek-v4-flash`、`credential_configured=true`），`code=review_completed`、
  `outcome=passed`、`unsubstantiated=0`。
- 真实 SDK 多 worker session：session_refs 数 A=3、B=6（B 的候选池额外 worker claim），
  磁盘 **native-sessions `*.db` 共 18 个**（600 权限），证明真实 SDK worker 已起。
- reviewer teardown 四齐 `status=done, agent_closed=true, proxy_stopped=true, confirmed=true`。
- **repair_rounds_spent=0** 四齐（无业务返修）；**无 recheck**。

## 6. 成本 / 计量

- **真实 generation 请求**：84（官方 per-attempt 计数；单 attempt 17–27，均 ≤48；总 ≤192）。
- **token / 计费**：SDK result 内 `model_usage`/`usage` 记为 `{"unknown": ["usage"]}`（SDK **不回报** per-attempt
  token）。故本 cohort3 **真实 token 数不可核 = unknown（不记 0）**。
- **开发 pi / shared pi 成本**：见 `LG032-SHARED-PI-COST-AUDIT.md`（snapshot `2026-10-15T21:24:34Z`）——
  该文件为**metadata 解析的工具自报估计（loggerprice = tool-reported estimate，非实际账单）**，且
  **shared unallocated**、未做 hard arm-level 拆分。LG032 confident 映射 26 logs / 1574 unique calls /
  noncache_in 1,678,454 / out 517,978 / cacheRead 124,136,832 / costEst 9.728773（量级估计）。
  **本报告不复用该口径作为 full-cost-saving**，也不把 request 数/时间当成本节省。
- **旧 032 invalid 106** = cohort1 87（mode-invalid）+ cohort2 19（entry assembly STOP）：**单列保留、不归零、
  不混入有效 AB、不补旧 cohort**；032 新已知上限 298 = 106 + 192。

## 7. 关键 hash / id / 账本（脱敏，未含 secret）

### 7.1 交付产物 sha256（result.json == evidence json，逐 attempt）

| attempt | sha256 | task_id | run_id | candidate_plan_hash |
|---|---|---|---|---|
| `s1_units__A` | `b54d3c018ac16a00ded280eb5588929923f9d6115b676848c5da963ef05a4d00` | `task_01M50QD1W3JVZ59516FXJQFGGH` | `run_01M50QD1Y8KDEJMS8KNZ5AFBN7` | `f73476375c33091d6cbff82a3ef54602ad8fc2585e5f770f5aa21d9043ad664b` |
| `s1_units__B` | `09c237d9d9978e05a4c5fc77dae126e604802cb7f8b534591df360991dabc309` | `task_01M50QGPEM42CCXFKZPNEX65PK` | `run_01M50QGPH9NC86HDP470A835M9` | `4301bd0384e9fb23ec96255a852902f3615fb8a1d24d2c30d516dbcc979552dd` |
| `s2_pipeline__A` | `0bf3c82326982da7eed3cd588febf991ba0dad6474bcff47322d676214e6f7f6` | `task_01M50QJVFRA9TDQ46RS3NWMDQH` | `run_01M50QJVJ7VVG83W1JFWFSFFN8` | `3519527fc0cbf9d778666f1012dd898eb66a3491b1a01b4794b646dd3fc94430` |
| `s2_pipeline__B` | `fe0bf73e7ff2124723250ef6d7da8bfc83147be5ffb1cf88ed1bf6f03c97620d` | `task_01M50QP4J3SNS0XSVKKP8X59ZP` | `run_01M50QP4NA18YBZBA4F7XC737T` | `025cc5d81e0bb7c91858142854872ecaf0acd5c3df3046ff31da6f62c34c7f44` |

### 7.2 物理 phase ledger（单一路径，跨 4 runtime 累加）

- 最终 `generation.count.json` = `{"count": 84}`，sha256 `fef0bd52e61e58a2f6200194bf7af5219a5d8c1f9ffd2dcbd7335fb81d92e68f`。
- `generation.jsonl` 84 行，sha256 `a266e2fd8fa80cbc828746b14d5b7aaaf0923d90c97331b42665295971aa3f72`。
- 每 attempt 前后账本 before/after 见 §3（20→40→57→84）。

### 7.3 逐 attempt ledger before/after & 记录

| attempt | ledger before | ledger after | SDK DB 数 | session_refs |
|---|---|---|---|---|
| `s1_units__A` | 0 | 20 | 3 | 3 |
| `s1_units__B` | 20 | 40 | 6 | 6 |
| `s2_pipeline__A` | 40 | 57 | 3 | 3 |
| `s2_pipeline__B` | 57 | 84 | 6 | 6 |

（以上 candidate_plan_hash / task_id / run_id 均取自对应 `result.json` 的
`accept_response.acceptance`。）

### 7.4 旧账本字节证据（preserved，未改）

| 账本 | 文件 | sha256 |
|---|---|---|
| cohort1 `{"count":87}` | `lg032-method-final-data/generation/generation.count.json` | `609946be7102a497ce9ddfbd1770aa8c2e7dd73925e5f48f93f3e9c2d8a01e68` |
| cohort1 jsonl (87 行) | `lg032-method-final-data/generation/generation.jsonl` | `beba08e0a1b3e77e4195a9ddb4d53a21a5d1826adf93f1b5ef45ba2af1871abd` |
| cohort2 `{"count":19}` | `lg032-cohort2-data/generation/generation.count.json` | `be90a0f9606c3c25a422bc22dc637c2b99af3e4d3b9d9179c5aee6aa78658585` |
| cohort2 jsonl (19 行) | `lg032-cohort2-data/generation/generation.jsonl` | `15a4bb003f844a7095632fa8a4ac97419b6f3a48d53858107b1bc4bf89595fbb` |

### 7.5 私有持久运行产物（项目旁、非 /tmp）

| 项 | 路径 | 权限 |
|---|---|---|
| phase data root / SoT / ledger / SDK native-sessions | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data/` | 775（driver `ensure_data_dir`，与旧 cohort2 一致）；session `*.db` 600 |
| formal runs/evidence | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal/{runs,evidence}` | 700 |
| 私有 stdout/stderr/result 副本 + STATUS | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-private-logs-20261015T212653Z/` | 700 |

## 8. 逐样本质量判断

- **s1_units（A label slugify + numeric clamp/in_range；B 同）**：两个 stub 均被**真实 overwrite 实现**，
  `slugify` 用 `re.compile(r"[^a-z0-9]+").sub("-", str(title).lower()).strip("-")`，`clamp`/`in_range`
  语义正确。machine gate 5/5；model reviewer 判 passed（A findings 3、B findings 0，**均 0 unsubstantiated**）。
  未调用 `view_file`；每文件一次写。**质量达标**。
- **s2_pipeline（A report/shapes 两模块；B 同）**：`shapes.area/perimeter` 处理 rect/circle 并对未知 kind
  抛 `ValueError`；`report.py` 正确 import 并格式化。machine gate 7/7；reviewer passed（findings 1 / 0 unsubstantiated）。
  **质量达标**。
- 两 sample 均**首轮 machine pass**，无需 repair/recheck。四 attempt 均在 `awaiting_acceptance` 由 acceptance 绑定交付。

## 9. 边界与合规

- **未自修 source/harness**：entry / driver / overlay / 产品 tree 零字节改动；tracked diff = 仅新增本报告 +
  R1 审计。未改 prompt / caps / tools / model / mode / budget / stop。
- **未补跑**：四 attempt 各一次，无重跑；无 worker replay；无未知写副作用重试。
- **未 STOP**：全程无 harness / mode / assembly / meter / hash / 未知写错误；无失败 attempt。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；私有日志/产物项目旁持久，非 /tmp；未 nested proxy /
  push / deploy / publish / **main merge**；未 mark 032 done；main `5df1956` 仍 clean。
- secret 仅 `DEEPSEEK_API_KEY` 由 env 读入，值未打印/未写文档/repo；不打印 prompt。
- 未碰 source/tasks（资料服务 21:13Z 复查不可达，本包不涉）。

## 10. 结论 / 下一步

- **新 cohort3 4 attempt 全部真实交付，质量达标，mode-isolation 成立，成本 84≪192**。
- **032 仍 in-progress；不 mark done；不 merge main**。结果提交独立入口（`ENTRY-INDEPENDENT-AUDIT-R1.md`）+
  本报告（脱敏）+ 私有证据；raw SDK / credentials 不入 repo。
- 交 PM：由 PM 决定 032 后续（本包不 self-done、不 main merge）。

## 11. 修订历史

- 2026-10-16（真实 provider 4 attempt）：新 cohort3 正式执行完成；阶段 0 R1 PASS；4/4 delivered；
  84 真实请求；mode A=off/B=on 实测；旧 106 保留单列；写本报告；精确 commit；clean 退出。
