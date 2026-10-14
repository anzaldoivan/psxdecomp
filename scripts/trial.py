#!/usr/bin/env python3
"""trial.py — a helper that takes out of a C file what the match does not need (psxdecomp's docs/ops/psxdecomp-floor.md, "Trials").

    trial.py FILE [--func NAME] [--repo DIR]
                                          take each register pin and each empty asm statement of the file's functions out
                                          in turn and ask the game's probe (`[trial] probe` of the record: exit 0 match,
                                          1 no match, 2 or more an error) whether the function still matches. What the
                                          match does not need is gone. What it needs gets a `// !FAKE: <reason>` line
    trial.py --self-test

A crutch is a register pin or an empty asm statement (a barrier): a construct that forces the compiler and says nothing
about the game. The trial takes each one out in turn and asks the game's probe (`[trial] probe` of the record) whether
the function still matches. It edits bytes: what it does not change comes back as it went in (the encoding, the line
ends). Nothing records a trial and no check asks for one: the marker is the record.

It runs beside the floor tool and reads the crutches and the record through it: scripts/trial.py beside
scripts/floor.py, and tools/psxd_trial.py beside tools/psxd_floor.py in a game whose record names `[trial] probe`
(/psxdecomp:upgrade delivers it there). It uses the standard library only, and it writes the source file it is given.
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and os.name == "posix" and not sys.flags.isolated and sys.executable and os.path.isfile(__file__):
    # Start again in isolated mode: a module beside this file or on PYTHONPATH never stands in for the standard library.
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])

import argparse
import bisect
import importlib.util
import pathlib
import re
import subprocess
import tempfile


def _floor():
    """The floor tool beside this file, loaded by its path: floor.py here, psxd_floor.py in a game."""
    me = pathlib.Path(__file__).resolve()
    path = me.with_name(me.name.replace("trial", "floor"))
    if not path.is_file():
        raise SystemExit("TRIAL FAIL no %s beside %s" % (path.name, me.name))
    spec = importlib.util.spec_from_file_location("psxd_floor_of_trial", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


floor = _floor()


TRIAL_ENV = ("PSXD_TRIAL_FILE", "PSXD_TRIAL_FUNC", "PSXD_TRIAL_PATH")
PROBE_SECONDS = 600

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def crutches(rel: str, text: str) -> list[dict]:
    """The crutches of one C file, in order: {kind `pin`|`barrier`, id, func (SCOPE outside a function), line, a, b
    (the span that `drop` removes), keep (what it leaves; None for a pin whose clause this tool cannot read), reason
    (of its marker, None with none), mark (the line of that marker)}. Two crutches never share one marker."""
    scan = floor.scan_file(rel, text)
    starts = [a for _, a, _ in scan["extents"]]
    seen: dict[tuple, int] = {}
    out = []
    for c in floor._crutches(text, floor.PREPROC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), floor.strip(text))):
        c = dict(c)
        i = bisect.bisect_right(starts, c["a"]) - 1
        c["func"] = scan["extents"][i][0] if i >= 0 and c["a"] < scan["extents"][i][2] else floor.SCOPE
        n = seen[(c["func"], c["name"])] = seen.get((c["func"], c["name"]), 0) + 1
        c["id"] = c["name"] + (":%d" % n if c["kind"] != "pin" else "#%d" % n if n > 1 else "")
        out.append(c)
    return out


def drop(text: str, c: dict) -> str:
    """The text without one crutch and without its marker. A pin loses its `asm("$n")` clause and nothing else:
    `register T x asm("$n")` becomes `register T x`, whatever stands before the name. A barrier goes with its line
    when nothing else stands on it."""
    lines = (text[:c["a"]] + c["keep"] + text[c["b"]:]).split("\n")
    if c["kind"] == "barrier" and not lines[c["line"]].strip():
        lines[c["line"]] = None
    if c["mark"] is not None:
        left = _COMMENT.sub(lambda m: "" if "!FAKE:" in m.group(0) else m.group(0), lines[c["mark"]] or "").rstrip()
        lines[c["mark"]] = left if left.strip() else None
    return "\n".join(l for l in lines if l is not None)


def mark(text: str, c: dict, reason: str) -> str:
    """The text with a `// !FAKE: <reason>` line of its own above a crutch, in the place of a marker with no reason."""
    lines = text.split("\n")
    if c["mark"] is not None:
        left = _COMMENT.sub(lambda m: "" if "!FAKE:" in m.group(0) else m.group(0), lines[c["mark"]]).rstrip()
        lines[c["mark"]] = left if left.strip() else None
    at = lines[c["line"]]
    lines[c["line"]] = "%s// !FAKE: %s\n%s" % (at[:len(at) - len(at.lstrip())], reason, at)
    return "\n".join(l for l in lines if l is not None)


def probe_of(tree: floor.Tree) -> str | None:
    """The `[trial] probe` command of the record. The record and the scripts it names are protected files."""
    return floor.record_table(tree, "trial").get("probe")


def variant_of(rel: str) -> str:
    """The path of the copy that a probe compiles: beside the tracked file, so its includes and its build rule hold."""
    f = pathlib.PurePosixPath(rel)
    return f.with_name("%s.psxd-trial%s" % (f.stem, f.suffix)).as_posix()


def trial_text(data: bytes):
    """(the text of a source as a trial edits it, the function that gives its bytes back), or a str that says why
    the file cannot be tried. The text is lossless: a byte that is no UTF-8 comes back as it was, and so do CRLF
    line ends. Mixed line ends and a lone CR are refused: no edit could keep them line for line."""
    crlf = b"\r\n" in data
    if b"\r" in data.replace(b"\r\n", b"") or crlf and data.count(b"\r\n") != data.count(b"\n"):
        return "mixed line ends or a lone CR: the trial edits a file line for line, with one kind of line end"
    text = data.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
    return text, lambda t: (t.replace("\n", "\r\n") if crlf else t).encode("utf-8", "surrogateescape")


def run_probe(repo, cmd: str, data: bytes, rel: str, func: str) -> int:
    """Ask the game's probe about one variant of a file (its bytes): 0 the function matches, 1 it does not, 2 the
    probe failed. The variant is a file beside the tracked one, so the tracked file is never the one that is
    compiled; a probe that changes the tracked file has failed, and so has one whose copy would stand on a file.
    The command gets three values, as `{file}`, `{func}` and `{path}` in its text or as three more arguments: the
    file to compile, the function, and the tracked path that the file stands for."""
    src = pathlib.Path(repo) / rel
    variant = pathlib.Path(repo) / variant_of(rel)
    if variant.exists() or variant.is_symlink():
        return 2
    before = src.read_bytes() if src.is_file() else None
    env = dict(os.environ, **dict(zip(TRIAL_ENV, (str(variant), func, rel))))
    line = cmd
    for key, var in zip(("{file}", "{func}", "{path}"), TRIAL_ENV):
        line = line.replace(key, '"$%s"' % var)
    if line == cmd:
        line += ' "$%s" "$%s" "$%s"' % TRIAL_ENV
    try:
        variant.write_bytes(data)
        r = subprocess.run(line, shell=True, cwd=str(repo), env=env, capture_output=True, text=True, timeout=PROBE_SECONDS)
        if (src.read_bytes() if src.is_file() else None) != before:
            return 2
        return r.returncode if r.returncode in (0, 1) else 2
    except (OSError, subprocess.TimeoutExpired):
        return 2
    finally:
        try:
            variant.unlink()
        except OSError:
            pass


def trial_function(text: str, rel: str, func: str, ask) -> tuple[str | None, dict]:
    """(the text with what the match does not need taken out and each survivor marked, the counts) for one function.
    `ask(text) -> 0|1|2` is the probe. None when the function cannot be tried: it does not match as it is, the probe
    answers otherwise for a comment (a control), or the probe failed."""
    mine = lambda t: [c for c in crutches(rel, t) if c["func"] == func and c["kind"] != "goto"]  # noqa: E731
    stats = {"tried": 0, "removed": 0, "kept": 0, "probes": 0, "why": ""}

    def probe(t):
        stats["probes"] += 1
        return ask(t)

    odd = [c for c in mine(text) if c["keep"] is None]
    if odd:
        stats["why"] = ("line %d: the tool cannot read the `asm(\"…\")` clause of this pin (one string, in one pair of "
                        "brackets), so it cannot try it" % (odd[0]["line"] + 1))
        return None, stats
    rc = probe(text)
    if rc != 0:
        stats["why"] = "it does not match as it is" if rc == 1 else "the probe failed (exit 2 or more, or it changed the tracked file)"
        return None, stats
    first = mine(text)[0]
    stats["tried"] = len(mine(text))
    lines = text.split("\n")
    lines.insert(first["line"], "/* psxd trial: a comment changes no code */")
    if probe("\n".join(lines)) != 0:                   # the control: a probe that a comment moves proves nothing
        stats["why"] = "the probe gives another answer for a comment: it does not compile the file it is given"
        return None, stats
    while True:
        i, went = 0, False
        while i < len(mine(text)):
            without = drop(text, mine(text)[i])
            rc = probe(without)
            if rc == 2:                            # an error is no `kept`: nothing was learned about this crutch
                stats["why"] = "the probe failed (exit 2 or more) on the text without %s" % mine(text)[i]["id"]
                return None, stats
            if rc == 0:
                text, went = without, True
                stats["removed"] += 1
            else:
                i += 1
        if not went or not mine(text):                 # a crutch that left can free another one: once more
            break
    for i in range(len(mine(text))):
        c = mine(text)[i]
        if not floor.reason_ok(c["reason"]):
            text = mark(text, c, "%s: the function does not match without it (trial)" % c["id"])
    stats["kept"] = len(mine(text))
    return text, stats


def cmd_trial(repo, file: str | None, func: str | None = None) -> int:
    """`trial FILE [--func NAME]`: try each crutch of a file's functions (of one function) and write the file."""
    repo = pathlib.Path(repo)
    tree = floor.Tree(repo)
    cmd = probe_of(tree)
    if not cmd:
        print("TRIAL FAIL no [trial] probe in %s: the command that says whether one function of a file still matches "
              "(exit 0 match, 1 no match, 2 or more an error)" % floor.RECORD)
        return 1
    try:
        rel = pathlib.Path(repo / file).resolve().relative_to(repo.resolve()).as_posix() if file else ""
    except ValueError:                                 # a path outside the repository
        rel = ""
    data = tree.raw(rel) if rel else None
    if data is None:
        print("TRIAL FAIL %s: no file of this repository (`trial <file> [--func <name>]`)" % (file or "no file"))
        return 1
    lossless = trial_text(data)
    if isinstance(lossless, str):
        print("TRIAL FAIL %s: %s" % (rel, lossless))
        return 1
    if (repo / variant_of(rel)).exists() or tree.has(variant_of(rel)):
        print("TRIAL FAIL %s: %s exists, and that is where the trial puts the copy that the probe compiles: move it"
              % (rel, variant_of(rel)))
        return 1
    text, to_bytes = lossless
    funcs = list(dict.fromkeys(c["func"] for c in crutches(rel, text) if c["func"] != floor.SCOPE and c["kind"] != "goto"
                               and func in (None, c["func"])))
    total, bad = {"tried": 0, "removed": 0, "kept": 0, "probes": 0}, 0
    for name in funcs:
        new, stats = trial_function(text, rel, name, lambda t: run_probe(repo, cmd, to_bytes(t), rel, name))
        for k in total:
            total[k] += stats[k]
        if new is None:
            bad += 1
            print("TRIAL FAIL %s %s: %s" % (rel, name, stats["why"]))
            continue
        text = new
        print("TRIAL %s %s: %d tried, %d removed, %d kept" % (rel, name, stats["tried"], stats["removed"], stats["kept"]))
    if to_bytes(text) != data:
        (repo / rel).write_bytes(to_bytes(text))
    if not funcs:
        print("TRIAL OK %s%s: no pin and no barrier in a function" % (rel, " " + func if func else ""))
        return 0
    print("TRIAL %s (%d function(s), %d tried, %d removed, %d kept; %d probe(s))" % (
        "FAIL" if bad else "OK", len(funcs), total["tried"], total["removed"], total["kept"], total["probes"]))
    return 1 if bad else 0


