# fake-kiwi

A simulated KiwiSDR for tests and the acceptance stack. The implementation lives
in the bridge package as `ghostjs8.sim.fake_kiwi` so tests import it directly
and it stays typed and linted; this directory documents how to run it.

```sh
# from bridge/
uv run python -m ghostjs8 fake-kiwi --wav ../tools/fixtures/cache/A_1_4.wav --align 15 --repeats 2 --port 8073
```

It speaks real KiwiSDR framing (big-endian SND PCM with correct headers, W/F
rows with the 16-byte header, MSG handshakes), enforces SND/W/F session
pairing, aligns playback to UTC 15-second boundaries, and can inject faults
(`too_busy`, `bad_password`, `down`, `db_update`, `silent`, compressed/stereo
flags, truncated frames, ADC overload). Waterfall rows are **synthetic**: they
test transport and rendering only. See `docs/operations.md` for the manual
real-receiver checklist.
