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
    publish.py check-public [DIR]         the public tree DIR (default: this repository) against the list:
                                          FAIL on an unlisted or agent-only file; WARN on an entry matching nothing
    publish.py release --summary TEXT [--repo DEV] [--rev REV] [--ack-new] [--dry-run] [--push]
                                          DEV's listed files at REV -> branch release/<sha10> in the public cache, one
                                          reproducible commit (Release-Of/-Tree/-Base trailers); developer only
    publish.py ship --summary TEXT [--repo DEV] [--rev REV] [--ack-new] [--dry-run] [--no-wait] [--timeout MIN]
                    [--replace] [--merge-reviewed]
                                          a release end to end: -dev's CI, the gate, the byte build and the game-free
                                          CI of the projection, the PR, its checks, the merge, public main; resumable;
                                          developer only (--dry-run stops before the push)
    publish.py import [--repo DEV] [--accept-governance] [--skip SHA ...]
                                          public contributor commits not yet in DEV -> one import commit each, written
                                          to the cache only (refs/psxdecomp/import); touches no DEV ref or worktree
    publish.py land [TIP] [--repo DEV]    fast-forward DEV to the import chain TIP when the gate is idle; developer only
    publish.py settings [--apply] [--repo DEV]
                                          the public repository's settings against the standard; --apply fixes
    publish.py verify-pr N [--merge] [--repo DEV]
                                          a public PR's required checks, their provenance and its claims; --merge squashes
    publish.py ci-log FILE                the last 60 lines of a build log that carry no asm, hex dump or instruction
    publish.py list [--draft] [--rev REV] [--repo DEV]
                                          the files the list publishes at REV; --draft: a first list (the tracked files
                                          outside the deny set, folded to `dir/`), and what it would leave behind
    publish.py ci-sim [--workflow NAME] [--projection] [--rev REV] [--private DIR] [--image REF] [--repo DEV]
                                          the workflow's `run:` steps as written, on a fresh clone of REV or on its
                                          release projection: in a clean ubuntu:24.04 container, or on this machine
                                          when the steps start containers themselves (build.yml; --private: a local
                                          <game>-private, --image: the toolchain image in [public].image's place)
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
import contextlib
import copy
import fnmatch
import functools
import glob
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
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

# ---- the public paths (config/public-paths.txt: what a dev repository publishes to its public repository) ----------
PUBLIC_PATHS_REL = "config/public-paths.txt"     # per line: `dir/` prefix, else an fnmatch glob (`*` crosses `/`)
RELEASE_TRAILERS = ("Release-Of", "Release-Tree", "Release-Base")    # in a release commit's body (a squash keeps them)
IMPORT_TRAILER = "Imported-From"                 # in the dev commit that takes a public commit: the public sha
CONFIG_REL = "config/psxdecomp.toml"             # its [public] table turns split mode on
PA3_REL = ".claude/pa3-managed.json"             # `files`: the paths PA3 manages; they never go public
GOVERNANCE_DEFAULT = ("config/public-paths.txt", "config/psxdecomp.toml", ".github/", "Makefile", "*.mk", "tools/",
                      ".gitattributes", ".gitignore", "CODEOWNERS", ".github/CODEOWNERS", "LICENSE", "SECURITY.md",
                      "CONTRIBUTING.md")
ACTIONS_APP = 15368                              # GitHub Actions' app id: a required check must come from Actions
TRUSTED_WORKFLOW = ".github/workflows/build.yml"
PUB_REF = "refs/psxdecomp/public-main"
# Agent working files never reach the public repository, even when the list names them (a prefix ends in `/`).
AGENT_DENY = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "HOW_WE_WORK.md", "PROJECT_CONTEXT.md", "GENERATION_PLAN.md",
              ".claude/", ".claude-state/", ".mcp.json", ".run/", "phase-ends/", "campaign/", "rules/", "templates/",
              "drafts/", "repro/", "docs/ops/", "docs/retired/", "tools/commit_task.sh", "tools/wave.py",
              "tools/card.py", "tools/task_log.py")

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


GIT_LOCATION_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")


def own_git_env() -> None:
    """Drop git's repository-location variables from this process. Every git call here names its repository with -C,
    but git exports GIT_DIR to a hook run in a linked worktree, and an inherited GIT_DIR wins over -C: the push gate's
    `git init` and `git add -A -f` in a temporary tree would rewrite dev's index and mark its repository bare."""
    for k in GIT_LOCATION_ENV:
        os.environ.pop(k, None)


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)


