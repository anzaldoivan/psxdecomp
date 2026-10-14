# The psxdecomp floor

psxdecomp checks a minimum in every game. The minimum has four parts: a roadmap on the kit's ladder, a small set of
tools, a guard for generated files, and a debt count. This file is the reference for those checks. `/psxdecomp:upgrade` rewrites it.

## After the bootstrap

1. Start a bare `claude` session in the repository. Project Architect's planner drafts `GENERATION_PLAN.md`.
2. Read the draft against the ladder in "Numbering". Approve it only when each ladder phase has a line.
3. Run `/psxdecomp:doctor`. Have the planner correct each `FAIL` of the `roadmap` row before the first phase starts.
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

The doctor's `roadmap` row reads `GENERATION_PLAN.md` and writes nothing. A `FAIL` fails the doctor. The gate does
not run these checks.

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

- The hook fails closed. A hook that cannot start, that fails, or that runs out of time refuses the call.
- A pattern that runs for 5 seconds refuses the call too. A checkout with no `config/guard.tsv` has no rule.
- The settings give the hook `"onFailure": "block"` for that. It needs Claude Code 2.1.295 or later.
- The hook reads the rules of the checkout that the call changes. A linked worktree is guarded by its own copy.
- The `guard` row of the doctor fails on a `bash` pattern that matches the empty command. Such a pattern refuses
  every command.
- The default rows refuse an edit of `asm/`, of the hash files and of the two baselines.
- Two default rows refuse a commit that skips the commit hook (`-n`, `--no-verify`) and a change of `core.hooksPath`.
- `.claude/settings.json` also holds an `Edit(...)` deny rule for each of those paths. It stops a shell redirection too.
- A new game also has two rows for `config/oracle.toml` and `config/oracle.*.sha1`. Add them to an older game by hand.
- Add a row when a session must not run a command raw, such as a new split. The file holds two examples.

## The tooling rows

`/psxdecomp:doctor` prints these rows. A row that is not due says `WAIT` and names the phase that makes it due.

| Row | Due when | It needs |
|---|---|---|
| `roadmap` | the plan exists | the roadmap checks above |
| `guard` | always | the hook groups in `.claude/settings.json`, and a `config/guard.tsv` that parses |
| `git-hooks` | the game holds the gate | the three git hooks of this clone, where git looks for hooks |
| `gate` | phase 1.3 is closed | one gate command, and at least one `config/check.*.sha` |
| `toolchain` | phase 1.4 is closed | `docs/ops/compiler-pin.md`, and a `config/toolchain.tsv` with every row at its pin |
| `names` | phase 1.4 is closed | the two ledgers, each with its header line. An assembly row that points at nothing fails. |
| `debt` | the first C file is in `src/`, or the first count | a debt baseline that is equal to the tree |
| `cpp` | phase 1.4 is closed | `[floor] cpp` in `config/psxdecomp.toml`, and a command that runs on this machine |
| `progress` | phase 1.9 opens | a workflow that uploads the progress report of each executable |

## The acceptance gate

A game has one command that proves a change. The default is `make verify`.

1. Run the policy checks first: `psxd_floor.py debt` and `names`, then `psxd_publish.py lint README.md` and `style`.
2. Run the build with its hash check.
3. Print `VERIFY OK` as the last line, or `VERIFY FAIL: <the command to run>`.

- Name another command in `[floor] gate` of `config/psxdecomp.toml`. A gate of the game's own goes in `[own] gate`.
  That key answers the `gate` row of the doctor, and the game's gate then holds its own hashes.
- psxdecomp delivers no makefile. Each game has targets of its own shape.

## The gate of the floor

`python3 tools/psxd_floor.py gate` runs the checks of this file in one command. Each finding is a line
`GATE FAIL <check>: <detail>`. A `GATE WARN` line refuses nothing. The last line is `GATE OK` or `GATE FAIL`.

