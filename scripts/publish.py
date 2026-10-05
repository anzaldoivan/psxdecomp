#!/usr/bin/env python3
"""publish.py — the publishing standard of a psxdecomp game repository: its README and its decomp.dev report.

    publish.py lint [README.md] [--repo DIR] [--categories TSV] [--discs TSV] [--release]
                                          the README against the standard: FAIL / WARN / INFO lines; exit 1 on a FAIL
    publish.py render [README.md] [--repo DIR] [--categories TSV] [--discs TSV] [--write]
                                          the generated blocks (disc table, progress table); prints a diff summary
    publish.py categories [TSV] [--repo DIR] [--history]
                                          config/categories.tsv's rules; --history: no id ever committed is gone
    publish.py categorize REPORT --categories TSV [-o OUT]
                                          every category's measures from the units' progress_categories; version 2
    publish.py validate REPORT [--categories TSV] [--artifact A] [--version V] [--exe NAME]
                                          a report.json against report.proto, its arithmetic and the firewall
    publish.py --self-test

One file, standard library only, no import from the plugin: S10 and /psxdecomp:upgrade copy it byte for byte into a
game repository as tools/psxd_publish.py, and the game's CI runs that copy. The standard itself (sections, ids, the
report contract, where each fact comes from) is psxdecomp's docs/PUBLISHING.md; this file is its code.

Game records it reads (all tracked, all the game's own): config/categories.tsv (`id parent name status`; identity
only, frozen from the first publish), config/discs.tsv (`disc serial executable track source`), config/medium.sha1,
config/check.*.sha, manifest/*.jsonl, the Makefile, and `git remote get-url origin`.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse

# ---- the AI policy (its one home; scripts/common.py re-exports it, the plugin's README carries it verbatim) -------
AI_POLICY = ("LLMs produce negligible decompilation results without good guidance. Investigate and familiarize "
             "yourself with the console's architecture and the game you are decompiling, and always use your own "
             "judgment. Humans drive the decisions; AI reads and writes the code.")
AI_POLICY_MARK = "<!-- psxdecomp: ai-policy -->"
# The start of the disclosure sentence the interview offered before AI_POLICY (the canned answers still carry it).
OLD_DISCLOSURE = "This project is developed with substantial AI assistance"


def ai_policy_block() -> str:
    return "%s\n> [!IMPORTANT]\n> **AI policy:** %s\n" % (AI_POLICY_MARK, AI_POLICY)


# ---- the README schema ------------------------------------------------------------------------------------------
README_H2 = ["Description", "Progress", "Building the decompilation", "Repository layout", "Getting started",
             "Acknowledgements", "License"]
README_H3 = {"Getting started": ["Setting up", "Contributing", "Reference"]}
FREE_AFTER = "Acknowledgements"          # any other H2 may follow it (Contact, Links…), none may precede it
BLOCKS = {"disc": "Description", "progress": "Progress"}      # generated block -> the H2 it lives under
GAME_BLOCK = ("<!-- progress:begin -->", "<!-- progress:end -->")  # the game's own numbers block (kit corpus), allowed


def marker(name: str, end: bool = False) -> str:
    return "<!-- psxdecomp:%s:%s -->" % (name, "end" if end else "begin")


NO_GAME_DATA = re.compile(r"\bno\s+(?:\*\*)?game\s+data\b", re.I)
SERIAL_RE = re.compile(r"^[A-Z]{4}-\d{5}$")                 # SLUS-01395, SLPS-01603
EXE_RE = re.compile(r"^[A-Z]{4}_\d{3}\.\d{2}$")             # SLUS_013.95
SHA1_RE = re.compile(r"\b[0-9a-f]{40}\b")
TODO_PHASE = "TODO(phase-"

# ---- decomp.dev (encounter/decomp.dev main, read 2026-10-04: crates/images/src/badge.rs, crates/github/src/lib.rs)
BADGE_MEASURES = {"fuzzy_match_percent", "fuzzy_match", "matched_code_percent", "matched_code", "code",
                  "matched_code_bytes", "matched_code_size", "matched_data_percent", "matched_data", "data",
                  "matched_data_bytes", "matched_data_size", "matched_functions", "functions",
                  "matched_functions_percent", "complete_code_percent", "complete_code", "complete_code_bytes",
                  "complete_code_size", "complete_data_percent", "complete_data", "complete_data_bytes",
                  "complete_data_size", "complete_units", "complete_units_percent"}
DECOMPDEV = "https://decomp.dev"
DD_URL = re.compile(r"https?://decomp\.dev/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(\.svg)?(?:\?([^\s)\"'<>\]]*))?"
                    r"(?=[\s)\"'<>\]]|$)")
DD_RESERVED = {"api", "manage", "login", "logout", "auth", "assets", "static", "projects", "about"}
REPORT_VERSION = 2                         # objdiff-core REPORT_VERSION: decomp.dev refuses any other after migrate()
ARTIFACT = re.compile(r"^[A-Za-z0-9._-]+_report$")

# ---- what psxdecomp writes into a game repository from this standard (S10, /psxdecomp:upgrade) -------------------
VENDORED = "tools/psxd_publish.py"                        # this file, byte for byte
WORKFLOW = ".github/workflows/psxdecomp-readme.yml"       # profiles/psx/psxdecomp-readme.yml: lint + the freeze

# ---- the category list ------------------------------------------------------------------------------------------
CATEGORIES_REL = "config/categories.tsv"
CATEGORIES_HEAD = ["id", "parent", "name", "status"]
CATEGORY_ID = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)?$")
KINDS = ("game", "sdk")                    # required; every other top-level id is a binary or an overlay group
DISCS_REL = "config/discs.tsv"
DISCS_HEAD = ["disc", "serial", "executable", "track", "source"]
SOURCES = ("redump", "dump")

# ---- objdiff report.proto (encounter/objdiff objdiff-core/protos/report.proto, read 2026-10-02 at eed74b9) -------
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
SUMMED = ["total_code", "matched_code", "total_data", "matched_data", "total_functions", "matched_functions",
          "complete_code", "complete_data"]
PCT_TOL = 0.01
HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")                  # 32+ bytes as hex
B64_RUN = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")           # 60+ bytes as base64


# ---- small helpers ----------------------------------------------------------------------------------------------

def _read(path) -> str | None:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)


def origin_slug(repo) -> str | None:
    """OWNER/REPO of `git remote get-url origin` on GitHub, or None."""
    r = _git(repo, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return "%s/%s" % (m[1], m[2]) if m else None


def repo_root(start) -> pathlib.Path:
    r = _git(start, "rev-parse", "--show-toplevel")
    return pathlib.Path(r.stdout.strip() if r.returncode == 0 else start).resolve()


def _tsv(text: str, head: list[str], what: str) -> tuple[list[dict], list[str]]:
    """Rows of a tab-separated record with a fixed header; `#` lines and blank lines are skipped."""
    rows, errs, seen_head = [], [], False
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if not seen_head:
            seen_head = True
            if cells != head:
                errs.append("%s:%d: the header must be %s" % (what, n, "<TAB>".join(head)))
            continue
        if len(cells) != len(head):
            errs.append("%s:%d: %d fields, want %d (tab-separated)" % (what, n, len(cells), len(head)))
            continue
        rows.append(dict(zip(head, (c.strip() for c in cells)), _line=n))
    if not seen_head:
        errs.append("%s: empty (no header row)" % what)
    return rows, errs


# ---- config/categories.tsv --------------------------------------------------------------------------------------

def parse_categories(text: str, what: str = CATEGORIES_REL) -> tuple[list[dict], list[str]]:
    rows, errs = _tsv(text, CATEGORIES_HEAD, what)
    ids: dict[str, dict] = {}
    for r in rows:
        at = "%s:%d" % (what, r["_line"])
        i = r["id"]
        if not CATEGORY_ID.match(i):
            errs.append("%s: id %r: lower-case [a-z0-9_], one optional `parent.child` dot" % (at, i))
        if i in ids:
            errs.append("%s: id %r declared twice (line %d)" % (at, i, ids[i]["_line"]))
        ids.setdefault(i, r)
        if r["status"] not in ("active", "retired"):
            errs.append("%s: status %r: active or retired" % (at, r["status"]))
        if not r["name"]:
            errs.append("%s: %s has no name" % (at, i))
        want = i.split(".", 1)[0] if "." in i else ""
        if r["parent"] != want:
            errs.append("%s: %s's parent column is %r, want %r (%s)" % (
                at, i, r["parent"], want, "the id's prefix" if want else "empty for a top-level id"))
    for r in rows:
        if "." in r["id"]:
            p = ids.get(r["id"].split(".", 1)[0])
            if p is None:
                errs.append("%s:%d: %s's parent %r is not declared" % (what, r["_line"], r["id"], r["parent"]))
            elif p["status"] == "retired" and r["status"] == "active":
                errs.append("%s:%d: %s is active under the retired %s" % (what, r["_line"], r["id"], p["id"]))
    for k in KINDS:
        if k in ids and ids[k]["status"] != "active":
            errs.append("%s: %r must stay active" % (what, k))
        elif k not in ids:
            errs.append("%s: %r is required (decomp.dev's guide: `game` and `sdk`)" % (what, k))
    return rows, errs


def load_categories(path) -> tuple[list[dict] | None, list[str]]:
    text = _read(path)
    if text is None:
        return None, []
    return parse_categories(text, os.path.basename(str(path)) if os.path.isabs(str(path)) else str(path))


def history_errors(repo, rows: list[dict], rel: str = CATEGORIES_REL) -> tuple[list[str], int]:
    """Every id in any committed version of the list is still declared: retire, never delete or rename."""
    r = _git(repo, "rev-list", "HEAD", "--", rel)
    if r.returncode != 0:
        return [], 0
    now = {x["id"] for x in rows}
    gone: dict[str, str] = {}
    commits = r.stdout.split()
    for c in commits:
        old = _git(repo, "show", "%s:%s" % (c, rel))
        if old.returncode != 0:
            continue
        for x in parse_categories(old.stdout)[0]:
            if x["id"] not in now:
                gone.setdefault(x["id"], c[:7])
    return ["%s: id %r was published (commit %s) and is gone: ids are frozen — restore the row with status retired"
            % (rel, i, c) for i, c in sorted(gone.items())], len(commits)


def active(rows: list[dict] | None) -> list[dict]:
    return [r for r in rows or [] if r["status"] == "active"]


# ---- config/discs.tsv, config/medium.sha1, config/check.*.sha ----------------------------------------------------

def load_discs(path) -> tuple[list[dict] | None, list[str]]:
    text = _read(path)
    if text is None:
        return None, []
    rows, errs = _tsv(text, DISCS_HEAD, DISCS_REL)
    for r in rows:
        at = "%s:%d" % (DISCS_REL, r["_line"])
        if not SERIAL_RE.match(r["serial"]):
            errs.append("%s: serial %r: the form printed on the disc, e.g. SLUS-01395" % (at, r["serial"]))
        if not EXE_RE.match(r["executable"]):
            errs.append("%s: executable %r: the boot file name, e.g. SLUS_013.95" % (at, r["executable"]))
        if r["source"] not in SOURCES:
            errs.append("%s: source %r: redump (checked against Redump) or dump" % (at, r["source"]))
        if not r["disc"]:
            errs.append("%s: the disc label is empty" % at)
    if not rows and not errs:
        errs.append("%s: no disc row" % DISCS_REL)
    return rows, errs


def sha_lines(text: str | None) -> list[tuple[str, str]]:
    """(sha1, name) per `sha1sum` line."""
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^([0-9a-fA-F]{40})\s+\*?(.+?)\s*$", line)
        if m:
            out.append((m[1].lower(), m[2]))
    return out


def data_track(medium: list[tuple[str, str]], track: str) -> str | None:
    if track:
        return next((h for h, n in medium if n == track), None)
    bins = [(h, n) for h, n in medium if n.lower().endswith(".bin")]
    if len(bins) == 1:
        return bins[0][0]
    return next((h for h, n in bins if re.search(r"\(track 0?1\)", n, re.I)), None)


def _norm(name: str) -> set[str]:
    base = os.path.basename(name).lower()
    out = {re.sub(r"[^a-z0-9]", "_", base)}
    stem, ext = os.path.splitext(base)
    if ext in (".bin", ".exe", ".elf"):
        out.add(re.sub(r"[^a-z0-9]", "_", stem))
    return out


def target_sha(repo: pathlib.Path, exe: str) -> tuple[str, str] | None:
    """(sha1, record) of the executable from config/check.*.sha: the line whose path names it."""
    want = _norm(exe)
    for rec in sorted(glob.glob(str(repo / "config" / "check.*.sha"))):
        for h, n in sha_lines(_read(rec)):
            if _norm(n) & want:
                return h, os.path.relpath(rec, repo)
    return None


def recorded_hashes(repo: pathlib.Path) -> set[str]:
    """Every SHA-1 in the tracked records a README may quote: medium.sha1, check.*.sha, the extraction manifest."""
    out = set()
    for pat in ("config/medium.sha1", "config/check.*.sha", "manifest/*.jsonl", "extracted/*/manifest.jsonl"):
        for f in glob.glob(str(repo / pat)):
            out |= set(SHA1_RE.findall((_read(f) or "").lower()))
    return out


# ---- the generated blocks ---------------------------------------------------------------------------------------

class Ctx:
    """Where a README's facts come from: the repository, and the two records (overridable to lint a draft)."""

    def __init__(self, repo, categories=None, discs=None):
        self.repo = pathlib.Path(repo).resolve()
        self.categories_path = pathlib.Path(categories) if categories else self.repo / CATEGORIES_REL
        self.discs_path = pathlib.Path(discs) if discs else self.repo / DISCS_REL
        self.categories, self.categories_errs = load_categories(self.categories_path)
        self.discs, self.discs_errs = load_discs(self.discs_path)
        self.slug = origin_slug(self.repo)


