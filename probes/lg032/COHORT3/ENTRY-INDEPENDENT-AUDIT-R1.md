---
title: "LG-032 COHORT3 独立入口验收 R1（阶段 0，0 real provider）— PASS"
doc_type: audit
category: engineering
status: "INDEPENDENT-AUDIT-R1 PASS — narrowed prepare guard supports the full 4-attempt sequential chain; 0 model; authorized to run cohort3 formal (4×48=192); 032 in-progress; no self formal/done"
experiment_id: lg032-cohort3-entry-independent-audit-r1-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "b634238"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-independent-audit-r1（独立入口验收 owner；非产品/driver/entry 作者；0 real provider）"
---

# LG-032 COHORT3 独立入口验收 R1（阶段 0）

> 独立于入口作者的新 `pi` context。**0 real provider**（未 build_runtime / Task / proxy / SDK；未发任何真实
> provider 请求；未加载/运行 model）。**未自修任何代码**。所有合成验证只在独立 nonce scratch（700）进行，
> **绝不**写正式 attempt id / 正式 output root / phase data root。旧报告/旧冻结/旧成本逐字节保留。

## 0. 结论（先给判断）

- **阶段 0 独立入口门 R1 = PASS。** 旧 `ENTRY-INDEPENDENT-AUDIT.md` 的唯一 FAIL 根因（入口 prepare helper
  `_assert_no_attempt_artifacts()` 无条件拒**全部四个**冻结 attempt id ⇒ 第 2 次 attempt 必 STOP）已在
  commit `b634238` 收窄为「**只拒当前 selected attempt id**」。
- 本次独立复验（调用**真实** prepare/guard，仅重定向受控路径常量到 nonce scratch）证明：**完整四次顺序链
  `s1_units__A → s1_units__B → s2_pipeline__A → s2_pipeline__B` 可逐一 prepare/保存**；其它既定 attempt 产物
  不阻塞后续、字节不变；重复**当前** attempt id 仍硬拒且不覆盖；`--prepare-only`（`current=None`）幂等、
  只建/核根、不碰历史；phaseRoot 始终未创建。
- 8/8 顺序链检查 + 4/4 负例守卫检查全部符合预期。⇒ **条件授权成立，按授权执行正式 cohort3 四次真实采样。**
- 032 仍 in-progress；未 mark done；未 merge main；旧 cohort1 87 / cohort2 19 **未删未改未归零**。

## 1. 独立身份核（只读；sha / tree / 版本全部一致）

| 项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| worktree / cwd | `lg032-cohort3-entry` | 同 | ✅ |
| branch | `fix/lg032-cohort3-entry` | 同 | ✅ |
| HEAD | `b634238` | `b6342388375b407913f1d3d7e895a8b9436277e4` | ✅ |
| tracked diff | clean | 空（`git status --porcelain` 空） | ✅ |
| entry `run_formal.py` | `e8340f90…90e2` | `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2` | ✅ |
| overlay `mode_config.py` | `df565291…88bf` | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ 未改 |
| driver `run_attempt.py` | `503a807f…6208` | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ 未改 |
| driver `final_cohort_config.py` | `a04a8f30…a117` | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ 未改 |
| 产品 tree `HEAD:backend/lightgravity` | `55e4de56…` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | ✅ |
| SDK / contract / model | `0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` | 同（`--freeze-identity`） | ✅ |
| caps | total 192 / attempt 48 / worker 12 / reviewer 1 | 同（`final_cohort_config.py`） | ✅ |

- 入口 sha 与 `COHORT3-FORMAL-FREEZE-R1.md` / `REPORT-GUARD-FIX.md` 声明一致；driver/overlay sha 与旧
  freeze / SERIAL-R1 冻结一致。旧 freeze（`3efff406…`）与旧 FAIL 报告字节未改（本 R1 为**新文件补遗**）。

## 2. mode / bootstrap / restore / 装配路径核（PASS）

- **显式 mode（A=False / B=True）**：`run_attempt.py` `_set_mode`（line 923-953）在 `build_runtime` **之前**
  经产品受控 `ConnectionService.update_settings` 写入 `decentralized_claim_enabled=(arm == "B")`；A 显式写
  `False`、B 显式写 `True`，**不继承**前次 attempt（同一 `settings.data_dir`）。
- **bootstrap 实际 assert**：`run_attempt.py` `_assert_active_mode`（line ~956-1000）在真 `build_runtime` 之后
  读**实际** dispatcher 对象（`_autonomous_claim` / `_autonomous_pool` / `_decentralized_enabled()`）与三持久
  开关，任一 `is not want` 即 `SystemExit`（fail-closed）⇒ 后续 arm A 绝不继承 arm B 的 pool 模式。
- **restore off 未变**：`finally` 调 `_safe_restore_mode`，恢复 `decentralized_claim_enabled=False` 并记
  `restored_off`。
