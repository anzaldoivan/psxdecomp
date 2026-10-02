"""PS1 medium probes: CUE sheets, raw/cooked data tracks, ISO9660, SYSTEM.CNF, the PS-X EXE header, PsyQ `Ps` stamps
and first-pass function seeds.

Written fresh for psxdecomp. Reads the dump in place and returns FACTS ONLY (names, sizes, addresses, counts, hashes):
no byte of the medium is returned, copied or written by this module.

Formats: psx-spx (CD-ROM, ISO9660 and EXE sections). PsyQ library stamps: a library module carries `Ps` followed by
the library number and a version halfword; the masked pattern below is the one mmx6's T0 probe used
(50 73 xx(&E0==0) .. .. .. (&88==0) (&EE==0); a BIG-endian version halfword at +6, as ghidra_psx_ldr DetectPsyQ
reads it: `47 00` -> 4.7, `40 10` -> 4.0.10). PsyQ <= 3.5 carries no stamp (signature matching only).
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
import struct

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
EXE_MAGIC = b"PS-X EXE"


# ---- CUE ---------------------------------------------------------------------------------------------------------

def parse_cue(path: str) -> list[dict]:
    """Tracks of a CUE sheet: [{number, mode, file (absolute), index01 (frames), pregap}]."""
    base = os.path.dirname(os.path.abspath(path))
    tracks, cur_file = [], None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()
            kw = parts[0].upper()
            if kw == "FILE":
                cur_file = os.path.join(base, parts[1])
            elif kw == "TRACK":
                tracks.append({"number": int(parts[1]), "mode": parts[2].upper(), "file": cur_file,
                               "index01": None, "index00": None})
            elif kw == "INDEX" and tracks:
                mm, ss, ff = (int(x) for x in parts[2].split(":"))
                frames = (mm * 60 + ss) * 75 + ff
                tracks[-1]["index%02d" % int(parts[1])] = frames
    return tracks


def sector_size(mode: str) -> int:
    if mode == "AUDIO":
        return 2352
    return int(mode.split("/")[1]) if "/" in mode else 2048


# ---- a data track ------------------------------------------------------------------------------------------------

class DataTrack:
    """Reads 2048-byte user data from a data track file at a byte offset (raw 2352 MODE1/MODE2 form 1, or cooked)."""

    def __init__(self, path: str, mode: str = "", offset: int = 0):
        self.path, self.offset = path, offset
        self.f = open(path, "rb")
        self.raw = sector_size(mode) == 2352 if mode else self._sniff_raw()
        self.ssize = 2352 if self.raw else 2048
        self.user = 0
        if self.raw:
            self.f.seek(offset)
            head = self.f.read(16)
            if head[:12] != SYNC:
                raise ValueError("no sector sync at the start of the data track")
            self.user = 24 if head[15] == 2 else 16          # MODE2 form 1 skips the 8-byte subheader

    def _sniff_raw(self) -> bool:
        self.f.seek(self.offset)
        return self.f.read(12) == SYNC

    def sector(self, lba: int) -> bytes:
        self.f.seek(self.offset + lba * self.ssize + self.user)
        return self.f.read(2048)

    def extent(self, lba: int, size: int) -> bytes:
        out = bytearray()
        for i in range((size + 2047) // 2048):
            out += self.sector(lba + i)
        return bytes(out[:size])

    def close(self):
        self.f.close()


# ---- ISO9660 -----------------------------------------------------------------------------------------------------

def iso_files(trk: DataTrack) -> list[dict]:
    """Every file on the ISO9660 volume: [{path, lba, size}] (upper-case paths, `;1` stripped)."""
    pvd = trk.sector(16)
    if pvd[1:6] != b"CD001":
        raise ValueError("no ISO9660 primary volume descriptor at sector 16")
    root = pvd[156:156 + 34]
    out, seen = [], set()

    def walk(lba, size, path):
        if lba in seen:
            return
        seen.add(lba)
        data, i = trk.extent(lba, size), 0
        while i < len(data):
            n = data[i]
            if n == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + n]
            i += n
            elba, esz = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            flags, nl = rec[25], rec[32]
            name = rec[33:33 + nl]
            if name in (b"\x00", b"\x01"):
                continue
            nm = name.decode("ascii", "replace").split(";")[0]
            p = path + "/" + nm
            if flags & 2:
                walk(elba, esz, p)
            else:
                out.append({"path": p.upper(), "lba": elba, "size": esz})

    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
    volume_id = pvd[40:72].decode("ascii", "replace").strip()
    return out, volume_id


def find_file(files, name: str):
    want = "/" + name.upper().lstrip("/\\").replace("\\", "/")
    for f in files:
        if f["path"] == want:
            return f
    return None


# ---- SYSTEM.CNF --------------------------------------------------------------------------------------------------

def parse_system_cnf(text: str) -> dict:
    out = {}
    for line in text.replace("\r", "\n").split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().upper()] = v.strip()
    boot = out.get("BOOT", "")
    m = re.match(r"(?i)cdrom:?\\*(.+?)(;\d+)?$", boot)
    out["boot_file"] = (m.group(1) if m else boot).replace("\\", "/").lstrip("/")
    return out


SERIAL_RE = re.compile(r"^([A-Z]{4})[_-](\d{3})\.(\d{2})$")


def serial_from_boot(name: str) -> str | None:
    """`SLUS_013.95` -> `SLUS-01395` (the label serial)."""
    m = SERIAL_RE.match(os.path.basename(name).upper())
    return "%s-%s%s" % m.groups() if m else None


# ---- the PS-X EXE ------------------------------------------------------------------------------------------------

def parse_exe_header(head: bytes) -> dict:
    if head[:8] != EXE_MAGIC:
        raise ValueError("not a PS-X EXE (magic)")
    pc0, gp0, t_addr, t_size = struct.unpack_from("<IIII", head, 0x10)
    d_addr, d_size, b_addr, b_size, s_addr, s_size = struct.unpack_from("<IIIIII", head, 0x20)
    marker = head[0x4C:0x800].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
    return {"pc0": "0x%08X" % pc0, "gp0": "0x%08X" % gp0, "t_addr": "0x%08X" % t_addr, "t_size": t_size,
            "s_addr": "0x%08X" % s_addr, "s_size": s_size, "bss_addr": "0x%08X" % b_addr, "bss_size": b_size,
            "region_marker": marker[:80]}


def ps_stamps(text: bytes, base: int) -> list[dict]:
    """PsyQ library stamps in an executable image: [{addr, libnum, version}]."""
    hits = []
    for m in re.finditer(rb"Ps", text):
        o = m.start()
        s = text[o:o + 8]
        if len(s) < 8 or s[2] & 0xE0 or s[6] & 0x88 or s[7] & 0xEE:
            continue
        v = struct.unpack_from(">H", s, 6)[0]
        ver = "%03X" % (v >> 4) if (v & 0xFF) == 0 else "%04X" % v
        hits.append({"addr": "0x%08X" % (base + o), "libnum": s[2], "version": ver})
    return hits


NO_STAMP = "no Ps stamp: PsyQ <=3.5 (signature-only) or not PsyQ"


def psyq_version(stamps: list[dict]) -> str | None:
    """`470` -> `4.7`, `4010` -> `4.0.10` when every stamp agrees; a list when they do not; None when there are none."""
    vers = sorted({h["version"] for h in stamps})
    if not vers:
        return None

    def fmt(v):
        if not v.isdigit():
            return v
        return "%s.%s" % (v[0], v[1:].rstrip("0") or "0") if len(v) == 3 else "%s.%s.%s" % (v[0], v[1], v[2:])
    return fmt(vers[0]) if len(vers) == 1 else ",".join(fmt(v) for v in vers)


def function_seeds(text: bytes, base: int, limit: int = 4096) -> list[str]:
    """First-pass function starts: `addiu sp,sp,-N` prologues (leads for PA3 phase 1.2, never facts)."""
    out = []
    for o in range(0, len(text) - 3, 4):
        w = struct.unpack_from("<I", text, o)[0]
        if (w >> 16) == 0x27BD and (w & 0x8000):
            out.append("0x%08X" % (base + o))
            if len(out) >= limit:
                break
    return out


SDK_STRINGS = [rb"Library Programs \(c\) 19\d\d-19\d\d Sony Computer Entertainment Inc\.",
               rb"PsyQ", rb"PSYQ", rb"Psy-Q"]


def sdk_strings(text: bytes) -> list[str]:
    out = []
    for pat in SDK_STRINGS:
        m = re.search(pat, text)
        if m:
            out.append(m.group(0).decode("ascii", "replace"))
    return out


# ---- the whole probe ---------------------------------------------------------------------------------------------

def hash_range(path, start, length, chunk=1 << 20) -> dict:
    h1, h2 = hashlib.sha1(), hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(start)
        left = length
        while left > 0:
            b = f.read(min(chunk, left))
            if not b:
                break
            h1.update(b)
            h2.update(b)
            left -= len(b)
    return {"sha1": h1.hexdigest(), "sha256": h2.hexdigest(), "bytes": length}


def toc(tracks: list[dict]) -> list[dict]:
    """Track table with lengths in frames, from the files and INDEX 01 offsets (Redump: one file per track)."""
    rows = []
    for i, t in enumerate(tracks):
        ss = sector_size(t["mode"])
        start = (t["index01"] or 0) * ss
        nxt = tracks[i + 1] if i + 1 < len(tracks) else None
        if nxt and nxt["file"] == t["file"]:
            end = (nxt["index00"] if nxt["index00"] is not None else nxt["index01"]) * ss
        else:
            end = os.path.getsize(t["file"]) if t["file"] and os.path.exists(t["file"]) else start
        rows.append({"number": t["number"], "mode": t["mode"], "start": start, "length": end - start,
                     "frames": (end - start) // ss})
    return rows


def identify(dump: str, seeds_limit: int = 4096) -> dict:
    """Facts about a PS1 dump (a .cue, or a single .bin/.iso data track). Raises ValueError on a non-PS1 medium."""
    dump = os.path.abspath(dump)
    if dump.lower().endswith(".cue"):
        tracks = parse_cue(dump)
        if not tracks:
            raise ValueError("the CUE sheet lists no tracks")
    else:
        tracks = [{"number": 1, "mode": "", "file": dump, "index01": 0, "index00": None}]
    t1 = tracks[0]
    if t1["mode"] == "AUDIO":
        raise ValueError("track 01 is audio, not a data track")
    rows = toc(tracks) if tracks[0]["mode"] else [{"number": 1, "mode": "?", "start": 0,
                                                    "length": os.path.getsize(dump), "frames": None}]
    trk = DataTrack(t1["file"], t1["mode"], rows[0]["start"])
    try:
        files, volume_id = iso_files(trk)
        cnf = find_file(files, "SYSTEM.CNF")
        if not cnf:
            raise ValueError("no SYSTEM.CNF on the data track (not a PS1 boot disc?)")
        cnf_info = parse_system_cnf(trk.extent(cnf["lba"], cnf["size"]).decode("ascii", "replace"))
        exe = find_file(files, cnf_info["boot_file"])
        if not exe:
            raise ValueError("SYSTEM.CNF boots %r, which is not on the disc" % cnf_info["boot_file"])
        image = trk.extent(exe["lba"], exe["size"])
    finally:
        trk.close()
    hdr = parse_exe_header(image[:0x800])
    base = int(hdr["t_addr"], 16)
    text = image[0x800:0x800 + hdr["t_size"]]
    stamps = ps_stamps(text, base)
    seeds = function_seeds(text, base, seeds_limit)
    toc_line = ";".join("%d:%s:%s" % (r["number"], r["mode"], r["frames"]) for r in rows)
    medium = {
        "console": "psx",
        "volume_id": volume_id,
        "files": len(files),
        "file_list": [{"path": f["path"], "size": f["size"]} for f in files][:200],
        "system_cnf": {k: v for k, v in cnf_info.items() if k in ("BOOT", "TCB", "EVENT", "STACK", "boot_file")},
        "boot_exe": os.path.basename(cnf_info["boot_file"]).upper(),
        "serial": serial_from_boot(cnf_info["boot_file"]),
        "exe": dict(hdr, file_size=exe["size"], sha1=hashlib.sha1(image).hexdigest()),
        "track01": dict(hash_range(t1["file"], rows[0]["start"], rows[0]["length"]),
                        mode=t1["mode"] or ("raw" if os.path.getsize(dump) % 2352 == 0 else "cooked")),
        "toc": {"tracks": len(rows), "line": toc_line,
                "fingerprint": hashlib.sha256(toc_line.encode()).hexdigest()[:16]},
        "psyq": {"stamps": len(stamps), "version": psyq_version(stamps),
                 "libnums": sorted({h["libnum"] for h in stamps}),
                 "first": stamps[0]["addr"] if stamps else None, "last": stamps[-1]["addr"] if stamps else None,
                 **({} if stamps else {"note": NO_STAMP})},
        "sdk_strings": sdk_strings(text),
        "seeds": {"method": "addiu sp,sp,-N prologue scan (leads only)", "count": len(seeds),
                  "entry": hdr["pc0"]},
    }
    return medium, seeds


def match_dat(dat_path: str, sha1: str) -> str | None:
    """The game name of a Redump/Logiqx DAT entry holding a rom with this sha1."""
    import xml.etree.ElementTree as ET
    for game in ET.parse(dat_path).getroot().iter("game"):
        for rom in game.iter("rom"):
            if rom.get("sha1", "").lower() == sha1.lower():
                return game.get("name")
    return None
