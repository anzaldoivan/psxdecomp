#!/usr/bin/env python3
"""floor.py — the roadmap, tooling and readability floor of a game repository (psxdecomp's docs/ops/psxdecomp-floor.md).

    floor.py plan [--repo DIR]            lint GENERATION_PLAN.md: `PLAN FAIL|WARN|INFO <check>: <detail>`; exit 1 on a FAIL
    floor.py ladder FILE                  the eleven ladder phases a constitution names; exit 1 when one is missing
    floor.py debt [--repo DIR]            count the readability debt of the tracked source against config/debt-baseline.txt;
                                          exit 1 when a count is over its row (a rise) or under it (a stale row), with
                                          no baseline, and with no policy line for a kind
    floor.py debt [--staged | --rev REV] [--against BASE]
                                          count the index or the revision REV in the work tree's place (no checkout);
                                          --against: judge the change since the revision BASE by BASE's own policy
    floor.py debt --bodies [--staged | --rev REV]
                                          the same counts by function body: one `DEBT BODY <path> <function>` line per
                                          body with debt, `(file scope)` for what no body holds; no check
    floor.py debt --files [--public] [--staged | --rev REV]
                                          the state of each C file: `stubs` (a function is still assembly), `matched`
                                          (every function is in C, and debt is left) or `finished` (no debt of any
                                          kind); the last line is the count that a README's generated block shows.
                                          --public: of the files that config/public-paths.txt lists only, which is what
                                          the public repository of a game in split mode can count itself
    floor.py debt --update                rewrite the rows to the counts of now; refused when the change since HEAD is
                                          one that HEAD's policy does not admit
    floor.py debt --recount               write the baseline in version 2: the rows of now and a policy line for each
                                          kind that has none; refused when the source differs from HEAD's
    floor.py debt --down [KIND]           switch a kind (or every kind) to `down`, one way: it never rises again
    floor.py debt --raise KIND N --reason TEXT
                                          the developer's act: a dated `raise` line that lets one change go over by N
    floor.py gate --staged | --bank | --ci BASE..HEAD | --push [BASE..HEAD]
                                          every check of the floor, each judged against what the change cannot
                                          rewrite: `GATE FAIL <check>: <detail>` lines; exit 1 on a FAIL. --staged: the
                                          index against HEAD (the commit hook). --bank: the work tree against HEAD, with
                                          the files git does not track yet; it writes the rows of an admitted change
                                          and runs the game's own check. --ci: each commit of the range against its
                                          parent, and the head of the range against its base. --push: as --ci, and the
                                          game's own check
                                          The tree is also read for a symbol dump (`symdump`): a tracked text file
                                          fails when 64 lines in a row have the shape of a PsyQ symbol dump. Such a
                                          text is a file of another build
    floor.py trial FILE [--func NAME]     take each register pin and each empty asm statement of the file's functions out
                                          in turn and ask the game's probe (`[trial] probe` of the record: exit 0 match,
                                          1 no match, 2 or more an error) whether the function still matches. What the
                                          match does not need is gone. What it needs gets a `// !FAKE: <reason>` line
                                          and a row in config/trials.tsv
    floor.py trial --recheck [--against BASE | --base-rows FILE] [--rows N]
                                          run rows again: those that are new since BASE and N at random; exit 1 on a
                                          row that says `kept` for a crutch the function matches without
    floor.py names [--init] [--repo DIR]  check config/names.tsv and config/asm-evidence.tsv; --init writes their header lines
    floor.py names [--staged | --rev REV] [--against BASE]
                                          the ledgers of the index or of a revision; --against: open only the rows that
                                          are new since the revision BASE
    floor.py toolchain [--repo DIR]       config/toolchain.tsv: each pinned checkout at its pin and clean, each file at its hash
    floor.py guard --hook                 a PreToolUse hook: stdin is the event, config/guard.tsv holds the rules
    floor.py --self-test

psxdecomp copies this file into a game as tools/psxd_floor.py. It uses the standard library only and it imports
nothing of the plugin. It writes the baseline (`debt --update`, `--recount`, `--down`, `--raise`, `gate --bank`), the
header line of each of the two ledgers (`names --init`), and, for `trial`, the source file it is given and
config/trials.tsv.

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

The debt kinds (one `<count> <kind> <path>` row each in the baseline). Every tracked file with a C or an assembly
suffix is read, in any folder but the splitter's output, the build's, the reference library, the folders of tools,
documents, records and tests, and the work folders of a campaign (drafts/, waves/, repro/, scratch/, sandbox/):
  pin              `register T x asm("$n")` (also `__asm__`, `__asm`): a register forced by hand
  goto             a `goto`, or a macro that hides one (each use)
  barrier          an empty asm statement, `__asm__("")`: it forces the compiler and holds no instruction
  <those three>-unmarked
                   one of them with no `// !FAKE: <reason>` comment of its own: on its line, or alone on the line
                   above. One marker covers one construct, and a marker with no reason covers none
  offset           a field read by its offset: `*(T *)(p + N)`, `((T *)p)[N]`, `M2C_FIELD(`, a byte pointer plus a
                   number, or a macro that hides one (each use). A sum with a variable is not counted
  address          a literal in the console's address ranges (RAM, scratchpad, I/O, BIOS) with no symbol, or a macro
                   that hides one (each use), outside the address header (`[debt] address_header`, include/addr.h)
  cast             an integer made of a pointer, or a pointer made of an integer: `(s32)&x`, `(T *)(s32)x`
  field            a member or a name `unk_10`, `field_0x10`: a field that has an offset and no name
  macro            a `#define` whose body holds `{`, `;` or a line continuation
  asm              an assembly file, an inline asm statement, or a macro that holds one (the macro and each use),
                   with no row in config/asm-evidence.tsv
  obscured         text that hides code from this tool: a statement outside every function body it sees (a head in
                   K&R form, by a macro, or not in column 0), a line continuation outside a directive, a digraph or
                   a trigraph for a brace, a source behind a symbolic link, an `#include` of C code from a folder
                   that is not read. A file with `.inc` in its name is a fragment that other files include inside a
                   function body: its statements are counted in its own file, and they rise only when each body that
                   includes it is new
  placeholder      a `func_XXXXXXXX` or `D_XXXXXXXX` name defined in a C file (also `FUN_`, `DAT_`, `sub_`, `loc_`)
  placeholder-use  each other place where such a name stands: a call, a read, a declaration
  unbased          any other function defined in a C file with no accepted row in config/names.tsv (once that file
                   exists)
  struct           a struct, union or enum body outside an include/ folder
  extern           an `extern` declaration or a prototype in a C file: a declaration has one owner, a header
  filename         a source file named by an address or a number (`func_80012344.c`, `misc12.c`)
  flag, reservation
                   a compiler option of one file, and a register taken from the compiler (`-ffixed-N`). The game
                   counts them: `[debt] flags` of the record names a command that prints `<count> <kind> <path>` lines
An `INCLUDE_ASM` stub is not debt: the progress report gives it no credit. The stub macro's own definition is not debt
either, nor is a file-scope asm statement of a header that holds assembler directives only.

The baseline's policy lines (one per kind; `debt --recount` writes the starting ones):
  mode <kind> down                              the kind never rises
  mode <kind> admit-new                         debt arrives only with a new function body: a body that exists, moves
                                                or is renamed never gets worse, and what stands outside a function
                                                rises only in a file that gets a new body
  budget <kind> <n> base <count> <bodies> <stubs>
                                                as admit-new, and the total grows by at most n for each 100 new bodies
                                                since the anchor, plus 2. A new body takes an INCLUDE_ASM line away
  raise <kind> <n> <date> <reason>              the developer lets the change that adds this line go over by n
A change is judged by the policy of the revision it starts from (`debt --against`): it cannot weaken a mode, raise a
budget, move an anchor, add a `skip` line or delete the file.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import signal
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
VERSION = "0.6.0"                                    # psxdecomp's version: a game's tool changes only to a later one


class Fail(Exception):
    """A refusal: printed with its command's prefix, exit 1."""


def _read(path) -> str | None:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _git(repo, *args) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, errors="replace")
    except OSError as e:                               # no git on this machine (a build container): as outside a repository
        return subprocess.CompletedProcess(args, 127, "", str(e))


def entry_match(entry: str, path: str) -> bool:
    """One entry in the syntax of config/public-paths.txt: `dir/` is a prefix, any other entry is an fnmatch glob."""
    return path.startswith(entry) if entry.endswith("/") else fnmatch.fnmatchcase(path, entry)


# ---- the tree reader: one source of files (the work tree, the index or a revision); nothing is exported to disk ----
INDEX = "index"
LINKS = ("120000", "160000")                         # a symbolic link and a submodule: not a file of this tree


class Tree:
    """The files of a repository from one source: the work tree (`source` None), the index (INDEX) or a revision.
    `paths`: the tracked files, sorted (a work tree with `untracked`: the files git neither tracks nor ignores as
    well). `read`: a file's text with CRLF and a lone CR as LF, or None for a path the source lacks, a symbolic link or a submodule.
    The index and a revision are read through one `git cat-file --batch`, so a check of a commit needs no checkout.
    Outside a git repository the work tree is every file under the folder."""

    def __init__(self, repo, source: str | None = None, untracked: bool = False):
        self.repo, self.source = pathlib.Path(repo), source
        self._blob: dict[str, str] = {}
        self._text: dict[str, str | None] = {}
        self._cat = None
        self.memo: dict = {}                           # what a check derived from this tree, by its own key
        self._set: set | None = None
        self.links: list[str] = []                     # the tracked symbolic links: no file of the tree, and said so
        self._keep = None                              # a view (`only`): the test of the paths it holds
        self._whole: Tree | None = None                # and the tree it is a view of, which owns the git process
        if source is None:
            r = _git(repo, "ls-files", "-z", *(("--cached", "--others", "--exclude-standard") if untracked else ()))
            if r.returncode == 0:
                found = {p for p in r.stdout.split("\0") if p}
            else:
                found = {f.relative_to(self.repo).as_posix() for f in self.repo.rglob("*")
                         if f.is_file() and ".git" not in f.relative_to(self.repo).parts}
            self.paths = sorted(found)
            self.links = [p for p in self.paths if is_source(p) and (self.repo / p).is_symlink()]
            return
        r = _git(repo, "ls-files", "-z", "-s") if source == INDEX else _git(repo, "ls-tree", "-r", "-z", source)
        if r.returncode != 0:
            raise Fail("git cannot read %s: %s" % ("the index" if source == INDEX else source,
                                                   (r.stderr or "").strip()[:200]))
        for rec in r.stdout.split("\0"):
            meta, tab, path = rec.partition("\t")
            cells = meta.split()
            if tab and len(cells) == 3 and cells[0] not in LINKS:
                self._blob.setdefault(path, cells[1] if source == INDEX else cells[2])
            elif tab and cells[:1] == ["120000"]:
                self.links.append(path)
        self.paths = sorted(self._blob)

    def only(self, keep) -> "Tree":
        """A view of this tree that holds the paths `keep(path)` accepts and no other: what a public repository
        holds of a game in split mode. A file outside the view reads as absent."""
        view = Tree.__new__(Tree)
        view.__dict__.update(self.__dict__)
        view.paths = [p for p in self.paths if keep(p)]
        view.links = [p for p in self.links if keep(p)]
        view._text, view.memo, view._set, view._keep, view._whole = {}, {}, None, keep, self
        return view

    def has(self, path: str) -> bool:
        """The source holds the file: a tracked one, or (a work tree with `untracked`) one that git does not ignore."""
        if self._set is None:
            self._set = set(self.paths)
        return path in self._set

    def read(self, path: str) -> str | None:
        if self._keep is not None:
            return self._whole.read(path) if self._keep(path) else None
        if path not in self._text:
            if self.source is None:
                f = self.repo / path
                try:
                    data = None if f.is_symlink() else f.read_bytes()
                except OSError:
                    data = None
            else:
                data = self._object(self._blob[path]) if path in self._blob else None
            self._text[path] = None if data is None else data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        return self._text[path]

    def raw(self, path: str) -> bytes | None:
        """A file's bytes as the source holds them; None as `read`."""
        if self._keep is not None:
            return self._whole.raw(path) if self._keep(path) else None
        if self.source is not None:
            return self._object(self._blob[path]) if path in self._blob else None
        f = self.repo / path
        try:
            return None if f.is_symlink() else f.read_bytes()
        except OSError:
            return None

    def _object(self, sha: str) -> bytes | None:
        if self._cat is None:
            self._cat = subprocess.Popen(["git", "-C", str(self.repo), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._cat.stdin.write(sha.encode() + b"\n")
        self._cat.stdin.flush()
        head = self._cat.stdout.readline().split()
        if len(head) != 3:                             # `<sha> missing`
            return None
        data = self._cat.stdout.read(int(head[2]) + 1)[:-1]
        return data if head[1] == b"blob" else None

    def close(self) -> None:
        if self._cat is not None and self._whole is None:
            self._cat.stdin.close()
            self._cat.stdout.close()
            self._cat.wait()
            self._cat = None

    def __del__(self):
        try:
            self.close()
        except Exception:                              # the interpreter is closing: the pipe is gone already
            pass


def source_name(source: str | None) -> str:
    return "the work tree" if source is None else "the index" if source == INDEX else source


def sibling() -> pathlib.Path:
    """psxdecomp's other tool, beside this file: publish.py in the plugin, psxd_publish.py in a game and in a
    temporary copy of a commit's tools. Each tool runs the other one from its own folder, never from the tree it
    checks."""
    me = pathlib.Path(__file__).resolve()
    return me.with_name(me.name.replace("floor", "publish"))


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
    """A `## Changes` line names the id (the router's own `phase 1.4 status -> closed` lines do not count)."""
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


# ---- the readability debt -----------------------------------------------------------------------------------------
KINDS = ("pin", "pin-unmarked", "goto", "goto-unmarked", "barrier", "barrier-unmarked", "offset", "address", "cast",
         "field", "macro", "asm", "obscured", "placeholder", "placeholder-use", "unbased", "struct", "extern", "filename",
         "flag", "reservation")
NUM = r"(?:0[xX][0-9A-Fa-f]+|\d+)"
OFFX = rf"(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*)(?:\s*[-+*]\s*(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*))*"
OPND = r"\(?\s*&?\s*\w+(?:\s*(?:->|\.)\s*\w+|\s*\[[^\[\]\n]*\])*\s*\)?"
PTR = r"\(\s*[\w ]+?\s*\*+\s*\)"
CAST = r"\(\s*[\w ]+?\s*\**\s*\)"
CHR = r"(?:const\s+)?(?:(?:unsigned|signed)\s+)?(?:char|[su]8)"
# A field read by its offset, in four forms, and a byte pointer plus a number. A sum with a variable (`(u8 *)dst + n`)
# is pointer arithmetic.
OFFSET = re.compile(
    rf"\*\s*{PTR}\s*\(\s*(?:{CAST}\s*)?{OPND}\s*\+\s*{OFFX}\s*\)"                  # *(T *)(p + N), *(T *)((U *)p + N)
    rf"|\*\s*\(\s*{PTR}\s*{OPND}\s*\+\s*{OFFX}\s*\)"                               # *((T *)p + N)
    rf"|{PTR}\s*\(\s*{PTR}\s*{OPND}\s*\+\s*{OFFX}\s*\)\s*\)\s*(?:->|\[)"            # ((T *)((U *)p + N))->f
    rf"|\(\s*{PTR}\s*{OPND}\s*\)\s*\[\s*{NUM}\s*\]"                                 # ((T *)p)[N]
    rf"|\(\s*{CHR}\s*\*+\s*\)\s*{OPND}\s*\+\s*{NUM}(?![\w.])"                         # (u8 *)p + N
    r"|\bM2C_FIELD\s*\(")
INT = r"(?:(?:(?:un)?signed\s+)?(?:int|long|short)|[su](?:8|16|32)|u?intptr_t)"
# An integer made of a pointer, or a pointer made of an integer: (s32)&x, (s32)(T *)p, (T *)(s32)x, (T *)((s32)x + n)
CASTS = re.compile(rf"\(\s*{INT}\s*\)\s*(?:&\s*\w|{PTR})|{PTR}\s*\(?\s*\(\s*{INT}\s*\)")
FIELD = re.compile(r"\b(?:unk|field)_?(?:0[xX])?[0-9A-Fa-f]{1,6}\b")
# A literal in the console's address ranges: main RAM and its mirrors, the scratchpad and the I/O ports, the BIOS ROM.
ADDRESS = re.compile(r"(?<![\w.])0[xX]0*(?:(?:8|[aA])0[01][0-9A-Fa-f]{5}|[19bB][fF]80[0-9A-Fa-f]{4}"
                     r"|[19bB][fF][cC][0-7][0-9A-Fa-f]{4})(?![0-9A-Fa-f])")
SIGN_BIT = re.compile(r"0[xX]0*80000000")               # the sign mask too: an address only behind a pointer cast
STUB_MACROS = ("INCLUDE_ASM", "INCLUDE_RODATA")       # the stub's own definition: assembly by design
ASM_WORD = r"(?:asm|__asm__|__asm)"
PIN = re.compile(r'\bregister\b[^;{}]*?\b%s\s*\(\s*"' % ASM_WORD)
GOTO = re.compile(r"\bgoto\s+\w+\s*;")
STRUCT = re.compile(r"\b(?:struct|union|enum)\b(?:\s*__attribute__\s*\(\(.*?\)\))?\s*\w*\s*\{")
INLINE_ASM = re.compile(r"\b%s\b\s*(?:(?:volatile|__volatile__)\b\s*)?\(" % ASM_WORD)
ASM_TEXT = re.compile(r'\s*((?:"(?:\\.|[^"\\\n])*"\s*)+)\)')              # the strings of an asm statement, behind its `(`
# Text that hides code from this tool: a statement outside every function body that the tool sees (a head in K&R
# form, by a macro, or not in column 0), a line continuation outside a directive, a digraph or a trigraph for a brace.
STATEMENT = re.compile(r"\breturn\b|\bgoto\s+\w+\s*;|\b(?:if|for|while|switch)\s*\(")
SPLICE = re.compile(r"\\\n|<%|%>|\?\?[<>/]")
EXTERN = re.compile(r"\bextern\b|^(?!static\b|typedef\b)(?:[A-Za-z_]\w*[\s*]+)+?[A-Za-z_]\w*\s*\([^;{}]*\)\s*;", re.M)
FILENAME = re.compile(r"(?:(?:func|code|text|seg|file|unk|misc|task|gap|data|rodata|bss)_?[0-9A-Fa-f]{2,}|[0-9A-Fa-f]{5,8})", re.I)
DEFINE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+(\w+)((?:\\\n|[^\n])*)", re.M)
PREPROC = re.compile(r"^[ \t]*#(?:\\\n|[^\n])*", re.M)
DEF_FUNC = re.compile(r"^(?:[A-Za-z_]\w*[\s*]+)+?([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.M)
DEF_DATA = re.compile(r"^(?!extern\b)(?:[A-Za-z_]\w*[\s*]+)+?((?:D|DAT)_[0-9A-Fa-f]{8}\w*)\s*(?:\[[^\]\n]*\]\s*)*[=;]", re.M)
PLACEHOLDER = re.compile(r"^(?:func|D|FUN|DAT|sub|loc)_[0-9A-Fa-f]{8}")      # a splitter's name, or a disassembler's
PLACEHOLDER_USE = re.compile(r"\b(?:func|D|FUN|DAT|sub|loc)_[0-9A-Fa-f]{8}\w*")
NOT_A_NAME = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "main"}
_STRIP = re.compile(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", re.S)
C_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".inc")              # read as C; the suffix is read in lower case
ASM_SUFFIXES = (".s", ".asm", ".sx")                                          # an assembly file: one count, unless a row
# Every tracked file with one of those suffixes counts, in any folder but these: the splitter's output, what a build
# or a dump writes, the reference library, and the folders that hold tools, documents, records and tests.
NOT_SOURCE = ("asm/", "build/", "expected/", "extracted/", "refs/", "tools/", "docs/", "config/", "tests/", "fixtures/",
              "cookbook/", "drafts/", "waves/", "repro/", "scratch/", "sandbox/")     # the last five: where a campaign works
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*"([^"\n]+)"', re.M)
ADDRESS_HEADER = "include/addr.h"
FIRST_SKIP = ("include/include_asm.h",)             # the stub macro's header, where a game keeps one
BASELINE_HEAD = (
    "%s: the count of readability debt in each tracked source file (`python3 %s --help` lists the kinds)." % (
        BASELINE, VENDORED),
    "`python3 %s debt` fails when a count is over its row, and when a row is over its count." % VENDORED,
    "After a change, run `python3 %s debt --update`. It refuses a rise in a function body that exists." % VENDORED,
    "A policy line gives each kind its mode: `down` (never rises), `admit-new` (debt arrives only with a new function",
    "body) or `budget <n>` (as admit-new, at most n for each 100 new bodies since the anchor). A mode only gets stronger.",
    "A `raise` line is the developer's: `python3 %s debt --raise <kind> <n> --reason <text>`." % VENDORED,
    "A `skip` line names files that the checker does not read. A change cannot add one.")
OLD_HEADS = ("%s: the count of readability debt" % BASELINE, "`python3 %s debt` fails when" % VENDORED,   # version 1's
             "After a change, run `python3 %s debt --update`. In `mode admit`" % VENDORED,
             "`python3 %s debt --down` switches" % VENDORED, "A `skip` line names files that the checker does not read.")


def strip(text: str) -> str:
    """Comments and string bodies become spaces. Newlines stay, so a line number is the same in both texts."""
    def blank(m):
        s = m.group(0)
        if s[0] == "/":
            return re.sub(r"[^\n]", " ", s)
        return s[0] + " " * (len(s) - 2) + s[-1] if len(s) >= 2 else s
    return _STRIP.sub(blank, text)


def _address_at(text: str) -> list[int]:
    """Where the address literals of a text start. `0x80000000` is the sign mask as well, so it counts only behind a
    pointer cast."""
    return [m.start() for m in ADDRESS.finditer(text)
            if not (SIGN_BIT.fullmatch(m.group(0)) and not re.search(r"\*\s*\)\s*\(?\s*$", text[:m.start()]))]


def _addresses(text: str) -> int:
    return len(_address_at(text))


MACRO_KINDS = ("asm", "goto", "offset", "address")   # what a macro can hide; the first that its body holds is its kind


def _macros(body: str, known=None) -> dict[str, str]:
    """{macro name: its kind of MACRO_KINDS} for each `#define` whose body holds an asm word, a `goto`, an offset
    read or an address, or uses a macro that does (`known` and the file's own, to a fixed point). M2C_FIELD is
    counted by its name, and the stub macros are not debt."""
    defs = [(m.group(1), m.group(2)) for m in DEFINE.finditer(body) if m.group(1) not in ("M2C_FIELD",) + STUB_MACROS]
    out = {}
    for name, text in defs:
        if re.search(r"\b%s\b" % ASM_WORD, text):
            out[name] = "asm"
        elif re.search(r"\bgoto\b", text):
            out[name] = "goto"
        elif OFFSET.search(text):
            out[name] = "offset"
        elif _addresses(text):
            out[name] = "address"
    grew = True
    while grew:
        grew = False
        seen = dict(known or {}, **out)
        for name, text in defs:
            if name in out:
                continue
            for kind in MACRO_KINDS:
                if _uses([k for k, v in seen.items() if v == kind and k != name], text):
                    out[name], grew = kind, True
                    break
    return out


def _use_rx(names) -> re.Pattern | None:
    return re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, sorted(names)))) if names else None


def _uses(names, text: str) -> int:
    rx = _use_rx(names)
    return len(rx.findall(text)) if rx else 0


BRACE = re.compile(r"[{}]")
STUB_USE = re.compile(r"^[ \t]*INCLUDE_ASM\s*\(", re.M)
STUB_NAME = re.compile(r"^[ \t]*INCLUDE_ASM\s*\([^;]*?\b([A-Za-z_]\w*)\s*\)", re.M)
SCOPE = ""                                             # the name of a file's bucket for what no function body holds


def extents(code: str) -> list[tuple[str, int, int]]:
    """[(name, start, end)] of the function bodies of a stripped text, in order. A body starts at a definition in
    column 0 (DEF_FUNC) and ends behind its matching brace. A definition inside an open body is dropped. Two heads
    with nothing between them but space are one body (an `#if` that chooses the head: the directives are blank
    here). A body whose braces never close ends at the next definition in column 0. What no body holds is the
    file's own scope: a K&R definition and a definition by a macro are read as that scope."""
    heads = [m for m in DEF_FUNC.finditer(code) if m.group(1) not in NOT_A_NAME]
    out, i = [], 0
    while i < len(heads):
        m, j = heads[i], i + 1
        opened = m.end() - 1
        while j < len(heads) and not code[opened + 1:heads[j].start()].strip():
            opened = heads[j].end() - 1                # another head of the same body
            j += 1
        depth, end = 0, None
        for brace in BRACE.finditer(code, opened):
            depth += 1 if brace.group() == "{" else -1
            if depth == 0:
                end = brace.end()
                break
        if end is None:
            end = heads[j].start() if j < len(heads) else len(code)
        while j < len(heads) and heads[j].start() < end:
            j += 1
        out.append((m.group(1), m.start(), end))
        i = j
    return out


_SCANS: dict[tuple, dict] = {}                         # one scan per text and context: a range of commits repeats most


def _plumbing(plain: str, at: int) -> bool:
    """The asm statement whose `(` ends at `at` holds assembler directives only (`.include`, `.macro` and its lines):
    the plumbing of the stub macro, not an instruction."""
    m = ASM_TEXT.match(plain, at)
    if not m:
        return False
    text = "".join(re.findall(r'"((?:\\.|[^"\\\n])*)"', m[1]))
    return all(not l.strip() or l.strip().startswith((".", "\\", "#")) or l.strip().endswith(":")
               for l in re.split(r"\\n|;", text))


def scan_file(rel: str, text: str, shared=None, address_header=ADDRESS_HEADER) -> dict:
    """One C file or header, read once. `hits`: [(kind, position)] of every kind that the text alone decides (not
    `unbased`, `filename`, `flag`, `reservation`). `extents`: its function bodies. `funcs`: {name: position} of the
    functions it defines under a name that is no placeholder. `stubs`: its INCLUDE_ASM lines. `shared`: the macros of
    the headers that hide a construct."""
    key = (hashlib.sha1(text.encode("utf-8", "replace")).digest(), in_include(rel), is_c(rel), is_header(rel),
           is_fragment(rel), rel == address_header, tuple(sorted((shared or {}).items())))
    if key in _SCANS:
        return _SCANS[key]
    body = strip(text)
    code = PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)
    plain = _STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)) if m.group(0)[0] == "/" else m.group(0), text)
    macros = dict(shared or {})
    macros.update(_macros(body, macros))
    defines = [m for m in DEFINE.finditer(body) if m.group(1) not in ("M2C_FIELD",) + STUB_MACROS]
    ext = extents(code)
    hits: list[tuple[str, int]] = []
    found = _crutches(text, code)
    for c in found:                                    # a pin, a goto, an empty asm statement: each with its own marker
        hits.append((c["kind"], c["a"]))
        if not reason_ok(c["reason"]):                 # no marker of its own, or a marker with no reason
            hits.append((c["kind"] + "-unmarked", c["a"]))
    # each construct in the code, each one that a macro's own body holds, and each use of such a macro
    hits += [("offset", m.start()) for m in OFFSET.finditer(code)]
    hits += [("offset", d.start()) for d in defines for _ in OFFSET.findall(d.group(2))]
    if rel != address_header:
        hits += [("address", at) for at in _address_at(code)]
        hits += [("address", d.start()) for d in defines for _ in _address_at(d.group(2))]
    hits += [("asm", d.start()) for d in defines if re.search(r"\b%s\b" % ASM_WORD, d.group(2))]
    for kind in MACRO_KINDS:
        rx = _use_rx([k for k, v in macros.items() if v == kind])
        if rx and not (kind == "address" and rel == address_header):
            hits += [(kind, m.start()) for m in rx.finditer(code)]
            hits += [("goto-unmarked", m.start()) for m in rx.finditer(code)] if kind == "goto" else []
    hits += [("cast", m.start()) for m in CASTS.finditer(code)]
    hits += [("field", m.start()) for m in FIELD.finditer(code)]
    hits += [("macro", m.start()) for m in DEFINE.finditer(body) if m.group(1) not in STUB_MACROS
             and re.search(r"[{;]|\\\n", m.group(2))]
    spans = [(c["a"], c["b"]) for c in found if c["kind"] != "goto"]
    starts = [a for _, a, _ in ext]

    def outside(at: int) -> bool:                      # in no function body
        i = bisect.bisect_right(starts, at) - 1
        return not (i >= 0 and at < ext[i][2])

    for m in INLINE_ASM.finditer(code):                # a header's own plumbing at file scope is the stub's, not debt
        if not any(a <= m.start() < b for a, b in spans) and not (is_header(rel) and outside(m.start()) and _plumbing(plain, m.end())):
            hits.append(("asm", m.start()))
    if not is_fragment(rel):
        hits += [("obscured", m.start()) for m in STATEMENT.finditer(code) if outside(m.start())]
    hits += [("obscured", m.start()) for m in SPLICE.finditer(code)]
    if not in_include(rel):
        hits += [("struct", m.start()) for m in STRUCT.finditer(code)]
    funcs: dict[str, int] = {}
    stub_lines = [(m.start(), code.find("\n", m.start())) for m in STUB_USE.finditer(code)]
    uses = [m for m in PLACEHOLDER_USE.finditer(code) if not any(a <= m.start() and (b < 0 or m.start() < b) for a, b in stub_lines)]
    if is_c(rel):
        hits += [("extern", m.start()) for m in EXTERN.finditer(code)]
        named: dict[str, int] = {}
        for m in list(DEF_FUNC.finditer(code)) + list(DEF_DATA.finditer(code)):
            if m.group(1) not in NOT_A_NAME or m.re is DEF_DATA:
                named.setdefault(m.group(1), m.start())
                if m.re is DEF_FUNC and not PLACEHOLDER.match(m.group(1)):
                    funcs.setdefault(m.group(1), m.start())
        hits += [("placeholder", at) for n, at in named.items() if PLACEHOLDER.match(n)]
        for n, at in named.items():                    # the name in its own definition is no use of it
            own = next((u for u in uses if u.group(0) == n and u.start() >= at), None)
            if own is not None:
                uses.remove(own)
    hits += [("placeholder-use", m.start()) for m in uses]
    inner: dict[str, str] = {}                         # a body from its first brace on: a rename leaves it as it was
    for name, a, b in ext:
        at = code.find("{", a, b)
        inner[name] = hashlib.sha1((inner.get(name, "") + " ".join(code[at if at >= 0 else a:b].split())).encode()).hexdigest()[:16]
    includes = []                                      # [(the body that holds the directive, the path it names)]
    for m in INCLUDE.finditer(plain):
        i = bisect.bisect_right(starts, m.start()) - 1
        includes.append((ext[i][0] if i >= 0 and m.start() < ext[i][2] else SCOPE, m.group(1)))
    _SCANS[key] = {"hits": hits, "extents": ext, "funcs": funcs, "stubs": len(STUB_USE.findall(code)),
                   "stub_names": STUB_NAME.findall(code), "inner": inner, "includes": includes,
                   "crutches": found}
    return _SCANS[key]


