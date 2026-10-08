# Architecture

ghost.js8 is a receive-only JS8Call listening post. It pulls audio and waterfall
data from public KiwiSDR web receivers, decodes JS8 with the **native JS8Call
application** running headless in Docker, and presents traffic in a browser.

## Components

Four separable components with explicit interfaces:

| Component | Today | Seam for later |
|---|---|---|
| **Receiver adapter** | KiwiSDR (`SND` + `W/F` WebSockets) | other SDR inputs |
| **Decoder adapter** | native JS8Call via PulseAudio + UDP API, behind an in-container *decoder-agent* | a WASM decoder |
| **Bridge** | session orchestration, health, fan-out to browsers | — |
| **Web UI** | Vite + Svelte 5 + TypeScript | — |

```
                      ┌──────────────────────── decoder container (×N slots) ─────────────────────┐
KiwiSDR ─SND─┐        │ decoder-agent ─pcm→ pulse null sink "ghost_rx"                            │
             ├─bridge─┤                     └ monitor → module-remap-source "ghost_rx_in" → JS8Call│
KiwiSDR ─W/F─┘   │    │ JS8Call ─UDP (localhost)→ decoder-agent        JS8Call out → "ghost_discard"│
                 │    │ supervisor: Xvfb, pulseaudio, js8call, decoder-agent                       │
                 │    └────────────────────────────────────────────────────────────────────────────┘
                 └─ /ws (JSON + binary) ─→ nginx (web) ─→ your reverse proxy ─→ browser
```

## Container topology

- **`decoder`** — one per concurrently decoded receiver (JS8Call is
  one-audio-input-per-instance). Ubuntu 24.04 by digest; Xvfb; user-mode
  PulseAudio; JS8Call AppImage extracted at build time and SHA-256 verified; the
  decoder-agent (Python, from this repo). Supervised; a fatal exit of any
  critical process exits the container so Docker restarts it. Internal network only.
- **`bridge`** — Python 3.12, FastAPI + uvicorn. Outbound Kiwi connections;
  leases decoder slots; serves `/ws`, `/api/*`, `/healthz`, `/readyz`.
  Internal network only.
- **`web`** — `nginxinc/nginx-unprivileged:alpine` by digest. Serves the static
  build and proxies `/ws` + `/api` to the bridge. The only service your reverse
  proxy talks to. TLS terminates at your proxy.
- **Test stack** (`docker-compose.test.yml`) — `fake-kiwi`, `bridge`, `decoder`,
  `acceptance` on an `internal: true` network (no egress).

## Why a decoder-agent

The brief requires JS8Call's UDP API on localhost and PulseAudio fed directly,
but also separate `decoder` and `bridge` services. A small Python agent inside
the decoder container owns both localhost concerns and exposes one internal
WebSocket to the bridge (binary PCM in; JSON decodes + health facts out). This is
also the seam where a WASM decoder adapter would plug in.

## Bridge ↔ browser contract (summary)

Full byte layouts live in [`protocol.md`](protocol.md) (milestone 6).

- JSON text frames: `{ "v": 1, "type": ..., ... }`, a discriminated union generated
  from Pydantic models.
  - server → client: `hello`, `health`, `session`, `decode`
    (`kind: activity|directed`), `station`, `receiver_status`, `error`
  - client → server: `hello`, `tune`, `select_receiver`, `subscribe`, `ping`
- Binary frames, little-endian, first byte = channel:
  - `0x01` audio: `u8 ch | u8 flags | u16 rsvd | u32 seq | u32 rate` + s16le PCM
  - `0x02` waterfall: `u8 ch | u8 flags | u16 bins | u32 seq | u32 start_hz | u32 span_hz` + u8 bins

## Health model

