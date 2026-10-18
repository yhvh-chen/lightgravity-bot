---
title: "LightGravity Demo Video Script (3–4 min)"
doc_type: script
category: presentation
updated: "2026-10-18"
---

# LightGravity Demo Video Script (3–4 min)

One continuous, real two-account run that takes a team task from raw materials to human acceptance. The film follows the five acts of the pitch deck ([outline](../pitch/outline.md)) and uses its visual system ([design](../pitch/design.md)). Target length **3:35**; hard limit 4:00.

This script is a plan, not evidence. Nothing in the film may be staged, mocked or spliced from different runs.

---

## 1. Recording Gates (all must pass before the real take)

| Gate | Required fact |
|---|---|
| Product fixes | Recording build = Google ASR + Tasks candidate (`ecda49f`, contract 1.22) plus fixes for the LG-233 readiness blockers: LG-220 (Board auto-refresh and navigation), LG-240 (`@bot` Task not opened), LG-241 (New task has no workspace), LG-242 (`TASK.md` not openable, `.git` files shown), LG-243/244 (Board checks and reviewer verdict, honest check status), LG-245 (Board Preview / Markdown artifact opens), LG-224 (PDF text layer), and English-only copy. Re-run readiness on that build while recording; footage is released only when product and capture checks pass. |
| Instance | One frozen candidate commit, isolated demo data directory on persistent disk (not `/tmp`), dedicated port. Record URL, commit and contract version. |
| Models | Coordinator and worker connections configured and tested; the **Reviewer uses a separate connection** from the worker. Executor enabled (not `--no-executor`). |
| Retrieval | Embedding configured and tested. If the film claims **EmbeddingGemma 2**, record on an instance using `embeddinggemma-2` (192.168.8.12), not `gemini-embedding-2`. |
| OCR | OCR configured with a vision model that accepts images (LG-233: DeepSeek `deepseek-flash` works, `deepseek-v4-pro` does not; Gemini flash for the Google demo). |
| English ASR | Google native audio transcription (Gemini, LG-234/239, PASS_WITH_LIMITATIONS) configured with its own Google key. Quality was only checked on a few synthetic samples, so on the day transcribe the exact `customer-call.wav` first and compare it with the script text; if a word that matters is wrong, re-record the clip or show the transcript with an on-screen note. Never edit the machine transcript to look perfect. |
| Accounts | Admin creates two member accounts: **Alice (A)** and **Ben (B)**. Each signs in from an independent browser context. |
| Numbers | Re-verify on the recording day: recruitable role count, test totals, deployment target. Show nothing that is not true on that day. |

---

## 2. Cast, Screens and Materials

- **Alice (A)**: requester and acceptor. Identity badge top-left: `ALICE · MEMBER`.
- **Ben (B)**: reviewer teammate. Identity badge: `BEN · MEMBER`.
- **Layout**: 1920×1080 capture, browser at 1440 px wide. Left rail `Tasks · Board · Team`, main area = Task workspace, right = Bot Chat.
- **Materials** (English only, prepared in advance, no personal data):
  1. `product-brief.pdf`: a digital PDF with a text layer (one page, launch brief for a fictional product).
  2. `whiteboard-notes.jpg`: a photo of handwritten or scanned notes (OCR path).
  3. `customer-call.wav`: English speech, 20–30 seconds, one speaker, clear audio. Suggested line: "We like Orbit Notes, but six dollars per user is a lot for a team that only meets once a week. An annual discount would make it an easy yes." (Google native ASR path.)
- **Deliverable requested**: `launch-brief.md`, a one-page launch brief in Markdown (headline and key message, a Free vs Team pricing table, the top customer concern and the response, a short FAQ), with every point citing the source it came from. Markdown renders in the Tasks workspace; HTML is never rendered in the app by design, so do not ask for `index.html`.
- **Early footage (LG-255)**: scenes 3b and 3d were recorded on the 1.21 test candidate (`take-005-3b3d.mp4`, 45 s). Reuse only after comparing the same screens on the frozen recording candidate. Known on-camera issues: raw frontmatter in View material, semantic panel header still says "Text search", warm up the embedding service before the take.
- **Material quality**: render the notes image with real line spacing (no overlapping text) and check every file by eye before the take.

---

## 3. Timeline

Times are **film time**, not real execution time. Waiting is cut or sped up and labelled `SPED UP ×N` or `TIME SKIPPED`.

