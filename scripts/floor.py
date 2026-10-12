#!/usr/bin/env python3
"""floor.py — the roadmap, tooling and readability floor of a game repository (psxdecomp's docs/ops/psxdecomp-floor.md).

    floor.py plan [--repo DIR]            lint GENERATION_PLAN.md: `PLAN FAIL|WARN|INFO <check>: <detail>`; exit 1 on a FAIL
    floor.py ladder FILE                  the eleven ladder phases a constitution names; exit 1 when one is missing
    floor.py debt [--repo DIR]            count the readability debt of the tracked source against config/debt-baseline.txt;
                                          exit 1 when a count is over its row (a rise) or under it (a stale row)
    floor.py debt --update [--admit]      rewrite the baseline to the counts of now; a rise needs `mode admit` and --admit
    floor.py debt --down                  switch the baseline to `mode down`, one way: from then on no rise is admitted
    floor.py names [--init] [--repo DIR]  check config/names.tsv and config/asm-evidence.tsv; --init writes their header lines
    floor.py toolchain [--repo DIR]       config/toolchain.tsv: each pinned checkout at its pin and clean, each file at its hash
    floor.py guard --hook                 a PreToolUse hook: stdin is the event, config/guard.tsv holds the rules
    floor.py --self-test

psxdecomp copies this file into a game as tools/psxd_floor.py. It uses the standard library only and it imports
nothing of the plugin. It writes two files and no other: the baseline (`debt --update`, `debt --down`) and the two header
lines of `names --init`.

The plan checks. `grammar` and `ladder` are a FAIL, the others a WARN.
  grammar    every phase line has its five keys, a unique id of this generation, a known status, depends that exist
  ladder     generation 1: each ladder phase n has a line `1.n`, or slices `1.n.m`, or a `## Changes` line that names 1.n
  numbering  an id over 1.10 that no `## Changes` line names; a line 1.n whose name is not ladder phase n's
  frozen     a closed phase's milestone differs from its text at the commit that closed it
  criteria   no `Done-criteria:` line; a milestone lost its required words (`N of N`, `0 stubs`, `format-check`)
  paths      a closed phase's `phase-end:` file, or a repository path in its milestone, does not exist
  markers    a `TODO(phase-N)` in a tracked file while phase 1.N is closed

The debt kinds (one `<count> <kind> <path>` row each in the baseline):
  pin           `register T x asm("$n")`: a register forced by hand
  pin-unmarked  a pin with no `// !FAKE:` reason on its line or on the line above
  goto          a `goto`
  offset        a field read by its offset: an offset cast, `M2C_FIELD(`, or a macro that hides one (each use)
  address       an address with no symbol, outside the address header (`[debt] address_header`, include/addr.h)
  macro         a `#define` whose body holds `{`, `;` or a line continuation
  asm           a tracked assembly file under src/, or an inline asm statement, with no row in config/asm-evidence.tsv
  placeholder   a `func_XXXXXXXX` or `D_XXXXXXXX` name defined in a C file
  unbased       any other function defined in a C file with no accepted row in config/names.tsv (once that file exists)
  struct        a struct, union or enum body outside include/
An `INCLUDE_ASM` stub is not debt: the progress report gives it no credit.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

PLAN = "GENERATION_PLAN.md"
CONTEXT = "PROJECT_CONTEXT.md"
GEN_END = "phase-ends/GenerationEnd_%d.md"
RECORD = "config/psxdecomp.toml"
BASELINE = "config/debt-baseline.txt"
NAMES = "config/names.tsv"
ASM_EVIDENCE = "config/asm-evidence.tsv"
TOOLCHAIN = "config/toolchain.tsv"
GUARD = "config/guard.tsv"
VENDORED = "tools/psxd_floor.py"


class Fail(Exception):
    """A refusal: printed with its command's prefix, exit 1."""


def _read(path) -> str | None:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, errors="replace")


def tracked(repo, *specs) -> list[str]:
    """The tracked paths under the pathspecs, sorted. Outside a git repository: the files on disk that match."""
    r = _git(repo, "ls-files", "-z", "--", *specs)
    if r.returncode == 0:
        return sorted(p for p in r.stdout.split("\0") if p)
    root = pathlib.Path(repo)
    return sorted(p.relative_to(root).as_posix() for s in specs for p in root.glob(s.replace(":(glob)", "")) if p.is_file())


def entry_match(entry: str, path: str) -> bool:
    """One entry in the syntax of config/public-paths.txt: `dir/` is a prefix, any other entry is an fnmatch glob."""
    return path.startswith(entry) if entry.endswith("/") else fnmatch.fnmatchcase(path, entry)


# ---- the ladder: the kit's eleven phases. A game's phase 1.n is ladder phase n -------------------------------------
# (n, the kit's name, the words a phase line's name must hold, the words its milestone must keep)
LADDER = (
    (0, "Governance and the firewall", r"governance\b.{0,40}\bfirewall", None),
    (1, "Deterministic extraction with a committed manifest", r"\bextraction\b", None),
    (2, "The oracles and the load map", r"\boracles?\b.{0,40}\bload map", None),
    (3, "The all-assembly byte-identical baseline", r"all-assembly|byte-identical baseline", "N of N"),
    (4, "The compiler pinned by evidence", r"\bcompiler\b.{0,30}\bpinned|\bpin\w*\b.{0,30}\bcompiler", None),
    (5, "The honest census and the differential harness", r"\bcensus\b", None),
    (6, "The multipliers", r"\bmultipliers\b", None),
    (7, "The codegen map and the permuter", r"\bcodegen map\b", None),
    (8, "First cracks, the manual wave, the routing cliff", r"\bcampaign\b|first cracks", "0 stubs"),
    (9, "Publish", r"\bpublish", None),
    (10, "Readability", r"\breadab", "format-check"),
)
LADDER_LINE = re.compile(r"^[\s|>*#-]*(?:phase\s+)?(?:\d+\.)?(\d{1,2})\b(.*)$", re.I)


def ladder_found(text: str) -> set[int]:
    """The ladder phases a constitution names: a line that starts with the phase's number (`Phase 4`, `1.4`, `| 4 |`)
    and holds its name's words."""
    found = set()
    for line in text.splitlines():
        m = LADDER_LINE.match(line)
        if m and int(m[1]) <= 10 and re.search(LADDER[int(m[1])][2], m[2], re.I):
            found.add(int(m[1]))
    return found


def ladder_missing(text: str) -> list[int]:
    return [n for n, _, _, _ in LADDER if n not in ladder_found(text)]


def cmd_ladder(path) -> int:
    text = _read(path)
    if text is None:
        print("LADDER FAIL %s: not readable" % path)
        return 1
    missing = ladder_missing(text)
    for n, name, _, _ in LADDER:
        print("LADDER %-7s 1.%-2d %s" % ("MISSING" if n in missing else "OK", n, name))
    print("LADDER %s (%d of %d phases named)" % ("FAIL" if missing else "OK", len(LADDER) - len(missing), len(LADDER)))
    return 1 if missing else 0


# ---- the plan: PA3's line grammar, read here and never written -----------------------------------------------------
# - <G>.<n>[.<m>] <name> | milestone: … | scope: … | depends: … | status: open|closed | phase-end: <file>
PHASE_ID = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
KEYS = ("milestone", "scope", "depends", "status", "phase-end")
NO_DEPENDS = ("", "—", "-", "–", "none")


class Plan:
    def __init__(self):
        self.generation: int | None = None
        self.done_criteria: str | None = None
        self.phases: list[dict] = []          # id, name, the five keys, `line` (its number), `raw`
        self.changes: list[str] = []


def _sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """{heading: [(line number, line)]} of the `## ` sections, HTML comments blanked; "" is the text above the first."""
    text = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    out, cur = {"": []}, ""
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            cur = line[3:].strip()
            out.setdefault(cur, [])
        else:
            out[cur].append((n, line))
    return out


def phase_fields(line: str) -> dict:
    parts = [p.strip() for p in re.sub(r"^\s*-\s+", "", line.strip()).split(" | ")]
    pid, _, name = parts[0].partition(" ")
    out = {"id": pid, "name": name.strip()}
    for p in parts[1:]:
        k, sep, v = p.partition(":")
        if sep and k.strip().lower() in KEYS and k.strip().lower() not in out:
            out[k.strip().lower()] = v.strip()
    return out