| Mode | It judges | Against |
|---|---|---|
| `--staged` | the index | `HEAD` |
| `--bank` | the work tree, with the files that git does not track yet | `HEAD` |
| `--ci <base>..<head>` | the head of the range | the base of the range |
| `--push` | the same as `--ci` | the same as `--ci` |

The gate refuses these things, and no other. Established projects run the byte check and count the same crutches. One
guards its checksum file against an agent (snowboardkids2-decomp). No project judges a change against its base: that
part is ours.

| What the gate refuses | Check |
|---|---|
| a build that does not give the bytes of the game: `[floor] gate` or `[own] gate` fails, at the bank and at a push | `game` |
| a change of a file that carries the floor, such as a tool, a hook, a deny rule, a workflow or a policy line | `protected`, `policy` |
| assembly that stands for a function: an assembly statement with an instruction or data, or an assembly file, with no evidence row | `debt` |
| a new pin, `goto` or barrier with no `// !FAKE: <reason>` comment | `debt` |
| a rise of a kind that the developer set to `down` | `debt` |
| a baseline, a ledger or a README that is not in order | `debt`, `names`, `readme`, `categories`, `style`, `own-debt` |

- The gate judges a change against a tree that the change cannot rewrite. An edited baseline or tool decides nothing.
- The two ends of a change decide. A merge in progress is judged against `HEAD`, as any other change.
- A base that names no commit fails. A tool that cannot run passes nothing.
- `--bank` writes the totals of the baseline when the change is admitted. A bank tool calls it before the commit.
- `--bank` and `--push` also run the check of the game, `[floor] gate` or `[own] gate`.
- The gate never refuses a function for its name. It never refuses a cast, an offset or a placeholder name.
- `protected` covers the two tools, the workflows, and the hooks, deny rules and `env` of `.claude/settings.json`.
- It also covers the `deny` rows of `config/guard.tsv`, and each value of `[own]`, `[trial]`, `[floor]` and `[debt]`.
- A new key in one of those four tables is a protected change. A file that a `skip` line covers keeps its bytes.
- A tool changes only to a later version. The new tool then judges the tree.
- The developer allows one protected change with `debt --raise protected <n> --reason <text>`.
- That line also allows a change of the policy, such as a new `skip` line.

Three git hooks run the gate in each clone. `python3 tools/psxd_publish.py hook --install` writes them.

| Hook | It runs | With the tools of |
|---|---|---|
| `pre-commit`, `pre-merge-commit` | `gate --staged` | `HEAD` |
| `pre-push` | `gate --push` for each branch that the push updates | the commit that the remote holds |

- A hook copies the tools into a temporary folder and runs them there. The copies of the change decide nothing.
- A hook is no tracked file. The bootstrap and `/psxdecomp:upgrade` write the hooks, and never over another hook.
- `pre-push` asks at the terminal for each `raise` line and each assembly row that the push adds.
- With no terminal, the answer is no. An agent session never pushes.
- `pre-push` works in split mode and outside it.

## Readability debt

`python3 tools/psxd_floor.py debt` counts the debt of the source. The rule is `rules/FIN1.md`.
The cleanup of a matched function is separate work. It comes after the bank, and a later commit lowers the count.

The tool reads four kinds in the text that the compiler gets. These are the kinds that the gate can refuse.

| Kind | It counts |
|---|---|
| `pin` | a register that the source forces: `register ... asm("$n")`, also with `__asm__` or `__asm` |
| `goto` | the word `goto` |
| `barrier` | an empty assembly statement, `__asm__("")`, or one inside a function that holds assembler directives only |
| `pin-unmarked` | a pin with no `// !FAKE: <reason>` comment of its own |
| `goto-unmarked` | a `goto` with no such comment |
| `barrier-unmarked` | a barrier with no such comment |
| `asm` | an assembly file, or an assembly statement that holds an instruction or emits data, with no row in `config/asm-evidence.tsv` |

