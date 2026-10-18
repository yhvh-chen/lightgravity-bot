---
title: "LightGravity Demo Narration (English, for CosyVoice)"
doc_type: narration
category: presentation
updated: "2026-10-19"
---

# LightGravity Demo Narration (English)

Narration for the 3:35 film in [script.md](script.md). Written for text-to-speech: one line = one sentence = one synthesis request. Keep each scene as its own audio file (`scene-1.wav`, `scene-3a.wav`, …) so the picture can be cut to the voice, not the other way round.

This is the **first draft**. Scenes 3a–3c, 5 and 8 name things that must be true on the recording day (PDF text layer, Gemini transcription, role library, Antigravity SDK); re-check them against the frozen recording build before final synthesis.

## Budget

Calm pace ≈ 2.3 words per second. Words in each scene leave silence for the picture to breathe.

| Scene | Film time | Shot | Words | Est. speech | Title |
|---|---|---|---|---|---|
| 1 | 0:00–0:15 | 15 s | 23 | ~10 s | Problem |
| 2 | 0:15–0:35 | 20 s | 31 | ~13 s | A task is a folder |
| 3a | 0:35–0:45 | 10 s | 11 | ~5 s | Intake: PDF |
| 3b | 0:45–0:55 | 10 s | 17 | ~7 s | Intake: image and OCR |
| 3c | 0:55–1:02 | 7 s | 6 | ~3 s | Intake: audio |
| 3d | 1:02–1:08 | 6 s | 11 | ~5 s | Search |
| 4 | 1:08–1:30 | 22 s | 38 | ~17 s | Human team layer |
| 5 | 1:30–2:05 | 35 s | 43 | ~19 s | AI task team |
| 6 | 2:05–2:30 | 25 s | 26 | ~11 s | Reviewer is not the author |
| 7 | 2:30–3:05 | 35 s | 46 | ~20 s | Cross-account acceptance |
| 8 | 3:05–3:20 | 15 s | 23 | ~10 s | Proof |
| 9 | 3:20–3:35 | 15 s | 8 | ~3 s | Closer |
| **Total** | | 215 s | **283** | ~123 s | |

## How to generate (CosyVoice3)

- Reference: `content/demo/voice/ref-james-6s.wav` (6 s works; 15 s failed with HTTP 500). The reference transcript must match what is spoken in that clip.
- Synthesize each **line** as one request (`mode=zero_shot`, `speed=1.0`), then join the lines of a scene with about 0.3 s of silence. If a scene is too long for its shot, shorten the text or raise `speed` slightly (max 1.1); do not rush it.
- Listen for: cut-off endings, "Y-A-M-L", "S-D-K", "Embedding Gemma two", "at bot". Respell a word if it is misread (see below).
- Keep every take; name files `scene-<id>-take<n>.wav` and note the chosen take.

## Files for batch generation

- [`narration-lines.json`](narration-lines.json): every line with scene, id, text, word count, estimated seconds and output file name; `risky` marks lines with brand or acronym words to listen to first (2-2, 3c-1, 3d-1, 4-2, 8-2).
- [`generate-narration.sh`](generate-narration.sh): runs the lines serially against the CosyVoice host. `REF_TEXT="<exact words in ref-james-6s.wav>" ./generate-narration.sh` generates all 30 lines into `out/`; pass ids (`./generate-narration.sh 2-2 4-2`) to test or retry only some. It never overwrites a take (a second run of the same line becomes `-take2`), removes files from failed requests, and does not save the voice on the server.

## Pronunciation cues (already applied in the text below)

| On screen | Spoken as | Why |
|---|---|---|
| YAML | Y-A-M-L | avoid "yammel" |
| SDK | S-D-K | avoid "sdick" |
| EmbeddingGemma 2 | Embedding Gemma two | digit and brand |
| `@bot` | at bot | avoid "at-sign" |
| OCR / PDF | omitted or spelled as needed | none used here except "P-D-F" if you add it |
| TASK.md | not read aloud | say "task" instead |

## Narration

### Scene 1 · 0:00–0:15 · Problem

Target: speech ≤ 12 s of the 15 s shot.

```text
AI agents now do real team work.
But chat threads lose context, and nobody can say who checked the result.
LightGravity changes that.
```

### Scene 2 · 0:15–0:35 · A task is a folder

Target: speech ≤ 17 s of the 20 s shot.

```text
In LightGravity, every task is a folder you own.
Markdown, Y-A-M-L and logs, on disk, not buried in a chat history.
Open any task, and you can read exactly what happened.
```

### Scene 3a · 0:35–0:45 · Intake: PDF

Target: speech ≤ 8 s of the 10 s shot.

```text
Alice drops in the source material, starting with a product brief.
```

### Scene 3b · 0:45–0:55 · Intake: image and OCR

Target: speech ≤ 8 s of the 10 s shot.

```text
Photos and scans are read too.
The text is extracted, and it stays linked to the original.
```

### Scene 3c · 0:55–1:02 · Intake: audio

Target: speech ≤ 5 s of the 7 s shot.

```text
Customer calls are transcribed by Gemini.
```

### Scene 3d · 1:02–1:08 · Search

Target: speech ≤ 5 s of the 6 s shot.

```text
Then everything is searchable by meaning, powered by Embedding Gemma two.
```

### Scene 4 · 1:08–1:30 · Human team layer

Target: speech ≤ 18 s of the 22 s shot.

```text
The team talks freely, and the bot stays quiet.
It only joins when someone says, at bot, and it works only from the sources they chose.
Alice asks for a launch brief, and a new task is created.
```

### Scene 5 · 1:30–2:05 · AI task team

Target: speech ≤ 29 s of the 35 s shot.

```text
For each task, LightGravity recruits a small team from its library of specialist roles.
You can see who was recruited, and what each member is working on.
Every step, and every file, lands in the task's own folder.
This part is sped up.
```

### Scene 6 · 2:05–2:30 · Reviewer is not the author

Target: speech ≤ 21 s of the 25 s shot.

```text
Workers can't mark their own work done.
Machine checks run first.
Then an independent reviewer, on a separate model connection, checks the result against the requirements.
```

### Scene 7 · 2:30–3:05 · Cross-account acceptance

Target: speech ≤ 29 s of the 35 s shot.

```text
Now Ben, signed in separately, opens the same task.
He reads the launch brief, checks every point against its source, and leaves feedback.
Back in Alice's account, the feedback is right there on the same task.
She accepts the delivery.
Done means a person accepted it.
```

### Scene 8 · 3:05–3:20 · Proof

Target: speech ≤ 12 s of the 15 s shot.

```text
The whole record stays in open files: the requirements, the candidate, and the acceptance.
Built on Google's Antigravity S-D-K, with Gemma for retrieval.
```

### Scene 9 · 3:20–3:35 · Closer

Target: speech ≤ 12 s of the 15 s shot.

```text
LightGravity.
Trust the delivery, not just the output.
```

## Optional silent beats

No voice is needed during: the two title cards in scene 1 (first 2 s), the Settings flash in scene 8, the browser holds right after each click, and the last 3 s of scene 9. Let the product speak.
