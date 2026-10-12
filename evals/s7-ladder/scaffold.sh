#!/bin/sh
# A bootstrap at the intake: the homebrew fixture disc, and S0 to S6 run for real against the pinned PA3 in a throwaway
# config folder (as tests/conftest.py does; needs the network for the pinned PA3 clone). The case tells the child that
# it is a plain session, so `/psxdecomp:new --resume --until S7` runs the intake. The constitution it writes must
# carry the kit's ladder, and no GENERATION_PLAN.md: the planner writes that after S10.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
tmp=$(mktemp -d)
export PSXDECOMP_CACHE="$tmp/cache"
python3 "$root/fixtures/homebrew-psx/make_disc.py" "$tmp/disc" >/dev/null
pkg=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import common; print(common.resolve_pa3()[0])' "$root/scripts")
python3 "$pkg/pa_install.py" --root --yes --no-clone --config-dir "$tmp/cfg" --pa3-dir "$tmp/cfg/pa3" --no-statusline >/dev/null
python3 "$root/scripts/install.py" run --target . --answers "$root/fixtures/answers.psx.txt" --dump "$tmp/disc/HOMEBREW.cue" \
    --config-dir "$tmp/cfg" --pa3-dir "$tmp/cfg/pa3" --no-fetch --until S6 >/dev/null