| # | Film time | Pitch act | Screen and action | Narration (VO) | Must be visible |
|---|---|---|---|---|---|
| 1 | 0:00–0:15 | 01–02 Problem | Title cards on obsidian: "Agents moved beyond code." → "Chat didn't." → product logo. | "AI agents now do real team work. But chat threads lose context, and nobody can say who checked the result." | Product name, one-line thesis. |
| 2 | 0:15–0:35 | 03 File SoT | Tasks rail: open an existing Task. Main area shows its directory: `TASK.md`, artifacts, evidence. Right panel shows the Task's Bot Chat with `Personal / Team`. | "In LightGravity, every task is a folder you own: Markdown, YAML and logs on disk, not a chat history." | A Task is a real directory; `TASK.md` opens. |
| 3a | 0:35–0:45 | 04 Intake | A, Team channel: attach `product-brief.pdf`, send. Receipt shows text from the text layer, keyword index and semantic index. | "Alice drops in the source material." | Per-file receipt with separate states. |
| 3b | 0:45–0:55 | 04 Intake | Attach `whiteboard-notes.jpg`. Receipt shows OCR text ready. Click View material: hold on the original, then scroll to the extracted text (the app stacks them, it does not show them side by side). Crop or scroll past the raw frontmatter block. | "Scans and photos are read too." | OCR text, linked to the original. Early footage: `probes/demo-footage-20261018/footage/take-005-3b3d.mp4`. |
| 3c | 0:55–1:02 | 04 Intake · 07 Google | Attach `customer-call.wav`. Receipt shows the English transcript ready; View material shows the machine transcript next to the audio original. | "And customer calls, transcribed by Gemini." | Transcript text, labelled as machine transcript, linked to the audio. |
| 3d | 1:02–1:08 | 07 EmbeddingGemma 2 | Top search, Semantic: query "pricing concerns from the call" → hits from the call transcript and the notes → open the call. | "Then everything is searchable by meaning, powered by EmbeddingGemma 2." | Semantic mode, hits from two formats, open source. |
| 4 | 1:08–1:30 | 05 Human layer | A and B exchange two plain Team messages; the bot stays silent. A ticks **Use as context** on the three sources, then sends the `@bot` request (Prompt P1). A new Task directory appears in Tasks; the right panel switches to it. | "The team talks freely. The bot only joins when someone says @bot, and works only from the sources they chose." | Silent messages, explicit `@bot`, selected sources, new Task ID. |
| 5 | 1:30–2:05 | 06 AI team | Team → Recruited: roles recruited for this Task from the role library. Board: phases advance on their own. Task workspace: `launch-brief.md` appears. | "For each task, LightGravity recruits a small team from its specialist role library. Every step lands in the task's folder." | Real members and roles for this Task ID; phases; artifacts. |
| 6 | 2:05–2:30 | 06 Reviewer ≠ Author | Board detail: machine checks, then the independent Reviewer verdict, with the Reviewer connection shown as separate from the worker. | "Workers can't mark their own work done. Machine checks run first, then an independent reviewer model checks the result against the requirements." | Check results, reviewer verdict, separate connection. |
| 7 | 2:30–3:05 | 05 Cross-account | Switch to B (badge visible first). B opens the same Task ID, reads the rendered `launch-brief.md` (pricing table, cited sources), posts feedback in Team (Prompt P2). Switch to A: A sees the feedback and clicks **Accept** on Board. Task shows accepted. | "Ben, signed in separately, inspects the same deliverable and leaves feedback. Alice accepts it. Done means a person accepted it." | Same Task ID in both accounts; Accept bound to the current candidate. |
| 8 | 3:05–3:20 | 03, 07, 08 Proof | Open `TASK.md` frontmatter: requirements revision, candidate and acceptance. Switch to a separate ADMIN context, show its identity, then briefly open Settings → Models with non-secret fields only. Corner badge with the deployment URL. | "The whole record stays in open files. Built on Google's Antigravity SDK and Gemma." | Revision and acceptance in the file; real deployment URL; ADMIN identity before Settings. |
| 9 | 3:20–3:35 | 11 Closer | Safety-orange end card: "Trust the delivery, not just the output." Links: live workspace, GitHub. | "LightGravity. Trust the delivery, not just the output." | Links that resolve. |

The narration column above is a summary; the voice-over text to record is [narration.md](narration.md) (257-word first draft, one file per scene). VO total stays under ~420 words, which is about 2:50 of speech at a calm pace and leaves room for silent product moments.

---

## 4. Prompts (paste, then hold for one second)

**P1 · Alice, Team channel, with the three sources selected as context**

```text
@bot Using the selected sources, write launch-brief.md: a one-page launch brief for
the product in the brief. Include the headline and key message, a Free vs Team pricing
table, the top customer concern from the call and how we answer it, and a short FAQ.
Cite the source for every point.
```

**P2 · Ben, Team channel**

```text
Checked launch-brief.md for <TASK-ID>: pricing matches the brief, and the concern from
the customer call is answered with the annual-plan idea from the notes. Good to accept.
```

Replace `<TASK-ID>` with the real ID from the run. Keep the ID readable on screen in Scenes 4, 5 and 7.

---

## 5. Recording and Editing Rules

**Capture while testing.** The pre-recording readiness run (LG-252) is executed in recording mode, so every real run also produces footage. A complete run where every scene passes and capture quality is verified is the master footage; failed runs are kept as evidence only.

