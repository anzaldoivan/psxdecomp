#!/bin/sh
# The shared poisoned fixture (labelled), plus a game rule G41 and the vendored tools/psxd_publish.py, copied from this
# checkout's scripts/publish.py as S8 writes it into every game.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
sh "$here/../_fixtures/poisoned-repo/build.sh" labelled
cat > rules/G41.md <<'RULE'
# G41 — Never key by bare function name

Scratch directories, ledgers and drafts are keyed by binary and address; each agent works in its own directory;
deliverables go to a directory no agent cleans; an agent never runs find, remove or move outside its own work
directory.
RULE
echo '- [G41](G41.md) — never key by bare function name.' >> rules/INDEX.md
mkdir -p tools
cp "$here/../../scripts/publish.py" tools/psxd_publish.py
