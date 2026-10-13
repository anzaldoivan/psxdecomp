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
    floor.py debt --update                rewrite the rows to the counts of now; refused when a kind that HEAD's policy
                                          holds `down` rose since HEAD
    floor.py debt --recount               write the baseline in version 2: the rows of now and a policy line for each
                                          kind that has none; refused when a `down` kind rose since HEAD
    floor.py debt --down [KIND]           switch a kind (or every kind) to `down`, one way: it never rises again
    floor.py debt --raise KIND N --reason TEXT
                                          the developer's act: a dated `raise` line that lets one change go over by N
    floor.py gate --staged | --bank | --ci BASE..HEAD | --push [BASE..HEAD]
                                          every check of the floor, each judged against what the change cannot
                                          rewrite: `GATE FAIL <check>: <detail>` lines; exit 1 on a FAIL. --staged: the
                                          index against HEAD (the commit hook). --bank: the work tree against HEAD, with
                                          the files git does not track yet; it writes the rows of an admitted change
                                          and runs the game's own check. --ci: the head of the range against its base.
                                          --push: as --ci, and the game's own check
    floor.py trial FILE [--func NAME]     take each register pin and each empty asm statement of the file's functions out
                                          in turn and ask the game's probe (`[trial] probe` of the record: exit 0 match,
                                          1 no match, 2 or more an error) whether the function still matches. What the
                                          match does not need is gone. What it needs gets a `// !FAKE: <reason>` line
    floor.py names [--init] [--repo DIR]  check config/names.tsv and config/asm-evidence.tsv; --init writes their header lines
    floor.py names [--staged | --rev REV] [--against BASE]
                                          the ledgers of the index or of a revision; --against: open only the rows that
                                          are new since the revision BASE
    floor.py toolchain [--repo DIR]       config/toolchain.tsv: each pinned checkout at its pin and clean, each file at its hash
    floor.py guard --hook                 a PreToolUse hook: stdin is the event, config/guard.tsv holds the rules
    floor.py --self-test

psxdecomp copies this file into a game as tools/psxd_floor.py. It uses the standard library only and it imports
nothing of the plugin. It writes the baseline (`debt --update`, `--recount`, `--down`, `--raise`, `gate --bank`), the
header line of each of the two ledgers (`names --init`), and, for `trial`, the source file it is given.

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
documents, records and tests, and the work folders of a campaign (drafts/, waves/, repro/, scratch/, sandbox/).
The first four kinds are read in the output of the game's preprocessor, `[floor] cpp` of the record (for example
`mipsel-linux-gnu-cpp -nostdinc -undef -D__GNUC__=2 -Iinclude {file}`): what the compiler sees, whatever a macro, a
line splice or an include does to the text, and in whatever file a unit reads. With no `[floor] cpp` they are read in
the raw text of each file, where a construct inside a macro is counted once, at the macro's definition:
  pin              `register T x asm("$n")` (also `__asm__`, `__asm`): a register forced by hand
  goto             the word `goto`
  barrier          an empty asm statement, `__asm__("")`, or one inside a function that holds assembler directives
                   only: it forces the compiler and holds no instruction
  <those three>-unmarked
                   one of them with no `// !FAKE: <reason>` comment of its own: on its line, or alone on the line
                   above, in the file that holds the line. One marker covers one construct, and a marker with no
                   reason covers none
  asm              an assembly file, or an asm statement that holds an instruction or emits data (`.word`, `.byte`,
                   `.incbin`), with no row in config/asm-evidence.tsv. A file-scope asm statement that holds
                   assembler directives only (`.include`, `.section`, `.set`, `.macro`) is a stub or its plumbing, and
                   no debt: the progress report gives a stub no credit
The other kinds are patterns over the raw text. They are counted and shown, and a pattern can be respelled:
  offset           a field read by its offset: `*(T *)(p + N)`, `((T *)p)[N]`, `M2C_FIELD(`, a byte pointer plus a
                   number, each also with a minus, or a macro that hides one (each use). A sum with a variable
                   is not counted
  address          a literal in the console's address ranges (RAM, scratchpad, I/O, BIOS) with no symbol, or a macro
                   that hides one (each use), outside the address header (`[debt] address_header`, include/addr.h)
  cast             an integer made of a pointer, or a pointer made of an integer: `(s32)&x`, `(T *)(s32)x`, also
                   with the SDK's names (`u_long`, `u_int`, `u_short`)
  field            a member or a name `unk_10`, `field_0x10`: a field that has an offset and no name
  macro            a `#define` whose body holds `{`, `;` or a line continuation
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

The baseline's policy lines (one per kind; `debt --recount` writes the starting ones):
  mode <kind> count                             the kind is counted and shown: each commit's diff of the baseline shows
                                                the debt it brings. Nothing is refused
  mode <kind> down                              the total of the kind in the tree never rises. The starting mode of
                                                `asm`, `pin-unmarked`, `goto-unmarked` and `barrier-unmarked`; the
                                                developer sets any other kind with `debt --down <kind>`
  raise <kind> <n> <date> <reason>              the developer lets the change that adds this line go over by n
A change is judged by the policy of the revision it starts from (`debt --against`): it cannot weaken a mode, add a
`skip` line or delete the file. A function that matches is never refused for its name: no kind about names starts
as `down`.
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and os.name == "posix" and not sys.flags.isolated and sys.executable and os.path.isfile(__file__):
    # Start again in isolated mode: a module beside this file or on PYTHONPATH never stands in for the standard library.
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])

import argparse
import bisect
import contextlib
import fnmatch
import hashlib
import json
import pathlib
import re
import signal
import subprocess
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


def as_read(data: bytes) -> str:
    """A file's bytes as every check reads them: UTF-8 with a replacement for what is none, CRLF and a lone CR as LF."""
    return data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def lines(text: str | None) -> list[str]:
    """The lines of a file's text: they end at a newline and at nothing else (no form feed, no line separator), so
    every reader of a file sees the same lines. A byte order mark is no part of the first one."""
    return (text or "").lstrip("\ufeff").split("\n")


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
        self._ids: dict[str, str | None] = {}          # the blob of each path that `blob` was asked for
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
        self.paths = sorted(self._blob)

    def only(self, keep) -> "Tree":
        """A view of this tree that holds the paths `keep(path)` accepts and no other: what a public repository
        holds of a game in split mode. A file outside the view reads as absent."""
        view = Tree.__new__(Tree)
        view.__dict__.update(self.__dict__)
        view.paths = [p for p in self.paths if keep(p)]
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
            self._text[path] = None if data is None else as_read(data)
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

    def blob(self, path: str) -> str | None:
        """The id of a file's bytes, as git names a blob; None for a path that the source holds no file for. The work
        tree gives the id of the bytes on its disk, tracked or not."""
        if self._whole is not None:
            return self._whole.blob(path)
        if self.source is not None:
            return self._blob.get(path)
        if path not in self._ids:
            data = self.raw(path)
            self._ids[path] = None if data is None else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        return self._ids[path]

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
         "field", "macro", "asm", "placeholder", "placeholder-use", "unbased", "struct", "extern", "filename",
         "flag", "reservation")
RETIRED = ("obscured",)                              # a kind of an unreleased build of this tool: its lines are dropped
NUM = r"(?:0[xX][0-9A-Fa-f]+|\d+)"
OFFX = rf"(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*)(?:\s*[-+*]\s*(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*))*"
OPND = r"\(?\s*&?\s*\w+(?:\s*(?:->|\.)\s*\w+|\s*\[[^\[\]\n]*\])*\s*\)?"
PTR = r"\(\s*\w[\w ]{0,60}?\s*\*+\s*\)"              # a type name has an end: a run of words with no star costs no more
CAST = r"\(\s*\w[\w ]{0,60}?\s*\**\s*\)"
CHR = r"(?:const\s+)?(?:(?:(?:unsigned|signed)\s+)?(?:char|[su]8)|u_?char)"
# A field read by its offset, in four forms, and a byte pointer plus a number. A sum with a variable (`(u8 *)dst + n`)
# is pointer arithmetic.
OFFSET = re.compile(
    rf"\*\s*{PTR}\s*\(\s*(?:{CAST}\s*)?{OPND}\s*[-+]\s*{OFFX}\s*\)"                 # *(T *)(p + N), *(T *)((U *)p - N)
    rf"|\*\s*\(\s*{PTR}\s*{OPND}\s*[-+]\s*{OFFX}\s*\)"                              # *((T *)p + N)
    rf"|{PTR}\s*\(\s*{PTR}\s*{OPND}\s*[-+]\s*{OFFX}\s*\)\s*\)\s*(?:->|\[)"           # ((T *)((U *)p + N))->f
    rf"|\(\s*{PTR}\s*{OPND}\s*\)\s*\[\s*-?\s*{NUM}\s*\]"                            # ((T *)p)[N], ((T *)p)[-N]
    rf"|\(\s*{CHR}\s*\*+\s*\)\s*{OPND}\s*[-+]\s*{NUM}(?![\w.])"                        # (u8 *)p + N
    r"|\bM2C_FIELD\s*\(")
INT = r"(?:(?:(?:un)?signed\s+)?(?:int|long|short)|[su](?:8|16|32)|u?intptr_t|u_?(?:long|int|short))"   # the SDK's names too
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
INLINE_ASM = re.compile(r"\b%s\b\s*(?:(?:volatile|__volatile__|__volatile)\b\s*)?\(" % ASM_WORD)
ASM_TEXT = re.compile(r'\s*((?:"(?:\\.|[^"\\\n])*"\s*)+)\)')              # the strings of an asm statement, behind its `(`
# What an assembler line may be and still emit nothing: a section, an include, a setting, a symbol's attributes, a
# macro's definition. Any other line of an asm statement is an instruction or data.
ASM_QUIET = re.compile(r"\.(?:include|section|pushsection|popsection|previous|text|data|rodata|bss|sdata|sbss|set|equ|equiv|align|balign|p2align"
                       r"|macro|endm|purgem|altmacro|noaltmacro|globl|global|type|size|ent|end|frame|mask|fmask|file|loc|ident"
                       r"|weak|local|extern|if\w*|else|elseif|endif)\b")
EXTERN = re.compile(r"\bextern\b|^(?!static\b|typedef\b)(?:[A-Za-z_]\w*[\s*]+)+?[A-Za-z_]\w*\s*\([^;{}]*\)\s*;", re.M)
FILENAME = re.compile(r"(?:(?:func|code|text|seg|file|unk|misc|task|gap|data|rodata|bss)_?[0-9A-Fa-f]{2,}|[0-9A-Fa-f]{5,8})", re.I)
DEFINE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+(\w+)((?:\\\n|[^\n])*)", re.M)
PREPROC = re.compile(r"^[ \t]*#(?:\\\n|[^\n])*", re.M)
DEF_FUNC = re.compile(r"^(?:[A-Za-z_]\w*[\s*]+)+?([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.M)
DEF_DATA = re.compile(r"^(?!extern\b)(?:[A-Za-z_]\w*[\s*]+)+?((?:D|DAT)_[0-9A-Fa-f]{8}\w*)\s*(?:\[[^\]\n]*\]\s*)*[=;]", re.M)
PLACEHOLDER = re.compile(r"^(?:func|D|FUN|DAT|sub|loc)_[0-9A-Fa-f]{8}")      # a splitter's name, or a disassembler's
PLACEHOLDER_USE = re.compile(r"\b(?:func|D|FUN|DAT|sub|loc)_[0-9A-Fa-f]{8}\w*")
NOT_A_NAME = {"if", "for", "while", "switch", "return", "sizeof", "do", "else"}
_STRIP = re.compile(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", re.S)
C_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".inc")              # read as C; the suffix is read in lower case
ASM_SUFFIXES = (".s", ".asm", ".sx")                                          # an assembly file: one count, unless a row
# Every tracked file with one of those suffixes counts, in any folder but these: the splitter's output, what a build
# or a dump writes, the reference library, and the folders that hold tools, documents, records and tests.
NOT_SOURCE = ("asm/", "build/", "expected/", "extracted/", "refs/", "tools/", "docs/", "config/", "tests/", "fixtures/",
              "cookbook/", "drafts/", "waves/", "repro/", "scratch/", "sandbox/")     # the last five: where a campaign works
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*"([^"\n]+)"', re.M)
ADDRESS_HEADER = "include/addr.h"
BASELINE_HEAD = (
    "%s: the count of readability debt in each tracked source file (`python3 %s --help` lists the kinds)." % (
        BASELINE, VENDORED),
    "`python3 %s debt` fails when a count is over its row, and when a row is over its count." % VENDORED,
    "After a change, run `python3 %s debt --update`, or bank with `gate --bank`, which writes the rows." % VENDORED,
    "A policy line gives each kind its mode: `count` (counted and shown) or `down` (the total of the tree never rises).",
    "A mode only gets stronger. A `raise` line is the developer's: `python3 %s debt --raise <kind> <n> --reason <text>`." % VENDORED,
    "A `skip` line names files that the checker does not read. A change cannot add one.")
OLD_HEADS = ("%s: the count of readability debt" % BASELINE, "`python3 %s debt` fails when" % VENDORED,   # an earlier tool's
             "After a change, run `python3 %s debt --update`" % VENDORED, "`python3 %s debt --down` switches" % VENDORED,
             "A policy line gives each kind its mode", "body) or `budget <n>`", "A mode only gets stronger.",
             "A `raise` line is the developer's", "A `skip` line names files that the checker does not read.")


def strip(text: str) -> str:
    """Comments and string bodies become spaces. Newlines stay, so a line number is the same in both texts."""
    def blank(m):
        s = m.group(0)
        if s[0] == "/":
            return re.sub(r"[^\n]", " ", s)
        return s[0] + " " * (len(s) - 2) + s[-1] if len(s) >= 2 else s
    return _STRIP.sub(blank, text)


def uncommented(text: str) -> str:
    """Comments become spaces, strings stay: the text in which an asm statement's own strings are read."""
    return _STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)) if m.group(0)[0] == "/" else m.group(0), text)


def _address_at(text: str) -> list[int]:
    """Where the address literals of a text start. `0x80000000` is the sign mask as well, so it counts only behind a
    pointer cast."""
    return [m.start() for m in ADDRESS.finditer(text)
            if not (SIGN_BIT.fullmatch(m.group(0)) and not re.search(r"\*\s*\)\s*\(?\s*$", text[:m.start()]))]


def _addresses(text: str) -> int:
    return len(_address_at(text))


MACRO_KINDS = ("offset", "address")                  # what a macro can hide from a pattern; the first that its body holds
MACRO_ROUNDS = 8                                     # a macro over a macro over a macro: so deep, and no deeper


def _macros(body: str, known=None) -> dict[str, str]:
    """{macro name: its kind of MACRO_KINDS} for each `#define` whose body holds an offset read or an address, or
    uses a macro that does (`known` and the file's own, MACRO_ROUNDS deep). M2C_FIELD is counted by its name, and the
    stub macros are not debt."""
    defs = [(m.group(1), m.group(2)) for m in DEFINE.finditer(body) if m.group(1) not in ("M2C_FIELD",) + STUB_MACROS]
    out = {}
    if not defs:                                       # most files define nothing
        return out
    for name, text in defs:
        if OFFSET.search(text):
            out[name] = "offset"
        elif _addresses(text):
            out[name] = "address"
    for _ in range(MACRO_ROUNDS):
        grew = False
        seen = dict(known or {}, **out)
        for name, text in defs:
            if name in out:
                continue
            for kind in MACRO_KINDS:
                if _uses([k for k, v in seen.items() if v == kind and k != name], text):
                    out[name], grew = kind, True
                    break
        if not grew:
            break
    return out


_USE_RX: dict[frozenset, re.Pattern] = {}


def _use_rx(names) -> re.Pattern | None:
    key = frozenset(names)
    if not key:
        return None
    if key not in _USE_RX:                             # the same names in thousands of files: one pattern
        _USE_RX[key] = re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, sorted(key))))
    return _USE_RX[key]


def _uses(names, text: str) -> int:
    rx = _use_rx(names)
    return len(rx.findall(text)) if rx else 0


BRACE = re.compile(r"[{}]")
STUB_USE = re.compile(r"\bINCLUDE_ASM\s*\(")          # every use counts, wherever it stands on its line
STUB_NAME = re.compile(r"\bINCLUDE_ASM\s*\([^;]*?\b([A-Za-z_]\w*)\s*\)")
SCOPE = ""                                             # the name of a file's bucket for what no function body holds


def extents(code: str) -> list[tuple[str, int, int]]:
    """[(name, start, end)] of the function bodies of a stripped text, in order: where the count of a file is shown
    by function (`debt --bodies`), where an assembly row finds its function, and where a trial finds the crutches of
    one. A body starts at a definition in column 0 (DEF_FUNC) and ends behind its matching brace. A definition
    inside an open body is dropped. Two heads with nothing between them but space are one body (an `#if` that
    chooses the head: the directives are blank here). A body whose braces never close ends at the next definition in
    column 0. What no body holds is the file's own scope. No check depends on this reading."""
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


