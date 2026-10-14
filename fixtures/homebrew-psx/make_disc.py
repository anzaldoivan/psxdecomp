#!/usr/bin/env python3
"""Build the synthetic PS1 disc: a PS-X EXE from hello.s's pre-encoded words, an ISO9660 volume with SYSTEM.CNF and
a planted debug leftover (MAIN.SYM: the PsyQ symbol magic and nothing else), written as raw MODE2/2352 sectors plus a
short audio track, and a Redump-style CUE sheet.

CC0 1.0. Deterministic (fixed dates). Output goes to the folder given (a temp dir in tests); nothing it writes is ever
committed: the repository's own audit refuses disc images and executables.

    python3 make_disc.py <out_dir>        -> HOMEBREW.cue, HOMEBREW (Track 1).bin, HOMEBREW (Track 2).bin, hello.exe
    python3 make_disc.py --proto <out_dir> -> PROTO.EXE: a second build (build_proto)
"""
import os
import struct
import sys

LOAD = 0x80010000
WORDS = [0x27BDFFE8, 0xAFBF0014, 0x2408002A, 0x1000FFFF, 0x00000000,   # _start
         0x27BDFFF8, 0x03E00008, 0x27BD0008]                             # leaf
STAMPS = bytes([0x50, 0x73, 0x01, 0, 0, 0, 0x47, 0, 0x50, 0x73, 0x03, 0, 0, 0, 0x47, 0])
BOOT = "HELLO.EXE"
MARKER = b"psxdecomp homebrew fixture (CC0)"
SYM_NAME = "MAIN.SYM"
SYM = b"MND\x01" + bytes(4)                     # the header of an empty PsyQ symbol file: no symbol in it
PROTO = "PROTO.EXE"
PROTO_TEXT = b"proto build %d\0\0"             # a string that the second build has and the first lacks


def exe_image() -> bytes:
    text = b"".join(struct.pack("<I", w) for w in WORDS) + STAMPS
    text += b"\0" * (-len(text) % 2048)
    hdr = bytearray(2048)
    hdr[0:8] = b"PS-X EXE"
    struct.pack_into("<IIII", hdr, 0x10, LOAD, 0, LOAD, len(text))
    struct.pack_into("<II", hdr, 0x30, 0x801FFFF0, 0)
    hdr[0x4C:0x4C + len(MARKER)] = MARKER
    return bytes(hdr) + text


