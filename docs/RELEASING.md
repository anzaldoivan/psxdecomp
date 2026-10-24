# Releasing

## A release

1. Tiers 0 and 1 green locally (`pytest -q`) and in CI.
   - Before the pull request, run `/code-review` on the release diff in a fresh session. Act only on findings about
     correctness or the release's requirements.
2. Tier 1b green (`bash fixtures/homebrew-psx/smoke/run.sh` → `SMOKE OK`).
3. Tier 2: `claude plugin eval . --ablation none --runs 1 --no-publish`.
   - Run it from a worktree with no repository copy under it: the command runs every `evals/` folder it finds.
   - The flow cases need `--allow-tools Bash Write WebFetch`. `refs-grep` needs `--scaffold`.
   - Every case scores 1.0, or the release notes record the reason. A backtest miss is a flaky case, never silently
     passed.
   - At each model release, PA3 bump and kit bump: run `--tag hygiene --scaffold --runs 5` again on both current
     models.
   - At each model release: run `/doctor prompt-audit` in a session here. It audits AGENTS.md, CLAUDE.md and the
     skills for instructions written for older models.
   - At each model release: run `tools/ab_agents.sh` again. AGENTS.md stays only while it scores at least as well as
     no file, at no more than +20% cost (`tools/ab_score.py`). `BASE=<revision> tools/ab_agents.sh` compares the
     working tree with that revision instead.
4. Tier 3: run `/psxdecomp:new` on one real game with your own dump, in an empty folder. Stop at PA3's first planner
   draft. Check three things:
   - `tools/audit_public.py` exits 0 on the tree and 1 on the planted fixture;
   - `config/psxdecomp.toml` holds the pins;
   - `docs/ops/refs.md` lists every fetched source with its class.
5. GitHub settings: `python3 scripts/doctor.py --repo . --only github` must print no WARN and no SKIP. Each WARN
   names the `gh api` command that fixes it. Run it yourself: doctor never does. The status check that the ruleset
   requires is the `firewall` job of `ci.yml`.
6. Bump `.claude-plugin/plugin.json` `version` on the release branch. Never push from an agent session.
   - Open the pull request, wait for CI, and squash-merge it.
   - Pull `main` and tag the tip of `main` as `vX.Y.Z`. Pushing the tag runs `.github/workflows/release.yml`.
   - That workflow refuses a tag whose commit is not on `main`. It checks the tag against the manifest, reruns tiers 0
     and 1, and drafts the release.
   - Paste the tier 2 and tier 3 results into the draft's notes before you publish it.
   - Tier 1 fails when it cannot resolve a pin (no network, a digest that is not the tested one). It skips only with
     `PSXDECOMP_ALLOW_SKIP=1`.

## Bumping a pin (PA3 or the kit)

1. Read the upstream's changes; record the evaluated commit in [ECOSYSTEM.md](ECOSYSTEM.md) (state `watch`).
2. Change `compat.toml` (PA3: `tag`, `sha`, `version`; kit: `digest`, or `repo` + `sha` once published) and
   `tested_on`.
3. Run tier 1. When the tree changed on purpose, regenerate the golden list (`PSXDECOMP_UPDATE_GOLDEN=1 pytest -q
   tests/test_pipeline.py`). Review its diff line by line.
4. Tiers 1b and 2; then ECOSYSTEM.md's row becomes `pinned`. Game repos move with `/psxdecomp:upgrade`.

## When the kit moves

The kit is pinned to a commit on a branch of a fork (`compat.toml [kit]`). Keep that branch: a commit no branch
reaches can stop being fetchable. When decomp-architect gets its own repository, or the branch moves, change `repo`,
`sha` and `subdir`. Keep `digest` as the second check. Run tier 1 before the bump lands.
