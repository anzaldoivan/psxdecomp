# Publishing: the README standard and decomp.dev reports

Every game repository psxdecomp bootstraps inherits two standards: how its README is laid out, and how it publishes
progress to [decomp.dev](https://decomp.dev). Both are code in `scripts/publish.py`, which S10 and
`/psxdecomp:upgrade` copy byte for byte into the game as `tools/psxd_publish.py`. The game's CI runs that copy
(`.github/workflows/psxdecomp-readme.yml`), so it needs nothing from the plugin. This page is the standard's one home;
other docs link here.

## When each part starts

The kit's phase ladder already works out every fact a category needs. The standard reads those records; it never
records them a second time, and it never asks for them before the phase that proves them.

| Fact a category needs | Where the game already records it | Phase |
|---|---|---|
| unit → binary or overlay | the split configs and the per-binary build | 3 |
| overlay → group (disc folder, archive) | the load map | 2 |
| game or SDK | the library-object boundaries; the census `kind` | 2, 5 |
| totals and matched counts | the census and the build's progress denominators | 5 |
| the report and its badges | the progress publisher | 9 (Publish) |

- **At bootstrap (S8)** the README is psxdecomp's template (`profiles/psx/README.md.template`), filled with the values
  the kit filled its skeleton with. `config/discs.tsv` is written when the answers carry a disc serial and a boot
  file name of the disc's own form. The progress block says "not published yet".
- **Phases 4 to 8** cost nothing extra. The badge table holds no numbers (decomp.dev serves them live), so banking a
  function never makes a README block stale. The game's own numbers block (the kit corpus `progress.py`, between
  `<!-- progress:begin -->` and `<!-- progress:end -->`) stays the game's; psxdecomp's markers are namespaced
  `psxdecomp:` so the two never collide.
- **Phase 9's first publish** creates `config/categories.tsv`. From that commit on its ids are frozen.

## Category ids: `config/categories.tsv`

Tab-separated, `#` comments allowed, header `id parent name status`. It holds identity only, with no membership
column: a list of member globs would copy the load map and could drift from it.

