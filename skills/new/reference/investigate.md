# S3 — investigate

Inputs: the title, region/version and serial (from `.run/bootstrap/interview.json` or `answers.txt`, and
`medium.json` when S2 ran). Seeds: `profiles/psx/profile.toml [research].search_seeds` (fill `{title}`, `{serial}`).

## The six questions — one `scout-web` agent each, launched in parallel in ONE message

1. **existing** — an existing decompilation or disassembly of this game (GitHub, decomp.dev, forums). Before the
   scouts, run `"$PSXD" decompdev lookup --title "<title>" --serial <serial>` (then without `--serial`) and hand the
   result to this agent: decomp.dev's listing with its measures and last commit is a dated fact, not a lead to
   re-find.
2. **siblings** — same developer or engine: sibling decomps and the toolchain they pin (compiler, aspsx, PsyQ
   version). The toolchain of a sibling is the first rung of this game's compiler ladder (e.g. mmx4 for X6; scope: mmx6, 2026-10-01).
3. **maps** — symbol or RAM maps, modding notes, practice hacks, randomizers, Archipelago worlds, cheat code sets, and
   ROM hacks with their documentation (romhacking.net, archive.org, hack source on GitHub). A hack's addresses speak
   for the retail disc only when the hack names the dump it patches (a hash or a Redump id): the lead records that id.
   Hack-only material (the hack's own code, its mod sheets) is out of scope. An unstated licence is class `facts`. A
   lead records the platform and revision it speaks for, checked without a hash where none is given (a PS-EXE header —
   pc0, t_addr, t_size, exe size — or a cheat's code-byte condition against `medium.json`); a lead naming neither, or
   another platform or region, speaks only for that release. Addresses read from a patched disc or its RAM
   (randomizer, Archipelago, practice build) are leads only where the source marks them vanilla. A mod's own build
   settings (its compiler, PsyQ version, linker flags) never enter the 1.4 ladder. Practice, randomizer and
   Archipelago features are never scope: take addresses, names and layout facts only. ROM-hack documents are a
   `--deep` probe only (no replayed project has yet used community RAM addresses for a matching decision): with
   `--deep`, when romhacking.net refuses (403), search archive.org: WebFetch
   `https://archive.org/advancedsearch.php?q="<title>"+AND+(hack+OR+patch+OR+project+OR+addendum+OR+tweaks+OR+documentation+OR+notes)+AND+NOT+mediatype:(movies+OR+audio+OR+etree)&fl[]=identifier&fl[]=title&fl[]=mediatype&rows=50&output=json`,
   then `https://archive.org/metadata/<identifier>` for items whose title names a hack, patch, project or
   documentation; read only text and workbook files, never a disc image, ROM set or patch archive.
4. **ports** — recompilation or port projects (psxrecomp-based, PC ports): facts plus their licence.
5. **versions** — releases, revisions and prototypes (TCRF, Redump): which release to target and why.
6. **sdk** — for the detected SDK stamp (`medium.json psyq.version`): start from its rows in `profiles/psx/psyq.toml`,
   then find matching triples (compiler + aspsx + flags) it lacks and where each was proven.

**GitHub search.** Right after the decomp.dev lookup, run `"$PSXD" ghsearch --title "<title>" --serial "<serial>"
--exe <TARGET_BINARY>`, adding `--exclude "<value>"` (quoted) when `answers.txt` carries `PSXDECOMP_BACKTEST_EXCLUDE`.
It writes `.run/bootstrap/research/github.md`: repositories named after the game (modding work rarely says "decomp")
and, with GitHub auth, files citing the serial. Hand its rows to the **existing**, **maps** and **ports** agents as
starting leads to classify, not to re-search. Scouts read rows through the GitHub API or raw file URLs only: no clone,
no release or off-GitHub download. Each lead names the decision it feeds (load/overlay map 1.2–1.3, RAM or data-symbol
seed, a name for the evidence ladder, the 1.4 ladder, version choice); a row that feeds none goes to Dead ends in one
line, not to Leads. A recomp's seeds and an agent-written research note are leads like any other, never facts. A
repository whose name says "decomp" but whose README describes a port or recompilation is a **ports** lead. A `SKIP`
line is a gap, never a failure: when the file lists **Fallback** URLs (the shell had no network), the **existing**
agent fetches each with WebFetch and applies the filter the file states. In a backtest (`PSXDECOMP_BACKTEST_EXCLUDE`
set), no agent opens, cites or follows those repositories: tell every scout. This includes any page or file that names
those repositories or quotes their documents.

Brief each agent with: the question, the title/serial/region, today's date, the output path
`.run/bootstrap/research/<question>.md`, and "shallow" (default) or "deep" (`--deep`: extended search, more sources).
The agent writes its report and returns ≤ 15 lines.

## Confirming a lead (`scout-repo`)

For each repository lead that would change a decision (a toolchain pin, an address map, a licence), launch one
`scout-repo` agent: a shallow clone into `.run/bootstrap/clones/<name>` (ignored), facts read from its tree (build
files, licence file, symbol counts), report to `.run/bootstrap/research/repo-<name>.md`. With `--deep`, every
repository lead gets one. Never copy code or text from a clone into anything that will be committed.

## Outputs (you write these from the agents' reports)

- `.run/bootstrap/prior-art.draft.md` — the table in `report-template.md`: every lead with source, licence, class,
  status (`lead` unless a probe checked it against `medium.json`), the evidence and **how to verify** (it becomes a
  phase 1.x check).
- `.run/bootstrap/refs.draft.toml` — `profiles/psx/refs.toml` plus a row for each game-specific repository lead
  (class from its licence: MIT/BSD/Apache → `adapt`; GPL/AGPL/MPL → `copyleft`; none, unstated or non-commercial →
  `facts`; a website → `link`), pinned to the commit the scout read, with `tier = "optional"` (the gate may promote
  one to `core`), `when`, `covers` (the game, version and scope it speaks for) and `used_by = "S3 lead <date>"`. Add
  no general-purpose source the profile does not carry: the library is curated from use (docs/REFS.md). If a lead
  contradicts a profile source, write a `[[trap]]` row and say so in the report.
- `.run/bootstrap/answers.draft.txt` — the kit's 13 keys drafted from interview + medium + research
  (`"$PSXD" answers template` for the shape). `COMMUNITY_WORK` lists the leads with their licences, or
  `none found on <date>`. `COMPILER_FAMILY` is a candidate set, never the pin.

Then `"$PSXD" install mark S3 --target . --note "<n> leads, <m> refs rows added"`.
