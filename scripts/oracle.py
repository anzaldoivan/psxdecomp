#!/usr/bin/env python3
"""oracle.py — the record of the other builds of a game: the disc scan, and one checksum file per supplied build.

    oracle.py record --repo R [--dump CUE | --medium FILE] [--dry-run]
    oracle.py add    --repo R --id ID --path P [--expect SHA1]... [--class C] [--carries TEXT] [--page URL] [--dry-run]
    oracle.py list   [--repo R]
    oracle.py locate --id ID [--repo R]
    oracle.py link   --id ID --path P [--repo R]
    oracle.py measure --id ID [--path P] [--dump D] [--repo R] [--dry-run]
    oracle.py --self-test

An oracle build is another build of the game's program that carries more than the target: symbols, a link map
(docs/REFS.md, "Oracle builds"). No command here commits, and no byte of a build is written anywhere.

`record` writes the disc scan into `[oracle]` of config/psxdecomp.toml: `checked` (the day), `disc_debug_files` and
`disc_psyq_sym` (the counts). The facts come from `--dump` (read in place, as identify.py reads it) or from `--medium`:
a medium.json, or a JSON file that holds its `debug_artifacts` alone (the scan of a dump on another machine). `--dump`
also registers the dump's path in the local record.

`add` records one build under its id. An id is a slug: a build date (`proto-2001-10-30`, `pc-2003-02-07`) or a serial
(`slpm-86959`). `retail` is reserved for the dump. It writes:

- config/oracle.<id>.sha1 (sha1sum format, base names, merged with the file's lines and sorted): one SHA-1 per file
  of the copy. A file gives one, a folder one per file. A disc image (.cue, .bin, .iso, .img) also gives one per file
  of its ISO 9660 volume, because a file taken out of the image is what a commit would hold. An empty file and a file
  over the audit's 50 MiB cap give none.
- one `[[build]]` table in config/oracle.toml: `id`, `class`, `carries`, `page`, `expect` (the stated hashes),
  `checked` (the day), `files` (the lines of the checksum file), `matched` (the stated hashes that a file of the copy
  has), and `image` with `image_size`: the file with a stated hash, or the largest file. doctor looks for that file
  in a registered copy by its size, and hashes nothing.
- the line `required: config/oracle.*.sha1` in config/firewall.txt, with the first build. From then on
  tools/audit_public.py refuses a tracked copy of any of those files, under any name.
- the path, in the local record: `<git-common-dir>/psxdecomp/local.toml` (common.local_set). Git cannot track that
  file, and each worktree of the clone reads it. A second `add` of an id merges the hashes of another part of the
  build and leaves a registered path that still exists.

`--expect` gives a SHA-1 that the build's page states (docs/REFS.md, the check-out rule). It may repeat. Before any
other read, each file of the copy is hashed, of any size. A copy where no file has a stated hash is refused, and
nothing is written. A copy lies outside the repository, or inside it under a folder that config/firewall.txt purges
and git ignores (`disks/builds/<id>/` is the home). Any other path inside is refused.

`list` prints one line per build: its id, its class, the count of its files, and whether this machine has it.
`locate` prints the registered path of one build (`--id retail`: the dump), for a Makefile or a tool; exit 1 when the
build is not on this machine. `link` registers a copy on another machine: a file of the copy must have a stated hash
of the build, or (a build with none) a hash of its committed checksum file.

`measure` maps the build's executable onto the dump's (scripts/img.py, the core that games hold as
tools/psxd_img.py) and prints one line: the share of the dump's executable words that the build holds, the runs, and
the strings that the build has and the dump lacks, with the floors of the method (docs/REFS.md, "Oracle builds"). A
share is a measure, never a class. `--path` (default: the registered copy) is the executable, a disc image or a folder;
`--dump` (default: the registered dump) the same for retail. It writes `.run/bootstrap/oracle/<id>.measure.tsv` (keys
and addresses) and `<id>.strings.txt` (the text, ignored), and `measured` in the build's table when config/oracle.toml
holds the id. `--id retail` scans the dump's executable alone: the functions that load a string, the references, and
whether a text is Shift-JIS.

`build_items` reads the `build` identifiers of a scout report's table `## archive.org items`: S10 refuses to commit
a file that holds one. After `add`, tools/audit_public.py runs: exit 1 when it fails.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import struct
import sys
import tempfile
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import identify  # noqa: E402
import img  # noqa: E402

RECORD = "config/psxdecomp.toml"
BUILDS = "config/oracle.toml"
HASHES = "config/oracle.%s.sha1"
HASH_GLOB = HASHES % "*"
HOME = "disks/builds"
REQUIRED = ("# ---- psxdecomp: the files of each other build of the game that a developer supplied (`psxd oracle add`) ----\n"
            "required: %s\n" % HASH_GLOB)
HEAD = ("# %s: the SHA-1 of each file of the build `%s` that a developer supplied (psxdecomp, `psxd oracle add`).\n"
        "# tools/audit_public.py refuses a tracked file with one of these hashes. No byte of the build is here.\n")
BUILDS_HEAD = ("# %s: the other builds of this game that a developer supplied (psxdecomp, `psxd oracle add`). One [[build]]\n"
               "# table per build id, and one checksum file each (config/oracle.<id>.sha1). `expect`: the SHA-1 values that\n"
               "# the build's page states. `image`: the file that doctor looks for in a registered copy. No byte and no path\n"
               "# of a build is here: a path lies in the git directory of each clone (`psxd oracle list`).\n" % BUILDS)
BUILD_KEYS = ("id", "class", "carries", "page", "expect", "checked", "files", "matched", "image", "image_size", "measured")
CLASSES = ("region", "prototype", "review", "debug", "demo", "port", "revision", "sibling")
CAP = 50 << 20                                   # the audit refuses a tracked file over 50 MiB whatever it holds
IMAGE_EXT = (".cue", ".bin", ".iso", ".img")
COMMAND = "psxd oracle record --repo . --dump <your dump>"
ADD_COMMAND = "psxd oracle add --repo . --id <id> --path <path> --expect <sha1>"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RETAIL = "retail"                                # the id of the dump: `locate --id retail`
MEASURED = ".run/bootstrap/oracle"
FLOORS = "floor: an unrelated PsyQ game maps 22-25%, a sister game 64-65%"   # docs/REFS.md, "Oracle builds"
ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{4,}$")       # an archive.org identifier; the header row is not one


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


def copy_files(byo: pathlib.Path, probe) -> list[pathlib.Path]:
    """The files of a supplied copy on disk: the file, or each file of the folder, and the track files of a CUE sheet
    among them."""
    files = [byo] if byo.is_file() else sorted(p for p in byo.rglob("*") if p.is_file()
                                              and not set(p.relative_to(byo).parts) & common.SKIP_NAMES)
    for p in [f for f in files if f.suffix.lower() == ".cue"]:
        try:
            tracks = [pathlib.Path(x["file"]) for x in probe.parse_cue(str(p)) if x.get("file")]
        except (ValueError, OSError, KeyError, TypeError):
            continue
        files += [x for x in tracks if x.is_file()]
    seen, out = set(), []                         # a sheet may spell its track another way: one file, counted once
    for f in files:
        st = f.stat()
        if (st.st_dev, st.st_ino) not in seen:
            seen.add((st.st_dev, st.st_ino))
            out.append(f)
    return out


def stated(byo: pathlib.Path, expect) -> list[tuple[pathlib.Path, str]]:
    """(file, sha1) for each file of the copy with a SHA-1 that the build's page states. Each file is hashed, of any
    size. Raises Fail on a value that is no SHA-1, and when no file matches."""
    want = {str(e).strip().lower() for e in expect}
    bad = sorted(e for e in want if not SHA1_RE.match(e))
    if bad:
        raise common.Fail("--expect %s is not a SHA-1 (40 hex digits). Nothing was written" % bad[0])
    files = copy_files(byo, identify.load_probe("psx")[1])
    hit = [(p, s) for p, s in ((p, sha1_file(p)) for p in files) if s in want]
    if not hit:
        raise common.Fail("no file of the copy has a stated hash (%d file(s) hashed, %d hash(es) stated): this is not "
                          "the build that the page describes, or not its image. Nothing was written"
                          % (len(files), len(want)))
    return hit


def build_items(text: str) -> list[str]:
    """The identifiers of the `build` rows of a scout report's table `## archive.org items` (agents/scout-web.md)."""
    m = re.search(r"(?m)^## archive\.org items[ \t]*\n(.*?)(?=^## |\Z)", text, re.S)
    out = []
    for line in (m.group(1).splitlines() if m else ()):
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1].lower().startswith("build") and ITEM_RE.match(cells[0]) and cells[0] not in out:
            out.append(cells[0])
    return out


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