def parse_plan(text: str) -> Plan:
    plan, secs = Plan(), _sections(text)
    for _, line in secs[""]:
        m = re.match(r"^# Generation (\d+)\b", line)
        if m and plan.generation is None:
            plan.generation = int(m[1])
        if line.startswith("Done-criteria:") and line[14:].strip():
            plan.done_criteria = line[14:].strip()
    for n, line in secs.get("Phases", []):
        if line.startswith("- "):
            plan.phases.append(dict(phase_fields(line), line=n, raw=line))
    plan.changes = [line[2:].strip() for _, line in secs.get("Changes", []) if line.startswith("- ")]
    return plan


def parse_gen_end(text: str) -> list[dict]:
    """The phases of a closed generation's record: `- 1.4 | <name> | milestone: …` under `## Phases`."""
    out = []
    for _, line in _sections(text).get("Phases", []):
        parts = [p.strip() for p in line[2:].split(" | ")] if line.startswith("- ") else []
        if len(parts) >= 2 and PHASE_ID.match(parts[0]):
            out.append({"id": parts[0], "name": parts[1], "status": "closed"})
    return out


def _slot(pid: str) -> int | None:
    m = PHASE_ID.match(pid)
    return int(m[2]) if m and int(m[1]) == 1 else None


def _named(changes: list[str], pid: str) -> bool:
    """A `## Changes` line names the id (the router's own `phase 1.4 status -> closed` lines do not count)."""
    rx = re.compile(r"(?<![\d.])%s(?![\d.]*\d)" % re.escape(pid))
    return any(rx.search(c) and not re.search(r"\brouter: phase \S+ status -> \w+$", c) for c in changes)


def load_plan(repo) -> tuple[Plan | None, list[dict]]:
    """(the plan or None, the phases of generation 1: the plan's own, or the closed generation's record)."""
    repo = pathlib.Path(repo)
    text = _read(repo / PLAN)
    if text is None:
        return None, []
    plan = parse_plan(text)
    if plan.generation in (None, 1):
        return plan, plan.phases
    end = _read(repo / (GEN_END % 1))
    return plan, parse_gen_end(end) if end else []


def phase_state(repo) -> dict[int, str]:
    """{ladder phase n: "absent" | "pending" | "open" | "closed"}. A slice 1.n.m counts for n. `closed`: every line of n
    is closed. `open`: a line of n is closed, or is open with every phase it depends on closed. `pending`: its lines
    wait for another phase. A later generation with no record of generation 1 counts the whole ladder as closed."""
    plan, gen1 = load_plan(repo)
    if plan is None:
        return {n: "absent" for n, _, _, _ in LADDER}
    if plan.generation not in (None, 1) and not gen1:
        return {n: "closed" for n, _, _, _ in LADDER}
    status = {p["id"]: p.get("status") for p in gen1}
    out = {}
    for n, _, _, _ in LADDER:
        mine = [p for p in gen1 if _slot(p["id"]) == n]
        if not mine:
            out[n] = "absent"
        elif all(p.get("status") == "closed" for p in mine):
            out[n] = "closed"
        elif any(p.get("status") == "closed" or all(
                status.get(d.strip()) == "closed" for d in p.get("depends", "").split(",")
                if d.strip().lower() not in NO_DEPENDS) for p in mine):
            out[n] = "open"
        else:
            out[n] = "pending"
    return out


def _closed_milestones(repo, ids: set[str]) -> dict[str, str] | None:
    """{id: its milestone at the first commit that holds it closed}; None outside a git history."""
    r = _git(repo, "log", "--format=%H", "--reverse", "--", PLAN)
    if r.returncode != 0 or not r.stdout.split():
        return None
    at: dict[str, str] = {}
    for sha in r.stdout.split()[-400:]:
        if not ids - set(at):
            break
        shown = _git(repo, "show", "%s:%s" % (sha, PLAN))
        if shown.returncode != 0:
            continue
        for p in parse_plan(shown.stdout).phases:
            if p["id"] in ids and p["id"] not in at and p.get("status") == "closed":
                at[p["id"]] = p.get("milestone", "")
    return at


REPO_PATH = re.compile(r"`([\w.-]+(?:/[\w.-]+)+/?)`")
MARKER = re.compile(r"TODO\(phase-(\d+)\)")
MARKER_SKIP = (":!phase-ends", ":!templates", ":!.claude", ":!refs")


def lint_plan(repo) -> list[tuple[str, str, str]]:
    """[(FAIL|WARN|INFO, check, detail)] for the repository's plan. No plan: one INFO line."""
    repo = pathlib.Path(repo)
    plan, gen1 = load_plan(repo)
    out: list[tuple[str, str, str]] = []
    add = lambda level, check, detail: out.append((level, check, detail))  # noqa: E731
    if plan is None:
        ctx = _read(repo / CONTEXT)
        add("INFO", "plan", "no %s%s" % (PLAN, "" if ctx is None else "; %s names %d of the %d ladder phases" % (
            CONTEXT, len(ladder_found(ctx)), len(LADDER))))
        return out
    # grammar
    ids = [p["id"] for p in plan.phases]
    if plan.generation is None:
        add("FAIL", "grammar", "no `# Generation <n>` title line")
    if not plan.phases:
        add("FAIL", "grammar", "no phase line under `## Phases`")
    for p in plan.phases:
        where = "line %d (%s)" % (p["line"], p["id"] or "no id")
        m = PHASE_ID.match(p["id"])
        if not m or not p["name"]:
            add("FAIL", "grammar", "%s: not `- <G>.<n> <name> | …`" % where)
            continue
        lacks = [k for k in KEYS if k not in p]
        if lacks:
            add("FAIL", "grammar", "%s: no `%s:`" % (where, "`, `".join(lacks)))
        if plan.generation is not None and int(m[1]) != plan.generation:
            add("FAIL", "grammar", "%s: the id is not of generation %d" % (where, plan.generation))
        if "status" in p and p["status"] not in ("open", "closed"):
            add("FAIL", "grammar", "%s: status is %r, not open or closed" % (where, p["status"]))
        if ids.count(p["id"]) > 1:
            add("FAIL", "grammar", "%s: the id has %d lines" % (where, ids.count(p["id"])))
        gone = [d.strip() for d in p.get("depends", "").split(",")
                if d.strip().lower() not in NO_DEPENDS and d.strip() not in ids]
        if gone:
            add("FAIL", "grammar", "%s: depends on %s, which has no line" % (where, ", ".join(gone)))
    state = phase_state(repo)
    first = plan.generation in (None, 1)
    # ladder
    if first:
        for n, name, _, _ in LADDER:
            if state[n] == "absent" and not _named(plan.changes, "1.%d" % n):
                add("FAIL", "ladder", "no line 1.%d (%s), no slice 1.%d.m, and no `## Changes` line that names 1.%d"
                    % (n, name, n, n))
    elif not gen1:
        add("WARN", "ladder", "generation %d and no %s: the ladder of generation 1 is not checked"
            % (plan.generation, GEN_END % 1))
    else:
        for n, name, _, _ in LADDER:
            if state[n] == "absent":
                add("WARN", "ladder", "%s holds no phase 1.%d (%s)" % (GEN_END % 1, n, name))
    # numbering
    for p in plan.phases if first else []:
        m = PHASE_ID.match(p["id"])
        if not m or int(m[1]) != 1:
            continue
        n = int(m[2])
        if n > 10 and not _named(plan.changes, p["id"]):
            add("WARN", "numbering", "%s (%s) is over 1.10 and no `## Changes` line names it: a slice of ladder phase n "
                "is 1.n.m" % (p["id"], p["name"][:40]))
        elif n <= 10 and not m[3] and not re.search(LADDER[n][2], p["name"], re.I):
            add("WARN", "numbering", "%s is named %r: ladder phase %d is %r" % (p["id"], p["name"][:40], n, LADDER[n][1]))
    # criteria
    if plan.done_criteria is None:
        add("WARN", "criteria", "no `Done-criteria:` line")
    for n, _, _, must in LADDER if first else []:
        mine = [p for p in plan.phases if _slot(p["id"]) == n]
        if must and mine and not any(re.search(r"(?<!\w)%s(?!\w)" % re.escape(must), p.get("milestone", ""), re.I)
                                     for p in mine) \
                and not _named(plan.changes, "1.%d" % n):
            add("WARN", "criteria", "no milestone of phase 1.%d holds `%s`, and no `## Changes` line names 1.%d"
                % (n, must, n))
    # frozen
    closed = [p for p in plan.phases if p.get("status") == "closed"]
    at = _closed_milestones(repo, {p["id"] for p in closed}) if closed else {}
    if at is None:
        add("INFO", "frozen", "no git history of %s: not checked" % PLAN)
    for p in closed if at else []:
        if p["id"] in at and at[p["id"]] != p.get("milestone", ""):
            add("WARN", "frozen", "%s is closed and its milestone differs from its text at the commit that closed it: "
                "record a correction as a `## Changes` line" % p["id"])
    # paths
    for p in closed:
        end = p.get("phase-end", "")
        if end and not (repo / end).is_file():
            add("WARN", "paths", "%s is closed and its phase-end file %s does not exist" % (p["id"], end))
        gone = [x for x in dict.fromkeys(REPO_PATH.findall(p.get("milestone", "")))
                if (repo / x.split("/")[0]).is_dir() and not (repo / x).exists()]
        if gone:
            add("WARN", "paths", "%s is closed and its milestone names %s, which %s not exist" % (
                p["id"], ", ".join(gone[:4]), "does" if len(gone) == 1 else "do"))
    # markers
    r = _git(repo, "grep", "-n", "-I", "-E", r"TODO\(phase-[0-9]+\)", "--", ".", *MARKER_SKIP)
    stale = []
    for hit in r.stdout.splitlines() if r.returncode == 0 else []:
        path, line, text = (hit.split(":", 2) + ["", ""])[:3]
        stale += ["%s:%s (1.%s)" % (path, line, n) for n in MARKER.findall(text) if state.get(int(n)) == "closed"]
    if stale:
        add("WARN", "markers", "%d `TODO(phase-N)` marker(s) of a closed phase: %s%s" % (
            len(stale), ", ".join(stale[:4]), ", …" if len(stale) > 4 else ""))
    groups = {s: [str(n) for n, _, _, _ in LADDER if state[n] == s] for s in ("closed", "open", "pending", "absent")}
    add("INFO", "state", "generation %s; ladder phases %s" % (plan.generation, "; ".join(
        "%s %s" % (s, ",".join(v)) for s, v in groups.items() if v)))
    return out


