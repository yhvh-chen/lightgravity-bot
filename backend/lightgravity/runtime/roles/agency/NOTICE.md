# agency-agents role library

This package distributes the complete role library from
[https://github.com/msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) at pinned commit
`652b2692f8d8ec2b1f1a38e559073e287dfdc469`.

- License: MIT
- Copyright: Copyright (c) 2025 AgentLand Contributors
- Upstream role files are preserved under `upstream/`. All remain byte-for-byte
  originals except `security/security-senior-secops.md`: three illustrative
  private-key headers use explicit non-key placeholders so the unmodified
  release secret scanner can inspect the entire package. No key body was present.
  Its `agency_source.sha256` and `blob_sha` retain original upstream identity;
  `packaged_sha256` and `packaged_blob_sha` identify the locally adapted bytes.
  The adapted native template uses the same placeholders. Source commit,
  repository, path, copyright and MIT license are retained.
- Adapted native Agent templates are under `templates/`; `MANIFEST.json` records
  each upstream path, git blob SHA-1, source SHA-256, adapted body SHA-256,
  capability metadata and license.
- No upstream installation script or runtime clone is used. Role text grants no
  tool, MCP, web, credential, budget, or execution permission.

## Enumeration rule

A role file is a `*.md` file found recursively under one of the division
directories listed in upstream `divisions.json` (academic, design, engineering, finance, game-development, gis, healthcare, marketing, paid-media, product, project-management, research, sales, security, spatial-computing, specialized, support, testing).
All other Markdown is non-role documentation/conversion output and is excluded;
the complete exclusion list and reasons are in `MANIFEST.json`.

## Capability adaptation

Capabilities use the controlled vocabulary `research|design|implementation|verification|writing|review`.
The reproducible classifier uses the division, filename slug and upstream
`name` (not prose descriptions). Review/verification take precedence, then
design/writing/implementation keywords, then a division default. `research`
is recorded as a limitation and is not executable because this version has no
web tool. Tool refs are limited to the existing bounded file tools; role text
never adds a tool.
