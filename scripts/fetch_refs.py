#!/usr/bin/env python3
"""fetch_refs.py — the pinned reference library: lint refs.toml, fetch each fetchable row into the ignored refs/<name>/
at its pinned ref (shallow; sparse when `paths` is set; archives checked by sha256), and write the committed index
docs/ops/refs.md that agents grep from.

    fetch_refs.py [--repo DIR] [--refs FILE] [--with NAME | --all] [--dry-run]
                                                                             fetch the core rows (plus the optional
                                                                             ones named) + write the index
    fetch_refs.py --lint [--refs FILE]                                       validate the rows only
    fetch_refs.py --check [--repo DIR]                                       drift: checkouts at their pins, index current
    fetch_refs.py --index-only [--repo DIR]                                  rewrite the index, fetch nothing
    fetch_refs.py --self-test                                                a local mirror fixture, every refusal tested

Exit 0 on success, 1 on a refusal or drift. byo rows are never fetched; a byo row carrying a URL is refused.
Tiers: `core` rows are fetched by default; `optional` rows only with --with/--all (each says `when`). The file's
[[authority]] (which source wins per topic) and [[trap]] (contradictions already paid for) go into the index.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CLASSES = {
    "adapt": "adapt code with attribution in THIRD_PARTY.md",
    "copyleft": "adapt only into a licence-compatible repo; facts otherwise",
    "facts": "cite facts, never copy text or code",
    "public": "quote freely",
    "byo": "never fetched; the user supplies a local path (copyrighted); a firewall purge path",
    "link": "the index keeps the URL and a summary; never fetched",
}
FETCHED = {"adapt", "copyleft", "facts", "public"}
TIERS = {"core", "optional"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_RE = re.compile(r"\.(zip|tar\.gz|tgz|tar\.xz)$")
INDEX_REL = "docs/ops/refs.md"
REFS_REL = "config/refs.toml"


def lint(rows: list[dict]) -> list[str]:
    errs, names = [], set()
    for i, r in enumerate(rows):
        n = r.get("name", "")
        tag = "row %d (%s)" % (i + 1, n or "?")
        if not NAME_RE.match(n):
            errs.append("%s: name must match %s" % (tag, NAME_RE.pattern))
        if n in names:
            errs.append("%s: duplicate name" % tag)
        names.add(n)
        c = r.get("class")
        if c not in CLASSES:
            errs.append("%s: class %r is not one of %s" % (tag, c, ", ".join(CLASSES)))
            continue
        if not str(r.get("licence", "")).strip():
            errs.append("%s: no licence (every row carries one, even 'unstated')" % tag)
        if not r.get("topics"):
            errs.append("%s: no topics (the index is searched by topic)" % tag)
        url = str(r.get("url", "")).strip()
        if c == "byo":
            if url:
                errs.append("%s: a byo row never carries a URL (copyrighted material is supplied locally, never "
                            "fetched)" % tag)
            continue
        if c == "link":
            if not url:
                errs.append("%s: a link row needs its URL" % tag)
            continue
        if not url:
            errs.append("%s: a fetched row needs a url" % tag)
        ref = str(r.get("ref", ""))
        if ARCHIVE_RE.search(url):
            if not re.match(r"^[0-9a-f]{64}$", str(r.get("sha256", ""))):
                errs.append("%s: an archive row needs its sha256" % tag)
        elif not ref:
            errs.append("%s: a fetched row needs a pinned ref (a 40-hex commit or a tag)" % tag)
        elif not SHA_RE.match(ref) and not re.match(r"^[A-Za-z0-9._/-]+$", ref):
            errs.append("%s: ref %r is neither a commit nor a tag" % (tag, ref))
        tier = r.get("tier")
        if tier not in TIERS:
            errs.append("%s: tier %r is not one of %s" % (tag, tier, ", ".join(sorted(TIERS))))
        elif tier == "optional" and not str(r.get("when", "")).strip():
            errs.append("%s: an optional row says `when` to fetch it" % tag)
        if not str(r.get("covers", "")).strip():
            errs.append("%s: no `covers` (which version or scope a hit speaks for)" % tag)
        for p in r.get("paths", []) or []:
            if p.startswith("/") or ".." in p.split("/"):
                errs.append("%s: sparse path %r must be relative and inside the repo" % (tag, p))
    return errs


def load_rows(path) -> list[dict]:
    return common.load_toml(path).get("ref", [])


def load_doc(path) -> dict:
    d = common.load_toml(path)
    return {"rows": d.get("ref", []), "authority": d.get("authority", []), "traps": d.get("trap", [])}


def lint_doc(doc: dict) -> list[str]:
    errs = lint(doc["rows"])
    names = {r.get("name") for r in doc["rows"]}
    for a in doc["authority"]:
        if not a.get("topic") or not a.get("order") or not a.get("rule"):
            errs.append("authority %r: needs topic, order and rule" % a.get("topic"))
        errs += ["authority %r names %r, which is not a row" % (a.get("topic"), n) for n in a.get("order", [])
                 if n not in names]
    for t in doc["traps"]:
        if not all(str(t.get(k, "")).strip() for k in ("what", "evidence", "do")):
            errs.append("trap %r: needs what, evidence and do" % str(t.get("what", ""))[:40])
    return errs


def wanted(r: dict, with_names, all_optional: bool) -> bool:
    if r["class"] not in FETCHED:
        return False
    return r.get("tier") == "core" or all_optional or r["name"] in (with_names or [])


def fetch_git(r: dict, dest: pathlib.Path):
    tmp = dest.with_name(dest.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    g = lambda *a, check=True: common.git(tmp, *a, check=check)  # noqa: E731
    g("init", "--quiet")
    g("remote", "add", "origin", r["url"])
    paths = r.get("paths") or []
    if paths:
        g("sparse-checkout", "set", "--no-cone", *paths)
    want = r["ref"] if SHA_RE.match(r["ref"]) else "refs/tags/%s" % r["ref"]
    res = g("fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", want, check=False)
    if res.returncode != 0:
        res = g("fetch", "--quiet", "--depth", "1", "origin", want, check=False)
    if res.returncode != 0 and not SHA_RE.match(r["ref"]):
        res = g("fetch", "--quiet", "--depth", "1", "origin", r["ref"], check=False)
    if res.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise common.Fail("%s: fetch of %s at %s failed: %s" % (r["name"], r["url"], r["ref"],
                                                                (res.stdout + res.stderr).strip()[-300:]))
    g("checkout", "--quiet", "FETCH_HEAD")
    head = g("rev-parse", "HEAD").stdout.strip()
    if SHA_RE.match(r["ref"]) and head != r["ref"]:
        shutil.rmtree(tmp, ignore_errors=True)
        raise common.Fail("%s: fetched %s, not the pinned %s" % (r["name"], head, r["ref"]))
    missing = [p for p in paths if not (tmp / p).exists()]
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    return head, missing


def fetch_archive(r: dict, dest: pathlib.Path):
    url = r["url"]
    if url.startswith("file://"):
        data = open(url[7:], "rb").read()
    elif os.path.isfile(url):
        data = open(url, "rb").read()
    else:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (pinned by sha256 below)
            data = resp.read()
    got = hashlib.sha256(data).hexdigest()
    if got != r["sha256"]:
        raise common.Fail("%s: archive sha256 %s does not match the pinned %s" % (r["name"], got, r["sha256"]))
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for m in z.namelist():
                if m.startswith("/") or ".." in m.split("/"):
                    raise common.Fail("%s: unsafe member %r in the archive" % (r["name"], m))
            z.extractall(dest)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            t.extractall(dest, filter="data")
    (dest / ".psxdecomp-sha256").write_text(got + "\n")
    return "sha256:" + got[:12], []


def pinned_head(dest: pathlib.Path) -> str | None:
    if (dest / ".git").is_dir():
        r = common.git(dest, "rev-parse", "HEAD", check=False)
        return r.stdout.strip() if r.returncode == 0 else None
    f = dest / ".psxdecomp-sha256"
    return "sha256:" + f.read_text().strip()[:12] if f.is_file() else None


def expected_head(r: dict) -> str:
    return "sha256:" + r["sha256"][:12] if ARCHIVE_RE.search(r.get("url", "")) else r["ref"]


# lint_scope: a toolchain version or a game named in a doc is a claim about ONE project at ONE time. It passes only
# with its scope at hand: inside a ``` fence (an example), or a date / scope key on the line, its nearest heading or
# its table's header. Code spans (`gcc-2.7.2-src`) are identifiers, not claims, and are skipped. In a TOML text the
# scope is the record: a line passes when any line of its [[...]] / [...] record carries a scope key.
SCOPE_TOOL = re.compile(r"\b(?:gcc[ -]?2\.\d|aspsx[ -]?v?\d\.\d|psy-?q[ -]?\d\.\d)", re.I)
# Bare X4/X6 are left out: in a game repo they are PA3 rule ids, not games (mmx4/mmx6 name the games).
SCOPE_GAME = re.compile(r"\b(?:BFM|mmx6|mmx4|ygofm|Xenogears|Vagrant Story|FF7|FF8)\b")
SCOPE_OK = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b(?:provenance:|scope:|seen_in|covers|used_by|evidence|sources)", re.I)
TOML_RECORD = re.compile(r"^\s*\[\[?[^\]]+\]\]?\s*(?:#.*)?$")
TOML_SCOPE = re.compile(r"(?:^|[{,\s])(?:used_by|evidence|covers|checked|sources|seen|scope)\s*=")


def _body(lines: list[str]) -> list[str]:
    """The lines with a leading YAML front matter blanked (metadata, not prose); line numbers are kept."""
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end:
            return [""] * (end + 1) + lines[end + 1:]
    return lines


def _claim(line: str) -> bool:
    bare = re.sub(r"`[^`]*`|(?<![\w.])(?:~|\.{1,2})?/[^\s|)]+", "", line)     # code spans and absolute paths: identifiers
    return bool(SCOPE_TOOL.search(bare) or SCOPE_GAME.search(bare))


def lint_scope(text: str, toml: bool = False) -> list[tuple[int, str]]:
    """Lines naming a toolchain version or a game without a date or scope key nearby: [(line_no, line)]."""
    lines = _body(text.splitlines())
    if toml:
        starts = [i for i, l in enumerate(lines) if TOML_RECORD.match(l)]
        bounds = list(zip([0] + starts, starts + [len(lines)]))
        bad = []
        for a, b in bounds:
            rec = lines[a:b]
            if any(TOML_SCOPE.search(l) or SCOPE_OK.search(l) for l in rec):
                continue
            bad += [(a + j + 1, l) for j, l in enumerate(rec) if _claim(l)]
        return sorted(bad)
    bad, fence, heading, header = [], False, "", ""
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if re.match(r"^#{1,6} ", line):
            heading, header = line, ""
            continue
        if line.startswith("|"):
            header = line if not (i and lines[i - 1].startswith("|")) else header
        else:
            header = ""
        if _claim(line) and not any(SCOPE_OK.search(s) for s in (line, heading, header)):
            bad.append((i + 1, line))
    return bad


def lint_file(path) -> list[tuple[int, str]]:
    path = pathlib.Path(path)
    return lint_scope(common.read(path), toml=path.suffix == ".toml")


# lint_dupes: a fact has one home. A prose sentence of 60+ characters (markdown, code spans, case and whitespace
# normalised; fences and table rows skipped; in TOML, the string values) found in two or more files is a copy: delete
# one and link to the home, never allowlist it.
DUPE_MIN = 60
META = re.compile(r"^[a-z_]+: \S.* · [a-z_]+: ")                 # an `id: G1 · group: G · …` record line
GENERATED = re.compile(r"[Gg]enerated by .{0,80}do not edit", re.S)


def _paragraphs(text: str, toml: bool):
    """(line_no, text) prose paragraphs: wrapped lines joined, a list item or a heading starts a new one."""
    if toml:
        for i, l in enumerate(text.splitlines()):
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"', l):
                yield i + 1, s
        return
    fence, cur, start = False, [], 0
    for i, l in enumerate(_body(text.splitlines()) + [""]):
        s = re.sub(r"^(?:>\s?)+", "", l.strip())                     # a blockquote is prose
        if s.startswith("```"):
            fence = not fence
        skip = fence or s.startswith(("```", "|", "<!--")) or not s or META.match(s)
        if (skip or re.match(r"^(#{1,6} |[-*+] |\d+\. )", s)) and cur:
            yield start, " ".join(cur)
            cur = []
        if skip:
            continue
        if not cur:
            start = i + 1
        cur.append(re.sub(r"^(#{1,6} |[-*+] |\d+\. )", "", s))


def _norm(s: str) -> str:
    s = re.sub(r"`[^`]*`", " ", s)
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_~]+", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def sentences(text: str, toml: bool = False):
    """(line_no, normalised sentence) for every prose sentence of DUPE_MIN+ characters."""
    for n, para in _paragraphs(text, toml):
        for sent in re.split(r"(?:(?<=[.!?;:])|(?<=[.!?;:][*_)]{1})|(?<=[.!?;:][*_]{2}))\s+(?=[A-Z*`(\[])", para):
            norm = _norm(sent)
            if len(norm) >= DUPE_MIN:
                yield n, norm


def lint_dupes(paths, root=None) -> list[tuple[str, list[str]]]:
    """Sentences found in two or more files: [(sentence, [path:line, ...])], each file once per sentence."""
    seen: dict[str, dict[str, int]] = {}
    for p in paths:
        p = pathlib.Path(p)
        try:
            text = common.read(p)
        except (OSError, UnicodeDecodeError):
            continue
        if GENERATED.search(text[:600]):
            continue                                # a generated index restates its source by design
        rel = p.relative_to(root).as_posix() if root else p.as_posix()
        for n, s in sentences(text, toml=p.suffix == ".toml"):
            seen.setdefault(s, {}).setdefault(rel, n)
    return [(s, ["%s:%d" % kv for kv in where.items()]) for s, where in seen.items() if len(where) > 1]


def render_index(rows: list[dict], refs_rel: str = REFS_REL, authority=(), traps=()) -> str:
    out = ["# Reference library", "",
           "*Generated by psxdecomp's `fetch_refs.py` from `%s`; do not edit by hand (re-run it).*" % refs_rel, "",
           "Fetchable sources are cloned at their pins into the ignored `refs/<name>/`. **Grep them; never Read a "
           "`refs/` tree whole** (dispatch `retriever-code` for anything wider than a grep). Cite a fact as "
           "`<name>@<ref> <path>`. What an agent may do with a source is decided by its class:", ""]
    out += ["| Class | Agents may |", "|---|---|"]
    out += ["| `%s` | %s |" % (c, d) for c, d in CLASSES.items()]
    out += ["", "`core` sources are fetched at bootstrap; `optional` ones only when their condition holds "
            "(`fetch_refs.py --with <name>`). A hit answers only within the source's *covers*.",
            "", "| Source | Class | Tier | Licence | Pin | Covers | Topics | Where |",
            "|---|---|---|---|---|---|---|---|"]
    order = {"core": 0, "optional": 1}
    for r in sorted(rows, key=lambda r: (order.get(r.get("tier"), 2), list(CLASSES).index(r["class"]), r["name"])):
        c = r["class"]
        tier = r.get("tier", "—")
        if c in FETCHED:
            where = "`refs/%s/`%s" % (r["name"], (" (" + ", ".join(r["paths"]) + ")") if r.get("paths") else "")
            if tier == "optional":
                where += "; fetch when: %s" % r.get("when", "")
            pin = "`%s`" % expected_head(r)[:12]
        elif c == "byo":
            where, pin = "your local path (never fetched, never committed)", "—"
        else:
            where, pin = r["url"], "—"
        out.append("| [%s](%s) | `%s` | %s | %s | %s | %s | %s | %s |" % (
            r["name"], r["url"] or "#", c, tier, r.get("licence", ""), pin, r.get("covers", "—"),
            ", ".join(r.get("topics", [])), where))
    if authority:
        out += ["", "## Which source wins", "", "| Topic | Order | Rule |", "|---|---|---|"]
        out += ["| %s | %s | %s |" % (a["topic"], " > ".join("`%s`" % n for n in a["order"]), a["rule"])
                for a in authority]
    if traps:
        out += ["", "## Known traps (contradictions already paid for)", ""]
        out += ["- %s. *Evidence:* %s. *Do:* %s." % (t["what"], t["evidence"], t["do"]) for t in traps]
    notes = [r for r in rows if r.get("note")]
    if notes:
        out += ["", "## Notes", ""]
        out += ["- **%s:** %s" % (r["name"], r["note"]) for r in sorted(notes, key=lambda r: r["name"])]
    out += ["", "## Search", "",
            "- By topic: `grep -n '<topic>' docs/ops/refs.md`, then `grep -rn '<term>' refs/<name>/`.",
            "- Example: which PsyQ library holds `SpuSetKey`? `grep -rln SpuSetKey refs/ | head`.",
            "- A fact the library cannot answer goes to a web retriever, and the source it finds becomes a row here.",
            ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--refs")
    ap.add_argument("--only", action="append")
    ap.add_argument("--with", dest="with_", action="append", help="also fetch this optional row (repeatable)")
    ap.add_argument("--all", action="store_true", help="fetch every optional row too")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    repo = pathlib.Path(a.repo).resolve()
    refs_path = pathlib.Path(a.refs) if a.refs else repo / REFS_REL
    if not refs_path.is_file():
        print("FAIL no refs file at %s" % refs_path)
        return 1
    doc = load_doc(refs_path)
    rows = doc["rows"]
    errs = lint_doc(doc)
    unknown = [n for n in (a.with_ or []) if n not in {r["name"] for r in rows}]
    errs += ["--with %s: no such row" % n for n in unknown]
    if errs:
        for e in errs:
            print("REFUSE %s" % e)
        print("FAIL refs.toml: %d problem(s)" % len(errs))
        return 1
    if a.lint:
        print("REFS LINT OK %d rows (%s; core %d, optional %d; %d authority, %d traps)" % (len(rows), ", ".join(
            "%s %d" % (c, sum(r["class"] == c for r in rows)) for c in CLASSES if any(r["class"] == c for r in rows)),
            sum(r.get("tier") == "core" for r in rows), sum(r.get("tier") == "optional" for r in rows),
            len(doc["authority"]), len(doc["traps"])))
        return 0
    try:
        refs_rel = refs_path.relative_to(repo).as_posix()
    except ValueError:
        refs_rel = REFS_REL
    index = render_index(rows, refs_rel, doc["authority"], doc["traps"])
    if a.check:
        bad = 0
        for r in rows:
            if r["class"] not in FETCHED:
                continue
            head = pinned_head(repo / "refs" / r["name"])
            want = expected_head(r)
            if head is None:
                if r.get("tier") == "optional":
                    continue                       # optional and not fetched: fine
                print("MISSING %s (not fetched)" % r["name"])
                bad += 1
            elif head != want:
                print("DRIFT %s at %s, pinned %s" % (r["name"], head[:12], want[:12]))
                bad += 1
        idx = repo / INDEX_REL
        if not idx.is_file() or common.read(idx) != index:
            print("DRIFT %s is not the index of %s (re-run fetch_refs.py --index-only)" % (INDEX_REL, refs_rel))
            bad += 1
        print("REFS %s %d rows" % ("OK" if not bad else "DRIFT %d" % bad, len(rows)))
        return 1 if bad else 0
    fetched = 0
    if not a.index_only:
        for r in rows:
            if not wanted(r, a.with_, a.all) or (a.only and r["name"] not in a.only):
                continue
            dest = repo / "refs" / r["name"]
            if pinned_head(dest) == expected_head(r):
                print("SKIP  %-28s at its pin" % r["name"])
                continue
            if a.dry_run:
                print("WOULD %-28s %s @ %s" % (r["name"], r["url"], expected_head(r)[:12]))
                continue
            try:
                head, missing = (fetch_archive if ARCHIVE_RE.search(r["url"]) else fetch_git)(r, dest)
            except common.Fail as e:
                print("FAIL %s" % e)
                return 1
            fetched += 1
            print("FETCH %-28s %s%s" % (r["name"], head[:12], ("  WARN missing paths: " + ", ".join(missing))
                                         if missing else ""))
    st = common.write(repo / INDEX_REL, index, dry=a.dry_run)
    print("INDEX %s %s" % (INDEX_REL, st if not a.dry_run else "would be " + st))
    print("REFS OK %d rows, %d fetched" % (len(rows), fetched))
    return 0


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        up = td / "upstream"
        up.mkdir()
        common.git(up, "init", "--quiet")
        (up / "docs").mkdir()
        (up / "docs" / "libspu.md").write_text("SpuSetKey lives in libspu\n")
        (up / "other.txt").write_text("not in the sparse set\n")
        common.git(up, "add", "-A")
        common.git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "x")
        common.git(up, "config", "uploadpack.allowAnySHA1InWant", "true")
        common.git(up, "config", "uploadpack.allowFilter", "true")
        sha = common.git(up, "rev-parse", "HEAD").stdout.strip()
        arc = td / "a.tar.gz"
        with tarfile.open(arc, "w:gz") as t:
            t.add(up / "docs" / "libspu.md", arcname="libspu.md")
        asha = hashlib.sha256(arc.read_bytes()).hexdigest()
        repo = td / "game"
        (repo / "config").mkdir(parents=True)

        def toml(rows, extra=""):
            lines = []
            for r in rows:
                lines.append("[[ref]]")
                lines += ["%s = %s" % (k, ('[%s]' % ", ".join('"%s"' % x for x in v)) if isinstance(v, list)
                                       else '"%s"' % v) for k, v in r.items()]
            (repo / "config" / "refs.toml").write_text("\n".join(lines) + "\n" + extra)

        good = [dict(name="mirror", url="file://" + str(up), ref=sha, licence="MIT", **{"class": "adapt"},
                     tier="core", covers="the mirror", topics=["spu"], paths=["docs"]),
                dict(name="arc", url=str(arc), ref="", sha256=asha, licence="MIT", **{"class": "facts"},
                     tier="optional", when="a test asks", covers="the archive", topics=["spu"]),
                dict(name="sdk", url="", licence="proprietary", **{"class": "byo"}, topics=["psyq"]),
                dict(name="site", url="https://example.invalid", licence="n/a", **{"class": "link"}, topics=["x"])]
        meta = ('[[authority]]\ntopic = "spu"\norder = ["mirror", "arc"]\nrule = "the mirror wins"\n'
                '[[trap]]\nwhat = "a trap"\nevidence = "a test"\ndo = "avoid it"\n')
        toml(good, meta)
        out = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(out):
            rc = main(["--repo", str(repo)])
        ok &= rc == 0 and (repo / "refs/mirror/docs/libspu.md").is_file() and not (repo / "refs/mirror/other.txt").exists()
        ok &= not (repo / "refs/arc").exists() and not (repo / "refs/sdk").exists()      # optional: not by default
        idx = (repo / INDEX_REL).read_text()
        ok &= "| [sdk](#) | `byo`" in idx and "## Which source wins" in idx and "## Known traps" in idx
        with contextlib.redirect_stdout(io.StringIO()):
            ok &= main(["--repo", str(repo), "--check"]) == 0                          # optional absent: no drift
            ok &= main(["--repo", str(repo), "--with", "arc"]) == 0
        ok &= (repo / "refs/arc/libspu.md").is_file()
        with contextlib.redirect_stdout(io.StringIO()):
            ok &= main(["--repo", str(repo), "--check"]) == 0
            # an idempotent second run fetches nothing
        out2 = io.StringIO()
        with contextlib.redirect_stdout(out2):
            main(["--repo", str(repo)])
        ok &= "0 fetched" in out2.getvalue()
        # refusals: a byo URL, a wrong archive hash, a wrong pinned commit, a missing licence, drift
        cases = [
            ("byo-url", [dict(good[2], url="https://example.invalid/psyq.zip")]),
            ("no-licence", [dict(good[0], licence="")]),
            ("bad-class", [dict(good[0], **{"class": "maybe"})]),
            ("bad-sha256", [dict(good[1], sha256="0" * 64, name="arc2")]),
            ("wrong-ref", [dict(good[0], ref="1" * 40, name="mirror2")]),
            ("no-tier", [{k: v for k, v in good[0].items() if k != "tier"}]),
            ("no-when", [{k: v for k, v in good[1].items() if k != "when"}]),
            ("no-covers", [{k: v for k, v in good[0].items() if k != "covers"}]),
        ]
        for label, rows in cases:
            toml(rows)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = main(["--repo", str(repo), "--all"])
            text = buf.getvalue()
            refused = rc == 1 and ("REFUSE" in text or "FAIL" in text)
            print("  control %-11s %s" % (label, "refused" if refused else "NOT REFUSED"))
            ok &= refused
        toml(good, '[[authority]]\ntopic = "x"\norder = ["nosuch"]\nrule = "r"\n')
        with contextlib.redirect_stdout(io.StringIO()):
            bad_auth = main(["--repo", str(repo), "--lint"]) == 1
        print("  control %-11s %s" % ("bad-authority", "refused" if bad_auth else "NOT REFUSED"))
        ok &= bad_auth
        toml(good, meta)
        (repo / INDEX_REL).write_text("stale\n")
        with contextlib.redirect_stdout(io.StringIO()):
            drift = main(["--repo", str(repo), "--check"]) == 1
        print("  control %-11s %s" % ("drift", "refused" if drift else "NOT REFUSED"))
        ok &= drift
    # lint_scope: unscoped claims flagged; a date, a scope key, a fence, a heading or a table header clears them
    doc = ("# T\nBFM used gcc 2.7.2.\nbfm in lower case and `gcc-2.7.2-src` are not claims.\n"
           "PsyQ 4.7 (seen 2026-10-01).\n```\nmmx6 example\n```\n## Leads (scope: 2026-10-01)\nX6 uses aspsx 2.86.\n"
           "# U\n| Game | Covers |\n|---|---|\n| mmx4 | gcc 2.7.2 |\n\nXenogears is mixed.\n")
    got = [n for n, _ in lint_scope(doc)]
    print("  lint_scope flags lines %s" % got)
    ok &= got == [2, 15]
    # TOML: the record is the scope; a record with used_by passes, the same record without it is flagged
    rec = '# head\n[[ref]]\nname = "gcc-2.7.2-src"\nwhen = "a gcc 2.7.2 pin"\n%s[[trap]]\nwhat = "mmx6 x"\nevidence = "e"\n'
    got_t = ([n for n, _ in lint_scope(rec % 'used_by = ["mmx6"]\n', toml=True)],
             [n for n, _ in lint_scope(rec % "", toml=True)])
    print("  lint_scope TOML records: with used_by %s, without %s" % got_t)
    ok &= got_t == ([], [3, 4])
    # lint_dupes: a sentence copied into a second file (other wrapping, case, markup) is found; a table row is not
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        sent = "The pinned compiler triple lives in one file and every other doc links to it."
        (td / "a.md").write_text("# A\n\n%s Then more.\n\n| %s |\n" % (sent, sent))
        (td / "b.md").write_text("Intro.\n\n- the pinned **compiler triple** lives in one file\n  and every other doc "
                                 "links to it.\n")
        (td / "c.md").write_text("| %s |\n\n```\n%s\n```\n" % (sent, sent))
        d = lint_dupes(sorted(td.glob("*.md")), td)
        print("  lint_dupes: %s" % [w for _, w in d])
        ok &= [w for _, w in d] == [["a.md:3", "b.md:3"]]
        ok &= lint_dupes([td / "a.md", td / "c.md"], td) == []
        meta = "---\nid: G%d\nstatus: active, tags: decomp, firewall, origin: decomp-architect, added: 2026-10-01\n---\n"
        (td / "g1.md").write_text(meta % 1 + sent + "\n")
        (td / "g2.md").write_text(meta % 2 + "# G2\nid: G2 · group: G · status: active · tags: decomp,firewall · origin: kit\n")
        (td / "g1.md").write_text(meta % 1 + sent + "\n# G1\nid: G1 · group: G · status: active · tags: decomp,firewall · origin: kit\n")
        (td / "gen.md").write_text("*Generated by x.py; do not edit by hand.*\n\n%s\n" % sent)
        ok &= lint_dupes([td / "g1.md", td / "g2.md", td / "gen.md"], td) == []       # front matter, generated index
    ok &= lint_scope("---\nid: X4\nnote: BFM\n---\nPY = /x/orca-mmx6/bin/python3\nrules X4 and X6 apply.\n") == []
    return common.self_test_banner("fetch_refs", ok)


if __name__ == "__main__":
    sys.exit(main())