def plan_summary(found) -> tuple[str, str]:
    fails, warns = [f for f in found if f[0] == "FAIL"], [f for f in found if f[0] == "WARN"]
    return ("FAIL" if fails else "WARN" if warns else "OK"), "%d fail, %d warn" % (len(fails), len(warns))


def cmd_plan(repo) -> int:
    found = lint_plan(repo)
    for f in found:
        print("PLAN %-4s %s: %s" % f)
    st, detail = plan_summary(found)
    print("PLAN %s (%s)" % ("FAIL" if st == "FAIL" else "OK", detail))
    return 1 if st == "FAIL" else 0


# ---- the readability debt -----------------------------------------------------------------------------------------
KINDS = ("pin", "pin-unmarked", "goto", "offset", "address", "macro", "asm", "placeholder", "unbased", "struct")
NUM = r"(?:0[xX][0-9A-Fa-f]+|\d+)"
OFFX = rf"(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*)(?:\s*[-+*]\s*(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*))*"
OPND = r"\(?\s*&?\s*\w+\s*\)?"
PTR = r"\(\s*[\w ]+?\s*\*+\s*\)"
CHR = r"(?:const\s+)?(?:(?:unsigned|signed)\s+)?(?:char|[su]8)"
OFFSET = re.compile(rf"\*\s*{PTR}\s*\(\s*{PTR}\s*{OPND}\s*\+\s*{OFFX}\s*\)|\(\s*{CHR}\s*\*+\s*\)\s*{OPND}\s*\+\s*{OFFX}"
                    r"|\bM2C_FIELD\s*\(")
ADDRESS = re.compile(r"\(\s*[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*\s*(?:\*\s*)+\)\s*0[xX][0-9A-Fa-f]{5,}")
PIN = re.compile(r'\bregister\b[^;{}]*?\b(?:asm|__asm__)\s*\(\s*"')
GOTO = re.compile(r"\bgoto\s+\w+\s*;")
STRUCT = re.compile(r"\b(?:struct|union|enum)\b\s*\w*\s*\{")
INLINE_ASM = re.compile(r"\b(?:asm|__asm__)\b\s*(?:(?:volatile|__volatile__)\b\s*)?\(")
DEFINE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+(\w+)((?:\\\n|[^\n])*)", re.M)
PREPROC = re.compile(r"^[ \t]*#(?:\\\n|[^\n])*", re.M)
DEF_FUNC = re.compile(r"^(?:[A-Za-z_]\w*[\s*]+)+?([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.M)
DEF_DATA = re.compile(r"^(?!extern\b)(?:[A-Za-z_]\w*[\s*]+)+?(D_[0-9A-Fa-f]{8}\w*)\s*(?:\[[^\]\n]*\]\s*)*[=;]", re.M)
PLACEHOLDER = re.compile(r"^(?:func|D)_[0-9A-Fa-f]{8}")
NOT_A_NAME = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "main"}
_STRIP = re.compile(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", re.S)
SOURCES = ("src/**/*.c", "src/**/*.h", "src/**/*.s", "src/**/*.S", "include/**/*.h", "src/*.c", "src/*.h", "src/*.s",
           "src/*.S", "include/*.h")
ADDRESS_HEADER = "include/addr.h"
FIRST_SKIP = ("include/include_asm.h",)             # the stub macro itself: assembly by design
BASELINE_HEAD = (
    "%s: the count of readability debt in each tracked source file (rules/FIN1.md)." % BASELINE,
    "`python3 %s debt` fails when a count is over its row, and when a row is over its count." % VENDORED,
    "After a change, run `python3 %s debt --update`. In `mode admit` a rise needs `--admit` and is printed." % VENDORED,
    "`python3 %s debt --down` switches to `mode down`, one way: from then on a count may only fall." % VENDORED,
    "A `skip` line names files that the checker does not read.")


def strip(text: str) -> str:
    """Comments and string bodies become spaces. Newlines stay, so a line number is the same in both texts."""
    def blank(m):
        s = m.group(0)
        if s[0] == "/":
            return re.sub(r"[^\n]", " ", s)
        return s[0] + " " * (len(s) - 2) + s[-1] if len(s) >= 2 else s
    return _STRIP.sub(blank, text)


def _macros(body: str) -> dict[str, str]:
    """{macro name: "offset" | "address"} for each `#define` whose body holds one."""
    out = {}
    for m in DEFINE.finditer(body):
        if m.group(1) == "M2C_FIELD":
            continue
        if OFFSET.search(m.group(2)):
            out[m.group(1)] = "offset"
        elif ADDRESS.search(m.group(2)):
            out[m.group(1)] = "address"
    return out


def _uses(names, text: str) -> int:
    return len(re.findall(r"\b(?:%s)\b" % "|".join(map(re.escape, sorted(names))), text)) if names else 0


def file_debt(rel: str, text: str, shared=None, based=None, address_header=ADDRESS_HEADER) -> dict[str, int]:
    """The counts of one C file or header, by kind (zero counts left out). `shared`: the offset and address macros of
    the headers. `based`: the names with a ledger row, or None before the ledger exists."""
    body = strip(text)
    code = PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)
    raw = text.split("\n")
    macros = dict(shared or {})
    macros.update(_macros(body))
    got = dict.fromkeys(KINDS, 0)
    pins = list(PIN.finditer(code))
    got["pin"] = len(pins)
    for m in pins:
        at = code.count("\n", 0, m.end())                              # the line of `asm("`, counted from 0
        if not any("!FAKE:" in raw[i] for i in (at - 1, at) if 0 <= i < len(raw)):
            got["pin-unmarked"] += 1
    got["goto"] = len(GOTO.findall(code))
    got["offset"] = len(OFFSET.findall(body)) + _uses([k for k, v in macros.items() if v == "offset"], code)
    if rel != address_header:
        got["address"] = len(ADDRESS.findall(body)) + _uses([k for k, v in macros.items() if v == "address"], code)
    got["macro"] = sum(1 for m in DEFINE.finditer(body) if re.search(r"[{;]|\\\n", m.group(2)))
    spans = [(m.start(), m.end()) for m in pins]
    got["asm"] = sum(1 for m in INLINE_ASM.finditer(code) if not any(a <= m.start() < b for a, b in spans))
    if not rel.startswith("include/"):
        got["struct"] = len(STRUCT.findall(code))
    if rel.endswith(".c"):
        funcs = {m.group(1) for m in DEF_FUNC.finditer(code)} - NOT_A_NAME
        data = {m.group(1) for m in DEF_DATA.finditer(code)}
        got["placeholder"] = sum(1 for n in funcs | data if PLACEHOLDER.match(n))
        if based is not None:
            got["unbased"] = sum(1 for n in funcs if not PLACEHOLDER.match(n) and n not in based)
    return {k: v for k, v in got.items() if v}


