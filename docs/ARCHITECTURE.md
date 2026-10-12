# Architecture

## A bootstrapper, not a runtime

Claude Code ignores `hooks`, `permissionMode` and `mcpServers` in plugin agents. PA3's agents depend on project
hooks, `tools/launch.py`, `plan_edit.py` and `.claude/pa.json`. So PA3's own installer installs PA3 **into each
repository**, unchanged. The plugin runs only the interview, the investigation, the reference library and the two
pinned installers. After S10 the repository needs nothing from the plugin.

```
/psxdecomp:new (skill, invocation-only)
  ├─ S0 preflight.py ─ S2 identify.py ─ profiles/psx/probes/psx.py      (scripts: deterministic, --self-test each)
  ├─ S1 interview ─ S3 decompdev.py + ghsearch.py → scout-web × 7 + scout-repo ─ S4 gate   (the model: AskUserQuestion, agents)
  ├─ S5 install.py: firewall pack (from the pinned kit's templates) → first commit
  ├─ S6 install.py → PA3's pa_install.py --project --yes  (pinned tag, sha-checked); pa.json "upgrade": "ask"
  ├─ restart → claude --agent plain → /psxdecomp:new --resume       (hooks/hooks.json repeats it at session start)
  ├─ S7 PA3's intake handed the kit's intake.decomp.md                 (PA3's tested path, unchanged)
  ├─ S8 install.py → the kit's install.py --answers (dry run, then run; digest-checked) + the README standard
  ├─ S9 fetch_refs.py → refs/ (git-ignored, searchable via .ignore) + docs/ops/refs.md (committed)
  └─ S10 doctor.py + config/psxdecomp.toml + tools/psxd_publish.py (the README lint, vendored; its CI)
         + tools/psxd_floor.py (the floor, vendored: roadmap lint, debt baseline, guard hook) + docs/ops/psxdecomp-floor.md
```