# ---- the keyword kinds: pin, goto, barrier, asm -----------------------------------------------------------------------
# These four are what a gate can refuse (their unmarked forms, and assembly), so they are read where the compiler
# reads them: in the output of the game's own preprocessor, `[floor] cpp` of the record (the method of FF7's linter,
# which runs the game's cpp before it scans). There a macro, a line splice, a digraph or an include of any file hides
# nothing: the text is what the compiler gets. Each hit keeps its file and its line through the `# <line> "<file>"`
# markers of the output. With no `[floor] cpp` the same scan reads the raw text of each file, where a construct
# inside a macro is counted once, at the macro's definition.
def asm_emits(text: str) -> bool:
    """The strings of an asm statement hold an instruction or emit data: a line that is no label, no comment and none
    of the directives of ASM_QUIET, outside a `.macro` definition."""
    inside = False
    for l in re.split(r"\\n|\n|;", text):
        l = re.sub(r"^[\w.$]+:\s*", "", l.replace("\\t", " ").replace('\\"', '"').strip())
        if not l or l.startswith(("#", "/*", "//")):
            continue
        if l.startswith(".macro"):
            inside = True
        elif l.startswith(".endm"):
            inside = False
        elif not inside and not ASM_QUIET.match(l):
            return True
    return False


def keywords(text: str, code: str) -> tuple[list[dict], list[tuple[str, int]]]:
    """(the crutches of a text as `_crutches` finds them, [(kind, position)] for what is no crutch): the word `goto`
    in any other form than `goto label;`, an asm statement that holds an instruction, emits data or cannot be read
    (`asm`), and an asm statement inside a function whose strings are assembler plumbing only (a `barrier`: it
    emits nothing and forces the compiler as an empty one does). The same statement at file scope is the plumbing of
    a stub or of its header, and no debt. `code`: the text with its comments and strings blank."""
    found = _crutches(text, code)
    plain = uncommented(text)
    spans = [(c["a"], c["b"]) for c in found if c["kind"] != "goto"]
    known = {c["a"] for c in found if c["kind"] == "goto"}
    more = [("goto", m.start()) for m in re.finditer(r"\bgoto\b", code) if m.start() not in known]
    for m in re.finditer(r"\b%s\b" % ASM_WORD, code):
        if any(a <= m.start() < b for a, b in spans):
            continue
        head = INLINE_ASM.match(code, m.start())
        strings = ASM_TEXT.match(plain, head.end()) if head else None
        if strings is None or asm_emits("".join(re.findall(r'"((?:\\.|[^"\\\n])*)"', strings[1]))):
            more.append(("asm", m.start()))
        elif code.count("{", 0, m.start()) + code.count("<%", 0, m.start()) > code.count("}", 0, m.start()) + code.count("%>", 0, m.start()):
            more.append(("barrier", m.start()))
    return found, more


def marked(hits: list[tuple[str, int]], marks: dict) -> list[tuple[str, int]]:
    """[(kind, line)] with a `<kind>-unmarked` beside each pin, goto and barrier that no marker covers. `hits`:
    [(kind, line from 0)]; `marks`: `markers` of the file. One marker covers one construct: the one on its line, or
    the one on the line below when the marker stands alone. A marker with no reason covers none."""
    out, used = [], set()
    for kind, line in sorted(hits, key=lambda h: h[1]):
        out.append((kind, line))
        if kind == "asm":
            continue
        mark = next((at for at in (line, line - 1) if at in marks and at not in used and (at == line or marks[at][1])), None)
        used.add(mark)
        if mark is None or not reason_ok(marks[mark][0]):
            out.append((kind + "-unmarked", line))
    return out


_RAW: dict[bytes, list] = {}


def raw_keywords(text: str) -> list[tuple[str, int]]:
    """[(kind, line from 0)] of the keyword kinds as the raw text of one file shows them: the view with no
    `[floor] cpp`. The body of a `#define` is read where it stands. The definition of a stub macro is assembly by
    design and is not read, and no other directive is."""
    key = hashlib.sha1(text.encode("utf-8", "replace")).digest()
    if key not in _RAW:
        def directive(m):
            define = DEFINE.match(m.group(0))
            return m.group(0) if define and define.group(1) not in STUB_MACROS else re.sub(r"[^\n]", " ", m.group(0))
        found, more = keywords(text, PREPROC.sub(directive, strip(text)))
        _RAW[key] = [(c["kind"], c["line"]) for c in found] + [(kind, text.count("\n", 0, at)) for kind, at in more]
    return _RAW[key]


LINE_MARK = re.compile(r'^#(?:line)?[ \t]+(\d+)[ \t]+"((?:[^"\\\n]|\\.)*)"[ \t\d]*$', re.M)
# A source may not write a line marker of its own (`#line 9 "other.c"`, `# 9 "other.c"`, also with a digraph or a
# trigraph for the hash): the count gives each construct the file and the line that the preprocessor reports.
LINE_DIRECTIVE = re.compile(r"^[ \t]*(?:#|%:|\?\?=)[ \t]*(?:line\b|\d)", re.M)
CPP_SECONDS = 120                                    # one unit; a preprocessor that hangs is a failure
CPP_CACHE = "psxd-cpp-cache.json"                    # in the repository's git folder: what each unit gave, by what it read
_cpp_cache_on = True                                 # a push and CI trust no file of this machine: they run every unit


def floor_cpp(tree: "Tree") -> str | None:
    """`[floor] cpp` of the record: the command that preprocesses one C unit of the game, with `{file}` for the unit
    (added as the last argument when the command names none). The game's own: `mipsel-linux-gnu-cpp -nostdinc -undef
    -D__GNUC__=2 -Iinclude {file}`, or the host's `cc -E` with the same flags. It prints line markers (no `-P`)."""
    return record_table(tree, "floor").get("cpp") or None


def _cpp_argv(cmd: str, unit: str) -> list[str]:
    import shlex
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        raise Fail("`[floor] cpp` (`%s`) is no command line: %s" % (cmd, e))
    if not argv:
        raise Fail("`[floor] cpp` is empty")
    return [a.replace("{file}", unit) for a in argv] if "{file}" in cmd else argv + [unit]


def unit_view(out: str, unit: str, root: str) -> tuple[dict[tuple[str, str, int], int], set[str]]:
    """({(kind, file, line from 0): count}, the files it read) for the preprocessor output of one unit. The output
    is cut at its line markers into runs. A construct is found in the whole text, so a run may end inside one, and it
    gets the file and the line of the run that holds its first character. A file that the unit includes twice is
    read once: of each line, the most that one run holds."""
    runs, texts, at, pos = [], [], 0, 0                # a run: (its start in the joined text, its file, its first line)
    file, n = unit, 1
    for m in LINE_MARK.finditer(out):
        chunk = out[pos:m.start()]
        runs.append((at, file, n))
        texts.append(chunk)
        at += len(chunk)
        p = m[2].replace("\\\\", "\\").replace('\\"', '"')
        if os.path.isabs(p):
            rel = os.path.relpath(p, root)
            p = p if rel.startswith("..") else rel
        file, n = (unit if p.startswith("<") else os.path.normpath(p).replace(os.sep, "/")), int(m[1])
        pos = min(m.end() + 1, len(out))
    runs.append((at, file, n))
    texts.append(out[pos:])
    files = {f for _, f, _ in runs}
    text = "".join(texts)
    if "asm" not in text and "goto" not in text:
        return {}, files
    starts = [r[0] for r in runs]
    found, more = keywords(text, strip(text))
    hits: dict[tuple, int] = {}
    for kind, at in [(c["kind"], c["a"]) for c in found] + more:
        i = bisect.bisect_right(starts, at) - 1
        key = (kind, runs[i][1], runs[i][2] + text.count("\n", runs[i][0], at) - 1, i)
        hits[key] = hits.get(key, 0) + 1
    once: dict[tuple[str, str, int], int] = {}
    for (kind, f, line, _), c in hits.items():
        once[(kind, f, line)] = max(once.get((kind, f, line), 0), c)
    return once, files


@contextlib.contextmanager
def exported(tree: "Tree"):
    """The folder that holds a tree's files, for a command that reads files: the work tree itself, or a temporary
    checkout of the index or of a revision, made by git with no change to the repository's own index."""
    if tree.source is None:
        yield str(tree.repo)
        return
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        steps = [["checkout-index", "-a", "-f", "--prefix=%s/tree/" % td]]
        if tree.source != INDEX:
            env["GIT_INDEX_FILE"] = os.path.join(td, "index")
            steps.insert(0, ["read-tree", tree.source])
        for step in steps:
            r = subprocess.run(["git", "-C", str(tree.repo)] + step, env=env, capture_output=True, text=True, errors="replace")
            if r.returncode != 0:
                raise Fail("git cannot write the files of %s for the preprocessor: %s" % (source_name(tree.source), r.stderr.strip()[-200:]))
        os.makedirs(os.path.join(td, "tree"), exist_ok=True)
        yield os.path.join(td, "tree")


def cpp_probe(repo, tree: "Tree | None" = None) -> tuple[str, str]:
    """(NONE|OK|FAIL, detail): whether `[floor] cpp` is set and runs on this machine. One C unit of the tree is
    preprocessed in the work tree, and its output must hold a line marker."""
    tree = tree or Tree(repo)
    cmd = floor_cpp(tree)
    if not cmd:
        return "NONE", ("no `[floor] cpp` in %s: pin, goto, barrier and asm are read in the raw text of each file, where a "
                        "construct inside a macro counts once, at the macro's definition" % RECORD)
    unit = next((p for p in tree.paths if is_source(p) and is_c(p)), None)
    if unit is None:
        return "OK", "`%s` (no C unit to run it on yet)" % cmd
    try:
        r = subprocess.run(_cpp_argv(cmd, unit), cwd=str(tree.repo), capture_output=True, timeout=CPP_SECONDS)
    except Fail as e:
        return "FAIL", str(e)
    except FileNotFoundError:
        return "FAIL", "`[floor] cpp` names a program that this machine lacks (`%s`): every gate fails here" % _cpp_argv(cmd, unit)[0]
    except (OSError, subprocess.TimeoutExpired) as e:
        return "FAIL", "`%s` on %s: %s" % (cmd, unit, type(e).__name__)
    if r.returncode != 0:
        return "FAIL", "`%s` exited %d on %s: %s" % (cmd, r.returncode, unit, (as_read(r.stderr).strip().splitlines() or [""])[-1][:160])
    if not LINE_MARK.search(as_read(r.stdout)):
        return "FAIL", "`%s` prints no `# <line> \"<file>\"` marker for %s (drop `-P`)" % (cmd, unit)
    return "OK", "`%s` runs here (tried on %s)" % (cmd, unit)


def _cache_file(repo) -> pathlib.Path | None:
    r = _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return pathlib.Path(r.stdout.strip()) / CPP_CACHE if r.returncode == 0 and r.stdout.strip() else None


def compiler_view(repo, tree: "Tree", cmd: str) -> dict[str, list[tuple[str, int]]]:
    """{path: [(kind, line from 0)]} of the keyword kinds as the game's preprocessor shows them: `cmd` run for each C
    unit of the tree, in a folder that holds the tree's files. A unit is a C file that no unit before it read: every
    C file that no `#include "…"` names is run first, the files that the line markers name are collected, and each C
    file not seen yet is run on its own, so the preprocessor decides what was covered and no pattern does. Of one
    line of one file, the most that one unit holds counts. A unit that the command cannot preprocess raises Fail: a
    judge that cannot read passes nothing. So does a file with a line directive of its own. Each unit's result is kept beside the files it read (their blobs), so a
    change costs the units that it touches."""
    if ("view", cmd) in tree.memo:
        return tree.memo[("view", cmd)]
    whole = tree._whole or tree
    units = [p for p in whole.paths if is_source(p) and is_c(p)]
    named = set()
    for p in units:
        text = whole.read(p) or ""
        folder = p.rsplit("/", 1)[0] + "/" if "/" in p else ""
        for inc in INCLUDE.findall(text) if "include" in text else ():
            named.update((os.path.normpath(folder + inc), os.path.normpath(inc), os.path.normpath("include/" + inc)))
    by_name: dict[str, list[str]] = {}
    for p in whole.paths:
        by_name.setdefault(p.rsplit("/", 1)[-1], []).append(p)

    def names_of(deps) -> str:                         # a new file of the same name could be found first by an include
        same = sorted(q for name in {d.rsplit("/", 1)[-1] for d in deps} for q in by_name.get(name, ()))
        return hashlib.sha1("\n".join(same).encode("utf-8", "replace")).hexdigest()

    store = _cache_file(repo) if _cpp_cache_on else None
    try:
        cache = json.loads(store.read_text(encoding="utf-8")) if store is not None and store.is_file() else {}
    except (OSError, ValueError):
        cache = {}
    cache = cache if isinstance(cache, dict) and cache.get("version") == VERSION and isinstance(cache.get("units"), dict) else {
        "version": VERSION, "units": {}}
    held, fresh = cache["units"], {}
    total: dict[tuple[str, str, int], int] = {}
    seen: set[str] = set()
    failed: list[str] = []

    def take(unit, hits, files):
        seen.update(files)
        for key, n in hits.items():
            total[key] = max(total.get(key, 0), n)

    slot = lambda unit: hashlib.sha1(("%s\0%s" % (cmd, unit)).encode()).hexdigest()  # noqa: E731

    def cached(unit):
        e = held.get(slot(unit))
        try:
            if e and all(whole.blob(p) == b for p, b in e["deps"].items()) and e["names"] == names_of(e["deps"]):
                return {(k, f, int(l)): int(n) for k, f, l, n in e["hits"]}, set(e["deps"])
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
        return None

    def run(root, unit):
        try:
            r = subprocess.run(_cpp_argv(cmd, unit), cwd=root, capture_output=True, timeout=CPP_SECONDS)
        except FileNotFoundError:
            raise Fail("`[floor] cpp` names a program that this machine lacks (`%s`): the gate reads what the game's "
                       "preprocessor prints. Install it, or name one that every machine of the project has (the host's "
                       "`cc -E` with the same flags reads the same text)" % _cpp_argv(cmd, unit)[0])
        except (OSError, subprocess.TimeoutExpired) as e:
            return unit, None, "%s: %s" % (type(e).__name__, str(e)[:120])
        if r.returncode != 0:
            return unit, None, (as_read(r.stderr).strip().splitlines() or ["exit %d" % r.returncode])[-1][:200]
        out = as_read(r.stdout)
        return (unit, out, "") if LINE_MARK.search(out) else (unit, None, "the output holds no `# <line> \"<file>\"` marker (a "
                                                              "preprocessor prints them unless `-P` is given): a hit would have no file")

    import concurrent.futures
    with contextlib.ExitStack() as stack:
        root = None
        first = [p for p in units if p not in named]
        for batch in (first, None):
            batch = [p for p in units if p not in seen and p not in first] if batch is None else batch
            todo = []
            for unit in batch:
                got = cached(unit)
                if got is None:
                    todo.append(unit)
                else:
                    take(unit, *got)
                    fresh[slot(unit)] = held[slot(unit)]
            if todo and root is None:
                root = stack.enter_context(exported(whole))
            with concurrent.futures.ThreadPoolExecutor(min(8, os.cpu_count() or 2)) as pool:
                for unit, out, err in pool.map(lambda u: run(root, u), todo):
                    if out is None:
                        failed.append("%s: %s" % (unit, err))
                        continue
                    hits, files = unit_view(out, unit, root)
                    take(unit, hits, files)
                    deps = {f: whole.blob(f) for f in files}
                    if all(deps.values()):             # every file it read is a file of this tree: the result can be kept
                        fresh[slot(unit)] = {
                            "deps": deps, "names": names_of(deps), "hits": [[k, f, l, n] for (k, f, l), n in sorted(hits.items())]}
    if failed:
        raise Fail("`[floor] cpp` (`%s`) cannot preprocess %d unit(s) of %s: %s%s" % (
            cmd, len(failed), source_name(tree.source), failed[0], " and %d more" % (len(failed) - 1) if len(failed) > 1 else ""))
    forged = [f for f in sorted(seen | set(units)) if "line" in (whole.read(f) or "") or re.search(r"(?:#|%:|\?\?=)\s*\\?\s*\d", whole.read(f) or "")]
    forged = [f for f in forged if LINE_DIRECTIVE.search(uncommented(whole.read(f)).replace("\\\n", "").replace("??/\n", ""))]
    if forged:
        raise Fail("%s%s holds a line directive (`#line`, or `#` and a number): a source that names its own file and line "
                   "would decide where the count puts its constructs" % (forged[0], " (and %d more)" % (len(forged) - 1) if len(forged) > 1 else ""))
    if store is not None and fresh != held:
        try:                                           # the units of this run and of the one before: a base and a head
            keep = dict(list(held.items())[-20000:], **fresh)
            tmp = store.with_name(store.name + ".%d" % os.getpid())
            tmp.write_text(json.dumps({"version": VERSION, "units": keep}), encoding="utf-8")
            os.replace(tmp, store)
        except OSError:
            pass
    out: dict[str, list[tuple[str, int]]] = {}
    for (kind, f, line), n in sorted(total.items()):
        out.setdefault(f, []).extend([(kind, line)] * n)
    tree.memo[("view", cmd)] = out
    return out


