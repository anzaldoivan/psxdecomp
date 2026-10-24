# The reference library

A small, pinned, greppable set of upstream sources in each game repository, **curated from use**. A source is in the
profile's list because mmx6 or BFM-decomp actually went to it (each row's `used_by` says where). Agents grep it
before they go to the web. Every row says what it may be used for (its licence class) and which version it speaks
for (`covers`). The index says which source wins when two disagree.

- **`config/refs.toml`** holds three tables. `[[ref]]` rows: `name`, `url`, `ref` or `sha256`, `licence`, `class`,
  `tier`, `covers`, `topics`, `paths`, `when`, `used_by`, `checked`. `[[authority]]`: per topic, the order of sources
  and the rule. `[[trap]]`: contradictions a project already paid for.
- **`fetch_refs.py`** fetches the `core` rows into the ignored `refs/<name>/` at their pins: shallow, sparse when
  `paths` is set, archives checked by sha256. `--with <name>` fetches an `optional` row when its `when` holds.
- **`docs/ops/refs.md`** — the committed index: the rows, the authority table, the traps.
- **The rule** (one `HOW_WE_WORK.md` line): grep `refs/` or dispatch `retriever-code`; never Read a `refs/` tree whole;
  the web only for what it lacks. Files, not skills: one index costs nothing until it is used.

## The curation audit (2026-10-01)

Method: count every source the projects cited and compare with the first list (13 fetched rows, 37 MB). For mmx6:
its five web-retriever reports (R1.1-001, R1.2-001, R1.3-002, R1.4-001, R1.6-003) and its tracked files. For BFM: its
tracked docs and its own `tools/reference/` clones.

