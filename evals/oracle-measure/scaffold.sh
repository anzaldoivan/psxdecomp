#!/bin/sh
# A bootstrap at the gate, with the developer's copy of another build in the ignored disks/builds/<id>/ of the folder.
# The homebrew fixture disc is built in the ignored disks/dump/ of the folder (the eval sandbox reads nothing outside
# it) and identified (S2); its planted debug file is taken out of medium.json. The copy is the fixture's second build (make_disc.py --proto). S3's drafts hold an invented lead for it:
# a review build, whose page states the copy's SHA-1. S4 must measure it and keep the page's class.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
disc="$(pwd -P)/disks/dump"
mkdir -p "$disc"
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$disc" >/dev/null
python3 "$root/fixtures/homebrew-psx/make_disc.py" --proto disks/builds/review-1999-01-01 >/dev/null
sha=$(python3 -c 'import hashlib,sys; print(hashlib.sha1(open(sys.argv[1],"rb").read()).hexdigest())' disks/builds/review-1999-01-01/PROTO.EXE)
python3 "$root/scripts/identify.py" "$disc/HOMEBREW.cue" --target . >/dev/null
python3 - <<'PY'
import json
p = ".run/bootstrap/medium.json"
d = json.load(open(p))
d["debug_artifacts"].update(count=0, psyq_sym=0, files=[])
for k in ("files", "file_list"):
    if isinstance(d.get(k), list):
        d[k] = [x for x in d[k] if "MAIN.SYM" not in json.dumps(x)]
json.dump(d, open(p, "w"), indent=2, sort_keys=True)
PY
for s in S0 S1 S2 S3; do python3 "$root/scripts/install.py" mark "$s" --target . --note scaffold >/dev/null; done
sed "s|^DUMP_PATH: .*|DUMP_PATH: $disc/HOMEBREW.cue|" "$root/fixtures/answers.psx.txt" > .run/bootstrap/answers.draft.txt
cp "$root/profiles/psx/refs.toml" .run/bootstrap/refs.draft.toml
mkdir -p .run/bootstrap/research
cat > .run/bootstrap/research/builds.md <<MD
# builds — homebrew fixture (invented leads)
## Leads
| Lead | Source (owner/repo or URL) | Licence | What it gives | How to verify |
|---|---|---|---|---|
| PSXDECOMP Homebrew Fixture, Jan 1, 1999 review build (id \`review-1999-01-01\`, class review): no symbols | https://hiddenpalace.example.invalid/PSXDECOMP_Homebrew_Fixture_(Jan_1,_1999_review_build) (read by the scaffold) | n/a | lineage: the code that the press got | 12 function bodies are byte-identical at the mapped addresses of both builds; the page states the SHA-1 of its executable \`PROTO.EXE\`: $sha |
## archive.org items
| identifier | kind (build or document) | confirmed by | file | SHA-1 |
|---|---|---|---|---|
## Dead ends
- no demo disc and no other region found (2 searches)
## For a person to read
| URL | Why it was blocked | What to look for |
|---|---|---|
MD
cat > .run/bootstrap/prior-art.draft.md <<MD
| # | Lead | Source | Status | Evidence / how to verify | Phase |
|---|---|---|---|---|---|
| L1 | Oracle build \`review-1999-01-01\`: the Jan 1, 1999 review build of PSXDECOMP Homebrew Fixture, no symbols | https://hiddenpalace.example.invalid/PSXDECOMP_Homebrew_Fixture_(Jan_1,_1999_review_build) (the build: \`byo\`, no copy) | lead | Verify: 12 function bodies are byte-identical at the mapped addresses of both builds. The page states the SHA-1 of \`PROTO.EXE\` ($sha) and the class review | 1.2 |
MD
