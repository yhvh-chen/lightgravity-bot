---
title: "LightGravity Pitch Deck Design System"
doc_type: design_guide
category: presentation
updated: "2026-10-18"
---

# LightGravity Pitch Deck Design System

This specification governs the visual identity, color tokens, typography hierarchy, and layout rules for all presentation decks and pitch materials under `pitch/`. Narrative structure and slide copy are defined in [outline.md](outline.md).

---

## 1. Design Philosophy & Aesthetic Identity

* **Core Style**: **Contemporary Neo-Brutalism** × **Editorial Modernism** × **Celestial Engineering Diagramming**.
* **Semantic Intent**:
  * **Deterministic & Governed**: Rejects generic AI presentation clichés (neon gradients, glassmorphism, blurry glows, and stock 3D spheres). Uses crisp black strokes, modular Swiss grids, and structured cards to visually mirror our thesis: *"Control is code. Models only execute."*
  * **Artifact-First**: Perforated borders, monospace tags, comparison matrices, and real system diagrams communicate that LightGravity is an engineering-grade workspace for verifiable deliverables—not a black-box chat wrapper.
  * **Editorial Wit**: Pairs heavy industrial sans-serif headlines with expressive italic serif accents, bringing publication-grade clarity and human warmth to technical architecture.

---

## 2. Color Palette & Tokens

The deck alternates between warm paper and deep obsidian grounds to create a deliberate **page-flip rhythm**, punctuated by flat, high-saturation primary accents.

### 2.1 Canvas Grounds
| Token | Hex | Usage |
| :--- | :--- | :--- |
| `bg-paper` | `#F4EFE6` | **Warm Parchment / Cream**. Primary ground for the cover, foundation matrices, human collaboration, and validation slides. |
| `bg-obsidian`| `#111116` | **Obsidian / Void Black**. High-contrast ground for problem framing, orbital workflows, AI team gates, cloud architecture, and vision slides. |
| `bg-highlight`| `#FF4D00` / `#2563EB` | **Full-Bleed Accent Ground**. Used sparingly for high-impact transitions, the Google AI foundation highlight, or the closing slide. |

### 2.2 Ink & Linework
| Token | Hex | Usage |
| :--- | :--- | :--- |
| `ink-primary` | `#111111` | Primary text on light grounds and all hard `1.5px–2px` container borders. |
| `ink-inverse` | `#F8FAFC` | Primary headline and body text on `bg-obsidian` or `bg-highlight` grounds. |
| `ink-muted` | `#64748B` / `#94A3B8` | Secondary captions, footnotes, and scope disclaimers. |

### 2.3 Functional Accents (Flat Fill Only — No Gradients)
* **Cobalt Blue (`#2563EB`)**: Control plane, Google Cloud integration, primary interactive highlights.
* **Safety Orange / Vermilion (`#FF4D00`)**: Core pain points, Antigravity SDK badges, critical callouts.
* **Acid Lime (`#D4FF28`)**: Acceptance (`Accepted`), winning comparison columns, EmbeddingGemma 2 badges, passed checks.
* **Soft Lilac (`#E2B7E8`)**: Secondary architectural layers (e.g., Coordination layer).

---

## 3. Typography Matrix

Every slide follows a strict **three-typeface system**:

```text
[Heavy Display Sans] + [Editorial Italic Serif Accent] + [Engineering Monospace]
```

1. **Display Sans (Primary Headline)**:
   * *Recommended*: `Plus Jakarta Sans (ExtraBold / 800)`, `Archivo Black`, or `Helvetica Now Display`.
   * *Role*: Main structural statements (e.g., **Agents moved beyond code.**, **Control is**).
2. **Editorial Italic Serif (Contrast Accent)**:
   * *Recommended*: `Instrument Serif (Italic)`, `Playfair Display (Italic)`, or `Newsreader (Italic)`.
   * *Role*: Highlights the emotional or conceptual pivot word in a headline (e.g., *Chat didn't.*, *orbits*, *code.*, *delivery*).
   * *Rule*: **Limit italic serif usage to 1–3 words per headline** to preserve visual tension.
3. **Engineering Monospace (Metadata & Code)**:
   * *Recommended*: `JetBrains Mono` or `Space Mono`.
   * *Role*: Section eyebrows (`— § 01 — THE PARADIGM SHIFT`), slide numbers (`01 / 11`), pill badges, CLI snippets, and schema keys.
4. **Body Sans (Descriptions & Tables)**:
   * *Recommended*: `Plus Jakarta Sans (Regular 400 / Medium 500)` or `Inter`.
   * *Line Height*: `1.45`–`1.55` for effortless scanning during a fast pitch.

---

## 4. Layout Grid, Framing & Graphic Motifs

### 4.1 Hard Borders & Offset Shadows
* **Hard Strokes**: Every card, table, and diagram node uses a solid `1.5px` or `2px` border (`#111111` on light grounds; `#FFFFFF` or accent-colored on dark grounds).
* **Sharp / Micro-Radius Corners**: Border radius is `0px` to `4px` maximum.
* **Hard Offset Shadows**: Never use blurry drop shadows. Where elevation is needed on `bg-paper`, use a crisp neo-brutalist offset shadow: `box-shadow: 4px 4px 0px #111111;`.
* **Perforated Artifact Frames**: For UI screenshots and reserved evidence boxes, use an inner dashed border (`1.5px dashed #111111`) to evoke physical work artifacts on an inspection desk.

### 4.2 Celestial & Orbital Geometry
* Used on the Cover (Slide 01), End-to-End Workflow (Slide 04), and Scale/Vision (Slide 10):
  * Concentric hairlines (`1px solid`) and dotted orbital rings (`stroke-dasharray: 4 6`).
  * Numbered circular nodes (`1`–`6`) orbiting a central `TASK` core.

### 4.3 Standard Header & Footer Rail
* **Top Eyebrow**: Left-aligned short accent bar + uppercase monospace section tag (`— § 02 — THE TWO FOUNDATIONS`).
* **Bottom Footer**:
  * **Left**: `LIGHTGRAVITY ◦ AI BUILDER CUP 2026`
  * **Center**: 11-dot pagination indicator (passed slides filled muted, current slide highlighted with an accent ring, remaining slides hollow).
  * **Right**: Zero-padded slide counter (`03 / 11`).

---

## 5. Strict Anti-Patterns

* ❌ **No Glassmorphism or Backdrop Blurs**: Keep all surfaces 100% opaque and legible.
* ❌ **No Neon Glows or Mesh Gradients**: Rely on stark color blocking and typography contrast.
* ❌ **No Stock Illustrations or 3D Avatars**: Every diagram must represent real system entities (`Source`, `Task`, `Run`, `Subtask`, `Role`, `Artifact`, `Review`, `lakeFS Branch`).
* ❌ **No Unverified Claims**: Keep `Now` (verified code & tests) visually and verbally distinct from `Next / Later` (roadmap & architectural evolution).