def origin_slug(repo) -> str | None:
    """OWNER/REPO of `git remote get-url origin` on GitHub, or None."""
    r = _git(repo, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return "%s/%s" % (m[1], m[2]) if m else None


def readme_slug(repo) -> str | None:
    """The slug a README names: [public].repo in split mode (dev's origin is the private `-dev`), else origin's."""
    try:
        cfg = load_public(repo)
    except Fail:
        cfg = None
    return cfg["repo"] if cfg else origin_slug(repo)


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
        self.slug = readme_slug(self.repo)


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


# ---- the public tree: check-public, then split mode v2: release (dev -> public cache), import, land, settings -------

class Fail(Exception):
    """A refusal with its reason: the command prints `<TAG> FAIL <reason>` and exits 1."""


def _cmd(tag: str):
    def deco(fn):
        @functools.wraps(fn)
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Fail as e:
                _line(tag, "FAIL", str(e))
                return 1
        return run
    return deco


def _dev_only(what: str):
    if os.environ.get("CLAUDECODE"):
        raise Fail("%s is for the developer, not an agent session (CLAUDECODE is set)" % what)


def parse_public_paths(text: str) -> list[str]:
    """The entries of config/public-paths.txt: `#` comments and blank lines skipped."""
    return [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def public_match(entry: str, path: str) -> bool:
    """One entry against a repo-relative path: a `dir/` entry is a prefix, any other is an fnmatch glob."""
    return path.startswith(entry) if entry.endswith("/") else fnmatch.fnmatchcase(path, entry)


@functools.lru_cache(maxsize=8)
def _matcher(entries: tuple):
    prefixes = tuple(e for e in entries if e.endswith("/"))
    globs = [fnmatch.translate(e) for e in entries if not e.endswith("/")]
    return prefixes, re.compile("|".join(globs)) if globs else None


def is_listed(entries, path: str) -> bool:
    prefixes, rx = _matcher(tuple(entries))
    return bool(prefixes and path.startswith(prefixes)) or bool(rx and rx.match(path))


is_denied = is_listed                                  # the deny set uses the list's syntax


def _git_raw(repo, *args, inp: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args), input=inp, capture_output=True)


def _must(repo, *args, inp=None, env=None) -> str:
    r = subprocess.run(["git", "-C", str(repo)] + list(args), input=inp, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise Fail("git %s: %s" % (" ".join(args[:2]), (r.stderr or r.stdout).strip()[:300]))
    return r.stdout.strip()


def tree_entries(repo, rev: str) -> dict[str, tuple[str, str]] | None:
    """{path: (mode, blob sha)} of every file in rev, or None when git cannot read it."""
    r = _git(repo, "ls-tree", "-r", "-z", rev)
    if r.returncode != 0:
        return None
    out = {}
    for rec in r.stdout.split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            mode, _, sha = meta.split()
            out[path] = (mode, sha)
    return out


def read_blobs(repo, shas: list[str]) -> dict[str, bytes]:
    """{sha: content} through one `git cat-file --batch`."""
    r = _git_raw(repo, "cat-file", "--batch", inp=("\n".join(shas) + "\n").encode() if shas else b"")
    out, buf, pos = {}, r.stdout, 0
    for sha in shas:
        end = buf.index(b"\n", pos)
        size = int(buf[pos:end].split()[2])
        out[sha] = buf[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    return out


def _line(tag: str, level: str, detail: str):
    print("%s %-4s %s" % (tag, level, detail))


# ---- [public] in config/psxdecomp.toml, the deny set, governance -------------------------------------------------

HEX40 = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_STR = ("repo", "url", "dev_branch", "private_repo", "private_rev", "image", "assisted_by")
PUBLIC_LIST = ("deny", "governance", "checks", "land_check", "audit")


def load_public(repo, rev: str | None = None) -> dict | None:
    """The [public] table (defaults filled) from the worktree, or from `git show rev:` when rev is given; None when
    split mode is off. A malformed table raises Fail."""
    if rev:
        r = _git(repo, "show", "%s:%s" % (rev, CONFIG_REL))
        text = r.stdout if r.returncode == 0 else None
    else:
        text = _read(pathlib.Path(repo) / CONFIG_REL)
    if text is None:
        return None
    try:
        t = tomllib.loads(text).get("public")
    except tomllib.TOMLDecodeError as e:
        raise Fail("%s: %s" % (CONFIG_REL, e))
    if t is None:
        return None
    if not isinstance(t, dict):
        raise Fail("%s: [public] must be a table" % CONFIG_REL)
    cfg = {"url": "", "dev_branch": "main", "private_repo": "", "private_rev": "", "image": "", "assisted_by": "",
           "keyed": {}}
    cfg.update({k: [] for k in PUBLIC_LIST})
    bad = []
    for k, v in t.items():
        if k in PUBLIC_STR and isinstance(v, str):
            cfg[k] = v
        elif k in PUBLIC_LIST and isinstance(v, list) and all(isinstance(x, str) for x in v):
            cfg[k] = v
        elif k == "keyed" and isinstance(v, dict):
            cfg[k] = v
            bad += ["keyed.%s: the number of key columns, an integer >= 1" % p for p, n in v.items()
                    if type(n) is not int or n < 1]
        else:
            bad.append("%s: unknown key or wrong type" % k)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", cfg.get("repo", "")):
        bad.append("repo: required, OWNER/REPO")
    if cfg["private_rev"] and not HEX40.match(cfg["private_rev"]):
        bad.append("private_rev: 40 hex")
    if cfg["image"] and not re.search(r"@sha256:[0-9a-f]{64}$", cfg["image"]):
        bad.append("image: pinned by digest (@sha256:<64 hex>)")
    if cfg["assisted_by"] != cfg["assisted_by"].strip() or not cfg["assisted_by"].isprintable():
        bad.append("assisted_by: one line, no surrounding spaces (e.g. \"Claude Code (Opus 5.5)\")")
    if bad:
        raise Fail("%s [public]: %s" % (CONFIG_REL, "; ".join(bad)))
    cfg["url"] = cfg["url"] or "https://github.com/%s.git" % cfg["repo"]
    return cfg


def _pa3_files(text) -> list[str]:
    try:
        files = json.loads(text or "{}").get("files", {})
    except (ValueError, AttributeError):
        return []
    return list(files) if isinstance(files, dict) else []


def deny_set(pa3_text, cfg) -> tuple:
    return tuple(AGENT_DENY) + tuple(_pa3_files(pa3_text)) + tuple((cfg or {}).get("deny", ()))


def deny_entries(repo, rev: str) -> tuple:
    """AGENT_DENY, every path PA3 manages at rev and [public].deny at rev."""
    r = _git(repo, "show", "%s:%s" % (rev, PA3_REL))
    try:
        cfg = load_public(repo, rev)
    except Fail:
        cfg = None
    return deny_set(r.stdout if r.returncode == 0 else None, cfg)


def governance(cfg) -> tuple:
    return tuple((cfg or {}).get("governance") or GOVERNANCE_DEFAULT)


def check_paths(paths, entries, deny) -> list[tuple[str, str]]:
    out = []
    for p in paths:
        if is_denied(deny, p):
            out.append(("FAIL", "%s: never public (agent file, PA3-managed or [public].deny), even when %s lists it"
                        % (p, PUBLIC_PATHS_REL)))
        elif not is_listed(entries, p):
            out.append(("FAIL", "%s: tracked but matched by no entry of %s (default deny)" % (p, PUBLIC_PATHS_REL)))
    for e in entries:
        if not any(public_match(e, p) for p in paths):
            out.append(("WARN", "%s: entry %r matches no tracked file" % (PUBLIC_PATHS_REL, e)))
    return out


def check_public(repo, deny=None) -> list[tuple[str, str]]:
    """[(FAIL|WARN, detail)] for a public tree: every tracked file is listed and none is denied (the deny set is read
    from the tree's own .claude/pa3-managed.json and config/psxdecomp.toml unless given)."""
    repo = pathlib.Path(repo)
    text = _read(repo / PUBLIC_PATHS_REL)
    if text is None:
        return [("FAIL", "%s: missing (default deny: nothing is public without it)" % PUBLIC_PATHS_REL)]
    r = _git(repo, "ls-files", "-z")
    if r.returncode != 0:
        return [("FAIL", "%s: not a git repository" % repo)]
    if deny is None:
        try:
            cfg = load_public(repo)
        except Fail:
            cfg = None
        deny = deny_set(_read(repo / PA3_REL), cfg)
    return check_paths([p for p in r.stdout.split("\0") if p], parse_public_paths(text), deny)


def cmd_check_public(directory) -> int:
    repo = repo_root(directory)
    found = check_public(repo)
    for lv, d in found:
        _line("PUBLIC", lv, d)
    fails = sum(f[0] == "FAIL" for f in found)
    n = len([p for p in _git(repo, "ls-files", "-z").stdout.split("\0") if p])
    print("PUBLIC CHECK %s (%d file(s), %d warn)" % ("OK" if not fails else "FAIL %d" % fails, n,
                                                    sum(f[0] == "WARN" for f in found)))
    return 1 if fails else 0


# ---- the public cache: a bare repo that borrows dev's objects; nothing is ever checked out -----------------------

def public_cache(dev) -> pathlib.Path:
    """<git-common-dir>/psxdecomp/public.git, created on first use, with dev's object store as an alternate."""
    cache = pathlib.Path(_must(dev, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "psxdecomp" / "public.git"
    if not cache.is_dir():
        cache.parent.mkdir(parents=True, exist_ok=True)
        _must(cache.parent, "init", "--bare", "-q", str(cache))
    objs = _must(dev, "rev-parse", "--path-format=absolute", "--git-path", "objects")
    alt = cache / "objects" / "info" / "alternates"
    alt.parent.mkdir(parents=True, exist_ok=True)
    if _read(alt) != objs + "\n":
        alt.write_text(objs + "\n", encoding="utf-8")
    return cache


def fetch_public(cache, url: str) -> str | None:
    """Public main into the cache (PUB_REF); its sha, or None while the public repository has no main."""
    ls = _git(cache, "ls-remote", "--heads", url, "refs/heads/main")
    if ls.returncode != 0:
        raise Fail("cannot read %s (create the empty public repository first): %s" % (url, ls.stderr.strip()[:200]))
    if not ls.stdout.strip():
        _git(cache, "update-ref", "-d", PUB_REF)
        return None
    _must(cache, "fetch", "-q", "--no-tags", url, "+refs/heads/main:" + PUB_REF)
    return _must(cache, "rev-parse", PUB_REF)


def write_tree(cache, entries: dict) -> str:
    """The tree of {path: (mode, blob)} written into the cache through a temporary index (never the cache's own)."""
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(td, "index"))
        _must(cache, "read-tree", "--empty", env=env)
        if entries:
            info = "".join("%s %s\t%s\0" % (m, s, p) for p, (m, s) in sorted(entries.items()))
            _must(cache, "update-index", "-z", "--index-info", inp=info, env=env)
        return _must(cache, "write-tree", env=env)


def trailers(repo, rev: str, key: str) -> list[str]:
    r = _git(repo, "log", "-1", "--format=%(trailers:key=" + key + ",valueonly)", rev)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def imported(repo, rev: str) -> set[str]:
    r = _git(repo, "log", "--format=%(trailers:key=" + IMPORT_TRAILER + ",valueonly)", rev)
    return {l.strip() for l in r.stdout.splitlines() if l.strip()}


def _dev_list(repo, rev: str) -> tuple[list[str] | None, str]:
    r = _git(repo, "show", "%s:%s" % (rev, PUBLIC_PATHS_REL))
    return (parse_public_paths(r.stdout) if r.returncode == 0 else None), r.stderr.strip()


def projection(cache, dev, rev: str):
    """(tree sha, {path: (mode, blob)}, problems): dev rev's listed, not denied files, written into the cache."""
    lst, _ = _dev_list(dev, rev)
    deny = deny_entries(dev, rev)
    want, probs = {}, []
    if lst is None:
        probs.append("%s: missing at %s" % (PUBLIC_PATHS_REL, rev[:10]))
    for p, (mode, sha) in sorted((tree_entries(dev, rev) or {}).items()):
        if not is_listed(lst or [], p):
            continue
        if is_denied(deny, p):
            probs.append("%s: listed but never public (agent file, PA3-managed or [public].deny)" % p)
        elif mode in ("120000", "160000"):
            probs.append("%s: a %s is listed (only regular files go public)" % (p, "symlink" if mode == "120000"
                                                                              else "gitlink"))
        else:
            want[p] = (mode, sha)
    return write_tree(cache, want), want, probs


_RELEASE_TREES: dict[tuple[str, str, str], str] = {}     # (cache, dev, Release-Of) -> its projection: a commit is fixed


def history(cache, dev, main) -> tuple[list[tuple[str, str, str]], list[str]]:
    """(releases [(public sha, Release-Of, Release-Tree)], contributor commits) of public main's first-parent
    history, oldest first. A release has the `Release: ` subject, the Of and Tree trailers, a Tree that is the
    projection of Of (or, when a purge removed Of from dev, the commit's own tree), and an Of not used before.
    Commits before the first release are ignored; every other later commit is a contributor's."""
    rels, contribs, used = [], [], set()
    if not main:
        return rels, contribs
    fmt = "%H%x1f%s%x1f%(trailers:key=Release-Of,valueonly)%x1f%(trailers:key=Release-Tree,valueonly)%x1e"
    log = _git(cache, "log", "--first-parent", "--reverse", "--format=" + fmt, main)    # not _must: strip() eats \x1f
    if log.returncode != 0:
        raise Fail("git log %s: %s" % (main[:10], log.stderr.strip()[:200]))
    for rec in log.stdout.split("\x1e"):
        if not rec.strip():
            continue
        c, subj, of, tree = [x.strip() for x in rec.lstrip("\n").split("\x1f")]
        ok = subj.startswith("Release: ") and HEX40.match(of) and HEX40.match(tree) and of not in used
        if ok:
            if _git(dev, "cat-file", "-e", of + "^{commit}").returncode == 0:
                key = (str(cache), str(dev), of)
                if key not in _RELEASE_TREES:
                    _RELEASE_TREES[key] = projection(cache, dev, of)[0]
                ok = _RELEASE_TREES[key] == tree
            else:
                ok = _must(cache, "rev-parse", c + "^{tree}") == tree
        if ok:
            rels.append((c, of, tree))
            used.add(of)
        elif rels:
            contribs.append(c)
    return rels, contribs


def releases(cache, dev, main) -> list[tuple[str, str, str]]:
    return history(cache, dev, main)[0]


def release_body(summary, of, tree, base, assisted=None) -> str:
    """The summary, then one trailer block: `Assisted-by:` (the Linux kernel's model: named when set, never
    required) and the three `Release-*` trailers last."""
    tag = "Assisted-by: %s\n" % assisted if assisted else ""
    return "%s\n\n%sRelease-Of: %s\nRelease-Tree: %s\nRelease-Base: %s\n" % (summary, tag, of, tree, base or "none")


def gh(args, inp=None) -> subprocess.CompletedProcess:
    """Every `gh` call goes through here (the self-test replaces it)."""
    try:
        return subprocess.run(["gh"] + list(args), input=inp, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(list(args), 127, "", "gh is not installed")


def _split(repo):
    """(dev root, [public] config, cache, public main sha) with the cache fetched."""
    dev = repo_root(repo)
    cfg = load_public(dev)
    if cfg is None:
        raise Fail("split mode is off: no [public] in %s" % CONFIG_REL)
    cache = public_cache(dev)
    main = fetch_public(cache, cfg["url"])
    if main and _git(dev, "merge-base", "--is-ancestor", main, "refs/heads/" + cfg["dev_branch"]).returncode == 0:
        raise Fail("%s main (%s) is in dev's own history: the URL reaches dev, not the public repository (after the "
                   "rename, the old URL redirects to -dev until the new public repository exists)" % (cfg["url"], main[:10]))
    return dev, cfg, cache, main


def _identity(dev) -> tuple[str, str]:
    n, e = (_git(dev, "config", k).stdout.strip() for k in ("user.name", "user.email"))
    if not (n and e):
        raise Fail("git config user.name / user.email are not set in %s" % dev)
    return n, e


def _subject(repo, rev: str) -> str:
    return _git(repo, "log", "-1", "--format=%s", rev).stdout.strip()


def _export(cache, tree: str, dest) -> None:
    r = _git_raw(cache, "archive", "--format=tar", tree)
    if r.returncode == 0:
        r = subprocess.run(["tar", "-x", "-C", str(dest)], input=r.stdout, capture_output=True)
    if r.returncode != 0:
        raise Fail("cannot export tree %s: %s" % (tree[:10], r.stderr.decode().strip()[:200]))


def _tail(r: subprocess.CompletedProcess, n: int = 20) -> str:
    return "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-n:])


def gate_checks(cache, dev, cfg, tree: str, want: dict, rev: str) -> dict[str, list[str]]:
    """The release gate on an export of the projection, by kind: `paths` (check-public), `readme` (the release lint),
    `audit` (the game's audit failed) and `noaudit` (nothing audits the tree). Writes no ref."""
    out = {"paths": [], "readme": [], "audit": [], "noaudit": []}
    lst = _dev_list(cache, tree)[0] or []
    out["paths"] = [d for lv, d in check_paths(sorted(want), lst, deny_entries(dev, rev)) if lv == "FAIL"]
    with tempfile.TemporaryDirectory() as td:
        x = pathlib.Path(td) / "tree"
        x.mkdir()
        _export(cache, tree, x)
        _git(x, "init", "-q")
        _git(x, "remote", "add", "origin", "https://github.com/%s.git" % cfg["repo"])
        _git(x, "add", "-A", "-f")
        readme = _read(x / "README.md")
        if readme is not None:
            out["readme"] = ["README %s: %s" % (ck, d) for lv, ck, d in lint(readme, Ctx(x), release=True)
                             if lv == "FAIL"]
        default = (x / "tools" / "audit_public.py").is_file()
        for name in sorted(os.listdir(dev)):                   # ignored hash sources (extracted/...) resolve
            if name != ".git" and not os.path.lexists(x / name):
                os.symlink(os.path.join(dev, name), x / name)
        if cfg["audit"]:
            argv = [a.replace("{tree}", str(x)).replace("{dev}", str(dev)) for a in cfg["audit"]]
        elif default:
            argv = ["python3", "tools/audit_public.py"]
        else:
            out["noaudit"] = ["no tools/audit_public.py in the tree and no [public].audit: nothing audits the release"]
            return out
        r = subprocess.run(argv, cwd=x, capture_output=True, text=True)
        if r.returncode != 0:
            out["audit"] = ["audit %s exited %d:\n%s" % (" ".join(argv[:2]), r.returncode, _tail(r))]
    return out


def preflight(cache, dev, cfg, tree: str, want: dict, rev: str) -> list[str]:
    """The release gate, run on the exported projection before any ref is written: FAIL lines."""
    g = gate_checks(cache, dev, cfg, tree, want, rev)
    return g["paths"] + g["readme"] + g["noaudit"] + g["audit"]


def tree_check(cache, dev, tree: str, argv: list[str], tip: str) -> subprocess.CompletedProcess:
    """[public].land_check on an export of tree, run from dev: `{tree}` is the export's directory, `{tip}` the commit
    it stands for."""
    with tempfile.TemporaryDirectory() as td:
        _export(cache, tree, td)
        argv = [a.replace("{tree}", td).replace("{tip}", tip) for a in argv]
        try:
            return subprocess.run(argv, cwd=dev, capture_output=True, text=True)
        except OSError as e:
            return subprocess.CompletedProcess(argv, 127, "", str(e))


def _prepare(dev, cfg, cache, main, rev: str, summary: str, ack) -> dict | None:
    """The release gate up to the commit, writing no ref: the sync check, the exact projection (its changes printed),
    the new paths (`ack(new)` raises Fail unless they are accepted), preflight, then the one reproducible commit in
    the cache. None when the projection already is public main's tree."""
    rels, contribs = history(cache, dev, main)
    seen = imported(dev, rev)
    pend = [c for c in contribs if c not in seen]
    if pend:
        raise Fail("public has %d contributor commit(s) %s lacks:\n%s\nrun import, land it at the phase end, release "
                   "again" % (len(pend), rev[:10], "\n".join("  %s %s" % (c[:10], _subject(cache, c)) for c in pend)))
    tree, want, probs = projection(cache, dev, rev)
    if probs:
        raise Fail("the projection of %s is not publishable:\n%s" % (rev[:10], "\n".join("  " + p for p in probs)))
    base = _must(cache, "rev-parse", main + "^{tree}") if main else None
    if tree == base:
        return None
    old = tree_entries(cache, main) if main else {}
    new = sorted(p for p in want if p not in old)
    for p in sorted(set(want) | set(old)):
        if want.get(p) != old.get(p):
            print("  %s %s" % ("A" if p in new else "D" if p not in want else "M", p))
    if new:
        ack(new)
    bad = preflight(cache, dev, cfg, tree, want, rev)
    if bad:
        raise Fail("preflight refused the release:\n%s" % "\n".join("  " + b for b in bad))
    name, email = _identity(dev)
    when = _must(dev, "log", "-1", "--format=%cI", rev)
    env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_NAME=name,
               GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=when)
    msg = "Release: %s\n\n%s" % (summary, release_body(summary, rev, tree, main, cfg["assisted_by"]))
    sha = _must(cache, "commit-tree", tree, *(["-p", main] if main else []), inp=msg, env=env)
    return {"rev": rev, "tree": tree, "want": want, "new": new, "sha": sha, "br": "release/" + rev[:10],
            "summary": summary, "main": main}


def _summary(summary) -> str:
    if not summary or not summary.strip() or "\n" in summary:
        raise Fail("--summary: one non-empty line, in your own words (it becomes the release's title)")
    return summary.strip()


def _rev(dev, cfg, rev) -> str:
    r = _git(dev, "rev-parse", "--verify", "-q", "%s^{commit}" % (rev or "refs/heads/" + cfg["dev_branch"]))
    if r.returncode != 0:
        raise Fail("%s: no such commit in %s" % (rev or cfg["dev_branch"], dev))
    return r.stdout.strip()


def _write_release(cache, cfg, p: dict, force: bool = False) -> tuple[str, pathlib.Path]:
    """The release branch in the cache and its PR body file: (ref, body path)."""
    ref = "refs/heads/" + p["br"]
    have = _git(cache, "rev-parse", "--verify", "-q", ref).stdout.strip()
    if have and have != p["sha"] and not force:
        raise Fail("%s exists in the cache at %s, not %s: delete it or release another revision" % (
            p["br"], have[:10], p["sha"][:10]))
    _must(cache, "update-ref", ref, p["sha"])
    body = cache / ("PR_BODY-%s.md" % p["rev"][:10])
    body.write_text(release_body(p["summary"], p["rev"], p["tree"], p["main"], cfg["assisted_by"]), encoding="utf-8")
    return ref, body


def _pr_create(cfg, p: dict, body) -> list[str]:
    return ["pr", "create", "--repo", cfg["repo"], "--base", "main", "--head", p["br"], "--title",
            "Release: " + p["summary"], "--body-file", str(body)]


def _open_pr(cache, cfg, p: dict, ref: str, body, force: bool = False) -> str:
    """Push the release branch to public and open its PR: the PR's URL."""
    _must(cache, "push", "-q", cfg["url"], "%s%s:%s" % ("+" if force else "", ref, ref))
    r = gh(_pr_create(cfg, p, body))
    if r.returncode != 0:
        raise Fail("gh pr create: %s" % (r.stderr.strip() or r.stdout.strip()))
    return r.stdout.strip()


def release_prs(cfg) -> list[dict]:
    """The open PRs of public whose head is a release/ branch: [{number, headRefName, url}]."""
    r = gh(["pr", "list", "--repo", cfg["repo"], "--state", "open", "--json", "number,headRefName,url"])
    if r.returncode != 0:
        raise Fail("gh pr list: %s" % (r.stderr.strip() or r.stdout.strip()))
    try:
        prs = json.loads(r.stdout or "[]")
    except ValueError:
        raise Fail("gh pr list: not JSON")
    return [x for x in prs if str(x.get("headRefName", "")).startswith("release/")]


@_cmd("RELEASE")
def cmd_release(repo=".", rev=None, summary=None, ack_new=False, dry_run=False, push=False) -> int:
    if not dry_run:
        _dev_only("release")
    summary = _summary(summary)
    dev, cfg, cache, main = _split(repo)
    rev = _rev(dev, cfg, rev)

    def ack(new):
        if not ack_new:
            raise Fail("%d new public path(s): review the list above, then rerun with --ack-new" % len(new))
    p = _prepare(dev, cfg, cache, main, rev, summary, ack)
    if p is None:
        print("RELEASE nothing to release: the listed files of %s are already on public" % rev[:10])
        return 0
    sha, br = p["sha"], p["br"]
    if dry_run:
        print("RELEASE dry run: would commit %s on %s (tree %s, %d file(s)); no ref written" % (
            sha[:10], br, p["tree"][:10], len(p["want"])))
        print("RELEASE next: `ci-sim --projection` runs no-rom on this tree in a clean container (and `--workflow "
              "build`), before it is public")
        return 0
    ref, body = _write_release(cache, cfg, p)
    print("RELEASE %s %s: %d file(s), %d new" % (br, sha[:10], len(p["want"]), len(p["new"])))
    if not main:                        # release 1: no main for a PR to target, so it becomes main, before the rulesets
        first = "git -C %s push %s %s:refs/heads/main" % (cache, cfg["url"], sha)
        if not push:
            print("RELEASE not pushed; public has no main yet, so release 1 becomes main (before settings --apply):\n"
                  "  %s" % first)
            return 0
        _must(cache, "push", "-q", cfg["url"], "%s:refs/heads/main" % sha)
        print("RELEASE pushed %s as public main (release 1); next: settings --apply" % sha[:10])
        return 0
    if not push:
        gh_cmd = " ".join("'%s'" % a if " " in a else a for a in _pr_create(cfg, p, body))
        print("RELEASE not pushed; to open the PR:\n  git -C %s push %s %s:%s\n  gh %s" % (cache, cfg["url"], ref, ref,
                                                                                         gh_cmd))
        return 0
    open_ = release_prs(cfg)
    if open_:
        raise Fail("an open release PR exists (%s): merge or close it first" % ", ".join(
            x["headRefName"] for x in open_))
    print("RELEASE pushed %s; PR: %s" % (br, _open_pr(cache, cfg, p, ref, body)))
    return 0


# ---- import: public contributor commits -> import commits in the cache -------------------------------------------

def _merge3(cache, ours: str, base: str, theirs: str) -> str | None:
    blobs = read_blobs(cache, [ours, base, theirs])
    with tempfile.TemporaryDirectory() as td:
        names = []
        for i, s in enumerate((ours, base, theirs)):
            f = os.path.join(td, str(i))
            pathlib.Path(f).write_bytes(blobs[s])
            names.append(f)
        r = subprocess.run(["git", "merge-file", "-p"] + names, capture_output=True)
    if r.returncode != 0:
        return None
    return _git_raw(cache, "hash-object", "-w", "--stdin", inp=r.stdout).stdout.decode().strip()


def keyed_merge(ours: bytes, base: bytes, theirs: bytes, n: int) -> bytes | None:
    """[public].keyed: a table merged row by row on its first n tab-separated columns, or None to refuse. Comment
    (`#`) and blank lines are ours; a row changed on one side takes that side (the same change on both is fine); rows
    new on theirs follow ours, in theirs' order. Refused: a key changed two ways, deleted on one side and changed on
    the other, a duplicate key, a row of fewer than n columns, or comment lines theirs changed and ours did not
    change the same way (they would be lost)."""
    def parse(data):
        rows, notes, order = {}, [], []
        text = data.decode("utf-8", "surrogateescape")
        for line in (text[:-1] if text.endswith("\n") else text).split("\n") if text else []:
            if not line.strip() or line.startswith("#"):
                notes.append(line)
                order.append((None, line))
                continue
            cols = line.split("\t")
            k = tuple(cols[:n])
            if len(cols) < n or k in rows:
                return None
            rows[k] = line
            order.append((k, line))
        return rows, notes, order
    parsed = [parse(x) for x in (ours, base, theirs)]
    if None in parsed:
        return None
    (o, on, oo), (b, bn, _), (t, tn, to) = parsed
    if tn != bn and tn != on:
        return None
    out = {}
    for k in set(o) | set(b) | set(t):
        ov, bv, tv = o.get(k), b.get(k), t.get(k)
        if ov == tv or tv == bv:
            out[k] = ov
        elif ov == bv:
            out[k] = tv
        else:
            return None
    lines = [line if k is None else out[k] for k, line in oo if k is None or out[k] is not None]
    lines += [out[k] for k, _ in to if k is not None and k not in o and out[k] is not None]
    return "".join(l + "\n" for l in lines).encode("utf-8", "surrogateescape")


def _merge_keyed(cache, ours: str, base: str, theirs: str, n: int) -> str | None:
    blobs = read_blobs(cache, [ours, base, theirs])
    merged = keyed_merge(blobs[ours], blobs[base], blobs[theirs], n)
    if merged is None:
        return None
    return _git_raw(cache, "hash-object", "-w", "--stdin", inp=merged).stdout.decode().strip()


def _take(cache, cfg, c: str, tip: str, ours: dict, rel_shas: set, accept_gov: bool):
    """(entries after taking public commit c on top of tip, [reasons it cannot be taken])."""
    parents = _must(cache, "rev-list", "--parents", "-n", "1", c).split()[1:]
    if len(parents) > 1:
        return None, ["%s: a merge commit (the public ruleset allows squash only)" % c[:10]]
    msg = _must(cache, "log", "-1", "--format=%B", c)
    m = re.search(r"This reverts commit ([0-9a-f]{40})", msg)
    if (m and m[1] in rel_shas) or msg.startswith('Revert "Release: '):
        return None, ["%s: reverts a release (the release is dev's, take the change back in dev)" % c[:10]]
    base = (tree_entries(cache, parents[0]) or {}) if parents else {}
    theirs = tree_entries(cache, c) or {}
    raw = _git(cache, "diff-tree", "-r", "-z", "--no-renames", "--no-commit-id", "--root", c).stdout.split("\0")
    paths, i = [], 0
    while i < len(raw):
        if raw[i].startswith(":") and i + 1 < len(raw):
            paths.append(raw[i + 1])
            i += 2
        else:
            i += 1
    deny, gov = deny_entries(cache, tip), governance(cfg)
    lt, lc = _dev_list(cache, tip)[0] or [], _dev_list(cache, c)[0] or []
    errs = []
    for p in paths:
        t = theirs.get(p)
        if t and t[0] in ("120000", "160000"):
            errs.append("%s: a %s (only regular files)" % (p, "symlink" if t[0] == "120000" else "gitlink"))
        elif is_denied(deny, p):
            errs.append("%s: denied (agent file, PA3-managed or [public].deny)" % p)
        elif not (is_listed(lt, p) or is_listed(lc, p)):
            errs.append("%s: listed by neither dev's list nor the commit's own" % p)
        elif is_listed(gov, p) and not accept_gov:
            errs.append("%s: a governance path: read it, then rerun with --accept-governance" % p)
    if errs:
        return None, errs
    new, conflicts = dict(ours), []
    for p in paths:
        b, t, o = base.get(p), theirs.get(p), ours.get(p)
        if o == b:
            new.pop(p, None) if t is None else new.__setitem__(p, t)
        elif o == t:
            continue
        elif all(x and x[0] in ("100644", "100755") for x in (o, b, t)) and o[0] == t[0]:
            merged = _merge3(cache, o[1], b[1], t[1])
            if merged is None and p in cfg["keyed"]:
                merged = _merge_keyed(cache, o[1], b[1], t[1], cfg["keyed"][p])
            if merged is None:
                conflicts.append(p)
            else:
                new[p] = (o[0], merged)
        else:
            conflicts.append(p)
    return (new, []) if not conflicts else (None, ["%s: conflicts with dev's own change" % p for p in conflicts])


@_cmd("IMPORT")
def cmd_import(repo=".", accept_governance=False, skip=()) -> int:
    dev, cfg, cache, main = _split(repo)
    base = _must(dev, "rev-parse", "--verify", "refs/heads/" + cfg["dev_branch"])
    rels, contribs = history(cache, dev, main)
    done = imported(dev, base)
    pending = [c for c in contribs if c not in done]
    if not pending:
        print("IMPORT nothing to import: dev %s holds every public contributor commit" % base[:10])
        return 0
    for s in skip:
        if not any(c.startswith(s) for c in pending):
            raise Fail("--skip %s: not a pending public commit" % s)
    name, email = _identity(dev)
    rel_shas = {r[0] for r in rels}
    ours, tip, shown = dict(tree_entries(cache, base) or {}), base, []
    for c in pending:
        an, ae, ad, cd, subj = _must(cache, "log", "-1", "--format=%an%x1f%ae%x1f%aI%x1f%cI%x1f%s", c).split("\x1f")
        extra = []
        if any(c.startswith(s) for s in skip):
            extra = ["Import-Skipped: by the maintainer"]
        else:
            new, errs = _take(cache, cfg, c, tip, ours, rel_shas, accept_governance)
            if errs:
                raise Fail("cannot import %s %s:\n%s\nnothing written" % (c[:10], subj, "\n".join("  " + e for e in errs)))
            ours = new
        co = ["Co-authored-by: " + v for v in trailers(cache, c, "Co-authored-by")]
        msg = "Import %s: %s\n\n%s\n" % (cd[:10], subj, "\n".join(["%s: %s" % (IMPORT_TRAILER, c)] + co + extra))
        env = dict(os.environ, GIT_AUTHOR_NAME=an, GIT_AUTHOR_EMAIL=ae, GIT_AUTHOR_DATE=ad, GIT_COMMITTER_NAME=name,
                   GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=cd)
        tip = _must(cache, "commit-tree", write_tree(cache, ours), "-p", tip, inp=msg, env=env)
        shown.append("%s Import %s: %s" % (tip[:10], cd[:10], subj))
    _must(cache, "update-ref", "refs/psxdecomp/import", tip)
    _must(cache, "update-ref", "refs/psxdecomp/import-base", base)
    print("\n".join(shown))
    print("IMPORT ready: %s on %s; land it at the phase end: psxd_publish.py land %s" % (tip, base[:10], tip))
    return 0


# ---- land: the import chain onto dev, only when the gate is idle -------------------------------------------------

def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def inbox_pending(text: str) -> list[str]:
    """The bullets the router has yet to consume, by PA3's own rule (tools/status.py `inbox_pending`, 3.14.2):
    top-level `- ` lines outside HTML comments, indented lines joined, the template's `<...>` placeholder left out."""
    out, cur = [], None
    for raw in re.sub(r"<!--.*?-->", "", text, flags=re.S).split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("- "):
            if cur is not None:
                out.append(cur)
            cur = line[2:].strip()
        elif cur is not None and line[:1] in (" ", "\t") and line.strip() and not line.strip().startswith("- "):
            cur += " " + line.strip()
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return [b for b in out if b and not re.match(r"^<.*>$", b)]


def land_blockers(dev, cfg, cache, tip) -> list[str]:
    import fcntl
    dev, out = pathlib.Path(dev), []
    if os.environ.get("CLAUDECODE"):
        out.append("CLAUDECODE is set: land is for the developer, not an agent session")
    st = _read(dev / ".run/status.json")
    d = {}
    if st is not None:
        try:
            d = json.loads(st)
        except ValueError:
            d = None
        if not isinstance(d, dict):
            out.append(".run/status.json is not a JSON object")
            d = {}
        elif any(d.get(k) is not None for k in ("task", "kind", "waiting")):
            out.append(".run/status.json: a task, kind or waiting is set (the router is busy)")
    sess = d.get("router_session")
    pidf = dev / ".run/warmer" / ("%s.pid" % sess) if sess else None
    if pidf and pidf.is_file():
        try:
            if _alive(int((_read(pidf) or "").strip())):
                out.append("warmer %s is alive (%s)" % (sess, pidf.relative_to(dev)))
        except ValueError:
            pass
    for f in sorted(glob.glob(str(dev / ".run/gate/locks/*.lock"))) + [str(dev / ".run/gate/apply.lock")]:
        if not os.path.exists(f):
            continue
        try:
            fd = os.open(f, os.O_RDONLY)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            out.append("flock held on %s (the gate is applying)" % os.path.relpath(f, dev))
        finally:
            os.close(fd)
    cur = dev / "phase-ends/current"
    if inbox_pending(_read(cur / "INBOX.md") or ""):
        out.append("phase-ends/current/INBOX.md has a pending bullet")
    out += ["phase-ends/current/%s exists" % n for n in ("REVIEW.md", "REPLAN.md") if (cur / n).exists()]
    waves = _read(dev / "config/waves.tsv")
    if waves is not None:
        rows = [l for l in waves.splitlines() if l.strip() and not l.lstrip().startswith("#")][1:]
        for l in rows:
            c = (l.split("\t") + [""] * 13)[:13]
            if c[3] == "-" or c[5] == "-" or c[11] in ("-", "") or c[12] == "open":
                out.append("config/waves.tsv: wave %s is not closed, drafted, fleeted and harvested" % c[0])
    for f in sorted(glob.glob(str(dev / "campaign/harvest/W*.start.json"))):
        ok = f[:-len(".start.json")] + ".ok"
        if not os.path.exists(ok):
            out.append("campaign/harvest/%s has no %s" % (os.path.basename(f), os.path.basename(ok)))
    br = _git(dev, "branch", "--show-current").stdout.strip()
    if br != cfg["dev_branch"]:
        out.append("dev is on %r, not %s" % (br, cfg["dev_branch"]))
    head = _git(dev, "rev-parse", "HEAD").stdout.strip()
    ib = _git(cache, "rev-parse", "--verify", "-q", "refs/psxdecomp/import-base").stdout.strip()
    if head != ib:
        out.append("HEAD %s is not the import base %s: import again" % (head[:10], ib[:10] or "(none)"))
    chain = _git(cache, "rev-list", "--first-parent", "--reverse", "%s..%s" % (head, tip)).stdout.split()
    allc = _git(cache, "rev-list", "%s..%s" % (head, tip)).stdout.split()
    if not chain or set(chain) != set(allc) or _git(cache, "rev-parse", chain[0] + "^").stdout.strip() != head:
        out.append("%s is not a first-parent line of commits on HEAD" % tip[:10])
    elif not all(trailers(cache, c, IMPORT_TRAILER) for c in chain):
        out.append("a commit of the chain has no %s trailer" % IMPORT_TRAILER)
    if _git(dev, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        out.append("dev has uncommitted changes to tracked files (dirty)")
    if not cfg["land_check"]:
        out.append("[public].land_check is not set (the byte check of the exported tip)")
    elif not out:
        r = tree_check(cache, dev, _must(cache, "rev-parse", tip + "^{tree}"), cfg["land_check"], tip)
        if r.returncode != 0:
            out.append("land_check exited %d:\n%s" % (r.returncode, _tail(r)))
    return out


def cmd_land(repo=".", tip=None) -> int:
    try:
        dev, cfg, cache, _ = _split(repo)
        tip = tip or _git(cache, "rev-parse", "--verify", "-q", "refs/psxdecomp/import").stdout.strip()
        r = _git(cache, "rev-parse", "--verify", "-q", "%s^{commit}" % tip) if tip else None
        if r is None or r.returncode != 0:
            raise Fail("no import to land: run import first")
        tip = r.stdout.strip()
        blockers = land_blockers(dev, cfg, cache, tip)
        if blockers:
            for b in blockers:
                _line("LAND", "FAIL", b)
            return 1
        old = _must(dev, "rev-parse", "HEAD")
        n = len(_must(cache, "rev-list", "%s..%s" % (old, tip)).split())
        _must(dev, "fetch", "-q", str(cache), tip)
        _must(dev, "merge", "--ff-only", "-q", tip)
    except Fail as e:
        _line("LAND", "FAIL", str(e))
        return 1
    print("LAND OK %s..%s (%d import commit(s))" % (old[:10], tip[:10], n))
    return 0


# ---- settings: the public repository against the standard --------------------------------------------------------

REPO_WANT = {"allow_merge_commit": False, "allow_rebase_merge": False, "allow_squash_merge": True,
             "squash_merge_commit_title": "PR_TITLE", "squash_merge_commit_message": "PR_BODY",
             "delete_branch_on_merge": True, "allow_forking": True, "has_wiki": False, "has_projects": False}
SECURITY_WANT = ("secret_scanning", "secret_scanning_push_protection")
SQUASH_PAIR = ("squash_merge_commit_title", "squash_merge_commit_message")
PR_KEYS = ("required_approving_review_count", "require_code_owner_review", "dismiss_stale_reviews_on_push",
           "require_last_push_approval", "required_review_thread_resolution")
BRANCH_POLICY = {"protected_branches": False, "custom_branch_policies": True}
ADMIN_UI = "turn off 'Allow administrators to bypass configured protection rules' in the environment's settings (UI only)"


def ruleset_want(name: str, checks) -> dict:
    pr = lambda n, owners: {"type": "pull_request", "parameters": {  # noqa: E731
        "required_approving_review_count": n, "require_code_owner_review": owners, "dismiss_stale_reviews_on_push": False,
        "require_last_push_approval": False, "required_review_thread_resolution": False,
        "allowed_merge_methods": ["squash"]}}
    body = {"name": name, "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}}
    if name == "main-integrity":
        return body | {"bypass_actors": [], "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"}, pr(0, False),
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True, "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": c, "integration_id": ACTIONS_APP} for c in checks]}}]}
    return body | {"bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
                   "rules": [pr(1, True)]}


def ruleset_norm(j: dict) -> dict:
    rules = []
    for r in j.get("rules") or []:
        p, t = r.get("parameters") or {}, r.get("type")
        if t == "pull_request":
            p = {k: p.get(k) if k == PR_KEYS[0] else bool(p.get(k)) for k in PR_KEYS} | {
                "allowed_merge_methods": sorted(p.get("allowed_merge_methods") or [])}
            p[PR_KEYS[0]] = p[PR_KEYS[0]] or 0
        elif t == "required_status_checks":
            p = {"strict_required_status_checks_policy": bool(p.get("strict_required_status_checks_policy")),
                 "do_not_enforce_on_create": bool(p.get("do_not_enforce_on_create")),
                 "required_status_checks": sorted(({"context": c.get("context"), "integration_id": c.get("integration_id")}
                                                   for c in p.get("required_status_checks") or []),
                                                  key=lambda c: c["context"] or "")}
        else:
            p = {}
        rules.append({"type": t, "parameters": p})
    cond = (j.get("conditions") or {}).get("ref_name") or {}
    bypass = [{k: b.get(k) for k in ("actor_id", "actor_type", "bypass_mode")} for b in j.get("bypass_actors") or []]
    return {"target": j.get("target"), "enforcement": j.get("enforcement"),
            "bypass_actors": sorted(bypass, key=lambda b: json.dumps(b, sort_keys=True)),
            "include": sorted(cond.get("include") or []), "exclude": sorted(cond.get("exclude") or []),
            "rules": sorted(rules, key=lambda r: r["type"] or "")}


