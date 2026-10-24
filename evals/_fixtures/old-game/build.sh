#!/bin/sh
# Writes the smallest older game into the current folder for the upgrade and doctor evals:
#   build.sh pa3-old|task-running|no-firewall|retired
# A git repository that psxdecomp 0.6.0 bootstrapped on PA3 3.14.2 with the kit: the record, pa.json, the kit's
# install record and the firewall block of .gitignore. No game byte, no tool of the game: the project is demo6.
#   pa3-old       as above: PA3 is older than the pin, so the upgrade plan names PA3's own update ([manual])
#   task-running  PA3 3.28.8 (3.2) with its loop running task T7.3 (.run/mod/loop.json): apply refuses
#   no-firewall   pa3-old without the kit's firewall block in .gitignore: doctor's `ignore` row FAILs
#   retired       PA3 3.28.8 and a card line that still names /discuss, which 3.24 removed: doctor's `pa3-retired` WARNs
# Refuses a folder that is a git repository's root or holds a file it writes: it never writes into an existing game.
set -eu
v=${1:?usage: build.sh pa3-old|task-running|no-firewall|retired}
case $v in pa3-old|task-running|no-firewall|retired) ;; *) echo "unknown variant $v" >&2; exit 2;; esac
for f in .git .gitignore .claude HOW_WE_WORK.md config docs; do
  if [ -e "$f" ]; then echo "build.sh: $(pwd) already holds $f; run it in an empty folder" >&2; exit 2; fi
done
pa=3.14.2
case $v in task-running|retired) pa=3.28.8;; esac
py=$(command -v python3)
git init --quiet -b main .
git config user.name fixture
git config user.email fixture@example.invalid
git remote add origin https://github.com/example/demo6.git    # never fetched: doctor's github row SKIPs offline
mkdir -p .claude config docs

printf '{\n  "pa_version": "%s",\n  "upgrade": "ask",\n  "mod": "on",\n  "project": "demo6",\n  "python": "%s"\n}\n' \
  "$pa" "$py" > .claude/pa.json

printf '%s\n' \
  '# config/psxdecomp.toml — written by psxdecomp at bootstrap.' '' \
  '[psxdecomp]' 'version = "0.6.0"' 'profile = "psx"' 'bootstrapped = "2026-09-01"' '' \
  '[pa3]' 'version = "3.14.2"' '' \
  '[refs]' 'file = "config/refs.toml"' 'index = "docs/ops/refs.md"' > config/psxdecomp.toml

printf '# decomp-architect install record\n\nInstalled on ProjectArchitect %s, 2026-09-01. Project demo6 (SLUS-99999).\n' \
  "$pa" > docs/decomp-architect-install.md

printf '%s\n' '# How we work — demo6' '' '## Docs map' \
  '- Plan: phase-ends/current/PHASE_PLAN.md. Constitution: PROJECT_CONTEXT.md (never edited).' '' \
  '## Conventions' '- Commit through tools/commit_task.sh; never push.' > HOW_WE_WORK.md
if [ "$v" = retired ]; then
  printf '%s\n' '- A design question first goes to /discuss; its record lands in phase-ends/.' >> HOW_WE_WORK.md
fi

printf '%s\n' '# psxdecomp ---- (the bootstrap scratch and the reference library; never tracked) ----' \
  '/.run/*' '!/.run/README.md' '/refs/' > .gitignore
if [ "$v" != no-firewall ]; then
  printf '%s\n' '' '# ---- decomp-architect, installed 2026-09-01 ----' \
    '# ROM firewall — in force from the FIRST commit' '*.bin' '*.cue' '*.iso' '/extracted/' >> .gitignore
fi

git add -A
git -c core.hooksPath=/dev/null commit --quiet -m "demo6: bootstrap (psxdecomp 0.6.0, PA3 $pa)"

if [ "$v" = task-running ]; then
  mkdir -p .run/mod
  printf '%s\n' '{"state": "running", "task": {"id": "T7.3"}, "ownerSid": "", "heartbeatAt": 0}' > .run/mod/loop.json
fi