def check_id(bid: str) -> str:
    if not ID_RE.match(bid or "") or len(bid) > 40:
        raise common.Fail("--id %r is not a build id: lower-case letters, digits and single hyphens, as "
                          "`proto-2001-10-30` or `slpm-86959`. Nothing was written" % bid)
    if bid == RETAIL:
        raise common.Fail("the id `%s` is the dump's: `psxd oracle record --dump` registers it. Nothing was written" % RETAIL)
    return bid


def home_problem(path: pathlib.Path, repo: pathlib.Path) -> str | None:
    """Why a path cannot hold a build: it lies inside the repository and not under a folder that the firewall purges
    and git ignores. None for a path outside the repository and for one under such a folder."""
    if not inside(path, repo):
        return None
    rel = path.relative_to(repo).as_posix()
    fw = repo / common.FIREWALL
    purged = [p for p in (common.firewall_lines(common.read(fw), "purge") if fw.is_file() else ())
              if rel.startswith(p.rstrip("/") + "/")]
    if not purged:
        return ("it lies inside the repository and under no folder that %s purges: keep it in %s/<id>/ or outside the "
                "repository" % (common.FIREWALL, HOME))
    if common.git(repo, "check-ignore", "-q", "--", rel, check=False).returncode != 0:
        return "it lies under %s, which %s purges and git does not ignore: add the folder to .gitignore" % (
            purged[0], common.FIREWALL)
    return None


def builds(repo) -> list[dict]:
    """The [[build]] tables of config/oracle.toml, by id; [] without the file."""
    p = pathlib.Path(repo) / BUILDS
    if not p.is_file():
        return []
    try:
        rows = tomllib.loads(common.read(p)).get("build") or []
    except tomllib.TOMLDecodeError as e:
        raise common.Fail("%s is not TOML (%s): `psxd oracle add` writes this file" % (BUILDS, e))
    if not isinstance(rows, list) or any(not isinstance(b, dict) or not isinstance(b.get("id"), str) for b in rows):
        raise common.Fail("%s: each build is a [[build]] table with an `id`" % BUILDS)
    return sorted(rows, key=lambda b: b["id"])


def builds_text(rows: list[dict]) -> str:
    def value(v):
        if isinstance(v, list):
            return "[%s]" % ", ".join(json.dumps(x) for x in v)
        return str(v) if isinstance(v, int) else json.dumps(v, ensure_ascii=False)

    out = BUILDS_HEAD + "".join("\n[[build]]\n" + "".join(
        "%s = %s\n" % (k, value(b[k])) for k in BUILD_KEYS if k in b) for b in sorted(rows, key=lambda b: b["id"]))
    if tomllib.loads(out).get("build", []) != sorted(rows, key=lambda b: b["id"]):
        raise common.Fail("%s: psxdecomp cannot write a value of a build as TOML. Nothing was written" % BUILDS)
    return out


def registered(repo) -> dict[str, str]:
    """{id: path} of the local record: each build, and `retail` for the dump."""
    local = common.local_read(repo)
    out = {k: str(v) for k, v in (local.get("builds") or {}).items()}
    if (local.get("dump") or {}).get("path"):
        out[RETAIL] = str(local["dump"]["path"])
    return out


def image_state(path: pathlib.Path, build: dict) -> str | None:
    """What a registered copy lacks of the build's `image`, by name and size only: no file is hashed."""
    name, size = build.get("image"), build.get("image_size")
    if not name:
        return None
    if path.is_file():                            # the file itself, or (a sheet is registered) the track beside it
        found = [path] if path.name == name or not (path.parent / name).is_file() else [path.parent / name]
    else:
        found = [p for p in path.rglob(name) if p.is_file()]
    if not found:
        return "holds no file `%s`" % name
    if all(p.stat().st_size != size for p in found):
        return "its `%s` has %d bytes, and the record says %s" % (name, found[0].stat().st_size, size)
    return None


