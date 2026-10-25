#!/usr/bin/env python3
"""resume_hint.py — the plugin's SessionStart hook: when a bootstrap in this folder is paused at the restart (its next
stage is S7, the intake), say how to resume. The restart line then no longer depends on the model remembering it.

    resume_hint.py              reads the hook payload on stdin (cwd); prints the hook JSON or nothing
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
RESTART = "Exit, then run `claude` here and type `/psxdecomp:new --resume`"
MOD_ON = ('PA3\'s mod is on here (.claude/pa.json "mod": "on"; S6 sets "off" for the intake): set it to "off", then '
          + RESTART[0].lower() + RESTART[1:])


def mod_on(cwd) -> bool:
    """PA3 3.2's mod runs this session: pa.json `"mod": "on"` and no PA_MOD_OFF (PA3's activation rule)."""
    off = os.environ.get("PA_MOD_OFF", "")
    if off not in ("", "0"):
        return False
    try:
        return json.loads(common.read(pathlib.Path(cwd) / ".claude" / "pa.json")).get("mod") == "on"
    except (OSError, ValueError, AttributeError):
        return False


def hint(cwd) -> dict | None:
    """The hook output for a bootstrap paused before S7, else None. The intake runs in a session the mod does not
    drive; the mod arms at a session start, so the check is pa.json's `mod` as this session found it."""
    st = pathlib.Path(cwd) / common.STATE_REL
    if not st.is_file() or common.State(cwd).first_open() != "S7":
        return None
    ready = not mod_on(cwd)
    say = "psxdecomp: the bootstrap is paused before S7. " + (RESUME[0].upper() + RESUME[1:] if ready else MOD_ON) + "."
    ctx = ("psxdecomp bootstrap in this folder: S0-S6 are done, the next stage is S7 (the intake). "
           + ("PA3's mod is off in this session: when the developer asks, run /psxdecomp:new --resume."
              if ready else "PA3's mod is on: do not run the intake here; tell the developer: " + MOD_ON + "."))
    return {"systemMessage": say,
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        inp = json.loads(raw) if raw.strip() else {}
        out = hint(inp.get("cwd") or os.getcwd())
    except Exception:                                                   # noqa: BLE001 — a hint, never a failure
        return 0
    if out:
        print(json.dumps(out))
    return 0


def self_test() -> int:
    ok = True
    saved = os.environ.pop("PA_MOD_OFF", None)
    with tempfile.TemporaryDirectory() as td:
        ok &= hint(td) is None                                          # no bootstrap here: silent
        st = common.State(td)
        for sid in ("S0", "S1", "S2", "S3", "S4", "S5"):
            st.mark(sid, "done")
        ok &= hint(td) is None                                          # paused at S6: not the restart
        st.mark("S6", "done")
        pa = pathlib.Path(td) / ".claude" / "pa.json"
        pa.parent.mkdir()
        pa.write_text('{"pa_version": "3.28.8", "mod": "on"}')
        on = hint(td)
        pa.write_text('{"pa_version": "3.28.8", "mod": "off"}')
        off = hint(td)
        print("  mod on:  %s\n  mod off: %s" % (on["systemMessage"], off["systemMessage"]))
        ok &= '"off"' in on["systemMessage"] and "`claude`" in on["systemMessage"] and "--resume" in on["systemMessage"]
        ok &= "--resume" in off["systemMessage"] and "Exit" not in off["systemMessage"]
        ok &= "--agent" not in on["systemMessage"] + off["systemMessage"]
        ok &= off["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        pa.write_text('{"pa_version": "3.28.8", "mod": "on"}')
        os.environ["PA_MOD_OFF"] = "1"
        ok &= "Exit" not in hint(td)["systemMessage"]                   # PA3's own switch counts as off
        os.environ.pop("PA_MOD_OFF")
        pa.write_text('{"pa_version": "3.28.8", "mod": "off"}')
        st.mark("S7", "failed", "x")
        ok &= hint(td) is not None                                      # a failed intake is still the next stage
        st.mark("S7", "done")
        ok &= hint(td) is None                                          # past the restart: silent
    if saved is not None:
        os.environ["PA_MOD_OFF"] = saved
    return common.self_test_banner("resume_hint", ok)


if __name__ == "__main__":
    sys.exit(main())
