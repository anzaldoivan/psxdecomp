#!/usr/bin/env python3
"""ghsearch.py — S3's GitHub search: repositories and files that name the game, as leads for the scouts. Read-only.

    ghsearch.py --title T [--serial S] [--exe E] [--exclude OWNER/REPO ...] [--out FILE] [--json]
    ghsearch.py --self-test                     canned API answers; no network

Community modding work rarely says "decomp" or "symbols" (Kuumba123's MegaManX6_PS1_Modding; scope: mmx6,
2026-10-03), so S3 searches GitHub for the game's own names. Repository search runs three queries: the title as a
phrase, the joined form `<joined> in:name` (MegaManX6) and the initials `<initials> in:name` (MMX6, DC2, BFM; a final
numbered token is kept whole, and only initials of 3+ characters are used). A repository is kept only when its name or
description holds one of those forms on a token boundary (drops MegaManX69, mmx5240), and a hit on the initials alone
also needs the platform or another title word next to it (`DC2 in:name` is mostly Defcon badges). Code search (the
serial in both forms and the executable's name) needs GitHub auth; its hits are grouped per repository, 5 paths each.

Backend: `gh api` when `gh auth status` is green; else api.github.com with $GH_TOKEN / $GITHUB_TOKEN; else anonymous
(repository search only: `SKIP code search: no GitHub auth`). A network error prints `SKIP` and exits 0: the search
never blocks S3. `--exclude` drops repositories (fnmatch, case-insensitive; backtests pass the replayed project's own
repositories); the plugin's own repository is always dropped (its fixtures are deliberately stale).

Writes `.run/bootstrap/research/github.md` (or `--out`): one row per repository, leads, not facts.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

API = "https://api.github.com"
TIMEOUT = 20
PER_PAGE = 30
MAX_PATHS = 5
MAX_CODE_REPOS = 15
ALWAYS_EXCLUDE = ["*/psxdecomp"]            # the plugin itself: its fixtures and evals plant stale leads on purpose
PLATFORM = re.compile(r"(?<![A-Za-z0-9])(ps1|psx|psone|playstation|ps-x)(?![a-z])", re.I)
ROMAN = re.compile(r"^(?=[IVX]+$)X{0,3}(IX|IV|V?I{0,3})$")
STOP = {"the", "and", "of", "for", "with"}
OUT_REL = ".run/bootstrap/research/github.md"


class NetError(Exception):
    pass


# ---- names ----------------------------------------------------------------------------------------------------

def tokens(title: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", title or "")


def variants(title: str) -> dict:
    """{'phrase', 'joined', 'initials' (or None)} for a title."""
    toks = tokens(title)
    joined = "".join(toks)
    initials = None
    if len(toks) >= 2:
        last = toks[-1]
        keep_last = bool(re.search(r"\d", last)) or bool(ROMAN.match(last))
        heads = [t[0] for t in (toks[:-1] if keep_last else toks)]
        cand = ("".join(heads) + (last if keep_last else "")).upper()
        initials = cand if len(cand) >= 3 else None
    return {"phrase": " ".join(toks), "joined": joined, "initials": initials}


def _form(word_parts: list[str]) -> str:
    return r"[\s_.\-]*".join(re.escape(p) for p in word_parts)


def _bounded(text: str, pattern: str) -> bool:
    """`pattern` occurs in `text` (case-insensitive) on a token boundary: before it the start, a non-alphanumeric or a
    lower→upper camel step; after it the end, a non-alphanumeric or an uppercase letter after a non-uppercase end."""
    for m in re.finditer(pattern, text or "", re.I):
        s, e = m.start(), m.end()
        left = s == 0 or not text[s - 1].isalnum() or (text[s - 1].islower() and text[s].isupper())
        right = e == len(text) or not text[e].isalnum() or (text[e].isupper() and not text[e - 1].isupper())
        if left and right:
            return True
    return False


def match(title: str, name: str, description: str) -> str | None:
    """Which form of the title the repository's name or description holds on a token boundary, or None."""
    v = variants(title)
    toks = tokens(title)
    full = _form(toks)                                  # the phrase with any or no separator: covers the joined form
    for where, text in (("name", name), ("description", description)):
        if toks and _bounded(text, full):
            return "%s: %s" % (where, v["joined"] if where == "name" else v["phrase"])
    if v["initials"]:
        both = "%s %s" % (name or "", description or "")
        hit = [w for w, t in (("name", name), ("description", description)) if _bounded(t, re.escape(v["initials"]))]
        if hit:
            words = [t for t in toks if len(t) >= 4 and t.lower() not in STOP]
            if PLATFORM.search(both) or any(_bounded(both, re.escape(w)) for w in words):
                return "%s: %s" % (hit[0], v["initials"])
    return None


