# {{GAME}}-private

The only place the game's files exist outside the developer's machine. It is a split-mode repository (psxdecomp
`docs/PUBLISHING.md`, Split mode). The public `{{GAME}}` and the private `{{GAME}}-dev` never hold a game byte (G12);
this repository holds the files the public CI needs, and nothing else.

## What it holds

| Path | What | Changes when |
|---|---|---|
| `inputs/` | The files the build reads, at the repository-relative paths the game's Makefile expects (mirrored: `inputs/disks/us/SLUS_000.00` lands at `disks/us/SLUS_000.00`) | never (the disc doesn't change) |
| `check/<EXE>.sha1` | The canonical hash list per executable, `sha1sum` format, repository-relative paths. CI checks the build against this copy, never a PR's | never, unless an executable is added |
| `backup/` | Optional: the reverse-engineering database export (G18's private archive) | when the developer takes a backup |

The compiler is not here: CI downloads it by pinned sha256, as the game's own recipe does.

## Rules (G12 scope clause)

- Private. Never made public, never forked (forking disabled), the owner is the only collaborator.
- Actions disabled: it runs no workflow and publishes no package.
- One deploy key, read-only, held only as the public `{{GAME}}`'s secret `PRIVATE_DEPLOY_KEY`; or in its place a
  fine-grained PAT with read access to this repository alone, held as `PRIVATE_REPO_TOKEN`.
- The agents never clone it. The developer's clone, if any, sits beside the game checkouts, never inside one.
- The public `{{GAME}}`'s `config/psxdecomp.toml` `[public].private_rev` names the commit CI reads.

`/psxdecomp:doctor` FAILs when any of these drifts.

## If its contents leak

See the public repository's `SECURITY.md` (the purge path). If this repository was made public or forked by mistake,
make it private at once, rotate the deploy key, and contact GitHub Support: its history counts as published from then
on.
