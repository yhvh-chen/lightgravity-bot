---
run_ref: run_01M522A85348ECGTNWWHQARWJ1
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
  session_id: sess_2214066322a84e288215bf357779ae29
  conversation_id: f01826263b7a849c864b17d08e90f3aa
  save_dir: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016/probes/prototype-selected-material-20261016/I-R2-QA/campaign/product-data/native-sessions/task_01M522A80FHRPQ1ZCRHFZ60PAM
  state: created
  source: result
  config_version: lg016.1
tool_policy:
  allowed_tools:
  - view-file
  - create-file
  - edit-file
workspace_ref: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016/probes/prototype-selected-material-20261016/I-R2-QA/campaign/product-data/workspaces/tasks/task_01M522A80FHRPQ1ZCRHFZ60PAM
assigned_subtask_refs:
- subtask_01M522A8C5XZ0SH2CQP3GXS07W
- subtask_01M522A8C5NTJ18YG975CMSA69
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
id: member_01M522A8C5KP2JBB1XSCC11MWE
revision: 2
---
# Member lg-default-worker

Role: lg-default-worker
