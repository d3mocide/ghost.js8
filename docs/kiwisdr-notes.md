# KiwiSDR protocol notes

What `bridge/src/ghostjs8/receivers/kiwisdr/` relies on. Verified against
[jks-prv/kiwiclient](https://github.com/jks-prv/kiwiclient) (`kiwi/client.py`,
`microkiwi_waterfall.py`) and exercised by `ghostjs8.sim.fake_kiwi`.

## Session pairing

A session is two WebSockets on the receiver's HTTP port (usually 8073):

```
ws://host:port/<session-id>/SND
ws://host:port/<session-id>/W/F
```

`<session-id>` is a client-chosen integer (browsers use a Unix timestamp). Both
streams **must** use the same identifier; `verify_pairing()` enforces it
before connecting, and the fake Kiwi refuses a W/F without a live SND under the
same id (`MSG pairing_error=...`).

## Wire format

Every server message starts with a 3-byte ASCII tag. Integers are
little-endian unless noted.

```
SND  "SND" flags:u8 seq:u32 smeter:u16be  pcm...
W/F  "W/F" pad:u8 x_bin:u32 flags_zoom:u32 seq:u32  bins:u8[1024]
MSG  "MSG" pad:u8 "name=value name=value ..."   (values URL-encoded; bare names allowed)
EXT  same as MSG
```

- `rssi_dBm = 0.1 * smeter - 127`.
- SND flags: `0x02` ADC overload · `0x08` stereo (IQ) · `0x10` compressed
  (IMA ADPCM) · `0x80` PCM is little-endian.
- **SND PCM is signed 16-bit big-endian** by default. We byte-swap to
  little-endian. If `0x80` is set the data is already LE and is passed through
  (never double-swapped).
- Compressed, stereo/IQ and non-12 kHz audio are **fatal, typed errors**
  (`UnsupportedAudioFormat`). Compressed frames already in flight when we send
  `compression=0` are dropped for a 2 s grace window first.
- W/F `flags_zoom`: low 16 bits zoom (0–14), high 16 bits flags. Rows are 1024
  `u8` bins; `dBm ≈ value − 255` (minus the receiver's waterfall calibration,
  typically ~13 dB). With `wf_comp=0` rows are uncompressed.
- Row start: `x_bin * bandwidth / (1024 << 14)`; span: `bandwidth >> zoom`.
  `bandwidth` comes from `MSG bandwidth=` (default 30 MHz).

## Handshake

Client → server is plain-text `SET ...` messages.

SND:

1. `SET auth t=kiwi p=<password>`
2. ← `MSG badp=0` (accepted) or a rejection (below), `version_maj/min`, `bandwidth`, …
3. ← `MSG audio_rate=12000` → `SET AR OK in=12000 out=44100`
4. ← `MSG sample_rate=12001.135` (true rate; must be within 1 % of 12 kHz) →
   `SET compression=0`, `SET agc=1 hang=0 thresh=-100 slope=6 decay=1000 manGain=50`,
   `SET mod=usb low_cut=100 high_cut=3000 freq=14078.000`, `SET ident_user=ghost.js8`
5. SND frames flow. `SET keepalive` every 2 s on each stream.

W/F:

1. `SET auth t=kiwi p=<password>`
2. ← `MSG wf_setup` → `SET zoom=<z> cf=<kHz>` (≥ v1.329; older servers get
   `SET zoom=<z> start=<counter>`), `SET maxdb=-10 mindb=-110`,
   `SET wf_speed=3`, `SET wf_comp=0`, `SET interp=13`, `SET ident_user=ghost.js8`

Frequencies on the wire are kHz at baseband: subtract `MSG freq_offset=` (kHz)
for downconverter-fronted receivers. **LSB passbands are negative**:
`low_cut=-3000 high_cut=-100`.

## What we send, and what we never send

Only per-channel settings: mode, passband, frequency, **this channel's** AGC
(DSP, not hardware), waterfall zoom/speed/compression, identity, keepalives.
Never: attenuation, `genattn`/`gen`, admin commands, or anything that changes
the receiver for other users. An integration test asserts this.

## Rejections → `ReceiverRejected(reason)`

| MSG | Reason |
|---|---|
| `too_busy=<n>` | `FULL` — all slots taken |
| `badp=1`, `3`, `4` | `AUTH` — password needed/wrong, or admin restrictions |
| `badp=2`, `6`, `7` | `BUSY` — starting up, database update, admin connected |
| `badp=5` | `DUPLICATE_IP` — one connection per address |
| `down` | `DOWN` |
| `redirect=<url>` | `REDIRECT` (not followed automatically) |

Transport failures: DNS/refused/non-WebSocket → `ReceiverUnreachable`; slow
connect or no audio within the handshake timeout → `ReceiverTimeout`; an
established stream closing → `ReceiverClosed`.

## Etiquette

- Identify as `ghost.js8` (`SET ident_user`), and in the HTTP User-Agent.
- One paired session per decoder slot, shared by every browser.
- The adapter never retries; the session layer reconnects with jittered
  exponential backoff (min 5 s, max 5 min) and does not retry `AUTH`/`FULL`
  rejections aggressively.
- Respect the receiver's own time limits; disconnect when told.