- `id`: `[a-z0-9_]+`, or `parent.child` with one dot (decomp.dev nests one level under the parent). `game` and `sdk`
  are required (decomp.dev's guide). Every other top-level id is one binary or one overlay group, and `main` is the
  boot executable's game code.
- **An id comes only from a fact that cannot change**: a disc file name or an archive entry index, never an inferred
  grouping such as a load slot or a guessed stage. A re-classified overlay keeps its id and its history.
- `parent`: empty for a top-level id; the id's prefix for a child.
- `name`: free text, improved as overlays are identified ("Rock 05" until the evidence names it). decomp.dev takes
  names from each report, so a rename costs nothing.
- `status`: `active` or `retired`. **A published id is never deleted or renamed**: decomp.dev keys each category's
  history by id, and a changed id silently starts a new, empty history. `categories --history` checks every committed
  version of the file.

Membership is decided at report time by the game's publisher, from the records in the table above. A unit lists
exactly one of `game` / `sdk`, plus `main`, or plus `<group>` and one `<group>.<file>`. A file with no code belongs to
no category: a category whose total code is 0 would show 100% matched.

## The report contract

decomp.dev ingests an objdiff `report.json` from a GitHub Actions artifact on a completed `push` run of the default
branch.

- **Version 2.** decomp.dev migrates v0 and v1 reports and refuses any other version. A v2 report's category measures
  are read exactly as written; nothing is recomputed. A generator that does not use objdiff-cli must therefore compute
  every category's measures itself, `total_units` and `complete_units` included.
- **Artifact `<EXE>_report`**, where the version is the boot executable's file name, e.g. `SLUS_000.00_report` (the
  decomp.dev guide's own example has this form). The file inside is `report.json`.
- **Every linked object is a unit**, the SDK's too, so the report sees the whole binary.
- **uint64 fields are decimal strings** (proto3 JSON). decomp.dev's parser would also take numbers; strings are the
  form every parser accepts.

The game emits units with their `progress_categories`; psxdecomp keeps the arithmetic:

```sh
python3 tools/psxd_publish.py categorize units.json --categories config/categories.tsv -o report.json
python3 tools/psxd_publish.py validate report.json --categories config/categories.tsv \
    --artifact SLUS_000.00_report --exe SLUS_000.00
```

`categorize` writes `version: 2`, the report's measures, and every active category's measures, named from the TSV.
It refuses an unregistered or retired id, a child listed without its parent, a unit in two overlays of one group, a
unit that is neither `game` nor `sdk` (or both), an active id no unit lists, and an active id with no code.
`validate` checks the schema, the firewall (no field outside report.proto, no long hex or base64 run), every ratio,
every category's sums against its units, the ids and their parents, and the artifact name. `decompdev.py validate`
is the same check from the plugin.

A sample upload step (push only, ROM-free; doctor's `progress` row lints a workflow like it):

```yaml
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  report:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<full commit SHA> # v7
      - run: python3 tools/progress_units.py > units.json          # the game's publisher (Phase 9)
      - run: python3 tools/psxd_publish.py categorize units.json --categories config/categories.tsv -o report.json
      - run: python3 tools/psxd_publish.py validate report.json --categories config/categories.tsv --artifact SLUS_000.00_report --exe SLUS_000.00
      - uses: actions/upload-artifact@<full commit SHA> # v4
        with:
          name: SLUS_000.00_report
          path: report.json
```

A repository admin then registers the project at `https://decomp.dev/manage/new`. Its `default_category` is not on
that form, so the project page and an unfiltered badge show game and SDK together; the README's headline badges
carry `category=game`.

## The README

Sections, in order (H1 title first, an HTML banner may precede it):

| Section | Holds |
|---|---|
| `## Description` | what the game is and what the project rebuilds; the AI policy block, verbatim; the generated disc block; a `> [!IMPORTANT]` note that the repository holds no game data |
| `## Progress` | the generated progress block; optional prose (what an overlay is, what "matched" means); the game's own numbers block |
| `## Building the decompilation` | requirements, the command block, and the line a green build prints; before the first build, an honest "not buildable yet" line |
| `## Repository layout` | a `Path` / `Contents` table of real paths |
| `## Getting started` | `### Setting up`, `### Contributing`, `### Reference`: one sentence and one link each |
| `## Acknowledgements` | the community work the project stands on |
| `## License` | the project's licence and the no-licence statement over `src/` |

Other sections may follow Acknowledgements (Contact, links), never precede it. The shape follows soul-re
(Description, Progress, the three short subsections), Lain (the disc table, the build block, the layout table) and
recvx-decomp (the AI notice). Prose stays human-written; only the two marked blocks are generated.

### The generated blocks

`python3 tools/psxd_publish.py render README.md --write` rewrites only these:

- `<!-- psxdecomp:disc:begin -->` … `end`, under Description: `Disc | Serial | Executable | SHA-1 of the data
  track` from `config/discs.tsv` (`disc serial executable track source`) and `config/medium.sha1`, then the target
  executable's SHA-1 from `config/check.*.sha`, labelled as the target (a rebuilt hash exists only once a binary
  matches). "(Redump)" is printed only for a row whose `source` is `redump`, that is, the hash was checked against
  Redump.
- `<!-- psxdecomp:progress:begin -->` … `end`, under Progress: the headline Code and Functions badges
  (`category=game`), then one row per active top-level id (the SDK last), each with `category=<id>` badges linked to
  that category's decomp.dev page. Under the table, each group with overlays gets a collapsed `<details>` list of its
  active `<group>.<file>` ids, with the same badges, so a 50-overlay game keeps a short table. OWNER/REPO is
  `git remote get-url origin`. Without a categories list it is the "not published yet" line.

### The lint

`python3 tools/psxd_publish.py lint README.md [--release]` prints `README FAIL|WARN|INFO <check>: <detail>`.

| Check | FAIL when |
|---|---|
| title, headings | no `# ` title; a section missing, repeated or out of order; an unknown `## ` before Acknowledgements; a `###` of Getting started missing |
| ai-policy | the block is missing, repeated, altered or outside Description; the old disclosure sentence is present |
| no-game-data | Description lacks the `[!IMPORTANT]` no-game-data note |
| blocks | a marker pair missing or misplaced; a block differs from what `render` writes |
| categories, discs | the record breaks its rules (INFO when absent; FAIL with `--release`) |
| disc | a SHA-1 in Description is in no tracked record (`config/medium.sha1`, `config/check.*.sha`, the extraction manifest) |
| badges | a decomp.dev URL names another repository, a measure decomp.dev does not render, or a category that is not active (decomp.dev would silently fall back to the whole report) |
| layout | a path is neither tracked nor git-ignored (WARN when it exists only on this machine) |
| build | a `make <target>` in a command block or code span is no Makefile target |
| links | a relative link is neither tracked nor git-ignored |
| todo | a `TODO(phase-` line (WARN; FAIL with `--release`) |

It reads one README, two small records, the Makefile and `git show` of one file's history, with the standard
library only, in well under a second.

## Enforcement

- **CI:** `.github/workflows/psxdecomp-readme.yml` runs the lint and `categories --history` on every push and pull
  request (full history, read-only token, actions pinned by commit SHA).
- **`/psxdecomp:doctor`:** the `readme` row FAILs without the AI policy block; on a README that carries the progress
  block it runs the lint and FAILs on a lint failure; an older README WARNs. The `publish-tool` row WARNs when the
  vendored lint or its workflow differ from the plugin's; the `categories` row checks the list and its freeze.
- **`/psxdecomp:upgrade`:** writes the vendored lint and the workflow (psxdecomp owns both), and lists the README's
  lint failures as a manual action; the prose is the developer's.
- **Phase 9:** a suggested `verified by:` clause for the Publish phase:
  `python3 tools/psxd_publish.py lint README.md --release && python3 tools/psxd_publish.py categories --history`
  and a validated report uploaded as `<EXE>_report`.

## Sources (read 2026-10-04)

- The decomp.dev guide: decompals/decompedia `tools/decomp-dev.md`.
- decomp.dev source (encounter/decomp.dev main): `crates/github/src/lib.rs` (artifact name, push runs only),
  `crates/web/src/handlers/report.rs` (the `parent.child` split, `?category=`, the silent fallback),
  `crates/images/src/badge.rs` (the measures), `crates/web/src/handlers/manage.rs` (the project form).
- objdiff (encounter/objdiff): `objdiff-core/src/bindings/report.rs` (`REPORT_VERSION = 2`, `migrate()`) and
  `objdiff-core/protos/report.proto`.
- Reference READMEs and category schemes: fmil95/soul-re, shdecompilations/silent-hill-decomp,
  Y0oshi/lain-psx-decompiled, AshfordFamily/recvx-decomp, Xeeynamo/ff7-decomp.

## Open questions (2026-10-04)

- A per-category badge has been read from source, never rendered: check one once a project is listed.
- Whether decomp.dev's parser takes uint64 as JSON numbers is untested; the standard writes strings either way.
- Setting a project's `default_category` needs a decomp.dev admin.
- A CI report needs the game's unit list without game data: committed records, or a person publishing locally.
  Each game's Phase 9 decides.