A game may also run in split mode: a public trunk, a private `-dev` workspace and a private `-private` store for the
game files. It is opt-in through `[public]` and `config/public-paths.txt`, which the bootstrap does not write;
`/psxdecomp:upgrade` then adds the public `build.yml` ([docs/PUBLISHING.md](PUBLISHING.md#split-mode-a-public-trunk-a-private-workspace-a-private-store)).

## Why the restart between S6 and S7

PA3's hooks, agents and settings load at session start, and its intake is tested in a `claude --agent plain`
session. Running the intake in the session that installed PA3 would be an untested path. The restart is one line for
the developer, and it keeps "don't deviate from the tested PA3 framework" literal.

The line is not left to the model. S6's `DONE` line carries all of it. The plugin's `SessionStart` hook
(`scripts/resume_hint.py`) prints it whenever a session opens on a bootstrap whose next stage is S7. A bare `claude`
opens PA3's router, because PA3's installer merges `"agent": "pa-session"` into `.claude/settings.json`. There is no
flag for "no agent", so `claude --agent plain` is the way past it. A per-project opt-out is proposed upstream: P1 in
[ECOSYSTEM.md](ECOSYSTEM.md#proposed-to-upstreams).

## Why the PA3 pin holds after the install

`resolve_pa3` checks the pin only while it installs. Two PA3 defaults would move a machine off it afterwards:

- A `--root` install without `--no-clone` clones PA3's upstream default branch and follows it. S6's `--root` hint
  carries `--no-clone`.
- A `.claude/pa.json` without `"upgrade"` means auto, so the router upgrades before its first task. S6 writes
  `"upgrade": "ask"` (recorded in `config/psxdecomp.toml [pa3]`).

The doctor's `pa3-drift` row WARNs on either drift.

## Why S5 writes the kit's firewall before PA3

"No game byte in git from the first commit": the first commit is the kit's own firewall pack. It holds the same
templates the kit's S2 writes, byte for byte, and its negative control proves it. Two consequences, both handled:

- PA3's installer then appends its `.gitignore` block (with `/.run/*`) after the kit's `!/.run/README.md`. S6 moves
  PA3's block back to the top, restoring the kit's tested order (and the kit's ignore probes pass).
- The kit's S2 finds the four files present and leaves them alone (its own rule). So the end state equals the kit's
  tested install. Tier 1 checks that every path of mmx6's install record (2026-10-01) exists in the fixture tree.

## Pins and refusals

`compat.toml` is the one record of what was tested (psxrecomp's single-manifest pattern). It holds PA3's tag and
commit and the kit's content digest: the kit is not yet a git repository of its own. `common.resolve_pa3` and
`resolve_kit` refuse anything else. `--force-untested` proceeds and records a deviation in the game repo's
`config/psxdecomp.toml`.

## Portability

- `find_python` resolves the interpreter per machine: the plugin option, then this interpreter, then the newest
  `python3.N` on PATH. The installer passes it to PA3 (`--python`), in place of a hard-coded Homebrew path.
- Host recipes (`profiles/psx/hosts/`) replace one machine's ops note; S10 copies the matching one into the repo.
- Upstream clones live in the plugin's cache (`$CLAUDE_PLUGIN_DATA`, `$PSXDECOMP_CACHE` or `~/.cache/psxdecomp`), never
  inside a game repository. PA3 treats a repo holding an `*-architect` folder as one to migrate.

## Testing tiers

| Tier | When | What |
|---|---|---|
| 0 | every push | Manifests validate. Schemas hold: profile, answers, refs, compat, eval cases. Skills are invocation-only. Links resolve. The repo's own firewall passes with its control. Every script's `--self-test` passes, and the writing count does not rise (`tests/golden/style.txt`) |
| 1 | every push | `install.py run` on the homebrew fixture: the tree equals the golden tree, and a second run changes nothing. The S5 dry run lists what S5 writes. The firewall control fails on the planted blob. A wrong PA3 or kit is refused. Every stage resumes, and so does an S10 that failed. The dump is never copied |
| 1b | weekly | the fixture exe: extract → splat split → all-asm build → sha1 equal, in the profile container |
| 1c | every push | split mode end to end on the fixture (`tests/test_split_e2e.py`) |
| 2 | manual / pre-release | `claude plugin eval . --ablation none --runs 1`. Graders: regex, `tool_used`, `tool_order`, `file_exists` only. Tag `hygiene` (5 runs, pass^5) proves that an agent grepping a poisoned game repo answers the current pin, not stale or kit text. It has one `llm` grader on the short answer. `s7-ladder` runs the real intake and reads the eleven ladder phases in the constitution |
| 3 | per release | `/psxdecomp:new` on a real game with your own dump, stopped at PA3's first planner draft |
| 4a | every push | With tiers 0 and 1: the bytes a session loads before it does anything match `tests/golden/always-loaded*.txt`, so growth is a reviewed diff. The plugin's bytes: `AGENTS.md`, agent descriptions, the hook and any skill Claude may invoke on its own. The fixture repo's bytes: `CLAUDE.md`, the card, settings, agents, skills and the hook |
| 4b | manual / pre-release | `BASE=<revision> tools/ab_agents.sh` runs the working tree against that revision on fixed questions. It scores correctness, cost and tokens. The tree is kept while it is at least as correct at no more than +20% cost |
| 5a | weekly | The C corpus (`fixtures/c-corpus/run.sh`): our own small functions, compiled with two candidate compilers in a fixture-owned image layer. Every truth matches itself and no truth is flagged. Every mutant fails. Every fake twin matches and is flagged: pin, `goto`, offset cast, own type, other symbol, bare address. Its host half (the lint and the mutation rule) runs with tier 0 |

Tier 1 fetches the kit at its `compat.toml` pin (cached by the pins in CI); `$PSXDECOMP_KIT` substitutes a local copy.
