#!/usr/bin/env python3
"""doctor.py — is this game repository healthy against the current psxdecomp pins? Read-only.

    doctor.py [--repo DIR] [--json]        one row per check: OK / WARN / FAIL; exit 1 on any FAIL
    doctor.py --self-test

Checks: the bootstrap record (config/psxdecomp.toml); PA3's version against compat.toml; the kit's install record;
the interpreter pa.json names exists on this machine; the firewall (ignore block, audit passes on the tree, the
planted-fixture hash present); the reference library (lint, pins, index current); refs/ ignored; the SDK (the
PsyQ release the game links, from the record's [psyq], and $PSXDECOMP_BYO_PSYQ_PATH: never inside the repository);
hygiene (WARN only: unscoped version or game claims and sentences copied between the tracked docs).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import fetch_refs  # noqa: E402


def check(repo) -> list[tuple[str, str, str]]:
    repo = pathlib.Path(repo).resolve()
    rows = []
    add = lambda n, s, d: rows.append((n, s, d))  # noqa: E731
    comp = common.compat()
    rec = repo / "config" / "psxdecomp.toml"
    if rec.is_file():
        r = common.load_toml(rec)
        add("record", "OK", "psxdecomp %s, profile %s, bootstrapped %s" % (
            r["psxdecomp"]["version"], r["psxdecomp"]["profile"], r["psxdecomp"]["bootstrapped"]))
        sdk = sdk_row(r.get("psyq"), repo, os.environ.get("PSXDECOMP_BYO_PSYQ_PATH"))
        if sdk:
            add("sdk", *sdk)
    else:
        add("record", "WARN", "no config/psxdecomp.toml (not bootstrapped by psxdecomp; /psxdecomp:upgrade adopts it)")
    pa = repo / ".claude" / "pa.json"
    if pa.is_file():
        conf = json.loads(common.read(pa))
        ver = conf.get("pa_version")
        add("pa3", "OK" if ver == comp["pa3"]["version"] else "WARN",
            "PA3 %s%s" % (ver, "" if ver == comp["pa3"]["version"] else " (tested %s)" % comp["pa3"]["version"]))
        py = conf.get("python")
        add("python", "OK" if py and os.path.exists(py) else "FAIL",
            "%s %s" % (py, "exists" if py and os.path.exists(py) else "is missing on this machine (re-run PA3's "
                       "--project install here to re-resolve it)"))
    else:
        add("pa3", "FAIL", "no .claude/pa.json (not a PA3 project)")
    kit_rec = repo / "docs" / "decomp-architect-install.md"
    if kit_rec.is_file():
        head = common.read(kit_rec)[:400]
        add("kit", "OK", "install record present%s" % (
            "" if "ProjectArchitect %s" % comp["pa3"]["version"] in head else " (written against another PA3)"))
    else:
        add("kit", "FAIL", "no docs/decomp-architect-install.md (the kit is not installed)")
    gi = repo / ".gitignore"
    gtext = common.read(gi) if gi.is_file() else ""
    add("ignore", "OK" if "# ROM firewall — in force from the FIRST commit" in gtext else "FAIL",
        "the kit's firewall block %s" % ("present" if "ROM firewall" in gtext else "missing from .gitignore"))
    audit = repo / "tools" / "audit_public.py"
    if audit.is_file():
        py = common.find_python((3, 11)) or sys.executable
        r = common.run([py, audit], cwd=repo, check=False, timeout=600)
        add("audit", "OK" if r.returncode == 0 else "FAIL",
            "tools/audit_public.py rc %d%s" % (r.returncode, "" if r.returncode == 0 else ": " + r.stdout.strip()[-200:]))
        add("fixture", "OK" if (repo / "config" / "firewall-fixture.sha1").is_file() else "FAIL",
            "planted-fixture hash %s" % ("present" if (repo / "config/firewall-fixture.sha1").is_file() else "missing"))
    else:
        add("audit", "FAIL", "no tools/audit_public.py")
    refs = repo / "config" / "refs.toml"
    if refs.is_file():
        errs = fetch_refs.lint_doc(fetch_refs.load_doc(refs))
        if errs:
            add("refs", "FAIL", "; ".join(errs[:3]))
        else:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fetch_refs.main(["--repo", str(repo), "--check"])
            drift = [l for l in buf.getvalue().splitlines() if l.startswith(("DRIFT", "MISSING"))]
            add("refs", "OK" if rc == 0 else "WARN", buf.getvalue().strip().splitlines()[-1] +
                ("" if rc == 0 else " — %s (fetch_refs.py --repo . fixes it)" % "; ".join(drift[:3])))
        ignored = common.git(repo, "check-ignore", "-q", "refs/x", check=False).returncode == 0
        add("refs-ignored", "OK" if ignored else "FAIL", "refs/ %s" % ("ignored" if ignored else "is NOT ignored"))
    else:
        add("refs", "WARN", "no config/refs.toml (no reference library)")
    add("hygiene", *hygiene_row(repo))
    return rows


# Not the repo's own current text: fetched sources, research, phase records (scoped by their phase), and the harness
# PA3 installs (.claude/, templates/: copies by design, refreshed by PA3, whose duplicates are PA3's to fix).
HYGIENE_SKIP = re.compile(r"^(?:refs/|research/|phase-ends/|\.claude/|templates/)|(?:^|/)\.run/")


def hygiene_row(repo: pathlib.Path) -> tuple[str, str]:
    """Unscoped claims (fetch_refs.lint_scope) and copied sentences (lint_dupes) over the tracked docs. Never FAIL."""
    r = common.git(repo, "ls-files", "-z", "--", "*.md", "*.toml", check=False)
    rels = [p for p in r.stdout.split("\0") if p and not HYGIENE_SKIP.search(p)] if r.returncode == 0 else []
    paths = [repo / p for p in rels if (repo / p).is_file()]
    per: dict[str, int] = {}
    scope = 0
    for p in paths:
        try:
            n = len(fetch_refs.lint_file(p))
        except (OSError, UnicodeDecodeError):
            continue
        scope += n
        if n:
            per[p.relative_to(repo).as_posix()] = per.get(p.relative_to(repo).as_posix(), 0) + n
    dupes = fetch_refs.lint_dupes(paths, repo)
    for _, where in dupes:
        for w in where:
            f = w.rsplit(":", 1)[0]
            per[f] = per.get(f, 0) + 1
    if not scope and not dupes:
        return "OK", "%d tracked docs: no unscoped claim, no copied sentence" % len(paths)
    top = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return "WARN", "%d unscoped claim(s), %d copied sentence(s) over %d tracked docs; top: %s" % (
        scope, len(dupes), len(paths), ", ".join("%s (%d)" % kv for kv in top))


def sdk_row(psyq: dict | None, repo: pathlib.Path, byo: str | None) -> tuple[str, str] | None:
    """The PsyQ release the game links and what a byo SDK must be; a byo path inside the repo is a firewall FAIL."""
    if not psyq and not byo:
        return None
    v = (psyq or {}).get("version", "unknown")
    if not psyq:
        what = "no [psyq] in the record"
    elif psyq.get("ships_compiler") == "no":
        what = "game links PsyQ %s; it ships no compiler" % v
    else:
        what = "game links PsyQ %s; shipped cc1 %s" % (v, psyq.get("cc1_banner") or "unknown")
    what += "; byo must be %s (docs/ops/refs.md, psyq-sdk row)" % v
    if not byo:
        return "OK", what
    path = pathlib.Path(byo).expanduser().resolve()
    if path == repo or repo in path.parents:
        return "FAIL", what + "; $PSXDECOMP_BYO_PSYQ_PATH is inside the repository (firewall): move it outside"
    if not path.is_dir():
        return "WARN", what + "; $PSXDECOMP_BYO_PSYQ_PATH %s does not exist" % path
    return "OK", what + "; byo path given"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    rows = check(a.repo)
    if a.json:
        print(json.dumps([dict(zip(("check", "status", "detail"), r)) for r in rows], indent=2))
    else:
        for r in rows:
            print("DOCTOR %-12s %-4s %s" % r)
    fails = sum(r[1] == "FAIL" for r in rows)
    print("DOCTOR %s (%d warn)" % ("OK" if not fails else "FAIL %d" % fails, sum(r[1] == "WARN" for r in rows)))
    return 1 if fails else 0


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        common.git(td, "init", "--quiet")
        rows = dict((r[0], r[1]) for r in check(td))
    ok = rows.get("pa3") == "FAIL" and rows.get("record") == "WARN" and rows.get("audit") == "FAIL"
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td).resolve()
        q = {"version": "4.7", "ships_compiler": "no"}
        (repo / "tools" / "psyq").mkdir(parents=True)
        cases = [(sdk_row(q, repo, str(repo / "tools" / "psyq")), "FAIL"), (sdk_row(q, repo, td + "/../nope"), "WARN"),
                 (sdk_row(q, repo, None), "OK"), (sdk_row(None, repo, None), None)]
        for got, want in cases:
            ok &= (got[0] if got else None) == want
        print("  sdk row: %s" % cases[0][0][1])
    with tempfile.TemporaryDirectory() as td:                           # hygiene: clean tree OK, one planted line WARN
        repo = pathlib.Path(td).resolve()
        common.git(repo, "init", "--quiet")
        (repo / "docs").mkdir()
        (repo / "docs" / "a.md").write_text("# Toolchain (scope: 2026-10-01)\n\nThe pin is gcc 2.95.2.\n")
        (repo / "refs").mkdir()
        (repo / "refs" / "x.md").write_text("BFM used gcc 2.7.2.\n")      # refs/ is not the repo's own text
        common.git(repo, "add", "-A", "-f")
        clean = hygiene_row(repo)
        (repo / "PROJECT_CONTEXT.md").write_text("Try gcc 2.6.3 + aspsx 2.63 first.\n")
        common.git(repo, "add", "-A")
        planted = hygiene_row(repo)
        print("  hygiene: clean %s; planted %s" % (clean[0], planted[1]))
        ok &= clean[0] == "OK" and planted[0] == "WARN" and "PROJECT_CONTEXT.md (1)" in planted[1]
    return common.self_test_banner("doctor", ok)


if __name__ == "__main__":
    sys.exit(main())