def _toml(repo) -> dict:
    """config/psxdecomp.toml, or {} when it is absent, not TOML, or this Python has no tomllib."""
    try:
        import tomllib
        with open(pathlib.Path(repo) / RECORD, "rb") as f:
            return tomllib.load(f)
    except Exception:                                  # the record is optional here
        return {}


def read_tsv(path, columns) -> tuple[list[dict] | None, list[str]]:
    """(the rows, the errors) of a tab-separated file with a header line. None when the file is absent."""
    text = _read(path)
    if text is None:
        return None, []
    rows, errs, head = [], [], None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        if head is None:
            head = cells
            if tuple(head) != tuple(columns):
                errs.append("line %d: the header is not %s" % (n, " ".join(columns)))
                return rows, errs
            continue
        if len(cells) != len(columns):
            errs.append("line %d: %d cell(s), not %d" % (n, len(cells), len(columns)))
            continue
        rows.append(dict(zip(columns, cells), _line=n))
    if head is None:
        errs.append("no header line")
    return rows, errs


def debt_counts(repo, skip=()) -> dict[tuple[str, str], int]:
    """{(kind, path): count} over the tracked src/ and include/ files that no `skip` entry covers."""
    repo = pathlib.Path(repo)
    files = [p for p in tracked(repo, *SOURCES) if not any(entry_match(e, p) for e in skip)]
    header = str((_toml(repo).get("debt") or {}).get("address_header") or ADDRESS_HEADER)
    names, _ = read_tsv(repo / NAMES, NAME_COLUMNS)
    based = None if names is None else {r["new_name"] for r in names if r["decision"] in ("accepted", "provisional")}
    evidence = {r["path"] for r in read_tsv(repo / ASM_EVIDENCE, ASM_COLUMNS)[0] or []}
    texts = {p: _read(repo / p) for p in files}
    shared: dict[str, str] = {}
    for p in files:
        if p.endswith(".h") and p != header and texts[p] is not None:
            shared.update(_macros(strip(texts[p])))
    out: dict[tuple[str, str], int] = {}
    for p in files:
        if texts[p] is None:
            continue
        if p.endswith((".s", ".S")):
            got = {} if p in evidence else {"asm": 1}
        else:
            got = file_debt(p, texts[p], shared, based, header)
            if p in evidence:
                got.pop("asm", None)
        for kind, n in got.items():
            out[(kind, p)] = n
    return out


def parse_baseline(text: str | None) -> tuple[dict[tuple[str, str], int], list[str], str, list[str]]:
    """(the rows {(kind, path): count}, the `skip` entries, the mode, the leading comment lines). None is the empty
    baseline in `mode admit`. Any other line raises Fail with its number, and so does a second row of one pair."""
    rows, skip, mode, head, top = {}, [], "admit", [], True
    for n, raw in enumerate((text or "").splitlines(), 1):
        l = raw.strip()
        if not l:
            continue
        m = re.fullmatch(r"(\d+) (\S+) (\S.*)", l)
        if l.startswith("#"):
            head += [l] if top else []
        elif l in ("mode admit", "mode down"):
            mode = l[5:]
        elif l.startswith("skip ") and l[5:].strip():
            skip.append(l[5:].strip())
        elif m and m[2] in KINDS and (m[2], m[3]) not in rows:
            rows[(m[2], m[3])] = int(m[1])
        else:
            raise Fail("%s:%d: %s" % (BASELINE, n, "%s %s has two rows" % (m[2], m[3]) if m and m[2] in KINDS else
                                      "not `<count> <kind> <path>`, `mode admit|down`, `skip <entry>` or a `#` comment"))
        top = top and l.startswith("#")
    return rows, skip, mode, head


def baseline_text(counts: dict, skip=(), mode="admit", head=()) -> str:
    lines = [l if l.startswith("#") else "# " + l for l in head] + ["mode %s" % mode] + ["skip %s" % e for e in skip]
    lines += ["%d %s %s" % (counts[k], k[0], k[1]) for k in sorted(counts, key=lambda k: (k[1], KINDS.index(k[0])))
              if counts[k] > 0]
    return "".join(l + "\n" for l in lines)


def first_baseline(repo) -> str:
    """A game's first baseline: the counts of now, `mode admit`, the stub macro's header skipped."""
    return baseline_text(debt_counts(repo, FIRST_SKIP), FIRST_SKIP, "admit", BASELINE_HEAD)


def _totals(counts: dict) -> str:
    by = {k: 0 for k in KINDS}
    for (kind, _), n in counts.items():
        by[kind] += n
    return ", ".join("%s %d" % (k, by[k]) for k in KINDS if by[k]) or "none"


def debt_status(repo) -> dict:
    """What the doctor reads: the baseline (or None), the counts of now, the rises and the stale rows."""
    repo = pathlib.Path(repo)
    text = _read(repo / BASELINE)
    rows, skip, mode, head = parse_baseline(text)
    counts = debt_counts(repo, skip)
    keys = sorted(set(rows) | set(counts), key=lambda k: (k[1], KINDS.index(k[0])))
    return {"baseline": text is not None, "rows": rows, "skip": skip, "mode": mode, "head": head, "counts": counts,
            "rise": [k for k in keys if counts.get(k, 0) > rows.get(k, 0)],
            "stale": [k for k in keys if counts.get(k, 0) < rows.get(k, 0)]}


def cmd_debt(repo, update=False, admit=False, down=False) -> int:
    repo = pathlib.Path(repo)
    try:
        st = debt_status(repo)
    except Fail as e:
        print("DEBT FAIL %s" % e)
        return 1
    rows, counts, mode = st["rows"], st["counts"], st["mode"]
    files = len({k[1] for k in counts})
    print("DEBT INFO totals: %s (%d file(s) with debt)" % (_totals(counts), files))
    if down:
        if not st["baseline"]:
            print("DEBT FAIL no %s: write it first (`debt --update`)" % BASELINE)
            return 1
        if st["rise"] or st["stale"]:
            print("DEBT FAIL the baseline is not equal to the tree: run `debt --update` first")
            return 1
        (repo / BASELINE).write_text(baseline_text(rows, st["skip"], "down", st["head"]), encoding="utf-8")
        print("DEBT DOWN %s is in `mode down`: a count may only fall" % BASELINE)
        return 0
    if update:
        if st["rise"] and (mode == "down" or not admit):
            for k in st["rise"]:
                print("DEBT FAIL rise %s %s: %d, its row is %d" % (k[0], k[1], counts.get(k, 0), rows.get(k, 0)))
            print("DEBT UPDATE refused: %d count(s) over their row%s" % (len(st["rise"]), (
                " (`mode down` admits none)" if mode == "down" else " (`--admit` admits them in `mode admit`)")))
            return 1
        for k in st["rise"]:
            print("DEBT ADMIT %s %s: %d -> %d" % (k[0], k[1], rows.get(k, 0), counts[k]))
        for k in st["stale"]:
            print("DEBT INFO %s %s: %d -> %d" % (k[0], k[1], rows[k], counts.get(k, 0)))
        (repo / BASELINE).parent.mkdir(parents=True, exist_ok=True)
        (repo / BASELINE).write_text(baseline_text(counts, st["skip"], mode, st["head"] or BASELINE_HEAD), encoding="utf-8")
        print("DEBT UPDATE written %s (%d row(s), %d fell, %d admitted; mode %s)" % (
            BASELINE, len(counts), len(st["stale"]), len(st["rise"]), mode))
        return 0
    if not st["baseline"]:
        print("DEBT CHECK OK (no %s: nothing to compare; `debt --update` writes it)" % BASELINE)
        return 0
    for k in st["rise"]:
        print("DEBT FAIL rise %s %s: %d, its row is %d" % (k[0], k[1], counts.get(k, 0), rows.get(k, 0)))
    for k in st["stale"]:
        print("DEBT FAIL stale %s %s: %d, its row is %d: run `python3 %s debt --update`" % (
            k[0], k[1], counts.get(k, 0), rows[k], VENDORED))
    bad = bool(st["rise"] or st["stale"])
    print("DEBT CHECK %s (%d rise(s), %d stale row(s); mode %s)" % ("FAIL" if bad else "OK", len(st["rise"]),
                                                                    len(st["stale"]), mode))
    return 1 if bad else 0


# ---- the two ledgers: names with their evidence, assembly with its reason ------------------------------------------
NAME_COLUMNS = ("kind", "image", "scope", "old_name", "new_name", "decision", "evidence", "reason")
NAME_KINDS = ("function", "data", "type", "field", "macro", "file")
DECISIONS = ("accepted", "provisional", "rejected")
EVIDENCE = ("psyq-sig", "string", "xref", "loadmap", "exe-header", "prior-art", "debug-symbol")
EVIDENCE_RE = re.compile(r"^(%s):[^:\s]+:\d+$" % "|".join(EVIDENCE))
ASM_COLUMNS = ("image", "symbol", "path", "class", "evidence", "date")
ASM_CLASSES = ("sdk-object", "hand-asm", "data-in-text")