def serial_forms(serial: str | None, exe: str | None) -> list[str]:
    """The serial as printed (SLUS-01334) and as an underscore (SLUS_01334), then the executable name (SLUS_013.34)."""
    out = []
    m = re.search(r"([A-Za-z]{4})[-_ ]?(\d{3})\.?(\d{2})", serial or "")
    if m:
        p, n = m.group(1).upper(), m.group(2) + m.group(3)
        out += ["%s-%s" % (p, n), "%s_%s" % (p, n)]
    if exe:
        out.append(exe)
    seen, res = set(), []
    for x in out:
        if x.lower() not in seen:
            seen.add(x.lower())
            res.append(x)
    return res


def excluded(full_name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(full_name.lower(), p.lower()) for p in patterns)


def split_excludes(values: list[str] | None) -> list[str]:
    return [x for v in (values or []) for x in re.split(r"[\s,]+", v) if x]


# ---- backends -------------------------------------------------------------------------------------------------

def gh_backend():
    def fetch(path: str, params: dict) -> dict:
        cmd = ["gh", "api", "-X", "GET", path] + sum((["-f", "%s=%s" % kv] for kv in params.items()), [])
        try:
            r = common.run(cmd, check=False, timeout=TIMEOUT * 2)
        except (OSError, Exception) as e:              # a timeout or a missing binary
            raise NetError(str(e))
        if r.returncode != 0:
            raise NetError((r.stderr or r.stdout).strip()[-300:])
        return json.loads(r.stdout)
    return fetch


def http_backend(token: str | None):
    def fetch(path: str, params: dict) -> dict:
        url = "%s/%s?%s" % (API, path.lstrip("/"), urllib.parse.urlencode(params))
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "psxdecomp-ghsearch",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise NetError(str(e))
    return fetch


def pick_backend() -> tuple[str, object, bool]:
    """(label, fetch, authenticated)."""
    try:
        if common.run(["gh", "auth", "status"], check=False, timeout=TIMEOUT).returncode == 0:
            return "gh api (authenticated)", gh_backend(), True
    except (OSError, Exception):
        pass
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return "api.github.com (token)", http_backend(token), True
    return "api.github.com (anonymous)", http_backend(None), False


# ---- search ---------------------------------------------------------------------------------------------------

def _licence(repo: dict) -> str:
    lic = repo.get("license") or {}
    sid = lic.get("spdx_id") or ""
    if not lic or sid in ("", "NOASSERTION"):
        return "unstated" if not lic else (lic.get("name") or "unstated")
    return sid


def _row(repo: dict, matched: str) -> dict:
    return {"repo": repo.get("full_name", ""), "url": repo.get("html_url") or "https://github.com/" + repo.get(
        "full_name", ""), "licence": _licence(repo), "updated": (repo.get("pushed_at") or repo.get("updated_at") or "")[:10],
        "matched": matched, "description": (repo.get("description") or "").strip(), "paths": [],
        "archived": bool(repo.get("archived"))}