def settings_drift(cfg: dict, api) -> list[dict]:
    """[{what, have, want, fix}] where the public repository differs from the standard; `fix` is a (method, path,
    body) tuple, or None when only the developer can fix it. `api(method, path, body=None)` returns the parsed JSON
    ({} for an empty success, None for 404). Only GETs are issued."""
    R, rows = "repos/" + cfg["repo"], []

    def row(what, have, want, fix=None, hint=None):
        rows.append({"what": what, "have": have, "want": want, "fix": fix, "hint": hint})

    def field(what, path, have, want, fix):
        if have != want:
            row(what, have, want, ("PUT", path, fix))
    repo = api("GET", R) or {}
    # One PATCH with the drifting keys only (GitHub refuses any allow_forking field on a user-owned repository), and
    # the squash title and message always together: GitHub refuses the message alone even when the title matches (422).
    drift = {k: v for k, v in REPO_WANT.items() if repo.get(k) != v}
    body = dict(drift, **({k: REPO_WANT[k] for k in SQUASH_PAIR} if set(SQUASH_PAIR) & set(drift) else {}))
    for k, v in drift.items():
        row("repo.%s" % k, repo.get(k), v, ("PATCH", R, body))
    if repo.get("visibility") != "public":
        row("repo.visibility", repo.get("visibility"), "public")
    sa = repo.get("security_and_analysis") or {}
    for k in SECURITY_WANT:
        have = (sa.get(k) or {}).get("status")
        if have != "enabled":
            row("repo.%s" % k, have, "enabled", ("PATCH", R, {"security_and_analysis": {k: {"status": "enabled"}}}))
    p = R + "/private-vulnerability-reporting"
    field("private-vulnerability-reporting", p, bool((api("GET", p) or {}).get("enabled")), True, None)
    p = R + "/vulnerability-alerts"
    field("vulnerability-alerts", p, api("GET", p) is not None, True, None)
    p = R + "/actions/permissions/workflow"
    j, fix = api("GET", p) or {}, {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}
    for k, v in fix.items():
        field("workflow.%s" % k, p, j.get(k), v, fix)
    p = R + "/actions/permissions"
    j = api("GET", p) or {}
    fix = {"enabled": True, "allowed_actions": j.get("allowed_actions") or "all", "sha_pinning_required": True}
    for k in ("enabled", "sha_pinning_required"):
        field("actions.%s" % k, p, j.get(k), True, fix)
    p = R + "/actions/permissions/fork-pr-contributor-approval"
    field("fork-pr-contributor-approval", p, (api("GET", p) or {}).get("approval_policy"), "all_external_contributors",
          {"approval_policy": "all_external_contributors"})
    p = R + "/actions/permissions/artifact-and-log-retention"
    field("artifact-and-log-retention", p, (api("GET", p) or {}).get("days"), 90, {"days": 90})
    listed = {x.get("name"): x.get("id") for x in api("GET", R + "/rulesets") or []}
    for name in ("main-integrity", "main-review"):
        want = ruleset_want(name, cfg["checks"])
        if name not in listed:
            row("ruleset %s" % name, "absent", "present", ("POST", R + "/rulesets", want))
            continue
        path = "%s/rulesets/%s" % (R, listed[name])
        have, w = ruleset_norm(api("GET", path) or {}), ruleset_norm(want)
        diff = [k for k in w if have[k] != w[k]]
        if diff:
            row("ruleset %s" % name, {k: have[k] for k in diff}, {k: w[k] for k in diff}, ("PUT", path, want))
    owner = cfg["repo"].split("/")[0]
    uid = (api("GET", "users/" + owner) or {}).get("id")
    for env, reviewers in (("fork-review", True), ("ci", False)):
        ep = "%s/environments/%s" % (R, env)
        j = api("GET", ep)
        body = {"prevent_self_review": False, "deployment_branch_policy": BRANCH_POLICY}
        body["reviewers"] = [{"type": "User", "id": uid}] if reviewers else []
        if j is None:
            row("environment %s" % env, "absent", "present", ("PUT", ep, body))
        else:
            rule = next((r for r in j.get("protection_rules") or [] if r.get("type") == "required_reviewers"), {})
            ids = sorted((x.get("reviewer") or {}).get("id") for x in rule.get("reviewers") or [])
            if ids != ([uid] if reviewers else []):
                row("environment %s reviewers" % env, ids, [uid] if reviewers else [], ("PUT", ep, body))
            if reviewers and bool(rule.get("prevent_self_review")):
                row("environment %s prevent_self_review" % env, True, False, ("PUT", ep, body))
            if j.get("deployment_branch_policy") != BRANCH_POLICY:
                row("environment %s deployment_branch_policy" % env, j.get("deployment_branch_policy"), BRANCH_POLICY,
                    ("PUT", ep, body))
            if "can_admins_bypass" in j and j["can_admins_bypass"]:
                row("environment %s can_admins_bypass" % env, True, False, None, ADMIN_UI)
        pols = ((api("GET", ep + "/deployment-branch-policies") or {}).get("branch_policies") or []) if j else []
        names = sorted(x.get("name") for x in pols)
        if names != ["main"]:
            row("environment %s branch policies" % env, names, ["main"],
                ("POST", ep + "/deployment-branch-policies", {"name": "main", "type": "branch"})
                if "main" not in names else None)
    if all(api("GET", R + "/actions/secrets/" + s) is None for s in ("PRIVATE_DEPLOY_KEY", "PRIVATE_REPO_TOKEN")):
        row("secret PRIVATE_DEPLOY_KEY", "absent", "gh secret set PRIVATE_DEPLOY_KEY --repo %s < <key file> (or a "
            "fine-grained PAT as PRIVATE_REPO_TOKEN, build.yml's `token:`)" % cfg["repo"])
    if api("GET", R + "/contents/.github/CODEOWNERS") is None:
        row("CODEOWNERS", "absent", ".github/CODEOWNERS on main (a release carries it)")
    return rows


def gh_api(method: str, path: str, body=None):
    r = gh(["api", "-X", method, path] + (["--input", "-"] if body is not None else []),
           json.dumps(body) if body is not None else None)
    if r.returncode != 0:
        if "404" in (r.stdout or "") + (r.stderr or ""):
            return None
        raise Fail("gh api %s %s: %s" % (method, path, _tail(r, 3)))
    return json.loads(r.stdout) if (r.stdout or "").strip() else {}


def _print_drift(rows):
    for r in rows:
        _line("SETTINGS", "DRIFT", "%s: have %s, want %s%s" % (r["what"], r["have"], r["want"],
                                                              " (%s)" % r["hint"] if r.get("hint") else ""))


@_cmd("SETTINGS")
def cmd_settings(repo=".", apply=False, api=None) -> int:
    if apply:
        _dev_only("settings --apply")
    cfg = load_public(repo_root(repo))
    if cfg is None:
        raise Fail("split mode is off: no [public] in %s" % CONFIG_REL)
    api = api or gh_api
    rows = settings_drift(cfg, api)
    if apply and rows:
        done = set()
        for r in rows:
            if r["fix"] and json.dumps(r["fix"], sort_keys=True) not in done:
                done.add(json.dumps(r["fix"], sort_keys=True))
                api(*r["fix"])
        rows = settings_drift(cfg, api)
    _print_drift(rows)
    print("SETTINGS OK" if not rows else "SETTINGS DRIFT %d row(s)" % len(rows))
    return 1 if rows else 0


# ---- verify-pr: a public PR before the developer merges it -------------------------------------------------------

def verify_pr(cfg: dict, n: int, api, release: dict | None = None) -> tuple[list[str], list[str], str]:
    """(failures, warnings, head sha) for public PR n. A `build *` check must come from build.yml run by
    `pull_request_target` at the PR head; any other required check (the no-rom audit) from a run at the PR head whose
    workflow file the PR does not change (otherwise the PR certifies itself). `release` ({br, reviewed}) is ship's
    own release PR: same-repo, from branch br, titled `Release: `; reviewed means the owner read the workflow diff, so
    a check from a workflow the release changes is accepted."""
    R, fails, warns = "repos/" + cfg["repo"], [], []
    pr = api("GET", "%s/pulls/%d" % (R, n))
    if not pr:
        return ["PR #%d not found" % n], [], ""
    head = pr.get("head") or {}
    H = head.get("sha") or ""
    fork = (head.get("repo") or {}).get("full_name") != cfg["repo"]
    if pr.get("state") != "open":
        fails.append("PR #%d is %s, not open" % (n, pr.get("state")))
    if (pr.get("base") or {}).get("ref") != "main":
        fails.append("PR #%d targets %s, not main" % (n, (pr.get("base") or {}).get("ref")))
    if fork and ((pr.get("title") or "").startswith("Release:") or re.search(r"^Release-[A-Za-z]+:", pr.get("body") or "",
                                                                             re.M)):
        fails.append("a fork PR claims to be a release (Release: title or Release-* trailer)")
    if release is not None and (fork or head.get("ref") != release["br"] or
                                not (pr.get("title") or "").startswith("Release: ")):
        fails.append("PR #%d is not the release PR of %s (head %s, title %r)" % (n, release["br"], head.get("ref"),
                                                                                 pr.get("title")))
    files = [f.get("filename", "") for f in api("GET", "%s/pulls/%d/files?per_page=100" % (R, n)) or []]
    runs = (api("GET", "%s/commits/%s/check-runs?per_page=100" % (R, H)) or {}).get("check_runs") or []
    wf = (api("GET", "%s/actions/runs?head_sha=%s&per_page=100" % (R, H)) or {}).get("workflow_runs") or []
    for name in cfg["checks"]:
        mine = [r for r in runs if r.get("name") == name]
        good = [r for r in mine if r.get("status") == "completed" and r.get("conclusion") == "success"
                and (r.get("app") or {}).get("id") == ACTIONS_APP]
        if not good:
            fails.append("check %r: %s" % (name, "not a completed success from GitHub Actions" if mine else "missing"))
            continue
        sid = (good[0].get("check_suite") or {}).get("id")
        w = next((x for x in wf if x.get("check_suite_id") == sid), None) or {}
        path = (w.get("path") or "none").split("@")[0]
        if name.startswith("build "):
            if path != TRUSTED_WORKFLOW or w.get("head_sha") != H or w.get("event") != "pull_request_target":
                fails.append("check %r comes from %s/%s at %s, not %s/pull_request_target at the PR head" % (
                    name, path, w.get("event"), (w.get("head_sha") or "none")[:10], TRUSTED_WORKFLOW))
        elif w.get("head_sha") != H or path == "none" or (path in files and not (release or {}).get("reviewed")):
            fails.append("check %r comes from %s at %s: it must run at the PR head from a workflow the PR does not "
                         "change" % (name, path, (w.get("head_sha") or "none")[:10]))
    if fork:
        touched = [f for f in files if f.startswith(".github/") or is_listed(governance(cfg), f)]
        if touched:
            warns.append("a fork PR changes governance paths (the code owner reviews them): %s" % ", ".join(touched))
    return fails, warns, H


@_cmd("VERIFY-PR")
def cmd_verify_pr(repo=".", n=0, merge=False, api=None) -> int:
    if merge:
        _dev_only("verify-pr --merge")
    cfg = load_public(repo_root(repo))
    if cfg is None:
        raise Fail("split mode is off: no [public] in %s" % CONFIG_REL)
    fails, warns, H = verify_pr(cfg, n, api or gh_api)
    for w in warns:
        _line("VERIFY-PR", "WARN", w)
    for f in fails:
        _line("VERIFY-PR", "FAIL", f)
    if fails:
        print("VERIFY-PR FAIL (%d)" % len(fails))
        return 1
    print("VERIFY-PR OK #%d %s" % (n, H[:10]))
    if merge:
        r = gh(["pr", "merge", str(n), "--repo", cfg["repo"], "--squash", "--match-head-commit", H])
        if r.returncode != 0:
            raise Fail("gh pr merge: %s" % _tail(r, 3))
        print("VERIFY-PR merged #%d" % n)
    return 0


# ---- ship: one release end to end, resumable ----------------------------------------------------------------------

SHIP_POLL = 30                                   # seconds between two reads of GitHub while ship waits
CI_PASS = ("success", "skipped", "neutral")      # a job guarded off by its repository condition is skipped