def status(repo) -> list[dict]:
    """One row per build of config/oracle.toml: id, class, files, `path` (the registered one, or None), `here` (it
    exists), `problem` (a path that the firewall refuses), `note` (the copy's image by name and size)."""
    repo = pathlib.Path(repo).resolve()
    paths, out = registered(repo), []
    for b in builds(repo):
        path = pathlib.Path(paths[b["id"]]).expanduser() if b["id"] in paths else None
        here = bool(path and path.exists())
        out.append({"id": b["id"], "class": b.get("class", "unstated"), "files": b.get("files", 0), "path": path,
                    "here": here, "problem": home_problem(path.resolve(), repo) if path else None,
                    "note": image_state(path, b) if here else None})
    return out


def uncovered(repo) -> list[str]:
    """The checksum files of the repository that no `required:` line of the firewall reads."""
    repo = pathlib.Path(repo)
    fw = repo / common.FIREWALL
    lines = common.firewall_lines(common.read(fw), "required") if fw.is_file() else []
    held = sorted(p.relative_to(repo).as_posix() for p in (repo / "config").glob("oracle*.sha1"))
    return [h for h in held if not any(h == l or fnmatch.fnmatchcase(h, l) for l in lines)]


def _target(repo) -> pathlib.Path:
    repo = pathlib.Path(repo).resolve()
    if not (repo / RECORD).is_file() or not (repo / common.FIREWALL).is_file():
        raise common.Fail("%s has no %s or no %s: bootstrap or adopt the repository first (/psxdecomp:upgrade)"
                          % (repo, RECORD, common.FIREWALL))
    return repo


def _copy(repo: pathlib.Path, path) -> pathlib.Path:
    path = pathlib.Path(os.path.expanduser(str(path))).resolve()
    why = home_problem(path, repo)
    if why:
        raise common.Fail("the copy is refused (firewall): %s. Nothing was written" % why)
    if not path.exists():
        raise common.Fail("%s does not exist. Nothing was written" % path)
    return path


def record(repo, debug: dict | None, dump: str | None = None, dry: bool = False) -> tuple[list[str], str]:
    """Write the disc scan into `[oracle]` of the record, and register the dump's path. Returns (one `created|changed
    <path>` line per file, the summary line)."""
    import upgrade
    repo = _target(repo)
    text = common.read(repo / RECORD)
    text = upgrade.record_set(text, "oracle", "checked", common.today())
    if debug is not None:
        text = upgrade.record_set(text, "oracle", "disc_debug_files", int(debug["count"]))
        text = upgrade.record_set(text, "oracle", "disc_psyq_sym", int(debug["psyq_sym"]))
    st = common.write(repo / RECORD, text, dry=dry)
    if dump and not dry and common.local_path(repo):
        common.local_set(repo, "dump", "path", os.path.abspath(os.path.expanduser(dump)))
    return (["%s%s %s" % ("would be " if dry else "", st, RECORD)] if st != "unchanged" else [],
            "%s; %d build(s)" % (scan_line(common.load_toml_str(text)["oracle"]), len(builds(repo))))


def add(repo, bid: str, path, expect=(), cls: str | None = None, carries: str | None = None, page: str | None = None,
        dry: bool = False) -> tuple[list[str], str]:
    """Record one build under its id (module docstring). Returns (one `created|changed <path>` line per file, the
    summary line). Every refusal comes before the first write. `expect`: the SHA-1 values that the build's page
    states."""
    repo = _target(repo)
    check_id(bid)
    if cls is not None and cls not in CLASSES:
        raise common.Fail("--class %s is not one of %s. Nothing was written" % (cls, ", ".join(CLASSES)))
    path = _copy(repo, path)
    paths = registered(repo)
    if paths.get(RETAIL) and path == pathlib.Path(paths[RETAIL]).expanduser().resolve():
        raise common.Fail("%s is the dump: the retail manifest covers your own disc, and a build's record is for "
                          "another build. Nothing was written" % path)
    rows = builds(repo)
    have = next((b for b in rows if b["id"] == bid), None)
    hit = stated(path, expect) if expect else []   # first: is this the build that the page describes?
    fresh = copy_hashes(path)
    if not fresh:
        raise common.Fail("%s holds no file to hash (empty, or over %d MiB each). Nothing was written" % (path, CAP >> 20))
    rel = HASHES % bid
    old = parse_hashes(common.read(repo / rel)) if (repo / rel).is_file() else {}
    merged = dict(old)
    for sha, name in fresh:
        merged.setdefault(sha, name)
    was = dict(have or {})
    new = dict(was, id=bid)
    for key, val in (("class", cls), ("carries", carries), ("page", page)):
        if val:
            new[key] = val
    new.setdefault("class", "unstated")
    new["expect"] = sorted({str(e).strip().lower() for e in expect} | set(was.get("expect", [])))
    new["matched"] = sorted({s for _, s in hit} | set(was.get("matched", [])))
    new["files"] = len(merged)
    if "image" not in new:                        # the file with a stated hash, else the largest: doctor's size check
        big = hit[0][0] if hit else max(copy_files(path, identify.load_probe("psx")[1]), key=lambda p: p.stat().st_size)
        new["image"], new["image_size"] = big.name, big.stat().st_size
    body = lambda b: {k: v for k, v in b.items() if k != "checked"}  # noqa: E731
    new["checked"] = was["checked"] if "checked" in was and body(new) == body(was) else common.today()
    written = []

    def w(file, body):
        st = common.write(repo / file, body, dry=dry)
        if st != "unchanged":
            written.append("%s%s %s" % ("would be " if dry else "", st, file))

    if merged != old:
        w(rel, HEAD % (rel, bid) + "".join("%s  %s\n" % (s, n) for s, n in sorted(merged.items(), key=lambda x: (x[1], x[0]))))
    fw = common.read(repo / common.FIREWALL)
    if HASH_GLOB not in common.firewall_lines(fw, "required"):
        w(common.FIREWALL, fw.rstrip("\n") + "\n\n" + REQUIRED)
    w(BUILDS, builds_text([b for b in rows if b["id"] != bid] + [new]))
    kept = paths.get(bid)
    if kept and pathlib.Path(kept).expanduser().resolve() != path and pathlib.Path(kept).expanduser().exists():
        where = "the registered path stays %s (`psxd oracle link` changes it)" % kept
    elif dry or common.local_path(repo) is None:
        where = "path not registered (%s)" % ("a dry run" if dry else "no git directory")
    else:
        common.local_set(repo, "builds", bid, str(path))
        where = "path registered for this clone"
    return written, "%s: %d file(s) hashed (%d new), %s; %s" % (
        bid, len(merged), len(merged) - len(old),
        "%d of %d stated hash(es) matched" % (len(new["matched"]), len(new["expect"])) if new["expect"] else "no stated hash",
        where)


