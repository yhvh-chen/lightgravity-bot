# Browser loopback-HTTP diagnostics (LG-013 / LG-021 / LG-027 support)

Scope: evidence only. This directory does not change product code, task state,
contracts or dependencies. It exists to establish *why* Chrome headless fails
to load loopback HTTP while `file://` renders, for real-browser acceptance.

## Correction (2025-10-15): real loopback HTTP **works**

The earlier verdict below (commit 8d27007) generalised "loopback HTTP is
parked" from two paths that are individually broken for unrelated reasons. A
third path shows real loopback HTTP working end-to-end on this host:

| path | result |
|---|---|
| `Page.navigate` to `http://127.0.0.1:PORT/marker` | hangs; server logs **no** GET; frame script context wedges |
| `fetch()` from a `data:` shell (opaque origin) | `Failed to fetch` — CORS rejection *after* the response, not a network block |
| `fetch()` from a `file://` shell | **works** — server logs `GET /marker` + `RESP 200`, page sees `MARKER-OK` |
| `fetch()` from `about:blank` | **works** — server logs `GET /marker` + `RESP 200` |

Verified on **both** an isolated Chrome for Testing 150.0.7871.124 and the
system Google Chrome 151.0.7922.71:

```
path=fetch browser=Chrome/150.0.7871.124 ok=true result="ok:200:MARKER-OK"
path=fetch browser=Chrome/151.0.7922.71  ok=true result="ok:200:MARKER-OK"
server: t=1.669 REQ GET /marker ... ; t=1.669 RESP 200
```

So the system 151 binary was **not** the problem: the prior probe only tested
`Page.navigate` (which does hang) and `data:`-origin `fetch` (which is
tripped by CORS). Neither implies "renderer loopback HTTP is blocked".

**Use for acceptance:** load a `file://` shell page and `fetch()` the loopback
API from it. Do **not** use main-frame `Page.navigate` to `http://` and do
**not** use a `data:` origin shell.

See `evidence/loopback-http-working-path.txt`.

## Original verdict (8d27007) — superseded

Chrome 151.0.7922.71 headless on this host **parks main-frame `Page.navigate`
to loopback HTTP after `URL_REQUEST_START_JOB` and never advances it to the
HTTP-stream layer.** This is not a server problem, not a DNS problem, not an
environment/namespace/proxy problem — but it is also **not** a general
renderer→HTTP block: subresource `fetch()` from a `file://`/`about:blank`
page reaches the server normally (see Correction above).

- `curl` to the same URL: HTTP 200 in <1 ms (see server log below).
- `Page.navigate` to `file://…` and `data:…`: returns in 5 ms, DOM renders,
  `Page.loadEventFired` fires.
- `Page.navigate` / `Target.createTarget(url)` to `http://127.0.0.1:PORT/...`:
  the CDP call never returns (bounded probe reports TIMEOUT at 8 s).
- A `file://` page that does `fetch("http://127.0.0.1:PORT/…")`: the promise
  stays `"pending"` forever; the server never logs the request.
- The marker server logs **zero** requests from Chrome in every run.

So the failure is a renderer→network-service HTTP gate that never resolves in
this headless build/config, not "the sandbox blocks loopback".

## Evidence: netlog lifecycle of the main-frame request

`--log-net-log` (Everything) for the main-frame `URL_REQUEST` (`source id 117`)
shows this sequence and then nothing:

```
REQUEST_ALIVE
CHECK_CORS_PREFLIGHT_REQUIRED (preflight_required:false)
NETWORK_DELEGATE_BEFORE_URL_REQUEST  (phase 1 + 2)
TRANSPORT_SECURITY_STATE_SHOULD_UPGRADE_TO_SSL (should_upgrade_to_ssl:false)
URL_REQUEST_START_JOB  (url http://127.0.0.1:36015/marker)
FIRST_PARTY_SETS_METADATA
COMPUTED_PRIVACY_MODE (privacy_mode:disabled)
<-- no HTTP_STREAM_REQUEST, no HTTP_STREAM_JOB, no socket connect,
    no HTTP_TRANSACTION_SEND_REQUEST, no response, no error -->
```

