# AGENTS.md — ghost.js8

Handoff notes for coding agents and humans. Keep this file current: if you change
an invariant, a command, or discover a gotcha, update it in the same commit.

## What this is

Receive-only JS8Call decoding through public KiwiSDR web receivers. The **native
JS8Call application** decodes inside a Docker container; the browser is only the
interface. Full design: [`docs/architecture.md`](docs/architecture.md).

```
KiwiSDR ─ SND ─→ bridge ─→ decoder-agent ─→ PulseAudio null sink ─→ JS8Call (native)
        └ W/F ─→ bridge ─→ browser canvas          JS8Call ─ UDP API ─→ decoder-agent ─→ bridge ─→ browser
```

## Layout

| Path | What |
|---|---|
| `bridge/` | Python package `ghostjs8` (uv project; extra `bridge` = FastAPI/uvicorn/pydantic). `python -m ghostjs8 {bridge,agent,fake-kiwi,acceptance}`. |
| `bridge/src/ghostjs8/sim/` | `fake_kiwi` (simulated KiwiSDR) and `acceptance` (browser-like test client) |
| `bridge/src/ghostjs8/receivers/` | Receiver adapter interface + KiwiSDR implementation |
| `bridge/src/ghostjs8/decoders/` | Decoder adapter interface + native JS8Call implementation (incl. the in-container decoder-agent) |
| `bridge/src/ghostjs8/session/` | Session orchestration, health state machine, staleness tracking |
| `bridge/src/ghostjs8/api/` | FastAPI app: `/ws`, `/api/*`, `/healthz`, `/readyz` |
| `bridge/src/ghostjs8/contract/` | Pydantic models — **the single source of truth** for the browser protocol |
| `contract/` | Generated JSON Schema (committed) |
| `web/` | Vite + Svelte 5 + TypeScript UI. `web/src/lib/` is framework-free (protocol, DSP, waterfall, audio). |
| `web/src/lib/protocol/generated.ts` | Generated from the JSON Schema. **Never edit by hand.** |
| `web/src/lib/` | Framework-free, unit-tested: `protocol/` (client, binary), `audio/` (ring, worklet, player), `waterfall/`, `state/` (reducer, situation, Svelte app store), `grid.ts`, `bands.ts` |
| `web/src/features/` | Svelte panels: receiver, tuning, audio, waterfall, timeline, stations, map, status |
| `web/src/lib/backdrop/` | ASCII backdrop engine (`ascii.ts`, pure helpers unit-tested) + per-viewer mode preference |
| `web/src/styles/tokens.css` | Design tokens: the single source for colour, glass, radii, spacing, type, motion |
| `web/deploy/` | nginx template for the `web` image |
| `tools/dev-stack.sh` | fake KiwiSDR + fake decoder-agent + real bridge, no Docker (`GHOSTNET=1 SEED_NET=1` for the autopilot + a seeded recording) |
| `bridge/src/ghostjs8/ghostnet/` | GhostNet autopilot: `schedule` (plan v1.5 windows), `picker` (nearest receiver), `recorder` (FLAC + waterfall PNG), `pilot` ([`docs/ghostnet.md`](docs/ghostnet.md)) |
| `decoder/` | Decoder container: Dockerfile, supervisor config, PulseAudio config, JS8Call ini template |
| `tools/fake-kiwi/` | Simulated KiwiSDR server using real SND/W/F framing |
| `tools/fixtures/` | Fetch + verify script for the GPL-3.0 upstream test recording (never vendored) |
| `tools/acceptance/` | Real-recording end-to-end acceptance runner |

## Commands

Run from the repo root.

| Command | Does |
|---|---|
| `make setup` | `uv sync --locked --all-extras` (bridge) + `npm ci` (web) |
| `make lint` | ruff check + ruff format --check + eslint + prettier --check |
| `make typecheck` | mypy --strict + svelte-check + tsc |
| `make test` | pytest + vitest |
| `make check` | all of the above |
| `make contract` | regenerate JSON Schema + TS types from Pydantic (milestone 6) |
| `make contract-check` | fail if generated files are out of date |
| `make decoder-image` | build `ghostjs8-decoder:dev` (set `EXTRA_CA=/path/bundle.crt` behind a TLS proxy) |
| `make fixtures` | fetch + SHA-256-verify the upstream test recording into `tools/fixtures/cache/` |
| `make acceptance` | real-recording end-to-end test in Docker (`docker-compose.test.yml`, isolated network) |
| `make e2e` | Playwright (desktop + phone) against the simulated stack; set `PW_CHROMIUM_PATH` to use a preinstalled Chromium |
| `make images` / `make up` / `make down` | production compose build / start / stop |
| `git tag vX.Y.Z && git push --tags` | release: CI publishes multi-arch (amd64 + arm64) images to GHCR (`.github/workflows/release.yml`) |
| `tools/dev-stack.sh` + `npm --prefix web run dev` | UI development against the simulated stack |

