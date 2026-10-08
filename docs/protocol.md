# Bridge ↔ browser protocol (v1)

One WebSocket at `/ws` (proxied by the `web` container). Text frames are JSON;
binary frames carry audio and waterfall data. The protocol is **receive-only**:
no message exists that could transmit.

**Source of truth:** `bridge/src/ghostjs8/contract/messages.py` (Pydantic).
Generated artifacts, committed and drift-checked in CI (`make contract-check`):

- `contract/schema.json` — JSON Schema (draft 2020-12)
- `web/src/lib/protocol/generated.ts` — TypeScript types

Every JSON message has `"v": 1` and a discriminating `"type"`. Every property
is always present (nullable fields are sent as `null`).

## Connection sequence

```
browser                                   bridge
   │ ── WebSocket upgrade (Origin checked) ──▶ │   1008 if Origin not allowed, 1013 if session full
   │ ◀── hello      (build, limits, receive_only: true)
   │ ◀── history    (recent decodes oldest-first, stations heard in the last 24 h)
   │ ◀── session    (receiver, tuning, state, subscribers)
   │ ◀── health     (component states)
   │ ◀── receiver_status (ADC overload, RSSI, receiver info)
   │ ── subscribe {audio, waterfall} ──▶      binary channels are opt-in (default off)
   │ ◀── decode / station / session / health / receiver_status … (as they happen)
   │ ◀── binary audio / waterfall frames (only if subscribed)
```

## Server → browser (JSON)

| `type` | When | Key fields |
|---|---|---|
| `hello` | first | `build`, `receive_only: true`, `limits {max_clients, audio_sample_rate, waterfall_max_fps, waterfall_bins}` |
| `history` | after hello | `decodes[]`, `stations[]` |
| `session` | on any change | `state` (`idle` · `connecting` · `connected` · `backoff` · `rejected` · `failed`), `receiver {host, port, name}`, `tuning`, `subscribers`, `reject_reason`, `detail`, `next_retry_utc` |
| `health` | on change, and every 10 s | `overall` (`listening` · `degraded` · `offline`), `components {bridge, decoder_process, decoder_api, decoder_capture, receiver, audio, waterfall}` each `{state, since, last_seen, detail}`, `last_decode_utc` |
| `decode` | each decode | `kind` (`activity` · `directed`), `utc` (from the decoder), `text`, `snr_db`, `offset_hz`, `dial_hz`, `freq_hz`, `speed`, `from_call`, `to_call`, `grid` |
| `station` | station heard / updated | `callsign`, `last_heard_utc`, `snr_db`, `grid` (**valid Maidenhead only**), `offset_hz`, `dial_hz`, `heard_count` |
| `receiver_status` | every 2 s while connected, and immediately on ADC-overload change | `adc_overload`, `rssi_dbm`, `info` |
| `error` | bad client message | `code` (`bad_message` · `unsupported_version` · `session_full` · `invalid_tuning` · `invalid_receiver` · `rate_limited` · `internal`), `message` |
| `pong` | reply to `ping` | `utc` |

### Semantics worth knowing

- **Health is evidence, not inference.** `since` is when the state last
  changed; `last_seen` is the last positive evidence. `last_decode_utc` only
  moves when a decode arrives. Thresholds: audio stale > 3 s, waterfall > 5 s,
  decoder report > 10 s, decoder API heartbeat > 40 s.
- **JS8Call reports directed traffic twice** (an `activity` line and a
  `directed` record). Both are forwarded; UIs may collapse pairs with equal
  `utc` and `offset_hz`. Station `heard_count` counts each transmission once.
- `session.state = rejected` with `reject_reason`:
  `full` / `busy` / `duplicate_ip` → retried no sooner than 60 s;
  `auth` / `redirect` → not retried until the operator acts. `failed` means the
  receiver sends audio we deliberately do not support (compressed, stereo/IQ,
  non-12 kHz); not retried.
- `grid` is `null` unless it is a valid 4/6/8-character Maidenhead locator.

## Browser → server (JSON)

| `type` | Fields | Notes |
|---|---|---|
| `hello` | `client` | informational |
| `subscribe` | `audio`, `waterfall` | per-connection opt-in to binary channels |
| `tune` | `tuning {dial_hz, mode, low_cut_hz, high_cut_hz}` | affects everyone watching this station |
| `select_receiver` | `receiver {host, port, name}`, `password` | loopback / link-local / reserved addresses refused; private ranges unless disabled |
| `disconnect_receiver` | — | release the receiver |
| `ping` | — | answered with `pong` |

Control messages (`tune`, `select_receiver`, `disconnect_receiver`) are rate
limited to 10 per 5 s per connection. Messages over 4 KiB are rejected.

## Binary frames (bridge → browser)

All integers **little-endian**. First byte is the channel.

### Audio — channel `0x01`

```
offset size  field
0      1     channel = 0x01
1      1     flags: bit0 = ADC overload reported for this block
2      2     reserved (0)
4      4     seq (u32, wraps)
8      4     sample_rate (u32) = 12000
12     n     PCM: mono signed 16-bit little-endian
```

Blocks are ~512 samples (~43 ms). Gaps in `seq` mean dropped blocks; the
browser player resynchronizes rather than buffering further.

### Waterfall — channel `0x02`

```
offset size  field
0      1     channel = 0x02
1      1     flags (reserved, 0)
2      2     bins (u16) = 1024
4      4     seq (u32)
8      4     start_hz (u32): frequency of bin 0
12     4     span_hz (u32): total span; bin width = span_hz / bins
16     bins  u8 per bin: dBm ≈ value − 255 (receiver waterfall calibration not applied)
```

Rows are capped at `limits.waterfall_max_fps` (default 10) per station.
Synthetic rows from `fake-kiwi` exercise transport and rendering only.

## HTTP

| Path | Response |
|---|---|
| `GET /healthz` | `{"status":"ok"}` — liveness |
| `GET /readyz` | a `health` message body; **200** when `overall = listening`, else **503** |
| `GET /api/receivers` | `ReceiverDirectory` (`fetched_utc`, `stale`, `source`, `receivers[]`) — cached 15 min, stale on error |

## Versioning

`v` is bumped on any breaking change. A bridge rejects messages with an
unknown `v` (`error: unsupported_version`); browsers should do the same and
reload.
