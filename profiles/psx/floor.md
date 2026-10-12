# The psxdecomp floor

psxdecomp checks a minimum in every game. The minimum is a roadmap on the kit's ladder, a small set of tools, and a
guard for generated and frozen files. This file is the reference for those checks. `/psxdecomp:upgrade` rewrites it.

## After the bootstrap

1. Start a bare `claude` session in the repository. Project Architect's planner drafts `GENERATION_PLAN.md`.
2. Read the draft against the ladder in "Numbering". Approve it only when each ladder phase has a line.
3. Run `python3 tools/psxd_floor.py plan`. Have the planner correct each `FAIL` before the first phase starts.
4. Let the router run one approved phase at a time. A phase closes when its `verified by:` commands pass.
5. Run `/psxdecomp:doctor` when a phase closes. A `WAIT` row names the phase that makes it due.
6. Read `docs/prior-art.md` before phase 1.2. Read `docs/ops/refs.md` before phase 1.4.
7. Record a game wiki or a manual as a `link` row in `config/refs.toml`. A name needs a source.

## Numbering

- Phase `1.n` is ladder phase n. The ladder has eleven phases, 0 to 10.
- A slice of phase n is `1.n.m`. The slices `1.8.1` and `1.8.2` are two parts of the campaign.
- Never renumber an id. Rules, markers and phase records cite it.
- A plan that merges or drops a ladder phase says so in a `## Changes` line that names the id.
- A later generation numbers its phases `2.n`. `phase-ends/GenerationEnd_1.md` then holds the ladder of generation 1.

| Phase | Ladder name | Words that the milestone keeps |
|---|---|---|
| 1.0 | Governance and the firewall | |
| 1.1 | Deterministic extraction with a committed manifest | |
| 1.2 | The oracles and the load map | |
| 1.3 | The all-assembly byte-identical baseline | `N of N` |
| 1.4 | The compiler pinned by evidence | |
| 1.5 | The honest census and the differential harness | |
| 1.6 | The multipliers | |
| 1.7 | The codegen map and the permuter | |
| 1.8 | First cracks, the manual wave, the routing cliff | `0 stubs` |
| 1.9 | Publish | |
| 1.10 | Readability | `format-check` |

## The roadmap checks

`python3 tools/psxd_floor.py plan` reads `GENERATION_PLAN.md` and writes nothing. The doctor's `roadmap` row runs the
same checks. A `FAIL` fails the doctor.

| Check | Level | The finding |
|---|---|---|
| `grammar` | FAIL | A phase line lacks one of its five keys, repeats an id, or depends on an id with no line. |
| `ladder` | FAIL | A ladder phase has no line, no slice, and no `## Changes` line that names it. |
| `numbering` | WARN | An id is over `1.10` and no `## Changes` line names it. Or a line holds the name of another phase. |
| `frozen` | WARN | The milestone of a closed phase differs from its text at the commit that closed it. |
| `criteria` | WARN | The `Done-criteria:` line is gone, or a milestone lost its words in the table above. |
| `paths` | WARN | A closed phase names a phase-end file or a repository path that does not exist. |
| `markers` | WARN | A tracked file holds `TODO(phase-N)` and phase `1.N` is closed. |

psxdecomp never writes the plan. The planner corrects a finding in an open phase. For a closed phase, record the
correction with `python3 tools/plan_edit.py append-change`, and leave the milestone as it closed.

## The guard

`.claude/settings.json` runs `python3 tools/psxd_floor.py guard --hook` before each Bash, Edit and Write call. The
hook reads `config/guard.tsv`. psxdecomp writes that file once. After that it is the game's own.

| Column | Value |
|---|---|
| `action` | `deny` or `allow`. The first row that matches a call decides. |
| `tool` | `bash` or `path`. |
| `pattern` | For `bash`, a regular expression that the hook searches in the command. For `path`, an entry in the syntax of `config/public-paths.txt`. |
| `say` | The text that the session reads when the hook refuses the call. Name the command to run in its place. |

- The hook never stops a call by accident. A missing file, a bad row or bad input lets the call run.
- The default rows refuse an edit of `asm/`, of the hash files and of the two baselines.
- `.claude/settings.json` also holds an `Edit(...)` deny rule for each of those paths. It stops a shell redirection too.
- Add a row when a session must not run a command raw, such as a new split. The file holds two examples.

## A tool of the game's own

A game can hold its own tool in place of a psxdecomp delivery. Record it in `[own]` of `config/psxdecomp.toml`.
psxdecomp then delivers nothing for that key, and the doctor checks that the path exists.

| Key | It replaces |
|---|---|
| `debt` | the readability debt baseline |
| `names` | the names ledger |
| `gate` | the acceptance gate command |
| `toolchain` | the toolchain pin table |
| `campaign` | the campaign templates |
| `matcher` | the offered matcher skill |

`/psxdecomp:upgrade` proposes a key when it finds a path that it knows. The developer records any other one with
`upgrade own <key> "<path or command>"`.
