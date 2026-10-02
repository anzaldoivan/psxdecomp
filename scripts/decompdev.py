#!/usr/bin/env python3
"""decompdev.py — decomp.dev's read API for research and health, and a report.json validator. Read-only.

    decompdev.py lookup --title T [--serial S] [--json]    projects matching a title (and serial) on decomp.dev
    decompdev.py status --repo OWNER/REPO [--json]         listed or not; the default version's measures
    decompdev.py validate REPORT.json [--artifact NAME [--version V]]
    decompdev.py --self-test                               canned projects and reports; no network

decomp.dev has no upload API: it reads an objdiff `report.json` from a GitHub Actions artifact named
`<version>_report` on the default branch (polled every few minutes, or at once with its GitHub App), and projects are
registered at https://decomp.dev/manage/new. `validate` checks a report against objdiff's report.proto in its proto3
JSON form (uint64 fields as strings), its arithmetic, and the firewall: no field outside the schema and no byte-like
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

BASE = "https://decomp.dev"
TIMEOUT = 20

# objdiff report.proto (encounter/objdiff objdiff-core/protos/report.proto, read 2026-10-02 at eed74b9).
F, U64, U32, STR, BOOL = "float", "uint64", "uint32", "string", "bool"
MEASURES = {"fuzzy_match_percent": F, "total_code": U64, "matched_code": U64, "matched_code_percent": F,
            "total_data": U64, "matched_data": U64, "matched_data_percent": F, "total_functions": U32,
            "matched_functions": U32, "matched_functions_percent": F, "complete_code": U64,
            "complete_code_percent": F, "complete_data": U64, "complete_data_percent": F, "total_units": U32,
            "complete_units": U32}
SCHEMA = {
    "Report": {"measures": "Measures", "units": ["ReportUnit"], "version": U32, "categories": ["ReportCategory"]},
    "Measures": MEASURES,
    "ReportCategory": {"id": STR, "name": STR, "measures": "Measures"},
    "ReportUnit": {"name": STR, "measures": "Measures", "sections": ["ReportItem"], "functions": ["ReportItem"],
                   "metadata": "ReportUnitMetadata"},
    "ReportUnitMetadata": {"complete": BOOL, "module_name": STR, "module_id": U32, "source_path": STR,
                           "progress_categories": [STR], "auto_generated": BOOL},
    "ReportItem": {"name": STR, "size": U64, "fuzzy_match_percent": F, "metadata": "ReportItemMetadata",
                   "address": U64},
    "ReportItemMetadata": {"demangled_name": STR, "virtual_address": U64},
}
# (matched, total, percent): the percent is 100 * matched / total within PCT_TOL (0 or 100 when the total is 0).
RATIOS = [("matched_code", "total_code", "matched_code_percent"),
          ("matched_data", "total_data", "matched_data_percent"),
          ("matched_functions", "total_functions", "matched_functions_percent"),
          ("complete_code", "total_code", "complete_code_percent"),
          ("complete_data", "total_data", "complete_data_percent")]
SUMMED = ["total_code", "matched_code", "total_data", "matched_data", "total_functions", "matched_functions"]
PCT_TOL = 0.01
HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")                  # 32+ bytes as hex
B64_RUN = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")           # 60+ bytes as base64
ARTIFACT = re.compile(r"^[A-Za-z0-9._-]+_report$")


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w[:1].upper() + w[1:] for w in rest)


def _byte_like(s: str) -> bool:
    if HEX_RUN.search(s):
        return True
    return any(re.search(r"\d", m) and re.search(r"[a-z]", m) and re.search(r"[A-Z]", m)
               for m in (x.group(0) for x in B64_RUN.finditer(s)))


def _num(v, kind: str, where: str, errs: list[str]):
    """A field's value as a number; proto3 JSON writes uint64 as a string (decimal), the rest as JSON numbers."""
    if kind == U64:
        if not isinstance(v, str) or not v.isdigit():
            errs.append("%s: uint64 must be a decimal string (proto3 JSON), got %r" % (where, v))
            return int(v) if isinstance(v, int) and not isinstance(v, bool) else 0
        return int(v)
    if kind == U32:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            errs.append("%s: uint32 must be a non-negative integer, got %r" % (where, v))
            return 0
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        errs.append("%s: float must be a number, got %r" % (where, v))
        return 0.0
    return float(v)


