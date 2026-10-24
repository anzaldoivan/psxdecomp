#!/usr/bin/env python3
"""layer_audit.py — no game file in any layer of the toolchain image, before it is published (psxdecomp's
docs/PUBLISHING.md, Cutover order, step 4). Standard library only.

    layer_audit.py IMAGE.tar --private DIR      IMAGE.tar: the OCI archive build.sh wrote (or `docker save`'s, with the
                                                containerd image store); DIR: a local <game>-private checkout
    layer_audit.py --self-test

Every regular file of every layer is hashed. A HIT is a file with the sha1 of one under DIR's inputs/ or backup/. A
NAME is a file that is named like a game or SDK file: an input's own name, a boot executable (SLUS_000.00), a disc
image, a PsyQ tool. ALLOW exempts a NAME only at its exact path with its exact sha256: the open-source
psyq-obj-parser of the SDK leg (Dockerfile). Exit 1 on either; a deleted file still sits in its layer, so every layer
is read, not the final filesystem.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import re
import sys
import tarfile
import tempfile

SUSPECT = re.compile(r"^[A-Z]{4}_\d{3}\.\d{2}$|\.(cue|chd|ecm|pbp|ccd|mdf|mds)$|^(psyq|psy-q)|^(cc1psx|ccpsx|aspsx|psylink)\.exe$", re.I)
# {path in the layer: sha256} of a file SUSPECT names that is no SDK file: the Dockerfile's PSYQ_OBJ_PARSER_SHA256
ALLOW = {"usr/local/bin/psyq-obj-parser": "56ea873e5e6a5b417e99fe19eaad6da224ca2b1d267c710ce8cd9e48a691a36a"}


def digests(f, *names: str) -> list[str]:
    hs = [hashlib.new(n) for n in names]
    for chunk in iter(lambda: f.read(1 << 20), b""):
        for h in hs:
            h.update(chunk)
    return [h.hexdigest() for h in hs]


def sha1_of(f) -> str:
    return digests(f, "sha1")[0]


def private_set(directory) -> tuple[dict[str, str], set[str]]:
    """({sha1: path}, {lower-case file name}) of the game files in a <game>-private checkout."""
    root = pathlib.Path(directory)
    files = [p for d in ("inputs", "backup") for p in sorted((root / d).rglob("*")) if p.is_file()]
    hashes = {}
    for p in files:
        with open(p, "rb") as f:
            hashes[sha1_of(f)] = str(p.relative_to(root))
    return hashes, {p.name.lower() for p in files}


def layers(image: tarfile.TarFile):
    """(digest, file object) per layer of an OCI archive's first image."""
    blob = lambda d: image.extractfile("blobs/sha256/" + d.split(":", 1)[1])  # noqa: E731
    m = json.load(image.extractfile("index.json"))["manifests"][0]
    doc = json.load(blob(m["digest"]))
    while "layers" not in doc:                                         # an index of indexes: the first image
        doc = json.load(blob(doc["manifests"][0]["digest"]))
    for l in doc["layers"]:
        if "zstd" in l.get("mediaType", ""):
            raise SystemExit("LAYERS FAIL %s is zstd: rebuild with gzip layers (this tool reads tar and tar+gzip)" % l["digest"])
        yield l["digest"], blob(l["digest"])


def audit(image_path, hashes: dict[str, str], names: set[str],
          allow: dict[str, str] = ALLOW) -> tuple[list[str], int, int]:
    """(findings, layers read, files hashed). A file at a path of `allow` is also hashed with sha256."""
    found, n_layers, n_files = [], 0, 0
    with tarfile.open(image_path) as image:
        for digest, f in layers(image):
            n_layers += 1
            with tarfile.open(fileobj=f, mode="r:*") as layer:
                for member in layer:
                    if not member.isfile():
                        continue
                    n_files += 1
                    base = member.name.rsplit("/", 1)[-1]
                    want = allow.get(member.name.removeprefix("./"))
                    sha1, sha256 = digests(layer.extractfile(member), "sha1", "sha256") if want else (
                        sha1_of(layer.extractfile(member)), None)
                    hit = hashes.get(sha1)
                    if hit:
                        found.append("HIT  %s in layer %s is %s" % (member.name, digest[7:19], hit))
                    elif (base.lower() in names or SUSPECT.search(base)) and not (want and sha256 == want):
                        found.append("NAME %s in layer %s" % (member.name, digest[7:19]))
    return found, n_layers, n_files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--private", metavar="DIR")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.image or not a.private:
        ap.error("IMAGE.tar and --private DIR")
    hashes, names = private_set(a.private)
    if not hashes:
        print("LAYERS FAIL %s has no file under inputs/ or backup/: nothing to compare with" % a.private)
        return 1
    found, n_layers, n_files = audit(a.image, hashes, names)
    for line in found:
        print("LAYERS %s" % line)
    print("LAYERS %s %d layer(s), %d file(s) against %d game file(s): %d hit(s), %d suspicious name(s)" % (
        "FAIL" if found else "OK", n_layers, n_files, len(hashes), sum(x.startswith("HIT") for x in found),
        sum(x.startswith("NAME") for x in found)))
    return 1 if found else 0


