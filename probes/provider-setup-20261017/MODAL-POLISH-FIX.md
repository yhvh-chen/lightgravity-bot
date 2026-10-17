# LG-115 — compact connection modal repair

Date: 2026-10-17. Owner: native Codex defect-repair subagent.
Base: stable R1 `eef3b3e` (product `345f71f`, includes LG-113 reference-lock fix).
Branch: `fix/provider-modal-polish-20261017`.
Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-modal-polish-20261017`.

## Change

The DeepSeek default modal now has four primary fields: Provider, Name, API key,
Model. The editable preset Base URL and existing SDK/proxy implementation notes
are in the collapsed Advanced disclosure. Custom and legacy custom
OpenAI-compatible Base URL remains a required primary field. Both placements
use the same existing value/change handler, validation and request construction.

Removed the default header draft explanation, internal-ID explanation, write-only
suffix, new-key storage paragraph and model implementation explanation from the
primary form. Existing configured credentials retain the Configured badge and
“Leave empty to keep the saved key” helper. Changed-provider/endpoint key
requirements and validation remain intact. Native/custom/ADC/LiteRT prerequisites
and current limitations have concise primary hints; full technical preset notes
remain in Advanced. Repeated ADC/LiteRT field explanations were removed.

The untested panel is “Not tested”; running state is “Testing current values…”.
Actual result badges, unsaved-draft identity, stale/error details and late-result
handling are unchanged. Paid-provider Test has the concise “Test may use API
credits” note. No API, provider state, authentication, save/cancel, permission,
focus, deep-link, or test-request behavior was changed.

No CSS was changed: the existing 540px desktop width, natural content sizing,
mobile near-fullscreen layout and reachable footer remain. Reduced primary
content addresses the excessive natural height; there is no new fixed-height
cap, clipping or scroll-based shortcut.

## Verification

Reused existing root `frontend/node_modules` through a temporary worktree-only
symlink; no package installation or lockfile change. Commands ran in the isolated
frontend directory:

- `./node_modules/.bin/vitest run tests/settings.test.tsx
  tests/provider-setup.test.tsx tests/settings-auth.test.ts
  tests/lg053-navigation-regression.test.tsx` — **39 passed / 4 files**.
- `npm run build` — **pass**, including `tsc --noEmit` and Vite production build
  (109 transformed modules).
- `git diff --check` — **pass**.

Existing 38 focused tests passed unchanged. One added behavior regression checks
that the preset endpoint lives inside collapsed Advanced rather than the primary
fields, editing it still requires a fresh key, and explicit draft Test sends the
edited endpoint/new key without Save. The existing custom endpoint regression
continues to verify required primary Base URL and independent Save behavior.
No copy snapshots or mirrored string tests were added.

The initial added test used an exact API-key label lookup and failed because the
inline hint participates in its label. Using the existing suite's prefix-regex
convention fixed the test selector; the final 39-test run passed. Earlier shell
commands with an incorrect frontend-relative path made no edits and were rerun
from the correct directory. Build artifacts and temporary dependency symlink
were removed from this isolated worktree before handoff.

## Limits and handoff

No browser was run, so **actual desktop modal height and mobile visual/readability
acceptance have not been measured here**. Independent pi must capture fresh
screenshots at the required sizes and confirm the approximately <=600px natural
desktop target and usable mobile form/buttons; old screenshots are not evidence
for this repair. A full frontend rerun was not needed after focused coverage and
successful type/build checks.

No backend, PM/task/root document, live service/data, real credential, package,
environment or runtime change. Product/vendor/model calls: **0**. Development
cost/token usage: unknown. No merge, push, deployment or task-done action.
