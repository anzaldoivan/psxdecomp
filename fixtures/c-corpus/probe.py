#!/usr/bin/env python3
"""probe.py: compile one C function with a pinned compiler and compare it with a target (inside the corpus image).

  probe.py target SRC FUNC [--compiler C] [-I DIR ...]             -> the target as JSON on stdout
  probe.py check SRC FUNC --target T.json [--compiler C] [-I DIR]  -> `PROBE match|fail <m>/<n>` or `PROBE nocompile`,
                                                                     then one `RELOC ...` line per relocation that differs
  probe.py --self-test

A target is {func, compiler, words, masks, relocs}: the function's words up to its last `jr $ra` and delay slot, the
mask of each relocated field, and each relocation's type and symbol. Two comparisons, because the first hides what the
second sees:
  words   every word equal once relocated fields are masked on both sides (what a probe against a linked binary can do)
  relocs  the same relocation type and symbol at the same word, and the same in-place addend
`match` needs both. A draft that reaches the same bytes through another symbol (`D_80001234` for `g_State.mode`) passes
the first and fails the second. Exit 0 on match, 1 on fail, 2 on nocompile. stdlib only; needs cc1, maspsx, cpp and as.
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile

JR_RA = 0x03E00008
MASKS = {4: 0x03FFFFFF, 5: 0xFFFF, 6: 0xFFFF, 7: 0xFFFF}      # R_MIPS_26, HI16, LO16, GPREL16
RTYPE = {2: "32", 4: "26", 5: "HI16", 6: "LO16", 7: "GPREL16"}
# name: (cc1, the assembler version maspsx imitates). Flags are the PsyQ defaults a PS1 game was built with.
COMPILERS = {"gcc2.95.2": ("/opt/cc/2.95.2-psx/cc1", "2.86"), "gcc2.7.2": ("/opt/cc/2.7.2-psx/cc1", "2.56")}
CFLAGS = "-O2 -G0 -msoft-float -funsigned-char -quiet"
ASFLAGS = "-EL -march=r3000 -mtune=r3000 -mabi=32 -no-pad-sections -G0"


def trim(words):
    """Cut after the last `jr $ra` and its delay slot; unchanged when there is none."""
    for i in range(len(words) - 1, -1, -1):
        if words[i] == JR_RA:
            return words[: min(i + 2, len(words))]
    return words


def build(src, obj, compiler="gcc2.95.2", incs=()):
    """cpp | cc1 | maspsx | as. Returns the tools' stderr when a stage fails, else None."""
    cc1, aspsx = COMPILERS[compiler]
    inc = " ".join("-I'%s'" % d for d in incs)
    cmd = ("set -o pipefail; mipsel-linux-gnu-cpp -nostdinc -undef -D__GNUC__=2 -DPSX %s '%s' | %s %s"
           " | maspsx --aspsx-version=%s --expand-div | mipsel-linux-gnu-as %s -o '%s' --"
           % (inc, src, cc1, CFLAGS, aspsx, ASFLAGS, obj))
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    return None if p.returncode == 0 and os.path.exists(obj) else (p.stderr or "compile failed")


