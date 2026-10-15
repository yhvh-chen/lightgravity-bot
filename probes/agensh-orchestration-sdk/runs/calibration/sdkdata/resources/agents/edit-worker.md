---
connection_ref: primary
conversation_ref: task-worker
skills:
  source: inline
  refs:
  - implementation
tool_refs:
- view-file
- create-file
- edit-file
hook_refs:
- staging-guard
- tool-observer
mcp_refs: []
trigger_refs: []
subagents: []
title: edit-worker
enabled: true
schema: lightgravity.bot/v1
kind: agent
id: edit-worker
revision: 0
---
