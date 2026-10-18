# DELIVERY — Gitea serial merge 2026-10-18 (Google-native ASR + Tasks 1.22.0)

Status: **integration complete locally; `main` pushed normally to Gitea without force; no deployment, service restart, Google call, Cloud resource, release, or GitHub push.** Root dirty work was preserved. Public 8123/5173 remains **1.20.0**; the repository now carries the accepted **1.22.0** candidate source.

## 1. Result at a glance

| Item | Value |
|---|---|
| Integration code HEAD (`main`) | `93e682c0ce5e9b5549b86052513085949641b839` |
| Before integration (`main`) | `cd0e8c8` |
| Published remote `origin/main` before fetch | `164990f` (published 1.18 source snapshot) |
| Merge-base `main` ↔ `origin/main` | `18de318` (branches had diverged; published tree is older/subset) |
| Accepted candidate | `integration/google-native-asr-20261018` tip `9592185` |
| Frozen candidate product | `ecda49f692097b07d6f574652f9ed72b6387919a`, tree `d96f22b6d5acbb509cb9cbf6c232d557215af19b` |
| Contract | `1.22.0` |
| Product subtree identity | `backend` `6cc2a72d…`, `frontend` `2526bbf5…`, `tests` `e9ebfaf7…`, `e2e` `90497e1e…` — **all byte-identical to `ecda49f`** |
| PM checkpoint commits | `5a5876f` (root dirty PM files), `c770bce` (reconciled with 1.22 docs), `8e4f9d8` (concurrent demo-recording PM batch) |
| Merge commits | `634f732` (published history, tree kept from internal main), `08e25e4` (candidate), `595f5fa` (records root PM checkpoint) |
| Report/evidence commit(s) | Added after `8e4f9d8`; docs/evidence-only and do not change the product tree |
| Final remote `main` after push | `__PUSHED_MAIN__` (verified with `git ls-remote` after push; see evidence) |

## 2. Branch inventory and merge decision

Full 278-local-branch table, classifications, worktree mapping and equivalence notes: **[BRANCHES.md](BRANCHES.md)** (machine-readable: [branches.tsv](branches.tsv)).

- 278 local branches: **133** ancestor of/merged into main, **145** unmerged tips. 3 remote branches plus `origin/HEAD` were fetched.
- **Included:** `integration/google-native-asr-20261018` `9592185` (frozen product `ecda49f`), containing the accepted Tasks 1.21 integration `8d869ff` and the Google-native ASR backend/UI.
- **Contributors/equivalents retained:** `qa/google-native-asr` (`ecda49f`), `dev/google-native-asr-backend` (`26a87ad`), `dev/google-native-asr-ui` (`f17b0d1`, UI tip cherry-picked as `b5b7e39`), `prep/google-native-asr` (`39ab939`), `integration/demo-tasks` (`8d869ff`), `qa/demo-tasks`/`fix/demo-tasks-qa-r1` (`b01e7ce`, product-equivalent), `test/lg233-readiness` (`84c33c1`, tree-identical to `539e622`), and the Tasks dev branches. Older tips are not merged wholesale.
- **Excluded:** `integration/lg214-remote-reader-candidate` and `dev/lg176`/`dev/lg178`/`dev/lg179`/`fix/lg180` remote-reader/frame line (frozen); old EG2/Reader English-ASR line (quality **FAILED**); failed experiments/QA-only branches. All retained, none deleted.
- **Other late branches assessed:** no unmerged branch newer than the candidate contains a newer completed product delivery with independent QA. The only recent alternatives are the equivalents above.

### Published history divergence

`origin/main` (`164990f`) was a published 1.18 source snapshot on a different history line. It has no file that the internal main lacks; its versions are older. The integration merged it with `git merge -s ours` to record the published history while keeping the newer internal product tree. This avoided reintroducing the 1.18 tree and did not discard any remote-only file.

## 3. What was integrated and how conflicts were resolved

