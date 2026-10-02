# Contributing

## Before a change

- Tier 0: `pytest -q tests/test_static.py tests/test_scripts.py` (free, no network beyond `claude plugin validate`).
- Tier 1: `pytest -q tests/test_pipeline.py`. It fetches the kit at its `compat.toml` pin; `PSXDECOMP_KIT` points it
  at a local copy instead. CI runs it the same way.
- CI (`.github/workflows/ci.yml`) runs tier 0 on Linux and macOS with Python 3.12 and 3.14, tier 1 on Linux, and
  tier 1b weekly. Actions are pinned to commit SHAs; Dependabot bumps them monthly.
- Every script has a `--self-test`; tier 0 runs them all.

The tiers, and what each one proves, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#testing-tiers).

## Releases and pin bumps

Follow [docs/RELEASING.md](docs/RELEASING.md). A PA3 or kit bump changes `compat.toml` and
[docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) together, after tiers 0–2 pass on the new pin.

## House rules

- One home per fact: fix a duplicate by linking to its home, never by copying (tier 0's `test_no_copied_prose`).
- A toolchain version or a game named in a doc carries its date or scope (`fetch_refs.lint_scope`).
- No game byte, no SDK file, no disc image, ever (`tools/audit_public.py`).
