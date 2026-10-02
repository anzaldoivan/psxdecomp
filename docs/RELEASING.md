# Releasing

## A release

1. Tiers 0 and 1 green locally (`pytest -q`) and in CI.
2. Tier 1b green (`bash fixtures/homebrew-psx/smoke/run.sh` → `SMOKE OK`).
3. Tier 2: `claude plugin eval . --ablation none --runs 1 --no-publish` (Bash, Write and WebFetch need
   `--allow-tools Bash Write WebFetch` for the flow cases; `refs-grep` needs `--scaffold`). Every case at 1.0, or a
   recorded reason in the release notes (a backtest miss is a flaky case, never silently passed).
   At each model release, PA3 bump and kit bump, re-run `--tag hygiene --scaffold --runs 5` on both current models.
   At each model release also run `/doctor prompt-audit` in a session here (it audits AGENTS.md, CLAUDE.md and the
   skills for instructions written for older models), and re-run `tools/ab_agents.sh`: AGENTS.md stays only while it
   scores at least as well as no file at no more than +20% cost (`tools/ab_score.py`).
4. Tier 3: `/psxdecomp:new` on one real game with your own dump, in an empty folder, stopped at PA3's first planner
   draft. Check `tools/audit_public.py` exits 0 on the tree and 1 on the planted fixture, `config/psxdecomp.toml` holds
   the pins, and `docs/ops/refs.md` lists every fetched source with its class.
5. GitHub settings: `python3 scripts/doctor.py --repo . --only github` must print no WARN (each WARN names the
   `gh api` command that fixes it; run it yourself, doctor never does).
6. Bump `.claude-plugin/plugin.json` `version`; tag `vX.Y.Z`. Never push from an agent session. Pushing the tag runs
   `.github/workflows/release.yml`: it checks the tag against the manifest, reruns tiers 0 and 1, and drafts the
   release; paste the tier 2 and tier 3 results into its notes before publishing it.

## Bumping a pin (PA3 or the kit)

1. Read the upstream's changes; record the evaluated commit in [ECOSYSTEM.md](ECOSYSTEM.md) (state `watch`).
2. Change `compat.toml` (PA3: `tag`, `sha`, `version`; kit: `digest`, or `repo` + `sha` once published) and
   `tested_on`.
3. Run tier 1; when the tree changed on purpose, regenerate the golden list (`PSXDECOMP_UPDATE_GOLDEN=1 pytest -q
   tests/test_pipeline.py`) and review its diff line by line.
4. Tiers 1b and 2; then ECOSYSTEM.md's row becomes `pinned`. Game repos move with `/psxdecomp:upgrade`.

## When the kit moves

The kit is pinned to a commit on a branch of a fork (`compat.toml [kit]`). Keep that branch: a commit no branch
reaches can stop being fetchable. When decomp-architect gets its own repository, or the branch moves, change `repo`,
`sha` and `subdir` (keep `digest` as the second check) and run tier 1 before the bump lands.
