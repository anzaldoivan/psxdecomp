#!/usr/bin/env python3
"""identify.py — S2: facts about the user's own dump, read in place.

    identify.py DUMP [--target DIR] [--profile psx] [--dat REDUMP.dat] [--dry-run]
    identify.py --self-test

Loads the console profile's probe module (profiles/<id>/profile.toml [medium].probe) and writes, under the target's
ignored .run/bootstrap/: medium.json (facts only: names, sizes, addresses, counts, hashes) and seeds.txt (first-pass
function starts, leads for PA3 phase 1.2). No byte of the medium is copied anywhere. The dump path itself is not
written to medium.json (it is machine-local; the interview record keeps it). A second line, DEBUG, names the debug
leftovers on the disc (a symbol file, a link map, source files): the S4 gate asks the developer about them.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def load_probe(profile: str):
    pdir = common.PLUGIN_ROOT / "profiles" / profile
    prof = common.load_toml(pdir / "profile.toml")
    if not prof["console"].get("supported"):
        raise common.Fail("console profile %r is not yet supported" % profile)
    path = pdir / prof["medium"]["probe"]
    spec = importlib.util.spec_from_file_location("probe_" + profile, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return prof, mod


def identify(dump: str, profile="psx", dat=None) -> tuple[dict, list[str]]:
    prof, probe = load_probe(profile)
    ext = dump.lower().rsplit(".", 1)[-1]
    if ext not in prof["medium"]["kinds"]:
        raise common.Fail("%s: .%s is not a supported dump kind (%s)" % (dump, ext, ", ".join(prof["medium"]["kinds"])))
    try:
        medium, seeds = probe.identify(dump)
    except (ValueError, OSError) as e:
        raise common.Fail("%s: %s" % (os.path.basename(dump), e))
    medium["profile"] = profile
    medium["identified_at"] = common.now_iso()
    if dat:
        name = probe.match_dat(dat, medium["track01"]["sha1"])
        medium["redump"] = {"dat": os.path.basename(dat), "match": name}
    return medium, seeds


def summary(m: dict) -> str:
    p = m["psyq"]
    return ("%s boots %s (serial %s); exe %s bytes at %s, entry %s; %d track(s), track 01 sha1 %s; PsyQ %s (%d stamps); "
            "%d seeds%s" % (m["volume_id"], m["boot_exe"], m["serial"] or "none", m["exe"]["file_size"],
                            m["exe"]["t_addr"], m["exe"]["pc0"], m["toc"]["tracks"], m["track01"]["sha1"][:12],
                            p["version"] or p.get("note", "not detected"), p["stamps"], m["seeds"]["count"],
                            ("; Redump: %s" % m["redump"]["match"]) if m.get("redump") else ""))


def debug_line(m: dict) -> str:
    """One line on the disc's debug leftovers (medium.json debug_artifacts): names, sizes and counts."""
    d = m.get("debug_artifacts")
    if d is None:
        return "not probed (this medium.json is older than the debug scan: run identify again)"
    exe = "boot exe: %d RCS keyword string(s), %d source path string(s)" % (d["rcs_ids"], d["c_paths"])
    if not d["count"]:
        return "no debug file among %d disc files; %s" % (m["files"], exe)
    shown = ", ".join("%s (%s, %d bytes%s)" % (f["path"].lstrip("/"), f["kind"], f["size"],
                                               ", PsyQ SYM magic" if f.get("psyq_sym") else "")
                      for f in d["files"][:4])
    more = "" if d["count"] <= 4 else " and %d more" % (d["count"] - 4)
    return "%d debug file(s) by extension, %d with the PsyQ SYM magic: %s%s; %s" % (d["count"], d["psyq_sym"], shown,
                                                                                  more, exe)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", nargs="?")
    ap.add_argument("--target", default=".")
    ap.add_argument("--profile", default="psx")
    ap.add_argument("--dat")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.dump:
        ap.error("DUMP is required")
    dump = os.path.abspath(os.path.expanduser(a.dump))
    target = pathlib.Path(a.target).resolve()
    if str(pathlib.Path(dump).resolve()).startswith(str(target) + os.sep):
        print("FAIL the dump lies inside the target folder; keep it outside the repository (firewall)")
        return 1
    try:
        medium, seeds = identify(dump, a.profile, a.dat)
    except common.Fail as e:
        print("FAIL %s" % e)
        return 1
    print("MEDIUM %s" % summary(medium))
    print("DEBUG %s" % debug_line(medium))
    if not a.dry_run:
        out = target / ".run" / "bootstrap"
        common.write(out / "medium.json", json.dumps(medium, indent=2, sort_keys=True) + "\n")
        common.write(out / "seeds.txt", "# first-pass function starts (%s); leads for phase 1.2, not facts\n%s\n"
                     % (medium["seeds"]["method"], "\n".join(seeds)))
        common.State(target).mark("S2", "done", summary(medium)[:300])
        print("WROTE .run/bootstrap/medium.json, .run/bootstrap/seeds.txt")
    return 0


