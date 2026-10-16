# Selected-material prototype — demo assets (LG-045)

This directory holds **human-written English SAMPLE data** and its expected
facts for the selected-material rapid prototype (LG-042..047). It is used by
LG-046 integration and LG-047 QA.

> **These files are SAMPLE fixtures, not real sources, not OCR output, and not
> measured model results.** No model was asked to produce them. Every project
> name, ID, budget, date and person is invented and deliberately unique so that
> an unaided base model cannot reproduce it. `expected-facts.json` records
> **fixture truth (what the human wrote)** — it is **not** a record of what any
> model actually answered. **Model results remain unverified until LG-047 QA.**

## Files

| File | Role | Sample | OCR output |
|---|---|---|---|
| `fixtures/alpha-brief.txt` | Primary source (project ORION-71) | yes | no |
| `fixtures/beta-brief.txt` | Secondary source (project LUMEN-33) | yes | no |
| `fixtures/gamma-decoy.txt` | Contradictory decoy — leave **unselected** | yes | no |
| `fixtures/cross-task-negative.txt` | Cross-Task isolation negative marker | yes | no |
| `expected-facts.json` | Fixture ground truth + negative-case expectations | yes | no |

All files are plain UTF-8 text / JSON. They contain no hashes, no real source
IDs and no secrets.

## Why a decoy and a cross-Task marker

- `gamma-decoy.txt` re-uses the ORION name but with **different** owner, date
  and budget. If an answer quotes a decoy value, that is evidence of context
  leakage or hallucination — **not** a correct result. It must stay unselected
  so QA can prove the answer follows the *selected* source only.
- `cross-task-negative.txt` exists to prove the frozen rule that selection is
  scoped to `global` or a single Task and **does not carry across Tasks**
  (docs/10 §5/§8, docs/08 §6.6.1). Selecting it from a different Task must be
  rejected with `reference_invalid` (422) **before** model dispatch.

## Fixture checks (offline, no network)

`check_fixtures.py` verifies the assets without any model, network or product
call: UTF-8 parse, referenced files exist, word-count caps, and that the
Markdown guide links resolve. Run it from the repository root:

```bash
python3 examples/selected-material-prototype/check_fixtures.py
```

It is intentionally small and does not mirror the product tests.

## Limits

- These fixtures do **not** validate the product. They are inputs for a
  functional QA upload of **English plain text only**.
- No OCR truth is claimed or fabricated; these are plain text files, not
  scans.
- Correctness of any real answer is judged in LG-047, not here.

## See also

- Guide: [`docs/11-selected-material-demo.md`](../../docs/11-selected-material-demo.md)
- Frozen contract: [`docs/10-selected-material-prototype.md`](../../docs/10-selected-material-prototype.md)
- Interface contract: [`docs/08-interface-contract.md`](../../docs/08-interface-contract.md) §6.6.1
