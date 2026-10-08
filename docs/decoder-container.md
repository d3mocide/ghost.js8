# Decoder container

`decoder/Dockerfile` (build context: repository root) builds the image that runs the **native JS8Call** decoder headless.
One container = one decoder slot = one receiver being decoded.

## Pins

| What | Pin | Where |
|---|---|---|
| Base | `ubuntu:24.04@sha256:534baea6…eb55` | `decoder/Dockerfile` `UBUNTU_IMAGE` |
| JS8Call | `3.0.3`, `JS8Call-v3.0.3-x86_64.AppImage` | `JS8CALL_VERSION` |
| JS8Call SHA-256 | `3f89bd821f281c59a9384c08a3ad783ea3b9ac6abf319ce6c0d881c2ecc6e6cd` | `JS8CALL_SHA256` — build fails on mismatch |
| apt packages | Ubuntu archive at build time (GPG-signed); not version-pinned | see `SECURITY-UPDATES.md` |

The SHA-256 was recorded on first download (2026-10-08). Upstream publishes no
detached signature for this release; their release workflow produces a GitHub
build attestation, which can be checked with
`gh attestation verify JS8Call-v3.0.3-x86_64.AppImage --repo JS8Call-improved/js8call-improved`.
The v3.0.3 tag is commit `4c592bd9…`, the same commit the acceptance-test
fixture is pinned to.

Ubuntu 24.04 is required: the 3.x AppImage fails on 22.04. Docker has no FUSE,
so the AppImage is extracted at build time (`--appimage-extract`) in a throwaway
stage. The extracted tree bundles Qt 6 and the PulseAudio client; the runtime
stage adds only what `ldd` showed missing (GL/EGL, X11/xcb, fontconfig,
freetype, harfbuzz, libusb).

### Building behind a TLS-intercepting proxy

```sh
docker build --secret id=extra_ca,src=/path/to/full-ca-bundle.crt -f decoder/Dockerfile -t ghostjs8-decoder .
```

The secret is used only by the download step in the `fetch` stage and never lands
in the image. Integrity comes from the SHA-256 check, not TLS.

## Processes

`tini` → `ghost-supervise` → `supervisord`:

| Program | Role |
|---|---|
| `xvfb` | virtual display `:99` (Qt xcb platform) |
| `pulseaudio` | user-mode daemon, graph from `/etc/ghostjs8/pulse.pa` |
| `js8call` | `ghost-start-js8call`: renders `JS8Call.ini`, waits for X + Pulse, execs `/opt/js8call/usr/bin/JS8Call` (not `AppRun`, so the process is named `JS8Call`) |
| `agent` | decoder-agent (`/opt/agent`, a uv-locked venv with only `websockets`): bridge link on `:8074/agent`, PCM → `pacat` → `ghost_rx`, JS8 UDP API owner, health facts |
| `fatal` (event listener) | on any `PROCESS_STATE_FATAL`, writes `/run/ghost/fatal` and stops supervisord |

A program that dies 4 times within its `startsecs` goes FATAL; the container
then exits with **code 70**, so a restart policy treats it as a failure. Nothing
can keep looking healthy with a dead decoder.

## Audio graph

```
decoder-agent ──pcm──▶ ghost_rx (null sink, mono)
                          └─ ghost_rx.monitor ─▶ ghost_rx_in (module-remap-source) ─▶ JS8Call input
JS8Call output ──────▶ ghost_discard (null sink, never monitored)
```

Qt hides PulseAudio monitor sources from its device list, so the monitor is
re-exposed as an ordinary capture source. JS8Call selects devices by
`SoundInId`/`SoundOutId`, which are `QAudioDevice::id()` — the PulseAudio
device **name** — so the names in `pulse.pa` are stable IDs. Keep them in sync
with `JS8Call.ini.tmpl`.

## JS8Call configuration