_SCANS: dict[tuple, dict] = {}                         # one scan per text and context: a range of commits repeats most


def scan_file(rel: str, text: str, shared=None, address_header=ADDRESS_HEADER) -> dict:
    """One C file or header, read once. `hits`: [(kind, position)] of every kind that a pattern over the raw text
    decides (not the keyword kinds, and not `unbased`, `filename`, `flag`, `reservation`). `extents`: its function
    bodies. `funcs`: {name: position} of the functions it defines under a name that is no placeholder. `stubs`: its
    INCLUDE_ASM lines. `shared`: the macros of the headers that hide an offset or an address."""
    key = (hashlib.sha1(text.encode("utf-8", "replace")).digest(), in_include(rel), is_c(rel), is_header(rel),
           rel == address_header, tuple(sorted((shared or {}).items())))
    if key in _SCANS:
        return _SCANS[key]
    body = strip(text)
    code = PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)
    macros = dict(shared or {})
    macros.update(_macros(body, macros))
    defines = [m for m in DEFINE.finditer(body) if m.group(1) not in ("M2C_FIELD",) + STUB_MACROS]
    ext = extents(code)
    hits: list[tuple[str, int]] = []
    # each construct in the code, each one that a macro's own body holds, and each use of such a macro
    hits += [("offset", m.start()) for m in OFFSET.finditer(code)]
    hits += [("offset", d.start()) for d in defines for _ in OFFSET.findall(d.group(2))]
    if rel != address_header:
        hits += [("address", at) for at in _address_at(code)]
        hits += [("address", d.start()) for d in defines for _ in _address_at(d.group(2))]
    for kind in MACRO_KINDS:
        rx = _use_rx([k for k, v in macros.items() if v == kind])
        if rx and not (kind == "address" and rel == address_header):   # (its own address macros are not in `shared`)
            hits += [(kind, m.start()) for m in rx.finditer(code)]
    hits += [("cast", m.start()) for m in CASTS.finditer(code)]
    hits += [("field", m.start()) for m in FIELD.finditer(code)]
    hits += [("macro", m.start()) for m in DEFINE.finditer(body) if m.group(1) not in STUB_MACROS
             and re.search(r"[{;]|\\\n", m.group(2))]
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
    _SCANS[key] = {"hits": hits, "extents": ext, "funcs": funcs, "stubs": len(STUB_USE.findall(code))}
    return _SCANS[key]


def file_bodies(rel: str, text: str, shared=None, based=None, address_header=ADDRESS_HEADER, view=None) -> dict[str, dict[str, int]]:
    """{function name: {kind: count}} of one C file or header: every function body it holds, also one with no debt,
    and under SCOPE what no body holds (left out when it is empty). Two bodies of one name are one entry. `based`:
    the names with a ledger row, or None before the ledger exists. `view`: [(kind, line from 0)] of the keyword kinds
    as the game's preprocessor shows them for this file (`compiler_view`); None: as the raw text shows them."""
    scan = scan_file(rel, text, shared, address_header)
    hits = list(scan["hits"])
    view = raw_keywords(text) if view is None else view
    if view:                                           # a hit stands in the body that holds the start of its line
        starts = [0] + [m.end() for m in re.finditer("\n", text)]
        hits += [(kind, starts[min(line, len(starts) - 1)]) for kind, line in marked(view, markers(text) if "!FAKE:" in text else {})]
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


def file_debt(rel: str, text: str, shared=None, based=None, address_header=ADDRESS_HEADER, view=None) -> dict[str, int]:
    """The counts of one C file or header, by kind (zero counts left out): the sum of its bodies and its scope."""
    got: dict[str, int] = {}
    for counts in file_bodies(rel, text, shared, based, address_header, view).values():
        for kind, n in counts.items():
            got[kind] = got.get(kind, 0) + n
    return {k: got[k] for k in KINDS if got.get(k)}


def is_source(path: str) -> bool:
    """A file that the debt count reads: a C or an assembly suffix, in no folder of NOT_SOURCE and in no folder whose
    name starts with a dot."""
    return (path.lower().endswith(C_SUFFIXES + ASM_SUFFIXES) and not path.startswith(NOT_SOURCE)
            and not any(part.startswith(".") for part in path.split("/")))


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
    for n, line in enumerate(lines(text), 1):
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


def debt_bodies(repo, skip=(), tree: Tree | None = None, cpp=False) -> dict[str, dict[str, dict[str, int]]]:
    """{path: {function name: {kind: count}}} over the tracked source files (is_source) that no `skip` entry covers:
    every function body of every C file (also one with no debt), and under SCOPE what no body holds. `tree`: the
    source to count (default: the work tree of `repo`). The ledgers and the record are read from the same source.
    `cpp`: the preprocess command that shows the keyword kinds (False: the tree's own `[floor] cpp`; None: no
    command, the raw text). With a command, a keyword that the preprocessor finds in any file that a unit reads is
    counted at that file, whatever its suffix and its folder."""
    tree = tree or Tree(repo)
    cmd = floor_cpp(tree) if cpp is False else cpp
    if ("bodies", tuple(skip), cmd) in tree.memo:
        return tree.memo[("bodies", tuple(skip), cmd)]
    covered = lambda p: any(entry_match(e, p) for e in skip)  # noqa: E731
    files = [p for p in tree.paths if is_source(p) and not covered(p)]
    header = address_header(tree)
    names, _ = read_tsv(NAMES, NAME_COLUMNS, tree)
    based = None if names is None else {r["new_name"] for r in names if r["decision"] == "accepted"}
    evidence: dict[str, set] = {}                      # {path: the symbols with a row}: a row clears one function, or one file
    for r in read_tsv(ASM_EVIDENCE, ASM_COLUMNS, tree, also=(ASM_COLUMNS_OLD,))[0] or []:
        evidence.setdefault(r["path"], set()).add(r["symbol"])
    view = compiler_view(repo, tree, cmd) if cmd else None
    texts = {p: tree.read(p) for p in files}
    shared: dict[str, str] = {}
    # The macros of every header and `.inc` are known in every file. The address header shares what it hides too, but
    # not its addresses: that is the place for them.
    heads = [(p, strip(texts[p])) for p in files if texts[p] is not None and (is_header(p) or p.lower().endswith(".inc"))]
    for _ in range(MACRO_ROUNDS):                      # a macro of one header may use a macro of another
        size = len(shared)
        for p, body in heads:
            shared.update({k: v for k, v in _macros(body, shared).items() if not (p == header and v == "address")})
        if len(shared) == size:
            break
    own: dict[str, dict] = {}                          # {a C file that others include: its macros}

    def known(p: str) -> dict[str, str]:
        """`shared`, and the macros of each C file that `p` includes: those are known in the file that includes it."""
        more: dict[str, str] = {}
        folder = p.rsplit("/", 1)[0] + "/" if "/" in p else ""
        for inc in INCLUDE.findall(texts[p]) if "include" in texts[p] else ():
            target = next((c for c in (os.path.normpath(folder + inc), os.path.normpath(inc), "include/" + inc) if tree.has(c)), None)
            if target in texts and target != p and is_c(target) and texts[target] is not None:
                if target not in own:
                    own[target] = _macros(strip(texts[target]), shared) if "define" in texts[target] else {}
                more.update(own[target])
        return dict(shared, **more) if more else shared
    out: dict[str, dict[str, dict[str, int]]] = {}
    for p in files:
        if texts[p] is None:
            continue
        if is_asm(p):
            out[p] = {} if p in evidence else {SCOPE: {"asm": 1}}
        else:
            out[p] = file_bodies(p, texts[p], known(p), based, header, None if view is None else view.get(p, []))
            for name in evidence.get(p, ()):
                if name != SCOPE:
                    out[p].get(name, {}).pop("asm", None)
        if FILENAME.fullmatch(p.rsplit("/", 1)[-1].rsplit(".", 1)[0]):
            out[p].setdefault(SCOPE, {})["filename"] = 1       # a name that says an address or a number, not a subject
    for p, hits in (view or {}).items():               # what a unit read and the count above does not: another suffix, another folder
        if p in out or covered(p) or (tree._keep is not None and not tree._keep(p)):
            continue
        text = tree.read(p) if not is_asm(p) else None
        got: dict[str, int] = {}
        for kind, _ in marked(hits, markers(text) if text and "!FAKE:" in text else {}):
            got[kind] = got.get(kind, 0) + 1
        out.setdefault(p, {})[SCOPE] = got
    for (kind, p), n in flag_counts(repo, tree).items():
        if not covered(p):
            out.setdefault(p, {}).setdefault(SCOPE, {})[kind] = n
    tree.memo[("bodies", tuple(skip), cmd)] = out
    return out


def debt_counts(repo, skip=(), tree: Tree | None = None, bodies=None, cpp=False) -> dict[tuple[str, str], int]:
    """{(kind, path): count}: the sum of each file's bodies and scope (`bodies`: a result of debt_bodies)."""
    out: dict[tuple[str, str], int] = {}
    for p, by in (debt_bodies(repo, skip, tree, cpp) if bodies is None else bodies).items():
        for got in by.values():
            for kind, n in got.items():
                out[(kind, p)] = out.get((kind, p), 0) + n
    return out



# ---- the baseline: one row per count, and the policy that judges a change -------------------------------------------
# A policy line gives each kind its mode. `count`: the kind is counted, its rows show what each commit brings, and
# nothing is refused. `down`: the total of the kind in the tree never rises. A `raise` line is the developer's act: it
# lets one change go over by its number. The change itself cannot weaken any of this: `admission` reads the policy of
# the revision that the change starts from.
MODES = ("count", "down")                            # weakest first
START_DOWN = ("asm", "pin-unmarked", "goto-unmarked", "barrier-unmarked")   # what `debt --recount` starts as `down`
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
        self.raises: list[tuple[str, int, str, str]] = []            # (kind, n, date, reason)
        self.head: list[str] = []
        self.other: list[str] = []

    def policy(self, kind: str) -> str | None:
        """`down` or `count`; None for a kind with no line."""
        return self.modes.get(kind)

    def lacks(self) -> list[str]:
        return [k for k in KINDS if k not in self.modes]

    def summary(self) -> str:
        by = {m: [k for k in KINDS if self.modes.get(k) == m] for m in reversed(MODES)}
        return "; ".join("%s: %s" % (m, ", ".join(ks)) for m, ks in by.items() if ks)


def parse_baseline(text: str | None) -> Baseline:
    """The baseline of a text; None is the absent file (version 0). A line that is no row, no policy line, no `skip`
    line and no `#` comment raises Fail with its number, and so do a second row of one pair, a second policy of one
    kind, and a file that mixes the two versions. `--update` writes every comment line above the policy lines. The
    lines `mode <kind> admit-new` and `budget <kind> …` of an unreleased build of this tool are read as `count`."""
    bl, old = Baseline(), 0
    if text is None:
        return bl
    bl.version = 2
    for n, raw in enumerate(lines(text), 1):
        l = raw.strip()
        if not l:
            continue
        where = "%s:%d" % (BASELINE, n)
        mode = re.fullmatch(r"mode (\S+) (down|count|admit-new)", l)
        budget = re.fullmatch(r"budget (\S+) \d{1,9} base \d{1,9} \d{1,9} \d{1,9}", l)
        rise = re.fullmatch(r"raise (\S+) (\d{1,9}) (\d{4}-\d\d-\d\d) (\S.*)", l)
        row = re.fullmatch(r"(\d{1,9}) (\S+) (\S.*)", l)
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
            raise Fail("%s: not `<count> <kind> <path>`, `mode <kind> down|count`, `raise <kind> <n> <date> <reason>`, "
                       "`skip <entry>` or a `#` comment" % where)
        elif kind in RETIRED:
            continue
        elif kind not in KINDS:
            bl.other.append(l)
        elif mode or budget:
            if kind in bl.modes:
                raise Fail("%s: %s has two policy lines" % (where, kind))
            bl.modes[kind] = "down" if mode and mode[2] == "down" else "count"
        elif rise:
            bl.raises.append((kind, int(rise[2]), rise[3], rise[4]))
        elif (kind, row[3]) in bl.rows:
            raise Fail("%s: %s %s has two rows" % (where, kind, row[3]))
        else:
            bl.rows[(kind, row[3])] = int(row[1])
    if old and (bl.modes or bl.raises):
        raise Fail("%s: a `mode %s` line of version 1 beside the policy lines of version 2" % (BASELINE, bl.old_mode))
    return bl


def baseline_text(bl: Baseline, counts: dict | None = None) -> str:
    """The file of a baseline in version 2: the comment lines, a policy line per kind, the lines of kinds this tool
    does not know, the `raise` lines, the `skip` lines, then one row per count above zero (`counts`, else its own)."""
    rows = bl.rows if counts is None else counts
    lines = [l if l.startswith("#") else "# " + l for l in bl.head]
    lines += ["mode %s %s" % (kind, bl.modes[kind]) for kind in KINDS if kind in bl.modes]
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
    version 1 file in `mode down`: the developer chose that)."""
    tree = tree or Tree(repo)
    bl = parse_baseline(tree.read(BASELINE))
    notes = []
    if bl.version == 0:
        bl.head = list(BASELINE_HEAD)
    counts = debt_counts(repo, bl.skip, tree)
    for kind in bl.lacks():
        bl.modes[kind] = "down" if bl.old_mode == "down" or kind in START_DOWN else "count"
        notes.append("%s: %s" % (kind, bl.modes[kind]))
    if bl.version == 1 or any(l.lstrip("# ").startswith(OLD_HEADS[4:8]) for l in bl.head):
        bl.head = list(BASELINE_HEAD) + [l for l in bl.head if not l.lstrip("# ").startswith(OLD_HEADS)]
    return baseline_text(bl, counts), notes


def first_baseline(repo) -> str:
    """A game's first baseline: the counts of now and the starting mode of each kind."""
    return recount_text(repo)[0]


def unpublished(tree: Tree):
    """The test of a path whose row this tree keeps for another tree: config/public-paths.txt exists, the tree lacks
    the file and the list does not publish it (the public tree of a game in split mode)."""
    public = tree.read(PUBLIC_PATHS)
    if public is None:
        return lambda path: False
    listed = [l.strip() for l in lines(public) if l.strip() and not l.lstrip().startswith("#")]
    return lambda path: not tree.has(path) and not any(entry_match(e, path) for e in listed)


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
    elsewhere = unpublished(tree)
    keys = sorted(set(bl.rows) | set(counts), key=lambda k: (k[1], KINDS.index(k[0])))
    for k in keys:
        have, row = counts.get(k, 0), bl.rows.get(k, 0)
        if have > row:
            st["rise"].append(k)
            out.append("rise %s %s: %d, its row is %d" % (k[0], k[1], have, row))
        elif have < row and not elsewhere(k[1]):
            st["stale"].append(k)
            out.append("stale %s %s: %d, its row is %d" % (k[0], k[1], have, row))
    return out, st


def policy_findings(old: Baseline, new: Baseline) -> list[str]:
    """What a change may not do to the policy that judged it: weaken a kind's mode, take its line out, add a `skip`
    line, delete the file. `old`: the baseline of the revision the change starts from."""
    if old.version == 0:
        return []
    if new.version == 0:
        return ["%s is gone" % BASELINE]
    out = ["a new `skip` line (%s)" % e for e in new.skip if e not in old.skip]
    if new.version == 1:
        return out + (["`mode down` became `mode admit`"] if (old.old_mode, new.old_mode) == ("down", "admit") else []) + (
            ["a version 2 file became a version 1 file"] if old.version == 2 else [])
    for kind in KINDS:
        was, now = "down" if old.old_mode == "down" else old.policy(kind), new.policy(kind)
        if was is None:
            continue
        if now is None:
            out.append("the policy line of %s is gone (it was %s)" % (kind, was))
        elif MODES.index(now) < MODES.index(was):
            out.append("%s went from %s to %s: a mode only gets stronger" % (kind, was, now))
    return out


