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
- A plan that merges or drops a ladder phase says so in a `## Changes` line. The line names the id and holds the word
  `merge` or `drop`. A line that only mentions the id answers nothing.
- An id over `1.10` is not a slice. A plan that has one keeps it. A `## Changes` line that names the id and says
  `ladder phase n` makes it a part of phase n. Phase n then stays open while that part is open.
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
| `grammar` | FAIL | A phase line lacks one of its five keys, repeats an id, or depends on an id with no line. A milestone that holds the separator of the fields is cut there. That finding is a WARN. |
| `ladder` | FAIL | A ladder phase has no line, no slice, and no `## Changes` line that merges or drops it. |
| `numbering` | WARN | An id is over `1.10` and no `## Changes` line names it. Or a line holds the name of another phase. |
| `frozen` | WARN | The milestone of a closed phase differs from its text at the commit that closed it. |
| `criteria` | WARN | The `Done-criteria:` line is gone, or a milestone lost its words in the table above. |
| `paths` | WARN | A closed phase names a phase-end file that does not exist. Or its milestone names a missing path under a tracked folder, and no `## Changes` line names the phase. |
| `markers` | WARN | A tracked file holds `TODO(phase-N)` and phase `1.N` is closed. |

psxdecomp never writes the plan. The planner corrects a finding in an open phase. For a closed phase, leave the
milestone as it closed and record the correction in the `## Changes` section of the plan. Name the id in the text:

    python3 tools/plan_edit.py --file GENERATION_PLAN.md append-change --by developer "correction to 1.3 (closed): <text>"

Without `--file GENERATION_PLAN.md` that tool writes to the phase plan, and the finding stays.

## The guard

`.claude/settings.json` runs `python3 tools/psxd_floor.py guard --hook` before each Bash call and each call that
edits a file. The hook reads `config/guard.tsv`. psxdecomp writes that file once. After that it is the game's own.

| Column | Value |
|---|---|
| `action` | `deny` or `allow`. The first row that matches a call decides. |
| `tool` | `bash` or `path`. |
| `pattern` | For `bash`, a regular expression that the hook searches in the command. For `path`, an entry in the syntax of `config/public-paths.txt`. |
| `say` | The text that the session reads when the hook refuses the call. Name the command to run in its place. |

- The hook never stops a call by accident. A missing file, a bad row or bad input lets the call run. A pattern that
  runs for 5 seconds lets the call run too.
- The hook reads the rules of the checkout that the call changes. A linked worktree is guarded by its own copy.
- The `guard` row of the doctor fails on a `bash` pattern that matches the empty command. Such a pattern refuses
  every command.
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
| `debt` | the first C file is in `src/`, or the first count | a debt baseline that is equal to the tree |
| `progress` | phase 1.9 opens | a workflow that uploads the progress report of each executable |

## The acceptance gate

A game has one command that proves a change. The default is `make verify`.

1. Run the policy checks first: `psxd_floor.py plan`, `debt` and `names`, then `psxd_publish.py lint README.md` and `style`.
2. Run the build with its hash check.
3. Print `VERIFY OK` as the last line, or `VERIFY FAIL: <the command to run>`.

- Name another command in `[floor] gate` of `config/psxdecomp.toml`. A gate of the game's own goes in `[own] gate`.
  That key answers the `gate` row of the doctor, and the game's gate then holds its own hashes.
- psxdecomp delivers no makefile. Each game has targets of its own shape.

## The gate of the floor

`python3 tools/psxd_floor.py gate` runs the checks of this file in one command. Each finding is a line
`GATE FAIL <check>: <detail>`. The last line is `GATE OK` or `GATE FAIL`.

| Mode | It judges | Against |
|---|---|---|
| `--staged` | the index | `HEAD` |
| `--bank` | the work tree, with the files that git does not track yet | `HEAD` |
| `--ci <base>..<head>` | each commit of the range, then the head of the range | the parent of each commit, then the base of the range |
| `--push` | the same as `--ci` | the same as `--ci` |

