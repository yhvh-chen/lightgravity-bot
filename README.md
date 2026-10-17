# LightGravity Bot

**Give your team bot the context and the goal. Get work you can inspect, review, and accept.**

LightGravity Bot is a collaborative AI workspace with multi-agent orchestration and human-in-the-loop delivery, for individuals and small teams. It brings source material, conversations, tasks, and deliverables together. Describe the outcome, let the system assemble AI workers as needed, and review the result after execution and independent checks.

Built on **Antigravity SDK**, with **EmbeddingGemma 2** as an optional semantic retrieval backend. Tasks and resources are defined in Markdown; working records and deliverables live in files you control.

[Installation preview](#installation-preview) · [Install and start](#install-and-start) · [Automatic task teams](#automatic-task-teams) · [Swarm direction](#toward-a-governed-self-organizing-swarm) · [Team mode](#team-mode) · [Architecture](#architecture) · [Validation and limitations](#validation-and-limitations)

> **Development source branch · October 18, 2026.** This branch, `development/task-teams-20261018`, is ahead of the published installation preview. It contains the reviewed development snapshot that combines the embedding settings, private Personal attachments, complete agency role library, and grouped task-team interface. It is a **source-only development branch**, not a new release, and it has **not** passed independent version QA. The published [installation preview](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017) and its prebuilt archive remain the earlier preview; they were not rebuilt from this branch.

> **Publication scope.** This source distribution was exported from the development snapshot without its tests, probes, runtime data, credentials, project-management documents, or internal Git history. The branch and both private repositories remain private; authorized access is required. No service restart, installer run, model request, or live-data change was performed for this publication.

## Installation preview

The published release is a local installation preview. It installs a stable runtime and launcher, keeps data outside the application directory, and does not start the service. The release assets were built from an earlier public source tree; this development branch is newer and is not a replacement release.

**Tested target:** Linux x86_64 only. Other operating systems and architectures are not claimed.

**Requirements:**

- Linux with Bash.
- `uv` 0.12 or newer on `PATH`.
- Network access so `uv` can download a managed CPython 3.12 runtime when needed and the packages pinned by `uv.lock`.
- **No Node.js or npm for the prebuilt archive.** A source checkout without a built frontend needs Node.js 22 LTS and npm 10.

Only the frontend is prebuilt. This is not an offline installer, and it does not deploy to a cloud environment.

Release assets include:

- `lightgravity-bot-<commit>-<timestamp>.tar.gz` — the prebuilt installation archive.
- `lightgravity-bot-<commit>-<timestamp>.tar.gz.sha256` — the archive checksum.
- `lightgravity-bot-<commit>-<timestamp>.MANIFEST.sha256` — per-file checksums inside the archive.

Download them from the [installation preview release page](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017).

## Install and start

### From the prebuilt release archive

```bash
# Download the archive and both companion checksum files from the release page.
sha256sum -c lightgravity-bot-*.tar.gz.sha256

tar -xzf lightgravity-bot-*.tar.gz
cd lightgravity-bot-*/

# Optional before installing: verify every archived file.
sha256sum -c MANIFEST.sha256

bash install.sh

"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

Open <http://127.0.0.1:8000/>. The installer does not start the service, does not enable LAN access, and does not ask for credentials. Stop it with:

```bash
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" stop
```

### From this development branch

```bash
git clone --branch development/task-teams-20261018 https://github.com/yhvh-chen/lightgravity-bot.git
cd lightgravity-bot
bash install.sh
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

A source checkout has no built frontend, so this path requires Node.js 22 and npm 10. The installer builds the frontend in a temporary staging directory without modifying the checkout. Because this branch is a development snapshot, validate it locally before relying on it.

### Defaults and lifecycle

| Purpose | Default |
|---|---|
| Application/runtime | `~/.local/opt/lightgravity-bot` |
| Data root | `~/.local/share/lightgravity-bot` |
| Task workspaces | `<data-root>/workspaces` |
| Secret store | `~/.config/lightgravity-bot/secrets` |
| Launcher configuration | `~/.config/lightgravity-bot/install.conf` |
| Stable launcher | `<application>/bin/lightgravity` |

The launcher works from any current directory. It supports `start`, `status`, and `stop`; add `--daemon` to `start` for a background process. Reinstalling updates application files while preserving external data, workspaces, secrets, accounts, and settings. Stop the installed service before reinstalling.

For custom paths, ports, team mode, archive creation, troubleshooting, and preservation behavior, see the [installation guide](docs/install.md).

### Connect a model

1. Open **Settings → Models & Providers / Connections**, create a connection, and save its credentials through the protected form.
2. Test the connection and set the coordinator and default worker connections.
3. Configure an independent reviewer connection for delivery acceptance. Acceptance is blocked without an available reviewer.

Protected interfaces store credential references. The currently validated generation path uses **DeepSeek** through the Antigravity SDK's OpenAI-compatible loopback proxy. Gemini and Vertex paths have not passed acceptance. The installer and this publication make no model calls.

### Try a delivery

Begin with a small, explicit task, such as generating a file in an authorized workspace. Inspect the task status, file contents, and review record before accepting the result or requesting changes.

The service provides `lightgravity start / status / stop` lifecycle commands. Closing or disconnecting the browser does not cancel background tasks.

## One team bot, two kinds of collaboration

**Team collaboration — people share the workspace.** In team mode, each person signs in with an individual account and shares chat, tasks, and sources. Ordinary group messages are saved without triggering the assistant; an explicit `@bot` invokes it. Messages inside a Task follow the task conversation rules.

**Multi-agent orchestration — AI workers form teams around tasks.** The system selects roles and skills, coordinates execution, and routes results through checks and independent review. AI members are created and released with a run, while task records and deliverables persist. Human accounts and AI members are distinct entities.

**Human-in-the-loop delivery — people review and accept the result.** Machine checks and independent model review precede user acceptance. Shared feedback is recorded; an automatic feedback-to-revision loop remains a proposed extension, not current behavior.

The team MVP has one shared workspace with administrator and member roles. Administrators manage accounts, models, and credentials. Personal chat is private to the signed-in user; Team conversations, tasks, and source material remain shared. Private tasks, private sources, and multi-tenant isolation are outside the current scope.

## Agent capabilities and terminology

These terms describe the current design and its boundaries. Validation remains specific to the scenarios in [Validation and limitations](#validation-and-limitations).

| Capability | What it means in LightGravity today |
|---|---|
| **Multi-Agent Orchestration** | Application code validates plans, selects roles, and schedules dependent subtasks. Workers execute assigned work; autonomous swarm coordination remains exploratory. |
| **Human-in-the-Loop (HITL)** | People provide requirements and feedback, inspect evidence, and decide whether to accept or request changes. Successful execution alone does not complete acceptance. |
| **Agentic Workflows** | Tasks connect planning, execution, checks, independent review, and acceptance through explicit state transitions. Reusable user-defined workflow templates and cross-task dependency management are proposed extensions. |
| **Evaluation and bounded repair** | Machine checks and independent review gate delivery; repair is subject to configured limits and budgets. An evaluator–optimizer loop describes iterative generation and evaluation, not self-learning. Broader team-feedback-driven loops remain a proposed extension. |
| **Context Engineering / Retrieval-Augmented Generation (RAG)** | Source intake, retrieval, and manually selected versioned text bindings provide task context. Retrieval indexes are rebuildable; optional semantic retrieval has documented quality limits. |
| **Execution traceability** | Task/run records, events, artifacts, check results, and available usage records support inspection. This is a bounded foundation for agent observability, without a claim of complete tracing or cost coverage. |

Proposed product extensions include feedback-to-change-list conversion, version comparison and inline artifact annotations, task following and acceptance handoff, reusable workflow templates, and scheduled or event-driven tasks. **Long-term shared memory** would require curated decisions and preferences that can be retrieved across tasks, with provenance and correction controls; stored chat history alone does not establish that capability. These directions are not delivery commitments or claims of current support.

## Task Ontology: a shared model of work

We use **Task Ontology** to describe LightGravity's explicit work model: the objects involved, their relationships, permitted actions, and the evidence required for completion.

| Object | What it represents |
|---|---|
| Task | A user goal, requirements, and acceptance criteria |
| Run / Subtask | An execution attempt and its work nodes |
| Role / Member | A role template and an AI participant in a particular run |
| Source / Artifact | Input material and deliverables, with versions and provenance |
| Resources and acceptance records | Execution dependencies, check results, and user decisions |

The current foundation is explicit schemas, stable references, and program-validated state transitions. Task Ontology describes this structure; general ontology reasoning, knowledge graph inference, and automatic business modeling are outside the current scope.

## Automatic task teams

Delivery work uses task-scoped AI teams: choose roles for the goal, assign dependent work, check the result, and release execution resources after confirmed stop. Ordinary questions follow the direct-answer path. Each task keeps its conversation, members, artifacts, and history.

The current development milestone extends the existing rule-based recruitment and stop-confirmation foundation. Its status below describes isolated development candidates and locally integrated source, **not the published release, the running service, or a version that has passed independent QA**.

| Feature | Current milestone status |
|---|---|
| **Default agency-agents library** | All 282 role files at the pinned upstream revision are packaged, with provenance, manifest hashes, and MIT license records. Available search, filters, and pagination are locally implemented and integrated; independent browser/version QA is pending. |
| **Goal-based automatic recruitment** | General role matching across the library is in development. Existing basic recruitment does not establish that this extension has passed real-task validation. |
| **A separate team for each task** | The grouped Recruited UI, Active/History views, local task filters, and explicit task navigation have passed local frontend checks. Backend capacity and group integration remain in development, and independent QA is pending. |
| **Concurrent tasks and automatic release** | Global worker/reviewer capacity and per-task release are in development. Acceptance requires actual overlapping SDK tasks and confirmed stop; member failure alone does not prove release. Released teams retain history and artifacts. |

The source snapshot includes the grouped task-team interface and the packaged role library. It does **not** claim complete automatic recruitment, tested concurrent capacity, automatic production release, or an accepted self-organizing swarm. SDK auto-delegation and autonomous claiming remain disabled by default.

## Toward a governed, self-organizing swarm

Our research direction is **agents that divide work around a shared goal and deliver reviewable results within explicit permissions and budgets.**

Today, application code validates plans, assembles teams, schedules dependencies, and writes control state. Workers execute assigned work. Basic rule-based team assembly is implemented; the broader role-library and concurrent-team extension is described in [Automatic task teams](#automatic-task-teams). Autonomous claiming and collaboration requests are disabled by default; delegation inside the SDK is disabled. **Self-organizing swarm behavior remains an exploration direction**, not a current production capability or a claim of default concurrency.

Three constraints guide that work:

- Tasks and authorization define the scope. Roles and skills do not expand permissions.
- Budgets cover execution, verification, revision, and failed attempts. Cost is assessed across the full delivery lifecycle.
- Results pass checks and review before user acceptance. Completion and interruption require confirmation that execution has stopped.

## Team mode

Team mode is off by default. Enable it explicitly during install:

```bash
bash install.sh --team
```

or at startup:

```bash
LIGHTGRAVITY_TEAM_MODE=1 "$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

When team mode starts with an empty account store, it creates the documented default login **`admin` / `admin123`** exactly once. Change that password immediately under **Settings → My Account**. Existing accounts and passwords are preserved across restarts and reinstalls. Administrators create other accounts under **Settings → Accounts**.

Single-user mode remains the default when team mode is unset. Use the Personal/Team tabs above chat. In team mode, Personal supports private chat; switch to Team for shared tasks and material intake. In single-user mode, Personal retains task delivery, uploads, and source selection, while Team is disabled with an explanation.

Administrators can list, create, enable or disable, change the role of, and reset passwords for accounts. Every signed-in user can change their own password. Changing or resetting a password, disabling an account, or changing its role invalidates that account's old sessions on the next request; open event streams recheck within approximately two seconds. The last active administrator cannot be disabled or demoted. Usernames are immutable, and there is no account deletion, invitation, or email self-registration.

For a remote instance, each participant can use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

For a normal LAN browser, use account-based team mode, bind with `--host 0.0.0.0`, and add the exact server address with `--allow-host SERVER_IP`. Binding alone does not provide browser authentication in single-user mode: its initial document requires a same-origin runtime token; use an SSH tunnel to retain that mode. Host allowlisting and account authentication remain separate checks. The default listener is loopback.

## From context to delivery

Getting work done involves source material, context, execution, and checking the result. LightGravity keeps these connected to a task, so follow-ups, revisions, and acceptance build on an existing record.

```text
Source material + goal
          |
Conversation and task
          |
Team assembly → Execution → Artifacts
                                |
                  Machine checks + independent review
                                |
                       User acceptance or revision
```

- **Carry context into execution.** Manually select ingested sources and bind versioned text context to a conversation or delivery task.
- **Assemble AI teams around an outcome.** Handle ordinary questions directly; create tasks, generate rule-based plans, select roles, and coordinate workers when delivery is needed.
- **Inspect the work and its evidence.** Retain artifacts, code diffs, check results, and source bindings for review and revision.
- **Keep control of your working files.** Markdown and YAML hold tasks and configuration, JSONL records messages and events, and retrieval indexes remain rebuildable caches.

Start with a bounded development task in an authorized workspace, or reproduce the selected-source file delivery example. Research, documentation, and broader knowledge work are expansion directions; the tested scope remains bounded by the validation below.

## Architecture

| Layer | Technology and responsibility |
|---|---|
| Workspace | Python backend and web interface connecting conversations, tasks, sources, and teams |
| Coordination and control | Application-managed routing, plan validation, dependencies, permissions, budgets, and state |
| Agent execution | **Antigravity SDK** for agent execution, tool calls, and native sessions |
| Current generation path | `google-antigravity==0.1.22` → `LocalOpenAIAgentConfig` → loopback authentication proxy → **DeepSeek** |
| Role library | Packaged agency-agents templates with pinned provenance, capability metadata, and bounded tool references |
| Optional vector retrieval | **EmbeddingGemma 2** service for semantic and media retrieval; lexical search and original files remain available when it is unconfigured or unavailable |
| Persistence | Markdown and YAML, JSONL, and SDK-native session storage; indexes can be rebuilt |

[Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python) provides the execution foundation. LightGravity connects it to tasks, sources, teams, and delivery acceptance. The currently validated generation path uses DeepSeek; Gemini and Vertex paths have not passed acceptance.

[EmbeddingGemma 2](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2?hl=en) supports unified multimodal embeddings. LightGravity connects through a configurable service, disabled by default, without depending on a developer-machine endpoint. Cross-modal retrieval quality still has limitations. Supported model modalities do not imply complete product support, and embeddings do not provide OCR or speech transcription.

You control the files and deployment environment. Model requests still go to the configured services; fully offline inference and plug-and-play support for arbitrary models are outside the current scope.

## Validation and limitations

This repository branch is a **development source snapshot**, not a production-ready release or a completed independent version QA. Its prebuilt release archive was not rebuilt from this branch.

**Source and publication checks (this branch):** the exported source tree was parsed and built locally; the frontend production build and locked Python dependency check completed against the same source. The role library's 282 adapted templates and 282 original upstream Markdown files were checked against the manifest's SHA-256 and git blob hashes, and the wheel package was inspected to confirm that the role data, manifest, license, and notice are included. Secret, runtime-data, internal-path, and forbidden-path scans were run over the exported tree. No product model calls, installer run, service restart, or live-data change was performed for this publication.

**Local integration status carried forward with provenance:** the implementation team's local checks for the combined development candidate passed, including frontend unit/type/build checks and backend API and settings checks. Those checks were run against isolated development data, not this exported branch, and their test files are not included in this distribution. They are implementation evidence, not independent version acceptance.

**Prior product validation:** earlier account-management and interface milestones passed independent browser, backend, and frontend campaigns on their frozen candidates. Those suites and detailed reports are not included in this distribution and were not rerun for this branch.

Current limitations:

- **Independent version QA is pending.** Local integration checks and installation evidence are not final version acceptance.
- **This branch is ahead of the release.** The published prebuilt archive corresponds to an earlier source tree. Rebuilding and revalidating an archive from this branch is a separate action.
- **Tested on Linux x86_64 only for the published preview.** Other operating systems and architectures are not claimed for this branch.
- **No cloud deployment.** The installer prepares a local service; hosting, public access, and managed cloud operation are out of scope.
- **Automatic teams and concurrency are incomplete.** General role matching, backend team/capacity integration, real overlapping SDK execution, and automatic release still require implementation and independent QA. No complete Swarm, self-organizing, or default production concurrency is claimed.
- **SDK auto-delegation and autonomous claiming are disabled by default.** Enabling them would require a separate scheduling, budget, and permission review.
- **Browser coverage uses Chromium.** Firefox was not rerun. Single-user settings writes require the supported same-origin runtime token handshake; team mode uses authenticated account cookies.
- **Source bindings record provided context.** Model citations have not been verified against individual source spans.
- **Media support is bounded.** PDF and image processing use explicit OCR. ASR is unavailable; Chinese transcription awaits its quality gate. Office formats have not been comprehensively tested.
- **Recovery is bounded.** Operations with unknown side effects are not automatically replayed. Complete checkpoint-skipping scheduling is not implemented.
- **Integration, deployment, and acceptance are separate.** Local installation and historical QA do not establish that a running service is updated, a release is published in every environment, or final user acceptance has occurred.
- **A project-wide license has not been selected.** Do not assume that dependency licenses grant rights to all repository content. The bundled agency-agents role library is MIT-licensed; see `THIRD-PARTY-NOTICES.md`.

## Source layout and development

- `backend/lightgravity/`: Python API, task coordination, storage, execution adapters, source processing, and runtime.
- `backend/lightgravity/runtime/roles/agency/`: the packaged role library, original upstream role files, manifest, MIT license, and notice.
- `frontend/src/`: React workspace interface, including the grouped task-team views.
- `install.sh` and `scripts/build-release.sh`: local installer and prebuilt-archive packager.
- `pyproject.toml` and `uv.lock`: Python package metadata and locked dependencies. The wheel includes the packaged role data.
- `frontend/package.json` and `frontend/package-lock.json`: frontend build dependencies.
- `docs/install.md`: installation, lifecycle, and packaging details.
- `THIRD-PARTY-NOTICES.md`: dependency provenance, the role-library license, and project license status.
- `.env.example`: optional environment variable names with empty credential fields. Export variables explicitly; the service does not automatically load `.env`.

```bash
make run               # Backend on 127.0.0.1:8000
make frontend-dev      # Frontend on 127.0.0.1:5173
make frontend-type     # Frontend type check
make frontend-build    # Frontend production build

# Build a local prebuilt archive without modifying the checkout.
bash scripts/build-release.sh [OUTPUT_DIR]
```

The packager requires Git, Node.js 22, npm 10, and uv. It includes the committed runtime source, locked dependencies, a frontend built from the same commit, the installer, the installation guide, the packaged role library, and frontend license notices. It excludes tests, development records, runtime data, secrets, and build caches.

Useful contributions include reproducible bug reports and improvements with explicit acceptance criteria. Include the version, reproduction steps, expected behavior, and actual result. Remove credentials and personal information from logs.

## Documentation

The detailed development documents are maintained outside this source distribution. The shipped installation guide is [docs/install.md](docs/install.md).

## License

A project-wide license has not yet been selected for this source preview. Do not assume that dependency licenses grant rights to all repository content. Dependency licenses and any applicable notices continue to apply; see `THIRD-PARTY-NOTICES.md`. The bundled agency-agents role library is distributed under its MIT license with its copyright notice and manifest.
