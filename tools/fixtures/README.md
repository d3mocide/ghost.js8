# Test fixtures

## `A_1_4.wav` — real-recording acceptance fixture

| | |
|---|---|
| Upstream | [`JS8Call-improved/js8call-improved`](https://github.com/JS8Call-improved/js8call-improved) |
| Commit | `4c592bd9a034f18178a3e7179db92acb14939668` (tag `v3.0.3`) |
| Path | `media/tests/A_1_4.wav` |
| Format | RIFF WAVE, mono, signed 16-bit PCM, 12 000 Hz, 15 s |
| SHA-256 | `60b650c2090dff5e2144f164ebe692cde5f048c769518e1b1b9e67223f3da138` |
| License | **GPL-3.0** (as part of the JS8Call-improved source tree) |
| Expected decode includes | `K0OG: KN4CRD SNR +02` |

`fetch_fixture.py` downloads the file from that exact commit, verifies the
SHA-256 and fails hard on mismatch. It is cached in `cache/` (git-ignored) and
**not redistributed** by this repository. Anyone running the acceptance test
fetches it from upstream under upstream's license.

ghost.js8 itself is GPL-3.0-or-later, so using the fixture in tests raises no
license conflict; we still keep it out of the tree to keep provenance explicit
and the repository free of third-party binaries.

```sh
python3 tools/fixtures/fetch_fixture.py   # or: make fixtures
```
