# GhostNet autopilot

ghost.js8 can monitor the GhostNet JS8 nets for you, unattended. When enabled,
the bridge follows the GhostNet operating plan (v1.5) for your region. Ahead of
each window it connects to a public KiwiSDR near your home grid and tunes the
net frequency. It records the window (traffic, waterfall and audio) for viewing
later in the web UI.

It is **off by default** and remains **receive only**: nothing in ghost.js8 can
transmit, and the autopilot never changes shared receiver hardware settings.

## Enable

Set these on the `bridge` service (for example in `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTJS8_GHOSTNET` | `off` | `on` enables the autopilot |
| `GHOSTJS8_GHOSTNET_REGION` | — | `na`, `eu` or `aus`: which nets and data bridges to follow |
| `GHOSTJS8_HOME_GRID` | — | Your Maidenhead locator (4 or 6 characters); receivers are ranked by distance from it |
| `GHOSTJS8_GHOSTNET_PREROLL_MINUTES` | `10` | Connect and start recording this long before a window opens |
| `GHOSTJS8_GHOSTNET_RECORD_AUDIO` | `on` | Record FLAC audio (traffic and waterfall are always recorded) |
| `GHOSTJS8_GHOSTNET_PARK` | `on` | Between windows, park on 7.107 MHz and keep watching (not recorded) |
| `GHOSTJS8_RECORDINGS_DIR` | `/data/nets` | Where recordings are written (on the bridge data volume) |
| `GHOSTJS8_NET_RETENTION_DAYS` | `90` | Recordings older than this are pruned hourly |

The autopilot also needs `GHOSTJS8_DB_PATH`. The production compose file sets it.

If the configuration is invalid (unknown region, bad grid, no store), the bridge
still starts. The autopilot stays off, and the error is logged and shown in the
GhostNet panel.

With the autopilot on, idle disconnect is disabled, because the point is to
listen with nobody watching.

## Schedule followed

Times are UTC (the plan's "Thursday night" nets in local time). The windows
come from `bridge/src/ghostjs8/ghostnet/schedule.py`.

| Window | When (UTC) | Dial | Regions |
|---|---|---|---|
| GhostNet North America | Fri 01:00–01:30 | 7.107 MHz | na |
| GhostNet Europe | Thu 18:00–18:30 | 7.107 MHz | eu |
| GhostNet Australia | Thu 07:00–07:30 | 7.107 MHz | aus |
| NA–EU data bridge | Sat 18:00–19:00 | 14.107 MHz | na, eu |
| NA–AUS data bridge | Sat 12:00–13:00 | 14.107 MHz | na, aus |
| NA–AUS data bridge (80 m) | Sat 13:30–14:00 | 3.575 MHz | na, aus |
| EU–AUS data bridge | Sat 20:00–21:00 | 14.107 MHz | eu, aus |
| EU–AUS data bridge (80 m) | Sat 21:30–22:00 | 3.575 MHz | eu, aus |
| AUS–South Pacific data bridge | Sat 08:00–09:00 | 14.107 MHz | aus |
| AUS–South Pacific data bridge (40 m) | Sat 09:00–09:30 | 7.107 MHz | aus |

All windows use USB with a 100–3000 Hz passband, which matches the JS8Call
decode filter. If the plan changes, edit `PLAN` and its tests.

The ALE codeplug and the HFN ALE net list distributed with the plan are for
ALE, a different mode. ghost.js8 does not use them.

## Receiver choice

Receivers come from the public directory, which is fetched by the bridge. The
picker:

1. keeps receivers that report a location, cover the dial frequency plus 3 kHz,
   have a free channel and, when they report SNR, have at least 15 dB;
2. sorts them by great-circle distance from the home grid;
3. connects to the nearest one.

The panel shows the reason, for example "nearest free receiver: 412 km, SNR 22 dB".

A receiver that rejects the session, fails, or stays connecting/backing off for
longer than 60 s is benched for 30 minutes, and the next candidate is tried. The
normal reconnect etiquette applies throughout: jittered backoff, identifying as
`ghost.js8`, and honouring `too_busy` and `down`.

## Manual override

A viewer can always take control by tuning, selecting another receiver or
disconnecting. The autopilot then steps back:

- **during a window**: it stays paused until the window ends, and the recording
  is marked *operator override* (it continues, but may not be on the net);
- **between windows**: it stays paused until the next window's pre-roll.

A new window always takes the station back.

## Recordings

Each window is stored under its net ID, `<window>-<YYYYMMDDTHHMM>Z` (for example
`na-net-20261009T0100Z`):

```
/data/nets/<net-id>/audio.flac      12 kHz mono 16-bit FLAC (≈35–50 MB per hour)
/data/nets/<net-id>/waterfall.png   one row per second, -500…+3500 Hz around the dial
```

Decodes and the net summary live in the SQLite store (tables `nets` and
`net_decodes`). The HTTP API serves them read-only:

| Endpoint | Returns |
|---|---|
| `GET /api/nets` | `NetSummary[]`, newest first |
| `GET /api/nets/{id}` | `NetLog` (summary, stations, traffic, waterfall geometry) |
| `GET /api/nets/{id}/waterfall.png` | waterfall image |
| `GET /api/nets/{id}/audio.flac` | audio |

Net IDs are validated against a strict pattern, so unknown IDs and path tricks
return 404.

## In the UI

- **GhostNet panel** shows:
  - the mode: *ON NET*, *WATCHING 7.107*, *PAUSED — MANUAL* or *AUTOPILOT OFF*;
  - the current or next window, with a countdown in UTC and local time;
  - a REC indicator and the receiver reason;
  - the recorded nets.
- **Net log** (`#/net/<id>`) shows:
  - the waterfall, with time and offset axes; click it to seek the audio;
  - the audio player and download links;
  - heard stations;
  - the traffic list, where each timestamp seeks the audio.
- **Tags**: traffic is tagged `FLASH` (@GSTFLASH), `GN` (@GHOSTNET and the
  `@GN<country><state>` groups) and `DIR` (directed).
- **@GSTFLASH alert**: live flash traffic raises a banner (`role="alert"`) until
  it is acknowledged. History replayed on connect does not raise it.

## Development

`GHOSTNET=1 SEED_NET=1 tools/dev-stack.sh` runs the simulated stack with the
autopilot on (`HOME_GRID` defaults to `EN34`, `GHOSTNET_REGION` to `na`). It
seeds a synthetic recording of last week's net: `python -m ghostjs8 seed-net
--db … --recordings …`. The Playwright suite uses the same setup.
