#!/usr/bin/env python3
"""floor.py — the tooling and readability floor of a game repository (psxdecomp's docs/ops/psxdecomp-floor.md).

    floor.py debt [--repo DIR]            count the readability debt of the tracked source against config/debt-baseline.txt;
                                          exit 1 when the total of a kind is over its row (a rise) or under it (a stale
                                          row), with no baseline, and with no policy line for a kind
    floor.py debt [--staged | --rev REV] [--against BASE]
                                          count the index or the revision REV in the work tree's place (no checkout);
                                          --against: judge the change since the revision BASE by BASE's own policy
    floor.py debt --files [--public] [--staged | --rev REV]
                                          the state of each C file: `stubs` (a function is still assembly), `matched`
                                          (every function is in C, and debt is left) or `finished` (no debt of any
                                          kind); the last line is the count that a README's generated block shows.
                                          --public: of the files that config/public-paths.txt lists only, which is what
                                          the public repository of a game in split mode can count itself
    floor.py debt --update                rewrite the rows to the totals of now; refused when a kind that HEAD's policy
                                          holds `down` rose since HEAD
    floor.py debt --recount               write the baseline in version 2: the totals of now and a policy line for each
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
    floor.py names [--init] [--repo DIR]  check config/names.tsv (it is its table) and config/asm-evidence.tsv (each row
                                          points at its evidence and at one function); --init writes their header lines
    floor.py names [--staged | --rev REV] [--against BASE]
                                          the ledgers of the index or of a revision; --against: open only the assembly
                                          rows that are new since the revision BASE
    floor.py toolchain [--repo DIR]       config/toolchain.tsv: each pinned checkout at its pin and clean, each file at its hash
    floor.py guard --hook                 a PreToolUse hook: stdin is the event, config/guard.tsv holds the rules
    floor.py --self-test

psxdecomp copies this file into a game as tools/psxd_floor.py. It uses the standard library only and it imports
nothing of the plugin. It writes the baseline (`debt --update`, `--recount`, `--down`, `--raise`, `gate --bank`), the
header line of each of the two ledgers (`names --init`).

The debt kinds (one `<count> <kind>` row each in the baseline: the total of the tree). Every tracked file with a C or an assembly
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
  placeholder      a `func_XXXXXXXX` or `D_XXXXXXXX` name defined in a C file (also `FUN_`, `DAT_`, `sub_`, `loc_`)
  placeholder-use  each other place where such a name stands: a call, a read, a declaration
  struct           a struct, union or enum body outside an include/ folder
  extern           an `extern` declaration or a prototype in a C file: a declaration has one owner, a header
  filename         a source file named by an address or a number (`func_80012344.c`, `misc12.c`)

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


# ---- the readability debt -----------------------------------------------------------------------------------------
KINDS = ("pin", "pin-unmarked", "goto", "goto-unmarked", "barrier", "barrier-unmarked", "offset", "address", "cast",
         "field", "asm", "placeholder", "placeholder-use", "struct", "extern", "filename")
RETIRED = ("obscured", "unbased", "macro", "flag", "reservation")   # kinds of an earlier build: their lines are dropped
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
    "%s: the count of readability debt of the tracked source, one total per kind (`python3 %s --help` lists the kinds)." % (
        BASELINE, VENDORED),
    "`python3 %s debt` fails when a total of the tree is over its row, and when a row is over its total." % VENDORED,
    "After a change, run `python3 %s debt --update`, or bank with `gate --bank`, which writes the totals." % VENDORED,
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
    by function, where an assembly row finds its function, and where a trial finds the crutches of one. A body starts at a definition in column 0 (DEF_FUNC) and ends behind its matching brace. A definition
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
# markers of the output. Every C file is preprocessed as a unit of its own. With no `[floor] cpp` the same scan reads the raw text of each file, where a construct
# inside a macro is counted once, at the macro's definition.
def asm_emits(text: str) -> bool:
    """The strings of an asm statement hold an instruction or emit data: a line that is no label, no comment and none
    of the directives of ASM_QUIET, outside a `.macro` definition. The text is read as the compiler hands it to the
    assembler: with each escape of the C string decoded (`\\x3b` is a `;`, `\\012` a line end), so that no spelling of
    a separator hides the statement behind it. A string that cannot be decoded is read as an instruction."""
    try:
        text = text.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except (UnicodeError, ValueError):
        return True
    inside = False
    for l in re.split(r"[\n\r;]", text):
        l = re.sub(r"^[\w.$]+:\s*", "", l.strip())
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
    file of the tree as a unit of its own, in a folder that holds the tree's files. A file that another unit includes
    is run as well: a build may compile it alone, and the text that it shows alone can differ from the text that it
    shows behind the macros of the unit that includes it. Of one line of one file, the most that one unit holds
    counts, so a file that many units read is counted once. A unit that the command cannot preprocess raises Fail: a
    judge that cannot read passes nothing. So does a file with a line directive of its own. The one exception is a
    file that fails alone and that another unit reads: no build compiles it alone either. Each unit's result is kept
    beside the files it read (their blobs), so a change costs the units that it touches."""
    if ("view", cmd) in tree.memo:
        return tree.memo[("view", cmd)]
    whole = tree._whole or tree
    units = [p for p in whole.paths if is_source(p) and is_c(p)]
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
    failed: list = []

    def take(unit, hits, files):
        seen.update(f for f in files if f != unit)     # what another unit read
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
        todo = []
        for unit in units:
            got = cached(unit)
            if got is None:
                todo.append(unit)
            else:
                take(unit, *got)
                fresh[slot(unit)] = held[slot(unit)]
        if todo:
            root = stack.enter_context(exported(whole))
            with concurrent.futures.ThreadPoolExecutor(min(8, os.cpu_count() or 2)) as pool:
                for unit, out, err in pool.map(lambda u: run(root, u), todo):
                    if out is None:
                        failed.append((unit, err))
                        continue
                    hits, files = unit_view(out, unit, root)
                    take(unit, hits, files)
                    deps = {f: whole.blob(f) for f in files}
                    if all(deps.values()):             # every file it read is a file of this tree: the result can be kept
                        fresh[slot(unit)] = {"deps": deps, "names": names_of(deps), "hits": [[k, f, l, n] for (k, f, l), n in sorted(hits.items())]}
    failed = ["%s: %s" % f for f in failed if f[0] not in seen]    # a fragment that only stands inside another unit
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
    decides (not the keyword kinds, and not `filename`). `extents`: its function bodies. `stubs`: its INCLUDE_ASM
    lines. `shared`: the macros of the headers that hide an offset or an address."""
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
    if not in_include(rel):
        hits += [("struct", m.start()) for m in STRUCT.finditer(code)]
    stub_lines = [(m.start(), code.find("\n", m.start())) for m in STUB_USE.finditer(code)]
    uses = [m for m in PLACEHOLDER_USE.finditer(code) if not any(a <= m.start() and (b < 0 or m.start() < b) for a, b in stub_lines)]
    if is_c(rel):
        hits += [("extern", m.start()) for m in EXTERN.finditer(code)]
        named: dict[str, int] = {}
        for m in list(DEF_FUNC.finditer(code)) + list(DEF_DATA.finditer(code)):
            if m.group(1) not in NOT_A_NAME or m.re is DEF_DATA:
                named.setdefault(m.group(1), m.start())
        hits += [("placeholder", at) for n, at in named.items() if PLACEHOLDER.match(n)]
        for n, at in named.items():                    # the name in its own definition is no use of it
            own = next((u for u in uses if u.group(0) == n and u.start() >= at), None)
            if own is not None:
                uses.remove(own)
    hits += [("placeholder-use", m.start()) for m in uses]
    _SCANS[key] = {"hits": hits, "extents": ext, "stubs": len(STUB_USE.findall(code))}
    return _SCANS[key]


def file_bodies(rel: str, text: str, shared=None, address_header=ADDRESS_HEADER, view=None) -> dict[str, dict[str, int]]:
    """{function name: {kind: count}} of one C file or header: every function body it holds, also one with no debt,
    and under SCOPE what no body holds (left out when it is empty). Two bodies of one name are one entry. `view`:
    [(kind, line from 0)] of the keyword kinds
    as the game's preprocessor shows them for this file (`compiler_view`); None: as the raw text shows them."""
    scan = scan_file(rel, text, shared, address_header)
    hits = list(scan["hits"])
    view = raw_keywords(text) if view is None else view
    if view:                                           # a hit stands in the body that holds the start of its line
        starts = [0] + [m.end() for m in re.finditer("\n", text)]
        hits += [(kind, starts[min(line, len(starts) - 1)]) for kind, line in marked(view, markers(text) if "!FAKE:" in text else {})]
    out: dict[str, dict[str, int]] = {name: {} for name, _, _ in scan["extents"]}
    starts = [a for _, a, _ in scan["extents"]]
    for kind, at in hits:
        i = bisect.bisect_right(starts, at) - 1
        name = scan["extents"][i][0] if i >= 0 and at < scan["extents"][i][2] else SCOPE
        got = out.setdefault(name, {})
        got[kind] = got.get(kind, 0) + 1
    return out


