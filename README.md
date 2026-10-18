---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-18"
---

# LightGravity Bot

> **Demo-recording fixes candidate · October 18, 2026 (local, not deployed):** the isolated `work/lg248-candidate-20261018` integration candidate implements contract **1.23.0** with the LG-248 recording fixes: a read-only canonical `TASK.md` endpoint, default-delivery workspace plus recorded machine checks bound to the current candidate, truthful per-Run worker/reviewer execution evidence, text-layer-first PDF extraction with optional OCR fallback, and leading configured-mention routing for Team Task messages with the real `health.team_bot_mention` value. The new endpoints/DTO/projection fields are additive, but the batch is **not purely additive**: LG-249 intentionally changes Team Task ordinary-message routing so ordinary messages are recorded-only unless they start with the configured mention; single-user routing is unchanged. The candidate also includes the native Files/navigation/Tasks repairs, the LG-220 Board refresh/navigation behavior and the LG-208 parsed read cache. These are developer-local integration checks, not independent QA or a deployment: no deployment was performed and no live 8123/5173 version was rechecked in this pass, no product model/OCR/ASR call was made, and independent LG-252 browser/recording validation is still pending. [Contract §24](docs/08-interface-contract.md)

> **Brand update · October 18, 2026:** the login and workspace now show the project Logo and the requested default-account reminder on **8123**, from local main `8a3f04d7`. Independent brand checks and 44 live deployment checks passed; accounts/data and all service processes were preserved. ASR is **disabled** while the selected remote EmbeddingGemma 2 + local Reader-container path is being prepared. The existing SSH identity was rejected by 192.168.8.12, so remote deployment awaits a working access method. [Deployment record](probes/remote-reader-20261018/lg212/DELIVERY.md). No remote push or release.

> **UI deployment · October 18, 2026:** the existing 8123 service and 5173 frontend now serve contract **1.20.0**, from local main `1ab4d7b`. Material-intake and English-transcription UI updates are installed; 73 public desktop/mobile deployment checks passed. English ASR remains **off and unconfigured**, and its recognition quality gate remains FAILED. Accounts/data and the disabled executor were preserved. Authenticated production screens were not opened; their isolated UI evidence is reused by exact source identity. [Deployment record](probes/english-asr-20261018/lg168/DELIVERY.md). No remote push or release.

> **Chat and task teams · October 18, 2026:** the isolated contract **1.18.0** candidate `94571a0` passed independent QA within the documented bounded cases: real overlapping SDK tasks, task-specific teams, confirmed stop and release, queue cancellation, private attachment context, and desktop/mobile UI. Deployed to the existing 8123 service from local main `b29cd7b`; desktop/mobile deployment smoke passed, and both remote main branches now contain the accepted product. Existing accounts/data and the disabled executor were preserved. [Deployment record](probes/chat-task-teams-20261017/lg138/deploy-LG138-DELIVERY.md). [Final report](probes/chat-task-teams-20261017/qa-LG123-final/REPORT.md).

> **Previous connection-dialog delivery (LG-104):** contract **1.17.0**, main df53ead. New/Edit opens a compact provider-specific dialog; Test uses the current draft without saving it, and advanced settings stay collapsed. Independent real-backend/browser QA passed at desktop and mobile sizes. New SDK providers support configuration and manual tests; native Task execution and arbitrary custom API hosts remain outside this delivery. The global generation ceiling is removed, with task execution still disabled. [QA and screenshots](probes/provider-setup-20261017/qa-r2/QA-R2.md) · [Local delivery](probes/provider-setup-20261017/qa-r2/DELIVERY.md).

> **Connection management consolidated:** Settings → Models & Providers retains the complete connection UI. The separate Connections sidebar entry was removed; Team/resource references and old links open the matching connection in Settings. Available on 8123 from `main@85d009d`. [Delivery and screenshots](probes/settings-connections-20261017/DELIVERY.md).

