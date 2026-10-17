# LG-109 backend → LG-110/LG-111 interface notes

Status: backend candidate on `feat/provider-backend-20261017`; contract constant
`1.17.0`. Root PM owns normative Markdown. No real vendor request or real key was
used.

1. **Draft result identity field.** The draft endpoint returns the existing
   `ConnectionTestResult` shape plus `draft: true`. The existing field is
   `connection_id` (not `connection_ref`), and it is `null` for an unsaved draft
   (same for `connection_revision`). A draft that reuses an existing saved id
   returns that id/revision after checking `expected_revision`.
2. **Missing/stale edit revision.** `existing_connection_id` without
   `expected_revision` is a sanitized `422 config_invalid` with diagnostic code
   `expected_revision_missing`; a stale value is the existing `409
   revision_conflict`.
3. **Changed credential recipient.** A draft edit that changes backend, auth
   mode or (for OpenAI-compatible) endpoint origin must include a fresh
   `credential_value`; otherwise it is a `422` with diagnostic
   `credential_recipient_changed`. The old key is never sent to the new target.
   The saved PATCH path also detaches an old `credential_ref` when the recipient
   identity changes and no replacement key is supplied. The secret file is not
   deleted, but the connection no longer references it. This is a deliberate
   safety decision; it is stricter than the earlier UI note that said the old ref
   was preserved verbatim.
4. **Provider capability fields.** `capabilities` is always present on the
   connection list/detail/create/update response (and resolved defaults) with
   `configurable`/`testable`/`executable`/`vendor_verified`; values may be
   `null` for an unknown legacy backend. Gemini/Vertex/LiteRT are configurable
   and testable but `executable=false`; only `openai-compat` is executable and
   default-eligible.
5. **Layer names stay stable.** No new layer names were added; the six existing
   names remain. `config_parse` now also proves static SDK config construction.
   Gemini/Vertex network results use `runtime_network`; LiteRT reports static
   package/file/config and never installs, downloads or infers.
6. **LiteRT paths.** `model_path` must resolve inside the configured workspace
   root (the existing Store path policy). Compiler save/test paths use the same
   restriction; no arbitrary extra model-root API was added.
7. **Native test seam.** `native_base_url`/`native_runner` are internal
   `ConnectionTester` test seams only. The Settings HTTP envelope does not accept
   an endpoint override for Gemini/Vertex, and the production tester does not
   set one. A loopback override requires an explicit constructor opt-in.

