#!/bin/sh
# ab_agents.sh — does AGENTS.md (+ CLAUDE.md = @AGENTS.md) help an agent answer questions about this repository?
# Not installed into game repos. Paid: about 3 questions x RUNS x 2 arms x models, each capped at $0.50.
#
#   tools/ab_agents.sh [OUT_DIR]          RUNS=3 MODELS="claude-opus-5-5 claude-sonnet-5-5" by default
#
# Two throwaway copies of the current working tree (tracked + untracked, minus ignored), each its own git repository
# OUTSIDE this one, so no parent CLAUDE.md is discovered: "with" keeps AGENTS.md and CLAUDE.md, "without" drops both.
# Everything else (.ignore included) is identical. Not --bare: that skips CLAUDE.md discovery. --setting-sources
# project keeps the user's own settings and CLAUDE.md out of both arms. Scores: tools/ab_score.py OUT_DIR.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$here/.run/ab-agents/$(date -u +%Y%m%dT%H%M%SZ)}
runs=${RUNS:-3}
models=${MODELS:-"claude-opus-5-5 claude-sonnet-5-5"}
py=${PYTHON:-python3}
mkdir -p "$out"
out=$(cd "$out" && pwd)
# Neutral folder names: an arm must not be readable from its working directory.
dir_with=$(mktemp -d "${TMPDIR:-/tmp}/psxd.XXXXXX")
dir_without=$(mktemp -d "${TMPDIR:-/tmp}/psxd.XXXXXX")
trap 'rm -rf "$dir_with" "$dir_without"' EXIT
armdir() { if [ "$1" = with ]; then echo "$dir_with"; else echo "$dir_without"; fi; }

for arm in with without; do
    d=$(armdir "$arm")
    (cd "$here" && git ls-files -co --exclude-standard -z | xargs -0 -I{} sh -c \
        'test -e "$1" && mkdir -p "$2/$(dirname "$1")" && cp -p "$1" "$2/$1" || true' _ {} "$d")
    if [ "$arm" = without ]; then rm -f "$d/AGENTS.md" "$d/CLAUDE.md"; fi
    (cd "$d" && git init -q && git add -A && \
        git -c user.name=ab -c user.email=ab@example.invalid commit -qm "snapshot")
done
test -f "$dir_with/AGENTS.md" || { echo "AB FAIL: no AGENTS.md in the working tree"; exit 1; }

"$py" "$here/tools/ab_score.py" --questions | while IFS="$(printf '\t')" read -r q text; do
    for model in $models; do
        short=$(echo "$model" | sed 's/^claude-//; s/-[0-9].*$//')
        r=1
        while [ "$r" -le "$runs" ]; do
            for arm in with without; do
                f="$out/$arm-$short-q$q-r$r.json"
                [ -s "$f" ] && continue                         # resumable: a finished run is kept
                (cd "$(armdir "$arm")" && claude -p --output-format json --setting-sources project \
                    --allowedTools Read,Grep,Glob --max-turns 12 --max-budget-usd 0.5 \
                    --no-session-persistence --model "$model" "$text" </dev/null >"$f.tmp" 2>"$f.err") || true
                mv "$f.tmp" "$f"
                echo "AB $arm $short q$q r$r done"
            done
            r=$((r + 1))
        done
    done
done
"$py" "$here/tools/ab_score.py" "$out"
