#!/bin/sh
# A bootstrap at the gate: the homebrew fixture disc (it holds MAIN.SYM, the PsyQ SYM magic) built outside the folder
# and identified (S2), S0-S3 marked done, and S3's drafts in place. S4 must ask the oracle-build question from S2's row.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
disc=$(mktemp -d)
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$disc" >/dev/null
python3 "$root/scripts/identify.py" "$disc/HOMEBREW.cue" --target . >/dev/null
for s in S0 S1 S2 S3; do python3 "$root/scripts/install.py" mark "$s" --target . --note scaffold >/dev/null; done
sed "s|^DUMP_PATH: .*|DUMP_PATH: $disc/HOMEBREW.cue|" "$root/fixtures/answers.psx.txt" > .run/bootstrap/answers.draft.txt
cp "$root/profiles/psx/refs.toml" .run/bootstrap/refs.draft.toml
mkdir -p .run/bootstrap/research
cat > .run/bootstrap/research/builds.md <<'MD'
# builds — homebrew fixture
## Leads
| Lead | Source (owner/repo or URL) | Licence | What it gives | How to verify |
|---|---|---|---|---|
| The disc holds /MAIN.SYM (symbols, 8 bytes, PsyQ SYM magic) | own bytes (S2, `medium.json` `debug_artifacts`) | n/a | names and function boundaries of this build | the symbol addresses land on function starts of the boot executable |
## archive.org items
| identifier | kind (build or document) | confirmed by | file | SHA-1 |
|---|---|---|---|---|
## Dead ends
- no other build of a homebrew fixture exists
MD
cat > .run/bootstrap/prior-art.draft.md <<'MD'
| # | Lead | Source | Status | Evidence / how to verify | Phase |
|---|---|---|---|---|---|
| L1 | Oracle build: the target disc itself holds /MAIN.SYM (symbols, 8 bytes, PsyQ SYM magic) | own bytes (S2) | lead | Verify: the symbol addresses land on function starts of the boot executable | 1.2 |
MD