- `[floor] cpp` in `config/psxdecomp.toml` names the preprocess command of the game, with `{file}` for the unit.
- An example is `cpp = "mipsel-linux-gnu-cpp -nostdinc -undef -D__GNUC__=2 -Iinclude {file}"`.
- The tool runs that command for each C file and reads its output. It runs the command with no shell.
- It also runs a C file that another file includes. A build can compile such a file alone.
- A macro, a line splice or a digraph hides nothing there. An `#include` of any file hides nothing either.
- The output holds `# <line> "<file>"` markers. Each construct counts at the file and the line that hold it.
- Do not give `-P` to the command. That option removes the markers.
- A source holds no line directive of its own, such as `#line`. The check fails on a file that holds one.
- The host's `cc -E` with the same flags reads the same text. Name a command that each machine of the project has.
- A unit that the command cannot preprocess fails the check. So does a command that the machine lacks.
- The tool keeps the result of each unit in the git folder, so a change costs the units that read a changed file.
  A push and CI run every unit again.
- A change is counted with the command of the tree that it starts from. A new command decides from the next change on.
- With no `[floor] cpp`, the tool reads the raw text of each file. `/psxdecomp:doctor` says so in its `cpp` row.
- In the raw text, a construct inside a macro counts one time, at the definition of the macro.
- One marker covers one construct. It stands on the line of the construct, or alone on the line above.
- The marker stands in the file that holds the line. A marker with no reason covers nothing.
- An `INCLUDE_ASM` stub is not debt. The progress report gives it no credit.
- A file-scope assembly statement that holds assembler directives only (`.include`, `.section`, `.set`, `.macro`)
  is the plumbing of a stub, and not debt. A line with `.word`, `.byte` or `.incbin` emits data.
- In split mode, the public repository must hold each file that its C units include.

The tool finds the other kinds with patterns over the raw text. They are counted and shown, and the gate refuses none.

| Kind | It counts |
|---|---|
| `offset` | a field read by its offset: `*(T *)(p + N)`, `((T *)p)[N]`, `M2C_FIELD(`, or a byte pointer plus a number, each also with a minus. A macro that hides one counts at each use. |
| `address` | a literal in the address ranges of the console with no symbol, or a macro that hides one, outside the address header |
| `cast` | an integer made of a pointer, or a pointer made of an integer: `(s32)&x`, `(T *)(s32)x`, also with `u_long`, `u_int` and `u_short` |
| `field` | a name such as `unk_10` or `field_0x10`: a field with an offset and no name |
| `placeholder` | a `func_` or `D_` address name that a C file defines, also `FUN_`, `DAT_`, `sub_` and `loc_` |
| `placeholder-use` | each other place where such a name stands |
| `struct` | a struct, union or enum body outside an `include/` folder |
| `extern` | an `extern` declaration or a prototype in a C file |
| `filename` | a source file named by an address or a number, such as `func_80012344.c` or `misc12.c` |

- A pattern is a count, not a proof. Code in another spelling is not counted.
- A file name with a suffix after the address, such as `func_800EFE70_ovl02.c`, is not counted as `filename`.
- For these kinds the tool reads each tracked file with a C suffix. It does not read `asm/`, `build/`, `expected/`,
  `extracted/`, `refs/`, `tools/`, `docs/`, `config/`, `tests/`, `fixtures/` and `cookbook/`.
- It does not read the work folders of a campaign: `drafts/`, `waves/`, `repro/`, `scratch/` and `sandbox/`.
- It also does not read a folder whose name starts with a dot. It reads each other folder.
- The tool knows the macros of each header in every file, and those of an included C file in the file that includes it.
- A pointer sum with a variable is not an `offset`. The address ranges are main RAM, the scratchpad, the I/O
  ports and the BIOS. The value `0x80000000` counts only behind a pointer cast, because it is also the sign mask.
