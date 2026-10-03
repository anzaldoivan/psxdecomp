#!/bin/sh
# A bootstrap paused at the restart: S0-S6 done, PA3's pa.json present, no intake yet. The eval child is a default
# session (not `claude --agent plain`), so /psxdecomp:new --resume must give the restart line and stop before S7.
set -e
git init --quiet -b main .
mkdir -p .run/bootstrap .claude
cat > .claude/pa.json <<'JSON'
{
  "pa_version": "3.14.2",
  "upgrade": "ask",
  "project": "homebrew-decomp"
}
JSON
at=2026-10-02T00:00:00Z
python3 - "$at" <<'PY'
import json, sys
at = sys.argv[1]
stages = {s: {"status": "done", "at": at, "note": "scaffold"} for s in ("S0", "S1", "S2", "S3", "S4", "S5", "S6")}
open(".run/bootstrap/state.json", "w").write(json.dumps({"version": 1, "stages": stages}, indent=2) + "\n")
PY