def admission(repo, base: Tree | None, head: Tree) -> tuple[list[tuple[str, str]], list[str]]:
    """([(check, detail)] for what a change may not do, the INFO lines). `base`: the tree the change starts from
    (None: a first commit, with nothing to compare). `head`: the tree it makes. Check `policy`: policy_findings.
    Check `debt`: the total of a `down` kind in the tree rose. Both trees are counted by this tool, with the `skip`
    lines that both baselines hold and with the preprocess command of the base's record, so a row or a command that
    the change wrote decides nothing. A `raise` line that the change
    adds lets its kind go over by its number. A kind in mode `count` is never refused."""
    new = parse_baseline(head.read(BASELINE))
    if base is None:
        return [], []
    old = parse_baseline(base.read(BASELINE))
    fails = [("policy", f) for f in policy_findings(old, new)]
    skip = tuple(e for e in new.skip if e in old.skip) if old.version else tuple(new.skip)
    cpp = floor_cpp(base)                              # both trees in the view of the tree the change starts from
    was, now = debt_counts(repo, skip, base, cpp=cpp), debt_counts(repo, skip, head, cpp=cpp)
    tot0, tot1 = _kind_totals(was), _kind_totals(now)
    seen = list(old.raises)
    slack: dict[str, int] = {}
    for r in new.raises:
        if r in seen:
            seen.remove(r)
        else:
            slack[r[0]] = slack.get(r[0], 0) + r[1]
    infos = []
    for kind in KINDS:
        mode = "down" if old.old_mode == "down" else (old.policy(kind) or new.policy(kind) or "count")
        over = tot1[kind] - tot0[kind]
        if mode != "down" or over <= 0:
            continue
        rose = sorted((p for k, p in now if k == kind and now[(k, p)] > was.get((k, p), 0)),
                      key=lambda p: (was.get((kind, p), 0) - now[(kind, p)], p))
        where = ", ".join("%s %d -> %d" % (p, was.get((kind, p), 0), now[(kind, p)]) for p in rose[:4]) + (
            " and %d more file(s)" % (len(rose) - 4) if len(rose) > 4 else "")
        if over > slack.get(kind, 0):
            fails.append(("debt", "%s is `down` and its total rose: %d -> %d (%s)%s" % (kind, tot0[kind], tot1[kind], where, (
                "; the `raise` line(s) of the change allow %d" % slack[kind]) if slack.get(kind) else "")))
        else:
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
    entries = [l.strip() for l in lines(listed) if l.strip() and not l.lstrip().startswith("#")]
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
    ledger = tree.read(NAMES) is not None
    out = []
    for p in sorted(bodies):
        stubs = scan_file(p, tree.read(p) or "", address_header=address_header(tree))["stubs"] if is_c(p) else 0
        if not is_c(p) or not (stubs or any(n != SCOPE for n in bodies[p])):
            continue
        counts = debt_counts(repo, bodies={p: bodies[p]})
        got = {k[0]: n for k, n in counts.items()}
        out.append(("stubs" if stubs else "matched" if got or not ledger else "finished", p, got))
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
        if floor_cpp(tree):
            print("DEBT INFO pin, goto, barrier and asm are read in the output of `[floor] cpp` (`%s`)" % floor_cpp(tree))
        elif any(k[0].split("-")[0] in ("pin", "goto", "barrier") or k[0] == "asm" and not is_asm(k[1]) for k in counts):
            print("DEBT INFO %s" % cpp_probe(repo, tree)[1])
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
                print("DEBT %s refused: %d finding(s) against HEAD, %s is unchanged" % (flag[2:].upper(), len(judged), BASELINE))
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
                    bl.modes[kind] = "down"
                _write_baseline(repo, baseline_text(bl))
                print("DEBT DOWN %s: %s may only fall from now on" % (BASELINE, ", ".join(kinds)))
                return 0
            for k in st["rise"]:
                print("DEBT INFO %s %s: %d -> %d" % (k[0], k[1], bl.rows.get(k, 0), counts[k]))
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
# A name is never required: a function that matches is banked and pushed under the name it has, and names come later,
# from people, tests, oracles and knowledge of the code. So a finding about a row of the names ledger is a warning.
# Only a ledger that cannot be read fails, and so does a row of the assembly ledger, which clears a count that blocks.
# A row is a claim, so it must point at something that a reader can open: its evidence names a file and a line that
# the tree holds, an accepted name is one that the source defines as the row's kind, and a `refs` row cites an entry
# of config/refs.toml. An assembly row names one function of a C file, or one assembly file. The rows that a change
# adds are the ones that are opened (`base`): a row that an earlier commit brought was checked there.
NAME_COLUMNS = ("kind", "image", "scope", "old_name", "new_name", "decision", "evidence", "reason")
NAME_KINDS = ("function", "data", "type", "field", "macro", "file")
DECISIONS = ("accepted", "provisional", "rejected")
EVIDENCE = ("psyq-sig", "string", "xref", "loadmap", "exe-header", "prior-art", "debug-symbol", "refs",
            "human", "test", "oracle", "debugger")   # a person's decision, a test, a second build of the game, a debugger session
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
    """[(FAIL|WARN|INFO, detail)] for the two ledgers of a tree (default: the work tree). A FAIL is a file that
    cannot be read as its table, or a row of the assembly ledger that points at nothing (it names no function of its C
    file, its evidence is no file and line of the tree). A WARN is a row of the names ledger that is malformed or
    points at nothing: its evidence is no file and line of the tree, its accepted name is nothing that the source
    defines as the row's kind. `base`: the tree a change starts from. The rows it holds already are not opened
    again, only their form is read."""
    tree, out = tree or Tree(repo), []
    seen = {NAMES: set(), ASM_EVIDENCE: set()}
    for rel in seen if base is not None else ():
        seen[rel] = set(lines(base.read(rel)))
    raw = {rel: lines(tree.read(rel)) for rel in seen}
    fresh = lambda rel, r: raw[rel][r["_line"] - 1] not in seen[rel]  # noqa: E731
    rows, errs = read_tsv(NAMES, NAME_COLUMNS, tree)
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % NAMES))
    else:
        symbols, loose = None, []
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
            loose += ["line %d: %s" % (r["_line"], b) for b in bad]
        live: dict[tuple, int] = {}
        for r in rows:
            if r["decision"] != "rejected":
                key = (r["new_name"], r["image"], r["scope"], r["kind"])
                live[key] = live.get(key, 0) + 1
        twice = sorted({k[0] for k, n in live.items() if n > 1})
        loose += ["%s has two rows that are not rejected" % n for n in twice]
        out += [("FAIL", "%s: %s" % (NAMES, e)) for e in errs] + [("WARN", "%s: %s" % (NAMES, e)) for e in loose]
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
                print("NAMES INFO with %s in place, each named function with no accepted row is counted as `unbased`. "
                      "A name is never required to bank or to push: run `python3 %s debt --update` for the rows" % (NAMES, VENDORED))
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
    bad, warned = sum(f[0] == "FAIL" for f in found), sum(f[0] == "WARN" for f in found)
    print("NAMES %s (%d finding(s), %d warning(s)%s)" % ("FAIL" if bad else "OK", bad, warned, "; only the rows that are new since "
                                                        "%s were opened" % against if against else ""))
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
    for line in lines(text):
        cells = [c.strip() for c in line.split("\t")]
        if line.startswith("#") or len(cells) < 3 or tuple(cells[:4]) == GUARD_COLUMNS:
            continue
        if cells[0] in ("deny", "allow") and cells[1] in ("bash", "path") and cells[2]:
            rules.append((cells[0], cells[1], cells[2], cells[3] if len(cells) > 3 else ""))
    return rules


def guard_errors(text: str) -> list[str]:
    errs = []
    for n, line in enumerate(lines(text), 1):
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


# ---- trials: a helper that takes out what the match does not need ---------------------------------------------------
# A crutch is a register pin or an empty asm statement (a barrier): a construct that forces the compiler and says
# nothing about the game. `trial` takes each one out in turn and asks the game's probe (`[trial] probe` of the
# record) whether the function still matches. What the match does not need is gone. What it needs gets a
# `// !FAKE: <reason>` line. The trial edits bytes: what it does not change comes back as it went in (the encoding,
# the line ends). Nothing records a trial and no check asks for one: the marker is the record.
TRIAL_ENV = ("PSXD_TRIAL_FILE", "PSXD_TRIAL_FUNC", "PSXD_TRIAL_PATH")
PROBE_SECONDS = 600
MARK = re.compile(r"!FAKE:[ \t]*([^\n]*?)[ \t]*(?:\*/|$)", re.M)
BARRIER = re.compile(r"\b(?:asm|__asm__|__asm)\b\s*(?:(?:volatile|__volatile__|__volatile)\b\s*)?\(\s*\"(\s*)\"\s*\)\s*;")
PIN_CLAUSE = re.compile(r'\s*\b(?:asm|__asm__|__asm)\s*\(\s*"([^"\n]*)"\s*\)')   # what a trial cuts: the clause, nothing else
PIN_VAR = re.compile(r"([A-Za-z_]\w*)\s*$")
DECL_END = re.compile(r"[;{}]")
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


def _crutches(text: str, code: str) -> list[dict]:
    """The crutches of a text, in order, each with its marker: `crutches` without the function, the id and the hash.
    A marker covers one crutch: the one on its line, or the one on the line below when the marker stands alone."""
    plain = uncommented(text)
    found = []
    for m in PIN.finditer(code):                       # each `asm("…")` clause of the declaration is a pin of its own
        stop = DECL_END.search(code, m.end())
        clauses = list(PIN_CLAUSE.finditer(plain, m.start(), stop.start() if stop else len(code)))
        if not clauses or clauses[0].start() >= m.end():   # the clause is not one string in one pair of brackets
            found.append({"kind": "pin", "a": m.start(), "b": m.end(), "keep": None, "name": "pin:?:?"})
            continue
        lo = m.start()
        for n, cl in enumerate(clauses):
            var = PIN_VAR.search(plain[lo:cl.start()])
            found.append({"kind": "pin", "a": cl.start() if n else lo, "b": cl.end(), "keep": "" if n else text[lo:cl.start()],
                          "name": "pin:%s:%s" % (cl[1], var[1] if var else "?")})
            lo = cl.end()
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
    (the span that `drop` removes), keep (what it leaves; None for a pin whose clause this tool cannot read), reason
    (of its marker, None with none), mark (the line of that marker)}. Two crutches never share one marker."""
    scan = scan_file(rel, text)
    starts = [a for _, a, _ in scan["extents"]]
    seen: dict[tuple, int] = {}
    out = []
    for c in _crutches(text, PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), strip(text))):
        c = dict(c)
        i = bisect.bisect_right(starts, c["a"]) - 1
        c["func"] = scan["extents"][i][0] if i >= 0 and c["a"] < scan["extents"][i][2] else SCOPE
        n = seen[(c["func"], c["name"])] = seen.get((c["func"], c["name"]), 0) + 1
        c["id"] = c["name"] + (":%d" % n if c["kind"] != "pin" else "#%d" % n if n > 1 else "")
        out.append(c)
    return out


def drop(text: str, c: dict) -> str:
    """The text without one crutch and without its marker. A pin loses its `asm("$n")` clause and nothing else:
    `register T x asm("$n")` becomes `register T x`, whatever stands before the name. A barrier goes with its line
    when nothing else stands on it."""
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


def probe_of(tree: Tree) -> str | None:
    """The `[trial] probe` command of the record. The record and the scripts it names are protected files."""
    return record_table(tree, "trial").get("probe")


def variant_of(rel: str) -> str:
    """The path of the copy that a probe compiles: beside the tracked file, so its includes and its build rule hold."""
    f = pathlib.PurePosixPath(rel)
    return f.with_name("%s.psxd-trial%s" % (f.stem, f.suffix)).as_posix()


def trial_text(data: bytes):
    """(the text of a source as a trial edits it, the function that gives its bytes back), or a str that says why
    the file cannot be tried. The text is lossless: a byte that is no UTF-8 comes back as it was, and so do CRLF
    line ends. Mixed line ends and a lone CR are refused: no edit could keep them line for line."""
    crlf = b"\r\n" in data
    if b"\r" in data.replace(b"\r\n", b"") or crlf and data.count(b"\r\n") != data.count(b"\n"):
        return "mixed line ends or a lone CR: the trial edits a file line for line, with one kind of line end"
    text = data.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
    return text, lambda t: (t.replace("\n", "\r\n") if crlf else t).encode("utf-8", "surrogateescape")


def run_probe(repo, cmd: str, data: bytes, rel: str, func: str) -> int:
    """Ask the game's probe about one variant of a file (its bytes): 0 the function matches, 1 it does not, 2 the
    probe failed. The variant is a file beside the tracked one, so the tracked file is never the one that is
    compiled; a probe that changes the tracked file has failed, and so has one whose copy would stand on a file.
    The command gets three values, as `{file}`, `{func}` and `{path}` in its text or as three more arguments: the
    file to compile, the function, and the tracked path that the file stands for."""
    src = pathlib.Path(repo) / rel
    variant = pathlib.Path(repo) / variant_of(rel)
    if variant.exists() or variant.is_symlink():
        return 2
    before = src.read_bytes() if src.is_file() else None
    env = dict(os.environ, **dict(zip(TRIAL_ENV, (str(variant), func, rel))))
    line = cmd
    for key, var in zip(("{file}", "{func}", "{path}"), TRIAL_ENV):
        line = line.replace(key, '"$%s"' % var)
    if line == cmd:
        line += ' "$%s" "$%s" "$%s"' % TRIAL_ENV
    try:
        variant.write_bytes(data)
        r = subprocess.run(line, shell=True, cwd=str(repo), env=env, capture_output=True, text=True, timeout=PROBE_SECONDS)
        if (src.read_bytes() if src.is_file() else None) != before:
            return 2
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

    odd = [c for c in mine(text) if c["keep"] is None]
    if odd:
        stats["why"] = ("line %d: the tool cannot read the `asm(\"…\")` clause of this pin (one string, in one pair of "
                        "brackets), so it cannot try it" % (odd[0]["line"] + 1))
        return None, stats
    rc = probe(text)
    if rc != 0:
        stats["why"] = "it does not match as it is" if rc == 1 else "the probe failed (exit 2 or more, or it changed the tracked file)"
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
            if rc == 2:                            # an error is no `kept`: nothing was learned about this crutch
                stats["why"] = "the probe failed (exit 2 or more) on the text without %s" % mine(text)[i]["id"]
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


def cmd_trial(repo, file: str | None, func: str | None = None) -> int:
    """`trial FILE [--func NAME]`: try each crutch of a file's functions (of one function) and write the file."""
    repo = pathlib.Path(repo)
    tree = Tree(repo)
    cmd = probe_of(tree)
    if not cmd:
        print("TRIAL FAIL no [trial] probe in %s: the command that says whether one function of a file still matches "
              "(exit 0 match, 1 no match, 2 or more an error)" % RECORD)
        return 1
    try:
        rel = pathlib.Path(repo / file).resolve().relative_to(repo.resolve()).as_posix() if file else ""
    except ValueError:                                 # a path outside the repository
        rel = ""
    data = tree.raw(rel) if rel else None
    if data is None:
        print("TRIAL FAIL %s: no file of this repository (`trial <file> [--func <name>]`)" % (file or "no file"))
        return 1
    lossless = trial_text(data)
    if isinstance(lossless, str):
        print("TRIAL FAIL %s: %s" % (rel, lossless))
        return 1
    if (repo / variant_of(rel)).exists() or tree.has(variant_of(rel)):
        print("TRIAL FAIL %s: %s exists, and that is where the trial puts the copy that the probe compiles: move it"
              % (rel, variant_of(rel)))
        return 1
    text, to_bytes = lossless
    funcs = list(dict.fromkeys(c["func"] for c in crutches(rel, text) if c["func"] != SCOPE and c["kind"] != "goto"
                               and func in (None, c["func"])))
    total, bad = {"tried": 0, "removed": 0, "kept": 0, "probes": 0}, 0
    for name in funcs:
        new, stats = trial_function(text, rel, name, lambda t: run_probe(repo, cmd, to_bytes(t), rel, name))
        for k in total:
            total[k] += stats[k]
        if new is None:
            bad += 1
            print("TRIAL FAIL %s %s: %s" % (rel, name, stats["why"]))
            continue
        text = new
        print("TRIAL %s %s: %d tried, %d removed, %d kept" % (rel, name, stats["tried"], stats["removed"], stats["kept"]))
    if to_bytes(text) != data:
        (repo / rel).write_bytes(to_bytes(text))
    if not funcs:
        print("TRIAL OK %s%s: no pin and no barrier in a function" % (rel, " " + func if func else ""))
        return 0
    print("TRIAL %s (%d function(s), %d tried, %d removed, %d kept; %d probe(s))" % (
        "FAIL" if bad else "OK", len(funcs), total["tried"], total["removed"], total["kept"], total["probes"]))
    return 1 if bad else 0


# ---- the gate: every check of the floor in one command, at the commit, at the bank, before a push and in CI ---------
# A check holds only against something the change cannot rewrite. So each change is judged against the tree it starts
# from (`transition`): HEAD for a commit and a bank, the range's base in CI and before a push. The tree a change
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
    except (ValueError, RecursionError):               # no JSON, or JSON nested deeper than the reader goes
        return {"_broken": True}
    return conf if isinstance(conf, dict) else {"_broken": True}