def search(fetch, authed: bool, title: str, serial: str | None = None, exe: str | None = None,
           exclude: list[str] | None = None) -> dict:
    """Returns {'rows', 'skips', 'dropped', 'excluded', 'queries'}."""
    pats = ALWAYS_EXCLUDE + list(exclude or [])
    v = variants(title)
    queries = ['"%s"' % v["phrase"], "%s in:name" % v["joined"]]
    if v["initials"] and v["initials"].lower() != v["joined"].lower():
        queries.append("%s in:name" % v["initials"])
    rows: dict[str, dict] = {}
    skips, dropped, excl = [], [], set()
    for q in queries:
        try:
            items = fetch("search/repositories", {"q": q, "per_page": str(PER_PAGE)}).get("items") or []
        except NetError as e:
            skips.append("SKIP repo search %s: %s" % (q, e))
            continue
        for repo in items:
            fn = repo.get("full_name", "")
            if excluded(fn, pats):
                excl.add(fn)
                continue
            if fn.lower() in rows:
                continue
            m = match(title, repo.get("name") or fn.split("/")[-1], repo.get("description") or "")
            if m is None:
                dropped.append(fn)
                continue
            rows[fn.lower()] = _row(repo, m)
    codeq = serial_forms(serial, exe)
    if codeq and not authed:
        skips.append("SKIP code search: no GitHub auth (gh auth login, or $GH_TOKEN)")
    elif codeq:
        hits: dict[str, dict] = {}
        for q in codeq:
            try:
                items = fetch("search/code", {"q": '"%s"' % q, "per_page": "50"}).get("items") or []
            except NetError as e:
                skips.append("SKIP code search %s: %s" % (q, e))
                continue
            for it in items:
                repo = it.get("repository") or {}
                fn = repo.get("full_name", "")
                if not fn or excluded(fn, pats):
                    if fn:
                        excl.add(fn)
                    continue
                h = hits.setdefault(fn.lower(), {"repo": repo, "terms": [], "paths": []})
                if q not in h["terms"]:
                    h["terms"].append(q)
                if it.get("path") and it["path"] not in h["paths"]:
                    h["paths"].append(it["path"])
        for key, h in list(hits.items())[:MAX_CODE_REPOS]:
            row = rows.get(key)
            if row is None:
                repo = h["repo"]
                try:
                    repo = fetch("repos/%s" % repo["full_name"], {}) or repo
                except NetError:
                    pass
                row = rows[key] = _row(repo, "")
            row["matched"] = "; ".join(x for x in (row["matched"], "code: " + ", ".join(h["terms"])) if x)
            row["paths"] = sorted(h["paths"])[:MAX_PATHS] + (["(+%d more)" % (len(h["paths"]) - MAX_PATHS)]
                                                            if len(h["paths"]) > MAX_PATHS else [])
    ordered = sorted(rows.values(), key=lambda r: r["updated"], reverse=True)       # newest first, then
    ordered.sort(key=lambda r: r["matched"].startswith("code:"))                      # named hits above code-only
    return {"rows": ordered, "skips": skips,
            "dropped": sorted(set(dropped)), "excluded": sorted(excl), "queries": queries + ['"%s"' % q for q in codeq]}


def _cell(s: str, n: int = 120) -> str:
    s = re.sub(r"\s+", " ", s or "").replace("|", "\\|")
    return s if len(s) <= n else s[:n - 1] + "…"


def render(res: dict, title: str, backend: str, date: str) -> str:
    out = ["# GitHub search — %s (%s)" % (title, date), "",
           "Leads, not facts: each row is a repository whose name, description or files mention the game. Its "
           "licence is GitHub's field (`unstated` when GitHub has none: class `facts`). Nothing here is verified "
           "against the game's bytes; the scouts classify each row.", "",
           "Backend: %s. Queries: %s." % (backend, ", ".join("`%s`" % q for q in res["queries"])), ""]
    if res["rows"]:
        out += ["| Repository | Licence | Last update | Matched by | Description | Paths |", "|---|---|---|---|---|---|"]
        for r in res["rows"]:
            out.append("| [%s](%s)%s | %s | %s | %s | %s | %s |" % (
                r["repo"], r["url"], " (archived)" if r["archived"] else "", r["licence"], r["updated"] or "?",
                _cell(r["matched"], 80), _cell(r["description"]), _cell(", ".join(r["paths"]), 200)))
    else:
        out.append("No repository found on %s." % date)
    out.append("")
    for s in res["skips"]:
        out.append("- %s" % s)
    out.append("- Dropped by the name filter: %d repositor%s%s." % (
        len(res["dropped"]), "y" if len(res["dropped"]) == 1 else "ies",
        " (%s)" % ", ".join(res["dropped"][:8]) + (" …" if len(res["dropped"]) > 8 else "") if res["dropped"] else ""))
    if res["excluded"]:                                  # a count only: in a backtest the names would be the answer
        out.append("- Excluded: %d repositor%s." % (len(res["excluded"]), "y" if len(res["excluded"]) == 1 else "ies"))
    return "\n".join(out) + "\n"


