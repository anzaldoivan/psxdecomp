#!/usr/bin/env python3
"""decompdev.py — decomp.dev's read API for research and health, and a report.json validator. Read-only.

    decompdev.py lookup --title T [--serial S] [--json]    projects matching a title (and serial) on decomp.dev
    decompdev.py status --repo OWNER/REPO [--json]         listed or not; the default version's measures
    decompdev.py validate REPORT.json [--artifact NAME [--version V]] [--exe NAME] [--categories TSV]
    decompdev.py --self-test                               canned projects and reports; no network

decomp.dev has no upload API: it reads an objdiff `report.json` from a GitHub Actions artifact named
`<version>_report` on the default branch (polled every few minutes, or at once with its GitHub App), and projects are
registered at https://decomp.dev/manage/new. `validate` is publish.py's (the standard, docs/PUBLISHING.md): objdiff's
report.proto in its proto3 JSON form (uint64 fields as strings), version 2, every measure's arithmetic including each
category's sums, the category ids, the artifact name, and the firewall: no field outside the schema and no byte-like
string (a long hex or base64 run). `--projects FILE` reads a saved /projects.json instead of the network.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import publish  # noqa: E402

BASE = "https://decomp.dev"
TIMEOUT = 20

# The report checks (schema, arithmetic, version 2, categories, the artifact name) live in publish.py, the file game
# repositories vendor as tools/psxd_publish.py; `validate` here is the same check from the plugin.
validate = publish.validate


# ---- the read API ---------------------------------------------------------------------------------------------

def fetch_json(path: str):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json",
                                                       "User-Agent": "psxdecomp-decompdev"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def projects(path: str | None = None) -> list[dict]:
    d = json.loads(common.read(path)) if path else fetch_json("/projects.json")
    return d["projects"] if isinstance(d, dict) else d


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def lookup(rows: list[dict], title: str, serial: str | None = None) -> list[dict]:
    t = _key(title)
    out = []
    for p in rows:
        names = [_key(p.get(k) or "") for k in ("name", "short_name", "repo")]
        if not any(t and t in n for n in names):
            continue
        if serial:
            versions = [_key(v) for v in [p.get("default_version")] + list(p.get("report_versions") or [])]
            if _key(serial) not in versions:
                continue
        out.append(p)
    return out


def summary(p: dict) -> str:
    m, c = p.get("measures") or {}, p.get("commit") or {}
    return "%s/%s | %s | %s | version %s | code %.2f%%, functions %.2f%% | commit %s %s | %s" % (
        p.get("owner"), p.get("repo"), p.get("name"), p.get("platform"), p.get("default_version"),
        m.get("matched_code_percent", 0), m.get("matched_functions_percent", 0), (c.get("sha") or "")[:7],
        (c.get("timestamp") or "")[:10], p.get("repo_url"))


def status(rows: list[dict], repo: str) -> tuple[bool, str]:
    owner, _, name = repo.partition("/")
    p = next((x for x in rows if (x.get("owner") or "").lower() == owner.lower()
              and (x.get("repo") or "").lower() == name.lower()), None)
    if not p:
        return False, ("not listed: once a `<version>_report` artifact (objdiff report.json) builds on the default "
                       "branch, register it at %s/manage/new" % BASE)
    return True, "listed, at commit %s: %s" % (((p.get("commit") or {}).get("sha") or "")[:7], summary(p))


# ---- self-test ------------------------------------------------------------------------------------------------

def _canned_report() -> dict:
    def meas(code, mcode, funcs, mfuncs):
        return {"fuzzy_match_percent": 100.0 * mcode / code, "total_code": str(code), "matched_code": str(mcode),
                "matched_code_percent": 100.0 * mcode / code, "total_functions": funcs, "matched_functions": mfuncs,
                "matched_functions_percent": 100.0 * mfuncs / funcs}
    report = {"version": publish.REPORT_VERSION,
              "units": [{"name": "main/a", "measures": meas(600, 500, 6, 5),
                         "functions": [{"name": "func_80010000", "size": "120", "fuzzy_match_percent": 100.0,
                                        "metadata": {"virtualAddress": "2147549184"}}],
                         "metadata": {"complete": False, "progressCategories": ["sdk"]}},
                        {"name": "main/b", "measures": meas(400, 100, 4, 2),
                         "metadata": {"complete": False, "progressCategories": ["game"]}}]}
    rows = publish.parse_categories("id\tparent\tname\tstatus\ngame\t\tGame\tactive\nsdk\t\tSDK\tactive\n")[0]
    return publish.categorize(report, rows)[0]


def self_test() -> int:
    ok = True
    canned = {"projects": [
        {"owner": "example", "repo": "game-a-decomp", "repo_url": "https://example.invalid/a", "name": "Game A",
         "short_name": None, "platform": "ps", "default_version": "SLUS_000.01", "report_versions": ["SLUS_000.01"],
         "commit": {"sha": "0123456789abcdef", "timestamp": "2026-10-02T00:00:00Z"},
         "measures": {"matched_code_percent": 100.0, "matched_functions_percent": 100.0}},
        {"owner": "example", "repo": "game-a2", "repo_url": "https://example.invalid/a2", "name": "Game A 2",
         "platform": "ps", "default_version": "us", "measures": {}, "commit": {}}]}
    with tempfile.TemporaryDirectory() as td:
        pj = os.path.join(td, "projects.json")
        with open(pj, "w") as f:
            json.dump(canned, f)
        rows = projects(pj)
    ok &= [p["repo"] for p in lookup(rows, "game a")] == ["game-a-decomp", "game-a2"]
    ok &= [p["repo"] for p in lookup(rows, "Game A", "SLUS-00001")] == ["game-a-decomp"]   # serial forms normalise
    ok &= lookup(rows, "Game B") == []
    listed, line = status(rows, "Example/Game-A-Decomp")
    ok &= listed and "commit 0123456" in line
    listed, line = status(rows, "example/nope")
    ok &= not listed and "/manage/new" in line
    good = _canned_report()
    errs = validate(good, artifact="SLUS_000.01_report", version="SLUS_000.01")
    print("  validate good: %s" % (errs or "clean"))
    ok &= errs == []
    controls = []
    bad = _canned_report()
    bad["units"][0]["measures"]["matched_code"] = "700"                 # matched > total in a unit
    controls.append(("matched > total", bad, None, "700 > total_code"))
    bad = _canned_report()
    bad["units"][1]["source"] = "x"                                     # a field outside the schema
    controls.append(("unknown field", bad, None, "unknown field"))
    bad = _canned_report()
    bad["units"][0]["functions"][0]["name"] = "data_" + "a5" * 64       # a planted 64-byte hex string
    controls.append(("64-byte hex", bad, None, "byte-like"))
    bad = _canned_report()
    bad["measures"]["total_code"] = 1000                                # uint64 as a JSON number
    controls.append(("uint64 as number", bad, None, "decimal string"))
    bad = _canned_report()
    bad["measures"]["matched_code_percent"] = 61.0                      # percent off its ratio
    controls.append(("percent off", bad, None, "is not 100*"))
    controls.append(("artifact name", _canned_report(), "report", "<version>_report"))
    controls.append(("artifact version", _canned_report(), "eu_report", "wants SLUS_000.01_report"))
    bad = _canned_report()
    bad["version"] = 1                                                  # decomp.dev reads only v2 categories as is
    controls.append(("version 1", bad, None, "emit 2"))
    bad = _canned_report()
    bad["categories"][0]["measures"]["matched_code"] = "200"            # a category off its units' sum
    controls.append(("category sum", bad, None, "the sum over its units"))
    for name, rep, art, want in controls:
        errs = validate(rep, artifact=art, version="SLUS_000.01" if art else None)
        hit = any(want in e for e in errs)
        print("  control %-17s %s" % (name, "caught" if hit else "MISSED %s" % errs))
        ok &= hit
    return common.self_test_banner("decompdev", ok)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    lk = sub.add_parser("lookup")
    lk.add_argument("--title", required=True)
    lk.add_argument("--serial")
    st = sub.add_parser("status")
    st.add_argument("--repo", required=True)
    for p in (lk, st):
        p.add_argument("--projects", help="a saved /projects.json (offline)")
        p.add_argument("--json", action="store_true")
    va = sub.add_parser("validate")
    va.add_argument("report")
    va.add_argument("--artifact")
    va.add_argument("--version")
    va.add_argument("--exe", help="the executable's file name: the artifact must be <exe>_report")
    va.add_argument("--categories", help="config/categories.tsv: the report's ids are its active ids")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd == "validate":
        cats = publish.load_categories(a.categories)[0] if a.categories else None
        errs = validate(json.loads(common.read(a.report)), a.artifact, a.version, cats, a.exe)
        for e in errs:
            print("REPORT ERROR %s" % e)
        print("REPORT %s (%d error%s)" % ("OK" if not errs else "FAIL", len(errs), "" if len(errs) == 1 else "s"))
        return 1 if errs else 0
    if a.cmd not in ("lookup", "status"):
        ap.print_help()
        return 2
    try:
        rows = projects(a.projects)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        print("DECOMPDEV UNREACHABLE %s (decomp.dev read API, %s)" % (e, common.today()))
        return 2
    if a.cmd == "lookup":
        found = lookup(rows, a.title, a.serial)
        if a.json:
            print(json.dumps(found, indent=2))
        else:
            for p in found:
                print("DECOMPDEV %s" % summary(p))
            print("DECOMPDEV %d project(s) match %r%s on decomp.dev, %s" % (
                len(found), a.title, " / %s" % a.serial if a.serial else "", common.today()))
        return 0
    listed, line = status(rows, a.repo)
    print(json.dumps({"repo": a.repo, "listed": listed, "detail": line}) if a.json else
          "DECOMPDEV %s %s" % ("LISTED" if listed else "NOT-LISTED", line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
