# Harvest

Game repositories bootstrapped by psxdecomp (and the earlier ones it adopts, as of 2026-10-01: mmx6, DC2, BFM) learn things the next
bootstrap should start with. They come back here only as **reviewed pull requests that name their origin**.

| What | From (in a game repo) | Lands in psxdecomp as |
|---|---|---|
| A matching triple proven at a gate | `docs/ops/compiler-pin.md` | a `[[seen_in]]` row in `profiles/psx/psyq.toml` naming the repo, the phase and the date |
| A probe fact a real disc contradicted | `docs/prior-art.md` corrections | a probe fix plus a tier-1 fixture case that reproduces it |
| A reference source agents kept needing | web-retriever reports | a `refs.toml` row (licence read and dated) |
| A host arrangement that worked | `docs/ops/*hosts*` | a `profiles/<id>/hosts/<recipe>.md` |
| A byo SDK a project verified (deferred until one is in hand) | its file list and checksums | a per-version sha256 manifest the doctor's `sdk` row checks, and stamp scanning of the SDK's LIB files |
| A research lead class S3 missed | a backtest miss | a search seed in `[research]` and, when it generalises, a backtest eval |

Not harvested: PA3's or the kit's own rules and cookbook entries (they go upstream to their own repositories), and
anything derived from a game's bytes.

Each harvest PR carries: the origin (repo, commit, file), why it generalises beyond that game, and the tier that
proves it here.