- The gate judges a change against a tree that the change cannot rewrite. An edited baseline or tool decides nothing.
- `--bank` writes the rows of the baseline when the change is admitted. A bank tool calls it before the commit.
- `--bank` and `--push` also run the check of the game, `[floor] gate` or `[own] gate`.
- The checks are `policy`, `debt`, `trials`, `protected`, `style`, `names`, `own-debt`, `plan`, `toolchain`, `readme` and `categories`.
- `protected` covers the files that carry the floor. The first are the two tools and the workflows.
- It also covers the hooks and the deny rules of `.claude/settings.json`, and the `deny` rows of `config/guard.tsv`.
- It also covers each check that the record names in `[own]`, `[trial]`, `[floor]` or `[debt]`.
- A new key in one of those four tables is a protected change. A file that a `skip` line covers keeps its bytes.
- `--ci` judges a commit with no parent against the base of the range. A base that names no commit fails.
- A tool changes only to a later version. The new tool then judges the tree.
- The developer allows one protected change with `debt --raise protected <n> --reason <text>`.
- That line also allows a change of the policy, such as a new `skip` line.
- A merge passes when it passes against each parent.

Three git hooks run the gate in each clone. `python3 tools/psxd_publish.py hook --install` writes them.

| Hook | It runs | With the tools of |
|---|---|---|
| `pre-commit`, `pre-merge-commit` | `gate --staged` | `HEAD` |
| `pre-push` | `gate --push` for each branch that the push updates | the commit that the remote holds |

- A hook copies the tools into a temporary folder and runs them there. The copies of the change decide nothing.
- A hook is no tracked file. The bootstrap and `/psxdecomp:upgrade` write the hooks, and never over another hook.
- `pre-push` asks at the terminal for each `raise` line and each assembly row that the push adds.
- With no terminal, the answer is no. An agent session never pushes.
- `pre-push` then runs the new trial rows again, and ten older rows. The branch must be checked out for that.
- `pre-push` works in split mode and outside it.

## Readability debt

`python3 tools/psxd_floor.py debt` counts the debt of each tracked file with a C or an assembly suffix. The rule
is `rules/FIN1.md`.

| Kind | It counts |
|---|---|
| `pin` | a register that the source forces: `register ... asm("$n")`, also with `__asm__` or `__asm` |
| `pin-unmarked` | a pin with no `// !FAKE: <reason>` comment of its own |
| `goto` | the word `goto` wherever it stands, or a macro that hides one, at each use. Only `goto label;` can carry a marker. |
| `goto-unmarked` | a `goto` with no `// !FAKE: <reason>` comment of its own |
| `barrier` | an empty assembly statement, `__asm__("")` |
| `barrier-unmarked` | a barrier with no `// !FAKE: <reason>` comment of its own |
| `offset` | a field read by its offset: `*(T *)(p + N)`, `((T *)p)[N]`, `M2C_FIELD(`, or a byte pointer plus a number, each also with a minus. A macro that hides one counts at each use. |
| `address` | a literal in the address ranges of the console with no symbol, or a macro that hides one, outside the address header |
| `cast` | an integer made of a pointer, or a pointer made of an integer: `(s32)&x`, `(T *)(s32)x`, also with `u_long`, `u_int` and `u_short` |
| `field` | a name such as `unk_10` or `field_0x10`: a field with an offset and no name |
| `macro` | a `#define` whose body holds `{`, `;` or a line continuation |
| `asm` | an assembly file, an inline assembly statement, the word `asm` in any other place, or a macro that holds one, with no row in `config/asm-evidence.tsv` |
| `obscured` | text that hides code from the tool: a statement outside each function body that the tool sees, or a line continuation outside a directive. A digraph for a brace, a `##` paste and a source behind a symbolic link count too. |
| `placeholder` | a `func_` or `D_` address name that a C file defines, also `FUN_`, `DAT_`, `sub_` and `loc_` |
| `placeholder-use` | each other place where such a name stands |
| `unbased` | any other function that a C file defines, with no accepted row in `config/names.tsv` |
| `struct` | a struct, union or enum body outside an `include/` folder |
| `extern` | an `extern` declaration or a prototype in a C file |
| `filename` | a source file named by an address or a number, such as `func_80012344.c` or `misc12.c` |
| `flag` | a compiler option of one file |
| `reservation` | a register that a file takes from the compiler, `-ffixed-N` |

- The tool does not read `asm/`, `build/`, `expected/`, `extracted/`, `refs/`, `tools/`, `docs/`, `config/`,
  `tests/`, `fixtures/` and `cookbook/`.
