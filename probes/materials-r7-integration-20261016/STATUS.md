---
title: "Materials R7 集成 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
---

# Materials R7 集成 STATUS

## Phase

- `phase = INTEGRATED`（A→B→C→D→E 顺序 `--no-ff` 已合入 `main`；LG-035 置 done；LG-037 保持 in-progress）。主代理只 PM，无嵌套派工、无新模型探针。
- Base (pre-merge) `main@2d76c83`（clean、预期）。
- **Post-merge main**: 见下（提交精确 HEAD 见收尾提交后的 `git rev-parse HEAD`；合并链 `89b0cc1`→`7eb88fe`→`e8a8e40`→`95b66bf`→`5f84503`）。

## Merge chain (real, no conflicts, no duplicate pick)

| Step | Branch @ tip | Merge commit |
|---|---|---|
| A | `test/materials-fixtures-r7-20261016@f21d6e3` | `89b0cc1` |
| B | `fix/materials-layout-r7-20261016@8182d36` | `7eb88fe` |
| C | `investigate/materials-endpoint-r7-20261016@1cfa417` | `e8a8e40` |
| D | `test/materials-ocr-cohort-r7-20261016@97c4f8f` | `95b66bf` |
| E | `fix/materials-table-mode-r7-20261016@4917413` (base `8182d36`, descends B) | `5f84503` |

Source tips unchanged; all five source worktrees clean; all other historical worktrees/dirty preserved.

## Checks (real exits, on merged candidate)

| Command | Exit | Result |
|---|---|---|
| `mypy` | 0 | 138 source files clean |
| `pytest tests/sources -q` | 0 | 147 passed, 1 skipped |
| `pytest tests/sources/ocr/test_layout.py test_table_mode.py -q` | 0 | 28 passed |
| `python probes/materials-table-mode-r7-20261016/offline_gate.py` | 0 | ALL_OK (byte-identical regeneration) |
| `tasks validate` | 0 | 41 tasks / 0 diagnostics |
| `tasks digest` | 0 | 38 done / 1 in-progress / 2 todo, complete=true, ready=[] |

Raw log: `evidence.txt`.

## Contract determination

- `prompt_kind`/`prompt_sha256`/`table_classification` = opaque local derivative evidence only (`derivative/ocr_evidence.jsonl` + pages `source_derivative`) ⇒ internal/opaque extension, **NO version bump**. Contract stays `1.11.0`; SDK `0.1.22`.
- `LIGHTGRAVITY_OCR_TABLE_MODE` optional non-secret env, default OFF; accepted values `1/true/yes/on` and `0/false/no/off` (case-insensitive); other values explicit error. Documented in docs/08 §6.6, docs/09, README.

## State

- **LG-035 → `done`（待 LG-040 集中版本 QA）**; only frontmatter `status` + body evidence changed; assignee/IDs preserved.
- **LG-037 `in-progress`** (new real rank 7/10 but old R5 image hard-gate FAIL unchanged; no cross-modal quality claim).
- **LG-040 / LG-041 remain locked** (LG-037 still blocks LG-040).
- Counts: **38 done / 1 in-progress / 2 todo**.

## Cost (separate, unknown ≠ 0)

- Current integration phase product LAN calls: **0** (no new POST/GET/ASR/embedding, no new model probes).
- Source history: C embedding **2 POST + 2 GET**; D OCR **3 POST + 1 GET**; E OCR **2 POST + 1 GET**; acquisition A **7 GET + 1 download** (incl. redundant size checks).
- pi/DeepSeek cost: **unknown, not zero**. LAN/endpoint price: unknown. Audio: 0.
- No push / deploy / publish / reset / clean. No `.env` copied.
