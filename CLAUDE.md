# CLAUDE.md

Read [AGENTS.md](AGENTS.md) first. It is the maintained guide for this repo: layout, setup,
commands, conventions, GPU gotchas, and the release process. Everything there applies to
Claude Code sessions.

Claude Code specifics:

- Run `pytest -m "not integration"` and `cd web && npm test` before reporting a change as done.
  A web test that fails only on a timeout while other suites run is load flakiness; re-run it alone
  before treating it as a break.
- The Android app in the sibling repo consumes this API. If you change a response shape, say so
  explicitly in your summary so the app can be updated in the same release.
- Never commit `.env`, anything under `data/`, `wheels-local/*.whl`, or `bundled-apk/*.apk`.
  Never put real names, hostnames, tokens, or private paths into code, tests, or docs; use the
  placeholders already used in `docs/end-to-end.md`.
- When you add a module, setting, convention, or gotcha, update `AGENTS.md`, `.env.example`, and
  the README in the same change.