def file_debt(rel: str, text: str, shared=None, address_header=ADDRESS_HEADER, view=None) -> dict[str, int]:
    """The counts of one C file or header, by kind (zero counts left out): the sum of its bodies and its scope."""
    got: dict[str, int] = {}
    for counts in file_bodies(rel, text, shared, address_header, view).values():
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
            out[p] = file_bodies(p, texts[p], known(p), header, None if view is None else view.get(p, []))
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



# ---- the baseline: one total per kind, and the policy that judges a change -------------------------------------------
# A policy line gives each kind its mode. `count`: the kind is counted, its total shows what each commit brings, and
# nothing is refused. `down`: the total of the kind in the tree never rises. A `raise` line is the developer's act: it
# lets one change go over by its number. The change itself cannot weaken any of this: `admission` reads the policy of
# the revision that the change starts from.
MODES = ("count", "down")                            # weakest first
START_DOWN = ("asm", "pin-unmarked", "goto-unmarked", "barrier-unmarked")   # what `debt --recount` starts as `down`
PUBLIC_PATHS = "config/public-paths.txt"


class Baseline:
    """config/debt-baseline.txt as read. `version` 0: no file. 1: the file of psxdecomp 0.6.0 and earlier (one `mode
    admit|down` line, in `old_mode`). 2: a policy line per kind. `totals`: {kind: its row}; the rows of an earlier
    file, one per kind and file (`by_file`), are summed. `other`: the lines of a kind this tool does not know (a newer
    tool wrote them), kept as they are."""

    def __init__(self):
        self.version, self.old_mode, self.by_file = 0, None, False
        self.totals: dict[str, int] = {}
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
    line and no `#` comment raises Fail with its number, and so do a second row of one kind or of one kind and file, a
    total beside the rows of its kind, a second policy of one kind, and a file that mixes the two versions. A row
    `<count> <kind> <path>` of an earlier file adds to its kind's total. `--update` writes every comment line above
    the policy lines. The lines `mode <kind> admit-new` and `budget <kind> …` of an unreleased build of this tool are
    read as `count`."""
    bl, old, form = Baseline(), 0, {}
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
        row = re.fullmatch(r"(\d{1,9}) (\S+)(?: (\S.*))?", l)
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
            raise Fail("%s: not `<count> <kind>`, `mode <kind> down|count`, `raise <kind> <n> <date> <reason>`, "
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
        elif form.get(kind) == "total" or (row[3] is None and kind in form) or (kind, row[3]) in form.get(kind, ()):
            raise Fail("%s: %s has two rows%s" % (where, kind, "" if row[3] is None else " (%s)" % row[3]))
        else:
            form[kind] = "total" if row[3] is None else form.get(kind, set()) | {(kind, row[3])}
            bl.totals[kind] = bl.totals.get(kind, 0) + int(row[1])
            bl.by_file |= row[3] is not None
    if old and (bl.modes or bl.raises):
        raise Fail("%s: a `mode %s` line of version 1 beside the policy lines of version 2" % (BASELINE, bl.old_mode))
    return bl


def baseline_text(bl: Baseline, totals: dict | None = None) -> str:
    """The file of a baseline in version 2: the comment lines, the `skip` lines, a policy line per kind, the lines of
    kinds this tool does not know, the `raise` lines, then one row `<count> <kind>` per kind above zero (`totals`,
    else its own)."""
    totals = bl.totals if totals is None else totals
    lines = [l if l.startswith("#") else "# " + l for l in bl.head]
    lines += ["skip %s" % e for e in bl.skip]
    lines += ["mode %s %s" % (kind, bl.modes[kind]) for kind in KINDS if kind in bl.modes]
    lines += bl.other
    lines += ["raise %s %d %s %s" % r for r in bl.raises]
    lines += ["%d %s" % (totals[k], k) for k in KINDS if totals.get(k, 0) > 0]
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
    totals = _kind_totals(debt_counts(repo, bl.skip, tree))
    for kind in bl.lacks():
        bl.modes[kind] = "down" if bl.old_mode == "down" or kind in START_DOWN else "count"
        notes.append("%s: %s" % (kind, bl.modes[kind]))
    if bl.version == 1 or any(l.lstrip("# ").startswith(OLD_HEADS[4:8]) for l in bl.head):
        bl.head = list(BASELINE_HEAD) + [l for l in bl.head if not l.lstrip("# ").startswith(OLD_HEADS)]
    return baseline_text(bl, totals), notes


def first_baseline(repo) -> str:
    """A game's first baseline: the counts of now and the starting mode of each kind."""
    return recount_text(repo)[0]


