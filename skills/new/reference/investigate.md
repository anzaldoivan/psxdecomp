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
3. **maps** — symbol or RAM maps, modding notes, practice hacks, randomizers, Archipelago worlds, cheat code sets.
4. **ports** — recompilation or port projects (psxrecomp-based, PC ports): facts plus their licence.
5. **versions** — releases, revisions and prototypes (TCRF, Redump): which release to target and why.
6. **sdk** — for the detected SDK stamp (`medium.json psyq.version`): start from its rows in `profiles/psx/psyq.toml`,
   then find matching triples (compiler + aspsx + flags) it lacks and where each was proven.

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