- `config/debt-baseline.txt` holds one `<count> <kind>` row for each kind above zero: the total of the tree.
- The diff of that file shows the debt that a commit brings.
- The check fails when a total is over its row. It also fails when a row is over its total.
- The tool takes a tree as the public tree of a game in split mode when `config/public-paths.txt` names each of its
  files. In that tree, a total under its row is no failure, because the row also counts the files that the public
  tree does not hold.
- If a commit on the public main adds a file that the list does not name, a total under its row fails again.
- A file of an earlier psxdecomp holds a row for each file. The tool adds them up. `debt --recount` writes totals.
- The check also fails with no baseline, and with no policy line for a kind.
- Run `debt --update` in the commit that changes a count, or bank with `gate --bank`.
- A `skip <entry>` line takes files out of the count. A change cannot add one.
- `[debt] address_header` in `config/psxdecomp.toml` names the address header. The default is `include/addr.h`.
- `[own] debt` names a scanner of the game. The gate runs it beside this count. It replaces no check.

### The policy of a kind

The baseline holds one policy line for each kind. `debt --recount` writes the starting lines.

| Line | Meaning |
|---|---|
| `mode <kind> count` | The kind is counted and shown. Nothing is refused. |
| `mode <kind> down` | The total of the kind in the tree never rises. |
| `raise <kind> <n> <date> <reason>` | The developer lets one change go over by `n`. |

- The starting mode is `down` for `asm`, `pin-unmarked`, `goto-unmarked` and `barrier-unmarked`.
- Each other kind starts in `count`. Its row shows the debt that each commit brings.
- No kind about names starts in `down`. A function that matches is never refused for its name.
- The tool compares the total of the tree that a change starts from with the total of the tree that it makes.
- `debt --against <revision>` judges a change by the policy of the revision that it starts from.
- A change cannot weaken a mode, add a `skip` line or delete the baseline.
- `debt --down <kind>` switches a kind to `down`. The switch is one way.
- `debt --raise <kind> <n> --reason <text>` writes a `raise` line. Only the developer runs it.
- The gate refuses a new `raise` line in an agent session. The developer commits it from a terminal.
- The gate refuses a new row of `config/asm-evidence.tsv` in an agent session in the same way.
- `debt --files` prints the state of each C file, `stubs`, `matched` or `finished`, and its counts.
- A finished file has every function in C and no debt of any kind.
- The README shows that count in a generated block. The README lint refuses the count in any other place.

## Trials

A register pin or an empty assembly statement is a crutch. It forces the compiler, and it says nothing about the game.
`python3 tools/psxd_trial.py <file>` is a helper that examines each crutch of a file. No check asks for a trial.

1. The tool takes one crutch out and asks the probe of the game.
2. The crutch is gone when the function still matches. A pin loses its `asm("…")` clause and nothing else.
3. A crutch that the match needs gets a `// !FAKE: <reason>` line above it. The marker is the record.

- `[trial] probe` in `config/psxdecomp.toml` names the probe. It is a command of the game.
- `/psxdecomp:upgrade` writes `tools/psxd_trial.py` when that key exists.
- The probe gets a file to compile, a function, and the path that the file stands for.
- Write them as `{file}`, `{func}` and `{path}` in the command. Without them, the tool adds three arguments.
- The probe exits 0 when the function matches, and 1 when it does not. Any other code is an error.
- An error is never read as "the match needs it". The trial of that function stops, and the file stays as it was.
- The probe compiles a copy beside the source. A probe that changes the source itself has failed.
- The tool edits bytes. The encoding and the line ends of the file stay. It refuses a file with mixed line ends.
- The tool first changes a comment only. It refuses a probe that then gives another answer.
- One marker covers one crutch. It stands on the line of the crutch, or alone on the line above.
- A marker with no reason covers nothing. The pin then counts as `pin-unmarked`.

## Names and assembly evidence