- It does not read the work folders of a campaign: `drafts/`, `waves/`, `repro/`, `scratch/` and `sandbox/`.
- It also does not read a folder whose name starts with a dot. It reads each other folder.
- An `#include` of a file of the tree that the tool does not read counts as `obscured`.
- That is a file with another suffix, or a file in a folder that is not read.
- A path through a linked folder or a submodule counts the same way.
- An `#include <...>` of a file of the tree counts as `obscured` too. Write the tree's own headers with quotes.
- The tool knows the macros of each header in every file, and those of an included C file in the file that includes it.
- The definition of `INCLUDE_ASM` and `INCLUDE_RODATA` is protected. A change of it needs a `raise protected` line.
- A fragment is a file that a function includes inside its braces. Its name decides nothing.
- A file of statements that no function includes counts as `obscured`.
- A branch of an `#if` must pair its braces. A lone brace in a branch counts as `obscured`.
- Where an `#if` chooses between two function heads, write the `{` behind the `#endif`.
- Every `INCLUDE_ASM` counts as a stub, wherever it stands on its line.
- The debt of a fragment rises only when each body that includes it is new.
- The tool sees a function body when its head starts in column 0 as `type name(arguments) {`.
- The game counts `flag` and `reservation`. `[debt] flags` in `config/psxdecomp.toml` names its command.
- That command prints one `<count> <kind> <path>` line for each count.
- An `INCLUDE_ASM` stub is not debt. The progress report gives it no credit. The definition of the stub macro is
  not debt either.
- A file-scope assembly statement of a header is not debt when it holds assembler directives only.
- A pointer sum with a variable is not an `offset`. The address ranges are main RAM, the scratchpad, the I/O
  ports and the BIOS. The value `0x80000000` counts only behind a pointer cast, because it is also the sign mask.
- `config/debt-baseline.txt` holds one `<count> <kind> <path>` row for each count above zero.
- The check fails when a count is over its row. It also fails when a row is over its count.
- The check also fails with no baseline, and with no policy line for a kind.
- Run `debt --update` in the commit that changes a count. The tool refuses a change that the policy does not admit.
- A `skip <entry>` line takes files out of the count. A change cannot add one.
- `[debt] address_header` in `config/psxdecomp.toml` names the address header. The default is `include/addr.h`.
- `[own] debt` names a scanner of the game. The gate runs it beside this count. It replaces no check.

### The policy of a kind

The baseline holds one policy line for each kind. `debt --recount` writes the starting lines.

| Line | Meaning |
|---|---|
| `mode <kind> down` | The kind never rises. |
| `mode <kind> admit-new` | Debt arrives only with a new function body. |
| `budget <kind> <n> base <count> <bodies> <stubs>` | As `admit-new`. The total grows by at most `n` for each 100 new bodies, plus 2. |
| `raise <kind> <n> <date> <reason>` | The developer lets one change go over by `n`. |

- The starting mode is `down` for each `-unmarked` kind and for `barrier`, `asm`, `obscured`, `unbased` and `reservation`.
- The starting mode is a budget of 30 for `pin` and of 12 for `goto`.
- Each other kind starts in `admit-new`.
- A body that exists never gets worse. That holds for a renamed body and for a body that moved to another file.
- Debt outside a function rises only in a file that gets a new body.
- A file that takes bodies from another file may also take the debt that stood beside them.
- A file that holds no function is free. A header holds definitions, and the tool counts each use of them.
- A body is new when it takes an `INCLUDE_ASM` line away. An empty body beside its stub is not new.
- A body is also new when its file is new and the repository gained a body.
- The bodies that are not new hold no more debt than the bodies that left the repository.
- The anchor of a budget is the tree at the time of `debt --recount`.
- `debt --against <revision>` judges a change by the policy of the revision that it starts from.
- A change cannot weaken a mode, raise a budget, move an anchor, add a `skip` line or delete the baseline.
- `debt --down <kind>` switches a kind to `down`. The switch is one way.
- `debt --raise <kind> <n> --reason <text>` writes a `raise` line. Only the developer runs it.
- The gate refuses a new `raise` line in an agent session. The developer commits it from a terminal.
- The gate refuses a new row of `config/asm-evidence.tsv` in an agent session in the same way.
- `debt --bodies` prints the counts of each function body.
- `debt --files` prints the state of each C file: `stubs`, `matched` or `finished`.
- A finished file has every function in C and no debt of any kind. The names ledger must exist.
- The README shows that count in a generated block. The README lint refuses the count in any other place.

## Trials

A register pin or an empty assembly statement is a crutch. It forces the compiler, and it says nothing about the game.
`python3 tools/psxd_floor.py trial <file>` examines each crutch of a file.

1. The tool takes one crutch out and asks the probe of the game.
2. The crutch is gone when the function still matches. A pin loses its `asm("…")` clause and nothing else.
3. A crutch that the match needs gets a `// !FAKE: <reason>` line above it.
4. The tool writes one row for that crutch in `config/trials.tsv`.