def _walk(obj, msg: str, where: str, errs: list[str]) -> dict:
    """Schema check of one message; returns its scalar fields as numbers (missing = proto3 default 0)."""
    out = {}
    if not isinstance(obj, dict):
        errs.append("%s: %s must be an object" % (where, msg))
        return out
    fields = SCHEMA[msg]
    names = {k: k for k in fields} | {_camel(k): k for k in fields}
    for key, v in obj.items():
        name = names.get(key)
        here = "%s.%s" % (where, key)
        if name is None:
            errs.append("%s: unknown field (not in report.proto %s; the firewall allows nothing outside it)"
                        % (here, msg))
            continue
        kind = fields[name]
        if isinstance(kind, list):
            if not isinstance(v, list):
                errs.append("%s: repeated field must be a list" % here)
                continue
            for i, x in enumerate(v):
                if kind[0] == STR:
                    if not isinstance(x, str):
                        errs.append("%s[%d]: string expected" % (here, i))
                    elif _byte_like(x):
                        errs.append("%s[%d]: byte-like string (long hex/base64 run): firewall" % (here, i))
                else:
                    _walk(x, kind[0], "%s[%d]" % (here, i), errs)
        elif kind in SCHEMA:
            out[name] = _walk(v, kind, here, errs)
        elif kind == STR:
            if not isinstance(v, str):
                errs.append("%s: string expected" % here)
            elif _byte_like(v):
                errs.append("%s: byte-like string (long hex/base64 run): firewall" % here)
        elif kind == BOOL:
            if not isinstance(v, bool):
                errs.append("%s: bool expected" % here)
        else:
            out[name] = _num(v, kind, here, errs)
    return out


def _measures(m: dict, where: str, errs: list[str]):
    g = lambda k: m.get(k, 0)  # noqa: E731
    for matched, total, pct in RATIOS:
        if g(matched) > g(total):
            errs.append("%s: %s %d > %s %d" % (where, matched, g(matched), total, g(total)))
        want = 100.0 * g(matched) / g(total) if g(total) else None
        got = g(pct)
        if (want is None and got not in (0.0, 100.0)) or (want is not None and abs(got - want) > PCT_TOL):
            errs.append("%s: %s %.4f is not 100*%s/%s (%s)" % (where, pct, got, matched, total,
                                                             "0 or 100" if want is None else "%.4f" % want))
    if g("complete_units") > g("total_units"):
        errs.append("%s: complete_units > total_units" % where)
    if not 0 <= g("fuzzy_match_percent") <= 100 + PCT_TOL:
        errs.append("%s: fuzzy_match_percent out of range" % where)


def validate(report, artifact: str | None = None, version: str | None = None) -> list[str]:
    errs: list[str] = []
    if artifact is not None:
        if not ARTIFACT.match(artifact):
            errs.append("artifact %r: decomp.dev reads an artifact named <version>_report" % artifact)
        elif version is not None and artifact != "%s_report" % version:
            errs.append("artifact %r: the version %r wants %s_report" % (artifact, version, version))
    top = _walk(report, "Report", "report", errs)
    tm = top.get("measures", {})
    _measures(tm, "report.measures", errs)
    units = report.get("units", []) if isinstance(report, dict) else []
    sums = dict.fromkeys(SUMMED, 0)
    for i, u in enumerate(units if isinstance(units, list) else []):
        um = _walk(u, "ReportUnit", "units[%d]" % i, []).get("measures", {})
        _measures(um, "units[%d].measures" % i, errs)
        for k in SUMMED:
            sums[k] += um.get(k, 0)
    if units:
        for k in SUMMED:
            if sums[k] != tm.get(k, 0):
                errs.append("report.measures.%s %d != the sum over units %d" % (k, tm.get(k, 0), sums[k]))
        if tm.get("total_units", 0) != len(units):
            errs.append("report.measures.total_units %d != %d units" % (tm.get("total_units", 0), len(units)))
    return errs


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
    def meas(code, mcode, funcs, mfuncs, units=None, done=0):
        d = {"fuzzy_match_percent": 100.0 * mcode / code, "total_code": str(code), "matched_code": str(mcode),
             "matched_code_percent": 100.0 * mcode / code, "total_functions": funcs, "matched_functions": mfuncs,
             "matched_functions_percent": 100.0 * mfuncs / funcs}
        if units:
            d.update(total_units=units, complete_units=done)
        return d
    return {"measures": meas(1000, 600, 10, 7, units=2), "version": 1,
            "units": [{"name": "main/a", "measures": meas(600, 500, 6, 5),
                       "functions": [{"name": "func_80010000", "size": "120", "fuzzy_match_percent": 100.0,
                                      "metadata": {"virtualAddress": "2147549184"}}]},
                      {"name": "main/b", "measures": meas(400, 100, 4, 2),
                       "metadata": {"complete": False, "progressCategories": ["game"]}}],
            "categories": [{"id": "game", "name": "Game", "measures": meas(1000, 600, 10, 7)}]}


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
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd == "validate":
        errs = validate(json.loads(common.read(a.report)), a.artifact, a.version)
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