def file_bodies(rel: str, text: str, shared=None, based=None, address_header=ADDRESS_HEADER) -> dict[str, dict[str, int]]:
    """{function name: {kind: count}} of one C file or header: every function body it holds, also one with no debt,
    and under SCOPE what no body holds (left out when it is empty). Two bodies of one name are one entry. `based`:
    the names with a ledger row, or None before the ledger exists."""
    scan = scan_file(rel, text, shared, address_header)
    hits = list(scan["hits"])
    if based is not None:
        hits += [("unbased", at) for n, at in scan["funcs"].items() if n not in based]
    out: dict[str, dict[str, int]] = {name: {} for name, _, _ in scan["extents"]}
    starts = [a for _, a, _ in scan["extents"]]
    for kind, at in hits:
        i = bisect.bisect_right(starts, at) - 1
        name = scan["extents"][i][0] if i >= 0 and at < scan["extents"][i][2] else SCOPE
        got = out.setdefault(name, {})
        got[kind] = got.get(kind, 0) + 1
    return out


def file_debt(rel: str, text: str, shared=None, based=None, address_header=ADDRESS_HEADER) -> dict[str, int]:
    """The counts of one C file or header, by kind (zero counts left out): the sum of its bodies and its scope."""
    got: dict[str, int] = {}
    for counts in file_bodies(rel, text, shared, based, address_header).values():
        for kind, n in counts.items():
            got[kind] = got.get(kind, 0) + n
    return {k: got[k] for k in KINDS if got.get(k)}


def is_source(path: str) -> bool:
    """A file that the debt count reads: a C or an assembly suffix, in no folder of NOT_SOURCE and in no folder whose
    name starts with a dot."""
    return (path.lower().endswith(C_SUFFIXES + ASM_SUFFIXES) and not path.startswith(NOT_SOURCE)
            and not any(part.startswith(".") for part in path.split("/")))


def is_fragment(path: str) -> bool:
    """A body that other files include inside their own function braces (`shared.inc.c`, `body.inc`): its statements
    stand outside a function by design. `_rises` holds it to the bodies that include it."""
    return ".inc" in path.rsplit("/", 1)[-1].lower()


def is_asm(path: str) -> bool:
    return path.lower().endswith(ASM_SUFFIXES)


def is_c(path: str) -> bool:
    """A translation unit: a file that defines functions and data, not a header and not a fragment."""
    return path.lower().endswith((".c", ".cc", ".cpp", ".cxx"))


def is_header(path: str) -> bool:
    return path.lower().endswith((".h", ".hpp"))


def in_include(path: str) -> bool:
    return path.startswith("include/") or "/include/" in path


def address_header(repo) -> str:
    """`[debt] address_header` of config/psxdecomp.toml, else include/addr.h. The key is read as text, so that a
    Python with no tomllib (before 3.11) counts the same tree as a newer one does. `repo`: a folder or a Tree."""
    table = None
    record = repo.read(RECORD) if isinstance(repo, Tree) else _read(pathlib.Path(repo) / RECORD)
    for line in (record or "").split("\n"):
        head = re.match(r"\s*\[\s*([^\]]+?)\s*\]\s*(?:#.*)?$", line)
        if head:
            table = head[1]
            continue
        m = re.match(r"""\s*["']?address_header["']?\s*=\s*(?:"([^"]*)"|'([^']*)')""", line)
        if m and table == "debt":
            return (m[1] if m[1] is not None else m[2]) or ADDRESS_HEADER
    return ADDRESS_HEADER


class Rows(list):
    """The rows of a ledger. `old`: its header is an earlier one (`also` of read_tsv), and a column it lacks reads
    as empty."""
    old = False


def read_tsv(path, columns, tree: Tree | None = None, also=()) -> tuple[list[dict] | None, list[str]]:
    """(the rows, the errors) of a tab-separated file with a header line. None when the file is absent. With a
    `tree`, `path` is a path of that tree. `also`: the earlier headers that are read as well."""
    text = _read(path) if tree is None else tree.read(str(path))
    if text is None:
        return None, []
    rows, errs, head = Rows(), [], None
    for n, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        if head is None:
            head = cells
            if tuple(head) in [tuple(a) for a in also]:
                rows.old = True
            elif tuple(head) != tuple(columns):
                errs.append("line %d: the header is not %s" % (n, " ".join(columns)))
                return rows, errs
            continue
        cells += [""] * (len(head) - len(cells))       # an editor trims the tabs of empty last cells
        if len(cells) != len(head):
            errs.append("line %d: %d cell(s), not %d" % (n, len(cells), len(head)))
            continue
        rows.append(dict(dict.fromkeys(columns, ""), **dict(zip(head, cells)), _line=n))
    if head is None:
        errs.append("no header line")
    return rows, errs


def flag_counts(repo, tree: Tree) -> dict[tuple[str, str], int]:
    """{(kind, path): count} of the two kinds that a game counts itself, `flag` (a compiler option of one file) and
    `reservation` (a register taken from the compiler, `-ffixed-N`). `[debt] flags` of the record names the game's
    lister: a command that prints `<count> flag|reservation <path>` lines for the work tree. It is run for the work
    tree and the index. A revision cannot be listed without a checkout, so its counts are the rows of its own
    baseline, which the gate held equal to the lister when that revision was committed."""
    cmd = record_table(tree, "debt").get("flags")
    out: dict[tuple[str, str], int] = {}
    if tree.source not in (None, INDEX):
        try:
            rows = parse_baseline(tree.read(BASELINE)).rows
        except Fail:
            rows = {}
        return {k: n for k, n in rows.items() if k[0] in ("flag", "reservation")} if cmd else {}
    if not cmd:
        return out
    r = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail("the lister of `[debt] flags` (`%s`) exited %d: %s" % (cmd, r.returncode, (r.stderr or r.stdout).strip()[-200:]))
    for line in r.stdout.splitlines():
        m = re.fullmatch(r"(\d+) (flag|reservation) (\S.*)", line.strip())
        if m and int(m[1]):
            out[(m[2], m[3])] = out.get((m[2], m[3]), 0) + int(m[1])
    return out


def debt_bodies(repo, skip=(), tree: Tree | None = None) -> dict[str, dict[str, dict[str, int]]]:
    """{path: {function name: {kind: count}}} over the tracked source files (is_source) that no `skip` entry covers:
    every function body of every C file (also one with no debt), and under SCOPE what no body holds. `tree`: the
    source to count (default: the work tree of `repo`). The ledgers and the record are read from the same source."""
    tree = tree or Tree(repo)
    if ("bodies", tuple(skip)) in tree.memo:
        return tree.memo[("bodies", tuple(skip))]
    covered = lambda p: any(entry_match(e, p) for e in skip)  # noqa: E731
    files = [p for p in tree.paths if is_source(p) and not covered(p)]
    header = address_header(tree)
    names, _ = read_tsv(NAMES, NAME_COLUMNS, tree)
    based = None if names is None else {r["new_name"] for r in names if r["decision"] == "accepted"}
    evidence: dict[str, set] = {}                      # {path: the symbols with a row}: a row clears one function, or one file
    for r in read_tsv(ASM_EVIDENCE, ASM_COLUMNS, tree, also=(ASM_COLUMNS_OLD,))[0] or []:
        evidence.setdefault(r["path"], set()).add(r["symbol"])
    texts = {p: tree.read(p) for p in files}
    shared: dict[str, str] = {}
    heads = [strip(texts[p]) for p in files if (is_header(p) or p.lower().endswith(".inc")) and p != header and texts[p] is not None]
    size = -1
    while len(shared) != size:                         # a macro of one header may use a macro of another
        size = len(shared)
        for body in heads:
            shared.update(_macros(body, shared))
    out: dict[str, dict[str, dict[str, int]]] = {}
    for p in files:
        if texts[p] is None:
            continue
        if is_asm(p):
            out[p] = {} if p in evidence else {SCOPE: {"asm": 1}}
        else:
            out[p] = file_bodies(p, texts[p], shared, based, header)
            for name in evidence.get(p, ()):
                if name != SCOPE:
                    out[p].get(name, {}).pop("asm", None)
        if FILENAME.fullmatch(p.rsplit("/", 1)[-1].rsplit(".", 1)[0]):
            out[p].setdefault(SCOPE, {})["filename"] = 1       # a name that says an address or a number, not a subject
    users: dict[str, set] = {}                         # {an included source: the (path, body) pairs that include it}
    for p in files:
        if texts[p] is None or is_asm(p):
            continue
        for name, inc in scan_file(p, texts[p], shared, header)["includes"]:
            folder = p.rsplit("/", 1)[0] + "/" if "/" in p else ""
            target = next((c for c in (os.path.normpath(folder + inc), os.path.normpath(inc), "include/" + inc) if tree.has(c)), None)
            if target is None or not target.lower().endswith(C_SUFFIXES):
                continue
            if not is_source(target) or covered(target):
                got = out[p].setdefault(SCOPE, {})     # code from a folder that the count does not read
                got["obscured"] = got.get("obscured", 0) + 1
            elif not is_header(target) and name != SCOPE:   # inside a function's braces: the file is that body's text
                users.setdefault(target, set()).add((p, name))
    tree.memo[("users", tuple(skip))] = users
    for p in tree.links:                               # a source behind a symbolic link is compiled and never read here
        if is_source(p) and not covered(p):
            out.setdefault(p, {}).setdefault(SCOPE, {})["obscured"] = 1
    for (kind, p), n in flag_counts(repo, tree).items():
        if not covered(p):
            out.setdefault(p, {}).setdefault(SCOPE, {})[kind] = n
    tree.memo[("bodies", tuple(skip))] = out
    return out


def tree_stubs(repo, skip=(), tree: Tree | None = None) -> tuple[dict, dict, dict]:
    """({path: the names of its INCLUDE_ASM lines}, {(path, function): the hash of its body from the first brace on},
    {a fragment: the (path, function) pairs that include it}) over the C files that `debt_bodies` reads: what tells a
    new body from a renamed one, and which bodies a fragment belongs to."""
    tree = tree or Tree(repo)
    if ("stubs", tuple(skip)) not in tree.memo:
        stubs, inner = {}, {}
        for p in debt_bodies(repo, skip, tree):
            if is_source(p) and not is_asm(p) and tree.read(p) is not None:
                scan = scan_file(p, tree.read(p) or "", address_header=address_header(tree))
                stubs[p] = list(scan["stub_names"])
                inner.update({(p, n): h for n, h in scan["inner"].items()})
        tree.memo[("stubs", tuple(skip))] = (stubs, inner, tree.memo.get(("users", tuple(skip)), {}))
    return tree.memo[("stubs", tuple(skip))]


def tree_shape(repo, skip=(), tree: Tree | None = None) -> tuple[int, int]:
    """(the function bodies, the INCLUDE_ASM lines) of the C files that `debt_bodies` reads: what a budget counts."""
    tree = tree or Tree(repo)
    bodies = debt_bodies(repo, skip, tree)
    stubs = 0
    for p in bodies:
        if is_c(p) and tree.read(p) is not None:
            stubs += scan_file(p, tree.read(p) or "", address_header=address_header(tree))["stubs"]
    return sum(len([n for n in by if n != SCOPE]) for by in bodies.values()), stubs


def debt_counts(repo, skip=(), tree: Tree | None = None, bodies=None) -> dict[tuple[str, str], int]:
    """{(kind, path): count}: the sum of each file's bodies and scope (`bodies`: a result of debt_bodies)."""
    out: dict[tuple[str, str], int] = {}
    for p, by in (debt_bodies(repo, skip, tree) if bodies is None else bodies).items():
        for got in by.values():
            for kind, n in got.items():
                out[(kind, p)] = out.get((kind, p), 0) + n
    return out


# ---- the baseline: one row per count, and the policy that judges a change -------------------------------------------
# A policy line gives each kind its mode. `down`: the kind never rises. `admit-new`: debt may arrive with a new
# function body, and a body that exists never gets worse. A body is new when it takes an INCLUDE_ASM line away. `budget <n>`: as admit-new, and the kind's total may grow by
# n for each 100 new bodies since the anchor (`base <count> <bodies> <stubs>`), plus BUDGET_SLACK. A new body is one
# that takes an INCLUDE_ASM line away: an empty function beside its stub buys nothing. A `raise` line is the
# developer's act: it lets one change go over by its number. The change itself cannot weaken any of this: `admission`
# reads the policy of the revision that the change starts from.
MODES = ("admit-new", "budget", "down")              # weakest first
START_DOWN = ("pin-unmarked", "goto-unmarked", "barrier", "barrier-unmarked", "asm", "obscured", "unbased",
              "reservation")                         # the modes that `debt --recount` gives a kind with no line
START_BUDGET = {"pin": 30, "goto": 12}
BUDGET_SLACK = 2
PUBLIC_PATHS = "config/public-paths.txt"


class Baseline:
    """config/debt-baseline.txt as read. `version` 0: no file. 1: the file of psxdecomp 0.6.0 and earlier (one `mode
    admit|down` line, in `old_mode`). 2: a policy line per kind. `other`: the lines of a kind this tool does not
    know (a newer tool wrote them), kept as they are."""

    def __init__(self):
        self.version, self.old_mode = 0, None
        self.rows: dict[tuple[str, str], int] = {}
        self.skip: list[str] = []
        self.modes: dict[str, str] = {}
        self.budgets: dict[str, tuple[int, int, int, int]] = {}      # kind: (n, count, bodies, stubs)
        self.raises: list[tuple[str, int, str, str]] = []            # (kind, n, date, reason)
        self.head: list[str] = []
        self.other: list[str] = []

    def policy(self, kind: str) -> tuple | None:
        """("down",), ("admit-new",) or ("budget", n, count, bodies, stubs); None for a kind with no line."""
        if kind in self.budgets:
            return ("budget",) + self.budgets[kind]
        return (self.modes[kind],) if kind in self.modes else None

    def lacks(self) -> list[str]:
        return [k for k in KINDS if self.policy(k) is None]

    def summary(self) -> str:
        by = {m: [k for k in KINDS if (self.policy(k) or ("",))[0] == m] for m in reversed(MODES)}
        return "; ".join("%s: %s" % (m, ", ".join(
            "%s %d" % (k, self.budgets[k][0]) if m == "budget" else k for k in ks)) for m, ks in by.items() if ks)


def parse_baseline(text: str | None) -> Baseline:
    """The baseline of a text; None is the absent file (version 0). A line that is no row, no policy line, no `skip`
    line and no `#` comment raises Fail with its number, and so do a second row of one pair, a second policy of one
    kind, and a file that mixes the two versions. `--update` writes every comment line above the policy lines."""
    bl, old = Baseline(), 0
    if text is None:
        return bl
    bl.version = 2
    for n, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        l = raw.strip()
        if not l:
            continue
        where = "%s:%d" % (BASELINE, n)
        mode = re.fullmatch(r"mode (\S+) (down|admit-new)", l)
        budget = re.fullmatch(r"budget (\S+) (\d+) base (\d+) (\d+) (\d+)", l)
        rise = re.fullmatch(r"raise (\S+) (\d+) (\d{4}-\d\d-\d\d) (\S.*)", l)
        row = re.fullmatch(r"(\d+) (\S+) (\S.*)", l)
        m = mode or budget or rise or row
        kind = m[2] if m is row and row else m[1] if m else None
        if l.startswith("#"):
            bl.head.append(l)
        elif l in ("mode admit", "mode down"):
            old += 1
            if old > 1:
                raise Fail("%s: a second `mode` line: the file holds one" % where)
            bl.version, bl.old_mode = 1, l[5:]
        elif l.startswith("skip ") and l[5:].strip():
            bl.skip.append(l[5:].strip())
        elif m is None:
            raise Fail("%s: not `<count> <kind> <path>`, `mode <kind> down|admit-new`, `budget <kind> <n> base <count> "
                       "<bodies> <stubs>`, `raise <kind> <n> <date> <reason>`, `skip <entry>` or a `#` comment" % where)
        elif kind not in KINDS:
            bl.other.append(l)
        elif mode or budget:
            if bl.policy(kind) is not None:
                raise Fail("%s: %s has two policy lines" % (where, kind))
            if mode:
                bl.modes[kind] = mode[2]
            else:
                bl.budgets[kind] = tuple(int(x) for x in budget.groups()[1:])
        elif rise:
            bl.raises.append((kind, int(rise[2]), rise[3], rise[4]))
        elif (kind, row[3]) in bl.rows:
            raise Fail("%s: %s %s has two rows" % (where, kind, row[3]))
        else:
            bl.rows[(kind, row[3])] = int(row[1])
    if old and (bl.modes or bl.budgets or bl.raises):
        raise Fail("%s: a `mode %s` line of version 1 beside the policy lines of version 2" % (BASELINE, bl.old_mode))
    return bl


def baseline_text(bl: Baseline, counts: dict | None = None) -> str:
    """The file of a baseline in version 2: the comment lines, a policy line per kind, the lines of kinds this tool
    does not know, the `raise` lines, the `skip` lines, then one row per count above zero (`counts`, else its own)."""
    rows = bl.rows if counts is None else counts
    lines = [l if l.startswith("#") else "# " + l for l in bl.head]
    for kind in KINDS:
        if kind in bl.budgets:
            lines.append("budget %s %d base %d %d %d" % ((kind,) + tuple(bl.budgets[kind])))
        elif kind in bl.modes:
            lines.append("mode %s %s" % (kind, bl.modes[kind]))
    lines += bl.other
    lines += ["raise %s %d %s %s" % r for r in bl.raises]
    lines += ["skip %s" % e for e in bl.skip]
    lines += ["%d %s %s" % (rows[k], k[0], k[1]) for k in sorted(rows, key=lambda k: (k[1], KINDS.index(k[0])))
              if rows[k] > 0]
    return "".join(l + "\n" for l in lines)


def _kind_totals(counts: dict) -> dict[str, int]:
    by = {k: 0 for k in KINDS}
    for (kind, _), n in counts.items():
        by[kind] += n
    return by


def _totals(counts: dict) -> str:
    by = _kind_totals(counts)
    return ", ".join("%s %d" % (k, by[k]) for k in KINDS if by[k]) or "none"


def recount_text(repo, tree: Tree | None = None) -> tuple[str, list[str]]:
    """(the baseline that `debt --recount` writes for a tree, the lines that say what it added): the counts of now,
    the policy lines the file holds, and the starting mode of each kind that has none (every kind `down` after a
    version 1 file in `mode down`). A budget's anchor is the tree of now."""
    tree = tree or Tree(repo)
    bl = parse_baseline(tree.read(BASELINE))
    notes = []
    if bl.version == 0:
        bl.skip = [e for e in FIRST_SKIP if e in tree.paths]
        bl.head = list(BASELINE_HEAD)
    counts = debt_counts(repo, bl.skip, tree)
    totals, shape = _kind_totals(counts), None
    for kind in bl.lacks():
        if bl.old_mode == "down" or kind in START_DOWN:
            bl.modes[kind] = "down"
        elif kind in START_BUDGET:
            shape = shape or tree_shape(repo, bl.skip, tree)
            bl.budgets[kind] = (START_BUDGET[kind], totals[kind]) + shape
        else:
            bl.modes[kind] = "admit-new"
        notes.append("%s: %s" % (kind, " ".join(map(str, bl.policy(kind)))))
    if bl.version == 1:
        bl.head = list(BASELINE_HEAD) + [l for l in bl.head if not l.lstrip("# ").startswith(OLD_HEADS)]
    return baseline_text(bl, counts), notes


def first_baseline(repo) -> str:
    """A game's first baseline: the counts of now, the starting mode of each kind, the stub macro's header skipped
    where one is tracked."""
    return recount_text(repo)[0]


