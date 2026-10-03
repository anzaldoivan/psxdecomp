#!/bin/sh
# A bootstrap at the gate: the homebrew fixture disc (PsyQ 4.7 stamps) built outside the folder and identified (S2),
# S0-S3 marked done, and S3's drafts in place. S4 must word the PsyQ question from S2's version.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
disc=$(mktemp -d)
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$disc" >/dev/null
python3 "$root/scripts/identify.py" "$disc/HOMEBREW.cue" --target . >/dev/null
for s in S0 S1 S2 S3; do python3 "$root/scripts/install.py" mark "$s" --target . --note scaffold >/dev/null; done
sed "s|^DUMP_PATH: .*|DUMP_PATH: $disc/HOMEBREW.cue|" "$root/fixtures/answers.psx.txt" > .run/bootstrap/answers.draft.txt
cp "$root/profiles/psx/refs.toml" .run/bootstrap/refs.draft.toml
cat > .run/bootstrap/prior-art.draft.md <<'MD'
| Lead | Licence | Class | Status | How to verify |
|---|---|---|---|---|
| none found (homebrew fixture) | — | — | lead | — |
MD
