---
title: Built-in default worker
enabled: true
connection_ref:
conversation_ref:
skills:
  source: inline
  refs: []
tool_refs:
- view-file
- create-file
- edit-file
hook_refs: []
mcp_refs: []
trigger_refs: []
subagents: []
budget: {}
schema: lightgravity.bot/v1
kind: agent
id: lg-default-worker
revision: 0
---
# Built-in worker

Seeded by the runtime because no agent template existed. It carries only the
bounded, workspace-scoped file tools (view/create/edit); it has no
command-execution or web grants and no explicit connection_ref: it runs on the
current default worker connection configured in Settings. Extend or replace it
from Team/Resources; deleting it and creating your own template is also
supported.
