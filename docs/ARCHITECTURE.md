# Architecture

## A bootstrapper, not a runtime

Claude Code ignores `hooks`, `permissionMode` and `mcpServers` in plugin agents, and PA3's agents depend on project
hooks, `tools/launch.py`, `plan_edit.py` and `.claude/pa.json`. So PA3 is installed **into each repository**,
unchanged, by its own installer; the plugin only runs the interview, the investigation, the reference library and the
two pinned installers. After S10 the repository needs nothing from the plugin.

```
/psxdecomp:new (skill, invocation-only)
  ├─ S0 preflight.py ─ S2 identify.py ─ profiles/psx/probes/psx.py      (scripts: deterministic, --self-test each)
  ├─ S1 interview ─ S3 scout-web × 6 + scout-repo ─ S4 gate            (the model: AskUserQuestion, agents)
  ├─ S5 install.py: firewall pack (from the pinned kit's templates) → first commit
  ├─ S6 install.py → PA3's pa_install.py --project --yes  (pinned tag, sha-checked)
  ├─ restart → claude --agent plain → /psxdecomp:new --resume
  ├─ S7 PA3's intake handed the kit's intake.decomp.md                 (PA3's tested path, unchanged)
  ├─ S8 install.py → the kit's install.py --answers (dry run, then run; digest-checked)
  ├─ S9 fetch_refs.py → refs/ (git-ignored, searchable via .ignore) + docs/ops/refs.md (committed)
  └─ S10 doctor.py + config/psxdecomp.toml
```

## Why the restart between S6 and S7

PA3's hooks, agents and settings load at session start, and its intake is tested in a `claude --agent plain`
session. Running the intake in the session that installed PA3 would be an untested path; the restart is one line for
the developer and keeps "don't deviate from the tested PA3 framework" literal.

## Why S5 writes the kit's firewall before PA3

"No game byte in git from the first commit": the first commit is the kit's own firewall pack (the same templates the
kit's S2 writes, byte for byte), proven by its negative control. Two consequences, both handled:

- PA3's installer then appends its `.gitignore` block (with `/.run/*`) after the kit's `!/.run/README.md`. S6 moves
  PA3's block back to the top, restoring the kit's tested order (and the kit's ignore probes pass).
- The kit's S2 finds the four files present and leaves them alone (its own rule), so the end state equals the kit's
  tested install: tier 1 checks every path of mmx6's install record (2026-10-01) exists in the fixture tree.

## Pins and refusals

`compat.toml` is the one record of what was tested (psxrecomp's single-manifest pattern): PA3's tag and commit, the
kit's content digest (the kit is not yet a git repository of its own). `common.resolve_pa3` / `resolve_kit` refuse
anything else; `--force-untested` proceeds and records a deviation in the game repo's `config/psxdecomp.toml`.

## Portability

- The interpreter is resolved per machine (`find_python`: the plugin option, then this interpreter, then the newest
  `python3.N` on PATH) and passed to PA3 (`--python`), replacing a hard-coded Homebrew path.
- Host recipes (`profiles/psx/hosts/`) replace one machine's ops note; S10 copies the matching one into the repo.
- Upstream clones live in the plugin's cache (`$CLAUDE_PLUGIN_DATA`, `$PSXDECOMP_CACHE` or `~/.cache/psxdecomp`), never
  inside a game repository (PA3 treats a repo holding an `*-architect` folder as one to migrate).

## Testing tiers

| Tier | When | What |
|---|---|---|
| 0 | every push | manifests validate; schemas (profile, answers, refs, compat, eval cases); skills invocation-only; links; the repo's own firewall with its control; every script's `--self-test` |
| 1 | every push | `install.py run` on the homebrew fixture: golden tree, a second run changes nothing, the S5 dry run lists what S5 writes, the firewall control fails on the planted blob, a wrong PA3 or kit is refused, resume from every stage, the dump never copied |
| 1b | weekly | the fixture exe: extract → splat split → all-asm build → sha1 equal, in the profile container |
| 2 | manual / pre-release | `claude plugin eval . --ablation none --runs 1` — regex, `tool_used`, `tool_order`, `file_exists` graders only; tag `hygiene` (5 runs, pass^5) proves an agent grepping a poisoned game repo answers the current pin, not stale or kit text, with one `llm` grader on the short answer |
| 3 | per release | `/psxdecomp:new` on a real game with your own dump, stopped at PA3's first planner draft |

Tier 1 needs the kit; until it is published CI skips it with that reason and it runs locally with `$PSXDECOMP_KIT`.
