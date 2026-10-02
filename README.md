# psxdecomp

> **Status: early (v0.1.0), PlayStation 1 only.** The decomp-architect kit is not yet published, so you need a local
> copy of it for now. Not affiliated with [psxrecomp](https://github.com/RetroPortingToolKit/psxrecomp); see
> [Thanks](#thanks).

**One Claude Code command turns an empty folder into a ready PlayStation matching-decompilation repository.**

You answer a short interview and point at your own disc dump. psxdecomp identifies the game in place, researches
existing work for you to confirm, sets up a local library of SDK and tooling references, and installs
[Project Architect](https://github.com/Druthulu/ProjectArchitect) with the decomp-architect kit. You finish in a
repository whose planner is ready to draft the roadmap, and which keeps working without the plugin.

## Games (backtests, 2026-10-01)

| Game | Serial | Notes |
|---|---|---|
| Mega Man X6 | SLUS-01395 (v1.1) | the mmx6 bootstrap of 2026-10-01 |
| Dino Crisis 2 | SLUS-01279 | the DC2 bootstrap branch of 2026-09-30 |
| Brave Fencer Musashi | SLUS-00726 | the kit's home project, [BFM-decomp](https://github.com/Druthulu/BFM-decomp) |

Each backtest replays a real bootstrap with its community leads blanked, and the research stage has to find them
again. Your own game goes through the same steps.

## Getting started

You need git, Python ≥ 3.12, Project Architect installed once per machine (the command tells you how), your own dump
of the game as a Redump CUE/BIN kept **outside** the folder, and a local copy of the kit (the `kit_path` option or
`$PSXDECOMP_KIT`). Docker is needed later, for building, not to bootstrap.

```
/plugin marketplace add anzaldoivan/psxdecomp
/plugin install psxdecomp
```

Then, in an **empty folder**, run `/psxdecomp:new`. It walks you through:

1. **Interview and identification.** You give the title, region and dump path. The disc is read in place, facts only.
2. **Research and your go-ahead.** psxdecomp looks for existing decomps, toolchains and maps, then shows you a
   report. Nothing is installed until you confirm it.
3. **Install.** It creates the repository with its ROM firewall as the first commit, then installs Project Architect
   and the kit. You restart Claude Code once, midway, when it asks you to.
4. **Handoff.** It fetches the reference library, runs a health check, and leaves you at a bare `claude`.

Two more commands: `/psxdecomp:doctor` checks a game repo's health (read-only), and `/psxdecomp:upgrade` adopts a
repo you set up by hand.

## What you get

```
your-game/
  config/psxdecomp.toml   what this repo was bootstrapped with
  docs/prior-art.md       the research report you confirmed
  docs/ops/refs.md        the reference-library index (the sources themselves sit in the ignored refs/)
  HOW_WE_WORK.md          Project Architect's working card for agents
  tools/audit_public.py   the ROM firewall, enforced from the first commit
```

## Your disc stays yours

No game byte and no SDK file ever lands in a repository, its CI or the tests. Your dump is read where it sits. The
PsyQ SDK is bring-your-own and never fetched. The tests use a synthetic disc built on the fly, and
`tools/audit_public.py` refuses disc images, executables and SDK paths on every push.

## Learn more

| Read | For |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how it is built, why, and how it is tested |
| [skills/new/reference/stages.md](skills/new/reference/stages.md) | every stage in detail: what it reads, writes and records |
| [compat.toml](compat.toml) and [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) | the pinned versions, and the upstreams watched |
| [docs/REFS.md](docs/REFS.md) | the reference library |
| [docs/PROFILES.md](docs/PROFILES.md) | console profiles, and the next consoles |
| [CONTRIBUTING.md](CONTRIBUTING.md) | tests, releases and pin bumps |

## Thanks

psxdecomp stands on other people's work:

- [Project Architect](https://github.com/Druthulu/ProjectArchitect) and the decomp-architect kit from
  [`BFM-decomp`](https://github.com/Druthulu/BFM-decomp), which psxdecomp installs unchanged.
- [psxrecomp](https://github.com/RetroPortingToolKit/psxrecomp), whose single-manifest pinning and README shape
  inspired ours. It takes ideas only, no code or text: its PolyForm Noncommercial licence is not compatible with this
  repository's.
- The tools and references a new repo starts from: [splat](https://github.com/ethteck/splat),
  [maspsx](https://github.com/mkst/maspsx), [spimdisasm](https://github.com/Decompollaborate/spimdisasm),
  [old-gcc](https://github.com/decompals/old-gcc), [ghidra_psx_ldr](https://github.com/lab313ru/ghidra_psx_ldr),
  [psy-q-decomp](https://github.com/sozud/psy-q-decomp), [sotn-decomp](https://github.com/Xeeynamo/sotn-decomp),
  [PCSX-Redux](https://github.com/grumpycoders/pcsx-redux), [psx-spx](https://github.com/psx-spx/psx-spx.github.io),
  [decomp.me](https://decomp.me) and [Redump](http://redump.org/).

The full ledger, with the commit each was checked at, is [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Licence

MIT ([LICENSE](LICENSE)). The fixture program is CC0. Nothing here is derived from any game.