def elf_function(path, func):
    """(words, {word index: mask}, {word index: [type, symbol]}) of func in an ELF32 LE relocatable object."""
    with open(path, "rb") as f:
        elf = f.read()
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 1:
        raise ValueError("%s is not ELF32 LE" % path)
    e_shoff, = struct.unpack_from("<I", elf, 0x20)
    e_shentsize, e_shnum = struct.unpack_from("<HH", elf, 0x2E)
    secs = [struct.unpack_from("<10I", elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    # (name, type, flags, addr, offset, size, link, info, align, entsize)
    st = next((s for s in secs if s[1] == 2), None)
    if st is None:
        raise ValueError("%s has no .symtab" % path)
    strtab = secs[st[6]]
    shstr = secs[struct.unpack_from("<H", elf, 0x32)[0]]

    def name_at(tab, off):
        b = tab[4] + off
        return elf[b: elf.index(b"\0", b)].decode()

    syms = []
    for k in range(st[5] // 16):
        st_name, st_value, st_size, st_info, _, st_shndx = struct.unpack_from("<IIIBBH", elf, st[4] + 16 * k)
        name = name_at(strtab, st_name)
        if not name and (st_info & 0xF) == 3 and st_shndx < len(secs):       # a section symbol: its section's name
            name = name_at(shstr, secs[st_shndx][0])
        syms.append((name, st_value, st_size, st_info, st_shndx))
    hit = next((s for s in syms if s[0] == func and s[4] not in (0, 0xFFF1, 0xFFF2) and s[4] < 0xFF00), None)
    if hit is None:
        raise ValueError("%s is not defined in %s" % (func, path))
    _, value, size, _, shndx = hit
    text = secs[shndx]
    if size == 0:
        later = [s[1] for s in syms if s[4] == shndx and s[1] > value and ((s[3] & 0xF) == 2 or (s[3] >> 4) != 0)]
        size = (min(later) if later else text[5]) - value
    n = size // 4
    words = trim(list(struct.unpack_from("<%dI" % n, elf, text[4] + value)))
    masks, relocs = {}, {}
    for s in secs:
        if s[1] == 9 and s[7] == shndx:                                       # SHT_REL against the function's section
            for k in range(s[5] // 8):
                r_offset, r_info = struct.unpack_from("<II", elf, s[4] + 8 * k)
                i = (r_offset - value) // 4
                if not (value <= r_offset < value + size) or i >= len(words):
                    continue
                masks[i] = masks.get(i, 0) | MASKS.get(r_info & 0xFF, 0xFFFFFFFF)
                relocs[i] = [RTYPE.get(r_info & 0xFF, str(r_info & 0xFF)), syms[r_info >> 8][0]]
    return words, masks, relocs


def target_of(obj, func, compiler):
    words, masks, relocs = elf_function(obj, func)
    return {"func": func, "compiler": compiler, "words": words, "masks": {str(k): v for k, v in sorted(masks.items())},
            "relocs": {str(k): v for k, v in sorted(relocs.items())}}


def compare(target, obj):
    """{"words_ok", "matched", "n", "relocs": [finding, ...], "match"} for the object's copy of the target function."""
    ours, masks, relocs = elf_function(obj, target["func"])
    ret = target["words"]
    tmask = {int(k): v for k, v in target["masks"].items()}
    trel = {int(k): v for k, v in target["relocs"].items()}
    matched, findings = 0, []
    for i in range(min(len(ret), len(ours))):
        keep = ~(tmask.get(i, 0) | masks.get(i, 0)) & 0xFFFFFFFF
        same = (ret[i] & keep) == (ours[i] & keep)
        matched += same
        if not same:
            continue
        a, b = trel.get(i), relocs.get(i)
        if a != b:
            findings.append("RELOC word %d: target %s, draft %s" % (i, " ".join(a) if a else "none", " ".join(b) if b else "none"))
        elif a and ret[i] != ours[i]:
            findings.append("RELOC word %d: %s %s has another offset in the draft" % (i, a[0], a[1]))
    words_ok = len(ours) == len(ret) and matched == len(ret)
    return {"words_ok": words_ok, "matched": matched, "n": len(ret), "relocs": findings,
            "match": words_ok and not findings}


def check(src, func, target, compiler=None, incs=()):
    """Compile src and compare; the result of compare(), or {"nocompile": stderr}."""
    with tempfile.TemporaryDirectory() as t:
        obj = os.path.join(t, "draft.o")
        err = build(src, obj, compiler or target["compiler"], incs)
        if err:
            return {"nocompile": err}
        try:
            return compare(target, obj)
        except ValueError as e:
            return {"nocompile": str(e)}


def self_test():
    """Good: a function matches its own target. Bad: another body fails on words. Relocation bad cases: the same words
    through another symbol, and through another offset of the same symbol, pass the masked words and fail the match."""
    with tempfile.TemporaryDirectory() as t:
        def write(name, text):
            path = os.path.join(t, name)
            with open(path, "w") as f:
                f.write(text)
            return path
        head = "struct S { int a; int b; }; extern struct S g_S; extern int g_T;\n"
        good = write("good.c", head + "int f(int x) { return g_S.b + x * 3; }\n")
        other = write("other.c", head + "int f(int x) { return g_S.b + x * 5; }\n")
        sym = write("sym.c", head + "int f(int x) { return g_T + x * 3; }\n")
        off = write("off.c", head + "int f(int x) { return g_S.a + x * 3; }\n")
        broken = write("broken.c", "int f(int x) { return y; }\n")
        for comp in sorted(COMPILERS):
            obj = os.path.join(t, "good.o")
            assert build(good, obj, comp) is None, comp
            tgt = target_of(obj, "f", comp)
            assert tgt["words"][-2] == JR_RA and tgt["relocs"], tgt
            r = check(good, "f", tgt)
            assert r["match"] and r["matched"] == r["n"], (comp, r)
            r = check(other, "f", tgt)
            assert not r["match"] and not r["words_ok"] and r["matched"] < r["n"], (comp, r)
            r = check(sym, "f", tgt)
            assert r["words_ok"] and not r["match"] and any("g_T" in x for x in r["relocs"]), (comp, r)
            r = check(off, "f", tgt)
            assert r["words_ok"] and not r["match"] and any("another offset" in x for x in r["relocs"]), (comp, r)
            assert "nocompile" in check(broken, "f", tgt), comp
    assert trim([1, JR_RA, 2, 0, 0]) == [1, JR_RA, 2] and trim([1, 2]) == [1, 2]
    print("SELF-TEST OK")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("mode", choices=("target", "check"))
    ap.add_argument("src")
    ap.add_argument("func")
    ap.add_argument("--target")
    ap.add_argument("--compiler", choices=sorted(COMPILERS))
    ap.add_argument("-I", dest="incs", action="append", default=[])
    ap.add_argument("--json", action="store_true", help="check: print the whole result as JSON instead of lines")
    a = ap.parse_args()
    if a.mode == "target":
        comp = a.compiler or "gcc2.95.2"
        with tempfile.TemporaryDirectory() as t:
            obj = os.path.join(t, "t.o")
            err = build(a.src, obj, comp, a.incs)
            if err:
                sys.exit("probe: %s does not compile under %s\n%s" % (a.src, comp, err))
            json.dump(target_of(obj, a.func, comp), sys.stdout, sort_keys=True)
        return 0
    with open(a.target) as f:
        r = check(a.src, a.func, json.load(f), a.compiler, a.incs)
    if a.json:
        json.dump(r, sys.stdout, sort_keys=True)
    elif "nocompile" in r:
        print("PROBE nocompile")
    else:
        print("PROBE %s %d/%d" % ("match" if r["match"] else "fail", r["matched"], r["n"]))
        for line in r["relocs"]:
            print(line)
    return 2 if "nocompile" in r else 0 if r["match"] else 1


if __name__ == "__main__":
    sys.exit(main())