def names_findings(repo) -> list[tuple[str, str]]:
    """[(FAIL|INFO, detail)] for the two ledgers: a FAIL is a malformed file or row."""
    repo, out = pathlib.Path(repo), []
    rows, errs = read_tsv(repo / NAMES, NAME_COLUMNS)
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % NAMES))
    else:
        for r in rows:
            bad = []
            if r["kind"] not in NAME_KINDS:
                bad.append("kind %r is not one of %s" % (r["kind"], "|".join(NAME_KINDS)))
            if r["decision"] not in DECISIONS:
                bad.append("decision %r is not one of %s" % (r["decision"], "|".join(DECISIONS)))
            if not EVIDENCE_RE.match(r["evidence"]):
                bad.append("evidence %r is not `<class>:<path>:<line>` with a class of %s" % (r["evidence"], "|".join(EVIDENCE)))
            if not r["new_name"]:
                bad.append("no new_name")
            errs += ["line %d: %s" % (r["_line"], b) for b in bad]
        twice = sorted({r["new_name"] for r in rows if sum(
            x["new_name"] == r["new_name"] and x["image"] == r["image"] and x["scope"] == r["scope"] and
            x["kind"] == r["kind"] and x["decision"] != "rejected" for x in rows) > 1 and r["decision"] != "rejected"})
        errs += ["%s has two rows that are not rejected" % n for n in twice]
        out += [("FAIL", "%s: %s" % (NAMES, e)) for e in errs]
        by = {d: sum(r["decision"] == d for r in rows) for d in DECISIONS}
        out.append(("INFO", "%s: %d row(s): %s" % (NAMES, len(rows), ", ".join("%d %s" % (by[d], d) for d in DECISIONS))))
    rows, errs = read_tsv(repo / ASM_EVIDENCE, ASM_COLUMNS)
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % ASM_EVIDENCE))
    else:
        for r in rows:
            if r["class"] not in ASM_CLASSES:
                errs.append("line %d: class %r is not one of %s" % (r["_line"], r["class"], "|".join(ASM_CLASSES)))
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", r["date"]):
                errs.append("line %d: date %r is not YYYY-MM-DD" % (r["_line"], r["date"]))
            if not r["path"] or not r["evidence"]:
                errs.append("line %d: no path or no evidence" % r["_line"])
        out += [("FAIL", "%s: %s" % (ASM_EVIDENCE, e)) for e in errs]
        out.append(("INFO", "%s: %d row(s)" % (ASM_EVIDENCE, len(rows))))
    return out


def cmd_names(repo, init=False) -> int:
    repo = pathlib.Path(repo)
    for rel, cols in ((NAMES, NAME_COLUMNS), (ASM_EVIDENCE, ASM_COLUMNS)) if init else ():
        if not (repo / rel).exists():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("\t".join(cols) + "\n", encoding="utf-8")
            print("NAMES INIT written %s" % rel)
    found = names_findings(repo)
    for level, detail in found:
        print("NAMES %-4s %s" % (level, detail))
    if not any(f[0] == "FAIL" for f in found) and (repo / NAMES).is_file():
        unbased = sum(n for (kind, _), n in debt_counts(repo, parse_baseline(_read(repo / BASELINE))[1]).items()
                      if kind == "unbased")
        print("NAMES INFO %d function(s) defined in src/ with no accepted or provisional row" % unbased)
    bad = sum(f[0] == "FAIL" for f in found)
    print("NAMES %s (%d malformed)" % ("FAIL" if bad else "OK", bad))
    return 1 if bad else 0


# ---- the toolchain's pins: read, never fetched, no command of the game run ------------------------------------------
TOOL_COLUMNS = ("name", "kind", "pin", "path")


def toolchain_rows(repo) -> list[tuple[str, str, str]] | None:
    """[(OK|FAIL|MISSING, name, detail)] per row of config/toolchain.tsv; None when the file is absent. `git`: the
    checkout's HEAD is the pin and it has no local change. `sha256`: the file's hash is the pin."""
    repo = pathlib.Path(repo)
    rows, errs = read_tsv(repo / TOOLCHAIN, TOOL_COLUMNS)
    if rows is None:
        return None
    out = [("FAIL", TOOLCHAIN, e) for e in errs]
    for r in rows:
        path = pathlib.Path(os.path.expanduser(r["path"]))
        path = path if path.is_absolute() else repo / path
        if r["kind"] == "git":
            head = _git(path, "rev-parse", "HEAD") if path.is_dir() else None
            if head is None or head.returncode != 0:
                out.append(("MISSING", r["name"], "%s is not a git checkout on this machine" % r["path"]))
            elif head.stdout.strip() != r["pin"]:
                out.append(("FAIL", r["name"], "%s is at %s, the pin is %s" % (r["path"], head.stdout.strip()[:12], r["pin"][:12])))
            elif _git(path, "status", "--porcelain").stdout.strip():
                out.append(("FAIL", r["name"], "%s has local changes: a patched tool is not the pinned tool" % r["path"]))
            else:
                out.append(("OK", r["name"], "%s at %s, clean" % (r["path"], r["pin"][:12])))
        elif r["kind"] == "sha256":
            if not path.is_file():
                out.append(("MISSING", r["name"], "%s is not on this machine" % r["path"]))
                continue
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            ok = h.hexdigest() == r["pin"].lower()
            out.append(("OK" if ok else "FAIL", r["name"], "%s %s" % (r["path"], "has the pinned hash" if ok else
                        "has hash %s, the pin is %s" % (h.hexdigest()[:12], r["pin"][:12]))))
        else:
            out.append(("FAIL", r["name"], "line %d: kind %r is not git or sha256" % (r["_line"], r["kind"])))
    return out


def cmd_toolchain(repo) -> int:
    rows = toolchain_rows(repo)
    if rows is None:
        print("TOOLCHAIN INFO no %s (columns: %s)" % (TOOLCHAIN, " ".join(TOOL_COLUMNS)))
        return 0
    for st, name, detail in rows:
        print("TOOLCHAIN %-7s %s: %s" % (st, name, detail))
    bad = sum(r[0] == "FAIL" for r in rows)
    print("TOOLCHAIN %s (%d row(s), %d fail, %d missing)" % ("FAIL" if bad else "OK", len(rows), bad,
                                                             sum(r[0] == "MISSING" for r in rows)))
    return 1 if bad else 0


# ---- the guard: a PreToolUse hook that reads config/guard.tsv -------------------------------------------------------
GUARD_COLUMNS = ("action", "tool", "pattern", "say")
PATH_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


def parse_guard(text: str | None) -> list[tuple[str, str, str, str]]:
    """The rules of a guard file, in order: (deny|allow, bash|path, pattern, say). A line that is no rule is skipped:
    the guard never fails on its own file (`guard_errors` names such lines for the doctor)."""
    rules = []
    for line in (text or "").splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if line.startswith("#") or len(cells) < 3 or tuple(cells[:4]) == GUARD_COLUMNS:
            continue
        if cells[0] in ("deny", "allow") and cells[1] in ("bash", "path") and cells[2]:
            rules.append((cells[0], cells[1], cells[2], cells[3] if len(cells) > 3 else ""))
    return rules


def guard_errors(text: str) -> list[str]:
    errs = []
    for n, line in enumerate(text.splitlines(), 1):
        cells = [c.strip() for c in line.split("\t")]
        if not line.strip() or line.startswith("#") or tuple(cells[:4]) == GUARD_COLUMNS:
            continue
        if len(cells) != 4 or cells[0] not in ("deny", "allow") or cells[1] not in ("bash", "path") or not cells[2]:
            errs.append("line %d: not `deny|allow <tab> bash|path <tab> pattern <tab> say`" % n)
        elif cells[1] == "bash":
            try:
                re.compile(cells[2])
            except re.error as e:
                errs.append("line %d: the pattern is not a regular expression (%s)" % (n, e))
    return errs


