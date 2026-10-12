# The psxdecomp floor

psxdecomp checks a minimum in every game. The minimum has four parts: a roadmap on the kit's ladder, a small set of
tools, a guard for generated files, and a debt count. This file is the reference for those checks. `/psxdecomp:upgrade` rewrites it.

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

## The tooling rows

`/psxdecomp:doctor` prints these rows. A row that is not due says `WAIT` and names the phase that makes it due.

| Row | Due when | It needs |
|---|---|---|
| `roadmap` | the plan exists | the roadmap checks above |
| `guard` | always | the hook groups in `.claude/settings.json`, and a `config/guard.tsv` that parses |
| `gate` | phase 1.3 is closed | one gate command, and at least one `config/check.*.sha` |
| `toolchain` | phase 1.4 is closed | `docs/ops/compiler-pin.md`, and a `config/toolchain.tsv` with every row at its pin |
| `names` | phase 1.4 is closed | the two ledgers, with no malformed row |
| `debt` | the first C file is in `src/` | a debt baseline that is equal to the tree |
| `progress` | phase 1.9 opens | a workflow that uploads the progress report of each executable |

## The acceptance gate

A game has one command that proves a change. The default is `make verify`.

1. Run the policy checks first: `psxd_floor.py plan`, `debt` and `names`, then `psxd_publish.py lint README.md` and `style`.
2. Run the build with its hash check.
3. Print `VERIFY OK` as the last line, or `VERIFY FAIL: <the command to run>`.

- Name another command in `[floor] gate` of `config/psxdecomp.toml`. A gate of the game's own goes in `[own] gate`.
- psxdecomp delivers no makefile. Each game has targets of its own shape.

## Readability debt

`python3 tools/psxd_floor.py debt` counts ten kinds of debt in the tracked files of `src/` and `include/`. The rule
is `rules/FIN1.md`.

| Kind | It counts |
|---|---|
| `pin` | a register that the source forces: `register ... asm("$n")` |
| `pin-unmarked` | a pin with no `// !FAKE:` reason on its line or on the line above |
| `goto` | a `goto` |
| `offset` | a field read by its offset: an offset cast, `M2C_FIELD(`, or a macro that hides one, at each use |
| `address` | an address with no symbol, outside the address header |
| `macro` | a `#define` whose body holds `{`, `;` or a line continuation |
| `asm` | an assembly file under `src/`, or an inline assembly statement, with no row in `config/asm-evidence.tsv` |
| `placeholder` | a `func_` or `D_` address name that a C file defines |
| `unbased` | any other function that a C file defines, with no accepted row in `config/names.tsv` |
| `struct` | a struct, union or enum body outside `include/` |

- An `INCLUDE_ASM` stub is not debt. The progress report gives it no credit.
- `config/debt-baseline.txt` holds one `<count> <kind> <path>` row for each count above zero.
- The check fails when a count is over its row. It also fails when a row is over its count.
- Run `debt --update` in the commit that changes a count.
- In `mode admit`, `debt --update --admit` accepts a rise and prints it. Use that mode during the campaign.
- `debt --down` switches to `mode down`. A count can then only fall. The switch is one way.
- A `skip <entry>` line takes files out of the count.
- `[debt] address_header` in `config/psxdecomp.toml` names the address header. The default is `include/addr.h`.

## Names and assembly evidence

The rule is `rules/NAME1.md`. `python3 tools/psxd_floor.py names` checks two tab-separated files.

| File | Columns |
|---|---|
| `config/names.tsv` | `kind image scope old_name new_name decision evidence reason` |
| `config/asm-evidence.tsv` | `image symbol path class evidence date` |

- `kind` is `function`, `data`, `type`, `field`, `macro` or `file`.
- `decision` is `accepted`, `provisional` or `rejected`.
- `evidence` is `<class>:<path>:<line>`. `rules/NAME1.md` lists the classes.
- The `class` of an assembly row is `sdk-object`, `hand-asm` or `data-in-text`.
- A function that is only hard to match has no class. It stays a stub.

## Toolchain pins

`python3 tools/psxd_floor.py toolchain` reads `config/toolchain.tsv`. Phase 1.4 writes that file. Its columns are
`name kind pin path`.

- A `git` row passes when the checkout at `path` is at the commit `pin` and has no local change.
- A `sha256` row passes when the file at `path` has the hash `pin`.
- The command runs no tool of the game. A path that is not on this machine is `MISSING`, not a failure.

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
