# LightGravity Bot

**Give your team bot the context and the goal. Get work you can inspect, review, and accept.**

LightGravity Bot is an AI workspace for individuals and small teams. It brings source material, conversations, tasks, and deliverables together. Describe the outcome, let the system assemble AI workers as needed, and review the result after execution and independent checks.

Built on **Antigravity SDK**, with **EmbeddingGemma 2** as an optional semantic retrieval backend. Tasks and resources are defined in Markdown; working records and deliverables live in files you control.

[Quick start](#quick-start) · [Team mode](#team-mode) · [Architecture](#architecture) · [Validation and limitations](#validation-and-limitations)

> **Development preview.** Page-loading failures and interface improvements are being investigated. Capabilities described here distinguish implementation from research directions.

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

**People share the workspace.** In team mode, each person signs in with an individual account and shares chat, tasks, and sources. Ordinary group messages are saved without triggering the assistant; an explicit `@bot` invokes it. Messages inside a Task follow the task conversation rules.

**AI workers form teams around tasks.** The system selects roles and skills, coordinates execution, and routes results through checks and independent review. AI members are created and released with a run, while task records and deliverables persist. Human accounts and AI members are distinct entities.

The current team MVP has one shared workspace with administrator and member roles. Administrators manage accounts, models, and credentials. All team material is shared; private messages, private sources, and multi-tenant isolation are outside the current scope.

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

## Toward a governed, self-organizing swarm

Our research direction is **agents that divide work around a shared goal and deliver reviewable results within explicit permissions and budgets.**

Today, application code validates plans, assembles teams, schedules dependencies, and writes control state. Workers execute assigned work. Autonomous claiming and collaboration requests are disabled by default; delegation inside the SDK is disabled. Dynamic team assembly is implemented; **self-organizing swarm behavior remains an exploration direction**.

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

- Python `>=3.12,<3.13`
- uv `0.12.x`
- Node.js `22 LTS`, npm `10.x`
- GNU make for the shared development commands

Run these commands from the repository root. They follow the existing startup workflow; see [current limitations](#validation-and-limitations) before trying the preview.

### Install and start

```bash
uv sync --locked --no-dev
npm --prefix frontend ci
npm --prefix frontend run build

uv run --no-dev lightgravity start \
  --data-dir ./bot-data \
  --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets \
  --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Choose another port if it is already in use. Keep runtime data, workspaces, and secrets in separate directories. Credentials belong in protected configuration, outside the repository and conversations.

### Connect a model

1. Open **Settings → Models & Providers / Connections**, create a connection, and save its credentials.
2. Test the connection and set the coordinator and default worker connections.
3. Configure an independent reviewer connection for delivery acceptance. Acceptance is blocked without an available reviewer.

Protected interfaces store credential references. The existing validated generation path uses DeepSeek.

### Try a delivery

Begin with a small, explicit task, such as generating a file in an authorized workspace. Inspect the task status, file contents, and review record before accepting the result or requesting changes.

The service provides `lightgravity start / status / stop` lifecycle commands. Closing or disconnecting the browser does not cancel background tasks.

## Team mode

Create accounts first. Passwords are entered interactively:

```bash
uv run --no-dev lightgravity user add --username alice --role admin --data-dir ./bot-data
uv run --no-dev lightgravity user add --username bob --role member --data-dir ./bot-data
```

Explicitly enable team mode at startup:

```bash
LIGHTGRAVITY_TEAM_MODE=1 uv run --no-dev lightgravity start \
  --data-dir ./bot-data \
  --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets \
  --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` and sign in. Single-user mode remains the default when `LIGHTGRAVITY_TEAM_MODE` is unset.

For a remote instance, each participant can use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

Team messages synchronize through polling approximately every three seconds. Background tabs catch up when visible again; login sessions expire on service restart. The default listener is loopback. Keep the service bound to loopback when using this setup.

## Validation and limitations

This is an early source preview, not a production-ready release.

Current limitations:

- **Page loading needs repair.** Users have reported failures in Files, Team, and Models & Providers. The cause is unverified. Navigation, search, chat, and personal/team switching changes are pending.
- **Source bindings record provided context.** Model citations have not been verified against individual source spans.
- **Media support is bounded.** PDF and image processing use explicit OCR. ASR is unavailable; Chinese transcription awaits its quality gate. Office formats have not been comprehensively tested.
- **Recovery is bounded.** Operations with unknown side effects are not automatically replayed. Complete checkpoint-skipping scheduling is not implemented.
- **Integration, deployment, and acceptance are separate.** Local integration and historical QA do not establish that a running service is updated, a release is published, or final user acceptance has occurred.

## Source layout and contributions

- `backend/lightgravity/`: Python API, task coordination, storage, execution adapters, source processing, and runtime.
- `frontend/src/`: React workspace interface.
- `pyproject.toml` and `uv.lock`: Python package metadata and locked dependencies.
- `frontend/package.json` and `frontend/package-lock.json`: frontend build dependencies.
- `.env.example`: optional environment variable names, with empty credential fields. Export variables explicitly; the service does not automatically load `.env`.

```bash
make run               # Backend on 127.0.0.1:8000
make frontend-dev      # Frontend on 127.0.0.1:5173
make frontend-type     # Frontend type check
make frontend-build    # Frontend production build
```

Build the frontend from the repository root before starting the combined service. The frontend is served from `frontend/dist`; Python wheels do not bundle this build. This source distribution includes application code and build configuration; the internal test suite and development records are not included. Some test tooling remains in locked development dependencies to preserve dependency resolution.

Useful contributions include reproducible bug reports and improvements with explicit acceptance criteria. Include the version, reproduction steps, expected behavior, and actual result. Remove credentials and personal information from logs.

## License

A project-wide license has not yet been selected for this source preview. Do not assume that dependency licenses grant rights to all repository content. Dependency licenses and any applicable notices continue to apply.
