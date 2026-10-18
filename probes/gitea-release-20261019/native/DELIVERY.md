# LG270 release scanner blocker — native repair

Base f6f8094d31e775b55949986d560ee57382c0bbe0, verified against root main and the release worktree. Isolated worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg270-release-secret-example-20261019. Branch fix/lg270-release-secret-example-20261019. Local repair only; pi owns serial integration, rebuild and authorized Gitea publication.

## Safe diagnosis

The unchanged release scanner matched the private-key-header signature in exactly two packaged role documents:

- backend/lightgravity/runtime/roles/agency/templates/security-senior-secops.md, three illustrative header lines.
- backend/lightgravity/runtime/roles/agency/upstream/security/security-senior-secops.md, the same three illustrative header lines.

These occur in a defensive secret-pattern examples list, not a supplied credential. The packaged upstream bytes exactly matched both the original SHA-256 and Git blob ID recorded for public agency-agents commit 652b2692f8d8ec2b1f1a38e559073e287dfdc469, security/security-senior-secops.md. There was no private-key body and no corresponding END marker. Conclusion: document-pattern false positive, with no evidence of an actual private key in these hits. No credential validation, environment readout or external permission change was performed; matched raw strings are deliberately absent from this report.

The preserved root/probes/gitea-release-20261019/logs/packager-temporary-override.diff changes the canonical scanner's two grep lines by adding exclusion arguments. This reduces scan coverage; artifacts built through that override do not demonstrate the original gate passed and must not be used as the accepted publication artifacts. The temporary script had already disappeared from the pi worktree by follow-up inspection; the diff remains the audit evidence. This repair neither used nor changed that override.

## Minimal repair and provenance

Only those three literal header examples in each document now use explicit non-key placeholders. The template body hash and manifest template hash are updated. Original agency_source repository, source commit, path, SHA-256, Git blob ID, copyright and MIT license are retained. Additional packaged_sha256/packaged_blob_sha identify the locally adapted source bytes, with a local_adaptation explanation. NOTICE explicitly documents the one upstream file that is locally sanitized; other upstream files remain byte-for-byte originals. The existing provenance check now validates packaged bytes against packaged hashes when present, retaining the original source identity assertions for this role. No runtime code, capability classification, scanner, build script, license or product behavior changed.

## Necessary checks

- Canonical release secret expression extracted unchanged from scripts/build-release.sh and applied with grep to its source distribution allowlist: 900 files inspected, zero matched paths, grep exit 1 (expected no matches). This is a source allowlist scan, not a claim about a newly rebuilt archive or generated frontend assets.
- Three focused existing role checks: manifest enumeration; every template provenance/capability/safe tools; packaged upstream integrity and license. 3 passed in 10.95s, temporary fixtures only, no model/network/browser.
- git diff --check passed. scripts/build-release.sh remains byte-for-byte unchanged from HEAD.
- No full suite, frontend rebuild or new archive build by native: pi must integrate this commit and rebuild with the original canonical release script, retain the prior failed/override evidence, then scan/verify the actual rebuilt artifacts before upload.

No actual secret was found in the two reported hits; this check does not establish an unrestricted historical credential audit. No user data, instance configuration, external credentials, protected service, root main, release worktree, remote push, upload, tag, deploy or restart was modified by native. LG269 and other bugs are untouched.
