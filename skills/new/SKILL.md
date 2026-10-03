---
name: new
description: Bootstrap a new PlayStation (PS1) matching-decompilation repository in this empty folder — interview, disc identification, prior-art research, a pinned reference library, then Project Architect 3.14.2 and the decomp-architect kit. Invoked only as /psxdecomp:new.
disable-model-invocation: true
argument-hint: "[--answers FILE|fixture:NAME] [--resume] [--deep] [--until S0..S10]"
---

# /psxdecomp:new

You are bootstrapping a matching-decompilation repository for a PS1 game in the **current folder**. Run the stages
below in order. Each stage ends by updating `.run/bootstrap/state.json`: script stages do it themselves; after a
stage you did, run `"$PSXD" install mark <SID> --target . --note "<one line>"` (`--status skipped` when skipped). `--resume` continues from the
first stage that is not done. `--until <SID>` stops after that stage.

Arguments: `$ARGUMENTS`

Reference files (read each when its stage starts, not before): `${CLAUDE_PLUGIN_ROOT}/skills/new/reference/` —
`interview.md`, `investigate.md`, `gate.md`, `intake.md`, `report-template.md`, `stages.md` (the contract).

With `--answers X` (a file, or `fixture:<name>` for the plugin's canned ones), S1 is the answers check; S3 still runs
and S4 presents the file's values as the drafted answers.

**Every command below runs through the launcher:** `PSXD="${CLAUDE_PLUGIN_ROOT}/scripts/psxd"`, then
`"$PSXD" <script> ...`. Scripts print one status line per check; quote the `DONE`/`FAIL` lines to the developer, not
the whole output.

## Hard rules (they hold in every stage)

1. **Firewall.** Never read, print, copy or commit a byte of the dump. Only `identify` touches it, in place, and it
   writes facts (names, sizes, addresses, counts, hashes) under the ignored `.run/bootstrap/`. Never put the dump
   inside this folder. Never fetch a `byo` reference (the PsyQ SDK): the developer gives a local path or nothing.
2. **PS1 only in v1.** Any other console: say "<console> is not yet supported by psxdecomp (v1 is PS1 only)", write
   nothing, run no installer, stop.
3. **Pins.** The scripts refuse a PA3 or kit that is not the tested one. Never pass `--force-untested` unless the
   developer asked for it in this session; it is recorded as a deviation.
4. **Nothing installs before the gate (S4).** S0–S4 write only under `.run/bootstrap/`.
5. **Facts, then the gate.** Every lead carries a status (`lead` until checked) and a licence class (see
   `reference/report-template.md`). Never present a lead as a fact.
6. Don't edit PA3's or the kit's files by hand; their installers own them.

## Stages

| Stage | Kind | Do |
|---|---|---|
| S0 preflight | script | `"$PSXD" preflight --target .` (add `--resume` when resuming). A `FAIL` stops the run; show `WARN`s once. |
| S1 interview | you | Follow `reference/interview.md` (AskUserQuestion, rounds of ≤4). With `--answers X`: run `"$PSXD" install answers --answers X --target .` instead; a refusal stops the run (nothing installed). |
| S2 identify | script | `"$PSXD" identify "<DUMP_PATH>" --target .` (add `--dat <file>` if the developer has a Redump DAT). No dump given (an `--answers` file without `DUMP_PATH`): `"$PSXD" install mark S2 --status skipped --target . --note "no dump"` and say so. |
| S3 investigate | you + agents | Follow `reference/investigate.md`: one `scout-web` agent per question, in parallel; `scout-repo` to confirm a lead from a clone. Writes `.run/bootstrap/research/*.md`, `prior-art.draft.md`, `refs.draft.toml`. |
| S4 gate | you | Follow `reference/gate.md`: show the report, the drafted answers and the drafted refs; the developer confirms or edits each, then answers the PsyQ question (worded from S2's version). Writes `.run/bootstrap/answers.txt`, `refs.toml`, `prior-art.md`. |
| S5 repo | script | `"$PSXD" install stage S5 --target .` — git init, licence, the kit's ROM firewall as the first commit after its negative control. |
| S6 PA3 | script | `"$PSXD" install stage S6 --target .` — PA3 3.14.2's own unattended per-repo install. If it says PA3 is not installed on this machine, show the one command it prints (`--root --no-clone`: the pinned copy, not PA3's upstream), let the developer run it, then resume. Its `DONE` line ends with the restart line. |
| — restart | — | PA3's hooks and agents load at session start. Tell the developer, verbatim: **"Exit, then run `claude --agent plain` here and type `/psxdecomp:new --resume`."** Stop: no S7 in this session, even when asked to go on. (The plugin's SessionStart hook repeats the line in the next session.) |
| S7 intake | you | Follow `reference/intake.md` (PA3's intake in this plain session, handed the kit's `intake.decomp.md` with the S4 answers). Commit what it writes. |
| S8 kit | script | `"$PSXD" install stage S8 --target .` — the pinned decomp-architect installer: its dry run, then the run. |
| S9 refs | script | `"$PSXD" install stage S9 --target .` — `config/refs.toml`, the core rows fetched into `refs/` at their pins (optional ones are fetched later, when their `when` holds), `docs/ops/refs.md`, the grep rule. |
| S10 handoff | script | `"$PSXD" install stage S10 --target .` — doctor, `config/psxdecomp.toml`, `docs/prior-art.md`. Then tell the developer: **"Run a bare `claude` here: PA3's planner drafts GENERATION_PLAN.md."** |

`--deep` widens S3 (extended web search, shallow clones of every repository lead). Without it, S3 is one shallow
search pass per question.

## Resuming

`--resume`: run `"$PSXD" install plan --target .`; continue at the `NEXT` stage. A `failed` stage is re-run from its
start (every stage is idempotent). If the current session is not a plain one and the next stage is S7, give the
restart line above and stop.

## What the developer sees at the end

One short summary: the stages and their one-line results, the deviations (if any), the commit list
(`git log --oneline`), and the next step. No transcript of tool output.