def _hook_rows(conf: dict) -> list[tuple[str, str, frozenset, str]]:
    """[(event, the hook entry as JSON, the tools of its matcher, the matcher)] for each hook of a settings file that
    runs one of psxdecomp's tools. The tools: the names that `|` joins. A matcher of any other form (a pattern, a
    bracket) has no tools here: it holds only as the same text."""
    out = []
    hooks = conf.get("hooks") if isinstance(conf.get("hooks"), dict) else {}
    for event, groups in hooks.items():
        for g in groups if isinstance(groups, list) else ():
            for h in g["hooks"] if isinstance(g, dict) and isinstance(g.get("hooks"), list) else ():
                if isinstance(h, dict) and "psxd_" in str(h.get("command", "")):
                    matcher = g.get("matcher", "") if isinstance(g.get("matcher", ""), str) else json.dumps(g.get("matcher"))
                    names = frozenset(matcher.split("|")) if re.fullmatch(r"\w+(?:\|\w+)*", matcher) else frozenset()
                    out.append((event, json.dumps(h, sort_keys=True), names, matcher))
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
        for event, entry, tools, matcher in _hook_rows(old):
            if not any(e == event and h == entry and (m == matcher or tools and tools <= t) for e, h, t, m in have):
                out.append("%s lost a hook of %s (or a tool of its matcher): %s" % (SETTINGS, event, json.loads(entry).get("command")))
        listed = lambda c: (c.get("permissions") if isinstance(c.get("permissions"), dict) else {}).get("deny")  # noqa: E731
        deny = lambda c: listed(c) if isinstance(listed(c), list) else []  # noqa: E731
        if deny(old) and not isinstance(listed(new), list):    # a string or a table that holds the rules' text holds no rule
            out.append("%s: `permissions.deny` is no list any more, so no deny rule holds" % SETTINGS)
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
    env = lambda c: c.get("env") if isinstance(c.get("env"), dict) else {}  # noqa: E731
    if not new.get("_broken") and env(new) != env(old):   # any variable: one can move the project folder, another can still a hook
        moved = sorted(k for k in set(env(new)) | set(env(old)) if env(new).get(k) != env(old).get(k))
        out.append("%s changes %s in `env`: a hook reads its surroundings from there" % (SETTINGS, ", ".join(map(str, moved))))
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
    def raises(tree):                                  # as `parse_baseline` reads them: no second reader of that file
        try:
            bl = parse_baseline(tree.read(BASELINE))
        except Fail:
            return []
        return ["raise %s %d %s %s" % r for r in bl.raises] + [l for l in bl.other if l.startswith("raise ")]

    out, had = [], raises(base)
    for l in raises(head):                             # one for one: a second copy of a line is a second raise
        if l in had:
            had.remove(l)
        else:
            out.append("`%s` in %s" % (l, BASELINE))
    had = lines(base.read(ASM_EVIDENCE))
    for l in lines(head.read(ASM_EVIDENCE))[1:]:
        if l in had:
            had.remove(l)
        elif l.strip() and not l.startswith("#"):
            out.append("the row of %s in %s" % (" ".join(l.split("\t")[1:3]), ASM_EVIDENCE))
    return out


def _sibling_run(repo, *args) -> tuple[int, list[str]]:
    """(the exit code, the output lines) of psxdecomp's other tool, the copy beside this file. 127 when none is there."""
    if not sibling().is_file():
        return 127, ["no %s beside %s" % (sibling().name, pathlib.Path(__file__).name)]
    r = subprocess.run([sys.executable, "-I", str(sibling()), *args], cwd=str(repo), capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).splitlines()


def _source_args(tree: Tree) -> list[str]:
    return [] if tree.source is None else ["--staged"] if tree.source == INDEX else ["--rev", tree.source]


def transition(repo, base: Tree, head: Tree, online: bool = False) -> tuple[list, list, bool]:
    """([(check, detail)], the INFO lines, a tool was replaced) for the change from the tree `base` to `head`: the
    two ends of a change decide, whatever the commits between them hold."""
    fails, infos = admission(repo, base, head)
    found, more, replaced = protected_findings(base, head, online)
    found += ["policy: " + d for ck, d in fails if ck == "policy"]       # a change of the policy is a protected change
    fails = [f for f in fails if f[0] != "policy"]
    other = parse_baseline(base.read(BASELINE)).other
    slack = sum(int(m[1]) for l in parse_baseline(head.read(BASELINE)).other if l not in other
                for m in [re.fullmatch(r"raise protected (\d{1,9}) \S+ \S.*", l)] if m)
    infos += more
    if found and len(found) <= slack:
        infos += ["protected, and a `raise protected` line of the change allows it: %s" % f for f in found]
    else:
        fails += [("policy", f[8:]) if f.startswith("policy: ") else ("protected", f) for f in found]
    rc, lines = _sibling_run(repo, "style", *_source_args(head), "--against", base.source, "--repo", str(repo))
    if rc:
        fails += [("style", l[11:]) for l in lines if l.startswith("STYLE FAIL ")] or [
            ("style", "exit %d: %s" % (rc, (lines or ["no output"])[-1]))]
    return fails, infos, replaced


def state(repo, tree: Tree, here: bool = True, base: Tree | None = None) -> tuple[list[tuple[str, str]], list[str]]:
    """([(check, detail)], the warnings) for a tree as it stands: its baseline, its ledgers (`base`: the tree the
    change starts from, whose ledger rows are not opened again), and (`here`: the work tree holds this tree) its
    plan, its toolchain pins, its README and its category ids. A finding about a name is a warning."""
    out = [("debt", f) for f in state_findings(repo, tree)[0]]
    found = names_findings(repo, tree, base)
    out += [("names", d) for lv, d in found if lv == "FAIL"]
    warns = ["names: %s" % d for lv, d in found if lv == "WARN"]
    if not here:
        return out, warns
    out += own_debt(repo, tree)
    out += [("plan", "%s: %s" % (ck, d)) for lv, ck, d in lint_plan(repo) if lv == "FAIL"]
    out += [("toolchain", "%s: %s" % (name, d)) for st, name, d in toolchain_rows(repo) or () if st == "FAIL"]
    for check, rel, args in (("readme", "README.md", ["lint", "README.md"]),
                             ("categories", "config/categories.tsv", ["categories", "config/categories.tsv", "--history"])):
        if tree.has(rel):
            rc, lines = _sibling_run(repo, *args, "--repo", str(repo))
            if rc:
                out += [(check, l) for l in lines if " FAIL " in l or " ERROR " in l][:20] or [(check, "exit %d" % rc)]
    return out, warns


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