Sequence (all in the isolated worktree `/home/yhvh/code/lightgravity-bot-worktrees/merge-gitea-20261018`, not in root):

1. `git merge --no-ff -s ours origin/main` → `634f732`.
2. `git merge --no-ff 9592185` → `08e25e4`. **Automatic merge, no product conflict.** The staged tree equalled the candidate tip tree `67cef27…`; product tree equalled frozen `d96f22b…`.
3. Root PM dirty files were committed as checkpoint `5a5876f`; the integration branch reconciled them with candidate docs in `c770bce`; `595f5fa` records the root checkpoint as an ancestor without overwriting the reconciled tree.
4. Root `main` fast-forwarded to the result. After that, a concurrent PM update (demo-recording fix batch) was preserved and committed as `8e4f9d8`; root worktree now carries the new code; only untracked `content/` remains.

Documentation reconciliation (contract stays **1.22.0**, no usage limits preserved):

- `docs/08-interface-contract.md`: candidate §§20–23 kept; §§22/23 statuses updated from “pending LG-207/LG-239” to **PASS_WITH_LIMITATIONS**, merged locally, not deployed; §23.1 keeps the no-usage-limit behaviour and adds the PM note that the old §18 “DeepSeek only” constraint is obsolete, old jobs keep their values, and PDF OCR is uncapped.
- `docs/07-settings-and-models.md`: kept existing §8 Embedding and §9 auto-index numbering (code docstrings reference §8); the Google ASR section is appended as **§10 / §10.1** with LG-239 status.
- `README.md`, `PROJECT.md`, `PROGRESS.md`, `docs/05`: kept the latest PM records and the candidate’s Tasks/Google notes; stale “pending LG-239/LG-207” wording was corrected. Historical failed-Record/Reader evidence is unchanged.
- `design.md`: clean 3-way merge. No product requirement was changed.
- `LG-246` priority-format issue (owned by another team) was **not modified**; the file is not part of the tracked PM checkpoint.

## 4. Verification actually run

No product code was changed after the frozen candidate. The product tree is byte-identical to `ecda49f`, so the full LG-238/LG-239 test campaign was not repeated.

| Check | Result | Evidence |
|---|---|---|
| Product diff `ecda49f..HEAD` for backend/frontend/tests/e2e/build files | **empty** | [merge-tree.txt](evidence/merge-tree.txt) |
| Subtree hashes backend/frontend/tests/e2e | identical to `ecda49f` | same |
| `CONTRACT_VERSION` | `1.22.0` | same |
| Focused backend: `tests/contracts/test_contracts.py` + `tests/asr/test_google_provider_contract.py` (lightweight LG-236 venv, no Torch) | **15 passed** | [backend-focused.txt](evidence/backend-focused.txt) |
| Frontend `npm run typecheck` + `npm run build` (sequential, low concurrency) | **exit 0**; 128 modules; `index-DDU0pU3S.js` 453.46 kB / `index-BMHMEIYi.css` 68.30 kB (same as candidate) | [frontend-build.txt](evidence/frontend-build.txt) |
| `git diff --check` | clean | — |
| Secret scan | **PASS_NO_SECRETS_FOUND** | [secret-scan.txt](evidence/secret-scan.txt) |
| Services 8123/5173/18123 | still listening, PIDs **536200 / 2332542 / 1597462**; no restart/deploy command run | [services-and-root.txt](evidence/services-and-root.txt) |

Existing QA identity carried (not re-run): LG-239 **PASS_WITH_LIMITATIONS** (one real Google call, HTTP 200 ~6.082 s, synthetic H1 only; no quality pass); LG-207 **PASS_WITH_LIMITATIONS** (Tasks browser). Original LG-238 checks: 123 backend / 35 source / 353 frontend / mypy 172. No Google product call, model call, deployment, or Cloud resource was made by this integration.

## 5. Root dirty work protection

