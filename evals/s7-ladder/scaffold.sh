#!/bin/sh
# A bootstrap at the intake: the homebrew fixture disc, and S0 to S6 run for real against the pinned PA3 in a throwaway
# config folder (as tests/conftest.py does; needs the network for the pinned PA3 clone). S6 leaves "mod": "off", and
# the case tells the child so, so `/psxdecomp:new --resume --until S7` runs the intake. The constitution it writes must
# carry the kit's ladder, and no GENERATION_PLAN.md: the planner writes that after S10.
# The cache is the default one under $HOME. `claude plugin eval` gives the scaffold and the child one sandbox home, so
# the kit that this script fetches is the kit that the child's `install where` finds: the child needs no network and
# no `git` for it. (An exported $PSXDECOMP_CACHE would not reach the child.)
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
tmp=$(mktemp -d)
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$tmp/disc" >/dev/null
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import common; common.resolve_kit()' "$root/scripts"
pkg=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import common; print(common.resolve_pa3()[0])' "$root/scripts")
python3 "$pkg/pa_install.py" --root --yes --no-clone --config-dir "$tmp/cfg" --pa3-dir "$tmp/cfg/pa3" --no-statusline >/dev/null
python3 "$root/scripts/install.py" run --target . --answers "$root/fixtures/answers.psx.txt" --dump "$tmp/disc/HOMEBREW.cue" \
    --config-dir "$tmp/cfg" --pa3-dir "$tmp/cfg/pa3" --no-fetch --until S6 >/dev/null
