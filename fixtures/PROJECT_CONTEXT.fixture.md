# {{GAME_TITLE}} — Project Context (TEST FIXTURE)

> **This is psxdecomp's canned constitution for tier-1 test installs (`install.py --intake-fixture`).** A real project's
> constitution is written by PA3's intake in a `claude --agent plain` session, handed the kit's `intake.decomp.md`
> (stage S7). Never use this file for a real game.

## Roadmap (the kit's ladder, abbreviated for the fixture)

- **Phase 0 — Governance and the firewall.** Milestone: the no-rom CI workflow is green on the first push.
- **Phase 1 — Extraction, the byte gate and the oracles.** Milestone: the fixture executable rebuilds byte-identical
  from assembly, with the hash check inside the build.
