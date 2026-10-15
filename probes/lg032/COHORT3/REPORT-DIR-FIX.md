---
title: "LG-032 COHORT3 入口目录装配最小返修 + 无模型真实入口持久化预检报告"
doc_type: report
category: engineering
status: "FIX-READY-for-independent-audit；本包 0 real provider；未跑 mode；未 mark 032 done；未 merge main；旧 raw/ledger/report/worktree 逐字节保留"
experiment_id: lg032-cohort3-entry-dir-fix-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "08d6d43"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-entry（入口目录装配最小返修 owner；非产品/driver 作者）"
---

# LG-032 COHORT3 入口目录装配最小返修 + 无模型持久化预检

## 0. 一句话结论

- 缺陷 = **COHORT2 正式入口把 `EVIDENCE_DIR` 指向全新独立输出 root，但入口与 driver 都不创建该目录**；
  首个真实 attempt 到 `run_attempt.py:888` 写 evidence 时 `FileNotFoundError` 终止（COHORT2 STOP）。
- 本包 **仅修入口受控目录准备**：新 COHORT3 入口新增一个函数 `prepare_output_roots()`，在真实
  attempt 之前（也只此一件事）预创建 `runs` / `evidence` 两个受控目录（mode `700`）。
- **`--prepare-only` 直接调用正式入口实际同一个 `prepare_output_roots()`**，不 build_runtime / Task /
  proxy / SDK / 生成；已在全新根上跑通，证实正式入口的 write 结果父目录存在。
- **本包 0 real provider 生成**（未 build runtime、未起 SDK、未发模型请求）；mode 未运行。
- 旧 cohort1（87 mode-invalid）与 cohort2（19 entry-FileNotFound）= **106 失败协议成本永久单列**，
  本包**未删/未改/未补/未归零**；032 仍 **in-progress**（不 done、不 merge）。

## 1. 缺陷复现与根因（只读）

COHORT2 STOP 的原始事实（`COHORT2-QA/COHORT2-FORMAL-REPORT.md` §3.5，逐字节保留）：

```
FileNotFoundError: [Errno 2] No such file or directory:
  '/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-formal/evidence/s1_units__A.json'
  at run_attempt.py:888  (C.EVIDENCE_DIR / f"{attempt_id}.json").write_text(...)
```

根因（确定性、非瞬态）：

| 层 | 行为 | 证据 |
|---|---|---|
| driver | 只 `mkdir` `RUNS_DIR/<attempt_id>`（`run_attempt.py:532/540/552/559/561`），**从不创建 `EVIDENCE_DIR`** | 只读 |
| cohort2 入口 | 只设置/断言 `C.EVIDENCE_DIR`，**无 mkdir** | `COHORT2-QA/run_formal.py`（未改） |
| 旧布局为何不炸 | 旧 `EVIDENCE_DIR = COHORT/evidence` 是**已 commit 的 repo 目录**（预先存在） | 只读 |
| 模型正常失败也需持久结果 | evidence 副本写在 `result.json` 之后、try 块内，失败直接终止 | `run_attempt.py:888` |

**结论**：模型无论成功/失败都要落 evidence；缺父目录 ⇒ 协议在真实执行中途不可恢复地终止。

## 2. 最小 diff（仅入口受控目录准备）

新增文件（仅此三处，均为**新**文件；无 tracked 文件被修改）：

| 文件 | sha256 | 作用 |
|---|---|---|
| `probes/lg032/COHORT3/run_formal.py` | `3efff406…54cd` | 新 COHORT3 正式入口（复用同一 modefixed driver + 唯一新增 `prepare_output_roots`） |
| `probes/lg032/COHORT3/.gitignore` | `943af652…dc65` | 不提交 bytecode / 原始 runtime 产物 |
| `probes/lg032/COHORT3/SOURCE-UNCHANGED-EVIDENCE.txt` | — | driver/overlay/产品/旧成本不变证据 |