- Private backup before any change: `/home/yhvh/tmp/lgmerge-20261018/dirty-backup` (dir `0700`, files `0600`): `tracked-dirty.patch`, `untracked-content.tar.gz`, status/name/hash manifests, `SHA256SUMS`. Checksums verified. See [root-dirty-protection.txt](evidence/root-dirty-protection.txt).
- Original 14 tracked PM files were hashed, then committed as separate management checkpoint `5a5876f`; reconciled in `c770bce`. A later concurrent PM edit to `BACKLOG.md`/`docs/06-roadmap.md` was preserved as checkpoint `8e4f9d8`. No `git clean`, `git reset --hard`, or temporary loss was used.
- `content/` was investigated: pitch/demo/logo assets, 26 files, no secrets/generated junk found; **left uncommitted** as requested for ambiguous other-team content. Initial and final snapshots are preserved.
- **Concurrent external change observed:** `content/demo/script.md` changed at `22:15:21` (after the 22:11 backup) by another process. The current version was **not overwritten**; both the original and final snapshots/hashes are preserved. See [content-concurrent-change.txt](evidence/content-concurrent-change.txt).
- Remaining root status at delivery: `?? content/` only.

## 6. Secrets and Git-object hygiene

- Read Gitea credentials only through a temporary `GIT_ASKPASS` (`0700` in `/tmp`), never printed and never placed in URL/argv/report. `GIT_TERMINAL_PROMPT=0` used. Temporary askpass directory removed after push.
- Scan since `cd0e8c8`: 102 changed files; 0 suspicious paths (`.env`, secret stores, DB/log/pid, node_modules, dist); 0 exact matches of the four private `.env` values; 0 common key/token/private-key patterns. Result: **PASS_NO_SECRETS_FOUND**. Real Google key is not in the repo; QA report/result are sanitized.
- No GitHub push. No force push. No branch deletion. No push of `--all`/`--mirror`.

## 7. Remaining limits / not done

- **Not deployed**, no service restart; 8123/5173 remain 1.20.0. Do not treat the repository 1.22.0 as online.
- No new Google call; LG-239's single call and limitations remain the only real-provider evidence. Recognition quality is still not a PASS gate.
- No full 123/35/353/mypy re-run because the product tree is identical; those results belong to LG-238/LG-239 evidence.
- Root-only ignored PM files (`docs/13`–`docs/15`, many new `backlog/tasks/*.md`, most `probes/**`) are not force-added; links from committed docs to those paths resolve in the root workspace but not in a clean clone. This is the repository's existing public/internal boundary, not a code regression. External `../olav-os`/`../olav-tasks` references are developer-machine references by design.
- The old Reader quality **FAILED**, H2 literal `thought`, name errors, and all historical limits remain unchanged.
- `LG-246` priority format was not touched.

## 8. Gitea links

Repository: <http://192.168.8.50:3000/admin/lightgravity-bot>

- Integrated `main`: <http://192.168.8.50:3000/admin/lightgravity-bot/src/branch/main>
- Integration code commit: <http://192.168.8.50:3000/admin/lightgravity-bot/commit/93e682c0ce5e9b5549b86052513085949641b839>
- Candidate branch: <http://192.168.8.50:3000/admin/lightgravity-bot/src/branch/integration/google-native-asr-20261018>
- Branch inventory: <http://192.168.8.50:3000/admin/lightgravity-bot/src/branch/main/probes/merge-gitea-20261018/BRANCHES.md>
- This report: <http://192.168.8.50:3000/admin/lightgravity-bot/src/branch/main/probes/merge-gitea-20261018/DELIVERY.md>
- LG-239 independent QA: <http://192.168.8.50:3000/admin/lightgravity-bot/src/branch/main/probes/google-native-asr-20261018/lg239/QA.md>

## 9. Handoff

The main agent can close the integration task using this report. The repository `main` is the actual merge result; the public service is intentionally unchanged at 1.20.0. Deployment, restart, release, or further product action still require separate explicit authorization.