def proto_image() -> bytes:
    """A second build: 20 words of other code, then the first build's text (at another address), then a function
    (scripts/img.py's self-test maker) that builds the address of PROTO_TEXT, a zero word, then the text."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
    import img
    first = exe_image()
    at = LOAD + 4 * 20 + len(first) - 2048 + 4 * 13
    text = b"".join(struct.pack("<I", w) for w in img.filler(3, 20) + img.body((at + 0x8000) >> 16, at & 0xFFFF, 0x4000)
                    + (0,))
    text = text[:80] + first[2048:] + text[80:] + PROTO_TEXT
    text += b"\0" * (-len(text) % 2048)
    hdr = bytearray(first[:2048])
    struct.pack_into("<I", hdr, 0x1C, len(text))
    return bytes(hdr) + text


def build_proto(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, PROTO)
    with open(path, "wb") as f:
        f.write(proto_image())
    return path


def both16(v):
    return struct.pack("<H", v) + struct.pack(">H", v)


def both32(v):
    return struct.pack("<I", v) + struct.pack(">I", v)


DATE7 = bytes([126, 10, 1, 0, 0, 0, 0])          # 2026-10-01 00:00:00 GMT


def dirrec(name: bytes, lba: int, size: int, isdir: bool) -> bytes:
    n = len(name)
    rec = bytearray(33 + n + (1 if n % 2 == 0 else 0))
    rec[0] = len(rec)
    rec[2:10] = both32(lba)
    rec[10:18] = both32(size)
    rec[18:25] = DATE7
    rec[25] = 2 if isdir else 0
    rec[28:32] = both16(1)
    rec[32] = n
    rec[33:33 + n] = name
    return bytes(rec)


def iso_sectors(files):
    """files: [(name, bytes)] -> list of 2048-byte user-data sectors for the whole volume."""
    root_lba, first = 20, 21
    layout, lba = [], first
    for name, data in files:
        layout.append((name, lba, data))
        lba += max(1, (len(data) + 2047) // 2048)
    total = lba
    root = dirrec(b"\x00", root_lba, 2048, True) + dirrec(b"\x01", root_lba, 2048, True)
    for name, l, data in sorted(layout):
        root += dirrec(name.encode() + b";1", l, len(data), False)
    root += b"\0" * (2048 - len(root))
    ptl = bytes([1, 0]) + struct.pack("<I", root_lba) + struct.pack("<H", 1) + b"\x00\x00"
    ptm = bytes([1, 0]) + struct.pack(">I", root_lba) + struct.pack(">H", 1) + b"\x00\x00"
    pvd = bytearray(2048)
    pvd[0], pvd[1:6], pvd[6] = 1, b"CD001", 1
    pvd[8:40] = b"PLAYSTATION".ljust(32)
    pvd[40:72] = b"PSXDECOMP_FIXTURE".ljust(32)
    pvd[80:88] = both32(total)
    pvd[120:124], pvd[124:128], pvd[128:132] = both16(1), both16(1), both16(2048)
    pvd[132:140] = both32(len(ptl))
    struct.pack_into("<I", pvd, 140, 18)
    struct.pack_into(">I", pvd, 148, 19)
    pvd[156:190] = dirrec(b"\x00", root_lba, 2048, True)
    pvd[881] = 1
    term = bytearray(2048)
    term[0], term[1:6], term[6] = 255, b"CD001", 1
    secs = [bytes(2048)] * 16 + [bytes(pvd), bytes(term), ptl.ljust(2048, b"\0"), ptm.ljust(2048, b"\0"), root]
    for name, l, data in layout:
        pad = data + b"\0" * (-len(data) % 2048 or (2048 if not data else 0))
        secs += [pad[i:i + 2048] for i in range(0, len(pad), 2048)]
    return secs


def bcd(n):
    return ((n // 10) << 4) | (n % 10)


def raw_mode2(secs) -> bytes:
    out = bytearray()
    for i, s in enumerate(secs):
        a = i + 150
        mm, ss, ff = a // 4500, (a // 75) % 60, a % 75
        head = b"\x00" + b"\xff" * 10 + b"\x00" + bytes([bcd(mm), bcd(ss), bcd(ff), 2])
        sub = bytes([0, 0, 0x08, 0]) * 2                       # form 1, data
        out += head + sub + s + b"\0" * 280                    # EDC/ECC zeroed: a fixture, not a burnable image
    return bytes(out)


def build(out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    exe = exe_image()
    cnf = ("BOOT = cdrom:\\%s;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n" % BOOT).encode()
    secs = iso_sectors([("SYSTEM.CNF", cnf), (BOOT, exe), (SYM_NAME, SYM)])
    t1 = os.path.join(out_dir, "HOMEBREW (Track 1).bin")
    t2 = os.path.join(out_dir, "HOMEBREW (Track 2).bin")
    with open(t1, "wb") as f:
        f.write(raw_mode2(secs))
    with open(t2, "wb") as f:
        f.write(b"\0" * 2352 * 300)
    cue = os.path.join(out_dir, "HOMEBREW.cue")
    with open(cue, "w", newline="\n") as f:
        f.write('FILE "HOMEBREW (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
                'FILE "HOMEBREW (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n'
                '    INDEX 01 00:02:00\n')
    with open(os.path.join(out_dir, "hello.exe"), "wb") as f:
        f.write(exe)
    return {"cue": cue, "track1": t1, "exe": os.path.join(out_dir, "hello.exe")}


if __name__ == "__main__":
    if sys.argv[1:2] == ["--proto"] and len(sys.argv) == 3:
        sys.exit(print("proto %s" % build_proto(sys.argv[2])))
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        sys.exit("usage: make_disc.py [--proto] <out_dir>")
    for k, v in build(sys.argv[1]).items():
        print("%s %s" % (k, v))
