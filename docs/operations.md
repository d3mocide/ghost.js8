# Operations

## Deploy

```sh
cp .env.example .env        # set GHOSTJS8_ALLOWED_ORIGINS, optionally a boot receiver
make images                 # or: docker compose build   (EXTRA_CA=... behind a TLS proxy)
make up                     # docker compose up -d
```

Only the `web` container publishes a port (default `127.0.0.1:8080`). Point
your reverse proxy at it; it terminates TLS and handles authentication.

### Published images and ARM

Tagged releases publish multi-arch images (`linux/amd64` and `linux/arm64`) to
GHCR. ARM means a Raspberry Pi 4/5 on a **64-bit** OS, Apple Silicon or ARM
cloud servers; there is no 32-bit ARM build of JS8Call. To run them instead
of building:

```sh
# in .env
GHOSTJS8_IMAGE_PREFIX=ghcr.io/d3mocide/ghostjs8
GHOSTJS8_TAG=0.1.0
```

```sh
docker compose pull && docker compose up -d --no-build
```

Building locally on an ARM host works too (`make images`); the decoder picks
the matching JS8Call build automatically.

### Receivers on your LAN

By default, a receiver chosen in the UI (or picked by the GhostNet autopilot)
must resolve to a **public** address. The bridge resolves the name, checks
every address, and connects to the checked address, so tricks like `127.1`,
names that point inside your network, or DNS rebinding are refused. To use
your own LAN KiwiSDR, either:

- set it as the boot receiver (`GHOSTJS8_RECEIVER_HOST`), which is trusted as
  configured, or
- set `GHOSTJS8_ALLOW_PRIVATE_RECEIVERS=true` to allow private and CGNAT
  (e.g. tailnet) addresses from the UI.

Loopback, link-local and cloud-metadata addresses are always refused.

### Hardening

All containers run as non-root, with `cap_drop: [ALL]` and
`no-new-privileges`. The decoder sits on an internal network with no egress.
The browser WebSocket accepts same-origin pages only unless
`GHOSTJS8_ALLOWED_ORIGINS` lists others. Connection attempts to receivers are
spaced at least 5 s apart, whoever triggers them.

### Reverse proxy

The bridge WebSocket lives at `/ws` on the same origin. Your proxy must pass
WebSocket upgrades and allow long-lived connections.

**Caddy**

```caddy
ghost.example.net {
    basic_auth {
        operator $2a$14$...   # caddy hash-password
    }
    reverse_proxy 127.0.0.1:8080
}
```

Caddy proxies WebSockets automatically.

**Nginx Proxy Manager:** add a proxy host to `http://<docker-host>:8080`, enable
*Websockets Support*, add an Access List for authentication, and in *Advanced*
set `proxy_read_timeout 3600s;`.

Set `GHOSTJS8_ALLOWED_ORIGINS=https://ghost.example.net` so other sites cannot
open the WebSocket from a visitor's browser.

### Multiple receivers

JS8Call takes one audio input per instance, so one decoder container decodes
one receiver at a time. In this release a bridge drives exactly one station
(one receiver + one decoder). To decode several receivers at once, run several
compose projects (`docker compose -p ghostjs8-40m ...`, each with its own
`.env` and port). An in-bridge pool of decoder slots is a planned follow-up
(see `architecture.md`).

### GhostNet autopilot

To monitor and record the GhostNet JS8 windows unattended, set
`GHOSTJS8_GHOSTNET=on`, `GHOSTJS8_GHOSTNET_REGION` and `GHOSTJS8_HOME_GRID`. See
[`ghostnet.md`](ghostnet.md). Recordings go to the `bridge-data` volume
(`/data/nets`) and are pruned after `GHOSTJS8_NET_RETENTION_DAYS`. Budget about
50 MB per recorded hour with audio on. A viewer who tunes or switches receivers
pauses the autopilot until the window ends.

## Health

`GET /readyz` returns the same health document the UI shows (200 only when
`overall = listening`, otherwise 503 with the reason). Every component carries
`state`, `since` (last state change), `last_seen` (last positive evidence) and
`detail`.

| Component | OK means | Goes DOWN when |
|---|---|---|
| bridge | the bridge is serving | (it is the thing answering) |
| decoder_process | agent reachable and JS8Call RUNNING under supervision | agent link lost, no agent report for 10 s, or JS8Call not running |
| decoder_api | JS8Call's UDP API heard within 40 s (PING every 15 s, or a request round trip) | no heartbeat for 40 s |
| decoder_capture | JS8Call holds an uncorked capture stream on `ghost_rx_in` | JS8Call stopped capturing its input |
| receiver | KiwiSDR session connected and audio flowing | rejected, failed, backing off, or idle |
| audio | receiver audio arrived within 3 s | stale > 3 s while connected |
| waterfall | waterfall rows arrived within 5 s | stale > 5 s while connected |
| last decode | time of the last real decode | never inferred; `null` until something is decoded |

