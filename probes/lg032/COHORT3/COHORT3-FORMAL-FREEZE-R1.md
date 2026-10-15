---
title: "LG-032 COHORT3 冻结补遗 R1（入口 guard 极小返修后）"
doc_type: freeze-addendum
category: engineering
status: "ADDENDUM-R1 — entry guard narrowed to current attempt id; entry sha e8340f90; source 55e4de56 / driver 503a807f / overlay df565291 字节不变; same-cohort3 首请求前协议更正; 旧 106 cost 不变; 0 real provider; 032 in-progress"
experiment_id: lg032-cohort3-formal-entry-20261016
supersedes_entry_sha: "3efff40668ea73728e01037c718bc1c2b4b8e8d30c5373afb23b8e737de954cd"
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-entry
branch: fix/lg032-cohort3-entry
base_commit: "c4f6b55"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort3-entry-guard-fix（入口 guard 极小返修 owner；0 real provider）"
---

# LG-032 COHORT3 冻结补遗 R1

> 本补遗是 **COHORT3-FORMAL-FREEZE.md 的新版本补遗**（旧 freeze 文件字节不变），记录入口 guard 极小
> 返修后的**新 entry sha** 与**实际 target guard**。它在 **same cohort3 首请求之前**更正协议参数：
> 入口 guard 由「拒全部四个 attempt id」收窄为「**只拒当前 selected attempt id**」。**0 real provider**；
> **不改**旧 106 cost；**不**新增 cohort；formal NOT run；032 in-progress。

## 0. 与旧 freeze 的差异（唯一）

| 项 | 旧冻结（`COHORT3-FORMAL-FREEZE.md`） | 本补遗 R1 |
|---|---|---|
| entry sha256 | `3efff40668ea73728e01037c718bc1c2b4b8e8d30c5373afb23b8e737de954cd` | `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2` |
| prepare guard 范围 | 全部四个 attempt id（任一旧产物即拒，第二次 attempt 必 STOP） | **仅当前** `runs/<current>/` + `result.json` + `evidence/<current>.json`；其它既定 attempt 产物保留 |
| `--prepare-only` | 同函数，拒全部历史产物 | `current_attempt_id=None`：幂等，只建/核根，不碰历史文件 |
| budget / model / mode / driver / overlay / stop / product | — | **全不变** |
| caps | total 192 / attempt 48 | **不变** |
| 旧 cohort1(87)+cohort2(19)=106 cost | 保留 | **保留，不改不归零** |

## 1. 冻结身份（只读复核，实测）

| 项 | 值 | 判定 |
|---|---|---|
| entry `run_formal.py` | `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2` | 新版本 |
| overlay `MODE-ISOLATION/mode_config.py` | `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf` | ✅ 字节不变 |
| driver `run_attempt.py` | `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208` | ✅ 字节不变 |
| driver `final_cohort_config.py` | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` | ✅ 字节不变 |
| 产品 source tree `HEAD:backend/lightgravity` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | ✅ 字节不变 |
| four ATTEMPT_IDS | `s1_units__A / s1_units__B / s2_pipeline__A / s2_pipeline__B` | ✅ 不变 |
| caps | total 192 / attempt 48 / worker 12 / reviewer 1 | ✅ 不变 |

## 2. 实际 target guard（返修后语义）

- 入口实际调用：`prepare_output_roots(current_attempt_id)`；normal 路径由合法 CLI `choices` 组装
  `f"{args.sample}__{args.arm}"`，`--prepare-only` 传 `None`。
- 对**当前** id：`runs/<current>/` 已存在、或其 `result.json`、或 `evidence/<current>.json` 已存在 ⇒
  `SystemExit`（不覆盖）。
- 对**其它**既定 attempt id：不检查、不拒绝、不触碰；顺序链 `A→B→A→B` 可继续。
- 保留：`_assert_controlled` 的 symlink / pathscope / parent / permissions / mkdir 验证。

## 3. 合成验证

见 `REPORT-GUARD-FIX.md` §3：独立 nonce scratch（700）调用真实 prepare/guard，5/5 通过
（fresh mkdir+writeJSON / otherID 后 nextID 允许且 otherID bytes 不变 / 重复 currentID 拒且 bytes 不变 /
symlink-outside 拒 / prepare-only 幂等不覆盖）。`not_formal`。

## 4. 边界

- **0 real provider**；未 build runtime / Task / proxy / SDK；未发模型请求。
- 未自 formal；未 mark 032 done；未 merge main；未 nested / push / deploy / publish。
- 旧 reports 与旧 106 cost 逐字节保留；不新增 cohort；cohort3 预算 192/48/298 不变。
- 下游须**独立入口复验** PASS 后，方可由 PM 派 formal owner 发真实模型。

## 5. 修订历史

- 2026-10-16（0 real provider）：入口 guard 收窄至当前 attempt id；记录新 entry sha 与实际 target
  guard；same-cohort3 首请求前更正协议；不改旧 106 cost。
