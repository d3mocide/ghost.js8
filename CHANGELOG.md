# Changelog

All notable changes. Versions follow SemVer; the protocol version (`v`) is
tracked separately in `docs/protocol.md`.

## [0.1.0] — unreleased

First MVP.

- Native JS8Call 3.0.3 decoder container (Ubuntu 24.04, Xvfb, PulseAudio null
  sink + remap-source + discard sink, supervised, checksum-verified binary).
- decoder-agent: PCM into PulseAudio, JS8Call UDP API with reply-port learning,
  call-activity polling, health facts.
- KiwiSDR adapter: paired SND/W/F sessions, big-endian PCM normalization with
  the little-endian flag honoured, typed rejections and format errors.
- Bridge: v1 protocol (Pydantic → JSON Schema → TypeScript), evidence-based
  health, binary audio/waterfall fan-out, receiver directory, SQLite history,
  reconnect policy, JSON logs.
- Web: Svelte 5 listening-post UI with waterfall, AudioWorklet monitor,
  timeline, stations, map and status; responsive and accessible.
- Real-recording acceptance test, Playwright smoke tests, CI.
- GhostNet autopilot (opt-in): follows the GhostNet v1.5 JS8 windows for a region
  on the nearest suitable public KiwiSDR, parks on 7.107 MHz between windows,
  and records traffic, a waterfall image and FLAC audio per window. It steps
  aside when a viewer takes control.
- "Ghost signal" visual design: frosted-glass panels over a deep solid
  gradient and a live ASCII backdrop. It shows drifting static and radio-wave
  rings carrying the callsign of each new decode. It also pulses on every 15 s
  JS8 slot, and an occasional ghost drifts past. A top-bar toggle switches to a
  still gradient; reduced motion draws one frame.
  The redesign also adds a sticky top bar and a hero strip showing the
  frequency, the situation and decodes/stations/last decode. The waterfall
  colormap was retuned to match.
- Net log viewer (`#/net/<id>`) with click-to-seek audio, and a live
  @GSTFLASH alert banner. Timeline tags for FLASH/GN/DIR traffic.
