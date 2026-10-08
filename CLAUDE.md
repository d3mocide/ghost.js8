# CLAUDE.md

@AGENTS.md

## Notes for Claude

- Milestone order is non-negotiable: decoder container → audio path →
  real-recording acceptance test passes → bridge contract → UI. Do not start UI
  work before `make acceptance` passes.
- When observed runtime behaviour conflicts with `docs/architecture.md` or the
  gotchas above, stop and raise it with the user instead of working around it.
- Run `make check` before every commit.
