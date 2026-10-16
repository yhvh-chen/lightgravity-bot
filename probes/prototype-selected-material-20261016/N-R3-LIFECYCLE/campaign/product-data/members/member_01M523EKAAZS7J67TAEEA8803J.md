---
run_ref: run_01M523EK321M4KD494CA042R1M
role_ref: lg-default-worker
state: released
template_version: '0'
connection_ref: conn-worker
connection_pin:
  connection_id: conn-worker
  role: worker
  revision: 0
  content_hash: 120e7558a8fff8b65e77a536885a669d9a9c9fcacac8fa723d41e13ca42dccb9
  backend: openai-compat
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com/v1
  credential_ref: DEEPSEEK_API_KEY
  credential_version:
  config_hash: 377c94b81cbc48d4bc79378a8f3e445da14a634d44bb4b3f634deee10615380b
skill_refs: []
session_ref:
  session_id: sess_ce1217fc38774d2ba3fe4c4be3622d47
  conversation_id: 1b884a218a9dd1338570f476ce5ed5c0
  save_dir: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-lifecycle-qa-r3-20261016/probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/campaign/product-data/native-sessions/task_01M523EJZBG1X1BMTQD8JE7TTH
  state: created
  source: result
  config_version: lg016.1
tool_policy:
  allowed_tools:
  - view-file
  - create-file
  - edit-file
workspace_ref: /home/yhvh/code/lightgravity-bot-worktrees/proto-material-lifecycle-qa-r3-20261016/probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/campaign/product-data/workspaces/tasks/task_01M523EJZBG1X1BMTQD8JE7TTH
assigned_subtask_refs:
- subtask_01M523EKAACQHS13HE9ZWTMM3A
- subtask_01M523EKAARRNG5B6DJSC2W81B
budget:
  max_workers: 3
  max_parallel: 2
  max_repair_rounds: 1
config_hash: e5a9a4f61a7fd2fdc05de48a4b77da672682a4b99c943e98e1142acf29f99a64
capabilities:
- implementation
- verification
schema: lightgravity.bot/v1
kind: member
id: member_01M523EKAAZS7J67TAEEA8803J
revision: 5
---
# Member lg-default-worker

Role: lg-default-worker
