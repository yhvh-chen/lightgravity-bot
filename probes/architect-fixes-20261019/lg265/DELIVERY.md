# LG265 runtime defaults repair

Base: ff44edae6d429764fe8e931cb3d294cf853f2c79 / contract 1.24.0.
Branch: fix/lg265-runtime-repairs-20261019. Native defect repair; pending pi integration/version QA.

PATCH settings now invokes an application-level callback, reusing the bootstrap responder/reviewer assemblers. The router serializes the saved defaults and callback to avoid concurrent saves applying in reverse order. Coordinator has a responder setter; each dialogue invocation retains its callable. Reviewer objects are frozen per newly opened Run; changing or clearing the default retains existing Run reviewers and in-flight lifecycle resources. Clearing the reviewer default restores honest UnavailableReviewer for subsequent Runs.

The response distinguishes a saved configuration from runtime assembly. runtime_applied=true means assembly completed, not that credentials passed a network test or a model answered. Failure/missing callback returns false and an explicit saved/restart message. Partial assembly may have occurred when false; restart is the fallback. Settings uses this actual result, with a conservative restart message for older servers. Worker freezing and permissions remain unchanged.

Validation: five startup/bootstrap checks passed in 42.06s, including HTTP save/clear/rewire, existing Run object retention, and injected callback failure with durable settings. A later targeted enhancement also exercises the newly wired tool-less responder with a labelled local model-method fixture; no network/model call. Frontend production build passed (tsc as part of build; Vite 133 modules). No full pytest/vitest/type/performance matrix or browser/real-model execution. Initial edit command failed because `python` is absent; rerun used python3, without source mutation from the failed command.

Evidence source: LG217 architecture supplement and LG265 acceptance criteria, plus LG263 prior native timing diagnosis. docs-kb CLI unavailable (`olav-tasks: command not found`); original Markdown was read directly. No shared contract/version/root task documents modified. No instance settings, user data, service, merge, push, deployment, or protected ports touched.
