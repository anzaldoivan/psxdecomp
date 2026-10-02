---
name: upgrade
description: Bring an existing PS1 decomp repository (one bootstrapped by hand, or one psxdecomp bootstrapped earlier) to the current psxdecomp pins — audit, plan, apply --dry-run, then apply on the developer's word. Invoked as /psxdecomp:upgrade.
disable-model-invocation: true
argument-hint: "[--dry-run] [--fetch] [--repo DIR]"
---

# /psxdecomp:upgrade

psxrecomp's migrate shape: **audit → plan → apply --dry-run → apply**. `PSXD="${CLAUDE_PLUGIN_ROOT}/scripts/psxd"`.

1. `"$PSXD" upgrade audit --repo <repo>` — show the `FAIL`/`WARN` rows.
2. `"$PSXD" upgrade plan --repo <repo>` — show the numbered actions. `[psxdecomp]` actions are applied by the script;
   `[manual]` ones (a PA3 or kit update, a pin to decide) are the developer's: give the command, never run it.
3. `"$PSXD" upgrade apply --dry-run --repo <repo>` — the exact writes.
4. Stop here when `--dry-run` was given. Otherwise ask (AskUserQuestion: `Apply` recommended / `Stop`), then
   `"$PSXD" upgrade apply --repo <repo>` (add `--fetch` to clone `refs/` too).
5. The script never commits. In a PA3 repository commit through the project's own path (`tools/commit_task.sh` when
   it exists, else an explicit-path `git commit`), only the paths `APPLY` printed. If a router session is running in
   that repository, do not apply; say so.
