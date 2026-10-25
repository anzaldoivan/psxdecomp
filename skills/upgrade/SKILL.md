---
name: upgrade
description: Bring an existing PS1 decomp repository (one bootstrapped by hand, or one psxdecomp bootstrapped earlier) to the current psxdecomp pins — audit, plan, apply --dry-run, then apply on the developer's word. Invoked as /psxdecomp:upgrade.
disable-model-invocation: true
argument-hint: "[--dry-run] [--fetch] [--take ACTION] [--repo DIR] | own KEY VALUE"
---

# /psxdecomp:upgrade

psxrecomp's migrate shape: **audit → plan → apply --dry-run → apply**. `PSXD="${CLAUDE_PLUGIN_ROOT}/scripts/psxd"`.

1. `"$PSXD" upgrade audit --repo <repo>` — show the `FAIL`/`WARN` rows.
2. `"$PSXD" upgrade plan --repo <repo>` — show the numbered actions. `[psxdecomp]` actions are applied by the script;
   `[manual]` ones (a PA3 or kit update, a pin to decide) are the developer's: give the command, never run it. In
   split mode the script also owns `docs/ops/psxdecomp-split.md`, the developer's release card (ship, the push gate,
   contributor PRs). The writing rule of the public files is four more
   actions: `ai-policy`, `ste-rule`, `style-hook` and `style-ratchet`. `style-public` is always `[manual]`: the
   developer adds `config/style-ratchet.txt` to `config/public-paths.txt`.

   Three actions cover the other builds of a game. `firewall-debug` is the script's. `record-oracle` and
   `oracle-public` are `[manual]`: give the command of the plan line.
3. `"$PSXD" upgrade apply --dry-run --repo <repo>` — the exact writes.
4. Stop here when `--dry-run` was given, or when the plan printed `PLAN BUSY`: a PA3 task is in flight. The
   script refuses to apply under it (`APPLY FAIL a PA3 task is in flight: ...`). Say why, with the file and the task
   that the line names, and that the upgrade waits for the task. Otherwise ask (AskUserQuestion: `Apply` recommended
   / `Stop`), then `"$PSXD" upgrade apply --repo <repo>` (add `--fetch` to clone `refs/` too).
5. The script never commits. Its last line, `COMMIT ...`, is the command that commits the paths it wrote.
   Run that command on the developer's word.

Tell the developer what each plan line does, in one line each. Two plan lines and what to say:

<example>

```
PLAN 3 [psxdecomp] floor: write tools/psxd_floor.py and docs/ops/psxdecomp-floor.md (…) — missing or older …
PLAN 7 [manual] PA3: the repository is at 3.14.2, psxdecomp is tested on 3.30.7; update with PA3's own installer …

3. I can apply this one: it adds the floor's tool and its reference file. Nothing of yours changes.
7. This one is yours: run PA3's installer yourself, then `/psxdecomp:upgrade` again and `/psxdecomp:doctor`. I do not
   run it.
```

</example>

Two kinds of action need a word to the developer:

- An action that ends in `-edited` names a psxdecomp file or rule that the game edited. The script never overwrites
  it unasked. Show the difference. On the developer's word run `"$PSXD" upgrade apply --take <action> --repo <repo>`,
  where `<action>` is the name without `-edited`, as the plan line prints it. Another name is refused.
- `own` records a tool of the game's own in `[own]` of `config/psxdecomp.toml`. psxdecomp then delivers nothing in
  its place. The plan proposes a key for a path that it knows. For any other one, and for
  `/psxdecomp:upgrade own <key> <value>`, run `"$PSXD" upgrade own <key> "<value>" --repo <repo>`. The key is one of
  `debt`, `names`, `gate`, `toolchain`, `campaign`, `matcher`. The value is a path or a command of the repository.
- `PLAN FAIL` or `APPLY FAIL` with "is not TOML" means that `config/psxdecomp.toml` has a typo. Nothing is written
  until the developer repairs it. `APPLY FAIL <n> step(s)` means that a tool of the game refused one step: the other
  writes are made, and a second apply finishes after the repair.
