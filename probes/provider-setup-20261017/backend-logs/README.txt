LG-109 backend evidence commands (run from the worktree)
========================================================

Environment:
- worktree: /home/yhvh/code/lightgravity-bot-worktrees/provider-backend-20261017
- branch: feat/provider-backend-20261017
- Python/venv: /home/yhvh/code/lightgravity-bot/.venv (existing dependencies)
- PYTHONPATH=backend so the worktree package is imported, not the main checkout

Targeted tests:
  PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m pytest \
    tests/adapter/test_provider_matrix.py \
    tests/adapter/test_sdk_config_provider_auth.py \
    tests/settings/test_provider_connections.py \
    tests/settings/test_draft_testing.py \
    tests/settings/test_native_sdk_protocol.py \
    tests/team/test_provider_draft_access.py \
    tests/api/test_provider_settings_api.py \
    tests/settings/test_testing.py \
    tests/settings/test_testing_budget.py \
    tests/contracts/test_contracts.py -q

Full suite:
  PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m pytest -q

Type check:
  PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m mypy backend/lightgravity

Result files:
- targeted-tests.txt: 55 passed
- full-suite.txt: 1195 passed, 5 skipped
- mypy.txt: Success, no issues in 147 source files

No real vendor request, real credential, service restart, package install,
user-data mutation, merge, deployment or remote push was performed.
