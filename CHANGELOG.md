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