Toolchain: Python 3.12 via `uv`, Node 22 LTS. Everything is pinned (see
[`docs/SECURITY-UPDATES.md`](docs/SECURITY-UPDATES.md) once written).

## Invariants — do not break

1. **Receive only.** No transmit button, TX field, or anything that looks like it
   could send. A Playwright test asserts this. A future radio interface must be a
   separate, explicit extension point. Branding stays mode-neutral ("JS8 ops
   console"); current capability is shown by the top bar's `RX` chip, which
   tracks the contract's `hello.receive_only`.
2. **Never change shared receiver hardware settings.** No attenuation changes,
   ever. Kiwi AGC is per-channel DSP; we send fixed per-channel defaults only.
   ADC overload is shown and receiver switching is offered — nothing else.
3. **Decoding is proven by the real recording, not mocks.** The acceptance test
   (`make acceptance`) must keep passing across decoder/runtime upgrades.
4. **Truthful readiness.** An open WebSocket proves nothing. Health reports
   distinct, timestamped component states; "last decode" is never inferred.
5. **Kiwi audio normalization:** request uncompressed mono at 12 kHz. SND PCM is
   big-endian s16 unless the frame's little-endian flag is set — honor it, never
   double-swap. Compressed, stereo, IQ, or non-12 kHz frames are rejected with a
   typed, logged error.
6. **SND and W/F connections share one session identifier.** Mismatch is an error.
7. **Bounded everything:** browser clients per session, audio buffer, waterfall
   frame rate. Drop/resync instead of growing latency.
8. **Contract is generated.** Edit the Pydantic models, run `make contract`,
   commit both. CI fails on drift.
9. **Pins:** base images by digest, Python deps by hash (`uv.lock`), Node deps by
   lockfile with exact versions, GitHub Actions by commit SHA, JS8Call by version
   + SHA-256.
10. **Be polite to public receivers:** identify as `ghost.js8`, back off on
    reconnect (jittered exponential, min 5 s, max 5 min), honor limits and
    rejections.

## Gotchas (learned the hard way)

- JS8Call 3.x AppImage fails on Ubuntu 22.04 — use **24.04**. Docker has no FUSE,
  so the AppImage is **unpacked at build time with `unsquashfs`** at the
  offset after its ELF runtime. It is never executed, which also lets an
  amd64 host prepare the arm64 tree. Upstream ships x86_64 and aarch64 only, with
  one SHA-256 pin per architecture.
- Receivers chosen by viewers or the autopilot go through
  `receivers/address_policy.py`: resolve, check **every** address, dial the
  checked IP, refuse redirects. Only the operator's boot target
  (`ReceiverTarget(trusted=True)`) skips it. The simulated stack needs
  `GHOSTJS8_ALLOW_LOOPBACK_RECEIVERS=true` (set by `tools/dev-stack.sh`).
- `StationConfig.min_connect_interval_s` (5 s) spaces all receiver connects.
  Station unit tests that reconnect quickly pass `min_connect_interval_s=0`.
- Local arm64 checks: `docker run --privileged --rm tonistiigi/binfmt --install arm64`
  (mount `binfmt_misc` first in a sandbox), then
  `DOCKER_DEFAULT_PLATFORM=linux/arm64 make acceptance`. It is slow under
  emulation but passes.
- Qt hides PulseAudio **monitor** sources from its input list. Expose the null
  sink's monitor via **`module-remap-source`** as an ordinary capture source.
- JS8Call's own audio output goes to a separate **discard** sink.
- JS8Call's UDP API: the agent listens on localhost and **learns the reply port**
  from incoming datagrams.
- JS8Call blocks on a settings dialog if `MyCall` or `MyGrid` is empty; the
  template sets receive-only placeholders. `PSKReporter` and `SpotToAPRS`
  **default to on** — they are forced off so we never publish spots.
- The decode filter (`[WideGraph] FilterCenter/FilterWidth`) **is** the decode
  range. It must cover the receiver passband.
- `AppRun` is a symlink; we exec `/opt/js8call/usr/bin/JS8Call` so the process
  is named `JS8Call` (healthcheck and `pkill -x JS8Call` rely on it).
- `RX.DIRECTED` `value` omits the sender (it is in `params.FROM`) and ends with
  the EOT marker `♢`. `RX.ACTIVITY` `value` carries the full `FROM: ...` line.
  `STATION.STATUS` arrives at ~2 Hz — ignore it. `PING` arrives every 15 s.
- JS8Call only emits `RX.SPOT` when spotting to PSKReporter is enabled (we keep
  it off). Heard stations come from the agent polling `RX.GET_CALL_ACTIVITY`
  (reply `RX.CALL_ACTIVITY`: callsign -> SNR/GRID/UTC).
- The decoder-agent may only send `ALLOWED_REQUESTS` to JS8Call (read-only);
  a test asserts `TX.*` requests raise.
- nginx's `mime.types` may lack `.mjs`; the web template serves it as
  `text/javascript`. With `nosniff`, MapLibre's module worker fails otherwise.
- MapLibre 6 loads its worker relative to its module URL: Vite must not
  pre-bundle it (`optimizeDeps.exclude`) and the app calls `setWorkerUrl()`
  with the `?url` import so production builds emit the worker.
- Compose's bake builder refuses build secrets outside the project; the
  Makefile builds with `COMPOSE_BAKE=false` and the default `extra_ca` secret is
  an empty in-repo file.
- `uv add/remove` re-syncs without extras; run `uv sync --all-extras` after.
- Building behind a TLS-intercepting proxy: pass the full CA bundle as build
  secret `extra_ca`; never disable verification.
- JS8 decoding depends on UTC alignment. The host must be NTP-synced; keep
  bridge-side audio buffering small.
- `uv` caches builds: if the editable install looks empty after creating new
  package dirs, run `uv sync --reinstall-package ghostjs8`.
- Every `*.proxy.kiwisdr.com` listing is one machine (`50.116.2.70`). When it refuses
  connections all ~400 of them fail together, so the picker ranks direct receivers
  first, `ReceiverPicker.bench_host()` benches the whole group after a connect
  failure, and the UI hides proxied receivers by default (`isProxied()`).
- `SelectReceiver.receiver.tls` must be forwarded into `ReceiverTarget`, or
  HTTPS-only receivers picked in the UI connect over plain `ws`.
- Desktop layout: left GhostNet/Receiver/Audio; centre Traffic, tuning strip,
  Waterfall; right Map/Stations/System. `Panel slim` hides the header for strips.
  No Node on the Pi host: run web checks and Playwright screenshots in
  `mcr.microsoft.com/playwright:v1.64.0-noble` (mount the repo, `npm ci` in `web/`).
- The autopilot never replaces a receiver that is `connected` and covers the dial,
  even one a viewer chose (`_adopt_working_receiver`): swapping a live feed for the
  "nearest" untried listing put a good session on a dead receiver. Receivers that
  stay silent ("no audio") are benched for 6 h, and ones that streamed for a minute
  are "proven" and ranked ahead of untried ones for 24 h (in memory: lost on restart).
- A receiver the autopilot did not choose (the operator's `GHOSTJS8_RECEIVER_HOST`, or a
  viewer's pick) gets the normal 60 s connect grace before it can be replaced, and is
  adopted as soon as it is `connected`. Pinning the boot receiver therefore survives restarts.
- JS8Call reports one transmission twice (RX.ACTIVITY, then RX.DIRECTED). The UI collapses
  them by `decodeKey`; `Store.station_decodes/station_counts` (GET `/api/stations/{call}`)
  dedupe on (utc, offset) and keep the directed record. Frames that are only `…` are noise:
  hidden in lists, a gap marker in Threads.
- GhostNet windows are UTC and live in `ghostnet/schedule.py` `PLAN`. A window in
  progress beats the next window's pre-roll. Any viewer tune/select/disconnect
  calls `station.operator_changed()`, which pauses the autopilot. Keep that hook
  on new control paths.
- The GhostNet distribution's ALE codeplug and HFN CSV are ALE, not JS8; don't
  import them.
- `soundfile` ships libsndfile in its manylinux wheel; the bridge image needs no
  system package for FLAC.
- axe flags scrollable lists with no focusable children
  (`scrollable-region-focusable`). It only shows up once a list overflows, as
  in the full e2e run, so give such lists `tabindex="0"` and a label.
- The ASCII backdrop canvas sits at `z-index: -1`, so the page base gradient
  lives on `<html>` and `<body>` must stay transparent, or the canvas is hidden.
  Keep the glass blur high enough (~20 px) that backdrop labels don't compete
  with panel text.
- TypeScript is pinned to 6.0.x because typescript-eslint does not yet support 7.

## Conventions

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `build:`, `ci:`, `chore:`).
- Python: fully typed, `mypy --strict` clean, ruff-formatted, asyncio throughout,
  injected clocks for anything time-based (tests must be deterministic).
- TypeScript: strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  no `any` at module boundaries.
- Structured JSON logs carrying a session ID.
