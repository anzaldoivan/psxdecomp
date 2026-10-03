# The reference library

A small, pinned, greppable set of upstream sources in each game repository, **curated from use**: a source is in the
profile's list because mmx6 or BFM-decomp actually went to it (each row's `used_by` says where). Agents grep it
before going to the web; every row says what it may be used for (its licence class), which version it speaks for
(`covers`), and the index says which source wins when two disagree.

- **`config/refs.toml`** — `[[ref]]` rows (`name`, `url`, `ref` or `sha256`, `licence`, `class`, `tier`, `covers`,
  `topics`, `paths`, `when`, `used_by`, `checked`), `[[authority]]` (per topic: the order of sources and the rule) and
  `[[trap]]` (contradictions a project already paid for).
- **`fetch_refs.py`** fetches the `core` rows into the ignored `refs/<name>/` at their pins (shallow, sparse when
  `paths` is set; archives checked by sha256); `--with <name>` fetches an `optional` row when its `when` holds.
- **`docs/ops/refs.md`** — the committed index: the rows, the authority table, the traps.
- **The rule** (one `HOW_WE_WORK.md` line): grep `refs/` or dispatch `retriever-code`; never Read a `refs/` tree whole;
  the web only for what it lacks. Files, not skills: one index costs nothing until it is used.

## The curation audit (2026-10-01)

Method: every source the projects cited — mmx6's five web-retriever reports (R1.1-001, R1.2-001, R1.3-002, R1.4-001,
R1.6-003) and its tracked files; BFM's tracked docs and its own `tools/reference/` clones — counted and compared
with the first list (13 fetched rows, 37 MB).

| Source | mmx6 | BFM | Verdict |
|---|---|---|---|
| splat | R1.3-002; 216 files | 2 docs | **core** |
| maspsx | R1.3-002, R1.4-001; 43 files | 3 docs | **core** |
| decompals/old-gcc | R1.4-001; 20 files | 4 docs | **core** (its Dockerfiles + patches say how each cc1 is built) |
| ghidra_psx_ldr | R1.2-001; its PsyQ signatures identified the libraries (1.2) | 4 docs | **core** |
| vanilla gcc source of the pinned compiler | — (pin is 2.95.2) | **292 citations** (`tools/reference/gcc-2.7.2`) | **added**, optional per pin: `gcc-2.7.2-src`, `gcc-2.95.2-src` |
| pcsx-redux | R1.2-001 (the docs site, 4 pages) | psyq-obj-parser, 20 files | parser **optional** (with a byo SDK); docs site a **link** |
| sotn-decomp | R1.3-002 (overlay configs) | P36 (style, GTE header) | **optional**, with a trap |
| psy-q-decomp | 0 | 0 | **optional** (the only open per-version source when no SDK is supplied) |
| psx-spx | 0 | 1 (hardware reference) | **optional** |
| PsyQ SDK (byo) | — | runtime library 4.2, 4.6 libs, 4.0 sample source | **byo**, version-matched to the stamps |
| psyz (2 rows) | 0 (only as mmx4's PC-port submodule) | 0 | **dropped** |
| PSn00bSDK | 0 | 0 | **dropped** (its API is not PsyQ's: a contradiction risk) |
| m2c | used as a tool (26 files), never read | used as a tool | **dropped** (installed as a tool anyway) |
| psxrecomp | ideas only | 1 | **dropped** (kept in ECOSYSTEM.md) |
| decomp.me · decomp.dev · TCRF · Redump | — · — · L8 · dump check | 7 · 3 · 3 · 1 | **links** |
| psxdev.net | 0 | 0 | **dropped** |

Result: **4 core sources (13 MB, about 9 s)**; 6 optional (up to 109 MB if all are fetched, mostly the two gcc
sources, of which a project needs only its pin's); 1 byo; 5 links.

decomp.dev is a research source too, not a fetched row: `scripts/decompdev.py lookup --title T [--serial S]` lists its
matching projects (repository, version, measures, last commit) from the read API, dated like any S3 lead. GitHub is
the other one: `scripts/ghsearch.py --title T [--serial S] [--exe E]` lists repositories named after the game (modding
work rarely says "decomp") and, with GitHub auth, files that cite its serial.

Game-specific sources stay out of the profile: S3 adds them per game (mmx4 for X6; Xenogears, FF7, Vagrant Story and
Tomba decomps were BFM's compiler precedents), as `optional` rows the S4 gate can promote.

## Contradictions: which source wins, and the traps already paid for

`[[authority]]` (per topic: the order of sources and the rule) and `[[trap]]` (what, evidence, do) live only in
[`profiles/psx/refs.toml`](../profiles/psx/refs.toml); the generated `docs/ops/refs.md` renders both in each game repo.

Not checked: pairwise content contradictions inside the core four (they cover disjoint topics: splitter, assembler
shim, compiler builds, loader signatures), and psy-q-decomp against a byo SDK (needs the SDK; a game repo's phase 1.2
check).

## Sourcing PsyQ (policy, 2026-10-01; not legal advice)

- **Instructions only.** PsyQ is Sony's and never distributed. The game repo names the release (`config/psxdecomp.toml
  [psyq]`, from [`psyq.toml`](../profiles/psx/psyq.toml)); the developer supplies a copy outside the repository
  (`PSXDECOMP_BYO_PSYQ_PATH`, checked by the doctor's `sdk` row).
- **No PsyQ URL and no downloader** in any file. **Never a source:** mkst/esa releases, FoxdieTeam/psyq_sdk,
  persona-psx `lib/psyq`, psx.arthus.net.
- **The default path needs no PsyQ binary:** decompals/old-gcc plus maspsx, as sotn-decomp does.
- Deferred until a real SDK is in hand: per-version sha256 manifests ([HARVEST](HARVEST.md)).

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