- **入口只做路径适配**：`_load_overlay_config()` 仅重定向
  `WORKTREE/COHORT/HARNESS_DIR/MODE_DIR/RUNS_DIR/EVIDENCE_DIR/FIXTURES_DIR/PHASE_DATA_DIR/LEDGER*` 路径常量；
  **不改** model/plan/profile/tools/truth/caps/seed，不复制 driver 逻辑，不换供应商。`--freeze-identity` 打印
  `ATTEMPTS` 与 192/48，四条命令同入口加载 cohort3 实际常量；无 fake/sink/stop/root 绕过。
- 结论：mode / 装配 / 版本 / caps 层面与冻结/SERIAL-R1 一致（PASS）。

## 3. 关键核：prepare 函数能否承载完整四次顺序（**PASS**）

### 3.1 代码事实（只读，`b634238` 修复后）

- `_assert_no_attempt_artifacts(current_attempt_id=None)`（`run_formal.py:172-200`）：`None` 直接返回（不查
  任何历史）；若 id 不在 `ATTEMPT_IDS` 拒；否则**只**检查 `runs/<current>/`、其 `result.json`、
  `evidence/<current>.json`，任一存在即 `SystemExit`（不覆盖）。
- `prepare_output_roots(current_attempt_id=None)`（`:203-291`）透传该 id；normal 路径由**合法 CLI `choices`**
  组装 `f"{args.sample}__{args.arm}"`（`:487`），`--prepare-only` 传 `None`（`:412`）。保留
  `_assert_controlled` 的 symlink / pathscope / parent / permissions / mkdir 验证。
- 对照：driver 自身 attempt gate 按当前 attempt id（`run_attempt.py:534-540`），与收窄后的入口 guard 语义一致。

### 3.2 实测复现（独立 nonce scratch；0 real provider）

- scratch：`lg032-cohort3-audit-r1-20261015T212613Z-auditr1`（mode `700`，唯一 nonce）。
- 方法：`importlib` 加载**真实**入口 `probes/lg032/COHORT3/run_formal.py`，**仅**把其模块级
  `FORMAL_OUTPUT_DIR/RUNS_DIR/EVIDENCE_DIR/PHASE_DATA_DIR` 与 sanctioned parent `WORKTREES_DIR` 重定向到
  scratch（**非** SDK 根 / **非**核心授权）；调用**真实** `prepare_output_roots()` /
  `_assert_no_attempt_artifacts()`。**不重写、不仿制、不放松** guard。
- 合成「前一次其它 attempt 已完成」与 driver 写产物一致：`runs/<id>/result.json` + `evidence/<id>.json`，
  记录 `synthetic: true`，**绝不**写正式 id / 正式 root / phase root。脚本 `seq_prepare_r1.py`
  sha256 = `6b1b2c01cc61b8faf9a161dd7fd44c8b2e198b4e33e290309b635e35e03aa7a1`；结果
  `seq_prepare_r1_result.json` sha256 = `7a08d26a0c069fa9fa56f8084c82cf9a2c939681037489bdfed43825561b78dd`。

| 步骤 | 场景 | 期望 | 实测 |
|---|---|---|---|
| 1 | 空 scratch 首次 prepare `s1_units__A` | PREPARED，700 | ✅ prepared；runs/evidence 700；phaseRoot ABSENT |
| 2 | fresh EVIDENCE_DIR 真 mkdir + writeJSON | 可写 | ✅ ok=true |
| 3a | 写完 `s1_units__A` 产物 | — | ✅ result/evidence 落盘 |
| 3b | **其它 attempt id 产物存在 → prepare `s1_units__B`** | 应 PREPARED | ✅ **PREPARED** |
| 3c | 上述后 `s1_units__A` 字节 | 不变 | ✅ unchanged=true |
| 5 | **完整四次顺序链**（每步后写产物再 prepare 下一个） | 四次 PREPARED | ✅ `s1_units__A`/`s1_units__B`/`s2_pipeline__A`/`s2_pipeline__B` **全 PREPARED** |
| 4 | 重复**当前** `s2_pipeline__B`（已有产物） | 拒且不覆盖 | ✅ REFUSED（`attempt dir already exists`）；bytes 不变 |
| 6 | `--prepare-only`（`current=None`）连跑两次 | 幂等、不碰历史 | ✅ PREPARED×2、`created_now=[]`、四 id 历史 bytes 不变、phaseRoot 仍 ABSENT |

- 结果字段：`verdict.all_ok=true`、`step5_full_sequential_chain_possible=true`、
  `step4_repeat_current_refused=true`、`step3_other_bytes_unchanged=true`、`real_generation=0`。

### 3.3 负例守卫（PASS，独立 scratch）

