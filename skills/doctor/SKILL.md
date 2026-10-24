---
name: doctor
description: Check an existing PS1 decomp repository against psxdecomp's tested pins — PA3 version, the kit's install record, the interpreter, the ROM firewall, the reference library. Read-only. Invoked as /psxdecomp:doctor.
disable-model-invocation: true
argument-hint: "[--repo DIR] [--offline] [--only ROW[,ROW]]"
---

# /psxdecomp:doctor

Read-only. Run `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" preflight --target . --resume --dry-run` only if the developer asks
about the machine. Otherwise run:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" doctor --repo . $ARGUMENTS
```

Report the `FAIL` and `WARN` rows, one line each, with the fix each row names. Never fix anything from this skill: it
diagnoses. A `WAIT` row is not due yet. Report it in one line with the phase that makes it due. The rows of the
floor are explained in the game's `docs/ops/psxdecomp-floor.md`.

| Row | Status | What it reads | Fix |
|---|---|---|---|
| `progress` | WAIT, WARN or FAIL (network when a report workflow exists) | A workflow that builds a decomp.dev report: its safety lint, and whether decomp.dev lists the repository. In split mode: the public `[public].repo`. With no workflow that uploads the report: WAIT before phase 1.9, WARN while it is open, FAIL once it is closed | the row names it |
| `github` | WARN only, network | The repository's security settings through `gh api` | the `gh api` command in the row, for the developer to run |
| `github` in split mode | FAIL | Origin, the `-dev`, is not private: dev's history is exposed | make it private |
| `private-repo` | FAIL, network | `<game>-private` breaks a rule: public, forked, Actions on, a writable or second deploy key, another collaborator, a `private_rev` it lacks | the row names it |
| `public-standard` | WARN, network | The public repository's drift from the standard | `settings --apply`, the developer's |
| `dev-ci` | WARN or FAIL, network | The latest push run of each workflow on origin's default branch. WARN: one is red. FAIL: a red job is one of `[public].checks` | a green push on dev before the next release |
| `refs` | WARN | Drift in the reference library | `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" fetch_refs --repo .` |
| `record` | WARN or FAIL | WARN: psxdecomp did not bootstrap the repository, or an `[own]` value names nothing. FAIL: `config/psxdecomp.toml` is not TOML | `/psxdecomp:upgrade`. For a FAIL the developer repairs the typo that the row names |
| `oracle` | WARN or FAIL | The disc scan in the record's `[oracle]`, and the builds of `config/oracle.toml`. No image is hashed. A build that this machine lacks is no warning. FAIL: the firewall does not read a checksum file, a build has no checksum file, or the firewall refuses a registered path | the row names the command. The developer runs it |
| `roadmap` | FAIL, WARN or WAIT | `GENERATION_PLAN.md` against the ladder. FAIL: a broken phase line, or a ladder phase with no line. WAIT: no plan yet | `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" plan --repo .` lists the findings. The planner corrects the plan, never this skill |
| `guard` | FAIL or WARN | A hook group of the profile is not in `.claude/settings.json`, or a line of `config/guard.tsv` is no rule | `/psxdecomp:upgrade` |
| `git-hooks` | WARN or FAIL | The three git hooks that run the gate in this clone. WARN: one is missing, or another hook stands there. FAIL: `core.hooksPath` sends git to a folder with other hooks | `python3 tools/psxd_publish.py hook --install` (the developer runs it) |
| `gate` | WAIT, WARN or FAIL | After phase 1.3: one gate command and the hash files. FAIL once phase 1.9 is closed | a `verify` make target, or `/psxdecomp:upgrade own gate "<command>"` |
| `toolchain` | WAIT or WARN | After phase 1.4: `docs/ops/compiler-pin.md`, and `config/toolchain.tsv` with every row at its pin | the row names it |
| `names` | WAIT, WARN or FAIL | After phase 1.4: the two ledgers. FAIL: a file that is no table, or an assembly row that points at nothing. WARN: a ledger is absent | `python3 tools/psxd_floor.py names` |
| `debt` | WAIT, WARN or FAIL | From the first C file: the debt baseline is equal to the tree. FAIL: a rise, a stale row, or a kind with no policy line. WARN: a version 1 baseline | `python3 tools/psxd_floor.py debt`, then `debt --update` (it refuses a rise of a kind in mode `down`) |
| `cpp` | WAIT, WARN or FAIL | After phase 1.4: `[floor] cpp` of the record, the preprocess command of the game. WARN: none, so pins, gotos and assembly are read in raw text. FAIL: the command does not run on this machine | the developer adds the key (the row gives the form) |
| `readme` | FAIL | A README lint failure. The standard: `docs/PUBLISHING.md` in the plugin | the row names it; the generated blocks: `python3 tools/psxd_publish.py render README.md --write` |
| `card` | WARN only | `HOW_WE_WORK.md` is over PA3's cap | move a section to `docs/ops/` and link it |
| `pa3-retired` | WAIT or WARN, never FAIL | The tracked text that names a PA3 name 3.24 or 3.25 removed (the list is psxdecomp's `common.PA3_RETIRED`: old commands, agents and scripts). PA3's own files and `phase-ends/` are not read. `PROJECT_CONTEXT.md` is frozen: named, not counted. WAIT: PA3 is older than 3.24 | after PA3's update, rewrite each named file's lines to the names PA3 now uses. The developer or a plan task does it, never this skill |

- A `WAIT` row never fails the run. The last line counts the rows that are not due.
- `--offline` skips the network rows. Their rows say `SKIP`: a check that did not run is never `OK`. The last line
  counts them.
- `--only github` runs just that row. A name that is no row exits 2 and lists the rows.
- `--json` prints the rows alone on stdout.
