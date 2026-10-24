#!/usr/bin/env python3
"""plan.py — the roadmap floor of a game repository: GENERATION_PLAN.md against the kit's ladder. Read-only.

    plan.py [--repo DIR]                  lint GENERATION_PLAN.md: `PLAN FAIL|WARN|INFO <check>: <detail>`; exit 1 on a FAIL
    plan.py ladder [FILE]                 the eleven ladder phases a constitution names (default: PROJECT_CONTEXT.md of
                                          the repository); exit 1 when one is missing
    plan.py --self-test

S7 reads the constitution with it, and the doctor's `roadmap` row and /psxdecomp:upgrade read the plan. No gate runs
it, and no game receives it: `psxd plan --repo .` runs it from the plugin.

The plan checks. `grammar` and `ladder` are a FAIL, the others a WARN.
  grammar    every phase line has its five keys, a unique id of this generation, a known status, depends that exist
  ladder     generation 1: each ladder phase n has a line `1.n`, or slices `1.n.m`, or a `## Changes` line that drops or
             merges 1.n (the id with one of the words drop, merge, fold, remove, replace, skip, omit)
  numbering  an id over 1.10 that no `## Changes` line names; a line 1.n whose name is not ladder phase n's. A
             `## Changes` line that names such an id and says `ladder phase n` makes it a part of phase n
  frozen     a closed phase's milestone differs from its text at the commit that closed it
  criteria   no `Done-criteria:` line; a milestone lost its required words (`N of N`, `0 stubs`, `format-check`)
  paths      a closed phase's `phase-end:` file, or a path in its milestone under a tracked folder, does not exist
             (a `## Changes` line that names the phase answers the milestone's paths)
  markers    a `TODO(phase-N)` in a tracked file while phase 1.N is closed (not in phase-ends/, templates/, .claude/,
             refs/ or psxdecomp's own tools/psxd_*.py)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from floor import _git, _read, lines  # noqa: E402

PLAN = "GENERATION_PLAN.md"
CONTEXT = "PROJECT_CONTEXT.md"
GEN_END = "phase-ends/GenerationEnd_%d.md"


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
LADDER_LINE = re.compile(r"^[\s>*#-]*(?:phase\s+(?:1\.)?|1\.|\|\s*(?:1\.)?(?=\d{1,2}\s*\|))(\d{1,2})\b(.*)$", re.I)


def ladder_found(text: str) -> set[int]:
    """The ladder phases a constitution names: a line that starts with the phase's number as `Phase 4`, `1.4` or the
    table cell `| 4 |`, and holds its name's words. A bare list number (`4. …`) names no phase."""
    found = set()
    for line in lines(text):
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
    """{heading: [(line number, line)]} of the `## ` sections; "" is the text above the first. An HTML comment that
    starts its line is blanked. Lines end at a newline and at nothing else, as PA3 reads them."""
    text = re.sub(r"^[ \t]*<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S | re.M)
    out, cur = {"": []}, ""
    for n, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if line.startswith("## "):
            cur = line[3:].strip()
            out.setdefault(cur, [])
        else:
            out[cur].append((n, line))
    return out


def phase_fields(line: str) -> dict:
    """One phase line as PA3 reads it: ` | ` parts the fields, a key may be spelled with `_`, the last value of a key
    wins. `unknown`: the parts that hold no known key (a ` | ` inside a milestone or a name cuts it there)."""
    parts = [p.strip() for p in re.sub(r"^\s*-\s+", "", line.strip()).split(" | ")]
    pid, name = (parts[0].split(None, 1) + ["", ""])[:2]
    out = {"id": pid, "name": name.strip(), "unknown": []}
    for p in parts[1:]:
        k, sep, v = p.partition(":")
        key = k.strip().lower().replace("_", "-")
        if sep and key in KEYS:
            out[key] = v.strip()
        else:
            out["unknown"].append(p)
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
        if re.match(r"\s*-\s+\S", line):
            plan.phases.append(dict(phase_fields(line), line=n, raw=line))
    plan.changes = [re.sub(r"^\s*-\s+", "", line).strip() for _, line in secs.get("Changes", []) if re.match(r"\s*-\s+\S", line)]
    return plan


def parse_gen_end(text: str) -> list[dict]:
    """The phases of a closed generation's record: `- 1.4 | <name> | milestone: …` under `## Phases`."""
    out = []
    for _, line in _sections(text).get("Phases", []):
        parts = [p.strip() for p in line[2:].split(" | ")] if line.startswith("- ") else []
        if len(parts) >= 2 and PHASE_ID.match(parts[0]):
            status = next((x for x in parts[2:] if x in ("open", "closed")), "closed")   # PA3 writes it; older records lack it
            out.append({"id": parts[0], "name": parts[1], "status": status})
    return out


ROUTER_LINE = re.compile(r"\brouter: phase \S+ status -> \w+$")
DROP_WORDS = re.compile(r"\b(?:drop|merg|fold|remov|replac|skip|omit)(?:e|es|ed|s|ped|ted|ing|ping|ting)?\b", re.I)
LADDER_WORDS = re.compile(r"\bladder phase (\d{1,2})\b", re.I)


def _id_rx(pid: str) -> re.Pattern:
    """The id as a token of its own: not a part of `v1.0`, of `1.10`, or of a size such as `1.5 GB`."""
    return re.compile(r"(?<![\w.])%s(?![\d.]*\d)(?!\s?(?:[GMKk]i?B|%%)\b)" % re.escape(pid))


def _named(changes: list[str], pid: str) -> bool:
    """A `## Changes` line names the id (PA3's own `router: phase 1.4 status -> closed` lines do not count; 3.28.8's
    phase close still writes them, `plan_edit.py gen-close` with `--by router`)."""
    rx = _id_rx(pid)
    return any(rx.search(c) and not ROUTER_LINE.search(c) for c in changes)


def _dropped(changes: list[str], pid: str) -> bool:
    """A `## Changes` line drops or merges the id: it names the id and holds one of the words of DROP_WORDS. A line
    that only mentions the id (`insert 1.8.1 after 1.8, before 1.9`) drops nothing."""
    rx = _id_rx(pid)
    return any(rx.search(c) and DROP_WORDS.search(c) and not ROUTER_LINE.search(c) for c in changes)


def _assigned(changes: list[str]) -> dict[str, int]:
    """{id over 1.10: ladder phase n} from each `## Changes` line that names the id and says `ladder phase n`."""
    out: dict[str, int] = {}
    for c in changes:
        m = LADDER_WORDS.search(c)
        if m and int(m[1]) <= 10 and not ROUTER_LINE.search(c):
            for pid in re.findall(r"(?<![\w.])1\.(?:1[1-9]|[2-9]\d)(?![\d.]*\d)", c):
                out.setdefault(pid, int(m[1]))
    return out


def _slot(pid: str, assigned=None) -> int | None:
    """The ladder phase of an id: n for 1.n and 1.n.m; for an id over 1.10, the phase a `## Changes` line gave it."""
    m = PHASE_ID.match(pid)
    if not m or int(m[1]) != 1:
        return None
    return int(m[2]) if int(m[2]) <= 10 else (assigned or {}).get("1.%s" % m[2])


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
    """{ladder phase n: "absent" | "pending" | "open" | "closed"}. A slice 1.n.m counts for n, and so does an id over
    1.10 that a `## Changes` line gives to `ladder phase n`. `closed`: every line of n is closed. `open`: a line of n is
    closed, or is open with every phase it depends on closed. `pending`: its lines wait for another phase. A later
    generation with no record of generation 1 counts the whole ladder as closed."""
    plan, gen1 = load_plan(repo)
    if plan is None:
        return {n: "absent" for n, _, _, _ in LADDER}
    if plan.generation not in (None, 1) and not gen1:
        return {n: "closed" for n, _, _, _ in LADDER}
    status = {p["id"]: p.get("status") for p in gen1}
    given = _assigned(plan.changes) if plan.generation in (None, 1) else {}
    out = {}
    for n, _, _, _ in LADDER:
        mine = [p for p in gen1 if _slot(p["id"], given) == n]
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
    """{id: its milestone at the first commit that holds it closed}; None outside a git history. The plan is read
    beside `repo`, also when `repo` is a folder inside its repository."""
    r = _git(repo, "log", "--format=%H", "--reverse", "--", PLAN)
    if r.returncode != 0 or not r.stdout.split():
        return None
    at: dict[str, str] = {}
    for sha in r.stdout.split()[-400:]:
        if not ids - set(at):
            break
        shown = _git(repo, "show", "%s:./%s" % (sha, PLAN))
        if shown.returncode != 0:
            continue
        for p in parse_plan(shown.stdout).phases:
            if p["id"] in ids and p["id"] not in at and p.get("status") == "closed":
                at[p["id"]] = p.get("milestone", "")
    return at


REPO_PATH = re.compile(r"`([\w.-]+(?:/[\w.-]+)+/?)`")
MARKER = re.compile(r"TODO\(phase-(\d+)\)")
MARKER_SKIP = (":!phase-ends", ":!templates", ":!.claude", ":!refs", ":!tools/psxd_*.py")   # history, PA3's, psxdecomp's own


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
        if p.get("unknown"):
            add("WARN", "grammar", "%s: ` | ` cuts the line at %r, which holds no key: a milestone or a name with ` | ` "
                "in it is read up to that point" % (where, p["unknown"][0][:40]))
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
            if state[n] == "absent" and not _dropped(plan.changes, "1.%d" % n):
                add("FAIL", "ladder", "no line 1.%d (%s), no slice 1.%d.m, and no `## Changes` line that drops or merges "
                    "1.%d" % (n, name, n, n))
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
                "is 1.n.m. A line that names it and says `ladder phase n` makes it a part of phase n" % (
                    p["id"], p["name"][:40]))
        elif n <= 10 and not m[3] and not re.search(LADDER[n][2], p["name"], re.I):
            add("WARN", "numbering", "%s is named %r: ladder phase %d is %r" % (p["id"], p["name"][:40], n, LADDER[n][1]))
    # criteria
    if plan.done_criteria is None:
        add("WARN", "criteria", "no `Done-criteria:` line")
    for n, _, _, must in LADDER if first else []:
        mine = [p for p in plan.phases if _slot(p["id"], _assigned(plan.changes)) == n]
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
    elif closed and _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        add("INFO", "frozen", "a shallow clone: the commits that closed %d phase(s) may be missing, so those are not "
            "checked" % len([p for p in closed if p["id"] not in at] or closed))
    for p in closed if at else []:
        if p["id"] in at and at[p["id"]] != p.get("milestone", ""):
            add("WARN", "frozen", "%s is closed and its milestone differs from its text at the commit that closed it: "
                "record a correction as a `## Changes` line" % p["id"])
    # paths
    top: dict[str, bool] = {}                       # {a first folder: it holds a tracked file}

    def there(path) -> bool:
        try:
            return path.exists()
        except OSError:                                # a name the file system refuses is a path that does not exist
            return False

    for p in closed:
        end = p.get("phase-end", "")
        if end and not (there(repo / end) and (repo / end).is_file()):
            add("WARN", "paths", "%s is closed and its phase-end file %s does not exist" % (p["id"], end[:80]))
        if _named(plan.changes, p["id"]):              # a correction of the closed phase is on record
            continue
        gone = []
        for x in dict.fromkeys(REPO_PATH.findall(p.get("milestone", ""))):
            first = x.split("/")[0]
            if first not in top:
                top[first] = bool(_git(repo, "ls-files", "--", first + "/").stdout.strip())
            if top[first] and not there(repo / x):     # an ignored folder (extracted/, build/) proves nothing
                gone.append(x)
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
        half = [_phase("1.3.1", "The all-assembly baseline, the executable", "closed", "1.2", "prints N of N"),
                _phase("1.3.2", "The all-assembly baseline, the overlays", "open", "1.3.1")]
        (repo / PLAN).write_text(self_plan(closed=3, drop=(3,), extra=half).replace("depends: 1.3 |", "depends: 1.3.2 |"))
        check("state: one closed slice and one open slice is an open phase", phase_state(repo)[3] == "open", phase_state(repo))
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
        passing = self_plan(drop=(9,), changes=["2026-01-04 developer: insert phase 1.8.1 after 1.8, before 1.9 Publish",
                                                "2026-01-05 developer: the v1.9 disc is out of scope; the volume is 1.9 GB"])
        (repo / PLAN).write_text(passing.replace("depends: 1.9 |", "depends: 1.8 |"))
        found = lint_plan(repo)
        check("a line that only mentions a dropped id exempts nothing", levels(found, "FAIL") == ["ladder"] and "1.9" in str(found), found)
        for word in ("merging 1.6 into 1.5", "removes 1.6", "replaced 1.6 by a slice of 1.5", "1.6 is dropped", "skipping 1.6"):
            check("a drop word: " + word, _dropped(["2026-01-02 developer: " + word], "1.6"), word)
        check("a word that only looks like one drops nothing", not _dropped(["2026-01-02 developer: 1.6 emerges; a foldout for 1.6"], "1.6"))
        check("an id inside a version or a size names no phase", not _named(["the v1.5 disc", "it grew to 1.5 GB", "see 1.50"], "1.5")
              and _named(["correction to 1.5 (closed)"], "1.5"))
        # an id over 1.10 is a part of the ladder phase that a Changes line gives it
        parts = [_phase("1.11", "Stage-overlay campaign", depends="1.8"), _phase("1.12", "Module-overlay campaign", depends="1.11")]
        gave = ["2026-01-06 developer: phases 1.11 and 1.12 were added after 1.8 — both are parts of ladder phase 8"]
        (repo / PLAN).write_text(self_plan(closed=9, extra=parts, changes=gave))
        check("state: an open part keeps its ladder phase open", phase_state(repo)[8] == "open", phase_state(repo))
        (repo / PLAN).write_text(self_plan(closed=9, extra=parts, changes=["2026-01-06 developer: insert 1.11 and 1.12"]))
        check("state: a part that no line gives to a phase counts for none", phase_state(repo)[8] == "closed", phase_state(repo))
        # PA3's reading of a line: an indented line, `phase_end:`, the last value of a key, a tab after the id
        odd = self_plan().replace("- 1.2 The", "  -\t1.2\tThe", 1).replace("| phase-end: phase-ends/PhaseEnd_Phase1.3.md",
                                                                           "| phase_end: phase-ends/PhaseEnd_Phase1.3.md")
        (repo / PLAN).write_text(odd.replace("- 1.6 ", "- 1.6 ", 1).replace("| status: open | phase-end: phase-ends/PhaseEnd_Phase1.6.md",
                                                                            "| status: closed | status: open | phase-end: phase-ends/PhaseEnd_Phase1.6.md"))
        found = lint_plan(repo)
        check("PA3's line forms are read", plan_summary(found)[0] == "OK" and phase_state(repo)[6] == "pending", found)
        (repo / PLAN).write_text(self_plan(milestones={2: "`ls | wc -l` prints 3"}))
        found = [f for f in lint_plan(repo) if f[1] == "grammar"]
        check("grammar: a ` | ` inside a milestone is said", len(found) == 1 and found[0][0] == "WARN" and "1.2" in found[0][2], found)
        (repo / PLAN).write_text(self_plan().replace("status: open | phase-end: phase-ends/PhaseEnd_Phase1.9.md",
                                                     "status: open | phase-end: phase-ends/PhaseEnd_Phase1.9.md\u2028"))
        check("a line ends at a newline and at nothing else", plan_summary(lint_plan(repo))[0] == "OK", lint_plan(repo))
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
        lost = {2: "the map is in `docs/memory-map.md`, the dump in `extracted/retail/manifest.jsonl`, and `make build` runs"}
        (repo / PLAN).write_text(self_plan(milestones=lost))
        (repo / "docs").mkdir()
        (repo / "docs" / "INDEX.md").write_text("x\n")
        _git(repo, "add", "docs")
        (repo / "phase-ends" / "PhaseEnd_Phase1.1.md").unlink()
        found = [f[2] for f in lint_plan(repo) if f[1] == "paths"]
        check("paths: the phase-end file and a milestone path", len(found) == 2 and "PhaseEnd_Phase1.1.md" in found[0]
              and "docs/memory-map.md" in found[1], found)
        (repo / "extracted").mkdir()                   # an untracked folder on one machine changes nothing
        again = [f[2] for f in lint_plan(repo) if f[1] == "paths"]
        check("paths: an untracked folder is not read", again == found, again)
        (repo / PLAN).write_text(self_plan(milestones=lost, changes=["2026-01-07 developer: correction to 1.2 (closed): the map moved"]))
        again = [f[2] for f in lint_plan(repo) if f[1] == "paths"]
        check("paths: a Changes line answers a closed milestone", len(again) == 1 and "PhaseEnd_Phase1.1.md" in again[0], again)
        (repo / PLAN).write_text(self_plan().replace("phase-end: phase-ends/PhaseEnd_Phase1.3.md", "phase-end: phase-ends/" + "x" * 300))
        check("paths: a name the file system refuses is a missing path", any("1.3" in f[2] for f in lint_plan(repo) if f[1] == "paths"))
        (repo / "phase-ends" / "PhaseEnd_Phase1.1.md").write_text("x\n")
        (repo / "docs" / "memory-map.md").write_text("TODO(phase-2): the load addresses.\nTODO(phase-9): later.\n")
        (repo / "templates").mkdir()
        (repo / "templates" / "t.md").write_text("TODO(phase-2)\n")
        for skipped in ("phase-ends/PhaseEnd_Phase1.2.md", ".claude/agents/a.md", "refs/x/notes.md"):   # history, PA3's, upstream
            (repo / skipped).parent.mkdir(parents=True, exist_ok=True)
            (repo / skipped).write_text("TODO(phase-2)\n")
        (repo / "tools").mkdir()
        (repo / "tools" / "psxd_floor.py").write_text("# a self-test string: TODO(phase-2)\n")   # psxdecomp's own tool
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
        with tempfile.TemporaryDirectory() as outer:   # the game in a folder of a larger repository: its plan is read there
            big = _repo(outer)
            (big / "game" / "phase-ends").mkdir(parents=True)
            (big / "game" / PLAN).write_text(self_plan())
            _commit(big, "closed")
            (big / "game" / PLAN).write_text(self_plan(milestones={3: "prints N of N, roughly"}))
            got = [f for f in lint_plan(big / "game") if f[1] == "frozen"]
            check("frozen: a plan in a folder of a repository", len(got) == 1 and got[0][0] == "WARN", got)
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
        (repo / "phase-ends" / "GenerationEnd_1.md").write_text(
            end.replace("- 1.9 | Publish | milestone: m\n", "- 1.9 | Publish | milestone: m | open | PhaseEnd_Phase1.9.md\n"))
        st = phase_state(repo)
        check("generation 2: the record's own status is read", (st[9], st[7]) == ("open", "closed"), st)
    full = "\n".join("- **Phase 1.%d %s** — milestone: m" % (n, name) for n, name, _, _ in LADDER)
    check("ladder: a full constitution", ladder_missing(full) == [])
    check("ladder: the kit's table rows", ladder_missing("\n".join("| %d | **%s** | m |" % (n, name) for n, name, _, _ in LADDER)) == [])
    check("ladder: two phases", ladder_missing("- **Phase 0 — Governance and the firewall.**\n- **Phase 1 — Extraction.**\n")
          == list(range(2, 11)))
    check("ladder: a word in prose is no phase", ladder_missing("We publish the census and the multipliers.\n") == list(range(11)))
    notes = "1. The extraction took two hours.\n9. We will publish nothing.\n- 3.8 campaign for the mayor\n5 census forms\n"
    check("ladder: a numbered list is no ladder", ladder_missing(notes) == list(range(11)), ladder_found(notes))


def self_test() -> int:
    bad = []

    def check(name, ok, detail=None):
        if not ok:
            bad.append(name)
            print("  FAILED: %s%s" % (name, "" if detail is None else " — %r" % (detail,)))

    self_test_plan(check)
    print("plan %s" % ("SELF-TEST OK" if not bad else "SELF-TEST FAILED (%d)" % len(bad)))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["ladder"])
    ap.add_argument("file", nargs="?", help="ladder: the constitution to read")
    ap.add_argument("--repo", help="the repository; default: the git checkout that holds the working directory")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.repo is None:
        top = _git(".", "rev-parse", "--show-toplevel")
        a.repo = top.stdout.strip() if top.returncode == 0 and top.stdout.strip() else "."
    if a.cmd == "ladder":
        return cmd_ladder(a.file or os.path.join(a.repo, CONTEXT))
    return cmd_plan(a.repo)


if __name__ == "__main__":
    sys.exit(main())
