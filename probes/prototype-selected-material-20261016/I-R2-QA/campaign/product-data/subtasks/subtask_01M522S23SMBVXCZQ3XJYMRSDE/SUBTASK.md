---
run_ref: run_01M522S1WSYE67ASEXF0T1YPNE
state: failed
depends_on:
- subtask_01M522S23S7PYXE9DSP85S8DTX
assignee_member_ref: member_01M522S23SEAF4XA0JZJYAGFS7
upstream_artifact_refs:
- subtask_01M522S23S7PYXE9DSP85S8DTX@5236a8322cd86656d21bc7e2da80695f4cb05bdd087cd5a445bbbe9d7b190c60:orion-summary.md
- subtask_01M522S23S7PYXE9DSP85S8DTX@5236a8322cd86656d21bc7e2da80695f4cb05bdd087cd5a445bbbe9d7b190c60:evidence:run_01M522S1WSYE67ASEXF0T1YPNE/subtask_01M522S23S7PYXE9DSP85S8DTX-lg006-diff.patch@sha256:3ccef88d396c71f13cdf8ef66b5487ff519e1815d01847d87ab581be44972f92
objective: 独立验证：Create the deliverable orion-summary.md (Markdown) using only the selected brief. It must contain the project name, programme owner, primary launch date, total budget, project ID, and change ticket. Return the file as the deliverable.
capability: verification
key: verify
write: false
config_hash: 7bfce8151ab88cea9f2324aca6a40ac861580c0f793898875caf63b5a3ce9656
reuse_identity: e8704bd99e90e557567d88229c06b34772ed2b927ffe2207dc43cece173de34c
acceptance:
  status: failed
  criteria:
  - "The requested deliverable file 'orion-summary.md' exists in the task workspace and satisfies the objective: Create the deliverable orion-summary.md (Markdown) using only the selected brief. It must contain the project name, programme owner, primary launch date, total budget, project ID, and change ticket. Return the file as the deliverable."
  evidence_refs: []
schema: lightgravity.bot/v1
kind: subtask
id: subtask_01M522S23SMBVXCZQ3XJYMRSDE
revision: 4
owner:
lease_expires_at:
fail_reason: 'AntigravityExecutionError: HTTP request failed with status 429: {"error":{"message":"local auth proxy call budget exhausted"}}'
---
# Subtask verify

独立验证：Create the deliverable orion-summary.md (Markdown) using only the selected brief. It must contain the project name, programme owner, primary launch date, total budget, project ID, and change ticket. Return the file as the deliverable.
