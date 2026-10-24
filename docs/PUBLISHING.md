# Publishing: the README standard and decomp.dev reports

Every game repository psxdecomp bootstraps inherits two standards: how its README is laid out, and how it publishes
progress to [decomp.dev](https://decomp.dev). Both are code in `scripts/publish.py`, which S10 and
`/psxdecomp:upgrade` copy byte for byte into the game as `tools/psxd_publish.py`. The game's CI runs that copy
(`.github/workflows/psxdecomp-readme.yml`), so it needs nothing from the plugin. This page is the standard's one home;
other docs link here.

## When each part starts

The kit's phase ladder already works out every fact a category needs. The standard reads those records; it never
records them a second time, and it never asks for them before the phase that proves them.

| Fact a category needs | Where the game already records it | Phase |
|---|---|---|
| unit → binary or overlay | the split configs and the per-binary build | 3 |
| overlay → group (disc folder, archive) | the load map | 2 |
| game or SDK | the library-object boundaries; the census `kind` | 2, 5 |
| totals and matched counts | the census and the build's progress denominators | 5 |
| the report and its badges | the progress publisher | 9 (Publish) |

- **At bootstrap (S8)** the README is psxdecomp's template (`profiles/psx/README.md.template`), filled with the values
  the kit filled its skeleton with. `config/discs.tsv` is written when the answers carry a disc serial and a boot
  file name of the disc's own form. The progress block says "not published yet".
- **Phases 4 to 8** cost nothing extra. The badge table holds no numbers (decomp.dev serves them live), so banking a
  function never makes a README block stale. The game's own numbers block (the kit corpus `progress.py`, between
  `<!-- progress:begin -->` and `<!-- progress:end -->`) is a second number: the lint warns until the game retires
  it. psxdecomp's markers are namespaced `psxdecomp:`, so the two never collide.
- **The first publish of phase 1.9** creates `config/categories.tsv`. From that commit on its ids are frozen.

## Category ids: `config/categories.tsv`

Tab-separated, `#` comments allowed, header `id parent name status`. It holds identity only, with no membership
column: a list of member globs would copy the load map and could drift from it.

