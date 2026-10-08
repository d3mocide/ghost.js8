# ghost.js8

**Receive-only JS8Call decoding through web-based KiwiSDR receivers.**

Passive, quiet, persistent listening on HF digital traffic, in the spirit of
S2 Underground's GhostNet. A d3FRAG Networks project.

ghost.js8 connects to a public (or your own) KiwiSDR, feeds its audio to the
**native JS8Call decoder** running headless in Docker, and shows the decoded
traffic, a live waterfall, heard stations and a map in a browser. It never
transmits.

```
KiwiSDR ─ SND ─▶ bridge ─▶ decoder-agent ─▶ PulseAudio ─▶ JS8Call (native, headless)
        └ W/F ─▶ bridge ─▶ browser              JS8Call ─ UDP ─▶ agent ─▶ bridge ─▶ browser
```

## Status

MVP complete:

- **Decoding is proven with a real recording.** `make acceptance` replays
  upstream's `A_1_4.wav` through real KiwiSDR framing into native JS8Call and
  asserts `K0OG: KN4CRD SNR +02` arrives on the browser WebSocket. It runs in CI.
- **Health is truthful.** Each component reports evidence with timestamps, and
  a dead decoder can't look healthy.
- **The UI** has receiver directory and manual entry, JS8 band presets,
  waterfall, audio monitor, traffic timeline, heard stations, a map and status.
  It works on desktop, tablet and phone.

## Quick start

```sh
git clone https://github.com/d3mocide/ghost.js8 && cd ghost.js8
cp .env.example .env          # set GHOSTJS8_ALLOWED_ORIGINS; optionally a boot receiver
docker compose up -d --build  # web on 127.0.0.1:8080
```

Put your reverse proxy (Caddy / Nginx Proxy Manager) in front for TLS and
authentication: see [`docs/operations.md`](docs/operations.md). The host clock
must be NTP-synced; JS8 decoding depends on it.

## Documentation

| | |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | components, topology, decisions |
| [`docs/protocol.md`](docs/protocol.md) | bridge ↔ browser protocol, binary layouts |
| [`docs/kiwisdr-notes.md`](docs/kiwisdr-notes.md) | KiwiSDR framing, pairing, byte order, etiquette |
| [`docs/decoder-container.md`](docs/decoder-container.md) | JS8Call headless, PulseAudio routing, UDP API |
| [`docs/operations.md`](docs/operations.md) | deploy, health, troubleshooting, manual checklist |
| [`docs/SECURITY-UPDATES.md`](docs/SECURITY-UPDATES.md) | pinning and update process |
| [`AGENTS.md`](AGENTS.md) | contributor/agent handoff: commands, invariants, gotchas |

## Development

Requires `uv`, Node 22, GNU make, Docker.

```sh
make setup        # pinned deps
make check        # ruff, mypy --strict, pytest, eslint, prettier, svelte-check, vitest
make contract     # regenerate JSON Schema + TS from the Pydantic contract
make acceptance   # real-recording end-to-end test (Docker)
make e2e          # Playwright against a simulated stack (no Docker)
```

UI work without Docker: `tools/dev-stack.sh` (fake KiwiSDR + fake decoder + real
bridge) in one terminal, `cd web && npm run dev` in another.

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).

- JS8Call (GPL-3.0) runs as a separate, unmodified process.
- The upstream test recording is fetched at test time and not redistributed.
- Map outlines are Natural Earth (public domain).