def guard_decision(event: dict, rules, root) -> str | None:
    """The `say` text of the first rule that matches the event when that rule denies; None when the call may run. A
    `bash` rule is a regular expression searched in a Bash command. A `path` rule is an entry in the syntax of
    config/public-paths.txt, matched against the repository path that an Edit or a Write names."""
    tool, inp = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Bash":
        kind, subject = "bash", str(inp.get("command") or "")
    elif tool in PATH_TOOLS and inp.get(PATH_TOOLS[tool]):
        target = pathlib.Path(event.get("cwd") or ".", inp[PATH_TOOLS[tool]]).resolve()
        try:
            kind, subject = "path", target.relative_to(pathlib.Path(root).resolve()).as_posix()
        except ValueError:
            return None                                # outside the repository: not this guard's file
    else:
        return None
    for action, rtool, pattern, say in rules:
        if rtool != kind:
            continue
        try:
            hit = re.search(pattern, subject) is not None if kind == "bash" else entry_match(pattern, subject)
        except re.error:
            continue
        if hit:
            return (say or "this repository's guard refuses it") if action == "deny" else None
    return None


def guard_hook(stdin=None) -> int:
    """`guard --hook`: print the hook's JSON answer when a rule denies the call. It never fails: bad JSON, no
    repository, no rules file or any other failure prints nothing, and the exit code is always 0 (the call runs)."""
    try:
        event = json.loads((stdin or sys.stdin).read())
        start = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
        r = _git(start, "rev-parse", "--show-toplevel")
        root = pathlib.Path(r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else start)
        say = guard_decision(event, parse_guard(_read(root / GUARD)), root)
        if say:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "psxd guard (%s): %s" % (GUARD, say)}}))
    except Exception:                                  # a hook that fails must not stop the session
        pass
    return 0


# ---- self-test ------------------------------------------------------------------------------------------------------
def _phase(pid, name, status="open", depends="—", milestone="m"):
    return "- %s %s | milestone: %s | scope: s | depends: %s | status: %s | phase-end: phase-ends/PhaseEnd_Phase%s.md" % (
        pid, name, milestone, depends, status, pid)


def self_plan(closed=5, drop=(), extra=(), changes=(), milestones=None) -> str:
    """A synthetic generation-1 plan: the ladder as lines 1.0 to 1.10, the first `closed` of them closed."""
    must = {3: "prints N of N", 8: "the census reads 0 stubs", 10: "`make format-check` passes"}
    must.update(milestones or {})
    lines = [_phase("1.%d" % n, name, "closed" if n < closed else "open", "1.%d" % (n - 1) if n else "—",
                    must.get(n, "m")) for n, name, _, _ in LADDER if n not in drop]
    return ("# Generation 1 — a synthetic game\n\nGoal: g\nDone-criteria: d\n\n## Phases\n\n<!-- Line grammar:\n"
            "     - <G>.<n> <name> | milestone: … -->\n\n%s\n\n## Changes\n\n<!-- - <date> who: what -->\n%s"
            % ("\n".join(lines + list(extra)), "".join("- %s\n" % c for c in changes)))


C_CLEAN = """#include "common.h"
// a goto in a comment, and M2C_FIELD(p, 4) too
s32 Player_Hp(Entity *self) {
    const char *s = "goto here; *(s32 *)0x1F800020";
    return self->hp + g_State.mode;
}
"""
C_DEBT = {
    "pin": ('void Walk(void) {\n    // !FAKE: the loop counter\n    register s32 i asm("$16");\n    i = 1;\n}\n',
            {"pin": 1}),
    "pin-unmarked": ('void Walk(void) {\n    register s32 i asm("$16");\n    i = 1;\n}\n', {"pin": 1, "pin-unmarked": 1}),
    "goto": ("void Walk(s32 n) {\nloop:\n    if (--n) goto loop;\n}\n", {"goto": 1}),
    "offset": ("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\ns32 Walk(void *p) {\n    return HP(p) + HP(p) + M2C_FIELD(p, s32 *, 8);\n}\n",
               {"offset": 4}),
    "address": ("void Walk(void) {\n    *(volatile u32 *)0x1F801070 = 0;\n}\n", {"address": 1}),
    "macro": ("#define SWAP(a, b) { s32 t = a; a = b; b = t; }\n#define TWO(a) \\\n    ((a) * 2)\n", {"macro": 2}),
    "asm": ('void Walk(void) {\n    __asm__("nop");\n}\n', {"asm": 1}),
    "placeholder": ("s32 D_800A1234 = 4;\nextern s32 D_800A5678;\nINCLUDE_ASM(\"asm/nonmatchings\", func_80010000);\n"
                    "s32 func_80012344(s32 a) {\n    return a;\n}\n", {"placeholder": 2}),
    "struct": ("struct Pair {\n    s32 a;\n};\ns32 Walk(struct Pair *p) {\n    return p->a;\n}\n", {"struct": 1}),
}


def _repo(td) -> pathlib.Path:
    repo = pathlib.Path(td).resolve()
    _git(repo, "init", "--quiet")
    return repo


def _commit(repo, msg) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit",
         "--quiet", "-m", msg)