def dev_ci(repo: str, sha: str, api) -> tuple[str, list[str]]:
    """The workflow runs of repo (OWNER/REPO) at sha, the newest per workflow and event: (state, one line per run).
    state is `ok` (every run completed and passed), `fail` (a run failed: its failing jobs are named), `wait` (a run
    is not completed) or `none` (no run yet)."""
    runs = (api("GET", "repos/%s/actions/runs?head_sha=%s&per_page=100" % (repo, sha)) or {}).get("workflow_runs") or []
    last = {}
    for r in sorted(runs, key=lambda r: (r.get("created_at") or "", r.get("id") or 0)):
        last[(r.get("workflow_id") or r.get("path"), r.get("event"))] = r
    if not last:
        return "none", ["no workflow run on %s at %s yet" % (repo, sha[:10])]
    state, lines = "ok", []
    for r in last.values():
        name = "%s (%s)" % (r.get("name") or r.get("path"), r.get("event"))
        if r.get("status") != "completed":
            state = "fail" if state == "fail" else "wait"
            lines.append("%s: %s" % (name, r.get("status")))
        elif r.get("conclusion") not in CI_PASS:
            state = "fail"
            jobs = (api("GET", "repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, r.get("id"))) or {}).get("jobs")
            bad = [j.get("name", "?") for j in jobs or [] if j.get("conclusion") not in CI_PASS + (None,)]
            lines.append(("%s: %s%s %s" % (name, r.get("conclusion"), " in job " + ", ".join(bad) if bad else "",
                                           r.get("html_url") or "")).rstrip())
        else:
            lines.append("%s: %s" % (name, r.get("conclusion")))
    return state, lines


def _ask(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def ships_log(dev) -> pathlib.Path:
    common = _must(dev, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return pathlib.Path(common) / "psxdecomp" / "ships.tsv"


def _release_head(dev, cfg, cache, rev: str, br: str, H: str, main: str) -> str:
    """The release PR's head H fetched from public and held to what ship would have built: its Release-Of is rev,
    its Release-Tree is rev's projection and its own tree, its parent is public main. Returns the projection tree."""
    _must(cache, "fetch", "-q", "--no-tags", cfg["url"], "+refs/heads/%s:refs/psxdecomp/ship-head" % br)
    got = _must(cache, "rev-parse", "refs/psxdecomp/ship-head")
    if got != H:
        raise Fail("public %s is at %s, the PR's head is %s: rerun ship" % (br, got[:10], H[:10]))
    tree = projection(cache, dev, rev)[0]
    of, rt = trailers(cache, H, "Release-Of"), trailers(cache, H, "Release-Tree")
    if of != [rev] or rt != [tree] or _must(cache, "rev-parse", H + "^{tree}") != tree:
        raise Fail("%s is not the release of %s (Release-Of %s, Release-Tree %s, tree %s; the projection is %s)" % (
            br, rev[:10], of, rt, _must(cache, "rev-parse", H + "^{tree}")[:10], tree[:10]))
    parent = _git(cache, "rev-parse", "-q", "--verify", H + "^").stdout.strip()
    if parent != main:
        raise Fail("public main moved to %s since %s was cut on %s: import and land what came in, push, then "
                   "ship --replace" % (main[:10], br, parent[:10]))
    return tree


def _ship_verify(dev, cfg, cache, rev: str, api, polls: int, sleep, no_wait: bool, record: bool = True) -> int:
    """Stage 9: public main carries the release of rev, its push runs all passed and every `build <EXE>` run uploaded
    `<EXE>_report`; then SHIP OK and one line in .git/psxdecomp/ships.tsv."""
    R = "repos/" + cfg["repo"]
    main = fetch_public(cache, cfg["url"])
    hit = [(c, t) for c, of, t in releases(cache, dev, main) if of == rev]
    if not hit:
        raise Fail("public main %s carries no release of %s (the merge did not land?)" % ((main or "none")[:10],
                                                                                            rev[:10]))
    c, t = hit[-1]
    if not _subject(cache, c).startswith("Release: ") or trailers(cache, c, "Release-Of") != [rev]:
        raise Fail("%s is not a release commit of %s" % (c[:10], rev[:10]))
    if c != main:
        print("SHIP verify  note: public main moved on to %s since the release %s" % (main[:10], c[:10]))
    if _must(cache, "rev-parse", c + "^{tree}") != t:
        print("SHIP verify  WARN %s's tree is not its Release-Tree %s: the PR took other commits (import them)" % (
            c[:10], t[:10]))
    runs = []
    for i in range(polls):
        runs = (api("GET", "%s/actions/runs?head_sha=%s&event=push&per_page=100" % (R, c)) or {}).get(
            "workflow_runs") or []
        if runs and all(r.get("status") == "completed" for r in runs):
            break
        if no_wait:
            print("SHIP verify  wait: %d push run(s) at %s still running (--no-wait); rerun ship to verify" % (
                len(runs), c[:10]))
            return 0
        if i < polls - 1:
            sleep(SHIP_POLL)
    else:
        raise Fail("verify: the push runs at %s did not complete in time (%s); rerun ship to keep waiting" % (
            c[:10], ", ".join("%s %s" % (r.get("name"), r.get("status")) for r in runs) or "none started"))
    bad = [r for r in runs if r.get("conclusion") != "success"]
    if bad:
        raise Fail("verify: push run(s) at %s did not pass: %s" % (c[:10], "; ".join(
            "%s %s %s" % (r.get("name"), r.get("conclusion"), r.get("html_url") or "") for r in bad)))
    build = [r for r in runs if (r.get("path") or "").split("@")[0] == TRUSTED_WORKFLOW]
    names = set()
    for r in build:
        names |= {a.get("name") for a in (api("GET", "%s/actions/runs/%s/artifacts?per_page=100" % (R, r.get("id")))
                                          or {}).get("artifacts") or []}
    missing = ["%s_report" % x[len("build "):] for x in cfg["checks"] if x.startswith("build ")
               and "%s_report" % x[len("build "):] not in names]
    if missing:
        raise Fail("verify: no %s uploaded by %s at %s" % (", ".join(missing), TRUSTED_WORKFLOW, c[:10]))
    m = re.search(r"\(#(\d+)\)$", _subject(cache, c))
    pr = "https://github.com/%s/pull/%s" % (cfg["repo"], m[1]) if m else "-"
    log = ships_log(dev)
    have = _read(log) or ""
    if record and not any(l.split("\t")[1:2] == [rev] for l in have.splitlines()):
        files = len(tree_entries(cache, c) or {})
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(("" if have else "# date\trev\tpublic\tpr\tfiles\n") + "%s\t%s\t%s\t%s\t%d\n" % (
                time.strftime("%Y-%m-%d"), rev, c, pr, files))
    print("SHIP verify  OK %s: Release-Of %s, Release-Tree %s; %d push run(s) passed; %s uploaded" % (
        c[:10], rev[:10], t[:10], len(runs), ", ".join(sorted(n for n in names if n and n.endswith("_report")))))
    print("SHIP OK %s\n  PR %s\n%s" % (c[:10], pr, "\n".join("  run %s" % (r.get("html_url") or r.get("name"))
                                                            for r in runs)))
    return 0


def cmd_ship(repo=".", summary=None, rev=None, ack_new=False, dry_run=False, no_wait=False, timeout=90,
             replace=False, merge_reviewed=False, api=None, sleep=time.sleep, ask=_ask, ci_sim=None) -> int:
    """dev -> public in one resumable command. Stages: state, dev-ci, gate, build, ci, push, checks, merge, verify;
    each prints `SHIP <stage> OK|FAIL ...`. Nothing public is written before the five local stages pass."""
    stage, api, ci_sim = "state", api or gh_api, ci_sim or cmd_ci_sim
    polls = max(1, int(timeout * 60) // SHIP_POLL)

    def ok(detail):
        print("SHIP %-7s OK %s" % (stage, detail))
    try:
        if not dry_run:
            _dev_only("ship")
        if summary is not None:
            summary = _summary(summary)
        dev, cfg, cache, main = _split(repo)
        if not main:
            raise Fail("public has no main: release 1 is the cutover's step 5 (`release --push`), not ship")
        rev = _rev(dev, cfg, rev)
        pushed = _git(dev, "rev-parse", "-q", "--verify", "refs/remotes/origin/%s^{commit}" % cfg["dev_branch"])
        pushed = pushed.stdout.strip()
        if rev != pushed:
            raise Fail("%s is not origin/%s (%s): ship releases only a commit -dev has and CI tested; push first" % (
                rev[:10], cfg["dev_branch"], pushed[:10] or "none"))
        br, R = "release/" + rev[:10], "repos/" + cfg["repo"]
        if any(of == rev for _, of, _ in releases(cache, dev, main)):
            ok("%s is already released on public main" % rev[:10])
            stage = "verify"
            return _ship_verify(dev, cfg, cache, rev, api, polls, sleep, no_wait, record=not dry_run)
        prs = release_prs(cfg)
        mine = [x for x in prs if x["headRefName"] == br]
        other = [x for x in prs if x["headRefName"] != br]
        if other and not replace:
            raise Fail("an open release PR of another revision exists (%s): merge or close it, or rerun with --replace "
                       "(ship closes it after its own gate passes)" % ", ".join(
                           "#%s %s" % (x.get("number"), x["headRefName"]) for x in other))
        if mine:
            n = int(mine[0]["number"])
            ok("%s: release PR #%d is open; resuming at its checks" % (rev[:10], n))
            if dry_run:
                print("SHIP dry run: ship would wait for PR #%d's checks, then merge it" % n)
                return 0
        else:
            ok("%s = origin/%s; public main %s" % (rev[:10], cfg["dev_branch"], main[:10]))
            stage = "dev-ci"
            slug = origin_slug(dev)
            if not slug:
                raise Fail("origin is not a GitHub repository: -dev's CI cannot be read")
            for i in range(polls):
                state, lines = dev_ci(slug, rev, api)
                if state in ("ok", "fail") or (state == "none" and i >= 2) or no_wait or i == polls - 1:
                    break
                sleep(SHIP_POLL)
            if state != "ok":
                raise Fail("%s at %s: %s\n%s" % (slug, rev[:10], {"wait": "still running", "none": "no workflow run",
                                                                  "fail": "a run failed"}[state],
                                                 "\n".join("  " + l for l in lines)))
            ok("%d run(s) passed on %s at %s" % (len(lines), slug, rev[:10]))
            stage = "gate"
            if summary is None:
                raise Fail("--summary: one non-empty line, in your own words (it becomes the release's title)")

            def ack_paths(new):
                if not ack_new and not ask("%d new public path(s) listed above: publish them? [y/N] " % len(new)):
                    raise Fail("%d new public path(s): review the list above, then rerun with --ack-new" % len(new))
            p = _prepare(dev, cfg, cache, main, rev, summary, ack_paths)
            if p is None:
                print("SHIP nothing to release: the listed files of %s are already on public" % rev[:10])
                return 0
            ok("%d file(s), %d new: in sync with public, exact projection, preflight passed" % (len(p["want"]),
                                                                                                 len(p["new"])))
            stage = "build"
            if not cfg["land_check"]:
                raise Fail("[public].land_check is not set: nothing proves the projection builds")
            r = tree_check(cache, dev, p["tree"], cfg["land_check"], rev)
            if r.returncode:
                raise Fail("land_check exited %d on the projection:\n%s" % (r.returncode, _tail(r)))
            ok("land_check passed on the projection %s" % p["tree"][:10])
            stage = "ci"
            print("SHIP %-7s ci-sim --projection: no-rom's jobs on the projection in a clean %s ..." % (stage, SIM_BASE),
                  flush=True)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ci_sim(str(dev), "no-rom", rev, True)
            out = buf.getvalue().strip().splitlines()
            if rc:
                raise Fail("no-rom is red on the projection (a file CI needs is unlisted, or a job fails):\n%s" %
                           "\n".join("  " + l for l in out[-30:]))
            ok(out[-1] if out else "no-rom green on the projection")
            if dry_run:
                print("SHIP dry run: would push %s (%s, %d file(s), %d new) and open its PR; nothing written to "
                      "public" % (p["br"], p["sha"][:10], len(p["want"]), len(p["new"])))
                return 0
            stage = "push"
            for x in other:
                r = gh(["pr", "close", str(x["number"]), "--repo", cfg["repo"], "--delete-branch", "--comment",
                        "Replaced by %s." % br])
                if r.returncode:
                    raise Fail("gh pr close %s: %s" % (x["number"], _tail(r, 3)))
                print("SHIP push    closed #%s %s (--replace)" % (x["number"], x["headRefName"]))
            ref, body = _write_release(cache, cfg, p, force=True)
            url = _open_pr(cache, cfg, p, ref, body, force=True)
            m = re.search(r"/pull/(\d+)", url)
            if not m:
                raise Fail("gh pr create printed no PR URL: %s" % url[:200])
            n = int(m[1])
            ok("%s %s pushed; PR #%d %s" % (br, p["sha"][:10], n, url))
        stage = "checks"
        if no_wait:
            print("SHIP checks  wait: PR #%d opened (--no-wait); rerun ship to wait for its checks and merge" % n)
            return 0
        H = ""
        for i in range(polls):
            pr = api("GET", "%s/pulls/%d" % (R, n)) or {}
            H = (pr.get("head") or {}).get("sha") or ""
            runs = (api("GET", "%s/commits/%s/check-runs?per_page=100" % (R, H)) or {}).get("check_runs") or []
            done = {x.get("name") for x in runs if x.get("status") == "completed"}
            red = [x.get("name") for x in runs if x.get("status") == "completed" and x.get("conclusion") != "success"
                   and x.get("name") in cfg["checks"]]
            if red or set(cfg["checks"]) <= done or pr.get("state") != "open":
                break
            if i < polls - 1:
                sleep(SHIP_POLL)
        else:
            raise Fail("PR #%d's checks did not complete in %d min (%s); rerun ship to keep waiting" % (
                n, timeout, ", ".join(sorted(set(cfg["checks"]) - done))))
        _release_head(dev, cfg, cache, rev, br, H, main)
        wf = [f for f in _must(cache, "diff", "--name-only", main, H, "--", ".github/workflows/").split() if f]
        if wf and not merge_reviewed:
            raise Fail("the release changes %s, so a check from it would certify itself. Review the diff:\n  git -C %s "
                       "diff %s %s -- .github/\nthen rerun ship --merge-reviewed" % (", ".join(wf), cache, main[:10],
                                                                                    H[:10]))
        fails, warns, _ = verify_pr(cfg, n, api, release={"br": br, "reviewed": bool(wf)})
        for w in warns:
            print("SHIP checks  WARN %s" % w)
        if fails:
            raise Fail("PR #%d:\n%s\nfix forward: close it, fix in dev, push, ship --replace" % (
                n, "\n".join("  " + f for f in fails)))
        ok("PR #%d at %s: %s green from GitHub Actions%s" % (n, H[:10], ", ".join(cfg["checks"]),
                                                             "; workflow diff reviewed" if wf else ""))
        stage = "merge"
        r = gh(["pr", "merge", str(n), "--repo", cfg["repo"], "--squash", "--admin", "--match-head-commit", H])
        if r.returncode:
            raise Fail("gh pr merge #%d: %s" % (n, _tail(r, 3)))
        ok("PR #%d squash-merged at %s" % (n, H[:10]))
        stage = "verify"
        return _ship_verify(dev, cfg, cache, rev, api, polls, sleep, no_wait)
    except Fail as e:
        print("SHIP %-7s FAIL %s" % (stage, e))
        return 1


# ---- pre-push: the local guard on dev -----------------------------------------------------------------------------

PRE_PUSH = """#!/bin/sh
# psxdecomp split mode: refuses a push of dev to the public repository, the deletion or a force-push of the dev
# branch, and any push from an agent session. Written by `python3 tools/psxd_publish.py hook --install`.
exec python3 "$(git rev-parse --show-toplevel)/%s" pre-push "$@"
""" % VENDORED
ZERO = "0" * 40


def url_slug(url: str) -> str | None:
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url.strip())
    return ("%s/%s" % (m[1], m[2])).lower() if m else None


def pre_push_refusals(dev, url: str, lines: list[str]) -> list[str]:
    """Why git must not push these refs (`<local ref> <local sha> <remote ref> <remote sha>` lines) to url."""
    out = []
    if os.environ.get("CLAUDECODE"):
        out.append("an agent session never pushes (CLAUDECODE is set)")
    try:
        cfg = load_public(dev)
    except Fail as e:
        return out + [str(e)]
    if cfg is None:
        return out
    pub = {cfg["url"].rstrip("/"), cfg["url"].rstrip("/").removesuffix(".git")}
    if url.rstrip("/") in pub or url.rstrip("/").removesuffix(".git") in pub or url_slug(url) == cfg["repo"].lower():
        out.append("%s is the public repository: dev's history never goes there; `release` publishes" % url)
    main = "refs/heads/" + cfg["dev_branch"]
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[2] != main:
            continue
        local, remote = parts[1], parts[3]
        if local == ZERO:
            out.append("deleting %s on %s" % (main, url))
        elif remote != ZERO and _git(dev, "cat-file", "-e", remote + "^{commit}").returncode:
            out.append("%s on %s is at %s, which dev lacks: fetch and merge first (a force-push would drop it)" % (
                main, url, remote[:10]))
        elif remote != ZERO and _git(dev, "merge-base", "--is-ancestor", remote, local).returncode:
            out.append("a force-push of %s to %s (%s is not an ancestor of %s)" % (main, url, remote[:10], local[:10]))
    return out


def push_gate(dev, cfg, sha: str) -> tuple[list[str], list[str], str]:
    """The release gate on the projection of a pushed dev commit, offline (the cache as last fetched, no fetch):
    (blocks, warnings, the release-ready line). Blocks: a listed denied path, symlink or gitlink, a check-public FAIL,
    a failing audit. Warnings: a README lint FAIL, nothing audits the tree, new public paths, nothing new to release."""
    cache = public_cache(dev)
    tree, want, blocks = projection(cache, dev, sha)
    g = gate_checks(cache, dev, cfg, tree, want, sha)
    blocks = blocks + g["paths"] + g["audit"]
    warns = g["readme"] + g["noaudit"]
    pub = _git(cache, "rev-parse", "-q", "--verify", PUB_REF + "^{commit}").stdout.strip()
    new = []
    if pub:
        old = tree_entries(cache, pub) or {}
        new = sorted(p for p in want if p not in old)
        if _must(cache, "rev-parse", pub + "^{tree}") == tree:
            warns.append("nothing new to release: the projection of %s is public main's tree (as last fetched)"
                         % sha[:10])
        elif new:
            warns.append("%d new public path(s) since public main (as last fetched); ship asks you to confirm them: "
                         "%s%s" % (len(new), ", ".join(new[:5]), ", ..." if len(new) > 5 else ""))
    else:
        warns.append("no public main in the cache, so new paths are not counted (before release 1 public has none; "
                     "after it, ship or release --dry-run fetches it)")
    return blocks, warns, "release-ready: %d files, %d new" % (len(want), len(new))


def pre_push_report(dev, url: str, lines: list[str]) -> tuple[list[str], list[str], str]:
    """(blocks, warnings, the last line) for a push: pre_push_refusals, then the gate on each dev-branch tip pushed to
    a remote that is not the public repository."""
    blocks = pre_push_refusals(dev, url, lines)
    cfg = None if blocks else load_public(dev)
    if cfg is None:
        return blocks, [], ""
    warns, last = [], ""
    for line in lines:
        parts = line.split()
        if len(parts) == 4 and parts[2] == "refs/heads/" + cfg["dev_branch"] and parts[1] != ZERO:
            b, w, last = push_gate(dev, cfg, parts[1])
            blocks, warns = blocks + b, warns + w
    return blocks, warns, last


def cmd_pre_push(remote: str, url: str, stdin=None) -> int:
    own_git_env()                                      # git runs the hook in the worktree's root: "." finds dev
    try:
        blocks, warns, last = pre_push_report(repo_root("."), url or remote, (stdin or sys.stdin).read().splitlines())
    except Fail as e:
        blocks, warns, last = [str(e)], [], ""
    for f in blocks:
        _line("PRE-PUSH", "FAIL", f)
    for w in warns:
        _line("PRE-PUSH", "WARN", w)
    if not blocks and not warns and last:
        print("PRE-PUSH %s" % last)
    return 1 if blocks else 0


def hook_path(dev) -> pathlib.Path:
    return pathlib.Path(_must(dev, "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-push"))


@_cmd("HOOK")
def cmd_hook(repo=".", install=False) -> int:
    """Report (or, --install, write) the pre-push hook; never overwrites another hook."""
    dev = repo_root(repo)
    f = hook_path(dev)
    have = _read(f)
    if have == PRE_PUSH and os.access(f, os.X_OK):
        print("HOOK OK %s" % f)
        return 0
    if have is not None and have != PRE_PUSH:
        raise Fail("%s is another hook: merge psxdecomp's into it by hand (see `hook` output of a clean clone)" % f)
    if not install:
        raise Fail("%s is missing: rerun with --install" % f)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(PRE_PUSH, encoding="utf-8")
    f.chmod(0o755)
    print("HOOK written %s" % f)
    return 0


# ---- ci-log: the public CI's log filter ---------------------------------------------------------------------------

CI_LOG_DROP = re.compile(r"asm/|\.s:|[0-9A-Fa-f]{8,}|\b[a-z]{1,7}(?:\.[a-z]+)?\s+\$\w+|\b[gd]label\b")


def ci_log(data: bytes) -> tuple[list[str], int, int, int]:
    """(the last 60 kept lines cut to 200 chars, withheld, kept, total): a build log without asm, hex or instructions."""
    lines = data.decode("utf-8", errors="replace").splitlines()
    kept = [l[:200] for l in lines if not CI_LOG_DROP.search(l)]
    return kept[-60:], len(lines) - len(kept), len(kept), len(lines)


def cmd_ci_log(path) -> int:
    try:
        data = pathlib.Path(path).read_bytes()
    except OSError as e:
        print("CI-LOG 0 line(s) shown of 0, 0 withheld (%s)" % e)
        return 0
    shown, withheld, kept, total = ci_log(data)
    print("\n".join(shown))
    print("CI-LOG %d line(s) shown of %d, %d withheld" % (len(shown), total, withheld))
    return 0


# ---- list: what the list publishes, and --draft: a first list ----------------------------------------------------

REF_FILES = ("Makefile", "*.mk", ".github/workflows/*", "config/*", "tools/*.py", "tools/*.sh")  # their text names paths
PATH_TOKEN = re.compile(r"[\w.-]+(?:/[\w.-]+)+")
DRAFT_HEAD = ("# %s — the files this repository publishes (default deny: a tracked file no entry\n# matches stays "
              "private). An entry ending in `/` is a directory prefix; any other is a glob.\n" % PUBLIC_PATHS_REL)


def draft_list(dev, rev: str) -> tuple[list[str], list[str]]:
    """(entries, warnings) of a first list for dev at rev: every tracked file outside the deny set, a directory with
    nothing private below it folded into `dir/` (so a file added there later is public without an edit: dc2 listed
    tools/ file by file and a new tool stayed behind). A warning names a private path a public build file refers to."""
    tree = tree_entries(dev, rev) or {}
    deny = deny_entries(dev, rev)
    private = {p for p, (mode, _) in tree.items() if is_denied(deny, p) or mode in ("120000", "160000")}
    above = lambda p: ["/".join(p.split("/")[:i]) + "/" for i in range(1, p.count("/") + 1)]  # noqa: E731
    closed = {d for p in private for d in above(p)}
    public = sorted(set(tree) - private)
    entries = list(dict.fromkeys(next((d for d in above(p) if d not in closed), p) for p in public))
    if not is_listed(entries, PUBLIC_PATHS_REL):
        entries.insert(0, PUBLIC_PATHS_REL)
    refs = [p for p in public if is_listed(REF_FILES, p)]
    blobs = read_blobs(dev, [tree[p][1] for p in refs])
    named = {}
    for p in refs:
        for tok in set(PATH_TOKEN.findall(blobs[tree[p][1]][:1 << 20].decode("utf-8", errors="replace"))):
            if tok in private:
                named.setdefault(tok, []).append(p)
    warns = ["%s stays private, and %s name%s it" % (t, ", ".join(by[:3]) + (" and %d more" % (len(by) - 3)
                                                                             if len(by) > 3 else ""),
                                                     "s" if len(by) == 1 else "") for t, by in sorted(named.items())]
    return entries, warns


@_cmd("LIST")
def cmd_list(repo=".", draft=False, rev=None) -> int:
    dev = repo_root(repo)
    rev = _must(dev, "rev-parse", "--verify", "%s^{commit}" % (rev or "HEAD"))
    tree = tree_entries(dev, rev) or {}
    if not draft:
        lst = _dev_list(dev, rev)[0]
        if lst is None:
            raise Fail("%s: missing at %s (list --draft prints a first one)" % (PUBLIC_PATHS_REL, rev[:10]))
        deny = deny_entries(dev, rev)
        paths = [p for p in sorted(tree) if is_listed(lst, p) and not is_denied(deny, p)]
        print("\n".join(paths))
        print("LIST %d of %d tracked file(s) are public at %s" % (len(paths), len(tree), rev[:10]), file=sys.stderr)
        return 0
    entries, warns = draft_list(dev, rev)
    sys.stdout.write(DRAFT_HEAD + "\n".join(entries) + "\n")
    for w in warns:
        print("LIST WARN %s" % w, file=sys.stderr)
    n = sum(is_listed(entries, p) for p in tree)
    print("LIST draft: %d entr%s for %d of %d tracked file(s) at %s, %d warning(s); what must stay private beyond the "
          "agent files goes in [public].deny first" % (len(entries), "y" if len(entries) == 1 else "ies", n, len(tree),
                                                       rev[:10], len(warns)), file=sys.stderr)
    return 0


# ---- ci-sim: a workflow's `run:` steps as written, on a fresh clone of a revision or on its release projection ---

SIM_BASE = "ubuntu:24.04"
# What the steps of the kit's workflows take from GitHub's ubuntu-24.04 runner; everything else they install themselves.
SIM_APT = "git make curl ca-certificates sudo xz-utils unzip python3 python3-venv clang-format build-essential " \
          "software-properties-common"
SIM_EXPR = re.compile(r"\$\{\{\s*(?:runner\.(temp)|matrix\.(exe)|env\.(\w+))\s*\}\}")
SIM_IF = re.compile(r"steps\.([\w-]+)\.outputs\.([\w-]+)\s*==\s*'([^']*)'")
SIM_DRIVER = """set -u
export CI=true GITHUB_ACTIONS=true GITHUB_EVENT_NAME=push GITHUB_REF=refs/heads/main GITHUB_SERVER_URL=https://github.com
export GITHUB_WORKSPACE="$WS" RUNNER_TEMP="$TMP" GITHUB_ENV="$TMP/.env" GITHUB_PATH="$TMP/.path"
mkdir -p "$TMP"; : > "$GITHUB_ENV"; : > "$GITHUB_PATH"; cd "$WS"
export GITHUB_SHA="$(git rev-parse HEAD)"
step() {
  echo "CI-SIM step $1: $3"
  ( while IFS= read -r l; do [ -n "$l" ] && export "$l"; done < "$GITHUB_ENV"
    while IFS= read -r l; do PATH="$l:$PATH"; done < "$GITHUB_PATH"
    [ -n "${SIM_IMAGE:-}" ] && [ -n "${IMAGE:-}" ] && export IMAGE="$SIM_IMAGE"
    export GITHUB_OUTPUT="$TMP/.out.$2"; : > "$GITHUB_OUTPUT"
    cd "$4" && bash -e "$SIM/$1.sh" ) || { echo "CI-SIM FAIL step $1: $3"; exit 1; }
}
"""


def _sim_expr(s: str) -> str:
    return SIM_EXPR.sub(lambda m: "${RUNNER_TEMP}" if m[1] else "${EXE}" if m[2] else "${%s}" % m[3], str(s))


def _yaml_scalar(v: str, keep_hash: bool = False):
    if v[:1] in "\"'" and v[1:].find(v[0]) >= 0:
        return v[1:1 + v[1:].find(v[0])]
    if not keep_hash:
        v = re.sub(r"\s+#.*$", "", v)
    if v.startswith("[") and v.endswith("]"):
        return [_yaml_scalar(x.strip()) for x in v[1:-1].split(",") if x.strip()]
    return v


def parse_yaml(lines: list[str], i: int = 0, indent: int = -1):
    """(value, next line) of the block-style YAML a workflow uses: mappings, `- ` lists, `|` scalars, [a, b] lists.
    Not a YAML parser: this file takes no dependency, and a line it cannot read is a Fail, never a guess."""
    out = None
    while i < len(lines):
        raw = lines[i]
        ind = len(raw) - len(raw.lstrip())
        body = raw[ind:]
        if not body or body.startswith("#"):
            i += 1
            continue
        if out is None:
            if ind <= indent:
                break
            indent = ind
        if ind < indent:
            break
        if ind > indent:
            raise Fail("workflow line %d: indentation not understood: %s" % (i + 1, body[:60]))
        if body.startswith("- "):
            if isinstance(out, dict):
                break
            out = [] if out is None else out
            lines[i] = " " * (ind + 2) + body[2:]
            if re.match(r"[\w.-]+:(\s|$)", body[2:]):
                item, i = parse_yaml(lines, i, ind + 1)
            else:
                item, i = _yaml_scalar(body[2:].strip()), i + 1
            out.append(item)
            continue
        m = re.match(r"([\w.-]+):(?:\s+(.*))?$", body)
        if not m or isinstance(out, list):
            raise Fail("workflow line %d: not understood: %s" % (i + 1, body[:60]))
        out = {} if out is None else out
        key, val, i = m[1], (m[2] or "").strip(), i + 1
        if val[:1] in ("|", ">") and len(val) <= 2:
            blk = []
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > ind):
                blk.append(lines[i])
                i += 1
            w = min((len(l) - len(l.lstrip()) for l in blk if l.strip()), default=0)
            out[key] = "\n".join(l[w:] for l in blk).rstrip("\n") + "\n"
        elif not val or val.startswith("#"):
            out[key], i = parse_yaml(lines, i, ind)
        else:
            out[key] = _yaml_scalar(val, keep_hash=key == "run")
    return out, i


def sim_job(job: dict, simdir: pathlib.Path, exe: str | None, host: bool) -> None:
    """Write job.sh and one N.sh per step into simdir. A `run:` body is copied as written; of `uses:` only checkout,
    setup-python (container only) and upload-artifact (the file exists) are stood in for; no expression is evaluated
    beyond runner.temp, matrix.exe and env.NAME, and one in a `run:` body is a Fail."""
    q = shlex.quote
    push = {"EXE": exe or "", "FORK": "false", "BASE_SHA": "$GITHUB_SHA", "HEAD_SHA": "$GITHUB_SHA", "PR": ""}
    drv = [SIM_DRIVER]
    for k, v in (job.get("env") or {}).items():                         # a push to main: what the job's env resolves to
        drv.append('export %s="%s"' % (k, push.get(k, "") if "${{" in str(v) else str(v).replace('"', '\\"')))
    for n, st in enumerate(job.get("steps") or [], 1):
        uses, w = str(st.get("uses") or ""), st.get("with") or {}
        title = st.get("name") or uses or "run"
        body = ["export %s=\"%s\"" % (k, _sim_expr(v)) for k, v in (st.get("env") or {}).items()]
        if "run" in st:
            body.append(st["run"])
        elif uses.startswith("actions/checkout@") and w.get("repository"):
            dest = q(str(w.get("path") or "."))
            body.append('set -o pipefail\n[ -n "${SIM_PRIVATE:-}" ] || { echo "--private DIR: a local checkout of '
                        '%s"; exit 1; }\nmkdir -p %s\ngit -C "$SIM_PRIVATE" archive "%s" | tar -x -C %s\n'
                        % (_sim_expr(w["repository"]), dest, _sim_expr(w.get("ref") or "HEAD"), dest))
        elif uses.startswith("actions/checkout@"):
            body.append('echo "the tree at $GITHUB_SHA"\n')
        elif uses.startswith("actions/setup-python@") and not host:
            v = q(str(w.get("python-version") or "3"))
            body.append('v=%s\ncommand -v "python$v" > /dev/null || { add-apt-repository -y ppa:deadsnakes/ppa && '
                        'apt-get install -y -qq "python$v" "python$v-venv"; } > /dev/null 2>&1\n'
                        '"python$v" -m venv "/opt/py$v" && echo "/opt/py$v/bin" >> "$GITHUB_PATH"\n' % v)
        elif uses.startswith("actions/upload-artifact@"):
            body.append('[ -s "%s" ] || { echo "nothing to upload at %s"; exit 1; }\necho "CI-SIM would upload %s: '
                        '$(($(wc -c < "%s"))) bytes"\n' % ((_sim_expr(w.get("path", "")),) * 2
                                                      + (_sim_expr(w.get("name", "artifact")), _sim_expr(w.get("path", "")))))
        else:
            body.append("echo %s\n" % q("CI-SIM not simulated: uses %s" % uses))
        text = "\n".join(body)
        if "${{" in text:
            raise Fail("step %d (%s): an expression ci-sim does not evaluate: %s" % (
                n, title, text[text.index("${{"):][:60].splitlines()[0]))
        (simdir / ("%d.sh" % n)).write_text(text, encoding="utf-8")
        call = 'step %d %s %s "%s"' % (n, q(str(st.get("id") or "s%d" % n)), q(title),
                                       _sim_expr(st.get("working-directory") or "$WS"))
        cond = SIM_IF.search(str(st.get("if") or ""))
        if cond:
            call = "if grep -qx %s \"$TMP/.out.%s\" 2> /dev/null; then %s; else echo %s; fi" % (
                q("%s=%s" % (cond[2], cond[3])), cond[1], call, q("CI-SIM skip step %d: %s (its `if`)" % (n, title)))
        drv.append(call)
    (simdir / "job.sh").write_text("\n".join(drv) + "\n", encoding="utf-8")


def sim_tree(dev, rev: str, proj: bool, dest: pathlib.Path) -> None:
    """A repository at dest with one HEAD: a fresh clone of dev at rev (tracked files only: what actions/checkout
    gives dev's CI), or rev's release projection as a first commit (what it gives the public repository's)."""
    if not proj:
        _must(dev, "clone", "-q", "--no-hardlinks", str(dev), str(dest))
        _must(dest, "checkout", "-q", "--detach", rev)
        return
    cache = public_cache(dev)
    tree, _, probs = projection(cache, dev, rev)
    if probs:
        raise Fail("the projection of %s is not publishable:\n%s" % (rev[:10], "\n".join("  " + x for x in probs)))
    dest.mkdir()
    _export(cache, tree, dest)
    _must(dest, "init", "-q", "-b", "main")
    _must(dest, "add", "-A", "-f")
    _must(dest, "-c", "user.name=ci-sim", "-c", "user.email=ci-sim@localhost.invalid", "-c", "commit.gpgsign=false",
          "commit", "-q", "-m", "the projection of %s" % rev)


def _sim_run(argv, env=None) -> int:
    p = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in p.stdout:
        print(line, end="", flush=True)
    return p.wait()


@_cmd("CI-SIM")
def cmd_ci_sim(repo=".", workflow="no-rom", rev=None, proj=False, private=None, image=None, host=None) -> int:
    dev = repo_root(repo)
    rev = _must(dev, "rev-parse", "--verify", "%s^{commit}" % (rev or "HEAD"))
    what = "the projection of %s" % rev[:10] if proj else "a fresh clone at %s" % rev[:10]
    rel = ".github/workflows/%s.yml" % workflow
    results = []
    with tempfile.TemporaryDirectory(prefix="psxd-ci-sim-", ignore_cleanup_errors=True) as td:
        td = pathlib.Path(td).resolve()
        sim_tree(dev, rev, proj, td / "tree")
        text = _read(td / "tree" / rel)
        if text is None:
            raise Fail("%s has no %s%s" % (what, rel, ": %s does not list it" % PUBLIC_PATHS_REL if proj else ""))
        jobs = (parse_yaml(text.splitlines())[0] or {}).get("jobs") or {}
        if host is None:                                               # steps that start containers run on this machine
            host = bool(re.search(r"^\s*(?:id=\$\()?docker\s", "\n".join(
                str(st.get("run", "")) for j in jobs.values() for st in j.get("steps") or []), re.M))
        img = None
        if not host:
            base = image or SIM_BASE
            img = "psxd-ci-sim:" + re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]
            df = ("FROM %s\nRUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq %s > "
                  "/dev/null && git config --system --add safe.directory '*'\n" % (base, SIM_APT))
            r = subprocess.run(["docker", "build", "-q", "-t", img, "-"], input=df, capture_output=True, text=True)
            if r.returncode != 0:
                raise Fail("docker build of %s + the runner's tools: %s" % (base, _tail(r, 5)))
        private = str(pathlib.Path(private).resolve()) if private else ""
        n = 0
        for jid, job in jobs.items():
            exes = (((job.get("strategy") or {}).get("matrix") or {}).get("exe")) or [None]
            for exe in exes if isinstance(exes, list) else [exes]:
                n += 1
                simdir = td / ("sim-%d" % n)
                simdir.mkdir()
                sim_job(job, simdir, exe, host)
                name = _sim_expr(job.get("name") or jid).replace("${EXE}", exe or "")
                print("CI-SIM job %s on %s%s" % (name, what, "" if host else " in %s" % (image or SIM_BASE)), flush=True)
                if host:
                    rc = _sim_run(["bash", str(simdir / "job.sh")], dict(
                        os.environ, SIM=str(simdir), WS=str(td / "tree"), TMP=str(td / ("runner-%d" % n)),
                        SIM_IMAGE=image or "", SIM_PRIVATE=private, GITHUB_REPOSITORY=origin_slug(dev) or ""))
                else:
                    rc = _sim_run(["docker", "run", "--rm", "-v", "%s:/src:ro" % (td / "tree"), "-v",
                                   "%s:/sim:ro" % simdir, "-e", "SIM=/sim", "-e", "WS=/work", "-e", "TMP=/tmp/runner",
                                   img, "bash", "-c", "cp -a /src /work && exec bash /sim/job.sh"])
                results.append((name, rc))
        if host and shutil.which("docker"):                             # containers wrote there as root
            subprocess.run(["docker", "run", "--rm", "-v", "%s:/t" % td, image or SIM_BASE, "chown", "-R",
                            "%d:%d" % (os.getuid(), os.getgid()), "/t"], capture_output=True)
    for name, rc in results:
        _line("CI-SIM", "OK" if rc == 0 else "FAIL", "%s%s" % (name, "" if rc == 0 else " (exit %d)" % rc))
    bad = sum(rc != 0 for _, rc in results)
    print("CI-SIM %s %s on %s: %d job(s)" % ("OK" if results and not bad else "FAIL", rel, what, len(results)))
    return 0 if results and not bad else 1


# ---- the writing checker: the findings of one Markdown text -------------------------------------------------------
# A unit is a paragraph, a list item, a table cell or a heading. Counted: a sentence of a numbered step over STEP_MAX
# words, any other sentence over SENT_MAX; a unit over PARA_MAX sentences; each semicolon in a unit; each contraction.
# A record line (`C0001 | title | tags`, two or more ` | `) is a table row: each field is a cell.
# Not counted: code spans, fences, front matter, metadata lines, comment lines, marker blocks, generated files. For
# the semicolon also: link targets, HTML tags and entities (`&amp;`), bare URLs. A code span, a path or a number is
# one word.
STEP_MAX, SENT_MAX, PARA_MAX = 20, 25, 6
STEP = re.compile(r"^\s*(?:>\s?)*\d+\. ")
SENT_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][*_)\"])|(?<=[.!?][*_]{2}))\s+(?=[A-Z0-9*`(\[\"])")
CONTRACTION = re.compile(r"\b(?:\w+n['’]t|\w+['’](?:ll|re|ve|d|m)|(?:it|that|there|here|what|who|he|she|let)['’]s)\b",
                         re.I)