Distinct, timestamped component states — never inferred from an open socket:
bridge connected · decoder process up · decoder API responding (UDP heartbeat age)
· decoder capturing (JS8Call's Pulse capture stream present and running) ·
receiver connected · audio fresh · waterfall fresh · last decode timestamp.

## Decisions (agreed 2026-10-08)

| # | Topic | Decision |
|---|---|---|
| D1 | UI framework | Svelte 5 + TS; hot paths framework-free in `web/src/lib/` |
| D2 | Map | MapLibre GL + self-hosted Protomaps PMTiles (low zoom, dark) |
| D3 | Contract | Pydantic → JSON Schema → TS (`json-schema-to-typescript`), CI drift check |
| D4 | Python deps | `uv` (`uv.lock` with hashes; `uv export --require-hashes` for images) |
| D5 | Scaling | one bridge, static pool of decoder slots (`DECODER_SLOTS`, default 1) |
| D6 | Shared sessions | one Kiwi connection per slot shared by all browsers; any client may retune (broadcast), optional hold lock |
| D7 | Directory | bridge fetches rx.linkfanel.net list, ~15 min cache, stale-on-error; manual host:port |
| D8 | Persistence | SQLite (WAL) on a volume; decodes + heard stations; 30-day default retention |
| D8b | Idle | keep decoding with no browsers attached; `IDLE_DISCONNECT_MINUTES` (0 = never) |
| D9 | Auth | reverse-proxy-fronted; bridge internal-only; WS Origin allowlist |
| D10 | License | GPL-3.0-or-later |
| D11 | Palette | "ghost signal": frosted glass over a deep solid gradient (ink → indigo → plum) with a live ASCII backdrop (drifting static, radio rings with the callsign on each decode, a pulse per 15 s JS8 slot, an occasional ghost); "still" mode and reduced motion/transparency honoured. Aqua→violet accent, mint for live signal. Type: Share Tech Mono for the wordmark, panel titles and big readouts; Space Grotesk for UI text; JetBrains Mono for data. Logo: line-art stencil ghost (bridges cut into the outline, radio-wave hem, slit eyes). Default waterfall colormap "spectre" (mirrored by recorded-net PNGs); viridis/inferno/grey selectable |
| D12 | Waterfall | zoomed around the dial by default, zoomable |
| — | Web server | nginx-unprivileged (lighter than Caddy; TLS is the outer proxy's job) |
| — | Defaults | Python 3.12, Node 22 LTS, supervisord + fatal-exit listener, passband 100–3000 Hz USB, Kiwi ident `ghost.js8`, reconnect backoff 5 s–5 min jittered |

## Implementation notes and deviations from the plan

| Topic | Planned | Shipped in 0.1.0 | Why / next |
|---|---|---|---|
| D2 map tiles | MapLibre + self-hosted Protomaps PMTiles | MapLibre + bundled Natural Earth 1:110m land/border GeoJSON (~160 KB) and a Maidenhead field grid | No tile server or extraction toolchain needed, zero third-party requests, fits the minimal look. PMTiles remains the upgrade path if detail is needed. |
| D5 decoder slots | one bridge leasing a pool of N decoder slots | one bridge drives one station (one receiver + one decoder) | Covers the MVP. Run several compose projects for several receivers. The in-bridge slot pool is a follow-up; the `Station`/`DecoderHandle` seams are where it goes. |
| D6 shared session | shared, any client retunes, optional hold lock | shared, any client retunes, changes broadcast to all viewers | The hold lock is a follow-up. |
| Station source | `RX.SPOT` | `RX.CALL_ACTIVITY` (agent polls `RX.GET_CALL_ACTIVITY`) | JS8Call emits `RX.SPOT` only when spotting to PSKReporter is on, which we keep off. |
| Directed text | — | `FROM: text`, EOM `♢` stripped | `RX.DIRECTED` omits the sender; activity and directed records of one transmission are collapsed in the UI. |
| UI dev/test | — | `ghostjs8.sim.fake_agent` + `tools/dev-stack.sh` | Browser tests and UI work without Docker. Scripted traffic, never a decoding claim. |

## Milestones (status)

All nine milestones are complete for 0.1.0. The original plan follows.


1. Repo skeleton, tooling, CLAUDE.md/AGENTS.md, CI scaffolding
2. Decoder image: pinned + checksum-verified JS8Call on Ubuntu 24.04, Xvfb, supervised
3. Pulse null sink + remap-source + discard sink; JS8Call configured by stable device names
4. KiwiSDR receiver adapter (paired SND/W/F, normalization, rejections) + contract v0
5. fake-kiwi + fixture pipeline → **acceptance test passes** (gate)
6. Full contract + generated TS, health state machine, fan-out, limits, directory, persistence
7. Web app: tokens/branding, shell, waterfall, AudioWorklet, timeline, stations, map, status
8. Responsive, accessibility, Playwright smoke (incl. no-transmit assertion)
9. Docs, security-update process, release tagging

## Known risks to verify early

- Exact JS8Call 3.0.3 release asset and SHA-256 from `JS8Call-improved`.
- Whether JS8Call needs a callsign / first-run dialog dismissed to decode headless.
- Whether Qt Multimedia selects devices by Pulse description or name.
- Kiwi actual sample rate is ~12000.x Hz; nominal 12 kHz accepted, drift absorbed
  by the bounded buffer; 20.25 kHz wideband mode rejected.
