#!/usr/bin/env python3
"""img.py — the map of another build of a game onto its retail build, and the strings that name its functions.

psxdecomp delivers this file into a game as tools/psxd_img.py (`owned`: a game does not edit it). It needs the
standard library only, and it runs with `python3 -I`. The plugin's `oracle measure` imports its functions.

    psxd_img.py proto --id ID --build DIR --exe PATH [--retail DIR] [--repo DIR]
    psxd_img.py strnames [--proto ID:DIR:PATH]... [--check] [--retail DIR] [--repo DIR]
    psxd_img.py show KEY [--repo DIR]
    psxd_img.py promote UNIT VRAM NAME [--repo DIR]
    psxd_img.py measure RETAIL_EXE BUILD_EXE
    psxd_img.py --self-test | --version

Every table holds keys, addresses and counts only: no word and no text of a game reaches a tracked file. The text
goes to an ignored file under .run/, and `show` prints it.

The contract: what the game writes, and this tool reads.
  config/oracle.units.tsv   tracked, written by the game's load-map tool (phase 1.2). Two `#` lines (the tool, the
                            columns), then `unit file offset vram words class`. class `exe` (one row: a PS-X EXE, its
                            words from offset 0x800, vram = the header's address) or `code` (words of the file from
                            offset, loaded at vram). file: a path under the retail folder. offset: hex. words: decimal.
  .run/oracle/functions.tsv ignored, written by the game's census (phase 1.5). Two `#` lines, then `unit vram words
                            name lane state`. lane `game | lib`; state as the census gives it (`c`, `asm`).
                            Without the file, strnames finds each start by a scan, and proto writes no functions table.
  config/oracle.retail      one line: the retail folder, relative to the repository (the default of --retail).

  proto     The tables of one build, against retail's units. --build: a folder with the build's files under retail's
            paths; --exe: the build's executable, a path inside --build. Writes config/oracle.<id>.map.tsv,
            config/oracle.<id>.strings.tsv and (with a function list) config/oracle.<id>.functions.tsv, each under two
            `#` lines, and the strings' text to .run/oracle/<id>/strings.txt.
  strnames  The functions that build the address of a string, in every unit. Each --proto adds the texts that the
            build has and retail lacks. Writes config/oracle.strnames.tsv and the text to .run/strnames/strings.txt.
            --check: the table regenerated in memory must equal the tracked one, and each row of
            config/oracle.strnames.aliases.tsv (`unit vram alias keys basis`, written by hand) must name a function and
            keys of the table. It writes nothing. A problem exits 1.
  show      The text of a key, from the ignored files (a developer with the disc reads the evidence).
  promote   One `provisional` row in config/names.tsv (rules/NAME1.md) for the function at UNIT VRAM of the strnames
            table: evidence `string:config/oracle.strnames.tsv:<line>`. One name per command, never in bulk.
  measure   The map of two PS-X EXEs and the build-only strings: one count line.

The core (from mmx5, mmx6 and dc2's imgcore.py, 2026-10-14; the functions keep their behaviour):
  mask     loose(): the target of each j/jal, the immediate of each lui and the immediate of each LO_OPS word are
           cleared. A stream has no function start, so every base register is taken as set by a lui.
  pair     (retail words, build words, cuts, build file name, build base, ram): two streams that are compared.
           cuts = [(unit, first word, words, vram)], the units of the retail stream. base = the address of word 0
           of the build's stream; ram = True for a RAM address (`0x%08X`), False for a file offset (`0x%X`).
           Build words `()`: the build has no such file.
  map      An anchor is a 16-word window that occurs once in each stream; the anchors of the longest chain in one
           order are kept, and each is extended under the mask to a maximal run. The same is then done in each gap
           between two neighbouring runs. Code that moved out of order, and code with no anchor, is not mapped: an
           undercount, never a false row.
           row: unit, retail 0xVRAM, words, build file, build address. A run is cut at the ends of the units.
  strings  Each printable string (>= 6 characters, then NUL) of the build's executable that retail's executable
           lacks; the code of the build's executable that builds its address (lui + addiu/ori); that code's retail
           address through the map, else the nearest mapped word within 32 words.
           row: key (12 hex of the text's sha1), length, class (format | path | other), build data address, build
           code address or -, retail unit or -, retail 0xVRAM or -, distance or - (words from the reference to the
           mapped word; 0: the reference itself is mapped). One row per reference.
  functions  One row per retail function (>= 8 words) that the build holds: its body, under the mask, is equal
           over the full length to words of the build.
           row: unit, 0xVRAM, name, words, state, build file or -, build address or -, basis, places.
           basis `run`: the body lies whole in one run of the map; the address is the run's. basis `search`: no
           run holds it, and the body is found elsewhere in the build; the address is written only when places
           is 1. places = the places of the build that hold the body (for `run`: the run's place included).
           The mask is loose, so a row is a lead: two bodies that differ only in masked fields are one body here.
  strnames The functions of retail that build the address of a string (lui + addiu/ori): name leads.
           text: the rules of two proven tools, no rule of ours. Ghidra's reference analyzer (12.1.4,
           OperandReferenceAnalyzer, its defaults): bytes 0x20-0x7E, tab, LF or CR, >= 5 of them, then a NUL within
           1000 bytes. Or spimdisasm's C string decoder (1.42.4, Utils.decodeBytesToStrings, Shift-JIS): no banned
           control byte, a Shift-JIS decode, a NUL, NUL bytes to the next 4-byte boundary; with GNU strings' floor of
           4 bytes (spimdisasm's symbol checks, such as one reference, are not modelled). class: sjis when a byte is
           >= 0x80, else format | path | other. Neither tool judges the content: a byte table that passes is a row,
           and it gets no alias. Read at each address that code builds or a word holds.
           A table: >= 2 consecutive words that are each the address of a text. A pair that builds the address of a
           text is `direct`; of a table, `table` (one row per text of the table). A unit sees its own texts, then
           those of the executable. gp-relative loads are not read: an undercount.
           The function: from the list (start `list`), else by a scan back to the word after the nearest `jr ra` and
           its delay slot, zero words skipped (start `scan`; an early return makes it wrong: a lead).
           A build adds the texts that retail lacks (the bytes and their NUL occur in no retail unit), from the
           build's executable, referenced from its code where the map holds that code word (distance 0); the row is
           retail's function and retail's code address. Other references give no row.
           row: unit, 0xVRAM, name, 0xCODE, key (12 hex of the text's sha1), length, class, via (direct | table),
           source (retail | a build id), start (list | scan). One row per function, text and source: the first
           reference.
"""
import argparse
import hashlib
import re
import struct
import sys
import tempfile
from bisect import bisect_left, bisect_right
from collections import defaultdict, namedtuple
from pathlib import Path

LO_OPS = {9, 13} | set(range(32, 39)) | {40, 41, 42, 43, 46, 49, 50, 57, 58}  # addiu ori, lb..lwr, sb..swr, lwc/swc1-2
MIN_WORDS = 8   # the short-function floor
ANCHOR = 16     # words of a map anchor
LUI_WINDOW = 16  # words a lui stays live for its addiu/ori
NEAR = 32       # words from a string's reference to the nearest mapped word that is still a lead
HEADER = 0x800  # the PS-X EXE header
STRING = re.compile(rb"[\x20-\x7e]{6,}")
FORMAT = re.compile(rb"%[-+ #0-9.]*l?[cdiopsuxX]")
PATH = re.compile(rb"[\\/]|\.[chsCHS]\b")
GHIDRA = re.compile(rb"[\t\n\r\x20-\x7e]{5,}")  # OperandReferenceAnalyzer: isValidAsciiByte, min length 5
LONGEST = 1000  # bytes Ghidra reads for a string
FLOOR = 4       # GNU strings' default minimum
BANNED = {*range(9), 11, *range(14, 26), *range(28, 32), 127}  # spimdisasm bannedEscapeCharacters
SPECIAL = {26, 27, 140, 141}                                   # spimdisasm escapeCharactersSpecialCases
JR_RA = 0x03E00008


def die(msg):
    sys.exit(f"psxd_img: {msg}")


