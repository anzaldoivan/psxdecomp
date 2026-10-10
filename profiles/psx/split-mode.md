# Releasing to the public repository

psxdecomp's `/psxdecomp:upgrade` writes this card and rewrites it on every upgrade: change psxdecomp's
`profiles/psx/split-mode.md`, not this copy. The full stage list lives in psxdecomp's `docs/PUBLISHING.md`, section
"Releasing with ship". `docs/ops/` is never public.

Run everything here in your own terminal, outside Claude Code. In an agent session (`CLAUDECODE` set) the hook,
`ship`, `release`, `land` and every merge refuse.

## The cadence

1. A phase ends. PA3's recap ends with `Push: git push`.
2. You push: `git push`. The pre-push hook builds the public projection of the commit you push, offline, and reports:
   - `PRE-PUSH FAIL …`: a leak. A denied or agent path is listed, a symlink or gitlink is listed, or the audit
     failed. The push stops. Unlist the path or remove the bytes, commit, push again.
   - `PRE-PUSH WARN …`: a README lint failure, new public paths, or nothing new to release. The push goes through.
   - `PRE-PUSH release-ready: N files, M new`: nothing to fix.
3. You ship: `python3 tools/psxd_publish.py ship --summary "one line, in your words"`.
4. You resume the router.

`git push --no-verify` skips the hook. It is yours alone, for a broken hook; the agents' deny list refuses it.

## What ship checks, and what to do when it stops

| Stage | Checks | When it fails |
|---|---|---|
| `state` | the commit is `origin/<dev_branch>`; public's releases and open release PRs | push first; another release PR open: `--replace`; no public main: release 1 is a cutover step (`release --push`) |
| `dev-ci` | every workflow run of -dev at that commit passed | fix in dev, push, ship again; still running: it waits up to `--timeout MIN` (90) |
| `gate` | contributor commits imported, exact projection, new paths, check-public, README lint, audit | `import`, then `land`, then push; new paths: answer `y`, or pass `--ack-new` |
| `build` | `[public].land_check`, the byte check, on the exported projection | the published files alone don't build: list what is missing, or fix in dev |
| `ci` | `ci-sim --projection`: `no-rom.yml`'s jobs on the projection, in a clean container | a file CI needs is unlisted, or a no-rom job is red: `python3 tools/psxd_publish.py ci-sim --projection` shows the whole log |
| `push` | pushes `release/<rev10>` and opens the PR | |
| `checks` | the PR's required checks, green, from GitHub Actions, at its head | red: fix forward (below); a workflow change: review the printed diff, then `ship --merge-reviewed` |
| `merge` | the admin squash, pinned to the head it checked | |
| `verify` | public main carries the release, its push runs passed, every `<EXE>_report` was uploaded | rerun ship once the cause is fixed |

- `--dry-run` stops after `ci`, before anything reaches public. `--no-wait` stops once the PR is open.
- To resume, rerun the same command. ship reads public and carries on: an open release PR goes to `checks`, a merged
  release to `verify`.
- Each stage prints `SHIP <stage> OK|FAIL …`. The last line is `SHIP OK`, and `.git/psxdecomp/ships.tsv` (local
  only) gains one line.

## Fixing forward

Nobody patches a red release PR on public. Fix the cause in dev, commit, push, then
`ship --summary "…" --replace`. ship closes the old PR only after the new release passes its local stages.

## Contributor PRs

- `python3 tools/psxd_publish.py verify-pr N`, then your review on GitHub, then `verify-pr N --merge`.
- At a phase end, with the agents idle: `import`, then `land`. ship refuses while a merged contributor commit is
  not imported.

## The agents

Agents commit. They never push, ship, release, land or merge; the hook and the deny list stop them. If an agent asks
you to run one of these, the decision is yours.