- **Recording mode.** Headed Chromium on an Xvfb 1920×1080 display, captured full-screen with FFmpeg (not Playwright's built-in video). Visible injected cursor with click feedback, typing character by character (`pressSequentially` with a delay), `slowMo` between actions, 1–2 s holds on key results. One window per account (or side by side). Playwright traces and logs are kept as evidence.
- **Capture preflight.** Before a full model task, make a short recording to verify account switches and identities, 1920×1080 framing, cursor feedback, timecodes, clean FFmpeg shutdown and playable output. Do not mix this footage into the film.
- **Preserve every attempt.** Each capture gets a unique `capture_id` directory with its own Playwright outputDir, recordings, traces, screenshots, logs and manifest. Continuations and retries never overwrite prior evidence. Record capture ID separately from product Task/Run IDs; retain failures.
- **Two verdicts.** Record product readiness and footage usability separately. Only a complete run with every product scene passing and complete, legible, playable, timecoded and hashed footage becomes master footage.
- **Tag every take.** Each run writes `timeline.json`: run ID, candidate commit/tree, scene number, start/end timecodes, pass/fail. Footage SHA256s go into the manifest.
- **Which footage is usable.** Only takes recorded on the frozen recording candidate (LG-251). All product scenes (2–8, including 3a–3d intake) come from the **same complete successful capture run**. Scenes 4–8 follow one Task from `@bot` to Accept; selected source IDs, versions and hashes match that run's intake.
- **Human take is the fallback.** Record a complete human OBS take only if agent footage does not look natural enough, with the same candidate, identity and evidence requirements.
- **One real run.** Capture one continuous real run with full raw screen recordings for both accounts, browser traces and server logs. Keep them with the film.
- **No splicing across runs.** Failed runs remain evidence. After a product fix, integrate and freeze a new candidate, then re-shoot the complete run. Missing footage also requires a complete new take; human fallback follows the same rule.
- **Speed-ups are labelled.** Any cut over waiting time carries `SPED UP ×N` or `TIME SKIPPED`.
- **Identity first.** After every account switch, show the badge and channel before the content.
- **Setup stays off camera.** Deployment, account creation and model configuration are not shown, except the Settings flash in Scene 8, using a separate ADMIN context after showing its identity; Alice and Ben remain members.
- **No secrets on screen.** Never show API keys, tokens, internal error codes or terminal commands.
- **Captions.** English subtitles (SRT and VTT) for all narration. Requirement keywords and the Task ID stay legible at 1080p.
- **Gated content.** Anything behind a failed gate (Section 1) is cut or labelled; never presented as a verified capability.

---

## 6. Pitch Copy to Align Before Recording

These statements in [outline.md](../pitch/outline.md) no longer match the product and would contradict the film:

| Slide | Current claim | Why it conflicts | Fix |
|---|---|---|---|
| 06 | "Full-Lifecycle Budgets: cost ceilings span execution, verification, repair…" | LG-230 removed model and API usage caps (counting and display remain). | Reword to "full-lifecycle usage accounting". |
| 08 | "host allow-list" in the API layer | LG-230 removed the model host allowlist. | Drop it, or say "Host/Origin guard" if that is what is meant. |
| 04, 08 | Left rail "Chat, Board, Files, Team" | LG-202 replaces Chat and Files with Tasks plus a right-side Bot Chat. | Update copy and screenshots after LG-202 ships. |
| 07 | "English audio transcripts" without naming the engine | ASR now runs on Google native audio transcription (Gemini); EmbeddingGemma 2 only embeds. | Name Gemini for transcription and keep EmbeddingGemma 2 for retrieval. |
| 07 | EmbeddingGemma 2 as the retrieval engine | The online demo plan uses Google API, which offers `gemini-embedding-2`, not EmbeddingGemma 2. | Record retrieval on an EmbeddingGemma 2 instance, or reword. |
| 09, 11 | Test counts, "120s verified demo film" | Numbers change; this film replaces the 120 s film. | Refresh on the recording day; link the new film. |

---

## 7. Production Process

| Step | Owner | Output |
|---|---|---|
| 1. Gates | PM | Section 1 checked and recorded; demo instance and model setup decided (LG-228). |
| 2. Freeze | pi | Candidate commit, isolated data dir and port, accounts A/B, configured connections, prepared materials. |
| 3. Test-and-record runs | independent pi (LG-252) | Full real runs in recording mode; per-scene verdict, real duration and usage; issues sent to fixers; footage and `timeline.json` archived for every run. |
| 4. Master footage | pi + PM | The first complete run on the frozen candidate where every scene passes and capture quality is verified becomes the master footage; otherwise fix and re-run. Complete human OBS take only as fallback. |
| 5. Edit | pi (editor) | Cut per Section 3 using the existing HyperFrames/FFmpeg pipeline; captions; labelled speed-ups. |
| 6. Independent QA | separate pi | Every scene checked against raw evidence; facts, labels, identity badges, no secrets, 1080p legibility. |
| 7. Delivery | PM | Final MP4 plus manifest (SHA256, source commit, run IDs) in `content/demo/`; pitch Slide 11 link updated. |