def _tar(files: dict[str, bytes], gz: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz" if gz else "w") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _image(path, layer_files: list[dict[str, bytes]]):
    blobs = {}

    def put(data: bytes) -> str:
        d = hashlib.sha256(data).hexdigest()
        blobs["blobs/sha256/" + d] = data
        return "sha256:" + d
    ls = [{"mediaType": "application/vnd.oci.image.layer.v1.tar" + ("+gzip" if i % 2 else ""),
           "digest": put(_tar(f, gz=bool(i % 2)))} for i, f in enumerate(layer_files)]
    manifest = put(json.dumps({"schemaVersion": 2, "layers": ls}).encode())
    blobs["index.json"] = json.dumps({"schemaVersion": 2, "manifests": [{"digest": manifest}]}).encode()
    pathlib.Path(path).write_bytes(_tar(blobs))


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "private" / "inputs" / "disks").mkdir(parents=True)
        (root / "private" / "inputs" / "disks" / "GAME.DAT").write_bytes(b"synthetic game file\n")
        hashes, names = private_set(root / "private")
        clean = [{"usr/bin/tool": b"a tool\n"}, {"opt/x/readme.md": b"text\n", "opt/x/data.bin": b"\x00\x01"}]
        _image(root / "clean.tar", clean)
        _image(root / "hit.tar", clean + [{"tmp/renamed": b"synthetic game file\n"}])     # deleted later: still a layer
        _image(root / "name.tar", clean + [{"work/SLUS_000.00": b"x"}, {"work/game.dat": b"y"}, {"t/PSYQ.zip": b"z"}])
        got = {n: audit(root / (n + ".tar"), hashes, names) for n in ("clean", "hit", "name")}
        ok &= got["clean"] == ([], 2, 3)
        ok &= len(got["hit"][0]) == 1 and got["hit"][0][0].startswith("HIT  tmp/renamed in layer ")
        ok &= got["hit"][0][0].endswith(" is inputs/disks/GAME.DAT")
        ok &= [x.split()[1] for x in got["name"][0]] == ["work/SLUS_000.00", "work/game.dat", "t/PSYQ.zip"]
        tool = "usr/local/bin/psyq-obj-parser"                       # ALLOW: that path with that sha256, nothing else
        allow = {tool: hashlib.sha256(b"synthetic tool\n").hexdigest()}
        _image(root / "allowed.tar", clean + [{tool: b"synthetic tool\n"}])
        _image(root / "other.tar", clean + [{tool: b"another tool\n"}])
        ok &= audit(root / "allowed.tar", hashes, names, allow) == ([], 3, 4)
        for image, a in (("other", allow), ("allowed", ALLOW)):                   # other bytes, then the real pin
            ok &= [x.split()[:2] for x in audit(root / (image + ".tar"), hashes, names, a)[0]] == [["NAME", tool]]
        ok &= set(ALLOW) == {tool} and re.fullmatch(r"[0-9a-f]{64}", ALLOW[tool]) is not None
        ok &= main([str(root / "clean.tar"), "--private", str(root / "private")]) == 0
        ok &= main([str(root / "hit.tar"), "--private", str(root / "private")]) == 1
        ok &= main([str(root / "clean.tar"), "--private", str(root)]) == 1         # an empty private set proves nothing
    print("layer_audit %s" % ("SELF-TEST OK" if ok else "SELF-TEST FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