class RenderError(Exception):
    pass


def badge(slug: str, label: str, measure: str, category: str) -> str:
    return "%s/%s.svg?mode=shield&label=%s&measure=%s&category=%s" % (DECOMPDEV, slug, label, measure, category)


def progress_row(slug: str, r: dict) -> str:
    """One `| Category | Name | Status |` row: the Code and Functions badges of r's id, each linked to its page."""
    page = "%s/%s?category=%s" % (DECOMPDEV, slug, r["id"])
    return "| `%s` | %s | [![Code](%s)](%s) [![Functions](%s)](%s) |" % (
        r["id"], r["name"].replace("|", "\\|"), badge(slug, "Code", "code", r["id"]), page,
        badge(slug, "Functions", "functions", r["id"]), page)


def render_progress(ctx: Ctx) -> list[str]:
    if ctx.categories is None:
        return ["*Not published yet.* The progress table and its [decomp.dev](%s) badges appear here with the "
                "project's first progress report; `config/categories.tsv` names what they count." % DECOMPDEV]
    if ctx.categories_errs:
        raise RenderError("config/categories.tsv: %s" % ctx.categories_errs[0])
    if not ctx.slug:
        raise RenderError("no GitHub `origin` remote: the badges need OWNER/REPO")
    s = ctx.slug
    head = ["| Category | Name | Status |", "|---|---|---|"]
    out = ["[![Code][psxd-code]][psxd-progress] [![Functions][psxd-functions]][psxd-progress]", ""] + head
    rows = [r for r in active(ctx.categories) if "." not in r["id"] and r["id"] not in KINDS]
    rows += [r for r in active(ctx.categories) if r["id"] == "sdk"]             # the binaries, then the SDK
    out += [progress_row(s, r) for r in rows]
    for r in rows:                     # each group's overlays, collapsed: a long table stays out of the way
        kids = [k for k in active(ctx.categories) if k["parent"] == r["id"]]
        if kids:
            out += ["", "<details><summary><code>%s</code>: %d overlay%s</summary>" % (
                r["id"], len(kids), "" if len(kids) == 1 else "s"), ""] + head
            out += [progress_row(s, k) for k in kids] + ["", "</details>"]
    out += ["", "Progress bars powered by [decomp.dev][psxd-progress].", "",
            "[psxd-code]: %s" % badge(s, "Code", "code", "game"),
            "[psxd-functions]: %s" % badge(s, "Functions", "functions", "game"),
            "[psxd-progress]: %s/%s" % (DECOMPDEV, s)]
    return out


