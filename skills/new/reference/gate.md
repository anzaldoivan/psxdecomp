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

## Writes (only after every group is confirmed)

- `.run/bootstrap/answers.txt` — the confirmed 13 keys plus the extras (`PSXDECOMP_CONSOLE: psx`,
  `PSXDECOMP_PROJECT_NAME`, `PSXDECOMP_REGION_VERSION`, `PSXDECOMP_BYO_PSYQ_PATH` if given), in the shape
  `"$PSXD" answers template` prints; check it with `"$PSXD" answers check .run/bootstrap/answers.txt`. Write
  `COMPILER_FAMILY` bare: the installer adds its dated `Candidate (S4 …)` label (`answers.scope_candidate`).
- `.run/bootstrap/refs.toml` — the confirmed rows; check with
  `"$PSXD" fetch_refs --lint --refs .run/bootstrap/refs.toml`.
- `.run/bootstrap/prior-art.md` — the confirmed table (S10 commits it as `docs/prior-art.md`).

Then `"$PSXD" install mark S4 --target . --note "confirmed: answers, <n> refs rows, <m> leads"`.
