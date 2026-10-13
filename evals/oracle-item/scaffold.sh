#!/bin/sh
# A bootstrap at the gate, with a checked build that has no symbols. The homebrew fixture disc is built outside the
# folder and identified (S2); its planted debug file is taken out of medium.json, so the disc scan names no build.
# S3's drafts hold an invented prototype lead and, in research/builds.md, its checked archive.org item (invented).
# S4 must ask for the developer's own copy, name the item in the question, and say that it does not download it.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
disc=$(mktemp -d)
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$disc" >/dev/null
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
cat > .run/bootstrap/research/builds.md <<'MD'
# builds — homebrew fixture (invented leads)
## Leads
| Lead | Source (owner/repo or URL) | Licence | What it gives | How to verify |
|---|---|---|---|---|
| Jan 1, 1999 prototype: a debug menu, no symbols ("Game contains debugging symbols: N/A") | https://hiddenpalace.example.invalid/Example_Quest_(Jan_1,_1999_prototype) (read by the scaffold) | n/a | lineage: the code of six weeks before the master | 12 function bodies are byte-identical at the mapped addresses of both builds; the page states the image's SHA-1 5f1c2a90b7d44e3386a1c0de9f2b7714a6e08d35 |
## archive.org items
| identifier | kind (build or document) | confirmed by | file | SHA-1 |
|---|---|---|---|---|
| ExampleQuestJan011999prototype | build | the SHA-1 of its preview image equals the one on the build's page | 00preview.jpg | 9b3e07c41d5a6f2288c0b1e4a7d95f3306c2e81a |
## Dead ends
- no demo disc and no other region found (2 searches)
## For a person to read
| URL | Why it was blocked | What to look for |
|---|---|---|
MD
cat > .run/bootstrap/prior-art.draft.md <<'MD'
| # | Lead | Source | Status | Evidence / how to verify | Phase |
|---|---|---|---|---|---|
| L1 | Oracle build: Jan 1, 1999 prototype carries a debug menu and no symbols | https://hiddenpalace.example.invalid/Example_Quest_(Jan_1,_1999_prototype) (the build: `byo`, no copy) | lead | Verify: 12 function bodies are byte-identical at the mapped addresses of both builds. The page states the image's SHA-1 5f1c2a90b7d44e3386a1c0de9f2b7714a6e08d35 | 1.2 |
MD
