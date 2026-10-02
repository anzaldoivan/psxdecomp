#!/usr/bin/env python3
"""preflight.py — S0: can this machine bootstrap a PS1 decomp here?

    preflight.py [--target DIR] [--resume] [--python EXE] [--min-disk-gb N] [--deep] [--dry-run]
    preflight.py --self-test

Checks git, gh, a Python >= 3.12 for the PA3 hooks (resolved per machine, never a hard-coded path), Docker and its
amd64 support, free disk, PA3's per-machine install, and that the target folder is empty (or holds only an earlier
bootstrap's .run/bootstrap with --resume). Writes .run/bootstrap/preflight.json (unless --dry-run). Exit 1 on a FAIL.
The plan tier is not asked: PA3 reads it from the credentials at S6 and picks its model ladder from it.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

ALLOWED_RESUME = {".run", ".git", ".gitignore", ".DS_Store"}


def folder_state(target: pathlib.Path, resume: bool) -> tuple[str, str]:
    if not target.exists():
        return "OK", "will be created"
    # Claude Code itself may create .claude/ (local settings) in the folder it was opened in: allowed, unless it
    # already holds a PA3 install (then this is not a new project)
    if (target / ".claude" / "pa.json").is_file():
        return "FAIL", "PA3 is already installed here (.claude/pa.json); use /psxdecomp:upgrade for an existing repo"
    entries = [p.name for p in target.iterdir() if p.name not in (".DS_Store", ".claude")]
    if not entries:
        return "OK", "empty"
    if resume:
        st = common.State(target)
        if st.path.is_file():
            return "OK", "resuming (first open stage: %s)" % (st.first_open() or "none")
        return "FAIL", "--resume given but there is no %s" % common.STATE_REL
    if entries == [".run"] and (target / common.STATE_REL).is_file():
        return "FAIL", "an earlier bootstrap is here; re-run with --resume"
    return "FAIL", "not empty (%s); run /psxdecomp:new in an empty folder" % ", ".join(sorted(entries)[:5])


def check_all(target: pathlib.Path, resume=False, python=None, min_disk_gb=30, deep=False) -> list[dict]:
    rows = []

    def add(name, status, detail, **kw):
        rows.append(dict(name=name, status=status, detail=detail, **kw))

    st, d = folder_state(target, resume)
    add("folder", st, d)
    g = shutil.which("git")
    add("git", "OK" if g else "FAIL", common.run(["git", "--version"]).stdout.strip() if g else "git not on PATH")
    gh = shutil.which("gh")
    if gh:
        auth = common.run(["gh", "auth", "status"], check=False)
        add("gh", "OK" if auth.returncode == 0 else "WARN",
            "authenticated" if auth.returncode == 0 else "installed, not logged in (research uses it for repo facts)")
    else:
        add("gh", "WARN", "gh not on PATH (optional: repo facts and licences come from the GitHub API)")
    py = common.find_python((3, 12), python or os.environ.get("CLAUDE_PLUGIN_OPTION_PYTHON_PATH"))
    add("python", "OK" if py else "FAIL", py or "no Python >= 3.12 found (PA3 needs it for its hooks)", path=py)
    dk = shutil.which("docker")
    if dk:
        info = common.run(["docker", "info", "--format", "{{.Architecture}} {{.OSType}}"], check=False)
        if info.returncode != 0:
            add("docker", "WARN", "installed but the daemon is not reachable (needed from phase 1.0, not now)")
        else:
            arch = info.stdout.strip()
            detail = "daemon %s" % arch
            status = "OK"
            if deep and "x86_64" not in arch:
                r = common.run(["docker", "run", "--rm", "--platform", "linux/amd64", "busybox", "uname", "-m"],
                               check=False, timeout=240)
                status = "OK" if r.stdout.strip() == "x86_64" else "WARN"
                detail += "; amd64 emulation %s" % ("works" if status == "OK" else "FAILED")
            elif "x86_64" not in arch:
                detail += "; amd64 via emulation (check with --deep)"
            add("docker", status, detail)
    else:
        add("docker", "WARN", "not installed (the build container is phase 1.0's; install Docker before then)")
    probe = target if target.exists() else target.parent
    free = shutil.disk_usage(probe).free / 1e9
    add("disk", "OK" if free >= min_disk_gb else "WARN", "%.0f GB free (want >= %d for builds and scratch)"
        % (free, min_disk_gb))
    c = common.compat()["pa3"]
    pa3_dir = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))) / "pa3"
    ver_file = pa3_dir / "VERSION"
    if ver_file.is_file():
        ver = common.read(ver_file).splitlines()[0].split(":", 1)[-1].strip()
        add("pa3-root", "OK" if ver == c["version"] else "WARN",
            "PA3 %s installed per machine%s" % (ver, "" if ver == c["version"] else
                                                 " (tested %s; S6 refuses a mismatch without --force-untested)"
                                                 % c["version"]), version=ver)
    else:
        add("pa3-root", "WARN", "PA3 is not installed on this machine; S6 shows the one command (it edits "
            "~/.claude/settings.json, so you run it yourself)")
    add("host", "OK", "%s %s" % (platform.system(), platform.machine()),
        recipe="macos-arm64" if platform.system() == "Darwin" else "linux-amd64")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=".")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--python")
    ap.add_argument("--min-disk-gb", type=int, default=30)
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    target = pathlib.Path(a.target).resolve()
    rows = check_all(target, a.resume, a.python, a.min_disk_gb, a.deep)
    for r in rows:
        print("CHECK %-9s %-4s %s" % (r["name"], r["status"], r["detail"]))
    fails = [r for r in rows if r["status"] == "FAIL"]
    if not a.dry_run and not fails:
        out = target / ".run" / "bootstrap" / "preflight.json"
        common.write(out, json.dumps({"at": common.now_iso(), "checks": rows,
                                      "psxdecomp": common.plugin_version()}, indent=2) + "\n")
        common.State(target).mark("S0", "done", "preflight OK (%d warn)" % sum(r["status"] == "WARN" for r in rows))
    print("PREFLIGHT %s (%d warn)" % ("FAIL" if fails else "OK", sum(r["status"] == "WARN" for r in rows)))
    return 1 if fails else 0


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        ok &= folder_state(t / "new", False)[0] == "OK"
        ok &= folder_state(t, False)[0] == "OK"
        (t / ".claude").mkdir()
        (t / ".claude" / "settings.local.json").write_text("{}")
        ok &= folder_state(t, False)[0] == "OK"             # Claude Code's own local settings are allowed
        (t / ".claude" / "pa.json").write_text("{}")
        ok &= folder_state(t, False)[0] == "FAIL"           # an existing PA3 repo is not a new project
        (t / ".claude" / "pa.json").unlink()
        (t / "stray.txt").write_text("x")
        ok &= folder_state(t, False)[0] == "FAIL"
        ok &= folder_state(t, True)[0] == "FAIL"            # --resume without a state file
        (t / "stray.txt").unlink()
        common.State(t).mark("S0", "done")
        ok &= folder_state(t, False)[0] == "FAIL"           # an earlier bootstrap: needs --resume
        ok &= folder_state(t, True)[0] == "OK"
    ok &= common.find_python((3, 12)) is not None
    return common.self_test_banner("preflight", ok)


if __name__ == "__main__":
    sys.exit(main())
