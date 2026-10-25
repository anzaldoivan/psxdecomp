# Harvest

Game repositories bootstrapped by psxdecomp (and the earlier ones it adopts, as of 2026-10-01: mmx6, DC2, BFM) learn things the next
bootstrap should start with. They come back here only as **reviewed pull requests that name their origin**.

| What | From (in a game repo) | Lands in psxdecomp as |
|---|---|---|
| A matching triple proven at a gate | `docs/ops/compiler-pin.md` | a `[[seen_in]]` row in `profiles/psx/psyq.toml` naming the repo, the phase and the date |
| A probe fact a real disc contradicted | `docs/prior-art.md` corrections | a probe fix plus a tier-1 fixture case that reproduces it |
| A reference source agents kept needing | web-retriever reports | a `refs.toml` row (licence read and dated) |
| A host arrangement that worked | `docs/ops/*hosts*` | a `profiles/<id>/hosts/<recipe>.md` |
| A byo SDK a project verified (mmx6, PsyQ 4.7, phase 1.9 T2 `d5cd466c`, 2026-10-24) | its hash list, `sha256  path` lines with names and hashes only (mmx6 `config/sdk.psyq47.sha256`) | a hash-only manifest per SDK version, which the doctor's `sdk` row checks, and stamp scanning of the SDK's LIB files. No SDK byte |
| A research lead class S3 missed | a backtest miss | a search seed in `[research]` and, when it generalises, a backtest eval |
| A debt class that a game's scanner proved | mmx5 `tools/readability/scan.py` (commits `198d2e2`, `077fc91`, read 2026-10-12) | a kind of `scripts/floor.py debt`, written fresh, with a planted file in its self-test |
| A tool of its own that does a delivery's work | one of the paths below | an `OWN_DETECT` entry in `scripts/upgrade.py` |

Three patterns of `scripts/floor.py` are close to lines of that scanner: the function-definition finder, the
placeholder-name pattern and the keyword set beside it. The scanner is AGPL-3.0 in mmx5. Its author, who is the owner
of this repository, offers those three patterns here under this repository's MIT licence (decided 2026-10-12).

## What a game keeps as its own

`/psxdecomp:upgrade` proposes an `[own]` key in `config/psxdecomp.toml` when a game holds one of these exact paths.
psxdecomp then delivers nothing for that key. The doctor checks that the path exists.

The list as of 2026-10-12. mmx5 was the first game to hold each path.

| `[own]` key | Path | What psxdecomp would deliver in its place |
|---|---|---|
| `debt` | `tools/readability/scan.py` | the debt baseline, the assembly ledger and rule `FIN1` |
| `names` | `config/names.basis.tsv` | the names ledger and rule `NAME1` |
| `toolchain` | `tools/toolchain/fetch.sh` | the toolchain pin table |
| `campaign` | `tools/wave/ledger.py` | the campaign templates |
| `matcher` | `.claude/skills/wave-draft-coders` | the offered matcher skill |

`gate` has no path: the developer records the gate command with `/psxdecomp:upgrade own gate "<command>"`.

Not harvested: PA3's or the kit's own rules and cookbook entries (they go upstream to their own repositories), and
anything derived from a game's bytes.

Each harvest PR carries: the origin (repo, commit, file), why it generalises beyond that game, and the tier that
proves it here.
