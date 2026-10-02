---
name: doctor
description: Check an existing PS1 decomp repository against psxdecomp's tested pins — PA3 version, the kit's install record, the interpreter, the ROM firewall, the reference library. Read-only. Invoked as /psxdecomp:doctor.
disable-model-invocation: true
argument-hint: "[--repo DIR]"
---

# /psxdecomp:doctor

Read-only. Run `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" preflight --target . --resume --dry-run` only if the developer asks
about the machine; otherwise just:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" doctor --repo ${ARGUMENTS:-.}
```

Report the `FAIL` and `WARN` rows, one line each, with the fix each row names. For drift in the reference library the
fix is `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" fetch_refs --repo .`; for a repository not bootstrapped by psxdecomp it
is `/psxdecomp:upgrade`. Never fix anything from this skill: it diagnoses.