def cmd_gate(repo, mode: str, rng: str | None = None, part: str = "all") -> int:
    """`gate --staged | --bank | --ci <base>..<head> | --push [<base>..<head>]`: `GATE FAIL <check>: <detail>` lines and
    one last line, `GATE OK` or `GATE FAIL`; exit 1 on a FAIL. `--bank` also counts the source files that git does not
    track yet, writes the rows of the baseline when the change is admitted, and runs the game's own check. `--ci`
    judges the head of the range against its base."""
    repo = pathlib.Path(repo).resolve()
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
    global _cpp_cache_on
    _cpp_cache_on = mode in ("staged", "bank")         # a push and CI run every unit: no file of this machine vouches
    try:
        if mode in ("staged", "bank"):
            head = Tree(repo, INDEX) if mode == "staged" else Tree(repo, None, untracked=True)
            base = Tree(repo, "HEAD") if _rev(repo, "HEAD") else None
            args = ["--" + mode]
        else:
            named, _, tip = (rng or "").partition("..")
            tip = _rev(repo, tip or "HEAD")
            if tip is None:
                raise Fail("%s names no commit: `gate --%s <base>..<head>`" % (rng, mode))
            first = _rev(repo, named) if named and set(named) != {"0"} else None
            if named and set(named) != {"0"} and first is None:
                raise Fail("the base %s names no commit of this repository: nothing would judge the change" % named)
            if first is None and mode == "push" and not rng:
                first = _rev(repo, "@{upstream}")
            n = len(_git(repo, "rev-list", tip, "^" + first).stdout.split()) if first else 0
            what = "%s; %d commit(s)%s" % (mode, n, "" if first else "; no base: the tree of the head only")
            head, base = Tree(repo, tip), Tree(repo, first) if first else None
            args = ["--" + mode, "%s..%s" % (first or "0" * 40, tip)]
        replaced = False
        if part == "all" and base is not None:
            fails, infos, replaced = transition(repo, base, head, mode in ("ci", "push"))
            acts = developer_acts(base, head)
            if mode in ("staged", "bank"):
                if acts and os.environ.get("CLAUDECODE"):
                    fails += [("raise", "%s is new, and this is an agent session (CLAUDECODE is set): the developer adds it and "
                               "commits it from a terminal" % a) for a in acts]
                infos += ["the developer's act, new in this change: %s" % a for a in acts]
            else:                                      # the pre-push hook asks the developer about each one
                warns += ["the developer's act, new in this change: %s" % a for a in acts]
        elif part == "all" and mode in ("staged", "bank"):
            infos.append("no commit yet: nothing to judge the change against")
        if mode == "bank" and not fails:
            st = state_findings(repo, head)[1]
            if st["baseline"].version == 2 and (st["rise"] or st["stale"]):
                _write_baseline(repo, baseline_text(st["baseline"], st["counts"]))
                infos.append("%s: the rows of now written (%d rose, %d fell)" % (BASELINE, len(st["rise"]), len(st["stale"])))
                head = Tree(repo, None, untracked=True)
        passed = _handover(repo, head, args + ["--part", "state"]) if replaced and not fails else None
        if passed is None:
            here = mode in ("staged", "bank") or _rev(repo, "HEAD") == head.source
            if not here:
                infos.append("the work tree is not at %s: its plan, README and category ids are not read" % head.source[:10])
            found, more = state(repo, head, here, base)
            fails, warns = fails + found, warns + more
            if mode in ("bank", "push") and not fails:
                fails += game_check(repo, head)
    except Fail as e:
        fails.append(("gate", str(e)))
    except Exception as e:                             # a check that cannot run passes nothing
        fails.append(("gate", "the tool failed (%s: %s): nothing was judged" % (type(e).__name__, " ".join(str(e).split())[:200])))
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
    "asm, the word in a macro (in raw text: once, at the definition)": ('#define PIN(r) asm(r)\nvoid Walk(void) {\n    register s32 i PIN("$16");\n}\n', {"asm": 1}),
    "cast": ("void Walk(Obj *p, s32 a) {\n    a = (s32)&p->next;\n    p = (Obj *)(s32)a;\n    a = (s32)(u8 *)p;\n}\n", {"cast": 3}),
    "field": ("s32 Walk(Obj *p) {\n    return p->unk_10 + p->field_0x14 + p->unk3C + p->hp;\n}\n", {"field": 3}),
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
    check("a file-scope asm statement of directives is no debt, an instruction in a function is", file_debt("include/common.h", plumbing) == {"asm": 1}
          and file_debt("src/a.c", plumbing) == {"asm": 1}, file_debt("include/common.h", plumbing))
    shared = _macros(strip("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\n"))
    check("a header's offset macro counts at each use", file_debt("src/a.c", "s32 Walk(void *p) {\n    return HP(p);\n}\n", shared)
          == {"offset": 1})
    check("unbased: a function with no row", file_debt("src/a.c", C_CLEAN, based=set()) == {"unbased": 1})
    check("unbased: a function with a row", file_debt("src/a.c", C_CLEAN, based={"Player_Hp"}) == {})
    bl = parse_baseline("# top\nmode goto down\nmode pin count\nmode shift down\n3 shift src/a.c\n"
                        "raise goto 2 2026-01-02 the first wave\nskip src/vendor/\n1 goto src/a.c\n# a note below a row\n")
    check("the baseline: its lines, and the lines of a kind this tool does not know", bl.version == 2
          and bl.head == ["# top", "# a note below a row"] and bl.policy("goto") == "down"
          and bl.policy("pin") == "count" and bl.other == ["mode shift down", "3 shift src/a.c"]
          and bl.raises == [("goto", 2, "2026-01-02", "the first wave")] and bl.lacks()[:2] == ["pin-unmarked", "goto-unmarked"], vars(bl))
    check("the baseline is written as it was read", baseline_text(bl) == "# top\n# a note below a row\nmode pin count\n"
          "mode goto down\nmode shift down\n3 shift src/a.c\nraise goto 2 2026-01-02 the first wave\nskip src/vendor/\n"
          "1 goto src/a.c\n", baseline_text(bl))
    early = parse_baseline("mode offset admit-new\nbudget pin 30 base 4 10 20\nmode asm down\n")
    check("the baseline: the lines of an unreleased build are read as `count`", (early.policy("offset"), early.policy("pin"),
          early.policy("asm")) == ("count", "count", "down"), early.modes)
    for name, text, want in (("two rows of one pair", "1 goto src/a.c\n1 goto src/a.c\n", "has two rows"),
                             ("two policy lines of one kind", "mode goto down\nmode goto count\n", "two policy lines"),
                             ("a second mode line of version 1", "mode down\nmode admit\n", "a second `mode` line"),
                             ("the two versions in one file", "mode admit\nmode goto down\n", "of version 1 beside"),
                             ("a count too long to be a number", "%s goto src/a.c\n" % ("9" * 5000), ":1: not `<count> <kind> <path>`"),
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
        (repo / "src" / "stubs.c").write_text('INCLUDE_ASM("asm/nonmatchings/a", Run);\nINCLUDE_ASM("asm/nonmatchings/a", Jump);\n')
        (repo / "src" / "boot.s").write_text("nop\n")
        (repo / "include" / "include_asm.h").write_text("#define INCLUDE_ASM(d, n) __asm__(\".include \\\"n\\\"\");\n")
        _git(repo, "add", "src", "include")
        run = lambda *a, **kw: _capture(cmd_debt, repo, *a, **kw)  # noqa: E731
        judge = lambda base, head=None: admission(repo, Tree(repo, base), Tree(repo, head))[0]  # noqa: E731
        walk, base_file = repo / "src" / "walk.c", repo / BASELINE
        again = C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;")
        rc, out = run()
        check("no baseline: the totals, and a failure", rc == 1 and "totals: goto 1, asm 1 " in out
              and "DEBT FAIL no config/debt-baseline.txt: `python3 tools/psxd_floor.py debt --recount` writes it" in out, out)
        rc, out = run(update=True)
        check("--update writes no first baseline", rc == 1 and not base_file.exists(), out)
        text = first_baseline(repo)
        check("the first baseline: a policy line per kind and the rows; the stub macro's header is read, and holds no debt", text.startswith(
            "# config/debt-baseline.txt: ") and text.endswith(
            "mode pin count\nmode pin-unmarked down\nmode goto count\nmode goto-unmarked down\nmode barrier count\n"
            "mode barrier-unmarked down\nmode offset count\nmode address count\nmode cast count\nmode field count\n"
            "mode macro count\nmode asm down\nmode placeholder count\nmode placeholder-use count\n"
            "mode unbased count\nmode struct count\nmode extern count\nmode filename count\nmode flag count\n"
            "mode reservation count\n1 asm src/boot.s\n1 goto src/walk.c\n"), text)
        rc, out = run(recount=True)
        check("--recount writes it", rc == 0 and base_file.read_text() == text and "DEBT RECOUNT written" in out
              and "DEBT INFO policy written: pin: count\n" in out, out)
        rc, out = run()
        check("an equal baseline passes", rc == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); down: pin-unmarked, goto-unmarked, "
              "barrier-unmarked, asm; count: pin, goto, barrier, offset, address, cast, field, macro, placeholder, "
              "placeholder-use, unbased, struct, extern, filename, flag, reservation)" in out, out)
        _git(repo, "add", "config")
        _commit(repo, "the floor")
        # a kind in mode `count` is counted and shown: the rows follow the tree, and nothing is refused
        walk.write_text(again)
        rc, out = run()
        check("a rise fails the equality of rows and counts, and names the command", rc == 1
              and "DEBT FAIL rise goto src/walk.c: 2, its row is 1\n" in out
              and "debt --update`, then commit config/debt-baseline.txt" in out, out)
        check("a counted kind is never refused", not judge("HEAD"), judge("HEAD"))
        rc, out = run(update=True)
        check("--update writes the rows of a counted kind", rc == 0 and "DEBT INFO goto src/walk.c: 1 -> 2\n" in out
              and "2 goto src/walk.c\n" in base_file.read_text() and run()[0] == 0, out)
        try:
            with open(os.devnull, "w") as null, contextlib.redirect_stderr(null):
                main(["debt", "--update", "--admit", "--repo", str(repo)])
            check("--admit is no flag", False)
        except SystemExit as e:
            check("--admit is no flag: exit 2", e.code == 2, e.code)
        base_file.write_text(text)
        walk.write_text(C_DEBT["goto"][0])
        # a `down` kind: the total of the tree never rises, wherever the construct stands and whatever the rows say
        unmarked = C_DEBT["pin-unmarked"][0].replace("Walk", "Run")
        walk.write_text(C_DEBT["goto"][0] + unmarked)
        base_file.write_text(text + "1 pin src/walk.c\n1 pin-unmarked src/walk.c\n")
        rc, out = run()
        check("a row written by hand is equal to the tree", rc == 0, out)
        rc, out = run(against="HEAD")
        check("and the change is refused all the same", rc == 1 and "DEBT FAIL debt: pin-unmarked is `down` and its total rose: "
              "0 -> 1 (src/walk.c 0 -> 1)\n" in out and "1 finding(s) against HEAD" in out, out)
        base_file.write_text(text)
        rc, out = run(update=True)
        check("--update refuses a rise of a `down` kind", rc == 1 and base_file.read_text() == text and "DEBT UPDATE refused" in out, out)
        (repo / "src" / "far.c").write_text(unmarked.replace("Run", "Far"))
        _git(repo, "add", "src/far.c")
        check("a rise in two files names both", [f[1] for f in judge("HEAD")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 2 (src/far.c 0 -> 1, src/walk.c 0 -> 1)"], judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0] + C_DEBT["pin"][0].replace("Walk", "Run"))
        check("a marked pin is counted, not refused", [f[1] for f in judge("HEAD")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 1 (src/far.c 0 -> 1)"], judge("HEAD"))
        _git(repo, "rm", "-q", "-f", "--cached", "src/far.c")
        (repo / "src" / "far.c").unlink()
        check("with a reason on each pin the change passes", not judge("HEAD"), judge("HEAD"))
        # a `raise` line is the developer's
        walk.write_text(C_DEBT["goto"][0] + unmarked)
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
        walk.write_text(walk.read_text() + unmarked.replace("Run", "Jump"))
        check("a `raise` line admits one change, not the next", len(judge("HEAD")) == 1, judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0] + unmarked.replace("Run", "Jump").replace("s32 i", "s32 j"))
        check("one unmarked pin in the place of another: the total did not rise", not judge("HEAD"), judge("HEAD"))
        walk.write_text(C_DEBT["goto"][0] + unmarked)
        # the policy that judges a change is the one it starts from
        mine = base_file.read_text()
        for name, text2, want in (
                ("a policy line taken out", mine.replace("mode pin-unmarked down\n", ""), "the policy line of pin-unmarked is gone (it was down)"),
                ("a weaker mode", mine.replace("mode pin-unmarked down", "mode pin-unmarked count"),
                 "pin-unmarked went from down to count: a mode only gets stronger"),
                ("a new skip line", mine + "skip src/\n", "a new `skip` line (src/)")):
            base_file.write_text(text2)
            got = judge("HEAD")
            check("policy: " + name, ("policy", want) in got, got)
        base_file.unlink()
        check("policy: a deleted baseline", judge("HEAD") == [("policy", "config/debt-baseline.txt is gone")], judge("HEAD"))
        base_file.write_text(mine.replace("mode offset count", "mode offset down"))
        check("policy: a stronger mode passes", not judge("HEAD"), judge("HEAD"))
        base_file.write_text(mine)
        rc, out = run(down="goto")
        check("--down switches one kind", rc == 0 and "mode goto down\n" in base_file.read_text()
              and "mode pin count" in base_file.read_text(), out)
        rc, out = run(down="all")
        check("--down switches every kind", rc == 0 and parse_baseline(base_file.read_text()).summary() == "down: " + ", ".join(KINDS), out)
        check("--down of a kind that is no kind", run(down="gotos")[0] == 1)
        base_file.write_text(mine)
        # a recount writes rows and policy lines; it admits nothing that a `down` kind refuses
        walk.write_text(walk.read_text() + unmarked.replace("Run", "Jump"))
        rc, out = run(recount=True)
        check("--recount admits no rise of a `down` kind", rc == 1 and "DEBT RECOUNT refused" in out and base_file.read_text() == mine, out)
        walk.write_text(again)
        base_file.write_text("mode admit\nskip include/include_asm.h\n1 asm src/boot.s\n# a note of the game\n")
        _git(repo, "add", "-A")
        _commit(repo, "the baseline of an older psxdecomp")
        rc, out = run()
        check("a version 1 baseline fails and names the command", rc == 1 and "is a version 1 file (`mode admit`): run "
              "`python3 tools/psxd_floor.py debt --recount`" in out, out)
        rc, out = run(recount=True)
        new = base_file.read_text()
        check("--recount makes it version 2 and keeps the game's own lines", rc == 0 and "# a note of the game\n" in new
              and "mode goto count\n" in new and "skip include/include_asm.h\n" in new and "mode admit\n" not in new
              and new.count("# ") == len(BASELINE_HEAD) + 1 and run()[0] == 0, out + new)
        base_file.write_text(new.replace("mode goto count", "budget goto 12 base 1 2 11").replace("mode offset count", "mode offset admit-new")
                             .replace(BASELINE_HEAD[3], "A policy line gives each kind its mode: `down` (never rises), `admit-new` (debt arrives only with a new function"))
        rc, out = run(recount=True)
        check("--recount writes the lines of an unreleased build as `count`, and the head of now", rc == 0 and base_file.read_text() == new, base_file.read_text())
        _git(repo, "add", "-A")
        _commit(repo, "version 2")
        # the two ends of a range decide: a body that leaves and comes back with more debt is counted, and not refused
        walk.write_text('INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
        run(update=True)
        _git(repo, "add", "-A")
        _commit(repo, "the body leaves")
        walk.write_text(again + unmarked)
        check("a `down` kind that rose over a range is refused at its ends", [f[1] for f in judge("HEAD~1")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 1 (src/walk.c 0 -> 1)"], judge("HEAD~1"))
        walk.write_text(again)
        rc, out = run(update=True)
        _git(repo, "add", "-A")
        _commit(repo, "the body is back")
        check("a counted kind over a range passes", rc == 0 and not judge("HEAD~2", "HEAD"), out)
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
        check("names: every function is unbased at first, and no name is required", "NAMES INFO 2 function(s) defined" in out
              and "A name is never required to bank or to push" in out, out)
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
              and [f[1] for f in found if f[0] != "INFO"] == ["config/names.tsv: Name0 has two rows that are not rejected"]
              and [f[0] for f in found if f[0] != "INFO"] == ["WARN"], [f for f in found if f[0] != "INFO"][:2])
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
            check("names: a warning, never a failure: " + name, rc == 0 and "NAMES WARN " in out and want in out
                  and "NAMES OK (0 finding(s), 1 warning(s))" in out, out)
        _git(repo, "add", "config", "include")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet",
             "-m", "a row that points at nothing")
        rc, out = _capture(cmd_names, repo, against="HEAD")
        check("names --against: a row that the base holds is not opened again", rc == 0 and "only the rows that are new since HEAD" in out, out)
        check("names --rev: the ledger of a revision", "NAMES WARN " in _capture(cmd_names, repo, source="HEAD")[1])
        (repo / "extracted").mkdir()                   # an ignored folder that this machine has: its files are opened
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + good)
        rc, out = _capture(cmd_names, repo)
        check("names: evidence in a folder that git does not hold is opened where the folder is", rc == 0
              and "NAMES WARN config/names.tsv: line 6: the evidence of g_Mode points at nothing: extracted/map.txt is no file of this tree" in out, out)
        (repo / "extracted" / "map.txt").write_text("x\n" * 7)
        check("names: and it is clean when the file is there", "NAMES WARN" not in _capture(cmd_names, repo)[1])
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
        check("names: a bad decision and a bad evidence class are warnings", rc == 0 and "decision 'sure'" in out and "evidence 'guess:" in out
              and "2 warning(s)" in out, out)
        for cls in ("human", "test", "oracle", "debugger"):
            (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("string:src/clean.c:4", cls + ":docs/boot.md:3"))
            rc, out = _capture(cmd_names, repo)
            check("names: the evidence class `%s`" % cls, rc == 0 and "NAMES WARN" not in out and "1 accepted" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row.replace("string:src/clean.c:4", "string:"))
        rc, out = _capture(cmd_names, repo)
        check("names: evidence with no path and no line", rc == 0 and "NAMES WARN" in out and "evidence 'string:'" in out, out)
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
                                        {SCOPE: {"offset": 1}, "B": {}}),
    "a definition by a macro is file scope": ("HANDLER(A) {\nx:\n    goto x; // !FAKE: the loop\n}\nvoid B(void) {\n}\n",
                                               {SCOPE: {"goto": 1}, "B": {}}),
    "an #if with two heads is one body": (
        "#ifdef VERSION_JP\ns32 A(s32 a) {\n#else\ns32 A(void) {\n#endif\nx:\n"
        "    goto x; // !FAKE: the loop\n}\nvoid B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "an #if with two heads and the brace behind its #endif": (
        "#ifdef VERSION_JP\ns32 A(s32 a)\n#else\ns32 A(void)\n#endif\n{\nx:\n"
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


# A preprocessor for the self-test, so that it needs none on the machine: it follows `#include "…"`, replaces the
# object-like macros it has read, prints a line marker at each change of file, and blanks every other directive. With
# PSXD_SELF_CPP_LOG set it writes each unit it is run for into that file.
CPP_SELF = r'''import os, re, sys
defs = {}
def emit(path, out):
    out.append('# 1 "%s"' % path)
    for n, line in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        inc = re.match(r'\s*#\s*include\s*"([^"]+)"', line)
        define = re.match(r"\s*#\s*define\s+(\w+)\s+(.*)", line)
        if inc:
            found = next((p for p in (os.path.join(os.path.dirname(path), inc[1]), os.path.join("include", inc[1])) if os.path.isfile(p)), None)
            if found is None:
                sys.exit("%s:%d: fatal error: %s: No such file or directory" % (path, n, inc[1]))
            emit(os.path.normpath(found), out)
            out.append('# %d "%s" 2' % (n + 1, path))
        elif define:
            defs[define[1]] = define[2]
            out.append("")
        elif line.lstrip().startswith("#"):
            out.append("")
        else:
            for name, body in defs.items():
                line = re.sub(r"\b%s\b" % name, body, line)
            out.append(line)
if os.environ.get("PSXD_SELF_CPP_LOG"):
    open(os.environ["PSXD_SELF_CPP_LOG"], "a").write(sys.argv[1] + "\n")
out = []
emit(sys.argv[1], out)
print("\n".join(out))
'''


def self_test_files(check) -> None:
    """Which files count, the kinds that a file's text alone does not decide, and the keyword kinds in the view of the
    game's preprocessor."""
    for path, want in (("src/a.c", True), ("include/a.h", True), ("lib/libgte/a.c", True), ("Src/A.C", True), ("game/a.cpp", True),
                       ("src/body.inc", True), ("src/boot.S", True), ("src/boot.asm", True), ("asm/main/a.s", False),
                       ("tools/host.c", False), ("build/a.c", False), ("refs/x/a.c", False), (".run/a.c", False),
                       ("src/.cache/a.c", False), ("docs/a.md", False), ("src/a.txt", False)):
        check("a counted file: %s" % path, is_source(path) == want)
    plumbing = '__asm__(".include \\"macro.inc\\"\\n");\n__asm__(".macro glabel label\\n.global \\\\label\\n\\\\label:\\n.endm\\n");\n'
    stub = '__asm__(".pushsection .text\\n\\t.align\\t2\\n\\t.set noreorder\\n\\t.set noat\\n.include \\"asm/a/Run.s\\"\\n\\t.set reorder\\n\\t.set at\\n.popsection");\n'
    for name, text, want in (
            ("a file-scope asm statement of assembler directives is the stub's plumbing, in a header and in a C file", plumbing, {}),
            ("an expanded stub is no debt", stub, {}),
            ("an instruction in a file-scope asm statement is assembly", '__asm__(".text\\nFast:\\n    jr $ra\\n nop\\n");\n', {"asm": 1}),
            ("data in a file-scope asm statement is assembly", '__asm__(".section .text\\n.word 0x03E00008\\n");\n', {"asm": 1}),
            ("a file pulled in as bytes is assembly", '__asm__(".incbin \\"blob.bin\\"");\n', {"asm": 1}),
            ("the use of an assembler macro is an instruction", '__asm__(".macro ret\\n jr $ra\\n.endm\\nret\\n");\n', {"asm": 1}),
            ("an asm statement that is no string is assembly", "__asm__(TEXT);\n", {"asm": 1}),
            ("assembler directives inside a function force the compiler: a barrier", 'void A(void) {\n    __asm__(".set noreorder");\n}\n',
             {"barrier": 1, "barrier-unmarked": 1}),
            ("an empty asm statement with another volatile spelling is a barrier", 'void A(void) {\n    __asm__ __volatile("");\n}\n',
             {"barrier": 1, "barrier-unmarked": 1}),
            ("a goto as an argument", "void A(s32 n) {\nl:\n    DO(goto, l);\n}\n", {"goto": 1, "goto-unmarked": 1}),
            ("a computed goto", "void A(void *p) {\n    goto *p;\n}\n", {"goto": 1, "goto-unmarked": 1}),
            ("a goto with a reason", "void A(void *p) {\n    // !FAKE: the jump table of the original\n    goto *p;\n}\n", {"goto": 1}),
            ("offsets with a minus and a negative index",
             "s32 A(u8 *p) {\n    return *(s32 *)(p - 4) + *(s32 *)((u8 *)p - 8) + ((s32 *)p)[-2];\n}\n", {"offset": 3}),
            ("the integer types of the SDK in a cast of a pointer",
             "u_long A(void *p) {\n    return (u_long)&p + (u_int)(s32 *)p + *(s32 *)(ulong)p + *((u_char *)p + 4);\n}\n", {"cast": 3, "offset": 1})):
        for rel in ("src/a.c", "include/a.h"):
            got = file_debt(rel, text)
            check("%s (%s)" % (name, rel), got == want, got)
    import time
    t0 = time.time()
    file_debt("src/slow.c", "s32 A(void) {\n    return *(" + "a " * 4000 + ");\n}\n" + "".join("#define M%d M%d\n" % (i, i + 1) for i in range(400)))
    check("a long run of words and a long chain of macros cost no more than a second", time.time() - t0 < 1.0, time.time() - t0)
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        unmarked = C_DEBT["goto-unmarked"][0]
        for rel in ("src/walk.c", "lib/walk.c", "asm/walk.c", "tools/walk.c", "src/func_80012344.c", "src/misc12.c"):
            put(rel, unmarked.replace("Walk", "W_" + re.sub(r"\W", "_", rel)))
        put("src/hand.asm", "nop\n")
        _git(repo, "add", "-A")
        got = debt_bodies(repo)
        check("code in any folder counts; the splitter's and the tools' folders do not", sorted(got) == [
            "lib/walk.c", "src/func_80012344.c", "src/hand.asm", "src/misc12.c", "src/walk.c"], sorted(got))
        check("a file named by an address or a number", got["src/func_80012344.c"][SCOPE] == {"filename": 1}
              and got["src/misc12.c"][SCOPE] == {"filename": 1} and SCOPE not in got["src/walk.c"], got["src/misc12.c"])
        check("an assembly file by another suffix", got["src/hand.asm"] == {SCOPE: {"asm": 1}}, got["src/hand.asm"])
        _commit(repo, "the tree")
        check("a revision and the index hold the same files", debt_bodies(repo, tree=Tree(repo, "HEAD")) == got
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
        put("tools/flags.py", "import sys\nsys.exit(4)\n")
        try:
            debt_bodies(repo)
            check("a lister that fails is a refusal", False)
        except Fail as e:
            check("a lister that fails is a refusal", "exited 4" in str(e), str(e))
        # a macro of a header and of an included C file that hides an offset counts where it is used
        put("tools/flags.py", "")
        put("src/shared/mac.c", "#define FIELD4(p) (*(s32 *)((p) + 4))\n")
        put("src/id.c", '#include "shared/mac.c"\ns32 Kept(s32 n) {\n    return FIELD4(n);\n}\n')
        got = debt_bodies(repo, tree=Tree(repo, None, untracked=True))["src/id.c"]
        check("a macro of an included C file that hides an offset counts where it is used", got["Kept"] == {"offset": 1}, got)
    self_test_view(check)


def self_test_view(check) -> None:
    """The keyword kinds in the view of the game's preprocessor: what a macro, an include of any file and a second
    unit do to the count, the three sources of a tree, a unit that cannot be read, and what one change costs."""
    out = '# 1 "src/u.c"\nvoid A(void) {\n# 1 "src/frag.def" 1\n    goto x;\n# 3 "src/u.c" 2\n    go\\\nto y; register int r\n# 1 "include/pin.h" 1\n asm("$4");\n# 5 "src/u.c" 2\n}\n'
    hits, files = unit_view(out, "src/u.c", "/nowhere")
    check("the view: each hit has the file and the line of its first character", hits == {
        ("goto", "src/frag.def", 0): 1, ("pin", "src/u.c", 3): 1} and files == {"src/u.c", "src/frag.def", "include/pin.h"}, (hits, files))
    twice = '# 1 "src/u.c"\n# 1 "src/t.c" 1\ngoto a; goto b;\n# 2 "src/u.c" 2\n# 1 "src/t.c" 1\ngoto a; goto b;\n# 3 "src/u.c" 2\n'
    check("the view: a file that a unit includes twice is read once", unit_view(twice, "src/u.c", "/nowhere")[0] == {("goto", "src/t.c", 0): 2})
    check("the view: marks cover one construct each, on the line or alone above it", marked(
        [("goto", 3), ("goto", 3), ("pin", 5), ("asm", 7)], {2: ("the loop", True), 5: ("", False)}) == [
        ("goto", 3), ("goto", 3), ("goto-unmarked", 3), ("pin", 5), ("pin-unmarked", 5), ("asm", 7)])
    saved = os.environ.get("PSXD_SELF_CPP_LOG")
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        log = pathlib.Path(td + ".cpp.log")
        os.environ["PSXD_SELF_CPP_LOG"] = str(log)

        def ran() -> list[str]:
            got = sorted(log.read_text().split()) if log.is_file() else []
            log.unlink(missing_ok=True)
            return got

        cpp = "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = '%s tools/cpp.py {file}'\n" % sys.executable
        put("tools/cpp.py", CPP_SELF)
        put("include/m.h", "#define AGAIN goto again\n")
        put("src/unit.c", '#include "m.h"\n#include "shared/body.c"\ns32 Two(s32 n) {\n#include "pins.def"\n    return n;\n}\n')
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    if (n--) AGAIN;\n    return n;\n}\n")
        put("src/pins.def", '    register s32 t asm("$17");\n')
        put("src/other.c", '#include "m.h"\n#include "shared/body.c"\n')
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n;\n}\n")
        _git(repo, "add", "-A")
        raw = debt_counts(repo)
        check("no [floor] cpp: the raw text shows the macro's goto at its definition, and no file of another suffix", raw == {
            ("goto", "include/m.h"): 1, ("goto-unmarked", "include/m.h"): 1}, raw)
        put(RECORD, cpp)
        _git(repo, "add", "-A")
        want = {("goto", "src/shared/body.c"): 1, ("goto-unmarked", "src/shared/body.c"): 1,
                ("pin", "src/pins.def"): 1, ("pin-unmarked", "src/pins.def"): 1}
        got = debt_counts(repo)
        check("[floor] cpp: a goto behind a macro counts where it is used, a pin in a file of any suffix where it stands, "
              "and a file that two units read once", got == want, got)
        check("the view: the units are the C files that no other unit read", ran() == ["src/alone.c", "src/other.c", "src/unit.c"])
        _commit(repo, "the tree")
        for name, src in (("the index", INDEX), ("a revision", "HEAD"), ("the work tree with the files git does not track", None)):
            tree = Tree(repo, src, untracked=src is None)
            check("the view: %s gives the same count" % name, debt_counts(repo, tree=tree) == want, debt_counts(repo, tree=tree))
        check("the view: no unit ran again, each result was kept beside the files it read", ran() == [], "ran")
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    // !FAKE: the loop of the original\n    if (n--) AGAIN;\n    return n;\n}\n")
        got = debt_bodies(repo)
        check("the view: a marker in the file that holds the line covers the construct", got["src/shared/body.c"] == {"One": {"goto": 1}}
              and got["src/pins.def"] == {SCOPE: {"pin": 1, "pin-unmarked": 1}}, got)
        check("the view: one changed file costs the units that read it", ran() == ["src/other.c", "src/unit.c"])
        put("src/alone.c", 's32 Alone(s32 n) {\n    __asm__("nop");\n    return n;\n}\n')
        check("the view: an asm statement in a function", debt_counts(repo).get(("asm", "src/alone.c")) == 1 and ran() == ["src/alone.c"])
        put(ASM_EVIDENCE, "\t".join(ASM_COLUMNS) + "\nmain\tAlone\tsrc/alone.c\thand-asm\tsrc/alone.c:2\t2026-01-02\tdeveloper\n")
        check("the view: an assembly row clears the function that holds the line", ("asm", "src/alone.c") not in debt_counts(repo))
        (repo / ASM_EVIDENCE).unlink()
        global _cpp_cache_on
        _cpp_cache_on = False
        debt_counts(repo)
        check("the view: a push and CI run every unit again", ran() == ["src/alone.c", "src/other.c", "src/unit.c"])
        _cpp_cache_on = True
        # a judge that cannot read passes nothing
        put("src/alone.c", '#include "gone.h"\ns32 Alone(s32 n) {\n    return n;\n}\n')
        try:
            debt_counts(repo)
            check("the view: a unit that the command cannot preprocess is a refusal", False)
        except Fail as e:
            check("the view: a unit that the command cannot preprocess is a refusal", "cannot preprocess 1 unit(s) of the work tree: "
                  "src/alone.c: src/alone.c:1: fatal error: gone.h" in str(e), str(e))
        rc, out = _capture(cmd_debt, repo)
        check("debt: and it says so", rc == 1 and "DEBT FAIL `[floor] cpp`" in out, out)
        for name, text in (("#line", '#line 3 "src/shared/body.c"\n'), ("a number behind a digraph, a comment and a splice", "/* x */ %: \\\n 3 \"src/shared/body.c\"\n")):
            put("src/alone.c", "s32 Alone(s32 n) {\nagain:\n%s    if (n--) goto again;\n    return n;\n}\n" % text)
            try:
                debt_counts(repo)
                check("the view: a source with a line directive (%s) is a refusal" % name, False)
            except Fail as e:
                check("the view: a source with a line directive (%s) is a refusal" % name, "src/alone.c holds a line directive" in str(e), str(e))
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n; /* # 3 and #line in a comment, and a baseline of 3 */\n}\n")
        check("the view: the words in a comment are no directive", debt_counts(repo) is not None)
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n;\n}\n")
        put(RECORD, cpp.replace(sys.executable, "/nowhere/psxd-no-such-cpp"))
        try:
            debt_counts(repo)
            check("the view: a program that the machine lacks is a refusal", False)
        except Fail as e:
            check("the view: a program that the machine lacks is a refusal", "names a program that this machine lacks (`/nowhere/psxd-no-such-cpp`)" in str(e), str(e))
        # the command of the tree a change starts from judges it
        put(RECORD, cpp)
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    if (n--) AGAIN;\n    return n;\n}\n")
        _git(repo, "add", "-A")
        put(BASELINE, first_baseline(repo))
        _commit(repo, "the floor, with its rows in the compiler's view")
        check("the first baseline holds the rows of the view", "1 pin-unmarked src/pins.def\n" in (repo / BASELINE).read_text()
              and "1 goto-unmarked src/shared/body.c\n" in (repo / BASELINE).read_text() and _capture(cmd_debt, repo)[0] == 0, (repo / BASELINE).read_text())
        put("include/m.h", "#define AGAIN goto again\n#define HIDDEN goto again\n")
        put("src/alone.c", '#include "m.h"\ns32 Alone(s32 n) {\nagain:\n    if (n--) HIDDEN;\n    return n;\n}\n')
        put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = '%s -c pass {file}'\n" % sys.executable)
        _git(repo, "add", "-A")
        got = admission(repo, Tree(repo, "HEAD"), Tree(repo, INDEX))[0]
        check("a change that swaps the preprocessor for one that prints nothing is judged by the command it started from", got == [
            ("debt", "goto-unmarked is `down` and its total rose: 1 -> 2 (src/alone.c 0 -> 1)")], got)
        found = protected_findings(Tree(repo, "HEAD"), Tree(repo, INDEX))[0]
        check("and the command itself is a protected value", any("[floor] cpp changed" in f for f in found), found)
    if saved is None:
        os.environ.pop("PSXD_SELF_CPP_LOG", None)
    else:
        os.environ["PSXD_SELF_CPP_LOG"] = saved
    import shutil
    cc = shutil.which("cc")
    if cc:                                             # a real preprocessor, where the machine has one: text that a pattern cannot read
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = 'cc -E -nostdinc -undef -Iinclude {file}'\n")
            put("include/common.h", '#define INCLUDE_ASM(FOLDER, NAME) __asm__(".section .text\\n\\t.include \\"" FOLDER "/" #NAME ".s\\"\\n")\n'
                "#define GLUE(a, b) a##b\n#define JUMP(l) GLUE(go, to) l\n#define REG(t, v, r) register t v GLUE(as, m)(r)\n")
            put("src/a.c", '#include "common.h"\nINCLUDE_ASM("asm/a", Run);\nint Walk(int n) <%\n    REG(int, i, "$16");\nloop:\n    if (--n) JUMP(loop);\n'
                "    if (n) go\\\nto loop;\n#if 0\n    goto loop;\n#endif\n    return i;\n%>\n")
            _git(repo, "add", "-A")
            try:
                got = {k: n for k, n in debt_counts(repo).items() if k[0].split("-")[0] in ("pin", "goto", "barrier", "asm")}
            except Fail as e:
                got = str(e)
            check("a real preprocessor: a paste, a splice, a digraph, a stub and a branch that is not compiled", got == {
                ("pin", "src/a.c"): 1, ("pin-unmarked", "src/a.c"): 1, ("goto", "src/a.c"): 2, ("goto-unmarked", "src/a.c"): 2}, got)


