# Ecosystem watch

A dated ledger of the upstreams psxdecomp pins or learns from (the shape of psxrecomp's `docs/ecosystem-watch.md`;
our own text). Each row: the commit evaluated, how far it was inspected, what is reusable. A PA3 or kit bump lands only
after tiers 0–2 pass on it ([RELEASING.md](RELEASING.md)).

States: **pinned** (in `compat.toml`, tested) · **fully inspected** (code read) · **metadata only** (licence, layout,
activity) · **watch** (re-check on the next release).

| Upstream | Commit / tag evaluated | Date | State | Licence | What psxdecomp takes |
|---|---|---|---|---|---|
| [Druthulu/ProjectArchitect](https://github.com/Druthulu/ProjectArchitect) | `v3.14.2` = `0ccf0df` | 2026-10-01 | pinned | see repo | the governance framework, installed unchanged; `pa_install.py --project --yes` is the unattended path (S6) |
| ProjectArchitect | `v3.15.2` = `7f01318` | 2026-10-01 | watch | — | newer than the pin; bump only through RELEASING |
| decomp-architect kit ([anzaldoivan/BFM-decomp](https://github.com/anzaldoivan/BFM-decomp) branch `kit-pa3`, `decomp-architect/`) | `898aeb3`, digest `sha256:581f5ec0…` | 2026-10-02 | pinned | — | the decomp overlay, installed by its own `install.py --answers` (S8); its firewall templates (S5) |
| [RetroPortingToolKit/psxrecomp](https://github.com/RetroPortingToolKit/psxrecomp) | `3505f2a` | 2026-10-01 | metadata only | PolyForm Noncommercial 1.0.0 | ideas only: the CLI scaffold shape, the disc probe's outputs, the single pin manifest, audit→plan→apply migration, this ledger's shape |
| [sozud/psy-q-decomp](https://github.com/sozud/psy-q-decomp) | `6edf9b2` | 2026-10-01 | metadata only | MIT | a `refs` row (no use yet in mmx6 or BFM) |
| [Xeeynamo/psyz](https://github.com/Xeeynamo/psyz) | `6bd06da` | 2026-10-01 | metadata only | MIT / MPL-2.0 / unlicensed by path | not a `refs` row (no use in mmx6 or BFM) |
| [ethteck/splat](https://github.com/ethteck/splat) | `1d09139`; PyPI `splat64` 0.50.0 | 2026-10-01 | fully inspected (as used by the 1b smoke) | MIT | the splitter; the smoke pins the PyPI release mmx6 pinned |
| [mkst/maspsx](https://github.com/mkst/maspsx) | `423ffc6` | 2026-10-01 | metadata only | MIT | a `refs` row |
| [Xeeynamo/sotn-decomp](https://github.com/Xeeynamo/sotn-decomp) | `9faca7c` | 2026-10-01 | metadata only | AGPL-3.0 | a `refs` row (`copyleft`), with a recorded trap (its psxsdk headers are not Sony's) |
| [grumpycoders/pcsx-redux](https://github.com/grumpycoders/pcsx-redux) | `2bcbea9` | 2026-10-01 | metadata only | GPL-2.0 | a `refs` row (psyq-obj-parser, with a byo SDK); its docs site is a link |
| [matt-kempster/m2c](https://github.com/matt-kempster/m2c) | `708d2d2` | 2026-10-01 | metadata only | GPL-3.0 | a tool game repos install; not a `refs` row (its source answered nothing) |
| [decompals/old-gcc](https://github.com/decompals/old-gcc) | `b74211c` | 2026-10-01 | metadata only | unstated | a `refs` row (`facts`); compilers pinned by asset sha256 in game repos |
| GNU gcc 2.7.2 / 2.95.2 source (`ftp.gnu.org`) | sha256 `7cd8bce5…` (`/old-gnu/gcc-2.7.2.tar.gz`), `064e1cb0…` (`gcc-2.95.2.tar.gz`) | 2026-10-01 | metadata only | GPL-2.0+ | `refs` rows, one per compiler pin (BFM's most-cited reference) |
| [lab313ru/ghidra_psx_ldr](https://github.com/lab313ru/ghidra_psx_ldr) | `6f6be18` | 2026-10-01 | metadata only | unstated | a `refs` row (`facts`): its PsyQ signatures identify the libraries |
| [Lameguy64/PSn00bSDK](https://github.com/Lameguy64/PSn00bSDK) | `5d9aa2d` | 2026-10-01 | metadata only | MPL-2.0 core | not a `refs` row: its API is not PsyQ's (a recorded trap) |
| [psx-spx/psx-spx.github.io](https://github.com/psx-spx/psx-spx.github.io) | `00d5dcb` | 2026-10-01 | metadata only | not stated in the repo | a `refs` row (`facts` until CC0 is confirmed) |
| [Decompollaborate/spimdisasm](https://github.com/Decompollaborate/spimdisasm) | `4b5d4c6` = 1.42.4 | 2026-10-01 | metadata only | MIT | a `refs` row (splat's disassembly backend; rabbitizer is its dependency) |
| [decompme/compilers](https://github.com/decompme/compilers) | `bf4f879` | 2026-10-01 | metadata only | unstated | a `refs` row (`facts`, read only: its build downloads PsyQ) |
| [decompals/decompedia](https://github.com/decompals/decompedia) (decomp.wiki) | 2026-09-24 | 2026-10-01 | metadata only | unstated | a `refs` link row |
| sadnescity/psx-spx-claude-plugin | — | 2026-10-01 | metadata only | — | the counter-example: docs as 46 auto-invoked skills; psxdecomp keeps docs as files |
| [shdecompilations/silent-hill-decomp](https://github.com/shdecompilations/silent-hill-decomp) | `a1f407c` | 2026-10-02 | metadata only | NOASSERTION | conventions only: objdiff progress report on decomp.dev, `.gitattributes`; byte-match CI with the ROM in a private GHCR image |
| [celophi/lom-decomp](https://github.com/celophi/lom-decomp) | `1e9f85a` | 2026-10-02 | metadata only | none stated | conventions only: `decomp.yaml` (ethteck/decomp_settings), private-image byte-match CI |
| [GabeRealB/parasite-eve-2-decomp](https://github.com/GabeRealB/parasite-eve-2-decomp) | `2e8c524` | 2026-10-02 | metadata only | CC0-1.0 | conventions only: private-image byte-match CI; its CLAUDE.md (42 KB) is the context-inflation counter-example |
| [Xeeynamo/ff7-decomp](https://github.com/Xeeynamo/ff7-decomp) | `5cd0058` | 2026-10-02 | metadata only | none stated | conventions only: the sotn-decomp house layout and report |
| [sozud/mmx4](https://github.com/sozud/mmx4) | `7569876` | 2026-10-02 | metadata only | AGPL-3.0 | conventions only here (game repos may port from it under its licence) |
| [FoxdieTeam/mgs_reversing](https://github.com/FoxdieTeam/mgs_reversing) | `c399b3e` | 2026-10-02 | metadata only | none stated | conventions only; not on decomp.dev |
| [encounter/dtk-template](https://github.com/encounter/dtk-template) | `95a941f` | 2026-10-02 | metadata only | CC0-1.0 | the shape: the template owns the game-repo layout (GC/Wii), the build generates a git-ignored `objdiff.json` |
| [aaaaaaaaaaway/kaze-no-notam-decomp](https://github.com/aaaaaaaaaaway/kaze-no-notam-decomp) | `691c0e9` | 2026-10-02 | metadata only | none stated | the pattern: its decomp.dev report is built from tracked files (function manifest, matched ledger), no ROM, no secrets |
| [decomp.dev](https://decomp.dev) | read API, 2026-10-02 | 2026-10-02 | metadata only | — | a research source (`scripts/decompdev.py`): `/projects.json`, `/{owner}/{repo}.json`; ingestion is an objdiff `report.json` artifact named `<version>_report` |

Tiers (core, optional) and verdicts live in `profiles/psx/refs.toml`, not here.

## Proposed to upstreams

Changes psxdecomp does not make itself: the kit owns the game-repo layout (as dtk-template does for GC/Wii), and a game
repo owns its own text. Each row goes to its owner as its own change. States: **proposed** · **sent** · **accepted** ·
**declined** · **deferred**.

| # | What | Evidence | Owner | State |
|---|---|---|---|---|
| K1 | Namespace foreign ids in `provenance:` lines (`BFM:G6`, not `G6`) | 120 of 148 lines in an installed tree cite bare ids that collide with the game's own `rules/G*.md` (2026-10-01); the `id-collision` eval passed 1.0, so hygiene, not a seen failure | kit | proposed |
| K2 | Cite the 12 dangling BFM paths as `BFM:<path>@<sha>` or drop them | `provenance:` lines name BFM files absent from the game repo (2026-10-01) | kit | proposed |
| K3 | Render the candidate compiler row as "superseded by the pin row" and grey it out after the pin | the row restates `COMPILER_FAMILY` under the pinned-triple row; psxdecomp labels it meanwhile (2026-10-01) | kit | proposed |
| K4 | Install the calibration docs into a pinned read-only `.decomp-architect/kit@<sha>/` | a grep cannot tell kit text from game text (B1 R1, 2026-10-01) | kit | deferred (a future major) |
| K5 | Fix the hygiene baseline: 4 unscoped claims, 6 copied sentences | doctor `hygiene` row on the tier-1 fixture tree (2026-10-01) | kit | proposed |
| K6 | A decomp.dev report built from the tracked verification log | kaze-no-notam-decomp does it from tracked files with no ROM and no secrets (2026-10-02); fits the firewall | kit | proposed |
| K7 | `objdiff.json` generated by the build and git-ignored | dtk-template's `.gitignore` lists it; the build writes it (2026-10-02) | kit | proposed |
| K8 | GitHub firewall settings and files from DC2 T0 (vulnerability reporting, rulesets, push protection, pinned actions) | DC2's settings read through `gh api` (2026-10-02); doctor's `github` row lints them | kit | proposed |
| K9 | `.gitattributes` and `.editorconfig` | shared by the PS1 projects at 100% on decomp.dev (2026-10-02) | kit | proposed |
| K10 | An optional `decomp.yaml` (ethteck/decomp_settings) | lom-decomp ships one; tools read one settings file (2026-10-02) | kit | proposed |
| K11 | Carry the AI policy block in the README skeleton itself, above `{{AI_DISCLOSURE}}` | psxdecomp's S10 inserts it into every generated README meanwhile (`common.AI_POLICY`, 2026-10-02) | kit | proposed |
| M1 | Mark the bootstrap-era compiler candidate as superseded: one `HOW_WE_WORK.md` line for `PROJECT_CONTEXT.md:149,498` (never edited), a prefix on `docs/ops/decomp-environment.md:11` and the install record's line 14 | the candidate text still reads as current while `docs/ops/compiler-pin.md` holds the pin; the mislabelled mmx4 rules are already a `refs.toml` trap (2026-10-01) | mmx6 | proposed (after its router session) |

## Rules for reuse

- `adapt`-class code may be adapted with attribution; `copyleft` only into a compatible repository; `facts` sources
  are cited, never copied. A licence is read from the source itself and dated; "unstated" means `facts`.
- psxrecomp and MegaManX6Recomp (same author, PolyForm Noncommercial): ideas and facts only, in any psxdecomp file.
