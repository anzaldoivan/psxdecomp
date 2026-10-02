# The stage contract

Every stage of `/psxdecomp:new`:

- reads only the pins (`compat.toml`, the profile) and the target's `.run/bootstrap/`;
- writes only what its row in the table names (S0–S4: only under the ignored `.run/bootstrap/`);
- records itself in `.run/bootstrap/state.json` (`done` / `skipped` / `failed`, a timestamp, a one-line note);
- is idempotent: re-running a `done` stage writes nothing and commits nothing (tier 1 proves it for S5–S10);
- refuses rather than guesses: a `FAIL <stage>: <reason>` line, exit 1, the state marked `failed`, nothing half-done
  committed.

| Stage | Writes | Commits |
|---|---|---|
| S0 preflight | `.run/bootstrap/preflight.json` | — |
| S1 interview | `.run/bootstrap/interview.json` (or `answers.txt` from `--answers`) | — |
| S2 identify | `.run/bootstrap/medium.json`, `seeds.txt` | — |
| S3 investigate | `.run/bootstrap/research/*.md`, `prior-art.draft.md`, `refs.draft.toml`, `answers.draft.txt` | — |
| S4 gate | `.run/bootstrap/answers.txt`, `refs.toml`, `prior-art.md` | — |
| S5 repo | `.git`, `.gitignore`, the kit's firewall pack (`config/firewall.txt`, `config/firewall-fixture.sha1`, `tools/audit_public.py`, `.github/workflows/no-rom.yml`), `LICENSE` | the first commit |
| S6 PA3 | PA3's per-repo files (its installer), `.gitignore` order | PA3's install commit; the order fix |
| S7 intake | `PROJECT_CONTEXT.md` and what PA3's intake writes | the intake |
| S8 kit | the kit's files (its installer); `.run/decomp-architect/` | the kit's close commit |
| S9 refs | `config/refs.toml`, `docs/ops/refs.md`, `.gitignore` `/refs/`, `config/firewall.txt` purge line, one `HOW_WE_WORK.md` line, `docs/ops/INDEX.md` row; ignored `refs/` | the refs commit |
| S10 handoff | `config/psxdecomp.toml`, `config/psxdecomp.profile.toml`, `docs/ops/host-recipe.md`, `docs/prior-art.md` | the handoff commit |

Deviations (`--force-untested`, `--intake-fixture`, PA3 leaving uncommitted paths, a kit dry-run mismatch) are kept
in the state file and written into `config/psxdecomp.toml [deviations]`.