def render_disc(ctx: Ctx) -> list[str]:
    if ctx.discs is None:
        return ["*Disc facts not recorded yet:* `config/discs.tsv` (disc, serial, executable) and the dump's "
                "`config/medium.sha1`."]
    if ctx.discs_errs:
        raise RenderError(ctx.discs_errs[0])
    medium = sha_lines(_read(ctx.repo / "config" / "medium.sha1"))
    out = ["| Disc | Serial | Executable | SHA-1 of the data track |", "|---|---|---|---|"]
    for d in ctx.discs:
        h = data_track(medium, d["track"])
        cell = "`%s`%s" % (h, " (Redump)" if d["source"] == "redump" else "") if h else "not recorded yet"
        out.append("| %s | %s | `%s` | %s |" % (d["disc"], d["serial"], d["executable"], cell))
    seen = []
    for d in ctx.discs:
        if d["executable"] in seen:
            continue
        seen.append(d["executable"])
        t = target_sha(ctx.repo, d["executable"])
        if t:
            out += ["", "The target `%s` has SHA-1 `%s` (`%s`); every build checks its rebuild against it."
                    % (d["executable"], t[0], t[1])]
    return out


RENDER = {"disc": render_disc, "progress": render_progress}


def _blocks(lines: list[str], name: str) -> list[tuple[int, int]]:
    b = [i for i, l in enumerate(lines) if l.strip() == marker(name)]
    e = [i for i, l in enumerate(lines) if l.strip() == marker(name, True)]
    return list(zip(b, e)) if len(b) == len(e) else [(-1, -1)]


def render(text: str, ctx: Ctx) -> str:
    """The README with every generated block it carries rewritten from the records; the rest stays byte for byte."""
    for name, fn in RENDER.items():
        lines = text.split("\n")
        spans = _blocks(lines, name)
        if spans == [(-1, -1)] or not spans:
            continue
        body = fn(ctx)
        for b, e in reversed(spans):
            if b < e:
                lines[b + 1:e] = body
        text = "\n".join(lines)
    return text


# ---- the lint ---------------------------------------------------------------------------------------------------

def _scan(text: str):
    """(lines, headings [(level, title, index)], indexes inside fenced code)."""
    lines = text.split("\n")
    heads, code, fence = [], set(), None
    for i, l in enumerate(lines):
        s = l.strip()
        m = re.match(r"^(`{3,}|~{3,})", s)
        if fence:
            code.add(i)
            if m and s[0] == fence[0] and len(m[1]) >= len(fence) and not s[len(m[1]):].strip():
                fence = None
            continue
        if m:
            fence = m[1]
            code.add(i)
            continue
        h = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", l)
        if h:
            heads.append((len(h[1]), h[2].strip(), i))
    return lines, heads, code


def _h2_spans(heads, n: int) -> dict[str, tuple[int, int]]:
    h2 = [(t, i) for lv, t, i in heads if lv <= 2]
    out = {}
    for k, (t, i) in enumerate(h2):
        if t not in out and any(lv == 2 and tt == t and ii == i for lv, tt, ii in heads):
            out[t] = (i, h2[k + 1][1] if k + 1 < len(h2) else n)
    return out


def makefile_targets(repo: pathlib.Path) -> set[str] | None:
    mk = repo / "Makefile"
    if not mk.is_file():
        return None
    out, todo, done = set(), [mk], set()
    while todo:
        f = todo.pop()
        if f in done:
            continue
        done.add(f)
        for line in (_read(f) or "").splitlines():
            inc = re.match(r"^-?include\s+(.+)$", line)
            if inc:
                for pat in inc[1].split():
                    if "$" not in pat:
                        todo += [pathlib.Path(p) for p in glob.glob(str(repo / pat))]
                continue
            m = re.match(r"^([^\s:#=$][^:=]*?)\s*::?(?!=)", line)
            if m and not line.startswith("\t"):
                out |= {t for t in m[1].split() if "%" not in t}
    return out