def state_findings(repo, tree: Tree | None = None) -> tuple[list[str], dict]:
    """(the FAIL lines of a tree's own baseline, what was read). The baseline must exist, be of version 2, hold a
    policy line for each kind and hold each count as its row. A row of a file that the tree lacks is not stale where
    config/public-paths.txt exists and lists no such path: the public tree of a game in split mode holds the rows of
    the files it does not publish."""
    tree = tree or Tree(repo)
    bl = parse_baseline(tree.read(BASELINE))
    counts = debt_counts(repo, bl.skip, tree)
    st = {"baseline": bl, "counts": counts, "rise": [], "stale": []}
    if bl.version == 0:
        return ["no %s: `python3 %s debt --recount` writes it" % (BASELINE, VENDORED)], st
    if bl.version == 1:
        return ["%s is a version 1 file (`mode %s`): run `python3 %s debt --recount`, or /psxdecomp:upgrade"
                % (BASELINE, bl.old_mode, VENDORED)], st
    out = ["no policy line for %s in %s: run `python3 %s debt --recount`" % (", ".join(bl.lacks()), BASELINE, VENDORED)
           ] if bl.lacks() else []
    public = tree.read(PUBLIC_PATHS)
    listed = None if public is None else [l.strip() for l in public.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    keys = sorted(set(bl.rows) | set(counts), key=lambda k: (k[1], KINDS.index(k[0])))
    for k in keys:
        have, row = counts.get(k, 0), bl.rows.get(k, 0)
        if have > row:
            st["rise"].append(k)
            out.append("rise %s %s: %d, its row is %d" % (k[0], k[1], have, row))
        elif have < row and not (listed is not None and k[1] not in tree.paths
                                 and not any(entry_match(e, k[1]) for e in listed)):
            st["stale"].append(k)
            out.append("stale %s %s: %d, its row is %d" % (k[0], k[1], have, row))
    return out, st


def policy_findings(old: Baseline, new: Baseline) -> list[str]:
    """What a change may not do to the policy that judged it: weaken a kind's mode, raise a budget or move its anchor,
    add a `skip` line, delete the file. `old`: the baseline of the revision the change starts from."""
    if old.version == 0:
        return []
    if new.version == 0:
        return ["%s is gone" % BASELINE]
    out = ["a new `skip` line (%s)" % e for e in new.skip if e not in old.skip]
    if new.version == 1:
        return out + (["`mode down` became `mode admit`"] if (old.old_mode, new.old_mode) == ("down", "admit") else []) + (
            ["a version 2 file became a version 1 file"] if old.version == 2 else [])
    for kind in KINDS:
        was = ("down",) if old.old_mode == "down" else old.policy(kind)
        now = new.policy(kind)
        if was is None:
            continue
        if now is None:
            out.append("the policy line of %s is gone (it was %s)" % (kind, " ".join(map(str, was))))
        elif MODES.index(now[0]) < MODES.index(was[0]):
            out.append("%s went from %s to %s: a mode only gets stronger" % (kind, was[0], now[0]))
        elif now[0] == was[0] == "budget" and now[1] > was[1]:
            out.append("the budget of %s went from %d to %d" % (kind, was[1], now[1]))
        elif now[0] == was[0] == "budget" and now[2:] != was[2:]:
            out.append("the anchor of the %s budget changed (base %s, was %s)" % (
                kind, " ".join(map(str, now[2:])), " ".join(map(str, was[2:]))))
    return out


def _rises(old: dict, new: dict, was=None, now=None) -> tuple[dict[str, int], list[tuple[str, str]], dict[str, int]]:
    """(the rise of each kind in what is not new, its lines [(kind, text)], {path: its new bodies}) between two
    results of debt_bodies. `was`, `now`: tree_stubs of the two trees. A body that the change adds is, in this order:
    the body of the same name that left another file (moved); the body with the same text from its first brace on
    that left under another name (renamed); a new body, when an INCLUDE_ASM line of its name left; a new body, when
    an INCLUDE_ASM line left its file under another name (a function that is named as it is banked), or when its file
    is new and the tree gained a body (a function carved out of an assembly segment); else it stands in the place of
    a body that left, and it may hold no more than those did. So an empty function in a file that exists buys
    nothing: there a body is new only when it takes a stub away. Where a file loses a stub under another name and loses a body in the
    same change, the added bodies with the most debt count as the new ones."""
    rise: dict[str, int] = {}
    lines: list[tuple[str, str]] = []
    stubs0, inner0, _ = was or ({}, {}, {})
    stubs1, inner1, users = now or ({}, {}, {})
    fresh: set = set()                                 # the (path, name) pairs that are new bodies
    origin: dict[str, set] = {}                        # {path: the files that its bodies came from}

    def compare(before: dict, after: dict, where: str, why: str) -> None:
        for kind in KINDS:
            if after.get(kind, 0) > before.get(kind, 0):
                rise[kind] = rise.get(kind, 0) + after[kind] - before.get(kind, 0)
                lines.append((kind, "%s: %s %s: %d -> %d" % (why, kind, where, before.get(kind, 0), after[kind])))

    def total(sets) -> dict:
        got: dict[str, int] = {}
        for counts in sets:
            for kind, n in counts.items():
                got[kind] = got.get(kind, 0) + n
        return got

    gone = {(p, n): c for p, by in old.items() for n, c in by.items() if n != SCOPE and n not in new.get(p, {})}
    came = sorted((p, n) for p, by in new.items() for n in by if n != SCOPE and n not in old.get(p, {}))
    for p, by in sorted(new.items()):
        for n, c in sorted(by.items()):
            if n != SCOPE and n in old.get(p, {}):
                compare(old[p][n], c, "%s %s" % (p, n), "rose in an existing body")
    left_by: dict[str, list[str]] = {}
    for p, n in sorted(gone):
        left_by.setdefault(n, []).append(p)
    rest = []
    for p, n in came:                                  # the same name, in another file
        if left_by.get(n):
            q = left_by[n].pop(0)
            origin.setdefault(p, set()).add(q)
            compare(gone.pop((q, n)), new[p][n], "%s %s (from %s)" % (p, n, q), "rose in a moved body")
        else:
            rest.append((p, n))
    by_text: dict[str, list] = {}
    for key in sorted(gone):
        if inner0.get(key):
            by_text.setdefault(inner0[key], []).append(key)
    came, rest = rest, []
    for p, n in came:                                  # the same text, under another name
        same = by_text.get(inner1.get((p, n)) or "", [])
        same = [k for k in same if k in gone]
        if same:
            origin.setdefault(p, set()).add(same[0][0])
            compare(gone.pop(same[0]), new[p][n], "%s %s (it was %s %s)" % (p, n, same[0][0], same[0][1]), "rose in a renamed body")
        else:
            rest.append((p, n))
    lost_stubs: dict[str, list[str]] = {}              # {path: the stub names that left it}
    for p in set(stubs0) | set(stubs1):
        left = list(stubs0.get(p, ()))
        for n in stubs1.get(p, ()):
            if n in left:
                left.remove(n)
        lost_stubs[p] = left
    anywhere = [n for names in lost_stubs.values() for n in names]
    new_in: dict[str, int] = {}
    came, rest = rest, []
    for p, n in came:                                  # a new body: the stub of its name left
        if n in anywhere:
            anywhere.remove(n)
            if n in lost_stubs.get(p, ()):
                lost_stubs[p].remove(n)
            else:
                next(names for names in lost_stubs.values() if n in names).remove(n)
            new_in[p] = new_in.get(p, 0) + 1
            fresh.add((p, n))
        else:
            rest.append((p, n))
    surplus = len(rest) - len(gone)                    # the bodies that the tree gained, beyond those it lost
    stand: list = []
    for p in sorted({q for q, _ in rest}):             # a new body under a new name: a stub left its file
        names = sorted((n for q, n in rest if q == p), key=lambda n: (-sum(new[p][n].values()), n))
        lost = [c for (q, _), c in sorted(gone.items()) if q == p]
        slots = max(0, min(len(lost_stubs.get(p, ())), len(names) - len(lost)))
        if p not in old and surplus > 0:               # or the file itself is new: a function carved out of an assembly segment
            more = min(len(names) - slots, surplus)
            slots, surplus = slots + more, surplus - more
        new_in[p] = new_in.get(p, 0) + slots
        fresh |= {(p, n) for n in names[:slots]}
        stand += [(p, n) for n in names[slots:]]
    if stand:                                          # the bodies that are not new stand for the bodies that left the tree
        for p in {q for q, _ in stand}:
            origin.setdefault(p, set()).update(q for q, _ in gone)
        compare(total(gone.values()), total(new[p][n] for p, n in stand), "%s%s (in the place of %s)" % (
            ", ".join("%s %s" % k for k in stand[:3]), " and %d more" % (len(stand) - 3) if len(stand) > 3 else "",
            "%d body(ies) that left" % len(gone) if gone else "no body that left: it takes no INCLUDE_ASM line away, and its file is "
            "not new"), "rose in a body that is not new")
    for p, by in sorted(new.items()):
        holds_bodies = any(n != SCOPE for n in by) or any(n != SCOPE for n in old.get(p, {}))
        before = total([old.get(p, {}).get(SCOPE, {})] + [old[q].get(SCOPE, {}) for q in sorted(origin.get(p, ())) if q != p])
        if users.get(p):                               # a fragment is the body of each function that includes it
            if not all(u in fresh for u in users[p]):
                stay = sorted("%s %s" % u for u in users[p] if u not in fresh)
                compare(before, by.get(SCOPE, {}), "%s (a fragment that %s includes)" % (
                    p, stay[0] + (" and %d more" % (len(stay) - 1) if len(stay) > 1 else "")),
                    "rose in a fragment of a body that is not new")
        elif holds_bodies and not new_in.get(p):       # a file of definitions only (a header, a data file) is free
            compare(before, by.get(SCOPE, {}), "%s (file scope)" % p, "rose outside a function with no new body")
    return rise, lines, new_in


def admission(repo, base: Tree | None, head: Tree) -> tuple[list[tuple[str, str]], list[str]]:
    """([(check, detail)] for what a change may not do, the INFO lines). `base`: the tree the change starts from
    (None: a first commit, with nothing to compare). `head`: the tree it makes. Check `policy`: policy_findings.
    Check `debt`: a rise in a body that exists, moved or was renamed; a rise outside a function in a file that got no
    new body; a rise of a `down` kind; a `budget` kind over its allowance. Both trees are counted by this tool, with
    the `skip` lines that both baselines hold, so a row that the change wrote decides nothing. A `raise` line that
    the change adds lets its kind go over by its number."""
    new = parse_baseline(head.read(BASELINE))
    if base is None:
        return [], []
    old = parse_baseline(base.read(BASELINE))
    fails = [("policy", f) for f in policy_findings(old, new)]
    skip = tuple(e for e in new.skip if e in old.skip) if old.version else tuple(new.skip)
    was, now = debt_bodies(repo, skip, base), debt_bodies(repo, skip, head)
    rise, lines, new_in = _rises(was, now, tree_stubs(repo, skip, base), tree_stubs(repo, skip, head))
    tot0, tot1 = _kind_totals(debt_counts(repo, bodies=was)), _kind_totals(debt_counts(repo, bodies=now))
    seen = list(old.raises)
    slack: dict[str, int] = {}
    for r in new.raises:
        if r in seen:
            seen.remove(r)
        else:
            slack[r[0]] = slack.get(r[0], 0) + r[1]
    infos = []
    for kind in KINDS:
        policy = ("down",) if old.old_mode == "down" else (old.policy(kind) or new.policy(kind) or ("admit-new",))
        over, mine = rise.get(kind, 0), [text for k, text in lines if k == kind]
        grew = tot1[kind] - tot0[kind]
        if policy[0] == "down" and grew > over:
            mine.append("rose in total: %s is `down`: %d -> %d" % (kind, tot0[kind], tot1[kind]))
            over = grew
        elif policy[0] == "budget" and grew > 0:
            bodies, stubs = tree_shape(repo, skip, head)
            fresh = max(0, min(bodies - policy[3], policy[4] - stubs))
            room = policy[2] + -(-policy[1] * fresh // 100) + BUDGET_SLACK
            if tot1[kind] > room and min(grew, tot1[kind] - room) > over:
                over = min(grew, tot1[kind] - room)
                mine.append("over its budget: %s is %d, the budget allows %d (%d for each 100 new bodies, %d new since "
                            "the anchor of %d, plus %d)" % (kind, tot1[kind], room, policy[1], fresh, policy[2], BUDGET_SLACK))
        if over > slack.get(kind, 0):
            fails += [("debt", text) for text in mine]
            if slack.get(kind):
                fails.append(("debt", "the `raise` line(s) of %s allow %d, the change needs %d" % (kind, slack[kind], over)))
        elif over:
            infos.append("%s is over by %d: the change's `raise` line(s) allow %d" % (kind, over, slack[kind]))
    infos += ["a new `raise` line: %s %d %s %s" % r for r in new.raises if r not in old.raises]
    return fails, infos


def debt_status(repo, source: str | None = None) -> dict:
    """What the doctor reads: the baseline, the counts of now, the rises and the stale rows, the FAIL lines. `source`:
    the index or a revision in the work tree's place (the baseline is read from the same source)."""
    fails, st = state_findings(repo, Tree(repo, source))
    return dict(st, fails=fails)


def cmd_bodies(repo, source: str | None = None) -> int:
    """`debt --bodies`: the counts of each function body and of each file's scope, one line per bucket with debt."""
    try:
        tree = Tree(repo, source)
        bodies = debt_bodies(repo, parse_baseline(tree.read(BASELINE)).skip, tree)
    except Fail as e:
        print("DEBT FAIL %s" % e)
        return 1
    n = with_debt = at_scope = 0
    for p in sorted(bodies):
        for name in sorted(bodies[p]):
            got = bodies[p][name]
            n += name != SCOPE
            if got:
                with_debt += name != SCOPE
                at_scope += sum(got.values()) if name == SCOPE else 0
                print("DEBT BODY %s %s: %s" % (p, name or "(file scope)", ", ".join(
                    "%s %d" % (k, got[k]) for k in KINDS if got.get(k))))
    print("DEBT BODIES %d file(s), %d function bodies, %d with debt, %d count(s) at file scope; totals: %s" % (
        len(bodies), n, with_debt, at_scope, _totals(debt_counts(repo, bodies=bodies))))
    return 0


def public_view(tree: Tree) -> Tree:
    """The tree as its public repository holds it: where config/public-paths.txt exists, the files it lists. A count
    that a published text shows is taken from this view, so the public repository's own check finds the same one."""
    listed = tree.read(PUBLIC_PATHS)
    if listed is None:
        return tree
    entries = [l.strip() for l in listed.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    return tree.only(lambda p: any(entry_match(e, p) for e in entries))


def file_states(repo, tree: Tree | None = None) -> list[tuple[str, str, dict]]:
    """[(state, path, its counts)] for each C file that holds a function body or an INCLUDE_ASM line. `stubs`: a
    function of the file is still assembly. `matched`: every function is in C, and the file holds debt, or the names
    ledger does not exist yet. `finished`: every function is in C and the file holds no debt of any kind, so each of
    its names has an accepted row and no crutch is left. Nobody writes that word by hand: this is where it comes
    from."""
    tree = tree or Tree(repo)
    skip = parse_baseline(tree.read(BASELINE)).skip
    bodies = debt_bodies(repo, skip, tree)
    stubs = tree_stubs(repo, skip, tree)[0]
    ledger = tree.read(NAMES) is not None
    out = []
    for p in sorted(bodies):
        if not is_c(p) or is_fragment(p) or not (stubs.get(p) or any(n != SCOPE for n in bodies[p])):
            continue
        counts = debt_counts(repo, bodies={p: bodies[p]})
        got = {k[0]: n for k, n in counts.items()}
        out.append(("stubs" if stubs.get(p) else "matched" if got or not ledger else "finished", p, got))
    return out


def cmd_files(repo, source: str | None = None, public: bool = False) -> int:
    """`debt --files`: the state of each C file, and the one line that a README's generated block reads. `public`:
    of the files that the repository publishes only."""
    try:
        tree = Tree(repo, source)
        tree = public_view(tree) if public else tree
        states = file_states(repo, tree)
    except Fail as e:
        print("DEBT FAIL %s" % e)
        return 1
    for state, p, got in states:
        print("DEBT FILE %-8s %s%s" % (state, p, ": " + ", ".join("%s %d" % (k, got[k]) for k in KINDS if got.get(k)) if got else ""))
    by = {st: sum(1 for x in states if x[0] == st) for st in ("finished", "matched", "stubs")}
    print("DEBT FILES %d C file(s): %d finished, %d matched, %d with stubs%s" % (
        len(states), by["finished"], by["matched"], by["stubs"],
        "" if tree.read(NAMES) is not None else " (no %s yet: no file is finished before each name has a row)" % NAMES))
    return 0


def _head(repo) -> Tree | None:
    """The tree of HEAD; None in a repository with no commit."""
    return Tree(repo, "HEAD") if _git(repo, "rev-parse", "-q", "--verify", "HEAD^{commit}").returncode == 0 else None


def _write_baseline(repo, text: str) -> None:
    (pathlib.Path(repo) / BASELINE).parent.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(repo) / BASELINE).write_text(text, encoding="utf-8")


def cmd_debt(repo, update=False, down=None, source: str | None = None, against: str | None = None, recount=False,
             raise_=None, reason=None) -> int:
    repo = pathlib.Path(repo)
    writes = sum(map(bool, (update, down, recount, raise_)))
    if writes > 1 or (writes and (source is not None or against)):
        print("DEBT FAIL one of --update, --recount, --down and --raise at a time; each writes the baseline of the work "
              "tree, so it takes no --staged, no --rev and no --against")
        return 1
    try:
        tree = Tree(repo, source)
        fails, st = state_findings(repo, tree)
        bl, counts = st["baseline"], st["counts"]
        print("DEBT INFO totals: %s (%d file(s) with debt%s)" % (_totals(counts), len({k[1] for k in counts}),
                                                                  "" if source is None else "; counted in " + source_name(source)))
        if bl.skip:
            print("DEBT INFO skip: %s (the checker does not read these files)" % ", ".join(bl.skip))
        if bl.other:
            print("DEBT INFO %d line(s) of a kind this tool does not know: kept, not checked" % len(bl.other))
        if raise_:
            return _cmd_raise(repo, bl, raise_, reason)
        if recount or update or down:
            head = _head(repo)
            judged, infos = admission(repo, head, tree) if head is not None else ([], [])
            if recount:                                # the source is what HEAD holds: only the tool or the file is new
                judged = [f for f in judged if f[0] == "debt"]
            for check, text in judged:
                print("DEBT FAIL %s: %s" % (check, text))
            for text in infos:
                print("DEBT INFO %s" % text)
            flag = "--recount" if recount else "--update" if update else "--down"
            if judged:
                print("DEBT %s refused: %d finding(s) against HEAD, %s is unchanged%s" % (
                    flag[2:].upper(), len(judged), BASELINE,
                    " (a recount admits nothing: commit or undo the change of the source first)" if recount else ""))
                return 1
            if recount:
                text, notes = recount_text(repo, tree)
                for note in notes:
                    print("DEBT INFO policy written: %s" % note)
                _write_baseline(repo, text)
                print("DEBT RECOUNT written %s (%d row(s))" % (BASELINE, len(parse_baseline(text).rows)))
                return 0
            if bl.version != 2 or bl.lacks():
                print("DEBT FAIL %s" % fails[0])
                return 1
            if down:
                kinds = list(KINDS) if down == "all" else [down]
                if kinds[0] not in KINDS:
                    print("DEBT FAIL %s is no kind (%s)" % (down, ", ".join(KINDS)))
                    return 1
                if st["rise"] or st["stale"]:
                    print("DEBT FAIL the baseline is not equal to the tree: run `debt --update` first")
                    return 1
                for kind in kinds:
                    bl.budgets.pop(kind, None)
                    bl.modes[kind] = "down"
                _write_baseline(repo, baseline_text(bl))
                print("DEBT DOWN %s: %s may only fall from now on" % (BASELINE, ", ".join(kinds)))
                return 0
            for k in st["rise"]:
                print("DEBT INFO admitted with a new body: %s %s: %d -> %d" % (k[0], k[1], bl.rows.get(k, 0), counts[k]))
            for k in st["stale"]:
                print("DEBT INFO %s %s: %d -> %d" % (k[0], k[1], bl.rows[k], counts.get(k, 0)))
            _write_baseline(repo, baseline_text(bl, counts))
            print("DEBT UPDATE written %s (%d row(s), %d fell, %d rose)" % (BASELINE, len(counts), len(st["stale"]),
                                                                           len(st["rise"])))
            return 0
        judged, infos = admission(repo, Tree(repo, against), tree) if against else ([], [])
    except Fail as e:
        print("DEBT FAIL %s" % e)
        return 1
    for text in fails:
        print("DEBT FAIL %s" % text)
    for check, text in judged:
        print("DEBT FAIL %s: %s" % (check, text))
    for text in infos:
        print("DEBT INFO %s" % text)
    if st["rise"] or st["stale"]:
        print("DEBT INFO to record the counts of now: `python3 %s debt --update`, then commit %s" % (VENDORED, BASELINE))
    bad = len(fails) + len(judged)
    print("DEBT CHECK %s (%d rise(s), %d stale row(s)%s%s)" % (
        "FAIL" if bad else "OK", len(st["rise"]), len(st["stale"]),
        "; %d finding(s) against %s" % (len(judged), against) if against else "",
        "; %s" % bl.summary() if bl.version == 2 and not bl.lacks() else ""))
    return 1 if bad else 0


def _cmd_raise(repo, bl: Baseline, raise_, reason) -> int:
    """`debt --raise KIND N --reason TEXT`: one dated `raise` line. The developer's act: an agent session is refused,
    and the pre-push hook asks the developer about each new line."""
    kind, n = raise_
    if os.environ.get("CLAUDECODE"):
        print("DEBT FAIL a raise is the developer's act, not an agent session's (CLAUDECODE is set)")
        return 1
    if bl.version != 2 or kind not in KINDS + ("protected",) or not n.isdigit() or int(n) < 1 or not (reason or "").strip():
        print("DEBT FAIL --raise KIND N --reason TEXT: a kind of %s, or `protected` (N changes of the files that carry "
              "the floor), a number above zero, a reason, and a version 2 %s" % ("|".join(KINDS), BASELINE))
        return 1
    import time
    line = (kind, int(n), time.strftime("%Y-%m-%d"), " ".join(reason.split()))
    if kind == "protected":
        bl.other.append("raise %s %d %s %s" % line)
    else:
        bl.raises.append(line)
    _write_baseline(repo, baseline_text(bl))
    print("DEBT RAISE written: raise %s %d %s %s" % line)
    print("DEBT INFO commit it with the change it admits; the pre-push hook asks you about each new `raise` line")
    return 0


# ---- the two ledgers: names with their evidence, assembly with its reason ------------------------------------------
# A row is a claim, so it must point at something that a reader can open: its evidence names a file and a line that
# the tree holds, an accepted name is one that the source defines as the row's kind, and a `refs` row cites an entry
# of config/refs.toml. An assembly row names one function of a C file, or one assembly file. The rows that a change
# adds are the ones that are opened (`base`): a row that an earlier commit brought was checked there.
NAME_COLUMNS = ("kind", "image", "scope", "old_name", "new_name", "decision", "evidence", "reason")
NAME_KINDS = ("function", "data", "type", "field", "macro", "file")
DECISIONS = ("accepted", "provisional", "rejected")
EVIDENCE = ("psyq-sig", "string", "xref", "loadmap", "exe-header", "prior-art", "debug-symbol", "refs")
EVIDENCE_RE = re.compile(r"^(%s):([^:\s]+):(\d+)$" % "|".join(EVIDENCE))
ASM_COLUMNS = ("image", "symbol", "path", "class", "evidence", "date", "verified_by")
ASM_COLUMNS_OLD = ASM_COLUMNS[:6]                    # the header of psxdecomp 0.6.0 and earlier: read, and said
ASM_CLASSES = ("sdk-object", "hand-asm", "data-in-text")
ASM_EVIDENCE_RE = re.compile(r"^([^:\s]+):(\d+)$")
REFS = "config/refs.toml"
DECL_DATA = re.compile(r"^(?:(?:extern|static|const|volatile)\s+)*(?:[A-Za-z_]\w*[\s*]+)+?([A-Za-z_]\w*)\s*"
                       r"(?:\[[^\]\n]*\]\s*)*(?:=|;)", re.M)
DECL_TYPE = re.compile(r"\b(?:struct|union|enum)\s+([A-Za-z_]\w*)\s*\{|\}\s*([A-Za-z_]\w*)\s*;"
                       r"|^typedef\b[^;{}]*?\b([A-Za-z_]\w*)\s*(?:\[[^\]\n]*\]\s*)*;", re.M)
DECL_FIELD = re.compile(r"^[ \t]+(?:[A-Za-z_]\w*[\s*]+)+?([A-Za-z_]\w*)\s*(?:\[[^\]\n]*\]\s*)*(?::\s*\d+\s*)?;", re.M)
LABEL = re.compile(r"^\s*(?:glabel|jlabel|dlabel|\.globl|\.global)\s+([A-Za-z_.$][\w.$]*)|^([A-Za-z_.$][\w.$]*):", re.M)
_SYMBOLS: dict[bytes, dict[str, set]] = {}


def file_symbols(text: str) -> dict[str, set]:
    """{kind: the names a C file or header defines as that kind}: functions (a body or an INCLUDE_ASM stub), data at
    file scope, types, members and macros."""
    key = hashlib.sha1(text.encode("utf-8", "replace")).digest()
    if key not in _SYMBOLS:
        body = strip(text)
        code = PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)
        funcs = {m.group(1) for m in DEF_FUNC.finditer(code)} - NOT_A_NAME | set(STUB_NAME.findall(code))
        _SYMBOLS[key] = {"function": funcs, "data": set(DECL_DATA.findall(code)) - funcs,
                         "type": {n for m in DECL_TYPE.finditer(code) for n in m.groups() if n},
                         "field": set(DECL_FIELD.findall(code)), "macro": {m.group(1) for m in DEFINE.finditer(body)}}
    return _SYMBOLS[key]


def tree_symbols(tree: Tree) -> dict[str, set]:
    """file_symbols over every C file and header that the debt count reads."""
    if "symbols" not in tree.memo:
        out: dict[str, set] = {k: set() for k in NAME_KINDS}
        for p in tree.paths:
            if is_source(p) and not is_asm(p):
                for kind, names in file_symbols(tree.read(p) or "").items():
                    out[kind] |= names
        tree.memo["symbols"] = out
    return tree.memo["symbols"]


def ref_rows(text: str | None) -> list[tuple[str, int, int]]:
    """[(name, first line, last line)] of the `[[ref]]` tables of a config/refs.toml, read as text."""
    out, start, name = [], None, ""
    lines = (text or "").split("\n")
    for n, line in enumerate(lines + ["[end]"], 1):
        if re.match(r"\s*\[", line):
            if start is not None:
                out.append((name, start, n - 1))
            start, name = (n, "") if re.match(r"\s*\[\[\s*ref\s*\]\]", line) else (None, "")
        elif start is not None:
            m = re.match(r"""\s*name\s*=\s*["']([^"']+)["']""", line)
            name = m[1] if m else name
    return out


def evidence_problem(tree: Tree, path: str, line: int, refs_class: bool = False) -> str | None:
    """Why `<path>:<line>` is no evidence in this tree, or None. The path is a file of the tree and the line is one
    of its lines. A path under a folder of which the tree holds nothing (an ignored folder: asm/, extracted/, refs/)
    is opened only in the work tree, and only where that folder is there. A `refs` row cites a line of a `[[ref]]`
    table of config/refs.toml, or a file under refs/<the name of such a table>/."""
    rows = ref_rows(tree.read(REFS)) if refs_class or path.startswith("refs/") else []
    if refs_class and path == REFS:
        return None if any(a <= line <= b for _, a, b in rows) else "line %d of %s is in no `[[ref]]` table" % (line, REFS)
    if path.startswith("refs/"):
        name = path.split("/")[1] if path.count("/") else ""
        if name not in [r[0] for r in rows]:
            return "%s: %s holds no `[[ref]]` table named %r" % (path, REFS, name)
    elif refs_class:
        return "a `refs` row cites %s:<line of the `[[ref]]` table> or refs/<name>/<file>:<line>, not %s" % (REFS, path)
    if "tops" not in tree.memo:
        tree.memo["tops"] = {p.split("/")[0] for p in tree.paths}
    text = tree.read(path) if path in tree.paths else None
    if text is None and path.split("/")[0] not in tree.memo["tops"] and "/" in path:
        f = tree.repo / path
        if tree.source is not None or not (tree.repo / path.split("/")[0]).is_dir():
            return None                                # not this tree's to open
        text = _read(f) if f.is_file() else None
    if text is None:
        return "%s is no file of this tree" % path
    return None if 1 <= line <= text.count("\n") + 1 else "%s has no line %d" % (path, line)


def names_findings(repo, tree: Tree | None = None, base: Tree | None = None) -> list[tuple[str, str]]:
    """[(FAIL|INFO, detail)] for the two ledgers of a tree (default: the work tree). A FAIL is a malformed file or
    row, or a row that points at nothing: its evidence is no file and line of the tree, its accepted name is nothing
    that the source defines as the row's kind, its assembly row names no function of its C file. `base`: the tree a
    change starts from. The rows it holds already are not opened again, only their form is read."""
    tree, out = tree or Tree(repo), []
    seen = {NAMES: set(), ASM_EVIDENCE: set()}
    for rel in seen if base is not None else ():
        seen[rel] = set((base.read(rel) or "").split("\n"))
    raw = {rel: (tree.read(rel) or "").lstrip("﻿").splitlines() for rel in seen}
    fresh = lambda rel, r: raw[rel][r["_line"] - 1] not in seen[rel]  # noqa: E731
    rows, errs = read_tsv(NAMES, NAME_COLUMNS, tree)
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % NAMES))
    else:
        symbols = None
        for r in rows:
            bad = []
            if r["kind"] not in NAME_KINDS:
                bad.append("kind %r is not one of %s" % (r["kind"], "|".join(NAME_KINDS)))
            if r["decision"] not in DECISIONS:
                bad.append("decision %r is not one of %s" % (r["decision"], "|".join(DECISIONS)))
            ev = EVIDENCE_RE.match(r["evidence"])
            if not ev:
                bad.append("evidence %r is not `<class>:<path>:<line>` with a class of %s" % (r["evidence"], "|".join(EVIDENCE)))
            if not r["new_name"]:
                bad.append("no new_name")
            if not bad and r["decision"] != "rejected" and fresh(NAMES, r):
                why = evidence_problem(tree, ev[2], int(ev[3]), ev[1] == "refs")
                if why:
                    bad.append("the evidence of %s points at nothing: %s" % (r["new_name"], why))
                if r["decision"] == "accepted":
                    symbols = symbols or tree_symbols(tree)
                    name, kind = r["new_name"], r["kind"]
                    held = name in tree.paths or any(p.endswith("/" + name) for p in tree.paths) if kind == "file" else name in symbols[kind]
                    if not held:
                        other = [k for k in NAME_KINDS[:5] if name in symbols[k]]
                        bad.append("%s is %s" % (name, "a %s in the source, not a %s" % (other[0], kind) if other else
                                                 "accepted as a %s, and the source defines no such %s" % (kind, kind)))
            errs += ["line %d: %s" % (r["_line"], b) for b in bad]
        live: dict[tuple, int] = {}
        for r in rows:
            if r["decision"] != "rejected":
                key = (r["new_name"], r["image"], r["scope"], r["kind"])
                live[key] = live.get(key, 0) + 1
        twice = sorted({k[0] for k, n in live.items() if n > 1})
        errs += ["%s has two rows that are not rejected" % n for n in twice]
        out += [("FAIL", "%s: %s" % (NAMES, e)) for e in errs]
        by = {d: sum(r["decision"] == d for r in rows) for d in DECISIONS}
        out.append(("INFO", "%s: %d row(s): %s" % (NAMES, len(rows), ", ".join("%d %s" % (by[d], d) for d in DECISIONS))))
    rows, errs = read_tsv(ASM_EVIDENCE, ASM_COLUMNS, tree, also=(ASM_COLUMNS_OLD,))
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % ASM_EVIDENCE))
    else:
        for r in rows:
            where = "line %d: " % r["_line"]
            if r["class"] not in ASM_CLASSES:
                errs.append(where + "class %r is not one of %s" % (r["class"], "|".join(ASM_CLASSES)))
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", r["date"]):
                errs.append(where + "date %r is not YYYY-MM-DD" % r["date"])
            if not r["path"] or not r["evidence"]:
                errs.append(where + "no path or no evidence")
                continue
            if not fresh(ASM_EVIDENCE, r):
                continue
            ev = ASM_EVIDENCE_RE.match(r["evidence"])
            why = evidence_problem(tree, ev[1], int(ev[2])) if ev else "%r is not `<path>:<line>`" % r["evidence"]
            if why:
                errs.append(where + "the evidence of %s points at nothing: %s" % (r["path"], why))
            text = tree.read(r["path"])
            if text is None:
                errs.append(where + "%s is no file of this tree" % r["path"])
            elif r["path"].endswith((".s", ".S")):
                if r["symbol"] and r["symbol"] not in {a or b for a, b in LABEL.findall(text)}:
                    errs.append(where + "%s holds no label %s" % (r["path"], r["symbol"]))
            elif r["symbol"] not in file_symbols(text)["function"]:
                errs.append(where + "%s defines no function %r: a row of a C file names one function, never the whole "
                            "file" % (r["path"], r["symbol"]))
            if not rows.old and not r["verified_by"]:
                errs.append(where + "no verified_by: who read the evidence of %s" % (r["symbol"] or r["path"]))
        out += [("FAIL", "%s: %s" % (ASM_EVIDENCE, e)) for e in errs]
        out.append(("INFO", "%s: %d row(s)%s" % (ASM_EVIDENCE, len(rows), (
            "; its header is the one of psxdecomp 0.6.0, with no `verified_by` column (/psxdecomp:upgrade adds it)"
            if rows.old else ""))))
    return out


