---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-19"
---

# LightGravity Bot

> **Collaborative AI workspace with multi-agent orchestration and human-in-the-loop delivery.**

**Give your team bot the context and the goal. Get work you can inspect, review, and accept.**

LightGravity Bot is a **collaborative AI workspace with multi-agent orchestration and human-in-the-loop delivery**, for individuals and small teams. It brings source material, conversations, tasks, and deliverables together. Describe the outcome, let the system assemble AI workers as needed, and review the result after execution and independent checks.

Built on **Antigravity SDK**, with **EmbeddingGemma 2** as an optional semantic retrieval backend. Tasks and resources are defined in Markdown; working records and deliverables live in files you control.

[Quick start](#quick-start) · [Team collaboration](#one-team-bot-two-kinds-of-collaboration) · [Agent capabilities](#agent-capabilities-and-terminology) · [Automatic task teams](#automatic-task-teams) · [Swarm direction](#toward-a-governed-self-organizing-swarm) · [Team mode](#team-mode) · [Architecture](#architecture) · [Validation and boundaries](#validation-and-boundaries) · [Documentation](#documentation)

> **Installation preview:** [GitHub release](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017) · [Gitea release](http://192.168.8.50:3000/admin/lightgravity-bot/releases/tag/install-preview-20261017). Both provide prebuilt archives, checksums, and manifests.

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

Start with a bounded development task in an authorized workspace, or reproduce the selected-source file delivery example. Research, documentation, and broader knowledge work are expansion directions; the evidence below defines the current tested scope.

## One team bot, two kinds of collaboration

**Team collaboration — people share the workspace.** In team mode, each person signs in with an individual account and shares chat, tasks, and sources. Ordinary group messages are saved without triggering the assistant; an explicit `@bot` invokes it. Messages inside a Task follow the task conversation rules.

**Multi-agent orchestration — AI workers form teams around tasks.** The system selects roles and skills, coordinates execution, and routes results through checks and independent review. AI members are created and released with a run, while task records and deliverables persist. Human accounts and AI members are distinct entities.

**Human-in-the-loop delivery — people review and accept the result.** Machine checks and independent model review precede user acceptance. In the verified game demo, one person creates the task, another signs in to inspect the result, play the game, and leave feedback, and the creator accepts the delivery from Board. Shared feedback is recorded; this demo does not establish an automatic feedback-to-revision loop.

The team MVP has one shared workspace with administrator and member roles. Administrators manage accounts, models, and credentials. Personal chat is private to the signed-in user; Team conversations, tasks, and source material remain shared. Private tasks, private sources, and multi-tenant isolation are outside the current scope.

## Agent capabilities and terminology

These terms describe the current design and its boundaries. Validation remains specific to the scenarios in [Validation and boundaries](#validation-and-boundaries).

| Capability | What it means in LightGravity today |
|---|---|
| **Multi-Agent Orchestration** | Application code validates plans, selects roles, and schedules dependent subtasks. Workers execute assigned work; autonomous swarm coordination remains exploratory. |
| **Human-in-the-Loop (HITL)** | People provide requirements and feedback, inspect evidence, and decide whether to accept or request changes. Successful execution alone does not complete acceptance. |
| **Agentic Workflows** | Tasks connect planning, execution, checks, independent review, and acceptance through explicit state transitions. Reusable user-defined workflow templates and cross-task dependency management are proposed extensions. |
| **Evaluation and bounded repair** | Machine checks and independent review gate delivery; repair is subject to configured limits and budgets. An evaluator–optimizer loop describes iterative generation and evaluation, not self-learning. Broader team-feedback-driven loops remain a proposed extension. |
| **Context Engineering / Retrieval-Augmented Generation (RAG)** | Source intake, retrieval, and manually selected versioned text bindings provide task context. Retrieval indexes are rebuildable; optional semantic retrieval has documented quality limits. |
| **Execution traceability** | Task/run records, events, artifacts, check results, and available usage records support inspection. This is a bounded foundation for agent observability, without a claim of complete tracing or cost coverage. |

Proposed product extensions include feedback-to-change-list conversion, version comparison and inline artifact annotations, task following and acceptance handoff, reusable workflow templates, and scheduled or event-driven tasks. **Long-term shared memory** would require curated decisions and preferences that can be retrieved across tasks, with provenance and correction controls; stored chat history alone does not establish that capability. These directions are not delivery commitments or claims of current support.

For the terminology behind orchestration, human approval, and evaluation loops, see [Microsoft Agent Framework orchestration patterns](https://learn.microsoft.com/agent-framework/workflows/orchestrations/) and [Anthropic's agent patterns](https://www.anthropic.com/engineering/building-effective-agents).

## Task Ontology: a shared model of work

We use **Task Ontology** to describe LightGravity's explicit work model: the objects involved, their relationships, permitted actions, and the evidence required for completion.

| Object | What it represents |
|---|---|
| Task | A user goal, requirements, and acceptance criteria |
| Run / Subtask | An execution attempt and its work nodes |
| Role / Member | A role template and an AI participant in a particular run |
| Source / Artifact | Input material and deliverables, with versions and provenance |
| Resources and acceptance records | Execution dependencies, check results, and user decisions |

The current foundation is explicit schemas, stable references, and program-validated state transitions. Task Ontology describes this structure; general ontology reasoning, knowledge graph inference, and automatic business modeling are outside the current scope. See the [task and resource model](docs/02-task-and-sdk-resources.md) and [interface contract](docs/08-interface-contract.md).

## Automatic task teams

Delivery work uses task-scoped AI teams: choose roles for the goal, assign dependent work, check the result, and release execution resources after confirmed stop. Ordinary questions follow the direct-answer path. Each task keeps its conversation, members, artifacts, and history.

LightGravity Bot provides task-scoped AI teams with rule-based recruitment and stop-confirmation:

| Feature | Capability & status |
|---|---|
| **Default agency-agents library** | 282 pinned upstream roles and their originals, provenance and MIT license are packaged; 275 are recruitable with the current tool set. Search, filters and pagination supported. |
| **Goal-based automatic recruitment** | Deterministic goal-fit metadata ranking is implemented. Real SDK tasks select appropriate frontend and technical-writing roles. |
| **A separate team for each task** | Recruited groups, Active/History views, task filters and task navigation supported. Task conversations, members, sessions and artifacts remain separate. |
| **Concurrent tasks and automatic release** | Real SDK tasks can run concurrently. Confirmed stop precedes resource release; history and artifacts persist. |

The [interaction and dispatch design](docs/13-chat-and-task-teams.md) defines the lifecycle and acceptance criteria.

Personal chat supports owner-only text attachment context, with a total 12,000-character context budget, up to 3 files, and 64 KiB of supported text per file. Unsupported binary content is reported without reading. Settings → Models & Providers includes optional embedding configuration for semantic retrieval.

## Toward a governed, self-organizing swarm

Our research direction is **agents that divide work around a shared goal and deliver reviewable results within explicit permissions and budgets.**

Today, application code validates plans, assembles teams, schedules dependencies, and writes control state. Workers execute assigned work. Basic rule-based team assembly is implemented; the broader role-library and concurrent-team extension is described in [Automatic task teams](#automatic-task-teams). Autonomous claiming and collaboration requests are disabled by default; delegation inside the SDK is disabled. **Self-organizing swarm behavior remains an exploration direction.**

Three constraints guide that work:

- Tasks and authorization define the scope. Roles and skills do not expand permissions.
- Budgets cover execution, verification, revision, and failed attempts. Cost is assessed across the full delivery lifecycle.
- Results pass checks and review before user acceptance. Completion and interruption require confirmation that execution has stopped.

## Architecture

| Layer | Technology and responsibility |
|---|---|
| Workspace | Python backend and web interface connecting conversations, tasks, sources, and teams |
| Coordination and control | Application-managed routing, plan validation, dependencies, permissions, budgets, and state |
| Agent execution | **Antigravity SDK** for agent execution, tool calls, and native sessions |
| Current generation path | `google-antigravity==0.1.22` → `LocalOpenAIAgentConfig` → loopback authentication proxy → **DeepSeek** |
| Optional vector retrieval | **EmbeddingGemma 2** service for semantic and media retrieval; lexical search and original files remain available when it is unconfigured or unavailable |
| Persistence | Markdown and YAML, JSONL, and SDK-native session storage; indexes can be rebuilt |

[Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python) provides the execution foundation. LightGravity connects it to tasks, sources, teams, and delivery acceptance. The currently validated generation path uses DeepSeek; Gemini and Vertex paths have not passed acceptance.

[EmbeddingGemma 2](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2?hl=en) supports unified multimodal embeddings. LightGravity connects through a configurable service, disabled by default, without depending on a developer-machine endpoint. Cross-modal retrieval quality still has limitations. Supported model modalities do not imply complete product support, and embeddings do not provide OCR or speech transcription.

You control the files and deployment environment. Model requests still go to the configured services; fully offline inference and plug-and-play support for arbitrary models are outside the current scope.

## Quick start

### Requirements

- Linux with Bash and uv `0.12+` on `PATH`.
- Network access to download Python 3.12 and the locked Python dependencies. The installer lets uv obtain Python when needed.
- Source installation without a built frontend additionally needs Node.js `22 LTS` and npm `10.x`. **Prebuilt release archives do not need Node.js or npm.**

Install uv using its [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/) if needed. The installer does not install system packages or execute a third-party installer. GNU make is only needed for the development Makefile commands.

### Install and start

```bash
bash install.sh

"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

Run `bash install.sh` from a source checkout or an extracted prebuilt archive. Source installation builds a missing frontend in a temporary staging directory. The installer prepares the application and prints the launcher path; it does not start the service. Add `--team` to the install command to explicitly configure account-based team mode.

Download the prebuilt installation archive and its checksum from the [GitHub release](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017) or [Gitea release](http://192.168.8.50:3000/admin/lightgravity-bot/releases/tag/install-preview-20261017), extract it, and run the same install command.

Open `http://127.0.0.1:8000/`. Use the same launcher with `status`, `stop`, or `start --daemon`. It works from any current directory. Data defaults to `~/.local/share/lightgravity-bot`, secrets to `~/.config/lightgravity-bot/secrets`, and application files to `~/.local/opt/lightgravity-bot`. Stop the installed service before reinstalling; existing external data and accounts are preserved.

For another port, custom paths, archive installation, or building a prebuilt archive with `bash scripts/build-release.sh`, see the [installation guide](docs/install.md). Archives bundle the frontend; Python dependencies are downloaded during installation.

### Connect a model

1. Open **Settings → Models & Providers**, create a connection, and save its credentials.
2. Test the connection and set the coordinator and default worker connections.
3. Configure an independent reviewer connection for delivery acceptance. Acceptance is blocked without an available reviewer.

Protected interfaces store credential references. See [model settings](docs/07-settings-and-models.md) for connection and default configuration. The existing validated path uses DeepSeek.

### Try a delivery

Begin with a small, explicit task, such as generating a file in an authorized workspace. Inspect the task status, file contents, and review record before accepting the result or requesting changes.

The [selected-material guide](docs/11-selected-material-demo.md) and [sample sources](examples/selected-material-prototype/README.md) provide a reproducible source-binding and file-delivery example.

The service provides `lightgravity start / status / stop` lifecycle commands. Closing or disconnecting the browser does not cancel background tasks.

## Team mode

When team mode starts with an empty account store, it creates **`admin` / `admin123`**. Existing accounts and passwords are preserved on restart. Sign in and use **Settings → My Account** to change your password; administrators create other accounts under **Settings → Accounts**.

You can also prepare accounts using the CLI. Passwords are entered interactively:

```bash
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" user add --username alice --role admin
"$HOME/.local/opt/lightgravity-bot/bin/lightgravity" user add --username bob --role member
```

Explicitly enable team mode at startup:

```bash
LIGHTGRAVITY_TEAM_MODE=1 "$HOME/.local/opt/lightgravity-bot/bin/lightgravity" start
```

Open `http://127.0.0.1:8000/` and sign in. Single-user mode remains the default when `LIGHTGRAVITY_TEAM_MODE` is unset.

Use the Personal/Team tabs above chat. In team mode, Personal supports private chat; switch to Team for shared tasks and material intake. In single-user mode, Personal retains task delivery, uploads, and source selection, while Team is disabled with an explanation. Open tasks from **Tasks workspace**; material search is in the top bar. Session Profiles, Hooks, MCP, Tools, Triggers, and Skills open directly from the single left navigation. Manage connections in **Settings → Models & Providers**; connection references open the matching Settings record.

Administrators manage team accounts from **Settings → Accounts**: list, create, enable/disable, change the `admin`/`member` role, and reset passwords. Every signed-in user has **Settings → My Account** to change their own password; it never loads model connections or the admin account list. Changing/resetting a password, disabling an account, or changing its role invalidates that account's old sessions on the next request; open event streams recheck within approximately two seconds. The last active administrator cannot be disabled or demoted. Usernames are immutable and there is no account deletion, invitation, or email self-registration.

For a remote instance, each participant can use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

For a normal LAN browser, use the account-based team mode above, bind with `--host 0.0.0.0`, and add the exact server IP with `--allow-host SERVER_IP`. Binding alone does not provide browser authentication in single-user mode: its initial document requires `X-LG-Token`; use an SSH tunnel to retain that mode. Host allowlisting and account authentication remain separate checks.

Team messages synchronize through polling approximately every three seconds. Background tabs catch up when visible again; login sessions survive restarts when persisted. The default listener is loopback. See the [interface contract](docs/08-interface-contract.md) for LAN deployment and access restrictions.

## Validation and boundaries

| Area | Status | Scope |
|---|---|---|
| Interface and workflows | Verified | Chromium end-to-end scenarios covering login, task creation, team chat, settings, and navigation. |
| Account management | Verified | Multi-user team mode, password updates, role management, last-admin protection, and session invalidation. |
| Selected-source delivery | Verified | Source upload → SDK execution nodes → independent model review → stop confirmation → user acceptance. |
| Team collaboration | Verified | Shared task channels, mention-based bot routing (`@bot`), and multi-user message synchronization. |
| Source intake and retrieval | Bounded | Text, PDF text-layer extraction, and lexical search; optional OCR and semantic embedding when configured. |

Current limitations and operational boundaries:

- **Browser coverage:** Tested primarily on Chromium-based browsers. Team mode uses authenticated session cookies; single-user mode uses same-origin runtime tokens.
- **Team message routing:** In Team mode, ordinary Task messages are recorded without bot invocation; only a message starting with `@bot` (or configured mention) invokes the assistant. Single-user mode routes messages directly.
- **Source context:** Ingested sources provide context to models via versioned text bindings.
- **Media support:** PDF processing reads an embedded text layer first and only OCRs sparse/scanned pages; images use explicit OCR; audio transcription is optional and disabled by default.
- **Recovery boundary:** Operations with unknown side effects are not automatically replayed. Complete checkpoint-skipping scheduling is not implemented.

## Development and contributions

Useful contributions include reproducible bug reports, real task samples, and improvements with explicit acceptance criteria. Include the version, reproduction steps, expected behavior, and actual result. Remove credentials and personal information from logs.

```bash
make run               # Backend, default 127.0.0.1:8000
make frontend-dev      # Frontend dev server, default 127.0.0.1:5173
make check             # Backend type checks and tests
make frontend-check    # Frontend type checks and tests
make check-all         # Backend and frontend checks
make frontend-build    # Frontend production build
```

Read [AGENTS.md](AGENTS.md) and [agent.md](agent.md) before development, plus [design.md](design.md) for frontend work. Configuration examples are in [.env.example](.env.example). Check the license of each dependency and reused component; upstream licenses do not establish a single license for all repository content.

## Documentation

| Entry | Contents |
|---|---|
| [Project handbook](PROJECT.md) · [Progress](PROGRESS.md) | Positioning, decisions, development history, and known issues |
| [Backlog](BACKLOG.md) · [Roadmap](docs/06-roadmap.md) | Tasks, dependencies, and milestone acceptance |
| [Architecture](docs/01-design.md) · [Tasks and resources](docs/02-task-and-sdk-resources.md) | Work model, module boundaries, and resource configuration |
| [SDK audit](docs/03-sdk-capability-audit.md) · [Bot behavior](docs/04-bot-behavior.md) | Execution foundation, message routing, and runtime rules |
| [Navigation](docs/05-navigation-and-team.md) · [Model settings](docs/07-settings-and-models.md) | Tasks workspace, single right Bot Chat, connections, and credentials |
| [Chat and task teams design](docs/13-chat-and-task-teams.md) | UI wireframes, task-based teams, release states, and dispatch gates |
| [Interface and state contract](docs/08-interface-contract.md) | Contract **1.26.0** specifications, API endpoints, state transitions, and coordination protocol |
| [Source intake and retrieval](docs/09-source-intake-and-retrieval.md) | Originals, derived content, indexes, and quality boundaries |
| [Selected-material prototype](docs/10-selected-material-prototype.md) · [Example guide](docs/11-selected-material-demo.md) | Source binding and reproducible workflows |
| [Two-minute demo film runsheet](docs/12-team-game-demo-runsheet.md) | 120-second runsheet with interface overview, setup and verified cross-account delivery/acceptance |
| [Demo recording script](content/demo/script.md) | Film script, voiceover transcript, and recording specifications |

Execution builds on Antigravity SDK; optional vector retrieval uses EmbeddingGemma 2. See [agent.md](agent.md) for role-content and design references. Runtime does not depend on developer-machine copies of Olav OS or Olav Tasks.
