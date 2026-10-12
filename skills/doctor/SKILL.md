---
name: doctor
description: Check an existing PS1 decomp repository against psxdecomp's tested pins — PA3 version, the kit's install record, the interpreter, the ROM firewall, the reference library. Read-only. Invoked as /psxdecomp:doctor.
disable-model-invocation: true
argument-hint: "[--repo DIR]"
---

# /psxdecomp:doctor

Read-only. Run `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" preflight --target . --resume --dry-run` only if the developer asks
about the machine. Otherwise run:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" doctor --repo ${ARGUMENTS:-.}
```

Report the `FAIL` and `WARN` rows, one line each, with the fix each row names. Never fix anything from this skill: it
diagnoses.

| Row | Status | What it reads | Fix |
|---|---|---|---|
| `progress` | WARN only, network | A workflow that builds a decomp.dev report: its safety lint, and whether decomp.dev lists the repository. In split mode: the public `[public].repo` | the row names it |
| `github` | WARN only, network | The repository's security settings through `gh api` | the `gh api` command in the row, for the developer to run |
| `github` in split mode | FAIL | Origin, the `-dev`, is not private: dev's history is exposed | make it private |
| `private-repo` | FAIL, network | `<game>-private` breaks a rule: public, forked, Actions on, a writable or second deploy key, another collaborator, a `private_rev` it lacks | the row names it |
| `public-standard` | WARN, network | The public repository's drift from the standard | `settings --apply`, the developer's |
| `dev-ci` | WARN or FAIL, network | The latest push run of each workflow on origin's default branch. WARN: one is red. FAIL: a red job is one of `[public].checks` | a green push on dev before the next release |
| `refs` | WARN | Drift in the reference library | `"${CLAUDE_PLUGIN_ROOT}/scripts/psxd" fetch_refs --repo .` |
| `record` | WARN | psxdecomp did not bootstrap the repository | `/psxdecomp:upgrade` |
| `readme` | FAIL | A README lint failure. The standard: `docs/PUBLISHING.md` in the plugin | the row names it; the generated blocks: `python3 tools/psxd_publish.py render README.md --write` |
| `card` | WARN only | `HOW_WE_WORK.md` is over PA3's cap | move a section to `docs/ops/` and link it |

- `--offline` skips the network rows. Their rows say `SKIP`: a check that did not run is never `OK`. The last line
  counts them.
- `--only github` runs just that row. A name that is no row exits 2 and lists the rows.
- `--json` prints the rows alone on stdout.