def link(repo, bid: str, path) -> str:
    """Register a copy of a recorded build for this clone. A file of the copy must have a stated hash of the build,
    or, for a build with none, a hash of its checksum file. Returns the summary line."""
    repo = _target(repo)
    build = next((b for b in builds(repo) if b["id"] == bid), None)
    if build is None:
        raise common.Fail("%s holds no build `%s` (`psxd oracle list`): `psxd oracle add` records a new one" % (BUILDS, bid))
    path = _copy(repo, path)
    if build.get("expect"):
        n = len(stated(path, build["expect"]))
        how = "%d file(s) with a stated hash" % n
    else:
        held = parse_hashes(common.read(repo / (HASHES % bid))) if (repo / (HASHES % bid)).is_file() else {}
        n = sum(sha in held for sha, _ in copy_hashes(path))
        if not n:
            raise common.Fail("no file of the copy has a hash of %s: this is not the build `%s`. Nothing was written"
                              % (HASHES % bid, bid))
        how = "%d file(s) of %s" % (n, HASHES % bid)
    common.local_set(repo, "builds", bid, str(path))
    return "%s: %s; path registered for this clone" % (bid, how)


def image_exe(path: pathlib.Path, probe) -> bytes:
    """The boot executable of a disc image (its SYSTEM.CNF), read as S2 reads it."""
    try:
        cue = path.suffix.lower() == ".cue"
        tracks = probe.parse_cue(str(path)) if cue else [{"number": 1, "mode": "", "file": str(path), "index01": 0}]
        trk = probe.DataTrack(tracks[0]["file"], tracks[0]["mode"], probe.toc(tracks)[0]["start"] if cue else 0)
    except (ValueError, OSError, KeyError, IndexError, TypeError) as e:
        raise common.Fail("%s: no data track (%s)" % (path, e))
    try:
        files = probe.iso_files(trk)[0]
        cnf = probe.find_file(files, "SYSTEM.CNF")
        boot = cnf and probe.find_file(files, probe.parse_system_cnf(
            trk.extent(cnf["lba"], cnf["size"]).decode("ascii", "replace"))["boot_file"])
        if not boot:
            raise common.Fail("%s: no SYSTEM.CNF, or its boot file is not on the disc" % path)
        return trk.extent(boot["lba"], boot["size"])
    except (ValueError, OSError, struct.error, IndexError) as e:
        raise common.Fail("%s: no ISO 9660 volume (%s)" % (path, e))
    finally:
        trk.close()


def head(path: pathlib.Path) -> bytes:
    with open(path, "rb") as f:
        return f.read(8)


def boot_exe(path: pathlib.Path, probe) -> bytes:
    """The PS-X EXE of a copy: the file itself, the boot file of a disc image, or in a folder the boot file of its
    SYSTEM.CNF, else of its disc image, else its one executable."""
    if not path.exists():
        raise common.Fail("%s does not exist" % path)
    if path.is_file():
        if head(path) == probe.EXE_MAGIC:
            return path.read_bytes()
        if path.suffix.lower() in IMAGE_EXT:
            return image_exe(path, probe)
        raise common.Fail("%s is no PS-X EXE and no disc image" % path)
    files = copy_files(path, probe)
    for cnf in sorted((p for p in files if p.name.upper() == "SYSTEM.CNF"), key=lambda p: len(p.parts)):
        boot = probe.parse_system_cnf(common.read(cnf))["boot_file"].upper()
        hit = [p for p in files if p.is_relative_to(cnf.parent) and p.relative_to(cnf.parent).as_posix().upper() == boot]
        if boot and hit:
            return hit[0].read_bytes()
    for p in sorted((p for p in files if p.suffix.lower() in IMAGE_EXT), key=lambda p: p.suffix.lower() != ".cue"):
        try:                                      # a .BIN is often game data, not a disc image
            return image_exe(p, probe)
        except common.Fail:
            continue
    exes = [p for p in files if head(p) == probe.EXE_MAGIC]
    if len(exes) != 1:
        raise common.Fail("%s holds %d PS-X EXE files and no SYSTEM.CNF: give the executable's path" % (path, len(exes)))
    return exes[0].read_bytes()


def exe_of(path, probe) -> bytes:
    exe = boot_exe(pathlib.Path(os.path.expanduser(str(path))).resolve(), probe)
    if not exe.startswith(probe.EXE_MAGIC) or len(exe) < 0x800:
        raise common.Fail("%s: the boot file is no PS-X EXE" % path)
    return exe


