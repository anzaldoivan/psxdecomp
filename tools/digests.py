#!/usr/bin/env python3
"""digests.py: the sha256 of each file that psxdecomp delivers into a game and that a game may not change itself.

  digests.py            print the document
  digests.py --write    write digests.json at the root of the plugin
  digests.py --check    exit 1 when digests.json is not the document of these sources

A game's gate accepts a changed copy of one of these files only when its bytes are the ones of a released psxdecomp
(scripts/floor.py `released_digests`): it reads digests.json at the tag `v<version>`. So the file is committed with
every change of its sources, and tier 0 runs `--check`. stdlib only.
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = {                                              # the path in a game: the source in the plugin
    "tools/psxd_floor.py": "scripts/floor.py",
    "tools/psxd_publish.py": "scripts/publish.py",
    ".github/workflows/psxdecomp-readme.yml": "profiles/psx/psxdecomp-readme.yml",
}


def document() -> str:
    version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
    files = {dst: hashlib.sha256((ROOT / src).read_bytes()).hexdigest() for dst, src in sorted(FILES.items())}
    return json.dumps({"version": version, "files": files}, indent=2) + "\n"


def main(argv) -> int:
    doc, path = document(), ROOT / "digests.json"
    if argv == ["--write"]:
        path.write_text(doc)
        print("DIGESTS written %s" % path.name)
    elif argv == ["--check"]:
        if not path.is_file() or path.read_text() != doc:
            print("DIGESTS FAIL digests.json is not the document of these sources: run `python3 tools/digests.py --write`")
            return 1
        print("DIGESTS OK")
    elif argv:
        sys.exit(__doc__)
    else:
        sys.stdout.write(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
