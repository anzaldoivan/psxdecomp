#!/usr/bin/env python3
"""audit_public.py — psxdecomp's own firewall: no game byte, no disc image, no executable, no SDK file is tracked in
this repository (the fixtures are generated at test time, never committed).

    audit_public.py                 audit every tracked file (git ls-files)
    audit_public.py --paths P...    audit these paths instead (the negative control uses this)
    audit_public.py --self-test     plant offenders in a temp dir; each must be refused, ending `AUDIT CONTROL OK`

Exit 0: `AUDIT OK <n> files`. Exit 1: one `OFFENDER <path> <reason>` line each.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNED_EXT = {".bin", ".iso", ".cue", ".img", ".chd", ".ccd", ".sub", ".mdf", ".mds", ".pbp", ".ecm", ".exe", ".psx",
              ".elf", ".o", ".obj", ".a", ".lib", ".cpe", ".sym", ".z64", ".n64", ".v64", ".gguf", ".safetensors"}
BANNED_PREFIX = ("refs/", ".run/", "tools/psyq/", "disks/", "extracted/", "evals/results/")
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MAX_BINARY = 256 * 1024


def reasons(path: str, rel: str):
    out = []
    low = rel.lower()
    if os.path.splitext(low)[1] in BANNED_EXT:
        out.append("banned extension %s" % os.path.splitext(low)[1])
    if low.startswith(BANNED_PREFIX):
        out.append("banned path (never tracked)")
    try:
        with open(path, "rb") as f:
            head = f.read(0x9320)
        size = os.path.getsize(path)
    except OSError:
        return out
    if head[:8] == b"PS-X EXE":
        out.append("PS-X EXE header")
    if head[:12] == SYNC:
        out.append("raw CD sector sync")
    if head[:4] == b"\x7fELF":
        out.append("ELF object")
    if head[0x8001:0x8006] == b"CD001" or head[0x9319:0x931E] == b"CD001":
        out.append("ISO9660 volume descriptor")
    if size > MAX_BINARY and b"\x00" in head[:8192]:
        out.append("binary file over %d KiB" % (MAX_BINARY // 1024))
    return out


def audit(paths, base) -> int:
    bad = 0
    for rel in paths:
        for r in reasons(os.path.join(base, rel), rel):
            print("OFFENDER %s %s" % (rel, r))
            bad += 1
    if bad:
        print("AUDIT FAIL %d offender(s)" % bad)
        return 1
    print("AUDIT OK %d files" % len(paths))
    return 0


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        plants = {"game.exe.txt": b"PS-X EXE" + b"\0" * 2040, "track.raw": SYNC + b"\0" * 2340,
                  "image.cue": b'FILE "x.bin" BINARY\n', "obj.dat": b"\x7fELF" + b"\0" * 60,
                  "iso.dat": b"\0" * 0x8001 + b"CD001" + b"\0" * 64, "refs/x.md": b"clone", "big.dat": b"\0" * 300000}
        for rel, data in plants.items():
            p = os.path.join(td, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data)
            caught = bool(reasons(p, rel))
            print("  control %-14s %s" % (rel, "refused" if caught else "NOT REFUSED"))
            ok &= caught
        clean = os.path.join(td, "ok.md")
        open(clean, "w").write("# PS-X EXE is a format name, mentioned in prose\n")
        ok &= not reasons(clean, "ok.md")
    print("AUDIT CONTROL OK" if ok else "AUDIT CONTROL FAILED")
    return 0 if ok else 1


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if "--paths" in argv:
        paths = argv[argv.index("--paths") + 1:]
        return audit(paths, os.getcwd())
    files = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, check=True).stdout
    return audit([p for p in files.decode().split("\0") if p], ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
