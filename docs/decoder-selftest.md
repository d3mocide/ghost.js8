# Decoder self-test

`decoder_process`, `decoder_api` and `decoder_capture` only prove that JS8Call is
alive and listening. The self-test proves it still **decodes**: once an interval the
decoder-agent mixes a recording of a real JS8 transmission into the audio it feeds
JS8Call and checks that the expected text comes back. The result is the
`decoder_selftest` health component.

It was added after a GhostNet window (2026-10-16 01:00Z) where a 4-day-old JS8Call
decoded about 5 % of what a fresh decoder pulled out of the same recording, while
every health component said `ok`. We never found the cause (the idle-timeout dialog
was ruled out), so the test is also how we will learn how it recurs.

## How it works

1. The agent picks the next UTC 15 s boundary at least 2 s away and arms a mixer.
2. From that instant the clip is added sample-by-sample (clamped, not wrapped) to the
   PCM on its way to PulseAudio. This is **after** the bridge fanned audio out to
   browsers and the recorder, so no viewer hears it and no recording contains it.
3. JS8Call decodes it about 14 s later. The agent's UDP handler sees the decodes.
   `@GHOSTNET` at ~1022 Hz or `KB8JEP:` at ~2321 Hz (±8 Hz) is a pass.
   `FOR NET.` at ~1343 Hz (-20 dB) is expected but too weak to count.
4. The agent never forwards the canary: matching decodes **and** JS8Call's delayed
   `……` re-report (about 35 s later) are swallowed for 90 s after injection, and
   `KB8JEP` is removed from the polled `RX.CALL_ACTIVITY` when its heard-time falls in
   a test window. Nothing canary-shaped reaches the store, the UI, the heard list or a
   net recording.
5. No decode within 35 s is a failure. One failure retries after 2 min (a real signal
   can sit on a canary offset). **Two in a row restart JS8Call**
   (`supervisorctl restart js8call`), with a 30 min cooldown, then retest after 2 min.

The test is deferred (never counted as a failure) when the bridge is not connected,
audio is not flowing, JS8Call is down or not capturing, or the bridge has asked to
hold. The bridge sends `selftest_hold` while a GhostNet window is recording, so the
test never occupies a decode period inside a net.

## Health mapping

| Agent state | Component | Meaning |
|---|---|---|
| never run / no report | `unknown` | not judged; does not degrade `overall` |
| last run passed | `ok` | `detail` says what decoded and the host load |
| 1 failure | `degraded` | `overall` becomes `degraded` |
| 2+ failures | `down` | JS8Call was restarted; `overall` stays `degraded` |
| `ok` but last pass older than 2.5 × interval | `degraded` | the test stopped running |

`/readyz` returns 503 whenever `overall` is not `listening`; the compose healthchecks
use `/healthz`, so a failing self-test never restarts a container by itself.

## Configuration (decoder container)

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTJS8_SELFTEST` | `on` | `off` disables it (component stays `unknown`) |
| `GHOSTJS8_SELFTEST_INTERVAL_S` | `3600` | seconds between passing runs |
| `GHOSTJS8_SELFTEST_FIRST_DELAY_S` | `300` | wait after agent start before the first run |
| `GHOSTJS8_SELFTEST_CLIP` | `/usr/share/ghostjs8/selftest/canary-js8-normal.wav` | 15 s, mono, 16-bit, 12 kHz WAV |

If the clip is missing or malformed the agent logs the error and runs without a
self-test.

## The clip

`decoder/rootfs/usr/share/ghostjs8/selftest/canary-js8-normal.wav`

| | |
|---|---|
| Source | our own GhostNet North America recording, 2026-10-16 01:01:15–01:01:30 UTC, 7.107 MHz USB via midtn.dynu.net |
| Format | RIFF WAVE, mono, signed 16-bit PCM, 12 000 Hz, 15 s (360 044 bytes) |
| SHA-256 | `dfa27695446742a31388565f23210d14f31450a0a67a669f1d9211e1921cd38b` |
| Expected | JS8Call 3.0.3 alone: `@GHOSTNET` 1022 Hz +7 dB, `KB8JEP:` 2321 Hz -4 dB, `FOR NET.` 1343 Hz -20 dB |
| Content | amateur-radio transmissions heard over the air (callsigns are public) |

It is a slice, not a synthetic signal, so it exercises the same decode path real
traffic takes. The expectations are in `selftest.CANARY_FRAMES`; a test pins them.
**If a JS8Call upgrade changes what the clip decodes, update both the clip notes here
and `CANARY_FRAMES`** (re-measure by replaying it through a fresh decoder; mixed into
a live stream the SNR drops by roughly 3-9 dB).

## Verified against real JS8Call

- Quiet-band replay with a 90 s interval: passes every run, the bridge forwards zero
  decodes, `last_decode_utc` stays null, no `KB8JEP` station appears, `/readyz` is
  `listening` with `decoder_selftest: ok`.
- Same stack with a silent clip: failure, failure 2 min later, JS8Call restarted
  (PID changed), bridge reports `overall: degraded`, `decoder_selftest: down`.