In the same trace a *speculative preconnect* (`PRECONNECT`, source id 111/120)
to `http://127.0.0.1:36015/` **does** open a TCP socket
(`local_address 127.0.0.1:48122 -> remote_address 127.0.0.1:36015`) but never
sends or receives bytes, and a background non-loopback request
(`clientservices.googleapis.com`) completes its full HTTP/2 lifecycle
normally. The netlog constants include `LOCAL_NETWORK_ACCESS_CHECK`,
`URL_REQUEST_DELEGATE_PLATFORM_LOCAL_NETWORK_ACCESS_PERMISSION_REQUIRED`,
`ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS` (Chrome 151 Local Network
Access family), consistent with the request being held at the network
delegate / LNA permission gate.

## Launch combinations actually tried (all hang)

1. `--headless=new --no-sandbox --disable-gpu --no-proxy-server
   --disable-extensions` (baseline).
2. Baseline + `--disable-features=LocalNetworkAccessChecks,
   PrivateNetworkAccessChecks,LocalNetworkAccessPermissionPrompt`.
3. Baseline + `--disable-features=LocalNetworkAccessChecks,
   LocalNetworkAccessForNavigations,LocalNetworkAccessForNavigationsWarningOnly,
   LocalNetworkAccessRestrictionsTemporaryOptOut,
   LocalNetworkAccessNonSecureContextAllowed`.
4. Baseline + `--disable-features=NetworkServiceSandbox`.
5. CDP `Browser.grantPermissions {localNetworkAccess}` and
   `Browser.setPermission {local-network-access, granted}` before navigation.

Also checked: no HTTP proxy env vars, no machine policy dir, no X server
(`DISPLAY=:1024/:1025` are stale sockets), no global puppeteer browser
download. System Chrome is the only available binary.

## Environment facts

- Chrome: `Google Chrome 151.0.7922.71` (`/usr/bin/google-chrome`).
- Host: `Linux yhvh-nas 7.0.0-28-generic`, net namespace `net:[4026531833]`,
  no `CAP_NET_*`, no proxy environment variables.
- DevTools port + `/json/version` + WebSocket + `Target.*` + `Runtime.evaluate`
  all succeed in tens of ms; only HTTP network loads are parked.

## Practical guidance for QA

- Real-browser loopback acceptance **is possible on this host with the system
  binary**. Use `loopback_smoke.mjs --path fetch`: a `file://` shell page that
  `fetch()`es the marker, then poll the side-effect flag. Both server-side
  (request log) and browser-side (marker body) facts are checked.
- Do **not** attribute `Page.navigate`-to-loopback hangs to the product, to the
  app, or to a generic "sandbox"; they are a browser main-frame-navigation
  behaviour here. They are also **not** what `frontend/tests/browser/`
  `shell-check.mjs` does (`file://` rendering, `Target.createTarget`).
- An isolated Chrome for Testing build is available under
  `~/.cache/lightgravity-bot/browsers/` (see `evidence/browser-binary.txt`) if a
  pinned, non-system binary is wanted for QA. It behaves the same as 151 for
  the paths above. Pass it with `--chrome` / `CHROME_BIN`; nothing hardcodes it.

## Real HTTP acceptance helper for LG-013 / LG-021 / LG-027

`http_probe_server.py` + `http_channel_smoke.mjs` +
`run_http_channel_smoke.sh` provide an executable acceptance path with a **real**
HTTP server (real HTML page, real JSON API, **real SSE stream**) and a **real**
browser. It deliberately does **not** mock the API/SSE and does **not** disable
web security.

```sh
cd probes/browser-diagnostics
./run_http_channel_smoke.sh --mode all --deadline-ms 9000
# pick the isolated binary with:  --chrome ~/.cache/lightgravity-bot/browsers/150.0.7871.124/chrome-linux64/chrome
```

Three modes, each hard-bounded and each printing two independent facts (server
request log and browser-side state):

- `doc-int` — **attempts exactly the requested technique**: CDP `Fetch.enable`
  with `resourceType:'Document'` and `Page.navigate` to the real http origin,
  fulfilling any Document pause from a Node GET. On this host it records
  `fetch_paused_for_document=false`: **the Document request never reaches the
  Fetch stage**, so no http `frame.location.origin` can be produced this way.
  See `evidence/document-interception-limitation.txt` for the full matrix.