# ---- self-test ------------------------------------------------------------------------------------------------

def _repo(fn, desc="", lic=None, pushed="2026-01-01T00:00:00Z"):
    return {"full_name": fn, "name": fn.split("/")[1], "description": desc, "html_url": "https://github.com/" + fn,
            "license": {"spdx_id": lic, "name": lic} if lic else None, "pushed_at": pushed}


def _canned():
    repos = {
        '"Mega Man X6"': [_repo("someone/mega-man-x6-tas", "TAS notes for Mega Man X6", "MIT")],
        "MegaManX6 in:name": [_repo("Kuumba123/MegaManX6_PS1_Modding", "Modding tools and docs", None,
                                    "2025-05-01T00:00:00Z"),
                              _repo("Kuumba123/MegaManX6_Practice", "Practice ROM"),
                              _repo("noise/MegaManX69", "unrelated"),
                              _repo("anzaldoivan/mmx6", "Matching decompilation of Mega Man X6"),
                              _repo("anzaldoivan/psxdecomp", "plugin with MegaManX6 fixtures")],
        "MMX6 in:name": [_repo("x/mmx6-randomizer", "a PS1 randomizer", "GPL-3.0"),
                         _repo("y/mmx6x", "nothing"), _repo("z/MMX6", "my homework")],
    }
    code = {'"SLUS-01395"': [{"path": "docs/mmx6-ghidra-findings.md", "repository": _repo("silasary/apworlds")},
                             {"path": "src/a.md", "repository": _repo("anzaldoivan/mmx6")}],
            '"SLUS_01395"': [],
            '"SLUS_013.95"': [{"path": "cheats/SLUS-01395.cht", "repository": _repo("duckstation/chtdb")}]
                             + [{"path": "c/%d.cht" % i, "repository": _repo("duckstation/chtdb")} for i in range(7)]}
    meta = {"silasary/apworlds": _repo("silasary/apworlds", "Archipelago worlds", "MIT"),
            "duckstation/chtdb": _repo("duckstation/chtdb", "Cheat database", None)}
    calls = []

    def fetch(path, params):
        calls.append((path, params.get("q")))
        if path == "search/repositories":
            return {"items": repos.get(params["q"], [])}
        if path == "search/code":
            return {"items": code.get(params["q"], [])}
        return meta[path.split("/", 1)[1]]
    return fetch, calls


