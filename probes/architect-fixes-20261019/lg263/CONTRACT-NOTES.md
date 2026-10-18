# LG263 public behavior handoff

Register additive legal Task transition waiting_user -> recovery_required for interrupted nonterminal Runs at restart. This is conservative parking, not acceptance, Run termination or stop confirmation. Preserve active_run/session refs/cleanup when stopping is unknown.

Recovery diagnostics add error.recorded payload code recovery_transition_failed when the requested parking write cannot be persisted; the scanner does not claim action recovery_required for that failed write.

Existing cancel from recovery_required can use its existing direct cancelled transition once real stop is confirmed. Idle verify/repair/waiting/recovery controls require persisted cleanup or adapter proof plus no pending reviewer cleanup. No graph refs alone is not stop proof. Unknown stop returns the existing unconfirmed record with an accurate manual-recovery explanation and retains the slot. Waiting-user Pause no longer publishes paused before confirmation. No new API endpoint, request schema, force-clear or review-only action.

No actual old business state was changed. Pi owns shared contract/version/docs registration and serial integration.
