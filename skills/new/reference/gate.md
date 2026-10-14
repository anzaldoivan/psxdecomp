# S4 — the gate

Contents: the view, the PsyQ question, the oracle-build question, the writes.

Nothing installs before this stage ends. Present, in this order, compactly:

1. **The medium**, one line: `medium.json`'s boot exe, serial, PsyQ version, stamp count, track 01 SHA-1, Redump
   match if any. Then one line on other builds: the disc's debug leftovers and the **builds** leads, or "none found".
2. **The prior-art report** — `prior-art.draft.md`'s table (leads, licence, class, status, how to verify) and its
   conventions table. A community decompilation of this game may exist. Then its conventions and AI policy are one
   decision: contribute there under its rules, or stay separate and say why.
3. **The drafted answers** — the 13 keys, one line each.
4. **The reference library** — the 4 core sources fetched at S9. Also the rows added to the profile's defaults
   (class, tier, what they cover) and any new `[[trap]]`.

The whole view fits one screen. The game is invented:

<example>

```
Medium: SLUS_000.00 (SLUS-00000), PsyQ 4.0, 212 stamps, track 01 SHA-1 3f2a…c91e, Redump match: yes.
Builds: the disc holds QUEST.SYM (symbols, 412,880 bytes, PsyQ SYM magic). No other build found (3 searches).
Prior art: 3 leads, 1 dead end.
  L1 compiler triple of the sibling game (MIT, adapt, lead) — verify: the 1.4 ladder runs it first
  L2 symbol file for the USA disc (unstated, facts, lead) — verify: 12 addresses land on function starts
  L3 PC port (GPL-3.0, copyleft, lead) — facts only
  Conventions: no community decompilation of this game. Nothing to decide.
Answers: 13 keys drafted. GOAL: every code binary byte-identical from readable C. COMPILER_FAMILY: gcc 2.7.2 era.
References: 4 core sources. Added: example/quest-symbols (facts, optional, the USA disc).
```

</example>

Then AskUserQuestion, at most 4 per round: for each group, `Confirm` (recommended) / `Edit` (the developer types the
change in the notes). Loop until every group is confirmed. Never drop a lead silently: a rejected lead stays in
`prior-art.md` with status `rejected` and the reason.

## The PsyQ question (after S2, in the first round)

Read `medium.json` `psyq.version` and its row in `${CLAUDE_PLUGIN_ROOT}/profiles/psx/psyq.toml` (`aspsx`, `old_gcc`).
Ask one question in the first round, worded from those values. The medium is a probe fact, so its slot is free.
Leave out a field the row has empty:

> Game links PsyQ `<version>` (aspsx `<aspsx>`, old-gcc `<old_gcc>`). The build doesn't need the SDK: the matching
> compilers come from old-gcc. Give a local PsyQ `<version>` path only for reference headers and libs, or `none`.

Options: `none` (recommended), `I'll paste a path`. No stamp or no row: say "the disc names no PsyQ release" and ask
the same with the version left open. A path must lie outside this folder. It is never fetched and never committed (the
firewall purges `tools/psyq/`). Only the answers file under `.run/` holds it.

## The oracle-build question (in the first round, when a build was named)

An oracle build is another build of this program that tells more than the target does. A build with symbols gives
names. A build without them (a prototype, a review build, another revision) gives lineage: what changed and what
stayed. Two places name one: `medium.json` `debug_artifacts` (the developer's own disc) and the **builds** leads of
the report.

When either place has a row, the first round is the prior-art group, the answers group, the PsyQ question
and this question. The reference-library group then moves to the second round. Ask for one build, the best-ranked by
the class table of `investigate.md`:

> Another build of this program exists: `<id>` (`<page>`). It carries `<what>`. Do you have your own copy?

Options: `none`, `I'll paste a path`, `not using it` (the developer types the reason in the notes).

- `<id>` is the lead's id. For a leftover on the developer's own disc, word the question from the probe row: the
  file's path, kind and size. `I'll paste a path` then takes the dump's own path.
- `<what>` is what the build's page states: "symbols", "a debug menu, no symbols", "the code of nine days before the
  master". Promise no names from a build whose page states none.
- A probe row without the PsyQ SYM magic is a lead by its extension only. Say so: a `.MAP` or a `.LIB` is often game
  data.
- When `.run/bootstrap/research/builds.md` lists a checked archive.org item for this build, add one sentence. It
  names the item and the hash that confirmed it, and it says who downloads:

  > archive.org holds it as `<identifier>`: the SHA-1 of `<file>` there equals the one on the build's page. I do not
  > download it. You do, and you paste the path.
- Never fetch a build. Name only a checked item, and only in this question. No file that S10 commits holds the
  identifier or a download link.
- One build is asked for. The others get one line and no question:
  "Also found: `<id>`, `<id>`. For a copy of one later: `psxd oracle add --repo . --id <id> --path <path> --expect <sha1>`."
- A path lies outside this folder, or in its ignored `disks/builds/<id>/`. It is never fetched and never committed.
  The answers file under `.run/` holds it, and S10 registers it in the git directory of the clone.
- With a path, write the lead's id into `PSXDECOMP_BYO_ORACLE_ID`. Write its page into `PSXDECOMP_BYO_ORACLE_PAGE`.
  Write its class into `PSXDECOMP_BYO_ORACLE_CLASS`: `region`, `prototype`, `review`, `debug`, `demo`, `port`,
  `revision` or `sibling`. The dump's own path needs none of the three.
- With a path, write the SHA-1 values that the build's page states into `PSXDECOMP_BYO_ORACLE_SHA1`, separated by
  spaces. S10 hashes the copy before anything else reads it, and it refuses a copy where no file has a stated hash.
  A page that states no hash: leave the key out, and say so in the row.
- Write the answer into the lead's row of `prior-art.md`: `byo path given`, `no copy`, or `rejected` with the reason.
  The row holds the build's id, its page and the stated hashes.

When neither place has a row, ask nothing. Say it in one line, with the searches that ran:

> No other build found: `<n>` searches (`<the seeds>`), and the disc scan found no debug file.

## Writes (only after every group is confirmed)

- `.run/bootstrap/answers.txt` — the confirmed 13 keys plus the extras, in the shape `"$PSXD" answers template` prints.
  The extras: `PSXDECOMP_CONSOLE: psx`, `PSXDECOMP_PROJECT_NAME`, `PSXDECOMP_REGION_VERSION`,
  `PSXDECOMP_BYO_PSYQ_PATH` when the PsyQ question got a path, and the `PSXDECOMP_BYO_ORACLE_*` keys of the
  oracle-build question (`PSXDECOMP_BYO_ORACLE_PATH` first).
  Check it with `"$PSXD" answers check .run/bootstrap/answers.txt`. Write
  `COMPILER_FAMILY` bare: the installer adds its dated `Candidate (S4 …)` label (`answers.scope_candidate`).
- `.run/bootstrap/refs.toml` — the confirmed rows; check with
  `"$PSXD" fetch_refs --lint --refs .run/bootstrap/refs.toml`.
- `.run/bootstrap/prior-art.md` — the confirmed table (S10 commits it as `docs/prior-art.md`).

Then `"$PSXD" install mark S4 --target . --note "confirmed: answers, <n> refs rows, <m> leads"`.
