# psxdecomp

One Claude Code command that turns an empty folder into a ready **PlayStation (PS1) matching-decompilation
repository**: a short interview, your disc identified in place, a researched prior-art report, a pinned local
reference library of SDK and tooling sources, then the two tested installers —
[Project Architect 3.14.2](https://github.com/Druthulu/ProjectArchitect) and the decomp-architect kit — ending where
PA3's planner drafts the roadmap.

> **Not affiliated with psxrecomp.** The name nods to it; psxdecomp takes ideas only (no code or text) from
> [RetroPortingToolKit/psxrecomp](https://github.com/RetroPortingToolKit/psxrecomp), whose PolyForm Noncommercial
> licence is not compatible with this repository's. See [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Quickstart

```
/plugin marketplace add anzaldoivan/psxdecomp
/plugin install psxdecomp
```

Then, in an **empty folder**:

```
/psxdecomp:new
```

You need git, Python ≥ 3.12, PA3 installed once per machine (`pa_install.py --root`; the command tells you), your own
dump of the game (a Redump CUE/BIN, kept **outside** the folder), and — until it is published — a local copy of the
decomp-architect kit (`kit_path` option or `$PSXDECOMP_KIT`). Docker is needed from phase 1.0 on, not to bootstrap.

| Stage | What happens |
|---|---|
| S0 preflight | git, gh, Python, Docker, disk, PA3; refuses a non-empty folder |
| S1 interview | console (PS1 only in v1), title, region/version, dump path; goals, licence, visibility, AI disclosure, optional PsyQ path |
| S2 identify | serial, boot exe, exe header, track 01 digest, TOC fingerprint, PsyQ stamps, function seeds — facts only, read in place |
| S3 investigate | parallel research: existing decomps, sibling toolchains, maps, ports, versions, SDK-era triples |
| S4 gate | you confirm the report, the drafted answers and the reference library; nothing is installed before this |
| S5 repo | git init, licence, the ROM firewall as the first commit after its negative control |
| S6 PA3 | PA3's own unattended per-repo install at the pinned tag |
| — | restart: `claude --agent plain`, then `/psxdecomp:new --resume` |
| S7 intake | PA3's intake, handed the kit's intake with your confirmed answers |
| S8 kit | the decomp-architect installer: dry run, then run |
| S9 refs | `refs/` cloned at the pins, `docs/ops/refs.md`, the grep-first rule |
| S10 handoff | doctor, `config/psxdecomp.toml`, `docs/prior-art.md`; then a bare `claude` |

Other commands: `/psxdecomp:doctor` (read-only health check of a game repo) and `/psxdecomp:upgrade` (audit → plan →
apply --dry-run → apply, for existing repos bootstrapped by hand).

**The game repository works without the plugin.** It records its pins in `config/psxdecomp.toml`; PA3 and the kit
live in the repository as their installers put them.

## Firewall

No game byte and no SDK file ever lands in this repository, its CI, the eval workspaces or the game repository: the
dump is read in place by `identify` (facts only), the PsyQ SDK is `byo` (a local path, never fetched), the test
target is a synthetic disc built at test time ([fixtures/homebrew-psx](fixtures/homebrew-psx/)), and
`tools/audit_public.py` refuses disc images, executables and SDK paths in every push.

## Docs

[ARCHITECTURE](docs/ARCHITECTURE.md) · [PROFILES](docs/PROFILES.md) · [REFS](docs/REFS.md) ·
[ECOSYSTEM](docs/ECOSYSTEM.md) · [RELEASING](docs/RELEASING.md) · [HARVEST](docs/HARVEST.md) ·
[the stage contract](skills/new/reference/stages.md) · [compat.toml](compat.toml)

## Licence

MIT ([LICENSE](LICENSE)). The fixture program is CC0. Nothing here is derived from any game.