# ---- self-test ------------------------------------------------------------------------------------------------------
C_TRIAL = """#include "common.h"
s32 Sum(s32 *p, s32 n) {
    register s32 i asm("$16");
    register s32 t asm("$17") = 0;
    __asm__("");
    for (i = 0; i < n; i++) {
        t += p[i];
    }
    return t;
}
"""
PROBE_SELF = """import sys
text = open(sys.argv[1], encoding="latin-1", newline="").read()
assert sys.argv[2] and sys.argv[3].endswith(".c"), sys.argv
RULE
"""


def _capture(fn, *args, **kw) -> tuple[int, str]:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kw)
    return rc, buf.getvalue()


def self_test_trials(check) -> None:
    got = crutches("src/sum.c", C_TRIAL)
    check("crutches: two pins and a barrier of one function", [(c["id"], c["func"], c["line"]) for c in got] == [
        ("pin:$16:i", "Sum", 2), ("pin:$17:t", "Sum", 3), ("barrier:1", "Sum", 4)], got)
    check("crutches: a pin leaves its declaration, a barrier leaves nothing", drop(C_TRIAL, got[1]).split("\n")[3] == "    register s32 t = 0;"
          and '__asm__' not in drop(C_TRIAL, got[2]) and drop(C_TRIAL, got[2]).count("\n") == C_TRIAL.count("\n") - 1)
    check("an asm statement that holds an instruction is no barrier", not crutches("src/a.c", 'void A(void) {\n    __asm__("nop");\n}\n'))
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td).resolve()
        floor._git(repo, "init", "--quiet")
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        rule = lambda body: put("tools/probe.py", PROBE_SELF.replace("RULE", body))  # noqa: E731
        trial = lambda *a, **kw: _capture(cmd_trial, repo, *a, **kw)  # noqa: E731
        put("src/sum.c", C_TRIAL)
        put(floor.RECORD, '[psxdecomp]\nversion = "0.6.0"\n')
        rc, out = trial("src/sum.c")
        check("trial: no probe is a refusal", rc == 1 and "TRIAL FAIL no [trial] probe in config/psxdecomp.toml" in out, out)
        put(floor.RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[trial]\nprobe = '%s tools/probe.py'\n" % sys.executable)
        floor._git(repo, "add", "-A")
        rule("sys.exit(1)")
        rc, out = trial("src/sum.c")
        check("trial: a function that does not match is not tried", rc == 1 and "TRIAL FAIL src/sum.c Sum: it does not match as it is" in out
              and (repo / "src/sum.c").read_text() == C_TRIAL, out)
        rule("sys.exit(1 if 'psxd trial' in text else 0)")
        rc, out = trial("src/sum.c")
        check("trial: the control: a probe that a comment moves", rc == 1 and "the probe gives another answer for a comment" in out, out)
        rule("sys.exit(3 if '$16' not in text else 0)")
        rc, out = trial("src/sum.c")
        check("trial: a probe that fails stops the trial", rc == 1 and "the probe failed (exit 2 or more)" in out
              and (repo / "src/sum.c").read_text() == C_TRIAL, out)
        rule("sys.exit(0 if 'asm(\"$16\")' in text else 1)")
        rc, out = trial("src/sum.c")
        text = (repo / "src/sum.c").read_text()
        check("trial: what the match needs stays, with a reason; the rest is gone", rc == 0 and
              "TRIAL src/sum.c Sum: 3 tried, 2 removed, 1 kept\n" in out and out.endswith("TRIAL OK (1 function(s), 3 tried, 2 removed, "
              "1 kept; 6 probe(s))\n") and text == C_TRIAL.replace('    register s32 t asm("$17") = 0;\n    __asm__("");\n', "    register s32 t = 0;\n")
              .replace("    register s32 i", "    // !FAKE: pin:$16:i: the function does not match without it (trial)\n    register s32 i"), out + text)
        check("trial: no file is left beside the source, and no ledger is written", sorted(x.name for x in (repo / "src").iterdir()) == ["sum.c"]
              and sorted(x.name for x in (repo / "config").iterdir()) == ["psxdecomp.toml"])
        check("the count's view: a marked pin", floor.file_debt("src/sum.c", text) == {"pin": 1})
        check("trial: a second run changes nothing", trial("src/sum.c")[0] == 0 and (repo / "src/sum.c").read_text() == text)
        put("src/sum.c", text.replace("// !FAKE: pin:$16:i: the function does not match without it (trial)", "// !FAKE:"))
        check("a marker with no reason is an unmarked pin", floor.file_debt("src/sum.c", (repo / "src/sum.c").read_text()) == {"pin": 1, "pin-unmarked": 1})
        rc, out = trial("src/sum.c", "Sum")
        check("trial --func writes the reason again", rc == 0 and (repo / "src/sum.c").read_text() == text, out)
        put(floor.RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[trial]\nprobe = '%s tools/probe.py {file} {func} {path}'\n" % sys.executable)
        check("trial: the command may name its three values", trial("src/sum.c")[0] == 0 and (repo / "src/sum.c").read_text() == text)
        # a crutch that needs another one: the second pass
        put("src/sum.c", C_TRIAL)
        rule("sys.exit(0 if ('asm(\"$16\")' in text or 'asm(\"$17\")' not in text) else 1)")
        rc, out = trial("src/sum.c")
        check("trial: a pin that only another pin needed goes in the second pass", rc == 0 and "0 kept" in out
              and "asm" not in (repo / "src/sum.c").read_text(), out)
        rc, out = trial("src/sum.c")
        check("trial: a file with no crutch", (rc, out) == (0, "TRIAL OK src/sum.c: no pin and no barrier in a function\n"), out)
        check("trial: a file that is not there", trial("src/gone.c")[0] == 1)
        # ---- trials as the reference projects run them: each attack on a trial is a control here ----

        def safe(fn, *a, **kw):                        # a crash is an answer of its own, and a wrong one
            try:
                return fn(*a, **kw)
            except Exception as e:
                return "%s: %s" % (type(e).__name__, str(e)[:120])

        bare = 'void A(void) {\n    register k asm("$17");\n    k = 1;\n}\n'
        got = safe(lambda: drop(bare, crutches("src/a.c", bare)[0]))
        check("a pin loses its asm clause and nothing else, so a declaration with no type still compiles",
              got == bare.replace(' asm("$17")', ""), got)
        two = 'void A(void) {\n    register s32 j = 0, k asm("$17");\n    register s32 a asm("$4"), b asm("$5");\n}\n'
        got = safe(lambda: [(c["id"], drop(two, c).split("\n")[c["line"]]) for c in crutches("src/a.c", two)])
        check("each asm clause of a declaration is a pin of its own", got == [
            ("pin:$17:k", "    register s32 j = 0, k;"), ("pin:$4:a", '    register s32 a, b asm("$5");'),
            ("pin:$5:b", '    register s32 a asm("$4"), b;')] and floor.file_debt("src/a.c", two) == {"pin": 3, "pin-unmarked": 3}, got)
        keep16 = "sys.exit(0 if 'asm(\"$16\")' in text else 1)"
        rule(keep16)
        put("src/odd.c", 'void Odd(void) {\n    register s32 a asm("$" "4");\n}\n')
        got = safe(trial, "src/odd.c")
        check("trial: a pin whose clause the tool cannot read is a finding, not a crash and not a skip", isinstance(got, tuple) and got[0] == 1
              and "TRIAL FAIL src/odd.c Odd: " in got[1] and "cannot read" in got[1], got)
        (repo / "src/odd.c").unlink()
        # the bytes of a source are its own: Shift-JIS text and CRLF line ends come back as they went in
        sjis = C_TRIAL.replace("s32 Sum", "/* テスト */\ns32 Sum").replace("\n", "\r\n").encode("shift_jis")
        (repo / "src/sum.c").write_bytes(sjis)
        got = safe(trial, "src/sum.c")
        want = (sjis.replace(b' asm("$17")', b"").replace(b'    __asm__("");\r\n', b"")
                .replace(b"    register s32 i", b"    // !FAKE: pin:$16:i: the function does not match without it (trial)\r\n    register s32 i"))
        check("trial: the bytes it does not change stay (Shift-JIS, CRLF)", isinstance(got, tuple) and got[0] == 0
              and (repo / "src/sum.c").read_bytes() == want, (got, (repo / "src/sum.c").read_bytes()[:160]))
        (repo / "src/sum.c").write_bytes(C_TRIAL.encode().replace(b"    return t;\n", b"    return t;\r\n"))
        got = safe(trial, "src/sum.c")
        check("trial: mixed line ends are refused, the file stays", isinstance(got, tuple) and got[0] == 1 and "line ends" in got[1]
              and b"return t;\r\n" in (repo / "src/sum.c").read_bytes(), got)
        # the copy that the probe compiles never stands on a file, and a path outside the repository is no crash
        put("src/sum.c", C_TRIAL)
        put("src/sum.psxd-trial.c", "int tracked;\n")
        got = safe(trial, "src/sum.c")
        check("trial: a file where its copy would go is not written over and not deleted", isinstance(got, tuple) and got[0] == 1
              and "src/sum.psxd-trial.c" in got[1] and (repo / "src/sum.psxd-trial.c").read_text() == "int tracked;\n"
              and (repo / "src/sum.c").read_text() == C_TRIAL, got)
        (repo / "src/sum.psxd-trial.c").unlink(missing_ok=True)
        got = safe(trial, "/etc/hosts")
        check("trial: a path outside the repository is a refusal", isinstance(got, tuple) and got[0] == 1 and "TRIAL FAIL" in got[1], got)
        rule("open(sys.argv[3], 'a').write('/* touched */\\n')\n" + keep16)
        got = safe(trial, "src/sum.c")
        check("trial: a probe that writes the tracked file has failed", isinstance(got, tuple) and got[0] == 1 and "the probe failed" in got[1], got)


def self_test() -> int:
    bad = []

    def check(name, ok, detail=None):
        if not ok:
            bad.append(name)
            print("  FAILED: %s%s" % (name, "" if detail is None else " — %r" % (detail,)))

    self_test_trials(check)
    print("trial %s" % ("SELF-TEST OK" if not bad else "SELF-TEST FAILED (%d)" % len(bad)))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="the source file")
    ap.add_argument("--func", help="one function of the file")
    ap.add_argument("--repo", help="the repository; default: the git checkout that holds the working directory")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.repo is None:
        top = floor._git(".", "rev-parse", "--show-toplevel")
        a.repo = top.stdout.strip() if top.returncode == 0 and top.stdout.strip() else "."
    return cmd_trial(a.repo, a.file, a.func)


if __name__ == "__main__":
    sys.exit(main())