- `[trial] probe` in `config/psxdecomp.toml` names the probe. It is a command of the game.
- The probe gets a file to compile, a function, and the path that the file stands for.
- Write them as `{file}`, `{func}` and `{path}` in the command. Without them, the tool adds three arguments.
- The probe exits 0 when the function matches, and 1 when it does not. Any other code is an error.
- An error is never read as "the match needs it". The trial stops, and `trial --recheck` fails on that row.
- The probe compiles a copy beside the source. A probe that changes the source itself has failed.
- The tool edits bytes. The encoding and the line ends of the file stay. It refuses a file with mixed line ends.
- The tool first changes a comment only. It refuses a probe that then gives another answer.
- One marker covers one crutch. It stands on the line of the crutch, or alone on the line above.
- A marker with no reason covers nothing. The pin then counts as `pin-unmarked`.
- The columns of `config/trials.tsv` are `path function crutch hash result`.
- A row belongs to its path. A function that moved to another file is tried again.
- The hash is of the function body with no comment. A body that changed needs a new trial.
- The gate refuses a marked crutch with no row, a row with another hash, and a row that stands for no marked crutch.
- `trial <file>` writes the rows of that file again. For a file that is gone, it removes them.
- With no probe, the gate refuses every marked crutch. A game keeps no pin that it cannot examine.
- `trial --recheck` runs rows again. It fails on a row for a crutch that the function matches without.
- It also fails on a row with no crutch behind it.

## Names and assembly evidence

The rule is `rules/NAME1.md`. `python3 tools/psxd_floor.py names` checks two tab-separated files.

| File | Columns |
|---|---|
| `config/names.tsv` | `kind image scope old_name new_name decision evidence reason` |
| `config/asm-evidence.tsv` | `image symbol path class evidence date verified_by` |

- `kind` is `function`, `data`, `type`, `field`, `macro` or `file`.
- `decision` is `accepted`, `provisional` or `rejected`. Only an accepted row clears `unbased`.
- `names --init` writes the header line of each file. When `config/names.tsv` exists, each named function with no
  accepted row is `unbased` debt, and `unbased` never rises. Add the rows before the ledger, or in the same commit.
- `evidence` is `<class>:<path>:<line>`. `rules/NAME1.md` lists the classes.
- The path is a file of the repository, and the file has that line. A row with other evidence fails.
- A `refs` row cites a line of a `[[ref]]` table in `config/refs.toml`, or a file under `refs/<name>/`.
- An accepted name is a name that the source defines as the kind of the row.
- The `class` of an assembly row is `sdk-object`, `hand-asm` or `data-in-text`.
- The `evidence` of an assembly row is `<path>:<line>`. `verified_by` names the person who read it.
- An assembly row of a C file names one function of that file. It clears the assembly of that function only.
- `names --against <revision>` opens only the rows that are new since that revision. The gate runs it that way.
- A function that is only hard to match has no class. It stays a stub.

## Toolchain pins

`python3 tools/psxd_floor.py toolchain` reads `config/toolchain.tsv`. Phase 1.4 writes that file. Its columns are
`name kind pin path`.

- A `git` row passes when the checkout at `path` is at the commit `pin` and no tracked file is changed. The pin is a
  commit hash of 7 to 40 hex digits. A tag is refused, because a tag can move.
- A `sha256` row passes when the file at `path` has the hash `pin`.
- The command runs no tool of the game. A path that is not on this machine is `MISSING`, not a failure. A folder of
  the game that is not a checkout of the tool is `MISSING` too.

## A tool of the game's own

A game can hold its own tool in place of a psxdecomp delivery. Record it in `[own]` of `config/psxdecomp.toml`.
psxdecomp then delivers nothing for that key, and the doctor checks that the path exists.

| Key | It replaces |
|---|---|
| `debt` | the readability debt baseline, the assembly ledger and `rules/FIN1.md` |
| `names` | the names ledger and `rules/NAME1.md` |
| `gate` | the acceptance gate command |
| `toolchain` | the toolchain pin table |
| `campaign` | the campaign templates |
| `matcher` | the offered matcher skill |

`/psxdecomp:upgrade` proposes a key when it finds a path that it knows. For any other one, ask
`/psxdecomp:upgrade own <key> "<path or command>"`. With `[own] debt` or `[own] names` the rule of the game holds, and
the two rule files that this document names are not delivered.
