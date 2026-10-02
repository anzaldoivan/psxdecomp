# AGENTS.md — psxdecomp

A Claude Code plugin that bootstraps PS1 matching-decompilation repositories. Overview: [README.md](README.md);
design and test tiers: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Commands

| What | Command |
|---|---|
| Tier 0 (free; every script's self-test included) | `pytest -q tests/test_static.py tests/test_scripts.py` |
| Tier 1 (bootstraps a fixture repo; fetches the pinned kit) | `pytest -q tests/test_pipeline.py` (`PSXDECOMP_KIT=<folder>` for a local kit) |
| One script's self-test | `python3 scripts/<name>.py --self-test` → `SELF-TEST OK` |
| Firewall audit | `python3 tools/audit_public.py --self-test && python3 tools/audit_public.py` |
| Workflow lint | `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` |
| Tier 2 evals (paid) | see [docs/RELEASING.md](docs/RELEASING.md) |

## Where things live

- Pins (Project Architect version and sha, kit digest): `compat.toml`, nowhere else. Upstream ledger:
  [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).
- Stages S0–S10: `scripts/common.py` `STAGES`; their texts: `skills/new/`.
- The AI policy text: `common.AI_POLICY` (the README and every game README carry it). Install commands: `common.INSTALL`
  and `profiles/psx/hosts/*.md`.
- Reference library policy: [docs/REFS.md](docs/REFS.md); the profile's rows: `profiles/psx/refs.toml`.

## Rules

- Never push, never tag, never publish a release from an agent session.
- House rules (one home per fact, scoped versions, no game byte): [CONTRIBUTING.md](CONTRIBUTING.md#house-rules).
- psxdecomp pins no compiler. A bootstrapped game repo records only a candidate set; the game pins its own triple in
  its phase 1.4 (`docs/ops/compiler-pin.md` there).

## Stale text on purpose

`evals/` and `fixtures/backtest/` hold deliberately stale or poisoned answers (old compiler leads, wrong ids) that the
evals test against. They are not this repo's facts: never cite them as current. `.ignore` keeps them out of a root
search; open them by path when you are editing a case.