def projection(tree: Tree) -> bool:
    """The tree is the public tree of a game in split mode: config/public-paths.txt exists and lists each source file
    of the tree. Its baseline holds the totals of the files that it does not publish as well."""
    public = tree.read(PUBLIC_PATHS)
    if public is None:
        return False
    listed = [l.strip() for l in lines(public) if l.strip() and not l.lstrip().startswith("#")]
    return all(any(entry_match(e, p) for e in listed) for p in tree.paths if is_source(p))


def state_findings(repo, tree: Tree | None = None) -> tuple[list[str], dict]:
    """(the FAIL lines of a tree's own baseline, what was read). The baseline must exist, be of version 2, hold a
    policy line for each kind and hold each total of the tree as its row. A total under its row is not stale in the
    public tree of a game in split mode (`projection`): its rows count the files that it does not publish too."""
    tree = tree or Tree(repo)
    bl = parse_baseline(tree.read(BASELINE))
    counts = debt_counts(repo, bl.skip, tree)
    totals = _kind_totals(counts)
    st = {"baseline": bl, "counts": counts, "totals": totals, "rise": [], "stale": []}
    if bl.version == 0:
        return ["no %s: `python3 %s debt --recount` writes it" % (BASELINE, VENDORED)], st
    if bl.version == 1:
        return ["%s is a version 1 file (`mode %s`): run `python3 %s debt --recount`, or /psxdecomp:upgrade"
                % (BASELINE, bl.old_mode, VENDORED)], st
    out = ["no policy line for %s in %s: run `python3 %s debt --recount`" % (", ".join(bl.lacks()), BASELINE, VENDORED)
           ] if bl.lacks() else []
    public = projection(tree)
    for k in KINDS:
        have, row = totals[k], bl.totals.get(k, 0)
        if have > row:
            st["rise"].append(k)
            out.append("rise %s: %d, its row is %d" % (k, have, row))
        elif have < row and not public:
            st["stale"].append(k)
            out.append("stale %s: %d, its row is %d" % (k, have, row))
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
    function of the file is still assembly. `matched`: every function is in C, and the file holds debt. `finished`:
    every function is in C and the file holds no debt of any kind. Nobody writes that word by hand: this is where it
    comes from."""
    tree = tree or Tree(repo)
    skip = parse_baseline(tree.read(BASELINE)).skip
    bodies = debt_bodies(repo, skip, tree)
    out = []
    for p in sorted(bodies):
        stubs = scan_file(p, tree.read(p) or "", address_header=address_header(tree))["stubs"] if is_c(p) else 0
        if not is_c(p) or not (stubs or any(n != SCOPE for n in bodies[p])):
            continue
        counts = debt_counts(repo, bodies={p: bodies[p]})
        got = {k[0]: n for k, n in counts.items()}
        out.append(("stubs" if stubs else "matched" if got else "finished", p, got))
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
    print("DEBT FILES %d C file(s): %d finished, %d matched, %d with stubs" % (len(states), by["finished"], by["matched"], by["stubs"]))
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
                print("DEBT RECOUNT written %s (%d total(s))" % (BASELINE, len(parse_baseline(text).totals)))
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
            for k in st["rise"] + st["stale"]:
                print("DEBT INFO %s: %d -> %d" % (k, bl.totals.get(k, 0), st["totals"][k]))
            _write_baseline(repo, baseline_text(bl, st["totals"]))
            print("DEBT UPDATE written %s (%d total(s), %d fell, %d rose)" % (
                BASELINE, sum(1 for n in st["totals"].values() if n), len(st["stale"]), len(st["rise"])))
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


# ---- the two ledgers: names, and assembly with its reason ----------------------------------------------------------
# A name is never required: a function that matches is banked and pushed under the name it has. The names ledger is
# the game's record, and the tool reads only that it is its table. A row of the assembly ledger clears a count that
# blocks, so it must point at something that a reader can open: its evidence names a file and a line that the tree
# holds, and it names one function of a C file, or one assembly file. The rows that a change adds are the ones that
# are opened (`base`): a row that an earlier commit brought was checked there.
NAME_COLUMNS = ("kind", "image", "scope", "old_name", "new_name", "decision", "evidence", "reason")
ASM_COLUMNS = ("image", "symbol", "path", "class", "evidence", "date", "verified_by")
ASM_COLUMNS_OLD = ASM_COLUMNS[:6]                    # the header of psxdecomp 0.6.0 and earlier: read, and said
ASM_CLASSES = ("sdk-object", "hand-asm", "data-in-text")
ASM_EVIDENCE_RE = re.compile(r"^([^:\s]+):(\d+)$")
REFS = "config/refs.toml"
LABEL = re.compile(r"^\s*(?:glabel|jlabel|dlabel|\.globl|\.global)\s+([A-Za-z_.$][\w.$]*)|^([A-Za-z_.$][\w.$]*):", re.M)


def file_functions(text: str) -> set[str]:
    """The functions that a C file defines: a body or an INCLUDE_ASM stub."""
    code = PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), strip(text))
    return {m.group(1) for m in DEF_FUNC.finditer(code)} - NOT_A_NAME | set(STUB_NAME.findall(code))


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


def evidence_problem(tree: Tree, path: str, line: int) -> str | None:
    """Why `<path>:<line>` is no evidence in this tree, or None. The path is a file of the tree and the line is one
    of its lines. A path under a folder of which the tree holds nothing (an ignored folder: asm/, extracted/, refs/)
    is opened only in the work tree, and only where that folder is there. A file under refs/ is one of a reference
    that config/refs.toml names (refs/<the name of its `[[ref]]` table>/)."""
    if path.startswith("refs/"):
        name = path.split("/")[1] if path.count("/") else ""
        if name not in [r[0] for r in ref_rows(tree.read(REFS))]:
            return "%s: %s holds no `[[ref]]` table named %r" % (path, REFS, name)
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
    """[(FAIL|INFO, detail)] for the two ledgers of a tree (default: the work tree). A FAIL is a file that cannot be
    read as its table, or a row of the assembly ledger that points at nothing (it names no function of its C file,
    its evidence is no file and line of the tree). `base`: the tree a change starts from. The assembly rows it holds
    already are not opened again, only their form is read."""
    tree, out = tree or Tree(repo), []
    seen = set(lines(base.read(ASM_EVIDENCE))) if base is not None else set()
    raw = lines(tree.read(ASM_EVIDENCE))
    rows, errs = read_tsv(NAMES, NAME_COLUMNS, tree)
    if rows is None:
        out.append(("INFO", "no %s (`names --init` writes its header line)" % NAMES))
    else:
        out += [("FAIL", "%s: %s" % (NAMES, e)) for e in errs]
        out.append(("INFO", "%s: %d row(s)" % (NAMES, len(rows))))
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
            if raw[r["_line"] - 1] in seen:
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
            elif r["symbol"] not in file_functions(text):
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
    try:
        tree = Tree(repo, source)
        found = names_findings(repo, tree, Tree(repo, against) if against else None)
    except Fail as e:
        print("NAMES FAIL %s" % e)
        return 1
    for level, detail in found:
        print("NAMES %-4s %s" % (level, detail))
    bad = sum(f[0] == "FAIL" for f in found)
    print("NAMES %s (%d finding(s)%s)" % ("FAIL" if bad else "OK", bad, "; only the assembly rows that are new since "
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
    """The rules of a guard file, in order: (deny|allow, bash|path, pattern, say). A line that is no rule is skipped
    (`guard_errors` names such lines for the doctor)."""
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
    """The guard ran out of time (a pattern that backtracks): the call is refused."""


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
    """`guard --hook`: print the hook's JSON answer when a rule denies the call. It fails closed: an event it cannot
    read, a rule that runs for GUARD_SECONDS or any other failure of its own denies the call and says why. A checkout
    with no rules file has nothing to guard, and its calls run. The exit code is 0: the JSON decides."""
    def slow(*_):
        raise _Slow()

    def deny(say: str) -> None:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": "psxd guard (%s): %s" % (GUARD, say)}}))

    alarm = hasattr(signal, "SIGALRM")
    try:
        if alarm:
            signal.signal(signal.SIGALRM, slow)
            signal.alarm(GUARD_SECONDS)
        event = json.loads((stdin or sys.stdin).read())
        if not isinstance(event, dict):
            raise ValueError("the event is no JSON object")
        for root in guard_roots(event):
            text = _read(root / GUARD)
            if text is None:                           # a checkout with no rules file: the next one speaks
                continue
            say = guard_decision(event, parse_guard(text), root)
            if say:
                deny(say)
            break
    except _Slow:
        deny("a rule ran for %d seconds, so the guard refuses the call: a pattern of %s backtracks without end" % (GUARD_SECONDS, GUARD))
    except Exception as e:                             # a guard that cannot judge a call refuses it
        deny("the guard failed on this call (%s: %s), so it refuses it" % (type(e).__name__, " ".join(str(e).split())[:120]))
    finally:
        if alarm:
            signal.alarm(0)
    return 0


# ---- crutches and their markers: a register pin, an empty asm statement (a barrier) and a `goto` force the compiler
# and say nothing about the game. A `// !FAKE: <reason>` comment covers one of them. scripts/trial.py (tools/psxd_trial.py
# in a game) reads them here too.
MARK = re.compile(r"!FAKE:[ \t]*([^\n]*?)[ \t]*(?:\*/|$)", re.M)
BARRIER = re.compile(r"\b(?:asm|__asm__|__asm)\b\s*(?:(?:volatile|__volatile__|__volatile)\b\s*)?\(\s*\"(\s*)\"\s*\)\s*;")
PIN_CLAUSE = re.compile(r'\s*\b(?:asm|__asm__|__asm)\s*\(\s*"([^"\n]*)"\s*\)')   # what a trial cuts: the clause, nothing else
PIN_VAR = re.compile(r"([A-Za-z_]\w*)\s*$")
DECL_END = re.compile(r"[;{}]")



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
    def no_number(word):                               # `NaN`, `Infinity`: Python reads them, JSON has no such value
        raise ValueError(word)
    try:
        conf = json.loads(tree.read(SETTINGS) or "{}", parse_constant=no_number)
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


def state(repo, tree: Tree, here: bool = True, base: Tree | None = None) -> list[tuple[str, str]]:
    """[(check, detail)] for a tree as it stands: its baseline, its ledgers (`base`: the tree the change starts
    from, whose assembly rows are not opened again), and (`here`: the work tree holds this tree) the game's own
    debt scanner, its README and its category ids."""
    out = [("debt", f) for f in state_findings(repo, tree)[0]]
    out += [("names", d) for lv, d in names_findings(repo, tree, base) if lv == "FAIL"]
    if not here:
        return out
    out += own_debt(repo, tree)
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
                _write_baseline(repo, baseline_text(st["baseline"], st["totals"]))
                infos.append("%s: the totals of now written (%d rose, %d fell)" % (BASELINE, len(st["rise"]), len(st["stale"])))
                head = Tree(repo, None, untracked=True)
        passed = _handover(repo, head, args + ["--part", "state"]) if replaced and not fails else None
        if passed is None:
            here = mode in ("staged", "bank") or _rev(repo, "HEAD") == head.source
            if not here:
                infos.append("the work tree is not at %s: its README and category ids are not read" % head.source[:10])
            fails += state(repo, head, here, base)
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
    old = parse_baseline("mode macro count\n2 macro src/a.c\n1 flag src/a.c\nraise flag 1 2026-01-02 r\n")
    check("the baseline: the lines of a retired kind are dropped", (old.modes, old.totals, old.raises, old.other) == ({}, {}, [], []))
    bl = parse_baseline("# top\nmode goto down\nmode pin count\nmode shift down\n3 shift src/a.c\n"
                        "raise goto 2 2026-01-02 the first wave\nskip src/vendor/\n1 goto src/a.c\n# a note below a row\n")
    check("the baseline: its lines, and the lines of a kind this tool does not know", bl.version == 2
          and bl.head == ["# top", "# a note below a row"] and bl.policy("goto") == "down"
          and bl.policy("pin") == "count" and bl.other == ["mode shift down", "3 shift src/a.c"]
          and bl.raises == [("goto", 2, "2026-01-02", "the first wave")] and bl.lacks()[:2] == ["pin-unmarked", "goto-unmarked"], vars(bl))
    check("the baseline is written as totals: a row of a file adds to the total of its kind", bl.by_file and baseline_text(bl)
          == "# top\n# a note below a row\nskip src/vendor/\nmode pin count\nmode goto down\nmode shift down\n3 shift src/a.c\n"
          "raise goto 2 2026-01-02 the first wave\n1 goto\n", baseline_text(bl))
    two = parse_baseline("2 goto src/a.c\n3 goto src/b.c\n4 pin\n")
    check("the baseline: rows of files are summed, a total is read as it is", (two.totals, two.by_file) == ({"goto": 5, "pin": 4}, True)
          and parse_baseline(baseline_text(two)).totals == two.totals and not parse_baseline(baseline_text(two)).by_file, vars(two))
    early = parse_baseline("mode offset admit-new\nbudget pin 30 base 4 10 20\nmode asm down\n")
    check("the baseline: the lines of an unreleased build are read as `count`", (early.policy("offset"), early.policy("pin"),
          early.policy("asm")) == ("count", "count", "down"), early.modes)
    for name, text, want in (("two rows of one pair", "1 goto src/a.c\n1 goto src/a.c\n", "has two rows"),
                             ("two rows of one kind", "1 goto\n2 goto\n", "goto has two rows"),
                             ("a total beside the rows of its kind", "1 goto src/a.c\n1 goto\n", "goto has two rows"),
                             ("two policy lines of one kind", "mode goto down\nmode goto count\n", "two policy lines"),
                             ("a second mode line of version 1", "mode down\nmode admit\n", "a second `mode` line"),
                             ("the two versions in one file", "mode admit\nmode goto down\n", "of version 1 beside"),
                             ("a count too long to be a number", "%s goto src/a.c\n" % ("9" * 5000), ":1: not `<count> <kind>`"),
                             ("a line that is no line", "mode sideways\n", ":1: not `<count> <kind>`")):
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
            "mode asm down\nmode placeholder count\nmode placeholder-use count\n"
            "mode struct count\nmode extern count\nmode filename count\n1 goto\n1 asm\n"), text)
        rc, out = run(recount=True)
        check("--recount writes it", rc == 0 and base_file.read_text() == text and "DEBT RECOUNT written" in out
              and "DEBT INFO policy written: pin: count\n" in out, out)
        rc, out = run()
        check("an equal baseline passes", rc == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); down: pin-unmarked, goto-unmarked, "
              "barrier-unmarked, asm; count: pin, goto, barrier, offset, address, cast, field, placeholder, "
              "placeholder-use, struct, extern, filename)" in out, out)
        _git(repo, "add", "config")
        _commit(repo, "the floor")
        # a kind in mode `count` is counted and shown: the rows follow the tree, and nothing is refused
        walk.write_text(again)
        rc, out = run()
        check("a rise fails the equality of rows and counts, and names the command", rc == 1
              and "DEBT FAIL rise goto: 2, its row is 1\n" in out
              and "debt --update`, then commit config/debt-baseline.txt" in out, out)
        check("a counted kind is never refused", not judge("HEAD"), judge("HEAD"))
        rc, out = run(update=True)
        check("--update writes the total of a counted kind", rc == 0 and "DEBT INFO goto: 1 -> 2\n" in out
              and "2 goto\n" in base_file.read_text() and run()[0] == 0, out)
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
        base_file.write_text(text + "1 pin\n1 pin-unmarked\n")
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
        # the public tree of a game in split mode holds the totals of the files it does not publish too
        run(recount=True)
        base_file.write_text(base_file.read_text() + "3 offset\n")
        rc, out = run()
        check("a total over the tree is stale", rc == 1 and "DEBT FAIL stale offset: 0, its row is 3" in out, out)
        (repo / PUBLIC_PATHS).write_text("# the list\nsrc/\ninclude/\nconfig/\n")
        _git(repo, "add", PUBLIC_PATHS)
        check("and not in a public tree, where the list names each source file", run()[0] == 0, run()[1])
        (repo / PUBLIC_PATHS).write_text("src/walk.c\nsrc/boot.s\ninclude/\nconfig/\n")
        check("a tree with a source file that the list does not name is dev's: stale", run()[0] == 1)
        _git(repo, "rm", "-q", "-f", "--cached", PUBLIC_PATHS)
        (repo / PUBLIC_PATHS).unlink()
        run(recount=True)
        walk.write_text(C_CLEAN.replace("Player_Hp", "Walk"))
        rc, out = run()
        check("a stale row fails", rc == 1 and "DEBT FAIL stale goto: 0, its row is 2\n" in out, out)
        rc, out = run(down="goto")
        check("--down needs an equal baseline", rc == 1 and "not equal" in out, out)
        rc, out = run(update=True)
        check("--update lowers a row", rc == 0 and "DEBT INFO goto: 2 -> 0\n" in out and
              " goto\n" not in base_file.read_text(), out)
        (repo / "src" / "walk.c").write_text(C_CLEAN)
        (repo / "src" / "untracked.c").write_text(C_DEBT["goto"][0])        # never added: a count reads tracked files
        check("an untracked file under src/ is not counted", not any(p == "src/untracked.c" for _, p in debt_counts(repo)))
        (repo / "src" / "boot.s").write_text("glabel boot\n    nop\n")
        (repo / "docs").mkdir()
        (repo / "docs" / "boot.md").write_text("# The boot code\n\nThe vendor wrote it in assembly.\n")
        _git(repo, "add", "docs")
        (repo / ASM_EVIDENCE).write_text("\t".join(ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\thand-asm\tdocs/boot.md:3\t2026-01-02\tdeveloper\n")
        rc, out = run()
        check("an evidence row clears an assembly file", rc == 1 and "DEBT FAIL stale asm: 0, its row is 1" in out, out)
        (repo / BASELINE).write_text("mode sideways\n")
        rc, out = run()
        check("a baseline line that is no row", rc == 1 and "config/debt-baseline.txt:1: not " in out, out)
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
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/gone.c:4\tthe string it prints\n"
        (repo / NAMES).write_text("\ufeff" + "\t".join(NAME_COLUMNS) + "\n" + row.replace("\tthe string it prints", "\t"))
        rc, out = _capture(cmd_names, repo)
        check("names: a row is the game's record: its evidence is not opened; a trimmed last cell and a BOM are read",
              rc == 0 and "config/names.tsv: 1 row(s)" in out and "NAMES OK (0 finding(s))" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row + row.replace("\n", "\tmore\n"))
        rc, out = _capture(cmd_names, repo)
        check("names: a row with more cells than the header fails", rc == 1 and "NAMES FAIL config/names.tsv: line 3: 9 cell(s), not 8" in out, out)
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n" + row)
        _git(repo, "add", "config")
        # an assembly row names one function of a C file, never the file
        two = 'void A(void) {\n    __asm__("nop");\n}\nvoid B(void) {\n    __asm__("nop");\n}\n'
        (repo / "src" / "two.c").write_text(two)
        _git(repo, "add", "src/two.c")
        asm_row = lambda sym, ev="docs/boot.md:3", who="developer": "\t".join(ASM_COLUMNS) + "\nmain\t%s\tsrc/two.c\thand-asm\t%s\t2026-01-02\t%s\n" % (sym, ev, who)  # noqa: E731
        (repo / ASM_EVIDENCE).write_text(asm_row("A"))
        check("an assembly row clears the function it names, and no other", _capture(cmd_names, repo)[0] == 0
              and debt_bodies(repo)["src/two.c"] == {"A": {}, "B": {"asm": 1}}, debt_bodies(repo)["src/two.c"])
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
        check("names: the cells of a row are not judged", rc == 0, out)
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
    "data and a struct are file scope": ("s32 D_800A1234 = 4;\nstruct S {\n    s32 a;\n};\n", {SCOPE: {"placeholder": 1, "struct": 1}}),
}


def self_test_bodies(check) -> None:
    for name, (text, want) in C_BODIES.items():
        got = file_bodies("src/a.c", text)
        check("bodies: " + name, got == want, got)
    stubs = scan_file("src/a.c", C_BODIES["a body beside its stub"][0])["stubs"]
    check("bodies: the stub lines of a file are counted", stubs == 1, stubs)
    for name, text in [(k, t) for k, (t, _) in C_DEBT.items()] + [(k, t) for k, (t, _) in C_BODIES.items()] + [("clean", C_CLEAN)]:
        for rel in ("src/a.c", "include/a.h"):
            total: dict[str, int] = {}
            for got in file_bodies(rel, text).values():
                for kind, n in got.items():
                    total[kind] = total.get(kind, 0) + n
            check("bodies: the sum of a file's bodies is its count: %s (%s)" % (name, rel), total == file_debt(rel, text), total)
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
        check("debt --files: a file with no debt of any kind is finished, with no names ledger", rc == 0
              and "DEBT FILE finished src/done.c\n" in out and "DEBT FILE stubs    src/half.c\n" in out
              and "DEBT FILE matched  src/one.c: goto 1\n" in out and "table.c" not in out
              and out.endswith("DEBT FILES 4 C file(s): 1 finished, 2 matched, 1 with stubs\n"), out)
        (repo / "config").mkdir()
        (repo / PUBLIC_PATHS).write_text("src/one.c\nsrc/half.c\n")
        _git(repo, "add", "config")
        rc, out = _capture(cmd_files, repo, public=True)
        check("debt --files --public: the files that the repository publishes, as its public tree counts them", out.endswith(
            "DEBT FILES 2 C file(s): 0 finished, 1 matched, 1 with stubs\n") and "src/one.c: goto 1\n" in out, out)
        _git(repo, "rm", "-q", "-f", "--cached", PUBLIC_PATHS)
        (repo / PUBLIC_PATHS).unlink()


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
            ("an instruction behind a separator spelled as an escape is assembly",
             '__asm__(".set noat\\x3b j $ra\\x3b nop");\n__asm__(".section .text\\012\\t.word 0x3c1a8003");\n__asm__(".set reorder\\073 jr $ra");\n', {"asm": 3}),
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
        # a macro of a header and of an included C file that hides an offset counts where it is used
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
        check("the view: every C file is a unit, also one that another unit includes", ran() == [
            "src/alone.c", "src/other.c", "src/shared/body.c", "src/unit.c"])
        _commit(repo, "the tree")
        for name, src in (("the index", INDEX), ("a revision", "HEAD"), ("the work tree with the files git does not track", None)):
            tree = Tree(repo, src, untracked=src is None)
            check("the view: %s gives the same count" % name, debt_counts(repo, tree=tree) == want, debt_counts(repo, tree=tree))
        check("the view: no unit ran again, each result was kept beside the files it read", ran() == [], "ran")
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    // !FAKE: the loop of the original\n    if (n--) AGAIN;\n    return n;\n}\n")
        got = debt_bodies(repo)
        check("the view: a marker in the file that holds the line covers the construct", got["src/shared/body.c"] == {"One": {"goto": 1}}
              and got["src/pins.def"] == {SCOPE: {"pin": 1, "pin-unmarked": 1}}, got)
        check("the view: one changed file costs the units that read it", ran() == ["src/other.c", "src/shared/body.c", "src/unit.c"])
        put("src/alone.c", 's32 Alone(s32 n) {\n    __asm__("nop");\n    return n;\n}\n')
        check("the view: an asm statement in a function", debt_counts(repo).get(("asm", "src/alone.c")) == 1 and ran() == ["src/alone.c"])
        put(ASM_EVIDENCE, "\t".join(ASM_COLUMNS) + "\nmain\tAlone\tsrc/alone.c\thand-asm\tsrc/alone.c:2\t2026-01-02\tdeveloper\n")
        check("the view: an assembly row clears the function that holds the line", ("asm", "src/alone.c") not in debt_counts(repo))
        (repo / ASM_EVIDENCE).unlink()
        global _cpp_cache_on
        _cpp_cache_on = False
        debt_counts(repo)
        check("the view: a push and CI run every unit again", ran() == ["src/alone.c", "src/other.c", "src/shared/body.c", "src/unit.c"])
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
        check("the first baseline holds the totals of the view", "1 pin-unmarked\n" in (repo / BASELINE).read_text()
              and "1 goto-unmarked\n" in (repo / BASELINE).read_text() and _capture(cmd_debt, repo)[0] == 0, (repo / BASELINE).read_text())
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
            put("src/b.c", '#include "common.h"\n#ifndef HIDE_B\nint Bfunc(int n) {\nagain:\n    if (--n) goto again;\n    return n;\n}\n#endif\n')
            put("src/c.c", '#include "common.h"\n#define HIDE_B 1\n#define IN_UNIT 1\n#include "b.c"\nint Cfunc(void) {\n#include "tail.c"\n}\n')
            put("src/tail.c", "#ifndef IN_UNIT\n#error this fragment stands inside a unit\n#endif\n    return 0;\n")
            _git(repo, "add", "-A")
            try:
                got = debt_counts(repo).get(("goto-unmarked", "src/b.c"))
            except Fail as e:
                got = str(e)
            check("a real preprocessor: a file is read alone as well, so the macros of a unit that includes it hide nothing", got == 1, got)
            (repo / "src/c.c").unlink()
            _git(repo, "add", "-A")
            try:
                debt_counts(repo)
                check("a real preprocessor: a fragment that fails alone and that no unit reads is a refusal", False)
            except Fail as e:
                check("a real preprocessor: a fragment that fails alone and that no unit reads is a refusal", "src/tail.c" in str(e), str(e))


def self_test_tree(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(td)
        (repo / "src").mkdir()
        (repo / "src" / "walk.c").write_text(C_DEBT["goto"][0])
        (repo / "src" / "two.c").write_bytes(C_DEBT["struct"][0].replace("\n", "\r\n").encode())
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
            debt_counts(repo, tree=Tree(repo, src)).get(("struct", "src/two.c")) == 1 for src in ("HEAD", INDEX, None)))
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


def self_test_markers(check) -> None:
    check("markers: a reason is a text", reason_ok("the loop counter") and not reason_ok("") and not reason_ok("-- ?") and not reason_ok(None))
    one = 'void A(void) {\n    // !FAKE: both\n    register s32 a asm("$4");\n    register s32 b asm("$5");\n}\n'
    check("markers: one marker covers one pin", file_debt("src/a.c", one) == {"pin": 2, "pin-unmarked": 1}, file_debt("src/a.c", one))
    tail = 'void A(void) {\n    register s32 a asm("$4"); // !FAKE: the first one\n    register s32 b asm("$5");\n}\n'
    check("markers: a marker behind a pin does not cover the pin below", file_debt("src/a.c", tail) == {"pin": 2, "pin-unmarked": 1})
    bare = 'void A(void) {\n    // !FAKE:\n    register s32 a asm("$4");\n    register s32 b asm("$5"); /* !FAKE: */\n}\n'
    check("markers: a marker with no reason covers nothing", file_debt("src/a.c", bare) == {"pin": 2, "pin-unmarked": 2})
    quoted = 'void A(void) {\n    register s32 a asm("$4"); Log("!FAKE: the first one");\n}\n'
    check("markers: a marker in a string is no marker", file_debt("src/a.c", quoted) == {"pin": 1, "pin-unmarked": 1})


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
            check("gate: an address name, a guessed name and a provisional row with no evidence pass", rc == 0
                  and "GATE WARN" not in out and "1 placeholder\n" in (repo / BASELINE).read_text() and out.endswith("GATE OK (staged)\n"), out)
            put(NAMES, "kind\tname\n")
            rc, out = staged()
            check("gate: a names ledger that cannot be read fails", rc == 1 and "GATE FAIL names: config/names.tsv: line 1: the header is not" in out, out)
            undo()
            # the baseline: a row written by hand, a policy line taken out, a new skip line
            put("src/walk.c", C_DEBT["goto"][0] + C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(BASELINE, base_text.replace("1 goto\n", "1 pin\n1 pin-unmarked\n1 goto\n"))
            rc, out = staged()
            check("gate: a row written by hand admits nothing", rc == 1 and "GATE FAIL debt: pin-unmarked is `down` and its total "
                  "rose: 0 -> 1 (src/walk.c 0 -> 1)\n" in out and out.endswith("GATE FAIL (staged; 1 finding(s))\n"), out)
            undo()
            put("src/walk.c", C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(BASELINE, base_text.replace("1 goto\n", "2 goto\n"))
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
                else base_text.replace("1 goto\n", "raise protected 1 2026-01-02 the runner changed\n1 goto\n"))
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
            check("gate --bank counts a file that is not tracked yet and writes the totals", rc == 0 and "2 goto\n" in (repo / BASELINE).read_text()
                  and "GATE INFO config/debt-baseline.txt: the totals of now written (1 rose, 0 fell)" in out
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
            put(BASELINE, ((repo / BASELINE).read_text() + "1 pin\n1 pin-unmarked\n"))
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
            put(BASELINE, ((repo / BASELINE).read_text() + "1 pin\n1 pin-unmarked\n")
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
                put(BASELINE, baseline_text(bl, _kind_totals(debt_counts(repo, bl.skip, Tree(repo, None, untracked=True)))))

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
        for name, stdin in (("an allowed call", json.dumps(cases[3][1])), ("an event with no cwd", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
                            ("another tool", json.dumps({"tool_name": "Read", "tool_input": {"file_path": "asm/a.s"}, "cwd": str(root)}))):
            check("guard --hook: %s prints nothing, exit 0" % name, _capture(guard_hook, io.StringIO(stdin)) == (0, ""))
        for name, stdin in (("bad JSON", "{not json"), ("no event", ""), ("a list", "[1]"), ("null", "null"),
                            ("an input that is no object", json.dumps({"tool_name": "Edit", "tool_input": "x"})),
                            ("a path that is a number", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 7}, "cwd": str(root)})),
                            ("a path with a NUL", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "asm/a\0.s"}, "cwd": str(root)}))):
            rc, out = _capture(guard_hook, io.StringIO(stdin))
            check("guard --hook: %s is refused: the guard fails closed" % name, rc == 0 and '"permissionDecision": "deny"' in out
                  and ("the guard failed on this call" in out or "asm/ is generated" in out), out)
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
        # a pattern that backtracks without end: the hook gives up and refuses the call
        global GUARD_SECONDS
        keep, GUARD_SECONDS = GUARD_SECONDS, 1
        (root / GUARD).write_text("deny\tbash\t(\\w+\\s*)+$\tNo.\n")
        slow = {"tool_name": "Bash", "tool_input": {"command": "echo " + "word " * 40 + "!"}, "cwd": str(root)}
        import time
        t0 = time.time()
        got = _capture(guard_hook, io.StringIO(json.dumps(slow)))
        GUARD_SECONDS = keep
        check("guard --hook: a pattern that hangs is cut off, and the call is refused", got[0] == 0 and '"deny"' in got[1]
              and "a rule ran for 1 seconds" in got[1] and time.time() - t0 < 4, (got, time.time() - t0))
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
        self_test_debt(check)
        self_test_bodies(check)
        self_test_files(check)
        self_test_tree(check)
        self_test_markers(check)
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
    ap.add_argument("cmd", nargs="?", choices=["debt", "names", "toolchain", "guard", "gate"])
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
    if a.cmd == "debt":
        if a.staged and a.rev:
            ap.error("debt: --staged or --rev, not both")
        if a.files:
            return cmd_files(a.repo, INDEX if a.staged else a.rev, a.public)
        return cmd_debt(a.repo, update=a.update, down=a.down, source=INDEX if a.staged else a.rev,
                        against=a.against, recount=a.recount, raise_=a.raise_, reason=a.reason)
    if a.cmd == "names":
        return cmd_names(a.repo, init=a.init, source=INDEX if a.staged else a.rev, against=a.against)
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
