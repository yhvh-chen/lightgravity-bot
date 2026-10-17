# LG-110 modal → backend interface notes

These are interface gaps observed while implementing the frozen
[MODAL-CONTRACT](MODAL-CONTRACT.md). They are reported for PM relay; this
frontend candidate does not change the contract or invent policy.

## 1. Persisted list test status is not defined on `ConnectionView`

The UX requires the saved list to show the true persisted recent test status.
The frozen draft-test section defines the `TestResult`, but the current
Connection view contract has no field carrying the latest **persisted** safe test
summary. The frontend therefore reads an optional additive field:

```ts
last_test?: {
  test_id?: string
  overall: string                 // verified | partial | failed | not_run …
  finished_at: string
  connection_revision?: number | null
  credential_version?: string | null
} | null
```

If absent/null, the list shows “Not tested” rather than fabricating status. It
marks a summary stale when its saved revision/credential version differs from the
current Connection. Draft-test results are never inserted into this field by the
frontend.

Backend request: expose the latest persisted safe test summary on list/detail
responses (or provide an equivalent read endpoint) without secrets or draft
diagnostics. Please confirm the exact field name before LG-111 integration.

## 2. Connection deletion route is not frozen

The UX requires row Delete with honest server reference/default blocking, but the
contract text does not define a Connection deletion endpoint. The frontend calls:

```http
DELETE /api/v1/settings/connections/{id}
Content-Type: application/json

{"expected_revision": 3}
```

and expects either success or the existing error envelope. A referenced/default
Connection must return a real conflict/reference error; the row stays visible.
The frontend also pre-blocks known `references.default_roles`/`agent_refs`
without sending the request.

Backend request: confirm/implement this route (or provide the intended equivalent)
with server-side reference/default protection and no silent dangling references.
Until then, a missing route is surfaced honestly as a request failure and no row
is removed.

## 3. No other contract change requested

The draft-test request/response shape, admin/token protection, no-save/no-store
semantics, write-only credential, optional provider fields, revision conflict and
capability separation are used as frozen. Native Task execution and custom-host
allowlisting are not expanded by this frontend work.
