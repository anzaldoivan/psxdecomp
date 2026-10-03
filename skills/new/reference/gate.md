# S4 — the gate

Nothing installs before this stage ends. Present, in this order, compactly:

1. **The medium** — one line from `medium.json` (boot exe, serial, PsyQ version and stamp count, track 01 SHA-1, and
   the Redump match if any).
2. **The prior-art report** — `prior-art.draft.md`'s table (leads, licence, class, status, how to verify).
3. **The drafted answers** — the 13 keys, one line each.
4. **The reference library** — the 4 core sources fetched at S9, the rows added to the profile's defaults (class,
   tier, what they cover), and any new `[[trap]]`.

Then AskUserQuestion, at most 4 per round: for each group, `Confirm` (recommended) / `Edit` (the developer types the
change in the notes). Loop until every group is confirmed. Never drop a lead silently: a rejected lead stays in
`prior-art.md` with status `rejected` and the reason.

## The PsyQ question (after S2, in the first round)

Read `medium.json` `psyq.version` and its row in `${CLAUDE_PLUGIN_ROOT}/profiles/psx/psyq.toml` (`aspsx`, `old_gcc`).
Ask one question in the first round (the medium is a probe fact, so its slot is free), worded from those values;
leave out a field the row has empty:

> Game links PsyQ `<version>` (aspsx `<aspsx>`, old-gcc `<old_gcc>`). The build doesn't need the SDK: the matching
> compilers come from old-gcc. Give a local PsyQ `<version>` path only for reference headers and libs, or `none`.

Options: `none` (recommended), `I'll paste a path`. No stamp or no row: say "the disc names no PsyQ release" and ask
the same with the version left open. A path must lie outside this folder; it is never fetched, never committed (the
firewall purges `tools/psyq/`), and only the answers file under `.run/` holds it.

## Writes (only after every group is confirmed)

- `.run/bootstrap/answers.txt` — the confirmed 13 keys plus the extras (`PSXDECOMP_CONSOLE: psx`,
  `PSXDECOMP_PROJECT_NAME`, `PSXDECOMP_REGION_VERSION`, `PSXDECOMP_BYO_PSYQ_PATH` when the PsyQ question got a
  path), in the shape
  `"$PSXD" answers template` prints; check it with `"$PSXD" answers check .run/bootstrap/answers.txt`. Write
  `COMPILER_FAMILY` bare: the installer adds its dated `Candidate (S4 …)` label (`answers.scope_candidate`).
- `.run/bootstrap/refs.toml` — the confirmed rows; check with
  `"$PSXD" fetch_refs --lint --refs .run/bootstrap/refs.toml`.
- `.run/bootstrap/prior-art.md` — the confirmed table (S10 commits it as `docs/prior-art.md`).

Then `"$PSXD" install mark S4 --target . --note "confirmed: answers, <n> refs rows, <m> leads"`.
