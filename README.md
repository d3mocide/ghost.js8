# ghost.js8

**Receive-only JS8Call decoding through web-based KiwiSDR receivers.**

Passive, quiet, persistent listening on HF digital traffic — inspired by
S2 Underground's GhostNet. A d3FRAG Networks project.

> Status: **milestone 1 — skeleton.** Nothing decodes yet. See
> [`docs/architecture.md`](docs/architecture.md) for the design and milestone plan.

## How it works

A Python bridge pulls audio (`SND`) and waterfall (`W/F`) from a KiwiSDR, feeds
the audio to the **native JS8Call application** running headless in Docker
(PulseAudio + Xvfb), and streams decoded traffic, audio and waterfall to a
browser UI. ghost.js8 never transmits.

## Development

Requires `uv`, Node 22, GNU make, and Docker (for the decoder and acceptance test).

```sh
make setup   # install pinned deps
make check   # lint + typecheck + unit tests
```

Agent/contributor notes: [`AGENTS.md`](AGENTS.md).

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE). JS8Call is a separate GPL-3.0 program
run as its own process; the upstream test recording is fetched at test time and
is not redistributed here.
