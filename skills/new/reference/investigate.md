# S3 — investigate

Contents: the eight questions, the classes of a builds lead, confirming a lead, the outputs.

Inputs: the title, region/version and serial (from `.run/bootstrap/interview.json` or `answers.txt`, and
`medium.json` when S2 ran). Seeds: `profiles/psx/profile.toml [research].search_seeds` (fill `{title}`, `{serial}`).

## The eight questions — one `scout-web` agent each, launched in parallel in ONE message

1. **existing** — an existing decompilation or disassembly of this game (GitHub, decomp.dev, forums). Before the
   scouts, run `"$PSXD" decompdev lookup --title "<title>" --serial <serial>`. Then run it without `--serial`. Hand
   the result to this agent. The decomp.dev listing, with its measures and last commit, is a dated fact, not a lead
   to re-find.
2. **siblings** — same developer or engine: sibling decomps and the toolchain they pin (compiler, aspsx, PsyQ
   version). A sibling's toolchain is the first rung of this game's compiler ladder (e.g. mmx4 for X6; scope: mmx6, 2026-10-01).
3. **maps** — symbol or RAM maps, modding notes, practice hacks, randomizers, Archipelago worlds, cheat code sets.
   Also ROM hacks with their documentation (romhacking.net, archive.org, hack source on GitHub). Rules for a lead:
   - A hack's addresses speak for the retail disc only when the hack names the dump it patches (a hash or a Redump
     id). The lead records that id.
   - Hack-only material (the hack's own code, its mod sheets) is out of scope. An unstated licence is class `facts`.
   - A lead records the platform and revision it speaks for. Without a hash, check a PS-EXE header (pc0, t_addr,
     t_size, exe size) or a cheat's code-byte condition against `medium.json`.
   - A lead that names neither, or another platform or region, speaks only for that release.
   - Addresses read from a patched disc or its RAM (randomizer, Archipelago, practice build) are leads only where
     the source marks them vanilla.
   - A mod's own build settings (its compiler, PsyQ version, linker flags) never enter the 1.4 ladder.
   - Practice, randomizer and Archipelago features are never scope: take addresses, names and layout facts only.
   - ROM-hack documents are a `--deep` probe only: no replayed project has yet used community RAM addresses for a
     matching decision. With `--deep`, when romhacking.net refuses (403), search archive.org. WebFetch
     `https://archive.org/advancedsearch.php?q="<title>"+AND+(hack+OR+patch+OR+project+OR+addendum+OR+tweaks+OR+documentation+OR+notes)+AND+NOT+mediatype:(movies+OR+audio+OR+etree)&fl[]=identifier&fl[]=title&fl[]=mediatype&rows=50&output=json`.
     Then fetch `https://archive.org/metadata/<identifier>` for items whose title names a hack, patch, project or
     documentation. Read only text and workbook files, never a disc image, ROM set or patch archive.
4. **ports** — recompilation or port projects (psxrecomp-based, PC ports): facts plus their licence.
5. **versions** — releases, revisions and prototypes (Redump, Hidden Palace): which release to target and why.
   A build that carries symbols can be the better first target. Weigh it against the release the developer owns.
6. **sdk** — for the detected SDK stamp (`medium.json psyq.version`). Start from its rows in
   `profiles/psx/psyq.toml`. Then find the matching triples (compiler + aspsx + flags) it lacks, and where each was
   proven.
7. **names** — where the game's own words come from. Search for a game wiki, the manual and a strategy guide.
   Symbols in another build belong to question 8. Rules for a lead:
   - A wiki or a manual becomes a `link` row.
   - Each row has `topics = ["names"]` and a `covers` value that names the release it speaks for.
   - A source of names proves no address and no behaviour. It gives the word for a thing that the bytes prove.
   - A name from another release is a lead until an address or a string of this release agrees with it.
8. **builds** — another build of this program that carries more than the target does. Hand the agent the
   `debug_artifacts` rows of `medium.json` as facts: S2 scanned the developer's own disc. The agent searches the
   other classes of the table below, in its order.
   - A lead records the build's id, in the form that the scout's file gives.
   - A lead records what the build carries: names, function boundaries, file layout, types.
   - Its `how to verify` is a byte check. N function bodies are byte-identical at the mapped addresses of both builds.
   - The agent reads pages only. It fetches no disc image, no symbol file and no patch, and it writes no download URL.
   - The agent also searches archive.org, by metadata calls only. The search is
     `https://archive.org/advancedsearch.php?q=<title>+prototype&fl[]=identifier&fl[]=title&fl[]=mediatype&rows=25&output=json`.
     `https://archive.org/metadata/<identifier>` then gives an item's files, their sizes and their SHA-1 values.
   - An item is checked when the build's page confirms it: the page states one of its SHA-1 values, or links to it.
     Skip every ROM set, Redump mirror and retail image. The rule: [docs/REFS.md](../../../docs/REFS.md), "Oracle
     builds".
   - A checked item goes to the report's table `## archive.org items`, with the hash that confirmed it. A document
     item (a manual, a guide book) becomes a `link` row.
   - A lead's row holds the build's date, its page and the hashes that the page states. It holds no identifier.
   - Leaked source code and SDK internals are never a source. Such a find is one line under Dead ends, with that reason.
   - A build is never a `[[ref]]` row of its own. The profile's `oracle-build` row covers it. The page that describes
     it becomes a `link` row.
   - A page that refuses the agent goes to the report's "For a person to read" table.
   - tcrf.net refuses every agent: its live pages are never fetched, and those of `datacrystal.tcrf.net` neither.

**GitHub search.** Right after the decomp.dev lookup, run
`"$PSXD" ghsearch --title "<title>" --serial "<serial>" --exe <TARGET_BINARY>`. Add `--exclude "<value>"` (quoted)
when `answers.txt` carries `PSXDECOMP_BACKTEST_EXCLUDE`. It writes `.run/bootstrap/research/github.md`:

- repositories named after the game (modding work rarely says "decomp");
- with GitHub auth, files citing the serial.

Rules for its rows:

- Hand the rows to the **existing**, **maps** and **ports** agents as starting leads to classify, not to re-search.
- Scouts read rows through the GitHub API or raw file URLs only: no clone, no release or off-GitHub download.
- Each lead names the decision it feeds: load/overlay map 1.2–1.3, RAM or data-symbol seed, a name for the evidence
  ladder, the 1.4 ladder, version choice. A row that feeds none goes to Dead ends in one line, not to Leads.
- A recomp's seeds and an agent-written research note are leads like any other, never facts.
- A repository whose name says "decomp" but whose README describes a port or recompilation is a **ports** lead.
- A `SKIP` line is a gap, never a failure. When the file lists **Fallback** URLs (the shell had no network), the
  **existing** agent fetches each with WebFetch and applies the filter the file states.
- In a backtest (`PSXDECOMP_BACKTEST_EXCLUDE` set), no agent opens, cites or follows those repositories: tell every
  scout. This includes any page or file that names those repositories or quotes their documents.

One search row sorted three ways. The game and the repositories are invented:

<example>

```
github.md row: example/quest-pc | GPL-3.0 | 2026-01-10 | name | "Example Quest decompilation" | —
  README: "a native PC port built from recompiled MIPS". It is a port, so it goes to the ports agent, not to existing.
github.md row: example/quest-symbols | unstated | 2025-11-02 | serial | "symbol names for the USA disc" | symbols.us.txt
  It feeds a decision (a name for the evidence ladder, phase 1.2): a lead for the maps agent, class from its licence.
github.md row: example/quest-fan-art | CC-BY-4.0 | 2024-03-09 | name | "fan art" | —
  It feeds no decision: one line under Dead ends.
```

</example>

The classes of a **builds** lead, best first (the projects' READMEs, read 2026-10-13):

| Class | It carries | Who used one |
|---|---|---|
| the target disc itself (`debug_artifacts`) | names, boundaries, types, file layout | Caesar0007/NFSHS-PSX-decomp: a symbol file on the retail disc |
| another region's retail disc | the same, for that region's build | diabpsx/psx_decomp: the Japanese disc |
| a prototype or a review build | the same, for an earlier build | FedericoMilesi/soul-re: a prototype built two weeks before release |
| a debug build | names and types | OpenDriver2/REDRIVER2, TOMB5/TOMB5 |
| a demo disc | often an earlier build of the same code | no project read so far |
| a port to another platform | names and structure, never addresses | Xeeynamo/sotn-decomp: PSP and Saturn builds beside the PS1 target |
| a sibling game's symbols | library and engine names | diabpsx/psx_decomp: library names from a sibling game's PC beta |
| regional releases as lineage witnesses | dates, and the age of the SDK | sushi-shi/kings-field-2-decomp: RCS id strings date the SDK |

Which source wins for a name, and the trap of a prototype's addresses: [docs/REFS.md](../../../docs/REFS.md), "Oracle
builds".

Brief each agent with: the question, the title/serial/region, today's date, the output path
`.run/bootstrap/research/<question>.md`, and "shallow" (default) or "deep" (`--deep`: extended search, more sources).
The agent writes its report and returns ≤ 15 lines.

## Confirming a lead (`scout-repo`)

For each repository lead that would change a decision (a toolchain pin, an address map, a licence), launch one
`scout-repo` agent. It makes a shallow clone into `.run/bootstrap/clones/<name>` (ignored). It reads facts from the
clone's tree (build files, licence file, symbol counts). It reports to `.run/bootstrap/research/repo-<name>.md`.
With `--deep`, every repository lead gets one. Never copy code or text from a clone into anything that will be
committed.

For an **existing** or **siblings** repository, brief the scout with "conventions" too. What that project writes down
and enforces decides whether work can ever go there. Its rows go to the report's conventions table. The evidence
(scope: PR threads of five decompilations, 2026-10-11): 70 PRs did not merge and gave a reason. 56 of the reasons
were about the change or the process, not the C. 22 of the 70 were the maintainers' own PRs.

## Outputs (you write these from the agents' reports)

- `.run/bootstrap/prior-art.draft.md` — the table in `report-template.md`. Every lead has its source, licence, class,
  status, evidence and **how to verify** (it becomes a phase 1.x check). The status is `lead` unless a probe checked
  it against `medium.json`.
- `.run/bootstrap/refs.draft.toml` — `profiles/psx/refs.toml` plus a row for each game-specific repository lead:
  - class from its licence: MIT/BSD/Apache → `adapt`; GPL/AGPL/MPL → `copyleft`; none, unstated or non-commercial →
    `facts`; a website → `link`;
  - pinned to the commit the scout read;
  - `tier = "optional"` (the gate may promote one to `core`), `when`, `covers` (the game, version and scope it
    speaks for) and `used_by = "S3 lead <date>"`.

  Add no general-purpose source the profile does not carry: the library is curated from use (docs/REFS.md). If a
  lead contradicts a profile source, write a `[[trap]]` row and say so in the report.
- `.run/bootstrap/answers.draft.txt` — the kit's 13 keys drafted from interview + medium + research
  (`"$PSXD" answers template` for the shape). `COMMUNITY_WORK` lists the leads with their licences, or
  `none found on <date>`. `COMPILER_FAMILY` is a candidate set, never the pin.

Then `"$PSXD" install mark S3 --target . --note "<n> leads, <m> refs rows added"`.