META = re.compile(r"^[a-z_]+: \S.* · [a-z_]+: ")                 # a `tags: a,b · date: … · origin: …` record line
GENERATED = re.compile(r"[Gg]enerated by .{0,80}do not edit", re.S)
ROW = re.compile(r"^(?!<!--)\S.* \| .* \| ")                   # a record line of an index: its fields are cells
MARK_BEGIN = re.compile(r"<!-- (\S+):begin -->")                 # the first line of a marker block


def _body(lines: list[str]) -> list[str]:
    """The lines with a leading YAML front matter blanked (metadata, not prose); line numbers are kept."""
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end:
            return [""] * (end + 1) + lines[end + 1:]
    return lines


def _prose(lines: list[str]) -> list[str]:
    """`_body`, with every marker block blanked too: a `<!-- x:begin -->` line, the next `<!-- x:end -->` line with
    the same x, and the lines between them. Both lines are outside a fence; a begin line with no end line opens no
    block."""
    out, fence, free = _body(lines), False, []
    for i, l in enumerate(out):
        fence ^= l.strip().startswith("```")
        if not fence:
            free.append(i)
    for n, i in enumerate(free):
        m = MARK_BEGIN.fullmatch(out[i].strip())                    # a blanked line is no begin line and no end line
        if not m:
            continue
        end = "<!-- %s:end -->" % m.group(1)
        j = next((j for j in free[n + 1:] if out[j].strip() == end), None)
        if j is not None:
            out = out[:i] + [""] * (j + 1 - i) + out[j + 1:]
    return out


def _row(line: str) -> bool:
    """A table row, or a record line: two or more ` | ` outside code spans and parentheses."""
    return line.startswith("|") or bool(ROW.match(re.sub(r"\([^()]*\)", "", re.sub(r"`[^`]*`", "x", line))))


def _spans(text: str):
    """(first_line, last_line, text) prose paragraphs: wrapped lines joined, a list item or a heading starts a new
    one."""
    fence, cur, start, last = False, [], 0, 0
    for i, l in enumerate(_prose(text.splitlines()) + [""]):
        s = re.sub(r"^(?:>\s?)+", "", l.strip())                     # a blockquote is prose
        if s.startswith("```"):
            fence = not fence
        skip = fence or s.startswith(("```", "<!--")) or not s or META.match(s) or _row(l)
        if (skip or re.match(r"^(#{1,6} |[-*+] |\d+\. )", s)) and cur:
            yield start, last, " ".join(cur)
            cur = []
        if skip:
            continue
        if not cur:
            start = i + 1
        last = i + 1
        cur.append(re.sub(r"^(#{1,6} |[-*+] |\d+\. )", "", s))


def _words(s: str) -> int:
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"`[^`]*`", "x", re.sub(r"<[^>]+>", " ", s)))
    return sum(1 for w in s.split() if re.search(r"\w", w))


def _bare(s: str) -> str:
    """The unit without the text a writer cannot reword: code spans, link targets, HTML tags and entities, URLs."""
    s = re.sub(r"(`+).+?\1", "x", s)
    s = re.sub(r"\]\([^)]*\)", "]", s)
    s = re.sub(r"</?[A-Za-z][\w-]*(?:\s[^<>]*)?/?>", " ", s)
    s = re.sub(r"&#?\w+;", " ", s)
    return re.sub(r"\bhttps?://\S+", "x", s)


def lint_spans(text: str) -> list[tuple[int, int, str]]:
    """[(first_line, last_line, finding)] of the units of `text`, in the order of the lines."""
    if GENERATED.search(text[:600]):
        return []
    lines = _prose(text.splitlines())
    units = [(a, b, para, STEP_MAX if STEP.match(lines[a - 1]) else SENT_MAX) for a, b, para in _spans(text)]
    fence = False
    for i, l in enumerate(lines):
        fence ^= l.lstrip().startswith("```")
        if not fence and _row(l):
            units += [(i + 1, i + 1, cell, SENT_MAX) for cell in re.split(r"(?<!\\)\|", re.sub(r"`[^`]*`", "`x`", l))]
    out = []
    for a, b, unit, cap in sorted(units):
        counts = [w for w in map(_words, SENT_END.split(unit)) if w]
        out += [(a, b, "%d words in a sentence (at most %d)" % (w, cap)) for w in counts if w > cap]
        if len(counts) > PARA_MAX:
            out.append((a, b, "%d sentences in a paragraph (at most %d)" % (len(counts), PARA_MAX)))
        bare = _bare(unit)
        out += [(a, b, "a semicolon (write two sentences)")] * bare.count(";")
        out += [(a, b, 'a contraction: "%s"' % m.group(0)) for m in CONTRACTION.finditer(bare)]
    return out


def lint_style(text: str) -> list[tuple[int, str]]:
    """[(line_no, finding)]: the writing findings of one Markdown text (the comment above lists what is counted)."""
    return [(a, m) for a, _, m in lint_spans(text)]


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

SELF_LIST = "# the public paths\nconfig/public-paths.txt\nLICENSE\nsrc/\ndocs/*.md\n"
WORLD_LIST = ("# the public paths\nconfig/public-paths.txt\nLICENSE\nREADME.md\nCONTRIBUTING.md\nMakefile\n.gitignore\n"
              "config/categories.tsv\nconfig/discs.tsv\nconfig/medium.sha1\nconfig/check.*.sha\nconfig/*.mk\ndocs/*.md\n"
              "src/\n")
WORLD_PUBLIC = sorted(["config/public-paths.txt", "LICENSE", "README.md", "CONTRIBUTING.md", "Makefile", ".gitignore",
                       "config/categories.tsv", "config/discs.tsv", "config/medium.sha1", "config/check.PSXD_000.01.sha",
                       "config/x.mk", "docs/g.md", "docs/setup.md", "src/a.c", "src/b.c"])
AUDIT_PY = ("import pathlib, sys\n"
            "bad = [str(p) for p in pathlib.Path('.').rglob('*') if p.is_file() and not p.is_symlink()\n"
            "       and p.parts[0] != '.git' and b'MARKER-BYTES' in p.read_bytes()]\n"
            "if bad:\n    print('leak: ' + ', '.join(bad))\nsys.exit(1 if bad else 0)\n")
A_C = "1\n2\n3\n4\n5\n6\n7\n8\n"


def _fake_store(cfg: dict) -> dict:
    R = "repos/" + cfg["repo"]
    env = lambda reviewers: {"protection_rules": [  # noqa: E731
        {"type": "required_reviewers", "prevent_self_review": False,
         "reviewers": [{"type": "User", "reviewer": {"id": 42}}] if reviewers else []}, {"type": "branch_policy"}],
        "can_admins_bypass": False, "deployment_branch_policy": dict(BRANCH_POLICY)}
    pol = lambda: {"branch_policies": [{"id": 1, "name": "main", "type": "branch"}]}  # noqa: E731
    return {R: {**REPO_WANT, "visibility": "public",
                "security_and_analysis": {k: {"status": "enabled"} for k in SECURITY_WANT}},
            R + "/private-vulnerability-reporting": {"enabled": True}, R + "/vulnerability-alerts": {},
            R + "/actions/permissions/workflow": {"default_workflow_permissions": "read",
                                                  "can_approve_pull_request_reviews": False},
            R + "/actions/permissions": {"enabled": True, "allowed_actions": "all", "sha_pinning_required": True},
            R + "/actions/permissions/fork-pr-contributor-approval": {"approval_policy": "all_external_contributors"},
            R + "/actions/permissions/artifact-and-log-retention": {"days": 90},
            R + "/rulesets": [{"id": 1, "name": "main-integrity"}, {"id": 2, "name": "main-review"}],
            R + "/rulesets/1": ruleset_want("main-integrity", cfg["checks"]) | {"id": 1},
            R + "/rulesets/2": ruleset_want("main-review", cfg["checks"]) | {"id": 2},
            "users/example": {"id": 42}, R + "/environments/fork-review": env(True),
            R + "/environments/ci": env(False), R + "/environments/fork-review/deployment-branch-policies": pol(),
            R + "/environments/ci/deployment-branch-policies": pol(),
            R + "/actions/secrets/PRIVATE_DEPLOY_KEY": {"name": "PRIVATE_DEPLOY_KEY"},
            R + "/contents/.github/CODEOWNERS": {"name": "CODEOWNERS"}}


def _fake_api(store: dict, writes: list):
    def api(method, path, body=None):
        if method == "GET":
            return copy.deepcopy(store.get(path))
        writes.append((method, path, body))
        if method == "PUT" and "can_admins_bypass" in (body or {}):
            writes.append(("BAD", path, body))
        if method == "PATCH" and len(set(SQUASH_PAIR) & set(body)) == 1:
            raise Fail("gh api PATCH %s: invalid_squash_commit_setting_combo (HTTP 422)" % path)   # GitHub's rules
        org = method == "PATCH" and (store[path].get("owner") or {}).get("type") == "Organization"
        if method == "PATCH" and "allow_forking" in body and not org:
            raise Fail("gh api PATCH %s: Allow forks setting can only be changed on org-owned private repositories "
                       "(HTTP 422)" % path)
        if method == "PATCH":
            for k, v in body.items():
                store[path].setdefault(k, {}).update(v) if isinstance(v, dict) else store[path].__setitem__(k, v)
        elif method == "POST" and path.endswith("/rulesets"):
            n = len(store[path]) + 1
            store[path].append({"id": n, "name": body["name"]})
            store["%s/%d" % (path, n)] = body | {"id": n}
        elif method == "POST":
            store.setdefault(path, {"branch_policies": []})["branch_policies"].append(
                {"id": 9, "name": body["name"], "type": "branch"})
        elif "/rulesets/" in path:
            store[path] = body | {"id": int(path.rsplit("/", 1)[1])}
        elif "/environments/" in path:
            store[path] = {"protection_rules": [{"type": "required_reviewers", "prevent_self_review": body["prevent_self_review"],
                                                 "reviewers": [{"type": "User", "reviewer": {"id": r["id"]}}
                                                               for r in body["reviewers"]]}],
                           "can_admins_bypass": (store.get(path) or {}).get("can_admins_bypass", False),
                           "deployment_branch_policy": body["deployment_branch_policy"]}
        elif body is None:
            store[path] = {"enabled": True} if "private-vuln" in path else {}
        else:
            store[path] = {**(store.get(path) or {}), **body}
        return {}
    return api


def _pr_store(cfg, fork=False, event="pull_request_target", path=TRUSTED_WORKFLOW, H="a" * 40, conclusion="success",
              title="Fix a", body="", files=("src/a.c",)):
    R = "repos/" + cfg["repo"]
    runs = [{"name": n, "status": "completed", "conclusion": conclusion, "app": {"id": ACTIONS_APP},
             "check_suite": {"id": 100 + i}} for i, n in enumerate(cfg["checks"])]
    wf = [{"id": 900 + i, "check_suite_id": 100 + i, "head_sha": H, "path": path if n.startswith("build ") else
           ".github/workflows/no-rom.yml", "event": event if n.startswith("build ") else "pull_request"}
          for i, n in enumerate(cfg["checks"])]
    return {R + "/pulls/7": {"state": "open", "base": {"ref": "main"}, "title": title, "body": body,
                             "head": {"sha": H, "repo": {"full_name": "fork/synthetic-decomp" if fork else cfg["repo"]}}},
            "%s/commits/%s/check-runs?per_page=100" % (R, H): {"check_runs": runs},
            "%s/actions/runs?head_sha=%s&per_page=100" % (R, H): {"workflow_runs": wf},
            R + "/pulls/7/files?per_page=100": [{"filename": f} for f in files]}


