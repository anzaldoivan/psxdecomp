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
   `[manual]` ones (a PA3 or kit update, a pin to decide) are the developer's: give the command, never run it. In
   split mode the script also owns `docs/ops/psxdecomp-split.md`, the developer's release card (ship, the push gate,
   contributor PRs); it rewrites that file whenever it differs.
3. `"$PSXD" upgrade apply --dry-run --repo <repo>` — the exact writes.
4. Stop here when `--dry-run` was given. Otherwise ask (AskUserQuestion: `Apply` recommended / `Stop`), then
   `"$PSXD" upgrade apply --repo <repo>` (add `--fetch` to clone `refs/` too).
5. The script never commits. Its last line, `COMMIT ...`, is the command that commits the paths it wrote.
   Run that command on the developer's word. If a router session is running in that repository, do not apply; say so.
