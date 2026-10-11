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

Report the `FAIL` and `WARN` rows, one line each, with the fix each row names. Two rows are WARN only and use the
network: `progress` (when a workflow builds a decomp.dev report: its safety lint, and whether decomp.dev lists the
repository, in split mode the public `[public].repo`) and `github` (the repository's security settings through `gh api`;
each WARN carries the `gh api` command that fixes it, for the developer to run). `--offline` skips both (their rows
say `SKIP`: a check that did not run is never `OK`, and the last line counts them); `--only github` runs just that row.
In split mode `github` checks only that origin, the `-dev`, is private (a FAIL otherwise: dev's
history is exposed), and two more use `gh api`: `private-repo` FAILs when `<game>-private` breaks its rules (public,
forked, Actions on, a writable or second deploy key, another collaborator, a `private_rev` it lacks), and
`public-standard` WARNs with the public repository's drift from the standard (`settings --apply` fixes it, the
developer's). `dev-ci` reads the latest push run of each workflow on origin's default branch: WARN when one is red,
FAIL when a red job is one of `[public].checks` (the fix is a green push on dev before the next release). For drift in the reference library the fix is `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" fetch_refs --repo .`;
for a repository not bootstrapped by psxdecomp it is `/psxdecomp:upgrade`. A README lint failure names its fix (the
standard: `docs/PUBLISHING.md` in the plugin); the generated blocks are
`python3 tools/psxd_publish.py render README.md --write`. Never fix anything from this skill: it diagnoses.