def measure(repo, bid: str, path=None, dump=None, dry: bool = False) -> tuple[list[str], str]:
    """Map a build's executable onto the dump's (module docstring). Returns (one `created|changed <path>` line for
    config/oracle.toml, the summary line)."""
    repo = pathlib.Path(repo).resolve()
    probe = identify.load_probe("psx")[1]
    paths = registered(repo)
    dump = dump or paths.get(RETAIL)
    if not dump:
        raise common.Fail("no dump: give --dump <your dump> (or register it: `%s`)" % COMMAND)
    retail = exe_of(dump, probe)
    written = []
    if bid == RETAIL:
        rows, text = img.exe_scan(retail)
        body = ("# %s/retail.measure.tsv -- psxd oracle measure --id retail: keys and addresses, no text\n# %s\n"
                % (MEASURED, img.COLUMNS["strnames"]) + "".join("\t".join(r) + "\n" for r in rows))
        line = "measure retail: %s; Shift-JIS %s" % (img.name_counts(rows).split(", retail")[0],
                                                     "yes" if any(r[6] == "sjis" for r in rows) else "no")
    else:
        check_id(bid)
        path = path or paths.get(bid)
        if not path:
            raise common.Fail("`%s` has no registered copy: give --path <the build's copy>" % bid)
        build = exe_of(path, probe)
        mrows, srows, text, (m, n, runs, s, c) = img.exe_measure(retail, build)
        body = ("# %s/%s.measure.tsv -- psxd oracle measure --id %s: keys and addresses, no text\n"
                "# map: %s | string: %s\n" % (MEASURED, bid, bid, img.COLUMNS["map"], img.COLUMNS["strings"])
                + "".join("map\t%s\n" % "\t".join(r) for r in mrows) + "".join("string\t%s\n" % "\t".join(r) for r in srows))
        share = "exe %.1f%%" % (100 * m / n if n else 0)
        line = "measure %s: exe %d of %d words in %d runs (%s); build-only strings %d (%d with a reference); %s" % (
            bid, m, n, runs, share[4:], s, c, FLOORS)
        rows = builds(repo)
        b = next((x for x in rows if x["id"] == bid), None)
        if b is not None and b.get("measured") != share:
            st = common.write(repo / BUILDS, builds_text([x for x in rows if x["id"] != bid] + [dict(b, measured=share)]),
                              dry=dry)
            written.append("%s%s %s" % ("would be " if dry else "", st, BUILDS))
    if not dry:
        common.write(repo / MEASURED / ("%s.measure.tsv" % bid), body)
        common.write(repo / MEASURED / ("%s.strings.txt" % bid), "".join(text))
    return written, line


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
    ap.add_argument("cmd", nargs="?", choices=["record", "add", "list", "locate", "link", "measure"])
    ap.add_argument("--repo", default=".")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--dump")
    src.add_argument("--medium")
    ap.add_argument("--id")
    ap.add_argument("--path")
    ap.add_argument("--expect", action="append", default=[], metavar="SHA1",
                    help="a SHA-1 that the build's page states (repeatable): the copy must hold a file with one")
    ap.add_argument("--class", dest="cls", choices=CLASSES)
    ap.add_argument("--carries", help="what the build's page says it carries: `symbols`, `a debug menu, no symbols`")
    ap.add_argument("--page", help="the page that describes the build (never a download link)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.cmd:
        ap.error("the command is one of record, add, list, locate, link, measure")
    if a.cmd in ("add", "link", "locate", "measure") and not a.id:
        ap.error("`%s` needs --id" % a.cmd)
    if a.cmd in ("add", "link") and not a.path:
        ap.error("`%s` needs --path" % a.cmd)
    repo = pathlib.Path(a.repo).resolve()
    try:
        if a.cmd == "list":
            paths = registered(repo)
            if RETAIL in paths:
                print("%-20s %-10s %-12s %s" % (RETAIL, "the dump", "-", "here" if os.path.exists(os.path.expanduser(paths[RETAIL])) else "registered, and the path is gone"))
            rows = status(repo)
            for r in rows:
                print("%-20s %-10s %-12s %s" % (r["id"], r["class"], "%d file(s)" % r["files"],
                                                "refused: %s" % r["problem"] if r["problem"] else
                                                "here" + ("; %s" % r["note"] if r["note"] else "") if r["here"] else
                                                "registered, and the path is gone" if r["path"] else "not on this machine"))
            print("ORACLE %d build(s), %d on this machine" % (len(rows), sum(r["here"] for r in rows)))
            return 0
        if a.cmd == "locate":
            got = registered(repo).get(a.id)
            if not got or not os.path.exists(os.path.expanduser(got)):
                print("oracle: `%s` is not on this machine%s (`%s`)" % (
                    a.id, ": %s is gone" % got if got else "", "psxd oracle record --dump <your dump>" if a.id == RETAIL
                    else "psxd oracle link --id %s --path <path>" % a.id), file=sys.stderr)
                return 1
            print(got)
            return 0
        if a.cmd == "link":
            print("ORACLE %s" % link(repo, a.id, a.path))
            return 0
        if a.cmd == "measure":
            written, line = measure(repo, a.id, a.path, a.dump, a.dry_run)
            print("ORACLE %s" % line)
            for x in written:
                print("  %s" % x)
            if written and not a.dry_run:
                print("NEXT commit %s" % BUILDS)
            return 0
        if a.cmd == "add":
            written, line = add(repo, a.id, a.path, a.expect, a.cls, a.carries, a.page, a.dry_run)
        else:
            debug = None
            if a.dump:
                dump = os.path.abspath(os.path.expanduser(a.dump))
                if home_problem(pathlib.Path(dump).resolve(), repo):
                    raise common.Fail("the dump lies inside the repository, outside a folder that the firewall purges "
                                      "and git ignores: keep it in disks/ or outside")
                debug = identify.identify(dump)[0]["debug_artifacts"]
            elif a.medium:
                debug = load_debug(a.medium)
            else:
                raise common.Fail("`record` writes a disc scan: give --dump <your dump>, or --medium <a medium.json>")
            written, line = record(repo, debug, a.dump, a.dry_run)
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
    fw = "purge: disks/\npurge: scratch/\nfixture:  config/firewall-fixture.sha1\n"
    rec = '[psxdecomp]\nversion = "0.0.0"\n\n[deviations]\nlist = []\n'
    debug = {"count": 2, "psyq_sym": 1, "files": [], "note": ""}

    def fresh(td, name, git=True):
        repo = pathlib.Path(td).resolve() / name
        common.write(repo / RECORD, rec)
        common.write(repo / common.FIREWALL, fw)
        common.write(repo / ".gitignore", "/disks/\n")
        if git:
            common.git(repo, "init", "-q")
        return repo

    def table(repo):
        return upgrade.record_tables(repo).get("oracle")

    def build(repo, bid):
        return next((b for b in builds(repo) if b["id"] == bid), None)

    def hashes(repo, bid):
        return parse_hashes(common.read(repo / (HASHES % bid)))

    def refused(fn, *args, **kw) -> bool:
        try:
            fn(*args, **kw)
        except common.Fail:
            return True
        return False

    with tempfile.TemporaryDirectory() as td:
        repo, out = fresh(td, "game"), pathlib.Path(td).resolve() / "outside"
        # the disc scan: the table, no build, the firewall as it was; a dry run writes nothing
        written, line = record(repo, debug, dry=True)
        ok &= common.read(repo / RECORD) == rec and written == ["would be changed %s" % RECORD]
        written, line = record(repo, debug)
        ok &= table(repo) == {"checked": common.today(), "disc_debug_files": 2, "disc_psyq_sym": 1}
        ok &= not (repo / BUILDS).exists() and common.read(repo / common.FIREWALL) == fw and written == ["changed %s" % RECORD]
        ok &= line == "disc: 2 debug file(s), 1 with the PsyQ SYM magic; 0 build(s)"
        ok &= record(repo, debug)[0] == [] and registered(repo) == {}                   # the same day: nothing to write
        print("  %s" % line)
        # an id that is none, the dump's id, a class that is none: refused
        sym = out / "PROTO.SYM"
        sym.parent.mkdir(parents=True)
        sym.write_bytes(b"MND\x01proto")
        ok &= all(refused(add, repo, bad, str(sym)) for bad in ("", "Proto", "a--b", "-a", "a_b", "x" * 41, RETAIL, "a/b", "a.*"))
        ok &= refused(add, repo, "proto-a", str(sym), cls="leak")
        # a copy inside the repository: refused, but for a folder that the firewall purges and git ignores
        common.write(repo / "notes" / "GAME.SYM", "x")
        common.write(repo / "scratch" / "GAME.SYM", "x")                                # purged, and git does not ignore it
        (out / "empty").mkdir(parents=True)
        (out / "empty" / "ZERO.SYM").write_bytes(b"")
        ok &= refused(add, repo, "proto-a", str(repo / "notes" / "GAME.SYM")) and refused(add, repo, "proto-a", str(repo))
        ok &= refused(add, repo, "proto-a", str(repo / "scratch" / "GAME.SYM")) and refused(add, repo, "proto-a", str(repo / "disks"))
        ok &= "does not ignore" in home_problem(repo / "scratch" / "GAME.SYM", repo)
        ok &= refused(add, repo, "proto-a", str(out / "nope")) and refused(add, repo, "proto-a", str(out / "empty"))
        ok &= not (repo / BUILDS).exists() and not list((repo / "config").glob("oracle*")) and registered(repo) == {}
        home = repo / HOME / "proto-a"
        home.mkdir(parents=True)
        (home / "PROTO.SYM").write_bytes(b"MND\x01proto")
        want = hashlib.sha1(b"MND\x01proto").hexdigest()
        written, line = add(repo, "proto-a", str(home), cls="prototype", carries="symbols", page="https://example.org/proto-a")
        ok &= common.read(repo / (HASHES % "proto-a")) == HEAD % (HASHES % "proto-a", "proto-a") + "%s  PROTO.SYM\n" % want
        ok &= common.firewall_lines(common.read(repo / common.FIREWALL), "required") == [HASH_GLOB]
        ok &= build(repo, "proto-a") == {"id": "proto-a", "class": "prototype", "carries": "symbols",
                                         "page": "https://example.org/proto-a", "expect": [], "checked": common.today(),
                                         "files": 1, "matched": [], "image": "PROTO.SYM", "image_size": 9}
        ok &= written == ["created %s" % (HASHES % "proto-a"), "changed %s" % common.FIREWALL, "created %s" % BUILDS]
        ok &= line == "proto-a: 1 file(s) hashed (1 new), no stated hash; path registered for this clone"
        ok &= registered(repo) == {"proto-a": str(home)} and table(repo)["disc_debug_files"] == 2
        ok &= str(out) not in common.read(repo / BUILDS) and str(repo) not in common.read(repo / BUILDS)
        ok &= add(repo, "proto-a", str(home))[0] == [] and uncovered(repo) == []        # idempotent; the class stays
        ok &= build(repo, "proto-a")["class"] == "prototype"
        ok &= common.git(repo, "status", "--porcelain", "--", "disks").stdout == ""      # git sees no file of the home
        print("  %s" % line)
        # a second build, outside: its own file and its own table; the first build's stay as they were
        d = out / "build"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "B.MAP").write_bytes(b"map")
        (d / "A.CPE").write_bytes(b"cpe!")
        (d / "ZERO").write_bytes(b"")
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "x.pyc").write_bytes(b"pyc")
        first = common.read(repo / (HASHES % "proto-a"))
        add(repo, "slpm-86959", str(d), cls="region")
        ok &= [l.split()[1] for l in common.read(repo / (HASHES % "slpm-86959")).splitlines() if not l.startswith("#")] == ["A.CPE", "B.MAP"]
        ok &= common.read(repo / (HASHES % "proto-a")) == first and [b["id"] for b in builds(repo)] == ["proto-a", "slpm-86959"]
        ok &= build(repo, "slpm-86959")["image"] == "A.CPE" and build(repo, "slpm-86959")["image_size"] == 4
        ok &= common.read(repo / common.FIREWALL).count("required: %s" % HASH_GLOB) == 1
        ok &= registered(repo) == {"proto-a": str(home), "slpm-86959": str(d)}
        # another part of a build under the same id: the hashes merge, the image and the registered path stay
        written, line = add(repo, "slpm-86959", str(sym))
        ok &= set(hashes(repo, "slpm-86959").values()) == {"A.CPE", "B.MAP", "PROTO.SYM"} and build(repo, "slpm-86959")["files"] == 3
        ok &= build(repo, "slpm-86959")["image"] == "A.CPE" and registered(repo)["slpm-86959"] == str(d)
        ok &= "the registered path stays %s" % d in line
        record(repo, debug)                                                             # a later scan keeps the builds
        ok &= len(builds(repo)) == 2 and len(hashes(repo, "slpm-86959")) == 3
        # the state of each build on this machine: here, its image by size, a path that is gone, none
        ok &= [(r["id"], r["here"], r["problem"], r["note"]) for r in status(repo)] == [("proto-a", True, None, None), ("slpm-86959", True, None, None)]
        (d / "A.CPE").write_bytes(b"cpe!!")
        ok &= "5 bytes" in status(repo)[1]["note"]
        (d / "A.CPE").unlink()
        ok &= status(repo)[1]["note"] == "holds no file `A.CPE`"
        common.local_set(repo, "builds", "slpm-86959", str(out / "gone"))
        ok &= [r["here"] for r in status(repo)] == [True, False] and status(repo)[1]["path"] == out / "gone"
        common.local_set(repo, "builds", "slpm-86959", str(repo / "notes"))
        ok &= "under no folder" in status(repo)[1]["problem"]
        common.local_set(repo, "builds", "slpm-86959", None)
        ok &= status(repo)[1]["path"] is None and registered(repo) == {"proto-a": str(home)}
        # a checksum file that no `required:` line reads
        common.write(repo / "config" / "oracle.sha1", "%s  OLD.SYM\n" % want)
        ok &= uncovered(repo) == ["config/oracle.sha1"]
        (repo / "config" / "oracle.sha1").unlink()
        # a second worktree of the clone reads the same local record
        common.git(repo, "add", "-A")
        common.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "builds")
        wt = pathlib.Path(td).resolve() / "worktree"
        common.git(repo, "worktree", "add", "-q", str(wt), "-b", "other")
        ok &= registered(wt) == {"proto-a": str(home)} and status(wt)[0]["here"] and status(wt)[0]["problem"] is None
        ok &= common.local_path(wt) == common.local_path(repo) == repo / ".git" / common.LOCAL_REL
        ok &= common.git(repo, "status", "--porcelain").stdout == ""                    # and git tracks no path of a build
        # link: a copy on another machine is checked against the committed file; a wrong copy is refused
        other = out / "elsewhere" / "RENAMED.SYM"
        other.parent.mkdir()
        other.write_bytes(b"MND\x01proto")
        ok &= refused(link, wt, "proto-a", str(d / "sub" / "B.MAP")) and refused(link, wt, "nope", str(other))
        ok &= refused(link, wt, "proto-a", str(wt / "notes" / "GAME.SYM")) and registered(repo) == {"proto-a": str(home)}
        ok &= link(wt, "proto-a", str(other)).startswith("proto-a: 1 file(s) of ") and registered(repo) == {"proto-a": str(other)}
        # a folder that is no git repository: the record is written, the path is not registered
        bare = fresh(td, "bare", git=False)
        written, line = add(bare, "proto-a", str(sym))
        ok &= line.endswith("path not registered (no git directory)") and build(bare, "proto-a")["files"] == 1
        # the dump: `record --dump` registers it, `add` refuses it (the retail manifest covers the developer's own disc)
        own = fresh(td, "own")
        paths = make_disc.build(str(out / "disc"))
        record(own, debug, paths["cue"])
        ok &= registered(own) == {RETAIL: paths["cue"]} and refused(add, own, "proto-a", paths["cue"])
        ok &= not (own / BUILDS).exists()
        # another build as a disc image: the image's files and each file of its volume
        disc = fresh(td, "image")
        add(disc, "demo-1999-01-01", paths["cue"], cls="demo")
        got = hashes(disc, "demo-1999-01-01")
        ok &= got.get(hashlib.sha1(make_disc.SYM).hexdigest()) == make_disc.SYM_NAME
        ok &= got.get(identify.identify(paths["cue"])[0]["exe"]["sha1"]) == "HELLO.EXE"
        ok &= {"HOMEBREW.cue", "HOMEBREW (Track 1).bin", "HOMEBREW (Track 2).bin", "SYSTEM.CNF"} <= set(got.values())
        ok &= add(disc, "demo-1999-01-01", paths["cue"])[0] == [] and hashes(disc, "demo-1999-01-01") == got   # a name with spaces survives a merge
        ok &= table(disc) is None
        print("  a disc image: %d hashes (%s)" % (len(got), ", ".join(sorted(set(got.values())))))
        # --expect: a stated hash matches a file of the copy, or the copy is refused before any write
        chk, proto2 = fresh(td, "check"), out / "REVIEW.SYM"
        proto2.write_bytes(b"MND\x01review")
        good, wrong = hashlib.sha1(b"MND\x01review").hexdigest(), "0" * 40
        ok &= refused(add, chk, "review-a", str(proto2), [wrong]) and refused(add, chk, "review-a", str(proto2), ["xyz"])
        ok &= not (chk / BUILDS).exists() and not list((chk / "config").glob("oracle*")) and registered(chk) == {}
        ok &= common.read(chk / common.FIREWALL) == fw
        written, line = add(chk, "review-a", str(proto2), [wrong, good.upper()], cls="review")
        ok &= build(chk, "review-a")["expect"] == [wrong, good] and build(chk, "review-a")["matched"] == [good]
        ok &= ", 1 of 2 stated hash(es) matched; " in line and build(chk, "review-a")["image"] == "REVIEW.SYM"
        ok &= refused(link, chk, "review-a", str(sym)) and link(chk, "review-a", str(proto2)).startswith("review-a: 1 file(s) with a stated hash")
        # a file over the cap is hashed for the check and gives no line: the page states the hash of a whole image
        big, cap = fresh(td, "big"), globals()["CAP"]
        track = pathlib.Path(paths["cue"]).parent / "HOMEBREW (Track 1).bin"
        globals()["CAP"] = 1024
        try:
            ok &= track.stat().st_size > CAP and refused(add, big, "proto-b", paths["cue"], [wrong])
            add(big, "proto-b", paths["cue"], [sha1_file(track)])                       # the sheet alone: its track counts
            names = set(hashes(big, "proto-b").values())
            ok &= build(big, "proto-b")["matched"] == [sha1_file(track)] and "SYSTEM.CNF" in names and track.name not in names
            ok &= build(big, "proto-b")["image"] == track.name and build(big, "proto-b")["image_size"] == track.stat().st_size
            ok &= status(big)[0]["note"] is None                                        # the sheet is registered: its track lies beside it
        finally:
            globals()["CAP"] = cap
        print("  --expect over the cap: %s" % ", ".join(sorted(names)))
        # a folder whose sheet names its track by another spelling of the path: the track is one file, one match
        disc = pathlib.Path(paths["cue"]).parent
        sheet = common.read(paths["cue"])
        common.write(paths["cue"], sheet.replace('FILE "HOMEBREW (Track 1).bin"', 'FILE "../%s/HOMEBREW (Track 1).bin"' % disc.name))
        try:
            ok &= len(stated(disc, [sha1_file(track)])) == 1 and len(copy_files(disc, identify.load_probe("psx")[1])) == 4
        finally:
            common.write(paths["cue"], sheet)
        # measure: a second build against the dump; its share goes into the build's table, its text into no table
        meas, proto = fresh(td, "measure"), pathlib.Path(make_disc.build_proto(str(out / "proto")))
        ok &= refused(measure, meas, "proto-1999-01-01", proto) and refused(measure, meas, "Bad", proto, paths["cue"])
        written, line = measure(meas, "proto-1999-01-01", proto.parent, paths["cue"])       # no record: the lines only
        ok &= written == [] and line.startswith("measure proto-1999-01-01: exe 512 of 512 words in 1 runs (100.0%); "
                                                "build-only strings 1 (1 with a reference); floor: ")
        add(meas, "proto-1999-01-01", str(proto.parent), cls="prototype")
        ok &= measure(meas, "proto-1999-01-01", dump=paths["cue"], dry=True)[0] == ["would be changed %s" % BUILDS]
        ok &= "measured" not in build(meas, "proto-1999-01-01")
        written, _ = measure(meas, "proto-1999-01-01", dump=paths["cue"])
        ok &= written == ["changed %s" % BUILDS] and build(meas, "proto-1999-01-01")["measured"] == "exe 100.0%"
        ok &= build(meas, "proto-1999-01-01")["class"] == "prototype"                    # a share is never a class
        ok &= measure(meas, "proto-1999-01-01", dump=paths["cue"])[0] == []
        held = {p.name: common.read(p) for p in (meas / MEASURED).iterdir()}
        ok &= sorted(held) == ["proto-1999-01-01.measure.tsv", "proto-1999-01-01.strings.txt"]
        ok &= "proto build" in held["proto-1999-01-01.strings.txt"] and "proto build" not in held["proto-1999-01-01.measure.tsv"]
        first = make_disc.exe_image()
        ws = img.words(first[2048:])
        back = first[:2048] + struct.pack("<%dI" % len(ws), *ws[::-1])                  # the negative control
        ok &= img.exe_measure(back, proto.read_bytes())[3][0] <= 16
        ok &= measure(meas, RETAIL, dump=paths["cue"])[1] == "measure retail: 0 functions, 0 references (direct 0, table 0); Shift-JIS no"
        print("  %s" % line.split("; floor")[0])
        # the identifiers of a report's table: the build rows only, with or without code marks
        report = ("# builds\n## Leads\n| a | b |\n## archive.org items\n"
                  "| identifier | kind (build or document) | confirmed by | file | SHA-1 |\n|---|---|---|---|---|\n"
                  "| `ExampleQuestJan011999prototype` | build | the page's hash | 00preview.jpg | %s |\n"
                  "| example-quest-manual | document | the page's link | manual.pdf | %s |\n"
                  "| ExampleQuestJan011999prototype | build | the page's link | x.7z | %s |\n"
                  "## Dead ends\n| other-item-name | build | x | y | z |\n" % (good, good, good))
        ok &= build_items(report) == ["ExampleQuestJan011999prototype"] and build_items("# builds\n## Leads\n") == []
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
        # the command line: `record` needs a scan, a refusal exits 1, `locate` prints the path alone
        cli = fresh(td, "cli")
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            ok &= main(["record", "--repo", str(cli)]) == 1 and table(cli) is None
            ok &= main(["record", "--repo", str(cli), "--dump", str(cli / "notes" / "x.cue")]) == 1
            ok &= main(["record", "--repo", str(cli), "--dump", paths["cue"]]) == 0
            ok &= table(cli) == {"checked": common.today(), "disc_debug_files": 1, "disc_psyq_sym": 1}
            ok &= main(["record", "--repo", str(cli)]) == 1                             # a scan exists: still no source
            ok &= main(["add", "--repo", str(cli), "--id", "proto-a", "--path", str(sym), "--expect", "0" * 40]) == 1
            ok &= builds(cli) == [] and main(["locate", "--repo", str(cli), "--id", "proto-a"]) == 1
            ok &= main(["locate", "--repo", str(fresh(td, "nodump")), "--id", RETAIL]) == 1
            ok &= main(["add", "--repo", str(cli), "--id", "proto-a", "--path", str(sym), "--expect", want, "--class", "prototype"]) == 0
            ok &= build(cli, "proto-a")["matched"] == [want] and main(["list", "--repo", str(cli)]) == 0
        ok &= "FAIL `record` writes a disc scan" in buf.getvalue() and "FAIL the dump lies inside the repository" in buf.getvalue()
        ok &= "NEXT commit %s %s %s" % (HASHES % "proto-a", common.FIREWALL, BUILDS) in buf.getvalue()
        ok &= "AUDIT not run" in buf.getvalue() and "FAIL no file of the copy has a stated hash" in buf.getvalue()
        ok &= "ORACLE 1 build(s), 1 on this machine" in buf.getvalue() and "`proto-a` is not on this machine" in err.getvalue()
        ok &= "`retail` is not on this machine (`psxd oracle record --dump <your dump>`)" in err.getvalue()
        ok &= re.search(r"(?m)^retail +the dump +- +here$", buf.getvalue()) is not None
        ok &= re.search(r"(?m)^proto-a +prototype +1 file\(s\) +here$", buf.getvalue()) is not None
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok &= main(["locate", "--repo", str(cli), "--id", "proto-a"]) == 0 and main(["locate", "--repo", str(cli), "--id", RETAIL]) == 0
        ok &= buf.getvalue() == "%s\n%s\n" % (sym, paths["cue"])
    return common.self_test_banner("oracle", ok)


if __name__ == "__main__":
    sys.exit(main())
