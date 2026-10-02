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
| decomp-architect kit (ships in Druthulu/BFM-decomp until its split) | digest `sha256:581f5ec0…` | 2026-10-01 | pinned | — | the decomp overlay, installed by its own `install.py --answers` (S8); its firewall templates (S5) |
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

Tiers (core, optional) and verdicts live in `profiles/psx/refs.toml`, not here.

## Rules for reuse

- `adapt`-class code may be adapted with attribution; `copyleft` only into a compatible repository; `facts` sources
  are cited, never copied. A licence is read from the source itself and dated; "unstated" means `facts`.
- psxrecomp and MegaManX6Recomp (same author, PolyForm Noncommercial): ideas and facts only, in any psxdecomp file.