def _link_targets(lines: list[str], code: set[int]) -> list[tuple[int, str]]:
    out = []
    for i, l in enumerate(lines):
        if i in code:
            continue
        l = re.sub(r"`[^`]*`", "", l)
        for m in re.finditer(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)", l):
            out.append((i, m[1]))
        m = re.match(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", l)
        if m:
            out.append((i, m[1]))
        for m in re.finditer(r"(?:src|href|srcset)=\"([^\"]+)\"", l):
            out.append((i, m[1].split()[0]))
    return out


def path_state(repo: pathlib.Path, rel: str) -> str:
    """tracked / ignored (an honest row: the folder for your own dump) / local (exists here, not in a clone) / missing."""
    rel = rel.strip().lstrip("/").rstrip("/")
    if not rel or _git(repo, "ls-files", "--", rel).stdout.strip():
        return "tracked"
    probe = rel + "/x" if (repo / rel).is_dir() or not (repo / rel).exists() else rel
    if _git(repo, "check-ignore", "-q", "--no-index", rel).returncode == 0 or \
            _git(repo, "check-ignore", "-q", "--no-index", probe).returncode == 0:
        return "ignored"
    if _git(repo, "rev-parse", "--git-dir").returncode != 0:
        return "tracked" if (repo / rel).exists() else "missing"         # not a repository: the files are all there is
    return "local" if (repo / rel).exists() else "missing"


def _path_finding(add, check: str, where: str, repo: pathlib.Path, rel: str):
    st = path_state(repo, rel)
    if st == "missing":
        add("FAIL", check, "%s: %s does not exist in the repository" % (where, rel))
    elif st == "local":
        add("WARN", check, "%s: %s exists here but is not tracked: a fresh clone will not have it" % (where, rel))


MAKE_OPT_ARG = {"-C", "-f", "-I", "-o", "-W", "--directory", "--file", "--include-dir", "--old-file", "--what-if"}


def make_targets_named(command: str) -> list[str]:
    """The targets of each `make` in one shell line: comments, separators, options and VAR=value skipped."""
    out = []
    command = re.sub(r"(^|\s)#.*$", "", command)
    for part in re.split(r"&&|\|\||[;|&()]", command):
        words = part.split()
        for k, w in enumerate(words):
            if os.path.basename(w) != "make":
                continue
            skip = False
            for t in words[k + 1:]:
                if skip:
                    skip = False
                    continue
                if t in MAKE_OPT_ARG or t in ("-j", "-l"):
                    skip = t in MAKE_OPT_ARG
                    continue
                if t.startswith("-") or "=" in t or re.fullmatch(r"\d+", t):
                    continue
                out.append(t.strip("'\"`"))
            break
    return [t for t in out if t]


def lint(text: str, ctx: Ctx, release: bool = False) -> list[tuple[str, str, str]]:
    """[(FAIL|WARN|INFO, check, detail)] for one README against the standard."""
    out = []
    add = lambda lv, ck, d: out.append((lv, ck, d))  # noqa: E731
    lines, heads, code = _scan(text)
    n = len(lines)
    first = next((l for l in lines if l.strip() and not l.lstrip().startswith("<")), "")
    if not first.startswith("# "):
        add("FAIL", "title", "the README starts with a `# ` title (an optional HTML banner may precede it)")
    # headings: the required H2s present, once, in order; nothing unknown before Acknowledgements
    h2 = [(t, i) for lv, t, i in heads if lv == 2]
    pos = 0
    seen = set()
    for t, i in h2:
        if t in README_H2:
            if t in seen:
                add("FAIL", "headings", "## %s appears twice (line %d)" % (t, i + 1))
                continue
            seen.add(t)
            k = README_H2.index(t)
            if k < pos:
                add("FAIL", "headings", "## %s (line %d) is out of order: the order is %s" % (
                    t, i + 1, " / ".join(README_H2)))
            pos = max(pos, k + 1)
        elif FREE_AFTER not in seen:
            add("FAIL", "headings", "## %s (line %d): not a section of the standard; extra sections go after "
                "## %s" % (t, i + 1, FREE_AFTER))
    for t in README_H2:
        if t not in seen:
            add("FAIL", "headings", "missing ## %s" % t)
    spans = _h2_spans(heads, n)
    for parent, kids in README_H3.items():
        if parent not in spans:
            continue
        a, b = spans[parent]
        h3 = [t for lv, t, i in heads if lv == 3 and a < i < b]
        got = [t for t in h3 if t in kids]
        for t in kids:
            if t not in got:
                add("FAIL", "headings", "missing ### %s under ## %s" % (t, parent))
        if [t for t in kids if t in got] != got:
            add("FAIL", "headings", "### %s under ## %s: the order is %s" % (", ".join(got), parent, " / ".join(kids)))
    desc = spans.get("Description", (0, 0))
    inside = lambda i, sec: spans.get(sec, (-1, -1))[0] < i < spans.get(sec, (-1, -1))[1]  # noqa: E731
    # the AI policy, once, verbatim, under Description; the old disclosure gone
    marks = [i for i, l in enumerate(lines) if l.strip() == AI_POLICY_MARK]
    if len(marks) != 1:
        add("FAIL", "ai-policy", "the AI policy block (%s) appears %d times, want once" % (AI_POLICY_MARK, len(marks)))
    else:
        i = marks[0]
        if "\n".join(lines[i:i + 3]) + "\n" != ai_policy_block():
            add("FAIL", "ai-policy", "the AI policy block (line %d) differs from psxdecomp's text: restore it "
                "verbatim (docs: PUBLISHING.md)" % (i + 1))
        if not inside(i, "Description"):
            add("FAIL", "ai-policy", "the AI policy block (line %d) belongs under ## Description" % (i + 1))
    if OLD_DISCLOSURE in text:
        add("FAIL", "ai-policy", "the old disclosure paragraph (%r…) is still there: the AI policy block replaces it"
            % OLD_DISCLOSURE[:40])
    quote = " ".join(l for l in lines[desc[0]:desc[1]] if l.lstrip().startswith(">"))
    if "[!IMPORTANT]" not in quote or not NO_GAME_DATA.search(quote):
        add("FAIL", "no-game-data", "## Description lacks the `> [!IMPORTANT]` note that the repository holds no "
            "game data")
    # generated blocks: present once, in their section, and fresh
    for name, sec in BLOCKS.items():
        b = [i for i, l in enumerate(lines) if l.strip() == marker(name)]
        e = [i for i, l in enumerate(lines) if l.strip() == marker(name, True)]
        if len(b) != 1 or len(e) != 1 or b[0] > e[0]:
            add("FAIL", "blocks", "the %s block needs one `%s` … `%s` pair (found %d/%d)" % (
                name, marker(name), marker(name, True), len(b), len(e)))
        elif not inside(b[0], sec):
            add("FAIL", "blocks", "the %s block (line %d) belongs under ## %s" % (name, b[0] + 1, sec))
    try:
        fresh = render(text, ctx)
    except RenderError as e:
        add("FAIL", "blocks", "cannot render the generated blocks: %s" % e)
        fresh = text
    if fresh != text:
        flines = fresh.split("\n")
        for name in BLOCKS:
            a, f = _blocks(lines, name), _blocks(flines, name)
            if a != [(-1, -1)] and [lines[x:y] for x, y in a] != [flines[x:y] for x, y in f]:
                add("FAIL", "blocks", "the %s block is stale: `python3 tools/psxd_publish.py render README.md "
                    "--write` regenerates it" % name)
    # the records behind the blocks
    if ctx.categories is None:
        add("FAIL" if release else "INFO", "categories", "no %s yet: the progress table says \"not published\" "
            "until the first report (Phase 9)" % CATEGORIES_REL)
    for e in ctx.categories_errs:
        add("FAIL", "categories", e)
    if ctx.discs is None:
        add("FAIL" if release else "INFO", "discs", "no %s yet: the disc table waits for it" % DISCS_REL)
    for e in ctx.discs_errs:
        add("FAIL", "discs", e)
    known = recorded_hashes(ctx.repo)
    for i in range(desc[0], desc[1]):
        for h in SHA1_RE.findall(lines[i]):
            if h not in known:
                add("FAIL", "disc", "line %d: SHA-1 %s is in no tracked record (config/medium.sha1, "
                    "config/check.*.sha, manifest/*.jsonl, extracted/*/manifest.jsonl)" % (i + 1, h))
    # decomp.dev URLs: this repository, a real measure, a registered category
    ids = {r["id"] for r in active(ctx.categories)}
    for i, l in enumerate(lines):
        for m in DD_URL.finditer(l):
            owner, name, svg, query = m[1], m[2], m[3], m[4] or ""
            if not svg and owner.lower() in DD_RESERVED:
                continue
            if not ctx.slug:
                add("FAIL", "badges", "line %d: a decomp.dev URL, but no GitHub `origin` remote to check it "
                    "against" % (i + 1))
            elif ("%s/%s" % (owner, name)).lower() != ctx.slug.lower():
                add("FAIL", "badges", "line %d: decomp.dev/%s/%s is not this repository (%s)" % (
                    i + 1, owner, name, ctx.slug))
            q = urllib.parse.parse_qs(query.replace("&amp;", "&"))
            for meas in q.get("measure", []):
                if meas not in BADGE_MEASURES:
                    add("FAIL", "badges", "line %d: measure=%s is not one decomp.dev renders (\"Unknown measure\")"
                        % (i + 1, meas))
            for cat in q.get("category", []):
                if cat not in ids:
                    add("FAIL", "badges", "line %d: category=%s is not an active id in %s; decomp.dev would "
                        "silently show the whole report" % (i + 1, cat, CATEGORIES_REL))
    # Repository layout: every path is real (tracked, or git-ignored like the folder for your own dump)
    if "Repository layout" in spans:
        a, b = spans["Repository layout"]
        rows = [l for l in lines[a:b] if l.lstrip().startswith("|")]
        if len(rows) < 3 or "path" not in rows[0].lower():
            add("FAIL", "layout", "## Repository layout needs a `| Path | Contents |` table")
        for l in rows[2:]:
            cell = l.strip().strip("|").split("|")[0]
            paths = re.findall(r"`([^`]+)`", cell)
            if not paths:
                add("FAIL", "layout", "layout row %r: the path goes in backticks" % l.strip()[:40])
            for rel in paths:
                _path_finding(add, "layout", "layout row", ctx.repo, rel)
    # Building: every `make X` in a command block or a code span is a real target
    if "Building the decompilation" in spans:
        a, b = spans["Building the decompilation"]
        fenced = [i for i in range(a, b) if i in code]
        if release and not fenced:
            add("FAIL", "build", "## Building the decompilation has no command block")
        targets = makefile_targets(ctx.repo)
        cmds = [(i, lines[i]) for i in fenced] + [(i, m[1]) for i in range(a, b) if i not in code
                                                   for m in re.finditer(r"`([^`]*\bmake\b[^`]*)`", lines[i])]
        for i, cmd in cmds:
            for t in make_targets_named(cmd):
                if targets is None:
                    add("FAIL", "build", "line %d: `make %s`, but the repository has no Makefile" % (i + 1, t))
                elif t not in targets:
                    add("FAIL", "build", "line %d: `make %s`: no such Makefile target" % (i + 1, t))
    # relative links resolve
    for i, t in _link_targets(lines, code):
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", t, re.I):
            continue
        path = urllib.parse.unquote(t.split("#", 1)[0].split("?", 1)[0])
        if path:
            _path_finding(add, "links", "line %d" % (i + 1), ctx.repo, path)
    todos = [i + 1 for i, l in enumerate(lines) if TODO_PHASE in l]
    if todos:
        add("FAIL" if release else "WARN", "todo", "%d `%s…)` line(s) (%s): replace each with the real text or an "
            "honest \"not yet\" line" % (len(todos), TODO_PHASE, ", ".join(map(str, todos[:6]))))
    return out


def lint_summary(found: list[tuple[str, str, str]]) -> tuple[str, str]:
    """(worst level, one line): for the doctor row."""
    fails = [f for f in found if f[0] == "FAIL"]
    warns = [f for f in found if f[0] == "WARN"]
    if fails:
        return "FAIL", "%d lint failure(s): %s: %s" % (len(fails), fails[0][1], fails[0][2])
    if warns:
        return "WARN", "%s: %s" % (warns[0][1], warns[0][2])
    return "OK", "on the README standard"


# ---- report.json: schema, arithmetic, categories ----------------------------------------------------------------

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


def _get(d: dict, name: str, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(name, d.get(_camel(name), default))


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


def unit_categories(u) -> list[str]:
    c = _get(_get(u, "metadata", {}), "progress_categories", [])
    return [x for x in c if isinstance(x, str)] if isinstance(c, list) else []


def _unit_numbers(u) -> dict:
    m = _get(u, "measures", {}) or {}
    out = {}
    for k in SUMMED + ["fuzzy_match_percent", "complete_units"]:
        v = _get(m, k, 0)
        try:
            out[k] = float(v) if k == "fuzzy_match_percent" else int(v)
        except (TypeError, ValueError):
            out[k] = 0
    return out


def _complete(u) -> bool:
    return _get(_get(u, "metadata", {}), "complete") is True or _unit_numbers(u)["complete_units"] >= 1


def aggregate(units: list) -> dict:
    """The Measures of a set of units, as objdiff computes a category (proto3 JSON form): sums, the code-weighted
    fuzzy match, ratios (100 when the total is 0), total_units and complete_units."""
    nums = [_unit_numbers(u) for u in units]
    s = {k: sum(x[k] for x in nums) for k in SUMMED}
    pct = lambda a, b: 100.0 * a / b if b else 100.0  # noqa: E731
    fuzzy = sum(x["fuzzy_match_percent"] * x["total_code"] for x in nums) / s["total_code"] if s["total_code"] \
        else 100.0
    m = {"fuzzy_match_percent": fuzzy}
    for k in SUMMED:
        m[k] = str(s[k]) if MEASURES[k] == U64 else s[k]
    for matched, total, p in RATIOS:
        m[p] = pct(s[matched], s[total])
    m["total_units"] = len(units)
    m["complete_units"] = sum(_complete(u) for u in units)
    return {k: m[k] for k in MEASURES}


def _compare(got: dict, want: dict, where: str, errs: list[str]):
    for k in SUMMED + ["total_units", "complete_units"]:
        w = int(want[k])
        if got.get(k, 0) != w:
            errs.append("%s.%s %d != %d, the sum over its units" % (where, k, got.get(k, 0), w))
    if abs(got.get("fuzzy_match_percent", 0.0) - want["fuzzy_match_percent"]) > PCT_TOL and \
            not (int(want["total_code"]) == 0 and got.get("fuzzy_match_percent", 0.0) in (0.0, 100.0)):
        errs.append("%s.fuzzy_match_percent %.4f is not its units' code-weighted mean %.4f" % (
            where, got.get("fuzzy_match_percent", 0.0), want["fuzzy_match_percent"]))


def validate(report, artifact: str | None = None, version: str | None = None, categories: list[dict] | None = None,
             exe: str | None = None) -> list[str]:
    errs: list[str] = []
    if artifact is not None:
        if not ARTIFACT.match(artifact):
            errs.append("artifact %r: decomp.dev reads an artifact named <version>_report" % artifact)
        elif version is not None and artifact != "%s_report" % version:
            errs.append("artifact %r: the version %r wants %s_report" % (artifact, version, version))
        if exe is not None and artifact != "%s_report" % exe:
            errs.append("artifact %r: the version is the executable's file name: %s_report" % (artifact, exe))
    elif exe is not None:
        errs.append("--exe %s needs --artifact (the upload's name, %s_report)" % (exe, exe))
    top = _walk(report, "Report", "report", errs)
    if top.get("version") != REPORT_VERSION:
        errs.append("report.version %r: emit %d (decomp.dev reads a v2 report's category measures as written and "
                    "refuses unknown versions)" % (_get(report, "version"), REPORT_VERSION))
    _measures(top.get("measures", {}), "report.measures", errs)
    units = _get(report, "units", []) if isinstance(report, dict) else []
    units = units if isinstance(units, list) else []
    for i, u in enumerate(units):
        _measures(_walk(u, "ReportUnit", "units[%d]" % i, []).get("measures", {}), "units[%d].measures" % i, errs)
    if units:
        _compare(top.get("measures", {}), aggregate(units), "report.measures", errs)
    cats = _get(report, "categories", []) if isinstance(report, dict) else []
    cats = [c for c in cats if isinstance(c, dict)] if isinstance(cats, list) else []
    declared = [_get(c, "id", "") for c in cats]
    for i, c in enumerate(cats):
        cid = declared[i]
        where = "categories[%d] (%s)" % (i, cid)
        if declared.count(cid) > 1 and declared.index(cid) == i:
            errs.append("%s: id declared %d times" % (where, declared.count(cid)))
        if "." in cid and cid.split(".", 1)[0] not in declared:
            errs.append("%s: its parent %r is not a category (decomp.dev nests `parent.child` under parent)"
                        % (where, cid.split(".", 1)[0]))
        cm = _walk(c, "ReportCategory", where, []).get("measures", {})
        _measures(cm, where + ".measures", errs)
        _compare(cm, aggregate([u for u in units if cid in unit_categories(u)]), where + ".measures", errs)
    for i, u in enumerate(units):
        cs = unit_categories(u)
        for cid in cs:
            if cid not in declared:
                errs.append("units[%d] (%s): category %r is not in report.categories" % (i, _get(u, "name"), cid))
            if "." in cid and cid.split(".", 1)[0] not in cs:
                errs.append("units[%d] (%s): lists %r but not its parent %r" % (i, _get(u, "name"), cid,
                                                                             cid.split(".", 1)[0]))
    if categories is not None:
        reg = {r["id"]: r for r in active(categories)}
        for cid in declared:
            if cid not in reg:
                errs.append("category %r is not an active id of %s" % (cid, CATEGORIES_REL))
            elif _get(cats[declared.index(cid)], "name") != reg[cid]["name"]:
                errs.append("category %r: name %r, %s says %r" % (cid, _get(cats[declared.index(cid)], "name"),
                                                                  CATEGORIES_REL, reg[cid]["name"]))
        for cid in reg:
            if cid not in declared:
                errs.append("active category %r of %s is missing from the report" % (cid, CATEGORIES_REL))
    return errs


def categorize(report: dict, categories: list[dict]) -> tuple[dict, list[str]]:
    """The report with version 2, report.measures and one category per active id, each computed from the units that
    list it. Refuses an unregistered or retired id, a child without its parent, and an active id no unit lists."""
    errs = []
    reg = {r["id"]: r for r in categories}
    units = _get(report, "units", []) or []
    used: set[str] = set()
    for i, u in enumerate(units):
        cs = unit_categories(u)
        used |= set(cs)
        for cid in cs:
            if cid not in reg:
                errs.append("units[%d] (%s): category %r is not registered in %s" % (i, _get(u, "name"), cid,
                                                                                 CATEGORIES_REL))
            elif reg[cid]["status"] != "active":
                errs.append("units[%d] (%s): category %r is retired" % (i, _get(u, "name"), cid))
            if "." in cid and cid.split(".", 1)[0] not in cs:
                errs.append("units[%d] (%s): lists %r but not its parent %r" % (i, _get(u, "name"), cid,
                                                                             cid.split(".", 1)[0]))
        kinds = [k for k in KINDS if k in cs]
        if len(kinds) != 1:
            errs.append("units[%d] (%s): lists %s; every unit is game or sdk, exactly one" % (
                i, _get(u, "name"), " and ".join(kinds) or "neither game nor sdk"))
        kids = [c for c in cs if "." in c]
        for parent in {c.split(".", 1)[0] for c in kids}:
            mine = [c for c in kids if c.startswith(parent + ".")]
            if len(mine) > 1:
                errs.append("units[%d] (%s): one unit is in one overlay: %s" % (i, _get(u, "name"), ", ".join(mine)))
    for r in active(categories):
        if r["id"] not in used:
            errs.append("active category %r: no unit lists it (retire it, or emit it)" % r["id"])
        elif not int(aggregate([u for u in units if r["id"] in unit_categories(u)])["total_code"]):
            errs.append("active category %r has no code: decomp.dev would show it 100%% matched; a file with no "
                        "code belongs to no category" % r["id"])
    out = {"measures": aggregate(units), "units": units, "version": REPORT_VERSION,
           "categories": [{"id": r["id"], "name": r["name"],
                           "measures": aggregate([u for u in units if r["id"] in unit_categories(u)])}
                          for r in active(categories)]}
    return out, errs


# ---- self-test --------------------------------------------------------------------------------------------------

SELF_TSV = ("# id\tparent\tname\tstatus — the synthetic game's categories\nid\tparent\tname\tstatus\n"
            "game\t\tGame\tactive\nsdk\t\tSDK\tactive\nmain\t\tMain executable\tactive\n"
            "ovl\t\tOVL/ overlays\tactive\novl.title\tovl\tTitle screen\tactive\novl.stage1\tovl\tStage 1\tactive\n")
SELF_DISCS = "disc\tserial\texecutable\ttrack\tsource\nDisc 1\tPSXD-00001\tPSXD_000.01\t\tdump\n"
SELF_MEDIUM = "1111111111111111111111111111111111111111  Synthetic Game (Track 1).bin\n" \
              "2222222222222222222222222222222222222222  Synthetic Game.cue\n"
SELF_CHECK = "3333333333333333333333333333333333333333  build/PSXD_000.01\n"
SELF_MAKE = ".PHONY: build check\nbuild:\n\techo build\ncheck extract: build\n\techo ok\ninclude config/*.mk\n"
SELF_README = """# synthetic-decomp

## Description

A matching decompilation of a synthetic game.

%s
<!-- psxdecomp:disc:begin -->
<!-- psxdecomp:disc:end -->

> [!IMPORTANT]
> This repository contains **no game data**: bring your own dump.

## Progress

<!-- psxdecomp:progress:begin -->
<!-- psxdecomp:progress:end -->

## Building the decompilation

```sh
make extract && make build
```

## Repository layout

| Path | Contents |
|---|---|
| `config/` | the records |
| `disks/` | your own dump (ignored by git) |

## Getting started

### Setting up

See [the setup](docs/setup.md).

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

### Reference

See the [cookbook](docs/setup.md#idioms).

## Acknowledgements

Everyone.

## License

MIT.
""" % ai_policy_block()


def _units():
    def u(name, cats, code, mcode, funcs, mfuncs, done=False):
        return {"name": name, "measures": {"fuzzy_match_percent": 100.0 * mcode / code, "total_code": str(code),
                                           "matched_code": str(mcode), "matched_code_percent": 100.0 * mcode / code,
                                           "total_functions": funcs, "matched_functions": mfuncs,
                                           "matched_functions_percent": 100.0 * mfuncs / funcs,
                                           "complete_code": str(code if done else 0),
                                           "complete_code_percent": 100.0 if done else 0.0},
                "metadata": {"complete": done, "progress_categories": cats}}
    return {"version": 1, "units": [u("main/a", ["game", "main"], 600, 500, 6, 5),
                                    u("main/libgpu", ["sdk"], 200, 200, 2, 2, done=True),
                                    u("ovl/title/a", ["game", "ovl", "ovl.title"], 300, 0, 3, 0),
                                    u("ovl/stage1/a", ["game", "ovl", "ovl.stage1"], 100, 100, 1, 1, done=True)]}


def _self_repo(td: str) -> pathlib.Path:
    repo = pathlib.Path(td).resolve()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t.invalid")
    run = lambda *a: subprocess.run(["git", "-C", str(repo)] + list(a), capture_output=True, text=True, env=env)  # noqa
    run("init", "-q")
    run("remote", "add", "origin", "https://github.com/example/synthetic-decomp.git")
    for rel, body in (("config/categories.tsv", SELF_TSV), ("config/discs.tsv", SELF_DISCS),
                      ("config/medium.sha1", SELF_MEDIUM), ("config/check.PSXD_000.01.sha", SELF_CHECK),
                      ("Makefile", SELF_MAKE), ("config/x.mk", "format:\n\techo f\n"), (".gitignore", "/disks/\n"),
                      ("docs/setup.md", "# Setup\n"), ("CONTRIBUTING.md", "# C\n"), ("README.md", SELF_README)):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")
    run("add", "-A")
    run("-c", "commit.gpgsign=false", "commit", "-qm", "synthetic")
    return repo


def self_test() -> int:
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print("  %-34s %s%s" % (name, "ok" if cond else "WRONG", "" if cond else "  " + str(detail)[:200]))
        ok &= bool(cond)

    rows, errs = parse_categories(SELF_TSV)
    check("categories good", errs == [] and len(rows) == 6, errs)
    for name, tsv, want in (
            ("categories bad id", SELF_TSV.replace("ovl.stage1\t", "ovl.Stage-1\t"), "lower-case"),
            ("categories duplicate", SELF_TSV + "main\t\tAgain\tactive\n", "declared twice"),
            ("categories no parent", SELF_TSV.replace("ovl\t\tOVL/ overlays\tactive\n", ""), "not declared"),
            ("categories parent column", SELF_TSV.replace("ovl.title\tovl", "ovl.title\tmain"), "parent column"),
            ("categories no sdk", SELF_TSV.replace("sdk\t\tSDK\tactive\n", ""), "'sdk' is required"),
            ("categories status", SELF_TSV.replace("Stage 1\tactive", "Stage 1\tgone"), "active or retired"),
            ("categories header", SELF_TSV.replace("id\tparent\tname\tstatus\n", "id\tname\n"), "header")):
        e = parse_categories(tsv)[1]
        check(name, any(want in x for x in e), e)
    # categorize -> validate; the gaps validate closes
    rep, errs = categorize(_units(), rows)
    check("categorize good", errs == [] and rep["version"] == 2 and len(rep["categories"]) == 6, errs)
    ovl = next(c for c in rep["categories"] if c["id"] == "ovl")["measures"]
    check("categorize sums", ovl["total_code"] == "400" and ovl["total_units"] == 2 and ovl["complete_units"] == 1
          and abs(ovl["fuzzy_match_percent"] - 25.0) < 1e-9, ovl)
    errs = validate(rep, "PSXD_000.01_report", "PSXD_000.01", rows, "PSXD_000.01")
    check("validate good", errs == [], errs)
    for name, mutate, want in (
            ("categorize unregistered", lambda r: r["units"][0]["metadata"]["progress_categories"].append("dbg"),
             "not registered"),
            ("categorize no parent", lambda r: r["units"][2]["metadata"]["progress_categories"].remove("ovl"),
             "not its parent"),
            ("categorize unemitted", lambda r: r["units"].pop(3), "no unit lists it"),
            ("categorize no kind", lambda r: r["units"][0]["metadata"]["progress_categories"].remove("game"),
             "neither game nor sdk"),
            ("categorize two overlays", lambda r: r["units"][2]["metadata"]["progress_categories"].append(
                "ovl.stage1"), "one unit is in one overlay"),
            ("categorize no code", lambda r: r["units"][3]["measures"].update(total_code="0", matched_code="0",
                                                                             complete_code="0"), "has no code")):
        r = _units()
        mutate(r)
        e = categorize(r, rows)[1]
        check(name, any(want in x for x in e), e)
    e = categorize(_units(), parse_categories(SELF_TSV.replace("Stage 1\tactive", "Stage 1\tretired"))[0])[1]
    check("categorize retired", any("is retired" in x for x in e), e)

    def bad(mutate):
        r = json.loads(json.dumps(rep))
        mutate(r)
        return r
    for name, r, kw, want in (
            ("validate version 1", bad(lambda r: r.update(version=1)), {}, "emit 2"),
            ("validate category sum", bad(lambda r: r["categories"][3]["measures"].update(total_code="401")), {},
             "the sum over its units"),
            ("validate total_units", bad(lambda r: r["categories"][3]["measures"].update(total_units=3)), {},
             "total_units 3 != 2"),
            ("validate unknown unit cat", bad(lambda r: r["categories"].pop(5)), {}, "not in report.categories"),
            ("validate dotted parent", bad(lambda r: r["categories"].pop(3)), {}, "parent 'ovl' is not a category"),
            ("validate artifact vs exe", rep, dict(artifact="us_report", exe="PSXD_000.01"), "executable's file name"),
            ("validate tsv name", bad(lambda r: r["categories"][2].update(name="Main")), dict(categories=rows),
             "says 'Main executable'"),
            ("validate uint64 as number", bad(lambda r: r["measures"].update(total_code=1200)), {}, "decimal string"),
            ("validate unknown field", bad(lambda r: r["units"][1].update(source="x")), {}, "unknown field"),
            ("validate 64-byte hex", bad(lambda r: r["units"][0].update(name="d_" + "a5" * 64)), {}, "byte-like")):
        e = validate(r, **kw)
        check(name, any(want in x for x in e), e)
    # render + lint on a synthetic repository
    with tempfile.TemporaryDirectory() as td:
        repo = _self_repo(td)
        ctx = Ctx(repo)
        text = render(SELF_README, ctx)
        check("render fills both blocks", "PSXD-00001" in text and "category=ovl&" not in text and
              "category=ovl)" in text and "| `sdk` |" in text and text.count("<details>") == 1 and
              "<code>ovl</code>: 2 overlays" in text and text.index("| `sdk` |") < text.index("| `ovl.title` |"),
              text[:300])
        check("render is idempotent", render(text, ctx) == text)
        named = make_targets_named("make -j 8 -C . -f Makefile build; echo done && make check|tee x  # make sure")
        check("make targets named", named == ["build", "check"], named)
        (repo / "dumps").mkdir()
        check("untracked path warns", path_state(repo, "dumps/") == "local" and
              path_state(repo, "disks/") == "ignored" and path_state(repo, "config/") == "tracked")
        found = lint(text, ctx)
        check("lint good", [f for f in found if f[0] != "INFO"] == [], found)
        check("lint stale", any("stale" in f[2] for f in lint(SELF_README, ctx)))
        for name, mutate, want, rel in (
                ("lint old disclosure", lambda t: t.replace("Everyone.", OLD_DISCLOSURE + "."), "old disclosure", 0),
                ("lint policy twice", lambda t: t.replace("Everyone.", ai_policy_block()), "2 times", 0),
                ("lint policy altered", lambda t: t.replace("always use", "sometimes use"), "differs", 0),
                ("lint no game data note", lambda t: t.replace("no game data", "nothing"), "no game data", 0),
                ("lint missing section", lambda t: t.replace("## Repository layout", "## Layout"), "missing ##", 0),
                ("lint order", lambda t: t.replace("## License\n\nMIT.\n", "").replace(
                    "## Acknowledgements", "## License\n\nMIT.\n\n## Acknowledgements"), "out of order", 0),
                ("lint unknown h2", lambda t: t.replace("## Getting started", "## Status\n\nx\n\n## Getting started"),
                 "not a section", 0),
                ("lint missing h3", lambda t: t.replace("### Reference", "### Links"), "missing ### Reference", 0),
                ("lint bad measure", lambda t: t + "\n![x](https://decomp.dev/example/synthetic-decomp.svg?"
                 "measure=percent)\n", "measure=percent", 0),
                ("lint unknown category", lambda t: t + "\n![x](https://decomp.dev/example/synthetic-decomp.svg?"
                 "category=ovl.stage9)\n", "category=ovl.stage9", 0),
                ("lint other repo", lambda t: t + "\n[p](https://decomp.dev/other/repo)\n", "not this repository", 0),
                ("lint stale block", lambda t: t.replace("| `main` | Main executable", "| `main` | Main"), "stale", 0),
                ("lint layout path", lambda t: t.replace("`config/`", "`include/`"), "include/ does not exist", 0),
                ("lint make target", lambda t: t.replace("make build", "make all"), "`make all`", 0),
                ("lint make in prose", lambda t: t.replace("## Building the decompilation\n",
                                                          "## Building the decompilation\n\nRun `make nosuch`.\n"),
                 "`make nosuch`", 0),
                ("lint second layout path", lambda t: t.replace("`config/` |", "`config/`, `mkk/` |"), "mkk", 0),
                ("lint broken link", lambda t: t.replace("docs/setup.md)", "docs/INSTALL.md)"), "INSTALL.md", 0),
                ("lint unrecorded sha1", lambda t: t.replace("A matching", "Hash " + "4" * 40 + ". A matching"),
                 "in no tracked record", 0),
                ("lint todo warns", lambda t: t.replace("Everyone.", "TODO(phase-5): x"), "TODO(phase-", 0),
                ("lint todo fails --release", lambda t: t.replace("Everyone.", "TODO(phase-5): x"), "TODO(phase-", 1)):
            got = lint(mutate(text), ctx, release=bool(rel))
            lv = "WARN" if name == "lint todo warns" else "FAIL"
            check(name, any(f[0] == lv and want in f[2] for f in got), got)
        # no categories.tsv yet: the progress block says so and the lint says INFO; --release FAILs
        (repo / CATEGORIES_REL).unlink()
        bare = Ctx(repo)
        t2 = render(text, bare)
        check("render before Phase 9", "Not published yet" in t2 and "decomp.dev/example" not in t2)
        got = lint(t2, bare)
        check("lint before Phase 9", [f[0] for f in got] == ["INFO"], got)
        check("lint --release needs the list", any(f[0] == "FAIL" and f[1] == "categories"
                                                   for f in lint(t2, bare, release=True)))
        # the freeze: an id committed once may be retired, never removed
        (repo / CATEGORIES_REL).write_text(SELF_TSV, encoding="utf-8")
        rows = load_categories(repo / CATEGORIES_REL)[0]
        check("history clean", history_errors(repo, rows) == ([], 1), history_errors(repo, rows))
        removed = parse_categories(SELF_TSV.replace("ovl.stage1\tovl\tStage 1\tactive\n", ""))[0]
        renamed = parse_categories(SELF_TSV.replace("ovl.stage1\t", "ovl.stage_one\t"))[0]
        retired = parse_categories(SELF_TSV.replace("Stage 1\tactive", "Stage 1\tretired"))[0]
        check("history removed id", any("'ovl.stage1'" in e for e in history_errors(repo, removed)[0]))
        check("history renamed id", any("'ovl.stage1'" in e for e in history_errors(repo, renamed)[0]))
        check("history retired id", history_errors(repo, retired)[0] == [])
    print("publish %s" % ("SELF-TEST OK" if ok else "SELF-TEST FAILED"))
    return 0 if ok else 1


# ---- the command line -------------------------------------------------------------------------------------------

def _ctx(a) -> tuple[Ctx, pathlib.Path]:
    readme = pathlib.Path(a.readme).resolve()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root(readme.parent)
    return Ctx(repo, a.categories, a.discs), readme


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("lint", "render"):
        p = sub.add_parser(name)
        p.add_argument("readme", nargs="?", default="README.md")
        p.add_argument("--repo", help="the repository (default: the README's git top level)")
        p.add_argument("--categories", help="default <repo>/%s" % CATEGORIES_REL)
        p.add_argument("--discs", help="default <repo>/%s" % DISCS_REL)
        p.add_argument("--release" if name == "lint" else "--write", action="store_true")
    ca = sub.add_parser("categories")
    ca.add_argument("tsv", nargs="?", default=CATEGORIES_REL)
    ca.add_argument("--repo", default=".")
    ca.add_argument("--history", action="store_true")
    cz = sub.add_parser("categorize")
    cz.add_argument("report")
    cz.add_argument("--categories", required=True)
    cz.add_argument("-o", "--output")
    va = sub.add_parser("validate")
    va.add_argument("report")
    va.add_argument("--categories")
    va.add_argument("--artifact")
    va.add_argument("--version")
    va.add_argument("--exe")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd in ("lint", "render"):
        ctx, readme = _ctx(a)
        text = _read(readme)
        if text is None:
            print("README FAIL %s: not readable" % readme)
            return 1
        if a.cmd == "render":
            try:
                new = render(text, ctx)
            except RenderError as e:
                print("RENDER FAIL %s" % e)
                return 1
            if a.write and new != text:
                readme.write_text(new, encoding="utf-8")
            print("RENDER %s %s" % ("unchanged" if new == text else ("written" if a.write else "stale (--write)"),
                                   readme))
            return 0
        found = lint(text, ctx, a.release)
        for lv, ck, d in found:
            print("README %-4s %s: %s" % (lv, ck, d))
        fails, warns = sum(f[0] == "FAIL" for f in found), sum(f[0] == "WARN" for f in found)
        print("README LINT %s (%d warn)%s" % ("OK" if not fails else "FAIL %d" % fails, warns,
                                             " --release" if a.release else ""))
        return 1 if fails else 0
    if a.cmd == "categories":
        repo = pathlib.Path(a.repo).resolve()
        path = pathlib.Path(a.tsv) if os.path.isabs(a.tsv) else repo / a.tsv
        rows, errs = load_categories(path)
        if rows is None:
            print("CATEGORIES none: no %s (the list starts with the first published report)" % a.tsv)
            return 0
        n = 0
        if a.history:
            more, n = history_errors(repo, rows, os.path.relpath(path, repo))
            errs += more
        for e in errs:
            print("CATEGORIES ERROR %s" % e)
        print("CATEGORIES %s %d ids (%d active)%s" % ("OK" if not errs else "FAIL", len(rows), len(active(rows)),
                                                     "; history: %d commit(s)" % n if a.history else ""))
        return 1 if errs else 0
    if a.cmd == "categorize":
        rows, errs = load_categories(a.categories)
        if rows is None or errs:
            print("CATEGORIZE ERROR %s" % ("; ".join(errs) if errs else "no %s" % a.categories))
            return 1
        out, errs = categorize(json.loads(_read(a.report) or "{}"), rows)
        for e in errs:
            print("CATEGORIZE ERROR %s" % e)
        if errs:
            print("CATEGORIZE FAIL (%d error%s); nothing written" % (len(errs), "" if len(errs) == 1 else "s"))
            return 1
        body = json.dumps(out, indent=1) + "\n"
        if a.output:
            pathlib.Path(a.output).write_text(body, encoding="utf-8")
        else:
            sys.stdout.write(body)
        print("CATEGORIZE OK %d units, %d categories%s" % (len(out["units"]), len(out["categories"]),
                                                          " -> %s" % a.output if a.output else ""),
              file=sys.stderr if not a.output else sys.stdout)
        return 0
    if a.cmd == "validate":
        cats = None
        if a.categories:
            cats, cerrs = load_categories(a.categories)
            if cats is None or cerrs:
                print("REPORT ERROR %s" % ("; ".join(cerrs) if cerrs else "no %s" % a.categories))
                return 1
        errs = validate(json.loads(_read(a.report) or "null"), a.artifact, a.version, cats, a.exe)
        for e in errs:
            print("REPORT ERROR %s" % e)
        print("REPORT %s (%d error%s)" % ("OK" if not errs else "FAIL", len(errs), "" if len(errs) == 1 else "s"))
        return 1 if errs else 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