`/etc/ghostjs8/JS8Call.ini.tmpl` is rendered on **every** start (JS8Call
rewrites the file on exit; we discard that). Environment:

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTJS8_JS8_CALL` | `N0CALL` | placeholder identity; JS8Call blocks on a settings dialog if empty |
| `GHOSTJS8_JS8_GRID` | `AA00` | placeholder grid; same reason |
| `GHOSTJS8_UDP_PORT` | `2242` | JS8Call UDP API target on `127.0.0.1` |
| `GHOSTJS8_FILTER_CENTER` | `1550` | decode filter center, Hz |
| `GHOSTJS8_FILTER_WIDTH` | `2900` | decode filter width, Hz (100–3000 Hz) |

The filter **is** the decode range (`nfa`/`nfb` in `mainwindow.cpp`), so it must
cover the receiver passband. All submodes are decoded (`SubModeMultiDecode`).

Settings forced off because their **defaults are on** and would transmit or
publish under the placeholder call: `PSKReporter`, `SpotToAPRS`,
`CheckForUpdates`, `WriteLogs`; plus `TxBeacon=0`, `TransmitOFF`, `RelayOFF`,
`AutoreplyOnAtStartup=false`, `Rig=None`.

## UDP API (observed on 3.0.3)

JSON datagrams `{"type", "value", "params"}` sent from an ephemeral port to
`127.0.0.1:2242`. Replies go to that source port (learn it from incoming
datagrams).

| Type | Notes |
|---|---|
| `PING` | every 15 s — the decoder-API liveness signal |
| `RX.ACTIVITY` | `value` is the full line, e.g. `K0OG: KN4CRD SNR +02 ` |
| `RX.DIRECTED` | `value` **omits the sender**; `params.FROM` carries it. Text ends with JS8's EOT marker `♢`. Display as `FROM + ": " + value` minus the marker. |
| `RX.SPOT`, `RX.CALL_ACTIVITY` | station / spot info |
| `STATION.STATUS` | ~2 Hz; ignore |
| `CLOSE` | sent on shutdown |

`AcceptUDPRequests=true` lets the agent query JS8Call; the agent sends only an
allowlist of read-only requests (`RX.GET_CALL_ACTIVITY`, `STATION.GET_CALLSIGN`)
and can never construct a `TX.*` request.

**`RX.SPOT` is only emitted when spotting to reporting networks is on**
(`processSpots()` returns early otherwise). We keep spotting off, so the agent
polls `RX.GET_CALL_ACTIVITY` every 15 s; the `RX.CALL_ACTIVITY` reply maps each
heard callsign to `{SNR, GRID, UTC}`. A matching `_ID` in a reply also proves
an API round trip (health: "decoder API responding").

## decoder-agent link

See `bridge/src/ghostjs8/decoders/js8call_native/agent_protocol.py`. The bridge
sends binary PCM (mono s16le 12 kHz); the agent sends JSON `js8` (verbatim
JS8Call messages) and `health` frames every 3 s. Audio queues are bounded at
both ends (~2 s) and drop oldest; queued audio is discarded on reconnect,
because JS8 needs live, time-aligned audio.

## Health

`ghost-healthcheck` (Docker `HEALTHCHECK`) fails unless all critical programs (xvfb, pulseaudio, agent, js8call)
are RUNNING, X answers, the Pulse graph exists, and JS8Call holds an
**uncorked capture stream on `ghost_rx_in`** (matched by
`application.process.binary=JS8Call`).

## Debugging

```sh
docker exec -u root <ctr> sh -c 'apt-get update && apt-get install -y x11-apps netpbm'
docker exec <ctr> sh -c 'xwd -root -silent | xwdtopnm | pnmtopng > /tmp/shot.png'
docker cp <ctr>:/tmp/shot.png .
```

Manual decode smoke test: copy a 12 kHz WAV in, start a UDP listener on
`127.0.0.1:2242`, then `paplay --device=ghost_rx file.wav` on a 15 s UTC boundary.