The rule is `rules/NAME1.md`. `python3 tools/psxd_floor.py names` checks two tab-separated files.

| File | Columns |
|---|---|
| `config/names.tsv` | `kind image scope old_name new_name decision evidence reason` |
| `config/asm-evidence.tsv` | `image symbol path class evidence date verified_by` |

- `kind` is `function`, `data`, `type`, `field`, `macro` or `file`.
- `decision` is `accepted`, `provisional` or `rejected`.
- A name is never required. A function that matches is banked and pushed under the name that it has.
- `names --init` writes the header line of each file.
- `evidence` is `<class>:<path>:<line>`. `rules/NAME1.md` lists the classes.
- The tool reads only that `config/names.tsv` is its table. It does not open the evidence of a name.
- A file that the tool cannot read as its table fails. A row of the assembly ledger that points at nothing also fails.
- The `class` of an assembly row is `sdk-object`, `hand-asm` or `data-in-text`.
- The `evidence` of an assembly row is `<path>:<line>`. `verified_by` names the person who read it.
- The path is a file of the repository with that line. A file under `refs/<name>/` needs a `[[ref]]` table of that
  name in `config/refs.toml`.
- An assembly row of a C file names one function of that file. It clears the assembly of that function only.
- `names --against <revision>` opens only the assembly rows that are new since that revision. The gate runs it that way.
- A function that is only hard to match has no class. It stays a stub.

## Toolchain pins

`python3 tools/psxd_floor.py toolchain` reads `config/toolchain.tsv`. Phase 1.4 writes that file. Its columns are
`name kind pin path`.

- A `git` row passes when the checkout at `path` is at the commit `pin` and no tracked file is changed. The pin is a
  commit hash of 7 to 40 hex digits. A tag is refused, because a tag can move.
- A `sha256` row passes when the file at `path` has the hash `pin`.
- The command runs no tool of the game. A path that is not on this machine is `MISSING`, not a failure. A folder of
  the game that is not a checkout of the tool is `MISSING` too.
- The doctor's `toolchain` row runs the same check. The gate does not run it.

## Other builds of the game

A prototype, a debug build or another revision can tell more than the target does. The game keeps one table and one
checksum file for each such build that a developer supplies. It keeps no byte of one.

| Where | What it holds | Tracked |
|---|---|---|
| `disks/builds/<id>/`, or a folder outside the repository | your copy of the build, and each file that you make from it | no |
| `ghidra/` | a database of the build | no |
| `config/oracle.toml` | one table for each build: its id, its class, its page and the hashes that the page states | yes |
| `config/oracle.<id>.sha1` | the SHA-1 of each file of the build | yes |
| the git directory of your clone | the path of your copy | no |

`psxd` is the launcher of the psxdecomp plugin. The game does not hold it.

- An id is the date of the build or its serial: `proto-2001-10-30`, `slpm-86959`. `retail` is the id of your disc.
- Add a build once for the project. The command checks your copy against the hash that the page of the build states:

      psxd oracle add --repo . --id <id> --path <your copy> --expect <sha1> --page <the page>

  Commit the files that it names. It also registers your path for this clone.
- A build that another developer added needs only your path:

      psxd oracle link --repo . --id <id> --path <your copy>

- List the builds. Print the path of one:

      psxd oracle list --repo .
      psxd oracle locate --repo . --id <id>

- Each worktree of the clone finds the same paths. No tracked file holds a path of your machine.
- A build that you do not have is no fault. The doctor's `oracle` row counts the builds on this machine.
- The audit refuses a tracked copy of a file of a build, under any name. It also refuses a tracked `.SYM`, `.CPE`,
  `.PDB` or `.DBG` file, and a listing of 64 lines.
- Never commit the text of a symbol file. Keep it in `disks/builds/<id>/`.
- A name from another build is a lead. It moves to the target after a byte check of the function at both addresses.

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