def self_test() -> int:
    sys.path.insert(0, str(common.PLUGIN_ROOT / "fixtures" / "homebrew-psx"))
    import make_disc
    ok = True
    with tempfile.TemporaryDirectory() as td:
        paths = make_disc.build(td)
        m, seeds = identify(paths["cue"])
        ok &= m["boot_exe"] == "HELLO.EXE" and m["exe"]["pc0"] == "0x80010000"
        ok &= m["psyq"] == {"stamps": 2, "version": "4.7", "libnums": [1, 3], "first": "0x80010020",
                            "last": "0x80010028"}
        ok &= seeds == ["0x80010000", "0x80010014"] and m["toc"]["tracks"] == 2
        ok &= m["toc"]["line"] == "1:MODE2/2352:25;2:AUDIO:150"
        # the planted debug leftover: a name, a size and the magic, never the file's bytes
        want = {"count": 1, "psyq_sym": 1, "rcs_ids": 0, "c_paths": 0, "note": m["debug_artifacts"]["note"],
                "files": [{"path": "/MAIN.SYM", "size": 8, "kind": "symbols", "psyq_sym": True}]}
        ok &= m["debug_artifacts"] == want and "MND\\u0001" not in json.dumps(m)
        ok &= debug_line(m).startswith("1 debug file(s) by extension, 1 with the PsyQ SYM magic: MAIN.SYM (symbols, ")
        print("  debug: %s" % debug_line(m))
        blob = json.dumps(m)
        ok &= "PS-X EXE" not in blob and td not in blob                    # facts only; no path, no bytes
        # a cooked .iso of the same volume: write the 2048-byte user data
        iso = os.path.join(td, "cooked.iso")
        sys.path.insert(0, str(common.PLUGIN_ROOT / "profiles" / "psx" / "probes"))
        import psx
        trk = psx.DataTrack(paths["track1"], "MODE2/2352")
        with open(iso, "wb") as f:
            for i in range(25):
                f.write(trk.sector(i))
        trk.close()
        m2, _ = identify(iso)
        ok &= m2["exe"]["sha1"] == m["exe"]["sha1"]
        # the stamp decoder: a big-endian halfword at +6 (ghidra_psx_ldr DetectPsyQ); patch levels keep 4 digits
        def stamped(*vers):
            return psx.psyq_version(psx.ps_stamps(b"".join(b"Ps\x01\0\0\0" + bytes.fromhex(v) for v in vers), 0))
        cases = {("4700",): "4.7", ("4010",): "4.0.10", ("3610",): "3.6.10", ("3611",): "3.6.11",
                 ("4000", "4010"): "4.0,4.0.10", (): None}
        for vers, want in cases.items():
            got = stamped(*vers)
            ok &= got == want
            print("  stamp %s -> %s%s" % ("+".join(vers) or "none", got, "" if got == want else " (want %s)" % want))
        # the scan itself: extensions are leads, the magic decides, the exe gives counts and no string
        disc = [{"path": "/DATA/STAGE1.MAP", "size": 9}, {"path": "/GAME.SYM", "size": 5}, {"path": "/A.SYM", "size": 4},
                {"path": "/SRC/MAIN.C", "size": 1}, {"path": "/MOVIE.STR", "size": 2}, {"path": "/SYM", "size": 3}]
        exe = b"\0$Id: main.c,v 1.4 $\0C:\\GAME\\MAIN.C\0C:\\GAME\\MAIN.C\0src/draw.c\0a.c\0$Revision: 2 $"
        d = psx.debug_artifacts(disc, exe, lambda f: b"MND\x01" if f["path"] == "/GAME.SYM" else b"MNDX")
        ok &= [f["path"] for f in d["files"]] == ["/GAME.SYM", "/A.SYM", "/DATA/STAGE1.MAP", "/SRC/MAIN.C"]
        ok &= (d["count"], d["psyq_sym"], d["rcs_ids"], d["c_paths"]) == (4, 1, 2, 2)
        ok &= "main" not in json.dumps(d).lower().replace("/src/main.c", "")
        none = psx.debug_artifacts(disc[4:], b"")
        ok &= (none["count"], none["files"]) == (0, []) and len(psx.debug_artifacts(disc * 30, b"")["files"]) == 50
        ok &= debug_line({"files": 2, "debug_artifacts": none}).startswith("no debug file among 2 disc files")
        ok &= debug_line({}).startswith("not probed")
        print("  debug scan: %d files, %d magic, %d RCS, %d source paths" % (d["count"], d["psyq_sym"], d["rcs_ids"],
                                                                         d["c_paths"]))
        # refusals: not a PS1 disc, an unsupported kind
        junk = os.path.join(td, "junk.iso")
        open(junk, "wb").write(b"\0" * 2048 * 20)
        for bad in (junk, os.path.join(td, "game.chd")):
            open(bad, "ab").close()
            try:
                identify(bad)
                ok = False
                print("  control %s NOT REFUSED" % os.path.basename(bad))
            except common.Fail:
                print("  control %s refused" % os.path.basename(bad))
        # a Redump DAT match
        dat = os.path.join(td, "psx.dat")
        open(dat, "w").write('<?xml version="1.0"?><datafile><game name="Fixture (World)"><rom name="t1.bin" sha1="%s"/>'
                             '</game></datafile>' % m["track01"]["sha1"])
        ok &= identify(paths["cue"], dat=dat)[0]["redump"]["match"] == "Fixture (World)"
    return common.self_test_banner("identify", ok)


if __name__ == "__main__":
    sys.exit(main())