Container level: the decoder's Docker `HEALTHCHECK` fails unless Xvfb,
PulseAudio, the agent and JS8Call are RUNNING **and** JS8Call is capturing. A
critical process that crash-loops goes FATAL and the container exits with code
70; `restart: unless-stopped` brings it back.

## What the headline means

| Headline | Meaning | What to do |
|---|---|---|
| LISTENING — TRAFFIC COPIED | everything healthy, decodes in the last 5 min | nothing |
| NO TRAFFIC — BAND QUIET | healthy, nothing decoded recently | normal. Propagation, time of day, or no activity. Try another band or receiver if you expected traffic |
| RECEIVER FULL / RECEIVER BUSY | the KiwiSDR refused: all slots taken, or temporarily unavailable | wait (retried no sooner than 60 s) or switch receiver |
| PASSWORD REQUIRED / RECEIVER REFUSED | auth or redirect | not retried; pick again with a password or another receiver |
| UNSUPPORTED RECEIVER AUDIO | receiver sends compressed, stereo/IQ or non-12 kHz audio | switch receiver (e.g. wideband 20.25 kHz Kiwis are not supported) |
| ADC OVERLOAD AT RECEIVER | the remote receiver's input is overloaded | switch receiver. Volume does not help, and ghost.js8 never changes shared hardware settings (attenuation) on someone else's Kiwi |
| AUDIO STALE | connected but no audio | usually network trouble; it will reconnect |
| DECODER OFFLINE / DEGRADED | JS8Call not running or not capturing | wait for the supervisor restart; check `docker compose logs decoder` |

## Troubleshooting

- **Decodes never appear, health all OK:** check the host clock. JS8 decoding
  needs UTC within about a second; run NTP/chrony on the Docker host. Also
  confirm the passband covers the signals (default 100–3000 Hz USB) and the
  dial is on a JS8 frequency.
- **`decoder_capture` DOWN:** `docker compose exec decoder pactl list short source-outputs`
  should show JS8Call on `ghost_rx_in`. See `decoder-container.md`.
- **Receiver keeps rejecting:** public receivers fill up, especially in the
  evening. The directory panel hides full receivers by default.
- **Logs:** structured JSON, one object per line, with `session` ids:
  `docker compose logs -f bridge | jq -r '[.ts,.level,.logger,.msg]|@tsv'`.
- **Behind a TLS-intercepting proxy at build time:** `EXTRA_CA=/path/bundle.crt make images`.

## Etiquette

Public KiwiSDRs are shared by their owners. ghost.js8 identifies itself as
`ghost.js8`, uses one connection per station no matter how many browsers
watch, backs off politely (5 s → 5 min, jittered; ≥ 60 s when full), never
retries auth failures automatically, and only changes per-channel settings.
Set `GHOSTJS8_IDLE_DISCONNECT_MINUTES` if you do not need persistent listening.

## Manual validation checklist (real receiver)

Synthetic waterfall rows and the fake agent only test transport and
rendering. Before a release, check against a real public KiwiSDR:

1. Pick a receiver covering 40 m or 20 m during an active period; tune 7.078 or 14.078 MHz USB.
2. Waterfall shows the 0–3 kHz JS8 segment with recognizable 50 Hz-wide JS8
   signals stacking on 15 s boundaries; the passband markers sit at 100/3000 Hz.
3. Audio monitor plays clean SSB audio with no growing delay. Buffer stays
   around 250 ms and "dropped" stays low.
4. Within a few cycles, decodes appear with plausible SNR (−24…+10) and offsets
   matching the visible signals.
5. Directed messages are marked DIR; heard stations fill in; stations that sent
   grids appear on the map at plausible locations.
6. Health shows every component ONLINE with fresh evidence ages.
7. Retune to another band: the waterfall and passband follow, and other open
   browsers see the change.
8. Switch receivers: old session closes, new one connects, no duplicate
   connections remain on the old receiver (check its user list).
9. `docker compose restart decoder`: health shows DECODER OFFLINE within
   about 10 s, then recovers, and decoding resumes without touching the bridge.
10. Leave the page: the "N watching" count in the Receiver panel of another
    browser drops, and audio stops.
11. If you find a receiver that reports ADC overload, the UI shows the overload
    banner and offers switching, and nothing on the receiver changes.

## Extension point: transmit

ghost.js8 is receive-only by design and a KiwiSDR cannot transmit. A future
radio interface must be a separate component with its own adapter, its own
authorization model, and explicit operator licensing checks. It must not be
added to the bridge ↔ browser protocol of this project: there is deliberately
no transmit message, and the browser tests assert no transmit control exists.