> **Navigation icons refreshed:** seven resource entries and Settings now use consistent outline SVG icons. Available on 8123 from `main@503dca3`; desktop and mobile navigation checks passed. [Delivery and screenshots](probes/nav-icons-20261017/DELIVERY.md).

> **Centered material search:** the top bar now contains an editable search field in the middle. Type and press Enter to search existing material; Escape closes results while keeping the query and focus. Desktop and 390px layouts were checked against the real backend. Available on 8123 from `main@52ca568`; see the [UI delivery and screenshots](probes/centered-search-20261017/DELIVERY.md).

> **Latest local main integration · October 17, 2026:** contract **1.16.0**, `main@ca58b35`. Team Task-ID queries, Board artifact downloads, candidate-bound acceptance and general reliability fixes passed independent QA with limitations. The original classification failure and its repair are preserved in the [delivery record](probes/generic-merge-20261017/DELIVERY.md) and [independent revalidation](probes/generic-merge-20261017/qa/QA-R2.md). Game roles, fixed recruitment mappings and demo recovery budgets were excluded; general role-library recruitment remains incomplete. After the authorized local restart, 8123 now serves contract 1.16.0 with the matching production frontend; account/data checks and the real-browser login smoke passed. Model execution remains disabled. The 5173 watcher-resource crash was recovered using polling; 18123 remains the separate demo replay. See the [restart record](probes/generic-merge-20261017/RESTART.md). No remote push or release was made.

> **Google native audio candidate · October 18, 2026 (not deployed):** the isolated LG-238 candidate assembles the LG-236 backend and LG-237 UI for a lightweight English audio path that calls the native Gemini inline-audio REST endpoint (no SDK, Torch, numpy, Reader, remote 192.168.8.12 service, Files API or environment product key). Contract is the additive **1.22.0** candidate; legacy EG2/Reader blocks without `provider` keep their 1.20 behavior, the old Reader quality record stays **FAILED**, and no quality pass is claimed. Checks used recorded responses with a fake transport; the public 8123/5173 service remains **1.20.0**. Independent LG-239 version/browser and one real Google call passed QA with limitations; the candidate is merged into local main but is **not deployed**. [Integration delivery](probes/google-native-asr-20261018/lg238/DELIVERY.md).

> **Tasks workspace candidate · October 18, 2026 (not deployed):** the isolated LG-206 integration candidate replaces the Chat main page with the Tasks workspace, binds the single right Bot Chat to the current Task, adds title-only New task through the existing `POST /tasks`, moves context selection into Tasks, and adds the Team conversation-history picker. Contract was the additive **1.21.0** candidate; existing endpoints/task semantics/permissions are unchanged. Independent LG-207 version/browser QA passed with limitations; the candidate is merged into local main but is **not deployed**; the public 8123/5173 service remains **1.20.0**. [Integration delivery](probes/demo-tasks-20261018/lg206/DELIVERY.md).
**Give your team bot the context and the goal. Get work you can inspect, review, and accept.**

LightGravity Bot is a **collaborative AI workspace with multi-agent orchestration and human-in-the-loop delivery**, for individuals and small teams. It brings source material, conversations, tasks, and deliverables together. Describe the outcome, let the system assemble AI workers as needed, and review the result after execution and independent checks.

Built on **Antigravity SDK**, with **EmbeddingGemma 2** as an optional semantic retrieval backend. Tasks and resources are defined in Markdown; working records and deliverables live in files you control.

