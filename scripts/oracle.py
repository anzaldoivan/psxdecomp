#!/usr/bin/env python3
"""oracle.py — the record of the oracle-build question: the disc scan, and the hashes of a supplied copy.

    oracle.py record --repo R [--dump CUE | --medium FILE] (--byo PATH | --no-copy) [--dry-run]
    oracle.py --self-test

An oracle build is another build of the game's program that carries more than the target: symbols, a link map
(docs/REFS.md, "Oracle builds"). `record` writes into a game repository and commits nothing:

- `[oracle]` in config/psxdecomp.toml: `checked` (the day), `disc_debug_files` and `disc_psyq_sym` (the counts of the
  disc scan), and `byo` ("none", "own disc", or "<n> file(s) hashed").
- config/oracle.sha1 (sha1sum format, base names, merged with the file's lines and sorted): one SHA-1 per file of the
  copy that `--byo` names. A file gives one, a folder one per file. A disc image (.cue, .bin, .iso, .img) also gives
  one per file of its ISO 9660 volume, because a file taken out of the image is what a commit would hold. An empty
  file and a file over the audit's 50 MiB cap give none.
- the line `required: config/oracle.sha1` in config/firewall.txt, when the file holds a hash (the audit refuses an
  empty source). From then on tools/audit_public.py refuses a tracked copy of any of those files, under any name.

The disc facts come from `--dump` (read in place, as identify.py reads it) or from `--medium`: a medium.json, or a
JSON file that holds its `debug_artifacts` alone (the scan of a dump on another machine). With neither, the facts of
an earlier record stay. `--byo` refuses a path inside the repository and writes nothing. The dump's own path gives no
hash: the retail manifest covers the developer's own disc. No byte and no path of a build is written anywhere.
tools/audit_public.py runs afterwards: exit 1 when it fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import identify  # noqa: E402

RECORD = "config/psxdecomp.toml"
HASHES = "config/oracle.sha1"
REQUIRED = ("# ---- psxdecomp: the files of a supplied copy of another build (`oracle record --byo`) ----\n"
            "required: %s\n" % HASHES)
HEAD = ("# %s: the SHA-1 of each file of another build that the developer supplied (psxdecomp, `oracle record --byo`).\n"
        "# tools/audit_public.py refuses a tracked file with one of these hashes. No byte of the build is here.\n" % HASHES)
CAP = 50 << 20                                   # the audit refuses a tracked file over 50 MiB whatever it holds
IMAGE_EXT = (".cue", ".bin", ".iso", ".img")
COMMAND = "psxd oracle record --repo . --dump <your dump> --no-copy"


def inside(path: pathlib.Path, repo: pathlib.Path) -> bool:
    return path == repo or repo in path.parents


def sha1_file(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def image_hashes(path: pathlib.Path, probe) -> tuple[list[tuple[str, str]], set[str]]:
    """(one (sha1, base name) per file of a disc image's ISO 9660 volume, the track files of a CUE sheet). A file that
    is no such image gives none."""
    try:
        cue = path.suffix.lower() == ".cue"
        tracks = probe.parse_cue(str(path)) if cue else [{"number": 1, "mode": "", "file": str(path), "index01": 0}]
        start = probe.toc(tracks)[0]["start"] if cue else 0
        trk = probe.DataTrack(tracks[0]["file"], tracks[0]["mode"], start)
    except (ValueError, OSError, KeyError, IndexError, TypeError):
        return [], set()
    try:
        files = probe.iso_files(trk)[0]
        out = [(hashlib.sha1(trk.extent(f["lba"], f["size"])).hexdigest(), f["path"].rsplit("/", 1)[-1])
               for f in files if 0 < f["size"] <= CAP]
    except (ValueError, OSError, struct.error, IndexError):
        out = []
    finally:
        trk.close()
    return out, {t["file"] for t in tracks if t.get("file")} if cue else set()


def copy_hashes(byo: pathlib.Path) -> list[tuple[str, str]]:
    """(sha1, base name) of each file of a supplied copy, and of each file inside a disc image among them."""
    probe = identify.load_probe("psx")[1]
    files = [byo] if byo.is_file() else sorted(p for p in byo.rglob("*") if p.is_file()
                                              and not set(p.relative_to(byo).parts) & common.SKIP_NAMES)
    files.sort(key=lambda p: p.suffix.lower() != ".cue")            # a sheet first: its tracks are read through it
    out, read = [], set()
    for p in files:
        if 0 < p.stat().st_size <= CAP:
            out.append((sha1_file(p), p.name))
        if p.suffix.lower() in IMAGE_EXT and str(p) not in read:
            inner, tracks = image_hashes(p, probe)
            out += inner
            read |= tracks
            for t in sorted(tracks):                                 # a sheet given alone: its track files count too
                if pathlib.Path(t) not in files and os.path.isfile(t) and 0 < os.path.getsize(t) <= CAP:
                    out.append((sha1_file(t), os.path.basename(t)))
    return out


def parse_hashes(text: str) -> dict[str, str]:
    """{sha1: name} of a sha1sum file, as the kit's audit reads one."""
    rows = (l.split(None, 1) for l in text.splitlines())
    return {r[0].lower(): r[1].strip() for r in rows if len(r) == 2 and len(r[0]) == 40}


def load_debug(path) -> dict:
    """The `debug_artifacts` of a medium.json, or of a JSON file that holds that table alone."""
    try:
        doc = json.loads(common.read(path))
    except (OSError, ValueError) as e:
        raise common.Fail("%s: not a JSON file (%s)" % (path, e))
    debug = doc.get("debug_artifacts", doc) if isinstance(doc, dict) else None
    if not isinstance(debug, dict) or not {"count", "psyq_sym"} <= set(debug):
        raise common.Fail("%s holds no `debug_artifacts` (count, psyq_sym): run `psxd identify <dump>` again" % path)
    return debug


def record(repo, debug: dict | None, byo: str | None, dump: str | None = None, dry: bool = False) -> tuple[list[str], str]:
    """Write the record (module docstring). Returns (one `created|changed <path>` line per file, the summary line).
    Every refusal comes before the first write."""
    import upgrade
    repo = pathlib.Path(repo).resolve()
    if not (repo / RECORD).is_file() or not (repo / common.FIREWALL).is_file():
        raise common.Fail("%s has no %s or no %s: bootstrap or adopt the repository first (/psxdecomp:upgrade)"
                          % (repo, RECORD, common.FIREWALL))
    have = upgrade.record_tables(repo).get("oracle") or {}
    own, fresh = False, []
    if byo:
        path = pathlib.Path(os.path.expanduser(byo)).resolve()
        if inside(path, repo):
            raise common.Fail("the copy lies inside the repository (firewall): keep it outside. Nothing was written")
        if not path.exists():
            raise common.Fail("%s does not exist. Nothing was written" % path)
        own = bool(dump) and path == pathlib.Path(os.path.expanduser(dump)).resolve()
        if not own:
            fresh = copy_hashes(path)
            if not fresh:
                raise common.Fail("%s holds no file to hash (empty, or over %d MiB each). Nothing was written"
                                  % (path, CAP >> 20))
    old = parse_hashes(common.read(repo / HASHES)) if (repo / HASHES).is_file() else {}
    merged = dict(old)
    for sha, name in fresh:
        merged.setdefault(sha, name)
    if merged:
        said = "%d file(s) hashed" % len(merged)
    else:
        said = "own disc" if own or (not byo and have.get("byo") == "own disc") else "none"
    text = common.read(repo / RECORD)
    text = upgrade.record_set(text, "oracle", "checked", common.today())
    if debug is not None:
        text = upgrade.record_set(text, "oracle", "disc_debug_files", int(debug["count"]))
        text = upgrade.record_set(text, "oracle", "disc_psyq_sym", int(debug["psyq_sym"]))
    text = upgrade.record_set(text, "oracle", "byo", said)
    written = []

    def w(rel, body):
        st = common.write(repo / rel, body, dry=dry)
        if st != "unchanged":
            written.append("%s%s %s" % ("would be " if dry else "", st, rel))

    if merged != old:
        w(HASHES, HEAD + "".join("%s  %s\n" % (s, n) for s, n in sorted(merged.items(), key=lambda x: (x[1], x[0]))))
    fw = common.read(repo / common.FIREWALL)
    if merged and HASHES not in common.firewall_lines(fw, "required"):
        w(common.FIREWALL, fw.rstrip("\n") + "\n\n" + REQUIRED)
    w(RECORD, text)
    return written, "%s; byo: %s%s" % (scan_line(common.load_toml_str(text)["oracle"]), said, " (%d new)" % (len(merged) - len(old)) if fresh else "")


def scan_line(table: dict) -> str:
    if "disc_debug_files" not in table:
        return "disc: not scanned"
    return "disc: %d debug file(s), %d with the PsyQ SYM magic" % (table["disc_debug_files"], table.get("disc_psyq_sym", 0))


def audit(repo: pathlib.Path) -> tuple[int, str] | None:
    """(exit code, last lines) of the game's tools/audit_public.py; None when the repository has none."""
    tool = repo / "tools" / "audit_public.py"
    if not tool.is_file():
        return None
    r = common.run([common.find_python() or sys.executable, tool], cwd=repo, check=False, timeout=600)
    return r.returncode, (r.stdout + r.stderr).strip()[-400:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["record"])
    ap.add_argument("--repo", default=".")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--dump")
    src.add_argument("--medium")
    copy = ap.add_mutually_exclusive_group()
    copy.add_argument("--byo")
    copy.add_argument("--no-copy", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd != "record":
        ap.error("the command is `record`")
    if not a.byo and not a.no_copy:
        ap.error("give --byo PATH (your own copy of another build) or --no-copy")
    repo = pathlib.Path(a.repo).resolve()
    try:
        debug = None
        if a.dump:
            dump = os.path.abspath(os.path.expanduser(a.dump))
            if inside(pathlib.Path(dump).resolve(), repo):
                raise common.Fail("the dump lies inside the repository; keep it outside (firewall)")
            debug = identify.identify(dump)[0]["debug_artifacts"]
        elif a.medium:
            debug = load_debug(a.medium)
        elif "disc_debug_files" not in (__import__("upgrade").record_tables(repo).get("oracle") or {}):
            raise common.Fail("no disc scan yet: give --dump <your dump>, or --medium <a medium.json>")
        written, line = record(repo, debug, a.byo, a.dump, a.dry_run)
    except common.Fail as e:
        print("FAIL %s" % e)
        return 1
    print("ORACLE %s" % line)
    for x in written:
        print("  %s" % x)
    if a.dry_run:
        return 0
    res = audit(repo)
    if res and res[0] != 0:
        print("FAIL the audit refuses the tree (the record stays written): %s" % res[1])
        return 1
    print("AUDIT %s" % ("OK" if res else "not run (no tools/audit_public.py)"))
    paths = [x.split(" ", 1)[1] for x in written]
    if paths:
        print("NEXT commit %s" % " ".join(paths))
    return 0


def self_test() -> int:
    import contextlib
    import io
    import upgrade
    sys.path.insert(0, str(common.PLUGIN_ROOT / "fixtures" / "homebrew-psx"))
    import make_disc
    ok = True
    fw = "purge: disks/\nfixture:  config/firewall-fixture.sha1\n"
    rec = '[psxdecomp]\nversion = "0.0.0"\n\n[deviations]\nlist = []\n'
    debug = {"count": 2, "psyq_sym": 1, "files": [], "note": ""}

    def fresh(td, name):
        repo = pathlib.Path(td).resolve() / name
        common.write(repo / RECORD, rec)
        common.write(repo / common.FIREWALL, fw)
        return repo

    def table(repo):
        return upgrade.record_tables(repo).get("oracle")

    def refused(*args) -> bool:
        try:
            record(*args)
        except common.Fail:
            return True
        return False

    with tempfile.TemporaryDirectory() as td:
        repo, out = fresh(td, "game"), pathlib.Path(td).resolve() / "outside"
        # no copy: the table, no hash file, the firewall as it was; a dry run writes nothing
        written, line = record(repo, debug, None, dry=True)
        ok &= common.read(repo / RECORD) == rec and written == ["would be changed %s" % RECORD]
        written, line = record(repo, debug, None)
        ok &= table(repo) == {"checked": common.today(), "disc_debug_files": 2, "disc_psyq_sym": 1, "byo": "none"}
        ok &= not (repo / HASHES).exists() and common.read(repo / common.FIREWALL) == fw and written == ["changed %s" % RECORD]
        ok &= line == "disc: 2 debug file(s), 1 with the PsyQ SYM magic; byo: none"
        ok &= record(repo, debug, None)[0] == []                                        # the same day: nothing to write
        print("  %s" % line)
        # a copy inside the repository, a missing one, an empty one: refused, nothing written
        common.write(repo / "notes" / "GAME.SYM", "x")
        (out / "empty").mkdir(parents=True)
        (out / "empty" / "ZERO.SYM").write_bytes(b"")
        before = common.read(repo / RECORD)
        ok &= refused(repo, None, str(repo / "notes" / "GAME.SYM")) and refused(repo, None, str(repo))
        ok &= refused(repo, None, str(out / "nope")) and refused(repo, None, str(out / "empty"))
        ok &= common.read(repo / RECORD) == before and not (repo / HASHES).exists()
        # a file: one hash, the `required:` line once; the disc facts of the earlier record stay
        sym = out / "PROTO.SYM"
        sym.write_bytes(b"MND\x01proto")
        written, line = record(repo, None, str(sym))
        want = hashlib.sha1(b"MND\x01proto").hexdigest()
        ok &= common.read(repo / HASHES) == HEAD + "%s  PROTO.SYM\n" % want
        ok &= common.firewall_lines(common.read(repo / common.FIREWALL), "required") == [HASHES]
        ok &= table(repo)["byo"] == "1 file(s) hashed" and table(repo)["disc_debug_files"] == 2
        ok &= line.endswith("byo: 1 file(s) hashed (1 new)") and str(out) not in common.read(repo / RECORD)
        ok &= record(repo, None, str(sym))[0] == []                                     # idempotent
        # a folder: one per file, merged and sorted by name; the empty file and the cache folder give none
        d = out / "build"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "B.MAP").write_bytes(b"map")
        (d / "A.CPE").write_bytes(b"cpe")
        (d / "ZERO").write_bytes(b"")
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "x.pyc").write_bytes(b"pyc")
        record(repo, None, str(d))
        names = [l.split()[1] for l in common.read(repo / HASHES).splitlines() if not l.startswith("#")]
        ok &= names == ["A.CPE", "B.MAP", "PROTO.SYM"] and table(repo)["byo"] == "3 file(s) hashed"
        ok &= common.read(repo / common.FIREWALL).count("required: %s" % HASHES) == 1
        record(repo, debug, None)                                                       # a later scan keeps the hashes
        ok &= table(repo)["byo"] == "3 file(s) hashed" and len(parse_hashes(common.read(repo / HASHES))) == 3
        # the dump's own path: no hash (the retail manifest covers the developer's own disc)
        own = fresh(td, "own")
        paths = make_disc.build(str(out / "disc"))
        record(own, debug, paths["cue"], dump=paths["cue"])
        ok &= table(own)["byo"] == "own disc" and not (own / HASHES).exists()
        record(own, debug, None)
        ok &= table(own)["byo"] == "own disc"
        # another build as a disc image: the image's files and each file of its volume
        img = fresh(td, "image")
        record(img, None, paths["cue"])
        got = parse_hashes(common.read(img / HASHES))
        ok &= got.get(hashlib.sha1(make_disc.SYM).hexdigest()) == make_disc.SYM_NAME
        ok &= got.get(identify.identify(paths["cue"])[0]["exe"]["sha1"]) == "HELLO.EXE"
        ok &= {"HOMEBREW.cue", "HOMEBREW (Track 1).bin", "HOMEBREW (Track 2).bin", "SYSTEM.CNF"} <= set(got.values())
        record(img, None, paths["cue"])                                                 # a name with spaces survives a merge
        ok &= parse_hashes(common.read(img / HASHES)) == got
        ok &= "disc_debug_files" not in table(img) and scan_line(table(img)) == "disc: not scanned"
        print("  a disc image: %d hashes (%s)" % (len(got), ", ".join(sorted(set(got.values())))))
        # the two shapes of --medium; a file that is neither
        common.write(out / "medium.json", json.dumps({"debug_artifacts": debug, "serial": "X"}))
        common.write(out / "debug.json", json.dumps(debug))
        common.write(out / "bad.json", json.dumps({"serial": "X"}))
        ok &= load_debug(out / "medium.json") == load_debug(out / "debug.json") == debug
        try:
            load_debug(out / "bad.json")
            ok = False
        except common.Fail:
            pass
        # the command line: a scan is needed once, the answer is needed always, a refusal exits 1
        cli = fresh(td, "cli")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok &= main(["record", "--repo", str(cli), "--no-copy"]) == 1
            ok &= main(["record", "--repo", str(cli), "--medium", str(out / "debug.json"), "--byo", str(cli)]) == 1
            ok &= table(cli) is None
            ok &= main(["record", "--repo", str(cli), "--dump", paths["cue"], "--no-copy"]) == 0
            ok &= table(cli) == {"checked": common.today(), "disc_debug_files": 1, "disc_psyq_sym": 1, "byo": "none"}
            ok &= main(["record", "--repo", str(cli), "--byo", str(sym)]) == 0 and table(cli)["byo"] == "1 file(s) hashed"
        ok &= "FAIL no disc scan yet" in buf.getvalue() and "NEXT commit %s %s %s" % (HASHES, common.FIREWALL, RECORD) in buf.getvalue()
        ok &= "AUDIT not run" in buf.getvalue()
    return common.self_test_banner("oracle", ok)


if __name__ == "__main__":
    sys.exit(main())