def self_test_tree(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        (repo / "src" / "two.c").write_bytes(C_DEBT["macro"][0].replace("\n", "\r\n").encode())
        os.symlink("walk.c", repo / "src" / "link.c")
        _git(repo, "add", "-A")
        (repo / "config").mkdir()
        (repo / BASELINE).write_text(first_baseline(repo))
        _commit(repo, "one")
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0] * 2)
        _git(repo, "add", "src/walk.c")
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0] * 2 + C_DEBT["goto-unmarked"][0])
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
        check("debt --against: the change since a revision is judged", rc == 1 and "DEBT FAIL debt: goto-unmarked is `down` and its "
              "total rose: 0 -> 1 (src/walk.c 0 -> 1)\n" in out and "1 finding(s) against HEAD" in out, out)
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
text = open(sys.argv[1], encoding="latin-1", newline="").read()
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
        ("pin:$16:i", "Sum", 2), ("pin:$17:t", "Sum", 3), ("barrier:1", "Sum", 4)], got)
    check("crutches: a pin leaves its declaration, a barrier leaves nothing", drop(C_TRIAL, got[1]).split("\n")[3] == "    register s32 t = 0;"
          and '__asm__' not in drop(C_TRIAL, got[2]) and drop(C_TRIAL, got[2]).count("\n") == C_TRIAL.count("\n") - 1)
    check("an asm statement that holds an instruction is no barrier", not crutches("src/a.c", 'void A(void) {\n    __asm__("nop");\n}\n'))
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        rule = lambda body: put("tools/probe.py", PROBE_SELF.replace("RULE", body))  # noqa: E731
        trial = lambda *a, **kw: _capture(cmd_trial, repo, *a, **kw)  # noqa: E731
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
              and (repo / "src/sum.c").read_text() == C_TRIAL, out)
        rule("sys.exit(0 if 'asm(\"$16\")' in text else 1)")
        rc, out = trial("src/sum.c")
        text = (repo / "src/sum.c").read_text()
        check("trial: what the match needs stays, with a reason; the rest is gone", rc == 0 and
              "TRIAL src/sum.c Sum: 3 tried, 2 removed, 1 kept\n" in out and out.endswith("TRIAL OK (1 function(s), 3 tried, 2 removed, "
              "1 kept; 6 probe(s))\n") and text == C_TRIAL.replace('    register s32 t asm("$17") = 0;\n    __asm__("");\n', "    register s32 t = 0;\n")
              .replace("    register s32 i", "    // !FAKE: pin:$16:i: the function does not match without it (trial)\n    register s32 i"), out + text)
        check("trial: no file is left beside the source, and no ledger is written", sorted(x.name for x in (repo / "src").iterdir()) == ["sum.c"]
              and sorted(x.name for x in (repo / "config").iterdir()) == ["psxdecomp.toml"])
        check("the count's view: a marked pin", file_debt("src/sum.c", text) == {"pin": 1})
        check("trial: a second run changes nothing", trial("src/sum.c")[0] == 0 and (repo / "src/sum.c").read_text() == text)
        put("src/sum.c", text.replace("// !FAKE: pin:$16:i: the function does not match without it (trial)", "// !FAKE:"))
        check("a marker with no reason is an unmarked pin", file_debt("src/sum.c", (repo / "src/sum.c").read_text()) == {"pin": 1, "pin-unmarked": 1})
        rc, out = trial("src/sum.c", "Sum")
        check("trial --func writes the reason again", rc == 0 and (repo / "src/sum.c").read_text() == text, out)
        put(RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[trial]\nprobe = '%s tools/probe.py {file} {func} {path}'\n" % sys.executable)
        check("trial: the command may name its three values", trial("src/sum.c")[0] == 0 and (repo / "src/sum.c").read_text() == text)
        # a crutch that needs another one: the second pass
        put("src/sum.c", C_TRIAL)
        rule("sys.exit(0 if ('asm(\"$16\")' in text or 'asm(\"$17\")' not in text) else 1)")
        rc, out = trial("src/sum.c")
        check("trial: a pin that only another pin needed goes in the second pass", rc == 0 and "0 kept" in out
              and "asm" not in (repo / "src/sum.c").read_text(), out)
        rc, out = trial("src/sum.c")
        check("trial: a file with no crutch", (rc, out) == (0, "TRIAL OK src/sum.c: no pin and no barrier in a function\n"), out)
        check("trial: a file that is not there", trial("src/gone.c")[0] == 1)
        # ---- trials as the reference projects run them: each attack on a trial is a control here ----

        def safe(fn, *a, **kw):                        # a crash is an answer of its own, and a wrong one
            try:
                return fn(*a, **kw)
            except Exception as e:
                return "%s: %s" % (type(e).__name__, str(e)[:120])

        bare = 'void A(void) {\n    register k asm("$17");\n    k = 1;\n}\n'
        got = safe(lambda: drop(bare, crutches("src/a.c", bare)[0]))
        check("a pin loses its asm clause and nothing else, so a declaration with no type still compiles",
              got == bare.replace(' asm("$17")', ""), got)
        two = 'void A(void) {\n    register s32 j = 0, k asm("$17");\n    register s32 a asm("$4"), b asm("$5");\n}\n'
        got = safe(lambda: [(c["id"], drop(two, c).split("\n")[c["line"]]) for c in crutches("src/a.c", two)])
        check("each asm clause of a declaration is a pin of its own", got == [
            ("pin:$17:k", "    register s32 j = 0, k;"), ("pin:$4:a", '    register s32 a, b asm("$5");'),
            ("pin:$5:b", '    register s32 a asm("$4"), b;')] and file_debt("src/a.c", two) == {"pin": 3, "pin-unmarked": 3}, got)
        keep16 = "sys.exit(0 if 'asm(\"$16\")' in text else 1)"
        rule(keep16)
        put("src/odd.c", 'void Odd(void) {\n    register s32 a asm("$" "4");\n}\n')
        got = safe(trial, "src/odd.c")
        check("trial: a pin whose clause the tool cannot read is a finding, not a crash and not a skip", isinstance(got, tuple) and got[0] == 1
              and "TRIAL FAIL src/odd.c Odd: " in got[1] and "cannot read" in got[1], got)
        (repo / "src/odd.c").unlink()
        # the bytes of a source are its own: Shift-JIS text and CRLF line ends come back as they went in
        sjis = C_TRIAL.replace("s32 Sum", "/* テスト */\ns32 Sum").replace("\n", "\r\n").encode("shift_jis")
        (repo / "src/sum.c").write_bytes(sjis)
        got = safe(trial, "src/sum.c")
        want = (sjis.replace(b' asm("$17")', b"").replace(b'    __asm__("");\r\n', b"")
                .replace(b"    register s32 i", b"    // !FAKE: pin:$16:i: the function does not match without it (trial)\r\n    register s32 i"))
        check("trial: the bytes it does not change stay (Shift-JIS, CRLF)", isinstance(got, tuple) and got[0] == 0
              and (repo / "src/sum.c").read_bytes() == want, (got, (repo / "src/sum.c").read_bytes()[:160]))
        (repo / "src/sum.c").write_bytes(C_TRIAL.encode().replace(b"    return t;\n", b"    return t;\r\n"))
        got = safe(trial, "src/sum.c")
        check("trial: mixed line ends are refused, the file stays", isinstance(got, tuple) and got[0] == 1 and "line ends" in got[1]
              and b"return t;\r\n" in (repo / "src/sum.c").read_bytes(), got)
        # the copy that the probe compiles never stands on a file, and a path outside the repository is no crash
        put("src/sum.c", C_TRIAL)
        put("src/sum.psxd-trial.c", "int tracked;\n")
        got = safe(trial, "src/sum.c")
        check("trial: a file where its copy would go is not written over and not deleted", isinstance(got, tuple) and got[0] == 1
              and "src/sum.psxd-trial.c" in got[1] and (repo / "src/sum.psxd-trial.c").read_text() == "int tracked;\n"
              and (repo / "src/sum.c").read_text() == C_TRIAL, got)
        (repo / "src/sum.psxd-trial.c").unlink(missing_ok=True)
        got = safe(trial, "/etc/hosts")
        check("trial: a path outside the repository is a refusal", isinstance(got, tuple) and got[0] == 1 and "TRIAL FAIL" in got[1], got)
        rule("open(sys.argv[3], 'a').write('/* touched */\\n')\n" + keep16)
        got = safe(trial, "src/sum.c")
        check("trial: a probe that writes the tracked file has failed", isinstance(got, tuple) and got[0] == 1 and "the probe failed" in got[1], got)


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
            # a name is never required: an address name, a guessed name and a provisional row with no evidence all pass
            put("src/guess.c", "s32 func_80012344(s32 n) {\n    return n;\n}\ns32 Enemy_Think(s32 n) {\n    return n;\n}\n")
            put(NAMES, "\t".join(NAME_COLUMNS) + "\nfunction\tmain\t\tfunc_80010000\tEnemy_Walk\tprovisional\tstring:src/gone.c:4\ta guess\n")
            _git(repo, "add", "-A")
            _capture(cmd_debt, repo, update=True)
            rc, out = staged()
            check("gate: an address name, a guessed name and a provisional row with no evidence pass, with a warning", rc == 0
                  and "GATE WARN names: config/names.tsv: line 2: the evidence of Enemy_Walk points at nothing" in out
                  and "1 unbased src/guess.c\n" in (repo / BASELINE).read_text() and out.endswith("GATE OK (staged)\n"), out)
            put(NAMES, "kind\tname\n")
            rc, out = staged()
            check("gate: a names ledger that cannot be read fails", rc == 1 and "GATE FAIL names: config/names.tsv: line 1: the header is not" in out, out)
            undo()
            # the baseline: a row written by hand, a policy line taken out, a new skip line
            put("src/walk.c", C_DEBT["goto"][0] + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(BASELINE, base_text.replace("1 goto src/walk.c", "1 pin src/walk.c\n1 pin-unmarked src/walk.c\n1 goto src/walk.c"))
            rc, out = staged()
            check("gate: a row written by hand admits nothing", rc == 1 and "GATE FAIL debt: pin-unmarked is `down` and its total "
                  "rose: 0 -> 1 (src/walk.c 0 -> 1)\n" in out and out.endswith("GATE FAIL (staged; 1 finding(s))\n"), out)
            undo()
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(BASELINE, base_text.replace("1 goto src/walk.c", "2 goto src/walk.c"))
            check("gate: a counted kind rises with its row", staged() == (0, "GATE OK (staged)\n"), staged())
            undo()
            for name, text, want in (("a policy line taken out", base_text.replace("mode pin-unmarked down\n", ""),
                                      "GATE FAIL policy: the policy line of pin-unmarked is gone"),
                                     ("a weaker mode", base_text.replace("mode asm down", "mode asm count"),
                                      "GATE FAIL policy: asm went from down to count"),
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
                     "changes CLAUDE_PROJECT_DIR in `env`"),
                    ("a variable that stills a check, set for every session", lambda: put(SETTINGS, json.dumps(dict(hooks, env={"PSXD_GATE": "1"}))),
                     "changes PSXD_GATE in `env`")):
                change()
                rc, out = staged()
                check("gate: " + name, rc == 1 and "GATE FAIL protected: " in out and want in out, out)
                undo()
            for name, text in (("deny rules that are no list", '{"permissions": {"deny": 5}}'), ("hooks that are no table", '{"hooks": 5}'),
                               ("a hook group that is no list", '{"hooks": {"PreToolUse": 5}}'), ("settings nested too deep", "[" * 200000)):
                put(SETTINGS, text)
                try:
                    rc, out = staged()
                except Exception as e:                 # the control: a crash is no answer
                    rc, out = -1, "%s: %s" % (type(e).__name__, str(e)[:80])
                check("gate: %s: a FAIL, never a crash" % name, rc == 1 and "GATE FAIL " in out and out.endswith(" finding(s))\n"), out[-200:])
                undo()
            rules = GATE_SETTINGS["permissions"]["deny"]
            for name, value in (("deny rules as one string", " ".join(rules)), ("deny rules as the keys of a table", dict.fromkeys(rules, False)),
                                ("deny rules inside another list", [rules])):
                put(SETTINGS, json.dumps(dict(hooks, permissions={"deny": value})))
                rc, out = staged()
                check("gate: %s are no deny rules" % name, rc == 1 and "GATE FAIL protected: " in out and "deny" in out, out[-300:])
                undo()
            for name, matcher in (("a matcher that is a character class of the old one", "[^|Bash|Edit|Write|]"),
                                  ("a matcher with one more token that is no tool name", "NoSuchTool(|Bash|Edit|Write|)")):
                put(SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash|Edit|Write"', json.dumps(matcher)))
                rc, out = staged()
                check("gate: %s loses the hook" % name, rc == 1 and "lost a hook of PreToolUse" in out, out[-300:])
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
                  "version %s -> 99.0.0, the released file" % VERSION in out and out.endswith("GATE OK by the later tool (ci; 1 commit(s))\n"), out)
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
            put("src/walk.c", C_DEBT["goto"][0] + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            rc, out = staged()
            check("gate: a later tool beside a refused change does not take over", rc == 1 and "by the later tool" not in out
                  and "pin-unmarked is `down` and its total rose" in out, out)
            undo()
            os.environ["PSXD_SELF_SCAN"] = "1"         # the game's own scanner is one more check, beside the count
            rc, out = staged()
            check("gate: the game's own debt scanner runs beside the count", rc == 1 and "GATE FAIL own-debt: the game's own scanner" in out
                  and "exited 1: SCAN FAIL" in out, out)
            del os.environ["PSXD_SELF_SCAN"]
            # the bank: the files git does not track yet count, and the rows of an admitted change are written
            put("src/new.c", C_DEBT["goto"][0].replace("Walk", "Run"))
            rc, out = gate("bank")
            check("gate --bank counts a file that is not tracked yet and writes its rows", rc == 0 and "1 goto src/new.c\n" in (repo / BASELINE).read_text()
                  and "GATE INFO config/debt-baseline.txt: the rows of now written (1 rose, 0 fell)" in out
                  and out.endswith("GATE OK (bank)\n"), out)
            put("src/new.c", C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            before = (repo / BASELINE).read_text()
            rc, out = gate("bank")
            check("gate --bank refuses an unmarked pin in a file that is not tracked yet", rc == 1 and
                  "GATE FAIL debt: pin-unmarked is `down` and its total rose: 0 -> 1 (src/new.c 0 -> 1)" in out and (repo / BASELINE).read_text() == before, out)
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
            # CI: the head of the range against its base
            rc, out = gate("ci", "%s..HEAD" % start)
            check("gate --ci: an admitted commit", (rc, out) == (0, "GATE OK (ci; 1 commit(s))\n"), out)
            put("src/walk.c", 'INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
            _capture(cmd_debt, repo, update=True)
            _git(repo, "add", "-A")
            _commit(repo, "the body leaves")
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            _capture(cmd_debt, repo, update=True)
            _git(repo, "add", "-A")
            _commit(repo, "the body is back, with one more marked goto")
            rc, out = gate("ci", "HEAD~2..HEAD")
            check("gate --ci: a counted kind over a range passes", (rc, out) == (0, "GATE OK (ci; 2 commit(s))\n"), out)
            put("src/walk.c", (repo / "src/walk.c").read_text() + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(BASELINE, (repo / BASELINE).read_text().replace("2 goto src/walk.c", "1 pin src/walk.c\n1 pin-unmarked src/walk.c\n2 goto src/walk.c"))
            _git(repo, "add", "-A")
            _commit(repo, "a commit that no hook saw")
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a commit that skipped the hook fails", rc == 1 and
                  "GATE FAIL debt: pin-unmarked is `down` and its total rose: 0 -> 1 (src/walk.c 0 -> 1)" in out, out)
            rc, out = gate("ci", "HEAD~3..HEAD")
            check("gate --ci: and so does every range that ends there", rc == 1 and "pin-unmarked is `down` and its total rose" in out, out)
            rc, out = gate("ci", "0000000000000000000000000000000000000000..HEAD")
            check("gate --ci with no base: the tree of the head", rc == 0 and "no base: the tree of the head only" in out, out)
            rc, out = gate("ci", "HEAD..nowhere")
            check("gate --ci: a range that names no commit", rc == 1 and "GATE FAIL gate: HEAD..nowhere names no commit" in out, out)
            rc, out = gate("ci", "nowhere..HEAD")
            check("gate --ci: a base that names no commit judges nothing, so it fails", rc == 1 and "GATE FAIL gate: the base nowhere "
                  "names no commit of this repository" in out, out)
            rc, out = gate("push", "HEAD~1..HEAD")
            check("gate --push: the range, as --ci", rc == 1 and "pin-unmarked is `down` and its total rose" in out, out)
            cwd = os.getcwd()
            try:
                os.chdir(repo.parent)
                rc, out = _capture(cmd_gate, repo.name, "ci", "HEAD~2..HEAD~1")
            finally:
                os.chdir(cwd)
            check("gate: a relative --repo reads the same repository", rc == 0 and out.startswith("GATE INFO the work tree is not at")
                  and out.endswith("GATE OK (ci; 1 commit(s))\n"), out)
            # a commit with no parent, put in the place of the history: the base judges it
            undo()
            good = _rev(repo, "HEAD~1")
            _git(repo, "checkout", "-q", "--orphan", "fresh", good)
            put("src/walk.c", (repo / "src/walk.c").read_text() + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(BASELINE, (repo / BASELINE).read_text().replace("2 goto src/walk.c", "1 pin src/walk.c\n1 pin-unmarked src/walk.c\n2 goto src/walk.c")
                .replace("mode asm down", "mode asm count"))
            _git(repo, "add", "-A")
            _commit(repo, "a history of one commit")
            rc, out = gate("ci", "%s..HEAD" % good)
            check("gate --ci: a commit with no parent is judged against the base", rc == 1 and "pin-unmarked is `down` and its total rose: 0 -> 1"
                  in out and "GATE FAIL policy: asm went from down to count" in out, out)
    finally:
        _sibling_run = keep


def self_test_judge(check) -> None:
    """What decides, and what a change cannot move: a merge is judged by its two ends, a file has one reader of its
    lines, and the standard library is the interpreter's."""
    global _sibling_run
    keep = _sibling_run
    if not sibling().is_file():
        _sibling_run = lambda repo, *args: (0, [])  # noqa: E731
    policy = "".join("mode %s down\n" % k for k in KINDS)
    feed = parse_baseline(policy + "# a note\x0craise goto 5 2026-01-02 behind a form feed\n# a note raise pin 5 2026-01-02 behind a separator\n")
    check("a line ends at a newline and at nothing else", feed.raises == [] and len(feed.head) == 2, feed.raises)
    rows, errs = read_tsv("x.tsv", ("a", "b"), tree=type("T", (), {"read": lambda self, p: "a\tb\n1\t2\x0c3\n"})())
    check("a ledger row holds a form feed, it does not end at one", [(r["a"], r["b"]) for r in rows] == [("1", "2\x0c3")] and not errs, (rows, errs))
    try:
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            gate = lambda mode, rng=None: _capture(cmd_gate, repo, mode, rng)  # noqa: E731
            body = lambda name, n: "s32 %s(s32 n) {\n%s    return n;\n}\n" % (name, "    n += *(s32 *)(n + 4);\n" * n)  # noqa: E731

            def rows_of_now():
                bl = parse_baseline((repo / BASELINE).read_text())
                put(BASELINE, baseline_text(bl, debt_counts(repo, bl.skip, Tree(repo, None, untracked=True))))

            def merge(first, second, msg):
                _git(repo, "add", "-A")
                made = _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit-tree", _git(repo, "write-tree").stdout.strip(),
                            "-p", first, "-p", second, "-m", msg).stdout.strip()
                _git(repo, "reset", "-q", "--hard", made)
                return made

            put("src/a.c", 'INCLUDE_ASM("asm/nonmatchings/a", Run);\n')
            put("src/b.c", 'INCLUDE_ASM("asm/nonmatchings/b", Jump);\n')
            _git(repo, "add", "-A")
            put(BASELINE, first_baseline(repo))
            _commit(repo, "the floor")
            base = _rev(repo, "HEAD")
            put("src/a.c", body("Run", 1))
            rows_of_now()
            _commit(repo, "Run, with one offset")
            left = _rev(repo, "HEAD")
            _git(repo, "reset", "-q", "--hard", base)
            put("src/b.c", body("Jump", 1))
            rows_of_now()
            _commit(repo, "Jump, with one offset")
            right = _rev(repo, "HEAD")
            put("src/a.c", body("Run", 1))
            rows_of_now()
            merge(left, right, "a merge of two banks")
            rc, out = gate("ci", "%s..HEAD" % base)
            check("gate --ci: a merge of two admitted branches passes", (rc, out) == (0, "GATE OK (ci; 3 commit(s))\n"), out)
            _git(repo, "reset", "-q", "--hard", left)
            (repo / ".git" / "MERGE_HEAD").write_text(right + "\n")
            put("src/b.c", body("Jump", 1) + C_DEBT["pin-unmarked"][0])
            rows_of_now()
            _git(repo, "add", "-A")
            rc, out = gate("staged")
            check("gate --staged: a merge in progress is judged against HEAD", rc == 1 and "pin-unmarked is `down` and its total rose: 0 -> 1" in out, out)
            (repo / ".git" / "MERGE_HEAD").unlink()
            _git(repo, "reset", "-q", "--hard", left)
            row = "main\tRun\tsrc/a.c\thand-asm\tsrc/a.c:1\t2026-01-02\tdeveloper\n"
            put(ASM_EVIDENCE, "\t".join(ASM_COLUMNS) + "\n" + row)
            _commit(repo, "the developer's assembly row")
            put(ASM_EVIDENCE, "\t".join(ASM_COLUMNS) + "\n" + row + row)
            _git(repo, "add", "-A")
            acts = developer_acts(Tree(repo, "HEAD"), Tree(repo, INDEX))
            check("a second copy of a ledger row is a new act", len(acts) == 1 and "the row of Run src/a.c" in acts[0], acts)
            _git(repo, "reset", "-q", "--hard", left)
            # the developer's acts are read by the reader of the baseline, line for line and one for one
            line = "raise offset 1 2026-01-02 the first one\n"
            put(BASELINE, (repo / BASELINE).read_text() + line)
            _commit(repo, "the developer's raise")
            put(BASELINE, (repo / BASELINE).read_text() + line)
            _git(repo, "add", "-A")
            acts = developer_acts(Tree(repo, "HEAD"), Tree(repo, INDEX))
            check("a second copy of a `raise` line is a new act", acts == ["`raise offset 1 2026-01-02 the first one` in config/debt-baseline.txt"], acts)
            _git(repo, "reset", "-q", "--hard", "HEAD")
            put(BASELINE, (repo / BASELINE).read_text() + "# a note\x0craise offset 9 2026-01-02 behind a form feed\n")
            _git(repo, "add", "-A")
            bl = parse_baseline(Tree(repo, INDEX).read(BASELINE))
            check("a `raise` behind a form feed raises nothing and is no act", len(bl.raises) == 1 and
                  developer_acts(Tree(repo, "HEAD"), Tree(repo, INDEX)) == [], bl.raises)
            # a module of the checkout beside the tool is not the standard library
            put(VENDORED, pathlib.Path(__file__).read_text(encoding="utf-8"))
            put("tools/bisect.py", "import os\nprint('GATE OK (a module of the checkout)')\nos._exit(0)\n")
            r = subprocess.run([sys.executable, str(repo / VENDORED), "--version"], capture_output=True, text=True, cwd=str(repo),
                               env=dict(os.environ, PYTHONPATH=str(repo / "tools")))
            check("a module of the checkout does not stand in for the standard library", (r.returncode, r.stdout.strip()) == (0, VERSION),
                  r.stdout + r.stderr[-200:])
    finally:
        _sibling_run = keep


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
        self_test_judge(check)
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
    ap.add_argument("--ci", metavar="BASE..HEAD", help="gate: judge the head of the range against its base")
    ap.add_argument("--push", nargs="?", const="", metavar="BASE..HEAD", help="gate: as --ci, and the game's own check")
    ap.add_argument("--part", default="all", choices=["all", "state"], help=argparse.SUPPRESS)
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
        return cmd_trial(a.repo, a.file, a.func)
    if a.cmd == "gate":
        modes = [m for m, on in (("staged", a.staged), ("bank", a.bank), ("ci", a.ci), ("push", a.push is not None)) if on]
        if len(modes) != 1:
            ap.error("gate: one of --staged, --bank, --ci <base>..<head> and --push [<base>..<head>]")
        return cmd_gate(a.repo, modes[0], a.ci or a.push or None, a.part)
    if a.cmd == "toolchain":
        return cmd_toolchain(a.repo)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