def cmd_names(repo, init=False, source: str | None = None, against: str | None = None) -> int:
    repo = pathlib.Path(repo)
    for rel, cols in ((NAMES, NAME_COLUMNS), (ASM_EVIDENCE, ASM_COLUMNS)) if init else ():
        if not (repo / rel).exists():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("\t".join(cols) + "\n", encoding="utf-8")
            print("NAMES INIT written %s" % rel)
            if rel == NAMES:
                print("NAMES INFO with %s in place, each named function with no accepted row is `unbased` debt, and "
                      "`unbased` never rises: add the accepted rows of the names the source holds, then run "
                      "`python3 %s debt --update`" % (NAMES, VENDORED))
    try:
        tree = Tree(repo, source)
        found = names_findings(repo, tree, Tree(repo, against) if against else None)
    except Fail as e:
        print("NAMES FAIL %s" % e)
        return 1
    for level, detail in found:
        print("NAMES %-4s %s" % (level, detail))
    if not any(f[0] == "FAIL" for f in found) and tree.read(NAMES) is not None:
        try:
            skip = parse_baseline(tree.read(BASELINE)).skip
        except Fail as e:
            print("NAMES INFO %s (the `skip` lines are not read)" % e)
            skip = []
        unbased = sum(n for (kind, _), n in debt_counts(repo, skip, tree).items() if kind == "unbased")
        print("NAMES INFO %d function(s) defined in src/ with no accepted row" % unbased)
    bad = sum(f[0] == "FAIL" for f in found)
    print("NAMES %s (%d finding(s)%s)" % ("FAIL" if bad else "OK", bad, "; only the rows that are new since %s were "
                                         "opened" % against if against else ""))
    return 1 if bad else 0


# ---- the toolchain's pins: read, never fetched, no command of the game run ------------------------------------------
TOOL_COLUMNS = ("name", "kind", "pin", "path")


def toolchain_rows(repo) -> list[tuple[str, str, str]] | None:
    """[(OK|FAIL|MISSING, name, detail)] per row of config/toolchain.tsv; None when the file is absent. `git`: the
    path is a checkout of its own, its HEAD starts with the pin (a commit hash of 7 digits or more, never a tag) and no
    tracked file is changed. `sha256`: the file's hash is the pin."""
    repo = pathlib.Path(repo)
    rows, errs = read_tsv(repo / TOOLCHAIN, TOOL_COLUMNS)
    if rows is None:
        return None
    out = [("FAIL", TOOLCHAIN, e) for e in errs]
    for r in rows:
        path = pathlib.Path(os.path.expanduser(r["path"]))
        path = path if path.is_absolute() else repo / path
        if r["kind"] == "git":
            top = _git(path, "rev-parse", "--show-toplevel") if path.is_dir() else None
            own = top is not None and top.returncode == 0 and pathlib.Path(top.stdout.strip()).resolve() == path.resolve()
            head = _git(path, "rev-parse", "HEAD") if own else None
            pin = r["pin"].lower()
            if head is None or head.returncode != 0:       # a folder of the game is not the tool's checkout
                out.append(("MISSING", r["name"], "%s is not a git checkout on this machine" % r["path"]))
            elif not re.fullmatch(r"[0-9a-f]{7,40}", pin):
                out.append(("FAIL", r["name"], "the pin %s is not a commit hash of 7 to 40 hex digits (a tag can move)" % r["pin"][:20]))
            elif not head.stdout.strip().startswith(pin):
                out.append(("FAIL", r["name"], "%s is at %s, the pin is %s" % (r["path"], head.stdout.strip()[:12], r["pin"][:12])))
            elif _git(path, "status", "--porcelain", "--untracked-files=no").stdout.strip():
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
        if len(cells) not in (3, 4) or cells[0] not in ("deny", "allow") or cells[1] not in ("bash", "path") or not cells[2]:
            errs.append("line %d: not `deny|allow <tab> bash|path <tab> pattern <tab> say`" % n)
        elif cells[1] == "bash":
            try:
                if re.search(cells[2], ""):
                    errs.append("line %d: the pattern matches the empty command, so it matches every command" % n)
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


GUARD_SECONDS = 5


class _Slow(BaseException):
    """The guard ran out of time (a pattern that backtracks): the call runs."""


def guard_roots(event: dict) -> list[pathlib.Path]:
    """The checkouts whose rules can speak for the event, nearest first: the one that holds the file an Edit or a
    Write names, the one the call runs in, the one the session started in. A linked worktree is a checkout of its
    own, so the rules that count are those of the tree that the call changes."""
    tool, inp, cwd = event.get("tool_name"), event.get("tool_input") or {}, event.get("cwd") or "."
    starts = []
    if tool in PATH_TOOLS and inp.get(PATH_TOOLS[tool]):
        at = pathlib.Path(cwd, inp[PATH_TOOLS[tool]]).resolve().parent
        while not at.is_dir() and at != at.parent:     # a file in a folder that does not exist yet
            at = at.parent
        starts.append(at)
    starts += [cwd, os.environ.get("CLAUDE_PROJECT_DIR")]
    roots = []
    for s in starts:
        r = _git(s, "rev-parse", "--show-toplevel") if s else None
        root = pathlib.Path(r.stdout.strip()) if r is not None and r.returncode == 0 and r.stdout.strip() else None
        if root is not None and root not in roots:
            roots.append(root)
    return roots or [pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)]


def guard_hook(stdin=None) -> int:
    """`guard --hook`: print the hook's JSON answer when a rule denies the call. It never fails: bad JSON, no
    repository, no rules file, a pattern that runs for GUARD_SECONDS or any other failure prints nothing, and the
    exit code is always 0 (the call runs)."""
    def slow(*_):
        raise _Slow()

    alarm = hasattr(signal, "SIGALRM")
    try:
        if alarm:
            signal.signal(signal.SIGALRM, slow)
            signal.alarm(GUARD_SECONDS)
        event = json.loads((stdin or sys.stdin).read())
        for root in guard_roots(event):
            text = _read(root / GUARD)
            if text is None:                           # a checkout with no rules file: the next one speaks
                continue
            say = guard_decision(event, parse_guard(text), root)
            if say:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": "psxd guard (%s): %s" % (GUARD, say)}}))
            break
    except (Exception, _Slow):                         # a hook that fails must not stop the session
        pass
    finally:
        if alarm:
            signal.alarm(0)
    return 0


# ---- trials: a crutch stays only when the match needs it, and a record says so ---------------------------------------
# A crutch is a register pin or an empty asm statement (a barrier): a construct that forces the compiler and says
# nothing about the game. `trial` takes each one out in turn and asks the game's probe (`[trial] probe` of the
# record) whether the function still matches. What the match does not need is gone. What it needs gets a
# `// !FAKE: <reason>` line and a row in config/trials.tsv: path, function, crutch, the hash of the function's body,
# `kept`, the digest of the probe. The gate asks for that row behind every marked crutch, with the hash of the body
# as it stands, so an edited body needs a new trial. `trial --recheck` runs rows again: a row that says `kept` for a
# crutch the function matches without is a forged row.
TRIALS = "config/trials.tsv"
TRIAL_COLUMNS = ("path", "function", "crutch", "hash", "result", "probe")
TRIAL_ENV = ("PSXD_TRIAL_FILE", "PSXD_TRIAL_FUNC", "PSXD_TRIAL_PATH")
PROBE_SECONDS = 600
MARK = re.compile(r"!FAKE:[ \t]*([^\n]*?)[ \t]*(?:\*/|$)", re.M)
BARRIER = re.compile(r"\b(?:asm|__asm__|__asm)\b\s*(?:(?:volatile|__volatile__)\b\s*)?\(\s*\"(\s*)\"\s*\)\s*;")
PIN_PARTS = re.compile(r"\bregister\s+(?P<decl>[^;{}=]*?\b(?P<var>[A-Za-z_]\w*))\s*\b(?:asm|__asm__|__asm)\s*\(\s*\"(?P<reg>[^\"\n]*)\"\s*\)")
_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def reason_ok(reason: str | None) -> bool:
    """A marker's reason is a text: three letters or digits at least. A bare `// !FAKE:` is no reason."""
    return reason is not None and len(re.findall(r"\w", reason)) >= 3


def markers(text: str) -> dict[int, tuple[str, bool]]:
    """{line (from 0): (the reason, the comment stands alone on its line)} for each comment that holds `!FAKE:`. A
    marker inside a string is no marker."""
    out = {}
    for m in _STRIP.finditer(text):
        s = m.group(0)
        mark = MARK.search(s) if s[0] == "/" else None
        if mark:
            line = text.count("\n", 0, m.start())
            start = text.rfind("\n", 0, m.start()) + 1
            out[line] = (mark[1].strip(), not text[start:m.start()].strip())
    return out


def body_hash(text: str, spans) -> str:
    """16 hex digits for the text of a function's bodies with no comment and no run of space: what a trial held."""
    plain = " ".join(" ".join(_STRIP.sub(lambda m: "" if m.group(0)[0] == "/" else m.group(0), text[a:b]).split()) for a, b in spans)
    return hashlib.sha256(plain.encode("utf-8", "replace")).hexdigest()[:16]


def _crutches(text: str, code: str) -> list[dict]:
    """The crutches of a text, in order, each with its marker: `crutches` without the function, the id and the hash.
    A marker covers one crutch: the one on its line, or the one on the line below when the marker stands alone."""
    plain = _STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)) if m.group(0)[0] == "/" else m.group(0), text)
    found = []
    for m in PIN.finditer(code):
        parts = PIN_PARTS.match(plain, m.start())
        found.append({"kind": "pin", "a": m.start(), "b": parts.end() if parts else m.end(), "keep": parts["decl"] if parts else None,
                      "name": "pin:%s:%s" % (parts["reg"], parts["var"]) if parts else "pin:?:?"})
    for m in BARRIER.finditer(code):
        if not plain[m.start(1):m.end(1)].strip():     # the string is empty in the text too, not only once it is blanked
            found.append({"kind": "barrier", "a": m.start(), "b": m.end(), "keep": "", "name": "barrier"})
    found += [{"kind": "goto", "a": m.start(), "b": m.end(), "keep": None, "name": "goto"} for m in GOTO.finditer(code)]
    found.sort(key=lambda c: c["a"])
    marks, used = markers(text), set()
    for c in found:
        c["line"] = text.count("\n", 0, c["a"])
        c["reason"] = c["mark"] = None
        for line in (c["line"], c["line"] - 1):
            if line in marks and line not in used and (line == c["line"] or marks[line][1]):
                used.add(line)
                c["reason"], c["mark"] = marks[line][0], line
                break
    return found


def crutches(rel: str, text: str) -> list[dict]:
    """The crutches of one C file, in order: {kind `pin`|`barrier`, id, func (SCOPE outside a function), line, a, b
    (the span that `drop` removes), keep (what it leaves), reason (of its marker, None with none), mark (the line of
    that marker), hash (of its function's body)}. Two crutches never share one marker."""
    scan = scan_file(rel, text)
    starts = [a for _, a, _ in scan["extents"]]
    spans: dict[str, list] = {}
    for name, a, b in scan["extents"]:
        spans.setdefault(name, []).append((a, b))
    seen: dict[tuple, int] = {}
    out = []
    for c in scan["crutches"]:
        c = dict(c)
        i = bisect.bisect_right(starts, c["a"]) - 1
        c["func"] = scan["extents"][i][0] if i >= 0 and c["a"] < scan["extents"][i][2] else SCOPE
        n = seen[(c["func"], c["name"])] = seen.get((c["func"], c["name"]), 0) + 1
        c["id"] = c["name"] + (":%d" % n if c["kind"] != "pin" else "#%d" % n if n > 1 else "")
        c["hash"] = body_hash(text, spans.get(c["func"], [(0, len(text))]))
        out.append(c)
    return out


def drop(text: str, c: dict) -> str:
    """The text without one crutch and without its marker. A pin `register T x asm("$n")` becomes `T x`. A barrier
    goes with its line when nothing else stands on it."""
    lines = (text[:c["a"]] + c["keep"] + text[c["b"]:]).split("\n")
    if c["kind"] == "barrier" and not lines[c["line"]].strip():
        lines[c["line"]] = None
    if c["mark"] is not None:
        left = _COMMENT.sub(lambda m: "" if "!FAKE:" in m.group(0) else m.group(0), lines[c["mark"]] or "").rstrip()
        lines[c["mark"]] = left if left.strip() else None
    return "\n".join(l for l in lines if l is not None)


def mark(text: str, c: dict, reason: str) -> str:
    """The text with a `// !FAKE: <reason>` line of its own above a crutch, in the place of a marker with no reason."""
    lines = text.split("\n")
    if c["mark"] is not None:
        left = _COMMENT.sub(lambda m: "" if "!FAKE:" in m.group(0) else m.group(0), lines[c["mark"]]).rstrip()
        lines[c["mark"]] = left if left.strip() else None
    at = lines[c["line"]]
    lines[c["line"]] = "%s// !FAKE: %s\n%s" % (at[:len(at) - len(at.lstrip())], reason, at)
    return "\n".join(l for l in lines if l is not None)


def probe_of(tree: Tree) -> tuple[str | None, str]:
    """(the `[trial] probe` command of the record, 16 hex digits for it and for each file of the tree that it names)."""
    cmd = record_table(tree, "trial").get("probe")
    h = hashlib.sha256((cmd or "").encode())
    for tok in re.split(r"[\s=:,;()'\"]+", cmd or ""):
        if tok in tree.paths:
            h.update(tree.raw(tok) or b"")
    return cmd, h.hexdigest()[:16]


def run_probe(repo, cmd: str, text: str, rel: str, func: str) -> int:
    """Ask the game's probe about one variant of a file: 0 the function matches, 1 it does not, 2 the probe failed.
    The variant is a file beside the tracked one, so the tracked file is never the one that is compiled. The command
    gets three values, as `{file}`, `{func}` and `{path}` in its text or as three more arguments: the file to
    compile, the function, and the tracked path that the file stands for."""
    src = pathlib.Path(repo) / rel
    variant = src.with_name("%s.psxd-trial%s" % (src.stem, src.suffix))
    env = dict(os.environ, **dict(zip(TRIAL_ENV, (str(variant), func, rel))))
    line = cmd
    for key, var in zip(("{file}", "{func}", "{path}"), TRIAL_ENV):
        line = line.replace(key, '"$%s"' % var)
    if line == cmd:
        line += ' "$%s" "$%s" "$%s"' % TRIAL_ENV
    try:
        variant.write_text(text, encoding="utf-8")
        r = subprocess.run(line, shell=True, cwd=str(repo), env=env, capture_output=True, text=True, timeout=PROBE_SECONDS)
        return r.returncode if r.returncode in (0, 1) else 2
    except (OSError, subprocess.TimeoutExpired):
        return 2
    finally:
        try:
            variant.unlink()
        except OSError:
            pass


def trial_function(text: str, rel: str, func: str, ask) -> tuple[str | None, dict]:
    """(the text with what the match does not need taken out and each survivor marked, the counts) for one function.
    `ask(text) -> 0|1|2` is the probe. None when the function cannot be tried: it does not match as it is, the probe
    answers otherwise for a comment (a control), or the probe failed."""
    mine = lambda t: [c for c in crutches(rel, t) if c["func"] == func and c["kind"] != "goto"]  # noqa: E731
    stats = {"tried": 0, "removed": 0, "kept": 0, "probes": 0, "why": ""}

    def probe(t):
        stats["probes"] += 1
        return ask(t)

    if probe(text) != 0:
        stats["why"] = "it does not match as it is"
        return None, stats
    first = mine(text)[0]
    stats["tried"] = len(mine(text))
    lines = text.split("\n")
    lines.insert(first["line"], "/* psxd trial: a comment changes no code */")
    if probe("\n".join(lines)) != 0:                   # the control: a probe that a comment moves proves nothing
        stats["why"] = "the probe gives another answer for a comment: it does not compile the file it is given"
        return None, stats
    while True:
        i, went = 0, False
        while i < len(mine(text)):
            without = drop(text, mine(text)[i])
            rc = probe(without)
            if rc == 2:
                stats["why"] = "the probe failed (exit 2 or more)"
                return None, stats
            if rc == 0:
                text, went = without, True
                stats["removed"] += 1
            else:
                i += 1
        if not went or not mine(text):                 # a crutch that left can free another one: once more
            break
    for i in range(len(mine(text))):
        c = mine(text)[i]
        if not reason_ok(c["reason"]):
            text = mark(text, c, "%s: the function does not match without it (trial)" % c["id"])
    stats["kept"] = len(mine(text))
    return text, stats


def trial_rows(tree: Tree) -> tuple[list[dict], list[str]]:
    rows, errs = read_tsv(TRIALS, TRIAL_COLUMNS, tree)
    return rows or [], errs


def trials_findings(repo, tree: Tree | None = None) -> list[str]:
    """What the gate refuses about crutches: a marker with no reason, a marked crutch with no row in
    config/trials.tsv, a row whose hash is not the body's (the body changed since its trial), a marked crutch and no
    `[trial] probe`, a crutch outside a function. An unmarked crutch is debt (`pin-unmarked`), not a finding here.
    A row is found by function, crutch and hash, so a function that moved to another file keeps its row."""
    tree = tree or Tree(repo)
    rows, errs = trial_rows(tree)
    out = ["%s: %s" % (TRIALS, e) for e in errs]
    have: dict[tuple, set] = {}
    for r in rows:
        if r["result"] == "kept":
            have.setdefault((r["function"], r["crutch"]), set()).add(r["hash"])
    marked = 0
    for p in tree.paths:
        text = tree.read(p) if is_source(p) and not is_asm(p) else None
        if not text or "!FAKE:" not in text:
            continue
        for c in crutches(p, text):
            if c["mark"] is None:
                continue
            marked += c["kind"] != "goto"
            where = "%s %s %s" % (p, c["func"] or "(file scope)", c["id"])
            row = have.get((c["func"], c["id"]))
            if not reason_ok(c["reason"]):
                out.append("no reason: %s: a `// !FAKE:` marker says why the crutch stays" % where)
            elif c["kind"] == "goto":                  # a goto needs its reason, and no trial
                continue
            elif c["func"] == SCOPE:
                out.append("no function: %s: a crutch outside a function cannot be tried" % where)
            elif not row:
                out.append("no row: %s has a marker and no row in %s: run `python3 %s trial %s --func %s`" % (
                    where, TRIALS, VENDORED, p, c["func"]))
            elif c["hash"] not in row:
                out.append("stale: %s: the body changed since its trial (hash %s, the row holds %s): run the trial again"
                           % (where, c["hash"], ", ".join(sorted(row))))
    if marked and not probe_of(tree)[0]:
        out.append("no [trial] probe in %s: a game cannot keep a crutch that it cannot examine" % RECORD)
    return out


def _write_trials(repo, rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r["path"], r["function"], r["crutch"]))
    f = pathlib.Path(repo) / TRIALS
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join("\t".join(r) + "\n" for r in [TRIAL_COLUMNS] + [tuple(r[c] for c in TRIAL_COLUMNS) for r in rows]),
                 encoding="utf-8")


def cmd_trial(repo, file: str | None, func: str | None = None, recheck: bool = False, against: str | None = None,
              sample: int = 10, base_rows: str | None = None) -> int:
    """`trial FILE [--func NAME]`: try each crutch of a file's functions (of one function), write the file and
    config/trials.tsv. `trial --recheck [--against BASE | --base-rows FILE] [--rows N]`: run rows again, those that
    are new since BASE (or that FILE, a copy of BASE's config/trials.tsv, does not hold: for a build with no git) and
    N more chosen at random; exit 1 on a row that says `kept` for a crutch the function matches without."""
    repo = pathlib.Path(repo)
    tree = Tree(repo)
    cmd, digest = probe_of(tree)
    if not cmd:
        print("TRIAL FAIL no [trial] probe in %s: the command that says whether one function of a file still matches "
              "(exit 0 match, 1 no match, 2 or more an error)" % RECORD)
        return 1
    rows, errs = trial_rows(tree)
    if errs:
        print("TRIAL FAIL %s: %s" % (TRIALS, errs[0]))
        return 1
    if recheck:
        return _recheck(repo, tree, cmd, rows, against, sample, base_rows)
    rel = pathlib.Path(repo / file).resolve().relative_to(repo.resolve()).as_posix() if file else ""
    text = tree.read(rel) if rel else None
    if text is None:
        print("TRIAL FAIL %s: no file of this repository (`trial <file> [--func <name>]`)" % (file or "no file"))
        return 1
    funcs = list(dict.fromkeys(c["func"] for c in crutches(rel, text) if c["func"] != SCOPE and c["kind"] != "goto"
                               and func in (None, c["func"])))
    if not funcs:
        print("TRIAL OK %s%s: no pin and no barrier in a function" % (rel, " " + func if func else ""))
        return 0
    total, bad = {"tried": 0, "removed": 0, "kept": 0, "probes": 0}, 0
    for name in funcs:
        new, stats = trial_function(text, rel, name, lambda t: run_probe(repo, cmd, t, rel, name))
        for k in total:
            total[k] += stats[k]
        if new is None:
            bad += 1
            print("TRIAL FAIL %s %s: %s" % (rel, name, stats["why"]))
            continue
        text = new
        print("TRIAL %s %s: %d tried, %d removed, %d kept" % (rel, name, stats["tried"], stats["removed"], stats["kept"]))
        here = lambda r: r["path"] == rel or name not in [n for n, _, _ in scan_file(r["path"], tree.read(r["path"]) or "")["extents"]]  # noqa: E731
        rows = [r for r in rows if not (r["function"] == name and here(r))]
        rows += [{"path": rel, "function": name, "crutch": c["id"], "hash": c["hash"], "result": "kept", "probe": digest}
                 for c in crutches(rel, text) if c["func"] == name and c["kind"] != "goto"]
    if text != tree.read(rel):
        (repo / rel).write_text(text, encoding="utf-8")
    if rows != trial_rows(tree)[0] or tree.read(TRIALS) is None and bad < len(funcs):
        _write_trials(repo, rows)
    print("TRIAL %s (%d function(s), %d tried, %d removed, %d kept; %d probe(s))" % (
        "FAIL" if bad else "OK", len(funcs), total["tried"], total["removed"], total["kept"], total["probes"]))
    return 1 if bad else 0


def _recheck(repo, tree: Tree, cmd: str, rows: list[dict], against: str | None, sample: int, base_rows: str | None = None) -> int:
    if base_rows is not None:
        old = {tuple(r[c] for c in TRIAL_COLUMNS) for r in read_tsv(base_rows, TRIAL_COLUMNS)[0] or []}
        against = against or base_rows
    else:
        old = {tuple(r[c] for c in TRIAL_COLUMNS) for r in trial_rows(Tree(repo, against))[0]} if against else set()
    new = [r for r in rows if tuple(r[c] for c in TRIAL_COLUMNS) not in old] if against else []
    rest = [r for r in rows if r not in new]
    import random
    picked = new + random.sample(rest, min(sample, len(rest)))
    bad = done = 0
    for r in picked:
        text = tree.read(r["path"])
        c = next((c for c in crutches(r["path"], text or "") if (c["func"], c["id"]) == (r["function"], r["crutch"])), None)
        where = "%s %s %s" % (r["path"], r["function"], r["crutch"])
        if c is None:
            print("TRIAL INFO %s: the source holds no such crutch (a row of a body that changed or moved)" % where)
            continue
        done += 1
        if run_probe(repo, cmd, text, r["path"], r["function"]) != 0:
            bad += 1
            print("TRIAL FAIL %s: the function does not match as it is" % where)
        elif run_probe(repo, cmd, drop(text, c), r["path"], r["function"]) == 0:
            bad += 1
            print("TRIAL FAIL removable: %s: the row says `kept`, and the function matches without it" % where)
    print("TRIAL RECHECK %s (%d row(s) run again: %d new since %s, %d of the %d others; %d finding(s))" % (
        "FAIL" if bad else "OK", done, len(new), against or "no base", len(picked) - len(new), len(rest), bad))
    return 1 if bad else 0


# ---- the gate: every check of the floor in one command, at the commit, at the bank, before a push and in CI ---------
# A check holds only against something the change cannot rewrite. So each change is judged against the tree it starts
# from (`transition`): HEAD for a commit and a bank, a commit's parent and the range's base in CI. The tree a change
# makes is then checked as it stands (`state`). A tool that a change replaces judges that change itself. The new tool
# takes over for what follows, and only after the old one accepted it.
TOOLS = (VENDORED, "tools/psxd_publish.py")
WORKFLOWS = ".github/workflows/"
SETTINGS = ".claude/settings.json"
RECORD_TABLES = ("own", "trial", "floor", "debt")     # the tables of the record that name a check of the game's own
DATA_SUFFIXES = (".tsv", ".txt", ".toml", ".json", ".md", ".csv")      # a ledger: its lines stay, a line may be added
GATE_ENV = "PSXD_GATE"                               # set while the game's own check runs: a gate inside it skips that check
GIT_LOCATION_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")


DIGESTS_URL = "https://raw.githubusercontent.com/anzaldoivan/psxdecomp/v%s/digests.json"   # the plugin's tag holds the file
DIGESTS_ENV = "PSXD_DIGESTS"                         # a file in the URL's place: a machine with no network, and the tests
README_WORKFLOW = WORKFLOWS + "psxdecomp-readme.yml"
_DIGESTS: dict[str, dict] = {}


def released_digests(version: str) -> dict[str, str]:
    """{path in a game: sha256} of the files that psxdecomp <version> delivers, as its release holds them. Raises Fail
    when the release cannot be read: a tool that nothing vouches for is not accepted."""
    if version not in _DIGESTS:
        src = os.environ.get(DIGESTS_ENV)
        try:
            if src:
                data = pathlib.Path(src).read_bytes()
            else:
                import urllib.request
                with urllib.request.urlopen(DIGESTS_URL % version, timeout=20) as r:
                    data = r.read()
            doc = json.loads(data)
        except Exception as e:                         # no network, no such release, no JSON
            raise Fail("cannot read the digests of psxdecomp %s (%s): %s" % (version, src or DIGESTS_URL % version, e))
        if not isinstance(doc, dict) or doc.get("version") != version or not isinstance(doc.get("files"), dict):
            raise Fail("the digests at %s are not those of psxdecomp %s" % (src or DIGESTS_URL % version, version))
        _DIGESTS[version] = doc["files"]
    return _DIGESTS[version]


def _released(tree: "Tree", rel: str, version: tuple) -> str | None:
    """Why the file of a tree is not the one that psxdecomp <version> released, or None when it is."""
    name = ".".join(map(str, version))
    try:
        want = released_digests(name).get(rel)
    except Fail as e:
        return str(e)
    have = hashlib.sha256(tree.raw(rel) or b"").hexdigest()
    return None if want == have else "it is not the file that psxdecomp %s released (sha256 %s, the release holds %s)" % (
        name, have[:12], (want or "no such file")[:12])


def tool_version(text: str | None) -> tuple[int, ...]:
    """The VERSION of a tool's text as a tuple; () for a text with none (a tool from before psxdecomp 0.6.0)."""
    m = re.search(r'^VERSION = "(\d+)\.(\d+)\.(\d+)"', text or "", re.M)
    return tuple(int(x) for x in m.groups()) if m else ()


def record_table(tree: Tree, table: str) -> dict[str, str]:
    """The string values of one table of config/psxdecomp.toml, read as text (no tomllib, as address_header)."""
    out, cur = {}, None
    for line in (tree.read(RECORD) or "").split("\n"):
        head = re.match(r"\s*\[\s*([^\]]+?)\s*\]\s*(?:#.*)?$", line)
        if head:
            cur = head[1]
            continue
        m = re.match(r"""\s*["']?([\w.-]+)["']?\s*=\s*(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""", line)
        if m and cur == table:
            out[m[1]] = m[2].replace('\\"', '"').replace("\\\\", "\\") if m[2] is not None else m[3]
    return out


def _settings(tree: Tree) -> dict:
    try:
        conf = json.loads(tree.read(SETTINGS) or "{}")
    except ValueError:
        return {"_broken": True}
    return conf if isinstance(conf, dict) else {"_broken": True}


def _hook_rows(conf: dict) -> list[tuple[str, str, frozenset]]:
    """[(event, the hook entry as JSON, the tools of its matcher)] for each hook of a settings file that runs one of
    psxdecomp's tools."""
    out = []
    hooks = conf.get("hooks") if isinstance(conf.get("hooks"), dict) else {}
    for event, groups in hooks.items():
        for g in groups if isinstance(groups, list) else ():
            for h in (g.get("hooks") or ()) if isinstance(g, dict) else ():
                if isinstance(h, dict) and "psxd_" in str(h.get("command", "")):
                    out.append((event, json.dumps(h, sort_keys=True), frozenset(str(g.get("matcher", "")).split("|"))))
    return out


