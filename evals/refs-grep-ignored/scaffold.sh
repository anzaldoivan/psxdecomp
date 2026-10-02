#!/bin/sh
# The refs-grep fixture under real conditions: a git repository whose .gitignore ignores /refs/ and whose .ignore
# re-includes it for search, as S9 writes them. Without the .ignore, Claude's content search (which honours .gitignore
# inside a git repository) skips refs/ from the root: 2026-10-02, answers still right but 7-8 turns instead of 2.
# refs-grep (no git) stays as the control.
here=$(cd "$(dirname "$0")" && pwd)
cp -R "$here/../refs-grep/workspace/." .
printf '# ---- psxdecomp ----\n/refs/\n/.run/\n' > .gitignore
printf '# ---- psxdecomp: search refs/ though git ignores it ----\n!/refs/\n' > .ignore
git init -q
git add -A
git -c user.name=fixture -c user.email=fixture@example.invalid commit -qm "fixture"