def self_test_plan(check) -> None:
    levels = lambda found, lv: sorted({f[1] for f in found if f[0] == lv})  # noqa: E731
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        check("no plan: one INFO line", [f[0] for f in lint_plan(repo)] == ["INFO"])
        check("no plan: every phase absent", set(phase_state(repo).values()) == {"absent"})
        (repo / CONTEXT).write_text("- **Phase 0 — Governance and the firewall.** x\n| 1.4 | **The compiler pinned by evidence** |\n")
        check("no plan: the constitution's ladder is counted", "names 2 of the 11" in lint_plan(repo)[0][2])
        (repo / PLAN).write_text(self_plan())
        for n in range(5):
            (repo / "phase-ends").mkdir(exist_ok=True)
            (repo / "phase-ends" / ("PhaseEnd_Phase1.%d.md" % n)).write_text("x\n")
        _commit(repo, "plan")
        found = lint_plan(repo)
        check("a ladder plan is clean", plan_summary(found)[0] == "OK", found)
        st = phase_state(repo)
        check("state: closed, open, pending", (st[4], st[5], st[6]) == ("closed", "open", "pending"), st)
        # a slice stands for its phase; a dropped phase fails; a Changes line that names it does not
        slices = [_phase("1.8.1", "The campaign, slice 1", milestone="0 stubs", depends="1.7"),
                  _phase("1.8.2", "The campaign, slice 2", depends="1.8.1")]
        (repo / PLAN).write_text(self_plan(drop=(8,), extra=slices).replace("depends: 1.8 |", "depends: 1.8.2 |"))
        check("slices 1.8.m stand for phase 8", plan_summary(lint_plan(repo))[0] == "OK", lint_plan(repo))
        (repo / PLAN).write_text(self_plan(drop=(6,)).replace("depends: 1.6 |", "depends: 1.5 |"))
        found = lint_plan(repo)
        check("a dropped phase fails `ladder`", levels(found, "FAIL") == ["ladder"] and "1.6" in str(found), found)
        merged = self_plan(drop=(6,), changes=["2026-01-02 developer: phases 1.5 and 1.6 merged into 1.5 — a small game",
                                               "2026-01-03 router: phase 1.4 status -> closed"])
        (repo / PLAN).write_text(merged.replace("depends: 1.6 |", "depends: 1.5 |"))
        check("a merge with a Changes line passes", plan_summary(lint_plan(repo))[0] == "OK", lint_plan(repo))
        only_router = self_plan(drop=(4,), changes=["2026-01-03 router: phase 1.4 status -> closed"])
        (repo / PLAN).write_text(only_router.replace("depends: 1.4 |", "depends: 1.3 |"))
        check("the router's status line names no phase", "ladder" in levels(lint_plan(repo), "FAIL"))
        # grammar: a lost key, a bad status, a doubled id, a dependency with no line, another generation's id
        base = self_plan()
        for name, text, want in (
                ("a line with no scope", base.replace(" | scope: s", "", 1), "no `scope:`"),
                ("a status that is no status", base.replace("status: open", "status: done", 1), "status is 'done'"),
                ("an id with two lines", base.replace("- 1.2 ", "- 1.1 ", 1), "has 2 lines"),
                ("a dependency with no line", base.replace("depends: 1.9", "depends: 1.19"), "depends on 1.19"),
                ("an id of another generation", base.replace("- 1.10 ", "- 2.10 "), "not of generation 1"),
                ("a line that is no phase line", base.replace("- 1.0 Governance", "- Governance"), "not `- <G>.<n> <name>")):
            (repo / PLAN).write_text(text)
            found = lint_plan(repo)
            check("grammar: " + name, any(f[:2] == ("FAIL", "grammar") and want in f[2] for f in found), found)
        # numbering: an id over 1.10 with no Changes line; a line whose name is another phase's
        late = [_phase("1.11", "Stage-overlay campaign", depends="1.8")]
        (repo / PLAN).write_text(self_plan(extra=late))
        found = lint_plan(repo)
        check("numbering: 1.11 unnamed", levels(found, "WARN") == ["numbering"] and not levels(found, "FAIL"), found)
        (repo / PLAN).write_text(self_plan(extra=late, changes=["2026-01-02 developer: insert phase 1.11 — overlays"]))
        check("numbering: 1.11 named by a Changes line", plan_summary(lint_plan(repo))[0] == "OK", lint_plan(repo))
        (repo / PLAN).write_text(self_plan().replace("- 1.7 The codegen map and the permuter", "- 1.7 Publish early"))
        check("numbering: a renumbered name", "numbering" in levels(lint_plan(repo), "WARN"))
        # criteria, paths, markers, frozen
        (repo / PLAN).write_text(self_plan(milestones={8: "the census reads 400 stubs"}).replace("Done-criteria: d\n", ""))
        found = [f for f in lint_plan(repo) if f[1] == "criteria"]
        check("criteria: the line and the words", len(found) == 2 and "`0 stubs`" in found[1][2], found)
        (repo / PLAN).write_text(self_plan(milestones={2: "the map is in `docs/memory-map.md` and `make build` runs"}))
        (repo / "docs").mkdir()
        (repo / "phase-ends" / "PhaseEnd_Phase1.1.md").unlink()
        found = [f[2] for f in lint_plan(repo) if f[1] == "paths"]
        check("paths: the phase-end file and a milestone path", len(found) == 2 and "PhaseEnd_Phase1.1.md" in found[0]
              and "docs/memory-map.md" in found[1], found)
        (repo / "phase-ends" / "PhaseEnd_Phase1.1.md").write_text("x\n")
        (repo / "docs" / "memory-map.md").write_text("TODO(phase-2): the load addresses.\nTODO(phase-9): later.\n")
        (repo / "templates").mkdir()
        (repo / "templates" / "t.md").write_text("TODO(phase-2)\n")
        _commit(repo, "markers")
        found = [f[2] for f in lint_plan(repo) if f[1] == "markers"]
        check("markers: a closed phase's marker, not templates/", len(found) == 1 and found[0].startswith("1 ")
              and "docs/memory-map.md:1 (1.2)" in found[0], found)
        (repo / "docs" / "memory-map.md").write_text("The load addresses.\n")
        (repo / PLAN).write_text(self_plan())
        _commit(repo, "clean")
        check("frozen: an unchanged closed milestone", "frozen" not in levels(lint_plan(repo), "WARN"))
        (repo / PLAN).write_text(self_plan(milestones={3: "prints N of N, roughly"}))
        found = [f for f in lint_plan(repo) if f[1] == "frozen"]
        check("frozen: a closed milestone rewritten", len(found) == 1 and found[0][0] == "WARN" and "1.3" in found[0][2], found)
        (repo / PLAN).write_text(self_plan(milestones={7: "another open milestone"}))
        check("frozen: an open milestone may change", "frozen" not in levels(lint_plan(repo), "WARN"))
        # generation 2: the ladder is the closed generation's record
        gen2 = "# Generation 2 — the modding base\n\nGoal: g\nDone-criteria: d\n\n## Phases\n\n%s\n\n## Changes\n" % _phase(
            "2.1", "The round-trip disc")
        (repo / PLAN).write_text(gen2)
        found = lint_plan(repo)
        check("generation 2 with no record: a WARN", levels(found, "WARN") == ["ladder"] and not levels(found, "FAIL"), found)
        check("generation 2 with no record: the ladder counts as closed", set(phase_state(repo).values()) == {"closed"})
        end = "# GenerationEnd — Generation 1\n\n## Phases\n" + "".join(
            "- 1.%d | %s | milestone: m\n" % (n, name) for n, name, _, _ in LADDER if n != 8)
        (repo / "phase-ends" / "GenerationEnd_1.md").write_text(end + "- 1.8.1 | First cracks | milestone: m\n")
        check("generation 2 with its record", plan_summary(lint_plan(repo))[0] == "OK", lint_plan(repo))
        (repo / "phase-ends" / "GenerationEnd_1.md").write_text(end)
        check("generation 2: a phase the record lacks", "1.8" in str([f for f in lint_plan(repo) if f[1] == "ladder"]))
    full = "\n".join("- **Phase 1.%d %s** — milestone: m" % (n, name) for n, name, _, _ in LADDER)
    check("ladder: a full constitution", ladder_missing(full) == [])
    check("ladder: the kit's table rows", ladder_missing("\n".join("| %d | **%s** | m |" % (n, name) for n, name, _, _ in LADDER)) == [])
    check("ladder: two phases", ladder_missing("- **Phase 0 — Governance and the firewall.**\n- **Phase 1 — Extraction.**\n")
          == list(range(2, 11)))
    check("ladder: a word in prose is no phase", ladder_missing("We publish the census and the multipliers.\n") == list(range(11)))


def self_test_debt(check) -> None:
    check("a clean file has no debt", file_debt("src/a.c", C_CLEAN) == {}, file_debt("src/a.c", C_CLEAN))
    for kind, (text, want) in C_DEBT.items():
        check("one planted file: " + kind, file_debt("src/a.c", text) == want, file_debt("src/a.c", text))
    check("a struct in include/ is no debt", file_debt("include/a.h", C_DEBT["struct"][0]) == {})
    check("the address header may hold addresses", file_debt("include/addr.h", C_DEBT["address"][0]) == {})
    shared = _macros(strip("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\n"))
    check("a header's offset macro counts at each use", file_debt("src/a.c", "s32 Walk(void *p) {\n    return HP(p);\n}\n", shared)
          == {"offset": 1})
    check("unbased: a function with no row", file_debt("src/a.c", C_CLEAN, based=set()) == {"unbased": 1})
    check("unbased: a function with a row", file_debt("src/a.c", C_CLEAN, based={"Player_Hp"}) == {})
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        (repo / "include").mkdir()
        (repo / "src" / "clean.c").write_text(C_CLEAN)
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        (repo / "src" / "boot.s").write_text("nop\n")
        (repo / "include" / "include_asm.h").write_text("#define INCLUDE_ASM(d, n) __asm__(\".include \\\"n\\\"\");\n")
        (repo / "untracked.c").write_text(C_DEBT["goto"][0])
        _git(repo, "add", "src", "include")
        run = lambda *a, **kw: _capture(cmd_debt, repo, *a, **kw)  # noqa: E731
        rc, out = run()
        check("no baseline: the totals and exit 0", rc == 0 and "totals: goto 1, macro 1, asm 1 " in out and "no config/" in out, out)
        text = first_baseline(repo)
        check("the first baseline", text.endswith("mode admit\nskip include/include_asm.h\n1 asm src/boot.s\n1 goto src/walk.c\n")
              and text.startswith("# config/debt-baseline.txt: "), text)
        (repo / "config").mkdir()
        (repo / BASELINE).write_text(text)
        rc, out = run()
        check("an equal baseline passes", rc == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); mode admit)" in out, out)
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0] + C_DEBT["goto"][0].replace("Walk", "Run"))
        rc, out = run()
        check("a rise fails", rc == 1 and "DEBT FAIL rise goto src/walk.c: 2, its row is 1\n" in out, out)
        rc, out = run(update=True)
        check("--update refuses a rise without --admit", rc == 1 and "DEBT UPDATE refused" in out and
              (repo / BASELINE).read_text() == text, out)
        rc, out = run(update=True, admit=True)
        check("--update --admit admits it and prints it", rc == 0 and "DEBT ADMIT goto src/walk.c: 1 -> 2\n" in out and
              "2 goto src/walk.c\n" in (repo / BASELINE).read_text(), out)
        (repo / "src" / "walk.c").write_text(C_CLEAN.replace("Player_Hp", "Walk"))
        rc, out = run()
        check("a stale row fails", rc == 1 and "DEBT FAIL stale goto src/walk.c: 0, its row is 2: run " in out, out)
        rc, out = run(down=True)
        check("--down needs an equal baseline", rc == 1 and "not equal" in out, out)
        rc, out = run(update=True)
        check("--update lowers a row", rc == 0 and "DEBT INFO goto src/walk.c: 2 -> 0\n" in out and
              "goto" not in (repo / BASELINE).read_text(), out)
        rc, out = run(down=True)
        check("--down switches the mode", rc == 0 and "\nmode down\n" in (repo / BASELINE).read_text(), out)
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        rc, out = run(update=True, admit=True)
        check("mode down admits no rise", rc == 1 and "`mode down` admits none" in out, out)
        (repo / "src" / "walk.c").write_text(C_CLEAN)
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\thand-asm\tdocs/boot.md:3\t2026-01-02\n")
        rc, out = run()
        check("an evidence row clears an assembly file", rc == 1 and "DEBT FAIL stale asm src/boot.s: 0, its row is 1" in out, out)
        (repo / BASELINE).write_text("mode down\n1 goto src/walk.c\n1 goto src/walk.c\n")
        rc, out = run()
        check("a baseline with two rows of one pair", rc == 1 and "has two rows" in out, out)
        (repo / BASELINE).write_text("mode sideways\n")
        rc, out = run()
        check("a baseline line that is no row", rc == 1 and "config/debt-baseline.txt:1: not " in out, out)
        # the ledgers
        (repo / BASELINE).unlink()
        (repo / ASM_EVIDENCE).unlink()
        rc, out = _capture(cmd_names, repo)
        check("names: no ledger is not a failure", rc == 0 and out.count("NAMES INFO no config/") == 2, out)
        rc, out = _capture(cmd_names, repo, init=True)
        check("names --init writes the two header lines", rc == 0 and (repo / NAMES).read_text() == "\t".join(NAME_COLUMNS) + "\n"
              and (repo / ASM_EVIDENCE).read_text() == "\t".join(ASM_COLUMNS) + "\n", out)
        check("names: every function is unbased at first", "NAMES INFO 2 function(s) defined" in out, out)
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/clean.c:4\tthe string it prints\n"
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row)
        rc, out = _capture(cmd_names, repo)
        check("names: a good row", rc == 0 and "1 row(s): 1 accepted" in out and "NAMES INFO 0 function(s)" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("accepted", "sure").replace("string:", "guess:"))
        rc, out = _capture(cmd_names, repo)
        check("names: a bad decision and a bad evidence class", rc == 1 and "decision 'sure'" in out and "evidence 'guess:" in out, out)
        (repo / NAMES).write_text("kind\tname\n")
        check("names: a wrong header", _capture(cmd_names, repo)[0] == 1)