def _public_self_test(check, td: str):
    """check-public, release, import, land, settings and verify-pr on throwaway repositories: nothing real is touched."""
    root = pathlib.Path(td)
    saved, real_gh, real_load = dict(os.environ), gh, load_public
    os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t",
                      GIT_COMMITTER_EMAIL="t@t.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    g = lambda repo, *a: _git(repo, "-c", "commit.gpgsign=false", *a)  # noqa: E731
    tick = [0]
    calls, prs = [], []

    def clock():
        tick[0] += 1
        os.environ.update(GIT_AUTHOR_DATE="2026-03-%02dT10:00:%02d+00:00" % (1 + tick[0] // 50, tick[0] % 50))
        os.environ["GIT_COMMITTER_DATE"] = os.environ["GIT_AUTHOR_DATE"]

    def agent(on):
        os.environ.pop("CLAUDECODE", None)
        if on:
            os.environ["CLAUDECODE"] = "1"

    def call(fn, *a, **k):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(*a, **k)
        return rc, buf.getvalue()

    def put(repo, files: dict):
        for rel, body in files.items():
            f = pathlib.Path(repo) / rel
            if body is None:
                f.unlink()
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")

    def commit(repo, msg, *extra):
        clock()
        g(repo, "add", "-A")
        return g(repo, "commit", "-qm", msg, *extra)

    def tracked(repo):
        return sorted(p for p in _git(repo, "ls-files", "-z").stdout.split("\0") if p)

    def fake_gh(args, inp=None):
        a = list(args)
        calls.append(a)
        if a[:2] == ["pr", "list"]:
            out = json.dumps([{"headRefName": h} for h in prs])
        elif a[:2] == ["pr", "create"]:
            out = "https://example.invalid/pull/1\n"
        elif a[:2] == ["pr", "merge"]:
            out = ""
        else:
            return subprocess.CompletedProcess(a, 1, "", "unexpected gh " + " ".join(a))
        return subprocess.CompletedProcess(a, 0, out, "")

    @contextlib.contextmanager
    def with_cfg(**over):
        globals()["load_public"] = lambda repo, rev=None: (lambda c: None if c is None else c | over)(real_load(repo, rev))
        try:
            yield
        finally:
            globals()["load_public"] = real_load

    class World:
        """A dev repository, the bare 'GitHub' public repository, a working clone of it for contributors."""

        def __init__(self, name):
            self.root = root / name
            self.dev, self.gh, self.wc = self.root / "dev", self.root / "gh.git", self.root / "wc"
            self.dev.mkdir(parents=True)
            self.gh.mkdir()
            for r, bare in ((self.dev, []), (self.gh, ["--bare"])):
                g(r, "init", "-q", *bare)
                g(r, "symbolic-ref", "HEAD", "refs/heads/main")
            g(self.dev, "config", "user.name", "Dev")
            g(self.dev, "config", "user.email", "dev@x.invalid")
            g(self.dev, "remote", "add", "origin", "https://github.com/example/synthetic-decomp.git")
            (self.root / "audit.py").write_text(AUDIT_PY, encoding="utf-8")
            put(self.dev, {PUBLIC_PATHS_REL: WORLD_LIST, "LICENSE": "lic\n", "src/a.c": A_C, "src/b.c": "b1\n",
                           "docs/g.md": "g1\n", "docs/setup.md": "# Setup\n", "docs/priv.txt": "p\n",
                           "CONTRIBUTING.md": "# C\n", "CLAUDE.md": "agents\n", "phase-ends/x.md": "private\n",
                           "internal/n.c": "n\n", ".claude/pa3-managed.json": '{"files": {"tools/pa3_tool.py": "h"}}',
                           "tools/pa3_tool.py": "t\n", "config/categories.tsv": SELF_TSV, "config/discs.tsv": SELF_DISCS,
                           "config/medium.sha1": SELF_MEDIUM, "config/check.PSXD_000.01.sha": SELF_CHECK,
                           "Makefile": SELF_MAKE, "config/x.mk": "format:\n\techo f\n", ".gitignore": "/disks/\n",
                           CONFIG_REL: self.toml()})
            put(self.dev, {"README.md": render(SELF_README, Ctx(self.dev))})
            commit(self.dev, "dev 1")
            self.cache = public_cache(self.dev)
            self.d1 = self.head()

        def toml(self, **over):
            c = dict(repo="example/synthetic-decomp", url=str(self.gh), dev_branch="main", deny=["internal/"],
                     checks=["build PSXD_000.01", "public-clean audit (no game bytes)"],
                     image="ghcr.io/example/psx-toolchain@sha256:" + "a" * 64, private_repo="example/synthetic-private",
                     private_rev="b" * 40, land_check=["true"],
                     audit=[sys.executable, str(self.root / "audit.py")]) | over
            return "[public]\n" + "".join("%s = %s\n" % (k, json.dumps(v)) for k, v in c.items())

        def head(self):
            return _git(self.dev, "rev-parse", "HEAD").stdout.strip()

        def rel(self, **k):
            return call(cmd_release, str(self.dev), **k)

        def imp(self, **k):
            return call(cmd_import, str(self.dev), **k)

        def land(self):
            return call(cmd_land, str(self.dev))

        def branches(self):
            return _git(self.cache, "for-each-ref", "--format=%(refname)", "refs/heads/release/").stdout.split()

        def state(self):
            return history(self.cache, self.dev, fetch_public(self.cache, str(self.gh)))

        def ref(self, name):
            return _git(self.cache, "rev-parse", "-q", "--verify", name).stdout.strip()

        @contextlib.contextmanager
        def variant(self, files=None, mut=None, add=True):
            """One throwaway dev commit, undone afterwards."""
            put(self.dev, files or {})
            if mut:
                mut()
            if add:
                commit(self.dev, "variant")
            else:
                clock()
                g(self.dev, "commit", "-qm", "variant")
            try:
                yield
            finally:
                g(self.dev, "reset", "-q", "--hard", "HEAD~1")

        def sync(self):
            if not (self.wc / ".git").exists():
                _must(self.root, "clone", "-q", str(self.gh), str(self.wc))
                g(self.wc, "config", "user.name", "Wc")
                g(self.wc, "config", "user.email", "wc@x.invalid")
            g(self.wc, "fetch", "-q", "origin")
            if g(self.wc, "rev-parse", "-q", "--verify", "origin/main").returncode == 0:
                _must(self.wc, "checkout", "-q", "-B", "main", "origin/main")

        def contrib(self, files, msg, mut=None, author="Con Tributor <con@x.invalid>"):
            self.sync()
            put(self.wc, files)
            if mut:
                mut(self.wc)
            clock()
            g(self.wc, "add", "-A")
            _must(self.wc, "-c", "commit.gpgsign=false", "commit", "-qm", msg, "--author", author)
            _must(self.wc, "push", "-q", "origin", "HEAD:main")
            return _must(self.wc, "rev-parse", "HEAD")

        def squash(self, br, n):
            """GitHub's squash merge of a release PR: PR title + body as the commit message."""
            self.sync()
            _must(self.wc, "fetch", "-q", str(self.cache), "refs/heads/" + br)
            subj, _, rest = _must(self.wc, "log", "-1", "--format=%B", "FETCH_HEAD").partition("\n\n")
            born = g(self.wc, "rev-parse", "-q", "--verify", "HEAD").returncode == 0
            _must(self.wc, "merge", "--squash", "-q", "FETCH_HEAD") if born else _must(
                self.wc, "reset", "-q", "--hard", "FETCH_HEAD")
            clock()
            _must(self.wc, "-c", "commit.gpgsign=false", "commit", "-q", *([] if born else ["--amend"]), "-m",
                  "%s (#%d)\n\n%s" % (subj, n, rest))
            _must(self.wc, "push", "-q", "origin", "HEAD:main")
            return _must(self.wc, "rev-parse", "HEAD")

        def rewind(self, sha):
            self.sync()
            _must(self.wc, "push", "-q", "-f", "origin", "%s:refs/heads/main" % sha)

    try:
        # ---- check-public: a clean tree passes; each negative control FAILs (or WARNs) on the named path
        chk = root / "chk"
        chk.mkdir()
        g(chk, "init", "-q")
        put(chk, {PUBLIC_PATHS_REL: SELF_LIST, "LICENSE": "x\n", "src/a.c": "a\n", "docs/g.md": "g\n"})
        g(chk, "add", "-A")
        check("public clean passes", check_public(chk) == [], check_public(chk))
        put(chk, {"notes.txt": "n\n"})
        g(chk, "add", "-A")
        check("public unlisted FAILs", [(a, b.split(":")[0]) for a, b in check_public(chk)] == [("FAIL", "notes.txt")],
              check_public(chk))
        g(chk, "rm", "-qf", "notes.txt")
        put(chk, {PUBLIC_PATHS_REL: SELF_LIST + ".claude/\n", ".claude/x": "x\n"})
        g(chk, "add", "-A")
        check("public listed agent path FAILs", any(a == "FAIL" and b.startswith(".claude/x")
                                                           for a, b in check_public(chk)), check_public(chk))
        put(chk, {PUBLIC_PATHS_REL: SELF_LIST + "tools/*.py\n", ".claude/x": None})
        g(chk, "add", "-A")
        check("public dead entry WARNs", [a for a, b in check_public(chk)] == ["WARN"], check_public(chk))
        check("public CLI exit codes", call(cmd_check_public, str(chk))[0] == 0, call(cmd_check_public, str(chk)))
        (chk / PUBLIC_PATHS_REL).unlink()
        check("public missing list FAILs", [a for a, b in check_public(chk)] == ["FAIL"], check_public(chk))
        check("public CLI exit 1", call(cmd_check_public, str(chk))[0] == 1)
        check("match: prefix, glob, miss", is_listed(["src/"], "src/a/b.c") and is_listed(["docs/*.md"], "docs/a/b.md")
              and not is_listed(["docs/*.md"], "docs/b.txt") and not is_listed([], "x"))
        c2 = root / "chk2"
        c2.mkdir()
        g(c2, "init", "-q")
        put(c2, {PUBLIC_PATHS_REL: SELF_LIST + "tools/x.py\n", "tools/x.py": "x\n", "src/a.c": "a\n", "docs/g.md": "g\n",
                 PA3_REL: '{"files": {"tools/x.py": "h"}}'})
        g(c2, "add", "-A")
        found = check_public(c2)
        check("public PA3-managed path FAILs", ("FAIL", "tools/x.py") in [(a, b.split(":")[0]) for a, b in found]
              and not any(b.startswith("src/a.c") for a, b in found), found)
        put(c2, {CONFIG_REL: '[public]\nrepo = "o/r"\ndeny = ["docs/"]\n'})
        g(c2, "add", "-A")
        check("public [public].deny path FAILs", ("FAIL", "docs/g.md") in [(a, b.split(":")[0]) for a, b in
                                                                         check_public(c2)], check_public(c2))
        bad = root / "badcfg"
        bad.mkdir()
        put(bad, {CONFIG_REL: '[public]\nrepo = 3\n'})
        try:
            load_public(bad)
            check("config: bad table is an error", False)
        except Fail as e:
            check("config: bad table is an error", "repo" in str(e), e)
        check("config: missing table is off", load_public(chk) is None)
        put(bad, {CONFIG_REL: '[public]\nrepo = "o/r"\nkeyed = {"config/u.tsv" = "2"}\n'})
        try:
            load_public(bad)
            check("config: a keyed column count must be an integer", False)
        except Fail as e:
            check("config: a keyed column count must be an integer", "keyed.config/u.tsv" in str(e), e)
        put(bad, {CONFIG_REL: '[public]\nrepo = "o/r"\nkeyed = {"config/u.tsv" = 2}\n'})
        check("config: keyed parses", load_public(bad)["keyed"] == {"config/u.tsv": 2})
        KB = "# units\n# alias\tstart\tunit\tend\na\t1\tu1\nb\t2\tu2\n"

        def km(o, t, b=KB, n=2):
            r = keyed_merge(o.encode(), b.encode(), t.encode(), n)
            return None if r is None else r.decode()
        check("keyed: a different-alias append on each side merges, ours first",
              km(KB + "a\t3\tu3\n", KB + "c\t9\tu9\n") == KB + "a\t3\tu3\nc\t9\tu9\n")
        narrow = KB.replace("a\t1\tu1\n", "a\t1\tu1\t4\n")
        check("keyed: a row narrowed on one side merges", km(narrow, KB + "c\t9\tu9\n") == narrow + "c\t9\tu9\n"
              and km(KB + "c\t9\tu9\n", narrow) == narrow + "c\t9\tu9\n")
        check("keyed: the same change on both sides merges", km(narrow, narrow) == narrow)
        check("keyed: the same key changed two ways refuses", km(narrow, KB.replace("u1\n", "u1\t5\n")) is None)
        check("keyed: deleted on one side, changed on the other refuses", km(KB.replace("a\t1\tu1\n", ""), narrow) is None)
        check("keyed: a key added two ways refuses", km(KB + "c\t9\tx\n", KB + "c\t9\ty\n") is None)
        check("keyed: a deletion on one side merges", km(KB.replace("b\t2\tu2\n", ""), KB + "c\t9\tu9\n") ==
              "# units\n# alias\tstart\tunit\tend\na\t1\tu1\nc\t9\tu9\n")
        check("keyed: their comment edit refuses", km(KB + "a\t3\tu3\n", KB.replace("# units", "# units!")) is None)
        check("keyed: a duplicate key or a short row refuses", km(KB + "a\t1\tdup\n", KB) is None and
              km(KB + "z\n", KB) is None)
        put(bad, {CONFIG_REL: '[public]\nrepo = "o/r"\nassisted_by = "Claude\\nSigned-off-by: x"\n'})
        try:
            load_public(bad)
            check("config: a multi-line assisted_by is an error", False)
        except Fail as e:
            check("config: a multi-line assisted_by is an error", "assisted_by" in str(e), e)

        # ---- the main world: dev, public, a contributor
        globals()["gh"] = fake_gh
        agent(True)                                              # the shell of an agent session, as in CI and here
        M = World("m")
        rc, out = M.rel(summary="first", ack_new=True)
        check("release refused as agent", rc == 1 and "CLAUDECODE" in out and not M.branches(), out)
        rc, out = M.rel(summary="first", ack_new=True, dry_run=True)
        check("dry-run allowed as agent", rc == 0 and "no ref written" in out and not M.branches(), out)
        check("dry-run lists the listed files", "  A src/a.c" in out and "CLAUDE.md" not in out
              and "phase-ends" not in out, out)
        agent(False)
        off = root / "off"
        off.mkdir()
        _self_repo(str(off))
        rc, out = call(cmd_release, str(off), summary="x")
        check("split mode off refuses", rc == 1 and "split mode is off" in out, out)
        with with_cfg(url=str(M.dev)):
            rc, out = M.rel(summary="first", ack_new=True, dry_run=True)
        check("a URL that reaches dev's history refuses (the rename's redirect)", rc == 1 and "dev's own history" in out
              and not M.branches(), out)
        rc, out = M.rel(summary="first")
        check("new paths refused w/o --ack-new", rc == 1 and "--ack-new" in out and not M.branches(), out)
        rc, out = M.rel(summary=" ", ack_new=True)
        check("summary required", rc == 1 and "--summary" in out and not M.branches(), out)
        rc, out = M.rel(summary="x", rev="nosuchrev", ack_new=True)
        check("release bad rev FAILs", rc == 1 and "no such commit" in out, out)

        def refuses(label, word, files=None, mut=None, add=True, **kw):
            with M.variant(files, mut, add):
                rc, out = M.rel(summary="first", ack_new=True, **kw)
            check(label, rc == 1 and word in out and not M.branches(), out)
        refuses("listed symlink refuses", "symlink", mut=lambda: os.symlink("a.c", M.dev / "src" / "l"))
        refuses("listed gitlink refuses", "gitlink", add=False,
                mut=lambda: g(M.dev, "update-index", "--add", "--cacheinfo", "160000,%s,src/mod" % M.d1))
        refuses("listed CLAUDE.md refuses", "CLAUDE.md", {PUBLIC_PATHS_REL: WORLD_LIST + "CLAUDE.md\n"})
        refuses("listed [public].deny refuses", "internal/n.c", {PUBLIC_PATHS_REL: WORLD_LIST + "internal/\n"})
        refuses("listed PA3 path refuses", "tools/pa3_tool.py", {PUBLIC_PATHS_REL: WORLD_LIST + "tools/pa3_tool.py\n"})
        refuses("audit marker refuses, no ref", "audit", {"src/leak.c": "MARKER-BYTES\n"})
        refuses("README linking unlisted path", "docs/priv.txt",
                {"README.md": (M.dev / "README.md").read_text() + "\nSee [p](docs/priv.txt).\n"})
        with with_cfg(audit=[]):
            rc, out = M.rel(summary="first", ack_new=True)
        check("no audit configured refuses", rc == 1 and "tools/audit_public.py" in out and not M.branches(), out)

        rc, out = M.rel(summary="first", ack_new=True)
        br = "release/" + M.d1[:10]
        rsha = M.ref("refs/heads/" + br)
        check("release 1 unpushed: prints the push to main", rc == 0 and rsha != "" and
              "%s:refs/heads/main" % rsha in out and "gh pr" not in out, out)
        _git(M.cache, "update-ref", "-d", "refs/heads/" + br)
        rc, out = M.rel(summary="first", ack_new=True)
        check("same inputs, same commit sha", rc == 0 and M.ref("refs/heads/" + br) == rsha, out)
        rc, out = M.rel(summary="first", ack_new=True)
        check("a rerun reuses the branch", rc == 0 and M.ref("refs/heads/" + br) == rsha, out)
        msg = _must(M.cache, "log", "-1", "--format=%B", rsha).splitlines()
        check("message ends with the three trailers", [l.split(":")[0] for l in msg[-3:]] == list(RELEASE_TRAILERS)
              and msg[-1] == "Release-Base: none" and msg[0] == "Release: first", msg)
        check("no [public].assisted_by, no Assisted-by", not any(l.startswith("Assisted-by") for l in msg), msg)
        tagged = release_body("s", "a" * 40, "b" * 40, None, "Claude Code (Opus 5.5)")
        parsed = _must(M.cache, "interpret-trailers", "--parse", inp=tagged).splitlines()
        check("Assisted-by heads the trailer block, Release-* stay last", [l.split(":")[0] for l in parsed] == [
            "Assisted-by"] + list(RELEASE_TRAILERS) and parsed[0] == "Assisted-by: Claude Code (Opus 5.5)", parsed)
        src = _read(pathlib.Path(__file__))
        check("no checkbox disclosure is left", src is not None and ("AI use " + "disclosed") not in src)
        check("release 1 is the exact projection", sorted(tree_entries(M.cache, rsha)) == WORLD_PUBLIC,
              sorted(tree_entries(M.cache, rsha)))
        prs[:] = ["release/old"]
        rc, out = M.rel(summary="first", ack_new=True, push=True)
        check("release 1 --push writes public main, no PR", rc == 0 and _must(M.gh, "rev-parse", "main") == rsha
              and not [c for c in calls if c[:1] == ["pr"]] and g(M.gh, "branch", "--list", "release/*").stdout.strip()
              == "", (out, calls))
        prs.clear()
        s1 = rsha
        rels, contribs = M.state()
        check("the real release is recognized", len(rels) == 1 and rels[0][1:] == (M.d1, _must(
            M.cache, "rev-parse", rsha + "^{tree}")) and contribs == [] and rels[0][0] == rsha, rels)
        rc, out = M.rel(summary="first")
        check("release again: nothing to release", rc == 0 and "nothing to release" in out, out)

        # ---- imports refused (each rewinds public main to the release squash)
        def refused(label, word, files, msg="x", mut=None, rewind=True, **kw):
            before = M.ref("refs/psxdecomp/import")
            c = M.contrib(files, msg, mut)
            rc, out = M.imp(**kw)
            check(label, rc == 1 and word in out and "nothing written" in out and M.ref("refs/psxdecomp/import") == before,
                  out)
            if rewind:
                M.rewind(s1)
            return c
        refused("denied CLAUDE.md refused", "CLAUDE.md: denied", {"CLAUDE.md": "x\n"})
        refused("PA3-managed path refused", "tools/pa3_tool.py: denied", {"tools/pa3_tool.py": "y\n"})
        refused("[public].deny path refused", "internal/n.c: denied", {"internal/n.c": "z\n"})
        refused("unlisted path refused", "notes.txt: listed by neither", {"notes.txt": "n\n"})
        refused("imported symlink refused", "src/l: a symlink", {}, mut=lambda wc: os.symlink("a.c", wc / "src" / "l"))
        refused("governance refused by default", "--accept-governance", {"Makefile": SELF_MAKE + "x:\n\techo x\n"},
                rewind=False)
        rc, out = M.imp(accept_governance=True)
        check("--accept-governance imports it", rc == 0 and "IMPORT ready" in out, out)
        M.rewind(s1)
        with M.variant(mut=lambda: (M.dev / "src" / "b.c").unlink()):
            refused("delete vs modify conflict refused", "src/b.c: conflicts", {"src/b.c": "b2\n"})
        with M.variant({"src/a.c": A_C + "dev\t9\n"}):
            refused("an append on both sides refused (path not keyed)", "src/a.c: conflicts",
                    {"src/a.c": A_C + "con\t9\n"}, rewind=False)
            with with_cfg(keyed={"src/a.c": 1}):
                rc, out = M.imp()
            got = read_blobs(M.cache, [tree_entries(M.cache, M.ref("refs/psxdecomp/import"))["src/a.c"][1]])
            check("[public].keyed merges both appends, ours first", rc == 0 and list(got.values())[0].decode() ==
                  A_C + "dev\t9\ncon\t9\n", out)
            M.rewind(s1)
        for label, text in (("Revert \"Release: \" refused", 'Revert "Release: first"\n\nThis reverts commit %s.\n'),
                            ("'This reverts' a release refused", "Undo\n\nThis reverts commit %s.\n")):
            refused(label, "reverts a release", {"src/a.c": "r\n"}, text % rels[0][0])
        sk = M.contrib({"CLAUDE.md": "x\n"}, "Skip me")
        rc, out = M.imp(skip=[sk[:10]])
        tip = M.ref("refs/psxdecomp/import")
        check("--skip records Import-Skipped", rc == 0 and "Import-Skipped: by the maintainer" in _must(
            M.cache, "log", "-1", "--format=%B", tip) and _must(M.cache, "rev-parse", tip + "^{tree}") == _must(
            M.cache, "rev-parse", M.d1 + "^{tree}"), out)
        M.rewind(s1)
        rtree = rels[0][2]
        forged = M.contrib({"src/a.c": "forged\n"}, "Release: x\n\nbody\n\nRelease-Of: %s\nRelease-Tree: %s\nRelease-Base: none\n"
                           % (M.d1, rtree))
        wrong = M.contrib({"src/a.c": "forged2\n"}, "Release: y\n\nRelease-Of: %s\nRelease-Tree: %s\nRelease-Base: none\n"
                          % ("1" * 40, "0" * 40))
        rels2, contribs2 = M.state()
        check("replayed Of/Tree is no release", len(rels2) == 1 and forged in contribs2, (rels2, contribs2))
        check("wrong Tree is no release", wrong in contribs2 and contribs2 == [forged, wrong], contribs2)
        M.rewind(s1)

        # ---- the round trip: a contributor edit/add/delete, dev's own work, import, land, release
        a_c1 = A_C.replace("2\n", "two\n")
        c1 = M.contrib({"src/a.c": a_c1, "src/c.c": "c1\n", "src/b.c": None}, "Fix a (#2)\n\nbody\n\nCo-authored-by: Pair "
                       "<pair@x.invalid>\n")
        put(M.dev, {"docs/g.md": "g2\n", "phase-ends/y.md": "p2\n"})
        commit(M.dev, "dev 2")
        rc, out = M.rel(summary="second")
        check("release refused while c1 pends", rc == 1 and c1[:10] in out and "Fix a" in out and "import" in out
              and M.branches() == ["refs/heads/" + br], out)
        before = (M.head(), g(M.dev, "status", "--porcelain").stdout, g(M.dev, "diff", "--cached").stdout)
        rc, out = M.imp()
        after = (M.head(), g(M.dev, "status", "--porcelain").stdout, g(M.dev, "diff", "--cached").stdout)
        tip, base = M.ref("refs/psxdecomp/import"), M.ref("refs/psxdecomp/import-base")
        check("import leaves HEAD, index, worktree", rc == 0 and before == after and after[1:] == ("", "")
              and base == M.head(), (out, before, after))
        check("author is the contributor", _must(M.cache, "log", "-1", "--format=%an <%ae>", tip) ==
              "Con Tributor <con@x.invalid>" and _must(M.cache, "log", "-1", "--format=%cn", tip) == "Dev"
              and re.fullmatch(r"Import \d{4}-\d{2}-\d{2}: Fix a \(#2\)", _subject(M.cache, tip)), out)
        body = _must(M.cache, "log", "-1", "--format=%B", tip)
        check("Imported-From and Co-authored-by", "Imported-From: " + c1 in body and
              body.rstrip().endswith("Co-authored-by: Pair <pair@x.invalid>"), body)
        names = _must(M.cache, "diff", "--name-only", base, tip).split()
        check("imports the listed src/ change", names == ["src/a.c", "src/b.c", "src/c.c"] and "src/b.c" not in
              tree_entries(M.cache, tip), names)
        rc, out = M.imp()
        check("import is deterministic", rc == 0 and M.ref("refs/psxdecomp/import") == tip, out)
        agent(True)
        h = M.head()
        rc, out = M.land()
        check("land refused as agent", rc == 1 and "CLAUDECODE" in out and M.head() == h, out)
        agent(False)

        dev_url, ref = "https://github.com/example/synthetic-decomp-dev.git", "refs/heads/main"
        ff = ["%s %s %s %s" % (ref, h, ref, M.d1)]
        check("pre-push: a fast-forward to -dev passes", pre_push_refusals(M.dev, dev_url, ff) == [],
              pre_push_refusals(M.dev, dev_url, ff))
        for label, url, lines, word in (
                ("the public slug", "git@github.com:Example/synthetic-decomp.git", ff, "public repository"),
                ("the public url", str(M.gh), ff, "public repository"),
                ("deleting main", dev_url, ["(delete) %s %s %s" % (ZERO, ref, h)], "deleting"),
                ("a force-push", dev_url, ["%s %s %s %s" % (ref, M.d1, ref, h)], "force-push"),
                ("an unknown remote tip", dev_url, ["%s %s %s %s" % (ref, h, ref, "e" * 40)], "fetch")):
            got = pre_push_refusals(M.dev, url, lines)
            check("pre-push refuses %s" % label, any(word in x for x in got), got)
        agent(True)
        got = pre_push_refusals(M.dev, dev_url, ff)
        agent(False)
        check("pre-push refuses any push from an agent session", any("CLAUDECODE" in x for x in got), got)
        hp = hook_path(M.dev)
        r1, r2, r3 = call(cmd_hook, str(M.dev)), call(cmd_hook, str(M.dev), install=True), call(cmd_hook, str(M.dev))
        check("hook: missing FAILs, --install writes it, then OK", r1[0] == 1 and r2[0] == 0 and r3[0] == 0 and
              os.access(hp, os.X_OK) and _read(hp) == PRE_PUSH, (r1, r2, r3))
        hp.write_text("#!/bin/sh\nexit 0\n")
        rc, out = call(cmd_hook, str(M.dev), install=True)
        check("hook: another hook is never overwritten", rc == 1 and "another hook" in out and
              _read(hp) == "#!/bin/sh\nexit 0\n", out)
        hp.unlink()

        def no_land(label, word, setup, undo=lambda: None):
            setup()
            rc, out = M.land()
            undo()
            check(label, rc == 1 and word in out and M.head() == h, out)
        run = M.dev / ".run"
        no_land("status task set refuses", "status.json", lambda: put(run, {"status.json": json.dumps(
            {"task": "fixture-task", "kind": None, "waiting": None})}), lambda: shutil.rmtree(run))
        no_land("live warmer refuses", "warmer r1", lambda: put(run, {
            "status.json": json.dumps({"task": None, "kind": None, "waiting": None, "router_session": "r1"}),
            "warmer/r1.pid": str(os.getpid())}), lambda: shutil.rmtree(run))
        import fcntl
        put(run, {"gate/locks/a.lock": ""})
        fd = os.open(str(run / "gate/locks/a.lock"), os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        no_land("held flock refuses", "flock", lambda: None, lambda: (os.close(fd), shutil.rmtree(run)))
        cur = M.dev / "phase-ends/current"
        no_land("INBOX bullet refuses", "INBOX.md", lambda: put(cur, {"INBOX.md": "# in\n- item\n"}),
                lambda: shutil.rmtree(cur))
        tmpl = "# INBOX\n\n<!-- Freeform bullets.\n- an example inside the comment -->\n\n- <note, or question>\n"
        check("INBOX: the template's placeholder and commented bullets are not pending (PA3's rule)",
              inbox_pending(tmpl) == [] and inbox_pending(tmpl + "- fix X\n  and Y\n") == ["fix X and Y"],
              inbox_pending(tmpl))
        no_land("REVIEW.md refuses", "REVIEW.md", lambda: put(cur, {"REVIEW.md": "r\n"}), lambda: shutil.rmtree(cur))
        row = ["W1", "x", "x", "-", "x", "d", "x", "x", "x", "x", "x", "f", "done"]
        no_land("open wave refuses", "waves.tsv", lambda: put(M.dev, {"config/waves.tsv": "# w\nid\n%s\n" % "\t".join(row)}),
                lambda: (M.dev / "config/waves.tsv").unlink())
        no_land("harvest without .ok refuses", "W1.start.json", lambda: put(M.dev, {"campaign/harvest/W1.start.json": "{}"}),
                lambda: shutil.rmtree(M.dev / "campaign"))
        no_land("HEAD moved refuses", "import base", lambda: (clock(), g(M.dev, "commit", "--allow-empty", "-qm", "m")),
                lambda: g(M.dev, "reset", "-q", "--hard", "HEAD~1"))
        no_land("dirty tracked file refuses", "dirty", lambda: put(M.dev, {"LICENSE": "changed\n"}),
                lambda: g(M.dev, "checkout", "--", "LICENSE"))
        with with_cfg(land_check=["false"]):
            rc, out = M.land()
        check("failing land_check refuses", rc == 1 and "land_check exited 1" in out and M.head() == h, out)
        with with_cfg(land_check=[]):
            rc, out = M.land()
        check("missing land_check refuses", rc == 1 and "land_check is not set" in out and M.head() == h, out)
        rc, out = M.land()
        check("idle land fast-forwards", rc == 0 and "LAND OK" in out and "1 import commit(s)" in out
              and M.head() == tip, out)
        with M.variant({PUBLIC_PATHS_REL: WORLD_LIST.replace("src/\n", "src/a.c\nsrc/b.c\n")}):
            rc, out = M.rel(summary="x", ack_new=True, dry_run=True)
        check("a path left the list: D", "  D src/c.c" in out, out)
        pre2, br2 = _must(M.gh, "rev-parse", "main"), "release/" + M.head()[:10]
        prs[:] = ["release/old"]
        with with_cfg(assisted_by="Claude Code (Opus 5.5)"):
            rc, out = M.rel(summary="second", push=True)
        check("release 2 --push refused, open PR", rc == 1 and "open release PR" in out
              and g(M.gh, "branch", "--list", "release/*").stdout.strip() == "", out)
        prs.clear()
        calls.clear()
        with with_cfg(assisted_by="Claude Code (Opus 5.5)"):
            rc, out = M.rel(summary="second", push=True)
        create = next((c for c in calls if c[:2] == ["pr", "create"]), [])
        check("release 2 goes back to the PR path", rc == 0 and g(M.gh, "rev-parse", "-q", "--verify", br2).returncode
              == 0 and create[create.index("--base") + 1:][:1] == ["main"] and br2 in create and "Release-Tree:" in (
                  _read(create[create.index("--body-file") + 1]) or "") and _must(M.gh, "rev-parse", "main") == pre2,
              out)
        r2 = M.ref("refs/heads/" + br2)
        check("[public].assisted_by becomes the release's Assisted-by", trailers(M.cache, r2, "Assisted-by") == [
            "Claude Code (Opus 5.5)"] and "Assisted-by: Claude Code (Opus 5.5)" in (
                _read(M.cache / ("PR_BODY-%s.md" % M.head()[:10])) or ""), trailers(M.cache, r2, "Assisted-by"))
        main1 = M.ref(PUB_REF)
        check("land, then a release passes the sync check", rc == 0 and r2 != "", out)
        t2 = tree_entries(M.cache, r2)
        check("round trip: release 2 is dev's work only", _must(M.cache, "diff", "--name-only", main1, r2).split() ==
              ["docs/g.md"] and "src/c.c" in t2 and "src/b.c" not in t2 and "phase-ends/y.md" not in t2, t2)

        # ---- a contributor commit merged while the release PR is open is imported by commit afterwards
        a_c2 = a_c1.replace("1\n", "ONE\n", 1)
        c2 = M.contrib({"src/a.c": a_c2}, "Tweak a (#3)")
        M.squash("release/" + M.head()[:10], 4)
        put(M.dev, {"src/a.c": a_c1.replace("7\n", "dev7\n")})
        commit(M.dev, "dev 3")
        rels3, contribs3 = M.state()
        rc, out = M.rel(summary="third")
        check("the squashed Assisted-by release is recognized", trailers(M.cache, rels3[-1][0], "Assisted-by") == [
            "Claude Code (Opus 5.5)"] and _subject(M.cache, rels3[-1][0]) == "Release: second (#4)"
              if len(rels3) == 2 else False, rels3)
        check("release refused, names c2 only", len(rels3) == 2 and rc == 1 and c2[:10] in out and c1[:10] not in out, out)
        rc, out = M.imp()
        merged = read_blobs(M.cache, [tree_entries(M.cache, M.ref("refs/psxdecomp/import"))["src/a.c"][1]])
        check("import merges 3-way with dev's edit", rc == 0 and list(merged.values())[0].decode() ==
              a_c2.replace("7\n", "dev7\n"), out)
        rc, out = M.land()
        check("land the second import", rc == 0 and "LAND OK" in out, out)
        rc, out = M.rel(summary="third")
        b3 = "release/" + M.head()[:10]
        check("round trip: release 3 is dev's edit only", rc == 0 and _must(M.cache, "diff", "--name-only", M.ref(PUB_REF),
                                                                           M.ref("refs/heads/" + b3)).split() == ["src/a.c"], out)
        M.squash(b3, 5)
        rc, out = M.rel(summary="third")
        check("round trip converges: nothing to release", rc == 0 and "nothing to release" in out, out)

        # ---- dev history rewritten (a purge); the release is still recognized by its tree
        P = World("purge")
        rc, out = P.rel(summary="first", ack_new=True)
        P.squash("release/" + P.d1[:10], 1)
        clock()
        g(P.dev, "commit", "--amend", "-qm", "rewritten")
        g(P.dev, "reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all")
        g(P.dev, "gc", "-q", "--prune=now")
        rels4, contribs4 = P.state()
        check("purged Release-Of recognized by tree", g(P.dev, "cat-file", "-e", P.d1 + "^{commit}").returncode != 0
              and len(rels4) == 1 and rels4[0][1] == P.d1 and contribs4 == [], (rels4, out))

        # ---- settings
        cfg = load_public(M.dev)
        store = _fake_store(cfg)
        check("compliant repo: no drift", settings_drift(cfg, _fake_api(store, [])) == [],
              settings_drift(cfg, _fake_api(store, [])))
        R = "repos/" + cfg["repo"]

        def setv(path, *keys_value):
            def f(s):
                d = s[path]
                for k in keys_value[:-2]:
                    d = d[k]
                d[keys_value[-2]] = keys_value[-1]
            return f
        rule = lambda path, t: lambda s: next(r for r in s[path]["rules"] if r["type"] == t)["parameters"]  # noqa: E731
        muts = [
            ("merge commit allowed", setv(R, "allow_merge_commit", True), "allow_merge_commit"),
            ("squash message at GitHub's default", setv(R, "squash_merge_commit_message", "COMMIT_MESSAGES"),
             "squash_merge_commit_message"),                  # alone in a PATCH, GitHub refuses PR_BODY (422)
            ("no push protection", setv(R, "security_and_analysis", "secret_scanning_push_protection", "status", "disabled"),
             "push_protection"),
            ("ruleset bypass actor", lambda s: s[R + "/rulesets/1"].update(bypass_actors=[
                {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]), "main-integrity"),
            ("missing required check", lambda s: rule(R + "/rulesets/1", "required_status_checks")(s)[
                "required_status_checks"].pop(), "main-integrity"),
            ("strict off", lambda s: rule(R + "/rulesets/1", "required_status_checks")(s).update(
                strict_required_status_checks_policy=False), "main-integrity"),
            ("rebase allowed", lambda s: rule(R + "/rulesets/2", "pull_request")(s).update(
                allowed_merge_methods=["squash", "rebase"]), "main-review"),
            ("wrong reviewer", lambda s: s[R + "/environments/fork-review"]["protection_rules"][0]["reviewers"][0][
                "reviewer"].update(id=7), "fork-review reviewers"),
            ("ci has reviewers", lambda s: s[R + "/environments/ci"]["protection_rules"][0].update(reviewers=[
                {"type": "User", "reviewer": {"id": 42}}]), "ci reviewers"),
            ("ci branch policy missing", lambda s: s.update({R + "/environments/ci/deployment-branch-policies": {
                "branch_policies": []}}), "ci branch policies"),
            ("policy first_time_contributors", setv(R + "/actions/permissions/fork-pr-contributor-approval",
                                                    "approval_policy", "first_time_contributors"), "fork-pr"),
            ("retention 30", setv(R + "/actions/permissions/artifact-and-log-retention", "days", 30), "retention"),
            ("sha pinning off", setv(R + "/actions/permissions", "sha_pinning_required", False), "sha_pinning"),
            ("vulnerability alerts off", lambda s: s.pop(R + "/vulnerability-alerts"), "vulnerability-alerts"),
            ("ruleset absent", lambda s: s.update({R + "/rulesets": [{"id": 1, "name": "main-integrity"}]}),
             "ruleset main-review")]
        for label, mut, word in muts:
            s = _fake_store(cfg)
            mut(s)
            rows = settings_drift(cfg, _fake_api(s, []))
            check("%s: one drift row" % label, len(rows) == 1 and word in rows[0]["what"] and rows[0]["fix"], rows)
        s = _fake_store(cfg)
        s.pop(R + "/actions/secrets/PRIVATE_DEPLOY_KEY")
        rows = settings_drift(cfg, _fake_api(s, []))
        check("missing secret: row, no fix", len(rows) == 1 and rows[0]["fix"] is None
              and "gh secret set PRIVATE_DEPLOY_KEY" in rows[0]["want"], rows)
        s[R + "/actions/secrets/PRIVATE_REPO_TOKEN"] = {"name": "PRIVATE_REPO_TOKEN"}
        check("a PAT secret in place of the deploy key: no drift", settings_drift(cfg, _fake_api(s, [])) == [])
        s = _fake_store(cfg)
        s[R + "/environments/ci"]["can_admins_bypass"] = True
        rows = settings_drift(cfg, _fake_api(s, []))
        check("admin bypass: row, UI hint, no fix", len(rows) == 1 and rows[0]["fix"] is None and "UI only"
              in rows[0]["hint"], rows)
        s = _fake_store(cfg)
        del s[R + "/environments/ci"]["can_admins_bypass"]
        check("absent can_admins_bypass is not compared", settings_drift(cfg, _fake_api(s, [])) == [])
        s, writes = _fake_store(cfg), []
        for _, mut, _ in muts:
            mut(s)
        rc, out = call(cmd_settings, str(M.dev), api=_fake_api(s, writes))
        check("settings reports drift, exit 1", rc == 1 and "SETTINGS DRIFT" in out and not writes, out)
        agent(True)
        rc, out = call(cmd_settings, str(M.dev), apply=True, api=_fake_api(s, writes))
        check("settings --apply refused as agent", rc == 1 and "CLAUDECODE" in out and not writes, out)
        agent(False)
        rc, out = call(cmd_settings, str(M.dev), apply=True, api=_fake_api(s, writes))
        check("--apply fixes every fixable row", rc == 0 and "SETTINGS OK" in out and writes
              and not [w for w in writes if w[0] == "BAD"], out)
        s["repos/example/synthetic-decomp/environments/ci"]["can_admins_bypass"] = True
        s.pop(R + "/actions/secrets/PRIVATE_DEPLOY_KEY")
        writes.clear()
        rc, out = call(cmd_settings, str(M.dev), apply=True, api=_fake_api(s, writes))
        check("--apply still exits 1 on unfixable", rc == 1 and out.count("DRIFT") >= 2 and not writes, out)

        # ---- verify-pr
        def verify(label, ok, word="", merge=False, **kw):
            st = _pr_store(cfg, **kw.pop("store", {}))
            for f in kw.pop("edit", []):
                f(st)
            rc, out = call(cmd_verify_pr, str(M.dev), n=7, merge=merge, api=_fake_api(st, []))
            check(label, (rc == 0) == ok and (word in out) and ("VERIFY-PR OK #7" in out) == ok, out)
        PR7 = R + "/pulls/7"
        verify("same-repo release PR passes", True)
        verify("fork PR passes", True, store={"fork": True})
        verify("same-repo pull_request event fails", False, "pull_request_target", store={"event": "pull_request"})
        verify("forged check from evil.yml fails", False, "evil.yml", store={
            "fork": True, "event": "pull_request", "path": ".github/workflows/evil.yml"})
        verify("stale head sha fails", False, "missing", edit=[lambda s: s[PR7]["head"].update(sha="b" * 40)])
        verify("failed conclusion fails", False, "not a completed success", store={"conclusion": "failure"})
        verify("missing check fails", False, "missing", edit=[lambda s: s["%s/commits/%s/check-runs?per_page=100" % (
            R, "a" * 40)]["check_runs"].pop()])
        verify("fork PR titled Release: fails", False, "claims to be a release", store={"fork": True,
                                                                                         "title": "Release: x"})
        verify("fork PR with Release-* trailer fails", False, "claims to be a release", store={
            "fork": True, "body": "x\n\nRelease-Of: " + "a" * 40})
        verify("fork PR touching .github/ warns", True, "WARN", store={"fork": True, "files": (".github/x.yml",)})
        verify("audit check from a workflow the PR changes fails", False, "does not change", store={
            "fork": True, "files": (".github/workflows/no-rom.yml",)})
        calls.clear()
        verify("--merge squashes at the head sha", True, "merged", merge=True)
        check("merge call is pinned to the head", any(c[:2] == ["pr", "merge"] and "--match-head-commit" in c
                                                          and "a" * 40 in c for c in calls), calls)
        agent(True)
        calls.clear()
        verify("verify-pr --merge refused as agent", False, "CLAUDECODE", merge=True)
        check("no merge call as agent", not [c for c in calls if c[:2] == ["pr", "merge"]], calls)

        # ---- ship: a fake GitHub (PRs, their checks, the squash merge, the runs) around the real bare public repo
        agent(False)
        DEVR = "example/synthetic-decomp-dev"
        g(M.dev, "remote", "set-url", "origin", "https://github.com/%s.git" % DEVR)
        hub = {"prs": {}, "n": 10, "dev": "success", "checks": "success", "lag": 1, "polls": 0, "art": True,
               "push": "success", "sim": 0}
        sleeps = []

        def hub_api(method, path, body=None):
            if method != "GET":
                raise Fail("unexpected %s %s" % (method, path))
            m = re.fullmatch(r"repos/%s/actions/runs\?head_sha=\w+&per_page=100" % DEVR, path)
            if m:
                st = hub["dev"]
                return {"workflow_runs": [] if st == "none" else [
                    {"id": 1, "workflow_id": 1, "name": "no-rom", "event": "push", "created_at": "2026-03-01",
                     "status": "in_progress" if st == "running" else "completed",
                     "conclusion": None if st == "running" else st, "html_url": "https://example.invalid/run/1"},
                    {"id": 0, "workflow_id": 1, "name": "no-rom", "event": "push", "created_at": "2026-02-01",
                     "status": "completed", "conclusion": "failure"},             # an older run, superseded
                    {"id": 2, "workflow_id": 2, "name": "build", "event": "push", "created_at": "2026-03-01",
                     "status": "completed", "conclusion": "skipped"}]}             # guarded off in -dev
            if path == "repos/%s/actions/runs/1/jobs?per_page=100" % DEVR:
                return {"jobs": [{"name": "compile-only", "conclusion": "failure"},
                                 {"name": "lint", "conclusion": "success"}]}
            m = re.fullmatch(r"%s/pulls/(\d+)" % R, path)
            if m:
                pr = hub["prs"].get(int(m[1]))
                return pr and {"state": pr["state"], "base": {"ref": "main"}, "title": pr["title"], "body": "",
                               "head": {"sha": pr["sha"], "ref": pr["br"], "repo": {"full_name": cfg["repo"]}}}
            m = re.fullmatch(r"%s/pulls/(\d+)/files\?per_page=100" % R, path)
            if m:
                sha = hub["prs"][int(m[1])]["sha"]
                return [{"filename": f} for f in _must(M.gh, "diff", "--name-only", sha + "^", sha).split()]
            if re.fullmatch(r"%s/commits/\w+/check-runs\?per_page=100" % R, path):
                hub["polls"] += 1
                done = hub["polls"] > hub["lag"]
                return {"check_runs": [{"name": c, "status": "completed" if done else "in_progress",
                                        "conclusion": hub["checks"] if done else None, "app": {"id": ACTIONS_APP},
                                        "check_suite": {"id": 100 + i}} for i, c in enumerate(cfg["checks"])]}
            m = re.fullmatch(r"%s/actions/runs\?head_sha=(\w+)&per_page=100" % R, path)
            if m:
                return {"workflow_runs": [{"id": 900 + i, "check_suite_id": 100 + i, "head_sha": m[1],
                                           "path": TRUSTED_WORKFLOW if c.startswith("build ") else
                                           ".github/workflows/no-rom.yml", "event": "pull_request_target"
                                           if c.startswith("build ") else "pull_request"}
                                          for i, c in enumerate(cfg["checks"])]}
            if re.fullmatch(r"%s/actions/runs\?head_sha=\w+&event=push&per_page=100" % R, path):
                return {"workflow_runs": [
                    {"id": 70, "name": "build", "path": TRUSTED_WORKFLOW, "status": "completed",
                     "conclusion": hub["push"], "html_url": "https://example.invalid/run/70"},
                    {"id": 71, "name": "no-rom", "path": ".github/workflows/no-rom.yml", "status": "completed",
                     "conclusion": "success", "html_url": "https://example.invalid/run/71"}]}
            if path == "%s/actions/runs/70/artifacts?per_page=100" % R:
                return {"artifacts": [{"name": "PSXD_000.01_report"}] if hub["art"] else []}
            raise Fail("unexpected GET " + path)

        def hub_gh(args, inp=None):
            a = list(args)
            calls.append(a)
            out = ""
            if a[:2] == ["pr", "list"]:
                out = json.dumps([{"number": n, "headRefName": x["br"], "url": x["url"]} for n, x in hub["prs"].items()
                                  if x["state"] == "open"])
            elif a[:2] == ["pr", "create"]:
                br_ = a[a.index("--head") + 1]
                hub["n"] += 1
                hub["prs"][hub["n"]] = {"br": br_, "sha": _must(M.gh, "rev-parse", "refs/heads/" + br_),
                                        "state": "open", "title": a[a.index("--title") + 1],
                                        "url": "https://github.com/%s/pull/%d" % (cfg["repo"], hub["n"])}
                out = hub["prs"][hub["n"]]["url"] + "\n"
            elif a[:2] == ["pr", "close"]:
                x = hub["prs"][int(a[2])]
                x["state"] = "closed"
                g(M.gh, "update-ref", "-d", "refs/heads/" + x["br"])
            elif a[:2] == ["pr", "merge"]:
                x = hub["prs"][int(a[2])]
                if a[a.index("--match-head-commit") + 1] != x["sha"] or "--admin" not in a or "--squash" not in a:
                    return subprocess.CompletedProcess(a, 1, "", "head moved")
                M.squash(x["br"], int(a[2]))
                x["state"] = "merged"
            else:
                return subprocess.CompletedProcess(a, 1, "", "unexpected gh " + " ".join(a))
            return subprocess.CompletedProcess(a, 0, out, "")
        globals()["gh"] = hub_gh

        sims = []

        def fake_sim(repo, workflow, rev, proj):
            """ci-sim without docker: the real projection tree, a job that passes unless hub["sim"] says otherwise."""
            with tempfile.TemporaryDirectory() as std:
                sim_tree(repo, rev, proj, pathlib.Path(std) / "tree")
                t = pathlib.Path(std) / "tree"
                sims.append((workflow, rev, proj, (t / "docs/g.md").is_file() and not (t / "CLAUDE.md").exists()))
            print("CI-SIM job audit on the projection of %s" % rev[:10])
            print("CI-SIM %s .github/workflows/%s.yml on the projection of %s: 1 job(s)" % (
                "FAIL" if hub["sim"] else "OK", workflow, rev[:10]))
            return hub["sim"]

        def ship(dev=None, **k):
            k.setdefault("summary", "fourth")
            k.setdefault("ask", lambda q: False)
            return call(cmd_ship, str(dev or M.dev), api=hub_api, sleep=sleeps.append, ci_sim=fake_sim, **k)

        def pushed():
            g(M.dev, "update-ref", "refs/remotes/origin/main", M.head())

        def writes():
            return [c[:3] for c in calls if c[:2] in (["pr", "create"], ["pr", "merge"], ["pr", "close"])]

        def pub_refs():
            return _git(M.gh, "for-each-ref", "--format=%(refname) %(objectname)").stdout

        def change(files, msg):
            put(M.dev, files)
            commit(M.dev, msg)
            pushed()

        S = World("ship1")
        g(S.dev, "update-ref", "refs/remotes/origin/main", S.head())
        rc, out = ship(S.dev)
        check("ship refuses release 1", rc == 1 and "release 1" in out and "SHIP state" in out, out)
        put(M.dev, {"docs/g.md": "g4\n"})
        commit(M.dev, "dev 4")
        before, calls[:] = pub_refs(), []
        agent(True)
        rc, out = ship()
        check("ship refused as agent", rc == 1 and "CLAUDECODE" in out, out)
        agent(False)
        rc, out = ship()
        check("ship refuses a commit -dev lacks", rc == 1 and "push first" in out, out)
        pushed()
        for st, word in (("failure", "compile-only"), ("none", "no workflow run"), ("running", "still running")):
            hub["dev"] = st
            rc, out = ship(timeout=1)
            check("dev CI %s refuses" % st, rc == 1 and "SHIP dev-ci  FAIL" in out and word in out, out)
        check("dev CI waits before refusing", len(sleeps) >= 2, sleeps)
        hub["dev"] = "success"
        with M.variant({"src/leak.c": "MARKER-BYTES\n"}):
            pushed()
            rc, out = ship(ack_new=True)
        check("a leak refuses at the gate", rc == 1 and "SHIP gate" in out and "audit" in out, out)
        with M.variant({"src/new.c": "n\n"}):
            pushed()
            rc, out = ship()
            check("new paths refused off a TTY", rc == 1 and "--ack-new" in out and "A src/new.c" in out, out)
            with with_cfg(land_check=["false"]):
                rc, out = ship(ask=lambda q: True)
            check("a confirmed path passes; land_check refuses", rc == 1 and "SHIP build" in out and
                  "land_check exited 1" in out, out)
        pushed()
        with with_cfg(land_check=[]):
            rc, out = ship()
        check("no land_check refuses", rc == 1 and "land_check is not set" in out, out)
        hub["sim"] = 1
        rc, out = ship()
        hub["sim"] = 0
        check("no-rom red on the projection refuses", rc == 1 and "SHIP ci      FAIL" in out and "CI-SIM FAIL" in out,
              out)
        check("nothing public before the local stages pass", pub_refs() == before and not writes(), writes())
        sims.clear()
        agent(True)
        rc, out = ship(dry_run=True)
        agent(False)
        check("ci-sim runs no-rom on the projection", rc == 0 and "SHIP ci      OK CI-SIM OK" in out and sims == [
            ("no-rom", M.head(), True, True)], (sims, out))
        check("dry run as agent: stops before the push", rc == 0 and "would push" in out and pub_refs() == before
              and not writes(), out)
        hub["polls"], sleeps[:] = 0, []
        rc, out = ship()
        main4 = _must(M.gh, "rev-parse", "main")
        merge = next((c for c in calls if c[:2] == ["pr", "merge"]), [])
        check("ship: one push, one PR, waits, merges, verifies", rc == 0 and "SHIP OK" in out and writes() == [
            ["pr", "create", "--repo"], ["pr", "merge", "11"]] and sleeps and trailers(M.gh, main4, "Release-Of") ==
              [M.head()] and _subject(M.gh, main4) == "Release: fourth (#11)", out)
        check("the merge is the admin squash pinned to the head", merge[merge.index("--match-head-commit") + 1] ==
              hub["prs"][11]["sha"] and "--admin" in merge, merge)
        led = [l for l in (_read(ships_log(M.dev)) or "").splitlines() if not l.startswith("#")]
        check("ships.tsv: one line", len(led) == 1 and led[0].split("\t")[1:3] == [M.head(), main4], led)
        n0 = len(writes())
        rc, out = ship()
        led = [l for l in (_read(ships_log(M.dev)) or "").splitlines() if not l.startswith("#")]
        check("a rerun after the merge only verifies", rc == 0 and "already released" in out and "SHIP OK" in out and
              len(writes()) == n0 and len(led) == 1, out)
        change({"phase-ends/z.md": "z\n"}, "private only")
        rc, out = ship()
        check("nothing to release", rc == 0 and "nothing to release" in out and len(writes()) == n0, out)
        change({"docs/g.md": "g5\n"}, "dev 5")
        rc, out = ship(summary="fifth", no_wait=True)
        check("--no-wait stops once the PR is open", rc == 0 and "PR #12" in out and writes()[n0:] == [
            ["pr", "create", "--repo"]], out)
        rc, out = ship(summary="fifth")
        check("a rerun resumes at the checks: no second PR", rc == 0 and "resuming" in out and "SHIP OK" in out and
              writes()[n0:] == [["pr", "create", "--repo"], ["pr", "merge", "12"]], out)
        change({"docs/g.md": "g6\n"}, "dev 6")
        ship(summary="sixth", no_wait=True)
        change({"docs/g.md": "g7\n"}, "dev 7")
        n0 = len(writes())
        rc, out = ship(summary="seventh")
        check("another revision's open PR refuses", rc == 1 and "--replace" in out and len(writes()) == n0, out)
        rc, out = ship(summary="seventh", replace=True)
        check("--replace closes it after the gate, then ships", rc == 0 and "SHIP OK" in out and writes()[n0:] == [
            ["pr", "close", "13"], ["pr", "create", "--repo"], ["pr", "merge", "14"]] and hub["prs"][13]["state"] ==
              "closed", out)
        change({PUBLIC_PATHS_REL: WORLD_LIST + ".github/\n", ".github/workflows/no-rom.yml": "on: push\n"}, "dev 8")
        n0 = len(writes())
        rc, out = ship(summary="eighth", ack_new=True)
        check("a workflow-changing release stops for review", rc == 1 and "certify itself" in out and "--merge-reviewed"
              in out and "diff" in out and writes()[n0:] == [["pr", "create", "--repo"]], out)
        rc, out = ship(summary="eighth", merge_reviewed=True)
        check("--merge-reviewed merges it", rc == 0 and "diff reviewed" in out and "SHIP OK" in out, out)
        change({"docs/g.md": "g9\n"}, "dev 9")
        hub["checks"], n0 = "failure", len(writes())
        rc, out = ship(summary="ninth")
        check("a red check refuses the merge", rc == 1 and "SHIP checks  FAIL" in out and "fix forward" in out and
              writes()[n0:] == [["pr", "create", "--repo"]], out)
        hub["checks"], hub["art"] = "success", False
        rc, out = ship(summary="ninth")
        check("no report artifact fails the verify", rc == 1 and "SHIP verify  FAIL" in out and "PSXD_000.01_report"
              in out, out)
        hub["art"] = True
        rc, out = ship(summary="ninth")
        check("a rerun verifies it", rc == 0 and "already released" in out and "SHIP OK" in out, out)
        change({"docs/g.md": "g10\n"}, "dev 10")
        ship(summary="tenth", no_wait=True)
        M.contrib({"src/a.c": a_c2 + "late\n"}, "Late fix")
        rc, out = ship(summary="tenth")
        check("public main moved under the PR refuses", rc == 1 and "moved" in out and "--replace" in out, out)

        # ---- the push gate: blocks a leak, warns on the rest, offline
        M.rewind(_must(M.gh, "rev-parse", "main~1"))
        base_h = M.head()
        _git(M.cache, "update-ref", "-d", PUB_REF)                     # never fetched (release 1 left none)
        b, w, last = pre_push_report(M.dev, dev_url, ["refs/heads/main %s refs/heads/main %s" % (base_h, base_h)])
        check("gate without a fetched public main says new paths are not counted", b == [] and any(
            "not counted" in x for x in w), (b, w, last))
        fetch_public(M.cache, str(M.gh))

        def gate(files=None):
            with M.variant(files):
                return pre_push_report(M.dev, dev_url, ["refs/heads/main %s refs/heads/main %s" % (M.head(), base_h)])
        b, w, last = gate({"docs/g.md": "g11\n"})
        check("gate: a clean push is release-ready", b == [] and w == [] and last == "release-ready: %d files, 0 new" %
              len(tree_entries(M.cache, PUB_REF)), (b, w, last))
        b, w, _ = gate({PUBLIC_PATHS_REL: WORLD_LIST + ".github/\nCLAUDE.md\n"})
        check("gate blocks a listed denied path", any("CLAUDE.md" in x for x in b), b)
        b, w, _ = gate({"src/leak.c": "MARKER-BYTES\n"})
        check("gate blocks an audit failure", any(x.startswith("audit") for x in b) and
              any("new public" in x for x in w), (b, w))
        b, w, _ = gate({"README.md": (M.dev / "README.md").read_text() + "\nSee [p](docs/priv.txt).\n"})
        check("gate only warns on a README lint failure", b == [] and any("README" in x and "docs/priv.txt" in x
                                                                             for x in w), (b, w))
        b, w, _ = gate({"docs/g.md": "g9\n"})                             # public main's content
        check("gate warns: nothing new to release", b == [] and any("nothing new" in x for x in w), (b, w))
        with M.variant({"src/leak.c": "MARKER-BYTES\n"}), contextlib.chdir(M.dev):
            rc, out = call(cmd_pre_push, "origin", dev_url, io.StringIO("refs/heads/main %s refs/heads/main %s\n" % (
                M.head(), base_h)))
        check("the hook's exit: 1 on a block", rc == 1 and "PRE-PUSH FAIL audit" in out, out)
        with M.variant({"README.md": (M.dev / "README.md").read_text() + "\nSee [p](docs/priv.txt).\n"}), \
                contextlib.chdir(M.dev):
            rc, out = call(cmd_pre_push, "origin", dev_url, io.StringIO("refs/heads/main %s refs/heads/main %s\n" % (
                M.head(), base_h)))
        check("the hook's exit: 0 on a warning", rc == 0 and "PRE-PUSH WARN" in out and "release-ready" not in out, out)
        with contextlib.chdir(M.dev):
            rc, out = call(cmd_pre_push, "origin", dev_url, io.StringIO("refs/heads/main %s refs/heads/main %s\n" % (
                M.head(), base_h)))
        check("the hook ends release-ready", rc == 0 and out.strip() == "PRE-PUSH release-ready: %d files, 0 new" % len(
            tree_entries(M.cache, PUB_REF)), out)
        wt = M.root / "wt"                                              # dc2's checkout is a linked worktree
        g(M.dev, "worktree", "add", "-q", "--detach", str(wt))
        os.environ["GIT_DIR"] = _must(wt, "rev-parse", "--absolute-git-dir")   # what git exports to its hooks there
        try:
            with contextlib.chdir(wt):
                rc, out = call(cmd_pre_push, "origin", dev_url, io.StringIO("refs/heads/main %s refs/heads/main %s\n" % (
                    M.head(), base_h)))
        finally:
            os.environ.pop("GIT_DIR", None)
        wt_index = sorted(p for p in _git(wt, "ls-files", "-z").stdout.split("\0") if p)
        check("a push from a linked worktree leaves its index and core.bare alone", rc == 0 and "release-ready" in out
              and wt_index == sorted(tree_entries(M.dev, "HEAD")) and _git(M.dev, "config", "core.bare").stdout.strip()
              == "false", (out, len(wt_index), _git(M.dev, "config", "core.bare").stdout))
        g(M.dev, "config", "core.bare", "false")
        g(M.dev, "worktree", "remove", "--force", str(wt))
    finally:
        globals()["gh"], globals()["load_public"] = real_gh, real_load
        os.environ.clear()
        os.environ.update(saved)


SELF_SIM = """name: sim
on:
  push:
    branches: [main]
jobs:
  a:
    name: job ${{ matrix.exe }}
    strategy:
      matrix:
        exe: ["PSXD_000.01"]
    env:
      EXE: ${{ matrix.exe }}
      PLAIN: "p q"   # a comment
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000 # v4
        with:
          submodules: false
      - name: env — one, two
        run: |
          echo "X=1 2" >> "$GITHUB_ENV"
          mkdir "$RUNNER_TEMP/work"
      - name: report
        id: rep
        working-directory: ${{ runner.temp }}/work
        env:
          WANT: "1 2"
        run: |
          [ "$X" = "$WANT" ] && [ "$PLAIN" = "p q" ] && [ -f "$GITHUB_WORKSPACE/Makefile" ]
          echo "$EXE" > report.json
          echo "make=yes" >> "$GITHUB_OUTPUT"
      - name: upload
        if: success() && steps.rep.outputs.make == 'yes'
        uses: actions/upload-artifact@0000000000000000000000000000000000000000 # v4
        with:
          name: ${{ matrix.exe }}_report
          path: ${{ runner.temp }}/work/report.json
      - run: test ! -e tools/private.py   # tracked files only
"""


def _sim_self_test(check, td: str):
    """list --draft and ci-sim (its steps on this machine: no container) on a throwaway repository."""
    repo = _self_repo(td)
    saved = dict(os.environ)
    os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t",
                      GIT_COMMITTER_EMAIL="t@t.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

    def commit(files: dict):
        for rel, body in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(body, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "more")

    def sim(**k):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_ci_sim(str(repo), "sim", host=True, **k)
        return rc, buf.getvalue()
    try:
        commit({".github/workflows/sim.yml": SELF_SIM, "tools/a.py": "# runs tools/wave.py\n", "tools/wave.py": "#\n",
                "tools/sub/b.py": "#\n", "src/a.c": A_C, "CLAUDE.md": "agents\n", "notes/keep.md": "private\n",
                CONFIG_REL: '[public]\nrepo = "example/synthetic"\ndeny = ["notes/"]\n'})
        entries, warns = draft_list(repo, "HEAD")
        check("list --draft folds what has nothing private", {"src/", ".github/", "docs/", "tools/sub/", "tools/a.py",
              "config/"} <= set(entries) and not {"tools/", "tools/wave.py", "CLAUDE.md", "notes/"} & set(entries),
              entries)
        check("list --draft names what stays behind", warns == ["tools/wave.py stays private, and tools/a.py names it"],
              warns)
        wf = parse_yaml(SELF_SIM.splitlines())[0]
        job = wf["jobs"]["a"]
        check("ci-sim reads the workflow", [sorted(s) for s in job["steps"]][:2] == [["uses", "with"], ["name", "run"]]
              and job["env"]["PLAIN"] == "p q" and job["strategy"]["matrix"]["exe"] == ["PSXD_000.01"]
              and wf["on"]["push"]["branches"] == ["main"] and job["steps"][1]["name"] == "env — one, two", job)
        rc, out = sim()
        check("ci-sim: a fresh clone, green", rc == 0 and "would upload PSXD_000.01_report: 12 bytes" in out
              and "CI-SIM OK   job PSXD_000.01" in out, out[-400:])
        commit({".github/workflows/sim.yml": SELF_SIM.replace('echo "$EXE" > report.json', "test -e nowhere")})
        rc, out = sim()
        check("ci-sim: a failing step is red", rc == 1 and "CI-SIM FAIL step 3: report" in out
              and "would upload" not in out, out[-400:])
        commit({".github/workflows/sim.yml": SELF_SIM, PUBLIC_PATHS_REL: "config/\nMakefile\nsrc/\n"})
        rc, out = sim(proj=True)
        check("ci-sim --projection: an unlisted workflow", rc == 1 and "does not list it" in out, out[-300:])
        commit({PUBLIC_PATHS_REL: "config/\nMakefile\nsrc/\n.github/\n"})
        rc, out = sim(proj=True)
        check("ci-sim --projection: the public tree, green", rc == 0 and "on the projection of" in out, out[-400:])
        commit({".github/workflows/sim.yml": SELF_SIM.replace("test ! -e tools/private.py", "echo ${{ github.sha }}")})
        rc, out = sim()
        check("ci-sim refuses an expression in run", rc == 1 and "does not evaluate" in out, out[-300:])
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _style_self_test(check):
    w = lambda n: "Word " + "word " * (n - 2) + "end."  # noqa: E731
    good = ("---\ntitle: %s; it's\n---\n# T\n\n%s %s\n\n1. %s\n\n- %s\n  %s\n\n| a | %s `a | b` | %s |\n\n```\n"
            "%s; don't\n```\n" % (w(40), w(25), w(25), w(20), w(13), w(12), w(25), w(25), w(40)))
    seven = "\n\n" + " ".join(["Short one."] * 7) + "\n"
    over, semi = "%d words in a sentence (at most %d)", "a semicolon (write two sentences)"
    index = ("<!-- id | title | tags -->\nC0001 | A title; a subtitle | a,b | x\nC0002 | %s | a | x\n"
             "C0003 | T | a | x\n" % w(26))
    block = "<!-- a:begin -->\n%s One; two.\n\n- an item; more\n\n| a | b; c |\n<!-- a:end -->\n" % w(26)
    inside = [(2, over % (26, 25)), (2, semi), (4, semi), (6, semi)]
    for name, text, want in (
            # the limits: one word more in a sentence, a step, a cell or a paragraph is one finding each
            ("style good text", good, []),
            ("style step of 21 words", good.replace("\n1. Word", "\n1. Word extra"), [(8, over % (21, 20))]),
            ("style cell of 26 words", good.replace("| a | Word", "| a | Word extra"), [(13, over % (26, 25))]),
            ("style 7 sentences", good + seven, [(20, "7 sentences in a paragraph (at most 6)")]),
            ("style generated file", "*Generated by x.py; do not edit by hand.*\n\n%s; it's\n" % w(40), []),
            ("style span, link, path, number", "See `a b c d e f` and [the long link text](http://x/y z) at /a/b/c, "
             "1,264 times, %s\n" % w(15), [(1, over % (26, 25))]),
            # one finding per semicolon, on the first line of its unit, and one per contraction
            ("style semicolons in a paragraph", "One part; two parts; three.\n", [(1, semi), (1, semi)]),
            ("style semicolon in a list item", "- an item; more\n", [(1, semi)]),
            ("style semicolon in a table cell", "# T\n\n| a | b; c |\n", [(3, semi)]),
            ("style semicolon in a heading", "# A title; a subtitle\n", [(1, semi)]),
            ("style semicolon in a blockquote", "> Quoted; text.\n", [(1, semi)]),
            ("style semicolon in a wrapped unit", "Wrapped line one\nand two; three.\n", [(1, semi)]),
            ("style contractions", "It doesn't run. You're done, and it's late. We'll see; they've gone.\n",
             [(1, semi)] + [(1, 'a contraction: "%s"' % c) for c in ("doesn't", "You're", "it's", "We'll", "they've")]),
            ("style possessive: no contraction", "The tool’s output isn’t the user's file.\n",
             [(1, 'a contraction: "isn’t"')]),
            # each exemption
            ("style exempt: code spans", "Use `a; b` and ``c ` ; d``.\n", []),
            ("style exempt: link target", "See [the map](docs/map.md;v=2).\n", []),
            ("style exempt: entities", "A &amp; B &#59; C.\n", []),
            ("style exempt: HTML tag", 'A <a href="x;y">link</a>.\n', []),
            ("style exempt: bare URL", "See https://x.org/a;b for it.\n", []),
            ("style exempt: fence", "```\na; b\n```\n", []),
            ("style exempt: metadata line", "# C1 — t\ntags: a;b · date: 2026-10-11 · origin: x;y\n", []),
            ("style exempt: comment line", "<!-- a; b -->\n", []),
            ("style exempt: contraction in a span", "Use `don't` here.\n", []),
            ("style link text is prose", "See [a; b](docs/map.md).\n", [(1, semi)]),
            ("style < and > in prose: no tag", "Use -version </dev/null; then a > b.\n", [(1, semi)]),
            # a record line is a row: its fields are cells, the line before and the line after are not part of it
            ("style record line: fields are cells", index, [(2, semi), (3, over % (26, 25))]),
            ("style pipes in a code span: no row", "Use `a | b | c`; go\non.\n", [(1, semi)]),
            # a marker block yields no unit; a begin line opens one only with its end line, both outside a fence
            ("style marker block: no finding", block, []),
            ("style after the end line: counted", block + "\nThree; four.\n", [(9, semi)]),
            ("style two marker blocks", "%s\n| a | b; c |\n%s\n\n%s\nOne; two.\n%s\n" % (
                marker("disc"), marker("disc", True), *GAME_BLOCK), []),
            ("style begin, no end: no block", block.replace("<!-- a:end -->\n", ""), inside),
            ("style end of another name: no block", block.replace("a:end", "b:end"), inside),
            ("style end in a fence: no block", "<!-- a:begin -->\n\nOne; two.\n\n```\n<!-- a:end -->\n```\n",
             [(3, semi)]),
            ("style begin in a fence: no block", "```\n<!-- a:begin -->\n```\n\nOne; two.\n\n<!-- a:end -->\n",
             [(5, semi)]),
            ("style marker pair in a fence", "```\n<!-- a:begin -->\n<!-- a:end -->\n```\n\nOne; two.\n", [(6, semi)]),
            ("style marker pair in two fences", "```\n<!-- a:begin -->\n```\n\nOne; two.\n\n```\n<!-- a:end -->\n```\n",
             [(5, semi)])):
        got = lint_style(text)
        check(name, got == want, got)
    for name, text in (("style wrapped unit: both lines", "Wrapped line one\nand two; three.\n"),
                       ("style pipes in parentheses: no row", "One line (`match` | `diff` | `error`); then\nmore.\n")):
        got = [(a, b) for a, b, _ in lint_spans(text)]
        check(name, got == [(1, 2)], got)


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
        (repo / CONFIG_REL).write_text('[public]\nrepo = "example/synthetic-public"\n', encoding="utf-8")
        check("split mode: the README names [public].repo, not dev's origin",
              Ctx(repo).slug == "example/synthetic-public" and "decomp.dev/example/synthetic-public" in render(
                  SELF_README, Ctx(repo)), Ctx(repo).slug)
        (repo / CONFIG_REL).unlink()
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
    shown, withheld, kept, total = ci_log(("asm/f.s:12: Error: bad opcode\n0x80012345 deadbeef 00112233\naddiu $sp, $sp, -24\n"
                                           "glabel func_80010000\nmake: *** [build] Error 1\n" + "x" * 300 + "\n").encode())
    check("ci-log withholds asm, hex, instructions", shown == ["make: *** [build] Error 1", "x" * 200]
          and (withheld, kept, total) == (4, 2, 6), shown)
    _style_self_test(check)
    with tempfile.TemporaryDirectory() as td:
        _public_self_test(check, td)
    with tempfile.TemporaryDirectory() as td:
        _sim_self_test(check, td)
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
    cp = sub.add_parser("check-public")
    cp.add_argument("dir", nargs="?", default=".")
    rl = sub.add_parser("release")
    rl.add_argument("--summary", help="the release's title, in your own words (one line)")
    rl.add_argument("--rev", help="the dev revision (default: [public].dev_branch's tip)")
    rl.add_argument("--ack-new", action="store_true", help="allow paths public does not have yet")
    rl.add_argument("--dry-run", action="store_true", help="the checks and the list; no ref is written")
    rl.add_argument("--push", action="store_true", help="push the branch and open the PR (release 1: push main)")
    sh = sub.add_parser("ship")
    sh.add_argument("--summary", help="the release's title, in your own words (one line)")
    sh.add_argument("--rev", help="the dev revision; it must be origin/<dev_branch> (default: dev_branch's tip)")
    sh.add_argument("--ack-new", action="store_true", help="allow paths public does not have yet without asking")
    sh.add_argument("--dry-run", action="store_true", help="stop before the push: nothing is written to public")
    sh.add_argument("--no-wait", action="store_true", help="stop once the PR is open (rerun ship to continue)")
    sh.add_argument("--timeout", type=int, default=90, metavar="MIN", help="how long to wait for CI (default 90)")
    sh.add_argument("--replace", action="store_true", help="close an open release PR of another revision")
    sh.add_argument("--merge-reviewed", action="store_true",
                    help="the release changes a workflow and you reviewed its diff: merge on its green checks")
    im = sub.add_parser("import")
    im.add_argument("--accept-governance", action="store_true")
    im.add_argument("--skip", action="append", default=[], metavar="SHA", help="a public commit dev must never take")
    ld = sub.add_parser("land")
    ld.add_argument("tip", nargs="?")
    st = sub.add_parser("settings")
    st.add_argument("--apply", action="store_true")
    vp = sub.add_parser("verify-pr")
    vp.add_argument("pr", type=int)
    vp.add_argument("--merge", action="store_true")
    for p in (rl, sh, im, ld, st, vp):
        p.add_argument("--repo", default=".", help="the dev repository (default: this one)")
    cl = sub.add_parser("ci-log")
    cl.add_argument("file")
    ls = sub.add_parser("list")
    ls.add_argument("--draft", action="store_true", help="print a first config/public-paths.txt")
    cs = sub.add_parser("ci-sim")
    cs.add_argument("--workflow", default="no-rom", help="the name in .github/workflows/ (default no-rom)")
    cs.add_argument("--projection", action="store_true", help="the release projection, not a clone of dev")
    cs.add_argument("--private", metavar="DIR", help="a local checkout of [public].private_repo (build.yml)")
    cs.add_argument("--image", metavar="REF", help="the container image to use")
    for p in (ls, cs):
        p.add_argument("--rev", help="the dev revision (default HEAD)")
        p.add_argument("--repo", default=".", help="the dev repository (default: this one)")
    pp = sub.add_parser("pre-push", help="git's pre-push hook calls this (stdin: the refs)")
    pp.add_argument("remote")
    pp.add_argument("url", nargs="?", default="")
    hk = sub.add_parser("hook")
    hk.add_argument("--install", action="store_true")
    hk.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    own_git_env()
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
    if a.cmd == "check-public":
        return cmd_check_public(a.dir)
    if a.cmd == "release":
        return cmd_release(a.repo, a.rev, a.summary, a.ack_new, a.dry_run, a.push)
    if a.cmd == "ship":
        return cmd_ship(a.repo, a.summary, a.rev, a.ack_new, a.dry_run, a.no_wait, a.timeout, a.replace,
                        a.merge_reviewed)
    if a.cmd == "import":
        return cmd_import(a.repo, a.accept_governance, a.skip)
    if a.cmd == "land":
        return cmd_land(a.repo, a.tip)
    if a.cmd == "settings":
        return cmd_settings(a.repo, a.apply)
    if a.cmd == "verify-pr":
        return cmd_verify_pr(a.repo, a.pr, a.merge)
    if a.cmd == "ci-log":
        return cmd_ci_log(a.file)
    if a.cmd == "list":
        return cmd_list(a.repo, a.draft, a.rev)
    if a.cmd == "ci-sim":
        return cmd_ci_sim(a.repo, a.workflow, a.rev, a.projection, a.private, a.image)
    if a.cmd == "pre-push":
        return cmd_pre_push(a.remote, a.url)
    if a.cmd == "hook":
        return cmd_hook(a.repo, a.install)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