def self_test() -> int:
    ok = True
    want = {"Mega Man X6": ("MegaManX6", "MMX6"), "Dino Crisis 2": ("DinoCrisis2", "DC2"),
            "Brave Fencer Musashi": ("BraveFencerMusashi", "BFM"), "Final Fantasy VII": ("FinalFantasyVII", "FFVII"),
            "Tekken 3": ("Tekken3", None), "Spyro the Dragon": ("SpyrotheDragon", "STD")}
    for t, (j, i) in want.items():
        v = variants(t)
        good = v["joined"] == j and v["initials"] == i
        print("  variants %-22s %s / %s %s" % (t, v["joined"], v["initials"], "ok" if good else "WRONG"))
        ok &= good
    cases = [("MegaManX5_PS1_Modding", "", True), ("MegaManX69", "", False), ("mmx5240", "", False),
             ("site-mmx5qq8x", "", False), ("mega-man-x5-tools", "", True), ("MMX5", "PS1 notes", True),
             ("MMX5", "my homework", False), ("tools", "Docs for Mega Man X5 on PSX", True),
             ("KuumbaMegaManX5Tools", "", True)]
    for name, desc, keep in cases:
        got = match("Mega Man X5", name, desc) is not None
        print("  boundary %-22s %s" % (name, "ok" if got == keep else "WRONG (kept=%s)" % got))
        ok &= got == keep
    ok &= serial_forms("USA SLUS-01334", "SLUS_013.34") == ["SLUS-01334", "SLUS_01334", "SLUS_013.34"]
    ok &= serial_forms("SLUS_013.34", "SLUS_013.34") == ["SLUS-01334", "SLUS_01334", "SLUS_013.34"]
    fetch, calls = _canned()
    res = search(fetch, True, "Mega Man X6", "USA SLUS-01395 (disc v1.1)", "SLUS_013.95", ["anzaldoivan/mmx6"])
    names = [r["repo"] for r in res["rows"]]
    print("  kept: %s" % ", ".join(names))
    ok &= set(names) == {"someone/mega-man-x6-tas", "Kuumba123/MegaManX6_PS1_Modding", "Kuumba123/MegaManX6_Practice",
                         "x/mmx6-randomizer", "silasary/apworlds", "duckstation/chtdb"}
    ok &= res["excluded"] == ["anzaldoivan/mmx6", "anzaldoivan/psxdecomp"]           # --exclude and the plugin itself
    ok &= set(res["dropped"]) == {"noise/MegaManX69", "y/mmx6x", "z/MMX6"}
    row = {r["repo"]: r for r in res["rows"]}
    ok &= row["Kuumba123/MegaManX6_PS1_Modding"]["licence"] == "unstated" and row["x/mmx6-randomizer"]["licence"] == "GPL-3.0"
    ok &= row["silasary/apworlds"]["licence"] == "MIT" and row["silasary/apworlds"]["paths"] == ["docs/mmx6-ghidra-findings.md"]
    ok &= len(row["duckstation/chtdb"]["paths"]) == MAX_PATHS + 1 and row["duckstation/chtdb"]["paths"][-1] == "(+3 more)"
    md = render(res, "Mega Man X6", "canned", "2026-10-03")
    ok &= "Leads, not facts" in md and "anzaldoivan" not in md and "- Excluded: 2 repositories." in md
    ok &= "| unstated |" in md and md.count("\n| [") == 6
    fetch, calls = _canned()
    res = search(fetch, False, "Mega Man X6", "SLUS-01395", "SLUS_013.95")
    ok &= not any(p == "search/code" for p, _ in calls)
    ok &= any(s.startswith("SKIP code search: no GitHub auth") for s in res["skips"])
    print("  no auth: %s" % res["skips"][0])

    def down(path, params):
        raise NetError("<urlopen error [Errno 8] nodename nor servname provided>")
    res = search(down, True, "Mega Man X6", "SLUS-01395", None)
    ok &= res["rows"] == [] and len(res["skips"]) == 3 + 2 and all(s.startswith("SKIP") for s in res["skips"])
    with tempfile.TemporaryDirectory() as td:
        rc = main(["--title", "Mega Man X6", "--serial", "SLUS-01395", "--out", os.path.join(td, "g.md")],
                  backend=("down", down, True))
        ok &= rc == 0 and "No repository found" in common.read(os.path.join(td, "g.md"))
    print("  network error: rc %d, %d SKIP lines" % (rc, len(res["skips"])))
    return common.self_test_banner("ghsearch", ok)


def main(argv=None, backend=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--title")
    ap.add_argument("--serial")
    ap.add_argument("--exe")
    ap.add_argument("--exclude", nargs="*", action="extend", default=[],
                    help="OWNER/REPO (fnmatch) to drop; space or comma separated")
    ap.add_argument("--out", help="default: %s under the current folder" % OUT_REL)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.title:
        ap.error("--title is required")
    label, fetch, authed = backend or pick_backend()
    res = search(fetch, authed, a.title, a.serial, a.exe, split_excludes(a.exclude))
    date = common.today()
    out = a.out or OUT_REL
    common.write(out, render(res, a.title, label, date))
    if a.json:
        print(json.dumps(dict(res, excluded=len(res["excluded"])), indent=2))
    else:
        for r in res["rows"]:
            print("GHSEARCH %s | %s | %s | %s | %s" % (r["repo"], r["licence"], r["updated"], r["matched"],
                                                    _cell(r["description"], 70)))
        for s in res["skips"]:
            print(s)
        print("GHSEARCH %d repositor%s for %r via %s, %d dropped by the name filter, %d excluded; %s (%s)" % (
            len(res["rows"]), "y" if len(res["rows"]) == 1 else "ies", a.title, label, len(res["dropped"]),
            len(res["excluded"]), out, date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
