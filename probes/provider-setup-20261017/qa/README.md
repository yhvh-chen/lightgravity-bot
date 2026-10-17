# LG-112 QA harness

Isolated QA evidence only; no product source is modified by this directory.

## Run

```bash
# from the QA worktree
cd probes/provider-setup-20261017/qa
# e2e node_modules is a temporary symlink to the existing Playwright install
/home/yhvh/code/lightgravity-bot/.venv/bin/python -m py_compile qa_common.py fixture_app.py http_probe.py concurrency_probe.py
PYTHONPATH=../../../backend:. /home/yhvh/code/lightgravity-bot/.venv/bin/python http_probe.py
PYTHONPATH=../../../backend:. /home/yhvh/code/lightgravity-bot/.venv/bin/python concurrency_probe.py
./node_modules/.bin/playwright test -c playwright.config.ts
```

The Playwright global setup starts the real candidate app on isolated loopback
ports with fresh temp roots and a controlled loopback fake OpenAI/Gemini
upstream. It never contacts `8123/5173/18123`, a real account, a real key or a
vendor. The fake upstream is not real-vendor verification.

Artifacts: `logs/`, `screenshots/`, and the final `QA-R1.md` verdict.