| Source | mmx6 | BFM | Verdict |
|---|---|---|---|
| splat | R1.3-002; 216 files | 2 docs | **core** |
| maspsx | R1.3-002, R1.4-001; 43 files | 3 docs | **core** |
| decompals/old-gcc | R1.4-001; 20 files | 4 docs | **core** (its Dockerfiles + patches say how each cc1 is built) |
| ghidra_psx_ldr | R1.2-001; its PsyQ signatures identified the libraries (1.2) | 4 docs | **core** |
| vanilla gcc source of the pinned compiler | — (pin is 2.95.2) | **292 citations** (`tools/reference/gcc-2.7.2`) | **added**, optional per pin: `gcc-2.7.2-src`, `gcc-2.95.2-src` |
| pcsx-redux | R1.2-001 (the docs site, 4 pages), and psyq-obj-parser in 1.9 T4 (2026-10-24) | psyq-obj-parser, 20 files | parser **optional** (with a byo SDK); docs site a **link** |
| sotn-decomp | R1.3-002 (overlay configs) | P36 (style, GTE header) | **optional**, with a trap |
| psy-k | 1.9 T4, the SDK leg (2026-10-24) | 0 | **optional** (with a byo SDK) |
| psy-q-decomp | 0 | 0 | **optional** (the only open per-version source when no SDK is supplied) |
| psx-spx | 0 | 1 (hardware reference) | **optional** |
| PsyQ SDK (byo) | — | runtime library 4.2, 4.6 libs, 4.0 sample source | **byo**, version-matched to the stamps |
| psyz (2 rows) | 0 (only as mmx4's PC-port submodule) | 0 | **dropped** |
| PSn00bSDK | 0 | 0 | **dropped** (its API is not PsyQ's: a contradiction risk) |
| m2c | used as a tool (26 files), never read | used as a tool | **dropped** (installed as a tool anyway) |
| psxrecomp | ideas only | 1 | **dropped** (kept in ECOSYSTEM.md) |
| decomp.me · decomp.dev · TCRF · Redump | — · — · L8 · dump check | 7 · 3 · 3 · 1 | **links** |
| psxdev.net | 0 | 0 | **dropped** |

Result: **4 core sources (13 MB, about 9 s)**, 10 optional, 2 byo, 13 links (counted 2026-10-24). Four of the links are exemplar projects. The optional ones take up to 109 MB if
all are fetched (measured 2026-10-12, before `psx-mnd-sym` and `psy-k`). Most of that is the two gcc sources, and a project needs only its pin's.

decomp.dev is a research source too, not a fetched row. `scripts/decompdev.py lookup --title T [--serial S]` lists
its matching projects from the read API: repository, version, measures, last commit. Each is dated like any S3 lead.
GitHub is the other one. `scripts/ghsearch.py --title T [--serial S] [--exe E]` lists repositories named after the
game. With GitHub auth it also lists files that cite its serial.

Game-specific sources stay out of the profile. S3 adds them per game, as `optional` rows the S4 gate can promote.
Examples: mmx4 for X6; Xenogears, FF7, Vagrant Story and Tomba decomps were BFM's compiler precedents.

## Contradictions: which source wins, and the traps already paid for

`[[authority]]` and `[[trap]]` (what, evidence, do) live only in
[`profiles/psx/refs.toml`](../profiles/psx/refs.toml). The generated `docs/ops/refs.md` renders both in each game repo.

Not checked: pairwise content contradictions inside the core four. They cover disjoint topics: splitter, assembler
shim, compiler builds, loader signatures. Also not checked: psy-q-decomp against a byo SDK. That needs the SDK and is
a game repo's phase 1.2 check.

## Sourcing PsyQ (policy, 2026-10-01; not legal advice)

- **Instructions only.** PsyQ is Sony's and never distributed. The game repo names the release (`config/psxdecomp.toml
  [psyq]`, from [`psyq.toml`](../profiles/psx/psyq.toml)). The developer supplies a copy in `tools/psyq/` or
  outside the repository (`PSXDECOMP_BYO_PSYQ_PATH`, checked by the doctor's `sdk` row). Git ignores `tools/psyq/`
  and the firewall purges it.
- **No PsyQ URL and no downloader** in any file. **Never a source:** mkst/esa releases, FoxdieTeam/psyq_sdk,
  persona-psx `lib/psyq`, psx.arthus.net, fuerchter/psyq-3.0-converted, the PsyQ archives of Xeeynamo/psyz's
  `requirements` release, and the prebuilt objects that chrono-cross-decomp downloads.
- **The default path needs no PsyQ binary:** decompals/old-gcc plus maspsx, as sotn-decomp does.
- **A hash-only manifest pins the SDK version** (since 2026-10-24). Its format and its check are in
  [floor.md](../profiles/psx/floor.md), The SDK leg.
- **The firewall is unchanged.** Only the build uses the SDK. An SDK leg converts it in the build
  ([ECOSYSTEM.md](ECOSYSTEM.md), K38), and no SDK byte enters git.

## Oracle builds (policy, 2026-10-13, not legal advice)

An oracle build is another build of the same program that carries more than the target: symbols, a link map, source
file names. Of the PS1 projects read on 2026-10-13, the ones with such a build took names, function boundaries and
types from it. S2 scans the developer's own disc for one (`medium.json` `debug_artifacts`). S3's **builds** question
searches for the others, and the S4 gate asks the developer.

- **Instructions only.** A build is the publisher's and never distributed. Its reference class is `byo` (the
  `oracle-build` row). The developer supplies a copy (`PSXDECOMP_BYO_ORACLE_PATH`), and no tracked file holds its path.
- **Ignored image, committed checksums.** A copy lies in the game's ignored `disks/builds/<id>/`, or outside the
  repository. Git ignores the image, and the project commits only a checksum file for each build id. Six projects
  read on 2026-10-13 do the same: zeldaret/oot and mm, Xeeynamo/sotn-decomp, celophi/lom-decomp,
  sushi-shi/kings-field-2-decomp and TOMB5/TOMB5. In split mode the developer adds the checksum files to
  `config/public-paths.txt`.
- **Where the rest is written.** The id, the checksum file and the commands: `scripts/oracle.py` (its docstring),
  and "Other builds of the game" in the game's `docs/ops/psxdecomp-floor.md`. The firewall's lines for a debug file:
  `common.FIREWALL_DEBUG`.
- **A local path, and no `.env` file.** The path of a copy lies in the git directory of the clone
  (`psxdecomp/local.toml`). A path with a space breaks Make and a sourced shell file, and no tool here reads a
  `.env` file.
- **No symbol dump as text.** The text of a symbol file is a file of the build, whatever tool wrote it. A hash and
  a path rule do not see it. No check of psxdecomp reads for it ([ECOSYSTEM.md](ECOSYSTEM.md), K35).
  `docs/ops/psxdecomp-floor.md` states the rule.
- **Pages only.** A scout reads the page that describes a build. It fetches no disc image, no symbol file and no
  patch. No committed file holds a download URL for one.
- **archive.org: the check-out rule.** An agent searches archive.org through its metadata API and reads metadata only.
  1. An item counts only when a second source confirms it. The build's page is that source. It states the hash of
     one of the item's files, or it links to the item. The collection and the uploader prove nothing.
  2. A ROM set, a Redump mirror and a retail image never count.
  3. The developer downloads. The agent never does.
  4. `psxd oracle add --id <id> --path <path> --expect <sha1>` checks a supplied copy against the hashes that the
     build's page states, before anything else reads it. It refuses a copy with no matching file.
  5. A document item (a manual, a guide book) becomes a `link` row under the same confirmation.
- **Where an item is named.** Only the gate's question and the scout's report under the ignored `.run/` hold an
  item's identifier. S10 refuses to commit when a tracked file holds one.
- **Any checked build, one at the gate.** The gate asks for the best-ranked build, with symbols or without: a
  prototype, a review build, another revision. A later copy goes through `psxd oracle add`, under its own id.
- **Never a source:** leaked source code and SDK internals. celophi/lom-decomp and abelbriggs1/tm1_decomp state the
  same rule in their READMEs.
- **A build speaks for itself only.** A name moves to the target after a byte check of the function body at both
  addresses. Until then it is a lead. The order of sources and the trap live in the profile's file, like every other.
- **A share is a measure, not a class.** `psxd oracle measure` maps the build's executable onto the target's. The
  method is `scripts/img.py` (its docstring, "map"). It prints the share of the target's words that the build holds,
  with two floors. The floors (2026-10-14, three PsyQ games, four builds) have two controls. A build against itself
  maps 100%, and its words reversed map 0.1 to 0.2%.
  - An unrelated PsyQ game maps 22 to 25%: the shared SDK.
  - A sister game of the same engine maps 64 to 65%.

  A share under about 30% cannot be told apart from the SDK. From phase 1.5, the census's `game` lane separates two
  builds: another game maps 0.1 to 0.2% there. The record's `class` stays the class that the build's page states.
- **No symbol parser of our own.** `ghidra-psx-ldr` (core) imports a PsyQ symbol file into Ghidra, and `psx-mnd-sym`
  (optional) dumps one to text or to a C header.
- **A site that refuses agents is never fetched live.** tcrf.net is one, with its subdomains (its stated policy,
  read 2026-10-13). It serves an agent a decoy that holds injected instructions. The fact comes from other sources first.
- **The preserved page is the check.** `https://archive.org/wayback/available?url=<page>` finds the page's Wayback
  Machine snapshot. The lead cites it with its timestamp, and its text is untrusted. When the tool refuses the
  snapshot too, its URL goes to the report's "For a person to read" table. No other tool takes its place.

## Classes

| Class | Agents may |
|---|---|
| `adapt` | adapt code with attribution in THIRD_PARTY.md |
| `copyleft` | adapt only into a licence-compatible repo; facts otherwise |
| `facts` | cite facts, never copy text or code |
| `public` | quote freely (none by default; psx-spx moves here once its CC0 is confirmed upstream) |
| `byo` | never fetched; the user gives a local path; the firewall purges it |
| `link` | the index keeps the URL and a summary |

## Lints

`fetch_refs.lint_doc` is the lint (tier 0 and every run); `lint_scope` wants a date or scope by each version or game.