def protected_findings(base: Tree, head: Tree, online: bool = False) -> tuple[list[str], list[str], bool]:
    """(what a change may not do to the files that carry the floor, the INFO lines, a tool was replaced and that is
    accepted). Each file is valid when it is valid against the tree the change starts from:
    - psxdecomp's two tools are the same bytes, or a later version. `online` (CI, the pre-push hook): and the bytes
      that psxdecomp released for that version (`released_digests`). A version number alone is no proof;
    - a workflow is the same bytes (a new workflow is free; psxdecomp's own changes as its tools do);
    - the settings keep each hook that runs a psxdecomp tool, each deny rule, and no `disableAllHooks`;
    - the guard keeps each `deny` row and gets no `allow` row;
    - the record keeps each value of [own], [trial], [floor] and [debt], and a file that such a value names keeps its
      bytes (a script) or its lines (a ledger)."""
    out, infos, replaced = [], [], False
    for rel in TOOLS:
        was, now = base.raw(rel), head.raw(rel)
        if was is None or was == now:
            continue
        if now is None:
            out.append("%s is gone" % rel)
            continue
        v0, v1 = tool_version(base.read(rel)), tool_version(head.read(rel))
        text = lambda v: ".".join(map(str, v)) or "no version"  # noqa: E731
        if v1 < v0:
            out.append("%s went from version %s back to %s" % (rel, text(v0), text(v1)))
        elif v1 == v0:
            out.append("%s changed and its version did not (%s): a tool changes only with an upgrade of psxdecomp" % (
                rel, text(v0)))
        else:
            why = _released(head, rel, v1) if online else None
            if why:
                out.append("%s changed: %s" % (rel, why))
                continue
            replaced = True
            infos.append("%s: version %s -> %s%s" % (rel, text(v0), text(v1), ", the released file" if online else
                                                     " (CI and the pre-push hook compare it with the released digest)"))
    for rel in sorted(p for p in base.paths if p.startswith(WORKFLOWS)):
        if base.raw(rel) == head.raw(rel):
            continue
        if rel == README_WORKFLOW and head.has(rel):     # psxdecomp's own workflow changes with an upgrade, as its tools do
            why = _released(head, rel, tool_version(head.read(VENDORED))) if online else None if replaced else "no tool changed with it"
            if not why:
                continue
            out.append("%s changed: %s" % (rel, why))
        else:
            out.append("%s %s" % (rel, "is gone" if not head.has(rel) else "changed: a workflow that exists keeps its bytes"))
    old, new = _settings(base), _settings(head)
    if new.get("_broken"):
        out.append("%s is not a JSON object" % SETTINGS)
    elif not old.get("_broken"):
        have = _hook_rows(new)
        for event, entry, tools in _hook_rows(old):
            if not any(e == event and h == entry and tools <= t for e, h, t in have):
                out.append("%s lost a hook of %s (or a tool of its matcher): %s" % (SETTINGS, event, json.loads(entry).get("command")))
        deny = lambda c: (c.get("permissions") or {}).get("deny") or [] if isinstance(c.get("permissions"), dict) else []  # noqa: E731
        gone = [r for r in deny(old) if r not in deny(new)]
        if gone:
            out.append("%s lost %d deny rule(s): %s" % (SETTINGS, len(gone), ", ".join(map(str, gone[:3]))))
        if new.get("disableAllHooks"):
            out.append("%s sets disableAllHooks" % SETTINGS)
    rules0, rules1 = parse_guard(base.read(GUARD)), parse_guard(head.read(GUARD))
    gone = [r for r in rules0 if r[0] == "deny" and r[:3] not in [x[:3] for x in rules1]]
    out += ["%s lost the row `deny %s %s`" % (GUARD, r[1], r[2]) for r in gone]
    out += ["%s has a new `allow` row (%s %s): the first row that matches decides, so it can open a denied path" % (
        GUARD, r[1], r[2]) for r in rules1 if r[0] == "allow" and r[:3] not in [x[:3] for x in rules0]]
    env = lambda c: {k: v for k, v in (c.get("env") or {}).items() if k.startswith("CLAUDE")} if isinstance(c.get("env"), dict) else {}  # noqa: E731
    if not new.get("_broken") and env(new) != env(old):
        out.append("%s sets %s in `env`: a hook finds the repository by that variable" % (SETTINGS, ", ".join(sorted(env(new)) or sorted(env(old)))))
    local = SETTINGS.replace(".json", ".local.json")
    if head.has(local) and head.raw(local) != base.raw(local):
        out.append("%s is tracked and changed: the settings of one machine are not the repository's" % local)
    skip = parse_baseline(base.read(BASELINE)).skip if _baseline_ok(base) else []
    for rel in sorted(set(base.paths) | set(head.paths)) if skip else ():
        if any(entry_match(e, rel) for e in skip) and base.raw(rel) != head.raw(rel):
            out.append("%s changed, and a `skip` line covers it: a file that the checker does not read keeps its bytes" % rel)
    named: list[str] = []
    for table in RECORD_TABLES:
        vals0, vals1 = record_table(base, table), record_table(head, table)
        if base.has(RECORD) and not replaced:
            out += ["%s [%s] %s is new (%r): a key of this table changes what a check reads" % (RECORD, table, key, vals1[key])
                    for key in sorted(vals1) if key not in vals0]
        for key, val in sorted(vals0.items()):
            if vals1.get(key) != val:
                out.append("%s [%s] %s changed (it was %r)" % (RECORD, table, key, val))
            named += [tok for tok in re.split(r"[\s=:,;()'\"]+", val) if tok in base.paths and tok not in named]
    for rel in named:
        was, now = base.read(rel), head.read(rel)
        if now is None:
            out.append("%s is gone (the record names it)" % rel)
        elif rel.endswith(DATA_SUFFIXES):
            left = set(now.split("\n"))
            lost = [l for l in was.split("\n") if l not in left]
            if lost:
                out.append("%s lost or changed %d line(s) (the record names it: a ledger keeps its lines)" % (rel, len(lost)))
        elif was != now:
            out.append("%s changed (the record names it: a check of the game's own keeps its bytes)" % rel)
    return out, infos, replaced


def _baseline_ok(tree: Tree) -> bool:
    try:
        parse_baseline(tree.read(BASELINE))
        return True
    except Fail:
        return False


def developer_acts(base: Tree, head: Tree) -> list[str]:
    """What only the developer adds, and a change added: a `raise` line of the baseline (also `raise protected`), a
    row of the assembly ledger. Each one lets a count rise or clears one, on a person's word."""
    lines = lambda t, rel: (t.read(rel) or "").lstrip("\ufeff").split("\n")  # noqa: E731
    out = ["`%s` in %s" % (l.strip(), BASELINE) for l in lines(head, BASELINE)
           if l.strip().startswith("raise ") and l not in lines(base, BASELINE)]
    old = set(lines(base, ASM_EVIDENCE))
    out += ["the row of %s in %s" % (" ".join(l.split("\t")[1:3]), ASM_EVIDENCE) for l in lines(head, ASM_EVIDENCE)[1:]
            if l.strip() and not l.startswith("#") and l not in old]
    return out


def _sibling_run(repo, *args) -> tuple[int, list[str]]:
    """(the exit code, the output lines) of psxdecomp's other tool, the copy beside this file. 127 when none is there."""
    if not sibling().is_file():
        return 127, ["no %s beside %s" % (sibling().name, pathlib.Path(__file__).name)]
    r = subprocess.run([sys.executable, "-I", str(sibling()), *args], cwd=str(repo), capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).splitlines()


def _source_args(tree: Tree) -> list[str]:
    return [] if tree.source is None else ["--staged"] if tree.source == INDEX else ["--rev", tree.source]


def transition(repo, bases: list[Tree], head: Tree, online: bool = False, changed=None) -> tuple[list, list, bool]:
    """([(check, detail)], the INFO lines, a tool was replaced) for the change from a base tree to `head`. With
    several bases (a merge and its parents) the change passes when it passes against one of them. `changed`: the
    paths the change touches, when the caller knows them: a check whose files it does not touch is not run."""
    best = None
    debt_due = changed is None or any(p.startswith("config/") or p.endswith((".c", ".h", ".s", ".S", ".inc")) for p in changed)
    style_due = changed is None or any(p.startswith("config/") or p.endswith(".md") for p in changed)
    for base in bases:
        fails, infos = admission(repo, base, head) if debt_due else ([], [])
        found, more, replaced = protected_findings(base, head, online)
        found += ["policy: " + d for ck, d in fails if ck == "policy"]       # a change of the policy is a protected change
        fails = [f for f in fails if f[0] != "policy"]
        other = parse_baseline(base.read(BASELINE)).other
        slack = sum(int(m[1]) for l in parse_baseline(head.read(BASELINE)).other if l not in other
                    for m in [re.fullmatch(r"raise protected (\d+) \S+ \S.*", l)] if m)
        infos += more
        if found and len(found) <= slack:
            infos += ["protected, and a `raise protected` line of the change allows it: %s" % f for f in found]
        else:
            fails += [("policy", f[8:]) if f.startswith("policy: ") else ("protected", f) for f in found]
        if style_due:
            rc, lines = _sibling_run(repo, "style", *_source_args(head), "--against", base.source, "--repo", str(repo))
            if rc:
                fails += [("style", l[11:]) for l in lines if l.startswith("STYLE FAIL ")] or [
                    ("style", "exit %d: %s" % (rc, (lines or ["no output"])[-1]))]
        if best is None or len(fails) < len(best[0]):
            best = (fails, infos, replaced)
        if not fails:
            break
    return best if best is not None else ([], [], False)


# ---- a symbol dump of a build, as text. A path rule and a hash cannot see one: the text is made on the developer's
# machine from a symbol file, and it has another hash each time. The shape is the SDK dumper's own. The
# rule is the audit's rule for a listing: the longest run of such lines in one file, and a short quote passes ----------
SYMDUMP_CAP = 64
SYMDUMP_SHAPE = r"[0-9a-f]{6}: \$[0-9a-f]{8} [^\n]*"    # the SDK's symbol dumper, and psx_mnd_sym: `000056: $00000000 94 Def ...`
SYMDUMP_LINE = re.compile(SYMDUMP_SHAPE + r"\Z")
SYMDUMP_RUN = re.compile(r"(?:^%s(?:\n|\Z)){%d}" % (SYMDUMP_SHAPE, SYMDUMP_CAP), re.M)


def symdump_run(text: str | None) -> int:
    """The longest run of lines with the shape of a symbol dump; 0 for a text with no run of SYMDUMP_CAP lines, and
    for a binary file."""
    if not text or "\0" in text[:8192] or not SYMDUMP_RUN.search(text):
        return 0
    best = run = 0
    for line in text.split("\n"):
        run = run + 1 if SYMDUMP_LINE.match(line) else 0
        best = max(best, run)
    return best


def symdump_findings(tree: Tree) -> list[str]:
    out = []
    for path in tree.paths:
        n = symdump_run(tree.read(path))
        if n:
            out.append("%s: %d lines in a row have the shape of a PsyQ symbol dump (cap %d). A dump of "
                       "another build is a file of that build: keep it in disks/builds/<id>/, which git ignores"
                       % (path, n, SYMDUMP_CAP))
    return out


def state(repo, tree: Tree, here: bool = True, base: Tree | None = None) -> list[tuple[str, str]]:
    """[(check, detail)] for a tree as it stands: its baseline, its ledgers (`base`: the tree the change starts from,
    whose ledger rows are not opened again), no symbol dump as text, and (`here`: the work tree holds this tree) its plan, its toolchain
    pins, its README and its category ids."""
    out = [("debt", f) for f in state_findings(repo, tree)[0]]
    out += [("trials", f) for f in trials_findings(repo, tree)]
    out += [("names", d) for lv, d in names_findings(repo, tree, base) if lv == "FAIL"]
    out += [("symdump", f) for f in symdump_findings(tree)]
    if not here:
        return out
    out += own_debt(repo, tree)
    out += [("plan", "%s: %s" % (ck, d)) for lv, ck, d in lint_plan(repo) if lv == "FAIL"]
    out += [("toolchain", "%s: %s" % (name, d)) for st, name, d in toolchain_rows(repo) or () if st == "FAIL"]
    for check, rel, args in (("readme", "README.md", ["lint", "README.md"]),
                             ("categories", "config/categories.tsv", ["categories", "config/categories.tsv", "--history"])):
        if tree.has(rel):
            rc, lines = _sibling_run(repo, *args, "--repo", str(repo))
            if rc:
                out += [(check, l) for l in lines if " FAIL " in l or " ERROR " in l][:20] or [(check, "exit %d" % rc)]
    return out


def own_debt(repo, tree: Tree) -> list[tuple[str, str]]:
    """The game's own debt scanner, `[own] debt` of the record, run beside this tool's count: it adds a check, it
    replaces none. A value that is a file of the tree is run by its interpreter (`.py`, `.sh`), any other value is a
    command. Not run inside the game's own check, which runs it itself."""
    cmd = record_table(tree, "own").get("debt")
    if not cmd or os.environ.get(GATE_ENV):
        return []
    if tree.has(cmd):
        cmd = ("%s %s" % (sys.executable, cmd)) if cmd.endswith(".py") else ("sh %s" % cmd) if cmd.endswith(".sh") else "./" + cmd
    r = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True, env=dict(os.environ, **{GATE_ENV: "1"}))
    last = ((r.stdout + r.stderr).strip().splitlines() or ["no output"])[-1]
    return [("own-debt", "the game's own scanner `%s` exited %d: %s" % (cmd, r.returncode, last[:200]))] if r.returncode else []


def game_check(repo, tree: Tree) -> list[tuple[str, str]]:
    """The game's own check, `[floor] gate` or `[own] gate` of the record, run by the shell in the repository."""
    cmd = record_table(tree, "floor").get("gate") or record_table(tree, "own").get("gate")
    if not cmd or os.environ.get(GATE_ENV):
        return []
    r = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True, env=dict(os.environ, **{GATE_ENV: "1"}))
    last = ((r.stdout + r.stderr).strip().splitlines() or ["no output"])[-1]
    return [("game", "`%s` exited %d: %s" % (cmd, r.returncode, last[:200]))] if r.returncode else []


