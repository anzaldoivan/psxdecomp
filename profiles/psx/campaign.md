# Campaign templates

The campaign is phase 1.8. Agents write C for the functions in waves, and the kit sets the rules of a wave. This file
gives the records of a campaign one shape, so that a count means the same thing in every game. They are templates.
A game builds its own tools on them, and psxdecomp checks none of these files. `/psxdecomp:upgrade` rewrites this
file.

## The bank ledger

`config/bank.tsv` holds one row for each function. One tab separates the columns.

| Column | Value |
|---|---|
| `binary` | the image that holds the function |
| `address` | its address, in hexadecimal |
| `symbol` | its current name |
| `words` | its size, in instructions |
| `state` | `open`, `banked` or `set-aside` |
| `best` | the best match percent that an attempt reached |
| `attempts` | the count of attempts |
| `wave` | the wave that last drew the function |
| `commit` | the commit that banked it |
| `blocker` | for `set-aside`, one blocker from "The give-up report" |

- The bank step refuses a dirty tree. Commit the other work first.
- A function is `banked` only when the whole binary has the same hash with the function in C.
- `best` is a high-water mark. It never falls, and a later attempt with a lower score leaves it.
- `set-aside` needs a named blocker. A function with no blocker stays `open`.
- A banked function is matched. `rules/FIN1.md` says when its file is finished.
- A draft that a tool wrote is banked by the same rules. Record its debt with `debt --update`.

## The wave ledger

`config/waves.tsv` holds one row for each wave.

| Column | Value |
|---|---|
| `wave` | the id of the wave |
| `opened`, `closed` | the two dates |
| `task` | one Project Architect task id |
| `drawn` | the functions that the wave drew |
| `banked`, `set_aside`, `no_verdict` | where the drawn functions ended. The three add up to `drawn`. |
| `tokens_k` | the coder tokens of the wave, in thousands. Leave it empty when nobody measured it. |
| `gate` | the result of the acceptance gate after the wave, with its commit |

- One task runs one wave. A task that runs many waves hides the cost of each.
- Close a wave only after the acceptance gate passed on a clean build.

## Budgets

- Give one function 20 minutes in a wave. That time includes the reading, the draft and the builds.
- Stop after ten attempts in a row that do not improve the best score.
- These numbers come from a project on another compiler. Measure the first manual wave, then record the numbers of
  this game in its wave playbook.

## The sandbox

- Write each draft as `.run/sandbox/<symbol>/attempt-NN.c`. Git does not track that folder.
- Move a draft into `src/` only when it matches. A tracked file holds no C that does not match.
- Keep the attempts of a function that is set aside. The next wave reads them first.

## The give-up report

When a budget ends, write one record with these fields and stop.

| Field | Value |
|---|---|
| `symbol` | the function |
| `best` | the best score, and the attempt that reached it |
| `attempts` | the count of attempts |
| `tried` | the approaches, one line each |
| `blocker` | `referent`, `call-set`, `cfg`, `types` or `unknown` |
| `next` | the one fact or tool that would remove the blocker |

Check the blockers in this order. Name the first one that holds.

1. `referent`. The draft reads or writes another symbol than the target. Compare the relocations first.
2. `call-set`. The draft calls other functions, or the same functions in another order.
3. `cfg`. The branches and the loops have another shape.
4. `types`. A width, a sign or a struct layout is different.
5. `unknown`. None of the four holds. Describe the difference that is left.

Do not name a compiler defect as a blocker without a small file that reproduces it.

## Matcher workflow

1. Read the assembly of the target and its row of the bank ledger.
2. Read the earlier attempts in the sandbox, and the cookbook entries for the symptoms that you see.
3. Write the draft in the sandbox. Use the names and the types that the headers have.
4. Build the draft alone and compare it with the target.
5. Check the difference in the triage order: referent, call set, control flow, types.
6. Change one thing for each attempt, and record its score.
7. Stop at the budget: 20 minutes, or ten attempts in a row with no better score.
8. On a match, move the function into `src/` and run the acceptance gate.
9. Mark each forced register with `// !FAKE:` and its reason.
10. Run `python3 tools/psxd_floor.py debt --update` in the commit that banks the function.
11. With no match, write the give-up report and keep the best draft in the sandbox.
12. Never weaken a gate to pass it, and never bank on a build that you did not run.
