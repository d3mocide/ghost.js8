# Security updates and pinning

Everything that enters an image or a build is pinned, so a build is
reproducible and an update is a reviewable diff.

| What | Pinned how | Where |
|---|---|---|
| Base images | tag **and** sha256 digest | `decoder/Dockerfile`, `bridge/Dockerfile`, `web/Dockerfile` (`ARG …_IMAGE=`) |
| JS8Call | version + SHA-256 of the AppImage; build fails on mismatch | `decoder/Dockerfile` (`JS8CALL_VERSION`, `JS8CALL_SHA256`) |
| Python deps | `uv.lock` with hashes; images install with `uv sync --locked` (hash-verified) | `bridge/uv.lock` |
| Node deps | exact versions + `package-lock.json` (integrity hashes); `npm ci` | `web/package*.json` |
| GitHub Actions | full commit SHA (with version comment) | `.github/workflows/*.yml` |
| Build tools | uv `0.11.32` (image digest), Node 22, Python 3.12 | Dockerfiles, `.nvmrc`, `.python-version` |
| Test fixture | upstream commit + SHA-256 | `tools/fixtures/fetch_fixture.py` |
| Basemap data | upstream commit + SHA-256 (provenance) | `web/public/map/README.md` |
| apt packages (decoder) | **not** version-pinned: installed from the GPG-signed Ubuntu archive at build time, so rebuilds pick up security fixes | `decoder/Dockerfile` |

## Automation

Renovate (`renovate.json`) opens PRs for npm, PyPI (via `uv.lock`), Docker
digests and GitHub Actions SHAs, groups action updates, and runs weekly lock
file maintenance. Security advisories get the `security` label. TypeScript is
held below 7 until typescript-eslint supports it.

Renovate does **not** update JS8Call. That is a manual, deliberate change.

## Updating JS8Call

1. Read the upstream release notes (`JS8Call-improved/js8call-improved`).
2. Download the new `JS8Call-vX.Y.Z-x86_64.AppImage`, compute its SHA-256, and
   check the GitHub build attestation if you can:
   `gh attestation verify JS8Call-vX.Y.Z-x86_64.AppImage --repo JS8Call-improved/js8call-improved`.
3. Update `JS8CALL_VERSION` and `JS8CALL_SHA256` in `decoder/Dockerfile`.
4. Diff `JS8_UI/Configuration.cpp`, `WideGraph.cpp` and the UDP message code
   for renamed settings keys or message shapes; update
   `decoder/rootfs/etc/ghostjs8/JS8Call.ini.tmpl` and
   `bridge/src/ghostjs8/decoders/js8call_native/messages.py`.
5. `make decoder-image && make acceptance`. **Do not merge unless the
   real-recording acceptance test passes.**

## Rebuild cadence

Rebuild and redeploy at least monthly, and promptly after any Ubuntu, Python,
nginx or Node security advisory, even without code changes, so the decoder's
apt packages and base layers stay current:

```sh
git pull && make images && make up
```

## Reporting a vulnerability

Open a private security advisory on the GitHub repository rather than a public
issue.

## Hardening already in place

- Containers run as non-root (`ghost` uid 10001 / nginx-unprivileged). The
  bridge filesystem is read-only except `/data` and `/tmp`.
- The decoder sits on an internal Docker network with no egress.
- Only the web port is published, bound to `127.0.0.1` by default.
- Strict CSP (no inline scripts, same-origin connections only), `nosniff`,
  `no-referrer`, COOP, restrictive Permissions-Policy.
- WebSocket Origin allowlist; per-connection rate limits on control messages;
  4 KiB message cap; receiver addresses validated (no loopback, link-local,
  reserved, or internal service names).
- The decoder-agent can only send read-only requests to JS8Call; spotting,
  update checks and transmit are disabled in its configuration.
- Build-time CA bundles for TLS-intercepting proxies are passed as BuildKit
  secrets and never written into an image.