- `channel` — **the working transport**: a `file://` shell page really
  `fetch()`es `/api/echo` and really opens an `EventSource` on `/sse`. The
  server log shows the browser's GETs (Chrome UA) and the SSE ticks; the page
  reports `ok:200:{...}` and `[1,2,3]`. This is a genuine browser↔server HTTP +
  streaming round trip.
- `bridge` — proves the **transparent-proxy transport** for a subresource:
  Node performs the real GET and `Fetch.fulfillRequest` delivers the real
  status/headers/body to the XHR. The server log distinguishes bridged requests
  (`ua='node'`) from native browser requests (`ua='Mozilla/…'`).

Observed run (system Chrome 151 and CFT 150 both): `doc-int
fetch_paused_for_document=false`; `channel ok=true` (`api="ok:200:…"`,
`sse=[1,2,3]`); `bridge ok=true`. See
`evidence/http-acceptance-run.txt`, `evidence/http-acceptance-run.json` and
`evidence/http-acceptance-server-log.txt`.

### Accurate limitation (do not over-claim)

The `channel`/`bridge` runs are real HTTP, but the **document origin is
`null`/`file://`, not `http://`**. The main-frame http navigation cannot be
bridged here because it never reaches CDP `Fetch` (parked earlier at the
network delegate). So this helper does **not** cover anything that requires a
same-origin http document (`location.origin === http://127.0.0.1:PORT`,
`document.cookie` at that origin, page↔API same-origin policy). Those must not
be reported as passing from this evidence.

## Files

- `http_probe_server.py` — real loopback HTTP server: `/page` (real HTML),
  `/api/echo` (real JSON), `/sse` (real event stream, N events + `done`),
  `/health`, `/marker`; logs method/path/peer/`Origin`/`User-Agent`; `--cors`
  only decides the `Access-Control-Allow-Origin` response header.
- `http_channel_smoke.mjs` — bounded real-browser HTTP acceptance
  (`--mode all|doc-int|channel|bridge`); per-call deadlines; own process-group
  cleanup; binary via `--chrome`/`CHROME_BIN`.
- `run_http_channel_smoke.sh` — one-command runner; starts the probe server,
  runs the smoke, prints the server log, cleans up only its own server group.
- `marker_server.py` — dependency-free loopback HTTP marker server; logs every
  request with a monotonic timestamp; `--cors` adds `Access-Control-Allow-Origin: *`
  so a `file://`/`about:blank` shell can read the marker; self-terminates on
  `--lifetime`.
- `loopback_smoke.mjs` — bounded, binary-configurable smoke proving real
  loopback HTTP. `--path fetch` (recommended) or `--path nav` (characterises the
  main-frame hang). Event-driven, per-call bounded, own process-group cleanup.
- `chrome_probe.mjs` — earlier bounded CDP probe comparing `Page.navigate` vs
  `Target.createTarget`; kept for the historical netlog repro.
- `evidence/` — captured run outputs, the netlog excerpt, the working-path
  proof, and the Document-interception limitation matrix.

## Reproduce (bounded)

Recommended working path (two independent facts: server log + DOM/body):

```sh
cd probes/browser-diagnostics
python3 marker_server.py --port 0 --ready-file /tmp/lgprobe_ready.json \
  --lifetime 60 --cors > /tmp/lgprobe_srv.log 2>&1 & SRV=$!
PORT=$(python3 -c "import json;print(json.load(open('/tmp/lgprobe_ready.json'))['port'])")
# real browser loopback HTTP via a file:// shell + fetch()
node loopback_smoke.mjs --url "http://127.0.0.1:$PORT/marker" --path fetch
# optional: an isolated pinned binary
#   --chrome ~/.cache/lightgravity-bot/browsers/150.0.7871.124/chrome-linux64/chrome
cat /tmp/lgprobe_srv.log   # must show GET /marker + RESP 200 from Chrome's UA
kill -- -$SRV               # clean up only the server we started (its own group)
```

Historical main-frame repro (expected to hang; no server GET):

```sh
node loopback_smoke.mjs --url "http://127.0.0.1:$PORT/marker" --path nav
# or the older: timeout 25 node chrome_probe.mjs "http://127.0.0.1:$PORT/marker" http --strategy both
```
