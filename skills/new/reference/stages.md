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
| S6 PA3 | PA3's per-repo files (its installer), `.gitignore` order, `.claude/pa.json` `"upgrade": "ask"` | PA3's install commit; the order fix; the upgrade pin |
| S7 intake | `PROJECT_CONTEXT.md` and what PA3's intake writes | the intake |
| S8 kit | the kit's files (its installer); `.run/decomp-architect/`; `README.md` from psxdecomp's README standard in place of the kit's untouched skeleton (else only the AI policy block, in place of the disclosure paragraph); `config/discs.tsv` when the answers carry a disc serial ([docs/PUBLISHING.md](../../../docs/PUBLISHING.md)) | the kit's close commit; the README commit. Before them, a commit of `.claude/pa.json` when PA3's session-start hook changed it and it is the only change |
| S9 refs | `config/refs.toml`, `docs/ops/refs.md`, `.gitignore` `/refs/`, `.ignore` `!/refs/` (search still reaches refs/), `config/firewall.txt` purge line, one `HOW_WE_WORK.md` line, `docs/ops/INDEX.md` row; ignored `refs/`. The firewall's block for a debug file of any build: four `glob:` lines (`.SYM`, `.CPE`, `.PDB`, `.DBG`) | the refs commit |
| S10 handoff | `config/psxdecomp.toml`, `config/psxdecomp.profile.toml`, `docs/ops/host-recipe.md` (with install commands), `docs/prior-art.md`, the agents' deny rules in `.claude/settings.json`, `tools/psxd_publish.py` and `.github/workflows/psxdecomp-readme.yml` (the README lint and its CI), the `HOW_WE_WORK.md` scope line and C-conventions pointer. The writing rule of the public files: `rules/STE1.md` and its `rules/INDEX.md` row, the style hook in `.claude/settings.json`, `config/style-ratchet.txt`. The floor: `tools/psxd_floor.py`, `docs/ops/psxdecomp-floor.md`, `docs/ops/psxdecomp-campaign.md` and their `docs/ops/INDEX.md` rows, `config/guard.tsv`, the guard hook. Its rules and ledgers: `rules/FIN1.md`, `rules/NAME1.md`, the header lines of `config/names.tsv` and `config/asm-evidence.tsv`, `config/debt-baseline.txt`. The oracle-build record: `[oracle]` in `config/psxdecomp.toml`, and for a supplied build `config/oracle.toml` and `config/oracle.<id>.sha1` with the firewall's `required: config/oracle.*.sha1` line. S10 writes the path of the dump and of the copy to `psxdecomp/local.toml` in the git directory, and no commit holds them | the handoff commit |

Deviations (`--force-untested`, `--intake-fixture`, PA3 leaving uncommitted paths, a kit dry-run mismatch) are kept
in the state file and written into `config/psxdecomp.toml [deviations]`. A constitution that does not name the
eleven ladder phases is one more deviation, recorded at S8.