入口相对 cohort2 入口的**唯一功能新增**：

```
def prepare_output_roots() -> dict:      # 唯一新增的目录准备函数
    _assert_controlled(OUTPUT_ROOT, parent=WORKTREES_DIR)   # 拒绝未知/软链/越界
    _assert_no_attempt_artifacts()                          # 四 attemptID/result/evidence 存在即拒
    mkdir OUTPUT_ROOT (700, exist_ok, parents)
    _assert_controlled(RUNS_DIR,     parent=OUTPUT_ROOT)
    _assert_controlled(EVIDENCE_DIR, parent=OUTPUT_ROOT)
    mkdir RUNS_DIR / EVIDENCE_DIR    (700, exist_ok)        # 不覆盖任何已存在 attempt/output 文件
    # 不创建 phaseRoot；不 build runtime/Task/proxy/SDK；不发 generation
```

- **不改** driver / budget / model / tools / stop / state / 模式；driver 与 overlay 字节不变（见 §6）。
- **不宽 root**：`_assert_controlled` 只承认冻结的受控父目录，`resolve(strict=False) != path` 即拒
  （软链逃逸），父目录非真实目录/为软链即拒。
- **不覆盖**：`exist_ok=True` 允许幂等复检，但 `_assert_no_attempt_artifacts()` 保证四个 attempt id /
  `result.json` / `<id>.json` 任一存在即拒跑 —— 绝不用 `exist_ok` 掩盖既有 attempt。
- **不创建 phaseRoot**：`lg032-cohort3-data` 由 driver 在真实 attempt 内创建（本包预检后仍 **ABSENT**）。

## 3. 新 COHORT3 路径（明确固定）

| 项 | 绝对路径 |
|---|---|
| 新持续 phase data root | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data` |
| 新正式 output root | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal` |
| RUNS_DIR | `…/lg032-cohort3-formal/runs` |
| EVIDENCE_DIR | `…/lg032-cohort3-formal/evidence` |

- 新 entry 独立放 `probes/lg032/COHORT3/run_formal.py`；**旧 entry `COHORT2-QA/run_formal.py` 原字节不动**
  （sha `a7477753…3040`，见 §6）。
- 复用已 QA 的 modefixed driver（`FINAL-COHORT/harness/run_attempt.py`，字节不变）。

## 4. Modes 与预检语义（identity/help 不写目录；prepare-only 受控写）

| 模式 | 行为 | 副作用 |
|---|---|---|
| `--help` | argparse 帮助 | **无**（rc=0，root 前后 ABSENT） |
| `--freeze-identity` | 打印非敏感身份（entry/overlay/driver sha、phaseRoot、RUNS/EVIDENCE、四 attemptID、192/48、mode polarity、source tree） | **无**（不 mkdir、不 build、不发请求；root 前后 ABSENT） |
| `--prepare-only` | 调用**同一** `prepare_output_roots()`；在**全新 NONCE scratch** 写合成准备记录 | **受控 mkdir×2（+root）×1（幂等）**，显式记录 |
| `--sample/--arm`（正式） | 同样调用 `prepare_output_roots()`，再 `run_attempt(..., dry_run=False)` | 真实 attempt（本包**未执行**） |

要点：

- **同一 prepare 函数**：`--prepare-only`（line 393）与正式路径（line 468）都调用
  `prepare_output_roots()`（定义 line 198），不存在第二份目录准备逻辑。
- **合成记录明确标注** `not_formal / not_product_result`，写入 **fresh NONCE scratch**
  （`lg032-cohort3-prepare-scratch-<utc>-<nonce>/prepare-record.json`），**绝不**向四个正式 attempt id
  路径或 phaseRoot 写假 result/evidence。
- **identity/help 不悄悄创建目录**；`--prepare-only` 的受控副作用已在 stdout 与 scratch 记录中如实登记。

