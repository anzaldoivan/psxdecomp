#!/usr/bin/env python3
"""Smoke only: extract the boot executable of the SYNTHETIC fixture disc with the profile's probe module. A game
repository's extraction is its own phase-1 tool, writing into ignored paths; this never runs on a real dump."""
import os
import sys

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(root, "profiles", "psx", "probes"))
import psx  # noqa: E402

cue, out = sys.argv[1], sys.argv[2]
t1 = psx.parse_cue(cue)[0]
trk = psx.DataTrack(t1["file"], t1["mode"])
files, _ = psx.iso_files(trk)
cnf = psx.find_file(files, "SYSTEM.CNF")
boot = psx.parse_system_cnf(trk.extent(cnf["lba"], cnf["size"]).decode())["boot_file"]
exe = psx.find_file(files, boot)
open(out, "wb").write(trk.extent(exe["lba"], exe["size"]))
print("EXTRACT %s %d bytes" % (boot, exe["size"]))