def _rev(repo, name: str) -> str | None:
    r = _git(repo, "rev-parse", "-q", "--verify", name + "^{commit}")
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _handover(repo, tree: Tree, args: list[str]) -> tuple[int, str] | None:
    """Run the gate again with the tools that `tree` holds, from a temporary folder: (its exit code, its output).
    None when the tree holds the very tool that runs."""
    mine = pathlib.Path(__file__).read_bytes()
    if tree.raw(VENDORED) in (None, mine):
        return None
    with tempfile.TemporaryDirectory() as td:
        for rel in TOOLS:
            if tree.raw(rel) is not None:
                (pathlib.Path(td) / pathlib.Path(rel).name).write_bytes(tree.raw(rel))
        r = subprocess.run([sys.executable, "-I", str(pathlib.Path(td) / pathlib.Path(VENDORED).name), "gate", *args,
                            "--repo", str(repo)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def cmd_gate(repo, mode: str, rng: str | None = None, part: str = "all", range_base: str | None = None) -> int:
    """`gate --staged | --bank | --ci <base>..<head> | --push [<base>..<head>]`: `GATE FAIL <check>: <detail>` lines and
    one last line, `GATE OK` or `GATE FAIL`; exit 1 on a FAIL. `--bank` also counts the source files that git does not
    track yet, writes the rows of the baseline when the change is admitted, and runs the game's own check. `--ci`
    judges each commit of the range against its parent, and the head of the range against its base."""
    repo = pathlib.Path(repo)
    index = os.environ.get("GIT_INDEX_FILE")
    if index and not os.path.isabs(index):             # `git commit -a` gives the hook an index of its own
        os.environ["GIT_INDEX_FILE"] = os.path.abspath(index)
    for k in GIT_LOCATION_ENV:                         # git exports these to a hook, and they win over `-C`
        os.environ.pop(k, None)
    os.environ["GIT_NO_REPLACE_OBJECTS"] = "1"       # a replaced object is not the history that was pushed
    fails: list[tuple[str, str]] = []
    infos: list[str] = []
    warns: list[str] = []
    passed, what = None, mode
    try:
        if mode in ("staged", "bank"):
            head = Tree(repo, INDEX) if mode == "staged" else Tree(repo, None, untracked=True)
            bases = [Tree(repo, r) for r in ("HEAD", "MERGE_HEAD") if _rev(repo, r)]
            replaced = False
            if part == "all" and bases:
                fails, infos, replaced = transition(repo, bases, head)
                acts = developer_acts(bases[0], head)
                if acts and os.environ.get("CLAUDECODE"):
                    fails += [("raise", "%s is new, and this is an agent session (CLAUDECODE is set): the developer adds it and "
                               "commits it from a terminal" % a) for a in acts]
                infos += ["the developer's act, new in this change: %s" % a for a in acts]
            elif part == "all":
                infos.append("no commit yet: nothing to judge the change against")
            if mode == "bank" and not fails:
                st = state_findings(repo, head)[1]
                if st["baseline"].version == 2 and (st["rise"] or st["stale"]):
                    _write_baseline(repo, baseline_text(st["baseline"], st["counts"]))
                    infos.append("%s: the rows of now written (%d rose with a new body, %d fell)" % (
                        BASELINE, len(st["rise"]), len(st["stale"])))
                    head = Tree(repo, None, untracked=True)
            passed = _handover(repo, head, ["--" + mode, "--part", "state"]) if replaced and not fails else None
            if passed is None:
                fails += state(repo, head, base=bases[0] if bases else None)
                if mode == "bank" and not fails:
                    fails += game_check(repo, head)
        else:
            named, _, tip = (rng or "").partition("..")
            tip = _rev(repo, tip or "HEAD")
            if tip is None:
                raise Fail("%s names no commit: `gate --%s <base>..<head>`" % (rng, mode))
            base = _rev(repo, named) if named and set(named) != {"0"} else None
            if named and set(named) != {"0"} and base is None:
                raise Fail("the base %s names no commit of this repository: nothing would judge the change" % named)
            if _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
                raise Fail("a shallow repository: the parents of its oldest commits are missing, so those commits would "
                           "be judged against nothing (fetch the full history)")
            if base is None and mode == "push" and not rng:
                base = _rev(repo, "@{upstream}")
            commits = _git(repo, "rev-list", "--reverse", tip, *(["^" + base] if base else ["--max-count=0"])).stdout.split()
            what = "%s; %d commit(s)%s" % (mode, len(commits), "" if base else "; no base: the tree of the head only")
            head = Tree(repo, tip)
            for n, c in enumerate(commits if part == "all" else ()):
                parents = _git(repo, "rev-list", "--parents", "-n", "1", c).stdout.split()[1:]
                if not parents and not (range_base or base):
                    continue
                if not parents:                        # a commit with no parent, beside a history: the base judges it
                    parents = [range_base or base]
                    infos.append("%s has no parent: it is judged against the base %s" % (c[:10], parents[0][:10]))
                changed = set()
                for p in parents:
                    changed |= {x for x in _git(repo, "diff-tree", "-r", "--name-only", "--no-commit-id", "-z", p, c).stdout.split("\0") if x}
                found, more, replaced = transition(repo, [Tree(repo, p) for p in parents], Tree(repo, c), mode == "push" or mode == "ci", changed)
                fails += [(ck, "%s: %s" % (c[:10], d)) for ck, d in found]
                infos += ["%s: %s" % (c[:10], i) for i in more]
                warns += ["%s: the developer's act, new in this commit: %s" % (c[:10], a) for a in developer_acts(Tree(repo, parents[0]), Tree(repo, c))]
                if replaced and not found:
                    passed = _handover(repo, Tree(repo, c), ["--" + mode, "%s..%s" % (c, tip)] + (
                        ["--range-base", range_base or base] if (range_base or base) else []))
                    if passed is not None:
                        what += "; from %s on, the tools of that commit judge" % c[:10]
                        break
            if passed is None:
                first = range_base or base
                direct = len(commits) == 1 and _git(repo, "rev-list", "--parents", "-n", "1", tip).stdout.split()[1:] == [first]
                if part == "all" and first and commits and not direct:
                    found, more, _ = transition(repo, [Tree(repo, first)], head, True)
                    fails += [(ck, "%s..%s: %s" % (first[:10], tip[:10], d)) for ck, d in found if (ck, d) not in
                              [(k, x.split(": ", 1)[-1]) for k, x in fails]]
                here = _rev(repo, "HEAD") == tip
                if not here:
                    infos.append("the work tree is not at %s: its plan, README and category ids are not read" % tip[:10])
                fails += state(repo, head, here, Tree(repo, first) if first else None)
                if mode == "push" and not fails:
                    fails += game_check(repo, head)
    except Fail as e:
        fails.append(("gate", str(e)))
    for check, detail in fails:
        print("GATE FAIL %s: %s" % (check, detail))
    for text in warns:
        print("GATE WARN %s" % text)
    for text in infos:
        print("GATE INFO %s" % text)
    rc = 1 if fails else 0
    if passed is not None:
        sys.stdout.write(passed[1])
        rc = rc or (1 if passed[0] else 0)
    if passed is None or fails:
        print("GATE %s (%s%s)" % ("FAIL" if fails else "OK", what, "; %d finding(s)" % len(fails) if fails else ""))
    return rc


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
    "goto": ("void Walk(s32 n) {\nloop:\n    // !FAKE: the loop of the original\n    if (--n) goto loop;\n}\n", {"goto": 1}),
    "goto-unmarked": ("void Walk(s32 n) {\nloop:\n    if (--n) goto loop;\n}\n", {"goto": 1, "goto-unmarked": 1}),
    "goto, through a macro": ("#define AGAIN goto loop\nvoid Walk(s32 n) {\nloop:\n    if (--n) AGAIN;\n}\n", {"goto": 1, "goto-unmarked": 1}),
    "barrier": ('void Walk(void) {\n    // !FAKE: the load must come first\n    __asm__("");\n}\n', {"barrier": 1}),
    "barrier-unmarked": ('void Walk(void) {\n    asm("");\n}\n', {"barrier": 1, "barrier-unmarked": 1}),
    "pin, the other spellings": ('void Walk(void) {\n    register s32 i __asm("$16");\n    register s32 j\n        __asm__ ( "$17" );\n}\n',
                                 {"pin": 2, "pin-unmarked": 2}),
    "asm, through a macro": ('#define PIN(r) asm(r)\nvoid Walk(void) {\n    register s32 i PIN("$16");\n}\n', {"asm": 2}),
    "cast": ("void Walk(Obj *p, s32 a) {\n    a = (s32)&p->next;\n    p = (Obj *)(s32)a;\n    a = (s32)(u8 *)p;\n}\n", {"cast": 3}),
    "field": ("s32 Walk(Obj *p) {\n    return p->unk_10 + p->field_0x14 + p->unk3C + p->hp;\n}\n", {"field": 3}),
    "obscured, a head in K&R form": ("s32 Walk(n)\ns32 n;\n{\n    if (n) {\n        return 1;\n    }\n    return 0;\n}\n", {"obscured": 3}),
    "obscured, a spliced line": ("void Walk(s32 n) {\n    n = n + \\\n        1;\n}\n", {"obscured": 1}),
    "obscured, a digraph": ("void Walk(s32 n) <%\n    n = 1;\n%>\n", {"obscured": 2}),
    "extern": ("extern s32 g_Mode;\ns32 Other(s32 a);\nstatic s32 Mine(s32 a);\ns32 Walk(void) {\n    extern s32 g_Late;\n    return g_Mode;\n}\n",
               {"extern": 3}),
    "placeholder, a disassembler's name": ("s32 FUN_80012344(void) {\n    return DAT_800A1234 + sub_80012000();\n}\n",
                                           {"placeholder": 1, "placeholder-use": 2}),
    "address, with leading zeros": ("void Walk(void) {\n    *(volatile u32 *)0x01F801070 = 0;\n}\n", {"address": 1}),
    "struct, with an attribute": ("struct __attribute__((packed)) Pair {\n    s32 a;\n};\n", {"struct": 1}),
    "offset": ("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\ns32 Walk(void *p) {\n    return HP(p) + HP(p) + M2C_FIELD(p, s32 *, 8);\n}\n",
               {"offset": 4}),
    "address": ("void Walk(void) {\n    *(volatile u32 *)0x1F801070 = 0;\n}\n", {"address": 1}),
    "address, no cast": ("void Walk(Obj *p) {\n    Load(2, 0x800D5800);\n    p->next = 0x8017CA14;\n}\n", {"address": 2}),
    "address, a function-pointer cast": ("void Walk(void) {\n    src = (s32 (*)[2])0x80103000;\n}\n", {"address": 1}),
    "address, a macro over a macro": ("#define SP(off) (0x1F800000 + (off))\n#define SP_OBJ SP(0x64)\n"
                                      "s32 Walk(void) {\n    return SP_OBJ + SP_OBJ;\n}\n", {"address": 3}),
    "no address": ("s32 Walk(s32 a) {\n    void *end = (void *)0xFFFFFFFF;\n    return (a & 0x80000000) ? 0x12345 : 0x1F;\n}\n", {}),
    "the sign mask behind a pointer cast": ("void Walk(void) {\n    *(u32 *)0x80000000 = 0;\n}\n", {"address": 1}),
    "offset, one cast": ("void Walk(s32 a) {\n    *(short *)(a + 0x9C) = 0;\n    *(unsigned char *)(a + 0x7B) = 4;\n"
                         "    *(s32 *)((s32)a + 8) = 1;\n}\n", {"offset": 3, "cast": 1}),
    "offset, the index form": ("s32 Walk(void *self) {\n    return ((s8 *)self)[0x45] + *((u8 *)self + 2);\n}\n", {"offset": 2}),
    "offset, through a member": ("void Walk(Ctx *ctx, Obj *a) {\n    *(short *)(ctx->pc + 4) = 0;\n    ((u8 *)a->link.owner)[0x14]--;\n"
                                 "    *(s32 *)(a->tbl[2] + 8) = 1;\n}\n", {"offset": 3}),
    "offset, a cast sum read through": ("s32 Walk(void *p) {\n    return ((Obj *)((u8 *)p + 0x10))->hp;\n}\n", {"offset": 1}),
    "offset, a byte pointer plus a number": ("void Walk(void *dst, s32 n) {\n    dst = (void *)((char *)dst + 0xC);\n}\n", {"offset": 1}),
    "no offset": ("void Walk(void *dst, s32 n) {\n    end = (u8 *)dst + n;\n    p = q + 4;\n}\n", {}),
    "the define of M2C_FIELD": ("#define M2C_FIELD(expr, type_ptr, offset) (*(type_ptr)((s8 *)(expr) + (offset)))\n", {}),
    "the stub macro": ("#define INCLUDE_ASM(FOLDER, NAME) \\\n    __asm__(\".include \\\"\" FOLDER \"/\" #NAME \".s\\\"\");\n", {}),
    "macro": ("#define SWAP(a, b) { s32 t = a; a = b; b = t; }\n#define TWO(a) \\\n    ((a) * 2)\n", {"macro": 2}),
    "asm": ('void Walk(void) {\n    __asm__("nop");\n}\n', {"asm": 1}),
    "placeholder": ("s32 D_800A1234 = 4;\nextern s32 D_800A5678;\nINCLUDE_ASM(\"asm/nonmatchings\", func_80010000);\n"
                    "s32 func_80012344(s32 a) {\n    return a;\n}\n", {"placeholder": 2, "placeholder-use": 1, "extern": 1}),
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


def self_test_debt(check) -> None:
    check("a clean file has no debt", file_debt("src/a.c", C_CLEAN) == {}, file_debt("src/a.c", C_CLEAN))
    for kind, (text, want) in C_DEBT.items():
        check("one planted file: " + kind, file_debt("src/a.c", text) == want, file_debt("src/a.c", text))
    check("a struct in include/ is no debt", file_debt("include/a.h", C_DEBT["struct"][0]) == {})
    check("the address header may hold addresses", file_debt("include/addr.h", C_DEBT["address"][0]) == {})
    plumbing = '__asm__(".include \\"macro.inc\\"\\n");\nstatic inline void Nop(void) {\n    __asm__("nop");\n}\n'
    check("a header's file-scope asm statement is no debt", file_debt("include/common.h", plumbing) == {"asm": 1}
          and file_debt("src/a.c", plumbing) == {"asm": 2}, file_debt("include/common.h", plumbing))
    shared = _macros(strip("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\n"))
    check("a header's offset macro counts at each use", file_debt("src/a.c", "s32 Walk(void *p) {\n    return HP(p);\n}\n", shared)
          == {"offset": 1})
    check("unbased: a function with no row", file_debt("src/a.c", C_CLEAN, based=set()) == {"unbased": 1})
    check("unbased: a function with a row", file_debt("src/a.c", C_CLEAN, based={"Player_Hp"}) == {})
    bl = parse_baseline("# top\nmode goto down\nbudget pin 30 base 4 10 20\nmode shift down\n3 shift src/a.c\n"
                        "raise goto 2 2026-01-02 the first wave\nskip src/vendor/\n1 goto src/a.c\n# a note below a row\n")
    check("the baseline: its lines, and the lines of a kind this tool does not know", bl.version == 2
          and bl.head == ["# top", "# a note below a row"] and bl.policy("goto") == ("down",)
          and bl.policy("pin") == ("budget", 30, 4, 10, 20) and bl.other == ["mode shift down", "3 shift src/a.c"]
          and bl.raises == [("goto", 2, "2026-01-02", "the first wave")] and bl.lacks()[:2] == ["pin-unmarked", "goto-unmarked"], vars(bl))
    check("the baseline is written as it was read", baseline_text(bl) == "# top\n# a note below a row\nbudget pin 30 base 4 10 20\n"
          "mode goto down\nmode shift down\n3 shift src/a.c\nraise goto 2 2026-01-02 the first wave\nskip src/vendor/\n"
          "1 goto src/a.c\n", baseline_text(bl))
    for name, text, want in (("two rows of one pair", "1 goto src/a.c\n1 goto src/a.c\n", "has two rows"),
                             ("two policy lines of one kind", "mode goto down\nbudget goto 3 base 1 1 1\n", "two policy lines"),
                             ("a second mode line of version 1", "mode down\nmode admit\n", "a second `mode` line"),
                             ("the two versions in one file", "mode admit\nmode goto down\n", "of version 1 beside"),
                             ("a line that is no line", "mode sideways\n", ":1: not `<count> <kind> <path>`")):
        try:
            parse_baseline(text)
            check("the baseline: %s is refused" % name, False)
        except Fail as e:
            check("the baseline: %s is refused" % name, want in str(e), str(e))
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        (repo / "include").mkdir()
        (repo / "config").mkdir()
        (repo / "src" / "clean.c").write_text(C_CLEAN)
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        stub = lambda *names: (repo / "src" / "stubs.c").write_text("".join(  # noqa: E731
            'INCLUDE_ASM("asm/nonmatchings/a", %s);\n' % n for n in names) or "// every function is in C\n")
        stub("Run", "Jump")                            # a new body is one that takes its stub away
        (repo / "src" / "boot.s").write_text("nop\n")
        (repo / "include" / "include_asm.h").write_text("#define INCLUDE_ASM(d, n) __asm__(\".include \\\"n\\\"\");\n")
        _git(repo, "add", "src", "include")
        run = lambda *a, **kw: _capture(cmd_debt, repo, *a, **kw)  # noqa: E731
        judge = lambda base, head=None: admission(repo, Tree(repo, base), Tree(repo, head))[0]  # noqa: E731
        walk, base_file = repo / "src" / "walk.c", repo / BASELINE
        rc, out = run()
        check("no baseline: the totals, and a failure", rc == 1 and "totals: goto 1, asm 1 " in out
              and "DEBT FAIL no config/debt-baseline.txt: `python3 tools/psxd_floor.py debt --recount` writes it" in out, out)
        rc, out = run(update=True)
        check("--update writes no first baseline", rc == 1 and not base_file.exists(), out)
        text = first_baseline(repo)
        check("the first baseline: a policy line per kind, the stub header skipped, the rows", text.startswith(
            "# config/debt-baseline.txt: ") and text.endswith(
            "budget pin 30 base 0 2 2\nmode pin-unmarked down\nbudget goto 12 base 1 2 2\nmode goto-unmarked down\nmode barrier down\n"
            "mode barrier-unmarked down\nmode offset admit-new\nmode address admit-new\nmode cast admit-new\nmode field admit-new\n"
            "mode macro admit-new\nmode asm down\nmode obscured down\nmode placeholder admit-new\nmode placeholder-use admit-new\n"
            "mode unbased down\nmode struct admit-new\nmode extern admit-new\nmode filename admit-new\nmode flag admit-new\n"
            "mode reservation down\nskip include/include_asm.h\n1 asm src/boot.s\n1 goto src/walk.c\n"), text)
        rc, out = run(recount=True)
        check("--recount writes it", rc == 0 and base_file.read_text() == text and "DEBT RECOUNT written" in out
              and "DEBT INFO policy written: pin: budget 30 0 2 2\n" in out, out)
        rc, out = run()
        check("an equal baseline passes", rc == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); down: pin-unmarked, goto-unmarked, "
              "barrier, barrier-unmarked, asm, obscured, unbased, reservation; budget: pin 30, goto 12; admit-new: offset, address, cast, "
              "field, macro, placeholder, placeholder-use, struct, extern, filename, flag)" in out, out)
        _git(repo, "add", "config")
        _commit(repo, "the floor")
        # a body that exists never gets worse, whatever the rows say
        walk.write_text(C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        rc, out = run()
        check("a rise fails and names the command", rc == 1 and "DEBT FAIL rise goto src/walk.c: 2, its row is 1\n" in out
              and "debt --update`, then commit config/debt-baseline.txt" in out
              and "DEBT INFO skip: include/include_asm.h" in out, out)
        rc, out = run(update=True)
        check("--update refuses a rise in a body that exists", rc == 1 and base_file.read_text() == text and
              "DEBT FAIL debt: rose in an existing body: goto src/walk.c Walk: 1 -> 2\n" in out and "DEBT UPDATE refused" in out, out)
        try:
            with open(os.devnull, "w") as null, contextlib.redirect_stderr(null):
                main(["debt", "--update", "--admit", "--repo", str(repo)])
            check("--admit is no flag", False)
        except SystemExit as e:
            check("--admit is no flag: exit 2", e.code == 2, e.code)
        base_file.write_text(text.replace("1 goto src/walk.c", "2 goto src/walk.c"))
        rc, out = run()
        check("a row written by hand is equal to the tree", rc == 0, out)
        rc, out = run(against="HEAD")
        check("and the change is refused all the same", rc == 1 and "DEBT FAIL debt: rose in an existing body: goto src/walk.c "
              "Walk: 1 -> 2\n" in out and "1 finding(s) against HEAD" in out, out)
        base_file.write_text(text)
        # debt arrives with a new body; outside a function it needs one in the same file
        more = C_DEBT["goto"][0] + C_DEBT["goto"][0].replace("Walk", "Run")
        walk.write_text(more)
        rc, out = run(update=True)
        check("--update refuses the debt of a body that takes no stub away", rc == 1 and "DEBT FAIL debt: rose in a body that is not "
              "new: goto src/walk.c Run (in the place of no body that left: it takes no INCLUDE_ASM line away, and its file is not new): 0 -> 1" in out, out)
        stub("Jump")
        rc, out = run(update=True)
        check("--update takes the debt of a new body", rc == 0 and "DEBT INFO admitted with a new body: goto src/walk.c: 1 -> 2\n" in out
              and "2 goto src/walk.c\n" in base_file.read_text() and run()[0] == 0 and not judge("HEAD"), out)
        base_file.write_text(text)
        stub("Run", "Jump")
        walk.write_text("void Pad(void) {\n}\n" + C_DEBT["goto"][0].replace("Walk", "Stroll").replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        check("an empty body beside a renamed one buys nothing", [f[1] for f in judge("HEAD")] == [
            "rose in a body that is not new: goto src/walk.c Stroll, src/walk.c Pad (in the place of 1 body(ies) that left): 1 -> 2"], judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0] + C_DEBT["struct"][0].split("s32 Walk")[0])
        check("a rise outside a function with no new body", [f[1] for f in judge("HEAD")] == [
            "rose outside a function with no new body: struct src/walk.c (file scope): 0 -> 1"], judge("HEAD"))
        walk.write_text(more + C_DEBT["struct"][0].split("s32 Walk")[0])
        stub("Jump")
        check("a rise outside a function beside a new body", not judge("HEAD"), judge("HEAD"))
        stub("Run", "Jump")
        walk.write_text(C_DEBT["goto"][0])
        (repo / "include" / "m.h").write_text("#define SWAP(a, b) { s32 t = a; a = b; b = t; }\n")
        _git(repo, "add", "include/m.h")
        check("a file of definitions only is free: what it hides is counted where it is used", not judge("HEAD"), judge("HEAD"))
        (repo / "include" / "m.h").write_text("#define AT(p) (*(s32 *)((u8 *)(p) + 4))\n")
        walk.write_text(C_DEBT["goto"][0].replace("loop:\n", "loop:\n    n = AT(n);\n"))
        check("a use of what a header hides is debt of the body that uses it", [f[1] for f in judge("HEAD")] == [
            "rose in an existing body: offset src/walk.c Walk: 0 -> 1"], judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0])
        _git(repo, "rm", "-q", "-f", "--cached", "include/m.h")
        (repo / "include" / "m.h").unlink()
        # a renamed and a moved body are the body they were
        walk.write_text(C_DEBT["goto"][0].replace("Walk", "Stroll").replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        check("a renamed body is no new body", [f[1] for f in judge("HEAD")] == [
            "rose in a body that is not new: goto src/walk.c Stroll (in the place of 1 body(ies) that left): 1 -> 2"], judge("HEAD"))
        (repo / "src" / "far.c").write_text(C_DEBT["goto"][0].replace("Walk", "Stroll").replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        walk.write_text("s32 g_Walk;\n")
        _git(repo, "add", "src/far.c")
        check("a body renamed and moved at once is no new body", [f[1] for f in judge("HEAD")] == [
            "rose in a body that is not new: goto src/far.c Stroll (in the place of 1 body(ies) that left): 1 -> 2"], judge("HEAD"))
        (repo / "src" / "far.c").write_text(C_DEBT["goto"][0].replace("s32 n", "s32 n, s32 pad").replace("Walk", "Stroll"))
        check("a body renamed with its text as it was is the body it was", not judge("HEAD"), judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0])
        (repo / "src" / "far.c").write_text(C_DEBT["goto"][0].replace("Walk", "Carved"))
        check("a body in a new file is new: a function carved out of an assembly segment", not judge("HEAD"), judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0] + C_DEBT["goto"][0].replace("Walk", "Carved"))
        _git(repo, "rm", "-q", "-f", "--cached", "src/far.c")
        (repo / "src" / "far.c").unlink()
        check("the same body in a file that exists takes no stub away", len(judge("HEAD")) == 1, judge("HEAD"))
        (repo / "src" / "far.c").write_text("s32 g_Far;\n")
        _git(repo, "add", "src/far.c")
        walk.write_text("s32 g_Walk;\n")
        (repo / "src" / "far.c").write_text(C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        _git(repo, "add", "src/far.c")
        check("a moved body is no new body", [f[1] for f in judge("HEAD")] == [
            "rose in a moved body: goto src/far.c Walk (from src/walk.c): 1 -> 2"], judge("HEAD"))
        (repo / "src" / "far.c").write_text(C_DEBT["goto"][0])
        check("a body moved as it was", not judge("HEAD"), judge("HEAD"))
        _git(repo, "rm", "-q", "-f", "--cached", "src/far.c")
        (repo / "src" / "far.c").unlink()
        # a `down` kind never rises, also with a new body; a `raise` line is the developer's
        walk.write_text(C_DEBT["goto"][0] + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
        stub("Jump")
        check("a `down` kind in a new body", [f[1] for f in judge("HEAD")] == [
            "rose in total: pin-unmarked is `down`: 0 -> 1"], judge("HEAD"))
        os.environ["CLAUDECODE"] = "1"
        rc, out = run(raise_=("pin-unmarked", "1"), reason="the trial is pending")
        check("--raise is refused in an agent session", rc == 1 and "the developer's act" in out and base_file.read_text() == text, out)
        del os.environ["CLAUDECODE"]
        rc, out = run(raise_=("pin-unmarked", "0"), reason="x")
        check("--raise needs a number above zero", rc == 1, out)
        rc, out = run(raise_=("pin-unmarked", "1"), reason="the trial\nis pending")
        raised = re.search(r"^raise pin-unmarked 1 \d{4}-\d\d-\d\d the trial is pending$", base_file.read_text(), re.M)
        check("--raise writes one dated line", rc == 0 and raised is not None, out)
        rc, out = run(update=True)
        check("--update takes what a `raise` line allows, and says so", rc == 0 and "DEBT INFO pin-unmarked is over by 1: the "
              "change's `raise` line(s) allow 1\n" in out and "DEBT INFO a new `raise` line: pin-unmarked 1 " in out, out)
        _git(repo, "add", "-u")
        _commit(repo, "a raise")
        walk.write_text(walk.read_text() + C_DEBT["pin-unmarked"][0].replace("Walk", "Jump"))
        stub()
        check("a `raise` line admits one change, not the next", len(judge("HEAD")) == 1, judge("HEAD"))
        stub("Jump")
        walk.write_text(C_DEBT["goto"][0] + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
        # the policy that judges a change is the one it starts from
        mine = base_file.read_text()
        for name, text2, want in (
                ("a policy line taken out", mine.replace("mode pin-unmarked down\n", ""), "the policy line of pin-unmarked is gone (it was down)"),
                ("a weaker mode", mine.replace("mode pin-unmarked down", "mode pin-unmarked admit-new"),
                 "pin-unmarked went from down to admit-new: a mode only gets stronger"),
                ("a budget in the place of `down`", mine.replace("mode asm down", "budget asm 5 base 1 3 0"),
                 "asm went from down to budget: a mode only gets stronger"),
                ("a higher budget", mine.replace("budget goto 12 ", "budget goto 50 "), "the budget of goto went from 12 to 50"),
                ("a moved anchor", mine.replace("budget goto 12 base 1 2 2", "budget goto 12 base 9 2 9"),
                 "the anchor of the goto budget changed (base 9 2 9, was 1 2 2)"),
                ("a new skip line", mine.replace("skip include/", "skip src/\nskip include/"), "a new `skip` line (src/)")):
            base_file.write_text(text2)
            got = judge("HEAD")
            check("policy: " + name, ("policy", want) in got, got)
        base_file.unlink()
        check("policy: a deleted baseline", judge("HEAD") == [("policy", "config/debt-baseline.txt is gone")], judge("HEAD"))
        base_file.write_text(mine.replace("mode offset admit-new", "mode offset down").replace("budget goto 12 ", "budget goto 6 "))
        check("policy: a stronger mode and a lower budget pass", not judge("HEAD"), judge("HEAD"))
        base_file.write_text(mine)
        rc, out = run(down="goto")
        check("--down switches one kind, a budget too", rc == 0 and "mode goto down\n" in base_file.read_text()
              and "budget goto" not in base_file.read_text() and "budget pin 30" in base_file.read_text(), out)
        rc, out = run(down="all")
        check("--down switches every kind", rc == 0 and parse_baseline(base_file.read_text()).summary() == "down: " + ", ".join(KINDS), out)
        check("--down of a kind that is no kind", run(down="gotos")[0] == 1)
        base_file.write_text(mine)
        # the budget: a new body is one that takes a stub away
        stubs = "".join('INCLUDE_ASM("asm/nonmatchings/a", func_8001%04X);\n' % i for i in range(10))
        body = lambda i, n=1: "void func_8001%04X(void) {\nx:\n%s}\n" % (i, "    goto x; // !FAKE: the loop\n" * n)  # noqa: E731
        (repo / "src" / "many.c").write_text(stubs)
        _git(repo, "add", "-A", "src")
        walk.write_text(C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        rc, out = run(recount=True)
        check("--recount admits nothing", rc == 1 and "a recount admits nothing" in out and base_file.read_text() == mine, out)
        walk.write_text(C_DEBT["goto"][0])
        base_file.write_text("mode admit\nskip include/include_asm.h\n1 asm src/boot.s\n# a note of the game\n")
        _git(repo, "add", "-A")
        _commit(repo, "ten stubs, and the baseline of an older psxdecomp")
        rc, out = run()
        check("a version 1 baseline fails and names the command", rc == 1 and "is a version 1 file (`mode admit`): run "
              "`python3 tools/psxd_floor.py debt --recount`" in out, out)
        rc, out = run(recount=True)
        new = base_file.read_text()
        check("--recount makes it version 2 and keeps the game's own lines", rc == 0 and "# a note of the game\n" in new
              and "budget goto 12 base 1 2 11\n" in new and "skip include/include_asm.h\n" in new and "mode admit\n" not in new
              and new.count("# ") == len(BASELINE_HEAD) + 1 and run()[0] == 0, out + new)
        _git(repo, "add", "-A")
        _commit(repo, "version 2")
        (repo / "src" / "many.c").write_text("".join(body(i) for i in range(10)))
        got = judge("HEAD")
        check("the budget: ten new bodies and ten gotos", len(got) == 1 and "over its budget: goto is 11, the budget allows 5 "
              "(12 for each 100 new bodies, 10 new since the anchor of 1, plus 2)" in got[0][1], got)
        (repo / "src" / "many.c").write_text("".join(body(i, int(i < 4)) for i in range(10)))
        check("the budget: ten new bodies and four gotos", not judge("HEAD"), judge("HEAD"))
        (repo / "src" / "many.c").write_text(stubs + "".join(body(i + 16, int(i < 4)) for i in range(10)))
        got = judge("HEAD")
        check("a body beside its stub is no new body", any(f[1].startswith("rose in a body that is not new: goto src/many.c") for f in got)
              and not any("over its budget" in f[1] for f in got), got)
        # one body, taken out in one commit and put back worse in the next: each commit passes, the range does not
        (repo / "src" / "many.c").write_text(stubs)
        walk.write_text('INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
        run(update=True)
        _git(repo, "add", "-A")
        _commit(repo, "the body leaves")
        walk.write_text(C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
        rc, out = run(update=True)
        _git(repo, "add", "-A")
        _commit(repo, "the body is back, worse")
        check("a body that left and came back worse: each commit is admitted", rc == 0 and not judge("HEAD~1", "HEAD")
              and not judge("HEAD~2", "HEAD~1"), out)
        check("and the range is refused", [f[1] for f in judge("HEAD~2", "HEAD")] == [
            "rose in an existing body: goto src/walk.c Walk: 1 -> 2"], judge("HEAD~2", "HEAD"))
        # version 1 in `mode down`: every kind is `down`
        base_file.write_text("mode down\n2 goto src/walk.c\n1 asm src/boot.s\n")
        _git(repo, "add", "-A")
        _commit(repo, "an older baseline in mode down")
        rc, out = run(recount=True)
        check("--recount after `mode down`: every kind is `down`", rc == 0 and parse_baseline(base_file.read_text()).summary()
              == "down: " + ", ".join(KINDS), out)
        base_file.write_text("mode admit\n2 goto src/walk.c\n1 asm src/boot.s\n")
        check("policy: `mode down` of version 1 does not become `mode admit`", ("policy", "`mode down` became `mode admit`") in judge("HEAD"))
        base_file.write_text("mode down\n2 goto src/walk.c\n1 asm src/boot.s\n")
        # the public tree of a game in split mode holds the rows of the files it does not publish
        run(recount=True)
        base_file.write_text(base_file.read_text() + "3 offset src/private.c\n")
        rc, out = run()
        check("a row of a file that is gone is stale", rc == 1 and "DEBT FAIL stale offset src/private.c: 0, its row is 3" in out, out)
        (repo / PUBLIC_PATHS).write_text("# the list\nsrc/walk.c\nsrc/boot.s\ninclude/\nconfig/\n")
        _git(repo, "add", PUBLIC_PATHS)
        check("and not where the public list does not name it", run()[0] == 0, run()[1])
        (repo / PUBLIC_PATHS).write_text("src/\ninclude/\nconfig/\n")
        check("a listed file that is gone is stale", run()[0] == 1)
        _git(repo, "rm", "-q", "-f", "--cached", PUBLIC_PATHS)
        (repo / PUBLIC_PATHS).unlink()
        run(recount=True)
        walk.write_text(C_CLEAN.replace("Player_Hp", "Walk"))
        rc, out = run()
        check("a stale row fails", rc == 1 and "DEBT FAIL stale goto src/walk.c: 0, its row is 2\n" in out, out)
        rc, out = run(down="goto")
        check("--down needs an equal baseline", rc == 1 and "not equal" in out, out)
        rc, out = run(update=True)
        check("--update lowers a row", rc == 0 and "DEBT INFO goto src/walk.c: 2 -> 0\n" in out and
              "goto src/walk.c" not in base_file.read_text(), out)
        (repo / "src" / "walk.c").write_text(C_CLEAN)
        (repo / "src" / "untracked.c").write_text(C_DEBT["goto"][0])        # never added: a count reads tracked files
        check("an untracked file under src/ is not counted", not any(p == "src/untracked.c" for _, p in debt_counts(repo)))
        (repo / "src" / "boot.s").write_text("glabel boot\n    nop\n")
        (repo / "docs").mkdir()
        (repo / "docs" / "boot.md").write_text("# The boot code\n\nThe vendor wrote it in assembly.\n")
        _git(repo, "add", "docs")
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\thand-asm\tdocs/boot.md:3\t2026-01-02\tdeveloper\n")
        rc, out = run()
        check("an evidence row clears an assembly file", rc == 1 and "DEBT FAIL stale asm src/boot.s: 0, its row is 1" in out, out)
        (repo / BASELINE).write_text("mode sideways\n")
        rc, out = run()
        check("a baseline line that is no row", rc == 1 and "config/debt-baseline.txt:1: not " in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n")
        rc, out = _capture(cmd_names, repo)
        check("names: a baseline that does not parse is said, not raised", rc == 0 and "NAMES INFO config/debt-baseline.txt:1" in out, out)
        (repo / NAMES).unlink()
        # the record's address header is read without tomllib; a run from a folder of the repository finds its root
        (repo / RECORD).write_text('[psxdecomp]\nversion = "0.0.0"\n\n[debt]  # ours\naddress_header = "include/hw.h"\n')
        check("the record's address header", address_header(repo) == "include/hw.h" and address_header(repo / "src") == ADDRESS_HEADER)
        (repo / RECORD).unlink()
        (repo / BASELINE).unlink()
        (repo / BASELINE).write_text(first_baseline(repo))
        cwd = os.getcwd()
        try:
            os.chdir(repo / "src")
            rc, out = _capture(main, ["debt"])
        finally:
            os.chdir(cwd)
        check("a run from a folder of the repository reads the repository", rc == 0 and "DEBT CHECK OK (0 rise(s)" in out
              and not (repo / "src" / "config").exists(), out)
        # the ledgers
        (repo / BASELINE).unlink()
        (repo / ASM_EVIDENCE).unlink()
        rc, out = _capture(cmd_names, repo)
        check("names: no ledger is not a failure", rc == 0 and out.count("NAMES INFO no config/") == 2, out)
        rc, out = _capture(cmd_names, repo, init=True)
        check("names --init writes the two header lines", rc == 0 and (repo / NAMES).read_text() == "\t".join(NAME_COLUMNS) + "\n"
              and (repo / ASM_EVIDENCE).read_text() == "\t".join(ASM_COLUMNS) + "\n", out)
        check("names: every function is unbased at first", "NAMES INFO 2 function(s) defined" in out
              and "`unbased` never rises" in out, out)
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/clean.c:4\tthe string it prints\n"
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row)
        rc, out = _capture(cmd_names, repo)
        check("names: a good row", rc == 0 and "1 row(s): 1 accepted" in out and "NAMES INFO 0 function(s)" in out, out)
        (repo / REFS).write_text("# the library\n" * 10 + '[[ref]]\nname = "manual"\nurl = "https://example.invalid/manual"\n\n[[trap]]\ntopic = "x"\n')
        _git(repo, "add", REFS)
        (repo / NAMES).write_text("﻿" + "\t".join(NAME_COLUMNS) + "\n" + row.replace("accepted", "provisional")
                                  .replace("string:src/clean.c:4\tthe string it prints", "refs:config/refs.toml:12"))
        rc, out = _capture(cmd_names, repo)
        check("names: a provisional name is not based; a refs row is evidence; a trimmed last cell and a BOM are read",
              rc == 0 and "1 provisional" in out and "NAMES INFO 2 function(s)" in out, out)
        many = "".join("function\tmain\t\tfunc_%08X\tName%d\tprovisional\tstring:src/clean.c:1\tr\n" % (i, i) for i in range(20000))
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + many + many[:70])
        import time
        t0 = time.time()
        found = names_findings(repo)
        check("names: two live rows of one name, and 20,000 rows in a second", time.time() - t0 < 2.0
              and [f[1] for f in found if f[0] == "FAIL"] == ["config/names.tsv: Name0 has two rows that are not rejected"],
              [f for f in found if f[0] == "FAIL"][:2])
        # a row points at something: a file and a line of the tree, a name that the source defines as the row's kind
        (repo / "include" / "types.h").write_text("#define HP_MAX 9\ntypedef struct Pair {\n    s32 first;\n} Pair;\nextern s32 g_Mode;\n")
        _git(repo, "add", "include/types.h")
        good = "".join("%s\tmain\t\t\t%s\taccepted\t%s\tr\n" % c for c in (
            ("function", "Player_Hp", "string:src/clean.c:4"), ("type", "Pair", "xref:include/types.h:2"),
            ("field", "first", "xref:include/types.h:3"), ("macro", "HP_MAX", "refs:refs/manual/items.txt:40"),
            ("data", "g_Mode", "loadmap:extracted/map.txt:7"), ("file", "src/clean.c", "refs:config/refs.toml:11")))
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + good)
        rc, out = _capture(cmd_names, repo)
        check("names: an accepted row of each kind, with evidence that the tree holds", rc == 0 and "6 accepted" in out, out)
        for name, cells, want in (
                ("evidence in a file that the tree lacks", ("function", "Player_Hp", "string:src/gone.c:4"), "src/gone.c is no file of this tree"),
                ("evidence at a line that the file lacks", ("function", "Player_Hp", "string:src/clean.c:99"), "src/clean.c has no line 99"),
                ("a refs row that cites no table", ("function", "Player_Hp", "refs:config/refs.toml:3"), "line 3 of config/refs.toml is in no `[[ref]]` table"),
                ("a refs row that cites another file", ("function", "Player_Hp", "refs:src/clean.c:1"), "a `refs` row cites config/refs.toml"),
                ("a file of a reference that has no row", ("function", "Player_Hp", "string:refs/wiki/a.txt:1"), "no `[[ref]]` table named 'wiki'"),
                ("a row of the wrong kind", ("data", "Player_Hp", "string:src/clean.c:4"), "Player_Hp is a function in the source, not a data"),
                ("a name that the source does not define", ("function", "Player_Mp", "string:src/clean.c:4"),
                 "Player_Mp is accepted as a function, and the source defines no such function"),
                ("a file that the tree lacks", ("file", "src/gone.c", "string:src/clean.c:4"), "src/gone.c is accepted as a file")):
            (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + "%s\tmain\t\t\t%s\taccepted\t%s\tr\n" % cells)
            rc, out = _capture(cmd_names, repo)
            check("names: " + name, rc == 1 and want in out and "NAMES FAIL (1 finding(s))" in out, out)
        _git(repo, "add", "config", "include")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet",
             "-m", "a row that points at nothing")
        rc, out = _capture(cmd_names, repo, against="HEAD")
        check("names --against: a row that the base holds is not opened again", rc == 0 and "only the rows that are new since HEAD" in out, out)
        check("names --rev: the ledger of a revision", _capture(cmd_names, repo, source="HEAD")[0] == 1)
        (repo / "extracted").mkdir()                   # an ignored folder that this machine has: its files are opened
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + good)
        rc, out = _capture(cmd_names, repo)
        check("names: evidence in a folder that git does not hold is opened where the folder is", rc == 1
              and "extracted/map.txt is no file of this tree" in out, out)
        (repo / "extracted" / "map.txt").write_text("x\n" * 7)
        check("names: and it passes when the file is there", _capture(cmd_names, repo)[0] == 0)
        # an assembly row names one function of a C file, never the file
        two = 'void A(void) {\n    __asm__("nop");\n}\nvoid B(void) {\n    __asm__("nop");\n}\n'
        (repo / "src" / "two.c").write_text(two)
        _git(repo, "add", "src/two.c")
        asm_row = lambda sym, ev="docs/boot.md:3", who="developer": "\t".join(ASM_COLUMNS) + "\nmain\t%s\tsrc/two.c\thand-asm\t%s\t2026-01-02\t%s\n" % (sym, ev, who)  # noqa: E731
        (repo / ASM_EVIDENCE).write_text(asm_row("A"))
        check("an assembly row clears the function it names, and no other", _capture(cmd_names, repo)[0] == 0
              and debt_bodies(repo)["src/two.c"] == {"A": {"unbased": 1}, "B": {"asm": 1, "unbased": 1}}, debt_bodies(repo)["src/two.c"])
        for name, text, want in (("a row for a whole C file", asm_row(""), "src/two.c defines no function ''"),
                                 ("a row for a function that the file lacks", asm_row("C"), "src/two.c defines no function 'C'"),
                                 ("evidence that is no path and line", asm_row("A", "the vendor said so"), "'the vendor said so' is not `<path>:<line>`"),
                                 ("evidence in a file that the tree lacks", asm_row("A", "docs/gone.md:1"), "docs/gone.md is no file of this tree"),
                                 ("no verified_by", asm_row("A", who=""), "no verified_by: who read the evidence of A"),
                                 ("a label that the assembly file lacks", asm_row("start").replace("src/two.c", "src/boot.s"), "src/boot.s holds no label start")):
            (repo / ASM_EVIDENCE).write_text(text)
            rc, out = _capture(cmd_names, repo)
            check("names: an assembly row: " + name, rc == 1 and want in out, out)
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS_OLD) + "\nmain\tA\tsrc/two.c\thand-asm\tdocs/boot.md:3\t2026-01-02\n")
        rc, out = _capture(cmd_names, repo)
        check("names: the header of psxdecomp 0.6.0 is read, and said", rc == 0 and "no `verified_by` column (/psxdecomp:upgrade adds it)" in out, out)
        (repo / "src" / "two.c").unlink()
        _git(repo, "rm", "-q", "--cached", "src/two.c")
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\n")
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/clean.c:4\tthe string it prints\n"
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("accepted", "sure").replace("string:", "guess:"))
        rc, out = _capture(cmd_names, repo)
        check("names: a bad decision and a bad evidence class", rc == 1 and "decision 'sure'" in out and "evidence 'guess:" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("string:src/clean.c:4", "string:"))
        rc, out = _capture(cmd_names, repo)
        check("names: evidence with no path and no line", rc == 1 and "evidence 'string:'" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("accepted", "rejected"))
        rc, out = _capture(cmd_names, repo)
        check("names: a rejected row bases no name", rc == 0 and "NAMES INFO 2 function(s)" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row)
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\tguess\tdocs/boot.md:3\tyesterday\tdeveloper\n")
        rc, out = _capture(cmd_names, repo)
        check("names: an assembly row with a class that is no class and a date that is no date",
              rc == 1 and "class 'guess'" in out and "date 'yesterday'" in out, out)
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\n")
        (repo / NAMES).write_text("kind\tname\n")
        check("names: a wrong header", _capture(cmd_names, repo)[0] == 1)