## 5. 预检实测（从全新根执行；0 real provider）

预检顺序（root 起初全部 ABSENT）：

1. `--help` → rc=0；`lg032-cohort3-data` / `lg032-cohort3-formal` 仍 **ABSENT**。
2. `--freeze-identity` → 全部 sha `[OK]`；phaseRoot_exists=False；outputRoot_exists=False；
   root 仍 **ABSENT**。source_tree = `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f`。
3. `--prepare-only`（全新根）→ rc=0；`created_now` = `[output root, runs, evidence]`；
   三目录 `mode=700`；`runs/`、`evidence/` **空**；`phase_data_dir_exists=False`；
   `attempt_ids_absent=True`；`real_generation=0`。
4. 幂等复跑 `--prepare-only` → rc=0；`created_now=[]`；目录仍 700/空；无 attempt 产物。
5. 文件系统核验（`find` 输出）：

```
lg032-cohort3-formal
lg032-cohort3-formal/evidence      (700, empty)
lg032-cohort3-formal/runs          (700, empty)
```

  **四 attemptIDs / runs/<id> / result.json / ledger / task 全部不存在**；`lg032-cohort3-data` **仍 ABSENT**。

反例（negative）守卫实测（在 `/tmp` 独立沙盒 monkeypatch 常量的 4 个 case，**不碰正式根**）：

| case | 期望 | 结果 |
|---|---|---|
| output root 为软链 | 拒 | ✅ refused（resolve≠path） |
| 全新受控根 | 可 prepare | ✅ runs/ created |
| 预存 attempt dir `runs/s1_units__A` | 拒（不掩盖） | ✅ refused |
| 预存 evidence `evidence/s1_units__A.json` | 拒 | ✅ refused |

**预检并非只 print 字符串路径**：它实际创建了 `runs` / `evidence` 两个 700 空目录，并证实正式入口
evidence 写入目标父目录存在；也非继承已 commit 目录（旧 `COHORT/evidence` 是 repo 目录，新 root 无此便利）。

## 6. source / driver hash 未变 + 旧成本保全

| 项 | 期望 | 实测 |
|---|---|---|
| `run_attempt.py` | `503a807f…6208` | ✅ 同 |
| `final_cohort_config.py` | `a04a8f30…a117` | ✅ 同 |
| `mode_config.py`（overlay） | `df565291…88bf` | ✅ 同 |
| 旧 cohort2 入口 | 原字节 | ✅ `a7477753…3040`（`git diff` 空） |
| 产品 tree | `55e4de56…` | ✅ 同（`HEAD:backend/lightgravity`） |
| `git diff --stat HEAD`（tracked） | 空 | ✅ 空（仅 3 个新文件） |
| cohort1 `generation.count.json` | 87 | ✅ `{"count":87}` |
| cohort2 `generation.count.json` | 19 | ✅ `{"count":19}` |
| cohort2-formal `evidence/` | 仍缺失（STOP 证据） | ✅ ABSENT |
| cohort2-qa / mode-isolation worktree | clean 未碰 | ✅ 0 行 status |