- `id`: `[a-z0-9_]+`, or `parent.child` with one dot (decomp.dev nests one level under the parent). `game` and `sdk`
  are required (decomp.dev's guide). Every other top-level id is one binary or one overlay group, and `main` is the
  boot executable's game code.
- **An id comes only from a fact that cannot change**: a disc file name or an archive entry index, never an inferred
  grouping such as a load slot or a guessed stage. A re-classified overlay keeps its id and its history.
- `parent`: empty for a top-level id; the id's prefix for a child.
- `name`: free text, improved as overlays are identified ("Rock 05" until the evidence names it). decomp.dev takes
  names from each report, so a rename costs nothing.
- `status`: `active` or `retired`. **A published id is never deleted or renamed**: decomp.dev keys each category's
  history by id, and a changed id silently starts a new, empty history. `categories --history` checks every committed
  version of the file.

Membership is decided at report time by the game's publisher, from the records in the table above. A unit lists
exactly one of `game` / `sdk`, plus `main`, or plus `<group>` and one `<group>.<file>`. A file with no code belongs to
no category: a category whose total code is 0 would show 100% matched.

## The report contract

decomp.dev ingests an objdiff `report.json` from a GitHub Actions artifact on a completed `push` run of the default
branch.

- **Version 2.** decomp.dev migrates v0 and v1 reports and refuses any other version. A v2 report's category measures
  are read exactly as written; nothing is recomputed. A generator that does not use objdiff-cli must therefore compute
  every category's measures itself, `total_units` and `complete_units` included.
- **Artifact `<EXE>_report`**, where the version is the boot executable's file name, e.g. `SLUS_000.00_report` (the
  decomp.dev guide's own example has this form). The file inside is `report.json`.
- **Every linked object is a unit**, the SDK's too, so the report sees the whole binary.
- **uint64 fields are decimal strings** (proto3 JSON). decomp.dev's parser would also take numbers; strings are the
  form every parser accepts.

The game emits units with their `progress_categories`; psxdecomp keeps the arithmetic:

```sh
python3 tools/psxd_publish.py categorize units.json --categories config/categories.tsv -o report.json
python3 tools/psxd_publish.py validate report.json --categories config/categories.tsv \
    --artifact SLUS_000.00_report --exe SLUS_000.00
```

`categorize` writes `version: 2`, the report's measures, and every active category's measures, named from the TSV.
It refuses an unregistered or retired id, a child listed without its parent, a unit in two overlays of one group, a
unit that is neither `game` nor `sdk` (or both), an active id no unit lists, and an active id with no code.
`validate` checks the schema, the firewall (no field outside report.proto, no long hex or base64 run), every ratio,
every category's sums against its units, the ids and their parents, and the artifact name. `decompdev.py validate`
is the same check from the plugin.

The upload step is the last step of the public repo's `build.yml`, which runs after the byte check (the template,
`profiles/psx/build.yml`; doctor's `progress` row lints a workflow like it). Push only for decomp.dev, ROM-free in
what it uploads. The report generator is a marked placeholder there: each game's phase 1.9 decides it.

A repository admin then registers the project at `https://decomp.dev/manage/new`. Its `default_category` is not on
that form, so the project page and an unfiltered badge show game and SDK together; the README's headline badges
carry `category=game`.

recomp.board ([recomp.fyi](https://recomp.fyi)) reads the same `<EXE>_report` artifact, once a day, from a workflow
on the default branch, so there is nothing to configure: a decomp that publishes the report needs no `.recomp.json`
and no form (psxdecomp adds none). Three things still apply:

- **A row must exist.** The board's scan finds most public decomps; otherwise the developer sends its one-field "add a
  project" issue form once. That is an outward step, the developer's (G64).
- **The activity clock.** A row reads Quiet after 90 days without a commit on the public repository and Dormant after
  180. In split mode the public repository moves only at releases and contributor merges, so a release at least every
  ~80 days keeps the row active. The same cadence keeps a report inside the 90-day artifact retention.
- **The cutover window.** The row follows the URL. Between renaming the old repository to `<game>-dev` (private) and
  creating the new public `<game>`, the URL redirects to a private repository, and the daily read may mark the row
  "repo missing". Do the rename and the create in one sitting, and check the row the next day.

## Split mode: a public trunk, a private workspace, a private store

A game can run as three repositories. Without `[public]` in `config/psxdecomp.toml` none of this applies.

| | `<game>` (public) | `<game>-dev` (private) | `<game>-private` (private) |
|---|---|---|---|
| Who works there | contributors, by fork and PR; the owner squash-merges | the agents, unchanged | nobody: almost write-once |
| Holds | the paths in `config/public-paths.txt` | everything tracked; never a game byte (G12) | the build's input files, the hash lists, an optional backup |
| Moves to the next by | `import`, then `land` at a phase end | `release` (a PR) | read by public CI through a deploy key |
| CI | `build.yml` (the byte check and the report) and `no-rom.yml` | the game's own; `build.yml` is guarded off | none (Actions disabled) |

Skeleton of `<game>-private`: `profiles/psx/private/`. Toolchain image recipe: `profiles/psx/image/Dockerfile`.

### Overrides

Split mode replaces two kit rulings ([ECOSYSTEM.md](ECOSYSTEM.md) K14, K15). The visibility flip of phase 1.9: nothing is
flipped; the public repository is created empty and release 1 is its first commit. `no-rom.yml`'s "byte-identity … is
therefore never in CI": the public `build.yml` byte-checks every push and pull request with the files from
`<game>-private`; `no-rom.yml` stays, a required check too.

### `[public]` and the list

```toml
[public]
repo = "owner/game"                  # the public repository
dev_branch = "main"                  # releases are cut from it; land fast-forwards it
checks = ["build SLUS_000.00", "public-clean audit (no game bytes)"]    # required on public main
image = "ghcr.io/owner/game-toolchain@sha256:<64 hex>"                 # public, open-source tools only
private_repo = "owner/game-private"
private_rev = "<40 hex>"             # the -private commit CI reads
land_check = ["<the game's byte check of a tree>", "{tree}"]
deny = []                            # never-public entries beyond the built-in agent paths and PA3's managed files
keyed = {"config/c_units.tsv" = 2}   # optional: tables import merges row by row, keyed on the first n columns
assisted_by = "…"                    # optional: the release's Assisted-by trailer
```

`config/public-paths.txt` is one list, itself public. An entry ending in `/` is a directory prefix; any other entry
is an `fnmatch.fnmatchcase` glob (`*` crosses `/`). Default deny: a tracked file no entry matches stays private.
`check-public [DIR]` FAILs on an unlisted file, on an agent path even if listed (`CLAUDE.md`, `.claude/`,
`docs/ops/`, PA3's managed files, `[public].deny`), and on a missing list.

`list --draft` prints a first list: every tracked file outside the deny set, with a directory that has nothing private
below it folded into `dir/` (a file added there later is public without an edit; a list kept file by file leaves new
tools behind). It warns when a public build file (the Makefile, `*.mk`, a workflow, `config/`, a tool) names a path
that stays private. What must stay private beyond the agent files goes in `[public].deny` first. `list` alone prints
the files the committed list publishes.

### `ci-sim`: the workflows on the tree that will be public

```sh
python3 tools/psxd_publish.py ci-sim [--workflow no-rom|build] [--projection] [--rev REV] [--private DIR] [--image REF]
```

It runs a workflow's `run:` steps as written, one job at a time, on a fresh clone of dev at REV (tracked files only,
what dev's CI gets) or, with `--projection`, on REV's release projection (what the public repository's CI gets). A dev
checkout hides both gaps: its ignored files (a fetched compiler, `asm/`) satisfy a step that fails in CI, and the
projection can lack a file a step calls. `no-rom` runs in a clean `ubuntu:24.04` container that has only the runner
tools the kit's steps name (`SIM_APT` in the code); `actions/setup-python` becomes a venv of that version. `build`
starts containers itself, so its steps run on this machine: `--private` is a local `<game>-private` checkout (the
deploy-key checkout's stand-in, read at `[public].private_rev`) and `--image` replaces `[public].image`, e.g. a local
tag before the push. Other `uses:` steps are named and skipped, except `upload-artifact`: its file must exist. An
expression in a `run:` body is refused, never guessed. It simulates a push to main, not a pull request.

### Release (dev to public)

```sh
python3 tools/psxd_publish.py release --summary "what this brings, in your words" [--rev REV] [--ack-new] [--dry-run] [--push]
```

`release` is the primitive: release 1 uses it, and [`ship`](#releasing-with-ship) runs it for every later release.
Developer-only: it refuses in an agent session (`CLAUDECODE`) unless `--dry-run`. It never writes a worktree. It works
in a bare cache, `.git/psxdecomp/public.git`, which borrows dev's objects and fetches public `main`:

1. **Sync check:** every contributor commit on public since the first release must already be imported into dev at
   REV (by its `Imported-From:` trailer). Otherwise it names them and stops: release never reverts a contributor.
2. **Exact projection:** the release tree is dev's listed, non-denied files at REV, nothing else. A path that left the
   list is deleted. Symlinks and gitlinks are refused.
3. **New paths** are listed; a release that adds any needs `--ack-new`.
4. **Preflight**, before any ref exists: `check-public` on the tree, the README lint, and the game's audit
   (`tools/audit_public.py`) on an export of the tree.
5. **One reproducible commit** on public `main` (same inputs, same sha), branch `release/<sha10>`, message `Release:
   <summary>`, then the body: the summary and the trailers (`Assisted-by:` when `[public].assisted_by` is set, then
   `Release-Of`, `Release-Tree`, `Release-Base`, last). `--push` pushes the branch and opens the PR (refused while
   another release PR is open); without it the two commands are printed.
6. **Release 1** has no `main` to open a PR against, so it becomes `main`: `--push` runs `git push <url>
   <sha>:refs/heads/main` (without `--push` the command is printed). That push is legal only before the rulesets
   exist, so `settings --apply` comes after it. Every later release takes the PR path.

The squash commit (`PR_TITLE` + `PR_BODY`) keeps the trailers. A public commit counts as a release only when its
subject starts `Release: `, its `Release-Tree` equals the projection of dev at `Release-Of`, and that `Release-Of`
was not used before (or, after a purge rewrote dev, its own tree equals `Release-Tree`).

### Releasing with `ship`

```sh
python3 tools/psxd_publish.py ship --summary "one line, in your words" [--rev REV] [--ack-new] [--dry-run] [--no-wait] [--timeout MIN] [--replace] [--merge-reviewed]
```

`ship` is every release after the first, start to finish, in one command the developer runs, typically right after
the phase-end push. It refuses in an agent session (`--dry-run` excepted) and refuses release 1. Each stage prints
`SHIP <stage> OK|FAIL …`, and nothing reaches public before the first five pass:

1. **state:** REV (default: the dev branch tip) must be `origin/<dev_branch>`, so a release is always a commit -dev
   has and its CI tested. A release of REV already on public main skips to stage 9; an open `release/<rev10>` PR
   skips to stage 7. An open release PR of another revision refuses, unless `--replace`: ship closes it at stage 6.
2. **dev-ci:** every workflow run of -dev at REV (the newest per workflow and event) completed and passed; a job
   guarded off by its repository condition counts as skipped, not failed. A failure names its jobs; a run in progress
   is waited for, up to `--timeout` minutes (default 90).
3. **gate:** `release`'s checks, without a ref: the sync check, the exact projection, the new paths (asked on a TTY,
   refused off one without `--ack-new`) and preflight.
4. **build:** `[public].land_check` on an export of the projection: the game's byte check proves the published files
   build before public sees them. Without `land_check` ship refuses.
5. **ci:** [`ci-sim --projection`](#ci-sim-the-workflows-on-the-tree-that-will-be-public) for `no-rom`: the public
   repository's game-free jobs, as `no-rom.yml` writes them, on REV's projection in a clean container. It catches a
   file public CI needs but the list leaves out, and a job that is green only on a dev checkout. It needs docker, as
   `land_check` does. `--dry-run` stops here.
6. **push:** the release branch is pushed (it is public from that moment, which is why every leak check ran first)
   and its PR opened.
7. **checks:** ship polls the PR head's check-runs until every `[public].checks` entry has completed (`--no-wait`
   stops before this), then holds the head to what ship builds (its `Release-Of`, `Release-Tree` and tree, its parent
   public main) and runs `verify-pr`'s checks on it as the owner's own release PR. A release that changes a workflow
   stops with the diff command; after the owner's review, `--merge-reviewed` accepts that check.
8. **merge:** `gh pr merge N --squash --admin --match-head-commit <head>` ([who merges what](#the-public-repo-standard)).
9. **verify:** public main carries the release of REV with its trailers, every push run at it passed, and each
   `build <EXE>` run uploaded `<EXE>_report`. ship prints `SHIP OK` with the PR and run URLs and adds one line to
   `.git/psxdecomp/ships.tsv` (date, REV, public sha, PR, file count; local only).

Rerunning the same command resumes: public's state decides the stage. A red release PR is fixed forward: close nothing
by hand, fix in dev, push, then `ship --replace`. In a split-mode game, `/psxdecomp:upgrade` writes the operator's
card (`docs/ops/psxdecomp-split.md`, from `profiles/psx/split-mode.md`): the cadence, each stage's fixes, contributor
PRs.

### Import and land (public to dev)

```sh
python3 tools/psxd_publish.py import [--accept-governance] [--skip SHA]
python3 tools/psxd_publish.py land [TIP]
```

`import` builds one dev commit per pending contributor commit, in the cache only: dev's refs, index and worktree are
untouched. The contributor stays the author (with their `Co-authored-by:` lines); the subject is `Import <date>:
<title>`, the trailer `Imported-From: <public sha>`. It refuses a denied or unlisted path, a symlink, a revert of a
release, a non-squash merge, and a conflict; a governance path (the list, `config/psxdecomp.toml`, `.github/`,
`Makefile`, `tools/`, ...) needs `--accept-governance`; `--skip` records a commit dev must never take.

A table both sides append to (dc2's `config/c_units.tsv`, one row per carve) conflicts in a 3-way merge whenever the
agents banked since the last land. A path in `[public].keyed` is then merged row by row on its first n tab-separated
columns. Comment lines are dev's; a row changed on one side takes that side; the contributor's new rows follow dev's.
Two different changes to one key, or a deletion on one side and a change on the other, still refuse. `land_check`
builds the merged tree before dev moves.

`land` is developer-only and runs at a phase end. It fast-forwards dev to the import chain only when the agents are
idle (`.run/status.json` clear, PA3's loop off with no live session, no gate lock, no pending INBOX bullet or
REVIEW/REPLAN, no open wave)
and the chain's tree passes `[public].land_check`, the game's byte check. Each refused condition is named.

### The local guard on dev

```sh
python3 tools/psxd_publish.py hook [--install]
```

GitHub enforces nothing on a Free private repository, so dev is guarded on the developer's machine. `hook --install`
writes `.git/hooks/pre-push` (never over another hook). The hook refuses any push from an agent session (`CLAUDECODE`),
a push of dev to the public repository (by `[public].url` or the GitHub slug, which also catches an old URL that now
redirects to it), and a deletion or force-push of the dev branch.

It is also the push gate. On a push of the dev branch to any other remote it builds the projection of the pushed
commit offline (no fetch; public main as the cache last saw it) and runs the release gate on it:

- **Blocks the push** (`PRE-PUSH FAIL`): a listed path that is denied, a symlink or a gitlink, a check-public
  failure, or a failing audit. These would leak at the next release.
- **Warns only** (`PRE-PUSH WARN`): a README lint failure, no audit configured, new public paths (not counted
  until the cache holds public main: ship and `release --dry-run` fetch it), nothing new to release. Otherwise the
  last line is `PRE-PUSH release-ready: N files, M new`.

The hook file itself never changes; the vendored tool carries the gate. `git push --no-verify` skips every hook: the
developer's escape hatch for a broken hook, and the reason the agents' deny list refuses it. That list is `profiles/psx/deny.json`: S10 writes its rules to a game's
`.claude/settings.json` `permissions.deny`; `/psxdecomp:upgrade` adds any missing and never removes one. doctor's `split-guard` row FAILs while the hook is missing, origin is the
public repository, or a workflow's action is not pinned to a full commit SHA (the public standard requires it, so
GitHub would not start that job). In split mode the README names `[public].repo`, never dev's origin.

### Public CI: `build.yml`

`profiles/psx/build.yml` is the template (`/psxdecomp:upgrade` writes it once, filling `{{REPO}}` and `{{EXES}}`).
It runs on `push` to main and on `pull_request_target` for every PR, so each PR runs main's copy of the file:

- **The code under test** is the pushed commit, or the PR's merge commit `refs/pull/N/merge`, taken only once
  GitHub has built it from the PR's current head on the current base. The event can arrive before GitHub
  computes it, so the job waits for it instead of reading the event's merge commit.
- **The game files** come from `<game>-private` at `[public].private_rev`, checked out with the read-only deploy key
  `PRIVATE_DEPLOY_KEY`. GitHub never passes that secret to a workflow triggered from a fork, so a workflow a fork adds
  can't reach them. A fine-grained PAT with read access to `<game>-private` alone works the same way: store it as
  `PRIVATE_REPO_TOKEN` and change the checkout's `ssh-key:` line to `token: ${{ secrets.PRIVATE_REPO_TOKEN }}`. The
  deploy key is the default because it opens one repository and never expires; a PAT must be renewed before it expires.
- **Fork PRs wait** in the `fork-review` environment, whose required reviewer is the owner. Other runs use the `ci`
  environment.
- **One job per EXE (`build <EXE>`), never skipped by a condition:** a skipped job counts as a passing required check.
  Its only condition is the repository guard, so the job doesn't run in `-dev`.
- **The runner runs no PR code.** It reads `[public]` with its own inline code. For a fork PR it uses the base's
  `[public]` and the base's `tools/psxd_publish.py`.
- **The deploy key leaves first.** The private checkout runs before any PR code, its key is not persisted, and the
  files move out of the workspace.
- **PR code runs only in containers** on a copy of the tree without `.git`. The toolchain fetch has the network but
  no game file. The build has the game files but no network, and its output goes to a file. The log shows only
  `ci-log`'s filtered summary: no `asm/` lines, no hex runs, no instructions.
- **The byte check** uses `<game>-private`'s `check/<EXE>.sha1`, never a copy from the PR.
- **The report** is validated by the trusted `psxd_publish.py validate` and uploaded as `<EXE>_report` only by a
  fully green run. No cache, no `always()`, no `continue-on-error`.

doctor's workflow lint (`lint_split_build`) holds the file to these invariants; `tests/test_static.py` plants a
violation of each.

A same-repo PR (a release) is tested with its own `[public]`, so a new image or `private_rev` is proven before it
merges. A change to `build.yml` itself first runs on the push to main after merge.

What stays a residual risk: an approved fork PR's build runs with the game files present. The defences are review
before approval, the code owner's review of governance paths, the network-less build, the filtered log, the
validated report, `verify-pr` before merging, and dev's own byte check at `land`.

### The public-repo standard

```sh
python3 tools/psxd_publish.py settings [--apply]
python3 tools/psxd_publish.py verify-pr N [--merge]
```

`settings` compares the public repository with the standard and prints each drift. `--apply` (developer-only) writes
it with `gh api`. doctor's `public-standard` row runs the same comparison read-only.

- **Merges:** squash only; title `PR_TITLE`, message `PR_BODY`; branches deleted on merge; forking on; wiki and
  projects off.
- **Security:** secret scanning and push protection; private vulnerability reporting; Dependabot alerts; a read-only
  default `GITHUB_TOKEN`; SHA-pinned actions; fork-PR approval for all external contributors; artifact retention 90
  days.
- **Ruleset `main-integrity`** (no bypass actors): no deletion, no force-push, a PR required, squash only, and the
  checks in `[public].checks`. They must be strict (up to date) and come from GitHub Actions. Nobody, the owner
  included, merges a red or stale check.
- **Ruleset `main-review`** (admin bypass in pull-request mode): one approving review and the code owner's review.
- **Environments:** `fork-review` (the owner as required reviewer, branch `main` only) and `ci` (branch `main` only).
- **Others:** the secret `PRIVATE_DEPLOY_KEY` (or `PRIVATE_REPO_TOKEN`); `.github/CODEOWNERS` on main. Turning off administrator bypass in
  the environment is a UI-only setting.

`verify-pr` checks a PR before the owner merges it. Each required check must come from `.github/workflows/build.yml`
under `pull_request_target`, on the PR's current head, with success. A check forged by a workflow a fork added fails
this. A fork PR that carries `Release:` or `Release-*` trailers is refused.

Who merges what:

- **A contributor's PR:** `verify-pr N`, then the owner's approving review, then `verify-pr N --merge` (a squash pinned
  to the head it checked).
- **A release PR** is the owner's own, and GitHub never lets an author approve their PR, so `main-review` is passed with
  the admin bypass: `gh pr merge N --squash --admin --match-head-commit <head>`. `main-integrity` has no bypass: the
  checks must still be green and up to date.
- **A release that changes a workflow** (`no-rom.yml`, `build.yml`) makes `verify-pr` refuse, since that check would
  certify itself. The owner's review of the diff is the gate; then the admin merge above.

### Cutover order

An existing game moves to split mode in this order, one game at a time. Every outward step is the developer's; the
agents' deny list and the `CLAUDECODE` refusal stop an agent from running them. The developer runs them in a terminal
outside Claude Code: a `!` command typed in a Claude Code session inherits `CLAUDECODE`, so the hook, `release`,
`land` and `settings --apply` refuse it. An agent may prepare each step, print its commands and verify it afterwards,
read-only.

0. Before anything is renamed or created, in the checkout:
   - `git remote set-url origin https://github.com/<owner>/<game>-dev.git`, even when the rename is already done. A
     checkout whose origin still names `<game>` reaches `-dev` only through GitHub's redirect, and the same
     `git push` reaches the public repository from the moment it exists.
   - `git config core.autocrlf false`: the vendored `tools/psxd_publish.py` stays byte-identical to the plugin's.
   - Dev's CI is green: doctor's `dev-ci` row is OK, and `ci-sim` passes on dev's HEAD. A check that is red on dev is
     red on public, and once required it blocks every pull request there (dc2's `compile-only`, red for 8 days before
     its release, 2026-10). Fix what the tools own; what an agent's code owns goes to its INBOX and waits.
   - `/psxdecomp:upgrade`, then doctor's `readme` and `publish-tool` rows OK, `.github/CODEOWNERS` tracked, and every
     workflow's actions pinned to a full commit SHA (the kit's `no-rom.yml` uses tags).
1. Rename `<game>` to `<game>-dev`, make it private, and create the empty public `<game>` in the same sitting: until
   it exists, the old URL redirects to `-dev` (release refuses a URL that reaches dev's own history, and recomp.board
   may mark the row "repo missing"). Recheck the fork count. Then `hook --install`.
2. Create `<game>-private` (private, Actions off, forking off where GitHub allows it: an organization's repository)
   and push the build inputs, `check/<EXE>.sha1` and the optional backup. Add a read-only deploy key.
   `psxd private_init --repo <dev> --out <dir>` builds the local repository, checks each input against the hash list
   and prints these commands; the key pair goes in `~/.ssh/psxd/`. On a personal account its owner, the only
   collaborator, can still fork it, even into an organization that disallows private forks; doctor's `private-repo`
   row FAILs on any fork.
3. Stop the game's agents (`.run/status.json` clear, no PA3 session, no open wave, no build container): this step
   commits to dev. First record the sha1 of what the agents left pending (`.run/status.json`, untracked logs,
   `phase-ends/current/INBOX.md`), outside the repository: those files are byte-identical when the agents resume.
   Put what must stay private beyond the agent files in `[public].deny`, take `list --draft` as
   `config/public-paths.txt`, and commit it with `[public]` (with `private_rev`) and any README fixes.
   `/psxdecomp:upgrade` then writes `build.yml`. `release --dry-run` must pass, then `ci-sim --projection`: the public
   tree runs its own `no-rom` green before anyone sees it.
4. Build the image with `profiles/psx/image/build.sh` and the game's args (two builds, one image), run
   `layer_audit.py` on it against the local `<game>-private`, push it to ghcr and make the package public (GitHub's
   UI). An anonymous pull must return the digest the build printed; set `[public].image` to it. Then
   `ci-sim --workflow build --private <dir>` must end in the byte check and, with a category list, a valid report.
5. Release 1:

   ```sh
   git push origin main
   gh secret set PRIVATE_DEPLOY_KEY --repo <owner>/<game> < ~/.ssh/psxd/<game>-private
   python3 tools/psxd_publish.py release --summary "Release 1: the public tree" --ack-new --push
   python3 tools/psxd_publish.py settings --apply && python3 tools/psxd_publish.py settings
   ```

   The secret comes first because release 1's push run needs the key; `settings --apply` comes last because its
   rulesets would refuse that push. Then turn off administrator bypass in both environments
   ([the standard](#the-public-repo-standard): UI only). doctor's `public-standard`, `private-repo` and `split-guard`
   rows must be OK, and `build <EXE>` green on main with the report uploaded. Delete the key pair's local files only
   after that green run. A red first run is fixed forward: release 2, merged as the standard's release PRs are.
   Release 1 is the only manual release; every later one is [`ship`](#releasing-with-ship).
6. Back to the decomp: add the two bullets below to the agents' INBOX (uncommitted, the agents take them), check the
   pending files against step 3's hashes, and resume the agents. The next day, check the recomp.board row and
   decomp.dev ([the report contract](#the-report-contract)). The first fork PR goes through `verify-pr`, then the
   merge.

```markdown
- Split mode is live: the public repo gets only the files `config/public-paths.txt` lists (default deny). When a
  task adds a file the public build or CI needs (a tool a scanner row or the Makefile calls, a new config table, a
  new docs page meant for contributors), add its path to `config/public-paths.txt` in the same commit. Standing fact
  for HOW_WE_WORK.md.
- `no-rom` is a required check on the public repo. Every step that banks or propagates code runs the game-free
  scanners it runs (`make format-check`, `make compile-only`, the type check) before it commits: a bank that turns
  one red blocks every public pull request until the next release.
```

## The README

Sections, in order (H1 title first, an HTML banner may precede it):

| Section | Holds |
|---|---|
| `## Description` | what the game is and what the project rebuilds; the AI policy block, verbatim; the generated disc block; a `> [!IMPORTANT]` note that the repository holds no game data |
| `## Progress` | the generated progress block; optional prose (what an overlay is, what "matched" means); the game's own numbers block |
| `## Building the decompilation` | requirements, the command block, and the line a green build prints; before the first build, an honest "not buildable yet" line |
| `## Repository layout` | a `Path` / `Contents` table of real paths |
| `## Getting started` | `### Setting up`, `### Contributing`, `### Reference`: one sentence and one link each |
| `## Acknowledgements` | the community work the project stands on |
| `## License` | the project's licence and the no-licence statement over `src/` |

Other sections may follow Acknowledgements (Contact, links), never precede it. The shape follows soul-re
(Description, Progress, the three short subsections), Lain (the disc table, the build block, the layout table) and
recvx-decomp (the AI notice). Prose stays human-written; only the two marked blocks are generated.

### The generated blocks

`python3 tools/psxd_publish.py render README.md --write` rewrites only these:

- `<!-- psxdecomp:disc:begin -->` … `end`, under Description: `Disc | Serial | Executable | SHA-1 of the data
  track` from `config/discs.tsv` (`disc serial executable track source`) and `config/medium.sha1`, then the target
  executable's SHA-1 from `config/check.*.sha`, labelled as the target (a rebuilt hash exists only once a binary
  matches). "(Redump)" is printed only for a row whose `source` is `redump`, that is, the hash was checked against
  Redump.
- `<!-- psxdecomp:progress:begin -->` … `end`, under Progress: the headline Code and Functions badges
  (`category=game`), then one row per active top-level id (the SDK last), each with `category=<id>` badges linked to
  that category's decomp.dev page. Under the table, each group with overlays gets a collapsed `<details>` list of its
  active `<group>.<file>` ids, with the same badges, so a 50-overlay game keeps a short table. OWNER/REPO is
  `git remote get-url origin`. Without a categories list it is the "not published yet" line.

### The lint

`python3 tools/psxd_publish.py lint README.md [--release]` prints `README FAIL|WARN|INFO <check>: <detail>`.

| Check | FAIL when |
|---|---|
| title, headings | no `# ` title; a section missing, repeated or out of order; an unknown `## ` before Acknowledgements; a `###` of Getting started missing |
| ai-policy | the block is missing, repeated, altered or outside Description; the old disclosure sentence is present |
| no-game-data | Description lacks the `[!IMPORTANT]` no-game-data note |
| blocks | a marker pair missing or misplaced; a block differs from what `render` writes |
| numbers | `## Progress` types a percent other than `100%`, or an `N of M` count, outside the generated block. A place in a series (`phase 1 of 3`) is no count. A marker inside a code fence hides nothing, and a numbers block with no end marker fails. A numbers block of the game's own also fails when no tool wrote it. A tool's block starts with a `generated by` comment or with the table header of the kit's `progress.py`. The check reads digits only, and it reads a line of an indented code block as prose |
| categories, discs | the record breaks its rules (INFO when absent; FAIL with `--release`) |
| disc | a SHA-1 in Description is in no tracked record (`config/medium.sha1`, `config/check.*.sha`, the extraction manifest) |
| badges | a decomp.dev URL names another repository, a measure decomp.dev does not render, or a category that is not active (decomp.dev would silently fall back to the whole report) |
| layout | a path is neither tracked nor git-ignored (WARN when it exists only on this machine) |
| build | a `make <target>` in a command block or code span is no Makefile target |
| links | a relative link is neither tracked nor git-ignored |
| todo | a `TODO(phase-` line (WARN; FAIL with `--release`) |

It reads one README, two small records, the Makefile and `git show` of one file's history, with the standard
library only, in well under a second.

The decomp.dev report is the one published number. `render` writes one sentence under the table that says what the
number counts. A numbers block of the game's own that a tool generates is a WARN, also with `--release`: retire it.
After an upgrade, the `readme-blocks` action of `/psxdecomp:upgrade` regenerates the two blocks.

A release runs the same debt check as the README workflow, on the tree that it would publish. `ship` and `release`
refuse a tree whose `config/debt-baseline.txt` is missing or not equal to its source, and name the command that
updates it. A row of a file that the tree does not publish is no finding. The pre-push hook of the development
repository warns for the same finding.

`validate` holds the report to the same rule. A unit whose `source_path` is not a C or C++ file (`.c`, `.cpp`,
`.cc`, `.cxx`) reports no matched code. Assembly is never credited, also a hand-written file that
`config/asm-evidence.tsv` accepts: that ledger clears the file's debt, it does not make it decompiled code. A unit
that reports matched code and names no `source_path` is a `REPORT WARN` line: the check cannot read it. For each
top-level category `validate` prints how many matched functions are 8 bytes or less, as an INFO line.

`categorize` marks a unit complete when its source is a C or C++ file, it has code, and all its code and data match. The
tool objdiff gives this mark to a unit of a module that the build checks byte for byte. The build workflow does that
check before the report. So on decomp.dev, a unit that `categorize` marks is a matched C file. It is not a finished file
(`rules/FIN1.md`). `validate` refuses an assembly unit that is marked complete.

## The writing style of the public prose files

The rules are in [CONTRIBUTING.md](../CONTRIBUTING.md#writing), in the style of ASD-STE100. A game counts the
findings of its public prose files with the vendored tool.

A public prose file is a `.md` file that `config/public-paths.txt` covers and that no deny entry covers. With no
public list, it is every `.md` file outside the agent paths and PA3's managed files. A file that git ignores is never a public prose file.

| Command | Result |
|---|---|
| `python3 tools/psxd_publish.py style FILE...` | Each finding of the named files, whatever their path. |
| `python3 tools/psxd_publish.py style` | A failure when the count of a public prose file is over its row. |
| `python3 tools/psxd_publish.py style --update` | Lower rows, at the counts of now. It refuses a rise. |

The ratchet is `config/style-ratchet.txt`. S10 and `/psxdecomp:upgrade` write it once, and then it is the game's.
It has two kinds of line:

- `<count> <path>`: the highest count that this file can have. A file with no row has row 0.
- `skip <entry>`: an entry in the syntax of the public list. `style` does not check a file that the entry covers.
  The first ratchet has the kit's five documents in `skip` lines.

The README workflow runs `style`. In split mode, the CI of the public repository runs that workflow too. Thus
`config/public-paths.txt` must list `config/style-ratchet.txt`. When it does not, upgrade plans the manual action
`style-public`.

S10 and upgrade also add a `PostToolUse` hook to `.claude/settings.json`. After a Write, an Edit or a Bash call, it
runs `style --hook`. The hook reports the findings in the public text that the agent changed. It never blocks.

## Enforcement

- **CI:** `.github/workflows/psxdecomp-readme.yml` runs the lint and `categories --history` on every push and pull
  request (full history, read-only token, actions pinned by commit SHA).
- **`/psxdecomp:doctor`:** the `readme` row FAILs without the AI policy block; on a README that carries the progress
  block it runs the lint and FAILs on a lint failure; an older README WARNs. The `publish-tool` row WARNs when the
  vendored lint or its workflow differ from the plugin's; the `categories` row checks the list and its freeze.
- **`/psxdecomp:upgrade`:** writes the vendored lint and the workflow (psxdecomp owns both), and lists the README's
  lint failures as a manual action; the prose is the developer's.
- **Phase 1.9:** a suggested milestone command for the Publish phase (its last task's `Verified:` line):
  `python3 tools/psxd_publish.py lint README.md --release && python3 tools/psxd_publish.py categories --history`
  and a validated report uploaded as `<EXE>_report`.

## Sources (read 2026-10-04; recomp.board 2026-10-09)

- The decomp.dev guide: decompals/decompedia `tools/decomp-dev.md`.
- decomp.dev source (encounter/decomp.dev main): `crates/github/src/lib.rs` (artifact name, push runs only),
  `crates/web/src/handlers/report.rs` (the `parent.child` split, `?category=`, the silent fallback),
  `crates/images/src/badge.rs` (the measures), `crates/web/src/handlers/manage.rs` (the project form).
- objdiff (encounter/objdiff): `objdiff-core/src/bindings/report.rs` (`REPORT_VERSION = 2`, `migrate()`) and
  `objdiff-core/protos/report.proto`.
- recomp.board: recomp.fyi `/add` and `/spec` (spec v1), the board repository's README and CONTRIBUTING.
- Reference READMEs and category schemes: fmil95/soul-re, shdecompilations/silent-hill-decomp,
  Y0oshi/lain-psx-decompiled, AshfordFamily/recvx-decomp, Xeeynamo/ff7-decomp.

## Open questions (2026-10-04)

- A per-category badge has been read from source, never rendered: check one once a project is listed.
- Whether decomp.dev's parser takes uint64 as JSON numbers is untested; the standard writes strings either way.
- Setting a project's `default_category` needs a decomp.dev admin.
- A CI report needs the game's unit list without game data: committed records, or a person publishing locally.
  Each game's phase 1.9 decides.
