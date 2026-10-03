#!/usr/bin/env python3
"""resume_hint.py — the plugin's SessionStart hook: when a bootstrap in this folder is paused at the restart (its next
stage is S7, the intake), say how to resume. The restart line then no longer depends on the model remembering it.

    resume_hint.py              reads the hook payload on stdin (cwd, agent_type); prints the hook JSON or nothing
    resume_hint.py --self-test

Read-only, never fails the session: any error prints nothing and exits 0.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

RESUME = "type `/psxdecomp:new --resume` to run the intake (S7) and finish the bootstrap"
RESTART = "Exit, then run `claude --agent plain` here and type `/psxdecomp:new --resume`"


def hint(cwd, agent_type: str | None) -> dict | None:
    """The hook output for a bootstrap paused before S7, else None."""
    st = pathlib.Path(cwd) / common.STATE_REL
    if not st.is_file() or common.State(cwd).first_open() != "S7":
        return None
    plain = agent_type == "plain"
    say = ("psxdecomp: the bootstrap is paused before S7. " + (RESUME[0].upper() + RESUME[1:] if plain else RESTART)
           + ".")
    ctx = ("psxdecomp bootstrap in this folder: S0-S6 are done, the next stage is S7 (the intake). "
           + ("This is a plain session: when the developer asks, run /psxdecomp:new --resume."
              if plain else "This is not a plain session: do not run the intake here; tell the developer: "
              + RESTART + "."))
    return {"systemMessage": say,
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        inp = json.loads(raw) if raw.strip() else {}
        out = hint(inp.get("cwd") or os.getcwd(), inp.get("agent_type"))
    except Exception:                                                   # noqa: BLE001 — a hint, never a failure
        return 0
    if out:
        print(json.dumps(out))
    return 0


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        ok &= hint(td, None) is None                                    # no bootstrap here: silent
        st = common.State(td)
        for sid in ("S0", "S1", "S2", "S3", "S4", "S5"):
            st.mark(sid, "done")
        ok &= hint(td, None) is None                                    # paused at S6: not the restart
        st.mark("S6", "done")
        bare, plain = hint(td, None), hint(td, "plain")
        print("  bare:  %s\n  plain: %s" % (bare["systemMessage"], plain["systemMessage"]))
        ok &= "--agent plain" in bare["systemMessage"] and "--resume" in bare["systemMessage"]
        ok &= "--agent plain" not in plain["systemMessage"] and "--resume" in plain["systemMessage"]
        ok &= bare["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        st.mark("S7", "failed", "x")
        ok &= hint(td, "plain") is not None                             # a failed intake is still the next stage
        st.mark("S7", "done")
        ok &= hint(td, "plain") is None                                 # past the restart: silent
    return common.self_test_banner("resume_hint", ok)


if __name__ == "__main__":
    sys.exit(main())