脚本 `seq_negative_r1.py` sha256 = `7fda663dcd90914ba44ee862173d7506dab6cd435ab8d988cc60d28dbc5a5d84`；结果
`seq_negative_r1_result.json` sha256 = `fed89ed3d2aaf278642d5c7d63ba757c77806826e31b5df89e0ace8a1f0ceaad`。
四例**全部 REFUSED**：未知 id `bogus__Z`；output root 为软链；parent（WORKTREES_DIR）为软链；output root
不在受控 parent 下。

### 3.4 判定

- **「前一次其它 attempt id 产物已存在时，下一新 attempt 仍可准备/保存」= 成立** ⇒ 旧 FAIL 已消除。
- 「重复当前 attempt id 必须拒绝、不覆盖」= 成立。 「fresh EVIDENCE_DIR 真 mkdir 且能 writeJSON」= 成立。
- 「完整 4 attempt 顺序链可跑」= 成立。⇒ **门 PASS。**

## 4. 正式目录状态（证据，独立核验）

| 项 | 状态 | 判定 |
|---|---|---|
| phase data root `lg032-cohort3-data` | **ABSENT**（identity/audit 前后均缺） | ✅ 须未创建 |
| outputRoot `lg032-cohort3-formal` | 存在，`runs/` 与 `evidence/` 均 700 **空** | ✅ 允许已 prepare 为空 700 |
| 四 attemptID / `runs/<id>` / `result.json` | **不存在** | ✅ 无 formal 产物 |
| formal `evidence/*.json` | **不存在** | ✅ |
| formal ledger / task | **不存在** | ✅ |
| 旧 cohort1 ledger `lg032-method-final-data` | `{"count":87}`，jsonl 87 行 | ✅ 保留 |
| 旧 cohort2 ledger `lg032-cohort2-data` | `{"count":19}`，jsonl 19 行 | ✅ 保留 |
| `--help` / `--freeze-identity` | rc=0；只读或幂等；root 状态不变 | ✅ |

- 旧 cohort1 87 + cohort2 19 = **106 协议失败成本保留**（sha 见下）；cohort3 预算 192/48/298 不变。
- scratch 内全部合成产物**仅在**独立 scratch root，**未**写正式 attempt id / 正式 root / phaseRoot。
- **0 forward / 0 real provider**：全程未 build runtime / Task / proxy / SDK，未发模型请求。

### 4.1 旧账本字节证据（preserved）

| 账本 | 文件 | sha256 |
|---|---|---|
| cohort1 `{"count":87}` | `lg032-method-final-data/generation/generation.count.json` | `609946be7102a497ce9ddfbd1770aa8c2e7dd73925e5f48f93f3e9c2d8a01e68` |
| cohort1 jsonl (87) | `lg032-method-final-data/generation/generation.jsonl` | `beba08e0a1b3e77e4195a9ddb4d53a21a5d1826adf93f1b5ef45ba2af1871abd` |
| cohort2 `{"count":19}` | `lg032-cohort2-data/generation/generation.count.json` | `be90a0f9606c3c25a422bc22dc637c2b99af3e4d3b9d9179c5aee6aa78658585` |
| cohort2 jsonl (19) | `lg032-cohort2-data/generation/generation.jsonl` | `15a4bb003f844a7095632fa8a4ac97419b6f3a48d53858107b1bc4bf89595fbb` |

## 5. 边界与合规

- **未自修代码**：entry / driver / overlay / 产品源**零字节改动**；tracked diff 空。修复来自入口作者
  `b634238`，本 owner 只**独立复验**。
- **0 real provider**；mode 未运行；无新 fake/real。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖正式或旧产物；合成验证只在独立 nonce scratch（700）。
- 未 nested proxy / push / deploy / publish / main merge；未 mark 032 done；未自 formal。
- 旧 reports / 旧 freeze / 旧 106 cost 逐字节保留。

## 6. 结论 / 下一步

- **阶段 0 独立入口门 R1 = PASS** ⇒ 按 PM **已授权**条件，**执行正式 cohort3 四次真实采样**，顺序
  `s1_units__A → s1_units__B → s2_pipeline__A → s2_pipeline__B`，每 attempt 唯一一次，各 48，总 192。
- 正式执行以 `COHORT3/run_formal.py` 同入口（`.venv` = `/home/yhvh/code/lightgravity-bot/.venv`），
  不另起 cohort、不补旧 cohort、不切供应商、不改 prompt/caps，`0.1.22` SDK。
- 032 仍 in-progress；不 mark done；不 merge main。

## 7. 修订历史

- 2026-10-16（阶段 0，0 real provider）：独立入口验收 R1 **PASS**（收窄 guard 后完整四次顺序链成立）；
  合成 8/8 + 负例 4/4；旧 106 账本字节证据记录；精确 commit 本报告后再执行正式 cohort3。