def self_test_toolchain(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "config").mkdir()
        check("toolchain: no file", toolchain_rows(repo) is None and cmd_toolchain_quiet(repo) == 0)
        (repo / "refs-tool").mkdir()
        tool = _repo(repo / "refs-tool")
        (tool / "a.py").write_text("x = 1\n")
        _commit(tool, "tool")
        head = _git(tool, "rev-parse", "HEAD").stdout.strip()
        (repo / "cc1.bin").write_bytes(b"cc1")
        digest = hashlib.sha256(b"cc1").hexdigest()
        rows = "\t".join(TOOL_COLUMNS) + "\nsplitter\tgit\t%s\trefs-tool\ncc1\tsha256\t%s\tcc1.bin\nlost\tgit\t%s\tnowhere\n" % (
            head, digest, head)
        (repo / TOOLCHAIN).write_text(rows)
        check("toolchain: at the pin, clean", [r[0] for r in toolchain_rows(repo)] == ["OK", "OK", "MISSING"], toolchain_rows(repo))
        check("toolchain: a missing path is not a failure", cmd_toolchain_quiet(repo) == 0)
        (tool / "a.py").write_text("x = 2\n")
        got = toolchain_rows(repo)
        check("toolchain: a dirty checkout fails", got[0][0] == "FAIL" and "local changes" in got[0][2], got)
        (tool / "a.py").write_text("x = 1\n")
        (repo / TOOLCHAIN).write_text(rows.replace(head, "0" * 40, 1).replace(digest, "0" * 64))
        got = toolchain_rows(repo)
        check("toolchain: off the pin, off the hash", [r[0] for r in got[:2]] == ["FAIL", "FAIL"] and cmd_toolchain_quiet(repo) == 1, got)
        (repo / TOOLCHAIN).write_text("\t".join(TOOL_COLUMNS) + "\nx\tdocker\ty\tz\n")
        check("toolchain: a kind that is no kind", toolchain_rows(repo)[0][0] == "FAIL")


def _capture(fn, *args, **kw) -> tuple[int, str]:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kw)
    return rc, buf.getvalue()


def cmd_toolchain_quiet(repo) -> int:
    return _capture(cmd_toolchain, repo)[0]


GUARD_SELF = ("# a guard file\n" + "\t".join(GUARD_COLUMNS) + "\n"
              "allow\tpath\tasm/README.md\t\n"
              "deny\tpath\tasm/\tasm/ is generated: run the splitter\n"
              "deny\tpath\tconfig/check.*.sha\tthe build writes the hash files\n"
              "deny\tbash\t\\bmake\\s+expected\\b\task the developer before a new baseline\n"
              "deny\tbash\t(\tan unclosed group\n"
              "not a rule\n")


def self_test_guard(check) -> None:
    rules = parse_guard(GUARD_SELF)
    check("guard: the rules, in order", [r[:2] for r in rules] == [("allow", "path"), ("deny", "path"), ("deny", "path"),
                                                                    ("deny", "bash"), ("deny", "bash")], rules)
    check("guard: the doctor's view of a bad file", len(guard_errors(GUARD_SELF)) == 2, guard_errors(GUARD_SELF))
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td).resolve()
        ev = lambda tool, **inp: {"tool_name": tool, "tool_input": inp, "cwd": str(root)}  # noqa: E731
        cases = [
            ("an Edit under a denied folder", ev("Edit", file_path=str(root / "asm/main/a.s")), "asm/ is generated"),
            ("a Write by a relative path", ev("Write", file_path="config/check.main.sha"), "the build writes"),
            ("the first matching row wins", ev("Edit", file_path=str(root / "asm/README.md")), None),
            ("a file no rule names", ev("Edit", file_path=str(root / "src/a.c")), None),
            ("a file outside the repository", ev("Edit", file_path="/somewhere/asm/a.s"), None),
            ("a Bash command a rule names", ev("Bash", command="cd x && make expected"), "ask the developer"),
            ("a Bash command no rule names", ev("Bash", command="make build"), None),
            ("a path rule does not read a command", ev("Bash", command="cat asm/main/a.s"), None),
            ("another tool", ev("Read", file_path=str(root / "asm/a.s")), None),
        ]
        for name, event, want in cases:
            got = guard_decision(event, rules, root)
            check("guard: " + name, (got is None) if want is None else (got or "").startswith(want), got)
        _git(root, "init", "--quiet")
        (root / "config").mkdir()
        (root / GUARD).write_text(GUARD_SELF)
        import io
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        rc, out = _capture(guard_hook, io.StringIO(json.dumps(cases[0][1])))
        answer = json.loads(out)["hookSpecificOutput"] if out else {}
        check("guard --hook: a denial is one JSON object, exit 0", rc == 0 and answer.get("permissionDecision") == "deny"
              and answer.get("hookEventName") == "PreToolUse" and "asm/ is generated" in answer.get("permissionDecisionReason", ""), out)
        for name, stdin in (("an allowed call", json.dumps(cases[3][1])), ("bad JSON", "{not json"), ("no event", ""),
                            ("an event with no cwd", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))):
            check("guard --hook: %s prints nothing, exit 0" % name, _capture(guard_hook, io.StringIO(stdin)) == (0, ""))
        (root / GUARD).unlink()
        check("guard --hook: no rules file allows the call", _capture(guard_hook, io.StringIO(json.dumps(cases[0][1]))) == (0, ""))


def self_test() -> int:
    bad = []

    def check(name, ok, detail=None):
        if not ok:
            bad.append(name)
            print("  FAILED: %s%s" % (name, "" if detail is None else " — %r" % (detail,)))

    saved = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        self_test_plan(check)
        self_test_debt(check)
        self_test_toolchain(check)
        self_test_guard(check)
    finally:
        if saved is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = saved
    print("floor %s" % ("SELF-TEST OK" if not bad else "SELF-TEST FAILED (%d)" % len(bad)))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["plan", "ladder", "debt", "names", "toolchain", "guard"])
    ap.add_argument("file", nargs="?", help="ladder: the constitution to read")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--admit", action="store_true")
    ap.add_argument("--down", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd == "guard":
        return guard_hook() if a.hook else 2
    if a.cmd == "plan":
        return cmd_plan(a.repo)
    if a.cmd == "ladder":
        return cmd_ladder(a.file or os.path.join(a.repo, CONTEXT))
    if a.cmd == "debt":
        return cmd_debt(a.repo, update=a.update, admit=a.admit, down=a.down)
    if a.cmd == "names":
        return cmd_names(a.repo, init=a.init)
    if a.cmd == "toolchain":
        return cmd_toolchain(a.repo)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
