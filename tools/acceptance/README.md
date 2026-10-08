# Acceptance test

`make acceptance` proves the whole decode path with a real recording:

```
A_1_4.wav ─▶ fake-kiwi (KiwiSDR SND framing, big-endian, UTC-aligned, ×2)
          ─▶ bridge (KiwiReceiver: framing + byte-order normalization)
          ─▶ decoder-agent ─▶ PulseAudio ghost_rx ─▶ remap-source ─▶ native JS8Call
          ─▶ UDP API ─▶ decoder-agent ─▶ bridge ─▶ browser-facing /ws
          ─▶ acceptance client asserts "K0OG: KN4CRD SNR +02" within 150 s
```

It runs in `docker-compose.test.yml` on an isolated network (no egress). The
client is `ghostjs8.sim.acceptance`; it validates every message against the
generated contract. Keep this test passing across every decoder or runtime
upgrade.
