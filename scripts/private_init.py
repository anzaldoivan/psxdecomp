#!/usr/bin/env python3
"""private_init.py — build the local `<game>-private` repository of a split-mode game (docs/PUBLISHING.md, Cutover
order, step 2): the files the build reads, the hash list per executable, the README and .gitattributes of
profiles/psx/private/, as one commit. It creates nothing on GitHub: it prints the developer's commands.

    private_init.py --repo DEV --out DIR [--input REL ...] [--game NAME]
    private_init.py --self-test

The inputs are every `target_path` of DEV's config/splat.*.yaml plus each --input, copied to inputs/<the same
repository-relative path>. check/<EXE>.sha1 is each line of DEV's config/check.*.sha, one file per executable. Every
input whose file name a check line carries must have that line's sha1 (a matching build reproduces its input), or
nothing is written. DIR must be new and outside DEV: no game file ever sits in a game checkout's tracked tree.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import publish  # noqa: E402

PROFILE = common.PLUGIN_ROOT / "profiles" / "psx" / "private"


def sha1(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def splat_targets(repo: pathlib.Path) -> list[str]:
    """The repository-relative `target_path` of every config/splat.*.yaml (relative to its `base_path`)."""
    out = []
    for cfg in sorted((repo / "config").glob("splat.*.yaml")):
        text = common.read(cfg)
        base = re.search(r"^\s*base_path:\s*(\S+)", text, re.M)
        for m in re.finditer(r"^\s*target_path:\s*(\S+)", text, re.M):
            p = (cfg.parent / (base[1] if base else ".") / m[1].strip("\"'")).resolve()
            out.append(os.path.relpath(p, repo))
    return out


def plan(repo: pathlib.Path, extra: list[str]) -> tuple[list[tuple[str, str]], dict[str, str], list[str], list[str]]:
    """([(input, its sha1)], {check file: text}, problems, notes)."""
    probs, notes, inputs, checks = [], [], [], {}
    lines = [(h, n) for f in sorted((repo / "config").glob("check.*.sha")) for h, n in publish.sha_lines(common.read(f))]
    for h, n in lines:
        rel = "check/%s.sha1" % os.path.basename(n)
        checks[rel] = checks.get(rel, "") + "%s  %s\n" % (h, n)
    if not lines:
        probs.append("no config/check.*.sha line: nothing for the public CI's byte check")
    want = {os.path.basename(n): h for h, n in lines}
    for rel in dict.fromkeys(splat_targets(repo) + extra):
        f = repo / rel
        if rel.startswith("..") or os.path.isabs(rel) or not f.is_file() or f.is_symlink():
            probs.append("%s: not a regular file inside %s" % (rel, repo))
            continue
        got = sha1(f)
        inputs.append((rel, got))
        if os.path.basename(rel) not in want:
            notes.append("%s: no check line carries its name; copied unverified" % rel)
        elif want[os.path.basename(rel)] != got:
            probs.append("%s: sha1 %s, the check list says %s" % (rel, got, want[os.path.basename(rel)]))
    if not inputs and not probs:
        probs.append("no input: no config/splat.*.yaml target_path and no --input")
    return inputs, checks, probs, notes


def game_slug(repo: pathlib.Path) -> str | None:
    """OWNER/GAME: [public].repo, else origin without its -dev."""
    try:
        cfg = publish.load_public(repo)
    except publish.Fail:
        cfg = None
    slug = cfg["repo"] if cfg else publish.origin_slug(repo)
    return re.sub(r"-dev$", "", slug) if slug else None


def build(repo: pathlib.Path, out: pathlib.Path, extra: list[str], game: str | None) -> int:
    repo, out = repo.resolve(), out.resolve()                          # macOS: /var is a link to /private/var
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print("PRIVATE FAIL %s exists and is not empty" % out)
        return 1
    if out == repo or repo in out.parents:
        print("PRIVATE FAIL %s is inside %s: the private repository sits beside a game checkout, never in one" % (out, repo))
        return 1
    slug = game or game_slug(repo)
    if not slug or "/" not in slug:
        print("PRIVATE FAIL no OWNER/GAME: set [public].repo, a GitHub origin, or --game OWNER/GAME")
        return 1
    inputs, checks, probs, notes = plan(repo, extra)
    for p in probs:
        print("PRIVATE FAIL %s" % p)
    if probs:
        return 1
    name = slug.split("/")[1]
    for rel, _ in inputs:
        dest = out / "inputs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, dest)
    for rel, text in checks.items():
        common.write(out / rel, text)
    common.write(out / "README.md", common.read(PROFILE / "README.md").replace("{{GAME}}", name))
    shutil.copyfile(PROFILE / ".gitattributes", out / ".gitattributes")
    bad = [rel for rel, h in inputs if sha1(out / "inputs" / rel) != h]            # the copy, read back
    if bad:
        print("PRIVATE FAIL copied but not identical: %s" % ", ".join(bad))
        return 1
    ident = [a for k in ("user.name", "user.email") for a in ("-c", "%s=%s" % (k, common.git(repo, "config", k).stdout.strip()))]
    common.git(out, "init", "-q", "-b", "main")
    common.git(out, "add", "-A")
    common.git(out, *ident, "-c", "commit.gpgsign=false", "commit", "-q", "-m",
               "%s-private: the build's inputs and the hash list per executable" % name)
    rev = common.git(out, "rev-parse", "HEAD").stdout.strip()
    for rel, h in inputs:
        print("PRIVATE input %s  inputs/%s" % (h, rel))
    for n in notes:
        print("PRIVATE WARN %s" % n)
    P, key = "%s-private" % slug, "~/.ssh/psxd/%s-private" % name
    print("PRIVATE OK %s: %d input(s), %d check list(s), commit %s\n" % (out, len(inputs), len(checks), rev))
    print("The developer's, in a terminal outside Claude Code:\n"
          "  gh repo create %s --private --disable-issues --disable-wiki\n"
          "  gh api -X PUT repos/%s/actions/permissions -F enabled=false\n"
          "  mkdir -p ~/.ssh/psxd && ssh-keygen -t ed25519 -N '' -C '%s public CI' -f %s\n"
          "  gh repo deploy-key add %s.pub --repo %s --title 'public CI (read-only)'\n"
          "  git -C %s remote add origin git@github.com:%s.git && git -C %s push -u origin main\n"
          "Then in %s: [public] private_repo = \"%s\", private_rev = \"%s\"; /psxdecomp:doctor's private-repo row "
          "checks the rest." % (P, P, name, key, key, P, out, P, out, publish.CONFIG_REL, P, rev))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the dev repository")
    ap.add_argument("--out", help="the new local repository (outside the dev repository)")
    ap.add_argument("--input", action="append", default=[], metavar="REL", help="one more file the build reads")
    ap.add_argument("--game", metavar="OWNER/GAME", help="default: [public].repo, else origin without -dev")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.out:
        ap.error("--out DIR")
    return build(pathlib.Path(a.repo).resolve(), pathlib.Path(a.out).expanduser().resolve(), a.input, a.game)


def self_test() -> int:
    import contextlib
    import io
    ok = True
    with tempfile.TemporaryDirectory() as td:
        os.mkdir(td + "/dev")
        repo = publish._self_repo(td + "/dev")
        common.git(repo, "config", "user.name", "t")
        common.git(repo, "config", "user.email", "t@t.invalid")
        (repo / "disks").mkdir()
        (repo / "disks" / "PSXD_000.01").write_bytes(b"synthetic executable\n")
        (repo / "disks" / "extra.dat").write_bytes(b"synthetic data\n")
        (repo / "config" / "splat.main.yaml").write_text("options:\n  base_path: ..\n  target_path: disks/PSXD_000.01\n")
        good = sha1(repo / "disks" / "PSXD_000.01")
        check = repo / "config" / "check.PSXD_000.01.sha"

        def run(out, *extra):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = build(repo, pathlib.Path(td) / out, list(extra), None)
            return rc, buf.getvalue()
        rc, text = run("wrong")                                         # the synthetic check line is not this file's
        ok &= rc == 1 and "the check list says 3333" in text and not (pathlib.Path(td) / "wrong").exists()
        check.write_text("%s  build/PSXD_000.01\n" % good)
        rc, text = run("dev/inside")
        ok &= rc == 1 and "never in one" in text
        rc, text = run("p", "disks/extra.dat")
        out = pathlib.Path(td) / "p"
        tracked = sorted(common.git(out, "ls-files").stdout.split())
        ok &= rc == 0 and tracked == [".gitattributes", "README.md", "check/PSXD_000.01.sha1", "inputs/disks/PSXD_000.01",
                                      "inputs/disks/extra.dat"]
        ok &= (out / "check/PSXD_000.01.sha1").read_text() == "%s  build/PSXD_000.01\n" % good
        ok &= "# synthetic-decomp-private" in (out / "README.md").read_text() and "{{" not in (out / "README.md").read_text()
        rev = common.git(out, "rev-parse", "HEAD").stdout.strip()
        ok &= 'private_rev = "%s"' % rev in text and "example/synthetic-decomp-private --private" in text
        ok &= "extra.dat: no check line" in text and run("p")[0] == 1   # a second run never overwrites
        print("  %s" % text.splitlines()[-9].strip()[:110])
    return common.self_test_banner("private_init", ok)


if __name__ == "__main__":
    sys.exit(main())