C_BODIES = {
    "two plain bodies": ("s32 A(void *p) {\n    return *(s32 *)(p + 4);\n}\n\nvoid B(void) {\nx:\n    goto x; // !FAKE: the loop\n}\n",
                         {"A": {"offset": 1}, "B": {"goto": 1}}),
    "a K&R definition is file scope": ("s32 A(p)\nvoid *p;\n{\n    return *(s32 *)(p + 4);\n}\nvoid B(void) {\n}\n",
                                        {SCOPE: {"offset": 1, "obscured": 1}, "B": {}}),
    "a definition by a macro is file scope": ("HANDLER(A) {\nx:\n    goto x; // !FAKE: the loop\n}\nvoid B(void) {\n}\n",
                                               {SCOPE: {"goto": 1, "obscured": 1}, "B": {}}),
    "an #if with two heads is one body": ("#ifdef VERSION_JP\ns32 A(s32 a) {\n#else\ns32 A(void) {\n#endif\nx:\n"
                                          "    goto x; // !FAKE: the loop\n}\nvoid B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "an `else if` in column 0 opens no body": ("void A(s32 a) {\n    if (a) {\n    }\nelse if (a == 2) {\nx:\n    goto x; // !FAKE: the loop\n"
                                               "    }\n}\n", {"A": {"goto": 1}}),
    "a body beside its stub": ("#ifndef NON_MATCHING\nINCLUDE_ASM(\"asm/nonmatchings/a\", func_80012344);\n#else\n"
                               "s32 func_80012344(s32 a) {\nx:\n    goto x; // !FAKE: the loop\n}\n#endif\n", {"func_80012344": {"goto": 1, "placeholder": 1}}),
    "braces that never close end at the next definition": (
        "void A(s32 a) {\n#ifdef X\n    if (a) {\n#else\n    if (!a) {\n#endif\nx:\n        goto x; // !FAKE: the loop\n    }\n}\n"
        "void B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "two bodies of one name are one entry": ("void A(void) {\nx:\n    goto x; // !FAKE: the loop\n}\nstruct S {\n    s32 a;\n};\n"
                                             "void A(s32 b) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 2}, SCOPE: {"struct": 1}}),
    "data, a macro and a struct are file scope": ("#define SWAP(a, b) { a = b; }\ns32 D_800A1234 = 4;\nstruct S {\n    s32 a;\n};\n",
                                                  {SCOPE: {"macro": 1, "placeholder": 1, "struct": 1}}),
}


def self_test_bodies(check) -> None:
    for name, (text, want) in C_BODIES.items():
        got = file_bodies("src/a.c", text)
        check("bodies: " + name, got == want, got)
    stubs = scan_file("src/a.c", C_BODIES["a body beside its stub"][0])["stubs"]
    check("bodies: the stub lines of a file are counted", stubs == 1, stubs)
    for name, text in [(k, t) for k, (t, _) in C_DEBT.items()] + [(k, t) for k, (t, _) in C_BODIES.items()] + [("clean", C_CLEAN)]:
        for rel, based in (("src/a.c", None), ("src/a.c", set()), ("include/a.h", None)):
            total: dict[str, int] = {}
            for got in file_bodies(rel, text, based=based).values():
                for kind, n in got.items():
                    total[kind] = total.get(kind, 0) + n
            check("bodies: the sum of a file's bodies is its count: %s (%s)" % (name, rel), total == file_debt(rel, text, based=based), total)
    check("bodies: an unbased name counts in its own body", file_bodies("src/a.c", C_BODIES["two plain bodies"][0], based={"A"})
          == {"A": {"offset": 1}, "B": {"goto": 1, "unbased": 1}})
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        for rel in ("src/one.c", "src/two.c"):         # one name in two files: two bodies
            (repo / rel).write_text("static void Step(void) {\nx:\n    goto x; // !FAKE: the loop\n}\n")
        (repo / "src" / "boot.s").write_text("nop\n")
        _git(repo, "add", "src")
        got = debt_bodies(repo)
        check("bodies: one name in two files is two bodies; an assembly file is file scope", got == {
            "src/one.c": {"Step": {"goto": 1}}, "src/two.c": {"Step": {"goto": 1}}, "src/boot.s": {SCOPE: {"asm": 1}}}, got)
        (repo / "src" / "half.c").write_text('INCLUDE_ASM("asm/nonmatchings/half", Later);\nvoid Now(void) {\n}\n')
        (repo / "src" / "done.c").write_text("void Done(void) {\n}\n")
        (repo / "src" / "table.c").write_text("s32 g_Table[4];\n")
        _git(repo, "add", "src")
        rc, out = _capture(cmd_files, repo)
        check("debt --files: no file is finished before the names ledger exists", rc == 0 and "DEBT FILE matched  src/done.c\n" in out
              and "DEBT FILE stubs    src/half.c\n" in out and "DEBT FILE matched  src/one.c: goto 1\n" in out and "table.c" not in out
              and "DEBT FILES 4 C file(s): 0 finished, 3 matched, 1 with stubs (no config/names.tsv yet" in out, out)
        (repo / "config").mkdir()
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\nfunction\tmain\t\t\tDone\taccepted\tstring:src/done.c:1\tr\n")
        rc, out = _capture(cmd_files, repo)
        check("debt --files: a file with no debt of any kind is finished", "DEBT FILE finished src/done.c\n" in out
              and "DEBT FILE matched  src/one.c: goto 1, unbased 1\n" in out
              and out.endswith("DEBT FILES 4 C file(s): 1 finished, 2 matched, 1 with stubs\n"), out)
        (repo / PUBLIC_PATHS).write_text("src/one.c\nsrc/half.c\n")
        _git(repo, "add", "config")
        rc, out = _capture(cmd_files, repo, public=True)
        check("debt --files --public: the files that the repository publishes, as its public tree counts them", out.endswith(
            "DEBT FILES 2 C file(s): 0 finished, 1 matched, 1 with stubs (no config/names.tsv yet: no file is finished before each "
            "name has a row)\n") and "src/one.c: goto 1\n" in out, out)
        _git(repo, "rm", "-q", "-f", "--cached", PUBLIC_PATHS)
        (repo / PUBLIC_PATHS).unlink()
        (repo / NAMES).unlink()
        for name in ("half.c", "done.c", "table.c"):
            (repo / "src" / name).unlink()
        _git(repo, "add", "-A", "src")
        rc, out = _capture(cmd_bodies, repo)
        check("debt --bodies prints each bucket", rc == 0 and "DEBT BODY src/one.c Step: goto 1\n" in out
              and "DEBT BODY src/boot.s (file scope): asm 1\n" in out
              and "DEBT BODIES 3 file(s), 2 function bodies, 2 with debt, 1 count(s) at file scope; totals: goto 2, asm 1\n" in out, out)


def self_test_files(check) -> None:
    """Which files count, and the kinds that a file's text alone does not decide."""
    for path, want in (("src/a.c", True), ("include/a.h", True), ("lib/libgte/a.c", True), ("Src/A.C", True), ("game/a.cpp", True),
                       ("src/body.inc", True), ("src/boot.S", True), ("src/boot.asm", True), ("asm/main/a.s", False),
                       ("tools/host.c", False), ("build/a.c", False), ("refs/x/a.c", False), (".run/a.c", False),
                       ("src/.cache/a.c", False), ("docs/a.md", False), ("src/a.txt", False)):
        check("a counted file: %s" % path, is_source(path) == want)
    plumbing = '__asm__(".include \\"macro.inc\\"\\n");\n__asm__(".macro glabel label\\n.global \\\\label\\n\\\\label:\\n.endm\\n");\n'
    check("a header's assembler directives are the stub's plumbing", file_debt("include/include_asm.h", plumbing) == {}, file_debt("include/include_asm.h", plumbing))
    check("an instruction in a header's asm statement is assembly", file_debt("include/fast.h", '__asm__(".text\\nFast:\\n    jr $ra\\n nop\\n");\n') == {"asm": 1})
    check("the same statements in a C file are assembly", file_debt("src/a.c", plumbing) == {"asm": 2})
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        unmarked = C_DEBT["goto-unmarked"][0]
        for rel in ("src/walk.c", "lib/walk.c", "asm/walk.c", "tools/walk.c", "src/func_80012344.c", "src/misc12.c"):
            put(rel, unmarked.replace("Walk", "W_" + re.sub(r"\W", "_", rel)))
        put("src/body.inc", "loop:\n    if (--n) goto loop;\n    return n;\n")
        put("src/hand.asm", "nop\n")
        os.symlink("walk.c", repo / "src" / "link.c")
        _git(repo, "add", "-A")
        got = debt_bodies(repo)
        check("code in any folder counts; the splitter's and the tools' folders do not", sorted(got) == [
            "lib/walk.c", "src/body.inc", "src/func_80012344.c", "src/hand.asm", "src/link.c", "src/misc12.c", "src/walk.c"], sorted(got))
        check("the code of a fragment is counted in its own file", got["src/body.inc"] == {
            SCOPE: {"goto": 1, "goto-unmarked": 1}}, got["src/body.inc"])
        check("a file named by an address or a number", got["src/func_80012344.c"][SCOPE] == {"filename": 1}
              and got["src/misc12.c"][SCOPE] == {"filename": 1} and SCOPE not in got["src/walk.c"], got["src/misc12.c"])
        check("an assembly file by another suffix; a source behind a symbolic link", got["src/hand.asm"] == {SCOPE: {"asm": 1}}
              and got["src/link.c"] == {SCOPE: {"obscured": 1}}, (got["src/hand.asm"], got["src/link.c"]))
        put("drafts/walk.c", unmarked)
        put("src/user.c", 'void User(s32 n) {\n#include "../drafts/walk.c"\n}\n')
        _git(repo, "add", "-A")
        got = debt_bodies(repo)
        check("an include of code that the count does not read", "drafts/walk.c" not in got and got["src/user.c"] == {
            "User": {}, SCOPE: {"obscured": 1}}, got["src/user.c"])
        (repo / "src" / "user.c").unlink()
        _git(repo, "add", "-A")
        got = debt_bodies(repo)
        _commit(repo, "the tree")
        check("a revision holds the same files and the same link", debt_bodies(repo, tree=Tree(repo, "HEAD")) == got
              and debt_bodies(repo, tree=Tree(repo, INDEX)) == got)
        # the two kinds that the game counts: its lister for the work tree, its rows for a revision
        put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[debt]\nflags = '%s tools/flags.py'\n" % sys.executable)
        put("tools/flags.py", "print('2 reservation src/walk.c')\nprint('1 flag src/walk.c')\nprint('0 flag lib/walk.c')\nprint('a line that is no row')\n")
        got = debt_bodies(repo)["src/walk.c"]
        check("the game's lister gives the flags and the reservations", got[SCOPE] == {"reservation": 2, "flag": 1}, got)
        put(BASELINE, first_baseline(repo))
        _git(repo, "add", "-A")
        _commit(repo, "the lister and its rows")
        check("a revision's flags are the rows of its baseline", debt_bodies(repo, tree=Tree(repo, "HEAD"))["src/walk.c"][SCOPE]
              == {"reservation": 2, "flag": 1} and admission(repo, Tree(repo, "HEAD"), Tree(repo))[0] == [])
        put("tools/flags.py", "print('3 reservation src/walk.c')\n")
        got = admission(repo, Tree(repo, "HEAD"), Tree(repo))[0]
        check("a reservation never rises", got == [("debt", "rose outside a function with no new body: reservation src/walk.c (file "
                                                     "scope): 2 -> 3")], got)
        put("tools/flags.py", "import sys\nsys.exit(4)\n")
        try:
            debt_bodies(repo)
            check("a lister that fails is a refusal", False)
        except Fail as e:
            check("a lister that fails is a refusal", "exited 4" in str(e), str(e))
        # a fragment is the body of the functions that include it
        put("tools/flags.py", "print('2 reservation src/walk.c')\nprint('1 flag src/walk.c')\n")
        frag = "    s32 v = *(s32 *)(obj + 4);\n    if (v) {\n        return v;\n    }\n    return 0;\n"
        put("src/shared/body.inc.c", frag)
        put("src/unit.c", 'INCLUDE_ASM("asm/nonmatchings/unit", One);\nINCLUDE_ASM("asm/nonmatchings/unit", Two);\n')
        _git(repo, "add", "-A")
        _commit(repo, "two stubs")
        judge = lambda: admission(repo, Tree(repo, "HEAD"), Tree(repo, None, untracked=True))[0]  # noqa: E731
        put("src/unit.c", 's32 One(u8 *obj) {\n#include "shared/body.inc.c"\n}\nINCLUDE_ASM("asm/nonmatchings/unit", Two);\n')
        put("src/shared/body.inc.c", frag)
        check("a fragment's statements are no hidden code", "obscured" not in debt_bodies(repo, tree=Tree(repo, None, untracked=True))["src/shared/body.inc.c"][SCOPE])
        check("a new body may bring its fragment", judge() == [], judge())
        _git(repo, "add", "-A")
        _commit(repo, "one body and its fragment")
        put("src/shared/body.inc.c", frag.replace("return 0;", "return *(s32 *)(obj + 8);"))
        got = judge()
        check("a fragment of a body that exists never gets worse", got == [("debt", "rose in a fragment of a body that is not new: offset "
              "src/shared/body.inc.c (a fragment that src/unit.c One includes): 1 -> 2")], got)
        put("src/unit.c", 's32 One(u8 *obj) {\n#include "shared/body.inc.c"\n}\ns32 Two(u8 *obj) {\n#include "shared/body.inc.c"\n}\n')
        check("also when a new body includes it too", len(judge()) == 1, judge())
        put("src/shared/body.inc.c", frag)
        check("a new body may include a fragment as it is", judge() == [], judge())
        # a file that takes the bodies of a file that is gone takes what stood beside them
        put("src/pair.c", C_DEBT["goto"][0] + C_DEBT["struct"][0].split("s32 Walk")[0])
        _git(repo, "add", "-A")
        _commit(repo, "a struct beside a body")
        _git(repo, "mv", "src/pair.c", "src/stride.c")
        check("a file that takes bodies of another file takes what stood beside them", judge() == [], judge())
        put("src/stride.c", (repo / "src/stride.c").read_text() + "struct More {\n    s32 a;\n};\n")
        check("and no more than that", judge() == [("debt", "rose outside a function with no new body: struct src/stride.c (file "
                                                    "scope): 1 -> 2")], judge())


def self_test_tree(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        (repo / "src" / "two.c").write_bytes(C_DEBT["macro"][0].replace("\n", "\r\n").encode())
        os.symlink("walk.c", repo / "src" / "link.c")
        _commit(repo, "one")
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0] * 2)
        _git(repo, "add", "src/walk.c")
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0] * 3)
        (repo / "src" / "new.c").write_text(C_DEBT["goto"][0])
        got = [debt_counts(repo, tree=Tree(repo, src)).get(("goto", "src/walk.c")) for src in ("HEAD", INDEX, None)]
        check("tree: a revision, the index and the work tree are three sources", got == [1, 2, 3], got)
        check("tree: CRLF is read as LF, from the disk and from a blob", all(
            debt_counts(repo, tree=Tree(repo, src)).get(("macro", "src/two.c")) == 2 for src in ("HEAD", INDEX, None)))
        check("tree: a symbolic link is no file of the tree", all(
            Tree(repo, src).read("src/link.c") is None for src in ("HEAD", INDEX, None)))
        check("tree: an untracked file counts only when asked for", "src/new.c" not in Tree(repo).paths
              and "src/new.c" in Tree(repo, untracked=True).paths and not Tree(repo, "HEAD").has("src/new.c"))
        try:
            Tree(repo, "no-such-revision")
            check("tree: a revision git cannot read is a refusal", False)
        except Fail:
            pass
        rc, out = _capture(cmd_debt, repo, against="HEAD")
        check("debt --against: the change since a revision is judged", rc == 1 and "DEBT FAIL debt: rose in an existing body: "
              "goto src/walk.c Walk: 1 -> 3\n" in out and "1 finding(s) against HEAD" in out, out)
        rc, out = _capture(cmd_debt, repo, source=INDEX, update=True)
        check("debt --staged takes no --update", rc == 1 and "takes no --staged" in out, out)
    check("the two tools stand side by side", sibling().name == pathlib.Path(__file__).name.replace("floor", "publish"))


C_TRIAL = """#include "common.h"
s32 Sum(s32 *p, s32 n) {
    register s32 i asm("$16");
    register s32 t asm("$17") = 0;
    __asm__("");
    for (i = 0; i < n; i++) {
        t += p[i];
    }
    return t;
}
"""
PROBE_SELF = """import sys
text = open(sys.argv[1]).read()
assert sys.argv[2] and sys.argv[3].endswith(".c"), sys.argv
RULE
"""


def self_test_trials(check) -> None:
    check("markers: a reason is a text", reason_ok("the loop counter") and not reason_ok("") and not reason_ok("-- ?") and not reason_ok(None))
    one = 'void A(void) {\n    // !FAKE: both\n    register s32 a asm("$4");\n    register s32 b asm("$5");\n}\n'
    check("markers: one marker covers one pin", file_debt("src/a.c", one) == {"pin": 2, "pin-unmarked": 1}, file_debt("src/a.c", one))
    tail = 'void A(void) {\n    register s32 a asm("$4"); // !FAKE: the first one\n    register s32 b asm("$5");\n}\n'
    check("markers: a marker behind a pin does not cover the pin below", file_debt("src/a.c", tail) == {"pin": 2, "pin-unmarked": 1})
    bare = 'void A(void) {\n    // !FAKE:\n    register s32 a asm("$4");\n    register s32 b asm("$5"); /* !FAKE: */\n}\n'
    check("markers: a marker with no reason covers nothing", file_debt("src/a.c", bare) == {"pin": 2, "pin-unmarked": 2})
    quoted = 'void A(void) {\n    register s32 a asm("$4"); Log("!FAKE: the first one");\n}\n'
    check("markers: a marker in a string is no marker", file_debt("src/a.c", quoted) == {"pin": 1, "pin-unmarked": 1})
    got = crutches("src/sum.c", C_TRIAL)
    check("crutches: two pins and a barrier of one function", [(c["id"], c["func"], c["line"]) for c in got] == [
        ("pin:$16:i", "Sum", 2), ("pin:$17:t", "Sum", 3), ("barrier:1", "Sum", 4)] and len({c["hash"] for c in got}) == 1, got)
    check("crutches: a pin leaves its declaration, a barrier leaves nothing", drop(C_TRIAL, got[1]).split("\n")[3] == "    s32 t = 0;"
          and '__asm__' not in drop(C_TRIAL, got[2]) and drop(C_TRIAL, got[2]).count("\n") == C_TRIAL.count("\n") - 1)
    check("the hash of a body reads no comment and no space", body_hash("a  b /* c */\n d", [(0, 15)]) == body_hash("a b d", [(0, 5)]))
    check("an asm statement that holds an instruction is no barrier", not crutches("src/a.c", 'void A(void) {\n    __asm__("nop");\n}\n'))
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        rule = lambda body: put("tools/probe.py", PROBE_SELF.replace("RULE", body))  # noqa: E731
        trial = lambda *a, **kw: _capture(cmd_trial, repo, *a, **kw)  # noqa: E731
        found = lambda: trials_findings(repo, Tree(repo, None, untracked=True))  # noqa: E731
        put("src/sum.c", C_TRIAL)
        put(RECORD, '[psxdecomp]\nversion = "0.6.0"\n')
        rc, out = trial("src/sum.c")
        check("trial: no probe is a refusal", rc == 1 and "TRIAL FAIL no [trial] probe in config/psxdecomp.toml" in out, out)
        put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[trial]\nprobe = '%s tools/probe.py'\n" % sys.executable)
        _git(repo, "add", "-A")
        rule("sys.exit(1)")
        rc, out = trial("src/sum.c")
        check("trial: a function that does not match is not tried", rc == 1 and "TRIAL FAIL src/sum.c Sum: it does not match as it is" in out
              and (repo / "src/sum.c").read_text() == C_TRIAL, out)
        rule("sys.exit(1 if 'psxd trial' in text else 0)")
        rc, out = trial("src/sum.c")
        check("trial: the control: a probe that a comment moves", rc == 1 and "the probe gives another answer for a comment" in out, out)
        rule("sys.exit(3 if '$16' not in text else 0)")
        rc, out = trial("src/sum.c")
        check("trial: a probe that fails stops the trial", rc == 1 and "the probe failed (exit 2 or more)" in out
              and (repo / "src/sum.c").read_text() == C_TRIAL and not (repo / TRIALS).exists(), out)
        rule("sys.exit(0 if 'asm(\"$16\")' in text else 1)")
        rc, out = trial("src/sum.c")
        text = (repo / "src/sum.c").read_text()
        check("trial: what the match needs stays, with a reason; the rest is gone", rc == 0 and
              "TRIAL src/sum.c Sum: 3 tried, 2 removed, 1 kept\n" in out and out.endswith("TRIAL OK (1 function(s), 3 tried, 2 removed, "
              "1 kept; 6 probe(s))\n") and text == C_TRIAL.replace('    register s32 t asm("$17") = 0;\n    __asm__("");\n', "    s32 t = 0;\n")
              .replace("    register s32 i", "    // !FAKE: pin:$16:i: the function does not match without it (trial)\n    register s32 i"), out + text)
        rows = (repo / TRIALS).read_text().splitlines()
        check("trial: one row for the survivor", rows[0].split("\t") == list(TRIAL_COLUMNS) and len(rows) == 2 and
              rows[1].split("\t")[:3] == ["src/sum.c", "Sum", "pin:$16:i"] and rows[1].split("\t")[4] == "kept"
              and re.fullmatch(r"[0-9a-f]{16}\t[a-z]+\t[0-9a-f]{16}", "\t".join(rows[1].split("\t")[3:])), rows)
        check("trial: no file is left beside the source", sorted(x.name for x in (repo / "src").iterdir()) == ["sum.c"])
        check("the gate's view: a marked pin with its row", found() == [] and file_debt("src/sum.c", text) == {"pin": 1}, found())
        check("trial: a second run changes nothing", trial("src/sum.c")[0] == 0 and (repo / "src/sum.c").read_text() == text
              and (repo / TRIALS).read_text().splitlines() == rows)
        put("src/sum.c", text.replace("t += p[i];", "t += p[i] + 1;"))
        check("trials: a body that changed since its trial", len(found()) == 1 and found()[0].startswith(
            "stale: src/sum.c Sum pin:$16:i: the body changed since its trial"), found())
        put("src/sum.c", text.replace("for (i = 0;", "/* the sum */\n    for (i = 0;"))
        check("trials: a comment changes no hash", found() == [], found())
        (repo / "src/sum.c").rename(repo / "src/total.c")
        check("trials: a function that moved keeps its row", found() == [], found())
        (repo / "src/total.c").rename(repo / "src/sum.c")
        put("src/sum.c", text)
        put(TRIALS, "\t".join(TRIAL_COLUMNS) + "\n")
        check("trials: a marked pin with no row", len(found()) == 1 and found()[0].startswith("no row: src/sum.c Sum pin:$16:i has a "
              "marker and no row in config/trials.tsv: run `python3 tools/psxd_floor.py trial src/sum.c --func Sum`"), found())
        put("src/sum.c", text.replace("// !FAKE: pin:$16:i: the function does not match without it (trial)", "// !FAKE:"))
        check("trials: a marker with no reason", [f[:40] for f in found()] == ["no reason: src/sum.c Sum pin:$16:i: a `/"]
              and file_debt("src/sum.c", (repo / "src/sum.c").read_text()) == {"pin": 1, "pin-unmarked": 1}, found())
        rc, out = trial("src/sum.c", "Sum")
        check("trial --func writes the reason and the row again", rc == 0 and (repo / "src/sum.c").read_text() == text and found() == [], out)
        put(RECORD, '[psxdecomp]\nversion = "0.6.0"\n')
        check("trials: a marked pin and no probe", found() == ["no [trial] probe in config/psxdecomp.toml: a game cannot keep a "
                                                               "crutch that it cannot examine"], found())
        put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[trial]\nprobe = '%s tools/probe.py {file} {func} {path}'\n" % sys.executable)
        put(TRIALS, "\t".join(TRIAL_COLUMNS) + "\n")
        check("trial: the command may name its three values", trial("src/sum.c")[0] == 0 and found() == [])
        # a row that says `kept` for a pin the function matches without: written by hand, found by the second trial
        _git(repo, "add", "-A")
        _commit(repo, "one honest row")
        forged = text.replace("    s32 t = 0;", "    // !FAKE: the accumulator must be in $17\n    register s32 t asm(\"$17\") = 0;")
        put("src/sum.c", forged)
        c = [c for c in crutches("src/sum.c", forged) if c["id"] == "pin:$17:t"][0]
        put(TRIALS, "\t".join(TRIAL_COLUMNS) + "\n" + "".join("src/sum.c\tSum\t%s\t%s\tkept\t%s\n" % (
            x["id"], x["hash"], "0" * 16) for x in crutches("src/sum.c", forged)))
        check("a forged row passes the record check", found() == [] and c["reason"] == "the accumulator must be in $17", found())
        rc, out = trial(None, recheck=True, against="HEAD", sample=0)
        check("trial --recheck finds the forged row", rc == 1 and "TRIAL FAIL removable: src/sum.c Sum pin:$17:t: the row says `kept`, "
              "and the function matches without it\n" in out and "TRIAL RECHECK FAIL (2 row(s) run again: 2 new since HEAD, 0 of the "
              "0 others; 1 finding(s))" in out, out)
        _git(repo, "checkout", "--", "src/sum.c", TRIALS)
        base_copy = repo / ".psxd-trials-base.tsv"   # a build with no git gets the base's rows as a file
        base_copy.write_text(_git(repo, "show", "HEAD:" + TRIALS).stdout)
        put(TRIALS, (repo / TRIALS).read_text() + "src/sum.c\tSum\tpin:$17:t\t%s\tkept\t%s\n" % ("0" * 16, "0" * 16))
        rc, out = trial(None, recheck=True, sample=0, base_rows=str(base_copy))
        check("trial --recheck --base-rows: the rows that the copy of the base does not hold", rc == 0 and "1 new since" in out
              and "the source holds no such crutch" in out, out)
        base_copy.unlink()
        _git(repo, "checkout", "--", TRIALS)
        rc, out = trial(None, recheck=True, against="HEAD")
        check("trial --recheck: an honest row holds", rc == 0 and "TRIAL RECHECK OK (1 row(s) run again: 0 new since HEAD, 1 of the 1 others" in out, out)
        # a crutch that needs another one: the second pass
        put("src/sum.c", C_TRIAL)
        rule("sys.exit(0 if ('asm(\"$16\")' in text or 'asm(\"$17\")' not in text) else 1)")
        rc, out = trial("src/sum.c")
        check("trial: a pin that only another pin needed goes in the second pass", rc == 0 and "0 kept" in out
              and "asm" not in (repo / "src/sum.c").read_text() and (repo / TRIALS).read_text() == "\t".join(TRIAL_COLUMNS) + "\n", out)
        rc, out = trial("src/sum.c")
        check("trial: a file with no crutch", (rc, out) == (0, "TRIAL OK src/sum.c: no pin and no barrier in a function\n"), out)
        check("trial: a file that is not there", trial("src/gone.c")[0] == 1)


GATE_SETTINGS = {"permissions": {"deny": ["Bash(git push *)", "Edit(/config/debt-baseline.txt)"]}, "hooks": {"PreToolUse": [
    {"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/tools/psxd_floor.py" guard --hook'}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "the game's own hook"}]}]}}


def self_test_gate(check) -> None:
    global _sibling_run
    keep = _sibling_run
    if not sibling().is_file():                        # this file alone: the checks of the other tool are not its to test
        _sibling_run = lambda repo, *args: (0, [])  # noqa: E731
    try:
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            gate = lambda mode, rng=None: _capture(cmd_gate, repo, mode, rng)  # noqa: E731
            mine = pathlib.Path(__file__).read_text(encoding="utf-8")
            put("src/walk.c", C_DEBT["goto"][0])
            put(VENDORED, mine)
            put(TOOLS[1], sibling().read_text(encoding="utf-8") if sibling().is_file() else "VERSION = \"0.6.0\"\n")
            put(SETTINGS, json.dumps(GATE_SETTINGS, indent=2) + "\n")
            put(GUARD, "deny\tpath\tasm/\tasm/ is generated\n")
            put(RECORD, '[psxdecomp]\nversion = "0.6.0"\n\n[own]\nnames = "config/names.basis.tsv"\ndebt = "python3 tools/scan.py --all"\n'
                '\n[floor]\ngate = "sh tools/check.sh"\n')
            put("tools/check.sh", 'test -z "$PSXD_SELF_RED" || { echo the build is red; exit 3; }\n')
            put("src/vendor/lib.c", "void Lib(void) {\n}\n")
            put("config/names.basis.tsv", "name\tbasis\nWalk\tthe string it prints\n")
            put("tools/scan.py", "import os, sys\nprint('SCAN %s' % ('FAIL' if os.environ.get('PSXD_SELF_SCAN') else 'OK'))\n"
                "sys.exit(1 if os.environ.get('PSXD_SELF_SCAN') else 0)\n")
            put("src/stubs.c", 'INCLUDE_ASM("asm/nonmatchings/a", Run);\n')
            put(WORKFLOWS + "no-rom.yml", "name: no-rom\n")
            _git(repo, "add", "-A")
            put(BASELINE, first_baseline(repo) + "skip src/vendor/\n")
            _git(repo, "add", "-A")
            rc, out = gate("staged")
            check("gate --staged before the first commit: the tree as it stands", rc == 0 and "no commit yet" in out
                  and out.endswith("GATE OK (staged)\n"), out)
            _commit(repo, "the floor")
            start = _rev(repo, "HEAD")
            rc, out = gate("staged")
            check("gate --staged with nothing staged", (rc, out) == (0, "GATE OK (staged)\n"), out)
            base_text = (repo / BASELINE).read_text()
            staged = lambda: (_git(repo, "add", "-A"), gate("staged"))[1]  # noqa: E731
            undo = lambda: (_git(repo, "reset", "-q", "--hard", "HEAD"), _git(repo, "clean", "-q", "-fd"))  # noqa: E731
            # a symbol dump of another build as text: the commit is refused, a short quote passes
            put("docs/notes/proto-symbols.txt", "".join(SYMDUMP_SELF[i % 4] for i in range(70)))
            rc, out = staged()
            check("gate: a staged symbol dump is refused", rc == 1 and "GATE FAIL symdump: docs/notes/proto-symbols.txt: 70 lines in a "
                  "row have the shape of a PsyQ symbol dump (cap 64)" in out, out)
            put("docs/notes/proto-symbols.txt", "".join(SYMDUMP_SELF[i % 4] for i in range(60)))
            rc, out = staged()
            check("gate: a quote of 60 lines passes", "symdump" not in out, out)
            undo()
            # the baseline: a row written by hand, a policy line taken out, a new skip line
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(BASELINE, base_text.replace("1 goto src/walk.c", "2 goto src/walk.c"))
            rc, out = staged()
            check("gate: a row written by hand admits nothing", rc == 1 and "GATE FAIL debt: rose in an existing body: goto "
                  "src/walk.c Walk: 1 -> 2\n" in out and out.endswith("GATE FAIL (staged; 1 finding(s))\n"), out)
            undo()
            for name, text, want in (("a policy line taken out", base_text.replace("mode pin-unmarked down\n", ""),
                                      "GATE FAIL policy: the policy line of pin-unmarked is gone"),
                                     ("a weaker mode", base_text.replace("mode asm down", "mode asm admit-new"),
                                      "GATE FAIL policy: asm went from down to admit-new"),
                                     ("a new skip line", base_text + "skip src/\n", "GATE FAIL policy: a new `skip` line (src/)")):
                put(BASELINE, text)
                rc, out = staged()
                check("gate: " + name, rc == 1 and want in out, out)
            undo()
            (repo / BASELINE).unlink()
            rc, out = staged()
            check("gate: a deleted baseline", rc == 1 and "GATE FAIL policy: config/debt-baseline.txt is gone" in out
                  and "GATE FAIL debt: no config/debt-baseline.txt" in out, out)
            undo()
            # the files that carry the floor: each is valid against HEAD
            hooks = json.loads(json.dumps(GATE_SETTINGS))
            for name, change, want in (
                    ("a tool that changed", lambda: put(VENDORED, mine + "# a change\n"), "tools/psxd_floor.py changed and its version did not"),
                    ("a tool with a lower version", lambda: put(VENDORED, mine.replace('VERSION = "%s"' % VERSION, 'VERSION = "0.5.9"')),
                     "tools/psxd_floor.py went from version %s back to 0.5.9" % VERSION),
                    ("a tool that is gone", lambda: (repo / TOOLS[1]).unlink(), "tools/psxd_publish.py is gone"),
                    ("a workflow that changed", lambda: put(WORKFLOWS + "no-rom.yml", "name: nothing\n"), "no-rom.yml changed"),
                    ("a hook that is gone", lambda: put(SETTINGS, json.dumps(dict(hooks, hooks={}))), "lost a hook of PreToolUse"),
                    ("a hook with a narrower matcher", lambda: put(SETTINGS, json.dumps(GATE_SETTINGS).replace("Bash|Edit|Write", "Edit|Write")),
                     "lost a hook of PreToolUse (or a tool of its matcher)"),
                    ("a hook command made empty", lambda: put(SETTINGS, json.dumps(GATE_SETTINGS).replace("guard --hook", "guard --hook || true")),
                     "lost a hook of PreToolUse"),
                    ("a deny rule that is gone", lambda: put(SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash(git push *)", ', "")),
                     "lost 1 deny rule(s): Bash(git push *)"),
                    ("disableAllHooks", lambda: put(SETTINGS, json.dumps(dict(hooks, disableAllHooks=True))), "sets disableAllHooks"),
                    ("a guard row that is gone", lambda: put(GUARD, "deny\tpath\tbuild/\tx\n"), "lost the row `deny path asm/`"),
                    ("a new allow row", lambda: put(GUARD, "allow\tpath\tasm/x.s\t\ndeny\tpath\tasm/\tasm/ is generated\n"), "a new `allow` row (path asm/x.s)"),
                    ("the game's own scanner, edited", lambda: put("tools/scan.py", "print('SCAN OK')\n"),
                     "tools/scan.py changed (the record names it"),
                    ("the game's own ledger, a row changed", lambda: put("config/names.basis.tsv", "name\tbasis\nWalk\tnone\n"),
                     "config/names.basis.tsv lost or changed 1 line(s)"),
                    ("the record's own check, replaced", lambda: put(RECORD, (repo / RECORD).read_text().replace("python3 tools/scan.py --all", "true")),
                     "config/psxdecomp.toml [own] debt changed"),
                    ("a new key that moves what a check reads", lambda: put(RECORD, (repo / RECORD).read_text() + '\n[debt]\naddress_header = "src/walk.c"\n'),
                     "config/psxdecomp.toml [debt] address_header is new ('src/walk.c')"),
                    ("a file that a skip line covers", lambda: put("src/vendor/lib.c", C_DEBT["goto"][0]),
                     "src/vendor/lib.c changed, and a `skip` line covers it"),
                    ("a new file under a skip line", lambda: put("src/vendor/more.c", C_DEBT["goto"][0]), "src/vendor/more.c changed, and a `skip` line"),
                    ("the settings of one machine, tracked", lambda: (put(SETTINGS.replace(".json", ".local.json"), '{"disableAllHooks": true}\n'),
                                                                      _git(repo, "add", "-f", SETTINGS.replace(".json", ".local.json"))),
                     ".claude/settings.local.json is tracked and changed"),
                    ("the project folder of the hooks, moved", lambda: put(SETTINGS, json.dumps(dict(hooks, env={"CLAUDE_PROJECT_DIR": "/nowhere"}))),
                     "sets CLAUDE_PROJECT_DIR in `env`")):
                change()
                rc, out = staged()
                check("gate: " + name, rc == 1 and "GATE FAIL protected: " in out and want in out, out)
                undo()
            put("config/names.basis.tsv", "name\tbasis\nWalk\tthe string it prints\nRun\tits caller\n")
            put(WORKFLOWS + "extra.yml", "name: extra\n")
            put(GUARD, "deny\tpath\tasm/\tasm/ is generated\ndeny\tpath\tbuild/\tthe build writes it\n")
            put(SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash|Edit|Write"', '"Bash|Edit|Write|MultiEdit"'))
            rc, out = staged()
            check("gate: a new ledger row, a new workflow, a new deny row and a wider matcher pass", (rc, out) == (0, "GATE OK (staged)\n"), out)
            undo()
            put(WORKFLOWS + "no-rom.yml", "name: nothing\n")
            put(BASELINE, base_text.replace("skip ", "raise protected 1 2026-01-02 the runner changed\nskip ") if "skip " in base_text
                else base_text.replace("1 goto src/walk.c", "raise protected 1 2026-01-02 the runner changed\n1 goto src/walk.c"))
            rc, out = staged()
            check("gate: a `raise protected` line of the developer allows one such change", rc == 0 and
                  "GATE INFO protected, and a `raise protected` line of the change allows it: .github/workflows/no-rom.yml changed" in out
                  and "GATE INFO the developer's act, new in this change: `raise protected 1 2026-01-02 the runner changed`" in out, out)
            os.environ["CLAUDECODE"] = "1"
            rc, out = staged()
            check("gate: a `raise` line in an agent session is refused", rc == 1 and "GATE FAIL raise: `raise protected 1 2026-01-02 the "
                  "runner changed` in config/debt-baseline.txt is new, and this is an agent session" in out, out)
            undo()
            put(ASM_EVIDENCE, "\t".join(ASM_COLUMNS) + "\nmain\tWalk\tsrc/walk.c\thand-asm\tsrc/walk.c:1\t2026-01-02\tdeveloper\n")
            rc, out = staged()
            check("gate: a new assembly row in an agent session is refused", rc == 1 and "GATE FAIL raise: the row of Walk src/walk.c in "
                  "config/asm-evidence.tsv is new" in out, out)
            del os.environ["CLAUDECODE"]
            check("gate: and it is the developer's to add", staged()[0] == 0)
            undo()
            # a tool of a later version judges the tree, after the tool of HEAD accepted the change
            later = mine.replace('VERSION = "%s"' % VERSION, 'VERSION = "99.0.0"').replace('"GATE %s (%s%s)"', '"GATE %s by the later tool (%s%s)"')
            put(VENDORED, later)
            rc, out = staged()
            check("gate: a later tool is accepted, and it judges the tree", rc == 0 and "GATE INFO tools/psxd_floor.py: version "
                  "%s -> 99.0.0" % VERSION in out and out.endswith("GATE OK by the later tool (staged)\n"), out)
            _git(repo, "add", "-A")
            _commit(repo, "a later tool, as an upgrade commits it")
            digests = pathlib.Path(td + ".digests.json")
            sha = lambda rel: hashlib.sha256((repo / rel).read_bytes()).hexdigest()  # noqa: E731
            digests.write_text(json.dumps({"version": "99.0.0", "files": {VENDORED: sha(VENDORED)}}))
            os.environ[DIGESTS_ENV] = str(digests)
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a later tool with the released digest is accepted, and it judges from there", rc == 0 and
                  "version %s -> 99.0.0, the released file" % VERSION in out and out.endswith("GATE OK by the later tool (ci; 0 commit(s))\n"), out)
            digests.write_text(json.dumps({"version": "99.0.0", "files": {VENDORED: "0" * 64}}))
            _DIGESTS.clear()
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a later version with other bytes is no released tool", rc == 1 and "by the later tool" not in out and
                  "GATE FAIL protected: " in out and "tools/psxd_floor.py changed: it is not the file that psxdecomp 99.0.0 released" in out, out)
            os.environ[DIGESTS_ENV] = str(digests) + ".gone"
            _DIGESTS.clear()
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: digests that cannot be read accept nothing", rc == 1 and "cannot read the digests of psxdecomp 99.0.0" in out, out)
            del os.environ[DIGESTS_ENV]
            _DIGESTS.clear()
            digests.unlink()
            _git(repo, "reset", "-q", "--hard", "HEAD~1")
            put(VENDORED, later)
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            rc, out = staged()
            check("gate: a later tool beside a refused change does not take over", rc == 1 and "by the later tool" not in out
                  and "rose in an existing body" in out, out)
            undo()
            os.environ["PSXD_SELF_SCAN"] = "1"         # the game's own scanner is one more check, beside the count
            rc, out = staged()
            check("gate: the game's own debt scanner runs beside the count", rc == 1 and "GATE FAIL own-debt: the game's own scanner" in out
                  and "exited 1: SCAN FAIL" in out, out)
            del os.environ["PSXD_SELF_SCAN"]
            # the bank: the files git does not track yet count, and the rows of an admitted change are written
            put("src/walk.c", C_DEBT["goto"][0] + C_DEBT["goto"][0].replace("Walk", "Run"))
            rc, out = gate("bank")
            check("gate --bank refuses the debt of a body that takes no stub away", rc == 1 and "rose in a body that is not new" in out, out)
            put("src/walk.c", C_DEBT["goto"][0])
            put("src/new.c", C_DEBT["goto"][0].replace("Walk", "Run"))
            put("src/stubs.c", "// every function is in C\n")
            rc, out = gate("bank")
            check("gate --bank admits a new body and writes its rows", rc == 0 and "1 goto src/new.c\n" in (repo / BASELINE).read_text()
                  and "GATE INFO config/debt-baseline.txt: the rows of now written (1 rose with a new body, 0 fell)" in out
                  and out.endswith("GATE OK (bank)\n"), out)
            put("src/new.c", C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            before = (repo / BASELINE).read_text()
            rc, out = gate("bank")
            check("gate --bank refuses an unmarked pin in a file that is not tracked yet", rc == 1 and
                  "GATE FAIL debt: rose in total: pin-unmarked is `down`: 0 -> 1" in out and (repo / BASELINE).read_text() == before, out)
            put("src/new.c", C_DEBT["goto"][0].replace("Walk", "Run"))
            os.environ["PSXD_SELF_RED"] = "1"
            rc, out = gate("bank")
            check("gate --bank runs the game's own check", rc == 1 and "GATE FAIL game: `sh tools/check.sh` exited 3: "
                  "the build is red" in out, out)
            os.environ[GATE_ENV] = "1"
            check("a gate inside the game's own check does not run it again", gate("bank")[0] == 0)
            del os.environ[GATE_ENV], os.environ["PSXD_SELF_RED"]
            _git(repo, "add", "-A")
            _commit(repo, "a bank")
            # CI: each commit against its parent, and the range against its base
            rc, out = gate("ci", "%s..HEAD" % start)
            check("gate --ci: an admitted commit", (rc, out) == (0, "GATE OK (ci; 1 commit(s))\n"), out)
            put("src/walk.c", 'INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
            _capture(cmd_debt, repo, update=True)
            _git(repo, "add", "-A")
            _commit(repo, "the body leaves")
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            _capture(cmd_debt, repo, update=True)
            _git(repo, "add", "-A")
            _commit(repo, "the body is back, worse")
            rc, out = gate("ci", "HEAD~2..HEAD")
            check("gate --ci: a body that left and came back worse fails as the range", rc == 1 and out.count("GATE FAIL") == 2
                  and "GATE FAIL debt: %s..%s: rose in an existing body: goto src/walk.c Walk: 1 -> 2" % (
                      _rev(repo, "HEAD~2")[:10], _rev(repo, "HEAD")[:10]) in out, out)
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(BASELINE, (repo / BASELINE).read_text().replace("2 goto src/walk.c", "3 goto src/walk.c"))
            _git(repo, "add", "-A")
            _commit(repo, "a commit that no hook saw")
            sha = _rev(repo, "HEAD")[:10]
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a commit that skipped the hook fails by its own name", rc == 1 and
                  "GATE FAIL debt: %s: rose in an existing body: goto src/walk.c Walk: 2 -> 3" % sha in out, out)
            rc, out = gate("ci", "0000000000000000000000000000000000000000..HEAD")
            check("gate --ci with no base: the tree of the head", rc == 0 and "no base: the tree of the head only" in out, out)
            rc, out = gate("ci", "HEAD..nowhere")
            check("gate --ci: a range that names no commit", rc == 1 and "GATE FAIL gate: HEAD..nowhere names no commit" in out, out)
            rc, out = gate("ci", "nowhere..HEAD")
            check("gate --ci: a base that names no commit judges nothing, so it fails", rc == 1 and "GATE FAIL gate: the base nowhere "
                  "names no commit of this repository" in out, out)
            rc, out = gate("push", "HEAD~1..HEAD")
            check("gate --push: the range, as --ci", rc == 1 and "rose in an existing body" in out, out)
            # a commit with no parent, put in the place of the history: the base judges it
            undo()
            good = _rev(repo, "HEAD~1")
            _git(repo, "checkout", "-q", "--orphan", "fresh", good)
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;\n    // !FAKE: again\n    goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(BASELINE, (repo / BASELINE).read_text().replace("2 goto src/walk.c", "4 goto src/walk.c").replace("mode asm down", "mode asm admit-new"))
            _git(repo, "add", "-A")
            _commit(repo, "a history of one commit")
            rc, out = gate("ci", "%s..HEAD" % good)
            check("gate --ci: a commit with no parent is judged against the base", rc == 1 and "has no parent: it is judged against the base"
                  in out and "rose in an existing body: goto src/walk.c Walk: 2 -> 4" in out and "GATE FAIL policy: " in out, out)
    finally:
        _sibling_run = keep


SYMDUMP_SELF = ("000008: $80010000 1 __SN_ENTRY_POINT\n", "00001d: $00000000 94 Def class TPDEF type UCHAR size 0 name u_char\n",
                "000040: $80010200 8c Function_start\n", "00005c: $00000000 80 Inc SLD linenum (to 5)\n")


def self_test_symdump(check) -> None:
    dump = lambda n: "Header : MND version 1\nTarget unit 0\n" + "".join(SYMDUMP_SELF[i % 4] for i in range(n))  # noqa: E731
    gnu = "".join("                0x00000000%08x                Func%d\n" % (0x80010000 + 8 * i, i) for i in range(200))
    check("symdump: 70 lines of a symbol dump are a run of 70", symdump_run(dump(70)) == 70, symdump_run(dump(70)))
    check("symdump: 60 lines pass, and 64 do not", symdump_run(dump(60)) == 0 and symdump_run(dump(64)) == 64)
    check("symdump: a table of addresses and names is the game's own text", symdump_run("".join(
        "%08X func_%08X\n" % (0x80010000 + 8 * i, 0x80010000 + 8 * i) for i in range(99))) == 0)
    check("symdump: CRLF as the tree reads it, and no newline at the end", symdump_run(dump(70).rstrip("\n")) == 70)
    check("symdump: a line of prose ends a run", symdump_run(dump(40) + "a note\n" + dump(40)) == 0)
    check("symdump: a GNU ld map of the game's own build passes", symdump_run(gnu) == 0)
    check("symdump: a checksum file, a listing and C pass", symdump_run("".join("%040x  f%d\n" % (i, i) for i in range(99))) == 0
          and symdump_run("".join("  %x:\t27bdffc0 \taddiu\tsp,sp,-64\n" % (4 * i) for i in range(99))) == 0
          and symdump_run(C_CLEAN * 40) == 0)
    check("symdump: a binary file is not read", symdump_run("\0" + dump(70)) == 0 and symdump_run(None) == 0)


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
        (tool / "a.out").write_text("built in place\n")
        (repo / "plain").mkdir()                       # a folder of the game, not a checkout of the tool
        (repo / "README.md").write_text("x\n")          # the game has a HEAD of its own, which is not the tool's
        _commit(repo, "the game")
        (repo / TOOLCHAIN).write_text("\t".join(TOOL_COLUMNS) + "\nshort\tgit\t%s\trefs-tool\nupper\tgit\t%s\trefs-tool\n"
                                      "tag\tgit\tv1.0\trefs-tool\nplain\tgit\t%s\tplain\n" % (head[:12], head.upper(), head))
        got = toolchain_rows(repo)
        check("toolchain: a short pin, an upper-case pin, a tag, a folder that is no checkout",
              [r[0] for r in got] == ["OK", "OK", "FAIL", "MISSING"] and "tag can move" in got[2][2], got)


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
    check("guard: an allow row with no say cell is a rule; a pattern that matches every command is an error",
          guard_errors("allow\tpath\tasm/README.md\ndeny\tbash\t\\bmake\\s+expected|\tAsk.\n")
          == ["line 2: the pattern matches the empty command, so it matches every command"])
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
                            ("a list", "[1]"), ("null", "null"), ("an input that is no object", json.dumps({"tool_name": "Edit", "tool_input": "x"})),
                            ("a path that is a number", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 7}, "cwd": str(root)})),
                            ("a path with a NUL", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "asm/a\0.s"}, "cwd": str(root)})),
                            ("an event with no cwd", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))):
            check("guard --hook: %s prints nothing, exit 0" % name, _capture(guard_hook, io.StringIO(stdin)) == (0, ""))
        # a linked worktree is guarded by its own rules, also while the session's project is the main checkout
        (root / "README.md").write_text("x\n")
        _commit(root, "rules")
        with tempfile.TemporaryDirectory() as other:
            tree = pathlib.Path(other).resolve() / "wt"
            _git(root, "worktree", "add", "--quiet", "--detach", str(tree))
            os.environ["CLAUDE_PROJECT_DIR"] = str(root)
            edit = {"tool_name": "Edit", "tool_input": {"file_path": str(tree / "asm/main/a.s")}, "cwd": str(tree)}
            rc, out = _capture(guard_hook, io.StringIO(json.dumps(edit)))
            check("guard --hook: an edit in a linked worktree is refused", rc == 0 and '"deny"' in out, out)
            bash = {"tool_name": "Bash", "tool_input": {"command": "make expected"}, "cwd": other}
            rc, out = _capture(guard_hook, io.StringIO(json.dumps(bash)))
            check("guard --hook: a call from outside a checkout falls back to the project", rc == 0 and '"deny"' in out, out)
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            _git(root, "worktree", "remove", "--force", str(tree))
        # a pattern that backtracks without end: the hook gives up and the call runs
        global GUARD_SECONDS
        keep, GUARD_SECONDS = GUARD_SECONDS, 1
        (root / GUARD).write_text("deny\tbash\t(\\w+\\s*)+$\tNo.\n")
        slow = {"tool_name": "Bash", "tool_input": {"command": "echo " + "word " * 40 + "!"}, "cwd": str(root)}
        import time
        t0 = time.time()
        got = _capture(guard_hook, io.StringIO(json.dumps(slow)))
        GUARD_SECONDS = keep
        check("guard --hook: a pattern that hangs is cut off, exit 0", got == (0, "") and time.time() - t0 < 4, (got, time.time() - t0))
        check("guard: a path through `..` is the file it reaches", guard_decision(
            ev("Edit", file_path=str(root / "src/../asm/main/a.s")), rules, root) is not None)
        check("guard: no flag, and a flag that is no flag, exit 0", _capture(main, ["guard"])[0] == 0
              and _capture(main, ["guard", "--bogus"])[0] == 0)
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
        self_test_bodies(check)
        self_test_files(check)
        self_test_tree(check)
        self_test_trials(check)
        self_test_gate(check)
        self_test_symdump(check)
        self_test_toolchain(check)
        self_test_guard(check)
    finally:
        if saved is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = saved
    print("floor %s" % ("SELF-TEST OK" if not bad else "SELF-TEST FAILED (%d)" % len(bad)))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["plan", "ladder", "debt", "names", "toolchain", "guard", "gate", "trial"])
    ap.add_argument("file", nargs="?", help="ladder: the constitution to read; trial: the source file")
    ap.add_argument("--func", help="trial: one function of the file")
    ap.add_argument("--recheck", action="store_true", help="trial: run rows of config/trials.tsv again")
    ap.add_argument("--rows", type=int, default=10, metavar="N", help="trial --recheck: N rows chosen at random (default 10)")
    ap.add_argument("--base-rows", metavar="FILE", help="trial --recheck: a copy of the base's config/trials.tsv, where no git is")
    ap.add_argument("--repo", help="the repository; default: the git checkout that holds the working directory")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--down", nargs="?", const="all", metavar="KIND")
    ap.add_argument("--recount", action="store_true")
    ap.add_argument("--raise", dest="raise_", nargs=2, metavar=("KIND", "N"))
    ap.add_argument("--reason", help="debt --raise: why")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--staged", action="store_true", help="debt: count the index; gate: judge the index against HEAD")
    ap.add_argument("--bank", action="store_true", help="gate: judge the work tree against HEAD, write the rows")
    ap.add_argument("--ci", metavar="BASE..HEAD", help="gate: judge each commit of the range, and the range")
    ap.add_argument("--push", nargs="?", const="", metavar="BASE..HEAD", help="gate: as --ci, and the game's own check")
    ap.add_argument("--part", default="all", choices=["all", "state"], help=argparse.SUPPRESS)
    ap.add_argument("--range-base", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=VERSION)
    ap.add_argument("--rev", help="debt: count this revision")
    ap.add_argument("--against", metavar="BASE", help="debt: report the counts that differ from this revision's")
    ap.add_argument("--bodies", action="store_true", help="debt: the counts of each function body, no check")
    ap.add_argument("--files", action="store_true", help="debt: the state of each C file: stubs, matched or finished")
    ap.add_argument("--public", action="store_true", help="debt --files: of the files that config/public-paths.txt lists only")
    ap.add_argument("--self-test", action="store_true")
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["guard"]:                          # a hook: no flag, a wrong flag or a missing one never blocks a call
        return guard_hook() if "--hook" in args else 0
    a = ap.parse_args(args)
    if a.self_test:
        return self_test()
    if a.repo is None:
        top = _git(".", "rev-parse", "--show-toplevel")
        a.repo = top.stdout.strip() if top.returncode == 0 and top.stdout.strip() else "."
    if a.cmd == "plan":
        return cmd_plan(a.repo)
    if a.cmd == "ladder":
        return cmd_ladder(a.file or os.path.join(a.repo, CONTEXT))
    if a.cmd == "debt":
        if a.staged and a.rev:
            ap.error("debt: --staged or --rev, not both")
        if a.bodies:
            return cmd_bodies(a.repo, INDEX if a.staged else a.rev)
        if a.files:
            return cmd_files(a.repo, INDEX if a.staged else a.rev, a.public)
        return cmd_debt(a.repo, update=a.update, down=a.down, source=INDEX if a.staged else a.rev,
                        against=a.against, recount=a.recount, raise_=a.raise_, reason=a.reason)
    if a.cmd == "names":
        return cmd_names(a.repo, init=a.init, source=INDEX if a.staged else a.rev, against=a.against)
    if a.cmd == "trial":
        return cmd_trial(a.repo, a.file, a.func, a.recheck, a.against, a.rows, a.base_rows)
    if a.cmd == "gate":
        modes = [m for m, on in (("staged", a.staged), ("bank", a.bank), ("ci", a.ci), ("push", a.push is not None)) if on]
        if len(modes) != 1:
            ap.error("gate: one of --staged, --bank, --ci <base>..<head> and --push [<base>..<head>]")
        return cmd_gate(a.repo, modes[0], a.ci or a.push or None, a.part, a.range_base)
    if a.cmd == "toolchain":
        return cmd_toolchain(a.repo)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
