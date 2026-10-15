# Browser loopback-HTTP diagnostics (LG-013 / LG-021 / LG-027 support)

Scope: evidence only. This directory does not change product code, task state,
contracts or dependencies. It exists to establish *why* Chrome headless fails
to load loopback HTTP while `file://` renders, for real-browser acceptance.

## Verdict (root cause)

Chrome 151.0.7922.71 headless on this host **parks every renderer-initiated
loopback-HTTP request after `URL_REQUEST_START_JOB` and never advances it to
the HTTP-stream layer**. This is not a server problem, not a DNS problem, not
an environment/namespace/proxy problem, and not specific to `Page.navigate`:

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

- Do **not** attribute loopback-HTTP hangs to the product, to the app, or to a
  generic "sandbox". The HTTP load itself never completes inside this Chrome.
- `file://` rendering is reliable here and is what `frontend/tests/browser/`
  `shell-check.mjs` already uses; `Target.createTarget` does **not** rescue
  loopback HTTP (the target stays on `about:blank`).
- If a real-browser loopback test is required, it must run under a Chrome build
  or configuration where renderer loopback HTTP is not gated (e.g. a different
  channel/binary, or a headed session on a working display). Record the exact
  binary + version + launch flags as the working scheme.

## Files

- `marker_server.py` — dependency-free loopback HTTP marker server; logs every
  request with a monotonic timestamp; self-terminates on `--lifetime`.
- `chrome_probe.mjs` — bounded CDP probe comparing `Page.navigate` vs
  `Target.createTarget`, reads the DOM marker, always bounds each CDP call.
- `evidence/` — captured run outputs and the netlog excerpt.

## Reproduce (bounded)

```sh
cd probes/browser-diagnostics
python3 marker_server.py --port 0 --ready-file /tmp/lgprobe_ready.json --lifetime 60 &
PORT=$(python3 -c "import json;print(json.load(open('/tmp/lgprobe_ready.json'))['port'])")
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$PORT/marker"   # -> 200
timeout 25 node chrome_probe.mjs "http://127.0.0.1:$PORT/marker" http --strategy both
# server log will show the curl request and NO Chrome request
```