[Quick start](#quick-start) · [Team collaboration](#one-team-bot-two-kinds-of-collaboration) · [Agent capabilities](#agent-capabilities-and-terminology) · [Automatic task teams](#automatic-task-teams) · [Swarm direction](#toward-a-governed-self-organizing-swarm) · [Team mode](#team-mode) · [Architecture](#architecture) · [Validation and limitations](#validation-and-limitations) · [Documentation](#documentation)

> **Installation preview published:** [GitHub release](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017) · [Gitea release](http://192.168.8.50:3000/admin/lightgravity-bot/releases/tag/install-preview-20261017). Both provide the same prebuilt archive, checksum, and manifest. Repository visibility remains private; authorized access is required. This release uses the account-management product baseline plus the installer; the separate game-demo candidate below remains a local delivery.

> **Development preview · October 17, 2026.** Account management passed independent QA on a frozen candidate: 30 Chromium end-to-end tests, 18 independent browser checks, and three navigation stability samples. The matching product code passed 1,061 backend tests (2 skipped), 181 frontend tests, and concurrency checks. The updated LAN runtime passed 27 live checks. See the [account management report](probes/accounts-20261017/README.md) for provenance and limits.

> **Two-minute demo film ready:** [Watch the final MP4](probes/video-20261017/v2/demo-120s.mp4) — 120 seconds, 1080p/30fps, English captions, silent. Interface overview, accelerated setup, and the verified two-account task/game/feedback/acceptance flow. Independent pi QA PASS; actual DeepSeek frame reviews and reproducible HyperFrames + FFmpeg sources are in the [video handoff](probes/video-20261017/README.md).

> **Two-account game demo delivered:** open http://192.168.8.50:18123. Real SDK execution, independent model review, stop confirmation, B's download/gameplay/feedback and A's Board acceptance passed linked independent QA. The final browser smoke passed with the ledger unchanged at 89/96. This entry replays the completed result with execution disabled. It uses the committed demo worktree (`delivery/lg068-local-20261017`, `61e2269`). At that delivery, root main was left unchanged; the general improvements have since been selectively merged as described above, while game roles and demo-specific configuration remain separate. See the [local handoff](probes/demo-team-game-20261017/DELIVERY.md) and [120-second runsheet](docs/12-team-game-demo-runsheet.md).

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

The current development milestone extends the existing rule-based recruitment and stop-confirmation foundation. Its status below describes isolated development candidates, now deployed to the existing service; the older installation-preview archive remains separate.

| Feature | Current milestone status |
|---|---|
| **Default agency-agents library** | 282 pinned upstream roles and their originals, provenance and MIT license are packaged; 275 are recruitable with the current tool set. Search, filters and pagination passed independent browser QA. |
| **Goal-based automatic recruitment** | Deterministic goal-fit metadata ranking is implemented. Real SDK tasks selected different frontend and technical-writing roles; this does not establish autonomous or semantic recruitment. |
| **A separate team for each task** | Recruited groups, Active/History views, task filters and task navigation passed independent real-backend/browser QA. Task conversations, members, sessions and artifacts remain separate. |
| **Concurrent tasks and automatic release** | Real SDK tasks overlapped; one reached acceptance while the other continued. Confirmed stop preceded release; history and artifacts persisted. The tested single-process limits were 2 active tasks, 3 global sessions, 1 reviewer and 2 nodes per task. A third task queued and cancelled without starting a Run. |

The [interaction and dispatch design](docs/13-chat-and-task-teams.md) defines the lifecycle and acceptance criteria. The [final independent report](probes/chat-task-teams-20261017/qa-LG123-final/REPORT.md) distinguishes fresh checks from audited evidence on unchanged code, preserves earlier failures and states the remaining limits. The HTML delivery sample was a supplied-template regression; no production-scale or arbitrary-task guarantee is implied.

Personal supports owner-only text attachment context, with a total 12,000-character context budget, at most 3 files, and 64 KiB of supported text per file. Unsupported binary content is not read; its status is provided to the model. The final real sample read the text code and correctly identified the unread binary. Settings → Models & Providers also includes separate optional embedding URL/model/key/test configuration. Embedding protocol and fallback checks used a labelled local HTTP fixture; vendor retrieval quality was not tested.

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

Download the prebuilt installation archive and its checksum from the [GitHub release](https://github.com/yhvh-chen/lightgravity-bot/releases/tag/install-preview-20261017) or [Gitea release](http://192.168.8.50:3000/admin/lightgravity-bot/releases/tag/install-preview-20261017), extract it, and run the same install command. The published archive was rebuilt from the source export and verified by downloading from both platforms; see the [publication handoff](probes/install-publish-20261017/DELIVERY.md).

Open `http://127.0.0.1:8000/`. Use the same launcher with `status`, `stop`, or `start --daemon`. It works from any current directory. Data defaults to `~/.local/share/lightgravity-bot`, secrets to `~/.config/lightgravity-bot/secrets`, and application files to `~/.local/opt/lightgravity-bot`. Stop the installed service before reinstalling; existing external data and accounts are preserved.

For another port, custom paths, archive installation, or building a prebuilt archive with `bash scripts/build-release.sh`, see the [installation guide](docs/install.md). Archives bundle the frontend; Python dependencies still require downloads. This Linux installation batch passed implementer smoke checks; independent version QA and Google Cloud deployment remain pending. See the [local installation handoff](probes/install-simple-20261017/DELIVERY.md).

### Connect a model

1. Open **Settings → Models & Providers**, create a connection, and save its credentials.
2. Test the connection and set the coordinator and default worker connections.
3. Configure an independent reviewer connection for delivery acceptance. Acceptance is blocked without an available reviewer.

Protected interfaces store credential references. See [model settings](docs/07-settings-and-models.md) for connection and default configuration. The existing validated path uses DeepSeek.

### Try a delivery

Begin with a small, explicit task, such as generating a file in an authorized workspace. Inspect the task status, file contents, and review record before accepting the result or requesting changes.

The [selected-material guide](docs/11-selected-material-demo.md) and [sample sources](examples/selected-material-prototype/README.md) provide a reproducible source-binding and file-delivery example. The fixtures are human-written samples, with an independently verified real SDK lifecycle run. That result covers the documented scenario.

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

Use the Personal/Team tabs above chat. In team mode, Personal supports private chat; switch to Team for shared tasks and material intake. In single-user mode, Personal retains task delivery, uploads, and source selection, while Team is disabled with an explanation. Open tasks from **Files → Task directories**; material search is in the top bar. Session Profiles, Hooks, MCP, Tools, Triggers, and Skills open directly from the single left navigation. Manage connections in **Settings → Models & Providers**; connection references open the matching Settings record.

Administrators manage team accounts from **Settings → Accounts**: list, create, enable/disable, change the `admin`/`member` role, and reset passwords. Every signed-in user has **Settings → My Account** to change their own password; it never loads model connections or the admin account list. Changing/resetting a password, disabling an account, or changing its role invalidates that account's old sessions on the next request; open event streams recheck within approximately two seconds. The last active administrator cannot be disabled or demoted. Account management is additive in contract 1.15; an older team backend or single-user mode shows only an honest explanation. Usernames are immutable and there is no account deletion, invitation, or email self-registration.

For a remote instance, each participant can use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 <server>
```

For a normal LAN browser, use the account-based team mode above, bind with `--host 0.0.0.0`, and add the exact server IP with `--allow-host SERVER_IP`. Binding alone does not provide browser authentication in single-user mode: its initial document requires `X-LG-Token`; use an SSH tunnel to retain that mode. Host allowlisting and account authentication remain separate checks.

Team messages synchronize through polling approximately every three seconds. Background tabs catch up when visible again; login sessions expire on service restart. The default listener is loopback. See the [interface contract](docs/08-interface-contract.md) for LAN deployment and access restrictions.

## Validation and limitations

These are separate validation records as of October 17, 2026. Each report's scope and limitations apply.

| Area | Evidence | Scope |
|---|---|---|
| Interface repair (contract 1.14.0) | 50 Chromium Playwright scenarios; 171 frontend tests; 1,004 backend tests, 5 skipped; 30 live runtime checks. | Independent QA: PASS_WITH_LIMITATIONS. No real model/OCR/embedding calls; some race/identity checks use unit regressions. [Report](probes/ui-repair-20261017/README.md) |
| Account management (contract 1.15.0) | 1,061 backend tests, 2 skipped; 181 frontend tests; 30 delivered Chromium tests, 18 independent checks, 3 navigation stability samples; 27 live checks. | Independent final QA: PASS. Results from unchanged product trees are carried forward with explicit provenance; concurrent CLI/API writes, last-admin protection, and session invalidation verified. No real model calls. [Report](probes/accounts-20261017/README.md) |
| Selected-source delivery | Native text upload → SDK execution and verification nodes → independent model review → stop confirmation → acceptance API. Independent QA: PASS_WITH_LIMITATIONS. | One complete lifecycle on a frozen candidate. [Report](probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md) |
| Team collaboration | 58 real HTTP checks; two Firefox user contexts covering login, shared messages, and logout. Independent QA: PASS_WITH_LIMITATIONS. | This campaign used a deterministic responder and did not revalidate real-model delivery. [Report](probes/team-chat-20261016/qa/QA-REPORT.md) |
| Source intake and retrieval | Integrated version QA for source processing, retrieval, and interface integration. | Quality samples are limited; historical Chinese image-retrieval failures remain recorded. Broad cross-modal quality is unproven. [Report](probes/lg040/TRANSITION-QA-20261016/REPORT.md) |

Current limitations:

- **Browser coverage uses Chromium.** Firefox was not rerun in this repair campaign. Single-user settings writes require the supported same-origin runtime token handshake; team mode uses authenticated account cookies. The Vite development preview alone does not provide the single-user handshake.
- The 1.21 Tasks and 1.22 Google-native ASR candidates passed independent QA with limitations and are merged into local main; the 1.23 demo-recording fixes are an isolated local candidate. No live 8123/5173 version was rechecked in this pass, and none of these candidates is deployed.
- **The 1.23 candidate is developer-integrated, not independently accepted, and is PROVISIONAL.** Its machine-check, execution-evidence, PDF and Team-mention behavior has focused backend/frontend coverage only. The full frontend suite reported **400 passed / 1 failed** on `lg120-roles` pagination, and that failure remains **OPEN/unclassified** pending native Files triage; an isolated rerun passing **5/5** is only a clue, not a classification or waiver. Playwright real-backend recording, real model execution and independent QA remain later gates. The candidate claims no deployment, release or production readiness.
- **LG-249 is an intentional behavior change, not a purely additive field.** In Team mode, ordinary Task messages are now recorded without classifier/responder/model invocation; only a message starting with the configured mention routes to the bot. Single-user mode keeps its previous routing. New DTO/health fields remain additive.
- **Source bindings record provided context.** Model citations have not been verified against individual source spans.
- **Media support is bounded.** PDF processing reads an embedded text layer first and only OCRs sparse/scanned pages (fewer than 16 visible characters per page), with optional `extractor` provenance; images use explicit OCR. English audio has an optional Google native candidate (contract 1.22.0, LG-239 independent browser plus one real Google call PASS_WITH_LIMITATIONS; merged into local main, not deployed) and a default-off legacy EG2/Reader path whose independent quality gate **FAILED**; the Google quality/recognition pass is not claimed. Chinese transcription awaits its quality gate. Office formats have not been comprehensively tested.
- **Recovery is bounded.** Operations with unknown side effects are not automatically replayed. Complete checkpoint-skipping scheduling is not implemented.
- **Integration, deployment, and acceptance are separate.** Local integration and historical QA do not establish that a running service is updated, a release is published, or final user acceptance has occurred.

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

Local 1.19 source-intake candidate: [design](docs/14-material-intake-and-auto-index.md) · [milestone LG-139](backlog/tasks/LG-139.md). Covers Chat receipts, backend-managed automatic media indexing, Files inspection, and semantic search. Implemented in isolated candidate `c3796ab`; [independent QA passed](probes/material-intake-20261018/lg145-r2/REPORT.md). Included in the deployed 1.20 service; private attachments retain their boundaries and English ASR remains off with its quality gate FAILED.

Most detailed project documents are currently in Chinese; the selected-material example guide is in English.

| Entry | Contents |
|---|---|
| [Project handbook](PROJECT.md) · [Progress](PROGRESS.md) | Positioning, decisions, development history, and known issues |
| [Backlog](BACKLOG.md) · [Roadmap](docs/06-roadmap.md) | Tasks, dependencies, and milestone acceptance |
| [Architecture](docs/01-design.md) · [Tasks and resources](docs/02-task-and-sdk-resources.md) | Work model, module boundaries, and resource configuration |
| [SDK audit](docs/03-sdk-capability-audit.md) · [Bot behavior](docs/04-bot-behavior.md) | Execution foundation, message routing, and runtime rules |
| [Navigation](docs/05-navigation-and-team.md) · [Model settings](docs/07-settings-and-models.md) | Tasks workspace, single right Bot Chat, connections, and credentials; provider-aware English ASR settings (legacy EG2/Reader and Google native) |
| [Chat and task teams design](docs/13-chat-and-task-teams.md) | UI wireframes, task-based teams, release states, dispatch gates and acceptance scenarios; independent version QA passed within the documented bounded cases; not deployed |
| [Interface and state contract](docs/08-interface-contract.md) | Contract **1.23.0** local demo-recording candidate (§24: read-only TASK.md, machine-check binding, execution evidence, PDF text layer, Team mention health) on top of the 1.22 Google-native audio (§23) and 1.21 Tasks-workspace (§22) fields; LG-252 independent browser/recording QA pending; no deployment or live-version recheck in this pass |
| [Source intake and retrieval](docs/09-source-intake-and-retrieval.md) | Originals, derived content, indexes, and quality boundaries |
| [Selected-material prototype](docs/10-selected-material-prototype.md) · [Example guide](docs/11-selected-material-demo.md) | Source binding and reproducible workflows |
| [Two-minute demo film](probes/video-20261017/README.md) | Final 1080p/30fps MP4, editable HyperFrames + FFmpeg project, subtitles, provenance and independent QA PASS |
| [Two-account game demo runsheet](docs/12-team-game-demo-runsheet.md) | 120-second runsheet with interface overview, accelerated setup and verified cross-account delivery/acceptance; final film and independent QA linked |

Execution builds on Antigravity SDK; optional vector retrieval uses EmbeddingGemma 2. See [agent.md](agent.md) for role-content and design references. Runtime does not depend on developer-machine copies of Olav OS or Olav Tasks.


### 英文转写UI更新（2026-10-18，已部署、ASR关闭）

已部署1.20的UI与后端已接通本地EG2音频编码器+开源Reader v2、Settings配置、Chat回执、Files音频/机器正文及词法/可选独立文本向量。默认关闭、共享英文音频、最长30秒，无标点/词时间戳；团队Personal私有附件不进入共享ASR，已生成的获授权转写在停用后仍可读取。保存配置不推理、不重建，路径只写、留空保留。

独立LG163功能/UI/权限路径通过，但新留出音频WER8%/21.739%、关键实体丢失，质量门FAILED。上游原版H2实测输出逐字相同，直接复制原版不能修复此例；H1原版未验证。最终候选2fbff57已完成文案/PCM32修复及独立针对性复验（46项浏览器检查通过），整体质量门仍FAILED，不宣称版本通过。生产/根源码现为1.20（main 1ab4d7b），ASR关闭且未配置；1.19资料摄取功能已一并部署，其既有独立验收不受英文质量失败影响。详情：[英文设计](docs/15-english-asr-and-ui.md)。