- **未** `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名；旧 raw/Run/ledger/report/worktree 未删改。
- **未** nested proxy / push / deploy / publish / main write；**未**动 `8123` 或他包进程；**未** mark 032 done。

## 7. 预算（冻结前口径；before 正式新调用再冻）

- **新 COHORT3 同协议**：4 attempt × 48 = **192**（same 4 sample/arm、seed、3 plan、48 cap；default off；
  仅 arm B 在 attempt 内显式开启）。其余协议不变。
- **旧 invalid 106 单列** = cohort1 87（mode-invalid）+ cohort2 19（entry FileNotFound）——**永久单列**，
  不洗、不补 attempt、不假装 validAB、不归零。
- **032 新已知上限 298 = 106 + 192**。
- **本包不 formal**；实际预算在**首个新真实调用之前**再冻结。
- **补遗准确纠正**：旧 COHORT2 报告 `COHORT2-FORMAL-REPORT.md` §3.4 写「剩 48×3=144」**不精确**——
  32 位口径下 cohort2 已耗 19、总上限 192，故 cohort2 未执行剩余应为 **192−19 = 173**（非 144）。
  该处**仅在补遗准确纠正，原历史报告逐字节保留**（见本 §8 修订/补遗，与 `COHORT2-FORMAL-REPORT.md`
  本文件**不覆写**）。
- **本 owner pi 开发/QA 成本 = unknown**（不记 0，不预设省 token）；shared pi 成本 unknown。

## 8. 8 轮记录（REPORT-DIR-FIX，逐轮）

| # | 轮次 | 动作 | 观察 / 结论 | 真实 provider |
|---|---|---|---|---|
| 1 | R1 读规约 | 读 `agent.md`、`COHORT2-FORMAL-REPORT.md` 关键 STOP 段、`run_formal.py` 必要局部（≤150 行）、`mode_config.py`、`run_attempt.py` 局部 | 确认缺陷=evidence 父目录缺失；driver 只 mkdir runs | 0 |
| 2 | R2 建 worktree | 新持久 worktree `lg032-cohort3-entry`，branch `fix/lg032-cohort3-entry`，base `qa/lg032-cohort2@08d6d43` clean | HEAD=08d6d43；仅新文件 | 0 |
| 3 | R3 写入口 | 新增 `COHORT3/run_formal.py`（同一 prepare 函数 + `--prepare-only` + 受控守卫）+ `.gitignore` | 编译 OK；driver/overlay 只读 | 0 |
| 4 | R4 只读身份 | `--help`、`--freeze-identity` | rc=0；sha 全 `[OK]`；root 前后 ABSENT | 0 |
| 5 | R5 修复守卫 | 首次 `--prepare-only` 因「output root 父目录不存在」误拒 → 改为先守卫+创建 output root，再守卫 runs/evidence | 纠正后全新根 prepare rc=0 | 0 |
| 6 | R6 预检 | 全新根 `--prepare-only` + 幂等复跑 + `find`/mode 核验 | 目录 700/空；phaseRoot 仍 ABSENT；四 attemptID 不存在 | 0 |
| 7 | R7 负例 | `/tmp` 沙盒 4 case（软链/全新/attempt dir/evidence file） | 软链与既有产物均被拒；全新可 prepare | 0 |
| 8 | R8 保全+报告 | hash/成本/worktree 保全核验；写 `SOURCE-UNCHANGED-EVIDENCE.txt` + 本报告 + 冻结候选 | tracked diff 空；87/19 未动；提交（精确、不空目录 gitlink/secret） | 0 |

**8 轮内 0 real provider；mode 未运行；无新 fake/real。**

## 9. 边界与下一步

- **本包 0 real provider**：未 build_runtime/Task/proxy/SDK、未发模型请求；`--prepare-only` 只做受控 mkdir。
- 固定目录 `lg032-cohort3-data` + `lg032-cohort3-formal/{runs,evidence}` 已按约定「**outputroot 预创建合法**」
  落地；`phaseDataRoot` 可仍未建（实测 ABSENT），而四 attemptIDs/runs/result/ledger/task 不得存在（实测不存在）。
- **交独立新 formal context 审核**：entry / 实际 prepare / 无 attempt 产物；审核通过后再
  **conditional 执行**真实 formal。本包**不 mark 032 done**、不改协议、不批预算。
- 旧报告「剩余 144」只在本报告 §7 **补遗准确纠正**（173），原历史保留。

## 10. 修订历史

- 2026-10-16（真实 provider=0）：COHORT3 入口目录装配最小返修；新增 `prepare_output_roots` 与
  `--prepare-only`；全新根预检 + 负例 + 保全核验通过；写冻结候选。**不 formal、不 mark 032 done、不 merge。**