def words(b):
    return struct.unpack(f"<{len(b) // 4}I", b[:len(b) // 4 * 4])


def loose(ws):
    """The mask of a stream: jump targets, lui immediates and the immediates of LO_OPS words cleared."""
    out = []
    for w in ws:
        op = w >> 26
        if op in (2, 3):
            w &= ~0x3FFFFFF
        elif op == 15 or op in LO_OPS:
            w &= ~0xFFFF
        out.append(w & 0xFFFFFFFF)
    return tuple(out)


def key(dk):
    return hashlib.sha1(struct.pack(f"<{len(dk)}I", *dk)).hexdigest()


# ---- the map ---------------------------------------------------------------------------------------------------------

def chain(pairs):
    """The longest subsequence of pairs (sorted by i) whose j also rises."""
    js, tails, prev = [], [], {}
    for p in pairs:
        k = bisect_left(js, p[1])
        prev[p] = tails[k - 1] if k else None
        js[k:k + 1], tails[k:k + 1] = [p[1]], [p]
    out, p = [], tails[-1] if tails else None
    while p:
        out.append(p)
        p = prev[p]
    return out[::-1]


def runs(a, b):
    """[(i, j, n)]: a[i:i+n] == b[j:j+n], rising and disjoint in both streams. a, b: loose words.
    The anchors of the two streams first, then those of each gap between two neighbouring runs, while one is found."""
    def once(ws, lo, hi):
        seen = {}
        for i in range(lo, hi - ANCHOR + 1):
            seen[ws[i:i + ANCHOR]] = i if ws[i:i + ANCHOR] not in seen else -1
        return seen

    out, gaps = [], [(0, len(a), 0, len(b))]
    while gaps:
        i0, i1, j0, j1 = gaps.pop()
        wa, wb = once(a, i0, i1), once(b, j0, j1)
        new, ei, ej = [], i0, j0
        for i, j in chain(sorted((i, wb[g]) for g, i in wa.items() if i >= 0 and wb.get(g, -1) >= 0)):
            if new and i < ei and j - i == new[-1][1] - new[-1][0]:
                continue  # inside the last run
            s = max(ei - i, ej - j, 0)  # an anchor is unique, so the last run covers under ANCHOR of its words
            i, j, n = i + s, j + s, ANCHOR - s
            while i > ei and j > ej and a[i - 1] == b[j - 1]:
                i, j, n = i - 1, j - 1, n + 1
            while i + n < i1 and j + n < j1 and a[i + n] == b[j + n]:
                n += 1
            if ei + ANCHOR <= i and ej + ANCHOR <= j:
                gaps.append((ei, i, ej, j))
            new.append((i, j, n))
            ei, ej = i + n, j + n
        if new and ei + ANCHOR <= i1 and ej + ANCHOR <= j1:
            gaps.append((ei, i1, ej, j1))
        out += new
    return sorted(out)


def lookup(rs, col, x, n=1):
    """The run of rs that holds [x, x+n) in stream col (0 = a, 1 = b), or None."""
    k = bisect_right([r[col] for r in rs], x) - 1
    return rs[k] if k >= 0 and x + n <= rs[k][col] + rs[k][2] else None


def twin(rs, x):
    """(the word of stream a, distance) for word x of stream b: through its run (distance 0), else through the
    nearest mapped word of b within NEAR words (distance = that word - x), else None."""
    k = bisect_right([r[1] for r in rs], x) - 1
    best = None
    if k >= 0:
        i, j, n = rs[k]
        if x < j + n:
            return i + x - j, 0
        best = (i + n - 1, j + n - 1 - x)
    if k + 1 < len(rs) and (best is None or rs[k + 1][1] - x < -best[1]):
        best = (rs[k + 1][0], rs[k + 1][1] - x)
    return best if best and abs(best[1]) <= NEAR else None


def place(pair, j):
    """(the build's file name, the address of word j of the build's stream) as a table writes them."""
    return pair[3], ("0x%08X" if pair[5] else "0x%X") % (pair[4] + 4 * j)


def map_rows(pairs):
    """(the rows of <id>-map, [the runs of each pair]). A run is cut at the ends of the pair's units."""
    rows, out = [], []
    for p in pairs:
        rs = runs(loose(p[0]), loose(p[1]))
        out.append(rs)
        for u, first, size, vram in p[2]:
            for i, j, n in rs:
                lo, hi = max(i, first), min(i + n, first + size)
                if lo < hi:
                    rows.append((u, f"0x{vram + 4 * (lo - first):08X}", str(hi - lo), *place(p, j + lo - i)))
    return rows, out


# ---- the strings -----------------------------------------------------------------------------------------------------

def refs(ws, base):
    """{address: [the address of the lui]}: each lui + addiu/ori pair of the words at base."""
    hi, out = {}, defaultdict(list)
    for i, w in enumerate(ws):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op in (9, 13) and rs in hi and i - hi[rs][1] <= LUI_WINDOW:
            out[(hi[rs][0] << 16) + (imm - (imm & 0x8000) * 2 if op == 9 else imm) & 0xFFFFFFFF].append(
                base + 4 * hi[rs][1])
        dest = (w >> 11) & 31 if op == 0 else rt if 8 <= op <= 15 or 32 <= op <= 38 else 31 if op == 3 else None
        hi.pop(dest, None)
        if op == 15:
            hi[rt] = (imm, i)
    return out


def strings(proto, retail):
    """[(offset, text)]: the NUL-ended printable strings of proto that are no such string of retail."""
    def ended(b):
        return [(m.start(), m.group()) for m in STRING.finditer(b) if b[m.end():m.end() + 1] == b"\x00"]
    have = {s for _, s in ended(retail)}
    return [(o, s) for o, s in ended(proto) if s not in have]


def kind(text):
    return "format" if FORMAT.search(text) else "path" if PATH.search(text) else "other"


def string_rows(build, retail, pbase, rs, unit, base):
    """(the rows of <id>-strings, the `key<TAB>text` lines in key order). build, retail: the two executables after
    the header; pbase, base: their RAM addresses; rs: the runs of the two (retail is stream a); unit: retail's name.
    The lines hold a game's text: an adapter writes them to an ignored path only."""
    code = refs(words(build), pbase)
    rows, text = [], {}
    for off, s in strings(build, retail):
        k, addr = hashlib.sha1(s).hexdigest()[:12], pbase + off
        text[k] = f"{k}\t{s.decode('ascii')}\n"
        for at in code.get(addr) or [None]:
            t = twin(rs, (at - pbase) // 4) if at else None
            rows.append((k, str(len(s)), kind(s), f"0x{addr:08X}", f"0x{at:08X}" if at else "-",
                         *((unit, f"0x{base + 4 * t[0]:08X}", str(t[1])) if t else "---")))
    return rows, [text[k] for k in sorted(text)]


def string_counts(rows):
    """(strings, those with a reference, those with a retail twin, those more with retail code within NEAR words)."""
    at = {d: {r[3] for r in rows if r[7] != "-" and (r[7] == "0") == d} for d in (True, False)}
    return (len({r[3] for r in rows}), len({r[3] for r in rows if r[4] != "-"}), len(at[True]),
            len(at[False] - at[True]))


# ---- the functions ---------------------------------------------------------------------------------------------------

def function_rows(functions, pairs, rs):
    """(the rows of <id>-functions, the number of functions asked). functions: [(unit, vram, name, words, state)],
    the lane an adapter picks; one under MIN_WORDS is not asked. pairs, rs: as map_rows takes and returns them."""
    la, lb = [loose(p[0]) for p in pairs], [loose(p[1]) for p in pairs]
    cut = {c[0]: (k, c) for k, p in enumerate(pairs) for c in p[2]}
    asked = []
    for unit, vram, name, n, state in functions:
        if n < MIN_WORDS:
            continue
        if unit not in cut:
            die(f"{unit} 0x{vram:08X} {name}: no unit of this name")
        k, (_, first, size, base) = cut[unit]
        o = (vram - base) // 4
        if o < 0 or o + n > size or (vram - base) % 4:
            die(f"{unit} 0x{vram:08X} {name}: outside the unit")
        asked.append((unit, vram, name, n, state, k, first + o))
    want, ix = {la[k][x:x + MIN_WORDS] for *_, k, x in asked}, defaultdict(list)
    for q, s in enumerate(lb):
        for j in range(len(s) - MIN_WORDS + 1):
            if s[j:j + MIN_WORDS] in want:
                ix[s[j:j + MIN_WORDS]].append((q, j))
    rows = []
    for unit, vram, name, n, state, k, x in asked:
        body = la[k][x:x + n]
        hits = [(q, j) for q, j in ix.get(body[:MIN_WORDS], ()) if lb[q][j:j + n] == body]
        r = lookup(rs[k], 0, x, n)
        if not hits:
            continue
        at = (k, r[1] + x - r[0]) if r else hits[0] if len(hits) == 1 else None
        rows.append((unit, f"0x{vram:08X}", name, str(n), state, *(place(pairs[at[0]], at[1]) if at else "--"),
                     "run" if r else "search", str(len(hits))))
    return rows, len(asked)


# ---- strnames: the strings that a function loads --------------------------------------------------------------------

def pack(ws):
    return struct.pack(f"<{len(ws)}I", *ws)


def decodes(b):
    try:
        b.decode("shift_jis")
        return True
    except UnicodeDecodeError:
        return False


# spimdisasm_size ports decodeBytesToStrings of spimdisasm 1.42.4 (https://github.com/Decompollaborate/spimdisasm):
#   MIT License. Copyright (c) 2022 Decompollaborate.
#   Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
#   documentation files (the "Software"), to deal in the Software without restriction, including without limitation
#   the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
#   to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
#   copyright notice and this permission notice shall be included in all copies or substantial portions of the
#   Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
#   LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
#   SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#   OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#   DEALINGS IN THE SOFTWARE.
def spimdisasm_size(buf, offset):
    """The size of the C string at offset as spimdisasm decodes it (Shift-JIS), or < 0: not a string."""
    dst, i = bytearray(), 0
    while offset + i < len(buf) and buf[offset + i] != 0:
        char, nxt = buf[offset + i], buf[offset + i + 1] if offset + i + 1 < len(buf) else None
        if char in BANNED:
            return -10
        valid = False
        if char > 0x7F:
            valid = decodes(bytes(dst) + bytes([char])) or (nxt is not None and nxt != 0x5C
                                                              and decodes(bytes(dst) + bytes([char, nxt])))
            if not valid and nxt == 0x5C:
                if dst and not decodes(dst):
                    return -60
                dst.clear()
                i += 2
                continue
        if not valid and char in SPECIAL:
            if dst and not decodes(dst):
                return -70
            dst.clear()
        else:
            dst.append(char)
        i += 1
    if offset + i >= len(buf):
        return -80
    if dst and not decodes(dst):
        return -90
    end = offset + i
    return i if not buf[end:min((end & ~3) + 4, len(buf))].strip(b"\x00") else -100


def text_at(b, off):
    """(bytes, class) of the text at offset off of b (the header's rules), else None. b starts 4-aligned."""
    end = b.find(b"\x00", off, off + LONGEST + 1) if 0 <= off else -1
    t = b[off:end] if end > off else b""
    if not GHIDRA.fullmatch(t):
        n = spimdisasm_size(b[off & ~3:off + LONGEST + 8], off & 3) if 0 <= off < len(b) else -1
        t = b[off:off + n] if n >= FLOOR else b""
    return (t, "sjis" if max(t) > 0x7F else kind(t)) if t else None


def shown(t):
    """A text as strings.txt shows it: Shift-JIS, an undecodable byte as \\xNN, tab LF CR as \\t \\n \\r."""
    return t.decode("shift_jis", "backslashreplace").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def texts(b, base, addrs):
    """{address: (bytes, class)}: the addresses of addrs that hold a text in the bytes at base. A text is read from
    the address that the code builds, so a text inside another, or after other printable bytes, is found."""
    out = {}
    for a in addrs:
        if base <= a < base + len(b):
            t = text_at(b, a - base)
            if t:
                out[a] = t
    return out


def known(units, shared, seen=None):
    """(texts, tables) of units [(unit, base, words)]. A unit's candidates are its words and the addresses its code
    builds; the shared unit's are those of every unit of seen (default: units)."""
    cand = {u: set(ws) | set(refs(ws, base)) for u, base, ws in seen or units}
    every = set().union(*cand.values())
    txt = {u: texts(pack(ws), base, every if u == shared else cand[u]) for u, base, ws in units}
    return txt, {u: pointer_tables(ws, base, {**txt.get(shared, {}), **txt[u]}) for u, base, ws in units}


def pointer_tables(ws, base, txt):
    """{table address: [text addresses]}: each run of >= 2 consecutive words that are each a key of txt."""
    out, k = {}, 0
    while k < len(ws):
        n = 0
        while k + n < len(ws) and ws[k + n] in txt:
            n += 1
        if n >= 2:
            out[base + 4 * k] = list(ws[k:k + n])
        k += n or 1
    return out


def string_refs(units, txt, tables, shared):
    """[(unit, code address, text address, via)]. units: [(unit, base, words)]; txt, tables: {unit: texts(),
    pointer_tables()}; shared: the unit whose texts every unit sees (the executable). The unit's own first."""
    out = []
    for u, base, ws in units:
        for at, codes in sorted(refs(ws, base).items()):
            hit = []
            for src in (u, shared):
                if at in txt.get(src, {}):
                    hit = [(at, "direct")]
                elif at in tables.get(src, {}):
                    hit = [(s, "table") for s in tables[src][at]]
                if hit:
                    break
            out += [(u, c, s, via) for c in codes for s, via in hit]
    return out


def start_of(ws, base, at):
    """The scan: the word after the nearest `jr ra` before at and its delay slot, zero words skipped."""
    i = (at - base) // 4
    s = next((k for k in range(i - 2, -1, -1) if ws[k] == JR_RA), -2) + 2
    while s < i and ws[s] == 0:
        s += 1
    return base + 4 * s


def units_of(pairs):
    """[(unit, vram, words)]: the retail units of pairs (stream a, cut), in the pairs' order."""
    return [(u, vram, p[0][first:first + size]) for p in pairs for u, first, size, vram in p[2]]


def name_rows(units, functions=None, name=None, builds=()):
    """(the rows of strnames, the `key<TAB>text` lines in key order). units: [(unit, vram, words)] of retail, the
    executable first. functions: {unit: [(vram, words, name)]} (start `list`); None: the start by scan, named
    name(unit, vram) or func_<ADDR>. builds: [(id, pairs, runs)]: pairs as map_rows takes them (retail is stream a,
    the executable is the first pair with a RAM address), runs as it returns them.
    The lines hold a game's text: an adapter writes them to an ignored path only."""
    shared, at = units[0][0], {u: (vram, ws) for u, vram, ws in units}
    txt, tables = known(units, shared)
    found = [(u, c, *(txt[u].get(s) or txt[shared][s]), via, "retail")
             for u, c, s, via in string_refs(units, txt, tables, shared)]
    have = b"\x00".join(pack(ws) for _, _, ws in units)
    for bid, pairs, rs in builds:
        e = next(k for k, p in enumerate(pairs) if p[5] and p[1])
        bu = [(k, p[4], p[1]) for k, p in enumerate(pairs) if p[1]]
        btxt, btab = known([u for u in bu if u[0] == e], e, bu)  # a file offset is no address: no texts of its own
        for k, c, s, via in string_refs(bu, btxt, btab, e):
            b, cls = btxt[e][s]
            j = (c - pairs[k][4]) // 4
            r = None if b + b"\x00" in have else lookup(rs[k], 1, j)
            if r:
                i = r[0] + j - r[1]
                for u, first, size, vram in pairs[k][2]:
                    if first <= i < first + size:
                        found.append((u, vram + 4 * (i - first), b, cls, via, bid))
    lists = {u: sorted(fs) for u, fs in (functions or {}).items()}
    starts = {u: [f[0] for f in fs] for u, fs in lists.items()}

    def owner(u, c):
        if functions is None:
            v = start_of(at[u][1], at[u][0], c)
            return v, (name(u, v) if name else None) or f"func_{v:08X}", "scan"
        k = bisect_right(starts.get(u, []), c) - 1
        if k >= 0 and c < lists[u][k][0] + 4 * lists[u][k][1]:
            return lists[u][k][0], lists[u][k][2], "list"
        return None

    rows, lines = {}, {}
    for u, c, b, cls, via, src in sorted(found, key=lambda f: (f[0], f[1], f[4])):
        f = owner(u, c)
        if f:
            k = hashlib.sha1(b).hexdigest()[:12]
            lines[k] = f"{k}\t{shown(b)}\n"
            rows.setdefault((u, f[0], k, src), (u, f"0x{f[0]:08X}", f[1], f"0x{c:08X}", k, str(len(b)), cls, via, src,
                                                f[2]))
    return sorted(rows.values(), key=lambda r: (r[0], r[1], r[8] != "retail", r[8], r[3], r[4])), \
        [lines[k] for k in sorted(lines)]


def name_counts(rows):
    """The count line of strnames, after the adapter's tag."""
    def fns(rs):
        return len({(r[0], r[1]) for r in rs})
    return (f"{fns(rows)} functions, {len(rows)} references (direct {sum(r[7] == 'direct' for r in rows)}, table "
            f"{sum(r[7] == 'table' for r in rows)}), retail {fns([r for r in rows if r[8] == 'retail'])}, builds "
            f"{fns([r for r in rows if r[8] != 'retail'])}, {fns([r for r in rows if r[9] == 'scan'])} start by scan")


def name_check(rows, table, aliases):
    """[problems]: table = the rows of the tracked table, aliases = the rows of its alias table (`#` lines dropped):
    unit, 0xVRAM, alias, keys (comma-separated), basis."""
    gone = sorted({r[8] for r in table if len(r) > 8} - {r[8] for r in rows})
    out = [] if [list(r) for r in rows] == [list(r) for r in table] else [
        "the table is stale: run strnames again" + (f" (it holds rows of {', '.join(gone)}: is a --proto missing?)"
                                                    if gone else "")]
    keys = defaultdict(set)
    for r in rows:
        keys[r[0], r[1]].add(r[4])
    for n, a in enumerate(aliases, 1):
        if len(a) != 5:
            out.append(f"alias row {n}: {len(a)} columns, not 5")
        elif (a[0], a[1]) not in keys:
            out.append(f"alias row {n}: {a[0]} {a[1]} has no row in the table")
        else:
            out += [f"alias row {n}: key {k} is no text of {a[0]} {a[1]}" for k in a[3].split(",")
                    if k not in keys[a[0], a[1]]]
    return out


def write(path, rows, head=""):
    with open(path, "w", newline="\n") as f:
        f.write(head + "".join("\t".join(r) + "\n" for r in rows))



# ---- the contract: the game's units and functions, the paths of the tables -----------------------------------------

VENDORED = "tools/psxd_img.py"                       # this file, byte for byte
VERSION = "0.6.4"                                    # psxdecomp's version: a game's tool changes only to a later one
UNITS, FUNCTIONS, RETAIL = "config/oracle.units.tsv", ".run/oracle/functions.tsv", "config/oracle.retail"
STRNAMES, ALIASES = "config/oracle.strnames.tsv", "config/oracle.strnames.aliases.tsv"
TEXTS, SCRATCH = ".run/strnames/strings.txt", ".run/oracle"
NAMES = "config/names.tsv"
NAME_COLUMNS = ("kind", "image", "scope", "old_name", "new_name", "decision", "evidence", "reason")  # floor.py's
UNIT_COLUMNS = ("unit", "file", "offset", "vram", "words", "class")
FUNCTION_COLUMNS = ("unit", "vram", "words", "name", "lane", "state")
COLUMNS = {
    "map": "unit\tretail_vram\twords\tbuild_file\tbuild_address",
    "strings": "key\tlength\tclass\tbuild_data\tbuild_code\tretail_unit\tretail_vram\tdistance",
    "functions": "unit\tvram\tname\twords\tstate\tbuild_file\tbuild_address\tbasis\tplaces",
    "strnames": "unit\tvram\tname\tcode\tkey\tlength\tclass\tvia\tsource\tstart",
}
BUILD_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")   # oracle.py's build id
EXE_MAGIC = b"PS-X EXE"


class Refused(Exception):
    pass


def read_tsv(path):
    """The rows of a table, `#` lines dropped; [] without the file."""
    return [x.split("\t") for x in Path(path).read_text().splitlines() if x and not x.startswith("#")] \
        if Path(path).is_file() else []


def contract(path, columns):
    """The rows of a contract file: a `# <columns>` line, then rows of that many cells."""
    text = Path(path).read_text().splitlines()
    if "# " + "\t".join(columns) not in text:
        raise Refused(f"{path}: no line `# {' '.join(columns)}` (tab-separated)")
    rows = [(n, x.split("\t")) for n, x in enumerate(text, 1) if x and not x.startswith("#")]
    for n, r in rows:
        if len(r) != len(columns):
            raise Refused(f"{path} line {n}: {len(r)} cells, not {len(columns)}")
    return [r for _, r in rows]


Unit = namedtuple("Unit", "unit file offset vram words cls data")


def exe_base(b, what):
    if b[:8] != EXE_MAGIC:
        raise Refused(f"{what}: no PS-X EXE (magic)")
    return struct.unpack_from("<I", b, 0x18)[0]


def units(repo, retail):
    """[Unit] of config/oracle.units.tsv, each with its retail file's bytes: the executable first, then the files in
    the order of their first row."""
    if not (Path(repo) / UNITS).is_file():
        raise Refused(f"{UNITS} missing: the game's load-map tool writes it (phase 1.2)")
    data, out = {}, []
    for unit, file, offset, vram, n, cls in contract(Path(repo) / UNITS, UNIT_COLUMNS):
        if cls not in ("exe", "code"):
            raise Refused(f"{UNITS}: {unit}: class {cls!r} is not exe or code")
        if file not in data:
            p = Path(retail) / file
            if not p.is_file():
                raise Refused(f"{p} missing (--retail: the folder of retail's files, or {RETAIL})")
            data[file] = p.read_bytes()
        u = Unit(unit, file, int(offset, 16), int(vram, 16), int(n), cls, data[file])
        if cls == "exe" and (u.offset != HEADER or exe_base(u.data, file) != u.vram):
            raise Refused(f"{UNITS}: {unit}: an exe row has offset 0x{HEADER:X} and the header's address as its vram")
        if u.offset % 4 or u.offset + 4 * u.words > len(u.data):
            raise Refused(f"{UNITS}: {unit}: offset 0x{u.offset:X} + {u.words} words is outside {file}")
        out.append(u)
    exe = [u for u in out if u.cls == "exe"]
    if len(exe) != 1:
        raise Refused(f"{UNITS}: {len(exe)} rows of class exe, not 1")
    files = list(dict.fromkeys(u.file for u in out if u.cls == "code"))
    return exe + sorted((u for u in out if u.cls == "code"), key=lambda u: files.index(u.file))


def functions(path):
    """[(unit, vram, words, name, lane, state)] of the census list; None without the file."""
    if not Path(path).is_file():
        return None
    out = []
    for unit, vram, n, name, lane, state in contract(path, FUNCTION_COLUMNS):
        if lane not in ("game", "lib"):
            raise Refused(f"{path}: {unit} {vram}: lane {lane!r} is not game or lib")
        out.append((unit, int(vram, 16), int(n), name, lane, state))
    return out


def pairs_of(us, build=None, exe=None):
    """(the pairs of map_rows, retail's executable, the build's): retail's units against the files of the build folder
    (under retail's paths) and its executable at exe. No build: retail against itself."""
    x = us[0]
    ws = words(x.data[HEADER:HEADER + 4 * x.words])
    if build is None:
        pexe, name = x.data, x.file
    else:
        if not (Path(build) / exe).is_file():
            raise Refused(f"{Path(build) / exe} missing (--build: a folder with the build's files under retail's paths)")
        pexe, name = (Path(build) / exe).read_bytes(), exe
    pairs = [(ws, words(pexe[HEADER:]), [(x.unit, 0, len(ws), x.vram)], name, exe_base(pexe, name), True)]
    for file in dict.fromkeys(u.file for u in us[1:]):
        group = [u for u in us[1:] if u.file == file]
        p = None if build is None else Path(build) / file
        have = p is None or p.is_file()
        pairs.append((words(group[0].data), words(group[0].data if p is None else p.read_bytes() if have else b""),
                      [(u.unit, u.offset // 4, u.words, u.vram) for u in group], file if have else "-", 0, False))
    return pairs, x.data, pexe


def retail_units(us):
    """[(unit, vram, words)] of retail, the executable first: name_rows' units."""
    return units_of(pairs_of(us)[0])


def head(rel, how, cols):
    return f"# {rel} -- generated by tools/psxd_img.py {how}; do not edit\n# {cols}\n"


def pct(a, b):
    return f"{100 * a // b}%" if b else "-"


def tables(bid, us, build, exe, fns, out, scratch):
    """Write the tables of build to the folder out and its strings' text to scratch; return the count line."""
    pairs, rexe, pexe = pairs_of(us, build, exe)
    rows, rs = map_rows(pairs)
    srows, text = string_rows(pexe[HEADER:], rexe[HEADER:], pairs[0][4], rs[0], us[0].unit, us[0].vram)
    have_units = {u.unit for u in us}
    game = [(u, v, name, n, st) for u, v, n, name, lane, st in fns or () if lane == "game" and u in have_units]
    frows, asked = function_rows(game, pairs, rs) if fns is not None else ([], 0)
    for name, body in (("map", rows), ("strings", srows), ("functions", frows)):
        if name != "functions" or fns is not None:
            rel = f"config/oracle.{bid}.{name}.tsv"
            write(Path(out) / Path(rel).name, body, head(rel, f"proto --id {bid}", COLUMNS[name]))
    Path(scratch).mkdir(parents=True, exist_ok=True)
    (Path(scratch) / "strings.txt").write_text("".join(text), encoding="utf-8", newline="\n")
    nx, wx = sum(r[2] for r in rs[0]), len(pairs[0][0])
    no, wo = sum(int(r[2]) for r in rows[len(rs[0]):]), sum(c[2] for p in pairs[1:] for c in p[2])
    n = string_counts(srows)
    run, one = sum(r[7] == "run" for r in frows), sum(r[7] == "search" and r[8] == "1" for r in frows)
    fn = (f"functions {len(frows)} of {asked} held: {run} in a run, {len(frows) - run} by search ({one} at one place)"
          if fns is not None else f"functions: no list ({FUNCTIONS})")
    return (f"psxd_img: proto {bid}: exe {nx} of {wx} words in {len(rs[0])} runs ({pct(nx, wx)}); overlays {no} of {wo} "
            f"words in {len(rows) - len(rs[0])} runs ({pct(no, wo)}), {sum(p[3] != '-' for p in pairs[1:])} of "
            f"{len(pairs) - 1} files in the build; {fn}; strings {n[0]}: {n[1]} with a reference, {n[2]} with a retail "
            f"twin, {n[3]} more with retail code within {NEAR} words")


def strnames(us, fns, builds):
    """(rows, text lines). fns: functions() or None (start by scan); builds: [(id, folder, executable)]."""
    lists = None
    if fns is not None:
        lists = {}
        for u, v, n, name, _, _ in fns:
            lists.setdefault(u, []).append((v, n, name))
    done = []
    for bid, build, exe in builds:
        pairs = pairs_of(us, build, exe)[0]
        done.append((bid, pairs, map_rows(pairs)[1]))
    return name_rows(retail_units(us), lists, builds=done)


def texts_of(repo):
    """{key: text} of every ignored text file of this tool."""
    out = {}
    for p in [Path(repo) / TEXTS] + sorted((Path(repo) / SCRATCH).glob("*/strings.txt")):
        for r in read_tsv(p):
            out.setdefault(r[0], "\t".join(r[1:]))
    return out


def promote(repo, unit, vram, name):
    """Append one provisional function row to config/names.tsv; return the count line."""
    if not re.fullmatch(r"[A-Za-z_]\w*", name):
        raise Refused(f"{name!r} is no C name")
    try:
        v = int(vram, 16)
    except ValueError:
        raise Refused(f"{vram!r} is no address")
    lines = (Path(repo) / STRNAMES).read_text().splitlines() if (Path(repo) / STRNAMES).is_file() else []
    hit = [(n, x.split("\t")) for n, x in enumerate(lines, 1) if not x.startswith("#") and x.count("\t") >= 4]
    hit = [(n, c) for n, c in hit if c[0] == unit and int(c[1], 16) == v]
    if not hit:
        raise Refused(f"no row of {STRNAMES} names {unit} 0x{v:08X} (run strnames first)")
    p = Path(repo) / NAMES
    text = p.read_text() if p.is_file() else ""
    rows = [x.split("\t") for x in text.splitlines() if x.strip() and not x.startswith("#")]
    if not rows or tuple(c.strip() for c in rows[0]) != NAME_COLUMNS:
        raise Refused(f"{NAMES} has no header line {' '.join(NAME_COLUMNS)} (`python3 tools/psxd_floor.py names --init`)")
    live = [dict(zip(NAME_COLUMNS, r + [""] * 8)) for r in rows[1:]]
    live = [r for r in live if r["decision"] != "rejected"]
    old = hit[0][1][2]
    if any(r["new_name"] == name and r["image"] == unit and r["kind"] == "function" for r in live):
        raise Refused(f"{NAMES} holds a function {name} of {unit} already")
    if any(r["old_name"] == old and r["image"] == unit for r in live):
        raise Refused(f"{NAMES} holds a row for {unit} {old} already: change that row")
    row = ("function", unit, "", old, name, "provisional", f"string:{STRNAMES}:{hit[0][0]}", "")
    p.write_text(text + ("" if text.endswith("\n") else "\n") + "\t".join(row) + "\n", newline="\n")
    keys = ", ".join(dict.fromkeys(c[4] for _, c in hit))
    return (f"psxd_img: promote: {NAMES}: {unit} {old} -> {name} provisional (string:{STRNAMES}:{hit[0][0]}); read "
            f"the text first: python3 {VENDORED} show <key> ({keys})")


def exe_measure(retail, build):
    """(map rows, string rows, text lines, (mapped words, words, runs, strings, with a reference)) of two PS-X EXEs:
    the map of the executables and the strings that the build has and retail lacks."""
    rbase, pbase = exe_base(retail, "retail"), exe_base(build, "the build")
    ws = words(retail[HEADER:])
    pair = (ws, words(build[HEADER:]), [("exe", 0, len(ws), rbase)], "exe", pbase, True)
    rows, rs = map_rows([pair])
    srows, text = string_rows(build[HEADER:], retail[HEADER:], pbase, rs[0], "exe", rbase)
    n = string_counts(srows)
    return rows, srows, text, (sum(r[2] for r in rs[0]), len(ws), len(rs[0]), n[0], n[1])


def exe_scan(retail):
    """(rows, text lines) of strnames on a PS-X EXE alone: every start by scan."""
    return name_rows([("exe", exe_base(retail, "retail"), words(retail[HEADER:]))])


def retail_dir(repo, given):
    if given:
        return Path(given)
    p = Path(repo) / RETAIL
    if not p.is_file() or not p.read_text().strip():
        raise Refused(f"no --retail and no {RETAIL} (one line: the retail folder, relative to the repository)")
    return Path(repo) / p.read_text().splitlines()[0].strip()


def build_spec(spec):
    bid, build, exe = (spec.split(":", 2) + ["", ""])[:3]
    if not BUILD_ID.fullmatch(bid) or not build or not exe:
        raise Refused(f"--proto {spec}: <id>:<the build's folder>:<its executable, a path inside the folder>")
    return bid, build, exe


# ---- self-test on synthetic words (the three makers serve the adapters' self-tests too) ------------------------------

def i_type(op, rs, rt, imm):
    return op << 26 | rs << 21 | rt << 16 | imm & 0xFFFF


def body(hi, lo, target, store=43):
    """A 12-word function: a frame, a lui + addiu pair, a call, a store through the pair."""
    return (i_type(9, 29, 29, -24), i_type(43, 29, 31, 16), i_type(15, 0, 4, hi), i_type(9, 4, 4, lo),
            3 << 26 | target, 0, i_type(15, 0, 2, hi), i_type(35, 29, 31, 16), i_type(store, 2, 4, lo + 8),
            0, 0x03E00008, i_type(9, 29, 29, 24))


def filler(seed, n):
    return tuple(i_type(12, 0, 8 + (seed + i) % 8, 1 + seed * 131 + i * 7) for i in range(n))  # andi: no mask


def core_selftest():
    fails = []

    def case(name, ok, text):
        print(f"selftest: {name} {'pass' if ok else 'FAIL'} ({text})")
        if not ok:
            fails.append(name)

    a = body(0x8009, 0x1234, 0x4000)
    case("mask", loose(a) == loose(body(0x800A, 0x4321, 0x5000)) and loose(a) != loose(body(0x8009, 0x1234, 0x4000, 41))
         and loose(filler(1, 4)) == filler(1, 4), "other addresses are one body, another opcode is not")
    s = loose(filler(5, 300))
    case("identity", runs(s, s) == [(0, 0, 300)], "a stream against itself is one run")
    raw = filler(5, 100) + filler(9, 10) + body(0x8001, 4, 8) + filler(5, 300)[100:]
    t = loose(raw)
    got = runs(s, t)
    case("insertion", got == [(0, 0, 100), (100, 122, 200)] and lookup(got, 0, 150) == (100, 122, 200)
         and lookup(got, 1, 110) is None, f"{got}")
    case("nearest", twin(got, 150) == (128, 0) and twin(got, 110) == (99, -11) and twin(got, 121) == (100, 1)
         and twin(runs(s[:60], t), 110) is None, "a word in a run, after one, before one, too far from one")
    cuts = [("one", 0, 150, 0x80010000), ("two", 150, 150, 0x800E0000)]
    rows, rs = map_rows([(filler(5, 300), raw, cuts, "OVL.BIN", 0, False),
                         (filler(5, 300), raw, [("exe", 0, 300, 0x80010000)], "A.EXE", 0x80010000, True),
                         (filler(5, 300), (), [("gone", 0, 300, 0x80020000)], "-", 0, False)])
    case("map rows", rows == [
        ("one", "0x80010000", "100", "OVL.BIN", "0x0"), ("one", "0x80010190", "50", "OVL.BIN", "0x1E8"),
        ("two", "0x800E0000", "150", "OVL.BIN", "0x2B0"), ("exe", "0x80010000", "100", "A.EXE", "0x80010000"),
        ("exe", "0x80010190", "200", "A.EXE", "0x800101E8")] and rs == [got, got, []],
        "a run is cut at a unit's end; a RAM address and a file offset; a unit with no file in the build")
    got = refs(filler(6, 4) + a, 0x80030000)
    case("lui pair", dict(got) == {0x80091234: [0x80030018]}, f"{[(hex(k), hex(v[0])) for k, v in got.items()]}")
    blob = b"\x00" * 8 + b"stage %d of %s\x00\x00" + b"src/boss.c\x00\x00" + b"kept text\x00" + b"short\x00"
    got = [(o, kind(x)) for o, x in strings(blob, b"\x00kept text\x00")]
    case("strings", got == [(8, "format"), (24, "path")], f"{got}")
    # An executable: 60 words of code, a function that builds the address of its string, a zero word, the string.
    # Retail has the same code 4 words lower and no string.
    text = b"stage %d of %s\x00\x00"
    build = filler(7, 4) + filler(8, 60) + body(0x8004, 0x0134, 0x4000) + (0,) + words(text) + (0,) * 4
    srows, lines = string_rows(struct.pack(f"<{len(build)}I", *build), struct.pack("<60I", *filler(8, 60)),
                               0x80040000, runs(loose(filler(8, 60)), loose(build)), "exe", 0x80010000)
    k = hashlib.sha1(text[:14]).hexdigest()[:12]
    case("string rows", srows == [(k, "14", "format", "0x80040134", "0x80040108", "exe", "0x800100EC", "-3")]
         and lines == [f"{k}\tstage %d of %s\n"] and string_counts(srows) == (1, 1, 0, 1),
         "the reference is 3 words after the last mapped word; the text is a line, never a row")
    # Five functions of one unit: f1 keeps its place, f2 moved to the head of the build, f3 is in the build twice
    # and out of order, f4 is absent, f5 is short. A second unit has no file in the build; its function is f2 again.
    f1, f2, f3, f4 = (body(0x8001, 4 * n, 8, store=st) for n, st in enumerate((43, 41, 40, 42)))
    retail = filler(1, 40) + f1 + filler(2, 40) + f2 + filler(3, 40) + f3 + filler(4, 40) + f4 + filler(5, 6)
    proto = body(0x8002, 0x7770, 0x60, store=41) + filler(1, 40) + f1 + filler(2, 40) + filler(3, 40) + filler(4, 40) \
        + f3 + f3
    pairs = [(retail, proto, [("exe", 0, len(retail), 0x80010000)], "A.EXE", 0x80018000, True),
             (filler(6, 20) + f2, (), [("ovl", 0, 32, 0x800E0000)], "-", 0, False)]
    fns = [("exe", 0x800100A0, "f1", 12, "c"), ("exe", 0x80010170, "f2", 12, "asm"),
           ("exe", 0x80010240, "f3", 12, "asm"), ("exe", 0x80010310, "f4", 12, "asm"),
           ("exe", 0x80010340, "f5", 6, "asm"), ("ovl", 0x800E0050, "g2", 12, "c")]
    rows, asked = function_rows(fns, pairs, map_rows(pairs)[1])
    case("function rows", asked == 5 and rows == [
        ("exe", "0x800100A0", "f1", "12", "c", "A.EXE", "0x800180D0", "run", "1"),
        ("exe", "0x80010170", "f2", "12", "asm", "A.EXE", "0x80018000", "search", "1"),
        ("exe", "0x80010240", "f3", "12", "asm", "-", "-", "search", "2"),
        ("ovl", "0x800E0050", "g2", "12", "c", "A.EXE", "0x80018000", "search", "1")],
        "in a run, moved, in two places (no address), absent (no row), short (not asked), a unit with no file")
    # strnames, the two tools' rules: spimdisasm 1.42.4's own sizes for these windows (run once in its package),
    # then Ghidra's reference rule (no padding, >= 5) and GNU strings' floor.
    win = [(b"PAGE\0\0\0\0", 0, 4), (b"abc\0", 0, 3), (b"hello\nworld\0", 0, 11),
           ("テスト".encode("shift_jis") + b"\0\0", 0, 6), (b"\x84\x40\x84\x41\0\0\0\0", 0, 4),
           (b"\x85\x40\x85\x41\0\0\0\0", 0, -90), (b"ab\x01cd\0\0\0", 0, -10), (b"ABCD\0\x01\x02\x03", 0, -100),
           (b"\0\0ok!\0\0", 2, 3), (b"x\x8c\x5cy\0\0\0\0", 0, 4), (b"\x1b[0m\0\0\0\0", 0, 4), (b"no nul", 0, -80),
           (b"tab\there\0\0\0", 0, 8)]
    got = [spimdisasm_size(w, o) for w, o, _ in win]
    case("spimdisasm", got == [n for *_, n in win] and text_at(b"ABCDE\0\x01\x02", 0) == (b"ABCDE", "other")
         and text_at(b"ABCD\0\x01\x02\x03", 0) is None and text_at(b"PAGE\0\0\0\0", 0) == (b"PAGE", "other")
         and text_at(b"abc\0", 0) is None, "13 windows sized as spimdisasm sizes them; Ghidra takes 5 unpadded "
         "characters; 4 padded pass the floor, 3 do not")
    # strnames, retail: three functions after a `jr ra`, its delay slot and two zero words; f1 loads a format, f2 a
    # table of three texts, f3 a Shift-JIS text, a text with a line feed, then three that no tool takes (an
    # unassigned lead byte; 3 characters; 4 characters with no NUL padding).
    base, data = 0x80010000, 4 * 29

    def hl(addr):
        return (addr + 0x8000) >> 16, addr & 0xFFFF

    def ref(rt, addr):
        return i_type(15, 0, rt, hl(addr)[0]), i_type(9, rt, rt, addr)

    blobs = [b"stage %d of %s\x00\x00", b"alpha\x00\x00\x00", b"beta\x00\x00\x00\x00", b"gamma\x00\x00\x00",
             "テスト".encode("shift_jis") + b"\x00\x00", b"line one\nline two\x00\x00\x00",
             b"\x85\x40\x85\x41\x00\x00\x00\x00", b"abc\x00", b"ABCD\x00\x01\x02\x03"]
    addr, o = [], base + data + 12  # the table's three words come first
    for x in blobs:
        addr.append(o)
        o += len(x)
    code = (filler(1, 2) + (JR_RA, 0, 0, 0)
            + (i_type(9, 29, 29, -24), *ref(4, addr[0]), 3 << 26, 0, JR_RA, i_type(9, 29, 29, 24))
            + (*ref(5, base + data), JR_RA, 0)
            + (*ref(4, addr[4]), *ref(5, addr[5]), *ref(6, addr[6]), *ref(7, addr[7]), *ref(8, addr[8]), JR_RA, 0))
    ws = code + tuple(addr[1:4]) + words(b"".join(blobs))
    tx = texts(pack(ws), base, set(ws) | set(refs(ws, base)))
    case("texts", data == 4 * len(code) and sorted(tx) == addr[:6]
         and [c for _, c in (tx[a] for a in addr[:6])] == ["format", "other", "other", "other", "sjis", "other"]
         and pointer_tables(ws, base, tx) == {base + data: addr[1:4]}, "a format, three others, Shift-JIS, a line "
         "feed; a table of three; the three others are refused")
    f1, f2, f3 = base + 24, base + 52, base + 68
    unit = [("exe", base, ws)]
    got, lines = name_rows(unit, {"exe": [(f1, 7, "f1"), (f2, 4, "f2"), (f3, 12, "f3")]})
    sha = [hashlib.sha1(x.rstrip(b"\x00")).hexdigest()[:12] for x in blobs]
    want = [("exe", f"0x{f1:08X}", "f1", f"0x{f1 + 4:08X}", sha[0], "14", "format", "direct", "retail", "list"),
            *(("exe", f"0x{f2:08X}", "f2", f"0x{f2:08X}", sha[n], str(len(blobs[n].rstrip(b"\x00"))), "other",
               "table", "retail", "list") for n in (1, 3, 2)),
            ("exe", f"0x{f3:08X}", "f3", f"0x{f3:08X}", sha[4], "6", "sjis", "direct", "retail", "list"),
            ("exe", f"0x{f3:08X}", "f3", f"0x{f3 + 8:08X}", sha[5], "17", "other", "direct", "retail", "list")]
    case("direct, table, sjis", got == sorted(want, key=lambda r: (r[3], r[4])) and len(lines) == 6
         and f"{sha[4]}\tテスト\n" in lines and f"{sha[5]}\tline one\\nline two\n" in lines, f"{len(got)} rows")
    got = name_rows(unit, name=lambda u, v: "named" if v == f1 else None)[0]
    case("scan", [r[1:3] + r[9:] for r in got[::2]] == [
        (f"0x{f1:08X}", "named", "scan"), (f"0x{f2:08X}", f"func_{f2:08X}", "scan"),
        (f"0x{f3:08X}", f"func_{f3:08X}", "scan")] and start_of(ws, base, f1 + 4) == f1
         and start_of(ws, base, base + 4) == base, "after a `jr ra`, its delay slot and two zero words; none before")
    # strnames, a build: g and h of retail; the build's g loads a text retail lacks, h one retail has, and a block
    # that retail lacks (no run) loads another new text.
    rbase, pbase = 0x80010000, 0x80018000
    rd, pd = rbase + 4 * 124, pbase + 4 * 128
    newt, kept, lost = b"debug menu %d\x00\x00\x00", b"kept text\x00\x00\x00", b"lost text\x00\x00\x00"
    retail = filler(8, 60) + body(0x8009, 0x1234, 0x4000) + body(*hl(rd), 0x4000) + filler(9, 40) \
        + words(kept)
    build = filler(8, 60) + body(*hl(pd), 0x4000) + body(*hl(pd + 16), 0x4000) \
        + filler(9, 40) + (*ref(4, pd + 28), JR_RA, 0) + words(newt + kept + lost)
    pairs = [(retail, build, [("exe", 0, len(retail), rbase)], "A.EXE", pbase, True)]
    fns = {"exe": [(rbase + 240, 12, "g"), (rbase + 288, 12, "h")]}
    got = name_rows(units_of(pairs), fns, builds=[("proto", pairs, map_rows(pairs)[1])])[0]
    k = [hashlib.sha1(x.rstrip(b"\x00")).hexdigest()[:12] for x in (newt, kept)]
    case("build", got == [("exe", "0x800100F0", "g", "0x800100F8", k[0], "13", "format", "direct", "proto", "list"),
                          ("exe", "0x80010120", "h", "0x80010128", k[1], "9", "other", "direct", "retail", "list")]
         and name_counts(got) == "2 functions, 2 references (direct 2, table 0), retail 1, builds 1, 0 start by scan"
         and name_rows(units_of(pairs), fns, builds=[("self", [(retail, retail, *pairs[0][2:])],
                                                       [[(0, 0, len(retail))]])])[0] == got[1:],
         "mapped to retail; a text retail has and a block outside every run give no row; retail against itself")
    table = [list(r) for r in got]
    case("check", name_check(got, table, [["exe", "0x800100F0", "debug_menu", k[0], "string:t.tsv"]]) == []
         and len(name_check(got, table[:1], [["exe", "0x80010000", "x", k[0], "b"], ["exe", "0x800100F0", "y",
                                                                                       k[1], "b"]])) == 3,
         "a fresh table and a true alias pass; a stale table, an unknown function and a foreign key fail")
    return fails


def contract_selftest():
    """The adapter on a planted game (synthetic words): the contract files, proto, strnames, show, promote."""
    fails = []

    def case(name, ok, text):
        print(f"self-test: {name} {'ok' if ok else 'FAIL'} ({text})")
        if not ok:
            fails.append(name)

    def read(d, name):
        return [x.split("\t") for x in (d / f"oracle.planted.{name}.tsv").read_text().splitlines()]

    f = [body(0x8001, 4 * n, 8, store=st) for n, st in enumerate((43, 41, 40, 42, 46, 57))]
    exe = bytearray(HEADER) + pack(filler(1, 40) + f[0] + filler(2, 40) + f[1] + filler(3, 20))
    exe[:8], exe[0x18:0x1C] = EXE_MAGIC, struct.pack("<I", 0x80018000)
    m1, m2 = filler(10, 20) + f[4] + filler(11, 20), filler(13, 20) + f[5] + filler(14, 20)
    files = {"GAME.EXE": bytes(exe), "BIN/A.BIN": pack(filler(4, 30) + f[2] + filler(5, 30)),
             "BIN/B.BIN": pack(filler(6, 20) + f[3] + filler(7, 20)), "ARC.BIN": pack(m1 + filler(12, 12) + m2)}
    unit_rows = [("exe", "GAME.EXE", "0x800", "0x80018000", "124", "exe"),
                 ("bin_a", "BIN/A.BIN", "0x0", "0x800D0000", "72", "code"),
                 ("bin_b", "BIN/B.BIN", "0x0", "0x800D0000", "52", "code"),
                 ("m1", "ARC.BIN", "0x0", "0x800E0000", "52", "code"),
                 ("m2", "ARC.BIN", "0x100", "0x800F0000", "52", "code")]
    fn_rows = [("exe", "0x800180A0", "12", "f0", "game", "c"), ("exe", "0x80018170", "12", "f1", "game", "asm"),
               ("bin_a", "0x800D0078", "12", "f2", "game", "asm"), ("bin_b", "0x800D0050", "12", "f3", "game", "asm"),
               ("exe", "0x800181A0", "4", "short", "game", "asm"), ("bin_c", "0x800D0000", "12", "gone", "game", "asm"),
               ("m1", "0x800E0050", "12", "lib:x:f4", "lib", "asm"), ("m2", "0x800F0050", "12", "f5", "game", "asm")]
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "game"
        for rel, b in files.items():
            (repo / "retail" / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / "retail" / rel).write_bytes(b)
        (repo / "config").mkdir()
        (repo / RETAIL).write_text("retail\n")
        write(repo / UNITS, unit_rows, head(UNITS, "a planted load map", "\t".join(UNIT_COLUMNS)))
        (repo / FUNCTIONS).parent.mkdir(parents=True)
        write(repo / FUNCTIONS, fn_rows, head(FUNCTIONS, "a planted census", "\t".join(FUNCTION_COLUMNS)))
        us, fns = units(repo, retail_dir(repo, None)), functions(repo / FUNCTIONS)
        out = repo / "config"
        line = tables("planted", us, repo / "retail", "GAME.EXE", fns, out, repo / SCRATCH / "planted")
        m, fr = read(out, "map"), read(out, "functions")
        case("identity", [u.unit for u in us] == ["exe", "bin_a", "bin_b", "m1", "m2"]
             and m[2:] == [["exe", "0x80018000", "124", "GAME.EXE", "0x80018000"],
                           ["bin_a", "0x800D0000", "72", "BIN/A.BIN", "0x0"],
                           ["bin_b", "0x800D0000", "52", "BIN/B.BIN", "0x0"],
                           ["m1", "0x800E0000", "52", "ARC.BIN", "0x0"], ["m2", "0x800F0000", "52", "ARC.BIN", "0x100"]]
             and [r[:5] + r[7:] for r in fr[2:]] == [
                 ["exe", "0x800180A0", "f0", "12", "c", "run", "1"], ["exe", "0x80018170", "f1", "12", "asm", "run", "1"],
                 ["bin_a", "0x800D0078", "f2", "12", "asm", "run", "1"],
                 ["bin_b", "0x800D0050", "f3", "12", "asm", "run", "1"], ["m2", "0x800F0050", "f5", "12", "asm", "run", "1"]]
             and "3 of 3 files in the build; functions 5 of 5 held: 5 in a run" in line, line)
        case("headers", all(t[0] == [f"# config/oracle.planted.{n}.tsv -- generated by tools/psxd_img.py proto --id "
                                     "planted; do not edit"] and t[1] == ["# " + COLUMNS[n].split("\t")[0]]
                                + COLUMNS[n].split("\t")[1:] for n, t in (("map", m), ("functions", fr))),
             "two `#` lines: the tool, the columns")
        # the build: no BIN/B.BIN, its function at the end of BIN/A.BIN; the executable at another address
        build = Path(tmp) / "build"
        (build / "BIN").mkdir(parents=True)
        (build / "BIN/A.BIN").write_bytes(files["BIN/A.BIN"] + pack(f[3]))
        (build / "PSX.EXE").write_bytes(bytes(exe[:0x18]) + struct.pack("<I", 0x80010000) + bytes(exe[0x1C:]))
        (build / "ARC.BIN").write_bytes(files["ARC.BIN"])
        line = tables("planted", us, build, "PSX.EXE", fns, out, repo / SCRATCH / "planted")
        m, fr = read(out, "map"), read(out, "functions")
        case("no file", m[2:5] == [["exe", "0x80018000", "124", "PSX.EXE", "0x80010000"],
                                   ["bin_a", "0x800D0000", "72", "BIN/A.BIN", "0x0"],
                                   ["m1", "0x800E0000", "52", "ARC.BIN", "0x0"]]
             and [r[5:] for r in fr[2:6]] == [["PSX.EXE", "0x800100A0", "run", "1"], ["PSX.EXE", "0x80010170", "run", "1"],
                                              ["BIN/A.BIN", "0x78", "run", "1"], ["BIN/A.BIN", "0x120", "search", "1"]]
             and "2 of 3 files in the build; functions 5 of 5 held: 4 in a run, 1 by search (1 at one place)" in line,
             line)
        (repo / FUNCTIONS).unlink()
        line = tables("nolist", us, build, "PSX.EXE", functions(repo / FUNCTIONS), out, repo / SCRATCH / "nolist")
        case("no list", not (out / "oracle.nolist.functions.tsv").exists() and "functions: no list" in line, line)
        # strnames, show and promote: a text that a function of the executable loads
        text = b"stage %d of %s\x00\x00"
        code = filler(7, 4) + filler(8, 60) + body(0x8004, 0x0134, 0x4000) + (0,) + words(text) + (0,) * 4
        exe2 = bytearray(HEADER) + pack(code)
        exe2[:8], exe2[0x18:0x1C] = EXE_MAGIC, struct.pack("<I", 0x80040000)
        (repo / "retail/GAME.EXE").write_bytes(bytes(exe2))
        write(repo / UNITS, [("exe", "GAME.EXE", "0x800", "0x80040000", str(len(code)), "exe")],
              head(UNITS, "a planted load map", "\t".join(UNIT_COLUMNS)))
        us = units(repo, repo / "retail")
        rows, lines = strnames(us, None, [])
        write(repo / STRNAMES, rows, head(STRNAMES, "strnames (builds: none)", COLUMNS["strnames"]))
        (repo / TEXTS).parent.mkdir(parents=True)
        (repo / TEXTS).write_text("".join(lines), encoding="utf-8", newline="\n")
        k = hashlib.sha1(text[:14]).hexdigest()[:12]
        case("strnames", [r[:3] + r[4:5] + r[9:] for r in rows] == [("exe", "0x80040000", "func_80040000", k, "scan")]
             and texts_of(repo) == {k: "stage %d of %s"} and name_check(rows, read_tsv(repo / STRNAMES), []) == [],
             "one function by scan; its key's text from the ignored file; the table checks")
        (repo / NAMES).write_text("\t".join(NAME_COLUMNS) + "\n")
        got = promote(repo, "exe", "80040000", "Stage_Print")
        last = (repo / NAMES).read_text().splitlines()[-1].split("\t")
        refused = 0
        for args in (("exe", "0x80040000", "Other"), ("exe", "0x80040100", "X"), ("exe", "0x80040000", "1bad")):
            try:
                promote(repo, *args)
            except Refused:
                refused += 1
        case("promote", last == ["function", "exe", "", "func_80040000", "Stage_Print", "provisional",
                                 f"string:{STRNAMES}:3", ""] and refused == 3 and k in got,
             "one provisional row cites the table's line; a second name, an unknown function, a bad name: refused")
        (repo / UNITS).write_text("# no columns line\nexe\tGAME.EXE\t0x800\t0x80040000\t1\texe\n")
        try:
            units(repo, repo / "retail")
            bad = False
        except Refused:
            bad = True
        r = exe_measure(bytes(exe2), bytes(exe2))
        case("contract, measure", bad and r[3] == (len(code), len(code), 1, 0, 0),
             "a units file with no columns line is refused; an executable against itself maps whole")
    return fails


def self_test():
    fails = core_selftest() + contract_selftest()
    print("img %s" % ("SELF-TEST OK" if not fails else "SELF-TEST FAILED (%s)" % " ".join(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("proto", help="config/oracle.<id>.{map,strings,functions}.tsv")
    p.add_argument("--id", required=True, help="the build's id (proto-2000-04-27)")
    p.add_argument("--build", required=True, help="a folder with the build's files under retail's paths")
    p.add_argument("--exe", required=True, help="the build's executable, a path inside --build")
    n = sub.add_parser("strnames", help=STRNAMES)
    n.add_argument("--proto", action="append", default=[], help="<id>:<the build's folder>:<its executable>")
    n.add_argument("--check", action="store_true", help="compare, write nothing")
    for x in (p, n):
        x.add_argument("--retail", help="the folder of retail's files (default: %s)" % RETAIL)
        x.add_argument("--functions", help="the census list (default: %s)" % FUNCTIONS)
    s = sub.add_parser("show", help="the text of a key, from the ignored files")
    s.add_argument("key")
    m = sub.add_parser("promote", help="one provisional row of %s" % NAMES)
    m.add_argument("unit")
    m.add_argument("vram")
    m.add_argument("name")
    e = sub.add_parser("measure", help="the map of two PS-X EXEs: one count line")
    e.add_argument("retail_exe")
    e.add_argument("build_exe")
    for x in (p, n, s, m):
        x.add_argument("--repo", default=".", help="the game's repository (default: .)")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    try:
        if a.cmd in ("proto", "strnames"):
            us = units(a.repo, retail_dir(a.repo, a.retail))
            fns = functions(a.functions or Path(a.repo) / FUNCTIONS)
        if a.cmd == "proto":
            if not BUILD_ID.fullmatch(a.id):
                raise Refused(f"--id {a.id}: lower-case letters, digits and single hyphens")
            print(tables(a.id, us, a.build, a.exe, fns, Path(a.repo) / "config", Path(a.repo) / SCRATCH / a.id))
        elif a.cmd == "strnames":
            builds = [build_spec(x) for x in a.proto]
            rows, text = strnames(us, fns, builds)
            if a.check:
                problems = name_check(rows, read_tsv(Path(a.repo) / STRNAMES), read_tsv(Path(a.repo) / ALIASES))
                for x in problems:
                    print(f"psxd_img: strnames --check: {x}")
                print(f"psxd_img: strnames --check {'FAIL' if problems else 'OK'}: {name_counts(rows)}")
                return 1 if problems else 0
            write(Path(a.repo) / STRNAMES, rows, head(STRNAMES, "strnames (builds: %s)" % (
                ", ".join(b[0] for b in builds) or "none"), COLUMNS["strnames"]))
            (Path(a.repo) / TEXTS).parent.mkdir(parents=True, exist_ok=True)
            (Path(a.repo) / TEXTS).write_text("".join(text), encoding="utf-8", newline="\n")
            print(f"psxd_img: strnames: {name_counts(rows)}")
        elif a.cmd == "show":
            got = texts_of(a.repo).get(a.key)
            if got is None:
                raise Refused(f"{a.key}: no such key in {TEXTS} or {SCRATCH}/*/strings.txt (run strnames or proto)")
            print(got)
        elif a.cmd == "promote":
            print(promote(a.repo, a.unit, a.vram, a.name))
        elif a.cmd == "measure":
            r = exe_measure(Path(a.retail_exe).read_bytes(), Path(a.build_exe).read_bytes())[3]
            print(f"psxd_img: measure: exe {r[0]} of {r[1]} words in {r[2]} runs ({100 * r[0] / r[1] if r[1] else 0:.1f}%); "
                  f"build-only strings {r[3]} ({r[4]} with a reference)")
        else:
            ap.print_usage(sys.stderr)
            return 2
    except (Refused, OSError, ValueError) as x:
        print(f"psxd_img: REFUSED {x}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
