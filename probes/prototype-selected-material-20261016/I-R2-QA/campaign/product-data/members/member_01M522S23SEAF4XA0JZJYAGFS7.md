---
run_ref: run_01M522S1WSYE67ASEXF0T1YPNE
role_ref: lg-default-worker
state: released
template_version: '0'
connection_ref: conn-worker
connection_pin:
  connection_id: conn-worker
  role: worker
  revision: 0
  content_hash: 81cb111b5f2375f5c9836ec0ca0dd4676ebeb12df72b1808520404af167bcfe7
  backend: openai-compat
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com/v1
  credential_ref: DEEPSEEK_API_KEY
  credential_version:
  config_hash: e380688bbf24789702ae36f5654ec95503c246263714c769ba762db8a483cd60
skill_refs: []
session_ref:
  session_id: sess_67b186b12599495e8103c29173d365e1
  conversation_id: 877999f594360491e4183c3e8bc2699f
  save_dir: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016/probes/prototype-selected-material-20261016/I-R2-QA/campaign/product-data/native-sessions/task_01M522S1RJE7KJKQRZS59PTNX6
  state: created
  source: result
  config_version: lg016.1
tool_policy:
  allowed_tools:
  - view-file
  - create-file
  - edit-file
workspace_ref: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016/probes/prototype-selected-material-20261016/I-R2-QA/campaign/product-data/workspaces/tasks/task_01M522S1RJE7KJKQRZS59PTNX6
assigned_subtask_refs:
- subtask_01M522S23S7PYXE9DSP85S8DTX
- subtask_01M522S23SMBVXCZQ3XJYMRSDE
budget:
  max_workers: 3
  max_parallel: 2
  max_repair_rounds: 1
config_hash: e771605217eee8f28d3d2ca79014678f2331a5ddddec52614391dbc6b762b5ec
capabilities:
- implementation
- verification
schema: lightgravity.bot/v1
kind: member
id: member_01M522S23SEAF4XA0JZJYAGFS7
revision: 4
---
# Member lg-default-worker

Role: lg-default-worker
