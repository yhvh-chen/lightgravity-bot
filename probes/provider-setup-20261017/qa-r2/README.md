# LG-112 R2 QA harness (final candidate)

QA evidence only. This directory does **not** modify product source.

## Layout

- `QA-R2.md` — independent R2 report and verdict.
- `concurrency_probe.py` — original QA-R1 natural/legacy probe (kept as history).
- `concurrency_probe_r2.py` — R2 supported-service + real-HTTP reference/delete
  interleavings, natural stress, lock contention, raw-bypass (outside guarantee)
  and unpatched production-host controls.
- `http_probe.py` — real HTTP/API/security/budget/SDK-local-protocol probe.
- `qa_common.py`, `fixture_app.py` — isolated runtime: fresh temp data/secret/
  workspace roots, fixed QA accounts, controlled loopback fake OpenAI/Gemini
  upstream + dummy keys. The fake upstream is **not** a vendor.
- `tests/provider-modal.spec.ts` — real-browser acceptance (8 scenarios) with
  R2 compact-modal assertions and fresh screenshots.
- `logs/`, `screenshots/` — actual evidence.

## Commands used (explicit existing interpreter; no install)

From this directory, with the root venv and a temporary `node_modules` symlink to
the existing Playwright install:

```bash
PYTHONPATH=../../../backend:. \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python http_probe.py

PYTHONPATH=../../../backend:. \
  /home/yhvh/code/lightgravity-bot/.venv/bin/python concurrency_probe_r2.py

CHROME_BIN=/usr/bin/google-chrome \
LG_QA_PYTHON=/home/yhvh/code/lightgravity-bot/.venv/bin/python \
  ./node_modules/.bin/playwright test -c playwright.config.ts
```

The frontend must be built first with the existing root `frontend/node_modules`
(`npm run build`), and the fixture app serves that `frontend/dist`.

No real vendor/model/credential/user account is used. See `QA-R2.md` for exact
results, preserved failures and limits.
