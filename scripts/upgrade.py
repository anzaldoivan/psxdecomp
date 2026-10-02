#!/usr/bin/env python3
"""upgrade.py — bring an existing game repository to the current psxdecomp pins: audit -> plan -> apply --dry-run ->
apply. psxrecomp's migrate shape, our own code.

    upgrade.py audit [--repo DIR]                 doctor's rows plus what differs from the current kit
    upgrade.py plan  [--repo DIR]                 numbered actions; each is `psxdecomp` (apply does it) or `manual`
    upgrade.py apply --dry-run [--repo DIR]       the exact writes, nothing written
    upgrade.py apply [--repo DIR] [--fetch]       the psxdecomp-owned writes only; never commits, never touches PA3's
                                                  or the kit's files; prints the paths to commit
    upgrade.py --self-test

psxdecomp owns: config/psxdecomp.toml, config/refs.toml, docs/ops/refs.md, its .gitignore block, its firewall purge
line, the one HOW_WE_WORK references line, the docs/ops/INDEX.md row. PA3 and kit upgrades are printed as commands for
the developer (their own installers, their own gates).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import doctor  # noqa: E402
import fetch_refs  # noqa: E402
import install  # noqa: E402

PROFILE_REFS = common.PLUGIN_ROOT / "profiles" / "psx" / "refs.toml"


def plan(repo: pathlib.Path) -> list[dict]:
    acts = []
    add = lambda owner, what, why, key: acts.append(dict(owner=owner, what=what, why=why, key=key))  # noqa: E731
    comp = common.compat()
    if not (repo / ".claude" / "pa.json").is_file():
        add("manual", "PA3: not a PA3 project; install PA3 first (psxdecomp adopts PA3 repositories only)", "no PA3",
            "pa3")
        if not (repo / "docs" / "decomp-architect-install.md").is_file():
            add("manual", "kit: then the decomp-architect kit, with its own installer", "no kit", "kit")
        return acts
    if not (repo / install.RECORD).is_file():
        add("psxdecomp", "adopt: write %s (pins as found, profile psx, `adopted`)" % install.RECORD,
            "the repository was not bootstrapped by psxdecomp", "adopt")
    refs = repo / "config" / "refs.toml"
    default = {r["name"]: r for r in fetch_refs.load_rows(PROFILE_REFS)}
    if not refs.is_file():
        add("psxdecomp", "refs: add config/refs.toml (the profile's %d rows), docs/ops/refs.md, the refs/ ignore and "
            "purge lines, the HOW_WE_WORK references line" % len(default), "no reference library", "refs-add")
    else:
        mine = {r["name"]: r for r in fetch_refs.load_rows(refs)}
        new = sorted(set(default) - set(mine))
        if new:
            add("psxdecomp", "refs: add rows %s" % ", ".join(new), "the profile gained rows", "refs-rows")
        doc = fetch_refs.load_doc(refs)
        if not doc["authority"] or not doc["traps"]:
            add("psxdecomp", "refs: add the profile's [[authority]] and [[trap]] tables", "which source wins per topic, "
                "and the contradictions already paid for", "refs-meta")
        gone = sorted(set(mine) - set(default))
        if gone:
            add("manual", "refs: rows not in the profile any more: %s (dropped by the curation audit, or your own "
                "additions); keep or remove each" % ", ".join(gone), "curation", "refs-gone")
        for n in sorted(set(default) & set(mine)):
            if default[n].get("ref") != mine[n].get("ref") or default[n]["class"] != mine[n]["class"]:
                add("manual", "refs: %s is %s/%s here, %s/%s in the profile" % (
                    n, mine[n]["class"], str(mine[n].get("ref", ""))[:12], default[n]["class"],
                    str(default[n].get("ref", ""))[:12]), "a pin or a class differs; decide per source", "refs-diff")
    gi = repo / ".gitignore"
    if gi.is_file() and "/refs/" not in common.read(gi).splitlines():
        add("psxdecomp", "ignore: add the /refs/ line in a psxdecomp block", "refs/ must never be tracked", "ignore")
    pa = repo / ".claude" / "pa.json"
    if pa.is_file():
        conf = json.loads(common.read(pa))
        if conf.get("pa_version") != comp["pa3"]["version"]:
            add("manual", "PA3: the repository is at %s, psxdecomp is tested on %s; update with PA3's own installer "
                "(`<python> <pa3>/pa_install.py --project %s`), then /psxdecomp:doctor"
                % (conf.get("pa_version"), comp["pa3"]["version"], repo), "PA3 version", "pa3")
        if conf.get("python") and not os.path.exists(conf["python"]):
            add("manual", "python: pa.json names %s, missing on this machine; re-run PA3's --project install here"
                % conf["python"], "portability", "python")
    else:
        add("manual", "PA3: not a PA3 project; install PA3 first (psxdecomp adopts PA3 repositories only)", "no PA3",
            "pa3")
    if not (repo / "docs" / "decomp-architect-install.md").is_file():
        add("manual", "kit: no decomp-architect install record; the kit installs on PA3 repositories with its own "
            "installer", "no kit", "kit")
    return acts


def toml_table(kind: str, d: dict) -> str:
    """One [[kind]] table; strings and string lists as JSON literals (valid TOML basic strings)."""
    lines = ["[[%s]]" % kind]
    for k, v in d.items():
        lines.append("%s = %s" % (k, json.dumps(v, ensure_ascii=False)))
    return "\n".join(lines) + "\n"


def apply(repo: pathlib.Path, dry: bool, fetch: bool) -> list[str]:
    acts = {a["key"] for a in plan(repo) if a["owner"] == "psxdecomp"}
    written = []

    def w(rel, text):
        st = common.write(repo / rel, text, dry=dry)
        if st != "unchanged":
            written.append("%s%s %s" % ("would be " if dry else "", st, rel))

    if "adopt" in acts:
        conf = json.loads(common.read(repo / ".claude/pa.json")) if (repo / ".claude/pa.json").is_file() else {}
        w(install.RECORD, "\n".join([
            "# config/psxdecomp.toml — adopted by /psxdecomp:upgrade (the repository predates psxdecomp).", "",
            "[psxdecomp]", 'version = "%s"' % common.plugin_version(), 'profile = "psx"',
            'bootstrapped = "adopted %s"' % common.today(), "", "[pa3]", 'version = "%s"' % conf.get("pa_version", ""),
            "", "[refs]", 'file = "config/refs.toml"', 'index = "docs/ops/refs.md"', "", "[deviations]",
            'list = ["adopted: not bootstrapped by psxdecomp; pins recorded as found"]', ""]))
    if "refs-add" in acts:
        w("config/refs.toml", common.read(PROFILE_REFS))
    elif "refs-rows" in acts or "refs-meta" in acts:
        cur = common.read(repo / "config/refs.toml")
        mine = {r["name"] for r in fetch_refs.load_rows(repo / "config/refs.toml")}
        prof = fetch_refs.load_doc(PROFILE_REFS)
        extra = []
        if "refs-rows" in acts:
            extra += [toml_table("ref", r) for r in prof["rows"] if r["name"] not in mine]
        if "refs-meta" in acts:
            have = fetch_refs.load_doc(repo / "config/refs.toml")
            if not have["authority"]:
                extra += [toml_table("authority", a) for a in prof["authority"]]
            if not have["traps"]:
                extra += [toml_table("trap", t) for t in prof["traps"]]
        w("config/refs.toml", cur.rstrip("\n") + "\n\n# ---- added by /psxdecomp:upgrade %s ----\n" % common.today()
          + "\n".join(extra))
    if "refs-add" in acts or "ignore" in acts:
        gi = common.read(repo / ".gitignore") if (repo / ".gitignore").is_file() else ""
        if "/refs/" not in gi.splitlines():
            w(".gitignore", gi + ("" if not gi or gi.endswith("\n") else "\n") + "%s ----\n/refs/\n" % install.PSX_MARK)
        fw = repo / "config/firewall.txt"
        if fw.is_file() and "purge: refs/" not in common.read(fw):
            w("config/firewall.txt", common.read(fw).rstrip("\n") + "\n\n%s: the reference library ----\npurge: refs/\n"
              % install.PSX_MARK)
        how = repo / "HOW_WE_WORK.md"
        if how.is_file() and install.REFS_RULE not in common.read(how):
            w("HOW_WE_WORK.md", install.insert_in_section(common.read(how), "## Docs map", install.REFS_RULE))
    if not dry and any(x.endswith(" HOW_WE_WORK.md") for x in written) and (repo / "tools/card.py").is_file():
        py = common.find_python((3, 11)) or sys.executable
        r = common.run([py, "tools/card.py", "check"], cwd=repo, check=False)
        written.append("card check rc %d: %s" % (r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:]))
    refs_file = repo / "config/refs.toml"
    if not dry and refs_file.is_file():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch_refs.main(["--repo", str(repo)] + ([] if fetch else ["--index-only"]))
        written.append("index docs/ops/refs.md (%s)" % buf.getvalue().strip().splitlines()[-1])
    elif dry and ("refs-add" in acts or "refs-rows" in acts):
        written.append("would write docs/ops/refs.md (the index)")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["audit", "plan", "apply"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    repo = pathlib.Path(a.repo).resolve()
    if a.cmd == "audit":
        for r in doctor.check(repo):
            print("AUDIT %-12s %-4s %s" % r)
        acts = plan(repo)
        print("AUDIT %d action(s): %d psxdecomp, %d manual" % (len(acts), sum(x["owner"] == "psxdecomp" for x in acts),
                                                              sum(x["owner"] == "manual" for x in acts)))
        return 0
    if a.cmd == "plan":
        acts = plan(repo)
        for i, x in enumerate(acts, 1):
            print("PLAN %d [%s] %s — %s" % (i, x["owner"], x["what"], x["why"]))
        print("PLAN %d action(s)%s" % (len(acts), "" if acts else " — up to date"))
        return 0
    if a.cmd == "apply":
        written = apply(repo, a.dry_run, a.fetch)
        for x in written:
            print("APPLY %s" % x)
        manual = [x for x in plan(repo) if x["owner"] == "manual"] if not a.dry_run else []
        for x in manual:
            print("MANUAL %s" % x["what"])
        print("APPLY %s %d write(s); nothing committed%s" % ("DRY RUN" if a.dry_run else "OK", len(written),
                                                           "" if a.dry_run else " (review, then commit the paths above)"))
        return 0
    ap.print_help()
    return 2


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td)
        common.git(repo, "init", "--quiet")
        (repo / "HOW_WE_WORK.md").write_text("# card\n## Docs map\n- a\n\n## Next\n")
        (repo / ".gitignore").write_text("/.run/*\n")
        ok &= {x["key"] for x in plan(repo)} == {"pa3", "kit"}          # not PA3: only manual steps
        (repo / ".claude").mkdir()
        (repo / ".claude/pa.json").write_text(json.dumps({"pa_version": "3.14.1", "python": "/nonexistent/python"}))
        keys = {x["key"] for x in plan(repo)}
        ok &= {"adopt", "refs-add", "ignore", "pa3", "python", "kit"} <= keys
        before = sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts)
        dry = apply(repo, True, False)
        ok &= sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts) == before and len(dry) >= 4
        apply(repo, False, False)
        ok &= (repo / "config/refs.toml").is_file() and (repo / "docs/ops/refs.md").is_file()
        ok &= install.REFS_RULE in (repo / "HOW_WE_WORK.md").read_text()
        keys2 = {x["key"] for x in plan(repo)}
        ok &= not ({"adopt", "refs-add", "ignore"} & keys2)
        ok &= apply(repo, True, False) == []                     # a second apply has nothing to do
        # an older refs.toml (a dropped row, no authority/traps) gains the new rows and tables; the dropped row is manual
        old = fetch_refs.load_rows(PROFILE_REFS)[:2] + [dict(fetch_refs.load_rows(PROFILE_REFS)[0], name="psn00bsdk")]
        (repo / "config/refs.toml").write_text("".join(toml_table("ref", r) for r in old))
        keys3 = {x["key"] for x in plan(repo)}
        ok &= {"refs-rows", "refs-meta", "refs-gone"} <= keys3
        apply(repo, False, False)
        doc = fetch_refs.load_doc(repo / "config/refs.toml")
        ok &= fetch_refs.lint_doc(doc) == [] and bool(doc["authority"]) and bool(doc["traps"])
        ok &= {x["key"] for x in plan(repo)} == {"refs-gone", "pa3", "python", "kit"}
    return common.self_test_banner("upgrade", ok)


if __name__ == "__main__":
    sys.exit(main())
